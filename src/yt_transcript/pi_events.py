"""Bounded Pi 1.0.4 JSONL completion validation."""

import json
from dataclasses import dataclass
from typing import Any, NoReturn

from .errors import classify_pi_failure


@dataclass(frozen=True)
class PiChunkResult:
    text: str
    stop_reason: str
    provider: str | None
    model: str | None
    retry_count: int


class PiEventParser:
    RECORD_LIMIT = 1024 * 1024
    TOTAL_LIMIT = 16 * 1024 * 1024
    TEXT_LIMIT = 1024 * 1024

    def __init__(self):
        self._buffer = bytearray()
        self._total = 0
        self._header = False
        self._settled = False
        self._final: dict[str, Any] | None = None
        self._retries = 0

    def _fail(self, code: str = "PI_PROTOCOL_INVALID") -> NoReturn:
        raise classify_pi_failure(code=code)

    def feed(self, data: bytes) -> None:
        self._total += len(data)
        if self._total > self.TOTAL_LIMIT:
            self._fail("PI_OUTPUT_LIMIT")
        self._buffer.extend(data)
        while b"\n" in self._buffer:
            line, _, remaining = self._buffer.partition(b"\n")
            self._buffer = bytearray(remaining)
            if len(line) > self.RECORD_LIMIT:
                self._fail("PI_OUTPUT_LIMIT")
            try:

                def invalid_constant(value: str) -> NoReturn:
                    raise ValueError("Invalid JSON constant")

                event = json.loads(
                    line.removesuffix(b"\r").decode("utf-8"),
                    parse_constant=invalid_constant,
                )
            except ValueError, UnicodeError, RecursionError:
                self._fail()
            if not isinstance(event, dict):
                self._fail()
            self._event(event)
        if len(self._buffer) > self.RECORD_LIMIT:
            self._fail("PI_OUTPUT_LIMIT")

    def _event(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if not self._header:
            if kind != "session":
                self._fail()
            self._header = True
            return
        if self._settled or kind == "session":
            self._fail()
        if not isinstance(kind, str):
            self._fail()
        entry = event.get("entry")
        if (
            kind == "entry_appended"
            and isinstance(entry, dict)
            and entry.get("type") in ("context_edit", "compaction", "branch_summary")
        ):
            self._fail("PI_CONTEXT_LIMIT")
        if kind.startswith(("compaction_", "summarization_retry_")):
            self._fail("PI_CONTEXT_LIMIT")
        if kind.startswith("tool_execution_") or kind == "bash_execution_update":
            self._fail()
        if kind == "message_update":
            update = event.get("assistantMessageEvent", {})
            if isinstance(update, dict) and str(update.get("type", "")).startswith(
                "toolcall_"
            ):
                self._fail()
        if kind == "turn_end" and event.get("toolResults"):
            self._fail()
        if kind in ("message_start", "message_end", "turn_end"):
            message = event.get("message")
            if not isinstance(message, dict):
                self._fail()
            if message.get("role") in (
                "toolResult",
                "compactionSummary",
                "branchSummary",
                "bashExecution",
            ):
                self._fail(
                    "PI_CONTEXT_LIMIT"
                    if message.get("role") in ("compactionSummary", "branchSummary")
                    else "PI_PROTOCOL_INVALID"
                )
            if message.get("role") == "assistant":
                content = message.get("content")
                if not isinstance(content, list) or any(
                    not isinstance(block, dict) for block in content
                ):
                    self._fail()
                if any(block.get("type") == "toolCall" for block in content):
                    self._fail()
                if kind == "message_start":
                    # A new attempt cannot reuse an earlier completed response.
                    self._final = None
                if kind == "message_end":
                    # Retain output/error evidence only, never thinking or signatures.
                    self._final = {
                        key: message.get(key)
                        for key in ("stopReason", "errorMessage", "provider", "model")
                    }
                    self._final["content"] = [
                        block for block in content if block.get("type") == "text"
                    ]
        if kind == "auto_retry_start":
            self._retries += 1
        if kind == "agent_settled":
            self._settled = True

    def finish(self) -> PiChunkResult:
        if self._buffer or not self._header or not self._settled or self._final is None:
            self._fail()
        message = self._final
        assert message is not None
        reason = message.get("stopReason")
        if reason == "length":
            self._fail("PI_OUTPUT_INCOMPLETE")
        if reason == "aborted":
            self._fail("PI_ABORTED")
        if reason == "error":
            text = message.get("errorMessage", "")
            raise classify_pi_failure(text if isinstance(text, str) else "")
        if reason != "stop":
            self._fail()
        texts = []
        for block in message["content"]:
            if block.get("type") == "text":
                if not isinstance(block.get("text"), str):
                    self._fail()
                texts.append(block["text"])
        text = "".join(texts).strip()
        if len(text.encode("utf-8")) > self.TEXT_LIMIT:
            self._fail("PI_OUTPUT_LIMIT")
        if not text:
            self._fail("PI_OUTPUT_INVALID")
        return PiChunkResult(
            text, reason, message.get("provider"), message.get("model"), self._retries
        )
