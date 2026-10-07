"""Context and omission acceptance uses local fake Pi processes, never a model."""

import json
import sys
from pathlib import Path

import pytest

from yt_transcript import formatter
from yt_transcript.chapters import Chapter, build_chapter_sections
from yt_transcript.cleaner import Cue
from yt_transcript.errors import FormattingError
from yt_transcript.sponsorblock import AnnotatedCue, SponsorBlockSegment


def sections(text="alpha beta gamma", chapters=None):
    return build_chapter_sections(
        (Cue(0, 1000, text),), chapters or (Chapter("Topic", 0, 10000),)
    )


def context_pi(tmp_path, monkeypatch, transform=""):
    script = tmp_path / "context_pi.py"
    record = tmp_path / "context_inputs.jsonl"
    script.write_text(
        "import sys,json\n"
        "data=json.loads(sys.stdin.read())\n"
        + f"with open({str(record)!r},'a') as f: f.write(json.dumps(data)+'\\n')\n"
        + "parts=[]\n"
        + "for run in data['runs']:\n"
        + "    text=' '.join(f['text'] for f in run['fragments'])\n"
        + "    parts.append((run['heading']+'\\n\\n' if run['heading'] else '')+text)\n"
        + "body='\\n\\n'.join(parts)\n"
        + transform
        + "\n"
        + "print(json.dumps({'type':'session'}))\n"
        + "print(json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':body}],'stopReason':'stop'}}))\n"
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


def test_context_unicode_title_escaping_and_exact_input_count():
    runs = sections(
        "café 😀 \\ command", (Chapter('Title **bold**\n"quote" 😀', 0, 5000),)
    )
    plan = formatter.plan_context_formatting(runs, chunk_chars=1000)
    payload = json.loads(plan.chunks[0])
    assert "😀" in plan.chunks[0]
    assert plan.character_counts == (len(plan.chunks[0]),)
    assert payload["runs"][0]["fragments"][0]["text"] == runs[0].text
    assert "\n" not in payload["runs"][0]["heading"]
    assert "\\*" in payload["runs"][0]["heading"]


def test_context_failure_keeps_existing_file(tmp_path, monkeypatch, capsys):
    from yt_transcript import service
    from yt_transcript.cli import main
    from yt_transcript.downloader import DownloadedCaptions
    from yt_transcript.metadata import VideoMetadata

    context_pi(tmp_path, monkeypatch, "body=body.replace('Topic', 'wrong')")
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk",
        chapters=(Chapter("Topic", 0, 10000),),
        chapter_status="available",
    )
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nsource\n", "en", False, metadata
        ),
    )
    path = tmp_path / "existing.md"
    path.write_text("original")
    assert main([metadata.url, "--no-config", "-o", str(path)]) == 1
    assert path.read_text() == "original"
    output = capsys.readouterr()
    assert not output.out and "PI_OUTPUT_INVALID" in output.err
    assert "Topic" not in output.err and "source" not in output.err


def test_pack_short_runs_and_split_long_context_without_word_loss():
    source = tuple(
        Cue(i * 1000, (i + 1) * 1000, "word " * 50 + str(i)) for i in range(10)
    )
    runs = build_chapter_sections(
        source, (Chapter("A", 0, 5000), Chapter("B", 5000, 10000))
    )
    plan = formatter.plan_context_formatting(runs, chunk_chars=1000, max_chunks=1)
    assert not plan.within_cap and max(plan.character_counts) <= 1000
    decoded = [json.loads(c) for c in plan.chunks]
    words = " ".join(
        f["text"]
        for payload in decoded
        for run in payload["runs"]
        for f in run["fragments"]
    )
    assert words == " ".join(c.text for c in source)
    assert any(run["continuation"] for payload in decoded for run in payload["runs"])
    small = build_chapter_sections(
        (Cue(0, 500, "a"), Cue(1000, 1500, "b")),
        (Chapter("A", 0, 1000), Chapter("B", 1000, 2000)),
    )
    assert len(formatter.plan_context_formatting(small, chunk_chars=1000).chunks) == 1


def test_context_overhead_limit_launches_nothing(monkeypatch):
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("must not launch"))
    with pytest.raises(FormattingError) as error:
        formatter.format_with_pi(
            "x" * 1000, sections=sections("x" * 1000), chunk_chars=1000
        )
    assert error.value.info.code == "PI_CONTEXT_LIMIT"
    with pytest.raises(FormattingError) as error:
        formatter.format_with_pi(
            "word " * 400,
            sections=sections("word " * 400),
            chunk_chars=1000,
            max_chunks=1,
        )
    assert error.value.info.code == "CHUNK_LIMIT_EXCEEDED"


