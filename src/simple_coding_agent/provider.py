"""
LLM provider interface and a deterministic MockProvider for tests.

Source mapping:
  Provider Protocol  <- abstraction over src/services/api/ in Claude Code
  ProviderResponse   <- normalized version of the Anthropic Messages API response
                        (text + tool_use blocks + stop_reason + usage)
  TokenUsage         <- usage object from Messages API
                        (input_tokens, output_tokens, cache_*_input_tokens)
  MockProvider       <- test double; the real AnthropicProvider would call
                        anthropic.messages.create() here.  Out of scope for
                        the replica per PYTHON_REPLICA_SPEC §2 non-goals.

The MockProvider takes a scripted list of ProviderResponse objects and returns
them in order from .call().  It also records each invocation so tests can
inspect what the AgentLoop passed in (system prompt, messages, tools).
"""

from __future__ import annotations

import json
import re
import uuid as _uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .models import ToolCall

_TOOL_ARGUMENT_FIELD_RE = re.compile(
    r'(?:^|,)\s*"(?P<key>[A-Za-z_][A-Za-z0-9_-]*)"\s*:'
)

# ---------------------------------------------------------------------------
# Stop reasons (mirror the Anthropic API stop_reason field)
# ---------------------------------------------------------------------------

STOP_END_TURN: str = "end_turn"
STOP_TOOL_USE: str = "tool_use"
STOP_MAX_TOKENS: str = "max_tokens"


# ---------------------------------------------------------------------------
# Provider exceptions
# ---------------------------------------------------------------------------

class PromptTooLongError(RuntimeError):
    """Provider-neutral context-window overflow error."""


_PROMPT_TOO_LONG_MARKERS: tuple[str, ...] = (
    "context length exceeded",
    "maximum context length",
    "prompt too long",
    "input is too large",
    "input too large",
    "too many tokens",
    "token limit exceeded",
    "tokens exceed",
    "context window",
)


def _is_prompt_too_long_error(exc: BaseException) -> bool:
    """True for known context-window overflow signals from provider SDKs."""
    parts = [str(exc)]
    for attr in ("message", "code", "type"):
        value = getattr(exc, attr, None)
        if value is not None:
            parts.append(str(value))
    text = " ".join(parts).lower()
    return any(marker in text for marker in _PROMPT_TOO_LONG_MARKERS)


