import pytest

from yt_transcript.chapters import (
    Chapter,
    build_chapter_sections,
    normalize_chapters,
    render_timed_text,
    snapshot_chapters,
)
from yt_transcript.cleaner import Cue, clean_vtt, clean_vtt_timed


def test_normalize_and_snapshot():
    data = [{"title": "One", "start_time": 0}, {"title": "Two", "start_time": 2.5}]
    snapshot = snapshot_chapters(data)
    data[0]["title"] = "mutated"
    result = normalize_chapters(snapshot, duration_seconds=10)
    assert result.status == "available"
    assert result.chapters == (Chapter("One", 0, 2500), Chapter("Two", 2500, 10000))


@pytest.mark.parametrize(
    "value",
    [
        "bad",
        [{}],
        [{"title": "", "start_time": 0}],
        [{"title": "x", "start_time": True}],
        [{"title": "x", "start_time": float("nan")}],
        [{"title": "x", "start_time": 10**400}],
        [{"title": "x", "start_time": -1}],
        [{"title": "x", "start_time": 0, "end_time": "bad"}],
        [{"title": "x", "start_time": 0, "end_time": 0}],
        [{"title": "x", "start_time": 0}, {"title": "y", "start_time": 0}],
        [{"title": "x" * 257, "start_time": 0}],
        [{"title": "x", "start_time": i} for i in range(257)],
        [
            {"title": "x", "start_time": 0, "end_time": 6},
            {"title": "y", "start_time": 5},
        ],
        [{"title": "x", "start_time": 0}, {"title": "y", "start_time": 0.0001}],
    ],
)
def test_invalid(value):
    assert normalize_chapters(value, duration_seconds=10).status == "invalid"


@pytest.mark.parametrize("value", [None, []])
def test_unavailable(value):
    assert normalize_chapters(value, duration_seconds=None).status == "unavailable"


def test_unknown_end_gaps_and_repeated_titles():
    result = normalize_chapters(
        [
            {"title": "x", "start_time": 2, "end_time": 3},
            {"title": "x", "start_time": 5},
        ],
        duration_seconds=None,
    )
    assert result.chapters == (Chapter("x", 2000, 3000), Chapter("x", 5000, None))


def test_runs_boundary_and_backward_order():
    cues = (
        Cue(0, 1000, "unassigned"),
        Cue(1000, 3000, "first"),
        Cue(2000, 4000, "second"),
        Cue(1000, 2000, "revisit"),
    )
    sections = build_chapter_sections(
        cues, (Chapter("A", 1000, 2000), Chapter("B", 2000, 4000))
    )
    assert [s.chapter_index for s in sections] == [None, 0, 1, 0]
    assert " ".join(s.text for s in sections) == " ".join(c.text for c in cues)


def test_timed_cleanup_preserves_rolling_timing():
    data = "WEBVTT\n\n00:00.000 --> 00:02.000\none two\n\n00:01.000 --> 00:03.000\none two three\n"
    assert clean_vtt_timed(data, automatic=True) == (
        Cue(0, 2000, "one two"),
        Cue(1000, 3000, "three"),
    )
    assert clean_vtt(data, automatic=True) == "one two three"


def test_timed_render_long_cue_and_hour_fractional_precision():
    cues = (Cue(3600001, 3620001, "long"), Cue(3620001, 3621001, "next"))
    text = render_timed_text(cues, source_indices=(0, 1))
    assert (
        text
        == "[01:00:00.001 - 01:00:20.001] long\n\n[01:00:20.001 - 01:00:21.001] next"
    )


def test_timed_render_breaks_removed_and_backward_gaps():
    cues = (Cue(0, 1000, "a"), Cue(2000, 3000, "b"), Cue(1000, 4000, "c"))
    text = render_timed_text(cues, source_indices=(0, 2, 3))
    assert text == "[00:00 - 00:01] a\n\n[00:02 - 00:03] b\n\n[00:01 - 00:04] c"
