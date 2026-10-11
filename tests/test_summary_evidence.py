"""Source ownership and strict evidence mechanics, without model execution."""

import json
from dataclasses import FrozenInstanceError

import pytest

from yt_transcript import formatter
from yt_transcript.chapters import Chapter, build_chapter_sections
from yt_transcript.cleaner import Cue
from yt_transcript.errors import FormattingError
from yt_transcript.summary_evidence import (
    EvidenceLimitError,
    bounded_claims,
    claims_payload,
    note_capacity,
    parse_claims,
    plan_summary_evidence,
    private_id_leaked,
    serialize,
    synthesis_payload,
)


def test_untimed_offsets_ownership_namespace_and_exact_bounds():
    source = '  α   yt_source_000001  quoted "value"  ' + "word. " * 200
    normalized = " ".join(source.split())
    plan = plan_summary_evidence(source, chunk_chars=500)
    spans = [s for group in plan.source_spans for s in group]
    assert " ".join(s.text for s in spans) == normalized
    assert len({s.source_id for s in spans}) == len(spans)
    assert plan.id_prefix not in normalized
    for chunk_index, group in enumerate(plan.source_spans, 1):
        for span in group:
            assert span.chunk_index == chunk_index
            assert span.origin.start_ms is span.origin.end_ms is None
            assert (
                span.text == normalized[span.origin.text_start : span.origin.text_end]
            )
    assert all(len(c) <= 500 for c in plan.chunks)
    assert plan == plan_summary_evidence(source, chunk_chars=500)
    frozen_field = "text"
    with pytest.raises(FrozenInstanceError):
        setattr(spans[0], frozen_field, "changed")
    assert private_id_leaked("A " + spans[0].source_id, plan.id_prefix)
    assert not private_id_leaked("yt_source_000001", plan.id_prefix)


def test_timed_origins_splits_gaps_and_backward_run_order():
    cues = (
        Cue(1000, 1500, "alpha " * 100),
        Cue(4000, 4500, "later words"),
        Cue(1000, 1500, "backward words"),
    )
    sections = build_chapter_sections(
        cues,
        (Chapter("Earlier", 0, 3000), Chapter("Later", 3000, 6000)),
        source_indices=(0, 4, 8),
    )
    plan = plan_summary_evidence("unused metadata", sections=sections, chunk_chars=700)
    spans = [s for group in plan.source_spans for s in group]
    assert [s.origin.source_index for s in spans][-2:] == [4, 8]
    assert [s.origin.run_id for s in spans][-2:] == [1, 2]
    assert "unused metadata" not in "".join(plan.chunks)
    for cue, original in zip(cues, (0, 4, 8), strict=True):
        owned = [s for s in spans if s.origin.source_index == original]
        assert " ".join(s.text for s in owned) == " ".join(cue.text.split())
        cursor = 0
        for span in owned:
            assert span.origin.word_start == cursor
            cursor = span.origin.word_end
            assert (span.origin.start_ms, span.origin.end_ms) == (
                cue.start_ms,
                cue.end_ms,
            )
        assert cursor == len(cue.text.split())
    assert all(c <= 700 for c in plan.character_counts)


def valid(statement="A qualified claim.", source_id="yt_source_000001"):
    return {
        "claims": [
            {
                "statement": statement,
                "source_ids": [source_id],
                "qualifications": ["Small sample.", "May not generalize."],
            }
        ]
    }


