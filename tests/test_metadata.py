import pytest

from yt_transcript.errors import TranscriptError
from yt_transcript.metadata import extract_video_metadata

URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.mark.parametrize(
    "duration,expected",
    [(0, 0), (1.5, 1.5), (-1, None), (float("nan"), None), (True, None), ("1", None)],
)
def test_metadata(duration, expected):
    result = extract_video_metadata(
        {
            "id": "abcdefghijk",
            "duration": duration,
            "uploader": "Person",
            "uploader_id": "@handle",
            "timestamp": 0,
        },
        canonical_url=URL,
    )
    assert result.duration_seconds == expected
    assert result.channel == "Person"
    assert result.channel_id is None
    assert result.upload_date == "1970-01-01"


@pytest.mark.parametrize(
    "date,expected",
    [("20080529", "2008-05-29"), ("20230230", None), ("bad", None), ("2023011", None)],
)
def test_dates(date, expected):
    assert (
        extract_video_metadata(
            {"id": "abcdefghijk", "upload_date": date, "timestamp": 0},
            canonical_url=URL,
        ).upload_date
        == expected
    )


@pytest.mark.parametrize(
    "title",
    [
        "yes",
        "null",
        "12",
        'colon: quote" back\\slash\nline',
        "emoji 😀 café",
        "\x01control",
        "---",
    ],
)
def test_yaml_roundtrip(title):
    import yaml

    from yt_transcript.metadata import VideoMetadata, format_transcript_file

    metadata = VideoMetadata(
        URL, "abcdefghijk", title=title, upload_date="2008-05-29", duration_seconds=1.5
    )
    body = "## Heading\n\n- item\n\n```python\nprint(1)\n```"
    document = format_transcript_file(
        metadata, body, language="en-orig", automatic=True
    )
    header = document.split("---\n", 2)[1]
    values = yaml.safe_load(header)
    assert values["title"] == title
    assert values["upload_date"] == "2008-05-29"
    assert values["duration_seconds"] == 1.5
    assert values["channel"] is None
    assert document.endswith(body + "\n")
    plain = format_transcript_file(
        metadata, "plain text", language="en-orig", automatic=True
    )
    assert document.split("---\n", 2)[:2] == plain.split("---\n", 2)[:2]
    assert document == format_transcript_file(
        metadata, body, language="en-orig", automatic=True
    )


def test_mismatch():
    with pytest.raises(TranscriptError):
        extract_video_metadata({"id": "different"}, canonical_url=URL)
