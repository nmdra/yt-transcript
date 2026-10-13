import json
from dataclasses import asdict

import pytest

from yt_transcript.chapter_output import parse_chapter_output
from yt_transcript.errors import (
    FormattingError,
    decode_worker_error,
    render_cli_error,
    render_diagnostics,
    render_mcp_error,
)


def payload(ids=(2, 5), bodies=("First body.", "Second body.")):
    return json.dumps(
        {"runs": [{"run_id": i, "body": b} for i, b in zip(ids, bodies, strict=True)]}
    )


def test_roundtrip_preserves_body_content_and_unicode():
    bodies = (
        '  Quotes "quoted", backslash \\, colon: brackets [] {}.\nCafé 日本語 🐍  ',
        "\nA second paragraph.\n\n*Literal Markdown*.\t",
    )
    for ensure_ascii in (True, False):
        raw = json.dumps(
            {
                "runs": [
                    {"run_id": i, "body": b}
                    for i, b in zip((2, 5), bodies, strict=True)
                ]
            },
            ensure_ascii=ensure_ascii,
        )
        assert parse_chapter_output(raw, (2, 5)) == bodies


def assert_reason(raw, reason, expected=(2, 5), **kwargs):
    with pytest.raises(FormattingError) as caught:
        parse_chapter_output(raw, expected, **kwargs)
    exc = caught.value
    assert exc.info.code == "PI_OUTPUT_INVALID"
    assert exc.info.message.endswith(f" Validation reason: {reason}.")
    assert exc.info.summary_diagnostic is None
    return exc


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not JSON PRIVATE_MODEL_CONTENT",
        '```json\n{"runs": []}\n```',
        'Commentary {"runs": []}',
        '{"runs": []} trailing commentary',
        '{"runs": [], "runs": []}',
        '{"runs": [{"run_id": 2, "run_id": 2, "body": "secret"}]}',
        '{"runs": [{"run_id": 2, "body": "a", "body": "b"}]}',
        '{"runs": NaN}',
        '{"runs": Infinity}',
        '{"runs": -Infinity}',
        '{"runs": [}',
    ],
)
def test_rejects_non_strict_json(raw):
    assert_reason(raw, "chapter_invalid_json")


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        "text",
        {},
        {"runs": [], "extra": "secret"},
        {"runs": {}},
        {"runs": None},
        {"runs": "text"},
        {"runs": [None]},
        {"runs": [[]]},
        {"runs": [{}]},
        {"runs": [{"run_id": 2}]},
        {"runs": [{"body": "secret"}]},
        {"runs": [{"run_id": 2, "body": "secret", "extra": True}]},
        {"runs": [{"run_id": 2, "body": None}]},
        {"runs": [{"run_id": 2, "body": 42}]},
        {"runs": [{"run_id": 2, "body": []}]},
    ],
)
def test_rejects_invalid_schema(value):
    assert_reason(json.dumps(value), "chapter_invalid_schema")


@pytest.mark.parametrize(
    "ids",
    [
        (),
        (2,),
        (2, 5, 7),
        (2, 2),
        (2, 7),
        (5, 2),
        (True, 5),
        (2.0, 5),
        ("2", 5),
        (None, 5),
    ],
)
def test_rejects_invalid_run_identity_and_order(ids):
    assert_reason(payload(ids, ("Body",) * len(ids)), "chapter_invalid_run_ids")


def test_parser_recursion_failure_is_safe(monkeypatch):
    import yt_transcript.chapter_output as chapter_output

    def recursive(raw):
        raise RecursionError("PRIVATE_MODEL_CONTENT")

    monkeypatch.setattr(chapter_output, "strict_json_loads", recursive)
    assert_reason(payload(), "chapter_invalid_json")


def test_boolean_is_not_integer_identity():
    assert_reason(payload((True,), ("Body",)), "chapter_invalid_run_ids", expected=(1,))


@pytest.mark.parametrize("body", ["", " ", "\t\n\r", "\u2003"])
def test_blank_body_requires_focused_opt_in(body):
    raw = payload(bodies=("Body", body))
    assert_reason(raw, "chapter_empty_body")
    assert parse_chapter_output(raw, (2, 5), allow_empty=True) == ("Body", body)


def test_focused_mode_still_requires_all_ids():
    assert_reason(payload((2,), ("",)), "chapter_invalid_run_ids", allow_empty=True)


def test_does_not_validate_or_edit_markdown_structure():
    bodies = ("---\ntitle: test\n---\nBody", "# Heading\n```\nUnclosed fence")
    assert parse_chapter_output(payload(bodies=bodies), (2, 5)) == bodies


@pytest.mark.parametrize("body", ["\ud800", "\udfff", "Body \ud800 text"])
def test_rejects_escaped_lone_surrogate_in_body(body):
    assert_reason(payload(bodies=(body, "Body")), "chapter_invalid_schema")


def test_rejects_raw_invalid_unicode_without_echo():
    assert_reason("\ud800", "chapter_invalid_json")


def test_empty_expected_runs_accepts_empty_list():
    assert parse_chapter_output('{"runs": []}', ()) == ()


def test_limit_counts_utf8_bytes_and_applies_before_parsing(monkeypatch):
    import yt_transcript.chapter_output as chapter_output

    def unexpected_parse(raw):
        pytest.fail("Oversized output must not reach JSON parsing")

    monkeypatch.setattr(chapter_output, "strict_json_loads", unexpected_parse)
    for raw in ("x" * (1048576 + 1), "é" * 524289):
        with pytest.raises(FormattingError) as caught:
            parse_chapter_output(raw, (2, 5))
        assert caught.value.info.code == "PI_OUTPUT_LIMIT"
        assert "Validation reason:" not in caught.value.info.message


def test_exact_byte_limit_is_accepted():
    prefix, suffix = '{"runs":[{"run_id":2,"body":"', '"}]}'
    body = "x" * (1048576 - len(prefix) - len(suffix))
    assert parse_chapter_output(prefix + body + suffix, (2,)) == (body,)


def test_invalid_json_errors_do_not_leak_model_content():
    secret = "PRIVATE_MODEL_CONTENT Bearer token=secret /home/private"
    exc = assert_reason(secret, "chapter_invalid_json")
    decoded = decode_worker_error(asdict(exc.info))
    rendered = (
        str(exc)
        + render_cli_error(exc)
        + render_mcp_error(decoded)
        + render_diagnostics(exc)
    )
    for fragment in (
        "PRIVATE_MODEL_CONTENT",
        "Bearer",
        "token=secret",
        "/home/private",
    ):
        assert fragment not in rendered
    assert exc.__cause__ is None
