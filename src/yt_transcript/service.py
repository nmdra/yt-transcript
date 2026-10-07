"""SDK-independent transcript services shared by CLI and MCP."""

import math
import os
from dataclasses import asdict, dataclass, replace
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

from .chapters import (
    ChapterSection,
    build_chapter_sections,
    render_chapter_text,
    render_timed_text,
)
from .cleaner import Cue, clean_vtt_timed
from .downloader import download_english_vtt
from .errors import ErrorInfo, TranscriptError
from .mcp_policy import MCPFormattingPolicy, validate_formatting_policy
from .metadata import VideoMetadata, format_transcript_file, metadata_mapping
from .sponsorblock import (
    CaptionProjection,
    SponsorBlockConfig,
    SponsorBlockRemovalReceipt,
    SponsorBlockResult,
    compute_receipt,
    lookup_sponsorblock,
    project_sponsorblock,
)

TranscriptMode = Literal["filtered", "full"]
TranscriptFormat = Literal["plain_text", "markdown"]


class ChapterResult(TypedDict):
    title: str
    start_seconds: int | float
    end_seconds: int | float | None


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
    chapter_status: Literal["available", "unavailable", "invalid"]
    chapters: list[ChapterResult]
    sponsorblock: SponsorBlockResult


class TranscriptResult(TypedDict):
    format: TranscriptFormat
    document: str
    metadata: MetadataResult
    character_count: int


def validate_service_result(operation: str, value: object) -> None:
    """Reject malformed worker results before SDK conversion can log their contents."""
    if operation != "get_transcript":
        raise TranscriptError(
            ErrorInfo("INTERNAL_ERROR", "Worker operation failed.", phase="mcp_worker")
        )
    expected = TranscriptResult

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
            if not (
                isinstance(item, dict)
                and set(item) == set(fields)
                and all(matches(item[key], hint) for key, hint in fields.items())
            ):
                return False
            if any(
                v < 0
                for k, v in item.items()
                if k.endswith("_cue_count") or k == "character_count"
            ):
                return False
            if "start_seconds" in item and (
                item["start_seconds"] < 0
                or (
                    item["end_seconds"] is not None
                    and item["end_seconds"] <= item["start_seconds"]
                )
            ):
                return False
            if "removal_status" in item:
                dropped, kept = (
                    item["removed_cue_count"],
                    item["retained_overlap_cue_count"],
                )
                state = item["removal_status"]
                if (
                    (
                        state in ("kept", "not_applied", "no_matching_captions")
                        and dropped != 0
                    )
                    or (state == "removed" and (dropped == 0 or kept != 0))
                    or (state == "partial" and (dropped == 0 or kept == 0))
                    or (state == "kept" and kept == 0)
                    or (state == "no_matching_captions" and kept != 0)
                ):
                    return False
            if annotation is SponsorBlockResult:
                state, segments = item["status"], item["segments"]
                if state == "disabled" and (item["enabled"] or segments):
                    return False
                if state != "disabled" and not item["enabled"]:
                    return False
                if state in ("disabled", "not_found") and segments:
                    return False
                if state == "available" and not segments:
                    return False
                if (state == "lookup_failed") != (item["warning"] is not None) or (
                    state == "lookup_failed"
                ) != (item["reason_code"] is not None):
                    return False
                if (
                    state == "lookup_failed"
                    and segments
                    and item["reason_code"] != "REMOVAL_WOULD_EMPTY"
                ):
                    return False
                if any(
                    (item[k] is not None) != bool(segments)
                    for k in ("source", "license_url", "changes")
                ):
                    return False
                count = item["removed_cue_count"]
                if item["removal_applied"] != (count > 0) or item["removal_stage"] != (
                    "source_filter" if count else "none"
                ):
                    return False
                if count > sum(s["removed_cue_count"] for s in segments) or (
                    count and state != "available"
                ):
                    return False
            return True
        if annotation is type(None):
            return item is None
        return type(item) is annotation and (
            not isinstance(item, float) or math.isfinite(item)
        )

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
    fragments: tuple[Cue, ...] = ()
    sections: tuple[ChapterSection, ...] = ()
    projection: CaptionProjection | None = None
    raw_receipt: SponsorBlockRemovalReceipt = SponsorBlockRemovalReceipt()

    @property
    def effective_body(self) -> str:
        return self.projection.body if self.projection else self.body

    @property
    def effective_sections(self) -> tuple[ChapterSection, ...]:
        return (
            build_chapter_sections(
                self.projection.fragments,
                self.metadata.chapters,
                source_indices=self.projection.source_indices,
            )
            if self.projection
            else self.sections
        )

    def mapping(self, *, effective: bool = False) -> MetadataResult:
        return cast(
            MetadataResult,
            metadata_mapping(
                self.metadata,
                language=self.language,
                automatic=self.automatic,
                sponsorblock_result=self.projection.lookup
                if effective and self.projection
                else self.metadata.sponsorblock,
                removal_receipt=self.projection.receipt
                if effective and self.projection
                else self.raw_receipt,
            ),
        )

    def document(self, body: str | None = None, *, effective: bool = False) -> str:
        return format_transcript_file(
            self.metadata,
            (self.effective_body if effective else self.body) if body is None else body,
            language=self.language,
            automatic=self.automatic,
            sponsorblock_result=self.projection.lookup
            if effective and self.projection
            else self.metadata.sponsorblock,
            removal_receipt=self.projection.receipt
            if effective and self.projection
            else self.raw_receipt,
        )


