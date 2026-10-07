import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from yt_transcript.errors import AppError
from yt_transcript.mcp_server import WorkerRunner
from yt_transcript.mcp_worker import validate_request


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "pi"},
        {"operation": []},
        {"operation": {}},
        {"operation": "doctor", "path": "private"},
        {"operation": "get_transcript", "url": "https://example.com"},
        {
            "operation": "get_transcript",
            "url": "https://youtu.be/abcdefghijk",
            "model": "x",
        },
    ],
)
def test_requests(payload):
    with pytest.raises((ValueError, AppError)):
        validate_request(payload)


def test_real_worker_invalid_request():
    result = subprocess.run(
        [sys.executable, "-m", "yt_transcript.mcp_worker"],
        input=b'{"operation":"pi","token":"secret"}',
        capture_output=True,
        timeout=5,
    )
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "CONFIG_INVALID"
    assert b"secret" not in result.stdout and not result.stderr


def install_child(tmp_path, monkeypatch, code):
    script = tmp_path / "child.py"
    script.write_text(code)
    original = asyncio.create_subprocess_exec
    processes = []

    async def launch(*args, **kwargs):
        process = await original(sys.executable, str(script), **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    return processes


def test_timeout_cancellation_cleanup_and_reuse(tmp_path, monkeypatch):
    marker = tmp_path / "marker"
    code = f"""import sys,time,signal
from tempfile import TemporaryDirectory
from pathlib import Path
def stop(*args): raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
    with TemporaryDirectory() as root:
        Path({str(marker)!r}).write_text(root)
        sys.stdin.buffer.read()
        sys.stderr.write('private' * 20000)
        sys.stderr.flush()
        time.sleep(30)
except KeyboardInterrupt: pass
"""
    processes = install_child(tmp_path, monkeypatch, code)

    async def check():
        runner = WorkerRunner(timeout_seconds=0.3)
        with pytest.raises(AppError) as exc:
            await runner.run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                }
            )
        assert exc.value.info.code == "MCP_TIMEOUT"
        assert processes[0].returncode is not None
        assert not Path(marker.read_text()).exists()
        runner.timeout_seconds = 10
        task = asyncio.create_task(
            runner.run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                }
            )
        )
        while len(processes) < 2:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        with pytest.raises(AppError) as exc:
            await runner.run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                }
            )
        assert exc.value.info.code == "MCP_BUSY"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[-1].returncode is not None
        assert not Path(marker.read_text()).exists()
        assert not runner._busy

    asyncio.run(check())


def test_response_limit_reaps(tmp_path, monkeypatch):
    processes = install_child(
        tmp_path,
        monkeypatch,
        "import sys,time\nsys.stdin.buffer.read()\nsys.stdout.buffer.write(b'x' * 1200000)\nsys.stdout.flush()\ntime.sleep(30)\n",
    )

    async def check():
        with pytest.raises(AppError) as exc:
            await WorkerRunner(timeout_seconds=5).run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                }
            )
        assert exc.value.info.code == "MCP_RESPONSE_LIMIT"
        assert processes[0].returncode is not None

    asyncio.run(check())
