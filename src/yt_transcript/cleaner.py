"""Supported YouTube WebVTT subset with conservative rolling cleanup."""

import html
import re
from dataclasses import dataclass

from .errors import ErrorInfo, TranscriptError


@dataclass(frozen=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


TIME = r"(?:[0-9]{2,}:)?[0-5][0-9]:[0-5][0-9]\.[0-9]{3}"
TIMING = re.compile(rf"^({TIME}) --> ({TIME})(?:[ \t]+[^\r\n]*)?$")
TAGS = re.compile(
    r"<(?:/?(?:c(?:\.[^ >]+)*|v(?:\s+[^>]+)?|lang(?:\s+[^>]+)?|b|i|u|ruby|rt)|(?:\d{2,}:)?\d{2}:\d{2}\.\d{3})>"
)


def _time(value: str) -> int:
    parts = value.split(":")
    seconds, milliseconds = parts[-1].split(".")
    return (
        int(parts[-2]) * 60
        + int(seconds)
        + (int(parts[-3]) * 3600 if len(parts) == 3 else 0)
    ) * 1000 + int(milliseconds)


def parse_vtt(vtt: str) -> list[Cue]:
    text = vtt.removeprefix("\ufeff").replace("\r\n", "\n")
    # YouTube cues can contain space-only payload lines. Only empty lines
    # separate blocks; treating spaces as separators detaches caption text.
    blocks = re.split(r"\n{2,}", text.strip())
    if not blocks or not re.fullmatch(r"WEBVTT(?:[ \t].*)?", blocks[0].split("\n")[0]):
        raise TranscriptError(
            ErrorInfo(
                "SUBTITLE_INVALID",
                "Missing WebVTT header.",
                "Use --raw-vtt to inspect captions separately.",
                "vtt_parse",
            )
        )
    cues = []
    for index, block in enumerate(blocks[1:], 1):
        lines = block.split("\n")
        if not block.strip() or re.match(
            r"^(NOTE(?:[ \t]|$)|STYLE$|REGION$)", lines[0]
        ):
            continue
        timing_index = 0 if "-->" in lines[0] else 1
        match = (
            TIMING.fullmatch(lines[timing_index]) if timing_index < len(lines) else None
        )
        if not match:
            raise TranscriptError(
                ErrorInfo(
                    "SUBTITLE_INVALID",
                    f"Invalid caption block {index}.",
                    "Use --raw-vtt to inspect captions separately.",
                    "vtt_parse",
                )
            )
        try:
            start, end = _time(match[1]), _time(match[2])
        except ValueError:
            raise TranscriptError(
                ErrorInfo(
                    "SUBTITLE_INVALID",
                    f"Invalid timing in block {index}.",
                    phase="vtt_parse",
                )
            ) from None
        if end < start:
            raise TranscriptError(
                ErrorInfo(
                    "SUBTITLE_INVALID",
                    f"Invalid timing in block {index}.",
                    phase="vtt_parse",
                )
            )
        payload = "\n".join(lines[timing_index + 1 :])
        payload = " ".join(html.unescape(TAGS.sub("", payload)).split())
        cues.append(Cue(start, end, payload))
    return cues


def clean_vtt(vtt: str, *, automatic: bool) -> str:
    result: list[str] = []
    previous: Cue | None = None
    previous_tokens: list[str] = []
    for cue in parse_vtt(vtt):
        tokens = cue.text.split()
        overlap = 0
        rolling = (
            previous is not None
            and cue.start_ms >= previous.start_ms
            and cue.start_ms <= previous.end_ms + 100
        )
        if automatic and rolling:
            for size in range(min(len(previous_tokens), len(tokens)), 0, -1):
                if previous_tokens[-size:] == tokens[:size] and (
                    size >= 2
                    or (
                        tokens == previous_tokens
                        and previous is not None
                        and cue.start_ms < previous.end_ms
                    )
                ):
                    overlap = size
                    break
        result.extend(tokens[overlap:])
        previous, previous_tokens = cue, tokens
    if not result:
        raise TranscriptError(
            ErrorInfo(
                "EMPTY_TRANSCRIPT",
                "empty transcript",
                "Use --raw-vtt to inspect captions separately.",
                "vtt_parse",
            )
        )
    return " ".join(result)
