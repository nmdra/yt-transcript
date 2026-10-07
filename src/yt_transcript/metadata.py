"""Python-owned video metadata and deterministic YAML serialization."""

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .errors import ErrorInfo, TranscriptError


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


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def extract_video_metadata(
    info: Mapping[str, Any], *, canonical_url: str
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
    return VideoMetadata(
        canonical_url,
        video_id,
        _string(info.get("title")),
        _string(info.get("channel")) or _string(info.get("uploader")),
        _string(info.get("channel_id")),
        _string(info.get("channel_url")) or _string(info.get("uploader_url")),
        date,
        duration,
    )


def metadata_mapping(
    metadata: VideoMetadata, *, language: str, automatic: bool
) -> dict[str, Any]:
    return {
        **asdict(metadata),
        "caption_language": language,
        "caption_source": "automatic" if automatic else "manual",
    }


def format_transcript_file(
    metadata: VideoMetadata, body: str, *, language: str, automatic: bool
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
        metadata_mapping(metadata, language=language, automatic=automatic),
        Dumper=QuotedDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    return f"---\n{header}---\n\n{body.rstrip()}\n"
