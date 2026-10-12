"""DeepSeek CLI and shared policy checks with synthetic captions only."""

import pytest

from yt_transcript import cli, doctor, formatter, service
from yt_transcript import deepseek_backend as backend
from yt_transcript.config import SponsorBlockConfig
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.errors import classify_deepseek_failure
from yt_transcript.mcp_policy import MCPFormattingPolicy
from yt_transcript.metadata import VideoMetadata

URL = "https://youtu.be/abcdefghijk"
SUMMARY = (
    "## Summary\n\nRetries can duplicate writes.\n\n## Key points\n\n- Use idempotency."
)


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "KEY_NOT_FOR_OUTPUT")
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
        "download_english_vtt",
        lambda url: DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nRetries can duplicate writes.\n",
            "en",
            False,
            metadata,
        ),
    )
    return metadata


@pytest.mark.parametrize("mode", ["standard", "focused", "summarized"])
def test_all_modes_and_default_thinking(source, monkeypatch, capsys, mode):
    calls = []

    def complete(req, config):
        calls.append((req, config))
        assert "DESCRIPTION_NOT_MODEL_INPUT" not in repr(req)
        return (
            SUMMARY
            if mode == "summarized"
            else "## Edited\n\nRetries can duplicate writes."
        )

    monkeypatch.setattr(backend, "complete", complete)
    assert (
        cli.main(
            [
                URL,
                "--no-config",
                "--provider",
                "deepseek",
                "--model",
                "deepseek-flash",
                "--editorial-mode",
                mode,
            ]
        )
        == 0
    )
    out = capsys.readouterr()
    assert not out.err and "Retries" in out.out
    assert len(calls) == 1
    req, config = calls[0]
    assert req.thinking is (mode == "summarized")
    assert req.thinking_level == ("medium" if mode == "summarized" else None)
    assert config.max_output_tokens == 16384
    assert "KEY_NOT_FOR_OUTPUT" not in out.out


@pytest.mark.parametrize(
    "thinking,level", [(False, "high"), (True, "low"), (True, "high")]
)
def test_cli_and_mcp_service_request_same_policy(
    source, monkeypatch, tmp_path, capsys, thinking, level
):
    requests = []
    monkeypatch.setattr(
        backend,
        "complete",
        lambda req, config: requests.append((req, config)) or SUMMARY,
    )
    config = tmp_path / "config.toml"
    config.write_text(
        '[formatting]\nprovider="deepseek"\nmodel="deepseek-flash"\n'
        'editorial_mode="summarized"\n'
        f'thinking={str(thinking).lower()}\nthinking_level="{level}"\n'
        "[deepseek]\nmax_output_tokens=20000\n"
    )
    assert cli.main([URL, "--config", str(config)]) == 0
    capsys.readouterr()
    result = service.fetch_transcript_document(
        URL,
        output_format="markdown",
        sponsorblock=SponsorBlockConfig(enabled=False),
        formatting=MCPFormattingPolicy(
            provider="deepseek",
            model="deepseek-flash",
            editorial_mode="summarized",
            thinking=thinking,
            thinking_level=level,
            deepseek_max_output_tokens=20000,
        ),
    )
    assert result["document"] == SUMMARY
    assert len(requests) == 2
    for req, settings in requests:
        assert req.thinking is thinking
        assert req.thinking_level == (level if thinking else None)
        assert settings.max_output_tokens == 20000


@pytest.mark.parametrize(
    "thinking,level,label", [(None, None, "on"), (False, "high", "off")]
)
def test_summary_preview_reports_policy_without_key(
    source, monkeypatch, tmp_path, capsys, thinking, level, label
):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.setattr(backend, "complete", lambda *a: pytest.fail("no completion"))
    config = tmp_path / "config.toml"
    text = '[formatting]\nprovider="deepseek"\nmodel="deepseek-flash"\neditorial_mode="summarized"\n'
    if thinking is not None:
        text += f'thinking={str(thinking).lower()}\nthinking_level="{level}"\n'
    config.write_text(text)
    assert cli.main([URL, "--config", str(config), "--preview"]) == 0
    out = capsys.readouterr()
    assert not out.err
    assert "provider: deepseek" in out.out
    assert f"requested thinking: {label}" in out.out
    if label == "on":
        assert "requested thinking level: medium" in out.out
        assert "DeepSeek effort mapping: medium -> high" in out.out
    else:
        assert "requested thinking level: not selected" in out.out
        assert "DeepSeek effort mapping" not in out.out