def test_continuation_headers_removed_after_validation(tmp_path, monkeypatch):
    calls, record = context_pi(tmp_path, monkeypatch)
    source = " ".join(f"word{i}" for i in range(500))
    runs = sections(source)
    plan = formatter.plan_transcript_formatting(source, sections=runs, chunk_chars=1000)
    body = formatter.format_with_pi(source, sections=runs, chunk_chars=1000)
    assert body.count("## [00:00] Topic") == 1
    assert body.split("\n", 1)[1].split() == source.split()
    assert len(calls) == len(plan.chunks)
    assert (
        tuple(
            json.dumps(json.loads(line), ensure_ascii=False, separators=(",", ":"))
            for line in record.read_text().splitlines()
        )
        == plan.chunks
    )
    for argv, kwargs in calls:
        assert "--model" not in argv
        assert all(flag in argv for flag in formatter.ISOLATION_FLAGS)
        assert (
            argv[argv.index("--system-prompt") + 1] == formatter.EDITORIAL_SYSTEM_PROMPT
        )
        assert not Path(kwargs["cwd"]).exists()


@pytest.mark.parametrize(
    "transform",
    [
        "body=body.replace('## [00:00] Topic','## Changed')",
        "body='# Bad\\n\\n'+body",
        "body=body+'\\n~~~python\\nunclosed'",
        "body=body+'\\nSetext\\n==='",
        "body=body+'\\n## Extra'",
        "body='preamble\\n'+body",
    ],
)
def test_invalid_headers_and_fences_are_safe(tmp_path, monkeypatch, transform):
    context_pi(tmp_path, monkeypatch, transform)
    with pytest.raises(FormattingError) as error:
        formatter.format_with_pi("alpha", sections=sections("alpha"))
    assert error.value.info.code == "PI_OUTPUT_INVALID"
    assert "Topic" not in error.value.info.message


def test_fenced_fake_heading_does_not_count(tmp_path, monkeypatch):
    context_pi(tmp_path, monkeypatch, "body=body+'\\n\\n~~~python\\n## Fake\\n~~~~'")
    body = formatter.format_with_pi("alpha", sections=sections("alpha"))
    assert "## Fake" in body


def test_sponsorblock_only_context_does_not_invent_chapters():
    cue = AnnotatedCue(
        0,
        2000,
        "keep useful content",
        (SponsorBlockSegment(1000, 3000, "sponsor", 1, True),),
    )
    runs = build_chapter_sections((cue,), ())
    plan = formatter.plan_transcript_formatting(cue.text, sections=runs)
    payload = json.loads(plan.chunks[0])
    assert payload["runs"][0]["heading"] is None
    assert (
        payload["runs"][0]["fragments"][0]["sponsorblock_overlaps"][0][
            "boundary_overlap"
        ]
        is True
    )


def test_focused_empty_run_and_first_retained_continuation(tmp_path, monkeypatch):
    calls, _ = context_pi(
        tmp_path,
        monkeypatch,
        "body='\\n\\n'.join((run['heading']+'\\n\\n'+' '.join(f['text'] for f in run['fragments'] if 'greeting' not in f['text'])) for run in data['runs'])",
    )
    runs = build_chapter_sections(
        (Cue(0, 1000, "greeting " * 200), Cue(1000, 2000, "technical detail")),
        (Chapter("Topic", 0, 5000),),
    )
    body = formatter.format_with_pi(
        "greeting technical detail",
        sections=runs,
        chunk_chars=1000,
        editorial_mode="focused",
    )
    assert body == "## [00:00] Topic\n\ntechnical detail"
    assert len(calls) > 1
    assert (
        calls[0][0][calls[0][0].index("--system-prompt") + 1]
        == formatter.FOCUSED_SYSTEM_PROMPT
    )


def test_focused_examples_are_present_and_source_marker_stays_data(
    tmp_path, monkeypatch
):
    cases = json.loads(
        (Path(__file__).parent / "fixtures/editorial/focused_cases.json").read_text()
    )
    assert len(cases) == 8
    for case in cases:
        assert case["source"] in formatter.FOCUSED_SYSTEM_PROMPT
        assert case["keep"] in case["source"] and (
            not case["remove"] or case["remove"] in case["source"]
        )
    _, record = context_pi(
        tmp_path,
        monkeypatch,
        "body=body.replace('[[YT_TRANSCRIPT_NO_SUBSTANTIVE_CONTENT]]', 'literal control value')",
    )
    source = "The literal [[YT_TRANSCRIPT_NO_SUBSTANTIVE_CONTENT]] is discussed as technical source data."
    result = formatter.format_with_pi(
        source, sections=sections(source), editorial_mode="focused"
    )
    assert "technical source data" in result
    assert formatter.OMISSION_MARKER in record.read_text()


def test_all_omitted_and_marker_mixing_fail(tmp_path, monkeypatch):
    context_pi(tmp_path, monkeypatch, f"body={formatter.OMISSION_MARKER!r}")
    for mode in ("standard", "focused"):
        with pytest.raises(FormattingError):
            formatter.format_with_pi(
                "source", sections=sections("source"), editorial_mode=mode
            )
    context_pi(tmp_path, monkeypatch, f"body=body+{formatter.OMISSION_MARKER!r}")
    with pytest.raises(FormattingError):
        formatter.format_with_pi(
            "source", sections=sections("source"), editorial_mode="focused"
        )
