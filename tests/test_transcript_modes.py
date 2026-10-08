"""Mode, receipts, and server permissions tested without network access."""

import asyncio
from dataclasses import asdict, replace

import pytest
import yaml
from mcp import Client

from yt_transcript import formatter, service
from yt_transcript.chapters import Chapter
from yt_transcript.config import AppConfig
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.errors import AppError
from yt_transcript.mcp_policy import MCPFormattingPolicy
from yt_transcript.mcp_server import create_server
from yt_transcript.mcp_worker import dispatch, validate_request
from yt_transcript.metadata import VideoMetadata
from yt_transcript.sponsorblock import (
    SponsorBlockConfig,
    SponsorBlockLookup,
    SponsorBlockSegment,
)

URL = "https://youtu.be/abcdefghijk"
VTT = b"WEBVTT\n\n00:00.000 --> 00:01.000\nintro\n\n00:01.000 --> 00:02.000\npromo\n\n00:02.500 --> 00:04.000\ncross useful\n\n00:08.000 --> 00:09.000\nsubject\n"


@pytest.fixture
def source(monkeypatch):
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk",
        duration_seconds=10,
        description="  Description sentinel\nhttps://example.test/\n",
    )
    calls = []

    def download(url):
        calls.append("download")
        return DownloadedCaptions(VTT, "en", False, metadata)

    def lookup(video_id, *, config, duration_seconds):
        if not config.enabled:
            return SponsorBlockLookup(categories=config.categories)
        calls.append("lookup")
        return SponsorBlockLookup(
            True,
            "available",
            config.categories,
            (SponsorBlockSegment(1000, 3000, "sponsor", 1, True),),
        )

    monkeypatch.setattr(service, "download_english_vtt", download)
    monkeypatch.setattr(service, "lookup_sponsorblock", lookup)
    return metadata, calls, download


def test_default_filtered_full_override_and_raw_receipts(source):
    metadata, calls, _ = source
    filtered = service.fetch_transcript_document(URL)
    assert calls == ["download", "lookup"]
    assert (
        filtered["metadata"]["sponsorblock"]["segments"][0]["removal_status"]
        == "partial"
    )
    body = filtered["document"]
    assert "promo" not in body and "cross useful" in body and "[00:08 - 00:09]" in body
    assert filtered["character_count"] == len(body)
    assert not body.startswith("---\n")
    calls.clear()
    full = service.fetch_transcript_document(URL, "full")
    assert calls == ["download"] and "promo" in full["document"]
    assert not full["metadata"]["sponsorblock"]["removal_applied"]
    assert (
        filtered["metadata"]["description"]
        == full["metadata"]["description"]
        == metadata.description
    )
    cleaned = service.fetch_clean_transcript(
        URL, sponsorblock=SponsorBlockConfig(enabled=True)
    )
    assert yaml.safe_load(cleaned.document().split("---\n", 2)[1]) == cleaned.mapping()
    raw = cleaned.mapping()
    assert raw["sponsorblock"]["segments"][0]["removal_status"] == "not_applied"
    assert raw["sponsorblock"]["retained_overlap_cue_count"] == 2
    assert raw["description"] == metadata.description
    assert cleaned.mapping(effective=True)["description"] == metadata.description
    assert (
        "promo" in cleaned.document()
        and "promo"
        not in cleaned.document(cleaned.effective_body, effective=True).split(
            "---\n", 2
        )[2]
    )
    assert "promo" not in cleaned.document(effective=True).split("---\n", 2)[2]
    assert cleaned.metadata.sponsorblock.status == "available"
    assert metadata.sponsorblock.status == "disabled"


