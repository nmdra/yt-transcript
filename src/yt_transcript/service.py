"""SDK-independent transcript services shared by CLI and MCP."""

import base64
import binascii
import json
import math
import os
import re
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from types import UnionType
from typing import (
    TYPE_CHECKING,
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
    display_time,
    milliseconds,
    render_chapter_text,
    render_timed_text,
)
from .cleaner import Cue, clean_vtt_timed
from .config import OpenRouterConfig
from .downloader import download_english_vtt, validate_youtube_url
from .errors import ErrorInfo, TranscriptError
from .json_tools import strict_json_loads
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

if TYPE_CHECKING:
    from .transcript_cache import TranscriptCache


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
    description: str | None


class TranscriptResult(TypedDict):
    format: TranscriptFormat
    document: str
    metadata: MetadataResult
    character_count: int


class VideoInfoResult(TypedDict):
    metadata: MetadataResult


class SegmentCueResult(TypedDict):
    start_seconds: int | float
    end_seconds: int | float
    text: str
    url: str


class SegmentResult(TypedDict):
    video_id: str
    mode: TranscriptMode
    cues: list[SegmentCueResult]


class SearchMatchResult(TypedDict):
    start_seconds: int | float
    end_seconds: int | float
    text: str
    context: str
    url: str


class SearchResult(TypedDict):
    video_id: str
    query: str
    matches: list[SearchMatchResult]


class PageResult(TypedDict):
    video_id: str
    document: str
    has_more: bool
    next_cursor: str | None


class CursorPayload(TypedDict):
    v: int
    cache_key: str
    snapshot_id: str
    next_index: int


