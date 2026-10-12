"""All HTTP operations are mocked. No API credits or network are used."""

import io
import json
import urllib.error
from dataclasses import asdict
from email.message import Message
from http.client import HTTPMessage
from types import SimpleNamespace

import pytest

from yt_transcript import formatter
from yt_transcript import openrouter_backend as backend
from yt_transcript.errors import FormattingError


class Response(io.BytesIO):
    status = 200
    headers: dict[str, str] = {}


def payload():
    request = formatter.ChunkRequest(
        "source rules", "no tools", "edit", "caption", "provider/model", 2
    )
    value = asdict(request)
    value.pop("own_process_group")
    value["max_output_tokens"] = 8192
    return value


def response(content: object = "## Edited\n\nCaption.", reason="stop", **message):
    return json.dumps(
        {
            "choices": [
                {
                    "finish_reason": reason,
                    "message": {"role": "assistant", "content": content, **message},
                }
            ]
        }
    ).encode()


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "TEST_KEY_NOT_FOR_OUTPUT")


def test_http_request_is_fixed_and_has_no_fallback(monkeypatch):
    captured = []
    raw = Response(response())
    raw.status = 200
    raw.headers = {}

    def open(request, **kwargs):
        captured.append((request, kwargs))
        return raw

    monkeypatch.setattr(
        backend.urllib.request,
        "build_opener",
        lambda handler: SimpleNamespace(open=open),
    )
    assert backend.complete_http(payload()).startswith("## Edited")
    req, kwargs = captured[0]
    assert req.full_url == backend.ENDPOINT and req.method == "POST"
    assert req.unredirected_hdrs["Authorization"] == "Bearer TEST_KEY_NOT_FOR_OUTPUT"
    assert "Authorization" not in req.headers
    body = json.loads(req.data)
    assert body["provider"] == {
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
    }
    assert body["stream"] is False and body["max_tokens"] == 8192
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert "caption" not in body["messages"][0]["content"]
    assert "<transcript_data>" in body["messages"][1]["content"]
    assert "TEST_KEY_NOT_FOR_OUTPUT" not in req.data.decode()
    assert kwargs == {"timeout": 2}


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "OPENROUTER_AUTH_FAILED"),
        (403, "OPENROUTER_AUTH_FAILED"),
        (402, "OPENROUTER_LIMITED"),
        (429, "OPENROUTER_LIMITED"),
        (302, "OPENROUTER_FAILED"),
        (500, "OPENROUTER_FAILED"),
    ],
)
def test_http_errors_never_read_or_forward_body(monkeypatch, status, code):
    class ErrorBody(io.BytesIO):
        def read(self, *args):
            pytest.fail("HTTP error body must not be read")

    error = urllib.error.HTTPError(
        backend.ENDPOINT, status, "Bearer private", Message(), ErrorBody(b"private")
    )

    def open(*args, **kwargs):
        raise error

    monkeypatch.setattr(
        backend.urllib.request,
        "build_opener",
        lambda handler: SimpleNamespace(open=open),
    )
    with pytest.raises(FormattingError) as exc:
        backend.complete_http(payload())
    assert exc.value.info.code == code and "private" not in str(exc.value)
    assert error.fp.closed


@pytest.mark.parametrize(
    "raw",
    [
        b"not JSON",
        b"\xff",
        b"[]",
        b'{"choices":[]}',
        b'{"choices":NaN}',
        b'{"choices":[],"choices":[]}',
        response(""),
        response(None),
        response("text", tool_calls=[{"private": "tool"}]),
        response("text", refusal="blocked"),
        response().replace(b'"assistant"', b'"user"'),
    ],
)
def test_invalid_responses(raw):
    with pytest.raises(FormattingError) as exc:
        backend.parse_response(raw)
    assert exc.value.info.code == "OPENROUTER_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "reason", ["length", "content_filter", "tool_calls", None, "unknown"]
)
def test_nonstop_is_incomplete(reason):
    with pytest.raises(FormattingError) as exc:
        backend.parse_response(response(reason=reason))
    assert exc.value.info.code == "OPENROUTER_OUTPUT_INCOMPLETE"


def test_http_200_error_status_and_size_limits(monkeypatch):
    with pytest.raises(FormattingError) as exc:
        backend.parse_response(b'{"error":{"code":429,"message":"private"}}')
    assert exc.value.info.code == "OPENROUTER_LIMITED" and "private" not in str(
        exc.value
    )
    monkeypatch.setattr(backend, "HTTP_LIMIT", 100)
    with pytest.raises(FormattingError):
        backend.parse_response(b"x" * 101)


