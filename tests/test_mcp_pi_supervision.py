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


def fixture_worker(
    tmp_path, *, hanging=False, mutation=False, multi=False, delay: float = 0
):
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
        + f"time.sleep({delay!r})\n"
        + f"calls=Path({str(tmp_path / 'calls')!r})\nwith calls.open('a') as f: f.write('call\\n')\n"
        + (
            "if len(calls.read_text().splitlines()) == 2:\n print(json.dumps({'type':'session'}),flush=True)\n print(json.dumps({'type':'compaction_start','reason':'overflow','private':'Bearer secret'}),flush=True)\n sys.exit(0)\n"
            if mutation
            else ""
        )
        + "sys.stderr.write('Bearer private-model-error')\n"
        + "events=[{'type':'session'},{'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'## Edited\\n\\nHello world.'}],'stopReason':'stop'}},{'type':'agent_settled'}]\n"
        + "for event in events: print(json.dumps(event),flush=True)\n"
    )
    captions = (
        b"WEBVTT\n\n00:00.000 --> 00:01.000\n"
        + (b"hello world " * 250 if multi else b"hello world")
        + b"\n"
    )
    worker = tmp_path / "fixture_worker.py"
    worker.write_text(
        "import sys\nfrom yt_transcript import formatter, service, mcp_worker\n"
        "from yt_transcript.downloader import DownloadedCaptions\n"
        "from yt_transcript.metadata import VideoMetadata\n"
        f"service.download_english_vtt=lambda url: DownloadedCaptions({captions!r},'en',False,VideoMetadata('https://www.youtube.com/watch?v=abcdefghijk','abcdefghijk',duration_seconds=10))\n"
        "formatter.ensure_pi=lambda: 'synthetic-pi'\n"
        "original=formatter.subprocess.Popen\n"
        + f"formatter.subprocess.Popen=lambda argv,**kw: original([sys.executable,{str(pi)!r}],**kw)\n"
        "raise SystemExit(mcp_worker.main())\n"
    )
    return worker, marker


@pytest.mark.parametrize("mutation", [False, True])
def test_multichunk_stdio_longer_deadline_and_no_retry(tmp_path, mutation):
    worker, marker = fixture_worker(tmp_path, multi=True, mutation=mutation, delay=0.15)
    server = tmp_path / "long_server.py"
    server.write_text(
        "import asyncio,sys\nfrom yt_transcript.mcp_server import create_server,WorkerRunner\n"
        "from yt_transcript.config import AppConfig\n"
        "original=asyncio.create_subprocess_exec\n"
        + f"async def spawn(*args,**kw): return await original(sys.executable,{str(worker)!r},**kw)\n"
        "asyncio.create_subprocess_exec=spawn\n"
        "create_server(AppConfig(chunk_chars=1000,max_chunks=4),runner=WorkerRunner(timeout_seconds=0.05,markdown_timeout_seconds=3)).run(transport='stdio')\n"
    )

    async def check():
        async with Client(
            StdioServerParameters(command=sys.executable, args=[str(server)])
        ) as client:
            result = await client.call_tool(
                "get_transcript",
                {"url": payload()["url"], "mode": "full", "output_format": "markdown"},
            )
            text = json.dumps(result.model_dump(mode="json"))
            assert "Bearer secret" not in text and "private-model-error" not in text
            calls = (tmp_path / "calls").read_text().splitlines()
            if mutation:
                assert result.is_error
                assert result.structured_content is None
                assert "PI_CONTEXT_MUTATED" in text and "(chunk 2/4)" in text
                assert "plain_text" in text
                assert len(calls) == 2
                assert "## Edited" not in text
            else:
                assert not result.is_error
                assert len(calls) == 4
                document = result.structured_content["document"]
                assert document.count("## Edited") == 4
                assert not document.startswith("---")
                assert len(document) == result.structured_content["character_count"]
            # Failure does not stop the server or launch another Pi process.
            assert len((await client.list_tools()).tools) == 1
        assert marker.exists()

    asyncio.run(check())


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
            assert edited.structured_content["document"] == "## Edited\n\nHello world."
            assert "private-model-error" not in json.dumps(edited.structured_content)
            assert marker.exists()

    asyncio.run(check())


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group safety")
@pytest.mark.parametrize("termination", ["cancel", "timeout"])
def test_cancel_kills_pi_in_worker_group(tmp_path, monkeypatch, termination):
    worker, marker = fixture_worker(tmp_path, hanging=True)
    original = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*args, **kwargs):
        process = await original(sys.executable, str(worker), **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def check():
        runner = WorkerRunner(
            markdown_timeout_seconds=2 if termination == "timeout" else 10
        )
        task = asyncio.create_task(runner.run(payload()))
        try:
            for _ in range(500):
                if marker.exists() and marker.read_text():
                    break
                await asyncio.sleep(0.01)
            assert marker.exists()
            pid = int(marker.read_text())
            assert os.getpgid(pid) == processes[0].pid
            if termination == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                from yt_transcript.errors import AppError

                with pytest.raises(AppError) as exc:
                    await task
                assert exc.value.info.code == "MCP_TIMEOUT"
            assert not runner._busy
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