def validate_service_result(operation: str, value: object) -> None:
    """Reject malformed worker results before SDK conversion can log their contents."""
    expected = {
        "get_transcript": TranscriptResult,
        "get_video_info": VideoInfoResult,
        "get_transcript_segment": SegmentResult,
        "search_transcript": SearchResult,
        "get_transcript_page": PageResult,
    }.get(operation)
    if expected is None:
        raise TranscriptError(
            ErrorInfo("INTERNAL_ERROR", "Worker operation failed.", phase="mcp_worker")
        )

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
                    and (
                        item["end_seconds"] < item["start_seconds"]
                        or (
                            annotation not in (SegmentCueResult, SearchMatchResult)
                            and item["end_seconds"] == item["start_seconds"]
                        )
                    )
                )
            ):
                return False
            if annotation in (SegmentCueResult, SearchMatchResult):
                if not item["text"].strip() or item["url"] != _cue_url_from_seconds(
                    item["url"].split("?v=")[-1].split("&")[0], item["start_seconds"]
                ):
                    return False
                if annotation is SearchMatchResult and len(item["context"]) > 500:
                    return False
            if annotation is MetadataResult:
                try:
                    canonical = validate_youtube_url(item["url"])
                except TranscriptError, TypeError:
                    return False
                if canonical.rsplit("=", 1)[-1] != item["video_id"]:
                    return False
                if (
                    item["duration_seconds"] is not None
                    and item["duration_seconds"] < 0
                ):
                    return False
            if "video_id" in item and not re.fullmatch(
                r"[A-Za-z0-9_-]{11}", item["video_id"]
            ):
                return False
            if annotation is TranscriptResult and item["character_count"] != len(
                item["document"]
            ):
                return False
            if annotation is SegmentResult:
                if len(item["cues"]) > 200 or any(
                    cue["url"]
                    != _cue_url_from_seconds(item["video_id"], cue["start_seconds"])
                    for cue in item["cues"]
                ):
                    return False
            if annotation is SearchResult:
                if (
                    not item["query"]
                    or len(item["query"]) > 600
                    or " ".join(item["query"].split()).casefold() != item["query"]
                ):
                    return False
                if len(item["matches"]) > 20 or any(
                    match["url"]
                    != _cue_url_from_seconds(item["video_id"], match["start_seconds"])
                    for match in item["matches"]
                ):
                    return False
            if annotation is PageResult:
                if (
                    not item["document"]
                    or len(item["document"]) > 20000
                    or item["has_more"] != (item["next_cursor"] is not None)
                ):
                    return False
                try:
                    cursor = validate_page_request(item["next_cursor"], 12000)
                    if cursor is not None and cursor["next_index"] == 0:
                        return False
                except TranscriptError:
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
    cache: TranscriptCache | None = None,
    on_progress: Callable[[int, int], None] | None = None,
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
        from .formatter import ensure_formatter

        formatting = validate_formatting_policy(
            asdict(formatting or MCPFormattingPolicy())
        )
        ensure_formatter(formatting.provider, formatting.model)
    cleaned = get_cached_snapshot(url, mode, sponsorblock=sponsorblock, cache=cache)
    projection = cleaned.projection
    assert projection is not None
    if output_format == "markdown":
        from .formatter import format_transcript

        assert formatting is not None
        progress_kwargs: dict[str, Any] = (
            {"on_progress": on_progress} if on_progress is not None else {}
        )
        body = format_transcript(
            cleaned.effective_body,
            sections=cleaned.effective_sections,
            model=formatting.model,
            provider=formatting.provider,
            openrouter=OpenRouterConfig(formatting.openrouter_max_output_tokens),
            chunk_chars=formatting.chunk_chars,
            summary_synthesis_chars=formatting.summary_synthesis_chars,
            timeout_seconds=formatting.timeout_seconds,
            max_chunks=formatting.max_chunks,
            editorial_mode=formatting.editorial_mode,
            own_process_group=not supervised,
            **progress_kwargs,
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


_RETRIEVAL_ERRORS = {
    "SEGMENT_RANGE_INVALID": "Invalid transcript segment range.",
    "SEARCH_QUERY_INVALID": "Invalid transcript search query.",
    "CACHE_CURSOR_INVALID": "Invalid transcript page cursor.",
    "CACHE_CURSOR_EXPIRED": "Transcript page snapshot is no longer available.",
    "CACHE_UNAVAILABLE": "Transcript paging requires available snapshot storage.",
    "CONFIG_INVALID": "Invalid transcript page size.",
    "MCP_RESPONSE_LIMIT": "Result exceeds the MCP size limit.",
}


def _retrieval_error(code: str) -> TranscriptError:
    return TranscriptError(ErrorInfo(code, _RETRIEVAL_ERRORS[code], phase="mcp_worker"))


def _resolved_policy(
    mode: TranscriptMode, sponsorblock: SponsorBlockConfig | None
) -> SponsorBlockConfig:
    if mode not in ("filtered", "full"):
        raise ValueError("Invalid transcript mode.")
    policy = (sponsorblock or SponsorBlockConfig()).resolved(default=True)
    return replace(policy, enabled=False) if mode == "full" else policy


def _cacheable(cleaned: CleanedTranscript, policy: SponsorBlockConfig) -> bool:
    lookup = (
        cleaned.projection.lookup
        if cleaned.projection
        else cleaned.metadata.sponsorblock
    )
    return not (policy.enabled and lookup.status == "lookup_failed")


def _matches_snapshot(
    cleaned: CleanedTranscript, canonical: str, policy: SponsorBlockConfig
) -> bool:
    lookup = cleaned.metadata.sponsorblock
    return (
        cleaned.metadata.url == canonical
        and cleaned.metadata.video_id == canonical.rsplit("=", 1)[-1]
        and lookup.enabled == policy.enabled
        and sorted(lookup.categories) == sorted(policy.categories)
        and _cacheable(cleaned, policy)
    )


def get_cached_snapshot(
    url: str,
    mode: TranscriptMode = "filtered",
    *,
    sponsorblock: SponsorBlockConfig | None = None,
    cache: TranscriptCache | None = None,
) -> CleanedTranscript:
    """Reuse captions only when a cache is explicitly supplied by MCP dispatch."""
    canonical = validate_youtube_url(url)
    policy = _resolved_policy(mode, sponsorblock)
    key = None
    if cache is not None:
        from .transcript_cache import make_cache_key

        key = make_cache_key(canonical, mode, policy)
        try:
            cached = cache.get(key)
        except Exception:
            cached = None
        if cached is not None and _matches_snapshot(cached, canonical, policy):
            return cached
    cleaned = fetch_clean_transcript(canonical, sponsorblock=policy)
    if cache is not None and key is not None and _cacheable(cleaned, policy):
        try:
            cache.put(key, cleaned)
        except Exception:
            pass
    return cleaned


def _effective_cues(
    cleaned: CleanedTranscript,
) -> tuple[tuple[Cue, ...], tuple[int, ...]]:
    if cleaned.projection is not None:
        return cleaned.projection.fragments, cleaned.projection.source_indices
    return cleaned.fragments, tuple(range(len(cleaned.fragments)))


def _cue_url_from_seconds(video_id: str, start_seconds: int | float) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&t={math.floor(start_seconds)}s"


def _cue_url(video_id: str, cue: Cue) -> str:
    return _cue_url_from_seconds(video_id, cue.start_ms / 1000)


def _checked_result(operation: str, result: Any) -> Any:
    validate_service_result(operation, result)
    # The public SDK returns both structured content and a compatibility JSON copy.
    encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
    if len(encoded) * 2 > 1024 * 1024:
        raise _retrieval_error("MCP_RESPONSE_LIMIT")
    if "document" in result and len(result["document"].encode("utf-8")) > 256 * 1024:
        raise _retrieval_error("MCP_RESPONSE_LIMIT")
    return result


def get_video_info(
    url: str,
    *,
    sponsorblock: SponsorBlockConfig | None = None,
    cache: TranscriptCache | None = None,
) -> VideoInfoResult:
    cleaned = get_cached_snapshot(url, sponsorblock=sponsorblock, cache=cache)
    return _checked_result(
        "get_video_info", {"metadata": cleaned.mapping(effective=True)}
    )


def validate_segment_range(
    start_seconds: object, end_seconds: object
) -> tuple[int, int]:
    try:
        start, end = milliseconds(start_seconds), milliseconds(end_seconds)
        if not isinstance(start_seconds, (int, float)) or not isinstance(
            end_seconds, (int, float)
        ):
            raise ValueError
        if (
            not 0 <= start_seconds < end_seconds
            or end_seconds - start_seconds > 900
            or end <= start
        ):
            raise ValueError
    except ValueError, OverflowError:
        raise _retrieval_error("SEGMENT_RANGE_INVALID") from None
    return start, end


def get_transcript_segment(
    url: str,
    start_seconds: int | float,
    end_seconds: int | float,
    mode: TranscriptMode = "filtered",
    *,
    sponsorblock: SponsorBlockConfig | None = None,
    cache: TranscriptCache | None = None,
) -> SegmentResult:
    start, end = validate_segment_range(start_seconds, end_seconds)
    cleaned = get_cached_snapshot(url, mode, sponsorblock=sponsorblock, cache=cache)
    fragments, _ = _effective_cues(cleaned)
    selected = [
        cue
        for cue in fragments
        if (cue.start_ms < end and cue.end_ms > start)
        or (cue.start_ms == cue.end_ms and start <= cue.start_ms < end)
    ]
    if len(selected) > 200:
        raise _retrieval_error("MCP_RESPONSE_LIMIT")
    video_id = cleaned.metadata.video_id
    cues: list[SegmentCueResult] = [
        {
            "start_seconds": cue.start_ms / 1000,
            "end_seconds": cue.end_ms / 1000,
            "text": cue.text,
            "url": _cue_url(video_id, cue),
        }
        for cue in selected
    ]
    return _checked_result(
        "get_transcript_segment", {"video_id": video_id, "mode": mode, "cues": cues}
    )


def validate_search_query(query: object, max_results: object) -> str:
    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query) > 200
        or type(max_results) is not int
        or not 1 <= max_results <= 20
    ):
        raise _retrieval_error("SEARCH_QUERY_INVALID")
    return " ".join(query.split()).casefold()


