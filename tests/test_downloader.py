import pytest

from yt_transcript.downloader import select_english_track, validate_youtube_url
from yt_transcript.errors import TranscriptError

ID = "abcdefghijk"


@pytest.mark.parametrize(
    "url",
    [
        f"https://youtu.be/{ID}",
        f"http://m.youtube.com/watch?v={ID}&list=abc",
        f"https://youtube.com/shorts/{ID}",
        f"https://www.youtube.com/embed/{ID}",
    ],
)
def test_urls(url):
    assert validate_youtube_url(url) == f"https://www.youtube.com/watch?v={ID}"


@pytest.mark.parametrize(
    "url",
    [
        "abcdefghijk",
        "https://youtube.com.evil/watch?v=abcdefghijk",
        "https://user@youtube.com/watch?v=abcdefghijk",
        "https://@youtube.com/watch?v=abcdefghijk",
        "https://:@youtube.com/watch?v=abcdefghijk",
        "https://youtube.com/playlist?list=abc",
        "https://youtube.com/channel/abc",
        "ftp://youtu.be/abcdefghijk",
        "https://youtu.be/abcdefghijk/extra",
    ],
)
def test_bad_urls(url):
    with pytest.raises(TranscriptError):
        validate_youtube_url(url)


@pytest.mark.parametrize("first_available", range(6))
def test_caption_priority_order(first_available):
    ordered = [
        ("subtitles", "en"),
        ("subtitles", "en-GB"),
        ("automatic_captions", "en-orig"),
        ("automatic_captions", "en-GB-orig"),
        ("automatic_captions", "en"),
        ("automatic_captions", "en-GB"),
    ]
    info = {"subtitles": {}, "automatic_captions": {}}
    for source, language in reversed(ordered[first_available:]):
        info[source][language] = [{"ext": "vtt"}]
    track = select_english_track(info)
    source, language = ordered[first_available]
    assert track.language == language
    assert track.automatic == (source == "automatic_captions")


def test_caption_priority_preserves_case_and_lexical_ties():
    formats = [{"ext": "vtt"}]
    assert (
        select_english_track(
            {"subtitles": {"en-US": formats, "en-GB": formats}}
        ).language
        == "en-GB"
    )
    assert (
        select_english_track({"subtitles": {"en": formats, "EN": formats}}).language
        == "EN"
    )


def test_real_upstream_selection():
    from typing import Any, cast

    from yt_dlp import YoutubeDL

    from yt_transcript.downloader import retry_delay

    assert [retry_delay(n) for n in range(5)] == [1, 2, 4, 4, 4]
    with YoutubeDL(
        cast(
            Any,
            {
                "quiet": True,
                "writesubtitles": True,
                "subtitleslangs": ["^en$"],
                "subtitlesformat": "vtt",
                "cachedir": False,
            },
        )
    ) as ydl:
        selected = ydl.process_subtitles(
            ID, {"en": [{"ext": "vtt", "url": "synthetic"}]}, {}
        )
    assert selected is not None and selected["en"]["ext"] == "vtt"


def test_download_orchestration(monkeypatch):
    from pathlib import Path

    import yt_transcript.downloader as module

    calls = []
    roots = []

    class FakeDL:
        def __init__(self, params):
            self.params = params
            roots.append(Path(params["outtmpl"]).parent)
            assert params["socket_timeout"] == 30
            assert params["retries"] == params["extractor_retries"] == 3
            assert params["skip_download"] and params["cachedir"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, **kwargs):
            calls.append(("extract", kwargs))
            return {
                "id": ID,
                "duration": 10,
                "chapters": [{"title": "Original", "start_time": 0}],
                "description": "Extracted description",
                "automatic_captions": {
                    "en-orig": [{"ext": "vtt", "url": "synthetic"}, {"ext": "srt"}]
                },
                "subtitles": {},
            }

        def process_ie_result(self, info, **kwargs):
            calls.append(("process", kwargs))
            assert info["description"] == "Extracted description"
            assert "chapters" not in info
            info["chapters"] = [{"title": "<Untitled Chapter 1>", "start_time": 0}]
            assert not info["subtitles"]
            assert list(info["automatic_captions"]) == ["en-orig"]
            assert len(info["automatic_captions"]["en-orig"]) == 1
            assert (
                self.params["writeautomaticsub"] and not self.params["writesubtitles"]
            )
            path = roots[0] / "captions.en-orig.vtt"
            path.write_bytes(b"WEBVTT\r\n\r\n00:00.000 --> 00:01.000\r\nhello\r\n")
            return {
                **info,
                "requested_subtitles": {
                    "en-orig": {"ext": "vtt", "filepath": str(path)}
                },
                "description": "Processed description\nhttps://example.test/\n",
            }

    monkeypatch.setattr(module, "ensure_deno", lambda: None)
    monkeypatch.setattr(module, "YoutubeDL", FakeDL)
    result = module.download_english_vtt(f"https://youtu.be/{ID}")
    assert result.vtt.endswith(b"hello\r\n")
    assert result.metadata.chapters[0].title == "Original"
    assert (
        result.metadata.description == "Processed description\nhttps://example.test/\n"
    )
    assert calls == [
        ("extract", {"download": False, "process": False}),
        ("process", {"download": True}),
    ]
    assert not roots[0].exists()


