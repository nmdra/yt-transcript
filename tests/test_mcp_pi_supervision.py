import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from yt_transcript.mcp_server import WorkerRunner


def payload():
    return {
        "operation": "get_transcript",
        "url": "https://youtu.be/abcdefghijk",
        "mode": "full",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
        "output_format": "markdown",
        "formatting": {
            "model": None,
            "chunk_chars": 12000,
            "timeout_seconds": 120,
            "max_chunks": 3,
            "editorial_mode": "standard",
        },
    }


def fixture_worker(tmp_path, *, hanging=False):
    marker = tmp_path / "pi-pid"
    pi = tmp_path / "fake_pi.py"
    pi.write_text(
        "import json, os, signal, sys, time\n"
        + f"from pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\n"
        + (
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(30)\n"
            if hanging
            else ""
        )
        + "sys.stdin.buffer.read()\n"
        + "sys.stderr.write('Bearer private-model-error')\n"
        + "events=[{'type':'session'},{'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'## Edited\\n\\nHello world.'}],'stopReason':'stop'}},{'type':'agent_settled'}]\n"
        + "for event in events: print(json.dumps(event),flush=True)\n"
    )
    worker = tmp_path / "fixture_worker.py"
    worker.write_text(
        "import sys\nfrom yt_transcript import formatter, service, mcp_worker\n"
        "from yt_transcript.downloader import DownloadedCaptions\n"
        "from yt_transcript.metadata import VideoMetadata\n"
        "service.download_english_vtt=lambda url: DownloadedCaptions(b'WEBVTT\\n\\n00:00.000 --> 00:01.000\\nhello world\\n','en',False,VideoMetadata('https://www.youtube.com/watch?v=abcdefghijk','abcdefghijk',duration_seconds=10))\n"
        "formatter.ensure_pi=lambda: 'synthetic-pi'\n"
        "original=formatter.subprocess.Popen\n"
        + f"formatter.subprocess.Popen=lambda argv,**kw: original([sys.executable,{str(pi)!r}],**kw)\n"
        "raise SystemExit(mcp_worker.main())\n"
    )
    return worker, marker


def test_real_stdio_markdown_worker_and_plain_default(tmp_path):
    worker, marker = fixture_worker(tmp_path)
    server = tmp_path / "fixture_server.py"
    server.write_text(
        "import asyncio,sys\nfrom yt_transcript.mcp_server import create_server\n"
        "from yt_transcript.config import AppConfig\n"
        "original=asyncio.create_subprocess_exec\n"
        + f"async def spawn(*args,**kw): return await original(sys.executable,{str(worker)!r},**kw)\n"
        "asyncio.create_subprocess_exec=spawn\n"
        "create_server(AppConfig()).run(transport='stdio')\n"
    )

    async def check():
        async with Client(
            StdioServerParameters(command=sys.executable, args=[str(server)])
        ) as client:
            (tool,) = (await client.list_tools()).tools
            assert (
                tool.input_schema["properties"]["output_format"]["default"]
                == "plain_text"
            )
            plain = await client.call_tool(
                "get_transcript", {"url": payload()["url"], "mode": "full"}
            )
            assert (
                not plain.is_error
                and plain.structured_content["format"] == "plain_text"
            )
            assert not marker.exists()
            edited = await client.call_tool(
                "get_transcript",
                {"url": payload()["url"], "mode": "full", "output_format": "markdown"},
            )
            assert not edited.is_error
            assert edited.structured_content["format"] == "markdown"
            assert edited.structured_content["document"].endswith(
                "## Edited\n\nHello world.\n"
            )
            assert "private-model-error" not in json.dumps(edited.structured_content)
            assert marker.exists()

    asyncio.run(check())


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group safety")
def test_cancel_kills_pi_in_worker_group(tmp_path, monkeypatch):
    worker, marker = fixture_worker(tmp_path, hanging=True)
    original = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*args, **kwargs):
        process = await original(sys.executable, str(worker), **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def check():
        runner = WorkerRunner()
        task = asyncio.create_task(runner.run(payload()))
        try:
            for _ in range(500):
                if marker.exists() and marker.read_text():
                    break
                await asyncio.sleep(0.01)
            assert marker.exists()
            pid = int(marker.read_text())
            assert os.getpgid(pid) == processes[0].pid
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert processes[0].returncode is not None
            for _ in range(200):
                path = Path(f"/proc/{pid}/stat")
                if (
                    not path.exists()
                    or path.read_text().rpartition(")")[2].split()[0] == "Z"
                ):
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Pi remained running after worker cancellation")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await runner.close()

    asyncio.run(check())
