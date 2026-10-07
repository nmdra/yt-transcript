import pytest

from yt_transcript.cleaner import Cue, clean_vtt, parse_vtt
from yt_transcript.errors import TranscriptError


def make_vtt(cues):
    return (
        "WEBVTT\n\n"
        + "\n\n".join(f"{start} --> {end}\n{text}" for start, end, text in cues)
        + "\n"
    )


def test_parser():
    text = "\ufeffWEBVTT\r\nKind: captions\r\n\r\nNOTE ignored\r\nprivate\r\n\r\nSTYLE\r\n::cue {}\r\n\r\nid\r\n00:01:00.000 --> 00:01:02.100 align:start\r\n<v Person><c.red>Hello</c></v> &amp; &lt;literal&gt;\r\n42 NOTE 😀"
    assert parse_vtt(text) == [Cue(60000, 62100, "Hello & <literal> 42 NOTE 😀")]


@pytest.mark.parametrize(
    "text",
    [
        "bad",
        "WEBVTT\n\nbad",
        "WEBVTT\n\n00:00.000 --> 00:99.000\ntext",
        "WEBVTT\n\n00:02.000 --> 00:01.000\ntext",
        "WEBVTT\n\n00:0٠.000 --> 00:01.000\ntext",
        "WEBVTT\n\n" + "9" * 5000 + ":00:00.000 --> 00:01.000\ntext",
    ],
)
def test_invalid(text):
    with pytest.raises(TranscriptError):
        parse_vtt(text)


@pytest.mark.parametrize(
    "automatic,second,start,expected",
    [
        (True, "first thing i want", "00:00.900", "so the first thing i want"),
        (True, "so the first thing", "00:00.900", "so the first thing"),
        (True, "the first thing", "00:00.900", "so the first thing"),
        (
            True,
            "so the first thing",
            "00:02.000",
            "so the first thing so the first thing",
        ),
        (
            False,
            "so the first thing",
            "00:00.900",
            "so the first thing so the first thing",
        ),
        (True, "Thing again", "00:00.900", "so the first thing Thing again"),
    ],
)
def test_rolling(automatic, second, start, expected):
    vtt = make_vtt(
        [("00:00.000", "00:01.000", "so the first thing"), (start, "00:03.000", second)]
    )
    assert clean_vtt(vtt, automatic=automatic) == expected


def test_three_cues():
    vtt = make_vtt(
        [
            ("00:00.000", "00:01.000", "so the first thing"),
            ("00:00.900", "00:02.000", "first thing i want"),
            ("00:01.900", "00:03.000", "i want to talk about"),
        ]
    )
    assert clean_vtt(vtt, automatic=True) == "so the first thing i want to talk about"


def test_one_token_and_repetition():
    vtt = make_vtt(
        [
            ("00:00.000", "00:01.000", "yes"),
            ("00:00.900", "00:02.000", "yes"),
            ("00:02.000", "00:03.000", "yes yes"),
        ]
    )
    assert clean_vtt(vtt, automatic=True) == "yes yes yes"


def test_empty():
    assert parse_vtt("WEBVTT\n") == []
    with pytest.raises(TranscriptError):
        clean_vtt("WEBVTT\n", automatic=False)