@pytest.mark.parametrize("flags", [[], ["--preview"]])
def test_missing_model_fails_before_extraction(source, monkeypatch, capsys, flags):
    monkeypatch.setattr(
        service, "download_english_vtt", lambda *a: pytest.fail("must fail early")
    )
    assert cli.main([URL, "--no-config", "--provider", "deepseek", *flags]) == 1
    out = capsys.readouterr()
    assert not out.out and "DEEPSEEK_NOT_CONFIGURED" in out.err


def test_missing_key_fails_before_extraction(source, monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.setattr(
        service, "download_english_vtt", lambda *a: pytest.fail("must fail early")
    )
    assert (
        cli.main(
            [URL, "--no-config", "--provider", "deepseek", "--model", "deepseek-flash"]
        )
        == 1
    )
    out = capsys.readouterr()
    assert not out.out and "DEEPSEEK_NOT_CONFIGURED" in out.err


def test_saved_deepseek_raw_needs_no_model_or_key(
    source, monkeypatch, tmp_path, capsys
):
    config = tmp_path / "config.toml"
    config.write_text(
        '[formatting]\nprovider="deepseek"\neditorial_mode="summarized"\n'
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.setattr(backend, "complete", lambda *a: pytest.fail("no completion"))
    assert cli.main([URL, "--config", str(config), "--raw"]) == 0
    assert capsys.readouterr().out == "Retries can duplicate writes.\n"


@pytest.mark.parametrize("existing", [False, True])
def test_failure_preserves_publication_and_safe_diagnostics(
    source, monkeypatch, tmp_path, capsys, existing
):
    output = tmp_path / "document.md"
    if existing:
        output.write_text("original")
    monkeypatch.setattr(
        backend,
        "complete",
        lambda *a: (_ for _ in ()).throw(
            classify_deepseek_failure("DEEPSEEK_OUTPUT_INCOMPLETE")
        ),
    )
    assert (
        cli.main(
            [
                URL,
                "--no-config",
                "--provider",
                "deepseek",
                "--model",
                "deepseek-flash",
                "-v",
                "-o",
                str(output),
            ]
        )
        == 1
    )
    out = capsys.readouterr()
    assert not out.out and "DEEPSEEK_OUTPUT_INCOMPLETE" in out.err
    assert "KEY_NOT_FOR_OUTPUT" not in out.err
    assert "DESCRIPTION_NOT_MODEL_INPUT" not in out.err
    if existing:
        assert output.read_text() == "original"
    else:
        assert not output.exists()


def test_doctor_cli_is_offline(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        doctor, "run_doctor", lambda **kw: seen.append(kw) or doctor.DoctorReport(())
    )
    assert (
        cli.main(
            [
                "--doctor",
                "--no-config",
                "--provider",
                "deepseek",
                "--model",
                "deepseek-flash",
            ]
        )
        == 0
    )
    assert seen == [
        {"include_pi": False, "provider": "deepseek", "model": "deepseek-flash"}
    ]
    assert "not verified" in capsys.readouterr().out


@pytest.mark.parametrize("configured", [False, True])
def test_doctor_checks_only_presence_without_exposing_values(monkeypatch, configured):
    monkeypatch.setattr(
        doctor, "_tool", lambda name, *a: doctor.DoctorCheck(name, "ok", "local")
    )
    monkeypatch.setattr(doctor.metadata, "version", lambda name: "1.0.0")
    monkeypatch.setattr(doctor.metadata, "requires", lambda name: [])
    if configured:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "PRIVATE_KEY_SENTINEL")
    else:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    report = doctor.run_doctor(
        include_pi=False,
        provider="deepseek",
        model="PRIVATE_MODEL_SENTINEL" if configured else None,
    )
    entries = {check.name: check for check in report.checks}
    assert entries["Pi"].detail == "not required"
    for name in ("DeepSeek model", "DeepSeek key"):
        assert entries[name].status == ("ok" if configured else "error")
    text = doctor.render_doctor(report)
    assert "PRIVATE_KEY_SENTINEL" not in text
    assert "PRIVATE_MODEL_SENTINEL" not in text
