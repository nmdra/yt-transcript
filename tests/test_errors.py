import pytest
from yt_dlp.networking.exceptions import TransportError
from yt_dlp.utils import DownloadError, ExtractorError, GeoRestrictedError

from yt_transcript.errors import (
    AppError,
    ErrorInfo,
    WarningCollector,
    classify_pi_failure,
    classify_ytdlp_error,
    render_cli_error,
    render_diagnostics,
    walk_causes,
)


@pytest.mark.parametrize(
    "exc,code",
    [
        (GeoRestrictedError("secret"), "GEO_RESTRICTED"),
        (TransportError("Bearer secret"), "NETWORK_FAILED"),
        (ExtractorError("Video unavailable"), "VIDEO_UNAVAILABLE"),
        (ExtractorError("unknown provider auth quota 403"), "YOUTUBE_EXTRACT_FAILED"),
    ],
)
def test_classify(exc, code):
    from typing import Any, cast

    wrapped = DownloadError("secret", exc_info=cast(Any, (type(exc), exc, None)))
    assert classify_ytdlp_error(wrapped, phase="metadata_extract").info.code == code


def test_cycles_and_malformed():
    class MalformedError(Exception):
        exc_info = "bad"

    exc = MalformedError("private")
    exc.__cause__ = exc
    assert list(walk_causes(exc)) == [exc]
    assert (
        classify_ytdlp_error(exc, phase="subtitle_download").info.code
        == "SUBTITLE_DOWNLOAD_FAILED"
    )


def test_warning():
    collector = WarningCollector()
    collector.warning("ordinary warning")
    assert not collector.access_limited
    collector.warning("PO Token required")
    assert collector.access_limited
    collector.warning("x" * 100000)
    assert collector._size <= 65536


@pytest.mark.parametrize(
    "text,code",
    [
        ("rate_limit_exceeded", "PI_RATE_LIMITED"),
        ("insufficient_quota", "PI_QUOTA_EXCEEDED"),
        ("unknown authentication quota failure", "PI_FAILED"),
    ],
)
def test_pi(text, code):
    assert classify_pi_failure(text).info.code == code


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "REMOTE_ACCESS_DENIED"),
        (403, "REMOTE_ACCESS_DENIED"),
        (429, "REMOTE_RATE_LIMITED"),
    ],
)
def test_http_status_precedence(status, code):
    import io

    from yt_dlp.networking.common import Response
    from yt_dlp.networking.exceptions import HTTPError

    response = Response(
        io.BytesIO(),
        "https://private?token=secret",
        {"Authorization": "Bearer key"},
        status=status,
    )
    cause = HTTPError(response)
    wrapped = ExtractorError("Sign in to confirm your age", cause=cause)
    for phase in ("metadata_extract", "subtitle_download"):
        result = classify_ytdlp_error(wrapped, phase=phase)
        assert result.info.code == code and result.info.phase == phase
        assert "secret" not in render_cli_error(result)


def test_fixture_recognizers():
    import json
    from pathlib import Path

    fixture = json.loads(
        (Path(__file__).parent / "fixtures/errors/recognizers.json").read_text()
    )
    for text, code in fixture["youtube"]:
        assert (
            classify_ytdlp_error(
                ExtractorError(text), phase="metadata_extract"
            ).info.code
            == code
        )
    for text, code in fixture["pi"]:
        assert classify_pi_failure(text).info.code == code


@pytest.mark.parametrize(
    "text",
    [
        "Unknown failure for video title: Video unavailable",
        "Unknown failure for title: Sign in to confirm your age",
        "Unknown failure for title: PO Token required",
    ],
)
def test_error_like_titles_do_not_establish_a_cause(text):
    assert (
        classify_ytdlp_error(ExtractorError(text), phase="metadata_extract").info.code
        == "YOUTUBE_EXTRACT_FAILED"
    )
    assert (
        classify_pi_failure(
            "Unknown failure for title: No API key found for x"
        ).info.code
        == "PI_FAILED"
    )
    collector = WarningCollector()
    collector.warning(text)
    assert not collector.access_limited


def test_typed_http_cause_wins_over_outer_transport():
    import io

    from yt_dlp.networking.common import Response
    from yt_dlp.networking.exceptions import HTTPError

    outer = TransportError("private")
    outer.__cause__ = HTTPError(
        Response(io.BytesIO(), "https://private", {}, status=429)
    )
    assert (
        classify_ytdlp_error(outer, phase="subtitle_download").info.code
        == "REMOTE_RATE_LIMITED"
    )