@pytest.mark.parametrize(
    "value",
    [
        {
            "claims": [
                {
                    "statement": "",
                    "source_ids": ["yt_source_000001"],
                    "qualifications": [],
                }
            ]
        },
        {"claims": [{"statement": "Claim", "source_ids": [], "qualifications": []}]},
        {
            "claims": [
                {"statement": "Claim", "source_ids": ["forged"], "qualifications": []}
            ]
        },
        {"claims": [{"statement": "Claim", "source_ids": ["yt_source_000001"]}]},
        {
            "claims": [
                {
                    "statement": "Claim",
                    "source_ids": ["yt_source_000001"] * 2,
                    "qualifications": [],
                }
            ]
        },
        {
            "claims": [
                {
                    "statement": "Claim",
                    "source_ids": ["yt_source_000001"],
                    "qualifications": [True],
                }
            ]
        },
        {
            "claims": [
                {
                    "statement": "Claim",
                    "source_ids": ["yt_source_000001"],
                    "qualifications": ["q"] * 17,
                }
            ]
        },
        {"claims": [], "extra": "untrusted"},
        {"claims": [valid()["claims"][0]] * 65},
    ],
)
def test_invalid_claim_schema_and_references(value):
    with pytest.raises(ValueError):
        parse_claims(json.dumps(value), ["yt_source_000001"])


@pytest.mark.parametrize(
    "raw",
    [
        '{"claims":[],"claims":[]}',
        '{"claims":NaN}',
        '```json\n{"claims":[]}\n```',
        '{"claims":[]} commentary',
        "---\nclaims: []",
        '{"claims":[]} {"claims":[]}',
    ],
)
def test_non_strict_json_is_rejected(raw):
    with pytest.raises(ValueError):
        parse_claims(raw, [])


def test_valid_qualifications_remain_objects_and_empty_claims_are_allowed():
    claims = parse_claims(serialize(valid()), ["yt_source_000001"])
    assert claims_payload(claims) == valid()
    payload = json.loads(
        synthesis_payload([{"chunk_index": 1, **claims_payload(claims)}])
    )
    assert payload["notes"][0]["claims"][0]["qualifications"] == [
        "Small sample.",
        "May not generalize.",
    ]
    assert "text" not in payload["notes"][0]
    assert parse_claims('{"claims":[]}', []) == ()


def test_escaped_note_capacity_and_minimum_feasibility():
    count, budget = 3, 2000
    capacity = note_capacity(count, budget)
    note = serialize(valid('Quoted "claim" with \\ and café.'))
    assert bounded_claims(note, ["yt_source_000001"], capacity)
    with pytest.raises(ValueError):
        bounded_claims(note, ["yt_source_000001"], len(note) - 14)
    with pytest.raises(EvidenceLimitError):
        note_capacity(3, 1000)
    with pytest.raises(EvidenceLimitError):
        plan_summary_evidence("identifier_too_large", chunk_chars=10)


def test_empty_evidence_fails_before_synthesis_and_ids_cannot_be_published(monkeypatch):
    monkeypatch.setattr(formatter, "ensure_pi", lambda: "fake")
    calls = []

    def complete(executable, source, **kwargs):
        calls.append(source)
        return '{"claims":[]}'

    monkeypatch.setattr(formatter, "_run_chunk", complete)
    source = "word. " * 600
    plan = formatter.plan_transcript_formatting(
        source, editorial_mode="summarized", chunk_chars=2000
    )
    with pytest.raises(FormattingError) as error:
        formatter.format_with_pi(source, editorial_mode="summarized", chunk_chars=2000)
    assert len(calls) == len(plan.chunks)
    assert error.value.info.chunk_index == plan.call_count
    monkeypatch.setattr(
        formatter,
        "_run_chunk",
        lambda *a, **k: "## Summary\n\nyt_source_000001\n\n## Key points\n\n- Claim.",
    )
    with pytest.raises(FormattingError):
        formatter.format_with_pi("short source", editorial_mode="summarized")


def test_note_prompt_does_not_demand_markdown():
    request = formatter._build_chunk_request(
        "{}",
        index=1,
        total=3,
        model=None,
        timeout_seconds=1,
        editorial_mode="summarized",
        summary_stage="notes",
        summary_note_chars=500,
    )
    assert "JSON" in request.system_prompt
    assert "requested Markdown body" not in request.system_prompt
    assert "Return only the claims JSON" in request.instruction
