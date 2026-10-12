"""Offline cache-location configuration and supervised-request propagation."""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from yt_transcript import service
from yt_transcript.config import (
    AppConfig,
    CacheConfig,
    load_config,
    validate_cache_policy,
)
from yt_transcript.errors import AppError, ConfigError, render_cli_error
from yt_transcript.mcp_policy import MCPFormattingPolicy
from yt_transcript.mcp_server import WorkerRunner, create_server
from yt_transcript.mcp_worker import dispatch, validate_request
from yt_transcript.metadata import VideoMetadata
from yt_transcript.service import CleanedTranscript
from yt_transcript.transcript_cache import TranscriptCache

URL = "https://youtu.be/abcdefghijk"


@pytest.mark.parametrize("policy", [{}, {"path": ""}, {"path": None}])
def test_omitted_or_empty_path_preserves_dynamic_default(tmp_path, monkeypatch, policy):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    selected = validate_cache_policy(policy)
    assert selected.path is None
    assert TranscriptCache(**asdict(selected)).path == (
        tmp_path / "xdg" / "yt-transcript" / "transcripts.db"
    )
    monkeypatch.setenv("XDG_CACHE_HOME", "relative")
    assert TranscriptCache(**asdict(selected)).path == (
        Path.home() / ".cache" / "yt-transcript" / "transcripts.db"
    )


def test_toml_custom_database_and_home_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = tmp_path / "config.toml"
    config_file.write_text('[cache]\npath = "~/private cache/custom.sqlite3"\n')
    expected = tmp_path / "private cache" / "custom.sqlite3"
    config = load_config(config_file)
    assert config.cache.path == str(expected)
    assert validate_cache_policy(asdict(config.cache)) == config.cache
    cache = TranscriptCache(**asdict(config.cache))
    cache.cleanup()
    assert cache.path == expected and expected.is_file()
    assert not (tmp_path / ".cache" / "yt-transcript" / "transcripts.db").exists()


@pytest.mark.parametrize(
    "value",
    [
        True,
        1,
        [],
        {},
        " ",
        "relative/private.sqlite3",
        "file:///private.sqlite3",
        "/",
        "/private\x00.sqlite3",
        "/private\n.sqlite3",
        "/private\r.sqlite3",
        "/private\x7f.sqlite3",
        "/private\u0085.sqlite3",
        "/" + "x" * 4096,
        "/" + "é" * 2048,
        "/private\ud800.sqlite3",
    ],
)
def test_invalid_paths_have_safe_configuration_errors(value):
    with pytest.raises(ConfigError) as exc:
        validate_cache_policy({"path": value})
    assert exc.value.info.code == "CONFIG_INVALID"
    assert exc.value.info.message == "Invalid cache.path."
    assert "private" not in render_cli_error(exc.value)


def test_toml_relative_path_rejected(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[cache]\npath = "relative.sqlite3"\n')
    with pytest.raises(ConfigError):
        load_config(config_file)


@pytest.mark.parametrize(
    "operation,extras,target",
    [
        ("get_transcript", {}, "fetch_transcript_document"),
        ("get_video_info", {}, "get_video_info"),
        (
            "get_transcript_segment",
            {"start_seconds": 0, "end_seconds": 10},
            "get_transcript_segment",
        ),
        (
            "search_transcript",
            {"query": "test", "max_results": 10},
            "search_transcript",
        ),
        (
            "get_transcript_page",
            {"cursor": None, "max_chars": 12000},
            "get_transcript_page",
        ),
    ],
)
def test_all_worker_operations_receive_configured_database(
    tmp_path, monkeypatch, operation, extras, target
):
    expected = tmp_path / "private" / "custom.sqlite3"
    request = {
        "operation": operation,
        "url": URL,
        "mode": "filtered",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
        "cache": asdict(CacheConfig(path=str(expected))),
        **extras,
    }
    captured = []

    def perform(*args, cache, **kwargs):
        assert isinstance(cache, TranscriptCache)
        captured.append(cache.path)
        cache.cleanup()
        return {"synthetic": True}

    monkeypatch.setattr(service, target, perform)
    assert dispatch(validate_request(request)) == {"synthetic": True}
    assert captured == [expected]
    assert expected.is_file()


def test_server_keeps_cache_path_out_of_public_tool_arguments(tmp_path):
    class Runner:
        def __init__(self):
            self.calls: list[dict[str, Any]] = []

        async def close(self):
            pass

        async def run(self, payload, *, on_progress=None):
            self.calls.append(payload)
            cleaned = CleanedTranscript(
                "hello",
                VideoMetadata(
                    "https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"
                ),
                "en",
                False,
            )
            return {
                "format": "plain_text",
                "document": "hello",
                "character_count": 5,
                "metadata": cleaned.mapping(),
            }

    async def check():
        runner = Runner()
        selected = CacheConfig(path=str(tmp_path / "private" / "selected.db"))
        async with Client(
            create_server(AppConfig(cache=selected), runner=runner),
            raise_exceptions=True,
        ) as client:
            tools = (await client.list_tools()).tools
            assert all("path" not in tool.input_schema["properties"] for tool in tools)
            assert not runner.calls
            result = await client.call_tool("get_transcript", {"url": URL})
            assert not result.is_error
            assert runner.calls[0]["cache"] == asdict(selected)
            assert json.dumps(runner.calls[0]["cache"])

    asyncio.run(check())


def test_cache_constructor_position_compatibility():
    assert CacheConfig(False, 12, 20) == CacheConfig(
        enabled=False, ttl_hours=12, max_size_mb=20, path=None
    )


@pytest.mark.parametrize("control", ["\x01", "\u0085"])
def test_control_characters_in_expanded_home_are_rejected(
    tmp_path, monkeypatch, control
):
    monkeypatch.setattr(
        Path, "expanduser", lambda self: tmp_path / ("private" + control) / "cache.db"
    )
    with pytest.raises(ConfigError) as exc:
        validate_cache_policy({"path": "~/cache.db"})
    assert exc.value.info.message == "Invalid cache.path."


def test_unicode_path_and_policy_keep_utf8_worker_request_bound(monkeypatch):
    from yt_transcript.mcp_worker import REQUEST_LIMIT

    path = "/" + "/".join("é" * 100 for _ in range(20)) + "/data.sqlite3"
    request = {
        "operation": "get_transcript",
        "url": URL,
        "mode": "full",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
        "cache": asdict(CacheConfig(path=path)),
        "output_format": "markdown",
        "formatting": asdict(MCPFormattingPolicy(model="m" * 4096)),
    }
    assert len(path.encode("utf-8")) <= 4096
    assert len(json.dumps(request).encode("utf-8")) > REQUEST_LIMIT
    assert len(json.dumps(request, ensure_ascii=False).encode("utf-8")) <= REQUEST_LIMIT
    launches = []

    async def launch(*args, **kwargs):
        launches.append(True)
        raise RuntimeError("synthetic stop before child creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)

    async def check():
        runner = WorkerRunner()
        with pytest.raises(AppError) as exc:
            await runner.run(request)
        assert exc.value.info.code == "INTERNAL_ERROR" and launches == [True]
        request["formatting"] = asdict(MCPFormattingPolicy(model="😀" * 4096))
        with pytest.raises(AppError) as exc:
            await runner.run(request)
        assert exc.value.info.code == "CONFIG_INVALID" and launches == [True]

    asyncio.run(check())
