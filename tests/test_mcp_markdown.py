import asyncio
from dataclasses import asdict, replace

import pytest
from mcp import Client

from yt_transcript import formatter, service
from yt_transcript.chapters import Chapter
from yt_transcript.config import AppConfig
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.errors import AppError, classify_pi_failure
from yt_transcript.mcp_policy import MCPFormattingPolicy, validate_formatting_policy
from yt_transcript.mcp_server import create_server
from yt_transcript.mcp_worker import dispatch, validate_request
from yt_transcript.metadata import VideoMetadata

URL = "https://youtu.be/abcdefghijk"
POLICY = {"enabled": False, "categories": ["sponsor"], "timeout_seconds": 10}


def request():
    return {
        "operation": "get_transcript",
        "url": URL,
        "mode": "full",
        "sponsorblock": POLICY,
        "output_format": "markdown",
        "formatting": asdict(MCPFormattingPolicy()),
    }


@pytest.fixture
def source(monkeypatch):
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk",
        duration_seconds=10,
    )
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nhello world\n", "en", False, metadata
        ),
    )
    monkeypatch.setattr(formatter, "ensure_pi", lambda: "synthetic-pi")
    return metadata


def test_plain_text_never_calls_pi(source, monkeypatch):
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("no Pi check"))
    monkeypatch.setattr(
        formatter, "format_with_pi", lambda *a, **k: pytest.fail("no Pi")
    )
    result = service.fetch_transcript_document(URL, "full")
    assert result["format"] == "plain_text"
    assert "[00:00 - 00:01] hello world" in result["document"]


def test_markdown_uses_shared_formatter_and_python_yaml(source, monkeypatch):
    calls = []

    def edit(body, **kwargs):
        calls.append((body, kwargs))
        return "## Edited\n\nHello world."

    monkeypatch.setattr(formatter, "format_with_pi", edit)
    result = dispatch(validate_request(request()))
    assert result["format"] == "markdown"
    assert result["document"].startswith("---\n")
    assert result["document"].endswith("## Edited\n\nHello world.\n")
    assert result["character_count"] == len("## Edited\n\nHello world.")
    assert calls[0][0] == "hello world"
    assert calls[0][1]["max_chunks"] == 3
    assert calls[0][1]["timeout_seconds"] == 120
    assert calls[0][1]["model"] is None
    assert calls[0][1]["own_process_group"] is False
    service.validate_service_result("get_transcript", result)


def test_direct_service_owns_pi_process_group(source, monkeypatch):
    calls = []
    monkeypatch.setattr(
        formatter, "format_with_pi", lambda body, **kw: calls.append(kw) or "Edited"
    )
    service.fetch_transcript_document(URL, "full", output_format="markdown")
    assert calls[0]["own_process_group"] is True


def test_markdown_has_canonical_chapter_headings(source, monkeypatch):
    metadata = replace(
        source, chapters=(Chapter("Intro", 0, 10000),), chapter_status="available"
    )
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nhello world\n", "en", False, metadata
        ),
    )
    monkeypatch.setattr(
        formatter, "_run_chunk", lambda *a, **kw: "## [00:00] Intro\n\nHello world."
    )
    result = service.fetch_transcript_document(URL, "full", output_format="markdown")
    assert "## [00:00] Intro" in result["document"]
    assert result["metadata"]["chapters"][0]["title"] == "Intro"


def test_cap_rejects_before_model(source, monkeypatch):
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\n" + b"word " * 1000 + b"\n",
            "en",
            False,
            source,
        ),
    )
    monkeypatch.setattr(
        formatter, "_run_chunk", lambda *a, **kw: pytest.fail("must not call model")
    )
    with pytest.raises(AppError) as exc:
        service.fetch_transcript_document(
            URL,
            "full",
            output_format="markdown",
            formatting=MCPFormattingPolicy(chunk_chars=1000, max_chunks=1),
        )
    assert exc.value.info.code == "CHUNK_LIMIT_EXCEEDED"


def test_pi_failure_has_no_raw_fallback(source, monkeypatch):
    def fail(*args, **kwargs):
        raise classify_pi_failure(code="PI_TIMEOUT")

    monkeypatch.setattr(formatter, "format_with_pi", fail)
    with pytest.raises(AppError) as exc:
        dispatch(request())
    assert exc.value.info.code == "PI_TIMEOUT"


def test_unsupported_supervision_fails_before_pi(source, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(service, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("no Pi"))
    with pytest.raises(AppError) as exc:
        dispatch(request())
    assert exc.value.info.code == "RUNTIME_INCOMPATIBLE"


@pytest.mark.parametrize(
    "key,value",
    [
        ("timeout_seconds", 121),
        ("timeout_seconds", True),
        ("max_chunks", None),
        ("max_chunks", 0),
        ("max_chunks", True),
        ("chunk_chars", 999),
        ("model", ""),
        ("model", []),
        ("editorial_mode", "invalid"),
    ],
)
def test_invalid_policy(key, value):
    policy = asdict(MCPFormattingPolicy())
    policy[key] = value
    with pytest.raises(ValueError):
        validate_formatting_policy(policy)
    payload = request()
    payload["formatting"] = policy
    with pytest.raises(ValueError):
        validate_request(payload)


def test_plain_worker_cannot_carry_formatting_policy():
    payload = request()
    payload["output_format"] = "plain_text"
    with pytest.raises(ValueError):
        validate_request(payload)


def test_sdk_schema_and_server_controls(source, monkeypatch):
    class Runner:
        def __init__(self):
            self.calls = []

        async def close(self):
            pass

        async def run(self, payload):
            self.calls.append(payload)
            return dict(dispatch(validate_request(payload)))

    monkeypatch.setattr(
        formatter, "_run_chunk", lambda *a, **kw: "## Edited\n\nHello world."
    )

    async def check():
        runner = Runner()
        config = AppConfig(model="saved-model", timeout_seconds=600, max_chunks=2)
        async with Client(create_server(config, runner=runner)) as client:
            (tool,) = (await client.list_tools()).tools
            schema = tool.input_schema["properties"]["output_format"]
            assert schema["default"] == "plain_text"
            assert schema["enum"] == ["plain_text", "markdown"]
            assert not runner.calls
            result = await client.call_tool(
                "get_transcript",
                {"url": URL, "mode": "full", "output_format": "markdown"},
            )
            assert not result.is_error
            assert result.structured_content["format"] == "markdown"
            policy = runner.calls[0]["formatting"]
            assert policy["model"] == "saved-model"
            assert policy["max_chunks"] == 2 and policy["timeout_seconds"] == 120
            for bad in [
                {"output_format": "Bearer private"},
                {"model": "private"},
                {"max_chunks": 99},
            ]:
                result = await client.call_tool("get_transcript", {"url": URL, **bad})
                assert result.is_error and "private" not in str(result.content)
            assert len(runner.calls) == 1

    asyncio.run(check())
