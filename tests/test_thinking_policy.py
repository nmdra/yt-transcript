"""Strict shared thinking configuration and pure mode policy."""

from itertools import product

import pytest

from yt_transcript.config import (
    AppConfig,
    DeepSeekConfig,
    load_config,
    resolve_config,
    resolve_thinking,
)
from yt_transcript.errors import ConfigError

CASES = list(
    product(
        ("pi", "openrouter", "deepseek"),
        ("standard", "focused", "summarized"),
        (None, False, True),
        (None, "low", "medium", "high"),
    )
)


@pytest.mark.parametrize("provider,mode,thinking,level", CASES)
def test_shared_precedence(provider, mode, thinking, level):
    if thinking is None and level is not None and mode != "summarized":
        with pytest.raises(ConfigError) as exc:
            resolve_thinking(provider, mode, thinking, level)
        assert exc.value.info.code == "CONFIG_INVALID"
        return
    if thinking is False:
        expected = False, None
    elif thinking is True or mode == "summarized":
        expected = True, level or "medium"
    else:
        expected = (False, None) if provider == "deepseek" else (None, None)
    assert resolve_thinking(provider, mode, thinking, level) == expected


@pytest.mark.parametrize(
    "thinking,level",
    [
        (0, None),
        (1, None),
        ("false", None),
        ([], None),
        ({}, None),
        (None, False),
        (None, 1),
        (None, []),
        (None, ["medium"]),
        (None, "max"),
        (False, "private-level"),
        (True, "MEDIUM"),
    ],
)
def test_invalid_values_are_safe(thinking, level):
    with pytest.raises(ConfigError) as exc:
        resolve_thinking("pi", "summarized", thinking, level)
    assert exc.value.info.code == "CONFIG_INVALID"
    assert "private-level" not in str(exc.value)


@pytest.mark.parametrize(
    "provider,mode",
    [
        ("private-provider", "standard"),
        ("pi", "private-mode"),
        ([], "standard"),
        ("pi", []),
    ],
)
def test_invalid_provider_or_mode_is_safe(provider, mode):
    with pytest.raises(ConfigError) as exc:
        resolve_thinking(provider, mode)
    assert "private-" not in str(exc.value)


@pytest.mark.parametrize(
    "text", ["", "[deepseek]", '[formatting]\nprovider="deepseek"']
)
def test_deepseek_defaults(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    assert DeepSeekConfig().max_output_tokens == 16384
    assert load_config(path).deepseek == DeepSeekConfig()
    assert load_config(disabled=True).deepseek == DeepSeekConfig()
    assert AppConfig().thinking is None
    assert AppConfig().thinking_level is None


@pytest.mark.parametrize("tokens", [1, 16384, 131073, 393216])
def test_deepseek_token_override(tmp_path, tokens):
    path = tmp_path / "config.toml"
    path.write_text(f"[deepseek]\nmax_output_tokens={tokens}")
    assert load_config(path).deepseek.max_output_tokens == tokens


@pytest.mark.parametrize(
    "text",
    [
        "deepseek=2",
        '[deepseek]\napi_key="PRIVATE_KEY"',
        "[deepseek]\nmax_output_tokens=true",
        "[deepseek]\nmax_output_tokens=0",
        "[deepseek]\nmax_output_tokens=393217",
        "[deepseek]\nmax_output_tokens=16384.0",
        '[formatting]\nthinking="false"',
        "[formatting]\nthinking=1",
        "[formatting]\nthinking=[]",
        '[formatting]\nthinking_level=["low","high"]',
        "[formatting]\nthinking_level=true",
        '[formatting]\nthinking_level="max"',
        '[formatting]\nthinking_level="PRIVATE_LEVEL"',
    ],
)
def test_invalid_toml(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert exc.value.info.code == "CONFIG_INVALID"
    assert "PRIVATE_" not in str(exc.value)


def test_cross_settings_use_final_cli_editorial_mode(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[formatting]\nthinking_level="low"')
    config = load_config(path)
    with pytest.raises(ConfigError):
        resolve_config(config)
    selected = resolve_config(config, editorial_mode="summarized")
    assert resolve_thinking(
        selected.provider,
        selected.editorial_mode,
        selected.thinking,
        selected.thinking_level,
    ) == (True, "low")
    with pytest.raises(ConfigError):
        resolve_config(selected, editorial_mode="focused")


@pytest.mark.parametrize("raw", ["raw", "raw-vtt"])
def test_raw_validates_before_reset_and_preserves_inactive_controls(raw):
    config = AppConfig(editorial_mode="summarized", thinking_level="low")
    selected = resolve_config(config, mode=raw)
    assert selected.editorial_mode == "standard"
    assert selected.thinking is None
    assert selected.thinking_level == "low"
    with pytest.raises(ConfigError):
        resolve_config(AppConfig(thinking_level="low"), mode=raw)
    disabled = resolve_config(
        AppConfig(thinking=False, thinking_level="high"), mode=raw
    )
    assert disabled.thinking is False and disabled.thinking_level == "high"


def test_existing_appconfig_positional_arguments_stay_in_place():
    values = AppConfig("raw", True, "model", 2000, 10, 2, "focused")
    assert values.mode == "raw"
    assert values.verbose is True
    assert values.model == "model"
    assert values.chunk_chars == 2000
    assert values.timeout_seconds == 10
    assert values.max_chunks == 2
    assert values.editorial_mode == "focused"
    assert values.deepseek == DeepSeekConfig()
    assert values.thinking is None and values.thinking_level is None


def test_deepseek_provider_override_and_raw_model_removal():
    config = AppConfig(provider="openrouter", model="old")
    selected = resolve_config(config, provider="deepseek", model="deepseek-flash")
    assert selected.provider == "deepseek" and selected.model == "deepseek-flash"
    assert resolve_config(selected, mode="raw").model is None
