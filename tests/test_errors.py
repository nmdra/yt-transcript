import pytest
from yt_dlp.networking.exceptions import TransportError
from yt_dlp.utils import DownloadError, ExtractorError, GeoRestrictedError

from yt_transcript.errors import (
    AppError,
    ErrorInfo,
    FormattingError,
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
    assert "warning: No model-processed transcript was returned." in cli
    assert "Retry with --raw" in cli
    assert 'output_format="plain_text"' in mcp
    assert "--raw" not in mcp
    assert "warning: No model-processed transcript was returned." in mcp


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


@pytest.mark.parametrize(
    "code",
    [
        "DEEPSEEK_NOT_CONFIGURED",
        "DEEPSEEK_FAILED",
        "DEEPSEEK_AUTH_FAILED",
        "DEEPSEEK_LIMITED",
        "DEEPSEEK_TIMEOUT",
        "DEEPSEEK_OUTPUT_INCOMPLETE",
        "DEEPSEEK_OUTPUT_INVALID",
        "DEEPSEEK_CONTEXT_LIMIT",
    ],
)
def test_deepseek_exact_decoder_and_recovery(code):
    from dataclasses import asdict, replace

    from yt_transcript.errors import (
        classify_deepseek_failure,
        decode_worker_error,
        render_mcp_error,
    )

    expected = classify_deepseek_failure(code).info
    decoded = decode_worker_error(
        asdict(replace(expected, message="PRIVATE_REASONING", hint="Bearer secret"))
    )
    assert decoded == expected
    cli = render_cli_error(AppError(decoded))
    mcp = render_mcp_error(decoded)
    assert "warning: No model-processed transcript was returned." in cli
    assert "warning: No model-processed transcript was returned." in mcp
    assert "--raw" not in mcp and 'output_format="plain_text"' in mcp
    assert "PRIVATE_REASONING" not in cli + mcp


@pytest.mark.parametrize(
    "stage,reason,context,counts",
    [
        ("notes", "raw_budget", False, (11, 10)),
        ("notes", "serialized_budget", False, (11, 10)),
        ("notes", "invalid_json", False, (None, None)),
        ("notes", "invalid_schema", False, (None, None)),
        ("notes", "invalid_reference", False, (None, None)),
        ("synthesis", "capacity", True, (None, None)),
        ("synthesis", "payload_budget", True, (11, 10)),
    ],
)
def test_deepseek_summary_translation_and_exact_decoder(stage, reason, context, counts):
    from dataclasses import asdict, replace

    from yt_transcript.errors import (
        decode_worker_error,
        render_mcp_error,
        summary_failure,
        translate_formatting_error,
    )

    exc = summary_failure(
        stage, reason, actual_chars=counts[0], allowed_chars=counts[1], context=context
    )
    exc.info = replace(exc.info, chunk_index=2, chunk_total=3)
    translated = translate_formatting_error(exc, "deepseek")
    assert translated.info.code == (
        "DEEPSEEK_CONTEXT_LIMIT" if context else "DEEPSEEK_OUTPUT_INVALID"
    )
    assert translated.info.summary_diagnostic == exc.info.summary_diagnostic
    assert decode_worker_error(asdict(translated.info)) == translated.info
    assert "(chunk 2/3)" in render_mcp_error(translated.info)
    bad = asdict(translated.info)
    bad["summary_diagnostic"]["reason"] = "PRIVATE_REASONING"
    with pytest.raises(ValueError):
        decode_worker_error(bad)


def test_deepseek_summary_decoder_rejects_wrong_code_or_stage():
    from dataclasses import asdict

    from yt_transcript.errors import classify_deepseek_failure, decode_worker_error

    value = asdict(classify_deepseek_failure("DEEPSEEK_FAILED").info)
    value["summary_diagnostic"] = {
        "stage": "notes",
        "reason": "invalid_json",
        "actual_chars": None,
        "allowed_chars": None,
    }
    with pytest.raises(ValueError):
        decode_worker_error(value)
    value["code"] = "DEEPSEEK_CONTEXT_LIMIT"
    with pytest.raises(ValueError):
        decode_worker_error(value)
    value["phase"] = "PRIVATE_REASONING"
    with pytest.raises(ValueError):
        decode_worker_error(value)


def test_output_failure_reports_validation_reason():
    from yt_transcript.errors import output_failure

    exc = output_failure("body_yaml_header")
    assert exc.info.code == "PI_OUTPUT_INVALID"
    assert exc.info.message == (
        "Pi returned an invalid Markdown body. Validation reason: body_yaml_header."
    )
    assert exc.info.hint is not None and "--raw" in exc.info.hint
    assert "validation_reason=body_yaml_header" in render_diagnostics(exc)


OUTPUT_REASONS = (
    "completion_empty_text",
    "body_empty_text",
    "body_yaml_header",
    "body_outer_fence",
    "chapter_invalid_fence",
    "chapter_level_one_heading",
    "chapter_setext_heading",
    "chapter_unclosed_fence",
    "chapter_missing_headings",
    "chapter_heading_mismatch",
    "chapter_preamble",
    "chapter_empty_body",
    "chapter_invalid_json",
    "chapter_invalid_schema",
    "chapter_invalid_run_ids",
    "transcript_unexpected_omission",
    "transcript_empty_output",
    "summary_empty_output",
    "summary_unexpected_omission",
    "summary_invalid_structure",
    "summary_empty_evidence",
    "summary_private_id",
)


@pytest.mark.parametrize("reason", OUTPUT_REASONS)
@pytest.mark.parametrize("provider", ["pi", "openrouter", "deepseek"])
def test_output_reasons_survive_translation_worker_and_rendering(reason, provider):
    from dataclasses import asdict, replace

    from yt_transcript.errors import (
        decode_worker_error,
        output_failure,
        render_mcp_error,
        translate_formatting_error,
    )

    exc = output_failure(reason)
    original_hint = exc.info.hint
    exc.info = replace(exc.info, chunk_index=2, chunk_total=3)
    translated = translate_formatting_error(exc, provider)
    assert translated.info.code == f"{provider.upper()}_OUTPUT_INVALID"
    assert translated.info.phase == f"{provider}_response"
    assert translated.info.hint == original_hint
    assert translated.info.summary_diagnostic is None
    assert (translated.info.chunk_index, translated.info.chunk_total) == (2, 3)
    assert translated.info.message.endswith(f" Validation reason: {reason}.")
    decoded = decode_worker_error(asdict(translated.info))
    assert decoded == translated.info
    cli, mcp = render_cli_error(AppError(decoded)), render_mcp_error(decoded)
    assert f"Validation reason: {reason}." in cli + mcp
    assert "(chunk 2/3)" in cli and "(chunk 2/3)" in mcp
    assert "--raw" in cli and "--raw" not in mcp
    assert 'output_format="plain_text"' in mcp
    assert f"validation_reason={reason}" in render_diagnostics(AppError(decoded))
    # No caller-supplied reason can replace the reason in the trusted message.
    assert "PRIVATE_REASONING" not in render_diagnostics(
        AppError(decoded), validation_reason="PRIVATE_REASONING"
    )


@pytest.mark.parametrize(
    "reason",
    [
        "PRIVATE_REASONING",
        "body_yaml_header\nBearer secret",
        " body_yaml_header",
        "body_yaml_header.",
        "chapter_unknown",
        "",
        None,
        [],
    ],
)
def test_output_failure_rejects_unknown_reason_without_echo(reason):
    from yt_transcript.errors import output_failure

    with pytest.raises(ValueError, match="^Invalid output validation reason$"):
        output_failure(reason)


@pytest.mark.parametrize("provider", ["pi", "openrouter", "deepseek"])
@pytest.mark.parametrize(
    "mutation",
    [
        "prefix",
        "suffix",
        "substring",
        "unknown_reason",
        "newline",
        "missing_period",
        "wrong_provider",
        "nonstring",
    ],
)
def test_output_worker_accepts_only_exact_trusted_messages(provider, mutation):
    from dataclasses import asdict, replace

    from yt_transcript.errors import (
        decode_worker_error,
        output_failure,
        translate_formatting_error,
    )

    exc = translate_formatting_error(output_failure("chapter_preamble"), provider)
    message = exc.info.message
    mutated = {
        "prefix": "Bearer secret " + message,
        "suffix": message + " PRIVATE_REASONING",
        "substring": "Validation reason: chapter_preamble.",
        "unknown_reason": message.replace("chapter_preamble", "PRIVATE_REASONING"),
        "newline": message + "\n",
        "missing_period": message[:-1],
        "wrong_provider": message.replace(
            {"pi": "Pi", "openrouter": "OpenRouter", "deepseek": "DeepSeek"}[provider],
            "OtherProvider",
        ),
        "nonstring": [message],
    }[mutation]
    decoded = decode_worker_error(
        asdict(replace(exc.info, message=mutated, hint="Bearer secret"))
    )
    assert decoded.message != message
    assert "Validation reason:" not in decoded.message
    assert "validation_reason=" not in render_diagnostics(AppError(decoded))
    assert "Bearer" not in render_cli_error(AppError(decoded))
    if provider == "pi":
        sanitized = replace(exc.info, message=mutated)
        for target in ("openrouter", "deepseek"):
            translated = translate_formatting_error(FormattingError(sanitized), target)
            assert "Validation reason:" not in translated.info.message


@pytest.mark.parametrize(
    "code",
    [
        "PI_FAILED",
        "PI_OUTPUT_LIMIT",
        "PI_CONTEXT_LIMIT",
        "OPENROUTER_FAILED",
        "DEEPSEEK_FAILED",
        "NETWORK_FAILED",
    ],
)
def test_output_reason_is_not_recognized_on_unrelated_codes(code):
    from dataclasses import asdict, replace

    from yt_transcript.errors import decode_worker_error, output_failure

    info = replace(output_failure("body_empty_text").info, code=code)
    assert "validation_reason=" not in render_diagnostics(AppError(info))
    decoded = decode_worker_error(asdict(info))
    assert "Validation reason:" not in decoded.message


@pytest.mark.parametrize("provider", ["pi", "openrouter", "deepseek"])
@pytest.mark.parametrize("context", [False, True])
def test_summary_diagnostic_keeps_priority_over_output_reason(provider, context):
    from dataclasses import asdict, replace

    from yt_transcript.errors import (
        decode_worker_error,
        output_failure,
        summary_failure,
        translate_formatting_error,
    )

    summary = summary_failure(
        "synthesis" if context else "notes",
        "capacity" if context else "invalid_json",
        context=context,
    )
    expected = translate_formatting_error(summary, provider)
    combined = replace(
        summary.info, message=output_failure("summary_private_id").info.message
    )
    decoded = decode_worker_error(asdict(combined))
    assert decoded == summary.info
    translated = translate_formatting_error(FormattingError(combined), provider)
    if provider != "pi":
        assert translated.info == expected.info
    diagnostics = render_diagnostics(AppError(combined))
    assert "summary=" in diagnostics
    assert "validation_reason=" not in diagnostics


def test_worker_preserves_requested_caption_language_message():
    from yt_transcript.errors import decode_worker_error

    for message in (
        "no captions found for requested language: fr",
        "no VTT captions found for requested language: zh-Hans",
    ):
        info = decode_worker_error(
            {
                "code": "NO_CAPTIONS",
                "message": message,
                "hint": "No matching captions were returned; availability is not guaranteed.",
                "phase": "caption_select",
                "retryable": False,
                "chunk_index": None,
                "chunk_total": None,
                "summary_diagnostic": None,
            }
        )
        assert info.message == message
    info = decode_worker_error(
        {
            "code": "NO_CAPTIONS",
            "message": "private upstream text",
            "hint": None,
            "phase": "caption_select",
            "retryable": False,
            "chunk_index": None,
            "chunk_total": None,
            "summary_diagnostic": None,
        }
    )
    assert info.message == "Worker operation failed."
