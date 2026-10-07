"""Explicit operator-only live smoke checks. Never part of offline acceptance."""

import os
import subprocess
import sys

import pytest
import yaml

from yt_transcript.downloader import validate_youtube_url

URL = os.environ.get("YT_TRANSCRIPT_TEST_URL")
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
    os.environ.get("YT_TRANSCRIPT_TEST_PI") != "1",
    reason="Separate explicit operator model-spend approval required",
)
def test_live_pi(tmp_path):
    # Operator must supply approval before enabling this test. Structure is not semantic proof.
    path = tmp_path / "edited.md"
    result = invoke("-o", str(path))
    assert result.returncode == 0 and not result.stdout
    _, header, body = path.read_text().split("---\n", 2)
    values = yaml.safe_load(header)
    assert URL is not None
    assert values["url"] == validate_youtube_url(URL)
    assert body.strip() and not body.lstrip().startswith(("---", "```"))
