"""Budgeted read-only source context, ownership, and opt-in CLI safety."""

import json

import pytest

from yt_transcript import formatter, service
from yt_transcript.chapters import Chapter, build_chapter_sections
from yt_transcript.cleaner import Cue
from yt_transcript.cli import main
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.errors import FormattingError
from yt_transcript.metadata import VideoMetadata

URL = "https://youtu.be/abcdefghijk"


def test_zero_context_preserves_existing_payloads():
    source = "One source sentence. Another source sentence. " * 30
    assert formatter.plan_formatting(
        source, chunk_chars=100
    ) == formatter.plan_formatting(source, chunk_chars=100, boundary_context_chars=0)
    sections = build_chapter_sections(
        (Cue(0, 1000, source),), (Chapter("Topic", 0, 2000),)
    )
    original = formatter.plan_context_formatting(sections, chunk_chars=500)
    assert original == formatter.plan_context_formatting(
        sections, chunk_chars=500, boundary_context_chars=0
    )
    assert set(json.loads(original.chunks[0])) == {"runs"}
    assert "source_id" not in original.chunks[0]


def test_current_words_are_owned_once_and_all_escaping_is_budgeted():
    source = " ".join(f'word_{i}_\\"λ\x00' for i in range(100))
    plan = formatter.plan_formatting(
        source, chunk_chars=1200, boundary_context_chars=15
    )
    current = []
    for index, chunk in enumerate(plan.chunks):
        envelope = json.loads(chunk)
        assert set(envelope) == {"previous_context", "current", "following_context"}
        current.extend(envelope["current"].split())
        assert len(chunk) <= 1200
        assert len(envelope["previous_context"]) <= 15
        assert len(envelope["following_context"]) <= 15
        if index == 0:
            assert not envelope["previous_context"]
    assert current == source.split()
    assert plan.character_counts == tuple(map(len, plan.chunks))
    capped = formatter.plan_formatting(
        source, chunk_chars=1200, boundary_context_chars=15, max_chunks=1
    )
    assert not capped.within_cap


def test_windows_omit_oversize_neighbor_tokens_without_truncation():
    assert formatter._word_window("oversized_identifier_token", 5) == ""
    assert formatter._word_window("oversized_identifier_token", 5, trailing=True) == ""
    assert formatter._word_window("first middle last", 11) == "first"
    assert (
        formatter._word_window("first middle last", 11, trailing=True) == "middle last"
    )


@pytest.mark.parametrize("provider", ["pi", "openrouter"])
@pytest.mark.parametrize("mode", ["standard", "focused"])
def test_context_transport_emits_only_current_and_preserves_chapters(
    provider, mode, monkeypatch
):
    from yt_transcript import openrouter_backend

    source = " ".join(f"retained_word_{i}" for i in range(160))
    sections = build_chapter_sections(
        (Cue(0, 1000, source), Cue(3000, 4000, "last substantive details")),
        (Chapter("TITLE_ONLY_BAIT", 0, 5000),),
        source_indices=(0, 2),
    )
    requests = []
    monkeypatch.setattr(
        formatter, "ensure_formatter", lambda p, m: "fake" if p == "pi" else None
    )

    def echo(request):
        requests.append(request)
        envelope = json.loads(request.source)
        assert "read-only" in request.append_system_prompt
        assert (
            "TITLE_ONLY_BAIT"
            not in envelope["previous_context"] + envelope["following_context"]
        )
        assert "REMOVED_CAPTION" not in request.source
        assert "exact numeric values" in request.system_prompt
        current = envelope["current"]
        return "\n\n".join(
            run["heading"] + "\n\n" + " ".join(f["text"] for f in run["fragments"])
            for run in current["runs"]
        )

    monkeypatch.setattr(
        formatter, "_run_pi_chunk", lambda executable, request: echo(request)
    )
    monkeypatch.setattr(
        openrouter_backend, "complete", lambda request, settings=None: echo(request)
    )
    plan = formatter.plan_transcript_formatting(
        source,
        sections=sections,
        chunk_chars=1500,
        boundary_context_chars=20,
        editorial_mode=mode,
        provider=provider,
    )
    result = formatter.format_transcript(
        source + " REMOVED_CAPTION",
        sections=sections,
        chunk_chars=1500,
        boundary_context_chars=20,
        editorial_mode=mode,
        provider=provider,
        model="fake/model",
    )
    assert result.count(sections[0].heading) == 1
    assert (
        result.split("\n", 1)[1].split()
        == (source + " last substantive details").split()
    )
    assert [r.source for r in requests] == list(plan.chunks)
    assert len(requests) == plan.call_count
    assert len(requests) > 1


