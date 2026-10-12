"""Offline regression checks for independent synthesis and safe rejection details."""

import json
from dataclasses import asdict, replace

import pytest

from yt_transcript import formatter
from yt_transcript.config import load_config
from yt_transcript.errors import (
    ConfigError,
    FormattingError,
    decode_worker_error,
    render_cli_error,
    render_mcp_error,
    summary_failure,
    translate_formatting_error,
)
from yt_transcript.mcp_policy import MCPFormattingPolicy, validate_formatting_policy
from yt_transcript.summary_evidence import (
    EvidenceFormattingPlan,
    SummaryNotesError,
    bounded_claims,
    claims_payload,
    note_capacity,
    serialize,
    synthesis_payload,
)

SUMMARY = "## Summary\n\nThe speaker explains a mechanism.\n\n## Key points\n\n- Results remain uncertain."


def test_valid_notes_above_old_allocation_reach_synthesis(monkeypatch):
    source = "word " * 24000
    plan = formatter.plan_transcript_formatting(
        source, editorial_mode="summarized", chunk_chars=30000
    )
    assert isinstance(plan, EvidenceFormattingPlan)
    assert len(plan.chunks) == 5
    old = note_capacity(5, 30000)
    new = note_capacity(5, 50000)
    assert old + len('{"claims":[]}') == 5980
    calls = []

    def run(executable, payload, **kwargs):
        calls.append((payload, kwargs))
        if kwargs["summary_stage"] == "synthesis":
            return SUMMARY
        ids = [span.source_id for span in plan.source_spans[len(calls) - 1]]
        # Exactly the compact response length observed in the reproduction.
        empty = serialize(
            {
                "claims": [
                    {
                        "statement": "",
                        "source_ids": [ids[0]],
                        "qualifications": ["Qualified."],
                    }
                ]
            }
        )
        raw = empty.replace(
            '"statement":""', '"statement":"' + "x" * (6767 - len(empty)) + '"'
        )
        assert len(raw) == 6767
        assert old < len(raw) < new
        return raw

    monkeypatch.setattr(formatter, "ensure_pi", lambda: "fake")
    monkeypatch.setattr(formatter, "_run_chunk", run)
    assert (
        formatter.format_with_pi(source, editorial_mode="summarized", chunk_chars=30000)
        == SUMMARY
    )
    assert len(calls) == 6
    assert 30000 < len(calls[-1][0]) <= 50000
    assert calls[0][1]["summary_note_chars"] == new + len('{"claims":[]}')


def test_synthesis_exact_boundary_includes_all_framing():
    empty = '{"claims":[]}'
    count, budget = 3, 2999
    capacity = note_capacity(count, budget)
    notes = []
    for index in range(1, count + 1):
        base = serialize(
            {"claims": [{"statement": "", "source_ids": ["id"], "qualifications": []}]}
        )
        raw = base.replace(
            '"statement":""',
            '"statement":"' + "x" * (capacity + len(empty) - len(base)) + '"',
        )
        claims = bounded_claims(raw, ["id"], capacity)
        notes.append({"chunk_index": index, **claims_payload(claims)})
    # Divisible allocation exhausts the full envelope, not just its claims.
    assert len(synthesis_payload(notes)) == budget
    with pytest.raises(SummaryNotesError) as exc:
        bounded_claims(raw.replace('"statement":"', '"statement":"x'), ["id"], capacity)
    assert exc.value.reason == "raw_budget"


@pytest.mark.parametrize("value", [True, 999, 500001, 1.5, "50000"])
def test_config_and_policy_reject_invalid_synthesis_budget(tmp_path, value):
    policy = asdict(MCPFormattingPolicy())
    policy["summary_synthesis_chars"] = value
    with pytest.raises(ValueError):
        validate_formatting_policy(policy)
    path = tmp_path / "config.toml"
    path.write_text("[formatting]\nsummary_synthesis_chars=" + json.dumps(value))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert exc.value.info.code == "CONFIG_INVALID"


