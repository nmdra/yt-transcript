"""Offline retrieval checks using source cues and private temporary SQLite storage."""

import base64
import json
from dataclasses import replace

import pytest

from yt_transcript import formatter, service
from yt_transcript.chapters import build_chapter_sections, display_time
from yt_transcript.cleaner import Cue
from yt_transcript.errors import AppError
from yt_transcript.metadata import VideoMetadata
from yt_transcript.sponsorblock import (
    CaptionProjection,
    SponsorBlockConfig,
    SponsorBlockLookup,
    SponsorBlockRemovalReceipt,
    project_sponsorblock,
)
from yt_transcript.transcript_cache import TranscriptCache, make_cache_key

URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def tmp_cache(tmp_path):
    return TranscriptCache(tmp_path / "cache" / "transcripts.db")


@pytest.fixture
def synthetic(monkeypatch):
    calls = []
    fragments = (
        Cue(10000, 11000, "First Alpha"),
        Cue(11000, 12000, "BETA second"),
        Cue(3000, 3000, "Alpha zero"),
        Cue(1000, 2500, "alpha backward"),
        Cue(14000, 15000, "Straße repeats repeats"),
    )

    def fetch(url, *, sponsorblock=None):
        calls.append((url, sponsorblock))
        enabled = sponsorblock is not None and sponsorblock.enabled is True
        lookup = SponsorBlockLookup(
            enabled,
            "not_found" if enabled else "disabled",
            sponsorblock.categories
            if sponsorblock is not None
            else ("sponsor", "selfpromo", "interaction"),
        )
        metadata = VideoMetadata(
            URL, "abcdefghijk", description="source description", sponsorblock=lookup
        )
        projection = project_sponsorblock(fragments, lookup)
        return service.CleanedTranscript(
            " ".join(c.text for c in fragments),
            metadata,
            "en",
            False,
            fragments,
            build_chapter_sections(fragments, ()),
            projection,
        )

    monkeypatch.setattr(service, "fetch_clean_transcript", fetch)
    return fragments, calls


def assert_error(code, function, *args, **kwargs):
    with pytest.raises(AppError) as exc:
        function(*args, **kwargs)
    assert exc.value.info.code == code
    return exc.value.info


def test_shared_snapshot_across_operations(tmp_cache, synthetic):
    _, calls = synthetic
    policy = SponsorBlockConfig(enabled=False)
    kwargs = {"cache": tmp_cache, "sponsorblock": policy}
    transcript = service.fetch_transcript_document(URL, **kwargs)
    for query in ("alpha", "beta", "strasse"):
        service.search_transcript("https://youtu.be/abcdefghijk", query, **kwargs)
    segment = service.get_transcript_segment(URL, 0, 15, **kwargs)
    info = service.get_video_info(URL, **kwargs)
    page = service.get_transcript_page(URL, **kwargs)
    assert len(calls) == 1
    assert info["metadata"] == transcript["metadata"]
    assert len(segment["cues"]) == 5
    assert page["has_more"] is False
    assert page["next_cursor"] is None
    for operation, result in (
        ("get_transcript", transcript),
        ("get_video_info", info),
        ("get_transcript_segment", segment),
        ("get_transcript_page", page),
    ):
        service.validate_service_result(operation, result)


def test_segment_preserves_backward_zero_and_original_times(synthetic):
    result = service.get_transcript_segment(URL, 2, 11)
    assert [(c["start_seconds"], c["end_seconds"]) for c in result["cues"]] == [
        (10.0, 11.0),
        (3.0, 3.0),
        (1.0, 2.5),
    ]
    assert result["cues"][-1]["url"].endswith("&t=1s")
    assert service.get_transcript_segment(URL, 3, 4)["cues"][0]["text"] == "Alpha zero"
    assert service.get_transcript_segment(URL, 2.5, 3)["cues"] == []


@pytest.mark.parametrize(
    "start,end",
    [
        (True, 3),
        (0, False),
        (float("nan"), 3),
        (0, float("inf")),
        (-1, 2),
        (2, 2),
        (3, 2),
        (0, 901),
        (0, 0.0001),
        (0, 10**100),
    ],
)
def test_invalid_segment_never_fetches(synthetic, start, end):
    _, calls = synthetic
    assert_error(
        "SEGMENT_RANGE_INVALID", service.get_transcript_segment, URL, start, end
    )
    assert calls == []


