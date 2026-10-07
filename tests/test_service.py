from yt_transcript import service
from yt_transcript.downloader import DownloadedCaptions
from yt_transcript.metadata import VideoMetadata


def test_shared_document_and_plan(monkeypatch):
    calls = []
    metadata = VideoMetadata(
        "https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"
    )

    def download(url):
        calls.append(url)
        return DownloadedCaptions(
            b"WEBVTT\n\n00:00.000 --> 00:01.000\nhello world\n", "en", False, metadata
        )

    monkeypatch.setattr(service, "download_english_vtt", download)
    result = service.fetch_transcript_document(metadata.url)
    assert len(calls) == 1
    assert result["character_count"] == 11
    assert result["document"].endswith("\n\nhello world\n")
    assert result["metadata"]["caption_source"] == "manual"
    assert len(result["metadata"]) == 10
    preview = service.preview_transcript_data(
        metadata.url,
        chunk_chars=1000,
        max_chunks=1,
        model_description="Pi configured default",
    )
    assert preview["within_cap"] and preview["planned_invocations"] == 1
    assert "document" not in preview
