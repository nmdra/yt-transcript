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


def test_safe_rendering():
    secret = "Bearer key cookie Authorization signed?token=value /home/private transcript \x1b[31m"
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
        "transcript",
        "\x1b",
    ):
        assert value not in rendered
