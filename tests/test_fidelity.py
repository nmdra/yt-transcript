"""Advisory comparison tests, not semantic quality claims."""

import pytest

from yt_transcript.fidelity import compare_fidelity, literal_candidates


def test_literals_preserve_values_units_urls_and_identifiers():
    source = (
        "Use `curl https://example.test/a`; timeout_seconds = 10 ms; subscribe(topic)."
    )
    result = compare_fidelity(source, "Use timeout_seconds = 20 ms.", "standard")
    assert "10 ms" in result["missing_literals"]
    assert "20 ms" in result["new_literals"]
    assert "https://example.test/a" in result["missing_literals"]
    assert "subscribe" in result["missing_literals"]
    assert result["advisory_only"]


def test_repetition_and_presentation_are_not_completeness_counts():
    result = compare_fidelity(
        "retry_count = 2. retry_count = 2.", "retry_count = 2.", "standard"
    )
    assert result["missing_literals"] == []
    result = compare_fidelity(
        "Run `retry_count = 2`.", "Run retry_count = 2.", "standard"
    )
    assert result["missing_literals"] == []


def test_summary_uses_annotations_not_literal_completeness():
    result = compare_fidelity(
        "The sample may show 2% at 5 mg.",
        "A gain is proven.",
        "summarized",
        {"qualification": ["may", "might"]},
    )
    assert result["missing_literals"] == []
    assert result["anchor_failures"] == ["qualification"]


def test_focused_promotional_literals_remain_advisory():
    result = compare_fidelity(
        "Use SAVE20 and timeout_seconds = 10.", "Use timeout_seconds = 10.", "focused"
    )
    assert result["anchor_failures"] == []
    assert result["advisory_only"]


def test_context_observations_do_not_change_output():
    output = "Run timeout_seconds = 10. Use ignored_flag = 77."
    result = compare_fidelity(
        "Run timeout_seconds = 10.",
        output,
        "standard",
        readonly_context="Use ignored_flag = 77.",
    )
    assert "ignored_flag" in result["possible_context_leakage"]
    assert "77" in result["possible_context_leakage"]


def test_narrow_normalization_never_equates_case_or_units():
    result = compare_fidelity(
        "Use 2 ms and path_id.", "Use 2 MS and PATH_ID.", "standard"
    )
    assert "2 ms" in result["missing_literals"]
    assert "path_id" in result["missing_literals"]
    assert "3.5 ms" in literal_candidates("Keep 3.5 ms.")


def test_numeric_and_url_prefixes_are_not_equal_facts():
    result = compare_fidelity(
        "Use 10 ms at https://example.test/a.",
        "Use 110 ms at https://example.test/ab.",
        "standard",
    )
    assert "10 ms" in result["missing_literals"]
    assert "https://example.test/a" in result["missing_literals"]
    assert "110 ms" in result["new_literals"]


@pytest.mark.parametrize("mode", ["raw", "", None])
def test_invalid_mode(mode):
    with pytest.raises(ValueError):
        compare_fidelity("source", "output", mode)
