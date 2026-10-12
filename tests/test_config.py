import re
import tomllib
from pathlib import Path

import pytest

from yt_transcript.config import (
    AppConfig,
    CacheConfig,
    DeepSeekConfig,
    MCPConfig,
    SponsorBlockConfig,
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
        "[formatting]\nchunk_chars=true",
        "[formatting]\nchunk_chars=999",
        "[formatting]\nchunk_chars=50001",
        '[formatting]\nmodel=" "',
        "[formatting]\nmax_chunks=0",
        "[formatting]\ntimeout_seconds=3601",
        "[formatting]\nother=1",
        "[other]",
        "mcp = 2",
        "cache = 2",
        "[cache]\nextra=true",
        "[cache]\nenabled=1",
        "[cache]\nttl_hours=true",
        "[cache]\nttl_hours=0",
        "[cache]\nttl_hours=169",
        "[cache]\nmax_size_mb=9",
        "[cache]\nmax_size_mb=501",
        "[cache]\nmax_size_mb=50.0",
        "[mcp]\nunknown=300",
        "[mcp]\nmarkdown_timeout_seconds=true",
        "[mcp]\nmarkdown_timeout_seconds=299",
        "[mcp]\nmarkdown_timeout_seconds=3601",
        "[mcp]\nmarkdown_timeout_seconds=300.0",
        '[mcp]\nmarkdown_timeout_seconds="1800"',
        "[output]\nverbose=1",
        '[output]\nmode="other"',
        "invalid = [",
        "output = 2",
        '[formatting]\neditorial_mode="unknown"',
        '[sponsorblock]\nenabled="yes"',
        "[sponsorblock]\ncategories=[]",
        '[sponsorblock]\ncategories=["sponsor", "sponsor"]',
        '[sponsorblock]\ncategories=["filler"]',
        "[sponsorblock]\ncategories=[true]",
        "[sponsorblock]\ntimeout_seconds=31",
        "[sponsorblock]\ntimeout_seconds=true",
        '[sponsorblock]\nendpoint="private"',
    ],
)
def test_invalid(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ConfigError):
        load_config(path)


def test_partial_and_precedence(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[formatting]\nmodel=" provider/model "\nmax_chunks=2\nchunk_chars=1000'
    )
    config = load_config(path)
    assert config.model == "provider/model"
    assert config.chunk_chars == 1000
    assert resolve_config(config, mode="raw").model is None
    assert resolve_config(config, mode="raw").max_chunks is None
    assert resolve_config(config, model="new", max_chunks=3).model == "new"
    assert load_config(path, disabled=True) == AppConfig()


def test_example_documents_all_supported_settings(tmp_path):
    example = Path(__file__).resolve().parents[1] / "config.example.toml"
    assert load_config(example) == AppConfig()
    text = example.read_text(encoding="utf-8")
    complete = re.sub(
        r"^# (?=(?:max_chunks|model|enabled|thinking|thinking_level) =)",
        "",
        text,
        flags=re.M,
    )
    tables = tomllib.loads(complete)
    assert set(tables) == {
        "output",
        "formatting",
        "openrouter",
        "deepseek",
        "sponsorblock",
        "mcp",
        "cache",
    }
    assert set(tables["cache"]) == set(CacheConfig.__dataclass_fields__)
    assert set(tables["output"]) | set(tables["formatting"]) == set(
        AppConfig.__dataclass_fields__
    ) - {"sponsorblock", "mcp", "openrouter", "deepseek", "cache"}
    assert set(tables["deepseek"]) == set(DeepSeekConfig.__dataclass_fields__)
    assert set(tables["sponsorblock"]) == set(SponsorBlockConfig.__dataclass_fields__)
    assert set(tables["mcp"]) == set(MCPConfig.__dataclass_fields__)
    selected = tmp_path / "complete.toml"
    selected.write_text(complete, encoding="utf-8")
    config = load_config(selected)
    assert config == AppConfig(
        max_chunks=20,
        model="provider/model-id",
        sponsorblock=SponsorBlockConfig(enabled=False),
        thinking=False,
        thinking_level="medium",
    )


@pytest.mark.parametrize("seconds", [300, 1800, 3600])
def test_mcp_timeout_config(tmp_path, seconds):
    path = tmp_path / "config.toml"
    path.write_text(f"[mcp]\nmarkdown_timeout_seconds={seconds}")
    config = load_config(path)
    assert config.mcp == MCPConfig(seconds)
    assert resolve_config(config, mode="raw").mcp == config.mcp
    assert load_config(path, disabled=True).mcp == MCPConfig()
    assert config.timeout_seconds == 600


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
