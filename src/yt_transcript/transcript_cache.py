"""Private, fail-open SQLite storage for versioned source-caption snapshots."""

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .chapters import Chapter, build_chapter_sections, milliseconds, normalize_chapters
from .cleaner import Cue
from .downloader import validate_youtube_url
from .errors import TranscriptError
from .json_tools import strict_json_loads
from .metadata import VideoMetadata
from .sponsorblock import (
    CATEGORIES,
    Reason,
    SponsorBlockConfig,
    SponsorBlockLookup,
    SponsorBlockSegment,
    Status,
    compute_receipt,
    project_sponsorblock,
    validate_policy,
)

if TYPE_CHECKING:
    from .service import CleanedTranscript, TranscriptMode

VERSION = 1
PAYLOAD_LIMIT = 5 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_FAULTS = (
    OSError,
    sqlite3.Error,
    ValueError,
    TypeError,
    OverflowError,
    UnicodeError,
    RecursionError,
    TranscriptError,
)


def _json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def make_cache_key(
    canonical_url: str, mode: TranscriptMode, policy: SponsorBlockConfig
) -> str:
    """Hash the canonical video identity and resolved processing policy."""
    url = validate_youtube_url(canonical_url)
    if mode not in ("filtered", "full"):
        raise ValueError("Invalid mode.")
    resolved = policy.resolved(default=True)
    if mode == "full":
        resolved = SponsorBlockConfig(
            False, resolved.categories, resolved.timeout_seconds
        )
    validate_policy(asdict(resolved) | {"categories": list(resolved.categories)})
    return hashlib.sha256(
        _json(
            {
                "v": VERSION,
                "video_id": url.rsplit("=", 1)[1],
                "mode": mode,
                "enabled": resolved.enabled,
                "categories": sorted(resolved.categories),
                "timeout_seconds": resolved.timeout_seconds,
                "caption_selection": "english-v1",
            }
        )
    ).hexdigest()


def _payload(cleaned: CleanedTranscript) -> bytes:
    return _json(
        {
            "v": VERSION,
            "metadata": asdict(cleaned.metadata),
            "language": cleaned.language,
            "automatic": cleaned.automatic,
            "fragments": [
                {"start_ms": c.start_ms, "end_ms": c.end_ms, "text": c.text}
                for c in cleaned.fragments
            ],
        }
    )


def snapshot_id(cleaned: CleanedTranscript) -> str:
    """Return the deterministic source payload hash, independent of access time."""
    return hashlib.sha256(_payload(cleaned)).hexdigest()


