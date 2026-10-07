"""Process-tree regression checks use local fake workers only."""

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from yt_transcript.errors import AppError
from yt_transcript.mcp_server import WorkerRunner


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process-state inspection")
def test_exited_worker_with_pipe_holding_descendant_is_cleaned(tmp_path, monkeypatch):
    marker = tmp_path / "descendant.pid"
    child = tmp_path / "worker.py"
    child.write_text(
        "import os,subprocess,sys\n"
        "process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"open({str(marker)!r}, 'w').write(str(process.pid))\n"
        "sys.stdin.buffer.read()\n"
        "os._exit(0)\n"
    )
    original = asyncio.create_subprocess_exec

    async def launch(*args, **kwargs):
        return await original(sys.executable, str(child), **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)

    async def check():
        try:
            with pytest.raises(AppError) as exc:
                await WorkerRunner(timeout_seconds=0.5).run({"operation": "doctor"})
            assert exc.value.info.code == "MCP_TIMEOUT"
            pid = int(marker.read_text())
            # Orphans can briefly remain zombies until the OS reaps them.
            for _ in range(100):
                stat = Path(f"/proc/{pid}/stat")
                if not stat.exists() or stat.read_text().split(") ", 1)[1][0] == "Z":
                    return
                await asyncio.sleep(0.01)
            pytest.fail("The pipe-holding descendant still runs after cleanup")
        finally:
            if marker.exists():
                try:
                    os.kill(int(marker.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    asyncio.run(check())
