"""Summary acceptance uses local fake Pi processes, never live models."""

import asyncio
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import yaml
from mcp import Client
from mcp.types import TextContent

from yt_transcript import formatter, service
from yt_transcript.chapters import Chapter, build_chapter_sections
from yt_transcript.cleaner import Cue
from yt_transcript.cli import main
from yt_transcript.config import AppConfig, load_config, resolve_config
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.errors import FormattingError, decode_worker_error
from yt_transcript.mcp_policy import MCPFormattingPolicy, validate_formatting_policy
from yt_transcript.mcp_server import create_server
from yt_transcript.mcp_worker import dispatch, validate_request
from yt_transcript.metadata import VideoMetadata
from yt_transcript.sponsorblock import SponsorBlockConfig

SUMMARY = "## Summary\n\nThe speaker explains retries.\n\n## Key points\n\n- Retries can duplicate writes.\n- Idempotency prevents duplicate effects."
SOURCE = "Retries can duplicate writes. Idempotency prevents duplicate effects. " * 30
URL = "https://www.youtube.com/watch?v=abcdefghijk"


def summary_pi(tmp_path, monkeypatch, outputs, *, sleep_at=None, reason_at=None):
    record = tmp_path / "summary-inputs.jsonl"
    script = tmp_path / "summary-pi.py"
    script.write_text(
        "import sys,json,time\n"
        + f"from pathlib import Path\nrecord=Path({str(record)!r})\n"
        + "index=len(record.read_text().splitlines()) if record.exists() else 0\n"
        + "data=sys.stdin.read()\n"
        + "with record.open('a') as f: f.write(json.dumps(data)+'\\n')\n"
        + f"body={outputs!r}[index]\n"
        + f"if index=={sleep_at!r}: time.sleep(10)\n"
        + f"reason='length' if index=={reason_at!r} else 'stop'\n"
        + "print(json.dumps({'type':'session'}))\n"
        + "print(json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':body}],'stopReason':reason}}))\n"
        + "print(json.dumps({'type':'agent_settled'}))\n"
    )
    original = formatter.subprocess.Popen
    calls = []

    def launch(argv, **kwargs):
        calls.append((argv, kwargs))
        return original([sys.executable, str(script)], **kwargs)

    monkeypatch.setattr(formatter, "ensure_pi", lambda: "fake-pi")
    monkeypatch.setattr(formatter.subprocess, "Popen", launch)
    return calls, record


def summary_plan(source=SOURCE, **kwargs):
    return formatter.plan_transcript_formatting(
        source, editorial_mode="summarized", chunk_chars=1000, **kwargs
    )