@pytest.mark.parametrize("value", [1000, 50000, 500000])
def test_config_and_policy_accept_budget_bounds(tmp_path, value):
    path = tmp_path / "config.toml"
    path.write_text(f"[formatting]\nsummary_synthesis_chars={value}")
    assert load_config(path).summary_synthesis_chars == value
    assert (
        validate_formatting_policy(
            asdict(MCPFormattingPolicy(summary_synthesis_chars=value))
        ).summary_synthesis_chars
        == value
    )


@pytest.mark.parametrize(
    "raw,reason",
    [
        ('{"claims":[],"claims":[]}', "invalid_json"),
        ("{}", "invalid_schema"),
        (
            '{"claims":[{"statement":"a","source_ids":["other"],"qualifications":[]}]}',
            "invalid_reference",
        ),
        ("x" * 114, "raw_budget"),
        (
            '{"claims":[{"statement":"\u0001\u0001\u0001\u0001\u0001\u0001\u0001\u0001\u0001\u0001","source_ids":["id"],"qualifications":[]}]}'.replace(
                "\u0001", "\\u0001"
            ),
            "raw_budget",
        ),
    ],
)
def test_notes_rejection_categories(raw, reason):
    with pytest.raises(SummaryNotesError) as exc:
        bounded_claims(raw, ["id"], 100)
    assert exc.value.reason == reason


def test_compact_serialization_overflow_counts_are_local(monkeypatch):
    from yt_transcript import summary_evidence

    # The string-only schema normally compacts to no more than the raw size.
    # Force expansion to exercise the independent defensive canonical-size check.
    raw = '{"claims":[{"statement":"a","source_ids":["id"],"qualifications":[]}]}'
    original = summary_evidence.serialize

    def expanded(value):
        result = original(value)
        return result + " " * 50 if value.get("claims") else result

    monkeypatch.setattr(summary_evidence, "serialize", expanded)
    capacity = len(raw) - len('{"claims":[]}')
    with pytest.raises(SummaryNotesError) as exc:
        bounded_claims(raw, ["id"], capacity)
    assert exc.value.reason == "serialized_budget"
    assert exc.value.actual_chars == len(raw) + 50
    assert exc.value.allowed_chars == len(raw)


def test_note_prompt_soft_target_and_hard_limit():
    request = formatter._build_chunk_request(
        "{}",
        index=1,
        total=6,
        model=None,
        timeout_seconds=1,
        editorial_mode="summarized",
        summary_stage="notes",
        summary_note_chars=10000,
    )
    assert "at most 10000 serialized JSON characters" in request.instruction
    assert "at most 7500 characters" in request.instruction
    assert "compact JSON" in request.instruction
    assert (
        "qualifications" in request.instruction
        and "essential claims" in request.instruction
    )


@pytest.mark.parametrize("provider", ["pi", "openrouter"])
def test_worker_roundtrip_and_rendering(provider):
    exc = summary_failure("notes", "raw_budget", actual_chars=6767, allowed_chars=5993)
    exc.info = replace(exc.info, chunk_index=1, chunk_total=6)
    exc = translate_formatting_error(exc, provider)
    safe = decode_worker_error(asdict(exc.info))
    assert "invalid summary notes" in render_cli_error(exc)
    assert safe.summary_diagnostic == exc.info.summary_diagnostic
    assert "Markdown" not in safe.message
    assert "actual_chars=6767" in render_mcp_error(safe)
    assert "allowed_chars=5993" in render_cli_error(FormattingError(safe))


@pytest.mark.parametrize(
    "patch",
    [
        {"stage": "secret"},
        {"reason": "secret"},
        {"actual_chars": True},
        {"actual_chars": 1048577},
        {"actual_chars": 1},
        {"extra": "secret"},
    ],
)
def test_worker_rejects_forged_summary_metadata(patch):
    exc = summary_failure("notes", "raw_budget", actual_chars=6767, allowed_chars=5993)
    wire = asdict(exc.info)
    wire["summary_diagnostic"].update(patch)
    with pytest.raises(ValueError):
        decode_worker_error(wire)
    assert "secret" not in render_mcp_error(
        replace(exc.info, summary_diagnostic=wire["summary_diagnostic"])
    )


