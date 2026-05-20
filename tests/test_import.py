"""Phase 1: minimal import smoke test."""

import simple_coding_agent


def test_package_imports() -> None:
    assert simple_coding_agent.__version__ == "0.1.0"
