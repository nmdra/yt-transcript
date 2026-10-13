"""Offline snapshot, storage privacy, and transaction boundary tests."""

import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from yt_transcript.chapters import (
    Chapter,
    build_chapter_sections,
    render_chapter_text,
    render_timed_text,
)
from yt_transcript.cleaner import Cue
from yt_transcript.metadata import VideoMetadata
from yt_transcript.service import CleanedTranscript
from yt_transcript.sponsorblock import (
    SponsorBlockConfig,
    SponsorBlockLookup,
    SponsorBlockSegment,
    compute_receipt,
    project_sponsorblock,
)
from yt_transcript.transcript_cache import (
    PAYLOAD_LIMIT,
    VERSION,
    TranscriptCache,
    make_cache_key,
    snapshot_id,
)

URL = "https://www.youtube.com/watch?v=abcdefghijk"
POLICY = SponsorBlockConfig(True)
KEY = make_cache_key(URL, "filtered", POLICY)


def cleaned(*, lookup=None, fragments=None, chapters=True, text="Source é 日本語"):
    cues = fragments or (
        Cue(8000, 10000, text),
        Cue(1000, 2000, "backward"),
        Cue(2500, 2500, "zero duration"),
        Cue(12000, 13000, "last"),
    )
    lookup = lookup or SponsorBlockLookup(True, "not_found")
    metadata = VideoMetadata(
        URL,
        "abcdefghijk",
        title="Title",
        channel="Channel",
        channel_id="channel-id",
        channel_url="https://www.youtube.com/@channel",
        upload_date="2026-01-02",
        duration_seconds=20,
        chapters=(Chapter("One", 0, 5000), Chapter("Two", 5000, 20000))
        if chapters
        else (),
        chapter_status="available" if chapters else "unavailable",
        sponsorblock=lookup,
        description='A description.\nSecond line: "quoted". 日本語',
    )
    return CleanedTranscript(
        " ".join(c.text for c in cues),
        metadata,
        "en-US",
        True,
        cues,
        build_chapter_sections(cues, metadata.chapters),
        project_sponsorblock(cues, lookup),
        compute_receipt(cues, lookup),
    )


@pytest.fixture
def cache(tmp_path):
    return TranscriptCache(tmp_path / "cache" / "transcripts.db", clock=lambda: 100000)


def rewrite(cache, mutate=None, *, payload=None, digest=True):
    with sqlite3.connect(cache.path) as connection:
        if payload is None:
            original = connection.execute("SELECT payload FROM snapshots").fetchone()[0]
            data = json.loads(original)
            assert mutate is not None
            mutate(data)
            payload = json.dumps(data, allow_nan=True).encode()
        connection.execute(
            "UPDATE snapshots SET payload = ?, snapshot_id = ?",
            (payload, hashlib.sha256(payload).hexdigest() if digest else "0" * 64),
        )


@pytest.mark.parametrize("chapters", [True, False])
@pytest.mark.parametrize("status", ["disabled", "not_found", "available"])
def test_roundtrip_preserves_source_and_rendering(cache, chapters, status):
    lookup = SponsorBlockLookup(
        status != "disabled",
        status,
        segments=(SponsorBlockSegment(1000, 3000, "sponsor", 5, True),)
        if status == "available"
        else (),
    )
    original = cleaned(lookup=lookup, chapters=chapters)
    identity = cache.put(KEY, original)
    assert identity == snapshot_id(original)
    # Restart reuse, not an in-memory hit.
    restored = TranscriptCache(cache.path, clock=cache.clock).get_exact(KEY, identity)
    assert restored == original
    assert restored is not None
    assert restored.metadata.description == original.metadata.description
    assert restored.fragments == original.fragments
    for effective in (False, True):
        assert restored.mapping(effective=effective) == original.mapping(
            effective=effective
        )
        assert restored.document(effective=effective) == original.document(
            effective=effective
        )
    assert restored.effective_sections == original.effective_sections
    assert render_chapter_text(restored.effective_sections) == render_chapter_text(
        original.effective_sections
    )
    assert restored.projection is not None and original.projection is not None
    assert render_timed_text(
        restored.projection.fragments, source_indices=restored.projection.source_indices
    ) == render_timed_text(
        original.projection.fragments, source_indices=original.projection.source_indices
    )
    if status == "available":
        assert restored.metadata.sponsorblock == lookup
        assert restored.raw_receipt.removed_cue_count == 0
        assert restored.projection.receipt.removed_cue_count == 1
        assert restored.projection.source_indices == (0, 2, 3)
        assert (
            restored.projection.fragments[1].start_ms
            == restored.projection.fragments[1].end_ms
        )


