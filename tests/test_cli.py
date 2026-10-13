import json
from importlib.metadata import version

import pytest
import yaml

from yt_transcript import downloader, formatter, service
from yt_transcript.cli import main
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.metadata import VideoMetadata

URL = "https://youtu.be/abcdefghijk"
DESCRIPTION = '  CLI_DESCRIPTION_SENTINEL\nquote" \\ path\nhttps://example.test/\n'
VTT = b"WEBVTT\r\n\r\n00:00.000 --> 00:01.000\r\nhello world\r\n"


@pytest.fixture
def pipeline(monkeypatch):
    calls = []
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk",
        title="Title",
        description=DESCRIPTION,
    )

    def download(url, **kwargs):
        calls.append("download")
        return DownloadedCaptions(VTT, "en", False, metadata)

    monkeypatch.setattr(downloader, "download_caption_vtt", download)
    monkeypatch.setattr(service, "download_caption_vtt", download)
    monkeypatch.setattr(formatter, "ensure_pi", lambda: calls.append("ensure") or "pi")

    def format(body, **kwargs):
        assert body == "hello world"
        assert "CLI_DESCRIPTION_SENTINEL" not in body + repr(kwargs)
        calls.append(("format", kwargs))
        return "## Edited\n\nhello world"

    monkeypatch.setattr(formatter, "format_transcript", format)
    return calls


def test_help(capsys):
    assert main(["--help"]) == 0
    assert "YouTube" in capsys.readouterr().out


def test_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out == version("yt-transcript") + "\n"


@pytest.mark.parametrize(
    "mode,expected",
    [
        ([], "## Edited\n\nhello world\n"),
        (["--raw"], "hello world\n"),
        (["--raw-vtt"], VTT.decode()),
    ],
)
def test_modes(pipeline, capsys, mode, expected):
    assert main([URL, "--no-config", *mode]) == 0
    captured = capsys.readouterr()
    assert captured.out == expected and captured.err == ""
    if mode:
        assert pipeline == ["download"]
    else:
        assert pipeline[-1][1]["model"] is None


@pytest.mark.parametrize("mode", [[], ["--raw"], ["--raw-vtt"]])
def test_files(pipeline, capsys, tmp_path, mode):
    path = tmp_path / "output"
    assert main([URL, "--no-config", *mode, "-o", str(path)]) == 0
    assert capsys.readouterr().out == ""
    if mode == ["--raw-vtt"]:
        assert path.read_bytes() == VTT
    else:
        assert path.read_text().startswith("---\n")
        assert "caption_language" in path.read_text()
        _, header, body = path.read_text().split("---\n", 2)
        assert yaml.safe_load(header)["description"] == DESCRIPTION
        assert "CLI_DESCRIPTION_SENTINEL" not in body


@pytest.mark.parametrize(
    "flags",
    [
        ["--raw", "--model", "x"],
        ["--raw", "--max-chunks", "1"],
        ["--preview", "--raw"],
        ["--no-clobber"],
        ["--doctor", "--no-config"],
        ["--mcp", "--raw"],
    ],
)
def test_conflicts(pipeline, capsys, flags):
    assert main([URL, "--no-config", *flags]) == 2
    assert pipeline == []
    assert capsys.readouterr().out == ""


def test_preview(pipeline, capsys):
    assert main([URL, "--no-config", "--preview"]) == 0
    assert pipeline == ["download"]
    output = capsys.readouterr().out
    assert "planned formatter invocations: 1" in output
    assert "CLI_DESCRIPTION_SENTINEL" not in output


def test_no_clobber_early(pipeline, tmp_path):
    path = tmp_path / "existing"
    path.write_text("old")
    assert main([URL, "--no-config", "-o", str(path), "--no-clobber"]) == 1
    assert pipeline == [] and path.read_text() == "old"


