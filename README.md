# yt-transcript

Get English YouTube video transcripts with chapter and timestamp context.
Use the CLI for raw captions or Pi-edited Markdown, or connect the MCP server to
an AI agent. No audio/video downloads or FFmpeg are required.

- MCP exposes `get_transcript(url, mode="filtered")`, with optional `full` mode.
- MCP keeps supplied chapters or adds original-video timestamp blocks.
- SponsorBlock filtering is default for MCP and opt-in for CLI, with full-caption fallback.
- Raw output and MCP do not call a model. Markdown uses Pi and can incur charges.

## Install

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/), Python
**3.14.7**, and [Deno](https://docs.deno.com/runtime/getting_started/installation/)
**2.3.0+**. Install [Pi](https://pi.dev) separately for Markdown editing.
Authenticate your Git client for this private repository, then run:

```sh
uv tool install --python 3.14.7 \
  'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git@v0.2.0-dev.1'
yt-transcript --version
yt-transcript --doctor
```

This pins the application to **0.2.0.dev1**. For verified release assets and exact
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

For Pi, follow [MCP setup](docs/mcp.md). Its default `filtered` mode attempts
SponsorBlock; `full` skips it. Both return deterministic captions without Pi calls.

## Install with an AI agent

Copy this prompt into an agent with local shell and file access:

```text
Install nmdra/yt-transcript v0.2.0-dev.1 for my user account with the MCP extra
and Python 3.14.7. Use the private GitHub release wheel, verify SHA256SUMS,
and constrain dependencies to its source archive's uv.lock. Use an isolated
uv tool installation, not the unrelated PyPI package named yt-transcript.
Ask before replacing an existing installation or installing missing runtimes.
Keep other tools and model credentials unchanged.

Back up Pi's user-level mcp.json (default ~/.pi/agent/mcp.json), preserve existing
servers, and add yt-transcript with its absolute executable path, args
["--mcp", "--no-config"], timeout 330, and exposure "codemode". Set description to:
"Get YouTube video transcript with chapter and timestamp context."
Read the installed Pi MCP documentation before changing its configuration.
Verify version, doctor, and only this server's startup/tool listing without
live YouTube, SponsorBlock, or model calls. Confirm it exposes only get_transcript.
Report paths, backup, and results, and remind me to run /reload in Pi.
Ask me to authenticate if access is missing. Never print credentials or add them
to URLs or project files.
```

## Documentation

- [Installation](docs/installation.md): prerequisites, pinned releases, updates, and uninstall
- [CLI reference](docs/cli.md): modes, configuration, preview, and file safety
- [MCP setup](docs/mcp.md): Pi configuration, tool results, and limits
- [Transcript behavior](docs/behavior.md): chapters, cleanup, focused editing, metadata, and filtering
- [Troubleshooting](docs/troubleshooting.md): error codes and recovery
- [Development and releases](docs/development.md): tests, live-check gates, and release workflow
- [Changelog](CHANGELOG.md)

Code is [MIT](LICENSE). SponsorBlock data is [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
unless separate permission is granted. Public/PyPI publication is not approved.