def _fields(value: Any, names: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError
    return value


def _ms(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValueError
    return value


def _string(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError
    return value


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError
    return value


def _restore(payload: bytes) -> CleanedTranscript:
    from .service import CleanedTranscript, validate_service_result

    if len(payload) > PAYLOAD_LIMIT:
        raise ValueError
    try:
        decoded = strict_json_loads(payload.decode("utf-8"))
    except UnicodeError, RecursionError, ValueError:
        raise ValueError from None
    data = _fields(decoded, "v metadata language automatic fragments")
    if type(data["v"]) is not int or data["v"] != VERSION:
        raise ValueError
    language = _string(data["language"])
    if language != "en" and not language.startswith("en-"):
        raise ValueError
    if type(data["automatic"]) is not bool:
        raise ValueError
    m = _fields(
        data["metadata"],
        "url video_id title channel channel_id channel_url upload_date "
        "duration_seconds chapters chapter_status sponsorblock description",
    )
    if (
        not isinstance(m["url"], str)
        or validate_youtube_url(m["url"]) != m["url"]
        or m["video_id"] != m["url"].rsplit("=", 1)[1]
    ):
        raise ValueError
    for name in (
        "title",
        "channel",
        "channel_id",
        "channel_url",
        "upload_date",
        "description",
    ):
        if m[name] is not None and not isinstance(m[name], str):
            raise ValueError
    duration = m["duration_seconds"]
    if duration is not None:
        milliseconds(duration)
    chapters = []
    for row in _list(m["chapters"]):
        row = _fields(row, "title start_ms end_ms")
        chapters.append(
            Chapter(
                _string(row["title"]),
                _ms(row["start_ms"]),
                None if row["end_ms"] is None else _ms(row["end_ms"]),
            )
        )
    status = m["chapter_status"]
    if status not in ("available", "unavailable", "invalid") or bool(chapters) != (
        status == "available"
    ):
        raise ValueError
    if chapters:
        normalized = normalize_chapters(
            [
                {
                    "title": c.title,
                    "start_time": c.start_ms / 1000,
                    "end_time": c.end_ms / 1000 if c.end_ms is not None else None,
                }
                for c in chapters
            ],
            duration_seconds=duration,
        )
        if normalized.chapters != tuple(chapters):
            raise ValueError
    s = _fields(m["sponsorblock"], "enabled status categories segments reason_code")
    categories = _list(s["categories"])
    validate_policy(
        {"enabled": s["enabled"], "categories": categories, "timeout_seconds": 10}
    )
    if s["status"] not in ("disabled", "available", "not_found", "lookup_failed"):
        raise ValueError
    if s["reason_code"] not in (
        None,
        "LOOKUP_FAILED",
        "RESPONSE_TOO_LARGE",
        "INVALID_RESPONSE",
        "ALIGNMENT_UNVERIFIED",
        "REMOVAL_WOULD_EMPTY",
    ):
        raise ValueError
    segments = []
    for row in _list(s["segments"]):
        row = _fields(row, "start_ms end_ms category votes locked")
        start, end = _ms(row["start_ms"]), _ms(row["end_ms"])
        if (
            end <= start
            or row["category"] not in CATEGORIES
            or row["category"] not in categories
            or type(row["votes"]) is not int
            or row["votes"] < 0
            or type(row["locked"]) is not bool
            or duration is None
            or end > milliseconds(duration)
        ):
            raise ValueError
        segments.append(
            SponsorBlockSegment(
                start, end, row["category"], row["votes"], row["locked"]
            )
        )
    lookup = SponsorBlockLookup(
        s["enabled"],
        cast(Status, s["status"]),
        tuple(categories),
        tuple(segments),
        cast(Reason | None, s["reason_code"]),
    )
    fragments = []
    for row in _list(data["fragments"]):
        row = _fields(row, "start_ms end_ms text")
        start, end = _ms(row["start_ms"]), _ms(row["end_ms"])
        if end < start:
            raise ValueError
        fragments.append(Cue(start, end, _string(row["text"])))
    if not fragments:
        raise ValueError
    cues = tuple(fragments)
    metadata = VideoMetadata(
        **(m | {"chapters": tuple(chapters), "sponsorblock": lookup})
    )
    cleaned = CleanedTranscript(
        " ".join(c.text for c in cues),
        metadata,
        language,
        data["automatic"],
        cues,
        build_chapter_sections(cues, metadata.chapters),
        project_sponsorblock(cues, lookup),
        compute_receipt(cues, lookup),
    )
    for effective in (False, True):
        validate_service_result(
            "get_transcript",
            {
                "format": "plain_text",
                "document": cleaned.body,
                "metadata": cleaned.mapping(effective=effective),
                "character_count": len(cleaned.body),
            },
        )
    return cleaned


def _default_path() -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME", ""))
    if not root.is_absolute():
        root = Path.home() / ".cache"
    return root / "yt-transcript" / "transcripts.db"


class TranscriptCache:
    """Each operation uses a short connection and returns safe misses on faults."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        ttl_hours: int = 24,
        max_size_mb: int = 50,
        enabled: bool = True,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if (
            type(ttl_hours) is not int
            or not 1 <= ttl_hours <= 168
            or type(max_size_mb) is not int
            or not 10 <= max_size_mb <= 500
            or type(enabled) is not bool
        ):
            raise ValueError("Invalid cache policy.")
        self.path = Path(path) if path is not None else _default_path()
        self.ttl_seconds = ttl_hours * 3600
        self.max_bytes = max_size_mb * 1024 * 1024
        self.enabled = enabled
        self.clock = clock or time.time

    def _private(self, path: Path, *, directory: bool = False) -> None:
        info = path.lstat()
        if not (
            stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        ):
            raise ValueError
        if os.name == "posix" and (
            info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ValueError

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # SQLite creates rollback journals inside this scope with owner-only access.
        old_umask = os.umask(0o077)
        connection = None
        try:
            parent = self.path.parent
            if not parent.exists() and not parent.is_symlink():
                parent.parent.mkdir(parents=True, exist_ok=True)
                try:
                    parent.mkdir(mode=0o700)
                except FileExistsError:
                    pass
            self._private(parent, directory=True)
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
            self._private(self.path)
            for suffix in ("-journal", "-wal", "-shm"):
                sidecar = Path(str(self.path) + suffix)
                if sidecar.exists() or sidecar.is_symlink():
                    self._private(sidecar)
            connection = sqlite3.connect(self.path, timeout=5)
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS snapshots ("
                "cache_key TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, "
                "payload BLOB NOT NULL, created REAL NOT NULL, accessed REAL NOT NULL)"
            )
            yield connection
        finally:
            if connection is not None:
                connection.close()
            os.umask(old_umask)

    def _now(self) -> float:
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise ValueError
        return now

    def _evict(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute(
            "DELETE FROM snapshots WHERE created <= ? OR created > ? OR created < 0 "
            "OR accessed < created OR accessed > ? "
            "OR typeof(created) NOT IN ('real', 'integer') "
            "OR typeof(accessed) NOT IN ('real', 'integer') "
            "OR typeof(payload) != 'blob' OR length(payload) > ?",
            (now - self.ttl_seconds, now, now, PAYLOAD_LIMIT),
        )
        total = connection.execute(
            "SELECT coalesce(sum(length(payload)), 0) FROM snapshots"
        ).fetchone()[0]
        for key, size in connection.execute(
            "SELECT cache_key, length(payload) FROM snapshots "
            "ORDER BY accessed, created, cache_key"
        ).fetchall():
            if total <= self.max_bytes:
                break
            connection.execute("DELETE FROM snapshots WHERE cache_key = ?", (key,))
            total -= size

    def get(self, key: str) -> CleanedTranscript | None:
        return self._get(key, None)

    def get_exact(self, key: str, snapshot_id: str) -> CleanedTranscript | None:
        if not isinstance(snapshot_id, str) or not _HEX.fullmatch(snapshot_id):
            return None
        return self._get(key, snapshot_id)

    def _get(self, key: str, expected: str | None) -> CleanedTranscript | None:
        if not self.enabled or not isinstance(key, str) or not _HEX.fullmatch(key):
            return None
        try:
            now = self._now()
            with self._connection() as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                self._evict(connection, now)
                row = connection.execute(
                    "SELECT snapshot_id, payload FROM snapshots WHERE cache_key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    return None
                digest, payload = row
                try:
                    if (
                        not isinstance(digest, str)
                        or not _HEX.fullmatch(digest)
                        or hashlib.sha256(payload).hexdigest() != digest
                    ):
                        raise ValueError
                    cleaned = _restore(payload)
                    if (
                        cleaned.projection
                        and cleaned.projection.lookup.status == "lookup_failed"
                    ):
                        raise ValueError
                except _FAULTS:
                    connection.execute(
                        "DELETE FROM snapshots WHERE cache_key = ?", (key,)
                    )
                    return None
                if expected is not None and digest != expected:
                    return None
                connection.execute(
                    "UPDATE snapshots SET accessed = ? WHERE cache_key = ?", (now, key)
                )
                return cleaned
        except _FAULTS:
            return None

    def put(self, key: str, cleaned: CleanedTranscript) -> str | None:
        if not self.enabled or not isinstance(key, str) or not _HEX.fullmatch(key):
            return None
        try:
            if (
                cleaned.projection
                and cleaned.projection.lookup.status == "lookup_failed"
            ):
                return None
            payload = _payload(cleaned)
            restored = _restore(payload)
            if (
                restored.projection
                and restored.projection.lookup.status == "lookup_failed"
            ):
                return None
            digest = hashlib.sha256(payload).hexdigest()
            now = self._now()
            with self._connection() as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?)",
                    (key, digest, payload, now, now),
                )
                self._evict(connection, now)
                retained = connection.execute(
                    "SELECT snapshot_id FROM snapshots WHERE cache_key = ?", (key,)
                ).fetchone()
                return digest if retained and retained[0] == digest else None
        except _FAULTS:
            return None

    def cleanup(self) -> None:
        if not self.enabled:
            return
        try:
            now = self._now()
            with self._connection() as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                self._evict(connection, now)
        except _FAULTS:
            pass
