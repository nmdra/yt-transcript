import json

import pytest

from yt_transcript.errors import FormattingError
from yt_transcript.pi_events import PiEventParser


def stream(reason="stop", text="## Café 😀\u2028\u2029", settled=True):
    events = [
        {"type": "session"},
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "private"},
                    {"type": "text", "text": text},
                ],
                "stopReason": reason,
            },
        },
    ]
    if settled:
        events.append({"type": "agent_settled"})
    return b"".join(
        json.dumps(event, ensure_ascii=False).encode() + b"\r\n" for event in events
    )


def test_incremental():
    parser = PiEventParser()
    data = stream(text="## Café 😀\u2028separator\u2029end")
    for byte in data:
        parser.feed(bytes([byte]))
    assert parser.finish().text == "## Café 😀\u2028separator\u2029end"


@pytest.mark.parametrize(
    "reason,code",
    [
        ("length", "PI_OUTPUT_INCOMPLETE"),
        ("error", "PI_FAILED"),
        ("aborted", "PI_ABORTED"),
        ("pending", "PI_PROTOCOL_INVALID"),
        ("toolUse", "PI_PROTOCOL_INVALID"),
        ("deferred", "PI_PROTOCOL_INVALID"),
        ("unknown", "PI_PROTOCOL_INVALID"),
    ],
)
def test_reason(reason, code):
    parser = PiEventParser()
    parser.feed(stream(reason))
    with pytest.raises(FormattingError) as exc:
        parser.finish()
    assert exc.value.info.code == code


@pytest.mark.parametrize(
    "data",
    [
        b"{}\n",
        b"[]\n",
        b"bad\n",
        b'{"type":"session"}\n\xff\n',
        stream(settled=False),
        stream()[:-1],
        stream() + b"{}\n",
    ],
)
def test_invalid(data):
    with pytest.raises(FormattingError):
        parser = PiEventParser()
        parser.feed(data)
        parser.finish()


@pytest.mark.parametrize(
    "kind,code",
    [
        ("compaction_start", "PI_CONTEXT_LIMIT"),
        ("summarization_retry_scheduled", "PI_CONTEXT_LIMIT"),
        ("tool_execution_start", "PI_PROTOCOL_INVALID"),
    ],
)
def test_forbidden(kind, code):
    parser = PiEventParser()
    with pytest.raises(FormattingError) as exc:
        parser.feed(
            json.dumps({"type": "session"}).encode()
            + b"\n"
            + json.dumps({"type": kind}).encode()
            + b"\n"
        )
    assert exc.value.info.code == code


def test_retry_final_only():
    parser = PiEventParser()
    parser.feed(stream("error", "discard", settled=False))
    parser.feed(b'{"type":"auto_retry_start","attempt":1}\n')
    parser.feed(stream(text="final").split(b"\r\n", 1)[1])
    assert parser.finish().text == "final"
    assert parser.finish().retry_count == 1


def test_unfinished_new_assistant_does_not_reuse_previous_completion():
    parser = PiEventParser()
    parser.feed(stream(text="previous", settled=False))
    parser.feed(
        b'{"type":"message_start","message":{"role":"assistant","content":[]}}\n'
        b'{"type":"agent_settled"}\n'
    )
    with pytest.raises(FormattingError) as exc:
        parser.finish()
    assert exc.value.info.code == "PI_PROTOCOL_INVALID"


def test_ignored_thinking_is_not_retained():
    parser = PiEventParser()
    parser.feed(stream())
    assert parser._final is not None
    assert all(block["type"] == "text" for block in parser._final["content"])
    assert "private" not in repr(parser._final)


def test_limits():
    parser = PiEventParser()
    with pytest.raises(FormattingError) as exc:
        parser.feed(b"x" * (parser.RECORD_LIMIT + 1))
    assert exc.value.info.code == "PI_OUTPUT_LIMIT"
