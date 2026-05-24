"""
P9-M1 / B1: Command-line entry to ProjectMemory.

Lets users populate, inspect, and remove file-backed project memory without
writing Python. Required for the Jaccard ``MemorySelector`` to have anything
to rank during a REPL session.

  simple-agent memory add <type> <id> <body...>
  simple-agent memory list [--type {user,feedback,project,reference}]
  simple-agent memory delete <id>
  simple-agent memory search <keyword>
  simple-agent memory show <id>
  simple-agent memory update <id> <body...>

Storage directory resolution:
  1. ``SIMPLE_AGENT_MEMORY_DIR`` env var (absolute path).
  2. ``<cwd>/.simple-agent/memory/`` -- default; ``ProjectMemory`` will
     ``mkdir(parents=True)`` it.

All guards from ``ProjectMemory`` (secret rejection, path-traversal) surface
as exit code 2 with a human-readable message on stderr. Idempotent deletes
exit 0. The output of ``list`` / ``search`` is one entry per line so it is
easy to grep or pipe.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .memory import MemoryEntry, MemoryType, ProjectMemory

_DEFAULT_STORAGE_RELDIR = Path(".simple-agent") / "memory"
_VALID_TYPES = tuple(t.value for t in MemoryType)


# ---------------------------------------------------------------------------
# Storage resolution
# ---------------------------------------------------------------------------

def _resolve_storage_dir() -> Path:
    """Resolve the memory storage directory from env or workspace default."""
    raw = os.environ.get("SIMPLE_AGENT_MEMORY_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / _DEFAULT_STORAGE_RELDIR).resolve()


def _store() -> ProjectMemory:
    storage = _resolve_storage_dir()
    storage.mkdir(parents=True, exist_ok=True)
    return ProjectMemory(storage_dir=str(storage))


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_add(args: argparse.Namespace) -> int:
    type_str = str(args.type)
    if type_str not in _VALID_TYPES:
        valid = ", ".join(_VALID_TYPES)
        print(
            f"error: unknown type {type_str!r}. Valid types: {valid}.",
            file=sys.stderr,
        )
        return 2

    entry = MemoryEntry(
        name=str(args.name),
        body=" ".join(str(part) for part in args.body),
        type=MemoryType(type_str),
        id=str(args.id),
    )

    try:
        _store().save(entry)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"saved memory {entry.id} ({type_str})")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    entries = _store().all()
    if args.type is not None:
        entries = [e for e in entries if e.type.value == args.type]
    for entry in entries:
        print(f"{entry.id}\t[{entry.type.value}]\t{entry.name}")
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    store = _store()
    try:
        store.delete(str(args.id))
    except ValueError as exc:
        # Invalid id (path traversal) reaches us here.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    entries = _store().search(str(args.keyword))
    for entry in entries:
        print(f"{entry.id}\t[{entry.type.value}]\t{entry.name}")
    return 0


def _cmd_update(args: argparse.Namespace) -> int:
    """Rewrite the body of an existing memory entry, preserving identity.

    Same secret-rejection + path-traversal guards as ``add`` (delegated
    to :meth:`ProjectMemory.save`). Missing ids exit with code 2 so
    callers can distinguish a no-op from a successful update.
    """
    store = _store()
    existing = store.load(str(args.id))
    if existing is None:
        print(f"error: no memory entry with id {args.id!r}", file=sys.stderr)
        return 2
    new_body = " ".join(str(part) for part in args.body)
    updated = MemoryEntry(
        id=existing.id,
        name=existing.name,
        body=new_body,
        type=existing.type,
        tags=list(existing.tags),
        created_at=existing.created_at,
    )
    try:
        store.save(updated)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"updated memory {updated.id}")
    return 0


def _cmd_migrate_format(args: argparse.Namespace) -> int:
    """Convert legacy .json memory entries to .md format (idempotent)."""
    storage = _resolve_storage_dir()
    storage.mkdir(parents=True, exist_ok=True)
    migrated = 0
    for json_path in sorted(storage.glob("*.json")):
        entry_id = json_path.stem
        md_path = storage / f"{entry_id}.md"
        if md_path.exists():
            continue  # already migrated — idempotent
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            entry = MemoryEntry.from_dict(data)
        except Exception as exc:
            print(f"warning: skipping {json_path.name}: {exc}", file=sys.stderr)
            continue
        try:
            md_path.write_text(entry.to_md_text(), encoding="utf-8")
            migrated += 1
        except Exception as exc:
            print(f"warning: could not write {md_path.name}: {exc}", file=sys.stderr)
    print(f"Migrated {migrated} entries. Run again to verify (idempotent).")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    entry = _store().load(str(args.id))
    if entry is None:
        print(f"error: no memory entry with id {args.id!r}", file=sys.stderr)
        return 2
    print(f"id:         {entry.id}")
    print(f"name:       {entry.name}")
    print(f"type:       {entry.type.value}")
    print(f"created_at: {entry.created_at}")
    print(f"tags:       {','.join(entry.tags)}")
    print("---")
    print(entry.body)
    return 0


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simple-agent memory",
        description="Manage file-backed project memory entries.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="Add a memory entry.")
    add.add_argument("type", help=f"Memory type (one of: {', '.join(_VALID_TYPES)}).")
    add.add_argument("id", help="Memory id (slug). Must be [A-Za-z0-9_-]+.")
    add.add_argument(
        "body",
        nargs="+",
        help="Body text. Multiple words are joined with single spaces.",
    )
    add.add_argument(
        "--name",
        default=None,
        help="Display name. Defaults to <id>.",
    )

    listp = sub.add_parser("list", help="List memory entries.")
    listp.add_argument(
        "--type",
        choices=_VALID_TYPES,
        default=None,
        help="Filter by memory type.",
    )

    delp = sub.add_parser("delete", help="Delete a memory entry by id.")
    delp.add_argument("id", help="Memory id to delete.")

    searchp = sub.add_parser("search", help="Substring-search entries by name or body.")
    searchp.add_argument("keyword", help="Case-insensitive substring.")

    showp = sub.add_parser("show", help="Print one memory entry in full.")
    showp.add_argument("id", help="Memory id to show.")

    updatep = sub.add_parser(
        "update", help="Update the body of an existing memory entry."
    )
    updatep.add_argument("id", help="Memory id to update.")
    updatep.add_argument(
        "body",
        nargs="+",
        help="New body text. Multiple words are joined with single spaces.",
    )

    sub.add_parser(
        "migrate-format",
        help="Convert legacy .json entries to .md format (idempotent).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Default name to id when omitted on `add`.
    if args.cmd == "add" and getattr(args, "name", None) is None:
        args.name = args.id

    handler = {
        "add": _cmd_add,
        "list": _cmd_list,
        "delete": _cmd_delete,
        "search": _cmd_search,
        "show": _cmd_show,
        "update": _cmd_update,
        "migrate-format": _cmd_migrate_format,
    }[str(args.cmd)]
    return handler(args)


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
