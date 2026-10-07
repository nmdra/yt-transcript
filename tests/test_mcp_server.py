import asyncio
import json

from mcp import Client
from mcp.types import TextContent

from yt_transcript.config import AppConfig
from yt_transcript.errors import AppError, ErrorInfo
from yt_transcript.mcp_server import create_server
from yt_transcript.metadata import VideoMetadata
from yt_transcript.service import CleanedTranscript


def text_content(result):
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


class Runner:
    def __init__(self):
        self.calls = []

    async def close(self):
        pass

    async def run(self, payload):
        self.calls.append(payload)
        if payload.get("url") == "invalid":
            raise AppError(
                ErrorInfo(
                    "INVALID_URL", "Expected a YouTube video URL.", phase="config"
                )
            )
        cleaned = CleanedTranscript(
            "hello world",
            VideoMetadata("https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
            "en",
            False,
        )
        return {
            "format": "plain_text",
            "document": cleaned.body,
            "metadata": cleaned.mapping(),
            "character_count": 11,
        }


def test_tools_schemas_and_success():
    async def check():
        runner = Runner()
        async with Client(
            create_server(AppConfig(mode="raw", model="saved"), runner=runner),
            raise_exceptions=True,
        ) as client:
            tools = (await client.list_tools()).tools
            assert [tool.name for tool in tools] == ["get_transcript"]
            assert not runner.calls
            tool = tools[0]
            assert tool.output_schema
            assert (
                tool.annotations is not None and tool.annotations.read_only_hint is True
            )
            result = await client.call_tool(
                "get_transcript", {"url": "https://youtu.be/abcdefghijk"}
            )
            assert result.structured_content["character_count"] == 11
            assert result.structured_content["document"] == "hello world"
            assert json.loads(text_content(result)) == result.structured_content
            import jsonschema

            jsonschema.validate(result.structured_content, tool.output_schema)
            assert not (await client.list_resources()).resources
            assert not (await client.list_prompts()).prompts

    asyncio.run(check())


def test_server_configures_markdown_deadline(monkeypatch):
    from yt_transcript import mcp_server
    from yt_transcript.config import MCPConfig

    created = []

    class CapturingRunner(Runner):
        def __init__(self, **kwargs):
            super().__init__()
            created.append(kwargs)

    monkeypatch.setattr(mcp_server, "WorkerRunner", CapturingRunner)
    create_server(AppConfig(mcp=MCPConfig(1800)))
    create_server(AppConfig())
    assert created == [
        {"markdown_timeout_seconds": 1800},
        {"markdown_timeout_seconds": 300},
    ]


def test_schema_errors_never_echo_arguments(caplog):
    async def check():
        runner = Runner()
        async with Client(create_server(AppConfig(), runner=runner)) as client:
            secret = "Bearer private-key cookie=private signed?token=value /home/private caption excerpt"
            for name, arguments in [
                ("get_transcript", {"url": {"Authorization": secret}}),
                ("get_transcript", {"url": [secret]}),
                (
                    "get_transcript",
                    {"url": "https://youtu.be/abcdefghijk", "extra": secret},
                ),
                ("doctor", {"private": secret}),
                ("preview_transcript", {"url": secret}),
                ("private-token-name", {}),
            ]:
                result = await client.call_tool(name, arguments)
                assert result.is_error
                assert "CONFIG_INVALID" in text_content(result)
                assert secret not in text_content(result)
            assert not runner.calls

    asyncio.run(check())
    assert "private-key" not in caplog.text
    assert "/home/private" not in caplog.text


def test_unexpected_worker_error_is_safe(caplog):
    class BrokenRunner(Runner):
        async def run(self, payload):
            raise RuntimeError("Bearer private-key caption excerpt")

    async def check():
        async with Client(create_server(AppConfig(), runner=BrokenRunner())) as client:
            result = await client.call_tool(
                "get_transcript", {"url": "https://youtu.be/abcdefghijk"}
            )
            assert result.is_error and "INTERNAL_ERROR" in text_content(result)

    asyncio.run(check())
    assert "private-key" not in caplog.text


def test_expected_failure_and_server_reuse():
    async def check():
        async with Client(create_server(AppConfig(), runner=Runner())) as client:
            failure = await client.call_tool("get_transcript", {"url": "invalid"})
            assert failure.is_error and "INVALID_URL" in text_content(failure)
            success = await client.call_tool(
                "get_transcript", {"url": "https://youtu.be/abcdefghijk"}
            )
            assert not success.is_error

    asyncio.run(check())
