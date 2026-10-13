"""Synthetic captions and mocked completions; no network or model calls."""

import pytest

from yt_transcript import formatter, service
from yt_transcript import openrouter_backend as backend
from yt_transcript.cli import main
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.errors import classify_openrouter_failure
from yt_transcript.metadata import VideoMetadata

URL = "https://youtu.be/abcdefghijk"
SUMMARY = (
    "## Summary\n\nRetries can duplicate writes.\n\n## Key points\n\n- Use idempotency."
)


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "KEY_NOT_FOR_OUTPUT")
    monkeypatch.setattr(
        formatter, "ensure_pi", lambda: pytest.fail("Pi must not be checked")
    )
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk",
        description="DESCRIPTION_NOT_MODEL_INPUT",
    )
    monkeypatch.setattr(
        service,
        "download_caption_vtt",
        lambda url, **kwargs: DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nRetries can duplicate writes.\n",
            "en",
            False,
            metadata,
        ),
    )
    return metadata


@pytest.mark.parametrize("mode", ["standard", "focused", "summarized"])
def test_all_modes_without_pi(source, monkeypatch, capsys, mode):
    calls = []

    def complete(req, config):
        calls.append(req)
        assert "DESCRIPTION_NOT_MODEL_INPUT" not in repr(req)
        return (
            SUMMARY
            if mode == "summarized"
            else "## Edited\n\nRetries can duplicate writes."
        )

    monkeypatch.setattr(backend, "complete", complete)
    assert (
        main(
            [
                URL,
                "--no-config",
                "--provider",
                "openrouter",
                "--model",
                "provider/model",
                "--editorial-mode",
                mode,
            ]
        )
        == 0
    )
    out = capsys.readouterr()
    assert not out.err and "Retries" in out.out
    assert len(calls) == 1 and "KEY_NOT_FOR_OUTPUT" not in out.out


def test_preview_does_not_require_key(source, monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setattr(backend, "complete", lambda *a: pytest.fail("no completion"))
    assert (
        main(
            [
                URL,
                "--no-config",
                "--provider",
                "openrouter",
                "--model",
                "provider/model",
                "--preview",
            ]
        )
        == 0
    )
    out = capsys.readouterr()
    assert (
        "provider: openrouter" in out.out
        and "planned formatter invocations: 1" in out.out
    )
    assert "Pi configured default" not in out.out and not out.err


@pytest.mark.parametrize("flags", [[], ["--preview"]])
def test_missing_model_is_safe_before_extraction(source, monkeypatch, capsys, flags):
    monkeypatch.setattr(
        service, "download_caption_vtt", lambda *a: pytest.fail("must fail early")
    )
    assert main([URL, "--no-config", "--provider", "openrouter", *flags]) == 1
    out = capsys.readouterr()
    assert not out.out and "OPENROUTER_NOT_CONFIGURED" in out.err


def test_saved_openrouter_raw_needs_no_credentials(
    source, monkeypatch, tmp_path, capsys
):
    config = tmp_path / "config.toml"
    config.write_text('[formatting]\nprovider="openrouter"')
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setattr(backend, "complete", lambda *a: pytest.fail("no completion"))
    assert main([URL, "--config", str(config), "--raw"]) == 0
    assert capsys.readouterr().out == "Retries can duplicate writes.\n"


@pytest.mark.parametrize("flags", [["--raw"], ["--mcp"], ["--raw-vtt"]])
def test_explicit_provider_flag_conflicts(capsys, flags):
    assert main(["--provider", "openrouter", *flags]) == 2
    assert "CONFIG_INVALID" in capsys.readouterr().err


def test_failure_preserves_file_and_safe_diagnostics(
    source, monkeypatch, tmp_path, capsys
):
    output = tmp_path / "existing.md"
    output.write_text("original")
    monkeypatch.setattr(
        backend,
        "complete",
        lambda *a: (_ for _ in ()).throw(
            classify_openrouter_failure("OPENROUTER_OUTPUT_INCOMPLETE")
        ),
    )
    assert (
        main(
            [
                URL,
                "--no-config",
                "--provider",
                "openrouter",
                "--model",
                "provider/model",
                "-v",
                "-o",
                str(output),
            ]
        )
        == 1
    )
    out = capsys.readouterr()
    assert not out.out and "OPENROUTER_OUTPUT_INCOMPLETE" in out.err
    assert (
        "KEY_NOT_FOR_OUTPUT" not in out.err
        and "DESCRIPTION_NOT_MODEL_INPUT" not in out.err
    )
    assert output.read_text() == "original"


def test_doctor_configuration_is_offline(monkeypatch, capsys):
    from yt_transcript import doctor

    seen = []
    monkeypatch.setattr(
        doctor, "run_doctor", lambda **kw: seen.append(kw) or doctor.DoctorReport(())
    )
    assert (
        main(
            [
                "--doctor",
                "--no-config",
                "--provider",
                "openrouter",
                "--model",
                "provider/model",
            ]
        )
        == 0
    )
    assert seen[0] == {
        "include_pi": False,
        "provider": "openrouter",
        "model": "provider/model",
    }
    assert "not verified" in capsys.readouterr().out
