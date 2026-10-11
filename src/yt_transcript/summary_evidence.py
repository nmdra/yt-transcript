"""Immutable retained-source ownership and strict private summary claims.

References establish supplied-span membership, never entailment or truth.
This module performs no backend, network, or process execution.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .chapters import ChapterSection
from .json_tools import strict_json_loads


class EvidenceLimitError(ValueError):
    """A source token or serialized evidence budget cannot fit."""


@dataclass(frozen=True)
class SpanOrigin:
    source_index: int | None = None
    run_id: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    word_start: int | None = None
    word_end: int | None = None
    text_start: int | None = None
    text_end: int | None = None

    def wire(self) -> dict[str, int | None]:
        if self.source_index is None:
            return {
                "start_ms": None,
                "end_ms": None,
                "text_start": self.text_start,
                "text_end": self.text_end,
            }
        return {
            "source_index": self.source_index,
            "run_id": self.run_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "word_start": self.word_start,
            "word_end": self.word_end,
        }


@dataclass(frozen=True)
class SourceSpan:
    source_id: str
    text: str
    chunk_index: int
    origin: SpanOrigin

    def wire(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "text": self.text,
            "origin": self.origin.wire(),
        }


@dataclass(frozen=True)
class EvidenceFormattingPlan:
    chunks: tuple[str, ...]
    source_spans: tuple[tuple[SourceSpan, ...], ...]
    id_prefix: str
    within_cap: bool
    synthesis_required: bool

    @property
    def character_counts(self) -> tuple[int, ...]:
        return tuple(map(len, self.chunks))

    @property
    def call_count(self) -> int:
        return len(self.chunks) + (1 if self.synthesis_required else 0)


def serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def source_namespace(retained_text: str) -> str:
    prefix = "yt_source_"
    index = 0
    while prefix in retained_text:
        index += 1
        prefix = f"yt_source{index}_"
    return prefix


def private_id_leaked(body: str, prefix: str) -> bool:
    return bool(re.search(re.escape(prefix) + r"[0-9]{6,}", body))


def plan_summary_evidence(
    transcript: str,
    *,
    sections: tuple[ChapterSection, ...] | None = None,
    chunk_chars: int = 12000,
    max_chunks: int | None = None,
) -> EvidenceFormattingPlan:
    """Partition normalized caption words once, budgeting IDs and origin framing."""
    if type(chunk_chars) is not int or chunk_chars < 1:
        raise ValueError("Invalid source budget.")
    normalized = " ".join(transcript.split())
    retained = (
        " ".join(s.text for s in sections) if sections is not None else normalized
    )
    prefix = source_namespace(retained)
    contextual = sections is not None and any(
        s.chapter_count
        or any(getattr(c, "sponsorblock_overlaps", ()) for c in s.fragments)
        for s in sections
    )
    chapter_mode = sections is not None and any(s.chapter_count for s in sections)
    chunks: list[str] = []
    owned: list[tuple[SourceSpan, ...]] = []
    current: list[SourceSpan] = []
    frames: dict[int, dict[str, Any]] = {}
    overlaps: dict[str, list[dict[str, Any]]] = {}
    seen: set[int] = set()
    next_id = 1

    def payload(spans: list[SourceSpan]) -> str:
        if not contextual:
            return serialize({"source_spans": [span.wire() for span in spans]})
        runs: list[dict[str, Any]] = []
        for span in spans:
            run_id = span.origin.run_id
            assert run_id is not None
            fragment = span.wire()
            if overlaps.get(span.source_id):
                fragment["sponsorblock_overlaps"] = overlaps[span.source_id]
            if runs and runs[-1]["run_id"] == run_id:
                runs[-1]["fragments"].append(fragment)
            else:
                runs.append(
                    {
                        **frames[run_id],
                        "continuation": run_id in seen,
                        "fragments": [fragment],
                    }
                )
        return serialize({"runs": runs})

    def flush() -> None:
        if current:
            chunks.append(payload(current))
            owned.append(tuple(current))
            seen.update(
                span.origin.run_id for span in current if span.origin.run_id is not None
            )
            current.clear()

    # Records contain one retained cue, or one normalized untimed transcript.
    records: list[tuple[str, int | None, ChapterSection | None, Any]] = []
    if sections is None:
        records.append((normalized, None, None, None))
    else:
        for section in sections:
            if len(section.fragments) != len(section.source_indices):
                raise ValueError("Invalid retained source indices.")
            chapter = section.chapter
            frames[section.run_id] = {
                "run_id": section.run_id,
                "chapter_index": section.chapter_index,
                "chapter_count": section.chapter_count,
                "heading": section.heading if chapter_mode else None,
                "title": chapter.title if chapter else None,
                "start_ms": chapter.start_ms if chapter else None,
                "end_ms": chapter.end_ms if chapter else None,
            }
            for cue, source_index in zip(
                section.fragments, section.source_indices, strict=True
            ):
                records.append((" ".join(cue.text.split()), source_index, section, cue))

    for text, source_index, section, cue in records:
        matches = list(re.finditer(r"\S+", text))
        word_start = 0
        while word_start < len(matches):
            source_id = f"{prefix}{next_id:06d}"
            if cue is not None:
                overlaps[source_id] = [
                    {
                        "category": s.category,
                        "start_ms": s.start_ms,
                        "end_ms": s.end_ms,
                        "boundary_overlap": True,
                    }
                    for s in getattr(cue, "sponsorblock_overlaps", ())
                ]

            def candidate(
                count: int,
                *,
                word_start=word_start,
                matches=matches,
                cue=cue,
                source_index=source_index,
                section=section,
                source_id=source_id,
                text=text,
            ) -> SourceSpan:
                end = word_start + count
                start_offset, end_offset = (
                    matches[word_start].start(),
                    matches[end - 1].end(),
                )
                origin = (
                    SpanOrigin(text_start=start_offset, text_end=end_offset)
                    if cue is None
                    else SpanOrigin(
                        source_index=source_index,
                        run_id=section.run_id if section else None,
                        start_ms=cue.start_ms,
                        end_ms=cue.end_ms,
                        word_start=word_start,
                        word_end=end,
                    )
                )
                return SourceSpan(
                    source_id, text[start_offset:end_offset], len(chunks) + 1, origin
                )

            low, high = 0, len(matches) - word_start
            while low < high:
                middle = (low + high + 1) // 2
                if len(payload([*current, candidate(middle)])) <= chunk_chars:
                    low = middle
                else:
                    high = middle - 1
            if low == 0:
                if current:
                    flush()
                    continue
                raise EvidenceLimitError("Source framing or token cannot fit.")
            if word_start + low < len(matches):
                sentences = [
                    i + 1
                    for i, m in enumerate(matches[word_start : word_start + low])
                    if m[0].endswith((".", "!", "?"))
                ]
                low = sentences[-1] if sentences else low
            current.append(candidate(low))
            next_id += 1
            word_start += low
            if word_start < len(matches):
                flush()
    flush()
    synthesis = len(chunks) > 1
    calls = len(chunks) + (1 if synthesis else 0)
    return EvidenceFormattingPlan(
        tuple(chunks),
        tuple(owned),
        prefix,
        max_chunks is None or calls <= max_chunks,
        synthesis,
    )


@dataclass(frozen=True)
class SummaryClaim:
    statement: str
    source_ids: tuple[str, ...]
    qualifications: tuple[str, ...]

    def wire(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "source_ids": list(self.source_ids),
            "qualifications": list(self.qualifications),
        }


def parse_claims(raw: str, supplied_ids: Sequence[str]) -> tuple[SummaryClaim, ...]:
    """Reject invalid schema and cross-call references without repairing output."""
    value = strict_json_loads(raw)
    if not isinstance(value, dict) or set(value) != {"claims"}:
        raise ValueError("Invalid summary claims.")
    claims = value["claims"]
    if not isinstance(claims, list) or len(claims) > 64:
        raise ValueError("Invalid summary claims.")
    allowed = set(supplied_ids)
    result = []
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {
            "statement",
            "source_ids",
            "qualifications",
        }:
            raise ValueError("Invalid summary claim.")
        statement, ids, qualifications = (
            claim["statement"],
            claim["source_ids"],
            claim["qualifications"],
        )
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("Invalid summary statement.")
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= 16
            or any(not isinstance(i, str) for i in ids)
        ):
            raise ValueError("Invalid summary references.")
        if len(set(ids)) != len(ids) or set(ids) - allowed:
            raise ValueError("Unknown or duplicate summary reference.")
        if (
            not isinstance(qualifications, list)
            or len(qualifications) > 16
            or any(not isinstance(q, str) for q in qualifications)
        ):
            raise ValueError("Invalid summary qualifications.")
        result.append(SummaryClaim(statement, tuple(ids), tuple(qualifications)))
    return tuple(result)


def claims_payload(claims: Sequence[SummaryClaim]) -> dict[str, Any]:
    return {"claims": [claim.wire() for claim in claims]}


def synthesis_payload(notes: list[dict[str, Any]]) -> str:
    return serialize({"notes": notes})


def note_capacity(
    chunk_count: int, chunk_chars: int, *, source_id_chars: int = 16
) -> int:
    if chunk_count < 1:
        raise EvidenceLimitError("No source chunks.")
    skeleton = [
        {"chunk_index": index, "claims": []} for index in range(1, chunk_count + 1)
    ]
    limit = (chunk_chars - len(synthesis_payload(skeleton))) // chunk_count
    framing = len(
        serialize(claims_payload([SummaryClaim("", ("x" * source_id_chars,), ())]))
    ) - len(serialize(claims_payload([])))
    if limit - framing < 256:
        raise EvidenceLimitError("Insufficient serialized note capacity.")
    return limit


def bounded_claims(
    raw: str, supplied_ids: Sequence[str], capacity: int
) -> tuple[SummaryClaim, ...]:
    empty_size = len(serialize(claims_payload([])))
    if len(raw) > capacity + empty_size:
        raise ValueError("Summary notes exceed budget.")
    claims = parse_claims(raw, supplied_ids)
    if len(serialize(claims_payload(claims))) - empty_size > capacity:
        raise ValueError("Summary notes exceed budget.")
    return claims