def search_transcript(
    url: str,
    query: str,
    mode: TranscriptMode = "filtered",
    max_results: int = 10,
    *,
    sponsorblock: SponsorBlockConfig | None = None,
    cache: TranscriptCache | None = None,
) -> SearchResult:
    normalized = validate_search_query(query, max_results)
    cleaned = get_cached_snapshot(url, mode, sponsorblock=sponsorblock, cache=cache)
    fragments, indices = _effective_cues(cleaned)
    runs: list[list[tuple[Cue, int]]] = []
    for cue, index in zip(fragments, indices, strict=True):
        if not runs or index != runs[-1][-1][1] + 1:
            runs.append([])
        runs[-1].append((cue, index))
    candidates: list[tuple[int, int, SearchMatchResult]] = []
    video_id = cleaned.metadata.video_id
    for run in runs:
        parts = [" ".join(cue.text.split()).casefold() for cue, _ in run]
        text = " ".join(parts)
        spans = []
        offset = 0
        for part in parts:
            spans.append((offset, offset + len(part)))
            offset += len(part) + 1
        starts = [start for start, _ in spans]
        ends = [end for _, end in spans]
        offset = 0
        previous_range = None
        while (found := text.find(normalized, offset)) >= 0:
            offset = found + len(normalized)
            first = bisect_right(ends, found)
            last = bisect_left(starts, offset) - 1
            if first > last or (first, last) == previous_range:
                continue
            previous_range = (first, last)
            cues = [cue for cue, _ in run[first : last + 1]]
            start_ms, end_ms = (
                min(c.start_ms for c in cues),
                max(c.end_ms for c in cues),
            )
            match: SearchMatchResult = {
                "start_seconds": start_ms / 1000,
                "end_seconds": end_ms / 1000,
                "text": " ".join(c.text for c in cues),
                "context": " ".join(
                    c.text for c, _ in run[max(0, first - 1) : last + 2]
                )[:500],
                "url": _cue_url_from_seconds(video_id, start_ms / 1000),
            }
            candidates.append((start_ms, run[first][1], match))
            candidates.sort(key=lambda item: (item[0], item[1]))
            del candidates[max_results:]
    return _checked_result(
        "search_transcript",
        {
            "video_id": video_id,
            "query": normalized,
            "matches": [item[2] for item in candidates[:max_results]],
        },
    )


