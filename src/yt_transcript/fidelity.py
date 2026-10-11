"""Offline, advisory literal comparison. This is not a semantic validator."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

MODES = ("standard", "focused", "summarized")
NUMBER = re.compile(
    r"(?<![\w])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
    r"(?:[ \t]*(?:%|ms|s|min|h|Hz|kHz|MHz|GHz|B|KB|MB|GB|KiB|MiB|GiB|kg|mg|g|km|cm|mm|m|°C|V|mV|W)(?!\w))?"
    r"(?!\w)"
)
URL = re.compile(r"https?://[^\s<>`\"']+")
IDENTIFIER = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b|\b[A-Za-z_][A-Za-z0-9_]*(?=\()"
)
INLINE_CODE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
FENCED_CODE = re.compile(r"^```[^\n]*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)


def normalize_literal(value: str) -> str:
    """Fold whitespace only. Do not change case, values, punctuation, or units."""
    return " ".join(value.split())


def literal_candidates(value: str) -> tuple[str, ...]:
    candidates = {normalize_literal(m[0]) for m in NUMBER.finditer(value)}
    candidates.update(m[0].rstrip(".,;!?)") for m in URL.finditer(value))
    candidates.update(m[0] for m in IDENTIFIER.finditer(value))
    candidates.update(normalize_literal(m[1]) for m in INLINE_CODE.finditer(value))
    candidates.update(normalize_literal(m[1]) for m in FENCED_CODE.finditer(value))
    return tuple(sorted(candidates - {""}))


def anchor_present(value: str, alternatives: Sequence[str]) -> bool:
    normalized = normalize_literal(value)
    return any(normalize_literal(anchor) in normalized for anchor in alternatives)


def _literal_present(literal: str, text: str, candidates: set[str]) -> bool:
    if (
        NUMBER.fullmatch(literal)
        or URL.fullmatch(literal)
        or IDENTIFIER.fullmatch(literal)
    ):
        return literal in candidates
    return bool(
        re.search(
            r"(?<![\w])" + re.escape(literal) + r"(?![\w])", normalize_literal(text)
        )
    )


def compare_fidelity(
    source: str,
    output: str,
    mode: str,
    expected_anchors: Mapping[str, Sequence[str]] | None = None,
    readonly_context: str | None = None,
) -> dict[str, Any]:
    """Return suspicious observations, never a production rejection or score.

    Summaries need annotated anchors, not source-literal completeness. Focused
    omissions can be legitimate; no automatic advertising/label exemption is used.
    Repeated literals are compared once. Context observations are approximate.
    """
    if mode not in MODES:
        raise ValueError("Invalid fidelity mode.")
    source_literals = set(literal_candidates(source))
    output_literals = set(literal_candidates(output))
    normalized_output = normalize_literal(output)
    missing = sorted(
        literal
        for literal in source_literals
        if not _literal_present(literal, output, output_literals)
    )
    new = sorted(
        literal
        for literal in output_literals
        if not _literal_present(literal, source, source_literals)
    )
    context_literals = set(literal_candidates(readonly_context or "")) - source_literals
    leaks = sorted(
        literal
        for literal in context_literals
        if _literal_present(literal, output, output_literals)
    )
    if readonly_context and normalize_literal(readonly_context) in normalized_output:
        leaks = sorted(set(leaks) | {normalize_literal(readonly_context)})
    return {
        "advisory_only": True,
        "missing_literals": [] if mode == "summarized" else missing,
        "new_literals": new,
        "possible_context_leakage": leaks,
        "anchor_failures": sorted(
            name
            for name, alternatives in (expected_anchors or {}).items()
            if not anchor_present(output, alternatives)
        ),
        "limitations": [
            "Literal differences do not establish omissions or hallucinations.",
            "Focused omissions can be legitimate; summary completeness is annotation-dependent.",
            "Reference validity and literal matches do not establish entailment or truth.",
        ],
    }
