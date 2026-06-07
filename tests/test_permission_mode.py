"""Tests for PermissionMode enum, PlanModeAttachment, and ENTER_PLAN_MODE_TEACHING_TEXT.

plan-surface M2 — permission.py basics.

Covers:
  - PermissionMode enum values + str representation (1)
  - PlanModeAttachment frozen / immutable / hash-stable (1)
  - ENTER_PLAN_MODE_TEACHING_TEXT contains "DO NOT write or edit any files yet" (1)
"""
from __future__ import annotations

import pytest

from simple_coding_agent.permission import (
    ENTER_PLAN_MODE_TEACHING_TEXT,
    PermissionMode,
    PlanModeAttachment,
)


def test_permission_mode_values() -> None:
    assert PermissionMode.NORMAL == "normal"
    assert PermissionMode.PLAN == "plan"
    assert str(PermissionMode.NORMAL) == "normal"
    assert str(PermissionMode.PLAN) == "plan"


def test_plan_mode_attachment_frozen_and_hash_stable() -> None:
    a1 = PlanModeAttachment()
    a2 = PlanModeAttachment()
    assert a1 == a2
    assert hash(a1) == hash(a2)
    # Frozen dataclass rejects attribute assignment.
    with pytest.raises(AttributeError):  # FrozenInstanceError subclasses AttributeError
        a1.foo = "bar"  # type: ignore[attr-defined]


def test_enter_plan_mode_teaching_text_contains_do_not_write() -> None:
    assert "DO NOT write or edit any files yet" in ENTER_PLAN_MODE_TEACHING_TEXT
