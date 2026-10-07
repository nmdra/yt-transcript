"""Supplied chapter validation and deterministic cue-level rendering."""

import math
import re
from dataclasses import dataclass
from typing import Literal

from .cleaner import Cue

ChapterStatus = Literal["available", "unavailable", "invalid"]


@dataclass(frozen=True)
class Chapter:
    title: str
    start_ms: int
    end_ms: int | None


@dataclass(frozen=True)
class ChapterExtraction:
    chapters: tuple[Chapter, ...] = ()
    status: ChapterStatus = "unavailable"


def milliseconds(value: object) -> int:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError
    result = round(number * 1000)
    if result > 2**63 - 1:
        raise ValueError
    return result


def snapshot_chapters(value: object) -> object:
    if not isinstance(value, list) or len(value) > 256:
        return value
    return [
        {key: row[key] for key in ("title", "start_time", "end_time") if key in row}
        if isinstance(row, dict)
        else row
        for row in value
    ]


def normalize_chapters(
    value: object, *, duration_seconds: int | float | None
) -> ChapterExtraction:
    if value is None or value == []:
        return ChapterExtraction()
    try:
        if not isinstance(value, list) or not 1 <= len(value) <= 256:
            raise ValueError
        duration = (
            milliseconds(duration_seconds) if duration_seconds is not None else None
        )
        starts = []
        for row in value:
            if not isinstance(row, dict):
                raise ValueError
            title = row.get("title")
            if not isinstance(title, str) or not title.strip() or len(title) > 256:
                raise ValueError
            start = milliseconds(row.get("start_time"))
            if starts and start <= starts[-1]:
                raise ValueError
            if duration is not None and start >= duration:
                raise ValueError
            starts.append(start)
        chapters = []
        for index, row in enumerate(value):
            next_start = starts[index + 1] if index + 1 < len(starts) else duration
            end = (
                milliseconds(row["end_time"])
                if row.get("end_time") is not None
                else next_start
            )
            if end is not None and (
                end <= starts[index] or (next_start is not None and end > next_start)
            ):
                raise ValueError
            chapters.append(Chapter(row["title"], starts[index], end))
        return ChapterExtraction(tuple(chapters), "available")
    except ValueError, OverflowError, TypeError:
        return ChapterExtraction((), "invalid")


def display_time(value: int) -> str:
    seconds, fraction = divmod(value, 1000)
    minutes, second = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    prefix = (
        f"{hours:02}:{minute:02}:{second:02}" if hours else f"{minute:02}:{second:02}"
    )
    return prefix + (f".{fraction:03}" if fraction else "")


def display_title(title: str, *, markdown: bool = False) -> str:
    title = " ".join(title.splitlines())
    title = " ".join(
        "".join(
            f"\\u{ord(c):04x}" if ord(c) < 32 or ord(c) == 127 else c for c in title
        ).split()
    )
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", title) if markdown else title


@dataclass(frozen=True)
class ChapterSection:
    run_id: int
    chapter_index: int | None
    chapter: Chapter | None
    chapter_count: int
    fragments: tuple[Cue, ...]
    source_indices: tuple[int, ...]

    @property
    def text(self) -> str:
        return " ".join(cue.text for cue in self.fragments)

    @property
    def heading(self) -> str:
        if self.chapter is None:
            return "## Unassigned captions"
        return f"## [{display_time(self.chapter.start_ms)}] {display_title(self.chapter.title, markdown=True)}"


def build_chapter_sections(
    fragments: tuple[Cue, ...],
    chapters: tuple[Chapter, ...],
    *,
    source_indices: tuple[int, ...] | None = None,
) -> tuple[ChapterSection, ...]:
    indices = (
        source_indices if source_indices is not None else tuple(range(len(fragments)))
    )
    if len(indices) != len(fragments):
        raise ValueError("Invalid fragment indices.")
    runs: list[ChapterSection] = []
    for cue, source_index in zip(fragments, indices, strict=True):
        index = next(
            (
                i
                for i, chapter in enumerate(chapters)
                if chapter.start_ms <= cue.start_ms
                and (chapter.end_ms is None or cue.start_ms < chapter.end_ms)
            ),
            None,
        )
        chapter = chapters[index] if index is not None else None
        if runs and runs[-1].chapter_index == index:
            previous = runs[-1]
            runs[-1] = ChapterSection(
                previous.run_id,
                index,
                chapter,
                len(chapters),
                (*previous.fragments, cue),
                (*previous.source_indices, source_index),
            )
        else:
            runs.append(
                ChapterSection(
                    len(runs), index, chapter, len(chapters), (cue,), (source_index,)
                )
            )
    return tuple(runs)


def render_timed_text(
    fragments: tuple[Cue, ...], *, source_indices: tuple[int, ...]
) -> str:
    if len(source_indices) != len(fragments):
        raise ValueError("Invalid fragment indices.")
    blocks = []
    group: list[Cue] = []
    previous_index = -1

    def flush():
        if group:
            blocks.append(
                f"[{display_time(group[0].start_ms)} - {display_time(max(c.end_ms for c in group))}] "
                + " ".join(c.text for c in group)
            )
            group.clear()

    for cue, index in zip(fragments, source_indices, strict=True):
        group_end = max((c.end_ms for c in group), default=0)
        if group and (
            index != previous_index + 1
            or cue.start_ms < group[-1].start_ms
            or cue.start_ms > group_end + 2000
            or max(cue.end_ms, group_end) - group[0].start_ms > 15000
        ):
            flush()
        group.append(cue)
        previous_index = index
    flush()
    return "\n\n".join(blocks)


def render_chapter_text(sections: tuple[ChapterSection, ...]) -> str:
    blocks = []
    for section in sections:
        chapter = section.chapter
        if chapter is None:
            blocks.append(
                "Unassigned captions\n\n"
                + render_timed_text(
                    section.fragments, source_indices=section.source_indices
                )
            )
        else:
            assert section.chapter_index is not None
            end = (
                display_time(chapter.end_ms)
                if chapter.end_ms is not None
                else "end unknown"
            )
            blocks.append(
                f"Chapter {section.chapter_index + 1} [{display_time(chapter.start_ms)} - {end}]: {display_title(chapter.title)}\n\n{section.text}"
            )
    return "\n\n".join(blocks)
