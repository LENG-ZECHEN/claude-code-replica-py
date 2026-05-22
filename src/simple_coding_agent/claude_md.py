"""
ClaudeMdLoader: load CLAUDE.md files and inject them into the system prompt.

Source mapping:
  ClaudeMdLoader  <- CLAUDE.md injection in src/utils/claudeMd.ts
                     Reads workspace-level and user-level CLAUDE.md files,
                     then prepends their content to the base system prompt.
"""

from __future__ import annotations

from pathlib import Path

from .trace import NullTracer, Tracer

_DEFAULT_USER_CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"


class ClaudeMdLoader:
    """Load project-level and user-level CLAUDE.md files.

    Results are cached by workspace_path so repeated calls within one
    agent session do not re-read disk.  No invalidation is needed for P6.
    """

    def __init__(
        self,
        *,
        user_claude_path: Path | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._user_claude_path = user_claude_path
        self._cache: dict[Path, str] = {}
        self._tracer: Tracer = tracer or NullTracer()

    def load(self, workspace_path: Path) -> str:
        """Return combined CLAUDE.md content for *workspace_path*.

        Project-level content appears first; user-level content second.
        The two sections are separated by a blank line when both are present.
        Returns an empty string when neither file exists or is readable.
        """
        if workspace_path in self._cache:
            cached = self._cache[workspace_path]
            self._tracer.emit("claude_md", cached=1, chars=len(cached))
            return cached

        parts: list[str] = []
        read_error = False

        project_path = workspace_path / "CLAUDE.md"
        if project_path.exists():
            try:
                parts.append(project_path.read_text(encoding="utf-8"))
            except OSError:
                read_error = True

        user_path = (
            self._user_claude_path
            if self._user_claude_path is not None
            else _DEFAULT_USER_CLAUDE_MD
        )
        if user_path.exists():
            try:
                parts.append(user_path.read_text(encoding="utf-8"))
            except OSError:
                read_error = True

        result = "\n\n".join(parts)
        if not read_error:
            self._cache[workspace_path] = result
        self._tracer.emit(
            "claude_md",
            cached=0,
            chars=len(result),
            read_error=int(read_error),
            sections=len(parts),
        )
        return result


__all__ = ["ClaudeMdLoader"]
