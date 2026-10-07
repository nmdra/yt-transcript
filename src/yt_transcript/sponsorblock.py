"""Bounded read-only SponsorBlock lookup and conservative caption projections."""

import hashlib
import http.client
import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, TypedDict
from urllib.parse import urlencode

from .chapters import milliseconds
from .cleaner import Cue

CATEGORIES = ("sponsor", "selfpromo", "interaction", "intro", "outro", "preview")
WARNING = "warning[SPONSORBLOCK_UNAVAILABLE]: SponsorBlock filtering was not applied; source captions were kept."
SOURCE = "SponsorBlock community data (https://sponsor.ajay.app)"
LICENSE = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
CHANGES = "Selected and time-normalized segment records; caption removal is reported separately."
BODY_LIMIT = 512 * 1024
Status = Literal["disabled", "available", "not_found", "lookup_failed"]
Reason = Literal[
    "LOOKUP_FAILED",
    "RESPONSE_TOO_LARGE",
    "INVALID_RESPONSE",
    "ALIGNMENT_UNVERIFIED",
    "REMOVAL_WOULD_EMPTY",
]
RemovalStatus = Literal[
    "removed", "partial", "kept", "no_matching_captions", "not_applied"
]


@dataclass(frozen=True)
class SponsorBlockConfig:
    enabled: bool | None = None
    categories: tuple[str, ...] = ("sponsor", "selfpromo", "interaction")
    timeout_seconds: int = 10

    def resolved(self, *, default: bool = False) -> SponsorBlockConfig:
        return replace(self, enabled=default if self.enabled is None else self.enabled)


@dataclass(frozen=True)
class SponsorBlockSegment:
    start_ms: int
    end_ms: int
    category: str
    votes: int
    locked: bool


@dataclass(frozen=True)
class SponsorBlockLookup:
    enabled: bool = False
    status: Status = "disabled"
    categories: tuple[str, ...] = ("sponsor", "selfpromo", "interaction")
    segments: tuple[SponsorBlockSegment, ...] = ()
    reason_code: Reason | None = None

    @property
    def warning(self) -> str | None:
        return WARNING if self.status == "lookup_failed" else None


class SegmentResult(TypedDict):
    category: str
    start_seconds: int | float
    end_seconds: int | float
    votes: int
    locked: bool
    removal_status: RemovalStatus
    removed_cue_count: int
    retained_overlap_cue_count: int


class SponsorBlockResult(TypedDict):
    enabled: bool
    status: Status
    categories: list[str]
    segments: list[SegmentResult]
    warning: (
        Literal[
            "warning[SPONSORBLOCK_UNAVAILABLE]: SponsorBlock filtering was not applied; source captions were kept."
        ]
        | None
    )
    reason_code: Reason | None
    source: Literal["SponsorBlock community data (https://sponsor.ajay.app)"] | None
    license_url: Literal["https://creativecommons.org/licenses/by-nc-sa/4.0/"] | None
    changes: (
        Literal[
            "Selected and time-normalized segment records; caption removal is reported separately."
        ]
        | None
    )
    removal_applied: bool
    removal_stage: Literal["source_filter", "none"]
    removed_cue_count: int
    retained_overlap_cue_count: int


@dataclass(frozen=True)
class SegmentRemovalReceipt:
    removal_status: RemovalStatus
    removed_cue_count: int = 0
    retained_overlap_cue_count: int = 0


@dataclass(frozen=True)
class SponsorBlockRemovalReceipt:
    segments: tuple[SegmentRemovalReceipt, ...] = ()
    removed_cue_count: int = 0
    retained_overlap_cue_count: int = 0


def sponsorblock_mapping(
    lookup: SponsorBlockLookup, receipt: SponsorBlockRemovalReceipt | None = None
) -> SponsorBlockResult:
    if receipt is None:
        if lookup.segments:
            raise ValueError("A computed removal receipt is required.")
        receipt = SponsorBlockRemovalReceipt()
    if len(receipt.segments) != len(lookup.segments):
        raise ValueError("Invalid removal receipt.")
    return {
        "enabled": lookup.enabled,
        "status": lookup.status,
        "categories": list(lookup.categories),
        "segments": [
            {
                "category": row.category,
                "start_seconds": row.start_ms / 1000,
                "end_seconds": row.end_ms / 1000,
                "votes": row.votes,
                "locked": row.locked,
                "removal_status": removal.removal_status,
                "removed_cue_count": removal.removed_cue_count,
                "retained_overlap_cue_count": removal.retained_overlap_cue_count,
            }
            for row, removal in zip(lookup.segments, receipt.segments, strict=True)
        ],
        "warning": WARNING if lookup.warning else None,
        "reason_code": lookup.reason_code,
        "source": SOURCE if lookup.segments else None,
        "license_url": LICENSE if lookup.segments else None,
        "changes": CHANGES if lookup.segments else None,
        "removal_applied": receipt.removed_cue_count > 0,
        "removal_stage": "source_filter" if receipt.removed_cue_count else "none",
        "removed_cue_count": receipt.removed_cue_count,
        "retained_overlap_cue_count": receipt.retained_overlap_cue_count,
    }