@pytest.mark.parametrize("mode", ["filtered", "full"])
@pytest.mark.parametrize("output_format", ["plain_text", "markdown"])
@pytest.mark.parametrize("editorial_mode", ["standard", "focused"])
@pytest.mark.parametrize("description", [None, "  MATRIX_DESCRIPTION_SENTINEL\n😀\n"])
def test_description_is_independent_of_mode_and_editing(
    source, monkeypatch, mode, output_format, editorial_mode, description
):
    metadata, calls, _ = source
    metadata = replace(metadata, description=description)
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(VTT, "en", False, metadata),
    )
    edits = []

    def edit(body, **kwargs):
        assert "MATRIX_DESCRIPTION_SENTINEL" not in body + repr(kwargs)
        edits.append((body, kwargs))
        return "Edited captions."

    monkeypatch.setattr(formatter, "ensure_pi", lambda: "fake-pi")
    monkeypatch.setattr(formatter, "format_with_pi", edit)
    payload = {
        "operation": "get_transcript",
        "url": URL,
        "mode": mode,
        "sponsorblock": {
            "enabled": True,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
    }
    if output_format == "markdown":
        payload.update(
            output_format="markdown",
            formatting=asdict(MCPFormattingPolicy(editorial_mode=editorial_mode)),
        )
    result = dispatch(validate_request(payload))
    service.validate_service_result("get_transcript", result)
    assert result["metadata"]["description"] == description
    assert result["character_count"] == len(result["document"])
    assert "MATRIX_DESCRIPTION_SENTINEL" not in result["document"]
    assert result["metadata"]["sponsorblock"]["removal_applied"] == (mode == "filtered")
    assert calls == (["lookup"] if mode == "filtered" else [])
    if output_format == "markdown":
        expected = (
            "intro cross useful subject"
            if mode == "filtered"
            else "intro promo cross useful subject"
        )
        assert len(edits) == 1 and edits[0][0] == expected
        assert edits[0][1]["editorial_mode"] == editorial_mode
        assert result["document"] == "Edited captions."
    else:
        assert edits == []
        assert ("promo" in result["document"]) == (mode == "full")


def test_disabled_filtered_returns_full_without_lookup(source):
    _, calls, _ = source
    result = service.fetch_transcript_document(
        URL, sponsorblock=SponsorBlockConfig(enabled=False)
    )
    assert calls == ["download"] and "promo" in result["document"]
    assert result["metadata"]["sponsorblock"]["status"] == "disabled"


@pytest.mark.parametrize(
    "status,reason",
    [
        ("not_found", None),
        ("lookup_failed", "LOOKUP_FAILED"),
        ("lookup_failed", "ALIGNMENT_UNVERIFIED"),
    ],
)
def test_lookup_fallback_keeps_source_and_safe_warning(
    source, monkeypatch, status, reason
):
    monkeypatch.setattr(
        service,
        "lookup_sponsorblock",
        lambda *args, **kwargs: SponsorBlockLookup(True, status, reason_code=reason),
    )
    result = service.fetch_transcript_document(URL)
    assert "promo" in result["document"]
    sb = result["metadata"]["sponsorblock"]
    assert not sb["removal_applied"] and sb["removed_cue_count"] == 0
    assert bool(sb["warning"]) == (status == "lookup_failed")


def test_chapter_labels_source_order_and_raw_compatibility(source, monkeypatch):
    metadata, _, _ = source
    metadata = replace(
        metadata,
        chapters=(Chapter("Introduction", 0, 5000), Chapter("Topic", 5000, 10000)),
        chapter_status="available",
    )
    monkeypatch.setattr(
        service,
        "download_english_vtt",
        lambda url: DownloadedCaptions(VTT, "en", False, metadata),
    )
    result = service.fetch_transcript_document(URL, "full")
    assert "Chapter 1 [00:00 - 00:05]: Introduction" in result["document"]
    assert "Chapter 2 [00:05 - 00:10]: Topic" in result["document"]
    assert (
        service.fetch_clean_transcript(URL).body == "intro promo cross useful subject"
    )


def test_sdk_two_mode_schema_and_omitted_equivalence():
    class Runner:
        calls = []

        async def close(self):
            pass

        async def run(self, payload):
            self.calls.append(payload)
            cleaned = service.CleanedTranscript(
                "ok", VideoMetadata(URL, "abcdefghijk"), "en", False
            )
            return {
                "format": "plain_text",
                "document": cleaned.body,
                "metadata": cleaned.mapping(),
                "character_count": 2,
            }

    async def check():
        runner = Runner()
        async with Client(create_server(AppConfig(), runner=runner)) as client:
            tools = (await client.list_tools()).tools
            schema = tools[0].input_schema
            assert schema["required"] == ["url"]
            assert set(schema["properties"]["mode"]["enum"]) == {"filtered", "full"}
            assert schema["properties"]["mode"]["default"] == "filtered"
            for arguments in (
                {"url": URL},
                {"url": URL, "mode": "filtered"},
                {"url": URL, "mode": "full"},
            ):
                assert not (
                    await client.call_tool("get_transcript", arguments)
                ).is_error
            assert runner.calls[0] == runner.calls[1]
            assert runner.calls[0]["sponsorblock"]["enabled"] is True
            assert runner.calls[2]["sponsorblock"]["enabled"] is False
            for mode in ("default", "private token", True, {}, None):
                assert (
                    await client.call_tool("get_transcript", {"url": URL, "mode": mode})
                ).is_error
            assert len(runner.calls) == 3

    asyncio.run(check())


def test_worker_strict_policy_and_full_forces_disable(source):
    request = {
        "operation": "get_transcript",
        "url": URL,
        "mode": "full",
        "sponsorblock": {
            "enabled": True,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
    }
    validate_request(request)
    result = dispatch(request)
    assert source[1] == ["download"] and "promo" in result["document"]
    for policy in (
        {"enabled": None, "categories": ["sponsor"], "timeout_seconds": 10},
        {"enabled": True, "categories": ["filler"], "timeout_seconds": 10},
        {"enabled": True, "categories": ["sponsor"], "timeout_seconds": True},
    ):
        with pytest.raises(ValueError):
            validate_request({**request, "sponsorblock": policy})
    for operation in ("doctor", "preview_transcript"):
        with pytest.raises(ValueError):
            validate_request({**request, "operation": operation})


@pytest.mark.parametrize(
    "field,value",
    [
        ("removed_cue_count", -1),
        ("removed_cue_count", True),
        ("retained_overlap_cue_count", -1),
        ("removal_applied", False),
        ("license_url", "private"),
        ("reason_code", "private"),
    ],
)
def test_result_rejects_false_receipts_and_uncontrolled_values(source, field, value):
    result = service.fetch_transcript_document(URL)
    bad = {
        **result,
        "metadata": {
            **result["metadata"],
            "sponsorblock": {**result["metadata"]["sponsorblock"], field: value},
        },
    }
    with pytest.raises(AppError):
        service.validate_service_result("get_transcript", bad)


def test_strict_worker_result_rejects_counts_and_literal_changes(source):
    result = service.fetch_transcript_document(URL)
    service.validate_service_result("get_transcript", result)
    bad = {
        **result,
        "metadata": {
            **result["metadata"],
            "sponsorblock": {
                **result["metadata"]["sponsorblock"],
                "warning": "private token",
            },
        },
    }
    with pytest.raises(AppError):
        service.validate_service_result("get_transcript", bad)
