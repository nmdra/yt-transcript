from dataclasses import asdict, replace

import pytest

from yt_transcript.config import (
    AppConfig,
    OpenRouterConfig,
    load_config,
    resolve_config,
)
from yt_transcript.errors import (
    OPENROUTER_MESSAGES,
    ConfigError,
    classify_openrouter_failure,
    decode_worker_error,
    render_cli_error,
)


def test_provider_defaults_precedence_and_raw(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[formatting]\nprovider="openrouter"\n[openrouter]\nmax_output_tokens=16000'
    )
    config = load_config(path)
    assert config.provider == "openrouter" and config.model is None
    assert config.openrouter == OpenRouterConfig(16000)
    assert AppConfig().provider == "pi"
    assert resolve_config(config, provider="pi").provider == "pi"
    assert resolve_config(config, mode="raw").model is None


@pytest.mark.parametrize(
    "table",
    [
        "[pi]",
        '[formatting]\nprovider="unknown"',
        '[openrouter]\napi_key="private"',
        "[openrouter]\nmax_output_tokens=true",
        "[openrouter]\nmax_output_tokens=0",
        "[openrouter]\nmax_output_tokens=131073",
    ],
)
def test_invalid_provider_config(tmp_path, table):
    path = tmp_path / "bad.toml"
    path.write_text(table)
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "private" not in str(exc.value)
    if table == "[pi]":
        assert "Rename [pi]" in (exc.value.info.hint or "")


@pytest.mark.parametrize("code", list(OPENROUTER_MESSAGES))
def test_openrouter_errors_rebuild_fixed_text(code):
    expected = classify_openrouter_failure(code).info
    safe = decode_worker_error(
        asdict(replace(expected, message="Bearer private", hint="/private"))
    )
    assert safe == expected
    assert "private" not in render_cli_error(classify_openrouter_failure(code))
    assert "model-processed" in render_cli_error(classify_openrouter_failure(code))