def _raise_prompt_too_long_if_known(exc: Exception) -> None:
    if _is_prompt_too_long_error(exc):
        raise PromptTooLongError(str(exc)) from exc


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    """Token counts reported by the API for one call.

    Source: usage object in anthropic Messages API response.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )


# ---------------------------------------------------------------------------
# ProviderResponse
# ---------------------------------------------------------------------------

@dataclass
class ProviderResponse:
    """Normalized assistant response from a provider.

    Shape invariants:
      stop_reason == "end_turn"   -> text is set, tool_calls is empty
      stop_reason == "tool_use"   -> tool_calls is non-empty; text may prefix them
      stop_reason == "max_tokens" -> text or tool_calls may be partial
      A response with no text and no tool_calls is considered malformed
      and the AgentLoop returns status="malformed" without raising.
    """
    text: str | None
    tool_calls: list[ToolCall]
    usage: TokenUsage
    stop_reason: str


@dataclass
class ProviderStreamEvent:
    """One incremental provider event plus the final normalized response."""
    type: str
    text: str | None = None
    response: ProviderResponse | None = None

    @staticmethod
    def text_delta(text: str) -> ProviderStreamEvent:
        return ProviderStreamEvent(type="text_delta", text=text)

    @staticmethod
    def done(response: ProviderResponse) -> ProviderStreamEvent:
        return ProviderStreamEvent(type="done", response=response)


# ---------------------------------------------------------------------------
# ProviderCall — call history entry for tests
# ---------------------------------------------------------------------------

@dataclass
class ProviderCall:
    """One recorded invocation of Provider.call().

    Used in tests to assert that the AgentLoop passed the right system
    prompt, messages, and tools to the provider.
    """
    system: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    response: ProviderResponse


# ---------------------------------------------------------------------------
# Provider Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Provider(Protocol):
    """Duck-typed LLM provider interface.

    Concrete implementations:
      MockProvider       — scripted responses for tests (this file)
      AnthropicProvider  — out of scope; would wrap anthropic.messages.create()
    """

    def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse: ...

    def stream_call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Iterator[ProviderStreamEvent]: ...


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------

class MockProvider:
    """Scripted Provider for deterministic tests.

    Returns responses from the provided script in order.  Raises IndexError
    when the script is exhausted (which usually means a test set up the wrong
    number of responses).  Records each call so tests can inspect what the
    loop sent.
    """

    def __init__(self, script: list[ProviderResponse]) -> None:
        self._script: list[ProviderResponse] = list(script)
        self._index: int = 0
        self._history: list[ProviderCall] = []

    def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        if self._index >= len(self._script):
            raise IndexError(
                f"MockProvider script exhausted "
                f"({len(self._script)} responses, asked for #{self._index + 1})"
            )
        response = self._script[self._index]
        self._index += 1
        self._history.append(ProviderCall(
            system=system,
            messages=list(messages),
            tools=list(tools),
            response=response,
        ))
        return response

    def stream_call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Iterator[ProviderStreamEvent]:
        response = self.call(system=system, messages=messages, tools=tools)
        if response.text:
            yield ProviderStreamEvent.text_delta(response.text)
        yield ProviderStreamEvent.done(response)

    @property
    def history(self) -> list[ProviderCall]:
        """Snapshot copy of call history (mutating it does not affect state)."""
        return list(self._history)

    # ------------------------------------------------------------------
    # Convenience builders for scripted responses
    # ------------------------------------------------------------------

    @staticmethod
    def direct_answer(text: str, usage: TokenUsage | None = None) -> ProviderResponse:
        """Build an end_turn response with text."""
        return ProviderResponse(
            text=text,
            tool_calls=[],
            usage=usage or TokenUsage(),
            stop_reason=STOP_END_TURN,
        )

    @staticmethod
    def tool_call(
        name: str,
        input: dict[str, Any],
        id: str | None = None,
        usage: TokenUsage | None = None,
    ) -> ProviderResponse:
        """Build a tool_use response with a single tool call."""
        return ProviderResponse(
            text=None,
            tool_calls=[ToolCall(
                id=id if id is not None else f"tu_{_uuid.uuid4().hex[:8]}",
                name=name,
                input=input,
            )],
            usage=usage or TokenUsage(),
            stop_reason=STOP_TOOL_USE,
        )

    @staticmethod
    def malformed(usage: TokenUsage | None = None) -> ProviderResponse:
        """Build a response with no text and no tool calls.

        The AgentLoop is expected to return status="malformed" on this.
        """
        return ProviderResponse(
            text=None,
            tool_calls=[],
            usage=usage or TokenUsage(),
            stop_reason=STOP_END_TURN,
        )


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    """Read an SDK object or dict field without depending on generated types."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic-style tool specs to Chat Completions function tools."""
    converted: list[dict[str, Any]] = []
    for tool in tools:
        schema = tool.get("input_schema", {"type": "object", "properties": {}})
        parameters = dict(schema) if isinstance(schema, dict) else {
            "type": "object",
            "properties": {},
        }
        converted.append({
            "type": "function",
            "function": {
                "name": str(tool["name"]),
                "description": str(tool.get("description", "")),
                "parameters": parameters,
            },
        })
    return converted


def _content_text(content: Any) -> str | None:
    """Normalize OpenAI assistant content into plain text."""
    if content is None:
        return None
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            text = _get_value(item, "text")
            if text is None:
                text = _get_value(item, "content")
            if text is not None:
                text_parts.append(str(text))
        return "\n".join(text_parts) or None
    return str(content)