@pytest.fixture
def fake_download(monkeypatch, tmp_path):
    from pathlib import Path
    from types import SimpleNamespace

    from yt_transcript import downloader as module

    state = SimpleNamespace(
        info={
            "id": ID,
            "subtitles": {"en": [{"ext": "vtt"}]},
            "automatic_captions": {},
        },
        failure=None,
        path_mode="normal",
        processed=0,
        root=None,
        params=None,
        warning=None,
    )

    class FakeDL:
        def __init__(self, params):
            self.params = params
            state.params = params
            state.root = Path(params["outtmpl"]).parent

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, *args, **kwargs):
            if state.warning:
                self.params["logger"].warning(state.warning)
            return state.info

        def process_ie_result(self, info, **kwargs):
            state.processed += 1
            assert "chapters" not in info
            if state.failure:
                raise state.failure
            language = next(iter(info["subtitles"] or info["automatic_captions"]))
            path = state.root / "captions.en.vtt"
            if state.path_mode == "outside":
                path = tmp_path / "outside.vtt"
            if state.path_mode != "missing":
                path.write_bytes(b"" if state.path_mode == "empty" else b"WEBVTT\n")
            if state.path_mode == "multiple":
                (state.root / "extra.vtt").write_bytes(b"WEBVTT\n")
            return {
                **info,
                "requested_subtitles": {
                    language: {
                        "filepath": str(path),
                        "ext": "srt" if state.path_mode == "nonvtt" else "vtt",
                    }
                },
            }

    monkeypatch.setattr(module, "ensure_deno", lambda: None)
    monkeypatch.setattr(module, "YoutubeDL", FakeDL)
    return state


@pytest.mark.parametrize(
    "status,accepted",
    [
        ("is_live", False),
        ("is_upcoming", False),
        ("post_live", False),
        ("was_live", True),
        ("not_live", True),
        (None, True),
        ("unknown", True),
    ],
)
def test_livestream_guard(fake_download, status, accepted):
    from yt_transcript.downloader import download_english_vtt

    fake_download.info["live_status"] = status
    if accepted:
        download_english_vtt(f"https://youtu.be/{ID}")
        assert fake_download.processed == 1
    else:
        with pytest.raises(TranscriptError) as exc:
            download_english_vtt(f"https://youtu.be/{ID}")
        assert exc.value.info.code == "UNSUPPORTED_LIVESTREAM"
        assert fake_download.processed == 0
    assert not fake_download.root.exists()


@pytest.mark.parametrize("mode", ["missing", "empty", "outside", "multiple", "nonvtt"])
def test_file_validation(fake_download, mode):
    from yt_transcript.downloader import download_english_vtt

    fake_download.path_mode = mode
    with pytest.raises(TranscriptError) as exc:
        download_english_vtt(f"https://youtu.be/{ID}")
    assert exc.value.info.code == "SUBTITLE_DOWNLOAD_FAILED"
    assert not fake_download.root.exists()


@pytest.mark.parametrize(
    "warning,code",
    [
        ("ordinary secret warning", "NO_ENGLISH_CAPTIONS"),
        (
            "Some web client subtitles require a PO Token which was not provided. private secret",
            "YOUTUBE_ACCESS_LIMITED",
        ),
    ],
)
def test_warning_missing_captions(fake_download, warning, code):
    from yt_transcript.downloader import download_english_vtt

    fake_download.info["subtitles"] = {}
    fake_download.warning = warning
    with pytest.raises(TranscriptError) as exc:
        download_english_vtt(f"https://youtu.be/{ID}")
    assert exc.value.info.code == code
    assert fake_download.processed == 0


@pytest.mark.parametrize(
    "chapters", ["bad", [None], [{"title": "x", "start_time": True}]]
)
def test_optional_malformed_chapters_do_not_reach_processor(fake_download, chapters):
    from yt_transcript.downloader import download_english_vtt

    fake_download.info["chapters"] = chapters
    result = download_english_vtt(f"https://youtu.be/{ID}")
    assert result.metadata.chapter_status == "invalid"
    assert not result.metadata.chapters and fake_download.processed == 1


def test_manual_options_and_valid_warning(fake_download):
    from yt_transcript.downloader import download_english_vtt

    fake_download.warning = "unknown secret warning"
    download_english_vtt(f"https://youtu.be/{ID}")
    assert fake_download.params["writesubtitles"]
    assert not fake_download.params["writeautomaticsub"]
    assert fake_download.params["subtitleslangs"] == ["^en$"]
    assert fake_download.params["remote_components"] == set()
    assert not fake_download.root.exists()


def test_subtitle_failure_no_retry(fake_download):
    from yt_dlp.utils import DownloadError

    from yt_transcript.downloader import download_english_vtt

    fake_download.failure = DownloadError("private secret")
    with pytest.raises(TranscriptError) as exc:
        download_english_vtt(f"https://youtu.be/{ID}")
    assert exc.value.info.code == "SUBTITLE_DOWNLOAD_FAILED"
    assert fake_download.processed == 1
    assert not fake_download.root.exists()


def test_ranking():
    vtt = [{"ext": "vtt", "url": "private"}]
    info = {
        "subtitles": {"en-z": vtt, "en-a": vtt, "en": vtt},
        "automatic_captions": {"en-orig": vtt, "en": vtt},
    }
    assert select_english_track(info).language == "en"
    del info["subtitles"]["en"]
    assert select_english_track(info).language == "en-a"
    info["subtitles"] = {}
    assert select_english_track(info).language == "en-orig"
    del info["automatic_captions"]["en-orig"]
    info["automatic_captions"]["en-GB-orig"] = vtt
    assert select_english_track(info).language == "en-GB-orig"
    del info["automatic_captions"]["en-GB-orig"]
    assert select_english_track(info).language == "en"


@pytest.mark.parametrize(
    "info,code",
    [
        ({"subtitles": {"english": [{"ext": "vtt"}]}}, "NO_ENGLISH_CAPTIONS"),
        ({"subtitles": {"en": [{"ext": "srt"}]}}, "NO_ENGLISH_VTT"),
    ],
)
def test_missing(info, code):
    with pytest.raises(TranscriptError) as exc:
        select_english_track(info)
    assert exc.value.info.code == code
