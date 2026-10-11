"""Offline evaluator schema, safety, determinism, and negative-case coverage."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/evaluate_fidelity.py"
CASES = ROOT / "tests/fixtures/editorial/fidelity_cases.json"
RESPONSES = ROOT / "tests/fixtures/editorial/fidelity_responses.json"


def module():
    spec = importlib.util.spec_from_file_location("offline_fidelity", SCRIPT)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def run(output, cases=CASES, responses=RESPONSES):
    # The child cannot use a socket or launch another process, even accidentally.
    prelude = """import builtins, runpy, socket, ssl, subprocess, sys
def forbidden(*args, **kwargs):
    raise AssertionError('External execution forbidden')
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
ssl.SSLSocket.connect = forbidden
subprocess.Popen = forbidden
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name in {'yt_transcript.formatter', 'yt_transcript.openrouter_backend', 'yt_transcript.downloader', 'yt_transcript.service', 'yt_transcript.mcp_server'}:
        raise AssertionError('Backend import forbidden')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            prelude,
            str(SCRIPT),
            "--cases",
            str(cases),
            "--responses",
            str(responses),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=10,
    )


def test_synthetic_report_is_deterministic_and_flags_loss():
    # tempfile paths are deliberately absent from the report.
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        first, second = (
            Path(directory) / "a/report.json",
            Path(directory) / "b/report.json",
        )
        assert run(first).returncode == run(second).returncode == 0
        assert first.read_bytes() == second.read_bytes()
        report = json.loads(first.read_text())
        assert report["offline_only"] and not report["semantic_fidelity_verified"]
        results = {r["response_id"]: r for r in report["results"]}
        bad = results["qualified_claim_lossy"]["annotations"]
        assert bad["missing_anchor_indices"]
        assert "proven" in bad["prohibited_additions_present"]
        good = results["long_qualifications_baseline"]["annotations"]["notes"]
        assert good["invalid_references_or_schema"] == 0
        assert good["missing_annotated_qualifications"] == []
        assert not good["entailment_verified"]
        assert results["entirely_promotional_baseline"]["annotations"][
            "completion_failed"
        ]
        assert not results["commands_baseline"]["provenance"]["acquisition_verified"]


@pytest.mark.parametrize(
    "mutation", ["unknown", "duplicate", "bad_schema", "nonfinite"]
)
def test_invalid_input_preserves_report_without_echo(tmp_path, mutation):
    raw = json.loads(RESPONSES.read_text())
    secret = "PRIVATE_SOURCE_SECRET"
    if mutation == "unknown":
        raw["responses"][0]["case_id"] = secret
        data = json.dumps(raw)
    elif mutation == "duplicate":
        data = '{"version":1,"version":1,"responses":[],"secret":"' + secret + '"}'
    elif mutation == "bad_schema":
        raw["responses"][0]["provenance"]["calls"] = True
        data = json.dumps(raw)
    else:
        data = '{"version":NaN,"responses":[]}'
    path = tmp_path / "responses.json"
    path.write_text(data)
    output = tmp_path / "report.json"
    output.write_text("old report")
    result = run(output, responses=path)
    assert result.returncode == 1
    assert output.read_text() == "old report"
    assert result.stderr == module().SAFE_ERROR
    assert secret not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_path_alias_rejection(tmp_path, alias):
    case = tmp_path / "cases.json"
    case.write_bytes(CASES.read_bytes())
    output = case
    if alias != "same":
        output = tmp_path / "report.json"
        if alias == "symlink":
            output.symlink_to(case)
        else:
            os.link(case, output)
    assert run(output, cases=case).returncode == 1
    assert case.read_bytes() == CASES.read_bytes()


def test_bounded_input_and_report(tmp_path, monkeypatch, capsys):
    oversized = tmp_path / "large.json"
    oversized.write_bytes(b" " * (8 * 1024 * 1024 + 1))
    output = tmp_path / "old.json"
    output.write_text("old")
    assert run(output, cases=oversized).returncode == 1
    evaluator = module()
    values = [
        (json.loads(CASES.read_text()), b"cases"),
        (json.loads(RESPONSES.read_text()), b"responses"),
    ]
    monkeypatch.setattr(evaluator, "read_json", lambda path: values.pop(0))
    monkeypatch.setattr(evaluator, "LIMIT", 100)
    assert (
        evaluator.main(
            [
                "--cases",
                str(CASES),
                "--responses",
                str(RESPONSES),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert output.read_text() == "old"
    assert capsys.readouterr().err == evaluator.SAFE_ERROR


def test_note_schema_reference_and_qualification_observations():
    evaluator = module()
    notes = [
        {
            "source_ids": ["span_a"],
            "response": json.dumps(
                {
                    "claims": [
                        {
                            "statement": "A gain.",
                            "source_ids": ["span_b"],
                            "qualifications": [],
                        }
                    ]
                }
            ),
        }
    ]
    report = evaluator.inspect_notes(notes, {"span_a", "span_b"}, ["small sample"])
    assert report["invalid_references_or_schema"] == 1
    assert report["missing_annotated_qualifications"] == ["small sample"]
    notes[0]["response"] = '{"claims":[],"claims":[]}'
    assert (
        evaluator.inspect_notes(notes, {"span_a"}, [])["invalid_references_or_schema"]
        == 1
    )


def test_argument_errors_do_not_echo_secrets(capsys):
    evaluator = module()
    assert evaluator.main(["--unknown-PRIVATE_SECRET"]) == 1
    assert capsys.readouterr().err == evaluator.SAFE_ERROR
