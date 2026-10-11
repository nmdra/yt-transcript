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
If you want to use saved SponsorBlock and Pi preferences, omit this flag.
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

## OpenRouter server backend

Keep `get_transcript` arguments unchanged.
Select the backend only in server TOML:

```toml
[formatting]
provider = "openrouter"
model = "openai/gpt-4o"
max_chunks = 20

[openrouter]
max_output_tokens = 16384
```

Launch without `--no-config` and make `OPENROUTER_API_KEY` available in the server environment.
Do not put the key in tool arguments, private worker JSON, or TOML.
After an approved configuration or installation update, reconnect the MCP server.
Explicit Markdown uses OpenRouter without Pi.
Plain text remains usable without a key or model.
Pi as an MCP client is separate from the server's formatting backend.
Both backends retain the POSIX restriction for supervised MCP Markdown.
Deadlines, one-active-worker behavior, result sizes, metadata, and safe errors remain unchanged.
See [CLI provider limits](cli.md#providers) for routing, privacy, and output-token limits.

When updating from dev7, rename `[pi]` to `[formatting]`. Pi remains the default backend.

## Explicit model-processed Markdown output

Request model editing explicitly:

```json
{"url": "https://youtu.be/VIDEO_ID", "mode": "filtered", "output_format": "markdown"}
```

Replace `VIDEO_ID` with an 11-character video ID.
This request authorizes model calls and can incur charges.
The result has `format="markdown"`, a Markdown document that contains only the transcript body, and structured metadata.
The character count equals the document length.
The request uses the shared CLI formatter, source chapter context, and selected SponsorBlock projection.
Standard and focused modes validate canonical chapter headings.
Summarized mode validates summary headings instead.
Source chapters remain in metadata.
Inline fallback timestamp blocks apply only to plain-text output.
Model fidelity is not guaranteed.

MCP Markdown currently requires POSIX process supervision.
If server TOML does not supply `formatting.model`, Pi uses its configured default model.
OpenRouter always requires an explicit model.
Server `formatting.chunk_chars` and `formatting.editorial_mode` apply.
`formatting.max_chunks` is finite and defaults to 20 when omitted.
`formatting.timeout_seconds` is limited to 120 seconds per call.

For a whole-video summary, use server TOML:

```toml
[formatting]
editorial_mode = "summarized"
max_chunks = 20
```

Start the server with that configuration and without `--no-config`.
Then reconnect the server.
Continue to request `output_format="markdown"`.
There is no caller-controlled `editorial_mode` tool argument.
The shared formatter targets 400–700 words, shorter for short sources.
One source chunk uses one summary call.
Multiple chunks use factual notes plus one final synthesis call.
The cap includes synthesis, so the default cap allows at most 19 source chunks when synthesis is needed.
An infeasible note budget fails before model calls.
The server returns no intermediate notes, private source IDs, partial summary, automatic retry, or fallback.
Summary notes use strict references from the same call and qualification arrays internally.
Valid references do not establish factual support.
Summary quality and target length are not guaranteed.
Descriptions stay outside model input, and metadata and the four result fields stay unchanged.
Plain-text requests still return captions without an AI model.
Read-only boundary context remains zero for MCP.
There is no new caller or server setting for boundary context.

The total Markdown worker deadline defaults to 300 seconds.
Set `mcp.markdown_timeout_seconds` to change this deadline (300–3600).
The deadline includes extraction, filtering, and all sequential model calls.
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
If a client disconnects earlier, the work is still canceled.

This setting does not extend the individual model-call deadline or guarantee completion.
A larger chunk cap permits more calls but does not extend any deadline.
Smaller `formatting.chunk_chars` can help with model context limits.
However, smaller chunks increase calls, delay, and possible cost.

The server checks the cap before model calls.
A formatting failure returns an error.
The server never returns raw captions as a fallback or partial Markdown after a formatting failure.
SponsorBlock fallback still keeps source captions before editing.
Removal receipts describe source filtering, not later model deletions or summary omissions.
Cancellation stops the supervised worker/model-helper group.
MCP disables CLI terminal progress so stdout contains only JSON-RPC.

Model failures include a warning that no processed transcript was returned.
The warning suggests an explicit new request with `output_format="plain_text"`.
There is no automatic retry.
`PI_CONTEXT_LIMIT` indicates a provider context limit or local planning limit.
`PI_CONTEXT_MUTATED` indicates forbidden Pi compaction or context changes.
This error does not prove provider overflow.
Errors include `(chunk i/n)` when available.
`MCP_TIMEOUT` identifies the total worker deadline, not a per-call model timeout.

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
To check an offline connection, initialize the server and list its tools.

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

`get_transcript` remains the primary tool and is listed first.
The development checkout adds four [retrieval tools](#retrieval-tools); these additions are not yet in the pinned dev9 release.

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
If you use the default `plain_text` output, neither mode calls Pi.

**Breaking change:** MCP `preview_transcript` and `doctor` are removed.
Use CLI `--preview` and `--doctor` instead.

**Contract change:** `document` contains only the transcript body for both output formats.
The result returns metadata only in `metadata`, not as YAML frontmatter in `document`.
CLI file output still includes YAML frontmatter.

Metadata includes an always-present `description` field: extractor text or `null`.
Both modes and output formats include the same description for the same source snapshot.
The SDK compatibility JSON also includes the description.
Descriptions stay out of `document`, `character_count`, and model input.
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

On a source-cache miss, `get_transcript` accesses YouTube and, by default, can contact SponsorBlock.
A valid same-policy cache hit reuses the source captions and metadata.
Missing Pi does not affect initialization, tool listing, or plain-text extraction.
The four result fields remain `format`, `document`, `metadata`, and `character_count`.

The tool has a typed output schema.
Caption/runtime failures are execution errors with `isError=true`.
These failures are not successful documents or protocol-level `MCPError` values.

Initialization and tool listing do not check runtimes or access the network.
A tool failure does not stop the server.

The server calls the selected provider only for explicit Markdown output.
The server never writes final documents or opens a port.
The server does not expose caller-controlled model selection, file paths, prompts, resources, sampling, or client roots.

At startup, the server accepts only configuration selection and verbosity in addition to `--mcp`.
TOML output mode does not affect MCP behavior.
Plain-text requests ignore all saved formatting settings.
SponsorBlock settings and formatting policy remain server-controlled.

Stdout contains only SDK protocol traffic.
Diagnostics use stderr.
Returned captions and metadata are untrusted source data.
They are never instructions to an agent.

Read-only annotations do not create a sandbox.
Temporary intermediate files and the private source-caption cache are permitted.
Cancellation cannot undo YouTube/SponsorBlock requests or model charges already incurred.

The server permits one active worker.
A second request receives `MCP_BUSY`.
The event loop remains responsive during downloads.

| Limit | Value |
|---|---|
| URL length | 4,096 characters |
| Private request | 16 KiB |
| Plain-text and retrieval operation deadline | 300 seconds |
| Markdown operation deadline | 300 seconds by default; server-configurable up to 3600 |
| Document | 256 KiB in UTF-8 |
| Serialized tool result, including compatibility text | 1 MiB |
| Accepted private progress records per operation | 64 KiB |

Descriptions count toward the serialized result limit, including their compatibility JSON copy.
A long description can exceed this limit even when the document fits its own limit.
Oversized results fail without truncation.
For Markdown, model calls can finish before a result-size error occurs.
The deterministic CLI supports larger transcripts.

Timeout, cancellation, disconnect, and shutdown stop workers.
After a two-second grace period, the supervisor kills and reaps an unresponsive worker.

Cooperative termination cleans temporary files on tested platforms.
Abrupt operating-system termination can leave system temporary files.
Cleanup is not guaranteed.

## Retrieval tools

These four additions are available in the development checkout, not the pinned dev9 release.
All return structured data and compatibility JSON.
They use the same supervised worker and source cache as `get_transcript`.
They never call Pi or OpenRouter.
Initialization and discovery remain network-free.

```text
get_video_info(url: str)
get_transcript_segment(url: str, start_seconds: float, end_seconds: float,
                       mode: Literal["filtered", "full"] = "filtered")
search_transcript(url: str, query: str,
                  mode: Literal["filtered", "full"] = "filtered", max_results: int = 10)
get_transcript_page(url: str, cursor: str | None = None, max_chars: int = 12000,
                    mode: Literal["filtered", "full"] = "filtered")
```

| Tool | Exact result fields | Behavior |
|---|---|---|
| `get_video_info` | `metadata` | Complete existing metadata mapping, using filtered policy |
| `get_transcript_segment` | `video_id, mode, cues` | Original cues intersecting the requested time range |
| `search_transcript` | `video_id, query, matches` | Literal, case-insensitive search with normalized whitespace |
| `get_transcript_page` | `video_id, document, has_more, next_cursor` | Whole timestamped cues from one stored snapshot |

A cold metadata request also fetches captions.
It can fail when usable English captions are unavailable.
Its metadata includes the same description, provenance, attribution, and filtering receipts as `get_transcript`.

Segments allow finite, nonnegative times with start less than end and an interval of at most 900 seconds.
At most 200 cues are returned; larger results fail without silent truncation.
Each cue has `start_seconds, end_seconds, text, url`.
Overlap includes the whole cue, with its original start/end times.
Zero-duration cues are included when their timestamp is within the requested interval.

Search allows a nonblank query of up to 200 characters and max_results from 1 through 20.
The returned query is whitespace-normalized and casefolded.
Phrases can cross adjoining cues, but cannot cross removed source cues.
Results use earliest timestamps, with source order for ties.
Each match has `start_seconds, end_seconds, text, context, url`.
Text preserves the complete covered cues; surrounding context is limited to 500 characters.
No match returns `matches: []`.

For example:

```json
{"name":"get_transcript_segment","arguments":{"url":"https://youtu.be/abcdefghijk","start_seconds":120,"end_seconds":240}}
{"name":"search_transcript","arguments":{"url":"https://youtu.be/abcdefghijk","query":"authentication","max_results":10}}
{"name":"get_transcript_page","arguments":{"url":"https://youtu.be/abcdefghijk","max_chars":12000}}
```

Replace the example ID with a real video ID before making a request.
Timestamp URLs point to original cue times, not word-level alignment.

Pages allow max_chars from 1000 through 20000, default 12000.
Each document uses one original timestamp range per cue.
Pages retain source order, including backward timestamps, and do not omit or repeat cues.
The final page can be shorter than 1000 characters.
If one cue cannot fit, the request fails with `MCP_RESPONSE_LIMIT`.

A page result can look like:

```json
{
  "video_id": "abcdefghijk",
  "document": "[00:00 - 00:02] Hello everyone",
  "has_more": true,
  "next_cursor": "opaque-snapshot-cursor"
}
```

Use the returned cursor unchanged for the next request, with the same URL, mode, and server policy.
The example cursor above is illustrative, not valid input.
A final page has `has_more=false` and `next_cursor=null`.
Malformed or mismatched cursors return `CACHE_CURSOR_INVALID`.
Expired, evicted, replaced, corrupt, or unreadable snapshots return `CACHE_CURSOR_EXPIRED`; continuation never fetches new captions.
The cursor is for stable paging, not authentication.

Invalid segment ranges return `SEGMENT_RANGE_INVALID`.
Invalid search queries or result bounds return `SEARCH_QUERY_INVALID`.
Invalid page-size bounds return `CONFIG_INVALID`.
All helpers retain the serialized result limit, safe errors, 300-second deadline, and one-active-worker limit.

## Local source cache

The development checkout enables a shared SQLite cache for MCP only.
It stores source cues, original timestamps, complete metadata, caption provenance, and SponsorBlock lookup data.
It does not store model-generated Markdown or credentials.
CLI behavior remains uncached.

Default settings:

```toml
[cache]
enabled = true
ttl_hours = 24
max_size_mb = 50
```

TTL allows integers from 1 through 168 hours and is measured from snapshot creation.
Access does not extend expiry.
The payload budget allows integers from 10 through 500 MiB.
Physical SQLite files can be larger than that budget.
Individual snapshots are limited to 5 MiB.

The location is `$XDG_CACHE_HOME/yt-transcript/transcripts.db` when XDG_CACHE_HOME is absolute, otherwise `~/.cache/yt-transcript/transcripts.db`.
On POSIX, the app directory and database use owner-only permissions.
Unsafe existing paths are rejected.
Source captions and descriptions are untrusted text stored locally.
They reach a model only for explicitly requested Markdown.

Equivalent video URL forms share a snapshot when mode and resolved SponsorBlock policy match.
Full and filtered use separate keys.
Policy changes, expiry, or eviction can require a new extraction.
An effective failed SponsorBlock lookup is not cached as a successful filtered result, including a removal that would empty the captions.
A successful not_found lookup may be cached.
No cache refresh tool or flag is provided.

With caching disabled or unavailable, transcript, metadata, search, and segment requests fetch normally.
Paging requires a stored snapshot and returns `CACHE_UNAVAILABLE` if it cannot retain one.
Cache faults do not increase model calls or change the no-model default.
Each Markdown request still calls the configured formatter.

To clear saved source data, stop all yt-transcript servers first.
Delete only the app's `yt-transcript` cache directory, including its SQLite sidecar files.
Restart the server afterward.
Keep unrelated cache directories and configuration files unchanged.

## Optional Markdown progress

Clients can request MCP progress notifications per explicit Markdown call.
The server reports completed model-call counts, including summary synthesis when needed.
Clients without a progress token receive the same final result without notifications.
Source fetching has no estimated percentage.

Progress does not extend a deadline or create a background task.
Cancellation and disconnect still stop the supervised worker.
Malformed worker progress is discarded, and arbitrary stderr is not forwarded.
Worker progress lines are limited to 512 bytes and accepted records to 64 KiB per operation.
Notification failure does not produce a partial result or trigger a model retry.
There are no task IDs, polling tools, or queues.
