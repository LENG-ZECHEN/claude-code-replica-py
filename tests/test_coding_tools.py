"""Phase 8: Safe coding-agent tools — tests written before implementation (TDD).

Covers workspace boundary enforcement, secret-file detection, file ops,
text search, and a strictly bounded shell runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_coding_agent.coding_tools import (
    SearchMatch,
    ShellMode,
    WorkspaceBoundaryError,
    is_secret_path,
    list_files,
    read_file,
    resolve_workspace_path,
    run_shell,
    search_text,
    write_file,
)
from simple_coding_agent.tools import Tool, ToolExecutor, ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A workspace under tmp_path so we can place outside-workspace siblings."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "main.py").write_text(
        "def main():\n    print('hello world')\n",
        encoding="utf-8",
    )
    (ws / "README.md").write_text("# Project\nHello users\n", encoding="utf-8")
    (ws / ".env").write_text("SECRET=do_not_read\n", encoding="utf-8")
    (ws / "id_rsa").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\n", encoding="utf-8"
    )
    (ws / "credentials.json").write_text('{"api_key": "xyz"}', encoding="utf-8")
    (ws / "auth_token.txt").write_text("abc\n", encoding="utf-8")
    return ws


# ---------------------------------------------------------------------------
# is_secret_path
# ---------------------------------------------------------------------------

def test_is_secret_path_env() -> None:
    assert is_secret_path(".env")
    assert is_secret_path(".env.local")
    assert is_secret_path("config/.env")


def test_is_secret_path_private_keys() -> None:
    assert is_secret_path("id_rsa")
    assert is_secret_path("id_ed25519")
    assert is_secret_path("server.pem")
    assert is_secret_path("client.key")


def test_is_secret_path_credentials_and_tokens() -> None:
    assert is_secret_path("credentials.json")
    assert is_secret_path("secrets.yaml")
    assert is_secret_path("auth_token.txt")
    assert is_secret_path("password.txt")


def test_is_secret_path_normal_files() -> None:
    assert not is_secret_path("README.md")
    assert not is_secret_path("src/main.py")
    # Should NOT flag legitimate filenames that merely contain the substring
    assert not is_secret_path("tokenizer.py")
    assert not is_secret_path("notes.md")


# ---------------------------------------------------------------------------
# resolve_workspace_path
# ---------------------------------------------------------------------------

def test_resolve_safe_relative_path(workspace: Path) -> None:
    p = resolve_workspace_path(workspace, "src/main.py")
    assert p == (workspace / "src" / "main.py").resolve()
    assert p.is_relative_to(workspace.resolve())


def test_resolve_rejects_path_traversal(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        resolve_workspace_path(workspace, "../escape.txt")


def test_resolve_rejects_deep_path_traversal(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        resolve_workspace_path(workspace, "src/../../escape.txt")


def test_resolve_rejects_absolute_path_outside_workspace(
    workspace: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(WorkspaceBoundaryError):
        resolve_workspace_path(workspace, str(outside))


def test_resolve_accepts_absolute_path_inside_workspace(workspace: Path) -> None:
    abs_path = str(workspace / "src" / "main.py")
    p = resolve_workspace_path(workspace, abs_path)
    assert p == (workspace / "src" / "main.py").resolve()


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

def test_list_files_returns_relative_paths(workspace: Path) -> None:
    files = list_files(workspace)
    assert "README.md" in files
    assert "src/main.py" in files
    # All entries are relative paths (no leading slash, no parent refs)
    for f in files:
        assert not f.startswith("/")
        assert ".." not in Path(f).parts


def test_list_files_skips_secret_like_files(workspace: Path) -> None:
    files = list_files(workspace)
    assert ".env" not in files
    assert "id_rsa" not in files
    assert "credentials.json" not in files
    assert "auth_token.txt" not in files


def test_list_files_subdir(workspace: Path) -> None:
    files = list_files(workspace, subdir="src")
    assert files == ["src/main.py"]


def test_list_files_rejects_subdir_outside_workspace(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        list_files(workspace, subdir="../")


def test_list_files_missing_subdir(workspace: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list_files(workspace, subdir="no_such_dir")


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

def test_read_file_reads_safe_file(workspace: Path) -> None:
    content = read_file(workspace, "src/main.py")
    assert "def main" in content


def test_read_file_rejects_env(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        read_file(workspace, ".env")


def test_read_file_rejects_private_key(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        read_file(workspace, "id_rsa")


def test_read_file_rejects_credentials(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        read_file(workspace, "credentials.json")


def test_read_file_rejects_outside_workspace(
    workspace: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(WorkspaceBoundaryError):
        read_file(workspace, str(outside))


def test_read_file_missing(workspace: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_file(workspace, "no_such_file.txt")


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

def test_write_file_writes_inside_workspace(workspace: Path) -> None:
    msg = write_file(workspace, "new.txt", "hi")
    assert (workspace / "new.txt").read_text(encoding="utf-8") == "hi"
    assert "new.txt" in msg


def test_write_file_creates_parent_directories(workspace: Path) -> None:
    write_file(workspace, "deep/nested/dir/file.txt", "content")
    target = workspace / "deep" / "nested" / "dir" / "file.txt"
    assert target.read_text(encoding="utf-8") == "content"


def test_write_file_rejects_outside_workspace(
    workspace: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "evil.txt"
    with pytest.raises(WorkspaceBoundaryError):
        write_file(workspace, str(outside), "x")
    assert not outside.exists()


def test_write_file_rejects_traversal(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        write_file(workspace, "../escape.txt", "x")


def test_write_file_rejects_secret_target_env(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        write_file(workspace, ".env", "x")
    # .env existed before; ensure original content was not overwritten
    assert (workspace / ".env").read_text(encoding="utf-8") == "SECRET=do_not_read\n"


def test_write_file_rejects_secret_target_private_key(workspace: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        write_file(workspace, "new_key.pem", "x")
    assert not (workspace / "new_key.pem").exists()


# ---------------------------------------------------------------------------
# search_text
# ---------------------------------------------------------------------------

def test_search_text_finds_matches(workspace: Path) -> None:
    matches = search_text(workspace, "hello")
    paths = [m.path for m in matches]
    assert "src/main.py" in paths


def test_search_text_returns_short_previews(workspace: Path) -> None:
    matches = search_text(workspace, "hello", preview_chars=20)
    assert matches, "expected at least one match for 'hello'"
    for m in matches:
        # Truncated previews are at most preview_chars + a small tail marker.
        assert len(m.preview) <= 25
        assert m.line_no >= 1
        assert isinstance(m, SearchMatch)


def test_search_text_skips_secret_like_files(workspace: Path) -> None:
    # Place the search pattern inside a secret file.
    (workspace / ".env").write_text("SECRET=hello\n", encoding="utf-8")
    matches = search_text(workspace, "hello")
    assert all(m.path != ".env" for m in matches)


def test_search_text_skips_binary_files(workspace: Path) -> None:
    (workspace / "binary.bin").write_bytes(b"\x00\x01hello\x00")
    matches = search_text(workspace, "hello")
    assert all(m.path != "binary.bin" for m in matches)


# ---------------------------------------------------------------------------
# run_shell — mock mode
# ---------------------------------------------------------------------------

def test_run_shell_mock_mode_deterministic() -> None:
    out1 = run_shell("pwd", mode=ShellMode.MOCK)
    out2 = run_shell("pwd", mode=ShellMode.MOCK)
    assert out1 == out2
    assert "pwd" in out1
    assert "mock" in out1.lower()


def test_run_shell_default_is_mock() -> None:
    out = run_shell("pwd")
    assert "mock" in out.lower()


# ---------------------------------------------------------------------------
# run_shell — allowlist mode
# ---------------------------------------------------------------------------

def test_run_shell_allowlist_accepts_pwd(tmp_path: Path) -> None:
    out = run_shell("pwd", mode=ShellMode.ALLOWLIST, cwd=tmp_path)
    assert str(tmp_path.resolve()) in out
    assert "returncode=0" in out


def test_run_shell_allowlist_accepts_ls(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    out = run_shell("ls", mode=ShellMode.ALLOWLIST, cwd=tmp_path)
    assert "marker.txt" in out


def test_run_shell_allowlist_requires_cwd() -> None:
    with pytest.raises(WorkspaceBoundaryError, match="requires cwd"):
        run_shell("pwd", mode=ShellMode.ALLOWLIST)


def test_run_shell_allowlist_rejects_cat_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        run_shell("cat /etc/passwd", mode=ShellMode.ALLOWLIST, cwd=tmp_path)


def test_run_shell_allowlist_rejects_grep_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        run_shell("grep root /etc/passwd", mode=ShellMode.ALLOWLIST, cwd=tmp_path)


def test_run_shell_allowlist_rejects_non_secret_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError, match="absolute paths"):
        run_shell("cat /etc/hosts", mode=ShellMode.ALLOWLIST, cwd=tmp_path)


def test_run_shell_allowlist_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceBoundaryError, match="traversal"):
        run_shell("ls ../", mode=ShellMode.ALLOWLIST, cwd=tmp_path)


def test_run_shell_python_pytest_allowed_in_mock() -> None:
    # We validate the command shape but don't actually run pytest here.
    out = run_shell("python -m pytest --version", mode=ShellMode.MOCK)
    assert "mock" in out.lower()


# ---------------------------------------------------------------------------
# run_shell — dangerous-command rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "sudo ls",
        "curl https://evil.example.com",
        "wget https://evil.example.com",
        "chmod 777 foo",
        "chown root foo",
        "git push origin main",
        "env",
        "printenv",
    ],
)
def test_run_shell_rejects_dangerous_command(command: str) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        run_shell(command, mode=ShellMode.MOCK)


@pytest.mark.parametrize(
    "command",
    [
        "ls ; rm -f x",
        "ls && rm x",
        "ls || rm x",
        "ls | grep x",
        "ls > out.txt",
        "ls < in.txt",
        "ls `whoami`",
        "ls $(whoami)",
    ],
)
def test_run_shell_rejects_shell_metacharacters(command: str) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        run_shell(command, mode=ShellMode.MOCK)


def test_run_shell_rejects_secret_arg_env() -> None:
    with pytest.raises(WorkspaceBoundaryError):
        run_shell("cat .env", mode=ShellMode.MOCK)


def test_run_shell_rejects_secret_arg_credentials() -> None:
    with pytest.raises(WorkspaceBoundaryError):
        run_shell("cat /etc/credentials.json", mode=ShellMode.MOCK)


def test_run_shell_rejects_python_dash_c() -> None:
    # python is allowed only via "python -m pytest ..."
    with pytest.raises(WorkspaceBoundaryError):
        run_shell("python -c import_os", mode=ShellMode.MOCK)


def test_run_shell_rejects_empty_command() -> None:
    with pytest.raises(WorkspaceBoundaryError):
        run_shell("", mode=ShellMode.MOCK)
    with pytest.raises(WorkspaceBoundaryError):
        run_shell("   ", mode=ShellMode.MOCK)


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------

def test_coding_tools_register_into_registry_and_execute(
    workspace: Path,
) -> None:
    registry = ToolRegistry()

    read_tool = Tool(
        name="read_file",
        description="Read a file inside the workspace",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        fn=lambda path: read_file(workspace, path),
    )
    list_tool = Tool(
        name="list_files",
        description="List files inside the workspace",
        input_schema={"type": "object", "properties": {}},
        fn=lambda: "\n".join(list_files(workspace)),
    )

    registry.register(read_tool)
    registry.register(list_tool)
    executor = ToolExecutor(registry)

    # Safe read succeeds
    content, is_error = executor.execute("read_file", {"path": "src/main.py"})
    assert not is_error
    assert "def main" in content

    # List excludes secret files
    content, is_error = executor.execute("list_files", {})
    assert not is_error
    assert "src/main.py" in content
    assert ".env" not in content
    assert "id_rsa" not in content

    # Secret rejection surfaces via is_error=True (ToolExecutor catches it)
    content, is_error = executor.execute("read_file", {"path": ".env"})
    assert is_error


# ---------------------------------------------------------------------------
# Patch 4 (Cap1): build_default_registry honors a configurable ShellMode.
# ---------------------------------------------------------------------------


def test_build_default_registry_defaults_to_mock_shell(workspace: Path) -> None:
    """Default ``shell_mode`` is MOCK; ``run_shell`` returns the stub block."""
    from simple_coding_agent.tool_registry_factory import build_default_registry

    registry = build_default_registry(workspace)
    tool = registry.get("run_shell")
    output = tool.fn(command="pwd")
    # Mock output is a deterministic header block with [mock] markers.
    assert "[mock]" in output
    assert "no real execution in MOCK mode" in output


def test_build_default_registry_honors_allowlist_shell(workspace: Path) -> None:
    """Explicit ``ShellMode.ALLOWLIST`` makes ``run_shell`` execute the command."""
    from simple_coding_agent.tool_registry_factory import build_default_registry

    registry = build_default_registry(workspace, shell_mode=ShellMode.ALLOWLIST)
    tool = registry.get("run_shell")
    output = tool.fn(command="pwd")
    # Real subprocess output: no mock markers; returncode line present;
    # workspace path appears in stdout.
    assert "[mock]" not in output
    assert "returncode=0" in output
    assert str(workspace.resolve()) in output