def test_openrouter_unicode_synthesis_transport_bound_before_helper(monkeypatch):
    from yt_transcript import openrouter_backend

    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(
        openrouter_backend.subprocess,
        "Popen",
        lambda *a, **kw: pytest.fail("must not launch helper or HTTP"),
    )
    request = formatter._build_chunk_request(
        "😀" * 300000,
        index=6,
        total=6,
        model="test/model",
        timeout_seconds=1,
        editorial_mode="summarized",
        summary_stage="synthesis",
    )
    assert len(request.source) < 500000
    with pytest.raises(FormattingError) as exc:
        openrouter_backend.complete(request)
    assert exc.value.info.code == "OPENROUTER_CONTEXT_LIMIT"


def test_too_small_synthesis_preflight_has_safe_reason_and_no_calls(monkeypatch):
    monkeypatch.setattr(formatter, "ensure_pi", lambda: pytest.fail("must not launch"))
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi(
            "word " * 24000,
            chunk_chars=30000,
            summary_synthesis_chars=1000,
            editorial_mode="summarized",
        )
    assert exc.value.info.code == "PI_CONTEXT_LIMIT"
    assert exc.value.info.summary_diagnostic == {
        "stage": "synthesis",
        "reason": "capacity",
        "actual_chars": None,
        "allowed_chars": None,
    }
    assert decode_worker_error(asdict(exc.value.info)) == exc.value.info


def test_direct_single_chunk_is_unchanged_at_minimum_synthesis_budget(monkeypatch):
    monkeypatch.setattr(formatter, "ensure_pi", lambda: "fake")
    calls = []

    def run(executable, payload, **kwargs):
        calls.append(kwargs)
        return SUMMARY

    monkeypatch.setattr(formatter, "_run_chunk", run)
    assert (
        formatter.format_with_pi(
            "Short source.", summary_synthesis_chars=1000, editorial_mode="summarized"
        )
        == SUMMARY
    )
    assert len(calls) == 1 and calls[0]["summary_stage"] is None


def test_long_source_ids_and_chunk_index_digits_are_reserved():
    from yt_transcript.summary_evidence import EvidenceLimitError, SummaryClaim

    count, budget, id_chars = 12, 12000, 200
    capacity = note_capacity(count, budget, source_id_chars=id_chars)
    notes = []
    for index in range(1, count + 1):
        claim = SummaryClaim("", ("x" * id_chars,), ("Qualified.",))
        base = serialize(claims_payload([claim]))
        claim = replace(claim, statement="x" * (capacity + 13 - len(base)))
        raw = serialize(claims_payload([claim]))
        assert len(raw) == capacity + 13
        accepted = bounded_claims(raw, claim.source_ids, capacity)
        notes.append({"chunk_index": index, **claims_payload(accepted)})
        with pytest.raises(SummaryNotesError) as exc:
            bounded_claims(raw + " ", claim.source_ids, capacity)
        assert exc.value.reason == "raw_budget"
    assert budget - count < len(synthesis_payload(notes)) <= budget
    with pytest.raises(EvidenceLimitError):
        note_capacity(count, 4000, source_id_chars=id_chars)


@pytest.mark.parametrize(
    "raw",
    ['```json\n{"claims":[]}\n```', "---\nclaims: []\n---", "[" * 2000 + "]" * 2000],
)
def test_notes_fences_yaml_and_deep_json_fail_closed(monkeypatch, raw):
    monkeypatch.setattr(formatter, "ensure_pi", lambda: "fake")
    calls = []

    def run(executable, payload, **kwargs):
        calls.append(kwargs)
        return raw

    monkeypatch.setattr(formatter, "_run_chunk", run)
    with pytest.raises(FormattingError) as exc:
        formatter.format_with_pi(
            "word " * 1000, chunk_chars=2000, editorial_mode="summarized"
        )
    assert exc.value.info.code == "PI_OUTPUT_INVALID"
    expected = (
        {"invalid_json", "invalid_schema"} if raw.startswith("[[") else {"invalid_json"}
    )
    assert exc.value.info.summary_diagnostic is not None
    assert exc.value.info.summary_diagnostic["reason"] in expected
    assert len(calls) == 1
    assert "Markdown" not in exc.value.info.message