@pytest.mark.parametrize("key", ["", " ", "key\nInjected: true", "key\x00", "é"])
def test_missing_or_unsafe_key(monkeypatch, key):
    monkeypatch.setenv("OPENROUTER_API_KEY", key) if "\x00" not in key else None
    if "\x00" in key:
        monkeypatch.setattr(backend.os, "environ", {"OPENROUTER_API_KEY": key})
    with pytest.raises(FormattingError) as exc:
        backend.ensure_openrouter("provider/model")
    assert exc.value.info.code == "OPENROUTER_NOT_CONFIGURED"


def test_missing_model():
    with pytest.raises(FormattingError):
        backend.ensure_openrouter(None)


def test_redirect_handler_rejects_redirect():
    req = backend.urllib.request.Request(backend.ENDPOINT)
    with pytest.raises(urllib.error.HTTPError):
        backend.NoRedirect().redirect_request(
            req, io.BytesIO(), 302, "", HTTPMessage(), "https://other.test"
        )


def test_actual_read_is_bounded_without_content_length(monkeypatch):
    raw = Response(b"x" * 10000)
    raw.status = 200
    raw.headers = {}
    monkeypatch.setattr(backend, "HTTP_LIMIT", 100)
    monkeypatch.setattr(
        backend.urllib.request,
        "build_opener",
        lambda handler: SimpleNamespace(open=lambda *a, **kw: raw),
    )
    with pytest.raises(FormattingError) as exc:
        backend.complete_http(payload())
    assert exc.value.info.code == "OPENROUTER_OUTPUT_INVALID"


def test_formatter_uses_shared_validation_without_pi(monkeypatch):
    monkeypatch.setattr(
        formatter, "ensure_pi", lambda: pytest.fail("must not require Pi")
    )
    calls = []
    monkeypatch.setattr(
        backend,
        "complete",
        lambda req, config: calls.append(req) or "## Edited\n\nCaption.",
    )
    assert formatter.format_transcript(
        "caption", "provider/model", provider="openrouter"
    ).startswith("## Edited")
    assert len(calls) == 1 and calls[0].source == "caption"
    monkeypatch.setattr(
        backend, "complete", lambda *a: "---\ntitle: private\n---\nwrong"
    )
    with pytest.raises(FormattingError) as exc:
        formatter.format_transcript("caption", "provider/model", provider="openrouter")
    assert (
        exc.value.info.code == "OPENROUTER_OUTPUT_INVALID"
        and exc.value.info.chunk_index == 1
    )


@pytest.mark.parametrize(
    "thinking,level",
    [(None, None), (False, None), (True, "low"), (True, "medium"), (True, "high")],
)
def test_http_reasoning_translation(monkeypatch, thinking, level):
    captured = []

    def open(request, **kwargs):
        captured.append(json.loads(request.data))
        return Response(response(reasoning="PRIVATE_REASONING_SENTINEL"))

    monkeypatch.setattr(
        backend.urllib.request,
        "build_opener",
        lambda handler: SimpleNamespace(open=open),
    )
    value = payload() | {"thinking": thinking, "thinking_level": level}
    result = backend.complete_http(value)
    assert "PRIVATE_REASONING_SENTINEL" not in result
    if thinking is None:
        assert "reasoning" not in captured[0]
    else:
        assert captured[0]["reasoning"] == {
            "enabled": thinking,
            "effort": level if thinking else "none",
            "exclude": True,
        }
    assert captured[0]["provider"]["require_parameters"] is True
    assert captured[0]["provider"]["allow_fallbacks"] is False


def test_private_request_allows_only_legacy_and_complete_new_shape():
    legacy = payload()
    legacy.pop("thinking")
    legacy.pop("thinking_level")
    assert backend.validate_request(legacy) == legacy
    assert backend.validate_request(payload()) == payload()
    for extra in ({"thinking": True}, {"thinking_level": "low"}, {"unknown": None}):
        with pytest.raises(ValueError):
            backend.validate_request(legacy | extra)


@pytest.mark.parametrize(
    "thinking,level",
    [
        (True, None),
        (None, "low"),
        (False, "low"),
        (1, "low"),
        ("false", None),
        (True, []),
        (True, "max"),
    ],
)
def test_private_request_rejects_unresolved_or_inconsistent_policy(thinking, level):
    with pytest.raises(ValueError):
        backend.validate_request(
            payload() | {"thinking": thinking, "thinking_level": level}
        )
