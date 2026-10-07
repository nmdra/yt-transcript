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
            assert {tool.name for tool in tools} == {
                "get_transcript",
                "preview_transcript",
                "doctor",
            }
            result = await client.call_tool(
                "get_transcript",
                {"url": "https://invalid.example/private?token=secret"},
            )
            assert result.is_error
            assert "INVALID_URL" in text_content(result)
            assert "secret" not in text_content(result)
            assert len((await client.list_tools()).tools) == 3

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
            assert len(json.loads(listing)["result"]["tools"]) == 3
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
            assert len((await client.list_tools()).tools) == 3
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
    async def run(self, payload):
        cleaned=CleanedTranscript("hello world",VideoMetadata("https://www.youtube.com/watch?v=abcdefghijk","abcdefghijk"),"en",False)
        return {"format":"plain_text","document":cleaned.document(),"metadata":cleaned.mapping(),"character_count":11}
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
            assert result.structured_content["document"].endswith("\n\nhello world\n")
            assert json.loads(text_content(result)) == result.structured_content

    asyncio.run(check())
