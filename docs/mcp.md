# MCP setup

[README](../README.md) · [Installation](installation.md) · [Transcript behavior](behavior.md)

Install the `mcp` extra before you start the stdio server.
The server uses the official `mcp` 2.3.0 SDK, not the third-party `fastmcp` package.

## Configure Pi

Use `command -v yt-transcript` to find the installed command.
Back up Pi's user-level `mcp.json` before you edit the file.
The file is normally at `~/.pi/agent/mcp.json`.
If `PI_CODING_AGENT_DIR` is set, use that directory instead.
Keep existing servers and top-level settings.
Add this entry to `mcpServers`:

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

Replace the command placeholder with the installed path.
The 330-second client timeout allows time beyond the server's 300-second operation deadline.
`--no-config` uses server defaults instead of your saved CLI TOML settings.
Omit this flag if you want to use saved SponsorBlock and Pi preferences.
The `codemode` exposure setting lets Pi's codemode find and call the tool.

In an existing Pi session, run `/reload`.
Then inspect `/mcp`.
A new session loads the user-level configuration automatically.
Trusted project `.pi/mcp.json` entries can override user-level entries with the same name.

`pi mcp list --json` connects to every enabled server.
To verify only this new server, use an isolated temporary Pi agent directory with only its entry and `PI_OFFLINE=1`.
Alternatively, initialize the server and list its tools through an MCP client.
Do not call `get_transcript` during an offline installation check.
If the installed Pi configuration format differs from this example, read the installed Pi MCP documentation.

## Explicit Pi Markdown output

Request model editing explicitly:

```json
{"url": "https://youtu.be/VIDEO_ID", "mode": "filtered", "output_format": "markdown"}
```

Replace `VIDEO_ID` with an 11-character video ID.
This request authorizes Pi calls and can incur charges.
The result has `format="markdown"`, a Markdown document that contains only the transcript body, and structured metadata.
The character count equals the document length.
The request uses the shared CLI formatter, source chapter context, and selected SponsorBlock projection.
The formatter validates chapter headings.
Inline fallback timestamp blocks apply only to plain-text output.
Model fidelity is not guaranteed.

MCP Markdown currently requires POSIX process supervision.
Pi uses its configured default model unless server TOML supplies `pi.model`.
Server `pi.chunk_chars` and `pi.editorial_mode` apply.
`pi.max_chunks` is finite and defaults to 20 when omitted.
`pi.timeout_seconds` is limited to 120 seconds per call.

The total Markdown worker deadline defaults to 300 seconds.
Set `mcp.markdown_timeout_seconds` to change this deadline (300–3600).
The deadline includes extraction, filtering, and all sequential Pi calls.
Plain text keeps its 300-second deadline.
These limits are not a hard billing cap.
Provider-internal retries can add requests.

For longer Markdown work, omit `--no-config` to load TOML.
Set:

```toml
[mcp]
markdown_timeout_seconds = 1800
```

Where supported, use a client timeout of at least 1830 seconds.
In Pi, update its `timeout` field.
Other clients use their own settings.
Then reconnect the server.
If a client disconnects earlier, the disconnection still cancels the work.

This setting does not extend the individual Pi-call deadline or guarantee completion.
A larger chunk cap permits more calls but does not extend any deadline.
Smaller `pi.chunk_chars` can help with model context limits.
However, smaller chunks increase calls, delay, and possible cost.

The server checks the cap before model calls.
A formatting failure returns an error.
The server never returns raw captions as a fallback or partial Markdown after a formatting failure.
SponsorBlock fallback still keeps source captions before editing.
Removal receipts describe source filtering, not later Pi deletions.
Cancellation stops the supervised worker/Pi group.
MCP disables CLI terminal progress so stdout contains only JSON-RPC.

Pi failures include a warning that no processed transcript was returned.
The warning suggests an explicit new request with `output_format="plain_text"`.
There is no automatic retry.
`PI_CONTEXT_LIMIT` indicates a provider context limit or local planning limit.
`PI_CONTEXT_MUTATED` indicates forbidden Pi compaction or context changes.
This error does not prove provider overflow.
Errors include `(chunk i/n)` when available.
`MCP_TIMEOUT` identifies the total worker deadline, not a per-call Pi timeout.

## Other clients and local development

Use a local stdio connection with the installed executable's absolute path and args `["--mcp", "--no-config"]`.
The installed server does not depend on the source checkout.
Back up the selected client's configuration.
Keep existing entries.

Use that client's native configuration format or setup command.
Do not copy Pi's `exposure`, `description`, or `timeout` fields into another client's configuration.
Where supported, allow a 330-second tool-call timeout.
Configuration locations, scope, field names, timeout units, and reload steps depend on the client:

