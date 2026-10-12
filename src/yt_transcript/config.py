"""Strict user-level TOML defaults."""

import os
import tomllib
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .errors import ConfigError, ErrorInfo
from .sponsorblock import CATEGORIES, SponsorBlockConfig


@dataclass(frozen=True)
class MCPConfig:
    markdown_timeout_seconds: int = 300


@dataclass(frozen=True)
class OpenRouterConfig:
    max_output_tokens: int = 16384


@dataclass(frozen=True)
class DeepSeekConfig:
    max_output_tokens: int = 16384


@dataclass(frozen=True)
class CacheConfig:
    enabled: bool = True
    ttl_hours: int = 24
    max_size_mb: int = 50
    path: str | None = None


@dataclass(frozen=True)
class AppConfig:
    mode: str = "markdown"
    verbose: bool = False
    model: str | None = None
    chunk_chars: int = 12000
    timeout_seconds: int = 600
    max_chunks: int | None = None
    editorial_mode: str = "standard"
    sponsorblock: SponsorBlockConfig = SponsorBlockConfig()
    mcp: MCPConfig = MCPConfig()
    provider: str = "pi"
    openrouter: OpenRouterConfig = OpenRouterConfig()
    cache: CacheConfig = CacheConfig()
    summary_synthesis_chars: int = 50000
    deepseek: DeepSeekConfig = DeepSeekConfig()
    thinking: bool | None = None
    thinking_level: str | None = None


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    root = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"
    return root / "yt-transcript" / "config.toml"


def invalid(key: str = "configuration") -> ConfigError:
    return ConfigError(
        ErrorInfo(
            "CONFIG_INVALID",
            f"Invalid {key}.",
            "Correct the configuration or use --no-config.",
            "config",
        )
    )


def resolve_thinking(
    provider: str,
    editorial_mode: str,
    thinking: bool | None = None,
    thinking_level: str | None = None,
) -> tuple[bool | None, str | None]:
    """Resolve requested thinking, without checking remote model capabilities."""
    if not isinstance(provider, str) or provider not in (
        "pi",
        "openrouter",
        "deepseek",
    ):
        raise invalid("formatting.provider")
    if not isinstance(editorial_mode, str) or editorial_mode not in (
        "standard",
        "focused",
        "summarized",
    ):
        raise invalid("formatting.editorial_mode")
    if thinking is not None and type(thinking) is not bool:
        raise invalid("formatting.thinking")
    if thinking_level is not None and (
        not isinstance(thinking_level, str)
        or thinking_level not in ("low", "medium", "high")
    ):
        raise invalid("formatting.thinking_level")
    if thinking is False:
        return False, None
    if thinking is True or editorial_mode == "summarized":
        return True, thinking_level or "medium"
    if thinking_level is not None:
        raise invalid("formatting.thinking_level without enabled thinking")
    return (False, None) if provider == "deepseek" else (None, None)


def validate_cache_policy(value: object) -> CacheConfig:
    if not isinstance(value, dict) or set(value) - {
        "enabled",
        "ttl_hours",
        "max_size_mb",
        "path",
    }:
        raise invalid("cache")
    enabled = value.get("enabled", True)
    ttl = value.get("ttl_hours", 24)
    size = value.get("max_size_mb", 50)
    if type(enabled) is not bool:
        raise invalid("cache.enabled")
    if type(ttl) is not int or not 1 <= ttl <= 168:
        raise invalid("cache.ttl_hours")
    if type(size) is not int or not 10 <= size <= 500:
        raise invalid("cache.max_size_mb")
    path = value.get("path")
    if path == "":
        path = None
    if path is not None:
        if not isinstance(path, str) or any(
            unicodedata.category(c) == "Cc" for c in path
        ):
            raise invalid("cache.path")
        try:
            expanded = Path(path).expanduser()
            if (
                not expanded.is_absolute()
                or not expanded.name
                or any(unicodedata.category(c) == "Cc" for c in str(expanded))
                or len(path.encode("utf-8")) > 4096
                or len(str(expanded).encode("utf-8")) > 4096
            ):
                raise invalid("cache.path")
        except RuntimeError, UnicodeError, ValueError:
            raise invalid("cache.path") from None
        path = str(expanded)
    return CacheConfig(enabled, ttl, size, path)


