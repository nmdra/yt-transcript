from pathlib import Path

import pytest

from yt_transcript import formatter
from yt_transcript.errors import FormattingError


def fake_pi(
    tmp_path,
    monkeypatch,
    *,
    reason="stop",
    sleep=False,
    exit_code=0,
    output="## Edited 😀",
):
    script = tmp_path / "fake_pi.py"
    script.write_text(
        "import sys,json,time,os\n"
        + "text=sys.stdin.buffer.read().decode()\n"
        + f"with open({str(tmp_path / 'inputs.jsonl')!r},'a',encoding='utf-8') as stream: stream.write(json.dumps(text,ensure_ascii=False)+'\\n')\n"
        + ("time.sleep(10)\n" if sleep else "")
        + 'sys.stderr.write("private" * 20000)\n'
        + f'events=[{{"type":"session"}},{{"type":"message_end","message":{{"role":"assistant","content":[{{"type":"text","text":{output!r}}}],"stopReason":{reason!r}}}}},{{"type":"agent_settled"}}]\n'
        + "for event in events: print(json.dumps(event,ensure_ascii=False),flush=True)\n"
        + f"sys.exit({exit_code})\n"
    )
    original = formatter.subprocess.Popen
    processes = []
    invocations = []
    import sys

    def launch(argv, **kwargs):
        invocations.append((argv, kwargs))
        process = original([sys.executable, str(script)], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(formatter, "ensure_pi", lambda: "resolved-pi")
    monkeypatch.setattr(formatter.subprocess, "Popen", launch)
    return invocations, processes


def test_process_and_isolation(tmp_path, monkeypatch):
    calls, processes = fake_pi(tmp_path, monkeypatch)
    assert (
        formatter.format_with_pi("source 😀", model="provider/model") == "## Edited 😀"
    )
    argv, kwargs = calls[0]
    assert argv[0] == "resolved-pi"
    assert all(flag in argv for flag in formatter.ISOLATION_FLAGS)
    assert argv[argv.index("--model") + 1] == "provider/model"
    assert "source 😀" not in " ".join(argv)
    assert not Path(kwargs["cwd"]).exists()
    assert processes[0].poll() == 0


def test_default_model_omitted(tmp_path, monkeypatch):
    calls, _ = fake_pi(tmp_path, monkeypatch)
    formatter.format_with_pi("source")
    assert "--model" not in calls[0][0]


@pytest.mark.parametrize(
    "reason,exit_code,code",
    [
        ("length", 0, "PI_OUTPUT_INCOMPLETE"),
        ("stop", 1, "PI_FAILED"),
        ("aborted", 0, "PI_ABORTED"),
    ],
)
def test_failures(tmp_path, monkeypatch, reason, exit_code, code):
    _, processes = fake_pi(tmp_path, monkeypatch, reason=reason, exit_code=exit_code)
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi("source")
    assert exc.value.info.code == code
    assert processes[0].poll() is not None


def test_timeout_reaps(tmp_path, monkeypatch):
    calls, processes = fake_pi(tmp_path, monkeypatch, sleep=True)
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi("source", timeout_seconds=1)
    assert exc.value.info.code == "PI_TIMEOUT"
    assert processes[0].poll() is not None
    assert not Path(calls[0][1]["cwd"]).exists()


@pytest.mark.parametrize(
    "output", ["", "```markdown\nbody\n```", "---\ntitle: fake\n---\nbody"]
)
def test_body_rejection(tmp_path, monkeypatch, output):
    fake_pi(tmp_path, monkeypatch, output=output)
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi("source")
    assert exc.value.info.code == "PI_OUTPUT_INVALID"


def test_internal_fences_and_rule(tmp_path, monkeypatch):
    body = "---\n\n## Section\n\n```python\nprint(1)\n```\n\ncontinuation"
    fake_pi(tmp_path, monkeypatch, output=body)
    assert formatter.format_with_pi("source") == body


def test_sequential_inputs_no_extra_call(tmp_path, monkeypatch):
    import json

    calls, _ = fake_pi(tmp_path, monkeypatch)
    source = "Café one two. Next command --flag. Third sentence."
    plan = formatter.plan_formatting(source, chunk_chars=25)
    body = formatter.format_with_pi(source, chunk_chars=25)
    inputs = [
        json.loads(line)
        for line in (tmp_path / "inputs.jsonl").read_text().splitlines()
    ]
    assert tuple(inputs) == plan.chunks
    assert len(calls) == len(plan.chunks)
    assert body.count("## Edited") == len(plan.chunks)


def test_interrupt_cleanup(tmp_path, monkeypatch):
    calls, processes = fake_pi(tmp_path, monkeypatch, sleep=True)
    original = formatter.time.sleep
    interrupted = False

    def interrupt(duration):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return original(duration)

    monkeypatch.setattr(formatter.time, "sleep", interrupt)
    with pytest.raises(KeyboardInterrupt):
        formatter.format_with_pi("source")
    assert processes[0].poll() is not None
    assert not Path(calls[0][1]["cwd"]).exists()


def test_launch_error(monkeypatch):
    monkeypatch.setattr(formatter, "ensure_pi", lambda: "pi")

    def denied(*args, **kwargs):
        raise OSError("Bearer secret")

    monkeypatch.setattr(formatter.subprocess, "Popen", denied)
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi("source")
    assert exc.value.info.code == "PI_LAUNCH_FAILED"


def test_chunking_and_cap(monkeypatch):
    text = "One two three. Four five six. Seven eight nine."
    plan = formatter.plan_formatting(text, chunk_chars=20, max_chunks=1)
    assert " ".join(plan.chunks) == text
    assert max(plan.character_counts) <= 20
    assert not plan.within_cap
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("must not launch"))
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi(text, chunk_chars=20, max_chunks=1)
    assert exc.value.info.code == "CHUNK_LIMIT_EXCEEDED"
    with pytest.raises(FormattingError):
        formatter.split_transcript("a" * 21, max_chars=20)


def test_progress_counts_only_validated_chunks(tmp_path, monkeypatch):
    fake_pi(tmp_path, monkeypatch)
    progress = []
    text = "One two three. Four five six. Seven eight nine."
    total = len(formatter.plan_formatting(text, chunk_chars=20).chunks)
    formatter.format_with_pi(
        text, chunk_chars=20, on_progress=lambda n, total: progress.append((n, total))
    )
    assert progress == [(n, total) for n in range(total + 1)]


def test_failed_chunk_does_not_increment_progress(tmp_path, monkeypatch):
    fake_pi(tmp_path, monkeypatch, reason="length")
    progress = []
    with pytest.raises(FormattingError):
        formatter.format_with_pi(
            "source", on_progress=lambda n, total: progress.append((n, total))
        )
    assert progress == [(0, 1)]


def test_inherited_process_group_timeout_reaps_direct_child(tmp_path, monkeypatch):
    _, processes = fake_pi(tmp_path, monkeypatch, sleep=True)
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi("source", timeout_seconds=1, own_process_group=False)
    assert exc.value.info.code == "PI_TIMEOUT"
    assert processes[0].poll() is not None
