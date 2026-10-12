"""MCP policy and local descendant cleanup, without real HTTP."""

import asyncio
import json
import os
import sys
from dataclasses import asdict

import pytest
from mcp import Client
from mcp.types import TextContent

from yt_transcript import formatter, service
from yt_transcript import openrouter_backend as backend
from yt_transcript.config import AppConfig
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.errors import AppError
from yt_transcript.mcp_policy import MCPFormattingPolicy, validate_formatting_policy
from yt_transcript.mcp_server import WorkerRunner, create_server
from yt_transcript.mcp_worker import dispatch, validate_request
from yt_transcript.metadata import VideoMetadata
from yt_transcript.sponsorblock import SponsorBlockConfig

URL = "https://youtu.be/abcdefghijk"


class Runner:
    async def close(self):
        pass

    async def run(self, request, *, on_progress=None):
        return dict(dispatch(validate_request(request)))


@pytest.mark.parametrize("mode", ["filtered", "full"])
@pytest.mark.parametrize("editorial", ["standard", "focused", "summarized"])
def test_mcp_provider_is_server_owned(monkeypatch, mode, editorial):
    monkeypatch.setenv("OPENROUTER_API_KEY", "KEY_NOT_FOR_OUTPUT")
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("no Pi"))
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk",
        description="DESCRIPTION_NOT_MODEL_INPUT",
    )
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nRetries can duplicate writes.\n",
            "en",
            False,
            metadata,
        ),
    )
    calls = []

    def complete(req, config):
        calls.append(req)
        assert not req.own_process_group and "DESCRIPTION_NOT_MODEL_INPUT" not in repr(
            req
        )
        return (
            "## Summary\n\nRetries can duplicate writes.\n\n## Key points\n\n- Use idempotency."
            if editorial == "summarized"
            else "## Edited\n\nRetries can duplicate writes."
        )

    monkeypatch.setattr(backend, "complete", complete)
    config = AppConfig(
        provider="openrouter",
        model="provider/model",
        editorial_mode=editorial,
        sponsorblock=SponsorBlockConfig(enabled=False),
    )

    async def check():
        async with Client(create_server(config, runner=Runner())) as client:
            tool = (await client.list_tools()).tools[0]
            assert set(tool.input_schema["properties"]) == {
                "url",
                "mode",
                "output_format",
            }
            result = await client.call_tool(
                "get_transcript",
                {"url": URL, "mode": mode, "output_format": "markdown"},
            )
            assert not result.is_error
            structured = result.structured_content
            assert structured["metadata"]["description"] == metadata.description
            assert structured["character_count"] == len(structured["document"])
            assert isinstance(result.content[0], TextContent)
            assert json.loads(result.content[0].text) == structured
            monkeypatch.delenv("OPENROUTER_API_KEY")
            plain = await client.call_tool("get_transcript", {"url": URL, "mode": mode})
            assert not plain.is_error and len(calls) == 1
            invalid = await client.call_tool(
                "get_transcript", {"url": URL, "provider": "openrouter"}
            )
            assert invalid.is_error
            missing = await client.call_tool(
                "get_transcript",
                {"url": URL, "mode": mode, "output_format": "markdown"},
            )
            assert missing.is_error and "KEY_NOT_FOR_OUTPUT" not in str(missing.content)

    asyncio.run(check())


@pytest.mark.parametrize(
    "key,value",
    [
        ("provider", "unknown"),
        ("provider", []),
        ("openrouter_max_output_tokens", True),
        ("openrouter_max_output_tokens", 0),
        ("openrouter_max_output_tokens", 131073),
        ("model", None),
    ],
)
def test_private_openrouter_policy_is_exact(key, value):
    policy = asdict(MCPFormattingPolicy(provider="openrouter", model="provider/model"))
    policy[key] = value
    with pytest.raises(ValueError):
        validate_formatting_policy(policy)


def test_missing_server_model_does_not_break_plain_text(monkeypatch):
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"
    )
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\ncaption\n", "en", False, metadata
        ),
    )

    async def check():
        async with Client(
            create_server(AppConfig(provider="openrouter"), runner=Runner())
        ) as client:
            assert not (
                await client.call_tool("get_transcript", {"url": URL, "mode": "full"})
            ).is_error
            bad = await client.call_tool(
                "get_transcript",
                {"url": URL, "mode": "full", "output_format": "markdown"},
            )
            assert bad.is_error and "OPENROUTER_NOT_CONFIGURED" in str(bad.content)

    asyncio.run(check())


@pytest.mark.skipif(os.name != "posix", reason="POSIX group supervision")
@pytest.mark.parametrize("provider", ["openrouter", "deepseek"])
def test_outer_deadline_kills_http_helper_and_allows_reuse(
    tmp_path, monkeypatch, provider
):
    marker = tmp_path / "helper-pid"
    helper = tmp_path / "helper.py"
    helper.write_text(
        "import os,signal,time,sys\nfrom pathlib import Path\n"
        + f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        + "signal.signal(signal.SIGTERM,signal.SIG_IGN)\nsys.stdin.read()\ntime.sleep(20)\n"
    )
    worker = tmp_path / "worker.py"
    worker.write_text(
        f"import sys\nfrom yt_transcript import service,mcp_worker,{provider}_backend as backend\n"
        "from yt_transcript.downloader import DownloadedCaptions\nfrom yt_transcript.metadata import VideoMetadata\n"
        "service.download_english_vtt=lambda url: DownloadedCaptions(b'WEBVTT\\n\\n00:00.000 --> 00:01.000\\ncaption\\n','en',False,VideoMetadata('https://www.youtube.com/watch?v=abcdefghijk','abcdefghijk'))\n"
        "original=backend.subprocess.Popen\n"
        + f"backend.subprocess.Popen=lambda argv,**kw: original([sys.executable,{str(helper)!r}],**kw)\n"
        "raise SystemExit(mcp_worker.main())\n"
    )
    original = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        return await original(sys.executable, str(worker), **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", "KEY_NOT_FOR_OUTPUT")
    payload = {
        "operation": "get_transcript",
        "url": URL,
        "mode": "full",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
        "output_format": "markdown",
        "formatting": asdict(
            MCPFormattingPolicy(provider=provider, model="provider/model")
        ),
    }

    async def check():
        runner = WorkerRunner(markdown_timeout_seconds=1)
        with pytest.raises(AppError) as exc:
            await runner.run(payload)
        assert exc.value.info.code == "MCP_TIMEOUT"
        pid = int(marker.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        helper.write_text(
            "import sys,json\nsys.stdin.read()\nprint(json.dumps({'text':'## Edited\\n\\nCaption.'}))\n"
        )
        runner.markdown_timeout_seconds = 5
        result = await runner.run(payload)
        assert result["format"] == "markdown"
        marker.unlink()
        helper.write_text(
            "import os,signal,time,sys\nfrom pathlib import Path\n"
            + f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
            + "signal.signal(signal.SIGTERM,signal.SIG_IGN)\nsys.stdin.read()\ntime.sleep(20)\n"
        )
        task = asyncio.create_task(runner.run(payload))
        async with asyncio.timeout(4):
            while not marker.exists():
                await asyncio.sleep(0.01)
        pid = int(marker.read_text())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert not runner._busy and runner._process is None
        helper.write_text(
            "import sys,json\nsys.stdin.read()\nprint(json.dumps({'text':'## Edited\\n\\nCaption.'}))\n"
        )
        assert (await runner.run(payload))["format"] == "markdown"
        await runner.close()

    asyncio.run(check())