class LookupFailure(ValueError):
    def __init__(self, reason: Reason):
        self.reason = reason


def validate_policy(value: object) -> SponsorBlockConfig:
    if not isinstance(value, dict) or set(value) != {
        "enabled",
        "categories",
        "timeout_seconds",
    }:
        raise ValueError
    enabled, categories, timeout = (
        value["enabled"],
        value["categories"],
        value["timeout_seconds"],
    )
    if type(enabled) is not bool or type(timeout) is not int or not 1 <= timeout <= 30:
        raise ValueError
    if (
        not isinstance(categories, list)
        or not categories
        or any(not isinstance(c, str) or c not in CATEGORIES for c in categories)
        or len(set(categories)) != len(categories)
    ):
        raise ValueError
    return SponsorBlockConfig(enabled, tuple(categories), timeout)


def _transport(path: str, timeout: int) -> tuple[int, bytes]:
    connection = http.client.HTTPSConnection(
        "sponsor.ajay.app", timeout=timeout, context=ssl.create_default_context()
    )
    try:
        connection.request(
            "GET",
            path,
            headers={"User-Agent": "yt-transcript/0.1", "Accept": "application/json"},
        )
        response = connection.getresponse()
        return response.status, response.read(BODY_LIMIT + 1)
    finally:
        connection.close()


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _json_constant(value: str) -> object:
    raise ValueError


def lookup_sponsorblock(
    video_id: str,
    *,
    config: SponsorBlockConfig,
    duration_seconds: int | float | None,
    transport: Callable[[str, int], tuple[int, bytes]] | None = None,
) -> SponsorBlockLookup:
    base = SponsorBlockLookup(
        enabled=bool(config.enabled), categories=config.categories
    )
    if not config.enabled:
        return base
    try:
        if duration_seconds is None or duration_seconds <= 0:
            raise LookupFailure("ALIGNMENT_UNVERIFIED")
        try:
            duration = milliseconds(duration_seconds)
        except ValueError, OverflowError:
            raise LookupFailure("ALIGNMENT_UNVERIFIED") from None
        prefix = hashlib.sha256(video_id.encode("ascii")).hexdigest()[:4]
        path = (
            "/api/skipSegments/"
            + prefix
            + "?"
            + urlencode(
                {
                    "categories": json.dumps(list(config.categories)),
                    "actionTypes": '["skip"]',
                    "service": "YouTube",
                }
            )
        )
        status, body = (transport or _transport)(path, config.timeout_seconds)
        if status == 404:
            return replace(base, status="not_found")
        if status != 200:
            raise LookupFailure("LOOKUP_FAILED")
        if len(body) > BODY_LIMIT:
            raise LookupFailure("RESPONSE_TOO_LARGE")
        buckets = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_json_constant,
        )
        if not isinstance(buckets, list):
            raise ValueError
        if len(buckets) > 512:
            raise LookupFailure("RESPONSE_TOO_LARGE")
        if any(
            not isinstance(bucket, dict) or not isinstance(bucket.get("videoID"), str)
            for bucket in buckets
        ):
            raise ValueError
        matching = [
            row
            for row in buckets
            if isinstance(row, dict) and row.get("videoID") == video_id
        ]
        if not matching:
            return replace(base, status="not_found")
        if len(matching) != 1:
            raise ValueError
        rows = matching[0].get("segments")
        if not isinstance(rows, list):
            raise ValueError
        if len(rows) > 256:
            raise LookupFailure("RESPONSE_TOO_LARGE")
        accepted = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError
            if (
                row.get("actionType") != "skip"
                or row.get("category") not in config.categories
            ):
                continue
            votes = row.get("votes")
            if type(votes) is not int:
                raise ValueError
            if votes < 0:
                continue
            locked = row.get("locked")
            if type(locked) is not bool and (
                type(locked) is not int or locked not in (0, 1)
            ):
                raise ValueError
            interval = row.get("segment")
            if not isinstance(interval, list) or len(interval) != 2:
                raise ValueError
            start, end = map(milliseconds, interval)
            if not 0 <= start < end <= duration:
                raise ValueError
            submitted = row.get("videoDuration")
            if (
                not isinstance(submitted, (int, float))
                or isinstance(submitted, bool)
                or submitted <= 0
            ):
                raise LookupFailure("ALIGNMENT_UNVERIFIED")
            try:
                submitted_ms = milliseconds(submitted)
            except ValueError, OverflowError:
                raise LookupFailure("ALIGNMENT_UNVERIFIED") from None
            if abs(submitted_ms - duration) > 1000:
                raise LookupFailure("ALIGNMENT_UNVERIFIED")
            accepted.append(
                SponsorBlockSegment(start, end, row["category"], votes, bool(locked))
            )
        return replace(
            base,
            status="available" if accepted else "not_found",
            segments=tuple(
                sorted(
                    accepted,
                    key=lambda s: (s.start_ms, s.end_ms, s.category, s.votes, s.locked),
                )
            ),
        )
    except LookupFailure as exc:
        return replace(base, status="lookup_failed", reason_code=exc.reason)
    except ValueError, TypeError, OverflowError, UnicodeError, RecursionError:
        return replace(base, status="lookup_failed", reason_code="INVALID_RESPONSE")
    except OSError, http.client.HTTPException:
        return replace(base, status="lookup_failed", reason_code="LOOKUP_FAILED")


