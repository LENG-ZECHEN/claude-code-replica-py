"""P9-M5 / B4: Unit tests for auto_learn cue detection.

Pure-function tests -- no fixtures, no I/O. Each case asserts that the
canonical cue label is returned (or ``None`` when no cue is present),
independently of input length and case.
"""

from __future__ import annotations

from simple_coding_agent.auto_learn import detect_cue, format_hint


def test_detect_cue_chinese_jizhu_returns_canonical_label() -> None:
    assert detect_cue("记住我喜欢用 tabs 缩进") == "记住"


def test_detect_cue_chinese_yihou_returns_canonical_label() -> None:
    assert detect_cue("以后请用 4 个空格缩进") == "以后"


def test_detect_cue_english_dont_apostrophe_variants() -> None:
    assert detect_cue("don't use semicolons") == "don't"
    assert detect_cue("Don't use tabs") == "don't"
    assert detect_cue("don’t add comments") == "don't"


def test_detect_cue_english_prefer_morphological_variants() -> None:
    assert detect_cue("I prefer dark mode") == "prefer"
    assert detect_cue("She prefers async") == "prefer"
    assert detect_cue("their preference is tabs") == "prefer"


def test_detect_cue_returns_none_for_unrelated_text() -> None:
    assert detect_cue("what is the weather today?") is None
    assert detect_cue("") is None
    assert detect_cue("preferential treatment is fine") is None


def test_format_hint_mentions_remember_command_and_cue() -> None:
    rendered = format_hint("记住")
    assert "记住" in rendered
    assert "/remember" in rendered
