"""Server-controlled, bounded policy for explicitly requested model editing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MCPFormattingPolicy:
    model: str | None = None
    chunk_chars: int = 12000
    timeout_seconds: int = 120
    max_chunks: int = 20
    editorial_mode: str = "standard"
    provider: str = "pi"
    openrouter_max_output_tokens: int = 16384
    summary_synthesis_chars: int = 50000
    deepseek_max_output_tokens: int = 16384
    thinking: bool | None = None
    thinking_level: str | None = None


def validate_formatting_policy(value: object) -> MCPFormattingPolicy:
    legacy_fields = {
        "model",
        "chunk_chars",
        "summary_synthesis_chars",
        "timeout_seconds",
        "max_chunks",
        "editorial_mode",
        "provider",
        "openrouter_max_output_tokens",
    }
    new_fields = {"deepseek_max_output_tokens", "thinking", "thinking_level"}
    if not isinstance(value, dict) or set(value) not in (
        legacy_fields,
        legacy_fields | new_fields,
    ):
        raise ValueError("Invalid MCP formatting policy.")
    if "deepseek_max_output_tokens" in value and (
        type(value["deepseek_max_output_tokens"]) is not int
        or not 1 <= value["deepseek_max_output_tokens"] <= 393216
    ):
        raise ValueError("Invalid MCP formatting policy.")
    for key, lower, upper in (
        ("chunk_chars", 1000, 50000),
        ("summary_synthesis_chars", 1000, 500000),
        ("timeout_seconds", 1, 120),
        ("max_chunks", 1, 1000),
        ("openrouter_max_output_tokens", 1, 131072),
    ):
        if type(value[key]) is not int or not lower <= value[key] <= upper:
            raise ValueError("Invalid MCP formatting policy.")
    if not isinstance(value["provider"], str) or value["provider"] not in (
        "pi",
        "openrouter",
        "deepseek",
    ):
        raise ValueError("Invalid MCP formatting policy.")
    model = value["model"]
    if model is not None and (
        not isinstance(model, str) or not model.strip() or len(model) > 4096
    ):
        raise ValueError("Invalid MCP formatting policy.")
    if value["provider"] in ("openrouter", "deepseek") and model is None:
        raise ValueError("Invalid MCP formatting policy.")
    if not isinstance(value["editorial_mode"], str) or value["editorial_mode"] not in (
        "standard",
        "focused",
        "summarized",
    ):
        raise ValueError("Invalid MCP formatting policy.")
    from .config import resolve_thinking
    from .errors import AppError

    try:
        resolve_thinking(
            value["provider"],
            value["editorial_mode"],
            value.get("thinking"),
            value.get("thinking_level"),
        )
    except AppError, ValueError:
        raise ValueError("Invalid MCP formatting policy.") from None
    return MCPFormattingPolicy(**value)