def test_key_policy_and_snapshot_identity():
    alias = "https://youtu.be/abcdefghijk"
    assert make_cache_key(alias, "filtered", POLICY) == KEY
    reordered = replace(POLICY, categories=tuple(reversed(POLICY.categories)))
    assert make_cache_key(URL, "filtered", reordered) == KEY
    for policy in (
        replace(POLICY, enabled=False),
        replace(POLICY, timeout_seconds=11),
        replace(POLICY, categories=("sponsor",)),
    ):
        assert make_cache_key(URL, "filtered", policy) != KEY
    assert make_cache_key(URL, "full", POLICY) != KEY
    assert make_cache_key(URL, "full", POLICY) == make_cache_key(
        URL, "full", replace(POLICY, enabled=False)
    )
    assert make_cache_key(URL, "filtered", SponsorBlockConfig()) == KEY
    assert snapshot_id(cleaned()) == snapshot_id(cleaned())
    assert snapshot_id(cleaned(text="different")) != snapshot_id(cleaned())
    changed = replace(
        cleaned(), metadata=replace(cleaned().metadata, description="changed")
    )
    assert snapshot_id(changed) != snapshot_id(cleaned())
    with pytest.raises(ValueError):
        make_cache_key(URL, "wrong", POLICY)  # type: ignore[arg-type]


def test_creation_ttl_not_access_ttl(cache):
    now = [100000]
    cache.clock = lambda: now[0]
    identity = cache.put(KEY, cleaned())
    now[0] += 86399
    assert cache.get_exact(KEY, identity) is not None
    assert snapshot_id(cache.get(KEY)) == identity
    now[0] += 1
    assert cache.get(KEY) is None
    assert cache.get_exact(KEY, identity) is None
    cache.cleanup()
    with sqlite3.connect(cache.path) as connection:
        assert connection.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0


def test_exact_replacement_and_two_connections(cache):
    first = cache.put(KEY, cleaned())
    other = TranscriptCache(cache.path, clock=cache.clock)
    assert other.get_exact(KEY, first) is not None
    second = other.put(KEY, cleaned(text="replacement"))
    assert second and second != first
    assert cache.get_exact(KEY, first) is None
    assert cache.get_exact(KEY, second) is not None
    assert cache.get_exact(KEY, "invalid") is None


@pytest.mark.parametrize(
    "lookup",
    [
        SponsorBlockLookup(True, "lookup_failed", reason_code="LOOKUP_FAILED"),
        SponsorBlockLookup(
            True,
            "available",
            segments=(SponsorBlockSegment(0, 20000, "sponsor", 1, False),),
        ),
    ],
)
def test_effective_lookup_failure_is_never_persisted(cache, lookup):
    original = cleaned(lookup=lookup, fragments=(Cue(1000, 2000, "only cue"),))
    assert original.projection is not None
    assert original.projection.lookup.status == "lookup_failed"
    if lookup.status == "available":
        assert original.metadata.sponsorblock.status == "available"
        assert original.projection.lookup.reason_code == "REMOVAL_WOULD_EMPTY"
    assert cache.put(KEY, original) is None
    assert not cache.path.exists()