def validate_page_request(cursor: object, max_chars: object) -> CursorPayload | None:
    if type(max_chars) is not int or not 1000 <= max_chars <= 20000:
        raise _retrieval_error("CONFIG_INVALID")
    if cursor is None:
        return None
    try:
        if (
            not isinstance(cursor, str)
            or not cursor
            or len(cursor) > 2048
            or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor)
        ):
            raise ValueError
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
        )
        if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != cursor:
            raise ValueError
        payload = strict_json_loads(raw.decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or set(payload) != {"v", "cache_key", "snapshot_id", "next_index"}
            or type(payload["v"]) is not int
            or payload["v"] != 1
            or type(payload["next_index"]) is not int
            or not 0 <= payload["next_index"] <= 2**63 - 1
            or any(
                not isinstance(payload[k], str)
                or not re.fullmatch(r"[0-9a-f]{64}", payload[k])
                for k in ("cache_key", "snapshot_id")
            )
        ):
            raise ValueError
    except ValueError, UnicodeError, binascii.Error:
        raise _retrieval_error("CACHE_CURSOR_INVALID") from None
    return cast(CursorPayload, payload)


def _encode_cursor(key: str, identity: str, next_index: int) -> str:
    payload: CursorPayload = {
        "v": 1,
        "cache_key": key,
        "snapshot_id": identity,
        "next_index": next_index,
    }
    return (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def get_transcript_page(
    url: str,
    cursor: str | None = None,
    max_chars: int = 12000,
    mode: TranscriptMode = "filtered",
    *,
    sponsorblock: SponsorBlockConfig | None = None,
    cache: TranscriptCache | None = None,
) -> PageResult:
    payload = validate_page_request(cursor, max_chars)
    canonical = validate_youtube_url(url)
    policy = _resolved_policy(mode, sponsorblock)
    from .transcript_cache import make_cache_key, snapshot_id

    key = make_cache_key(canonical, mode, policy)
    if payload is not None and payload["cache_key"] != key:
        raise _retrieval_error("CACHE_CURSOR_INVALID")
    if cache is None:
        raise _retrieval_error(
            "CACHE_CURSOR_EXPIRED" if payload else "CACHE_UNAVAILABLE"
        )
    if payload is not None:
        try:
            cleaned = cache.get_exact(key, payload["snapshot_id"])
        except Exception:
            cleaned = None
        if cleaned is None or not _matches_snapshot(cleaned, canonical, policy):
            raise _retrieval_error("CACHE_CURSOR_EXPIRED")
        identity, index = payload["snapshot_id"], payload["next_index"]
    else:
        if not cache.enabled:
            raise _retrieval_error("CACHE_UNAVAILABLE")
        cleaned = get_cached_snapshot(canonical, mode, sponsorblock=policy, cache=cache)
        if not _cacheable(cleaned, policy):
            raise _retrieval_error("CACHE_UNAVAILABLE")
        try:
            identity = snapshot_id(cleaned)
            retained = cache.get_exact(key, identity)
        except Exception:
            retained = None
        if retained is None or not _matches_snapshot(retained, canonical, policy):
            raise _retrieval_error("CACHE_UNAVAILABLE")
        cleaned, index = retained, 0
    fragments, _ = _effective_cues(cleaned)
    if not 0 <= index < len(fragments):
        raise _retrieval_error(
            "CACHE_CURSOR_INVALID" if payload else "CACHE_UNAVAILABLE"
        )
    lines: list[str] = []
    count = 0
    while index < len(fragments):
        cue = fragments[index]
        line = f"[{display_time(cue.start_ms)} - {display_time(cue.end_ms)}] {cue.text}"
        added = len(line) + bool(lines)
        if count + added > max_chars:
            if not lines:
                raise _retrieval_error("MCP_RESPONSE_LIMIT")
            break
        lines.append(line)
        count += added
        index += 1
    has_more = index < len(fragments)
    return _checked_result(
        "get_transcript_page",
        {
            "video_id": cleaned.metadata.video_id,
            "document": "\n".join(lines),
            "has_more": has_more,
            "next_cursor": _encode_cursor(key, identity, index) if has_more else None,
        },
    )