def _encode_arguments(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, separators=(",", ":"))


def _flush_text_message(
    out: list[dict[str, Any]],
    role: str,
    text_parts: list[str],
) -> None:
    text = "\n".join(part for part in text_parts if part)
    if text:
        out.append({"role": role, "content": text})
    text_parts.clear()


def _openai_messages(
    system: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert normalized replica messages to Chat Completions messages."""
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})

    for msg in messages:
        role = str(msg["role"])
        content = msg["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        if role == "assistant" and isinstance(content, list):
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(str(block.get("text", "")))
                elif block_type == "tool_use":
                    tool_calls.append({
                        "id": str(block["id"]),
                        "type": "function",
                        "function": {
                            "name": str(block["name"]),
                            "arguments": _encode_arguments(block.get("input")),
                        },
                    })

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            if text_parts or tool_calls:
                out.append(assistant_msg)
            continue

        if role == "user" and isinstance(content, list):
            text_parts = []
            for block in content:
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(str(block.get("text", "")))
                    continue
                if block_type == "tool_result":
                    _flush_text_message(out, "user", text_parts)
                    out.append({
                        "role": "tool",
                        "tool_call_id": str(block["tool_use_id"]),
                        "content": str(block.get("content", "")),
                    })
            _flush_text_message(out, "user", text_parts)

    return out


def _parse_lenient_flat_tool_arguments(arguments: str) -> dict[str, Any] | None:
    """Best-effort parser for flat tool argument objects.

    Some OpenAI-compatible providers stream long function-call arguments with
    raw newlines or unescaped quotes inside string values.  The normal path
    still requires valid JSON; this fallback only accepts a simple object with
    string-like field names and scalar values.
    """
    text = arguments.strip()
    if not text.startswith("{") or not text.endswith("}"):
        return None

    body = text[1:-1]
    matches = list(_TOOL_ARGUMENT_FIELD_RE.finditer(body))
    if not matches:
        return None

    parsed: dict[str, Any] = {}
    for i, match in enumerate(matches):
        key = match.group("key")
        value_start = match.end()
        value_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        raw_value = body[value_start:value_end].strip()
        if not raw_value:
            return None
        if raw_value.endswith(","):
            raw_value = raw_value[:-1].rstrip()

        try:
            parsed[key] = json.loads(raw_value)
            continue
        except json.JSONDecodeError:
            pass

        if not raw_value.startswith('"'):
            return None

        value = raw_value[1:]
        if value.endswith('"'):
            value = value[:-1]
        parsed[key] = value.replace('\\"', '"').replace("\\\\", "\\")

    return parsed


def _parse_tool_arguments(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        parsed = _parse_lenient_flat_tool_arguments(arguments)
        if parsed is None:
            raise ValueError("OpenAI tool call arguments must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI tool call arguments must decode to an object")
    return parsed


def _parse_openai_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    tool_calls: list[ToolCall] = []
    for raw in raw_tool_calls or []:
        function = _get_value(raw, "function")
        if function is None:
            continue
        arguments = _get_value(function, "arguments", "{}") or "{}"
        parsed = _parse_tool_arguments(str(arguments))
        tool_calls.append(ToolCall(
            id=str(_get_value(raw, "id")),
            name=str(_get_value(function, "name")),
            input=parsed,
        ))
    return tool_calls


@dataclass
class StreamToolParseFailure:
    """Structured description of one tool call whose arguments did not parse.

    Carried by `StreamToolParseError` so callers can show the model exactly
    which call was rejected without printing raw API contents.
    """
    index: int
    id: str
    name: str
    raw_arguments: str
    reason: str


class StreamToolParseError(ValueError):
    """Raised when one or more streamed tool calls have unparseable arguments.

    `partial_tool_calls` holds calls that *did* parse; `failures` holds one
    `StreamToolParseFailure` per broken call. Inherits from `ValueError` so
    existing tests that expect `ValueError` continue to match.
    """

    def __init__(
        self,
        partial_tool_calls: list[ToolCall],
        failures: list[StreamToolParseFailure],
    ) -> None:
        first = failures[0]
        super().__init__(
            f"OpenAI streaming tool call #{first.index} ({first.name!r}) "
            f"had unparseable arguments: {first.reason}"
        )
        self.partial_tool_calls = partial_tool_calls
        self.failures = failures


def _parse_openai_stream_tool_calls(
    tool_call_parts: dict[int, dict[str, str]],
) -> list[ToolCall]:
    """Parse accumulated streaming tool-call fragments.

    Raises `StreamToolParseError` when one or more calls have unparseable
    arguments. The exception carries the calls that *did* parse so callers
    (currently `OpenAIProvider.stream_call`) can surface a controlled
    response instead of crashing the whole stream.
    """
    tool_calls: list[ToolCall] = []
    failures: list[StreamToolParseFailure] = []
    for index in sorted(tool_call_parts):
        parts = tool_call_parts[index]
        raw_arguments = parts.get("arguments") or "{}"
        name = parts.get("name", "")
        call_id = parts.get("id") or f"call_{_uuid.uuid4().hex[:8]}"
        try:
            parsed = _parse_tool_arguments(raw_arguments)
        except ValueError as exc:
            failures.append(StreamToolParseFailure(
                index=index,
                id=call_id,
                name=name,
                raw_arguments=raw_arguments,
                reason=str(exc),
            ))
            continue
        tool_calls.append(ToolCall(id=call_id, name=name, input=parsed))

    if failures:
        raise StreamToolParseError(
            partial_tool_calls=tool_calls,
            failures=failures,
        )
    return tool_calls


def _map_openai_finish_reason(reason: Any, has_tool_calls: bool) -> str:
    if reason == "tool_calls" or has_tool_calls:
        return STOP_TOOL_USE
    if reason == "length":
        return STOP_MAX_TOKENS
    if reason in ("stop", None):
        return STOP_END_TURN
    return str(reason)


def _openai_usage(raw_usage: Any) -> TokenUsage:
    return TokenUsage(
        input_tokens=int(
            _get_value(raw_usage, "prompt_tokens", _get_value(raw_usage, "input_tokens", 0)) or 0
        ),
        output_tokens=int(
            _get_value(
                raw_usage,
                "completion_tokens",
                _get_value(raw_usage, "output_tokens", 0),
            )
            or 0
        ),
    )


class OpenAIProvider:
    """Provider backed by the OpenAI Chat Completions API.

    The rest of the replica keeps its Anthropic-like normalized message and
    tool shapes. This provider is the adapter that translates those shapes to
    OpenAI SDK Chat Completions requests and back to ProviderResponse.
    """

    def __init__(
        self,
        model: str,
        max_tokens: int = 1024,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {max_tokens}")
        self._model = model
        self._max_tokens = max_tokens
        if client is not None:
            self._client = client
            return

        from openai import OpenAI

        if api_key is not None and base_url is not None:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        elif api_key is not None:
            self._client = OpenAI(api_key=api_key)
        elif base_url is not None:
            self._client = OpenAI(base_url=base_url)
        else:
            self._client = OpenAI()

    def _request(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": _openai_messages(system, messages),
        }
        converted_tools = _openai_tools(tools)
        if converted_tools:
            request["tools"] = converted_tools
            request["tool_choice"] = "auto"
        return request

    def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        try:
            completion = self._client.chat.completions.create(
                **self._request(system, messages, tools)
            )
        except Exception as exc:
            _raise_prompt_too_long_if_known(exc)
            raise
        choices = _get_value(completion, "choices", [])
        if not choices:
            return ProviderResponse(
                text=None,
                tool_calls=[],
                usage=_openai_usage(_get_value(completion, "usage")),
                stop_reason=STOP_END_TURN,
            )

        choice = choices[0]
        message = _get_value(choice, "message")
        tool_calls = _parse_openai_tool_calls(_get_value(message, "tool_calls"))
        return ProviderResponse(
            text=_content_text(_get_value(message, "content")),
            tool_calls=tool_calls,
            usage=_openai_usage(_get_value(completion, "usage")),
            stop_reason=_map_openai_finish_reason(
                _get_value(choice, "finish_reason"),
                bool(tool_calls),
            ),
        )

    def stream_call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Iterator[ProviderStreamEvent]:
        try:
            stream = self._client.chat.completions.create(
                **self._request(system, messages, tools),
                stream=True,
            )
        except Exception as exc:
            _raise_prompt_too_long_if_known(exc)
            raise
        text_parts: list[str] = []
        tool_call_parts: dict[int, dict[str, str]] = {}
        finish_reason: Any = None
        usage = TokenUsage()

        try:
            for chunk in stream:
                raw_usage = _get_value(chunk, "usage")
                if raw_usage is not None:
                    usage = _openai_usage(raw_usage)

                choices = _get_value(chunk, "choices", [])
                if not choices:
                    continue

                choice = choices[0]
                delta = _get_value(choice, "delta")
                text = _content_text(_get_value(delta, "content"))
                if text:
                    text_parts.append(text)
                    yield ProviderStreamEvent.text_delta(text)

                for raw_tool_call in _get_value(delta, "tool_calls", []) or []:
                    raw_index = _get_value(raw_tool_call, "index", len(tool_call_parts))
                    index = int(raw_index if raw_index is not None else len(tool_call_parts))
                    parts = tool_call_parts.setdefault(
                        index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    raw_id = _get_value(raw_tool_call, "id")
                    if raw_id:
                        parts["id"] = str(raw_id)
                    function = _get_value(raw_tool_call, "function")
                    if function is None:
                        continue
                    name = _get_value(function, "name")
                    if name:
                        parts["name"] += str(name)
                    arguments = _get_value(function, "arguments")
                    if arguments:
                        parts["arguments"] += str(arguments)

                chunk_finish_reason = _get_value(choice, "finish_reason")
                if chunk_finish_reason is not None:
                    finish_reason = chunk_finish_reason
        except Exception as exc:
            _raise_prompt_too_long_if_known(exc)
            raise

        try:
            tool_calls = _parse_openai_stream_tool_calls(tool_call_parts)
            response = ProviderResponse(
                text="".join(text_parts) or None,
                tool_calls=tool_calls,
                usage=usage,
                stop_reason=_map_openai_finish_reason(finish_reason, bool(tool_calls)),
            )
        except StreamToolParseError as parse_error:
            failure_lines = "\n".join(
                f"- tool_call #{f.index} {f.name!r} (id={f.id}): {f.reason}"
                for f in parse_error.failures
            )
            recovered_text = "".join(text_parts)
            controlled_text = (
                (recovered_text + "\n\n" if recovered_text else "")
                + "The model emitted tool calls whose arguments could not be "
                "parsed; aborting this turn.\n"
                + failure_lines
            )
            # Drop ALL tool calls from this turn (including any that parsed
            # successfully) to avoid partial side effects in the coding agent.
            response = ProviderResponse(
                text=controlled_text,
                tool_calls=[],
                usage=usage,
                stop_reason=STOP_END_TURN,
            )
        yield ProviderStreamEvent.done(response)


__all__ = [
    "STOP_END_TURN",
    "STOP_MAX_TOKENS",
    "STOP_TOOL_USE",
    "MockProvider",
    "OpenAIProvider",
    "PromptTooLongError",
    "Provider",
    "ProviderCall",
    "ProviderResponse",
    "ProviderStreamEvent",
    "TokenUsage",
]