def load_config(path: Path | None = None, *, disabled: bool = False) -> AppConfig:
    if disabled:
        return AppConfig()
    explicit = path is not None
    path = path.expanduser().absolute() if path is not None else default_config_path()
    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise invalid("configuration size")
        data = tomllib.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        if not explicit:
            return AppConfig()
        raise invalid("configuration file") from None
    except OSError, UnicodeError, tomllib.TOMLDecodeError:
        raise invalid("configuration file") from None
    if "pi" in data:
        raise ConfigError(
            ErrorInfo(
                "CONFIG_INVALID",
                "The legacy pi table is not supported.",
                "Rename [pi] to [formatting]; keep credentials outside TOML.",
                "config",
            )
        )
    if set(data) - {
        "output",
        "formatting",
        "openrouter",
        "deepseek",
        "sponsorblock",
        "mcp",
        "cache",
    }:
        raise invalid("configuration table")
    values: dict[str, Any] = {"cache": validate_cache_policy(data.get("cache", {}))}
    for table, allowed in (
        ("output", {"mode", "verbose"}),
        (
            "formatting",
            {
                "provider",
                "model",
                "chunk_chars",
                "summary_synthesis_chars",
                "timeout_seconds",
                "max_chunks",
                "editorial_mode",
                "thinking",
                "thinking_level",
            },
        ),
    ):
        entries = data.get(table, {})
        if not isinstance(entries, dict) or set(entries) - allowed:
            raise invalid(table)
        for key, value in entries.items():
            if key == "mode":
                valid = isinstance(value, str) and value in (
                    "markdown",
                    "raw",
                    "raw-vtt",
                )
            elif key == "provider":
                valid = isinstance(value, str) and value in (
                    "pi",
                    "openrouter",
                    "deepseek",
                )
            elif key == "editorial_mode":
                valid = isinstance(value, str) and value in (
                    "standard",
                    "focused",
                    "summarized",
                )
            elif key in ("verbose", "thinking"):
                valid = type(value) is bool
            elif key == "thinking_level":
                valid = isinstance(value, str) and value in ("low", "medium", "high")
            elif key == "model":
                valid = isinstance(value, str) and bool(value.strip())
                if valid:
                    value = value.strip()
            else:
                lo, hi = {
                    "chunk_chars": (1000, 50000),
                    "summary_synthesis_chars": (1000, 500000),
                    "timeout_seconds": (1, 3600),
                    "max_chunks": (1, 1000),
                }[key]
                valid = type(value) is int and lo <= value <= hi
            if not valid:
                raise invalid(f"{table}.{key}")
            values[key] = value
    openrouter = data.get("openrouter", {})
    if not isinstance(openrouter, dict) or set(openrouter) - {"max_output_tokens"}:
        raise invalid("openrouter")
    tokens = openrouter.get("max_output_tokens", 16384)
    if type(tokens) is not int or not 1 <= tokens <= 131072:
        raise invalid("openrouter.max_output_tokens")
    values["openrouter"] = OpenRouterConfig(tokens)
    deepseek = data.get("deepseek", {})
    if not isinstance(deepseek, dict) or set(deepseek) - {"max_output_tokens"}:
        raise invalid("deepseek")
    tokens = deepseek.get("max_output_tokens", 16384)
    if type(tokens) is not int or not 1 <= tokens <= 393216:
        raise invalid("deepseek.max_output_tokens")
    values["deepseek"] = DeepSeekConfig(tokens)
    mcp = data.get("mcp", {})
    if not isinstance(mcp, dict) or set(mcp) - {"markdown_timeout_seconds"}:
        raise invalid("mcp")
    markdown_timeout = mcp.get("markdown_timeout_seconds", 300)
    if type(markdown_timeout) is not int or not 300 <= markdown_timeout <= 3600:
        raise invalid("mcp.markdown_timeout_seconds")
    values["mcp"] = MCPConfig(markdown_timeout)
    sponsor = data.get("sponsorblock", {})
    if not isinstance(sponsor, dict) or set(sponsor) - {
        "enabled",
        "categories",
        "timeout_seconds",
    }:
        raise invalid("sponsorblock")
    enabled = sponsor.get("enabled")
    if "enabled" in sponsor and type(enabled) is not bool:
        raise invalid("sponsorblock.enabled")
    categories = sponsor.get("categories", ["sponsor", "selfpromo", "interaction"])
    if (
        not isinstance(categories, list)
        or not categories
        or any(not isinstance(c, str) or c not in CATEGORIES for c in categories)
        or len(set(categories)) != len(categories)
    ):
        raise invalid("sponsorblock.categories")
    timeout = sponsor.get("timeout_seconds", 10)
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise invalid("sponsorblock.timeout_seconds")
    values["sponsorblock"] = SponsorBlockConfig(enabled, tuple(categories), timeout)
    return AppConfig(**values)


def resolve_config(
    file_config: AppConfig,
    *,
    mode: str | None = None,
    verbose: bool | None = None,
    provider: str | None = None,
    model: str | None = None,
    max_chunks: int | None = None,
    sponsorblock: bool | None = None,
    editorial_mode: str | None = None,
) -> AppConfig:
    values = {
        k: v
        for k, v in {
            "mode": mode,
            "verbose": verbose,
            "provider": provider,
            "model": model,
            "max_chunks": max_chunks,
            "editorial_mode": editorial_mode,
        }.items()
        if v is not None
    }
    if provider is not None and provider not in ("pi", "openrouter", "deepseek"):
        raise invalid("provider")
    if editorial_mode is not None and editorial_mode not in (
        "standard",
        "focused",
        "summarized",
    ):
        raise invalid("editorial_mode")
    if model is not None:
        if not model.strip():
            raise invalid("model selector")
        values["model"] = model.strip()
    if max_chunks is not None and (
        type(max_chunks) is not int or not 1 <= max_chunks <= 1000
    ):
        raise invalid("max_chunks")
    result = replace(file_config, **values)
    if sponsorblock is not None:
        result = replace(
            result, sponsorblock=replace(result.sponsorblock, enabled=sponsorblock)
        )
    # Validate against the selected editorial mode before raw output resets it.
    resolve_thinking(
        result.provider, result.editorial_mode, result.thinking, result.thinking_level
    )
    if result.mode != "markdown":
        result = replace(result, model=None, max_chunks=None, editorial_mode="standard")
    return result
