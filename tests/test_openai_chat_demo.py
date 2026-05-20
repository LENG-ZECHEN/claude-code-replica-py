"""Tests for the hardened ``examples/openai_chat_demo.py``.

These tests verify that the demo is safe-by-default: it cannot reach the
network, cannot leak secret values, and refuses to call the API without
an explicit ``--confirm-api-call`` flag.

The OpenAIProvider import is patched to a sentinel that raises if
instantiated, so any path that would construct a real provider will
fail loudly inside the test.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
_DEMO_PATH = _EXAMPLES_DIR / "openai_chat_demo.py"


def _load_demo_module() -> Any:
    """Import ``examples/openai_chat_demo.py`` as a module for testing."""
    spec = importlib.util.spec_from_file_location("openai_chat_demo", _DEMO_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["openai_chat_demo"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def demo(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    module = _load_demo_module()

    class _ExplodingProvider:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError(
                "OpenAIProvider must not be constructed during these tests"
            )

    monkeypatch.setattr(module, "OpenAIProvider", _ExplodingProvider)
    try:
        yield module
    finally:
        sys.modules.pop("openai_chat_demo", None)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "SIMPLE_AGENT_MODEL",
        "SIMPLE_AGENT_MAX_TOKENS",
        "OPENAI_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_env_file(path: Path, **values: str) -> Path:
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# --no-dotenv guarantees no .env read
# ---------------------------------------------------------------------------

def test_no_dotenv_skips_env_file_even_when_present(
    demo: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = _write_env_file(
        tmp_path / ".env",
        SIMPLE_AGENT_MODEL="should-not-leak",
        DASHSCOPE_API_KEY="sk-should-not-leak",
        OPENAI_BASE_URL="https://should-not-leak.example/v1",
    )

    rc = demo.main(["--no-dotenv", "--env-file", str(env_file), "--dry-run"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "should-not-leak" not in captured.out
    assert "sk-should-not-leak" not in captured.out
    assert "Dotenv:             disabled (--no-dotenv)" in captured.out
    assert "Model:              (missing" in captured.out
    assert os.environ.get("SIMPLE_AGENT_MODEL") is None
    assert os.environ.get("DASHSCOPE_API_KEY") is None
    assert os.environ.get("OPENAI_BASE_URL") is None


def test_no_dotenv_does_not_touch_default_dotenv(
    demo: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Even with the project root .env present, --no-dotenv must skip it."""

    def _explode(_path: Path) -> None:
        raise AssertionError("--no-dotenv must not invoke _load_dotenv")

    monkeypatch.setattr(demo, "_load_dotenv", _explode)

    rc = demo.main(["--no-dotenv", "--dry-run"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "disabled (--no-dotenv)" in captured.out


# ---------------------------------------------------------------------------
# --dry-run exits before any provider call
# ---------------------------------------------------------------------------

def test_dry_run_exits_before_provider_call(
    demo: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = _write_env_file(
        tmp_path / ".env",
        SIMPLE_AGENT_MODEL="dry-run-model",
        OPENAI_API_KEY="sk-test",
        OPENAI_BASE_URL="https://dry-run.example/v1",
    )

    def _explode_run(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("--dry-run must not reach _run()")

    monkeypatch.setattr(demo, "_run", _explode_run)

    rc = demo.main(["--env-file", str(env_file), "--dry-run"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Preflight" in captured.out
    assert "Dry-run: exiting before any network call." in captured.out
    assert "Model:              dry-run-model" in captured.out
    assert "OPENAI_API_KEY:     present" in captured.out
    assert "OPENAI_BASE_URL:    set" in captured.out


def test_dry_run_does_not_leak_secret_values(
    demo: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hidden_value = "opaque-test-value-do-not-print"
    env_file = _write_env_file(
        tmp_path / ".env",
        SIMPLE_AGENT_MODEL="m",
        OPENAI_API_KEY=hidden_value,
        DASHSCOPE_API_KEY=hidden_value + "-dash",
        OPENAI_BASE_URL="https://endpoint.example/v1",
    )

    rc = demo.main(["--env-file", str(env_file), "--dry-run"])

    captured = capsys.readouterr()
    assert rc == 0
    assert hidden_value not in captured.out
    assert hidden_value not in captured.err
    assert "opaque-test-value-do-not-print-dash" not in captured.out
    assert "https://endpoint.example/v1" not in captured.out
    assert "OPENAI_API_KEY:     present" in captured.out
    assert "DASHSCOPE_API_KEY:  present" in captured.out
    assert "OPENAI_BASE_URL:    set" in captured.out


# ---------------------------------------------------------------------------
# Default behavior refuses to call the API
# ---------------------------------------------------------------------------

def test_default_refuses_without_confirm_api_call(
    demo: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = _write_env_file(
        tmp_path / ".env",
        SIMPLE_AGENT_MODEL="m",
        OPENAI_API_KEY="sk-test",
    )

    def _explode_run(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("default mode must not reach _run()")

    monkeypatch.setattr(demo, "_run", _explode_run)

    rc = demo.main(["--env-file", str(env_file)])

    captured = capsys.readouterr()
    assert rc == 3
    assert "--confirm-api-call" in captured.out
    assert "Refusing to call the API" in captured.out


def test_dry_run_overrides_missing_confirm_flag(
    demo: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = _write_env_file(
        tmp_path / ".env",
        SIMPLE_AGENT_MODEL="m",
        OPENAI_API_KEY="sk-test",
    )

    rc = demo.main(["--env-file", str(env_file), "--dry-run"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "--confirm-api-call" not in captured.out


# ---------------------------------------------------------------------------
# Missing model / key reported without calling the API
# ---------------------------------------------------------------------------

def test_missing_model_returns_2_without_calling_api(
    demo: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = demo.main(["--no-dotenv", "--confirm-api-call"])

    captured = capsys.readouterr()
    assert rc == 2
    assert "SIMPLE_AGENT_MODEL" in captured.err


def test_missing_api_key_returns_2_without_calling_api(
    demo: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SIMPLE_AGENT_MODEL", "m")

    rc = demo.main(["--no-dotenv", "--confirm-api-call"])

    captured = capsys.readouterr()
    assert rc == 2
    assert "OPENAI_API_KEY" in captured.err


# ---------------------------------------------------------------------------
# Combined hardening: env-unset + .env-bypass + dry-run is fully safe
# ---------------------------------------------------------------------------

def test_no_dotenv_plus_dry_run_with_real_dotenv_present_is_safe(
    demo: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Simulates the original takeover-discovered issue and proves it is fixed."""
    env_file = _write_env_file(
        tmp_path / ".env",
        SIMPLE_AGENT_MODEL="leaked-model",
        DASHSCOPE_API_KEY="sk-leak",
        OPENAI_BASE_URL="https://leak.example/v1",
    )
    monkeypatch.setattr(demo, "_DEFAULT_DOTENV", env_file)

    rc = demo.main(["--no-dotenv", "--dry-run"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "leaked-model" not in captured.out
    assert "sk-leak" not in captured.out
    assert "leak.example" not in captured.out
    assert os.environ.get("SIMPLE_AGENT_MODEL") is None
    assert os.environ.get("DASHSCOPE_API_KEY") is None
