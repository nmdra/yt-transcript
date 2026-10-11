# yt-transcript

<img width="2172" height="724" alt="yt-transcript Workflow Overview" src="https://github.com/user-attachments/assets/c556b444-b47f-4afa-88c4-0aca64639cae" />

Get English YouTube transcripts with chapter and timestamp context.
Use the CLI to get raw captions or model-edited Markdown.
You can also connect an AI agent to the MCP server.
The tool does not download audio or video.
The tool does not require FFmpeg.

- **CLI:** raw captions, previews, or model-edited Markdown
- **MCP:** `get_transcript` with `filtered` and `full` modes
- **Context:** keeps supplied chapters or adds timestamp blocks with original video times
- **SponsorBlock:** enabled by default for MCP; opt-in for CLI; includes full-caption fallback
- **No model required:** raw CLI output and MCP plain text make no model calls
- **Optional model editing:** Pi is the default; OpenRouter provides a direct API backend

## Install

Requirements:

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python **3.14.7**
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) **2.3.0+**
- [Pi](https://pi.dev), installed separately, for the default Markdown backend

> [!NOTE]
> The default backend uses Pi for Markdown editing and focused cleanup after caption extraction.
> Install and configure Pi separately, or select OpenRouter with an explicit model and environment-only API key.
> Raw transcript output and plain-text MCP output do not require Pi.

Install the pinned release:

```sh
uv tool install --python 3.14.7 \
  'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git@v1.0.0'

yt-transcript --version
yt-transcript --doctor
```

This command pins the application to **1.0.0**.

See the [installation guide](docs/installation.md) for verified release assets, checksum checks, and exact dependency versions.

> **Important:** `uvx yt-transcript` selects an unrelated PyPI project. Install this project from the pinned GitHub release instead.

## Use

Replace `URL` with a YouTube video URL:

```sh
# Raw captions — no model call
yt-transcript URL --no-config --raw -o transcript.txt

# Preview planned processing without calling Pi
yt-transcript URL --no-config --preview

# Pi-edited Markdown
yt-transcript URL --no-config --max-chunks 3 -o transcript.md

# Focused editing removes separable non-substantive passages
yt-transcript URL --no-config --editorial-mode focused --max-chunks 3 -o focused.md

# Whole-video summary; the cap includes the final synthesis call
yt-transcript URL --no-config --editorial-mode summarized --max-chunks 3 -o summary.md
```

Raw output does not require a model.
`--preview` fetches captions without calling Pi.
The preview shows the number of planned calls before Markdown editing.
When the captions clearly identify the intended word, all Markdown modes allow conservative ordinary-word spelling correction.
Names, technical terms, numbers, URLs, code, commands, and uncertain words remain protected.
These are model instructions, not a guaranteed spelling check.
Raw output and MCP plain text are unchanged.
See [spelling correction limits](docs/behavior.md#conservative-spelling-correction).
If you use `-o`, the output file includes YAML metadata.
Stdout contains only the transcript body.

## OpenRouter

Direct OpenRouter formatting does not require Pi:

```sh
# Set OPENROUTER_API_KEY in the environment first; do not store it in TOML.
yt-transcript URL --no-config --provider openrouter --model openai/gpt-4o --max-chunks 3 -o transcript.md
yt-transcript URL --no-config --provider openrouter --model openai/gpt-4o --editorial-mode summarized --max-chunks 20 -o summary.md
```

Pi remains the default backend.
Raw output and MCP plain text do not use a model.
This release uses `[formatting]` instead of `[pi]`, with a separate `[openrouter]` token limit.
OpenRouter requires an explicit model ID and `OPENROUTER_API_KEY` in the process environment.
The default `openrouter.max_output_tokens` is **16384 tokens per model call**.
Reasoning tokens can consume this allowance.
The selected model must support the limit.
A larger allowance does not guarantee completion.
To save settings, edit your existing tables using [config.example.toml](config.example.toml).
For MCP, select the backend in server TOML and make the key available in the server environment.
The tool does not retry automatically or use a fallback provider.
The tool does not return partial output.
The tool sends transcript text to OpenRouter and its upstream provider.
This can incur charges.
See the [CLI provider guide](docs/cli.md#providers).
When you update from dev7, rename `[pi]` to `[formatting]`.
Keep your existing Pi settings.

## MCP

For a compatible MCP client, follow the [MCP setup guide](docs/mcp.md).

The MCP server provides `get_transcript`:

- `filtered` is the default and attempts SponsorBlock filtering
- `full` skips SponsorBlock filtering
- Plain-text output makes no model call
- `output_format="markdown"` explicitly enables the server-selected model backend
- Plain text keeps supplied chapters; otherwise, it adds timestamp context
- Server-configured `summarized` mode produces a whole-video summary for explicit Markdown requests
- The CLI writes progress to terminal stderr

**MCP retrieval tools:** The server also provides `get_video_info`, `get_transcript_segment`, `search_transcript`, and `get_transcript_page`.
The retrieval tools share a private local source-caption cache with `get_transcript`.
By default, the cache is enabled and snapshots expire 24 hours after creation.
The retrieval tools do not call a model.
Markdown still makes model calls on each request.
Markdown can also send optional progress notifications.
See [retrieval tools and cache](docs/mcp.md#retrieval-tools).

## Install with an AI agent

Copy this prompt into an agent that has local shell and file access:

```text
Install `nmdra/yt-transcript` `v1.0.0` for my user account with the MCP extra and exactly Python `3.14.7`.

First read the official installation guide, MCP guide, and release page:
https://github.com/nmdra/yt-transcript/blob/main/docs/installation.md
https://github.com/nmdra/yt-transcript/blob/main/docs/mcp.md
https://github.com/nmdra/yt-transcript/releases/tag/v1.0.0

Use the GitHub release wheel, not the unrelated PyPI package `yt-transcript`. Verify the wheel and source archive against the release `SHA256SUMS`. Stop if either check fails. Extract dependency constraints from that release source archive's `uv.lock` without executing archive content. Install the verified wheel in an isolated user-level `uv tool` environment with the MCP extra and exactly Python `3.14.7`.

Ask before replacing an existing installation, changing configuration, or installing missing runtimes/tools such as Python, Deno, Pi, or `uv`. Keep unrelated tools, environment variables, API keys, model credentials, and existing MCP servers unchanged. Preserve the existing backend, model, editorial mode, limits, and other TOML settings unless I approve a change. Do not overwrite an existing TOML file with the example configuration.

Configure MCP only for the client(s) I select. Read each client's official MCP documentation first. Use its native setup command or configuration format, not another client's schema. Use the installed executable's absolute path. Load the saved server TOML if I want its backend and editorial settings; explain that `--no-config` bypasses those settings.

Pi remains the default backend. If I select OpenRouter, require an explicit OpenRouter model ID and `OPENROUTER_API_KEY` in the MCP server's inherited process environment. Do not put the key in TOML, command arguments, MCP tool arguments, or chat. Explain that a running client does not inherit a key exported later in another terminal. The version 1.0.0 OpenRouter default is 16384 output tokens per model call; reasoning tokens can consume this allowance, and the selected model must support it. A larger allowance does not guarantee completion. Preserve any explicit output-token override.

Explain that version 1.0.0 permits only conservative ordinary-word spelling correction in model-generated Markdown. Uncertain words, names, technical terms, and protected literals remain unchanged. This is a prompt policy, not a guaranteed spelling checker. Raw output and MCP plain text remain model-free.

Explain that version 1.0.0 exposes five MCP tools, with `get_transcript` still primary and its public arguments unchanged. Source captions and metadata are stored privately in a shared local SQLite cache for 24 hours by default, with a 50 MiB retained-payload budget. Preserve any saved `[cache]` settings. The four retrieval helpers are model-free; Markdown still formats on each explicit request. Pagination needs a stored snapshot and expired cursors fail without refetching. No extra dependency or setup service is needed.

Perform offline installation checks only: inspect the installed version and Python version, run CLI help and doctor, and initialize MCP and list its tools if supported. Do not call any retrieval tool, fetch a video, run preview, or make a model request without separate approval. Doctor checks local readiness, not authentication or model accuracy. Explain how to reconnect the selected MCP client; for an active Pi session, use `/reload`.

If an asset, checksum, lockfile, compatibility detail, or configuration is ambiguous, stop and explain instead of guessing. Report the installed version, Python version, checksum results, release-locked dependency versions, install location, configuration changes, and offline startup/connectivity results without secrets.
```

## Documentation

- [Installation](docs/installation.md): prerequisites, pinned releases, updates, and uninstall
- [CLI reference](docs/cli.md): modes, configuration, preview, and file safety
- [MCP setup](docs/mcp.md): client configuration, tool results, and limits
- [Transcript behavior](docs/behavior.md): chapters, cleanup, focused editing, metadata, and filtering
- [Troubleshooting](docs/troubleshooting.md): error codes and recovery
- [Development and releases](docs/development.md): tests, conditions for live checks, and release workflow
- [Changelog](CHANGELOG.md)

## License

The code has an [MIT](LICENSE) license.

SponsorBlock data has a [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) license unless separate permission is granted.

GitHub releases use the tag-triggered public release workflow.
PyPI publication requires separate approval.
