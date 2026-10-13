"""Strict chapter-body protocol without model-owned chapter headings."""

from .errors import classify_pi_failure, output_failure
from .json_tools import strict_json_loads

_OUTPUT_LIMIT_BYTES = 1048576


def parse_chapter_output(
    result: str, expected_run_ids: tuple[int, ...], *, allow_empty: bool = False
) -> tuple[str, ...]:
    """Return unchanged bodies only when schema and ordered run IDs match."""
    try:
        size = len(result.encode("utf-8"))
    except UnicodeError:
        raise output_failure("chapter_invalid_json") from None
    if size > _OUTPUT_LIMIT_BYTES:
        raise classify_pi_failure(code="PI_OUTPUT_LIMIT")
    try:
        value = strict_json_loads(result)
    except ValueError, TypeError, RecursionError:
        raise output_failure("chapter_invalid_json") from None
    if not isinstance(value, dict) or set(value) != {"runs"}:
        raise output_failure("chapter_invalid_schema")
    runs = value["runs"]
    if not isinstance(runs, list):
        raise output_failure("chapter_invalid_schema")
    ids = []
    bodies = []
    for run in runs:
        if (
            not isinstance(run, dict)
            or set(run) != {"run_id", "body"}
            or not isinstance(run["body"], str)
        ):
            raise output_failure("chapter_invalid_schema")
        try:
            run["body"].encode("utf-8")
        except UnicodeError:
            raise output_failure("chapter_invalid_schema") from None
        if type(run["run_id"]) is not int:
            raise output_failure("chapter_invalid_run_ids")
        ids.append(run["run_id"])
        bodies.append(run["body"])
    if tuple(ids) != expected_run_ids or len(set(ids)) != len(ids):
        raise output_failure("chapter_invalid_run_ids")
    if not allow_empty and any(not body.strip() for body in bodies):
        raise output_failure("chapter_empty_body")
    return tuple(bodies)
