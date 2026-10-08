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


@pytest.mark.parametrize("value", [None, "", " \t\r\n", True, 7, [], {}])
def test_invalid_description_becomes_null(value):
    from yt_transcript.metadata import metadata_mapping

    metadata = extract_video_metadata(
        {"id": "abcdefghijk", "description": value}, canonical_url=URL
    )
    assert metadata.description is None
    assert (
        metadata_mapping(metadata, language="en", automatic=False)["description"]
        is None
    )


def test_missing_description_becomes_null():
    from yt_transcript.metadata import metadata_mapping

    metadata = extract_video_metadata({"id": "abcdefghijk"}, canonical_url=URL)
    assert metadata.description is None
    assert (
        metadata_mapping(metadata, language="en", automatic=False)["description"]
        is None
    )


@pytest.mark.parametrize(
    "description",
    [
        '  colon: quote" back\\slash\r\nline  \n',
        "emoji 😀 café\n\n",
        "\x01control",
        "---\nurl: https://invalid.example/\n---\n",
        "00:00 Intro\nhttps://example.test/?token=published\n<b>markup</b>",
        "null",
    ],
)
def test_description_roundtrip(description):
    import json

    import yaml

    from yt_transcript.metadata import format_transcript_file, metadata_mapping

    metadata = extract_video_metadata(
        {"id": "abcdefghijk", "description": description}, canonical_url=URL
    )
    assert metadata.description == description
    mapping = metadata_mapping(metadata, language="en", automatic=False)
    assert json.loads(json.dumps(mapping)) == mapping
    body = "## Heading\n\nCaption text."
    document = format_transcript_file(metadata, body, language="en", automatic=False)
    _, header, rendered_body = document.split("---\n", 2)
    assert yaml.safe_load(header) == mapping
    assert yaml.safe_load(header)["description"] == description
    assert rendered_body == "\n" + body + "\n"
    assert document == format_transcript_file(
        metadata, body, language="en", automatic=False
    )


def test_description_preserves_positional_fields_and_mapping_prefix():
    from yt_transcript.chapters import Chapter
    from yt_transcript.metadata import VideoMetadata, metadata_mapping
    from yt_transcript.sponsorblock import SponsorBlockLookup

    chapters = (Chapter("Intro", 0, 1000),)
    lookup = SponsorBlockLookup()
    metadata = VideoMetadata(
        URL,
        "abcdefghijk",
        "Title",
        "Channel",
        "UCid",
        "https://example.test/channel",
        "2008-05-29",
        1.5,
        chapters,
        "available",
        lookup,
    )
    assert (
        metadata.url,
        metadata.video_id,
        metadata.title,
        metadata.channel,
        metadata.channel_id,
        metadata.channel_url,
        metadata.upload_date,
        metadata.duration_seconds,
        metadata.chapters,
        metadata.chapter_status,
        metadata.sponsorblock,
    ) == (
        URL,
        "abcdefghijk",
        "Title",
        "Channel",
        "UCid",
        "https://example.test/channel",
        "2008-05-29",
        1.5,
        chapters,
        "available",
        lookup,
    )
    assert metadata.description is None
    mapping = metadata_mapping(metadata, language="en", automatic=False)
    assert list(mapping) == [
        "url",
        "video_id",
        "title",
        "channel",
        "channel_id",
        "channel_url",
        "upload_date",
        "duration_seconds",
        "caption_language",
        "caption_source",
        "chapter_status",
        "chapters",
        "sponsorblock",
        "description",
    ]
