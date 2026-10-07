"""Python-owned video metadata and deterministic YAML serialization."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .chapters import Chapter, ChapterStatus, normalize_chapters
from .errors import ErrorInfo, TranscriptError
from .sponsorblock import (
    SponsorBlockLookup,
    SponsorBlockRemovalReceipt,
    sponsorblock_mapping,
)


@dataclass(frozen=True)
class VideoMetadata:
    url: str
    video_id: str
    title: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    channel_url: str | None = None
    upload_date: str | None = None
    duration_seconds: int | float | None = None
    chapters: tuple[Chapter, ...] = ()
    chapter_status: ChapterStatus = "unavailable"
    sponsorblock: SponsorBlockLookup = SponsorBlockLookup()


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def extract_video_metadata(
    info: Mapping[str, Any], *, canonical_url: str, chapter_input: object = None
) -> VideoMetadata:
    video_id = canonical_url.rsplit("=", 1)[1]
    if info.get("id") != video_id:
        raise TranscriptError(
            ErrorInfo(
                "YOUTUBE_EXTRACT_FAILED",
                "Extracted video ID does not match the requested video.",
                phase="metadata_extract",
            )
        )
    date = None
    if info.get("upload_date") is not None:
        raw = info["upload_date"]
        if isinstance(raw, str) and len(raw) == 8 and raw.isdigit():
            try:
                date = datetime.strptime(raw, "%Y%m%d").date().isoformat()
            except ValueError:
                pass
    else:
        timestamp = info.get("timestamp")
        if (
            isinstance(timestamp, (int, float))
            and not isinstance(timestamp, bool)
            and (isinstance(timestamp, int) or math.isfinite(timestamp))
        ):
            try:
                date = datetime.fromtimestamp(timestamp, UTC).date().isoformat()
            except ValueError, OverflowError, OSError:
                pass
    duration = info.get("duration")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or (isinstance(duration, float) and not math.isfinite(duration))
        or duration < 0
    ):
        duration = None
    extracted = normalize_chapters(chapter_input, duration_seconds=duration)
    return VideoMetadata(
        canonical_url,
        video_id,
        _string(info.get("title")),
        _string(info.get("channel")) or _string(info.get("uploader")),
        _string(info.get("channel_id")),
        _string(info.get("channel_url")) or _string(info.get("uploader_url")),
        date,
        duration,
        extracted.chapters,
        extracted.status,
    )


def metadata_mapping(
    metadata: VideoMetadata,
    *,
    language: str,
    automatic: bool,
    sponsorblock_result: SponsorBlockLookup | None = None,
    removal_receipt: SponsorBlockRemovalReceipt | None = None,
) -> dict[str, Any]:
    return {
        **{
            key: getattr(metadata, key)
            for key in (
                "url",
                "video_id",
                "title",
                "channel",
                "channel_id",
                "channel_url",
                "upload_date",
                "duration_seconds",
            )
        },
        "caption_language": language,
        "caption_source": "automatic" if automatic else "manual",
        "chapter_status": metadata.chapter_status,
        "chapters": [
            {
                "title": c.title,
                "start_seconds": c.start_ms / 1000,
                "end_seconds": c.end_ms / 1000 if c.end_ms is not None else None,
            }
            for c in metadata.chapters
        ],
        "sponsorblock": sponsorblock_mapping(
            sponsorblock_result or metadata.sponsorblock, removal_receipt
        ),
    }


def format_transcript_file(
    metadata: VideoMetadata,
    body: str,
    *,
    language: str,
    automatic: bool,
    sponsorblock_result: SponsorBlockLookup | None = None,
    removal_receipt: SponsorBlockRemovalReceipt | None = None,
) -> str:
    import yaml

    class QuotedDumper(yaml.SafeDumper):
        pass

    QuotedDumper.add_representer(
        str,
        lambda dumper, value: dumper.represent_scalar(
            "tag:yaml.org,2002:str", value, style='"'
        ),
    )
    header = yaml.dump(
        metadata_mapping(
            metadata,
            language=language,
            automatic=automatic,
            sponsorblock_result=sponsorblock_result,
            removal_receipt=removal_receipt,
        ),
        Dumper=QuotedDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    return f"---\n{header}---\n\n{body.rstrip()}\n"
