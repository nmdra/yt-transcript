# yt-transcript

Get one English YouTube caption track. Clean it deterministically, or edit it into Markdown through the local Pi CLI.

The project requires Python 3.14.7 or newer. Local development uses the installed stable Python 3.14.7, pinned in `.python-version`.

It does not download video or audio. It does not require FFmpeg.

**Bare `uvx yt-transcript` runs an unrelated PyPI project.** This project retains that name for Git-first delivery only. Publication is not approved.

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) through its official instructions.

From this project directory, run:

```sh
uv sync --locked --group dev --extra mcp
uv run yt-transcript --help
uv run yt-transcript --version
```

Install [Deno](https://docs.deno.com/runtime/getting_started/installation/) separately. Deno must be on `PATH`. The selected yt-dlp release supports Deno 2.3.0 or newer.

The `yt-dlp[default]` dependency supplies EJS scripts. The locked yt-dlp 2026.8.19 release requires yt-dlp-ejs 0.8.0. Automatic remote EJS component downloads are disabled.

For Markdown, install [Pi](https://pi.dev) separately. The formatter supports the Pi 1.0.4 CLI interface or newer compatible releases.

Pi offers an official installer and an npm package. The npm method requires Node.js 22.19 or newer:

```sh
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Authenticate directly in Pi through `/login`. Select or save a default model through `/model`. This wrapper never installs runtimes or changes credentials.

## Output modes

```sh
uv run yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config
uv run yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --raw
uv run yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --raw-vtt -o captions.vtt
uv run yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --model provider/model-id -o transcript.md
```

| Mode | Body | Pi | File metadata |
|---|---|---|---|
| Default | Edited Markdown | Yes | YAML with `-o` |
| `--raw` | One normalized paragraph | No | YAML with `-o` |
| `--raw-vtt` | Unchanged VTT bytes | No | None |

Stdout contains only the body. File output leaves stdout empty. All non-VTT bodies end with one newline.

Use `-o` for Python-generated YAML metadata. Shell redirection receives the body only:

```sh
uv run yt-transcript URL --no-config --raw > body.txt
uv run yt-transcript URL --no-config --raw -o transcript.txt
uv run yt-transcript URL --no-config --raw | wc -w
```

The URL must contain an 11-character video ID. Supported hosts are `youtube.com`, `www.youtube.com`, `m.youtube.com`, and `youtu.be`.

Watch, shorts, and embed URLs are supported. A playlist parameter on a video URL does not enable playlist downloads.

## Configuration

The wrapper reads `$XDG_CONFIG_HOME/yt-transcript/config.toml` when `XDG_CONFIG_HOME` is an absolute, nonempty path. Otherwise, it reads `~/.config/yt-transcript/config.toml`.

Relative XDG paths are ignored. Project files and parent directories are never searched. A missing default file uses built-in defaults.

`--config PATH` selects one file instead of discovery. `--no-config` disables wrapper configuration. These flags do not change Pi configuration or credentials.

The precedence is explicit CLI flags, then the selected TOML file, then built-in defaults:

```toml
[output]
mode = "markdown"       # "markdown", "raw", or "raw-vtt"
verbose = false

[pi]
chunk_chars = 12000
timeout_seconds = 600
# max_chunks = 20
# Omit model to use Pi's configured default.
# model = "provider/model-id"
```

Unknown keys, invalid types, malformed TOML, and files larger than 64 KiB are errors. The wrapper does not create configuration files.

| Key | Valid values |
|---|---|
| `output.mode` | `markdown`, `raw`, `raw-vtt` |
| `output.verbose` | Boolean |
| `pi.model` | Nonempty selector string, or omit the key |
| `pi.chunk_chars` | Integer 1,000 through 50,000 |
| `pi.timeout_seconds` | Integer 1 through 3,600, per chunk |
| `pi.max_chunks` | Integer 1 through 1,000, or omit for unlimited |

`--raw`, `--raw-vtt`, `--model`, `--max-chunks`, and `-v` override their corresponding defaults. There is no `--markdown` or `--quiet` flag.

Raw modes ignore saved Pi preferences after schema checks. An explicit CLI model or chunk cap conflicts with a raw mode.

Without an explicit model in TOML or CLI, every Pi call omits `--model`. Pi chooses its configured default. The wrapper never selects a fallback model.

Help, version, and doctor ignore wrapper TOML. A malformed configuration still blocks raw mode unless `--no-config` is supplied.

## Preview and cost controls

```sh
uv run yt-transcript URL --no-config --preview
uv run yt-transcript URL --no-config --max-chunks 10 -o transcript.md
```

Preview downloads and cleans captions, but never calls Pi. It shows these fields in a fixed order:

1. Canonical URL
2. Cleaned character count
3. Planned formatter invocations
4. Largest chunk size
5. Configured chunk limit
6. Maximum chunks
7. Cap result
8. Model selection

Preview requires Markdown mode and no output path. A cap exceedance is a successful preview report. Actual formatting rejects the cap before any Pi call.

Preview is not a cache or a reservation. A later run downloads again. Invocation counts are not token counts, dollar estimates, or exact provider-request counts.

The formatter splits on sentence boundaries or whitespace without token splits or overlap. It sends chunks sequentially through independent in-memory Pi sessions.

The formatter joins completed bodies without a final synthesis call. It does not summarize, globally deduplicate Markdown, or pass earlier generated chunks to Pi.

A single token larger than the chunk limit fails rather than truncates. Character limits do not guarantee a compatible context window or output limit.

**Default Markdown sends caption text to the configured model/provider.** It can incur one paid call per chunk, plus Pi/provider-internal retries.

A repeated run can incur new charges. A timeout or cancellation cannot undo provider work or billing. No wrapper-level model retries occur.

`--no-session` prevents local Pi session persistence. It does not prevent provider-side logging or retention.

## Pi isolation and completeness

Pi receives cleaned source text through stdin. It receives neither YAML metadata nor the upstream metadata dictionary.

The wrapper replaces the coding prompt with editorial instructions. It supplies a fixed append prompt and disables tools, extensions, MCP, skills, templates, themes, and context files.

Pi runs in an empty temporary directory. User credentials, compatible endpoints, and default model configuration remain available. Custom provider extensions are not supported.

This isolation is not an operating-system sandbox or a prompt-injection guarantee. Returned captions and generated Markdown remain untrusted data.

The wrapper reads bounded JSONL events internally. Success requires process exit 0, `agent_settled`, and a final authoritative assistant message with `stopReason='stop'`.

Length stops, aborts, compaction, tool calls, missing completion, invalid JSON, and oversized output fail before publication. Events, thinking, and raw stderr never enter documents or diagnostics.

A normal stop does not prove factual accuracy or semantic completeness. Offline structural tests do not prove faithful actual LLM edits.

## Metadata files

Default and raw `-o` files share this fixed schema:

```yaml
---
url: "https://www.youtube.com/watch?v=YE7VzlLtp-4"
video_id: "YE7VzlLtp-4"
title: "Example video"
channel: "Example channel"
channel_id: "UCexample"
channel_url: "https://www.youtube.com/channel/UCexample"
upload_date: "2008-05-29"
duration_seconds: 597
caption_language: "en-orig"
caption_source: "automatic"
---

The transcript starts here.
```

Python serializes every string safely with double quotes. The serializer can also quote mapping keys. All ten fields are always present.

The canonical URL excludes playlist and tracking parameters. The video ID must match the single extracted video.

The channel falls back to the uploader name. The channel URL falls back to the uploader URL. The channel ID never falls back to a handle.

The upload date uses UTC. A valid timestamp supplies an absent date. An explicitly malformed date becomes `null` rather than a guessed date.

Duration preserves zero and fractional seconds. Missing or invalid optional values become `null`. Caption language retains the selected key exactly.

Caption source is `manual` or `automatic`. These fields do not prove that the text is untranslated original English.

Metadata comes from the same processed extraction as the captions. Python adds the header exactly once, after all formatting succeeds. Pi cannot replace it.

Descriptions, signed subtitle URLs, cookies, tokens, counts, and extraction timestamps are excluded. Raw VTT receives no header or byte changes.

## Caption selection and cleanup

The wrapper chooses one track with VTT formats, in this order:

1. Manual `en`
2. Other manual `en-` keys, in lexical order
3. Automatic `en-orig`, then other English `-orig` keys
4. Automatic `en`
5. Other automatic `en-` keys, in lexical order

Matching ignores case but preserves the original key. YouTube-provided translated English is a fallback. The wrapper does not translate locally or infer translation provenance.

The wrapper downloads captions only into a temporary directory. It performs one metadata extraction and does not silently switch tracks after a download error.

The supported VTT parser retains caption text, Unicode, punctuation, and descriptions such as `[Music]`. It skips metadata blocks and strips supported VTT tags before entity decoding.

Manual captions preserve repetition. Automatic cleanup removes exact suffix/prefix overlaps only within consecutive rolling cues, with at most a 100 ms gap.

Larger gaps and backward times reset the overlap comparison. Case and punctuation differences remain distinct. Intentional repetition inside a cue remains intact.

This heuristic does not guarantee perfect speech reconstruction. Malformed or empty cleaned captions fail. Raw VTT remains an explicit diagnostic path.

Active livestreams fail with `active livestreams are not supported`. Upcoming videos fail with `video has not started`.

Post-live videos fail with `livestream processing is incomplete; try again later`. Completed streams and unknown states are accepted without a completeness promise.

The fixed upstream network policy uses a 30-second socket timeout, three HTTP retries, and three extractor retries. Retry delays are 1, 2, then 4 seconds.

There is no whole-workflow retry. These limits are not total request or time budgets. Authentication and unavailable-video errors are not guaranteed retryable.

YouTube can block extraction or require PO tokens. Full runtime setup does not guarantee access. The wrapper provides no cookies, bypass flags, or token provisioning.

## Doctor and file safety

```sh
uv run yt-transcript --doctor
uv run yt-transcript URL --no-config --raw -o transcript.txt --no-clobber
```

Doctor is local and ignores wrapper TOML. It reports Python, package versions, EJS compatibility, Deno, and Pi readiness.

Version commands use isolated directories and five-second deadlines. Doctor does not run a model or access YouTube, credentials, or authentication commands.

A healthy report establishes local readiness only. It does not establish video access, provider authentication, caption completeness, or model accuracy.

File output uses a completed sibling temporary file. Default publication atomically replaces the destination after success. Pre-output failures leave existing files unchanged.

`--no-clobber` requires `-o`. It rejects existing entries, including broken symlinks, before extraction. Atomic hard-link publication also rejects a destination created during processing.

Filesystems without usable hard links fail closed. There is no replacement fallback. A cleanup failure after publication produces a warning, not a false publication failure.

The output parent directory must exist. Stdout is not transactional. A failed stdout write can leave partial bytes in a pipe.

## Optional stdio MCP server

The MCP extra uses the official `mcp` 2.3.0 SDK with `MCPServer`. It does not use the third-party `fastmcp` package.

```sh
uv run --extra mcp yt-transcript --mcp --no-config
```

Example client configuration:

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

Client-specific configuration keys can differ. Use the absolute project directory for local startup.

The server exposes exactly three tools:

| Tool | Input | Structured output |
|---|---|---|
| `get_transcript` | `url: string` | `format`, `document`, `metadata`, `character_count` |
| `preview_transcript` | `url: string` | `metadata`, `character_count`, `planned_invocations`, `largest_chunk_chars`, `chunk_chars`, `max_chunks`, `within_cap`, `model_selection` |
| `doctor` | No arguments | `healthy`, `checks` with `name`, `status`, `detail` |

`get_transcript` returns `format='plain_text'`. Its document contains the complete Python-generated YAML header and cleaned body. Character count excludes the header.

Clients that save files must save `structuredContent.document` verbatim. Do not add a second header. The SDK also returns serialized JSON text for compatibility.

Transcript and preview tools access YouTube. Doctor checks local dependencies and Deno without any Pi invocation. Missing Pi does not affect MCP readiness.

All tools have typed output schemas. Expected failures are execution errors with `isError=true`, not successful documents or protocol-level `MCPError` values.

Initialization and tool listing do not check runtimes or access the network. A tool failure does not stop the server.

The server never calls Pi, writes final documents, opens a port, or exposes model selection, file paths, prompts, resources, sampling, or client roots.

Startup accepts only configuration selection and verbosity beside `--mcp`. TOML mode and Pi timeout do not affect MCP behavior.

Preview uses the configured chunk size and cap. Its model description is hypothetical and never authorizes formatting.

Stdout contains only SDK protocol traffic. Diagnostics use stderr. Returned captions and metadata are untrusted source data, never instructions to an agent.

Read-only annotations do not create a sandbox. Temporary intermediate files are permitted. Cancellation cannot undo YouTube requests already sent.

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

## Errors and recovery

Expected CLI failures use `error[CODE]: MESSAGE` and an optional safe hint. Verbose mode uses allowlisted diagnostic fields only.

| Codes | Action |
|---|---|
| `INVALID_URL`, `CONFIG_INVALID` | Correct the input or use `--no-config`. |
| `RUNTIME_MISSING`, `RUNTIME_INCOMPATIBLE` | Install compatible Deno/EJS components and run doctor. |
| `NO_ENGLISH_CAPTIONS`, `NO_ENGLISH_VTT` | No matching captions were returned. Availability is not fully proven. |
| `YOUTUBE_ACCESS_LIMITED` | Check permitted browser access. Captions can be omitted by access restrictions. |
| `VIDEO_UNAVAILABLE`, `AUTH_REQUIRED`, `AGE_RESTRICTED`, `GEO_RESTRICTED` | Check permitted browser/account access. No bypass is provided. |
| `REMOTE_RATE_LIMITED`, `NETWORK_FAILED` | Wait or check network/certificates. Keep TLS verification enabled. |
| `REMOTE_ACCESS_DENIED` | Check permitted access and runtime setup. A 403 alone does not prove authentication or token diagnosis. |
| `YOUTUBE_EXTRACT_FAILED`, `SUBTITLE_DOWNLOAD_FAILED` | Check supported yt-dlp/runtime setup and permitted access. |
| `UNSUPPORTED_LIVESTREAM` | Wait for a completed, processed recording. |
| `SUBTITLE_INVALID`, `EMPTY_TRANSCRIPT` | Use `--raw-vtt` to inspect captions separately. |
| `PI_NOT_FOUND`, `PI_LAUNCH_FAILED`, `PI_INCOMPATIBLE` | Install compatible Pi or use `--raw`. |
| `PI_AUTH_FAILED`, `PI_MODEL_UNAVAILABLE` | Configure the provider or the chosen/default model directly in Pi. |
| `PI_RATE_LIMITED`, `PI_QUOTA_EXCEEDED` | Wait or check provider quota. Rate limits and quota are distinct. |
| `PI_CONTEXT_LIMIT`, `PI_OUTPUT_INCOMPLETE` | Reduce chunk size, review the model choice, or use `--raw`. |
| `PI_TIMEOUT`, `PI_ABORTED`, `PI_FAILED` | Check provider/model setup or use deterministic output. |
| `PI_PROTOCOL_INVALID`, `PI_OUTPUT_INVALID`, `PI_OUTPUT_LIMIT` | Check compatible Pi setup. Buffered output is discarded. |
| `CHUNK_LIMIT_EXCEEDED` | Preview the plan or explicitly change the cap. No text is truncated. |
| `OUTPUT_EXISTS`, `OUTPUT_FAILED` | Choose a usable path and check filesystem support. |
| `MCP_BUSY`, `MCP_TIMEOUT`, `MCP_RESPONSE_LIMIT`, `INTERNAL_ERROR` | Wait or use the deterministic CLI. |

Unknown upstream wording receives a generic error, not a guessed authentication or billing cause. Private causes and raw warnings never enter CLI or MCP errors.

Exit codes are 0 for success, 2 for input/configuration errors, 1 for operation errors, and 130 for interruption.

## Development and distribution

```sh
uv run --extra mcp pytest -m 'not integration'
uv run ruff check .
uv run ruff format --check .
uv build
uvx --from . yt-transcript --help
uvx --from . yt-transcript --version
```

The lockfile records exact development dependencies. Runtime execution never upgrades them automatically. Automated tests use synthetic metadata and local child processes, without YouTube or Pi calls.

Live checks require an operator-supplied public URL:

```sh
YT_TRANSCRIPT_TEST_URL='https://youtu.be/VIDEO_ID' uv run pytest -m integration tests/test_integration.py
```

A live Pi check additionally requires explicit spend approval and `YT_TRANSCRIPT_TEST_PI=1`. A URL alone never enables a model call.

The Git source is the private repository [NMDRA/yt-transcript](https://github.com/NMDRA/yt-transcript). Your Git client needs authenticated access.

```sh
uvx --from 'git+https://github.com/NMDRA/yt-transcript.git' yt-transcript --help
uvx --from 'yt-transcript[mcp] @ git+https://github.com/NMDRA/yt-transcript.git' yt-transcript --mcp --no-config
```

Keep credentials out of URLs and command arguments. PyPI publication and live model checks still require separate approval.
