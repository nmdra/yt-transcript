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
Install nmdra/yt-transcript v0.2.0-dev.3 for my user account with the MCP extra
and Python 3.14.7. Use the GitHub release wheel, verify SHA256SUMS,
and constrain dependencies to its source archive's uv.lock. Use an isolated
uv tool installation, not the unrelated PyPI package named yt-transcript.
Ask before replacing an existing installation or installing missing runtimes.
Keep other tools and model credentials unchanged.

Ask which MCP client(s) I want configured. Use user-level configuration unless
I approve project scope. Read each selected client's official MCP documentation;
use its native setup command or configuration format, not another client's schema.
Back up affected files and preserve existing servers and unrelated settings.
Register a local stdio server named yt-transcript with the installed executable's
absolute path and args ["--mcp", "--no-config"]. Where supported, allow a 330-second
tool-call timeout. Apply client-specific fields only when documented for that client.
Pi is the optional Markdown formatter, not a required MCP client.
Verify version, doctor, and only this server's startup/tool listing without
live YouTube, SponsorBlock, or model calls. Confirm it exposes only get_transcript.
Report installation/configuration paths, backups, checks, and any missing runtimes.
Give each selected client's reload/restart instructions.
Ask me to authenticate if access is missing. Never print credentials or add them
to URLs or project files.

Read these guides before installation or configuration:
Installation: https://github.com/nmdra/yt-transcript/blob/main/docs/installation.md
MCP setup and client documentation: https://github.com/nmdra/yt-transcript/blob/main/docs/mcp.md
Release assets: https://github.com/nmdra/yt-transcript/releases/tag/v0.2.0-dev.3
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