def test_failed_effective_lookup_rejected_on_read(cache):
    cache.put(KEY, cleaned())

    def mutate(data):
        data["metadata"]["sponsorblock"].update(
            status="lookup_failed", reason_code="LOOKUP_FAILED"
        )

    rewrite(cache, mutate)
    assert cache.get(KEY) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(extra=1),
        lambda d: d.update(v=VERSION + 1),
        lambda d: d.update(v=True),
        lambda d: d.update(automatic=1),
        lambda d: d.update(language="12"),
        lambda d: d.update(translated="yes"),
        lambda d: d.update(fragments=[]),
        lambda d: d["fragments"][0].update(extra=1),
        lambda d: d["fragments"][0].update(start_ms=True),
        lambda d: d["fragments"][0].update(start_ms=-1),
        lambda d: d["fragments"][0].update(end_ms=0),
        lambda d: d["fragments"][0].update(end_ms=2**63),
        lambda d: d["fragments"][0].update(text=10),
        lambda d: d["metadata"].update(extra=1),
        lambda d: d["metadata"].update(video_id="xxxxxxxxxxx"),
        lambda d: d["metadata"].update(url="https://youtu.be/abcdefghijk"),
        lambda d: d["metadata"].update(title=1),
        lambda d: d["metadata"].update(description=[]),
        lambda d: d["metadata"].update(duration_seconds=True),
        lambda d: d["metadata"].update(duration_seconds=float("nan")),
        lambda d: d["metadata"].update(duration_seconds=float("inf")),
        lambda d: d["metadata"].update(chapter_status="unavailable"),
        lambda d: d["metadata"]["chapters"][0].update(extra=1),
        lambda d: d["metadata"]["chapters"][0].update(start_ms=True),
        lambda d: d["metadata"]["chapters"][0].update(end_ms=0),
        lambda d: d["metadata"]["sponsorblock"].update(extra=1),
        lambda d: d["metadata"]["sponsorblock"].update(enabled=1),
        lambda d: d["metadata"]["sponsorblock"].update(status="available"),
        lambda d: d["metadata"]["sponsorblock"].update(categories=["unknown"]),
        lambda d: d["metadata"]["sponsorblock"].update(
            categories=["sponsor", "sponsor"]
        ),
        lambda d: d["metadata"]["sponsorblock"].update(reason_code="UNKNOWN"),
    ],
)
def test_strict_snapshot_validation(cache, mutate):
    assert cache.put(KEY, cleaned())
    rewrite(cache, mutate)
    assert cache.get(KEY) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra", 1),
        ("start_ms", True),
        ("end_ms", 1),
        ("votes", True),
        ("votes", -1),
        ("locked", 1),
        ("category", "unknown"),
        ("end_ms", 30000),
    ],
)
def test_segment_validation(cache, field, value):
    source = cleaned(
        lookup=SponsorBlockLookup(
            True,
            "available",
            segments=(SponsorBlockSegment(1000, 3000, "sponsor", 1, True),),
        )
    )
    assert cache.put(KEY, source)
    rewrite(
        cache,
        lambda d: d["metadata"]["sponsorblock"]["segments"][0].update({field: value}),
    )
    assert cache.get(KEY) is None


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b'{"v":1,"v":1}',
        b"\xff",
        b"[NaN]",
        b"[" * 2000,
        b"x" * (PAYLOAD_LIMIT + 1),
    ],
)
def test_corrupt_duplicate_and_oversize_payloads(cache, payload):
    assert cache.put(KEY, cleaned())
    rewrite(cache, payload=payload)
    assert cache.get(KEY) is None


def test_digest_is_verified_even_without_exact(cache):
    assert cache.put(KEY, cleaned())
    rewrite(cache, payload=b"{}", digest=False)
    assert cache.get(KEY) is None


def test_oversize_write_does_not_replace_existing(cache):
    first = cache.put(KEY, cleaned())
    assert cache.put(KEY, cleaned(text="é" * PAYLOAD_LIMIT)) is None
    assert cache.get_exact(KEY, first) is not None


def test_atomic_lru_budget_and_retained_id(cache):
    cache.max_bytes = 3500
    first = cache.put("1" * 64, cleaned(text="a" * 600))
    cache.clock = lambda: 100001
    second = cache.put("2" * 64, cleaned(text="b" * 600))
    cache.clock = lambda: 100002
    assert cache.get_exact("1" * 64, first)
    cache.clock = lambda: 100003
    third = cache.put("3" * 64, cleaned(text="c" * 600))
    assert third
    assert cache.get_exact("1" * 64, first)
    assert cache.get_exact("2" * 64, second) is None
    assert cache.get_exact("3" * 64, third)
    with sqlite3.connect(cache.path) as connection:
        assert (
            connection.execute("SELECT sum(length(payload)) FROM snapshots").fetchone()[
                0
            ]
            <= cache.max_bytes
        )
    cache.max_bytes = 1
    assert cache.put(KEY, cleaned()) is None
    assert cache.get(KEY) is None


def test_write_failure_rolls_back_replacement_and_eviction(cache, monkeypatch):
    identity = cache.put(KEY, cleaned())

    def interrupted(connection, now):
        connection.execute("DELETE FROM snapshots")
        raise sqlite3.OperationalError("synthetic interruption")

    reader = TranscriptCache(cache.path, clock=cache.clock)
    monkeypatch.setattr(cache, "_evict", interrupted)
    assert cache.put(KEY, cleaned(text="replacement")) is None
    assert reader.get_exact(KEY, identity) is not None
    cache.cleanup()
    assert reader.get_exact(KEY, identity) is not None


def test_disabled_is_no_io(tmp_path):
    cache = TranscriptCache(tmp_path / "absent" / "db", enabled=False)
    assert cache.get(KEY) is None
    assert cache.get_exact(KEY, "0" * 64) is None
    assert cache.put(KEY, cleaned()) is None
    cache.cleanup()
    assert not cache.path.parent.exists()