def test_source_payload_overflow_retains_context_code_without_synthesis_metadata(
    monkeypatch,
):
    plan = formatter.plan_transcript_formatting(
        "word " * 1000, chunk_chars=2000, editorial_mode="summarized"
    )
    assert isinstance(plan, EvidenceFormattingPlan)
    plan = replace(plan, chunks=("x" * 2001, *plan.chunks[1:]))
    monkeypatch.setattr(
        formatter, "_run_chunk", lambda *a, **kw: pytest.fail("no calls")
    )
    with pytest.raises(FormattingError) as exc:
        formatter._summarize_transcript(
            "fake",
            plan,
            chunk_chars=2000,
            summary_synthesis_chars=50000,
            model=None,
            timeout_seconds=1,
            own_process_group=True,
            on_progress=None,
            provider="pi",
            openrouter=None,
        )
    assert exc.value.info.code == "PI_CONTEXT_LIMIT"
    assert exc.value.info.summary_diagnostic is None


def test_summary_parser_recursion_failure_is_safe(monkeypatch):
    from yt_transcript import summary_evidence

    def recursive(raw):
        raise RecursionError("private parser detail")

    monkeypatch.setattr(summary_evidence, "strict_json_loads", recursive)
    with pytest.raises(SummaryNotesError) as exc:
        bounded_claims('{"claims":[]}', [], 100)
    assert exc.value.reason == "invalid_json"
    assert "private" not in str(exc.value)


@pytest.mark.parametrize("provider", ["pi", "openrouter"])
@pytest.mark.parametrize("raw", ['```json\n{"claims":[]}\n```', "---\nclaims: []\n---"])
def test_real_notes_dispatch_keeps_strict_json_rejection(monkeypatch, provider, raw):
    from yt_transcript import openrouter_backend

    calls = []
    monkeypatch.setattr(formatter, "ensure_formatter", lambda *a: "fake")

    def complete(*args):
        calls.append(args)
        return raw

    monkeypatch.setattr(formatter, "_run_pi_chunk", complete)
    monkeypatch.setattr(openrouter_backend, "complete", complete)
    with pytest.raises(FormattingError) as exc:
        formatter.format_transcript(
            "word " * 1000,
            provider=provider,
            chunk_chars=2000,
            editorial_mode="summarized",
        )
    diagnostic = exc.value.info.summary_diagnostic
    assert diagnostic is not None and diagnostic["reason"] == "invalid_json"
    assert len(calls) == 1


@pytest.mark.parametrize("provider", ["pi", "openrouter"])
def test_real_notes_dispatch_accepts_valid_notes_before_synthesis(
    monkeypatch, provider
):
    from yt_transcript import openrouter_backend

    monkeypatch.setattr(formatter, "ensure_formatter", lambda *a: "fake")
    calls = []

    def complete(*args):
        request = args[-1] if provider == "pi" else args[0]
        calls.append(request)
        if "whole-video summary from" in request.instruction:
            return SUMMARY
        payload = json.loads(request.source)
        source_id = payload["source_spans"][0]["source_id"]
        return serialize(
            {
                "claims": [
                    {
                        "statement": "Qualified claim.",
                        "source_ids": [source_id],
                        "qualifications": ["Uncertain."],
                    }
                ]
            }
        )

    monkeypatch.setattr(formatter, "_run_pi_chunk", complete)
    monkeypatch.setattr(openrouter_backend, "complete", complete)
    assert (
        formatter.format_transcript(
            "word " * 1000,
            provider=provider,
            chunk_chars=2000,
            editorial_mode="summarized",
        )
        == SUMMARY
    )
    assert len(calls) > 2


