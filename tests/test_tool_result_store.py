"""Phase 4: ToolResultStore tests — written before implementation (TDD)."""

from simple_coding_agent.tool_result_store import (
    DEFAULT_MAX_INLINE_CHARS,
    DEFAULT_TOTAL_BUDGET_CHARS,
    PERSISTED_OUTPUT_TAG,
    PREVIEW_CHARS,
    ContentReplacementState,
    StoredResult,
    ToolResultStore,
)

# --- Constants ---

def test_constants_defined() -> None:
    assert PERSISTED_OUTPUT_TAG == "<persisted-output>"
    assert PREVIEW_CHARS == 2000
    assert DEFAULT_MAX_INLINE_CHARS == 50_000


# --- StoredResult ---

def test_stored_result_fields() -> None:
    r = StoredResult(
        tool_use_id="tc_1",
        path="/tmp/result_tc_1.txt",
        original_size=100_000,
        preview="first 2000 chars...",
    )
    assert r.tool_use_id == "tc_1"
    assert r.path == "/tmp/result_tc_1.txt"
    assert r.original_size == 100_000
    assert r.preview == "first 2000 chars..."


# --- ToolResultStore.should_externalize ---

def test_should_externalize_over_threshold() -> None:
    store = ToolResultStore()
    content = "x" * (DEFAULT_MAX_INLINE_CHARS + 1)
    assert store.should_externalize(content) is True


def test_should_externalize_at_threshold() -> None:
    store = ToolResultStore()
    content = "x" * DEFAULT_MAX_INLINE_CHARS
    assert store.should_externalize(content) is False


def test_should_externalize_under_threshold() -> None:
    store = ToolResultStore()
    assert store.should_externalize("short content") is False


def test_should_externalize_custom_threshold() -> None:
    store = ToolResultStore(max_inline_chars=10)
    assert store.should_externalize("12345678901") is True
    assert store.should_externalize("1234567890") is False


# --- ToolResultStore.make_pointer ---

def test_make_pointer_contains_tag() -> None:
    store = ToolResultStore()
    pointer = store.make_pointer("/tmp/out.txt", original_size=75_000, preview="abc...")
    assert PERSISTED_OUTPUT_TAG in pointer
    assert "/tmp/out.txt" in pointer
    assert "75000" in pointer
    assert "abc..." in pointer


# --- ToolResultStore.process_result (no externalization) ---

def test_process_result_short_content_unchanged() -> None:
    store = ToolResultStore()
    content = "small result"
    out_content, stored = store.process_result("tc_1", content)
    assert out_content == content
    assert stored is None


# --- ToolResultStore.process_result (with externalization) ---

def test_process_result_long_content_externalized(tmp_path: object) -> None:
    store = ToolResultStore(storage_dir=str(tmp_path))
    content = "y" * (DEFAULT_MAX_INLINE_CHARS + 1)
    out_content, stored = store.process_result("tc_2", content)
    assert PERSISTED_OUTPUT_TAG in out_content
    assert stored is not None
    assert stored.tool_use_id == "tc_2"
    assert stored.original_size == len(content)


def test_process_result_file_written(tmp_path: object) -> None:
    import os
    store = ToolResultStore(storage_dir=str(tmp_path))
    content = "z" * (DEFAULT_MAX_INLINE_CHARS + 1)
    _, stored = store.process_result("tc_3", content)
    assert stored is not None
    assert os.path.exists(stored.path)
    with open(stored.path) as f:
        assert f.read() == content


# --- ToolResultStore.retrieve ---

def test_retrieve_stored_result(tmp_path: object) -> None:
    store = ToolResultStore(storage_dir=str(tmp_path))
    content = "w" * (DEFAULT_MAX_INLINE_CHARS + 1)
    _, stored = store.process_result("tc_4", content)
    assert stored is not None
    retrieved = store.retrieve("tc_4")
    assert retrieved == content


def test_retrieve_unknown_id_returns_none() -> None:
    store = ToolResultStore()
    assert store.retrieve("nonexistent") is None


# --- ContentReplacementState ---

def test_replacement_state_records_decision() -> None:
    state = ContentReplacementState()
    state.record("tc_1", "<persisted-output path=...>")
    assert state.has_replacement("tc_1")
    assert state.get_replacement("tc_1") == "<persisted-output path=...>"


def test_replacement_state_unknown_id() -> None:
    state = ContentReplacementState()
    assert not state.has_replacement("unknown")
    assert state.get_replacement("unknown") is None


def test_replacement_state_frozen_after_record() -> None:
    """Once recorded, the same id always returns the same pointer (cache stability)."""
    state = ContentReplacementState()
    state.record("tc_1", "pointer_v1")
    state.record("tc_1", "pointer_v2")  # second record ignored
    assert state.get_replacement("tc_1") == "pointer_v1"


