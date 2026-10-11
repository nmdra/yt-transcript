#!/usr/bin/env python3
"""Evaluate saved editorial responses offline, without importing a backend."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from yt_transcript.errors import AppError
from yt_transcript.fidelity import MODES, anchor_present, compare_fidelity
from yt_transcript.json_tools import strict_json_loads
from yt_transcript.output import write_output
from yt_transcript.summary_evidence import parse_claims

LIMIT = 8 * 1024 * 1024
SAFE_ERROR = (
    "error: Invalid fidelity data or report path; existing report was preserved.\n"
)


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str):
        raise ValueError("Invalid arguments.")


def obj(value: Any, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Invalid schema.")
    return value


def rows(value: Any, maximum: int = 512) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("Invalid list.")
    return value


def string(value: Any, *, blank: bool = False) -> str:
    if not isinstance(value, str) or (not blank and not value.strip()):
        raise ValueError("Invalid string.")
    return value


def strings(value: Any, maximum: int = 512) -> list[str]:
    return [string(v) for v in rows(value, maximum)]


def digest(value: str | bytes) -> str:
    return hashlib.sha256(
        value.encode("utf-8") if isinstance(value, str) else value
    ).hexdigest()


def read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise ValueError("Invalid file.")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Input limit.")
    parsed = strict_json_loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Invalid document.")
    return parsed, raw


def mode_map(value: Any, modes: list[str], *, groups: bool) -> dict[str, Any]:
    mapping = obj(value, set(modes))
    for mode in modes:
        if groups:
            for group in rows(mapping[mode], 128):
                if not strings(group, 16):
                    raise ValueError("Empty alternatives.")
        else:
            strings(mapping[mode], 128)
    return mapping


def validate_cases(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    obj(value, {"version", "cases"})
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("Invalid version.")
    result = {}
    for case in rows(value["cases"], 256):
        obj(
            case,
            {
                "id",
                "family",
                "modes",
                "source_spans",
                "expected_anchors",
                "removable_anchors",
                "prohibited_additions",
                "required_headings",
                "readonly_context",
                "expected_qualifications",
                "questions",
            },
        )
        key = string(case["id"])
        if not re.fullmatch(r"[a-z0-9_]{1,80}", key) or key in result:
            raise ValueError("Invalid case ID.")
        string(case["family"])
        modes = strings(case["modes"], 3)
        if not modes or len(set(modes)) != len(modes) or set(modes) - set(MODES):
            raise ValueError("Invalid modes.")
        spans = rows(case["source_spans"])
        ids = set()
        for span in spans:
            obj(span, {"id", "text"})
            source_id = string(span["id"])
            string(span["text"])
            if source_id in ids:
                raise ValueError("Duplicate source ID.")
            ids.add(source_id)
        if not spans:
            raise ValueError("Empty source.")
        mode_map(case["expected_anchors"], modes, groups=True)
        mode_map(case["removable_anchors"], modes, groups=True)
        mode_map(case["required_headings"], modes, groups=False)
        strings(case["prohibited_additions"], 128)
        strings(case["expected_qualifications"], 128)
        strings(case["questions"], 32)
        string(case["readonly_context"], blank=True)
        result[key] = case
    if not result:
        raise ValueError("Empty dataset.")
    return result


def inspect_notes(
    chunks: Any, source_ids: set[str], qualifications: list[str]
) -> dict[str, Any]:
    """Mechanical inspection of saved private JSON, not entailment validation."""
    valid = invalid = 0
    all_qualifications = []
    for chunk in rows(chunks):
        obj(chunk, {"source_ids", "response"})
        supplied = strings(chunk["source_ids"])
        if len(set(supplied)) != len(supplied) or set(supplied) - source_ids:
            raise ValueError("Invalid saved ownership.")
        try:
            claims = parse_claims(string(chunk["response"]), supplied)
            for claim in claims:
                valid += len(claim.source_ids)
                all_qualifications.extend(claim.qualifications)
        except ValueError, TypeError:
            invalid += 1
    joined = " ".join(all_qualifications)
    return {
        "valid_references": valid,
        "invalid_references_or_schema": invalid,
        "missing_annotated_qualifications": [
            q for q in qualifications if not anchor_present(joined, [q])
        ]
        if chunks
        else [],
        "qualification_check_available": bool(chunks),
        "entailment_verified": False,
    }


def evaluate(
    cases: dict[str, dict[str, Any]], responses: dict[str, Any]
) -> list[dict[str, Any]]:
    obj(responses, {"version", "responses"})
    if type(responses["version"]) is not int or responses["version"] != 1:
        raise ValueError("Invalid response version.")
    report = []
    report_bytes = 0
    seen = set()
    for response in rows(responses["responses"], 2048):
        obj(
            response,
            {"id", "case_id", "mode", "completion", "output", "notes", "provenance"},
        )
        key = string(response["id"])
        if not re.fullmatch(r"[a-z0-9_]{1,80}", key) or key in seen:
            raise ValueError("Invalid response ID.")
        seen.add(key)
        case = cases.get(string(response["case_id"]))
        mode = string(response["mode"])
        if case is None or mode not in case["modes"]:
            raise ValueError("Unknown case or mode.")
        output = string(response["output"], blank=True)
        completion = string(response["completion"])
        if completion not in {"stop", "length", "error", "refusal"}:
            raise ValueError("Invalid completion.")
        provenance = obj(
            response["provenance"],
            {"kind", "backend", "model", "calls", "prompt_sha256"},
        )
        if provenance["kind"] not in {"synthetic", "operator_supplied"} or provenance[
            "backend"
        ] not in {"fixture", "pi", "openrouter"}:
            raise ValueError("Invalid provenance.")
        string(provenance["model"])
        if (
            type(provenance["calls"]) is not int
            or not 0 <= provenance["calls"] <= 100000
        ):
            raise ValueError("Invalid call count.")
        if not re.fullmatch(r"[0-9a-f]{64}", string(provenance["prompt_sha256"])):
            raise ValueError("Invalid prompt hash.")
        source = " ".join(span["text"] for span in case["source_spans"])
        anchors = {
            str(i): alternatives
            for i, alternatives in enumerate(case["expected_anchors"][mode])
        }
        observations = compare_fidelity(
            source, output, mode, anchors, case["readonly_context"]
        )
        prohibited = [
            a for a in case["prohibited_additions"] if anchor_present(output, [a])
        ]
        headings = [line for line in output.splitlines() if line.startswith("## ")]
        required = case["required_headings"][mode]
        heading_ok = headings == required if required else True
        removable = [
            i
            for i, a in enumerate(case["removable_anchors"][mode])
            if anchor_present(output, a)
        ]
        notes = inspect_notes(
            response["notes"],
            {s["id"] for s in case["source_spans"]},
            case["expected_qualifications"],
        )
        report.append(
            {
                "response_id": key,
                "case_id": case["id"],
                "mode": mode,
                "provenance": {**provenance, "acquisition_verified": False},
                "source_sha256": digest(source),
                "response_sha256": digest(
                    json.dumps(response, ensure_ascii=False, sort_keys=True)
                ),
                "annotations": {
                    "anchor_total": len(anchors),
                    "missing_anchor_indices": observations["anchor_failures"],
                    "removable_anchor_indices_retained": removable,
                    "prohibited_additions_present": prohibited,
                    "headings_match": heading_ok,
                    "completion_failed": completion != "stop" or not output.strip(),
                    "notes": notes,
                },
                "advisory_observations": observations,
                "review": {
                    "questions": case["questions"],
                    "source_excerpt": source[:240],
                    "output_excerpt": output[:240],
                    "human_review_completed": False,
                },
            }
        )
        report_bytes += len(json.dumps(report[-1], ensure_ascii=False).encode("utf-8"))
        if report_bytes > LIMIT:
            raise ValueError("Report limit.")
    if not report:
        raise ValueError("Empty responses.")
    return report


def reject_aliases(paths: list[Path]) -> None:
    for index, path in enumerate(paths):
        for other in paths[:index]:
            if path.resolve() == other.resolve():
                raise ValueError("Path alias.")
            if path.exists() and other.exists() and os.path.samefile(path, other):
                raise ValueError("Path alias.")


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        reject_aliases([args.cases, args.responses, args.output])
        case_data, case_raw = read_json(args.cases)
        response_data, response_raw = read_json(args.responses)
        results = evaluate(validate_cases(case_data), response_data)
        data = (
            json.dumps(
                {
                    "report_version": 1,
                    "dataset_version": case_data["version"],
                    "cases_sha256": digest(case_raw),
                    "responses_sha256": digest(response_raw),
                    "offline_only": True,
                    "semantic_fidelity_verified": False,
                    "results": results,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ).encode("utf-8")
            + b"\n"
        )
        if len(data) > LIMIT:
            raise ValueError("Report limit.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_output(args.output, data)
    except AppError, OSError, ValueError, TypeError, RuntimeError, RecursionError:
        sys.stderr.write(SAFE_ERROR)
        return 1
    print("Fidelity report written. Observations require review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