- [Claude Code](https://code.claude.com/docs/en/mcp)
- [Codex configuration](https://developers.openai.com/codex/config-reference)
- [Cursor](https://www.cursor.com/docs/context/mcp)
- [VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Claude Desktop and local MCP connections](https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers)

For Pi, use [Configure Pi](#configure-pi) above and the installed Pi documentation.
For another MCP client, read its official local-server setup guide before you edit configuration.
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

The server provides exactly one tool:

```text
get_transcript(url: str, mode: Literal["filtered", "full"] = "filtered",
               output_format: Literal["plain_text", "markdown"] = "plain_text")
```

URL is the only required argument.
If you omit the mode, the server uses `filtered`.
This mode attempts SponsorBlock unless you explicitly disable it.
The mode returns full captions when no usable segments exist or lookup fails.
Expected failures include a safe warning in metadata.
`full` skips SponsorBlock completely.
With the default `plain_text` output, neither mode calls Pi.

**Breaking change:** MCP `preview_transcript` and `doctor` are removed.
Use CLI `--preview` and `--doctor` instead.

**Contract change:** `document` contains only the transcript body for both output formats.
The result returns metadata only in `metadata`, not as YAML frontmatter in `document`.
CLI file output still includes YAML frontmatter.

Metadata includes an always-present `description` field: extractor text or `null`.
Both modes and output formats include the same description for the same source snapshot.
The SDK compatibility JSON includes it too.
Descriptions stay out of `document`, `character_count`, and Pi input.
Clients that reject unknown metadata keys must update for this additional field.
See [Metadata files](behavior.md#metadata-files) for normalization and source-data limits.

Plain-text requests return `format='plain_text'`.
The document contains the deterministic body.
Supplied chapters produce title/time headings.
Missing or invalid chapters produce inline time ranges in short blocks, targeting 15 seconds.
Unassigned runs also use timed blocks.
Original cue times remain unchanged after removal.
Blocks break across removed gaps.
These are cue ranges, not exact word times.
The character count equals the length of `document`, including labels.
The result does not include a second transcript array.

Clients can save `structuredContent.document` unchanged as a file that contains only the transcript body.
To save provenance with the transcript, serialize `structuredContent.metadata` as YAML frontmatter before the body.
Keep SponsorBlock attribution, license, and removal receipts when you export metadata.
The SDK also returns serialized JSON text for compatibility.
This protocol representation remains unchanged.

`get_transcript` accesses YouTube and, by default, can contact SponsorBlock.
Missing Pi does not affect initialization, tool listing, or plain-text extraction.
The four result fields remain `format`, `document`, `metadata`, and `character_count`.

The tool has a typed output schema.
Caption/runtime failures are execution errors with `isError=true`.
These failures are not successful documents or protocol-level `MCPError` values.

Initialization and tool listing do not check runtimes or access the network.
A tool failure does not stop the server.

The server calls Pi only for explicit Markdown output.
The server never writes final documents or opens a port.
The server does not expose caller-controlled model selection, file paths, prompts, resources, sampling, or client roots.

At startup, the server accepts only configuration selection and verbosity in addition to `--mcp`.
TOML output mode does not affect MCP behavior.
Plain-text requests ignore all saved Pi settings.
SponsorBlock settings and Pi policy remain server-controlled.

Stdout contains only SDK protocol traffic.
Diagnostics use stderr.
Returned captions and metadata are untrusted source data.
They are never instructions to an agent.

Read-only annotations do not create a sandbox.
Temporary intermediate files are permitted.
Cancellation cannot undo YouTube/SponsorBlock requests or model charges already incurred.

The server permits one active worker.
A second request receives `MCP_BUSY`.
The event loop remains responsive during downloads.

| Limit | Value |
|---|---|
| URL length | 4,096 characters |
| Private request | 16 KiB |
| Plain-text operation deadline | 300 seconds |
| Markdown operation deadline | 300 seconds by default; server-configurable up to 3600 |
| Document | 256 KiB in UTF-8 |
| Serialized tool result, including compatibility text | 1 MiB |
| Retained private stderr | 64 KiB |

Descriptions count toward the serialized result limit, including their compatibility JSON copy.
A long description can exceed this limit even when the document fits its own limit.
Oversized results fail without truncation.
For Markdown, a result-size error can occur after Pi calls.
The deterministic CLI supports larger transcripts.

Timeout, cancellation, disconnect, and shutdown stop workers.
After a two-second grace period, the supervisor kills and reaps an unresponsive worker.

Cooperative termination cleans temporary files on tested platforms.
Abrupt operating-system termination can leave system temporary files.
Cleanup is not guaranteed.
