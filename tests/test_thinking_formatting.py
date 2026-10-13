"""Shared request tests use fake completions only, without HTTP or Pi."""

import json

import pytest

from yt_transcript import formatter
from yt_transcript.chapters import Chapter, build_chapter_sections
from yt_transcript.cleaner import Cue
from yt_transcript.config import DeepSeekConfig
from yt_transcript.errors import FormattingError

SUMMARY = "## Summary\n\nThe speaker explains retries.\n\n## Key points\n\n- Retries can duplicate writes."
SOURCE = "Retries can duplicate writes. Idempotency prevents duplicate effects. " * 30


def fake_backend(monkeypatch, provider, output):
    calls = []

    def complete(request, config=None):
        calls.append((request, config))
        return output(request)

    if provider == "pi":
        monkeypatch.setattr(formatter, "ensure_pi", lambda: "fake-pi")
        monkeypatch.setattr(
            formatter, "_run_pi_chunk", lambda executable, request: complete(request)
        )
    else:
        from yt_transcript import deepseek_backend, openrouter_backend

        backend = deepseek_backend if provider == "deepseek" else openrouter_backend
        monkeypatch.setattr(backend, "ensure_" + provider, lambda model: None)
        monkeypatch.setattr(backend, "complete", complete)
    return calls


@pytest.mark.parametrize("provider", ["pi", "openrouter", "deepseek"])
@pytest.mark.parametrize(
    "thinking,level,expected",
    [
        (None, None, (True, "medium")),
        (None, "low", (True, "low")),
        (True, "high", (True, "high")),
        (False, "high", (False, None)),
    ],
)
@pytest.mark.parametrize("multiple", [False, True])
def test_summary_policy_is_identical_in_every_stage(
    monkeypatch, provider, thinking, level, expected, multiple
):
    def output(request):
        if "Extract factual notes" in request.instruction:
            source_id = json.loads(request.source)["source_spans"][0]["source_id"]
            return json.dumps(
                {
                    "claims": [
                        {
                            "statement": "Retries can duplicate writes.",
                            "source_ids": [source_id],
                            "qualifications": [],
                        }
                    ]
                }
            )
        return SUMMARY

    calls = fake_backend(monkeypatch, provider, output)
    source = SOURCE if multiple else "Retries can duplicate writes."
    plan = formatter.plan_transcript_formatting(
        source, provider=provider, editorial_mode="summarized", chunk_chars=2000
    )
    assert plan.synthesis_required is multiple
    config = DeepSeekConfig()
    assert (
        formatter.format_transcript(
            source,
            "model",
            provider=provider,
            deepseek=config,
            editorial_mode="summarized",
            chunk_chars=2000,
            thinking=thinking,
            thinking_level=level,
        )
        == SUMMARY
    )
    assert len(calls) == plan.call_count
    assert {(request.thinking, request.thinking_level) for request, _ in calls} == {
        expected
    }
    if provider == "deepseek":
        assert all(item[1] is config for item in calls)
    if multiple:
        assert "whole-video summary from" in calls[-1][0].instruction


@pytest.mark.parametrize("provider", ["pi", "openrouter", "deepseek"])
@pytest.mark.parametrize("mode", ["standard", "focused"])
@pytest.mark.parametrize("contextual", [False, True])
def test_unspecified_policy_preserves_defaults_and_context(
    monkeypatch, provider, mode, contextual
):
    body = (
        "## [00:00] Retries\n\nRetries can duplicate writes."
        if contextual
        else "## Edited\n\nRetries can duplicate writes."
    )

    def output(request):
        if not contextual:
            return body
        return json.dumps(
            {
                "runs": [
                    {"run_id": run["run_id"], "body": "Retries can duplicate writes."}
                    for run in json.loads(request.source)["runs"]
                ]
            }
        )

    calls = fake_backend(monkeypatch, provider, output)
    sections = (
        build_chapter_sections(
            (Cue(0, 1000, "Retries can duplicate writes."),),
            (Chapter("Retries", 0, 1000),),
        )
        if contextual
        else None
    )
    # Use the canonical heading from the section, not a provider-generated heading.
    if sections:
        body = sections[0].heading + "\n\nRetries can duplicate writes."
    assert (
        formatter.format_transcript(
            "Retries can duplicate writes.",
            "model",
            provider=provider,
            editorial_mode=mode,
            sections=sections,
        )
        == body
    )
    expected = (False, None) if provider == "deepseek" else (None, None)
    assert [(r.thinking, r.thinking_level) for r, _ in calls] == [expected]


