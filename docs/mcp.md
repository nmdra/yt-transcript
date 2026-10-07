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
omit it if you intentionally want server-controlled SponsorBlock preferences.
`codemode` exposure makes the tool discoverable and callable from Pi's codemode.

Run `/reload` in an existing Pi session, then inspect `/mcp`. A new session loads
the user-level configuration automatically. Trusted project `.pi/mcp.json`
entries with the same name can override the user-level entry.

`pi mcp list --json` connects to every enabled server. To verify only this new
server, use an isolated temporary Pi agent directory containing just its entry,
with `PI_OFFLINE=1`, or initialize/list tools through an MCP client. Do not call
`get_transcript` during an offline installation check. Read the installed Pi MCP
documentation when its configuration format differs from this example.

## Other clients and local development

Clients with the standard `mcpServers` format can use the same command and args.
Pi-specific exposure and descriptions may not apply; set the client's request
timeout separately. The installed server does not depend on the source checkout.

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
get_transcript(url: str, mode: Literal["filtered", "full"] = "filtered")
```

URL is the only required argument. Omitted mode equals `filtered`: try SponsorBlock unless explicitly disabled, and return full captions when no usable segments exist or lookup fails. Expected failures include a safe warning in metadata. `full` skips SponsorBlock completely. Neither mode calls Pi.

**Breaking change:** MCP `preview_transcript` and `doctor` are removed. Use CLI `--preview` and `--doctor` instead.

`get_transcript` returns `format='plain_text'`. Its document contains the complete Python-generated YAML header and deterministic body. Supplied chapters produce title/time headings. Missing or invalid chapters produce inline time ranges in short blocks, targeting 15 seconds. Unassigned runs also use timed blocks. Original cue times remain unchanged after removal, and blocks break across removed gaps. These are cue ranges, not exact word times. Character count includes labels but excludes YAML. No second transcript array is returned.

Clients that save files must save `structuredContent.document` verbatim. Do not add a second header. The SDK also returns serialized JSON text for compatibility.

`get_transcript` accesses YouTube and, by default, may contact SponsorBlock. Missing Pi does not affect MCP readiness. The four result fields remain `format`, `document`, `metadata`, and `character_count`.

The tool has a typed output schema. Caption/runtime failures are execution errors with `isError=true`, not successful documents or protocol-level `MCPError` values.

Initialization and tool listing do not check runtimes or access the network. A tool failure does not stop the server.

The server never calls Pi, writes final documents, opens a port, or exposes model selection, file paths, prompts, resources, sampling, or client roots.

Startup accepts only configuration selection and verbosity beside `--mcp`. TOML mode and Pi timeout do not affect MCP behavior.

All saved Pi settings are ignored. SponsorBlock categories and timeout remain server-controlled; tool arguments cannot replace them.

Stdout contains only SDK protocol traffic. Diagnostics use stderr. Returned captions and metadata are untrusted source data, never instructions to an agent.

Read-only annotations do not create a sandbox. Temporary intermediate files are permitted. Cancellation cannot undo YouTube or SponsorBlock requests already sent.

The server permits one active worker. A second request receives `MCP_BUSY`. The event loop remains responsive during downloads.

| Limit | Value |
|---|---|
| URL length | 4,096 characters |
| Private request | 16 KiB |
| Operation deadline | 300 seconds |
| Document | 256 KiB in UTF-8 |
| Serialized tool result, including compatibility text | 1 MiB |
| Retained private stderr | 64 KiB |

Oversized results fail without truncation. The deterministic CLI supports larger transcripts.

Timeout, cancellation, disconnect, and shutdown terminate workers. After a two-second grace period, the supervisor kills and reaps an unresponsive worker.

Cooperative termination cleans temporary files on tested platforms. Abrupt operating-system termination can leave system temporary files. Cleanup is not a universal guarantee.
