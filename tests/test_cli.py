from importlib.metadata import version

import pytest

from yt_transcript import downloader, formatter, service
from yt_transcript.cli import main
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.metadata import VideoMetadata

URL = "https://youtu.be/abcdefghijk"
VTT = b"WEBVTT\r\n\r\n00:00.000 --> 00:01.000\r\nhello world\r\n"


@pytest.fixture
def pipeline(monkeypatch):
    calls = []
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk", title="Title"
    )

    def download(url, **kwargs):
        calls.append("download")
        return DownloadedCaptions(VTT, "en", False, metadata)

    monkeypatch.setattr(downloader, "download_english_vtt", download)
    monkeypatch.setattr(service, "download_english_vtt", download)
    monkeypatch.setattr(formatter, "ensure_pi", lambda: calls.append("ensure") or "pi")

    def format(body, **kwargs):
        calls.append(("format", kwargs))
        return "## Edited\n\nhello world"

    monkeypatch.setattr(formatter, "format_with_pi", format)
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
    assert "planned formatter invocations: 1" in capsys.readouterr().out


def test_no_clobber_early(pipeline, tmp_path):
    path = tmp_path / "existing"
    path.write_text("old")
    assert main([URL, "--no-config", "-o", str(path), "--no-clobber"]) == 1
    assert pipeline == [] and path.read_text() == "old"


def test_config_raw(pipeline, tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('[output]\nmode="raw"\n[pi]\nmodel="saved"\nmax_chunks=1')
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
    path.write_text('[pi]\neditorial_mode="focused"')
    assert main([URL, "--config", str(path)]) == 0
    assert pipeline[-1][1]["editorial_mode"] == "focused"
    pipeline.clear()
    assert main([URL, "--config", str(path), "--editorial-mode", "standard"]) == 0
    assert pipeline[-1][1]["editorial_mode"] == "standard"
    pipeline.clear()
    capsys.readouterr()
    assert main([URL, "--config", str(path), "--raw"]) == 0
    assert pipeline == ["download"] and capsys.readouterr().out == "hello world\n"


def test_raw_vtt_ignores_saved_sponsorblock_and_focused(pipeline, tmp_path, capsys):
    path = tmp_path / "saved.toml"
    path.write_text('[sponsorblock]\nenabled=true\n[pi]\neditorial_mode="focused"')
    assert main([URL, "--config", str(path), "--raw-vtt"]) == 0
    assert pipeline == ["download"] and capsys.readouterr().out == VTT.decode()


def test_focused_preview_does_not_call_pi(pipeline, capsys):
    assert main([URL, "--no-config", "--editorial-mode", "focused", "--preview"]) == 0
    assert pipeline == ["download"]
    assert "editorial mode: focused" in capsys.readouterr().out


def test_failed_format_preserves_file(pipeline, monkeypatch, tmp_path, capsys):
    from yt_transcript.errors import classify_pi_failure

    def fail(*args, **kwargs):
        raise classify_pi_failure(code="PI_OUTPUT_INCOMPLETE")

    monkeypatch.setattr(formatter, "format_with_pi", fail)
    path = tmp_path / "existing"
    path.write_text("old")
    assert main([URL, "--no-config", "-o", str(path)]) == 1
    assert path.read_text() == "old"
    captured = capsys.readouterr()
    assert not captured.out and "PI_OUTPUT_INCOMPLETE" in captured.err


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

    monkeypatch.setattr(formatter, "format_with_pi", edit)
    assert main([URL, "--no-config"]) == 0
    assert capsys.readouterr().out == "## Edited\n\nhello world\n"
    assert "Pi chunks 1/2" in stream.getvalue()
    assert "Pi chunks 2/2" in stream.getvalue()
    assert "hello world" not in stream.getvalue()
