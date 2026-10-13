import asyncio
import json
import subprocess
import sys

from mcp import Client, StdioServerParameters
from mcp.types import TextContent


def text_content(result):
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


def test_real_stdio_outside_repository(tmp_path):
    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "yt_transcript", "--mcp", "--no-config"],
            cwd=tmp_path,
        )
        async with Client(params) as client:
            tools = (await client.list_tools()).tools
            assert [tool.name for tool in tools] == [
                "get_transcript",
                "get_video_info",
                "get_transcript_segment",
                "search_transcript",
                "get_transcript_page",
            ]
            result = await client.call_tool(
                "get_transcript",
                {"url": "https://invalid.example/private?token=secret"},
            )
            assert result.is_error
            assert "INVALID_URL" in text_content(result)
            assert "secret" not in text_content(result)
            assert len((await client.list_tools()).tools) == 5

    asyncio.run(check())


def test_stdout_contains_only_jsonrpc(tmp_path):
    from mcp.types import DEFAULT_NEGOTIATED_VERSION

    async def check():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "yt_transcript",
            "--mcp",
            "--no-config",
            cwd=tmp_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdin and process.stdout and process.stderr
        stdin = process.stdin

        async def send(message):
            stdin.write(json.dumps(message).encode() + b"\n")
            await stdin.drain()

        try:
            await send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": DEFAULT_NEGOTIATED_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "offline", "version": "0"},
                    },
                }
            )
            initial = await asyncio.wait_for(process.stdout.readline(), 10)
            assert json.loads(initial)["id"] == 1
            await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            await send(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            )
            listing = await asyncio.wait_for(process.stdout.readline(), 10)
            assert len(json.loads(listing)["result"]["tools"]) == 5
            process.stdin.close()
            tail = await asyncio.wait_for(process.stdout.read(), 10)
            assert await asyncio.wait_for(process.wait(), 10) == 0
            for line in (initial + listing + tail).splitlines():
                event = json.loads(line)
                assert event["jsonrpc"] == "2.0" and isinstance(event, dict)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    asyncio.run(check())


def test_stdio_eof_clean_shutdown(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "yt_transcript", "--mcp", "--no-config"],
        input=b"",
        capture_output=True,
        cwd=tmp_path,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout == b""


def test_stdio_cancellation_and_disconnect_cleanup(tmp_path):
    from pathlib import Path

    marker = tmp_path / "worker-marker"
    worker = tmp_path / "cooperative_worker.py"
    worker.write_text(f"""import os,sys,signal,time
from tempfile import TemporaryDirectory
from pathlib import Path
def stop(*args): raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
    with TemporaryDirectory() as root:
        Path({str(marker)!r}).write_text(str(os.getpid())+'\\n'+root)
        sys.stdin.buffer.read()
        time.sleep(30)
except KeyboardInterrupt: pass
""")
    server = tmp_path / "cancellation_server.py"
    server.write_text(f"""import asyncio,sys
from yt_transcript.mcp_server import create_server,WorkerRunner
from yt_transcript.config import AppConfig
original=asyncio.create_subprocess_exec
async def spawn(*args,**kwargs):
    return await original(sys.executable,{str(worker)!r},**kwargs)
asyncio.create_subprocess_exec=spawn
create_server(AppConfig(),runner=WorkerRunner()).run(transport="stdio")
""")

    async def wait_for_marker():
        for _ in range(200):
            if marker.exists():
                return Path(marker.read_text().splitlines()[1])
            await asyncio.sleep(0.01)
        raise AssertionError("Worker did not start")

    async def check():
        params = StdioServerParameters(
            command=sys.executable, args=[str(server)], cwd=tmp_path
        )
        async with Client(params) as client:
            task = asyncio.create_task(
                client.call_tool(
                    "get_transcript", {"url": "https://youtu.be/abcdefghijk"}
                )
            )
            root = await wait_for_marker()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            for _ in range(300):
                if not root.exists():
                    break
                await asyncio.sleep(0.01)
            assert not root.exists()
            assert len((await client.list_tools()).tools) == 5
            marker.unlink()
            task = asyncio.create_task(
                client.call_tool(
                    "get_transcript", {"url": "https://youtu.be/abcdefghijk"}
                )
            )
            root = await wait_for_marker()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            for _ in range(300):
                if not root.exists():
                    break
                await asyncio.sleep(0.01)
            assert not root.exists()
        marker.unlink()
        async with Client(params) as client:
            task = asyncio.create_task(
                client.call_tool(
                    "get_transcript", {"url": "https://youtu.be/abcdefghijk"}
                )
            )
            root = await wait_for_marker()
            # Exit the transport while the worker is active, without a tool result.
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for _ in range(300):
            if not root.exists():
                break
            await asyncio.sleep(0.01)
        assert not root.exists()

    asyncio.run(check())