def test_worker_error_allowlist():
    from dataclasses import asdict

    from yt_transcript.errors import decode_worker_error, render_mcp_error

    info = ErrorInfo(
        "NETWORK_FAILED",
        "Bearer secret caption text",
        "private /home/path",
        "subtitle_download",
    )
    safe = decode_worker_error(asdict(info))
    assert "secret" not in render_mcp_error(safe)
    assert "/home" not in render_mcp_error(safe)
    assert safe.code == "NETWORK_FAILED"


@pytest.mark.parametrize(
    "code", ["PI_NOT_FOUND", "PI_AUTH_FAILED", "PI_TIMEOUT", "PI_CONTEXT_MUTATED"]
)
def test_worker_pi_errors_rebuild_trusted_messages(code):
    from dataclasses import asdict, replace

    from yt_transcript.errors import decode_worker_error

    expected = classify_pi_failure(code=code, chunk_index=1, chunk_total=2).info
    payload = asdict(
        replace(expected, message="Bearer private caption text", hint="/private/path")
    )
    assert decode_worker_error(payload) == expected


@pytest.mark.parametrize(
    "required,cap,accepted",
    [
        ("5", "3", True),
        ("100001", "3", False),
        ("5", "1001", False),
        ("3", "5", False),
        ("5", "0", False),
        ("private", "3", False),
    ],
)
def test_worker_chunk_limit_details_are_bounded(required, cap, accepted):
    from dataclasses import asdict, replace

    from yt_transcript.errors import decode_worker_error

    expected = classify_pi_failure(code="CHUNK_LIMIT_EXCEEDED").info
    message = (
        f"formatting requires {required} chunks, exceeding max-chunks {cap}; "
        "use --preview, --raw, or explicitly raise the cap"
    )
    decoded = decode_worker_error(
        asdict(replace(expected, message=message, hint="Bearer private"))
    )
    assert decoded.message == (message if accepted else expected.message)
    assert decoded.hint == expected.hint


@pytest.mark.parametrize(
    "index,total", [(None, 2), (1, None), (3, 2), (True, 2), (0, 2)]
)
def test_worker_rejects_invalid_chunk_pairs(index, total):
    from dataclasses import asdict

    from yt_transcript.errors import decode_worker_error

    payload = asdict(classify_pi_failure(code="PI_CONTEXT_MUTATED").info)
    payload.update(chunk_index=index, chunk_total=total)
    with pytest.raises(ValueError):
        decode_worker_error(payload)


@pytest.mark.parametrize(
    "code",
    [
        "PI_CONTEXT_MUTATED",
        "PI_CONTEXT_LIMIT",
        "PI_OUTPUT_INVALID",
        "PI_TIMEOUT",
        "PI_NOT_FOUND",
        "CHUNK_LIMIT_EXCEEDED",
    ],
)
def test_formatting_recovery_is_interface_specific(code):
    from yt_transcript.errors import render_mcp_error

    exc = classify_pi_failure(code=code, chunk_index=2, chunk_total=3)
    cli = render_cli_error(exc)
    mcp = render_mcp_error(exc.info)
    assert "(chunk 2/3)" in cli and "(chunk 2/3)" in mcp
    assert "warning: No Pi-processed transcript was returned." in cli
    assert "Retry with --raw" in cli
    assert 'output_format="plain_text"' in mcp
    assert "--raw" not in mcp
    assert "warning: No Pi-processed transcript was returned." in mcp


def test_nonformatting_errors_have_no_pi_warning():
    from yt_transcript.errors import render_mcp_error

    info = ErrorInfo("INVALID_URL", "Expected a YouTube video URL.")
    assert "warning:" not in render_mcp_error(info)
    assert "warning:" not in render_cli_error(AppError(info))


def test_safe_rendering():
    secret = "Bearer key cookie Authorization signed?token=value /home/private transcript caption-secret \x1b[31m"
    exc = AppError(
        ErrorInfo("PI_FAILED", "Pi formatting failed.", phase="pi_response"),
        cause=Exception(secret),
    )
    rendered = render_cli_error(exc) + render_diagnostics(
        exc,
        library_version=secret,
        exception_class=secret,
        stop_reason=secret,
        stderr=secret,
    )
    assert secret not in rendered
    for value in (
        "Bearer",
        "cookie",
        "Authorization",
        "token=value",
        "private",
        "transcript caption-secret",
        "\x1b",
    ):
        assert value not in rendered
