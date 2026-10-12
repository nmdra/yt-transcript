"""Real local helpers prove deadlines and cleanup, never HTTP or a model."""

import json
import subprocess
import sys
import time
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from yt_transcript import deepseek_backend as backend
from yt_transcript import formatter
from yt_transcript.errors import FormattingError, classify_deepseek_failure


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
    monkeypatch.setenv("DEEPSEEK_API_KEY", "TEST_KEY_NOT_FOR_OUTPUT")
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
    assert exc.value.info.code == "DEEPSEEK_OUTPUT_INVALID"
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
    assert exc.value.info.code == "DEEPSEEK_TIMEOUT"
    assert processes[0].poll() is not None and time.monotonic() - start < 6


def test_worker_errors_are_sanitized(tmp_path, monkeypatch):
    info = asdict(classify_deepseek_failure("DEEPSEEK_AUTH_FAILED").info)
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
        exc.value.info.code == "DEEPSEEK_AUTH_FAILED"
        and processes[0].poll() is not None
    )


def test_real_worker_invalid_request_never_calls_http():
    result = subprocess.run(
        [sys.executable, "-m", "yt_transcript.deepseek_worker"],
        input=b'{"private":"bad"}',
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0 and not result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "DEEPSEEK_OUTPUT_INVALID"
    assert b"private" not in result.stdout


def test_cancellation_reaps_helper(tmp_path, monkeypatch):
    processes, _ = install_helper(
        tmp_path, monkeypatch, "sys.stdin.read()\ntime.sleep(20)"
    )

    def cancel(_):
        raise KeyboardInterrupt

    # Keep subprocess.wait's cleanup clock intact while interrupting supervision.
    monkeypatch.setattr(
        backend, "time", SimpleNamespace(monotonic=time.monotonic, sleep=cancel)
    )
    with pytest.raises(KeyboardInterrupt):
        backend.complete(request())
    assert processes[0].poll() is not None


def test_input_bound_prevents_helper_launch(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "TEST_KEY_NOT_FOR_OUTPUT")
    monkeypatch.setattr(backend, "INPUT_LIMIT", 100)
    monkeypatch.setattr(
        backend.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not launch")
    )
    with pytest.raises(FormattingError) as exc:
        backend.complete(request())
    assert exc.value.info.code == "DEEPSEEK_CONTEXT_LIMIT"


@pytest.mark.parametrize(
    "raw",
    [
        '{"text":"first","text":"private"}',
        '{"text":NaN}',
        '{"text":" "}',
        '{"text":"okay","reasoning_content":"PRIVATE_REASONING"}',
    ],
)
def test_helper_strict_json_envelope(tmp_path, monkeypatch, raw):
    processes, _ = install_helper(
        tmp_path, monkeypatch, "sys.stdin.read()\nprint(" + repr(raw) + ")"
    )
    with pytest.raises(FormattingError) as exc:
        backend.complete(request())
    assert exc.value.info.code == "DEEPSEEK_OUTPUT_INVALID"
    assert "PRIVATE_REASONING" not in str(exc.value)
    assert processes[0].poll() is not None


def test_helper_cannot_forward_other_provider_error(tmp_path, monkeypatch):
    from yt_transcript.errors import classify_pi_failure

    info = asdict(classify_pi_failure(code="PI_AUTH_FAILED").info)
    install_helper(
        tmp_path,
        monkeypatch,
        "sys.stdin.read()\nprint(" + repr(json.dumps({"error": info})) + ")",
    )
    with pytest.raises(FormattingError) as exc:
        backend.complete(request())
    assert exc.value.info.code == "DEEPSEEK_OUTPUT_INVALID"


def test_worker_oversized_input_never_calls_http():
    result = subprocess.run(
        [sys.executable, "-m", "yt_transcript.deepseek_worker"],
        input=b"x" * (backend.INPUT_LIMIT + 1),
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout)["error"]["code"] == "DEEPSEEK_OUTPUT_INVALID"
