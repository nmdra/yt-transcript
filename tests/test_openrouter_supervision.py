"""Real local helpers prove deadlines and cleanup, never HTTP or a model."""

import json
import subprocess
import sys
import time
from dataclasses import asdict

import pytest

from yt_transcript import formatter
from yt_transcript import openrouter_backend as backend
from yt_transcript.errors import FormattingError, classify_openrouter_failure


def install_helper(tmp_path, monkeypatch, code):
    script = tmp_path / "helper.py"
    script.write_text("import sys,json,time,signal\n" + code)
    original = subprocess.Popen
    processes = []
    argv_seen = []

    def launch(argv, **kwargs):
        argv_seen.append(argv)
        process = original([sys.executable, str(script)], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(backend.subprocess, "Popen", launch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "TEST_KEY_NOT_FOR_OUTPUT")
    return processes, argv_seen


def request(**kwargs):
    return formatter.ChunkRequest(
        "source",
        "source only",
        "edit",
        kwargs.pop("source", "caption"),
        "provider/model",
        1,
        **kwargs,
    )


def test_helper_success_and_credentials_not_serialized(tmp_path, monkeypatch):
    record = tmp_path / "stdin.json"
    processes, argv = install_helper(
        tmp_path,
        monkeypatch,
        "from pathlib import Path\n"
        + f"data=sys.stdin.read(); Path({str(record)!r}).write_text(data)\n"
        + "sys.stderr.write('Bearer private' * 10000)\nprint(json.dumps({'text':'## Edited\\n\\nCaption.'}))\n",
    )
    assert backend.complete(request()).startswith("## Edited")
    assert processes[0].poll() == 0
    assert "TEST_KEY_NOT_FOR_OUTPUT" not in record.read_text() + repr(argv)
    assert "own_process_group" not in json.loads(record.read_text())


@pytest.mark.parametrize(
    "code",
    [
        "print('private malformed')",
        "sys.stdout.write('x'*10000)",
        "print(json.dumps({'text':42}))",
        "print(json.dumps({'text':'okay','extra':'private'}))",
    ],
)
def test_invalid_helper_output_is_safe_and_reaped(tmp_path, monkeypatch, code):
    processes, _ = install_helper(tmp_path, monkeypatch, "sys.stdin.read()\n" + code)
    monkeypatch.setattr(backend, "HELPER_LIMIT", 1000)
    with pytest.raises(FormattingError) as exc:
        backend.complete(request())
    assert exc.value.info.code == "OPENROUTER_OUTPUT_INVALID"
    assert "private" not in str(exc.value) and processes[0].poll() is not None


@pytest.mark.parametrize("read_input", [True, False])
def test_hard_deadline_kills_sigterm_resistant_helper(
    tmp_path, monkeypatch, read_input
):
    code = (
        "sys.stdin.read()\n" if read_input else ""
    ) + "signal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(20)"
    processes, _ = install_helper(tmp_path, monkeypatch, code)
    start = time.monotonic()
    with pytest.raises(FormattingError) as exc:
        backend.complete(request(source="caption " * 30000))
    assert exc.value.info.code == "OPENROUTER_TIMEOUT"
    assert processes[0].poll() is not None and time.monotonic() - start < 6


def test_worker_errors_are_sanitized(tmp_path, monkeypatch):
    info = asdict(classify_openrouter_failure("OPENROUTER_AUTH_FAILED").info)
    info["message"] = "Bearer private"
    processes, _ = install_helper(
        tmp_path,
        monkeypatch,
        "sys.stdin.read()\nprint(" + repr(json.dumps({"error": info})) + ")",
    )
    with pytest.raises(FormattingError) as exc:
        backend.complete(request(own_process_group=False))
    assert "private" not in str(exc.value)
    assert (
        exc.value.info.code == "OPENROUTER_AUTH_FAILED"
        and processes[0].poll() is not None
    )


def test_real_worker_invalid_request_never_calls_http():
    result = subprocess.run(
        [sys.executable, "-m", "yt_transcript.openrouter_worker"],
        input=b'{"private":"bad"}',
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0 and not result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "OPENROUTER_OUTPUT_INVALID"
    assert b"private" not in result.stdout
