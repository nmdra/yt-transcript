# yt-transcript

<img width="2172" height="724" alt="yt-transcript Workflow Overview" src="https://github.com/user-attachments/assets/c556b444-b47f-4afa-88c4-0aca64639cae" />

Get YouTube transcripts in a caption language that you select. Use the CLI or an AI agent that uses MCP.
Save raw captions, create edited Markdown, or create a whole-video summary.
The tool uses only captions. It does not download audio or video. It does not require FFmpeg.

## Features

- **Model-free transcripts:** raw CLI output and MCP plain text make no model calls
- **Optional Markdown editing:** standard transcripts, focused cleanup, or whole-video summaries
- **Chapter and timestamp context:** supplied chapters or timestamp blocks with original video times
- **SponsorBlock filtering:** enabled by default for MCP, opt-in for CLI, with full-caption fallback
- **Agent retrieval:** video metadata, time-range excerpts, transcript search, and stable pagination
- **Language selection:** `--language` or `[captions].language`; native tracks rank first, and the tool reports every translation it uses
- **Machine-readable output:** `--json` for doctor, preview, transcript, and error output
- **Local source cache:** the CLI and MCP share private caption snapshots; snapshots expire after 24 hours by default
- **Provider choice:** Pi by default, or direct OpenRouter and DeepSeek APIs
- **Cost and output controls:** preview planned calls, set a call cap, and publish files only after processing succeeds

## Install

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/), Python **3.14.7 or newer**, and [Deno](https://docs.deno.com/runtime/getting_started/installation/) **2.3.0+**.
[yt-dlp](https://github.com/yt-dlp/yt-dlp) retrieves captions and video metadata and is installed automatically as a dependency.
The minimum supported version is **2026.10.26**, also pinned in the v1.2.2 release lockfile.
Markdown also requires a configured model backend. Raw output and MCP plain text do not require one.

Install the pinned **v1.2.2** release with MCP support:

```sh
uv tool install --python 3.14.7 \
  'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git@v1.2.2'

yt-transcript --version
yt-transcript --doctor
```

> **Important:** Bare `uvx yt-transcript` and `uv tool install yt-transcript` select an unrelated PyPI project. Use this repository's pinned tag or verified release wheel.

Use the [installation guide](docs/installation.md) for verified assets, exact dependency versions, and updates.
For detailed agent setup instructions, use the [agent installation guide](docs/agent-install.md).

### Install with an AI agent

Copy this prompt into an agent that has local shell and file access:

```text
Install `nmdra/yt-transcript` latest version with MCP extra using exactly Python via isolated user-level `uv tool`. Follow official docs(https://github.com/nmdra/yt-transcript/tree/main/docs); use GitHub release assets, not PyPI, and verify wheel/source SHA256 and `uv.lock` dependencies. Stop on errors or ambiguity; require consent before installing tools, replacing installations, or changing settings, while preserving existing configuration, credentials, cache, and MCP servers. Configure only selected clients using official methods and absolute paths. Default to Pi; OpenRouter and Deepseek requires an explicit model ID and securely inherited API key. Run offline checks only, without retrieval or model calls, and report verified results without secrets.
```

## CLI quickstart

Replace `URL` with a YouTube video URL.
These examples use `--no-config` to ignore saved wrapper settings. Omit this option to use your configuration.

### Get captions without a model

```sh
# Save cleaned captions with YAML metadata
yt-transcript URL --no-config --raw -o transcript.txt

# Write only the transcript body to stdout
yt-transcript URL --no-config --raw

# Save unchanged caption VTT
yt-transcript URL --no-config --raw-vtt -o captions.vtt
```

### Create Markdown or a summary

Set up [Pi](https://pi.dev), the default backend, or follow the [provider guide](docs/providers.md) for OpenRouter or DeepSeek.

```sh
# Fetch captions and inspect the plan without a model call
yt-transcript URL --no-config --preview

# Create an edited transcript
yt-transcript URL --no-config --max-chunks 3 -o transcript.md

# Remove separable non-substantive passages
yt-transcript URL --no-config --editorial-mode focused --max-chunks 3 -o focused.md

# Create a whole-video summary
yt-transcript URL --no-config --editorial-mode summarized --max-chunks 3 -o summary.md
```

Markdown sends captions to the selected model and can incur charges.
`--max-chunks` limits planned model calls, including final synthesis for multi-chunk summaries.
Preview retrieves captions but never calls a model.
If a plan exceeds the limit, it fails before any model calls. The tool does not process only part of the video.

Raw and Markdown files written with `-o` include YAML metadata. Stdout contains only the body.
The tool does not automatically retry model calls, switch providers, or publish partial output.
See the [CLI reference](docs/cli.md) for configuration, spelling-correction limits, preview details, and file safety.

## MCP quickstart

Connect the installed executable to your MCP client using the [MCP setup guide](docs/mcp.md).
Use the executable's absolute path and `--mcp`. Keep existing client configuration and server settings.

The primary tool returns model-free plain text by default:

```text
get_transcript(url="URL")                  # filtered, with SponsorBlock fallback
get_transcript(url="URL", mode="full")     # skip SponsorBlock
```

Plain text preserves chapters or timestamp context. Request `output_format="markdown"` only if you want model editing through the server-selected backend.

| Tool | Use |
| --- | --- |
| `get_transcript` | Get the complete transcript as plain text or explicit Markdown |
| `get_video_info` | Get video metadata |
| `get_transcript_segment` | Get original cues for a time range |
| `search_transcript` | Find words or phrases with timestamp links |
| `get_transcript_page` | Read a stored transcript in pages |

The four retrieval helpers never call a model.
They share the local source-caption cache with `get_transcript`. Markdown still makes model calls on each explicit request.
See [tool contracts and cache settings](docs/mcp.md#retrieval-tools).

## Documentation

- [Installation](docs/installation.md): prerequisites, verified releases, updates, and uninstall
- [Agent installation prompt](docs/agent-install.md): safe setup through an AI agent
- [Model providers](docs/providers.md): Pi, OpenRouter, DeepSeek, API keys, thinking, and token limits
- [CLI reference](docs/cli.md): modes, configuration, preview, and file safety
- [MCP setup](docs/mcp.md): client configuration, tool results, and cache settings
- [Pi prompt example](docs/pi-prompt.md): `/yt` commands for summaries, concept explanations, and Obsidian notes
- [Transcript behavior](docs/behavior.md): chapters, cleanup, summaries, metadata, and filtering
- [Troubleshooting](docs/troubleshooting.md): error codes and recovery
- [Development and releases](docs/development.md): tests, live-check approval, and release workflow
- [Changelog](CHANGELOG.md)

## License

The code has an [MIT](LICENSE) license.
SponsorBlock data has a [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) license unless separate permission is granted.

GitHub releases use the tag-triggered public release workflow.
PyPI publication requires separate approval.
