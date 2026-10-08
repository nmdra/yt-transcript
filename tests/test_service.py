import pytest
import yaml

from yt_transcript import service
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.errors import AppError
from yt_transcript.metadata import VideoMetadata


@pytest.mark.parametrize(
    "description", [None, "  Description sentinel\nhttps://example.test/\n"]
)
def test_shared_document_and_plan(monkeypatch, description):
    calls = []
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk",
        "abcdefghijk",
        description=description,
    )

    def download(url):
        calls.append(url)
        return DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nhello world\n", "en", False, metadata
        )

    monkeypatch.setattr(service, "download_english_vtt", download)
    result = service.fetch_transcript_document(metadata.url)
    assert len(calls) == 1
    assert result["character_count"] == 27
    assert result["document"] == "[00:00 - 00:01] hello world"
    assert result["character_count"] == len(result["document"])
    assert result["metadata"]["caption_source"] == "manual"
    assert len(result["metadata"]) == 14
    assert result["metadata"]["description"] == description
    service.validate_service_result("get_transcript", result)
    cleaned = service.CleanedTranscript("hello world", metadata, "en", False)
    assert yaml.safe_load(cleaned.document().split("---\n", 2)[1]) == cleaned.mapping()
    assert cleaned.mapping()["description"] == description


@pytest.mark.parametrize("value", [True, 1, [], {"private-description": "sentinel"}])
def test_description_type_validation_is_safe(value, caplog):
    cleaned = service.CleanedTranscript(
        "body",
        VideoMetadata("https://youtu.be/abcdefghijk", "abcdefghijk"),
        "en",
        False,
    )
    result = {
        "format": "plain_text",
        "document": "body",
        "metadata": {**cleaned.mapping(), "description": value},
        "character_count": 4,
    }
    with pytest.raises(AppError) as exc:
        service.validate_service_result("get_transcript", result)
    assert exc.value.info.code == "INTERNAL_ERROR"
    assert exc.value.info.message == "Worker operation failed."
    assert "private-description" not in str(exc.value) + caplog.text


def test_description_is_required_even_when_nullable():
    cleaned = service.CleanedTranscript(
        "body",
        VideoMetadata("https://youtu.be/abcdefghijk", "abcdefghijk"),
        "en",
        False,
    )
    mapping = dict(cleaned.mapping())
    del mapping["description"]
    with pytest.raises(AppError) as exc:
        service.validate_service_result(
            "get_transcript",
            {
                "format": "plain_text",
                "document": "body",
                "metadata": mapping,
                "character_count": 4,
            },
        )
    assert exc.value.info.code == "INTERNAL_ERROR"