def test_configuration_and_policy_accept_summarized(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[pi]\neditorial_mode="summarized"')
    config = load_config(path)
    assert config.editorial_mode == "summarized"
    assert resolve_config(AppConfig(), editorial_mode="summarized") == config
    for mode in ("raw", "raw-vtt"):
        assert resolve_config(config, mode=mode).editorial_mode == "standard"
    policy = MCPFormattingPolicy(editorial_mode="summarized")
    assert validate_formatting_policy(asdict(policy)) == policy


def test_summary_prompt_has_no_transcript_editing_contract():
    prompt = formatter.get_editorial_prompt("summarized")
    assert "400" in prompt and "700" in prompt
    assert "untrusted" in prompt and "uncertainty" in prompt
    assert "## Summary" in prompt and "## Key points" in prompt
    assert "never a summary" not in prompt
    assert "not a summary" not in prompt


def test_single_chunk_uses_one_isolated_summary_call(tmp_path, monkeypatch):
    calls, record = summary_pi(tmp_path, monkeypatch, [SUMMARY])
    progress = []
    assert (
        formatter.format_with_pi(
            "Retries can duplicate writes.",
            editorial_mode="summarized",
            model="provider/model",
            max_chunks=1,
            own_process_group=False,
            on_progress=lambda n, total: progress.append((n, total)),
        )
        == SUMMARY
    )
    assert progress == [(0, 1), (1, 1)]
    assert record.read_text().splitlines() == [
        json.dumps("Retries can duplicate writes.")
    ]
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert all(flag in argv for flag in formatter.ISOLATION_FLAGS)
    assert argv[argv.index("--model") + 1] == "provider/model"
    assert "Summarize" in argv[-1] and "Edit transcript" not in argv[-1]
    assert not kwargs["start_new_session"]
    assert not Path(kwargs["cwd"]).exists()


def test_multiple_chunks_produce_bounded_notes_then_one_summary(tmp_path, monkeypatch):
    plan = summary_plan()
    assert len(plan.chunks) > 1
    assert plan.call_count == len(plan.chunks) + 1
    notes = ['- Claim "quoted"; uncertainty remains. 😀' for _ in plan.chunks]
    calls, record = summary_pi(tmp_path, monkeypatch, [*notes, SUMMARY])
    progress = []
    result = formatter.format_with_pi(
        SOURCE,
        editorial_mode="summarized",
        chunk_chars=1000,
        max_chunks=plan.call_count,
        timeout_seconds=2,
        on_progress=lambda n, total: progress.append((n, total)),
    )
    assert result == SUMMARY and "quoted" not in result
    inputs = [json.loads(line) for line in record.read_text().splitlines()]
    assert tuple(inputs[:-1]) == plan.chunks
    synthesis = json.loads(inputs[-1])
    assert synthesis == {
        "notes": [
            {"chunk_index": index, "text": note} for index, note in enumerate(notes, 1)
        ]
    }
    assert len(inputs[-1]) <= 1000
    assert len(calls) == plan.call_count
    assert progress == [(n, plan.call_count) for n in range(plan.call_count + 1)]
    assert "notes" in calls[0][0][-1]
    assert "whole-video summary" in calls[-1][0][-1]
    assert all(not Path(kwargs["cwd"]).exists() for _, kwargs in calls)


def test_synthesis_is_reserved_by_cap_before_launch(monkeypatch):
    plan = summary_plan()
    capped = summary_plan(max_chunks=len(plan.chunks))
    assert not capped.within_cap
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("must not launch"))
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi(
            SOURCE,
            editorial_mode="summarized",
            chunk_chars=1000,
            max_chunks=len(plan.chunks),
        )
    assert exc.value.info.code == "CHUNK_LIMIT_EXCEEDED"
    assert str(plan.call_count) in exc.value.info.message
    safe = decode_worker_error(asdict(exc.value.info))
    assert safe.message == exc.value.info.message
    assert safe.code == "CHUNK_LIMIT_EXCEEDED"
    tampered = replace(
        exc.value.info, message=exc.value.info.message + "; private token"
    )
    assert "private token" not in decode_worker_error(asdict(tampered)).message


def test_summary_note_budget_is_checked_before_launch(monkeypatch):
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("must not launch"))
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi(
            "word " * 10000,
            editorial_mode="summarized",
            chunk_chars=1000,
        )
    assert exc.value.info.code == "PI_CONTEXT_LIMIT"


@pytest.mark.parametrize("bad", ["x" * 1000, '"' * 200, formatter.OMISSION_MARKER])
def test_bad_notes_fail_without_synthesis_or_partial_output(tmp_path, monkeypatch, bad):
    plan = summary_plan()
    calls, _ = summary_pi(tmp_path, monkeypatch, [bad])
    progress = []
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi(
            SOURCE,
            editorial_mode="summarized",
            chunk_chars=1000,
            on_progress=lambda n, total: progress.append((n, total)),
        )
    assert exc.value.info.code == "PI_OUTPUT_INVALID"
    assert (exc.value.info.chunk_index, exc.value.info.chunk_total) == (
        1,
        plan.call_count,
    )
    assert len(calls) == 1 and progress == [(0, plan.call_count)]


@pytest.mark.parametrize(
    "bad", ["## Edited\n\ntranscript", "## Summary\n\n", SUMMARY + "\n# Invalid"]
)
def test_invalid_final_summary_fails_and_does_not_complete_progress(
    tmp_path, monkeypatch, bad
):
    plan = summary_plan()
    calls, _ = summary_pi(
        tmp_path, monkeypatch, [*["- Factual note."] * len(plan.chunks), bad]
    )
    progress = []
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi(
            SOURCE,
            editorial_mode="summarized",
            chunk_chars=1000,
            on_progress=lambda n, total: progress.append((n, total)),
        )
    assert exc.value.info.code == "PI_OUTPUT_INVALID"
    assert (exc.value.info.chunk_index, exc.value.info.chunk_total) == (
        plan.call_count,
        plan.call_count,
    )
    assert len(calls) == plan.call_count
    assert progress[-1] == (len(plan.chunks), plan.call_count)