def test_config_raw(pipeline, tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('[output]\nmode="raw"\n[formatting]\nmodel="saved"\nmax_chunks=1')
    assert main([URL, "--config", str(path)]) == 0
    assert pipeline == ["download"]
    assert capsys.readouterr().out == "hello world\n"


@pytest.mark.parametrize(
    "flags",
    [
        ["--raw", "--editorial-mode", "focused"],
        ["--raw-vtt", "--sponsorblock"],
        ["--mcp", "--sponsorblock"],
        ["--doctor", "--editorial-mode", "standard"],
    ],
)
def test_new_flag_conflicts_are_early(pipeline, capsys, flags):
    assert main([URL, "--no-config", *flags]) == 2
    assert pipeline == [] and capsys.readouterr().out == ""


def test_focused_config_precedence_and_raw_ignore(pipeline, tmp_path, capsys):
    path = tmp_path / "focused.toml"
    path.write_text('[formatting]\neditorial_mode="focused"')
    assert main([URL, "--config", str(path)]) == 0
    assert pipeline[-1][1]["editorial_mode"] == "focused"
    pipeline.clear()
    assert main([URL, "--config", str(path), "--editorial-mode", "standard"]) == 0
    assert pipeline[-1][1]["editorial_mode"] == "standard"
    pipeline.clear()
    capsys.readouterr()
    # --no-cache keeps this test on config precedence; cache reuse is covered separately.
    assert main([URL, "--config", str(path), "--raw", "--no-cache"]) == 0
    assert pipeline == ["download"] and capsys.readouterr().out == "hello world\n"


def test_raw_vtt_ignores_saved_sponsorblock_and_focused(pipeline, tmp_path, capsys):
    path = tmp_path / "saved.toml"
    path.write_text(
        '[sponsorblock]\nenabled=true\n[formatting]\neditorial_mode="focused"'
    )
    assert main([URL, "--config", str(path), "--raw-vtt"]) == 0
    assert pipeline == ["download"] and capsys.readouterr().out == VTT.decode()


def test_focused_preview_does_not_call_pi(pipeline, capsys):
    assert main([URL, "--no-config", "--editorial-mode", "focused", "--preview"]) == 0
    assert pipeline == ["download"]
    assert "editorial mode: focused" in capsys.readouterr().out


@pytest.mark.parametrize(
    "code",
    [
        "PI_OUTPUT_INCOMPLETE",
        "PI_CONTEXT_MUTATED",
        "PI_CONTEXT_LIMIT",
        "PI_TIMEOUT",
        "PI_OUTPUT_INVALID",
    ],
)
def test_failed_format_preserves_file(pipeline, monkeypatch, tmp_path, capsys, code):
    from yt_transcript.errors import classify_pi_failure

    def fail(*args, **kwargs):
        raise classify_pi_failure(code=code, chunk_index=2, chunk_total=3)

    monkeypatch.setattr(formatter, "format_transcript", fail)
    path = tmp_path / "existing"
    path.write_text("old")
    assert main([URL, "--no-config", "-o", str(path)]) == 1
    assert path.read_text() == "old"
    captured = capsys.readouterr()
    assert not captured.out and code in captured.err
    assert "(chunk 2/3)" in captured.err
    assert "warning: No model-processed transcript was returned." in captured.err
    assert "Retry with --raw" in captured.err
    pipeline.clear()
    # A cached snapshot would skip the fetch; uncached recovery is the behavior under test.
    assert main([URL, "--no-config", "--raw", "--no-cache"]) == 0
    assert pipeline == ["download"]
    recovery = capsys.readouterr()
    assert recovery.out == "hello world\n" and recovery.err == ""


def test_terminal_progress_stays_off_stdout(pipeline, monkeypatch, capsys):
    import io

    from yt_transcript import cli

    stream = io.StringIO()
    monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(cli.sys, "stderr", stream)

    def edit(body, **kwargs):
        callback = kwargs["on_progress"]
        callback(0, 2)
        callback(1, 2)
        callback(2, 2)
        return "## Edited\n\nhello world"

    monkeypatch.setattr(formatter, "format_transcript", edit)
    assert main([URL, "--no-config"]) == 0
    assert capsys.readouterr().out == "## Edited\n\nhello world\n"
    assert "Model calls via pi 1/2" in stream.getvalue()
    assert "Model calls via pi 2/2" in stream.getvalue()
    assert "hello world" not in stream.getvalue()


@pytest.mark.parametrize("failure", [RuntimeError, OSError])
def test_progress_thread_failure_keeps_transcription_working(
    pipeline, monkeypatch, capsys, failure
):
    import io
    import threading

    from yt_transcript import cli

    stream = io.StringIO()
    monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(cli.sys, "stderr", stream)

    def fail(self):
        raise failure("cannot start progress thread")

    monkeypatch.setattr(threading.Thread, "start", fail)
    assert main([URL, "--no-config", "--raw"]) == 0
    assert capsys.readouterr().out == "hello world\n"
    assert not stream.getvalue()
    assert pipeline == ["download"]


def test_language_flag_and_verbose_provenance(monkeypatch, capsys):
    seen = []
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"
    )

    def download(url, **kwargs):
        seen.append(kwargs.get("language"))
        return DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nbonjour\n", "fr", False, metadata, True
        )

    monkeypatch.setattr(downloader, "download_caption_vtt", download)
    monkeypatch.setattr(service, "download_caption_vtt", download)
    assert main([URL, "--no-config", "--raw", "--language", "fr", "-v"]) == 0
    captured = capsys.readouterr()
    assert seen == ["fr"]
    assert captured.out == "bonjour\n"
    assert "caption: fr; source=manual; translated" in captured.err


