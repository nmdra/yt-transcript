"""Server-controlled, bounded policy for explicitly requested MCP Pi editing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MCPFormattingPolicy:
    model: str | None = None
    chunk_chars: int = 12000
    timeout_seconds: int = 120
    max_chunks: int = 20
    editorial_mode: str = "standard"


def validate_formatting_policy(value: object) -> MCPFormattingPolicy:
    if not isinstance(value, dict) or set(value) != {
        "model",
        "chunk_chars",
        "timeout_seconds",
        "max_chunks",
        "editorial_mode",
    }:
        raise ValueError("Invalid MCP formatting policy.")
    for key, lower, upper in (
        ("chunk_chars", 1000, 50000),
        ("timeout_seconds", 1, 120),
        ("max_chunks", 1, 1000),
    ):
        if type(value[key]) is not int or not lower <= value[key] <= upper:
            raise ValueError("Invalid MCP formatting policy.")
    model = value["model"]
    if model is not None and (
        not isinstance(model, str) or not model.strip() or len(model) > 4096
    ):
        raise ValueError("Invalid MCP formatting policy.")
    if not isinstance(value["editorial_mode"], str) or value["editorial_mode"] not in (
        "standard",
        "focused",
        "summarized",
    ):
        raise ValueError("Invalid MCP formatting policy.")
    return MCPFormattingPolicy(**value)
