# yt-transcript

<img width="2172" height="724" alt="yt-transcript Workflow Overview" src="https://github.com/user-attachments/assets/c556b444-b47f-4afa-88c4-0aca64639cae" />

Get English YouTube transcripts with chapter and timestamp context.
Use the CLI for raw captions or Pi-edited Markdown.
You can also connect the MCP server to an AI agent.
The tool does not download audio or video and does not require FFmpeg.

- **CLI:** raw captions, previews, or Pi-edited Markdown
- **MCP:** `get_transcript` with `filtered` and `full` modes
- **Context:** keeps supplied chapters or adds timestamp blocks with original video times
- **SponsorBlock:** enabled by default for MCP; opt-in for CLI; includes full-caption fallback
- **No model required:** raw CLI output and MCP plain text make no model calls
- **Optional Pi editing:** Markdown output uses Pi and can incur model charges

## Install

Requirements:

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python **3.14.7**
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) **2.3.0+**
- [Pi](https://pi.dev), installed separately, only for Markdown editing

> [!NOTE]
> `yt-transcript` uses Pi for Markdown editing and focused cleanup after caption extraction.
> You must install and configure Pi separately to use these features.
> Raw transcript output and plain-text MCP output do not require Pi.

Install the pinned release:

```sh
uv tool install --python 3.14.7 \
  'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git@v0.2.0-dev.7'

yt-transcript --version
yt-transcript --doctor
```

This command pins the application to **0.2.0.dev7**.

For verified release assets, checksum verification, and exact dependency versions, see the [installation guide](docs/installation.md).

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
The preview shows the planned call count before Markdown editing.
With `-o`, the output file includes YAML metadata.
Stdout contains only the transcript body.

## MCP

For a compatible MCP client, follow the [MCP setup guide](docs/mcp.md).

The MCP server provides `get_transcript`:

- `filtered` is the default and attempts SponsorBlock filtering
- `full` skips SponsorBlock filtering
- Plain-text output makes no model call
- `output_format="markdown"` explicitly enables Pi editing
- Plain text keeps supplied chapters; otherwise, it adds timestamp context
- Server-configured `summarized` mode produces a whole-video summary for explicit Markdown requests
- The CLI writes progress to terminal stderr

## Install with an AI agent

Copy the following prompt into an agent with local shell and file access:

```text
Install `nmdra/yt-transcript` `v0.2.0-dev.7` for my user account with the MCP extra using Python `3.14.7`; first read the official installation guide, MCP guide, and release page at https://github.com/nmdra/yt-transcript/blob/main/docs/installation.md, https://github.com/nmdra/yt-transcript/blob/main/docs/mcp.md, and https://github.com/nmdra/yt-transcript/releases/tag/v0.2.0-dev.7. Use the GitHub release wheel, not the unrelated PyPI package `yt-transcript`; verify it against the release `SHA256SUMS` and stop if verification fails; constrain dependencies to the same release source archive's `uv.lock`; install it as an isolated user-level `uv tool` with the MCP extra and exactly Python `3.14.7`; ask before replacing or modifying any existing installation or installing missing runtimes/tools such as Python, Deno, or `uv`; keep unrelated tools, configs, environment variables, API keys, model credentials, and existing MCP servers unchanged; configure MCP only for the client(s) I select, after reading each client's official MCP documentation, using that client's native setup command or config format rather than another client's schema; if any required asset, checksum, lockfile, compatibility detail, or configuration is ambiguous, stop and explain instead of guessing; afterward, verify and report the installed version, Python version, checksum result, lockfile-constrained dependency setup, install location, MCP config changes, and a non-secret startup/connectivity check if supported.
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