@pytest.mark.parametrize("provider", ["pi", "openrouter", "deepseek"])
def test_direct_chunk_entry_resolves_summary_policy(monkeypatch, provider):
    calls = fake_backend(monkeypatch, provider, lambda request: SUMMARY)
    formatter._run_chunk(
        "fake-pi" if provider == "pi" else None,
        "source",
        index=1,
        total=1,
        model="model",
        timeout_seconds=2,
        provider=provider,
        editorial_mode="summarized",
    )
    assert (calls[0][0].thinking, calls[0][0].thinking_level) == (True, "medium")


@pytest.mark.parametrize(
    "invalid",
    [
        "---\ntitle: private\n---\nbody",
        "## Wrong\n\nbody",
        "PRIVATE_REASONING_SENTINEL",
    ],
)
def test_deepseek_summary_validation_is_safe_and_translated(monkeypatch, invalid):
    fake_backend(monkeypatch, "deepseek", lambda request: invalid)
    with pytest.raises(FormattingError) as exc:
        formatter.format_transcript(
            "Retries can duplicate writes.",
            "model",
            provider="deepseek",
            editorial_mode="summarized",
        )
    assert exc.value.info.code == "DEEPSEEK_OUTPUT_INVALID"
    assert exc.value.info.chunk_index == 1
    assert "PRIVATE_REASONING_SENTINEL" not in str(exc.value)


def test_deepseek_notes_keep_evidence_validation_and_safe_diagnostics(monkeypatch):
    fake_backend(
        monkeypatch,
        "deepseek",
        lambda request: json.dumps(
            {
                "claims": [
                    {
                        "statement": "PRIVATE_REASONING_SENTINEL",
                        "source_ids": ["not-a-source-id"],
                        "qualifications": [],
                    }
                ]
            }
        ),
    )
    with pytest.raises(FormattingError) as exc:
        formatter.format_transcript(
            SOURCE,
            "model",
            provider="deepseek",
            editorial_mode="summarized",
            chunk_chars=2000,
        )
    assert exc.value.info.code == "DEEPSEEK_OUTPUT_INVALID"
    assert exc.value.info.chunk_index == 1
    assert "PRIVATE_REASONING_SENTINEL" not in str(exc.value)


@pytest.mark.parametrize("provider", ["pi", "openrouter", "deepseek"])
@pytest.mark.parametrize(
    "thinking,level,expected",
    [(True, "low", (True, "low")), (False, "high", (False, None))],
)
def test_contextual_and_boundary_calls_receive_explicit_policy(
    monkeypatch, provider, thinking, level, expected
):
    sections = build_chapter_sections(
        (Cue(0, 1000, "Retries can duplicate writes."),), (Chapter("Retries", 0, 1000),)
    )
    body = sections[0].heading + "\n\nRetries can duplicate writes."

    def output(request):
        return json.dumps(
            {
                "runs": [
                    {"run_id": run["run_id"], "body": "Retries can duplicate writes."}
                    for run in json.loads(request.source)["current"]["runs"]
                ]
            }
        )

    calls = fake_backend(monkeypatch, provider, output)
    assert (
        formatter.format_transcript(
            "Retries can duplicate writes.",
            "model",
            provider=provider,
            sections=sections,
            thinking=thinking,
            thinking_level=level,
            boundary_context_chars=100,
        )
        == body
    )
    assert (calls[0][0].thinking, calls[0][0].thinking_level) == expected
    assert "previous_context" in json.loads(calls[0][0].source)


def test_summary_resolves_once_for_all_stages(monkeypatch):
    original = formatter.resolve_thinking
    policies = []

    def resolve(*args):
        policies.append(args)
        return original(*args)

    monkeypatch.setattr(formatter, "resolve_thinking", resolve)

    def output(request):
        if "Extract factual notes" in request.instruction:
            source_id = json.loads(request.source)["source_spans"][0]["source_id"]
            return json.dumps(
                {
                    "claims": [
                        {
                            "statement": "Retries can duplicate writes.",
                            "source_ids": [source_id],
                            "qualifications": [],
                        }
                    ]
                }
            )
        return SUMMARY

    calls = fake_backend(monkeypatch, "pi", output)
    formatter.format_transcript(
        SOURCE, editorial_mode="summarized", chunk_chars=2000, thinking_level="high"
    )
    assert len(calls) > 1
    assert len(policies) == 1


def test_deepseek_notes_budget_still_fails_without_synthesis(monkeypatch):
    calls = fake_backend(monkeypatch, "deepseek", lambda request: " " * 60000)
    with pytest.raises(FormattingError) as exc:
        formatter.format_transcript(
            SOURCE,
            "model",
            provider="deepseek",
            editorial_mode="summarized",
            chunk_chars=2000,
        )
    assert exc.value.info.code == "DEEPSEEK_OUTPUT_INVALID"
    assert exc.value.info.chunk_index == 1
    assert len(calls) == 1
