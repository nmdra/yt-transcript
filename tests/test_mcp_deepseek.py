"""Server-owned DeepSeek settings with synthetic captions and fake completions."""

import asyncio
from dataclasses import asdict

import pytest
from mcp import Client

from yt_transcript import deepseek_backend as backend
from yt_transcript import formatter, service
from yt_transcript.config import AppConfig, CacheConfig, DeepSeekConfig
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.mcp_policy import MCPFormattingPolicy, validate_formatting_policy
from yt_transcript.mcp_server import create_server
from yt_transcript.mcp_worker import dispatch, validate_request
from yt_transcript.metadata import VideoMetadata
from yt_transcript.sponsorblock import SponsorBlockConfig

URL = "https://youtu.be/abcdefghijk"


class Runner:
    def __init__(self):
        self.calls = []

    async def close(self):
        pass

    async def run(self, request, *, on_progress=None):
        self.calls.append(request)
        return dict(dispatch(validate_request(request)))


@pytest.fixture
def source(monkeypatch):
    calls = []

    def download(url):
        calls.append(url)
        return DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nRetries can duplicate writes.\n",
            "en",
            False,
            VideoMetadata(
                "https://www.youtube.com/watch?v=abcdefghijk",
                "abcdefghijk",
                description="DESCRIPTION_NOT_MODEL_INPUT",
            ),
        )

    monkeypatch.setattr(service, "download_english_vtt", download)
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("no Pi"))
    return calls


@pytest.mark.parametrize("mode", ["full", "filtered"])
@pytest.mark.parametrize(
    "editorial,thinking,level,expected",
    [
        ("standard", None, None, (False, None)),
        ("focused", None, None, (False, None)),
        ("summarized", None, None, (True, "medium")),
        ("summarized", False, "high", (False, None)),
        ("summarized", True, "low", (True, "low")),
        ("standard", True, "high", (True, "high")),
    ],
)
def test_server_policy_and_model_free_cache(
    monkeypatch, tmp_path, source, mode, editorial, thinking, level, expected
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "KEY_NOT_FOR_OUTPUT")
    completions = []

    def complete(req, config):
        completions.append(req)
        assert (req.thinking, req.thinking_level) == expected
        assert config == DeepSeekConfig(20000)
        assert not req.own_process_group
        assert "DESCRIPTION_NOT_MODEL_INPUT" not in repr(req)
        return (
            "## Summary\n\nRetries can duplicate writes.\n\n## Key points\n\n- Use idempotency."
            if editorial == "summarized"
            else "## Edited\n\nRetries can duplicate writes."
        )

    monkeypatch.setattr(backend, "complete", complete)
    config = AppConfig(
        provider="deepseek",
        model="deepseek-v4-pro",
        deepseek=DeepSeekConfig(20000),
        editorial_mode=editorial,
        thinking=thinking,
        thinking_level=level,
        sponsorblock=SponsorBlockConfig(enabled=False),
        cache=CacheConfig(path=str(tmp_path / "cache")),
    )

    async def check():
        runner = Runner()
        async with Client(create_server(config, runner=runner)) as client:
            result = await client.call_tool(
                "get_transcript",
                {"url": URL, "mode": mode, "output_format": "markdown"},
            )
            assert not result.is_error
            assert result.structured_content["format"] == "markdown"
            assert "KEY_NOT_FOR_OUTPUT" not in str(result)
            assert result.structured_content["metadata"]["description"] == (
                "DESCRIPTION_NOT_MODEL_INPUT"
            )
            policy = runner.calls[0]["formatting"]
            assert policy["thinking"] is thinking
            assert policy["thinking_level"] == level
            assert policy["deepseek_max_output_tokens"] == 20000
            monkeypatch.delenv("DEEPSEEK_API_KEY")
            plain = await client.call_tool("get_transcript", {"url": URL, "mode": mode})
            assert not plain.is_error
            assert "formatting" not in runner.calls[-1]
            assert len(completions) == 1
            assert len(source) == 1
            missing = await client.call_tool(
                "get_transcript",
                {"url": URL, "mode": mode, "output_format": "markdown"},
            )
            assert missing.is_error
            assert "DEEPSEEK_NOT_CONFIGURED" in str(missing.content)
            assert "KEY_NOT_FOR_OUTPUT" not in str(missing.content)
            assert len(completions) == 1

    asyncio.run(check())


@pytest.mark.parametrize(
    "key,value",
    [
        ("deepseek_max_output_tokens", True),
        ("deepseek_max_output_tokens", 0),
        ("deepseek_max_output_tokens", 393217),
        ("model", None),
        ("thinking", 1),
        ("thinking", "true"),
        ("thinking_level", []),
        ("thinking_level", True),
        ("thinking_level", "max"),
        ("thinking_level", "low"),
    ],
)
def test_private_policy_rejects_invalid_values(key, value):
    policy = asdict(MCPFormattingPolicy(provider="deepseek", model="model"))
    policy[key] = value
    with pytest.raises(ValueError):
        validate_formatting_policy(policy)


def test_missing_model_still_allows_plain_text(monkeypatch, source):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(backend, "complete", lambda *a: pytest.fail("no model"))

    async def check():
        async with Client(
            create_server(AppConfig(provider="deepseek"), runner=Runner())
        ) as client:
            plain = await client.call_tool(
                "get_transcript", {"url": URL, "mode": "full"}
            )
            assert not plain.is_error
            missing = await client.call_tool(
                "get_transcript",
                {"url": URL, "mode": "full", "output_format": "markdown"},
            )
            assert missing.is_error
            assert "DEEPSEEK_NOT_CONFIGURED" in str(missing.content)

    asyncio.run(check())


def test_all_five_public_schemas_and_retrieval_are_model_free(
    monkeypatch, tmp_path, source
):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(backend, "complete", lambda *a: pytest.fail("no model"))
    config = AppConfig(
        provider="deepseek",
        editorial_mode="summarized",
        thinking_level="high",
        sponsorblock=SponsorBlockConfig(enabled=False),
        cache=CacheConfig(path=str(tmp_path / "cache")),
    )

    async def check():
        runner = Runner()
        async with Client(create_server(config, runner=runner)) as client:
            tools = (await client.list_tools()).tools
            assert {
                tool.name: set(tool.input_schema["properties"]) for tool in tools
            } == {
                "get_transcript": {"url", "mode", "output_format"},
                "get_video_info": {"url"},
                "get_transcript_segment": {
                    "url",
                    "start_seconds",
                    "end_seconds",
                    "mode",
                },
                "search_transcript": {"url", "query", "mode", "max_results"},
                "get_transcript_page": {"url", "cursor", "mode", "max_chars"},
            }
            for name, arguments in (
                ("get_transcript", {}),
                ("get_video_info", {}),
                ("get_transcript_segment", {"start_seconds": 0, "end_seconds": 1}),
                ("search_transcript", {"query": "Retries"}),
                ("get_transcript_page", {}),
            ):
                result = await client.call_tool(name, {"url": URL, **arguments})
                assert not result.is_error, str(result.content)
            assert len(runner.calls) == 5
            assert all("formatting" not in request for request in runner.calls)
            assert len(source) == 1

    asyncio.run(check())