# ---------------------------------------------------------------------------
# GAP A — process_result() idempotency (ContentReplacementState wired in)
# ---------------------------------------------------------------------------

def test_process_result_same_id_returns_same_pointer(tmp_path: object) -> None:
    """Calling process_result twice with the same id returns identical pointer."""
    store = ToolResultStore(storage_dir=str(tmp_path))
    content = "a" * (DEFAULT_MAX_INLINE_CHARS + 1)
    pointer1, stored1 = store.process_result("idem_1", content)
    pointer2, stored2 = store.process_result("idem_1", content)
    assert pointer1 == pointer2
    assert stored1 is not None and stored2 is not None
    assert stored1.path == stored2.path


def test_process_result_second_call_ignores_changed_content(tmp_path: object) -> None:
    """Once externalized, a different content string for the same id still returns
    the original pointer (cache wins — ensures prompt-cache stability)."""
    store = ToolResultStore(storage_dir=str(tmp_path))
    original = "b" * (DEFAULT_MAX_INLINE_CHARS + 1)
    pointer1, _ = store.process_result("idem_2", original)

    different = "c" * (DEFAULT_MAX_INLINE_CHARS + 1)
    pointer2, stored2 = store.process_result("idem_2", different)

    assert pointer2 == pointer1
    assert stored2 is not None
    assert stored2.original_size == len(original)  # original size, not new content size


# ---------------------------------------------------------------------------
# GAP B — process_results_batch() with per-item and total-budget checks
# ---------------------------------------------------------------------------

def test_total_budget_chars_constant() -> None:
    assert DEFAULT_TOTAL_BUDGET_CHARS == 200_000


def test_process_results_batch_empty_returns_empty() -> None:
    store = ToolResultStore()
    assert store.process_results_batch([]) == []


def test_process_results_batch_all_under_limits_unchanged(tmp_path: object) -> None:
    """Items under both thresholds: returned as-is with stored=None."""
    store = ToolResultStore(
        max_inline_chars=100,
        total_budget_chars=500,
        storage_dir=str(tmp_path),
    )
    results = [("a", "x" * 40), ("b", "y" * 50), ("c", "z" * 30)]
    outputs = store.process_results_batch(results)
    assert len(outputs) == 3
    for (out_content, stored), (_, original) in zip(outputs, results):
        assert out_content == original
        assert stored is None


def test_process_results_batch_per_item_threshold_applies(tmp_path: object) -> None:
    """One item over max_inline_chars is externalized; the others stay inline."""
    store = ToolResultStore(
        max_inline_chars=50,
        total_budget_chars=10_000,
        storage_dir=str(tmp_path),
    )
    results = [("small", "x" * 30), ("big", "y" * 60), ("also_small", "z" * 20)]
    outputs = store.process_results_batch(results)

    out_small, stored_small = outputs[0]
    out_big, stored_big = outputs[1]
    out_also_small, stored_also_small = outputs[2]

    assert stored_small is None and out_small == "x" * 30
    assert stored_big is not None and PERSISTED_OUTPUT_TAG in out_big
    assert stored_also_small is None and out_also_small == "z" * 20


def test_process_results_batch_total_budget_externalizes_largest(tmp_path: object) -> None:
    """Items each under max_inline_chars but total over total_budget_chars:
    the largest item(s) are externalized until the total drops to budget."""
    store = ToolResultStore(
        max_inline_chars=100,
        total_budget_chars=200,
        storage_dir=str(tmp_path),
    )
    # Total = 80 + 70 + 60 = 210 > 200; only largest (80) needs externalizing
    results = [
        ("small_a", "a" * 80),
        ("small_b", "b" * 70),
        ("small_c", "c" * 60),
    ]
    outputs = store.process_results_batch(results)

    out_a, stored_a = outputs[0]   # 80 chars — largest, externalized
    out_b, stored_b = outputs[1]   # 70 chars — stays inline
    out_c, stored_c = outputs[2]   # 60 chars — stays inline

    assert stored_a is not None, "largest item should be externalized"
    assert PERSISTED_OUTPUT_TAG in out_a
    assert stored_b is None, "second item should remain inline"
    assert out_b == "b" * 70
    assert stored_c is None, "third item should remain inline"
    assert out_c == "c" * 60


def test_process_results_batch_idempotent_across_calls(tmp_path: object) -> None:
    """Calling process_results_batch twice with the same inputs yields the same pointers."""
    store = ToolResultStore(
        max_inline_chars=50,
        total_budget_chars=10_000,
        storage_dir=str(tmp_path),
    )
    big_content = "x" * 60
    results = [("big_id", big_content)]

    outputs1 = store.process_results_batch(results)
    outputs2 = store.process_results_batch(results)

    assert outputs1[0][0] == outputs2[0][0], "pointer must be identical across calls"
    assert outputs1[0][1] is not None and outputs2[0][1] is not None
    assert outputs1[0][1].path == outputs2[0][1].path
