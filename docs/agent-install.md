# Install with an AI agent

[README](../README.md) · [Installation](installation.md) · [MCP setup](mcp.md) · [Model providers](providers.md)

Copy this prompt into an agent that has local shell and file access.
The prompt tells the agent to install the pinned release, preserve existing settings, and use only offline verification checks.

```text
Install `nmdra/yt-transcript` `v1.2.0` for my user account with the MCP extra and exactly Python `3.14.7`.

First, read the official installation guide, MCP guide, and release page:
https://github.com/nmdra/yt-transcript/blob/main/docs/installation.md
https://github.com/nmdra/yt-transcript/blob/main/docs/mcp.md
https://github.com/nmdra/yt-transcript/releases/tag/v1.2.0

Use the GitHub release wheel, not the unrelated PyPI package `yt-transcript`.
Verify the wheel and source archive against the release `SHA256SUMS`.
Stop if either check fails.
Extract dependency constraints from that release source archive's `uv.lock`. Do not execute archive content.
Install the verified wheel in an isolated user-level `uv tool` environment with the MCP extra and exactly Python `3.14.7`.

Ask before you replace an existing installation, change configuration, or install missing runtimes/tools such as Python, Deno, Pi, or `uv`.
Keep unrelated tools, environment variables, API keys, model credentials, and existing MCP servers unchanged.
Preserve the existing backend, model, editorial mode, limits, and other TOML settings unless I approve a change.
Do not overwrite an existing TOML file with the example configuration.

Configure MCP only for the client(s) I select.
Read each client's official MCP documentation first.
Use that client's native setup command or configuration format, not another client's schema.
Use the installed executable's absolute path.
Load the saved server TOML if I want its backend and editorial settings. Explain that `--no-config` bypasses those settings.

Pi remains the default backend.
If I select OpenRouter or DeepSeek, require an explicit model ID and the matching `OPENROUTER_API_KEY` or `DEEPSEEK_API_KEY` in the MCP server's inherited process environment.
Read the provider guide at https://github.com/nmdra/yt-transcript/blob/main/docs/providers.md before you change provider or thinking settings.
Do not put the key in TOML, command arguments, MCP tool arguments, or chat.
Explain that a running client does not inherit a key that I export later in another terminal.
The version 1.2.0 OpenRouter default is 16384 output tokens per model call. Reasoning tokens can use this allowance, and the selected model must support it.
A larger allowance does not guarantee completion.
Preserve any explicit output-token override.

Explain that version 1.2.0 permits only conservative ordinary-word spelling correction in model-generated Markdown.
Uncertain words, names, technical terms, and protected literals remain unchanged.
This is a prompt policy, not a guaranteed spelling checker.
Raw output and MCP plain text remain model-free.

Explain that version 1.2.0 exposes five MCP tools. `get_transcript` remains the primary tool, and its public arguments remain unchanged.
Source captions and metadata are stored privately in a shared local SQLite cache for 24 hours by default, with a 50 MiB retained-payload budget.
Preserve any saved `[cache]` settings.
The four retrieval helpers are model-free. Markdown still formats on each explicit request.
Pagination requires a stored snapshot. Expired cursors fail without refetching.
No extra dependency or setup service is needed.

Perform only offline installation checks: inspect the installed version and Python version, run CLI help and doctor, and initialize MCP and list its tools if supported.
Do not call any retrieval tool, retrieve a video, run preview, or make a model request without separate approval.
Doctor checks local readiness, not authentication or model accuracy.
Explain how to reconnect the selected MCP client. For an active Pi session, use `/reload`.

If an asset, checksum, lockfile, compatibility detail, or configuration is ambiguous, stop and explain. Do not guess.
Report the installed version, Python version, checksum results, release-locked dependency versions, install location, configuration changes, and offline startup/connectivity results. Do not include secrets.
```
