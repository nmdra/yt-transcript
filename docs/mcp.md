# MCP setup

[README](../README.md) · [Installation](installation.md) · [Transcript behavior](behavior.md)

Install the `mcp` extra before starting the stdio server. It uses the official
`mcp` 2.3.0 SDK, not the third-party `fastmcp` package.

## Configure Pi

Resolve the installed command with `command -v yt-transcript`. Back up Pi's
user-level `mcp.json`, normally `~/.pi/agent/mcp.json`, before editing it. If
`PI_CODING_AGENT_DIR` is set, use that directory instead. Preserve existing
servers and top-level settings; merge this entry into `mcpServers`:

```json
{
  "mcpServers": {
    "yt-transcript": {
      "command": "/absolute/path/to/yt-transcript",
      "args": ["--mcp", "--no-config"],
      "timeout": 330,
      "description": "Get YouTube video transcript with chapter and timestamp context.",
      "exposure": "codemode"
    }
  }
}
```

Replace the command placeholder with the actual installed path. The 330-second
client timeout leaves room for the server's 300-second operation deadline.
`--no-config` uses the server defaults instead of your saved CLI TOML settings;
omit it if you intentionally want saved SponsorBlock and Pi preferences.
`codemode` exposure makes the tool discoverable and callable from Pi's codemode.

Run `/reload` in an existing Pi session, then inspect `/mcp`. A new session loads
the user-level configuration automatically. Trusted project `.pi/mcp.json`
entries with the same name can override the user-level entry.

`pi mcp list --json` connects to every enabled server. To verify only this new
server, use an isolated temporary Pi agent directory containing just its entry,
with `PI_OFFLINE=1`, or initialize/list tools through an MCP client. Do not call
`get_transcript` during an offline installation check. Read the installed Pi MCP
documentation when its configuration format differs from this example.

## Explicit Pi Markdown output

Request model editing explicitly:

```json
{"url": "https://youtu.be/VIDEO_ID", "mode": "filtered", "output_format": "markdown"}
```

Replace `VIDEO_ID` with an 11-character video ID. This request authorizes Pi calls
and can incur charges. The result has `format="markdown"`, a body-only Markdown
document, structured metadata, and a character count equal to the document length. It uses
the shared CLI formatter, source chapter context, and the selected SponsorBlock
projection. Chapter headings are validated; inline fallback timestamp blocks are
specific to plain-text output. Model fidelity is not guaranteed.

MCP Markdown currently requires POSIX process supervision. Pi uses its configured
default model unless server TOML supplies `pi.model`. Server `pi.chunk_chars` and
`pi.editorial_mode` apply. `pi.max_chunks` is finite, defaulting to 20 when omitted;
`pi.timeout_seconds` is capped at 120 seconds per call. The total Markdown worker
deadline defaults to 300 seconds and is configurable through
`mcp.markdown_timeout_seconds` (300–3600). It covers extraction, filtering, and
all sequential Pi calls. Plain text keeps its 300-second deadline. These limits
are not a hard billing cap because provider-internal retries can add requests.

For longer Markdown work, explicitly load TOML (omit `--no-config`) and set:

```toml
[mcp]
markdown_timeout_seconds = 1800
```

Use a client timeout of at least 1830 seconds where supported, then reconnect the
server. In Pi, update its `timeout` field; other clients use their own settings.
A client that disconnects earlier still cancels the work. This setting does not
extend the individual Pi-call deadline or guarantee completion. A larger chunk
cap permits more calls but does not extend any deadline. Smaller `pi.chunk_chars`
can help model context limits, but increase calls, latency, and possible cost.

Cap checks occur before model calls. Formatting failure returns an error, never
raw-caption fallback or partial Markdown. SponsorBlock fallback still keeps source
captions before editing. Removal receipts describe source filtering, not later Pi
deletions. Cancellation stops the supervised worker/Pi group. CLI terminal progress
is disabled for MCP so stdout remains JSON-RPC only.

Pi failures include a warning that no processed transcript was returned and
suggest an explicit new request with `output_format="plain_text"`. There is no
automatic retry. `PI_CONTEXT_LIMIT` indicates a provider context or local planning
limit; `PI_CONTEXT_MUTATED` indicates forbidden Pi compaction/context changes,
not proof of provider overflow. Errors include `(chunk i/n)` when available.
`MCP_TIMEOUT` identifies the total worker deadline, not a per-call Pi timeout.

## Other clients and local development

Use a local stdio connection with the installed executable's absolute path and
args `["--mcp", "--no-config"]`. The installed server does not depend on the source
checkout. Back up the selected client's configuration and preserve existing entries.