@pytest.mark.parametrize(
    "options",
    [
        {"ttl_hours": True},
        {"ttl_hours": 0},
        {"ttl_hours": 169},
        {"max_size_mb": True},
        {"max_size_mb": 9},
        {"max_size_mb": 501},
        {"enabled": 1},
    ],
)
def test_bounded_constructor_policy(options):
    with pytest.raises(ValueError):
        TranscriptCache(**options)


def test_default_paths_and_shared_root_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    before = tmp_path.stat().st_mode
    cache = TranscriptCache(clock=lambda: 100000)
    assert cache.path == tmp_path / "yt-transcript" / "transcripts.db"
    assert cache.put(KEY, cleaned())
    assert tmp_path.stat().st_mode == before
    monkeypatch.setenv("XDG_CACHE_HOME", "relative/path")
    assert (
        TranscriptCache().path
        == Path.home() / ".cache" / "yt-transcript" / "transcripts.db"
    )
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert (
        TranscriptCache().path
        == Path.home() / ".cache" / "yt-transcript" / "transcripts.db"
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_private_creation_journal_and_umask(cache, monkeypatch):
    old = os.umask(0o022)
    original = cache._evict
    observed = []

    def inspect(connection, now):
        journal = Path(str(cache.path) + "-journal")
        observed.append(stat.S_IMODE(journal.stat().st_mode))
        original(connection, now)

    monkeypatch.setattr(cache, "_evict", inspect)
    try:
        assert cache.put(KEY, cleaned())
        assert observed == [0o600]
        assert stat.S_IMODE(cache.path.stat().st_mode) == 0o600
        assert stat.S_IMODE(cache.path.parent.stat().st_mode) == 0o700
        actual = os.umask(0o022)
        assert actual == 0o022
    finally:
        os.umask(old)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
@pytest.mark.parametrize("target", ["directory", "database", "journal", "wal", "shm"])
def test_unsafe_permissions_are_misses(cache, target):
    assert cache.put(KEY, cleaned())
    if target == "directory":
        path = cache.path.parent
        path.chmod(0o755)
    elif target == "database":
        path = cache.path
        path.chmod(0o644)
    else:
        suffix = {"journal": "-journal", "wal": "-wal", "shm": "-shm"}[target]
        path = Path(str(cache.path) + suffix)
        path.touch(mode=0o644)
    assert cache.get(KEY) is None
    assert cache.put(KEY, cleaned()) is None
    cache.cleanup()


@pytest.mark.parametrize("target", ["directory", "database", "journal"])
def test_symlink_paths_are_rejected(tmp_path, target):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    path = tmp_path / "app" / "db"
    if target == "directory":
        path.parent.symlink_to(real, target_is_directory=True)
    else:
        path.parent.mkdir(mode=0o700)
        destination = real / "file"
        destination.touch(mode=0o600)
        link = path if target == "database" else Path(str(path) + "-journal")
        link.symlink_to(destination)
    cache = TranscriptCache(path)
    assert cache.put(KEY, cleaned()) is None
    assert cache.get(KEY) is None
    cache.cleanup()


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership contract")
def test_wrong_owner_rejected(cache, monkeypatch):
    assert cache.put(KEY, cleaned())
    monkeypatch.setattr(os, "getuid", lambda: cache.path.stat().st_uid + 1)
    assert cache.get(KEY) is None
    assert cache.put(KEY, cleaned()) is None


def test_storage_faults_fail_open(tmp_path, cache, monkeypatch, caplog):
    broken = tmp_path / "not-a-directory"
    broken.write_text("file")
    unavailable = TranscriptCache(broken / "db")
    assert unavailable.put(KEY, cleaned()) is None
    assert unavailable.get(KEY) is None
    unavailable.cleanup()
    assert cache.put(KEY, cleaned())
    cache.path.write_bytes(b"corrupt database")
    assert cache.get(KEY) is None
    assert cache.put(KEY, cleaned()) is None
    cache.cleanup()
    assert not caplog.records


@pytest.mark.parametrize("created", [-1, 100001, "invalid", float("inf")])
def test_invalid_creation_time(cache, created):
    assert cache.put(KEY, cleaned())
    with sqlite3.connect(cache.path) as connection:
        connection.execute("UPDATE snapshots SET created = ?", (created,))
    assert cache.get(KEY) is None


def test_busy_second_connection_fails_open_and_retains_snapshot(cache, monkeypatch):
    identity = cache.put(KEY, cleaned())
    connect = sqlite3.connect

    class ShortTimeout(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "PRAGMA busy_timeout=5000":
                sql = "PRAGMA busy_timeout=1"
            return super().execute(sql, parameters)

    def short_timeout(*args, **kwargs):
        return connect(*args, **kwargs, factory=ShortTimeout)

    # A held write lock must not replace the stored row. No sleeps or network.
    with connect(cache.path) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        monkeypatch.setattr(sqlite3, "connect", short_timeout)
        assert cache.put(KEY, cleaned(text="new")) is None
    monkeypatch.setattr(sqlite3, "connect", connect)
    assert cache.get_exact(KEY, identity) is not None


def test_exact_payload_limit_is_accepted(cache):
    assert cache.put(KEY, cleaned(text="x"))
    with sqlite3.connect(cache.path) as connection:
        baseline = connection.execute(
            "SELECT length(payload) FROM snapshots"
        ).fetchone()[0]
    source = cleaned(text="x" * (PAYLOAD_LIMIT - baseline + 1))
    identity = cache.put(KEY, source)
    assert identity == snapshot_id(source)
    with sqlite3.connect(cache.path) as connection:
        assert (
            connection.execute("SELECT length(payload) FROM snapshots").fetchone()[0]
            == PAYLOAD_LIMIT
        )
    assert cache.get_exact(KEY, identity) == source
    assert cache.put(KEY, cleaned(text=source.fragments[0].text + "x")) is None
    assert cache.get_exact(KEY, identity) == source


def test_supplied_effective_failure_is_not_persisted(cache):
    source = cleaned()
    assert source.projection is not None
    source = replace(
        source,
        projection=replace(
            source.projection,
            lookup=SponsorBlockLookup(
                True, "lookup_failed", reason_code="LOOKUP_FAILED"
            ),
        ),
    )
    assert cache.put(KEY, source) is None
    assert not cache.path.exists()


@pytest.mark.parametrize("now", [float("nan"), float("inf"), -1, True])
def test_invalid_clock_is_fail_open(cache, now):
    cache.clock = lambda: now
    assert cache.put(KEY, cleaned()) is None
    assert cache.get(KEY) is None
    cache.cleanup()
    assert not cache.path.exists()


@pytest.mark.parametrize(
    "damage", ["expired", "oversize", "digest", "json", "access_time"]
)
def test_invalid_rows_are_removed_on_read(cache, damage):
    identity = cache.put(KEY, cleaned())
    assert identity
    if damage == "expired":
        cache.clock = lambda: 100000 + cache.ttl_seconds
    elif damage == "oversize":
        rewrite(cache, payload=b"x" * (PAYLOAD_LIMIT + 1))
    elif damage == "digest":
        rewrite(cache, payload=b"{}", digest=False)
    elif damage == "json":
        rewrite(cache, payload=b"{")
    else:
        with sqlite3.connect(cache.path) as connection:
            connection.execute("UPDATE snapshots SET accessed = -1")
    assert cache.get(KEY) is None
    with sqlite3.connect(cache.path) as connection:
        assert connection.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0


def test_stale_cursor_does_not_delete_healthy_replacement(cache):
    old = cache.put(KEY, cleaned())
    new = cache.put(KEY, cleaned(text="replacement"))
    assert old != new
    assert cache.get_exact(KEY, old) is None
    assert cache.get_exact(KEY, new) is not None


def test_cache_key_is_language_scoped_and_english_stable():
    policy = SponsorBlockConfig(True)
    assert make_cache_key(URL, "filtered", policy, "en") == KEY
    assert make_cache_key(URL, "filtered", policy, "EN") == KEY
    french = make_cache_key(URL, "filtered", policy, "fr")
    assert french != KEY
    assert make_cache_key(URL, "filtered", policy, "fr") == french


def test_previous_payload_version_is_a_miss(cache):
    assert cache.put(KEY, cleaned())
    rewrite(cache, lambda d: d.update(v=1))
    assert cache.get(KEY) is None


def test_translation_provenance_survives_roundtrip(cache):
    original = replace(cleaned(), translated=True)
    identity = cache.put(KEY, original)
    restored = TranscriptCache(cache.path, clock=cache.clock).get_exact(KEY, identity)
    assert restored is not None
    assert restored.translated is True
    assert restored.cache_hit is None
    assert restored.mapping()["caption_translated"] is True


def test_cache_language_must_be_a_language_tag(cache):
    assert cache.put(KEY, cleaned())
    rewrite(cache, lambda d: d.update(language="12"))
    assert cache.get(KEY) is None
