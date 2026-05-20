"""
Phase 8: Safe coding-agent tools.

Workspace-scoped file operations and a strictly bounded shell runner.

Design goals:
  - Every file operation is rooted at a workspace and refuses to escape it,
    either via ``..`` traversal or via absolute paths pointing outside.
  - Secret-like files (``.env*``, private keys, credentials, token files) are
    refused for both reads and writes, and skipped when listing or searching.
  - ``run_shell`` is bounded by a tiny command allowlist, refuses shell
    metacharacters, refuses arguments that look like secret paths, and runs
    with ``shell=False``. Default mode is MOCK so an agent can be wired up
    without granting real shell access.

The implementation is intentionally minimal and explainable rather than
attempting to mirror any production sandbox; see docs/PYTHON_REPLICA_SPEC.md.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class WorkspaceBoundaryError(Exception):
    """Raised when an operation would escape the workspace or touch a secret.

    Used uniformly across path resolution, file ops, and the shell runner so
    callers (and the ``ToolExecutor``) can convert it into an ``is_error``
    tool result with a single ``except`` clause.
    """


# ---------------------------------------------------------------------------
# Secret-file detection
# ---------------------------------------------------------------------------

# Patterns are anchored to a single basename component. ``is_secret_path``
# scans every component of a path, so e.g. ``config/.env`` is flagged because
# the trailing component matches the first pattern.
_SECRET_BASENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    # ``.env``, ``.env.local``, ``.env.production`` ...
    re.compile(r"^\.env(\..*)?$", re.IGNORECASE),
    # Common ssh / gpg private key basenames
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$"),
    re.compile(r"^\.netrc$"),
    re.compile(r"^\.npmrc$"),
    re.compile(r"^\.pgpass$"),
    # ``secret(s)``, ``credential(s)``, ``password``, ``passwd``, ``apikey``
    # bounded by ``.``, ``_``, ``-`` or string anchors so ``readme.md`` is OK.
    re.compile(
        r"(^|[._-])(secret|credential|password|passwd|apikey)s?([._-]|$)",
        re.IGNORECASE,
    ),
    # ``token`` bounded -- catches ``auth_token.txt`` but not ``tokenizer.py``.
    re.compile(r"(^|[._-])tokens?([._-]|$)", re.IGNORECASE),
)

_SECRET_EXTENSIONS: frozenset[str] = frozenset(
    {".pem", ".key", ".pfx", ".p12", ".asc", ".gpg"}
)


def _basename_is_secret(basename: str) -> bool:
    """Return True if a single path component looks like a secret file."""
    if not basename or basename in (".", ".."):
        return False
    if Path(basename).suffix.lower() in _SECRET_EXTENSIONS:
        return True
    return any(pat.search(basename) for pat in _SECRET_BASENAME_PATTERNS)


def is_secret_path(path: str | Path) -> bool:
    """Return True if *path* refers to a secret-like file by name.

    Every component of *path* is checked, so secret leaves under benign
    directories are still flagged (e.g. ``config/.env``).
    """
    p = Path(str(path))
    return any(
        _basename_is_secret(part)
        for part in p.parts
        if part not in ("/", "")
    )


# ---------------------------------------------------------------------------
# Workspace boundary
# ---------------------------------------------------------------------------


def resolve_workspace_path(root: str | Path, path: str | Path) -> Path:
    """Resolve *path* against *root* and ensure it stays inside the workspace.

    Accepts relative paths joined under *root* and absolute paths that already
    point inside *root*. Rejects anything else with ``WorkspaceBoundaryError``.

    ``Path.resolve`` runs in non-strict mode so the path does not need to
    exist yet -- callers like ``write_file`` rely on this to create new files.
    """
    root_resolved = Path(root).resolve()
    raw = Path(path)
    candidate = raw if raw.is_absolute() else (root_resolved / raw)
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError) as exc:
        raise WorkspaceBoundaryError(f"cannot resolve path: {path!s}") from exc
    if not resolved.is_relative_to(root_resolved):
        raise WorkspaceBoundaryError(
            f"path {path!s} escapes workspace {root_resolved}"
        )
    return resolved


def _ensure_not_secret(rel: Path | str) -> None:
    """Raise ``WorkspaceBoundaryError`` if *rel* refers to a secret-like file."""
    if is_secret_path(rel):
        raise WorkspaceBoundaryError(
            f"refusing to touch secret-like path: {rel!s}"
        )


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


def list_files(
    root: str | Path,
    subdir: str | None = None,
    max_results: int = 1000,
) -> list[str]:
    """List files under the workspace as POSIX-style relative paths.

    Skips secret-like files and directories, does not follow symlinks, and
    caps results at ``max_results``. The optional ``subdir`` must resolve
    inside the workspace; otherwise ``WorkspaceBoundaryError`` is raised.
    """
    root_resolved = Path(root).resolve()
    start = (
        resolve_workspace_path(root_resolved, subdir)
        if subdir is not None
        else root_resolved
    )
    if not start.exists():
        raise FileNotFoundError(f"not found: {start}")
    if not start.is_dir():
        raise NotADirectoryError(f"not a directory: {start}")

    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        # Prune secret-named directories in-place so os.walk skips them.
        dirnames[:] = sorted(d for d in dirnames if not _basename_is_secret(d))
        for fname in sorted(filenames):
            if _basename_is_secret(fname):
                continue
            full = Path(dirpath) / fname
            if full.is_symlink():
                continue
            try:
                rel = full.relative_to(root_resolved)
            except ValueError:
                continue
            results.append(rel.as_posix())
            if len(results) >= max_results:
                return results
    return results


# ---------------------------------------------------------------------------
# read_file / write_file
# ---------------------------------------------------------------------------


def read_file(root: str | Path, path: str) -> str:
    """Read a UTF-8 text file inside the workspace.

    Raises ``WorkspaceBoundaryError`` if *path* escapes the workspace or
    refers to a secret-like file. Raises ``FileNotFoundError`` if the file
    does not exist.
    """
    root_resolved = Path(root).resolve()
    full = resolve_workspace_path(root_resolved, path)
    rel = full.relative_to(root_resolved)
    _ensure_not_secret(rel)
    return full.read_text(encoding="utf-8")


def write_file(root: str | Path, path: str, content: str) -> str:
    """Write *content* to a file inside the workspace.

    Creates parent directories as needed. Refuses targets that escape the
    workspace or look like secret files. Returns a short confirmation string
    suitable for inclusion in a tool result.
    """
    root_resolved = Path(root).resolve()
    full = resolve_workspace_path(root_resolved, path)
    rel = full.relative_to(root_resolved)
    _ensure_not_secret(rel)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {rel.as_posix()}"


# ---------------------------------------------------------------------------
# search_text
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchMatch:
    """One hit returned by ``search_text``."""

    path: str
    line_no: int
    preview: str


_BINARY_SNIFF_BYTES: int = 1024


def _looks_binary(path: Path) -> bool:
    """Heuristic binary check: a null byte in the first ``_BINARY_SNIFF_BYTES``."""
    try:
        with open(path, "rb") as fh:
            sample = fh.read(_BINARY_SNIFF_BYTES)
    except OSError:
        return True
    return b"\x00" in sample


def search_text(
    root: str | Path,
    pattern: str,
    subdir: str | None = None,
    max_results: int = 100,
    preview_chars: int = 120,
) -> list[SearchMatch]:
    """Plain-substring search across workspace text files.

    Skips secret files (via ``list_files``) and binary files (null-byte
    sniff). Each preview is truncated to ``preview_chars`` with a short
    ``...`` tail so the result stays cheap to inline.
    """
    root_resolved = Path(root).resolve()
    candidates = list_files(root_resolved, subdir=subdir, max_results=10_000)
    matches: list[SearchMatch] = []
    for rel in candidates:
        full = root_resolved / rel
        if _looks_binary(full):
            continue
        try:
            with open(full, encoding="utf-8") as fh:
                for line_no, line in enumerate(fh, start=1):
                    if pattern in line:
                        text = line.rstrip("\n")
                        if len(text) > preview_chars:
                            text = text[:preview_chars] + "..."
                        matches.append(
                            SearchMatch(path=rel, line_no=line_no, preview=text)
                        )
                        if len(matches) >= max_results:
                            return matches
        except (UnicodeDecodeError, OSError):
            continue
    return matches


# ---------------------------------------------------------------------------
# run_shell
# ---------------------------------------------------------------------------


class ShellMode(Enum):
    """Execution mode for ``run_shell``.

    ``MOCK`` returns a deterministic string without invoking any process --
    safe to wire into an LLM agent for demos. ``ALLOWLIST`` actually runs the
    command with ``shell=False`` after the same safety checks.
    """

    MOCK = "mock"
    ALLOWLIST = "allowlist"


_ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {"pwd", "ls", "cat", "grep", "python"}
)

# Ordered so multi-char metacharacters are detected first in error messages.
_BLOCKED_METACHARS: tuple[str, ...] = (
    "&&", "||", "$(", ";", "|", ">", "<", "`",
)

_DEFAULT_TIMEOUT_SECONDS: float = 5.0


def is_safe_command(command: str) -> bool:
    """Return True if *command* passes the same safety checks as ``run_shell``."""
    try:
        _validate_command(command)
    except WorkspaceBoundaryError:
        return False
    return True


def _validate_command(command: str) -> list[str]:
    """Validate *command* and return its parsed argv on success.

    Rejects:
      - empty or whitespace-only commands
      - shell metacharacters (``; && || | > < ` $(``)
      - base commands not on the allowlist
      - ``python`` invocations that are not ``python -m pytest ...``
      - positional arguments that look like secret paths
    """
    if not command or not command.strip():
        raise WorkspaceBoundaryError("empty command")

    for meta in _BLOCKED_METACHARS:
        if meta in command:
            raise WorkspaceBoundaryError(
                f"shell metacharacter not allowed: {meta!r}"
            )

    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise WorkspaceBoundaryError(f"cannot parse command: {exc}") from exc

    if not argv:
        raise WorkspaceBoundaryError("empty command")

    base = argv[0]
    if base not in _ALLOWED_COMMANDS:
        raise WorkspaceBoundaryError(f"command not on allowlist: {base!r}")

    if base == "python" and (
        len(argv) < 3 or argv[1] != "-m" or argv[2] != "pytest"
    ):
        raise WorkspaceBoundaryError(
            "python is only allowed via 'python -m pytest ...'"
        )

    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        if is_secret_path(arg):
            raise WorkspaceBoundaryError(
                f"argument refers to a secret-like path: {arg!r}"
            )

    return argv


def _workspace_path_args(argv: list[str]) -> list[str]:
    """Return argv entries that should resolve inside cwd in ALLOWLIST mode."""
    base = argv[0]
    if base in {"cat", "ls"}:
        return [arg for arg in argv[1:] if not arg.startswith("-")]

    if base == "grep":
        positional = [arg for arg in argv[1:] if not arg.startswith("-")]
        # First positional is the pattern; any remaining positionals are paths.
        return positional[1:]

    return []


def _validate_allowlist_workspace(argv: list[str], cwd: str | Path | None) -> Path:
    """Require cwd and ensure shell path args stay inside it."""
    if cwd is None:
        raise WorkspaceBoundaryError("ALLOWLIST mode requires cwd")

    root = Path(cwd).resolve()
    if not root.exists():
        raise FileNotFoundError(f"not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")

    for arg in _workspace_path_args(argv):
        raw = Path(arg)
        if raw.is_absolute():
            raise WorkspaceBoundaryError(
                f"absolute paths are not allowed in ALLOWLIST mode: {arg!r}"
            )
        if ".." in raw.parts:
            raise WorkspaceBoundaryError(
                f"path traversal is not allowed in ALLOWLIST mode: {arg!r}"
            )
        resolve_workspace_path(root, raw)

    return root


def run_shell(
    command: str,
    mode: ShellMode = ShellMode.MOCK,
    cwd: str | Path | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Run *command* under the requested mode after the safety checks.

    Validation runs in both modes so the agent learns the same boundary
    regardless of whether it has real shell access yet. ``ALLOWLIST`` mode
    invokes ``subprocess.run`` with ``shell=False`` and captures output.
    """
    argv = _validate_command(command)

    if mode is ShellMode.MOCK:
        return (
            f"[mock] $ {command}\n"
            f"[mock] argv={argv}\n"
            f"[mock] returncode=0\n"
            f"[mock] (no real execution in MOCK mode)"
        )

    root = _validate_allowlist_workspace(argv, cwd)

    try:
        completed = subprocess.run(
            argv,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkspaceBoundaryError(
            f"command timed out after {timeout}s: {command}"
        ) from exc
    except FileNotFoundError as exc:
        raise WorkspaceBoundaryError(
            f"executable not found: {argv[0]}"
        ) from exc

    return (
        f"$ {command}\n"
        f"returncode={completed.returncode}\n"
        f"--- stdout ---\n{completed.stdout}"
        f"--- stderr ---\n{completed.stderr}"
    )


__all__ = [
    "SearchMatch",
    "ShellMode",
    "WorkspaceBoundaryError",
    "is_safe_command",
    "is_secret_path",
    "list_files",
    "read_file",
    "resolve_workspace_path",
    "run_shell",
    "search_text",
    "write_file",
]