def test_invalid_language_is_rejected_before_extraction(monkeypatch, capsys):
    monkeypatch.setattr(
        service, "download_caption_vtt", lambda *a, **k: pytest.fail("must not fetch")
    )
    assert main([URL, "--no-config", "--raw", "--language", "fr EN"]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "CONFIG_INVALID" in captured.err


def _cache_metadata():
    return VideoMetadata("https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk")


def _cache_download(calls):
    def download(url, **kwargs):
        calls.append(url)
        return DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nhello world\n",
            "en",
            False,
            _cache_metadata(),
        )

    return download


def test_cli_cache_is_cold_then_warm(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(service, "download_caption_vtt", _cache_download(calls))
    assert main([URL, "--no-config", "--raw"]) == 0
    assert capsys.readouterr().out == "hello world\n"
    assert main([URL, "--no-config", "--raw", "-v"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "hello world\n"
    assert len(calls) == 1
    assert "cache: reused local source snapshot" in captured.err


def test_cli_no_cache_forces_refetch(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(service, "download_caption_vtt", _cache_download(calls))
    assert main([URL, "--no-config", "--raw"]) == 0
    capsys.readouterr()
    assert main([URL, "--no-config", "--raw", "--no-cache"]) == 0
    capsys.readouterr()
    assert main([URL, "--no-config", "--raw", "--no-cache"]) == 0
    capsys.readouterr()
    assert len(calls) == 3


def test_cli_configured_cache_policy_and_force_flag(monkeypatch, capsys, tmp_path):
    calls = []
    monkeypatch.setattr(service, "download_caption_vtt", _cache_download(calls))
    path = tmp_path / "config.toml"
    path.write_text("[cache]\nenabled = false\n", encoding="utf-8")
    # Disabled: two runs, two fetches, nothing reused or stored.
    assert main([URL, "--config", str(path), "--raw"]) == 0
    capsys.readouterr()
    assert main([URL, "--config", str(path), "--raw"]) == 0
    capsys.readouterr()
    assert len(calls) == 2
    # --cache overrides the configured disable, then the next run reuses it.
    assert main([URL, "--config", str(path), "--raw", "--cache"]) == 0
    capsys.readouterr()
    assert len(calls) == 3
    assert main([URL, "--config", str(path), "--raw", "--cache", "-v"]) == 0
    captured = capsys.readouterr()
    assert len(calls) == 3
    assert "cache: reused local source snapshot" in captured.err


def test_cli_raw_vtt_stays_uncached(monkeypatch, capsys):
    import os
    from pathlib import Path

    calls = []
    monkeypatch.setattr(downloader, "download_caption_vtt", _cache_download(calls))
    assert main([URL, "--no-config", "--raw-vtt"]) == 0
    capsys.readouterr()
    assert main([URL, "--no-config", "--raw-vtt"]) == 0
    capsys.readouterr()
    assert len(calls) == 2
    root = Path(os.environ["XDG_CACHE_HOME"]) / "yt-transcript"
    assert not (root / "transcripts.db").exists()


def test_cli_populates_the_shared_cache_for_mcp(monkeypatch, capsys):
    from yt_transcript.sponsorblock import SponsorBlockConfig
    from yt_transcript.transcript_cache import TranscriptCache

    calls = []
    monkeypatch.setattr(service, "download_caption_vtt", _cache_download(calls))
    assert main([URL, "--no-config", "--raw"]) == 0
    capsys.readouterr()
    assert len(calls) == 1
    snapshot = service.get_cached_snapshot(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "full",
        sponsorblock=SponsorBlockConfig(),
        cache=TranscriptCache(),
    )
    assert snapshot.cache_hit is True
    assert len(calls) == 1


def test_json_doctor_is_one_document(monkeypatch, capsys):
    from yt_transcript import doctor

    report = doctor.DoctorReport((doctor.DoctorCheck("Python", "ok", "3.14.7"),))
    monkeypatch.setattr(doctor, "run_doctor", lambda **kwargs: report)
    assert main(["--doctor", "--json", "--no-config"]) == 0
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["command"] == "doctor"
    assert document["healthy"] is True
    assert captured.out.count("\n") == 1
    assert captured.err == ""


def test_json_preview_is_one_document_without_transcript_text(pipeline, capsys):
    assert main([URL, "--no-config", "--preview", "--json"]) == 0
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["command"] == "preview"
    assert document["plan"]["invocations"] == 1
    assert document["plan"]["within_cap"] is True
    assert document["caption"]["language"] == "en"
    assert document["caption"]["translated"] is None
    assert document["cache"]["enabled"] is True
    assert "CLI_DESCRIPTION_SENTINEL" not in captured.out
    assert "hello world" not in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("editorial_mode", ["standard", "summarized"])
def test_json_preview_matches_text_summary_note_limit(pipeline, capsys, editorial_mode):
    text_args = [
        URL,
        "--no-config",
        "--preview",
        "--editorial-mode",
        editorial_mode,
    ]
    assert main(text_args) == 0
    text_report = capsys.readouterr().out
    assert main([*text_args, "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    text_limit = next(
        line.split(": ", 1)[1]
        for line in text_report.splitlines()
        if line.startswith("summary notes hard output limit:")
    )
    note_limit = document["plan"]["summary_note_limit"]
    assert text_limit == (
        str(note_limit) if note_limit is not None else "not applicable"
    )
    assert document["plan"]["within_cap"] is True


def test_json_raw_transcript_carries_cues_and_nulls_stdout_description(
    pipeline, capsys
):
    assert main([URL, "--no-config", "--raw", "--json"]) == 0
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["command"] == "transcript"
    assert document["mode"] == "raw"
    assert document["body"] == "hello world"
    assert document["character_count"] == len("hello world")
    assert document["description"] is None
    assert document["cues"] == [
        {"start_seconds": 0.0, "end_seconds": 1.0, "text": "hello world"}
    ]
    assert document["caption_language"] == "en"
    assert document["caption_source"] == "manual"
    assert document["caption_translated"] is None
    assert captured.err == ""


def test_json_markdown_document_has_body_without_cues(pipeline, capsys):
    assert main([URL, "--no-config", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["mode"] == "markdown"
    assert document["body"] == "## Edited\n\nhello world"
    assert "cues" not in document


def test_json_file_output_includes_description_and_no_yaml(pipeline, tmp_path, capsys):
    path = tmp_path / "out.json"
    assert main([URL, "--no-config", "--raw", "--json", "-o", str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("{")
    assert not text.startswith("---")
    assert json.loads(text)["description"] == DESCRIPTION


def test_json_config_error_is_one_document(monkeypatch, capsys):
    monkeypatch.setattr(
        service, "download_caption_vtt", lambda *a, **k: pytest.fail("must not fetch")
    )
    assert main([URL, "--no-config", "--raw", "--json", "--language", "fr EN"]) == 2
    captured = capsys.readouterr()
    document = json.loads(captured.err)
    assert document["command"] == "error"
    assert document["error"]["code"] == "CONFIG_INVALID"
    assert captured.out == ""
    assert captured.err.count("\n") == 1


def test_json_argument_error_is_one_document(capsys):
    assert main(["--json", "--not-a-real-flag"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]["code"] == "CONFIG_INVALID"
    assert captured.out == ""


def test_json_rejects_raw_vtt_and_mcp(pipeline, capsys):
    assert main([URL, "--no-config", "--raw-vtt", "--json"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]["code"] == "CONFIG_INVALID"
    assert captured.out == ""
    assert main(["--mcp", "--json"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]["code"] == "CONFIG_INVALID"
    assert captured.out == ""


def test_json_keeps_sponsorblock_warning_inside_the_document(monkeypatch, capsys):
    from yt_transcript.sponsorblock import SponsorBlockLookup

    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"
    )

    def download(url, **kwargs):
        return DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nhello world\n",
            "en",
            False,
            metadata,
        )

    failed = SponsorBlockLookup(True, "lookup_failed", reason_code="LOOKUP_FAILED")
    monkeypatch.setattr(service, "download_caption_vtt", download)
    monkeypatch.setattr(service, "lookup_sponsorblock", lambda *a, **k: failed)
    assert main([URL, "--no-config", "--raw", "--json", "--sponsorblock"]) == 0
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["sponsorblock"]["status"] == "lookup_failed"
    assert document["sponsorblock"]["warning"]
    assert captured.err == ""
