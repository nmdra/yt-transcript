"""Safe validation diagnostics with fake completions and no live calls."""

import json

import pytest

from yt_transcript.errors import FormattingError, render_cli_error
from yt_transcript.pi_events import PiEventParser


@pytest.mark.parametrize("text", [None, "", " \n\t "])
def test_settled_empty_response_identifies_completion_without_reasoning(text):
    content = [{"type": "thinking", "thinking": "PRIVATE_REASONING"}]
    if text is not None:
        content.append({"type": "text", "text": text})
    events = [
        {"type": "session"},
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": content,
                "stopReason": "stop",
                "errorMessage": "Bearer PRIVATE_KEY",
            },
        },
        {"type": "agent_settled"},
    ]
    parser = PiEventParser()
    parser.feed(b"".join(json.dumps(event).encode() + b"\n" for event in events))
    with pytest.raises(FormattingError) as caught:
        parser.finish()
    rendered = render_cli_error(caught.value)
    assert "PI_OUTPUT_INVALID" in rendered
    assert "Validation reason: completion_empty_text." in rendered
    assert "PRIVATE_REASONING" not in rendered and "PRIVATE_KEY" not in rendered


def test_pi_completion_lone_surrogate_is_a_safe_protocol_error():
    events = [
        {"type": "session"},
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "PRIVATE_MODEL_TEXT \ud800"}],
                "stopReason": "stop",
            },
        },
        {"type": "agent_settled"},
    ]
    parser = PiEventParser()
    parser.feed(b"".join(json.dumps(event).encode() + b"\n" for event in events))
    with pytest.raises(FormattingError) as caught:
        parser.finish()
    assert caught.value.info.code == "PI_PROTOCOL_INVALID"
    assert "PRIVATE_MODEL_TEXT" not in render_cli_error(caught.value)
