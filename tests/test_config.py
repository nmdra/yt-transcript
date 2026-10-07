from pathlib import Path

import pytest

from yt_transcript.config import (
    AppConfig,
    default_config_path,
    load_config,
    resolve_config,
)
from yt_transcript.errors import ConfigError


@pytest.mark.parametrize("xdg", ["", "relative", "/tmp/absolute"])
def test_discovery(monkeypatch, tmp_path, xdg):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", xdg)
    expected = Path(xdg) if xdg.startswith("/") else tmp_path / ".config"
    assert default_config_path() == expected / "yt-transcript/config.toml"
    assert load_config(disabled=True) == AppConfig()


@pytest.mark.parametrize(
    "text",
    [
        "[pi]\nchunk_chars=true",
        "[pi]\nchunk_chars=999",
        "[pi]\nchunk_chars=50001",
        '[pi]\nmodel=" "',
        "[pi]\nmax_chunks=0",
        "[pi]\ntimeout_seconds=3601",
        "[pi]\nother=1",
        "[other]",
        "[output]\nverbose=1",
        '[output]\nmode="other"',
        "invalid = [",
        "output = 2",
    ],
)
def test_invalid(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ConfigError):
        load_config(path)


def test_partial_and_precedence(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[pi]\nmodel=" provider/model "\nmax_chunks=2\nchunk_chars=1000')
    config = load_config(path)
    assert config.model == "provider/model"
    assert config.chunk_chars == 1000
    assert resolve_config(config, mode="raw").model is None
    assert resolve_config(config, mode="raw").max_chunks is None
    assert resolve_config(config, model="new", max_chunks=3).model == "new"
    assert load_config(path, disabled=True) == AppConfig()


def test_files(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing")
    with pytest.raises(ConfigError):
        load_config(tmp_path)
    path = tmp_path / "config"
    for content in (b"\xff", b" " * 65537):
        path.write_bytes(content)
        with pytest.raises(ConfigError):
            load_config(path)
    path.write_bytes(b"")
    assert load_config(path) == AppConfig()
