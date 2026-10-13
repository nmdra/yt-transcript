"""Versioned machine-readable CLI documents. Exactly one document per stream."""

import json
from collections.abc import Mapping
from typing import Any

from .doctor import DoctorReport
from .errors import (
    CODES,
    PHASES,
    AppError,
    safe_diagnostic_fields,
    validate_summary_diagnostic,
)

SCHEMA_VERSION = 1
DOCTOR_NOTE = (
    "Local readiness only; access, authentication, and model accuracy are not verified."
)


def serialize(document: dict[str, Any]) -> str:
    """Return one compact JSON document with exactly one trailing newline."""
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _position(value: object) -> int | None:
    return value if type(value) is int else None


def doctor_document(report: DoctorReport) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "doctor",
        "healthy": report.healthy,
        "checks": [
            {"name": check.name, "status": check.status, "detail": check.detail}
            for check in report.checks
        ],
        "note": DOCTOR_NOTE,
    }


def error_document(
    exc: AppError, *, verbose: bool = False, **fields: Any
) -> dict[str, Any]:
    """Expose exactly what the text error renderer already prints."""
    info = exc.info
    try:
        diagnostic = validate_summary_diagnostic(info.summary_diagnostic)
    except ValueError:
        diagnostic = None
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "error",
        "error": {
            "code": info.code if info.code in CODES else "INTERNAL_ERROR",
            "phase": info.phase if info.phase in PHASES else "mcp_worker",
            "retryable": bool(info.retryable),
            "chunk_index": _position(info.chunk_index),
            "chunk_total": _position(info.chunk_total),
            "message": _text(info.message) or "Operation failed.",
            "hint": _text(info.hint),
            "summary_diagnostic": diagnostic,
            "diagnostic": safe_diagnostic_fields(exc, **fields) if verbose else None,
        },
    }


def preview_document(
    *,
    canonical_url: str,
    language: str,
    automatic: bool,
    translated: bool | None,
    cache_enabled: bool,
    cache_hit: bool | None,
    cleaned_characters: int,
    retained_characters: int,
    sponsorblock_enabled: bool,
    sponsorblock_status: str,
    removed_cues: int,
    warning: str | None,
    plan_invocations: int,
    character_counts: tuple[int, ...],
    synthesis_invocations: int,
    summary_note_limit: int | None,
    within_cap: bool,
    configured_chunk_chars: int,
    configured_summary_synthesis_chars: int,
    max_chunks: int | None,
    provider: str,
    model: str | None,
    editorial_mode: str,
    thinking: bool | None,
    thinking_level: str | None,
    boundary_context_chars: int | None,
) -> dict[str, Any]:
    """Describe the planned model calls. Never carries caption text or descriptions."""
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "preview",
        "canonical_url": canonical_url,
        "caption": {
            "language": language,
            "source": "automatic" if automatic else "manual",
            "translated": translated,
        },
        "cache": {"enabled": cache_enabled, "hit": bool(cache_hit)},
        "sponsorblock": {
            "enabled": sponsorblock_enabled,
            "status": sponsorblock_status,
            "removed_cues": removed_cues,
            "warning": warning,
        },
        "characters": {"cleaned": cleaned_characters, "retained": retained_characters},
        "plan": {
            "invocations": plan_invocations,
            "synthesis_invocations": synthesis_invocations,
            "largest_chunk": max(character_counts, default=0),
            "character_counts": list(character_counts),
            "summary_note_limit": summary_note_limit,
            "configured_chunk_chars": configured_chunk_chars,
            "configured_summary_synthesis_chars": configured_summary_synthesis_chars,
            "max_chunks": max_chunks,
            "within_cap": within_cap,
        },
        "provider": provider,
        "model": model,
        "editorial_mode": editorial_mode,
        "thinking": {
            "requested": thinking,
            "level": thinking_level,
            "deepseek_medium_mapping": "medium -> high"
            if provider == "deepseek" and thinking_level == "medium"
            else None,
        },
        "boundary_context_chars": boundary_context_chars,
    }


def transcript_document(
    *,
    mode: str,
    metadata: Mapping[str, Any],
    body: str,
    cache_enabled: bool,
    cache_hit: bool | None,
    cues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reuse the YAML metadata mapping so JSON and file metadata cannot drift."""
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "transcript",
        "mode": mode,
        "cache": {"enabled": cache_enabled, "hit": bool(cache_hit)},
        **metadata,
        "body": body,
        "character_count": len(body),
    }
    if cues is not None:
        document["cues"] = cues
    return document
