"""Strict JSON parsing shared by private protocols and offline evidence."""

import json
from typing import Any


def strict_json_loads(value: str) -> Any:
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate JSON key.")
            result[key] = item
        return result

    def constant(value):
        raise ValueError("Nonfinite JSON value.")

    try:
        return json.loads(value, object_pairs_hook=pairs, parse_constant=constant)
    except RecursionError:
        raise ValueError("JSON nesting is too deep.") from None