def _overlaps(cue: Cue, segment: SponsorBlockSegment) -> bool:
    if cue.start_ms == cue.end_ms:
        return segment.start_ms <= cue.start_ms < segment.end_ms
    return cue.start_ms < segment.end_ms and cue.end_ms > segment.start_ms


def compute_receipt(
    fragments: tuple[Cue, ...],
    lookup: SponsorBlockLookup,
    *,
    removed_indices: tuple[int, ...] = (),
    selected: bool = False,
) -> SponsorBlockRemovalReceipt:
    removed = set(removed_indices)
    overlapping: set[int] = set()
    receipts = []
    for segment in lookup.segments:
        matching = {i for i, cue in enumerate(fragments) if _overlaps(cue, segment)}
        overlapping.update(matching)
        dropped, kept = len(matching & removed), len(matching - removed)
        status: RemovalStatus = (
            "not_applied"
            if not selected
            else "partial"
            if dropped and kept
            else "removed"
            if dropped
            else "kept"
            if kept
            else "no_matching_captions"
        )
        receipts.append(SegmentRemovalReceipt(status, dropped, kept))
    return SponsorBlockRemovalReceipt(
        tuple(receipts), len(removed), len(overlapping - removed)
    )


@dataclass(frozen=True)
class AnnotatedCue(Cue):
    sponsorblock_overlaps: tuple[SponsorBlockSegment, ...] = ()


@dataclass(frozen=True)
class CaptionProjection:
    fragments: tuple[Cue, ...]
    source_indices: tuple[int, ...]
    removed_indices: tuple[int, ...]
    lookup: SponsorBlockLookup
    receipt: SponsorBlockRemovalReceipt

    @property
    def body(self) -> str:
        return " ".join(c.text for c in self.fragments)


def project_sponsorblock(
    fragments: tuple[Cue, ...], lookup: SponsorBlockLookup
) -> CaptionProjection:
    mask: list[tuple[int, int]] = []
    for segment in sorted(lookup.segments, key=lambda s: (s.start_ms, s.end_ms)):
        if mask and segment.start_ms <= mask[-1][1]:
            mask[-1] = (mask[-1][0], max(mask[-1][1], segment.end_ms))
        else:
            mask.append((segment.start_ms, segment.end_ms))
    selected = lookup.status == "available"
    removed = tuple(
        i
        for i, cue in enumerate(fragments)
        if selected
        and cue.end_ms > cue.start_ms
        and any(start <= cue.start_ms and cue.end_ms <= end for start, end in mask)
    )
    if fragments and len(removed) == len(fragments):
        removed = ()
        selected = False
        lookup = replace(
            lookup, status="lookup_failed", reason_code="REMOVAL_WOULD_EMPTY"
        )
    indices = tuple(i for i in range(len(fragments)) if i not in removed)
    kept = tuple(
        AnnotatedCue(
            cue.start_ms,
            cue.end_ms,
            cue.text,
            tuple(
                s
                for s in lookup.segments
                if _overlaps(cue, s)
                and not (s.start_ms <= cue.start_ms < cue.end_ms <= s.end_ms)
            ),
        )
        for i, cue in enumerate(fragments)
        if i not in removed
    )
    return CaptionProjection(
        kept,
        indices,
        removed,
        lookup,
        compute_receipt(fragments, lookup, removed_indices=removed, selected=selected),
    )
