# yt-transcript

Get English YouTube video transcripts with chapter and timestamp context.
Use the CLI for raw captions or Pi-edited Markdown, or connect the MCP server to
an AI agent. No audio/video downloads or FFmpeg are required.

- MCP exposes `get_transcript`, with filtered/full modes and optional Pi Markdown output.
- MCP keeps supplied chapters or adds original-video timestamp blocks.
- SponsorBlock filtering is default for MCP and opt-in for CLI, with full-caption fallback.
- Raw output and MCP plain text call no model. Explicit Markdown uses Pi and can incur charges.

## Install

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/), Python
**3.14.7**, and [Deno](https://docs.deno.com/runtime/getting_started/installation/)
**2.3.0+**. Install [Pi](https://pi.dev) separately for Markdown editing.
Install the pinned release from this repository:

```sh
uv tool install --python 3.14.7 \
  'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git@v0.2.0-dev.3'
yt-transcript --version
yt-transcript --doctor
```

This pins the application to **0.2.0.dev3**. For verified release assets and exact
dependency versions, see [installation details](docs/installation.md).
**Bare `uvx yt-transcript` runs an unrelated PyPI project.**

## Use

Replace `URL` with a YouTube video URL:

```sh
yt-transcript URL --no-config --raw -o transcript.txt
yt-transcript URL --no-config --preview
yt-transcript URL --no-config --max-chunks 3 -o transcript.md
yt-transcript URL --no-config --editorial-mode focused --max-chunks 3 -o focused.md
```

Raw text needs no model. Preview fetches captions without calling Pi. Review its
planned call count before Markdown editing. `-o` adds YAML metadata; stdout is
body-only. Focused editing removes separable non-substantive passages.

For any compatible MCP client, follow [MCP setup](docs/mcp.md). Its default `filtered` mode attempts
SponsorBlock; `full` skips it. Default plain text calls no model; explicitly set
`output_format="markdown"` for Pi editing. CLI progress appears on terminal stderr.

## Install with an AI agent

Copy this prompt into an agent with local shell and file access:

```text
Install `nmdra/yt-transcript` `v0.2.0-dev.3` for my user account with the MCP extra using Python `3.14.7`; first read the official installation guide, MCP guide, and release page at https://github.com/nmdra/yt-transcript/blob/main/docs/installation.md, https://github.com/nmdra/yt-transcript/blob/main/docs/mcp.md, and https://github.com/nmdra/yt-transcript/releases/tag/v0.2.0-dev.3. Use the GitHub release wheel, not the unrelated PyPI package `yt-transcript`; verify it against the release `SHA256SUMS` and stop if verification fails; constrain dependencies to the same release source archive’s `uv.lock`; install it as an isolated user-level `uv tool` with the MCP extra and exactly Python `3.14.7`; ask before replacing or modifying any existing installation or installing missing runtimes/tools such as Python or `uv`; keep unrelated tools, configs, environment variables, API keys, model credentials, and existing MCP servers unchanged; configure MCP only for the client(s) I select, after reading each client’s official MCP documentation, using that client’s native setup command or config format rather than another client’s schema; if any required asset, checksum, lockfile, compatibility detail, or configuration is ambiguous, stop and explain instead of guessing; afterward, verify and report the installed version, Python version, checksum result, lockfile-constrained dependency setup, install location, MCP config changes, and a non-secret startup/connectivity check if supported.
```

## Documentation

- [Installation](docs/installation.md): prerequisites, pinned releases, updates, and uninstall
- [CLI reference](docs/cli.md): modes, configuration, preview, and file safety
- [MCP setup](docs/mcp.md): client configuration, tool results, and limits
- [Transcript behavior](docs/behavior.md): chapters, cleanup, focused editing, metadata, and filtering
- [Troubleshooting](docs/troubleshooting.md): error codes and recovery
- [Development and releases](docs/development.md): tests, live-check gates, and release workflow
- [Changelog](CHANGELOG.md)

Code is [MIT](LICENSE). SponsorBlock data is [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
unless separate permission is granted. Future public releases and PyPI publication require separate approval.
