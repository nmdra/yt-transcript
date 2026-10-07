"""SDK-independent deterministic service results shared by CLI and MCP."""

from dataclasses import dataclass
from types import UnionType
from typing import (
    Any,
    Literal,
    TypedDict,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from .cleaner import clean_vtt
from .downloader import download_english_vtt
from .errors import ErrorInfo, TranscriptError
from .formatter import plan_formatting
from .metadata import VideoMetadata, format_transcript_file, metadata_mapping


class MetadataResult(TypedDict):
    url: str
    video_id: str
    title: str | None
    channel: str | None
    channel_id: str | None
    channel_url: str | None
    upload_date: str | None
    duration_seconds: int | float | None
    caption_language: str
    caption_source: Literal["manual", "automatic"]


class TranscriptResult(TypedDict):
    format: Literal["plain_text"]
    document: str
    metadata: MetadataResult
    character_count: int


class PreviewResult(TypedDict):
    metadata: MetadataResult
    character_count: int
    planned_invocations: int
    largest_chunk_chars: int
    chunk_chars: int
    max_chunks: int | None
    within_cap: bool
    model_selection: str


class CheckResult(TypedDict):
    name: str
    status: str
    detail: str


class DoctorResult(TypedDict):
    healthy: bool
    checks: list[CheckResult]


def validate_service_result(operation: str, value: object) -> None:
    """Reject malformed worker results before SDK conversion can log their contents."""
    expected = {
        "get_transcript": TranscriptResult,
        "preview_transcript": PreviewResult,
        "doctor": DoctorResult,
    }[operation]

    def matches(item: object, annotation: Any) -> bool:
        origin = get_origin(annotation)
        if origin in (Union, UnionType):
            return any(matches(item, part) for part in get_args(annotation))
        if origin is Literal:
            return any(
                type(item) is type(part) and item == part
                for part in get_args(annotation)
            )
        if origin is list:
            return isinstance(item, list) and all(
                matches(part, get_args(annotation)[0]) for part in item
            )
        if hasattr(annotation, "__required_keys__"):
            fields = get_type_hints(annotation)
            return (
                isinstance(item, dict)
                and set(item) == set(fields)
                and all(matches(item[key], hint) for key, hint in fields.items())
            )
        if annotation is type(None):
            return item is None
        return type(item) is annotation

    if not matches(value, expected):
        raise TranscriptError(
            ErrorInfo("INTERNAL_ERROR", "Worker operation failed.", phase="mcp_worker")
        )


@dataclass(frozen=True)
class CleanedTranscript:
    body: str
    metadata: VideoMetadata
    language: str
    automatic: bool

    def mapping(self) -> MetadataResult:
        return cast(
            MetadataResult,
            metadata_mapping(
                self.metadata, language=self.language, automatic=self.automatic
            ),
        )

    def document(self, body: str | None = None) -> str:
        return format_transcript_file(
            self.metadata,
            self.body if body is None else body,
            language=self.language,
            automatic=self.automatic,
        )


def fetch_clean_transcript(url: str) -> CleanedTranscript:
    downloaded = download_english_vtt(url)
    try:
        body = clean_vtt(
            downloaded.vtt.decode("utf-8-sig"), automatic=downloaded.automatic
        )
    except UnicodeError:
        raise TranscriptError(
            ErrorInfo(
                "SUBTITLE_INVALID", "Captions are not valid UTF-8.", phase="vtt_parse"
            )
        ) from None
    return CleanedTranscript(
        body, downloaded.metadata, downloaded.language, downloaded.automatic
    )


def fetch_transcript_document(url: str) -> TranscriptResult:
    cleaned = fetch_clean_transcript(url)
    return {
        "format": "plain_text",
        "document": cleaned.document(),
        "metadata": cleaned.mapping(),
        "character_count": len(cleaned.body),
    }


def preview_transcript_data(
    url: str, *, chunk_chars: int, max_chunks: int | None, model_description: str
) -> PreviewResult:
    cleaned = fetch_clean_transcript(url)
    plan = plan_formatting(cleaned.body, chunk_chars=chunk_chars, max_chunks=max_chunks)
    return {
        "metadata": cleaned.mapping(),
        "character_count": len(cleaned.body),
        "planned_invocations": len(plan.chunks),
        "largest_chunk_chars": max(plan.character_counts, default=0),
        "chunk_chars": chunk_chars,
        "max_chunks": max_chunks,
        "within_cap": plan.within_cap,
        "model_selection": model_description,
    }


def doctor_data() -> DoctorResult:
    from .doctor import run_doctor

    report = run_doctor(include_pi=False)
    return {
        "healthy": report.healthy,
        "checks": [
            {"name": check.name, "status": check.status, "detail": check.detail}
            for check in report.checks
        ],
    }