def test_segment_cue_limit(monkeypatch):
    cues = tuple(Cue(0, 1, "many") for _ in range(201))
    cleaned = service.CleanedTranscript(
        "many", VideoMetadata(URL, "abcdefghijk"), "en", False, cues
    )
    monkeypatch.setattr(
        service, "fetch_clean_transcript", lambda *args, **kwargs: cleaned
    )
    assert_error("MCP_RESPONSE_LIMIT", service.get_transcript_segment, URL, 0, 1)


def test_search_normalization_evidence_and_earliest_order(synthetic):
    result = service.search_transcript(URL, "  ALPHA\t ")
    assert result["query"] == "alpha"
    assert [m["start_seconds"] for m in result["matches"]] == [1.0, 3.0, 10.0]
    assert [m["text"] for m in result["matches"]] == [
        "alpha backward",
        "Alpha zero",
        "First Alpha",
    ]
    phrase = service.search_transcript(URL, "alpha beta")["matches"][0]
    assert phrase["text"] == "First Alpha BETA second"
    assert phrase["context"] == "First Alpha BETA second Alpha zero"
    assert (
        service.search_transcript(URL, "STRASSE")["matches"][0]["text"]
        == "Straße repeats repeats"
    )
    assert len(service.search_transcript(URL, "repeats")["matches"]) == 1
    assert service.search_transcript(URL, "missing")["matches"] == []


def test_search_does_not_bridge_removed_source_indices(monkeypatch):
    cues = (Cue(0, 1000, "left"), Cue(2000, 3000, "right"))
    cleaned = service.CleanedTranscript(
        "left removed right",
        VideoMetadata(URL, "abcdefghijk"),
        "en",
        False,
        (cues[0], Cue(1000, 2000, "removed"), cues[1]),
        projection=CaptionProjection(
            cues,
            (0, 2),
            (1,),
            SponsorBlockLookup(),
            SponsorBlockRemovalReceipt(),
        ),
    )
    monkeypatch.setattr(
        service, "fetch_clean_transcript", lambda *args, **kwargs: cleaned
    )
    assert service.search_transcript(URL, "left right")["matches"] == []
    assert service.search_transcript(URL, "left")["matches"][0]["context"] == "left"


@pytest.mark.parametrize(
    "query,count",
    [
        ("", 10),
        (" \n", 10),
        ("x" * 201, 10),
        ("x", True),
        ("x", 0),
        ("x", 21),
        ("x", 1.5),
    ],
)
def test_invalid_search_never_fetches(synthetic, query, count):
    _, calls = synthetic
    assert_error(
        "SEARCH_QUERY_INVALID", service.search_transcript, URL, query, max_results=count
    )
    assert calls == []


def test_search_context_is_bounded_and_evidence_is_not_truncated(monkeypatch):
    cue = Cue(0, 0, "ß" * 200 + " " + "evidence " * 100)
    cleaned = service.CleanedTranscript(
        cue.text, VideoMetadata(URL, "abcdefghijk"), "en", False, (cue,)
    )
    monkeypatch.setattr(
        service, "fetch_clean_transcript", lambda *args, **kwargs: cleaned
    )
    match = service.search_transcript(URL, "ß" * 200)["matches"][0]
    assert match["text"] == cue.text
    assert len(match["context"]) == 500


def test_paging_covers_every_cue_once_and_source_order(
    tmp_cache, synthetic, monkeypatch
):
    fragments, calls = synthetic
    original = service.fetch_clean_transcript

    def fetch(*args, **kwargs):
        cleaned = original(*args, **kwargs)
        cues = tuple(replace(c, text=c.text + " x" * 210) for c in fragments)
        return replace(
            cleaned,
            body=" ".join(c.text for c in cues),
            fragments=cues,
            projection=project_sponsorblock(cues, cleaned.metadata.sponsorblock),
        )

    monkeypatch.setattr(service, "fetch_clean_transcript", fetch)
    lines = []
    cursor = None
    while True:
        page = service.get_transcript_page(
            URL,
            cursor,
            max_chars=1000,
            cache=tmp_cache,
            sponsorblock=SponsorBlockConfig(enabled=False),
        )
        assert len(page["document"]) <= 1000
        lines.extend(page["document"].splitlines())
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        assert page["next_cursor"] != cursor
        cursor = page["next_cursor"]
    assert len(calls) == 1
    assert len(lines) == len(fragments)
    assert lines == [
        f"[{display_time(c.start_ms)} - {display_time(c.end_ms)}] {c.text}" + " x" * 210
        for c in fragments
    ]


