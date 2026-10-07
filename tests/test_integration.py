"""Explicit operator-only live smoke checks. Never part of offline acceptance."""

import os
import subprocess
import sys

import pytest
import yaml

from yt_transcript.downloader import validate_youtube_url

URL = os.environ.get("YT_TRANSCRIPT_TEST_URL")
PI_MODE = os.environ.get("YT_TRANSCRIPT_TEST_EDITORIAL_MODE", "")
PI_CAP = os.environ.get("YT_TRANSCRIPT_TEST_MAX_CHUNKS", "")
PI_APPROVED = (
    os.environ.get("YT_TRANSCRIPT_TEST_PI") == "1"
    and PI_MODE in ("standard", "focused")
    and 1 <= len(PI_CAP) <= 4
    and PI_CAP.isascii()
    and PI_CAP.isdigit()
    and 1 <= int(PI_CAP) <= 1000
)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="No operator-supplied public video URL"),
]


def invoke(*args):
    assert URL is not None
    return subprocess.run(
        [sys.executable, "-m", "yt_transcript", URL, "--no-config", *args],
        capture_output=True,
        timeout=1200,
    )


def test_live_raw(tmp_path):
    assert URL is not None
    canonical = validate_youtube_url(URL)
    result = invoke("--raw")
    assert result.returncode == 0
    body = result.stdout.decode("utf-8")
    assert body.strip() and not body.startswith("WEBVTT") and "-->" not in body
    assert not body.startswith("---\n")
    path = tmp_path / "raw.txt"
    result = invoke("--raw", "-o", str(path))
    assert result.returncode == 0 and not result.stdout
    _, header, body = path.read_text().split("---\n", 2)
    values = yaml.safe_load(header)
    assert values["url"] == canonical
    assert values["video_id"] == canonical.rsplit("=", 1)[1]
    assert values["caption_language"].lower().startswith("en")
    assert values["caption_source"] in ("manual", "automatic")
    assert body.strip()


@pytest.mark.skipif(
    not PI_APPROVED,
    reason="Fresh spend approval, selected editorial mode, and preview-approved cap required",
)
def test_live_pi(tmp_path):
    # Operator must supply approval before enabling this test. Structure is not semantic proof.
    path = tmp_path / "edited.md"
    result = invoke(
        "--editorial-mode", PI_MODE, "--max-chunks", PI_CAP, "-o", str(path)
    )
    assert result.returncode == 0 and not result.stdout
    _, header, body = path.read_text().split("---\n", 2)
    values = yaml.safe_load(header)
    assert URL is not None
    assert values["url"] == validate_youtube_url(URL)
    assert body.strip() and not body.lstrip().startswith(("---", "```"))


@pytest.mark.skipif(
    os.environ.get("YT_TRANSCRIPT_TEST_CHAPTERS") != "1",
    reason="Confirmed chapter-bearing operator URL required",
)
def test_live_chapters(tmp_path):
    path = tmp_path / "chapters.txt"
    result = invoke("--raw", "-o", str(path))
    assert result.returncode == 0 and not result.stdout
    values = yaml.safe_load(path.read_text().split("---\n", 2)[1])
    status = values["chapter_status"]
    count = len(values["chapters"])
    assert status == "available" and count > 0


@pytest.mark.skipif(
    os.environ.get("YT_TRANSCRIPT_TEST_SPONSORBLOCK") != "1"
    or os.environ.get("YT_TRANSCRIPT_TEST_SPONSORBLOCK_LICENSE_OK") != "1",
    reason="Segment-bearing operator URL and upstream license confirmation required",
)
def test_live_sponsorblock():
    from yt_transcript.service import fetch_clean_transcript
    from yt_transcript.sponsorblock import SponsorBlockConfig

    assert URL is not None
    cleaned = fetch_clean_transcript(URL, sponsorblock=SponsorBlockConfig(enabled=True))
    assert cleaned.projection is not None
    status = cleaned.projection.lookup.status
    count = cleaned.projection.receipt.removed_cue_count
    assert status == "available" and count > 0
