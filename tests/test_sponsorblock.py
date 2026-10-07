import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from yt_transcript.cleaner import Cue
from yt_transcript.sponsorblock import (
    SponsorBlockConfig,
    SponsorBlockLookup,
    SponsorBlockSegment,
    compute_receipt,
    lookup_sponsorblock,
    project_sponsorblock,
    sponsorblock_mapping,
)

ID = "abcdefghijk"
CONFIG = SponsorBlockConfig(enabled=True)


def row(**overrides):
    return {
        "category": "sponsor",
        "actionType": "skip",
        "segment": [1, 3],
        "votes": 1,
        "locked": True,
        "videoDuration": 10,
        **overrides,
    }


def lookup(rows, **kwargs):
    return lookup_sponsorblock(
        ID,
        config=CONFIG,
        duration_seconds=10,
        transport=lambda path, timeout: (
            200,
            json.dumps([{"videoID": ID, "segments": rows}]).encode(),
        ),
        **kwargs,
    )


def test_https_transport_is_fixed_bounded_and_redirect_free(monkeypatch):
    from yt_transcript import sponsorblock

    calls = []

    class Response:
        status = 302

        def read(self, count):
            calls.append(("read", count))
            return b"redirect"

    class Connection:
        def __init__(self, host, **kwargs):
            assert host == "sponsor.ajay.app" and kwargs["timeout"] == 10
            assert kwargs["context"].check_hostname

        def request(self, method, path, *, headers):
            calls.append((method, path, headers))

        def getresponse(self):
            return Response()

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(sponsorblock.http.client, "HTTPSConnection", Connection)
    result = lookup_sponsorblock(ID, config=CONFIG, duration_seconds=10)
    assert result.status == "lookup_failed"
    assert calls[0][0] == "GET" and set(calls[0][2]) == {"User-Agent", "Accept"}
    assert calls[1] == ("read", sponsorblock.BODY_LIMIT + 1) and calls[-1] == "closed"
    assert len(calls) == 3


def test_prefix_request_and_local_matching():
    calls = []

    def transport(path, timeout):
        calls.append((path, timeout))
        return 200, json.dumps(
            [
                {"videoID": "other", "segments": [row()]},
                {"videoID": ID, "segments": [row(locked=1)]},
            ]
        ).encode()

    result = lookup_sponsorblock(
        ID, config=CONFIG, duration_seconds=10, transport=transport
    )
    assert result.status == "available" and result.segments[0].locked is True
    path, timeout = calls[0]
    assert ID not in path and hashlib.sha256(ID.encode()).hexdigest()[:4] in path
    query = parse_qs(urlsplit(path).query)
    assert json.loads(query["categories"][0]) == list(CONFIG.categories)
    assert json.loads(query["actionTypes"][0]) == ["skip"] and timeout == 10


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"segment": [True, 3]}, "INVALID_RESPONSE"),
        ({"segment": [3, 1]}, "INVALID_RESPONSE"),
        ({"segment": [1, float("nan")]}, "INVALID_RESPONSE"),
        ({"votes": True}, "INVALID_RESPONSE"),
        ({"locked": 2}, "INVALID_RESPONSE"),
        ({"videoDuration": 0}, "ALIGNMENT_UNVERIFIED"),
        ({"videoDuration": 12}, "ALIGNMENT_UNVERIFIED"),
    ],
)
def test_invalid_eligible_rows(overrides, reason):
    result = lookup([row(**overrides)])
    assert result.status == "lookup_failed" and result.reason_code == reason
    assert not result.segments and result.warning


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (404, b"ignored", "not_found"),
        (200, b"[]", "not_found"),
        (200, b"bad", "lookup_failed"),
        (302, b"", "lookup_failed"),
        (200, b"x" * 524289, "lookup_failed"),
    ],
)
def test_response_fallback(status, body, expected):
    result = lookup_sponsorblock(
        ID, config=CONFIG, duration_seconds=10, transport=lambda *args: (status, body)
    )
    assert result.status == expected


