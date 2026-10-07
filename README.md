# yt-transcript

<img width="2172" height="724" alt="yt-transcript Workflow Overview" src="https://github.com/user-attachments/assets/c556b444-b47f-4afa-88c4-0aca64639cae" />

Get English YouTube transcripts with chapter and timestamp context.
Use the CLI for raw captions or Pi-edited Markdown, or connect the MCP server to an AI agent. No audio/video downloads or FFmpeg required.

- **CLI:** raw captions, previews, or Pi-edited Markdown
- **MCP:** `get_transcript` with `filtered` and `full` modes
- **Context:** preserves supplied chapters or adds original-video timestamp blocks
- **SponsorBlock:** enabled by default for MCP, opt-in for CLI, with full-caption fallback
- **No model required:** raw CLI output and MCP plain text make no model calls
- **Optional Pi editing:** Markdown output uses Pi and may incur model charges

## Install

Requires:

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python **3.14.7**
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) **2.3.0+**
- [Pi](https://pi.dev) separately, only for Markdown editing

> [!NOTE]
> `yt-transcript` uses the Pi agent for transcript post-processing features such as Markdown editing and focused cleanup. To use these features, Pi must be installed and configured separately. Raw transcript output and plain-text MCP usage do not require Pi.

Install the pinned release:

```sh
uv tool install --python 3.14.7 \
  'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git@v0.2.0-dev.5'

yt-transcript --version
yt-transcript --doctor
```

This pins the application to **0.2.0.dev5**.

For verified release assets, checksum verification, and exact dependency versions, see the [installation guide](docs/installation.md).

> **Important:** `uvx yt-transcript` resolves to an unrelated PyPI project. Install this project from the pinned GitHub release instead.

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
```

Raw output requires no model. `--preview` fetches captions without calling Pi and shows the planned call count before Markdown editing. When using `-o`, output includes YAML metadata; stdout is body-only.

## MCP

For any compatible MCP client, follow the [MCP setup guide](docs/mcp.md).

The MCP server exposes `get_transcript`:

- `filtered` is the default and attempts SponsorBlock filtering
- `full` skips SponsorBlock filtering
- plain-text output makes no model call
- `output_format="markdown"` explicitly enables Pi editing
- supplied chapters are preserved; otherwise timestamp context is added
- CLI progress is written to terminal stderr

## Install with an AI agent

Copy the following prompt into an agent with local shell and file access:

```text
Install `nmdra/yt-transcript` `v0.2.0-dev.5` for my user account with the MCP extra using Python `3.14.7`; first read the official installation guide, MCP guide, and release page at https://github.com/nmdra/yt-transcript/blob/main/docs/installation.md, https://github.com/nmdra/yt-transcript/blob/main/docs/mcp.md, and https://github.com/nmdra/yt-transcript/releases/tag/v0.2.0-dev.5. Use the GitHub release wheel, not the unrelated PyPI package `yt-transcript`; verify it against the release `SHA256SUMS` and stop if verification fails; constrain dependencies to the same release source archive's `uv.lock`; install it as an isolated user-level `uv tool` with the MCP extra and exactly Python `3.14.7`; ask before replacing or modifying any existing installation or installing missing runtimes/tools such as Python, Deno, or `uv`; keep unrelated tools, configs, environment variables, API keys, model credentials, and existing MCP servers unchanged; configure MCP only for the client(s) I select, after reading each client's official MCP documentation, using that client's native setup command or config format rather than another client's schema; if any required asset, checksum, lockfile, compatibility detail, or configuration is ambiguous, stop and explain instead of guessing; afterward, verify and report the installed version, Python version, checksum result, lockfile-constrained dependency setup, install location, MCP config changes, and a non-secret startup/connectivity check if supported.
```

## Documentation

- [Installation](docs/installation.md) — prerequisites, pinned releases, updates, and uninstall
- [CLI reference](docs/cli.md) — modes, configuration, preview, and file safety
- [MCP setup](docs/mcp.md) — client configuration, tool results, and limits
- [Transcript behavior](docs/behavior.md) — chapters, cleanup, focused editing, metadata, and filtering
- [Troubleshooting](docs/troubleshooting.md) — error codes and recovery
- [Development and releases](docs/development.md) — tests, live-check gates, and release workflow
- [Changelog](CHANGELOG.md)

## License

Code is licensed under [MIT](LICENSE).

SponsorBlock data is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) unless separate permission is granted.

GitHub releases use the tag-triggered public release workflow. PyPI publication requires separate approval.