def test_summary_context_preserves_input_not_canonical_output_headings(
    tmp_path, monkeypatch
):
    sections = build_chapter_sections(
        (Cue(0, 1000, "Retries can duplicate writes."),),
        (Chapter("Untrusted chapter title", 0, 2000),),
    )
    calls, record = summary_pi(tmp_path, monkeypatch, [SUMMARY])
    result = formatter.format_with_pi(
        "Retries can duplicate writes.",
        sections=sections,
        editorial_mode="summarized",
    )
    assert result == SUMMARY and "Untrusted chapter title" not in result
    assert (
        json.loads(json.loads(record.read_text()))["runs"][0]["title"]
        == "Untrusted chapter title"
    )
    append = calls[0][0][calls[0][0].index("--append-system-prompt") + 1]
    assert "canonical" not in append and "untrusted" in append


def download_fixture(monkeypatch):
    metadata = VideoMetadata(URL, "abcdefghijk", description="DESCRIPTION_NOT_PI_INPUT")
    vtt = b"WEBVTT\n\n00:00.000 --> 00:01.000\n" + SOURCE.encode() + b"\n"
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(vtt, "en", False, metadata),
    )
    return metadata


def test_cli_preview_counts_synthesis_without_pi(tmp_path, monkeypatch, capsys):
    download_fixture(monkeypatch)
    config = tmp_path / "config.toml"
    config.write_text("[pi]\nchunk_chars=1000\n[sponsorblock]\nenabled=false")
    monkeypatch.setattr(
        formatter, "ensure_pi", lambda: pytest.fail("preview must not launch Pi")
    )
    assert (
        main(
            [
                URL,
                "--config",
                str(config),
                "--editorial-mode",
                "summarized",
                "--preview",
            ]
        )
        == 0
    )
    out = capsys.readouterr()
    assert f"planned formatter invocations: {summary_plan().call_count}" in out.out
    assert "editorial mode: summarized" in out.out and not out.err


def test_cli_failed_synthesis_keeps_existing_file(tmp_path, monkeypatch, capsys):
    download_fixture(monkeypatch)
    config = tmp_path / "config.toml"
    config.write_text(
        '[pi]\nchunk_chars=1000\neditorial_mode="summarized"\n[sponsorblock]\nenabled=false'
    )
    plan = summary_plan()
    calls, record = summary_pi(
        tmp_path,
        monkeypatch,
        [*["- Factual note."] * len(plan.chunks), "## Edited\n\nwrong"],
    )
    output = tmp_path / "existing.md"
    output.write_text("original")
    assert main([URL, "--config", str(config), "-o", str(output)]) == 1
    out = capsys.readouterr()
    assert output.read_text() == "original" and not out.out
    assert "PI_OUTPUT_INVALID" in out.err
    assert "DESCRIPTION_NOT_PI_INPUT" not in record.read_text()
    assert len(calls) == plan.call_count


def test_cli_summary_yaml_keeps_metadata_out_of_pi(tmp_path, monkeypatch, capsys):
    metadata = download_fixture(monkeypatch)
    plan = summary_plan()
    calls, record = summary_pi(
        tmp_path, monkeypatch, [*["- Factual note."] * len(plan.chunks), SUMMARY]
    )
    config = tmp_path / "config.toml"
    config.write_text("[pi]\nchunk_chars=1000\n[sponsorblock]\nenabled=false")
    output = tmp_path / "summary.md"
    assert (
        main(
            [
                URL,
                "--config",
                str(config),
                "--editorial-mode",
                "summarized",
                "-o",
                str(output),
            ]
        )
        == 0
    )
    _, header, body = output.read_text().split("---\n", 2)
    assert yaml.safe_load(header)["description"] == metadata.description
    assert body == "\n" + SUMMARY + "\n"
    assert "DESCRIPTION_NOT_PI_INPUT" not in record.read_text()
    assert len(calls) == plan.call_count
    assert not capsys.readouterr().out


def test_saved_summary_preference_does_not_change_cli_raw(
    tmp_path, monkeypatch, capsys
):
    download_fixture(monkeypatch)
    config = tmp_path / "config.toml"
    config.write_text(
        '[pi]\neditorial_mode="summarized"\n[sponsorblock]\nenabled=false'
    )
    monkeypatch.setattr(
        formatter, "ensure_pi", lambda: pytest.fail("raw must not check Pi")
    )
    assert main([URL, "--config", str(config), "--raw"]) == 0
    assert capsys.readouterr().out == SOURCE.strip() + "\n"


