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
    assert capsys.readouterr().out == "0.1.0\n"


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