def test_stdio_success_fixture(tmp_path):
    # Test-only composition injects deterministic service results. Production has no fixture flag.
    script = tmp_path / "server_fixture.py"
    script.write_text("""from yt_transcript.mcp_server import create_server
from yt_transcript.config import AppConfig
from yt_transcript.metadata import VideoMetadata
from yt_transcript.service import CleanedTranscript
class Runner:
    async def close(self): pass
    async def run(self, payload, *, on_progress=None):
        cleaned=CleanedTranscript("hello world",VideoMetadata("https://www.youtube.com/watch?v=abcdefghijk","abcdefghijk",description='STDIO_DESCRIPTION_SENTINEL\\nquote" 😀\\n'),"en",False)
        return {"format":"plain_text","document":cleaned.body,"metadata":cleaned.mapping(),"character_count":11}
create_server(AppConfig(),runner=Runner()).run(transport="stdio")
""")

    async def check():
        params = StdioServerParameters(
            command=sys.executable, args=[str(script)], cwd=tmp_path
        )
        async with Client(params, raise_exceptions=True) as client:
            result = await client.call_tool(
                "get_transcript", {"url": "https://youtu.be/abcdefghijk"}
            )
            assert result.structured_content["document"] == "hello world"
            assert (
                result.structured_content["metadata"]["description"]
                == 'STDIO_DESCRIPTION_SENTINEL\nquote" 😀\n'
            )
            assert json.loads(text_content(result)) == result.structured_content

    asyncio.run(check())