@pytest.mark.parametrize("value", [-1, 1001, True, 1.5, "10", None])
def test_invalid_python_context_values(value):
    with pytest.raises(ValueError):
        formatter.plan_transcript_formatting("source", boundary_context_chars=value)


def test_infeasible_context_fails_before_backend_and_cap_is_replanned(monkeypatch):
    monkeypatch.setattr(
        formatter, "ensure_formatter", lambda *a: pytest.fail("must not launch")
    )
    with pytest.raises(FormattingError) as error:
        formatter.format_transcript(
            "token",
            boundary_context_chars=1000,
            chunk_chars=1000,
            provider="openrouter",
        )
    assert error.value.info.code == "OPENROUTER_CONTEXT_LIMIT"
    with pytest.raises(ValueError):
        formatter.format_with_pi(
            "source", editorial_mode="summarized", boundary_context_chars=1
        )
    source = "word " * 100
    normal = formatter.plan_formatting(source, chunk_chars=1000)
    contextual = formatter.plan_formatting(
        source, chunk_chars=1000, boundary_context_chars=20
    )
    assert normal.call_count < contextual.call_count
    with pytest.raises(FormattingError) as error:
        formatter.format_with_pi(
            source,
            chunk_chars=1000,
            boundary_context_chars=20,
            max_chunks=normal.call_count,
        )
    assert error.value.info.code == "CHUNK_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    "flags",
    [
        ["--raw"],
        ["--raw-vtt"],
        ["--editorial-mode", "summarized"],
        ["--doctor"],
        ["--mcp"],
    ],
)
@pytest.mark.parametrize("context", ["0", "20"])
def test_cli_context_restrictions_before_extraction(
    flags, context, monkeypatch, capsys
):
    monkeypatch.setattr(
        service, "fetch_clean_transcript", lambda *a, **k: pytest.fail("must not fetch")
    )
    prefix = [] if flags in (["--doctor"], ["--mcp"]) else [URL]
    assert (
        main([*prefix, "--no-config", *flags, "--boundary-context-chars", context]) == 2
    )
    result = capsys.readouterr()
    assert "CONFIG_INVALID" in result.err and not result.out


@pytest.mark.parametrize("value", ["-1", "1001", "PRIVATE_SECRET", "1.5"])
def test_cli_context_value_errors_are_sanitized(value, capsys):
    assert main([URL, "--no-config", "--boundary-context-chars", value]) == 2
    result = capsys.readouterr()
    assert "PRIVATE_SECRET" not in result.err
    assert not result.out


def download(monkeypatch):
    source = "retained source sentence. " * 70
    vtt = b"WEBVTT\n\n00:00.000 --> 00:01.000\n" + source.encode() + b"\n"
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk",
        description="DESCRIPTION_SECRET",
    )
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda *a, **k: DownloadedCaptions(vtt, "en", False, metadata),
    )
    return source


def test_cli_preview_never_calls_provider_and_exposes_context_budget(
    monkeypatch, capsys
):
    download(monkeypatch)
    monkeypatch.setattr(
        formatter, "ensure_formatter", lambda *a: pytest.fail("no provider")
    )
    assert (
        main([URL, "--no-config", "--preview", "--boundary-context-chars", "20"]) == 0
    )
    result = capsys.readouterr()
    assert "boundary context characters per side: 20" in result.out
    assert "DESCRIPTION_SECRET" not in result.out
    assert not result.err


def test_cli_context_failure_preserves_old_file(monkeypatch, capsys, tmp_path):
    download(monkeypatch)
    monkeypatch.setattr(formatter, "ensure_pi", lambda: "fake")

    def fail(*a, **k):
        raise formatter.classify_pi_failure(code="PI_OUTPUT_INVALID")

    monkeypatch.setattr(formatter, "_run_chunk", fail)
    output = tmp_path / "old.md"
    output.write_text("old document")
    assert (
        main([URL, "--no-config", "--boundary-context-chars", "20", "-o", str(output)])
        == 1
    )
    assert output.read_text() == "old document"
    assert not capsys.readouterr().out


def test_shared_rules_reinforce_no_correction_without_losing_focused_examples():
    for mode in ("standard", "focused", "summarized"):
        prompt = formatter.get_editorial_prompt(mode)
        assert "Do not repair caption errors" in prompt
        assert "unsupported causal/logical transitions" in prompt
        assert "exact numeric values" in prompt
    focused = formatter.get_editorial_prompt("focused")
    assert "Synthetic examples" in focused and formatter.OMISSION_MARKER in focused