def cursor_text(**overrides):
    value = {
        "v": 1,
        "cache_key": "a" * 64,
        "snapshot_id": "b" * 64,
        "next_index": 1,
        **overrides,
    }
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "cursor",
    [
        "!",
        "a" * 2049,
        "Zg",
        cursor_text(v=True),
        cursor_text(v=2),
        cursor_text(next_index=True),
        cursor_text(next_index=-1),
        cursor_text(next_index=2**63),
        cursor_text(cache_key="A" * 64),
        cursor_text(extra=1),
    ],
)
def test_bad_cursor_never_fetches(synthetic, tmp_cache, cursor):
    _, calls = synthetic
    assert_error(
        "CACHE_CURSOR_INVALID",
        service.get_transcript_page,
        URL,
        cursor,
        cache=tmp_cache,
    )
    assert calls == []


def test_duplicate_cursor_json_rejected():
    raw = (
        '{"v":1,"v":1,"cache_key":"'
        + "a" * 64
        + '","snapshot_id":"'
        + "b" * 64
        + '","next_index":1}'
    )
    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    assert_error("CACHE_CURSOR_INVALID", service.validate_page_request, encoded, 1000)


@pytest.mark.parametrize("count", [True, 999, 20001, 1000.0])
def test_invalid_page_size_never_fetches(synthetic, count):
    _, calls = synthetic
    assert_error("CONFIG_INVALID", service.get_transcript_page, URL, max_chars=count)
    assert calls == []


def test_missing_replaced_expired_and_bad_index_never_refetch(tmp_cache, synthetic):
    _, calls = synthetic
    policy = SponsorBlockConfig(enabled=False).resolved(default=True)
    service.get_transcript_page(URL, cache=tmp_cache, sponsorblock=policy)
    key = make_cache_key(URL, "filtered", policy)
    assert_error(
        "CACHE_CURSOR_EXPIRED",
        service.get_transcript_page,
        URL,
        cursor_text(cache_key=key),
        cache=tmp_cache,
        sponsorblock=policy,
    )
    assert_error(
        "CACHE_CURSOR_INVALID",
        service.get_transcript_page,
        URL,
        cursor_text(),
        cache=tmp_cache,
        sponsorblock=policy,
    )
    from yt_transcript.transcript_cache import snapshot_id

    cleaned = tmp_cache.get(key)
    assert cleaned is not None
    identity = snapshot_id(cleaned)
    assert_error(
        "CACHE_CURSOR_INVALID",
        service.get_transcript_page,
        URL,
        cursor_text(cache_key=key, snapshot_id=identity, next_index=5),
        cache=tmp_cache,
        sponsorblock=policy,
    )
    replacement = replace(
        cleaned, metadata=replace(cleaned.metadata, description="replacement")
    )
    tmp_cache.put(key, replacement)
    assert_error(
        "CACHE_CURSOR_EXPIRED",
        service.get_transcript_page,
        URL,
        cursor_text(cache_key=key, snapshot_id=identity),
        cache=tmp_cache,
        sponsorblock=policy,
    )
    assert len(calls) == 1


def test_page_requires_cache_before_fetch(synthetic, tmp_path):
    _, calls = synthetic
    assert_error("CACHE_UNAVAILABLE", service.get_transcript_page, URL)
    disabled = TranscriptCache(tmp_path / "disabled" / "transcripts.db", enabled=False)
    assert_error("CACHE_UNAVAILABLE", service.get_transcript_page, URL, cache=disabled)
    assert calls == []


