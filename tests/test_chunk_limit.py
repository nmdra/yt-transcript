"""Large source chunks remain bounded and preserve complete caption coverage."""

import json
from dataclasses import asdict

import pytest

from yt_transcript.chapters import Chapter, build_chapter_sections
from yt_transcript.cleaner import Cue
from yt_transcript.config import load_config
from yt_transcript.errors import ConfigError
from yt_transcript.formatter import plan_transcript_formatting
from yt_transcript.mcp_policy import MCPFormattingPolicy, validate_formatting_policy


@pytest.mark.parametrize("size", [1000, 50000, 50001, 200000])
def test_source_chunk_limit_matches_cli_and_mcp_policy(tmp_path, size):
    path = tmp_path / "config.toml"
    path.write_text(f"[formatting]\nchunk_chars={size}\n")
    config = load_config(path)
    assert config.chunk_chars == size
    assert (
        validate_formatting_policy(
            asdict(MCPFormattingPolicy(chunk_chars=size))
        ).chunk_chars
        == size
    )
    assert config.summary_synthesis_chars == 50000


@pytest.mark.parametrize("size", [999, 200001, True, 200000.0, "200000"])
def test_mcp_source_chunk_limit_rejects_out_of_range_or_wrong_types(size):
    with pytest.raises(ValueError):
        validate_formatting_policy(asdict(MCPFormattingPolicy(chunk_chars=size)))


def test_source_chunk_default_remains_12000():
    assert load_config(disabled=True).chunk_chars == 12000
    assert MCPFormattingPolicy().chunk_chars == 12000


def test_toml_source_chunk_limit_rejects_above_200000(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[formatting]\nchunk_chars=200001\n")
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize("chapter_mode", [False, True])
def test_200000_character_plan_preserves_all_source_words(chapter_mode):
    source = ("one two three four. " * 15000).strip()
    sections = (
        build_chapter_sections((Cue(0, 1000, source),), (Chapter("Topic", 0, 10000),))
        if chapter_mode
        else None
    )
    plan = plan_transcript_formatting(source, sections=sections, chunk_chars=200000)
    assert plan.call_count == 2
    assert 50000 < max(plan.character_counts) <= 200000
    if chapter_mode:
        retained = " ".join(
            fragment["text"]
            for chunk in plan.chunks
            for run in json.loads(chunk)["runs"]
            for fragment in run["fragments"]
        )
    else:
        retained = " ".join(plan.chunks)
    assert retained == source