@pytest.mark.parametrize("provider", ["pi", "openrouter"])
@pytest.mark.parametrize(
    "mode,stage",
    [
        ("standard", None),
        ("focused", None),
        ("summarized", None),
        ("summarized", "synthesis"),
    ],
)
def test_other_dispatch_stages_keep_markdown_validation(
    monkeypatch, provider, mode, stage
):
    from yt_transcript import openrouter_backend

    monkeypatch.setattr(formatter, "_run_pi_chunk", lambda *a: "```markdown\nBody\n```")
    monkeypatch.setattr(
        openrouter_backend, "complete", lambda *a: "```markdown\nBody\n```"
    )
    with pytest.raises(FormattingError):
        formatter._run_chunk(
            "fake",
            "source",
            index=1,
            total=1,
            model=None,
            timeout_seconds=1,
            provider=provider,
            editorial_mode=mode,
            summary_stage=stage,
        )


def test_new_settings_preserve_legacy_constructor_positions():
    from yt_transcript.config import AppConfig, CacheConfig, MCPConfig, OpenRouterConfig
    from yt_transcript.sponsorblock import SponsorBlockConfig

    config = AppConfig(
        "markdown",
        False,
        None,
        12000,
        600,
        None,
        "summarized",
        SponsorBlockConfig(),
        MCPConfig(),
        "pi",
        OpenRouterConfig(),
        CacheConfig(),
    )
    assert config.cache == CacheConfig() and config.summary_synthesis_chars == 50000
    policy = MCPFormattingPolicy(None, 12000, 120, 20, "summarized", "pi", 8192)
    assert (
        policy.openrouter_max_output_tokens == 8192
        and policy.summary_synthesis_chars == 50000
    )


@pytest.mark.parametrize("change", ["allowed_bool", "missing", "code", "stage"])
def test_worker_rejects_additional_forged_diagnostics(change):
    wire = asdict(
        summary_failure("notes", "raw_budget", actual_chars=100, allowed_chars=50).info
    )
    if change == "allowed_bool":
        wire["summary_diagnostic"]["allowed_chars"] = True
    elif change == "missing":
        del wire["summary_diagnostic"]["allowed_chars"]
    elif change == "code":
        wire["code"] = "PI_CONTEXT_LIMIT"
    else:
        wire["summary_diagnostic"]["stage"] = "synthesis"
    with pytest.raises(ValueError):
        decode_worker_error(wire)


@pytest.mark.parametrize("provider", ["pi", "openrouter"])
@pytest.mark.parametrize(
    "stage,reason,context,expected",
    [
        ("notes", "raw_budget", False, "formatting.summary_synthesis_chars"),
        ("synthesis", "capacity", True, "formatting.summary_synthesis_chars"),
        ("notes", "invalid_json", False, "strict JSON notes"),
        ("notes", "invalid_schema", False, "strict JSON notes"),
        ("notes", "invalid_reference", False, "strict JSON notes"),
    ],
)
def test_summary_hints_are_trusted_and_survive_translation_roundtrip(
    provider, stage, reason, context, expected
):
    counts = (
        {"actual_chars": 100, "allowed_chars": 50} if reason == "raw_budget" else {}
    )
    exc = summary_failure(stage, reason, context=context, **counts)
    assert exc.info.hint is not None and expected in exc.info.hint
    translated = translate_formatting_error(exc, provider)
    assert translated.info.hint == exc.info.hint
    wire = asdict(translated.info)
    wire["hint"] = "private forged hint"
    decoded = decode_worker_error(wire)
    assert decoded.hint == exc.info.hint
    rendered = render_mcp_error(decoded)
    assert "private forged hint" not in rendered
    assert 'output_format="plain_text"' in rendered
    assert "smaller" not in rendered