def test_direct_service_is_uncached_and_progress_is_optional(synthetic, monkeypatch):
    _, calls = synthetic
    seen = []
    monkeypatch.setattr(formatter, "ensure_formatter", lambda *args: None)

    def format_body(body, **kwargs):
        seen.append(kwargs)
        if "on_progress" in kwargs:
            kwargs["on_progress"](0, 1)
            kwargs["on_progress"](1, 1)
        return "formatted"

    monkeypatch.setattr(formatter, "format_transcript", format_body)
    progress = []
    service.fetch_transcript_document(URL, output_format="markdown")
    service.fetch_transcript_document(
        URL,
        output_format="markdown",
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert len(calls) == 2
    assert "on_progress" not in seen[0]
    assert progress == [(0, 1), (1, 1)]


def test_readiness_precedes_cache_fetch(synthetic, tmp_cache, monkeypatch):
    _, calls = synthetic

    def fail(*args):
        raise RuntimeError("formatter not ready")

    monkeypatch.setattr(formatter, "ensure_formatter", fail)
    with pytest.raises(RuntimeError):
        service.fetch_transcript_document(
            URL, output_format="markdown", cache=tmp_cache
        )
    assert calls == []


def test_result_validation_exact_fields_and_source_order(synthetic):
    result = service.get_transcript_segment(URL, 0, 20)
    service.validate_service_result("get_transcript_segment", result)
    assert_error(
        "INTERNAL_ERROR",
        service.validate_service_result,
        "get_transcript_segment",
        {**result, "extra": 1},
    )
    bad = {**result, "cues": [{**result["cues"][0], "start_seconds": True}]}
    assert_error(
        "INTERNAL_ERROR", service.validate_service_result, "get_transcript_segment", bad
    )
    page = {
        "video_id": "abcdefghijk",
        "document": "body",
        "has_more": True,
        "next_cursor": None,
    }
    assert_error(
        "INTERNAL_ERROR", service.validate_service_result, "get_transcript_page", page
    )


def test_cached_markdown_still_formats_on_every_request(
    tmp_cache, synthetic, monkeypatch
):
    _, calls = synthetic
    edits = []
    monkeypatch.setattr(formatter, "ensure_formatter", lambda *args: None)
    monkeypatch.setattr(
        formatter,
        "format_transcript",
        lambda body, **kwargs: edits.append(body) or "edited",
    )
    for _ in range(2):
        service.fetch_transcript_document(
            URL,
            output_format="markdown",
            cache=tmp_cache,
            sponsorblock=SponsorBlockConfig(enabled=False),
        )
    assert len(calls) == 1
    assert len(edits) == 2


def test_page_expiry_never_refetches(tmp_path, synthetic):
    _, calls = synthetic
    now = [1000.0]
    cache = TranscriptCache(
        tmp_path / "expiry" / "transcripts.db", clock=lambda: now[0]
    )
    policy = SponsorBlockConfig(enabled=False)
    cleaned = service.get_cached_snapshot(URL, sponsorblock=policy, cache=cache)
    from yt_transcript.transcript_cache import snapshot_id

    key = make_cache_key(URL, "filtered", policy.resolved(default=True))
    cursor = cursor_text(cache_key=key, snapshot_id=snapshot_id(cleaned))
    now[0] += 24 * 3600 + 1
    assert_error(
        "CACHE_CURSOR_EXPIRED",
        service.get_transcript_page,
        URL,
        cursor,
        cache=cache,
        sponsorblock=policy,
    )
    assert len(calls) == 1


def test_ordinary_cache_faults_fall_back_but_pages_require_storage(
    synthetic, tmp_cache, monkeypatch
):
    _, calls = synthetic

    def fail(*args):
        raise OSError("private database detail")

    monkeypatch.setattr(tmp_cache, "get", fail)
    monkeypatch.setattr(tmp_cache, "put", fail)
    service.get_video_info(URL, cache=tmp_cache)
    service.search_transcript(URL, "alpha", cache=tmp_cache)
    monkeypatch.setattr(tmp_cache, "get_exact", fail)
    info = assert_error(
        "CACHE_UNAVAILABLE", service.get_transcript_page, URL, cache=tmp_cache
    )
    assert "private" not in info.message
    assert len(calls) == 3


def test_failed_effective_filtering_is_not_cached(synthetic, tmp_cache, monkeypatch):
    _, calls = synthetic
    fetch = service.fetch_clean_transcript

    def failed(*args, **kwargs):
        cleaned = fetch(*args, **kwargs)
        assert cleaned.projection is not None
        lookup = SponsorBlockLookup(
            enabled=True,
            status="lookup_failed",
            reason_code="LOOKUP_FAILED",
        )
        return replace(cleaned, projection=replace(cleaned.projection, lookup=lookup))

    writes = []
    monkeypatch.setattr(service, "fetch_clean_transcript", failed)
    monkeypatch.setattr(tmp_cache, "put", lambda *args: writes.append(args))
    service.get_cached_snapshot(URL, cache=tmp_cache)
    assert_error("CACHE_UNAVAILABLE", service.get_transcript_page, URL, cache=tmp_cache)
    assert len(calls) == 2
    assert writes == []


def test_oversize_search_evidence_and_page_cue_fail_without_truncation(
    monkeypatch, tmp_cache
):
    cue = Cue(0, 1, "needle " + "😀" * 150000)
    lookup = SponsorBlockLookup(enabled=False, status="disabled")
    cleaned = service.CleanedTranscript(
        cue.text,
        VideoMetadata(URL, "abcdefghijk", sponsorblock=lookup),
        "en",
        False,
        (cue,),
        projection=project_sponsorblock((cue,), lookup),
    )
    monkeypatch.setattr(
        service, "fetch_clean_transcript", lambda *args, **kwargs: cleaned
    )
    assert_error("MCP_RESPONSE_LIMIT", service.search_transcript, URL, "needle")
    assert_error(
        "MCP_RESPONSE_LIMIT",
        service.get_transcript_page,
        URL,
        cache=tmp_cache,
        sponsorblock=SponsorBlockConfig(enabled=False),
    )


def test_sdk_multi_operation_snapshot_acceptance(monkeypatch, tmp_path):
    import asyncio

    import jsonschema
    from mcp import Client
    from mcp.types import TextContent

    from yt_transcript.config import AppConfig
    from yt_transcript.downloader import DownloadedCaptions
    from yt_transcript.mcp_server import create_server
    from yt_transcript.mcp_worker import dispatch, validate_request

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "sdk-cache"))
    extraction = []
    lookups = []
    model_calls = []
    source_texts = [f"alpha beta evidence {index} " + "x" * 390 for index in range(7)]
    vtt = (
        "WEBVTT\n\n"
        + "\n\n".join(
            f"00:{index * 2:02}.000 --> 00:{index * 2 + 1:02}.000\n{text}"
            for index, text in enumerate(source_texts)
        )
        + "\n"
    )

    def download(url):
        extraction.append(url)
        return DownloadedCaptions(
            vtt.encode(), "en", False, VideoMetadata(URL, "abcdefghijk")
        )

    def lookup(video_id, **kwargs):
        lookups.append(video_id)
        return SponsorBlockLookup(enabled=True, status="not_found")

    def edit(body, **kwargs):
        model_calls.append((body, kwargs["editorial_mode"]))
        return "Mocked Markdown output."

    monkeypatch.setattr(service, "download_english_vtt", download)
    monkeypatch.setattr(service, "lookup_sponsorblock", lookup)
    monkeypatch.setattr(formatter, "ensure_formatter", lambda *args: None)
    monkeypatch.setattr(formatter, "format_transcript", edit)

    class DispatchRunner:
        async def run(self, payload, *, on_progress=None):
            return dict(dispatch(validate_request(payload)))

        async def close(self):
            pass

    async def check():
        async with Client(
            create_server(AppConfig(), runner=DispatchRunner()), raise_exceptions=True
        ) as client:
            tools = (await client.list_tools()).tools
            assert [tool.name for tool in tools] == [
                "get_transcript",
                "get_video_info",
                "get_transcript_segment",
                "search_transcript",
                "get_transcript_page",
            ]
            assert set(tools[0].input_schema["properties"]) == {
                "url",
                "mode",
                "output_format",
            }
            schemas = {tool.name: tool.output_schema for tool in tools}

            async def call(name, **args):
                result = await client.call_tool(
                    name, {"url": "https://youtu.be/abcdefghijk", **args}
                )
                assert not result.is_error
                content = result.content[0]
                assert isinstance(content, TextContent)
                assert json.loads(content.text) == result.structured_content
                schema = schemas[name]
                assert schema is not None
                jsonschema.validate(result.structured_content, schema)
                return result.structured_content

            transcript = await call("get_transcript")
            for query in ("alpha", "beta evidence", "missing"):
                await call("search_transcript", query=query)
            segment = await call(
                "get_transcript_segment", start_seconds=0, end_seconds=14
            )
            assert [cue["text"] for cue in segment["cues"]] == source_texts
            lines = []
            cursor = None
            while True:
                page = await call("get_transcript_page", cursor=cursor, max_chars=1000)
                assert len(page["document"]) <= 1000
                lines.extend(page["document"].splitlines())
                if not page["has_more"]:
                    assert page["next_cursor"] is None
                    break
                cursor = page["next_cursor"]
            assert lines == [
                f"[{display_time(index * 2000)} - {display_time(index * 2000 + 1000)}] {text}"
                for index, text in enumerate(source_texts)
            ]
            info = await call("get_video_info")
            assert info["metadata"] == transcript["metadata"]
            assert len(extraction) == len(lookups) == 1
            assert model_calls == []
            for _ in range(2):
                markdown = await call("get_transcript", output_format="markdown")
                assert markdown["document"] == "Mocked Markdown output."
            assert len(extraction) == len(lookups) == 1
            assert len(model_calls) == 2
            assert model_calls[0] == model_calls[1]

    asyncio.run(check())