def test_summary_notes_fill_but_never_exceed_synthesis_budget(tmp_path, monkeypatch):
    plan = summary_plan()
    limit = formatter._summary_note_limit(len(plan.chunks), 1000)
    calls, record = summary_pi(
        tmp_path, monkeypatch, [*["x" * limit] * len(plan.chunks), SUMMARY]
    )
    assert (
        formatter.format_with_pi(SOURCE, editorial_mode="summarized", chunk_chars=1000)
        == SUMMARY
    )
    payload = json.loads(record.read_text().splitlines()[-1])
    assert 1000 - len(plan.chunks) < len(payload) <= 1000
    assert len(calls) == plan.call_count


@pytest.mark.parametrize("failure", ["timeout", "incomplete"])
def test_synthesis_failure_preserves_diagnostics_and_cleanup(
    tmp_path, monkeypatch, failure
):
    plan = summary_plan()
    calls, _ = summary_pi(
        tmp_path,
        monkeypatch,
        [*["- Factual note."] * len(plan.chunks), SUMMARY],
        sleep_at=len(plan.chunks) if failure == "timeout" else None,
        reason_at=len(plan.chunks) if failure == "incomplete" else None,
    )
    progress = []
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi(
            SOURCE,
            editorial_mode="summarized",
            chunk_chars=1000,
            timeout_seconds=1,
            on_progress=lambda n, total: progress.append((n, total)),
        )
    assert exc.value.info.code == (
        "PI_TIMEOUT" if failure == "timeout" else "PI_OUTPUT_INCOMPLETE"
    )
    assert (exc.value.info.chunk_index, exc.value.info.chunk_total) == (
        plan.call_count,
        plan.call_count,
    )
    assert progress[-1] == (len(plan.chunks), plan.call_count)
    assert all(not Path(kwargs["cwd"]).exists() for _, kwargs in calls)


@pytest.mark.parametrize(
    "bad",
    ["", "```markdown\n" + SUMMARY + "\n```", "---\ntitle: fake\n---\n" + SUMMARY],
)
def test_summary_keeps_existing_body_safety_checks(tmp_path, monkeypatch, bad):
    summary_pi(tmp_path, monkeypatch, [bad])
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi("source", editorial_mode="summarized")
    assert exc.value.info.code == "PI_OUTPUT_INVALID"


def test_summary_optional_caveats_section(tmp_path, monkeypatch):
    body = (
        SUMMARY + "\n\n## Conclusions and caveats\n\nThe speaker qualifies the result."
    )
    summary_pi(tmp_path, monkeypatch, [body])
    assert formatter.format_with_pi("source", editorial_mode="summarized") == body


def test_mcp_server_summary_policy_and_compatibility_round_trip(tmp_path, monkeypatch):
    metadata = download_fixture(monkeypatch)
    plan = summary_plan()
    calls, record = summary_pi(
        tmp_path, monkeypatch, ([*["- Factual note."] * len(plan.chunks), SUMMARY]) * 2
    )

    class Runner:
        async def close(self):
            pass

        async def run(self, payload):
            return dict(dispatch(validate_request(payload)))

    async def check():
        config = AppConfig(
            editorial_mode="summarized",
            chunk_chars=1000,
            sponsorblock=SponsorBlockConfig(enabled=False),
        )
        async with Client(create_server(config, runner=Runner())) as client:
            tool = (await client.list_tools()).tools[0]
            assert set(tool.input_schema["properties"]) == {
                "url",
                "mode",
                "output_format",
            }
            for mode in ("filtered", "full"):
                result = await client.call_tool(
                    "get_transcript",
                    {"url": URL, "mode": mode, "output_format": "markdown"},
                )
                assert not result.is_error
                structured = result.structured_content
                assert structured["document"] == SUMMARY
                assert structured["format"] == "markdown"
                assert structured["character_count"] == len(SUMMARY)
                assert structured["metadata"]["description"] == metadata.description
                service.validate_service_result("get_transcript", structured)
                assert isinstance(result.content[0], TextContent)
                assert json.loads(result.content[0].text) == structured
                plain = await client.call_tool(
                    "get_transcript", {"url": URL, "mode": mode}
                )
                assert (
                    not plain.is_error
                    and plain.structured_content["format"] == "plain_text"
                )
                assert SOURCE.strip() in plain.structured_content["document"]
            invalid = await client.call_tool(
                "get_transcript", {"url": URL, "editorial_mode": "summarized"}
            )
            assert invalid.is_error
        assert len(calls) == 2 * plan.call_count
        assert all(not kwargs["start_new_session"] for _, kwargs in calls)
        assert "DESCRIPTION_NOT_PI_INPUT" not in record.read_text()

    asyncio.run(check())