@pytest.mark.parametrize(
    "body",
    [
        b"[" * 2000 + b"]" * 2000,
        b'[{"videoID":"abcdefghijk","videoID":"abcdefghijk","segments":[]}]',
        b'[{"videoID":"other","segments":[],"bad":NaN}]',
    ],
    ids=["deep", "duplicate", "nonfinite"],
)
def test_non_strict_or_deep_json_falls_back(body):
    result = lookup_sponsorblock(
        ID, config=CONFIG, duration_seconds=10, transport=lambda *args: (200, body)
    )
    assert result.status == "lookup_failed" and result.reason_code == "INVALID_RESPONSE"
    assert result.warning and not result.segments


def test_disabled_cancellation_and_timeout():
    def forbidden(*args):
        raise AssertionError("transport must not run")

    assert (
        lookup_sponsorblock(
            ID,
            config=SponsorBlockConfig(enabled=False),
            duration_seconds=10,
            transport=forbidden,
        ).status
        == "disabled"
    )

    def cancel(*args):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        lookup_sponsorblock(ID, config=CONFIG, duration_seconds=10, transport=cancel)

    def timeout(*args):
        raise TimeoutError("private token")

    result = lookup_sponsorblock(
        ID, config=CONFIG, duration_seconds=10, transport=timeout
    )
    assert result.reason_code == "LOOKUP_FAILED" and "private" not in (
        result.warning or ""
    )


def test_ignored_rows_and_duplicate_buckets():
    assert (
        lookup([row(votes=-1), row(category="filler"), row(actionType="full")]).status
        == "not_found"
    )
    result = lookup_sponsorblock(
        ID,
        config=CONFIG,
        duration_seconds=10,
        transport=lambda *args: (
            200,
            json.dumps(
                [{"videoID": ID, "segments": []}, {"videoID": ID, "segments": []}]
            ).encode(),
        ),
    )
    assert result.reason_code == "INVALID_RESPONSE"


def test_union_containment_and_unique_receipts():
    segments = (
        SponsorBlockSegment(1000, 2000, "sponsor", 1, True),
        SponsorBlockSegment(2000, 3000, "selfpromo", 1, False),
    )
    source = SponsorBlockLookup(True, "available", CONFIG.categories, segments)
    cues = (
        Cue(0, 500, "keep"),
        Cue(1000, 3000, "drop"),
        Cue(2500, 3500, "cross"),
        Cue(1500, 1500, "point"),
    )
    projection = project_sponsorblock(cues, source)
    assert projection.body == "keep cross point"
    assert projection.removed_indices == (1,) and projection.source_indices == (0, 2, 3)
    assert projection.receipt.removed_cue_count == 1
    assert [r.removal_status for r in projection.receipt.segments] == [
        "partial",
        "partial",
    ]
    assert projection.receipt.retained_overlap_cue_count == 2
    raw = sponsorblock_mapping(source, compute_receipt(cues, source))
    filtered = sponsorblock_mapping(source, projection.receipt)
    assert not raw["removal_applied"] and filtered["removal_applied"]
    assert all(r["removal_status"] == "not_applied" for r in raw["segments"])


def test_all_removal_rolls_back():
    source = lookup([row()])
    projection = project_sponsorblock((Cue(1000, 2000, "keep"),), source)
    assert projection.body == "keep"
    assert projection.lookup.reason_code == "REMOVAL_WOULD_EMPTY"
    assert projection.lookup.segments
    assert projection.receipt.segments[0].removal_status == "not_applied"


def test_removed_kept_and_no_matching():
    source = lookup([row(), row(segment=[5, 6])])
    p = project_sponsorblock((Cue(1000, 2000, "drop"), Cue(8000, 9000, "keep")), source)
    assert [r.removal_status for r in p.receipt.segments] == [
        "removed",
        "no_matching_captions",
    ]
    p = project_sponsorblock((Cue(500, 1500, "cross"),), source)
    assert p.receipt.segments[0].removal_status == "kept"
