"""Machine-readable document shape, versioning, and safety. No network, no model calls."""

import json

import pytest

from yt_transcript import json_output
from yt_transcript.doctor import DoctorCheck, DoctorReport
from yt_transcript.errors import AppError, ErrorInfo


def test_serialize_is_one_compact_line():
    text = json_output.serialize({"schema_version": 1, "command": "doctor"})
    assert text.endswith("\n")
    assert text.count("\n") == 1
    assert json.loads(text) == {"schema_version": 1, "command": "doctor"}


def test_serialize_rejects_non_finite_floats():
    with pytest.raises(ValueError):
        json_output.serialize({"value": float("nan")})


def test_doctor_document_shape():
    report = DoctorReport(
        (
            DoctorCheck("Python", "ok", "3.14.7"),
            DoctorCheck("deno", "error", "not installed"),
        )
    )
    document = json_output.doctor_document(report)
    assert document["schema_version"] == json_output.SCHEMA_VERSION
    assert document["command"] == "doctor"
    assert document["healthy"] is False
    assert document["checks"] == [
        {"name": "Python", "status": "ok", "detail": "3.14.7"},
        {"name": "deno", "status": "error", "detail": "not installed"},
    ]
    assert "not verified" in document["note"]


def test_error_document_carries_bounded_position_and_bool():
    exc = AppError(
        ErrorInfo(
            "PI_TIMEOUT",
            "model call timed out",
            "Retry later.",
            "pi_response",
            True,
            2,
            3,
        )
    )
    error = json_output.error_document(exc)["error"]
    assert error["code"] == "PI_TIMEOUT"
    assert error["phase"] == "pi_response"
    assert error["retryable"] is True
    assert error["chunk_index"] == 2
    assert error["chunk_total"] == 3
    assert error["diagnostic"] is None


def test_error_document_discards_unknown_codes_and_phases():
    exc = AppError(ErrorInfo("PRIVATE_CODE", "private message", phase="private_phase"))
    error = json_output.error_document(exc)["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["phase"] == "mcp_worker"


def test_error_document_verbose_diagnostic_discards_arbitrary_text():
    exc = AppError(ErrorInfo("PI_FAILED", "model failed", phase="pi_response"))
    document = json_output.error_document(
        exc, verbose=True, http_status=401, line="private stderr text"
    )
    diagnostic = document["error"]["diagnostic"]
    assert diagnostic["http_status"] == "401"
    assert "line" not in diagnostic
    assert "private stderr text" not in json_output.serialize(document)


def test_preview_document_shape_and_omissions():
    document = json_output.preview_document(
        canonical_url="https://www.youtube.com/watch?v=abcdefghijk",
        language="fr",
        automatic=True,
        translated=True,
        cache_enabled=True,
        cache_hit=True,
        cleaned_characters=100,
        retained_characters=90,
        sponsorblock_enabled=False,
        sponsorblock_status="disabled",
        removed_cues=0,
        warning=None,
        plan_invocations=3,
        character_counts=(1000, 900),
        synthesis_invocations=1,
        summary_note_limit=4000,
        within_cap=True,
        configured_chunk_chars=12000,
        configured_summary_synthesis_chars=50000,
        max_chunks=20,
        provider="deepseek",
        model="deepseek-flash",
        editorial_mode="summarized",
        thinking=True,
        thinking_level="medium",
        boundary_context_chars=None,
    )
    assert document["command"] == "preview"
    assert document["caption"] == {
        "language": "fr",
        "source": "automatic",
        "translated": True,
    }
    assert document["cache"] == {"enabled": True, "hit": True}
    assert document["plan"]["invocations"] == 3
    assert document["plan"]["largest_chunk"] == 1000
    assert document["plan"]["character_counts"] == [1000, 900]
    assert document["plan"]["summary_note_limit"] == 4000
    assert document["thinking"]["deepseek_medium_mapping"] == "medium -> high"
    assert "chunks" not in document["plan"]


def test_transcript_document_reuses_metadata_keys():
    metadata = {
        "url": "https://www.youtube.com/watch?v=abcdefghijk",
        "video_id": "abcdefghijk",
        "caption_language": "en",
        "caption_source": "manual",
        "caption_translated": False,
        "description": "private description",
    }
    document = json_output.transcript_document(
        mode="raw",
        metadata=metadata,
        body="hello",
        cache_enabled=True,
        cache_hit=False,
        cues=[{"start_seconds": 0.0, "end_seconds": 1.0, "text": "hello"}],
    )
    assert document["mode"] == "raw"
    assert document["body"] == "hello"
    assert document["character_count"] == 5
    assert document["video_id"] == "abcdefghijk"
    assert document["cues"][0]["start_seconds"] == 0.0
    assert document["schema_version"] == json_output.SCHEMA_VERSION


def test_transcript_document_omits_cues_when_not_supplied():
    document = json_output.transcript_document(
        mode="markdown",
        metadata={"video_id": "abcdefghijk"},
        body="edited",
        cache_enabled=False,
        cache_hit=None,
    )
    assert "cues" not in document
    assert document["cache"] == {"enabled": False, "hit": False}