def test_stdio_cached_retrieval_and_optional_progress(tmp_path):
    """Actual private worker processes share a snapshot, with local source mocks."""
    import os
    from pathlib import Path

    log = tmp_path / "calls"
    worker = tmp_path / "snapshot_worker.py"
    worker.write_text(
        """import socket,time
from pathlib import Path
from yt_transcript import service,formatter,mcp_worker
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.metadata import VideoMetadata
from yt_transcript.sponsorblock import SponsorBlockLookup
def denied(*args,**kwargs): raise AssertionError("No network")
socket.create_connection=denied
socket.socket.connect=denied
LOG=Path(LOG_PATH)
def mark(kind):
    with LOG.open("a") as f: f.write(kind+"\\n")
cues=[]
for i in range(40):
    cues.append(f"00:{i:02d}.000 --> 00:{i:02d}.900\\nCue {i:02d} authentication JWT cache "+"words "*12)
vtt=("WEBVTT\\n\\n"+"\\n\\n".join(cues)+"\\n").encode()
metadata=VideoMetadata("https://www.youtube.com/watch?v=abcdefghijk","abcdefghijk",duration_seconds=40)
def download(url, **kwargs):
    mark("download")
    return DownloadedCaptions(vtt,"en",False,metadata)
def lookup(video_id,*,config,duration_seconds):
    mark("lookup")
    return SponsorBlockLookup(config.enabled,"not_found" if config.enabled else "disabled",config.categories)
def format_body(body,*,on_progress=None,**kwargs):
    mark("model")
    if on_progress:
        for done in range(3):
            on_progress(done,2)
            time.sleep(0.01)
    return "## Edited\\n\\nSource captions."
service.download_caption_vtt=download
service.lookup_sponsorblock=lookup
formatter.ensure_formatter=lambda *a: None
formatter.format_transcript=format_body
raise SystemExit(mcp_worker.main())
""".replace("LOG_PATH", repr(str(log)))
    )
    server = tmp_path / "snapshot_server.py"
    server.write_text(
        """import asyncio,sys
from yt_transcript.mcp_server import create_server
from yt_transcript.config import AppConfig
original=asyncio.create_subprocess_exec
async def spawn(*args,**kwargs):
    return await original(sys.executable,WORKER_PATH,**kwargs)
asyncio.create_subprocess_exec=spawn
create_server(AppConfig()).run(transport="stdio")
""".replace("WORKER_PATH", repr(str(worker)))
    )

    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(server)],
            cwd=tmp_path,
            env={**os.environ, "XDG_CACHE_HOME": str(tmp_path / "cache")},
        )
        notifications = []

        async def report(progress, total, message):
            notifications.append((progress, total, message))

        async with Client(params, raise_exceptions=True) as client:
            tools = (await client.list_tools()).tools
            assert len(tools) == 5
            assert set(tools[0].input_schema["properties"]) == {
                "url",
                "mode",
                "output_format",
            }
            url = "https://youtu.be/abcdefghijk"
            plain = await client.call_tool("get_transcript", {"url": url})
            assert plain.structured_content["format"] == "plain_text"
            for query in ("authentication", "JWT", "cache"):
                result = await client.call_tool(
                    "search_transcript", {"url": url, "query": query}
                )
                assert result.structured_content["matches"]
            segment = await client.call_tool(
                "get_transcript_segment",
                {"url": url, "start_seconds": 2, "end_seconds": 4},
            )
            assert [c["start_seconds"] for c in segment.structured_content["cues"]] == [
                2.0,
                3.0,
            ]
            lines, cursor = [], None
            while True:
                page = await client.call_tool(
                    "get_transcript_page",
                    {"url": url, "cursor": cursor, "max_chars": 1000},
                )
                data = page.structured_content
                assert len(data["document"]) <= 1000
                lines.extend(data["document"].splitlines())
                cursor = data["next_cursor"]
                if not data["has_more"]:
                    assert cursor is None
                    break
            assert len(lines) == 40
            for i, line in enumerate(lines):
                assert f"Cue {i:02d} " in line
            info = await client.call_tool("get_video_info", {"url": url})
            assert (
                info.structured_content["metadata"]
                == plain.structured_content["metadata"]
            )
            assert log.read_text().splitlines() == ["download", "lookup"]
            edited = await client.call_tool(
                "get_transcript",
                {"url": url, "output_format": "markdown"},
                progress_callback=report,
            )
            assert (
                edited.structured_content["document"] == "## Edited\n\nSource captions."
            )
            for _ in range(50):
                if len(notifications) == 3:
                    break
                await asyncio.sleep(0.01)
            assert [(p[0], p[1]) for p in notifications] == [(0, 2), (1, 2), (2, 2)]
            assert all(
                p[2] == f"Formatting model call {int(p[0])}/2" for p in notifications
            )
            again = await client.call_tool(
                "get_transcript", {"url": url, "output_format": "markdown"}
            )
            assert again.structured_content == edited.structured_content
        async with Client(params, raise_exceptions=True) as client:
            await client.call_tool(
                "get_video_info", {"url": "https://www.youtube.com/shorts/abcdefghijk"}
            )
        assert log.read_text().splitlines() == ["download", "lookup", "model", "model"]
        assert Path(tmp_path / "cache/yt-transcript/transcripts.db").exists()

    asyncio.run(check())