def fetch_clean_transcript(
    url: str, *, sponsorblock: SponsorBlockConfig | None = None
) -> CleanedTranscript:
    downloaded = download_english_vtt(url)
    try:
        fragments = clean_vtt_timed(
            downloaded.vtt.decode("utf-8-sig"), automatic=downloaded.automatic
        )
    except UnicodeError:
        raise TranscriptError(
            ErrorInfo(
                "SUBTITLE_INVALID", "Captions are not valid UTF-8.", phase="vtt_parse"
            )
        ) from None
    policy = (sponsorblock or SponsorBlockConfig()).resolved()
    lookup = lookup_sponsorblock(
        downloaded.metadata.video_id,
        config=policy,
        duration_seconds=downloaded.metadata.duration_seconds,
    )
    projection = project_sponsorblock(fragments, lookup)
    metadata = replace(downloaded.metadata, sponsorblock=lookup)
    return CleanedTranscript(
        " ".join(c.text for c in fragments),
        metadata,
        downloaded.language,
        downloaded.automatic,
        fragments,
        build_chapter_sections(fragments, downloaded.metadata.chapters),
        projection,
        compute_receipt(fragments, lookup),
    )


def fetch_transcript_document(
    url: str,
    mode: TranscriptMode = "filtered",
    *,
    sponsorblock: SponsorBlockConfig | None = None,
    output_format: TranscriptFormat = "plain_text",
    formatting: MCPFormattingPolicy | None = None,
    supervised: bool = False,
) -> TranscriptResult:
    if mode not in ("filtered", "full"):
        raise ValueError("Invalid transcript mode.")
    if output_format not in ("plain_text", "markdown"):
        raise ValueError("Invalid transcript format.")
    if output_format == "markdown":
        if supervised and os.name != "posix":
            raise TranscriptError(
                ErrorInfo(
                    "RUNTIME_INCOMPATIBLE",
                    "MCP Markdown output requires POSIX process supervision.",
                    "Use plain_text output on this platform.",
                    "runtime_check",
                )
            )
        from .formatter import ensure_pi

        formatting = validate_formatting_policy(
            asdict(formatting or MCPFormattingPolicy())
        )
        ensure_pi()
    policy = (sponsorblock or SponsorBlockConfig()).resolved(default=True)
    if mode == "full":
        policy = replace(policy, enabled=False)
    cleaned = fetch_clean_transcript(url, sponsorblock=policy)
    projection = cleaned.projection
    assert projection is not None
    if output_format == "markdown":
        from .formatter import format_with_pi

        assert formatting is not None
        body = format_with_pi(
            cleaned.effective_body,
            sections=cleaned.effective_sections,
            model=formatting.model,
            chunk_chars=formatting.chunk_chars,
            timeout_seconds=formatting.timeout_seconds,
            max_chunks=formatting.max_chunks,
            editorial_mode=formatting.editorial_mode,
            own_process_group=not supervised,
        )
    else:
        body = (
            render_chapter_text(cleaned.effective_sections)
            if cleaned.metadata.chapters
            else render_timed_text(
                projection.fragments, source_indices=projection.source_indices
            )
        )
    return {
        "format": output_format,
        "document": body,
        "metadata": cleaned.mapping(effective=True),
        "character_count": len(body),
    }
