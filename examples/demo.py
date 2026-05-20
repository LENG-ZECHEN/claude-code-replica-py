"""
Phase 10: Runnable MockProvider demo for simple_coding_agent.

Run:
    python examples/demo.py

After ``pip install -e .[dev]`` the same demo is exposed as a console script:
    simple-agent

This wrapper delegates to ``simple_coding_agent.cli.main`` so both entry
paths produce identical output. No LLM call is made and no API key is
required; every file operation is confined to a temporary workspace.
"""

from __future__ import annotations

from simple_coding_agent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