@pytest.mark.parametrize("mismatch", ["video", "policy"])
def test_wrong_snapshot_identity_is_not_reused(tmp_cache, synthetic, mismatch):
    from yt_transcript.transcript_cache import snapshot_id

    _, calls = synthetic
    policy = SponsorBlockConfig(enabled=True if mismatch == "policy" else False)
    source = service.get_cached_snapshot(
        URL, sponsorblock=SponsorBlockConfig(enabled=False)
    )
    if mismatch == "video":
        source = replace(
            source,
            metadata=replace(
                source.metadata,
                url="https://www.youtube.com/watch?v=zyxwvutsrqp",
                video_id="zyxwvutsrqp",
            ),
        )
    key = make_cache_key(URL, "filtered", policy)
    identity = tmp_cache.put(key, source)
    assert identity == snapshot_id(source)
    calls.clear()
    assert_error(
        "CACHE_CURSOR_EXPIRED",
        service.get_transcript_page,
        URL,
        cursor_text(cache_key=key, snapshot_id=identity, next_index=1),
        cache=tmp_cache,
        sponsorblock=policy,
    )
    assert calls == []
    result = service.get_video_info(URL, cache=tmp_cache, sponsorblock=policy)
    assert result["metadata"]["video_id"] == "abcdefghijk"
    assert result["metadata"]["sponsorblock"]["enabled"] == policy.enabled
    assert len(calls) == 1
    # Fresh fetch replaced the mismatched row with a request-consistent snapshot.
    service.get_video_info(URL, cache=tmp_cache, sponsorblock=policy)
    assert len(calls) == 1


def test_common_query_keeps_earliest_bounded_ranges(monkeypatch):
    cues = tuple(
        Cue(i * 1000, i * 1000 + 900, f"a a a {i}") for i in reversed(range(5000))
    )
    lookup = SponsorBlockLookup(enabled=False, status="disabled")
    cleaned = service.CleanedTranscript(
        " ".join(c.text for c in cues),
        VideoMetadata(URL, "abcdefghijk", sponsorblock=lookup),
        "en",
        False,
        cues,
        projection=project_sponsorblock(cues, lookup),
    )
    monkeypatch.setattr(
        service, "fetch_clean_transcript", lambda *args, **kwargs: cleaned
    )
    result = service.search_transcript(
        URL, "a", max_results=2, sponsorblock=SponsorBlockConfig(enabled=False)
    )
    assert len(result["matches"]) == 2
    assert [m["start_seconds"] for m in result["matches"]] == [0.0, 1.0]