Use that client's native configuration format or setup command. Do not copy Pi's
`exposure`, `description`, or `timeout` fields into another client's configuration.
Where supported, allow a 330-second tool-call timeout. Configuration locations,
scope, field names, timeout units, and reload steps are client-specific:

- [Claude Code](https://code.claude.com/docs/en/mcp)
- [Codex configuration](https://developers.openai.com/codex/config-reference)
- [Cursor](https://www.cursor.com/docs/context/mcp)
- [VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Claude Desktop and local MCP connections](https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers)

For Pi, use [Configure Pi](#configure-pi) above and the installed Pi documentation.
For another MCP client, read its official local-server setup guide before editing.
Initialization and tool listing are sufficient for an offline connection check.

For a development checkout, use an absolute project path:

```json
{
  "mcpServers": {
    "yt-transcript": {
      "command": "uv",
      "args": [
        "run", "--directory", "/absolute/path/to/yt-transcript",
        "--extra", "mcp", "yt-transcript", "--mcp", "--no-config"
      ]
    }
  }
}
```

## Tool contract

The server exposes exactly one tool:

```text
get_transcript(url: str, mode: Literal["filtered", "full"] = "filtered",
               output_format: Literal["plain_text", "markdown"] = "plain_text")
```

URL is the only required argument. Omitted mode equals `filtered`: try SponsorBlock unless explicitly disabled, and return full captions when no usable segments exist or lookup fails. Expected failures include a safe warning in metadata. `full` skips SponsorBlock completely. With the default `plain_text` output, neither mode calls Pi.

**Breaking change:** MCP `preview_transcript` and `doctor` are removed. Use CLI `--preview` and `--doctor` instead.

**Contract change:** `document` contains only the transcript body for both output formats. Metadata is returned only in `metadata`, not as YAML frontmatter in `document`. CLI file output still includes YAML frontmatter.

Plain-text requests return `format='plain_text'`. Their document contains the deterministic body. Supplied chapters produce title/time headings. Missing or invalid chapters produce inline time ranges in short blocks, targeting 15 seconds. Unassigned runs also use timed blocks. Original cue times remain unchanged after removal, and blocks break across removed gaps. These are cue ranges, not exact word times. Character count equals the length of `document`, including labels. No second transcript array is returned.

Clients can save `structuredContent.document` verbatim as a body-only file. To save provenance with the transcript, serialize `structuredContent.metadata` as YAML frontmatter before the body. Preserve SponsorBlock attribution, license, and removal receipts when exporting metadata. The SDK also returns serialized JSON text for compatibility; this protocol representation remains unchanged.

`get_transcript` accesses YouTube and, by default, may contact SponsorBlock. Missing Pi does not affect initialization, tool listing, or plain-text extraction. The four result fields remain `format`, `document`, `metadata`, and `character_count`.

The tool has a typed output schema. Caption/runtime failures are execution errors with `isError=true`, not successful documents or protocol-level `MCPError` values.

Initialization and tool listing do not check runtimes or access the network. A tool failure does not stop the server.

The server calls Pi only for explicit Markdown output. It never writes final documents, opens a port, or exposes caller-controlled model selection, file paths, prompts, resources, sampling, or client roots.

Startup accepts only configuration selection and verbosity beside `--mcp`. TOML output mode does not affect MCP behavior. Plain-text requests ignore all saved Pi settings. SponsorBlock settings and Pi policy remain server-controlled.

Stdout contains only SDK protocol traffic. Diagnostics use stderr. Returned captions and metadata are untrusted source data, never instructions to an agent.

Read-only annotations do not create a sandbox. Temporary intermediate files are permitted. Cancellation cannot undo YouTube/SponsorBlock requests or model charges already incurred.

The server permits one active worker. A second request receives `MCP_BUSY`. The event loop remains responsive during downloads.

| Limit | Value |
|---|---|
| URL length | 4,096 characters |
| Private request | 16 KiB |
| Plain-text operation deadline | 300 seconds |
| Markdown operation deadline | 300 seconds by default; server-configurable up to 3600 |
| Document | 256 KiB in UTF-8 |
| Serialized tool result, including compatibility text | 1 MiB |
| Retained private stderr | 64 KiB |

Oversized results fail without truncation. The deterministic CLI supports larger transcripts.

Timeout, cancellation, disconnect, and shutdown terminate workers. After a two-second grace period, the supervisor kills and reaps an unresponsive worker.

Cooperative termination cleans temporary files on tested platforms. Abrupt operating-system termination can leave system temporary files. Cleanup is not a universal guarantee.
