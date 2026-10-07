"""Strict user-level TOML defaults."""

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from .errors import ConfigError, ErrorInfo


@dataclass(frozen=True)
class AppConfig:
    mode: str = "markdown"
    verbose: bool = False
    model: str | None = None
    chunk_chars: int = 12000
    timeout_seconds: int = 600
    max_chunks: int | None = None


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
    if set(data) - {"output", "pi"}:
        raise invalid("configuration table")
    values = {}
    for table, allowed in (
        ("output", {"mode", "verbose"}),
        ("pi", {"model", "chunk_chars", "timeout_seconds", "max_chunks"}),
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
            elif key == "verbose":
                valid = type(value) is bool
            elif key == "model":
                valid = isinstance(value, str) and bool(value.strip())
                if valid:
                    value = value.strip()
            else:
                lo, hi = {
                    "chunk_chars": (1000, 50000),
                    "timeout_seconds": (1, 3600),
                    "max_chunks": (1, 1000),
                }[key]
                valid = type(value) is int and lo <= value <= hi
            if not valid:
                raise invalid(f"{table}.{key}")
            values[key] = value
    return AppConfig(**values)


def resolve_config(
    file_config: AppConfig,
    *,
    mode: str | None = None,
    verbose: bool | None = None,
    model: str | None = None,
    max_chunks: int | None = None,
) -> AppConfig:
    values = {
        k: v
        for k, v in {
            "mode": mode,
            "verbose": verbose,
            "model": model,
            "max_chunks": max_chunks,
        }.items()
        if v is not None
    }
    if model is not None:
        if not model.strip():
            raise invalid("model selector")
        values["model"] = model.strip()
    if max_chunks is not None and (
        type(max_chunks) is not int or not 1 <= max_chunks <= 1000
    ):
        raise invalid("max_chunks")
    result = replace(file_config, **values)
    if result.mode != "markdown":
        result = replace(result, model=None, max_chunks=None)
    return result
