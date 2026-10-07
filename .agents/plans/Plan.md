# Plan: English YouTube transcript CLI and stdio MCP server

## Goal

Build a Python CLI that accepts one YouTube video URL, selects the best available English VTT captions, cleans them mechanically, and uses the locally installed Pi CLI to produce an edited Markdown document by default. Keep `--raw` as the deterministic plain-text path without an LLM, and `--raw-vtt` as the unchanged-caption path. Non-VTT files written with `-o` include Python-generated YAML metadata before the body. Use `uvx` as the primary distribution interface. Support optional user-level TOML defaults and explicit config-file selection. Add `--mcp` for a deterministic stdio MCP server that returns content/metadata without Pi calls or final file writes. Keep video, audio, FFmpeg, research, and summarization outside the product.

This document is an implementation plan, not approval to publish or push.

## Current State and Evidence

- Initial inspection found an empty working directory at `/home/nimendra/Documents/Projects/yt-transcript`. `git status --short` reported no Git repository. The initial plan is now present; there is no application implementation or test suite to preserve.
- `uv` and `python3` are available locally. No implementation or runtime checks have run.
- Python 3.11 provides `tomllib`; `load` reads a binary file and invalid TOML raises `TOMLDecodeError`. No extra TOML dependency is needed. [Python tomllib](https://docs.python.org/3.11/library/tomllib.html)
- The XDG Base Directory specification defines user configuration under `$XDG_CONFIG_HOME`, falling back to `$HOME/.config` when unset or empty. Relative XDG paths are invalid and must be ignored. [XDG specification](https://specifications.freedesktop.org/basedir/latest/)
- `uvx` aliases `uv tool run`, uses an isolated environment, and supports `--from git+https://...`. Console-script names can differ from distribution names. [uv tool guide](https://docs.astral.sh/uv/guides/tools/)
- A build backend is required for normal package installation and console entry points. `uv build` produces wheel and source distributions. [uv project creation](https://docs.astral.sh/uv/concepts/projects/init/), [uv packaging guide](https://docs.astral.sh/uv/guides/package/)
- `YoutubeDL.extract_info` supports `download=False, process=False`. `process_ie_result` can then process the extracted video. Subtitle options include `writesubtitles`, `writeautomaticsub`, `subtitleslangs`, and `subtitlesformat`. [yt-dlp API source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py)
- `process_subtitles` prefers manual captions for matching language keys, but can fall back to a non-VTT format even when VTT is requested. `_write_subtitles` sets the selected track's `filepath`. Therefore, filter to VTT explicitly and verify the downloaded result. [yt-dlp API source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py)
- YouTube extraction distinguishes original automatic captions with `-orig`. Translated automatic tracks can also appear in `automatic_captions`; language keys are not limited to regional variants. Some subtitle requests require PO tokens. [YouTube extractor source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py)
- Full YouTube support uses EJS scripts and an external JavaScript runtime. `yt-dlp[default]` includes `yt-dlp-ejs`. Deno is enabled by default; the EJS guide currently lists Deno 2.3.0 as its minimum. Recheck the guide when implementing. [EJS setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS), [dependency declaration](https://github.com/yt-dlp/yt-dlp/blob/master/pyproject.toml)
- The extractor metadata contract defines `title`, `channel`, `channel_id`, `channel_url`, `uploader`, `uploader_url`, `duration` (seconds, integer or float), `upload_date` (UTC, `YYYYMMDD`), and `timestamp`. Some fields can be absent. `upload_date` can be derived from `timestamp` during yt-dlp processing. YouTube extractor fixtures demonstrate these fields. Reuse this metadata from the existing extraction rather than request it separately. [Extractor metadata contract](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/common.py), [YouTube extractor and fixtures](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py)
- WebVTT has structured headers, optional cue identifiers, timing lines, payloads, and non-caption blocks. Parse blocks rather than remove all lines that resemble metadata. [WebVTT specification](https://www.w3.org/TR/webvtt1/)
- The PyPI distribution name `yt-transcript` is already occupied. Bare `uvx yt-transcript` currently refers to another project, not this one. [PyPI project](https://pypi.org/project/yt-transcript/), [PyPI metadata](https://pypi.org/pypi/yt-transcript/json)

- Pi print mode accepts piped stdin, prepends it to the prompt, writes final assistant text to stdout, and exits. `--no-session` uses an in-memory session; `--model` accepts provider/model identifiers. `--no-tools` disables built-in, custom, extension, and MCP tools, but does not itself prevent extension startup code. Additional resource flags disable extensions, MCP, skills, templates, and context-file discovery. [Pi CLI reference](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md)
- Pi text mode rejects failed/aborted assistant responses, but can return successful-looking text after a length stop. JSON mode exposes authoritative assistant messages and `stopReason`; model errors can still accompany process exit 0. Validate events and process status independently, and wait for `agent_settled`, not just `agent_end`. [CLI integration](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli-integration.md), [JSON events](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/json.md), [Message types](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/message-types.md)
- Pi installation and model authentication remain user responsibilities. Current installation guidance specifies Node.js 22.19+ for npm installation and supports subscription, API-key, or local-model access. User credentials and compatible endpoints remain available without loading custom provider extensions. [Quickstart](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/quickstart.md), [Models](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md)
- The resource loader falls back to global `APPEND_SYSTEM.md` unless explicit append-system-prompt sources are supplied. Supply a fixed editorial append prompt as well as the replacement system prompt to prevent that fallback. [Pi resource loader](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/resource-loader.ts)
- Pi configuration and transcript input can influence model behavior. Disabling resources reduces this surface but is not an operating-system sandbox or a guarantee against prompt injection. [Configuration](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/configuration.md), [Security](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/security.md)

- Research agents verified that yt-dlp exposes `socket_timeout`, `retries`, `extractor_retries`, and retry-delay functions. Use upstream retry behavior rather than repeat the complete wrapper workflow. Socket timeouts are not total workflow deadlines, and not every HTTP failure is retryable. [yt-dlp API](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py), [HTTP downloader](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/downloader/http.py)
- The extractor contract distinguishes `is_live`, `is_upcoming`, `post_live` (VOD not yet processed), and completed `was_live` videos. This permits a guard using the existing extraction result. [Extractor contract](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/common.py)
- Pi has internal retry behavior, so counting wrapper chunk invocations does not establish a hard provider-request or dollar cap. [Pi retry settings](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/settings.md)
- `os.replace` can overwrite an existing destination. Publishing a completed sibling temporary file through `os.link` can provide atomic no-replace creation on supported filesystems; an existence check followed by replacement cannot provide this guarantee. [Python file operations](https://docs.python.org/3.11/library/os.html), [POSIX link semantics](https://pubs.opengroup.org/onlinepubs/9699919799/functions/link.html)

- MCP stdio uses UTF-8 JSON-RPC over stdin/stdout. Under the documented stdio binding, messages are newline-delimited and stdout contains only valid protocol messages; diagnostics belong on stderr. Delegate framing and supported-version negotiation to the official SDK, not a handwritten protocol loop. [MCP stdio specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- Research and direct PyPI verification found official `mcp` 2.3.0, non-yanked, requiring Python >=3.10. Its v2 public API exports `MCPServer` from `mcp.server`; it is not the v1 `mcp.server.fastmcp.FastMCP` API or the separate third-party `fastmcp` package. Recheck latest stable metadata when implementation starts. [PyPI metadata](https://pypi.org/pypi/mcp/json), [v2.3.0 exports](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/__init__.py), [v2.3.0 server](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/mcpserver/server.py)
- SDK v2 provides `@server.tool()`, structured output inferred from compatible type annotations, and `server.run(transport='stdio')`. `Client(server, raise_exceptions=True)` supports in-memory async tests. Tool execution errors use error results; v2 `MCPError` instead produces a protocol error. Do not mix v1 error/types/annotation examples with v2. [Structured results](https://py.sdk.modelcontextprotocol.io/v2/servers/structured-output/), [Error handling](https://py.sdk.modelcontextprotocol.io/v2/servers/handling-errors/), [Testing](https://py.sdk.modelcontextprotocol.io/v2/get-started/testing/)
- MCP annotations describe behavior but do not enforce access control. Stdio is not a sandbox. SDK request cancellation does not establish that a blocking yt-dlp thread stopped; application-owned child-process cancellation and cleanup must be tested. [Tools and annotations](https://py.sdk.modelcontextprotocol.io/v2/servers/tools/), [SDK stdio implementation](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/stdio.py)

- yt-dlp `DownloadError.exc_info` and `ExtractorError.cause`/`exc_info` can preserve underlying exceptions, but can be absent. Typed network/HTTP/geo errors are stronger classification evidence than display text. `expected=True` does not identify authentication/unavailability. [Exception definitions](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/utils/_utils.py), [Network exceptions](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/networking/exceptions.py), [Subtitle wrapping](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py)
- HTTP 403 does not prove authentication or PO-token diagnosis. Captions can be omitted after warning-only extraction restrictions. [PO-token guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide), [YouTube extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py)
- Pi's subprocess interface does not establish a provider-neutral typed taxonomy for authentication, quota, model lookup, or context errors. Unknown startup stderr/errorMessage wording requires a generic fallback, not a guessed root cause.

The installed Pi 1.0.4 documentation was read in full for README, CLI, CLI integration, usage, quickstart, models, configuration, security, JSON events, and message types. No Pi model call was run during planning.

Upstream `master` sources describe current behavior, not a pinned release guarantee. Lock and test the stable version selected during implementation.

## Decisions

### Confirmed by the user

1. **Full YouTube setup:** depend on `yt-dlp[default]` and document external Deno on `PATH`. Reject the Python-only promise because current upstream guidance does not support it. No FFmpeg requirement.
2. **English translation fallback:** allow YouTube-provided translated English tracks after original English tracks. Do not implement translation locally.
3. **License:** MIT.
4. **Git-first delivery:** retain local distribution name `yt-transcript` and command `yt-transcript`. Verify from a Git source once a remote exists. Defer PyPI naming and publication to a separate release plan.
5. **File metadata:** preserve YAML frontmatter for every non-VTT `-o` file, including default Markdown and `--raw` plain text. Stdout contains only the selected body; raw VTT remains unchanged.
6. **Pi editorial formatting:** default to Markdown through the local Pi CLI; add `--raw` and `--model`. Use a subprocess, not a Python Pi SDK or bundled Node/Pi installation.
7. **Long transcripts:** chunk and combine using sequential Pi calls. This increases cost and latency. Do not summarize chunks or use a final lossy synthesis call.
8. **Isolated formatter:** disable tools and resource loading. Custom provider extensions are not supported in this mode. Keep the user's built-in-provider credentials, compatible endpoints, and default model settings.
9. **TOML configuration:** load user defaults from the XDG config location; support `--config PATH` and `--no-config`. Never auto-load project files. Allow output mode, verbosity, chunk size, timeout, and an optional explicit model override. Keep Pi's default model when no override is supplied.
10. **Recommended reliability and output protections:** add preview, an optional chunk cap, offline doctor checks, no-clobber file output, bounded yt-dlp retries, and a conservative livestream guard. Keep Markdown quality heuristics, translation provenance, and receipts as follow-up features. Pi JSON completion validation is now in scope under the error-handling decision below.
11. **MCP:** start with `yt-transcript --mcp`; expose deterministic tools only. Return document content and structured metadata, without arbitrary paths or final filesystem writes. Do not expose Pi formatting, sampling, model selectors, or an opt-in model tool. Use the official SDK through an optional `mcp` package extra so ordinary CLI users do not require it.

12. **Error handling:** share stable codes, phase-aware evidence, safe hints, and allowlisted diagnostics across CLI/MCP. Use Pi JSON events internally, as selected by the user, to reject length-stopped or incomplete chunks before publication. No new wrapper retries, model fallback, or access-control workarounds.

13. **Python baseline update:** the user requested the latest stable Python, then selected installed Python 3.14.7 instead of updating uv to install 3.14.8. Use Python >=3.14.7, pin local development to 3.14.7, and keep standard-library TypedDict result schemas. Python 3.11 support is no longer required. The official release API lists 3.14.8 as latest, but uv 0.8.13 has no download for it. No uv or system Python upgrade is approved. [Python release API](https://www.python.org/api/v2/downloads/release/)

### CLI contract

Use standard-library `argparse`:

```text
yt-transcript URL [OPTIONS]
yt-transcript --doctor
yt-transcript --mcp [--config PATH | --no-config] [-v]

  -h, --help
  --mcp
  -o, --output PATH
  --no-clobber
  --preview
  --max-chunks N
  --doctor
  --raw
  --raw-vtt
  --model MODEL
  --config PATH
  --no-config
  -v, --verbose
  --version
```

- Accept one HTTP(S) video URL: YouTube watch URLs, `youtu.be` links, and `/shorts/` or `/embed/` video paths. Accept exact hosts `youtube.com`, `www.youtube.com`, `m.youtube.com`, and `youtu.be`. Reject lookalike hosts, credentials, playlist-only URLs, channel URLs, bare IDs, and non-YouTube URLs before network access.
- Normalize the video ID to a canonical watch URL. A video URL containing a playlist parameter still processes only that video.
- The built-in output mode is Markdown; TOML may select another default and explicit raw-mode flags override it. Default Markdown stdout is Pi-edited Markdown with one final newline. It contains no YAML header or progress messages.
- `--raw` bypasses Pi and emits one whitespace-normalized transcript paragraph with one final newline. Preserve case, punctuation, Unicode, and caption descriptions such as `[Music]` in deterministic cleanup.
- `--raw-vtt` outputs the selected VTT file bytes unchanged, including with `-o`. It bypasses cleaning, Pi, and frontmatter formatting. Make `--raw` and `--raw-vtt` mutually exclusive.
- Use Pi's configured default model unless the user explicitly sets a model in TOML or through `--model`. CLI `--model MODEL` overrides the TOML value. If neither supplies a model, omit the model argument from every Pi invocation; do not hardcode a provider/model, change Pi settings, or choose a fallback model. Forward an effective nonempty selector as one argument without a shell. Reject an explicit CLI `--model` whenever the effective output mode is raw or raw VTT. Ignore a TOML-only model in raw modes so a saved formatting preference cannot break `--raw`.
- `-o` directs output to a file, with no body on stdout. Default and `--raw` files contain the same YAML header schema, a blank line, then their Markdown or plain-text body with one final newline. Only `--raw-vtt` files contain unchanged VTT bytes without metadata. Shell redirection (`> transcript.md`) receives only the body without metadata; use `-o` to get frontmatter. Replace an existing destination only after all download and processing steps succeed. Use a sibling temporary file plus `os.replace` by default; require the parent directory to exist. `--no-clobber` selects the atomic no-replace policy below and requires `-o`.
- Default success has no progress output. Route static safe warning messages to stderr; `--verbose` adds selected language/source and allowlisted upstream diagnostics there. Never send yt-dlp diagnostics to stdout.
- `--config PATH` selects a single TOML file instead of the auto-discovered user file. `--no-config` disables all wrapper config loading and restores built-in defaults before applying other CLI flags. These flags are mutually exclusive. Help/version do not load TOML or require a video URL.
- Exit 0 for success, 2 for invalid arguments/URL/configuration, 1 for extraction, caption, parsing, runtime, Pi formatting, or output failures, and 130 for interruption. Expected failures print `error[CODE]: MESSAGE` on stderr and, when useful, one `hint: ACTION` line. Include chunk position for formatting failures. Verbose mode adds only allowlisted diagnostic fields, not upstream exception text or raw tracebacks.
- Finish extraction, cleaning, every Pi chunk, body validation, and metadata serialization before emitting output. Pre-output failures leave stdout empty and existing output files unchanged. A failed stdout write can already have emitted bytes; do not claim transactional stdout.

### Shared error handling contract

Add `errors.py` with `AppError`, immutable `ErrorInfo(code, message, hint, phase, retryable, chunk_index, chunk_total)`, `classify_ytdlp_error`, `classify_pi_failure`, `render_cli_error`, and an allowlisted diagnostic renderer. Preserve an original exception privately, never in wire data. Existing `ConfigError`, `TranscriptError`, and `FormattingError` become subclasses of this common boundary.

- Phases: `config`, `runtime_check`, `metadata_extract`, `caption_select`, `subtitle_download`, `vtt_parse`, `pi_start`, `pi_response`, `output`, `mcp_worker`. `retryable` describes a possibly transient condition, not permission or a promise to retry; wrapper retries remain disabled.
- Classification precedence: wrapper checks, trustworthy typed cause/status evidence, narrow release-tested error recognizers, then phase-specific fallback. Traverse `__cause__`, `__context__`, optional `cause`, and `exc_info[1]` with an identity set and maximum depth 8; tolerate malformed, absent, and cyclic cause information.
- Text recognizers inspect only bounded upstream error/warning fields, never caption text, generated Markdown, video titles, or the entire event stream. Unknown wording must not falsely assert a specific access or provider fault. Store recognizers and version-pinned/synthetic fixtures together.

| Stable codes | Evidence and safe guidance |
|---|---|
| `INVALID_URL`, `CONFIG_INVALID` | Local input/schema checks; correct the input or use `--no-config`. Exit 2. |
| `RUNTIME_MISSING`, `RUNTIME_INCOMPATIBLE` | Local Deno/EJS checks prove the setup issue. Run doctor and install compatible components; never infer runtime failure from a 403 alone. |
| `NO_ENGLISH_CAPTIONS`, `NO_ENGLISH_VTT` | Selection returned no candidate and no known access-limitation evidence. Say no English captions were returned, not that the video definitely has none. |
| `YOUTUBE_ACCESS_LIMITED` | Known challenge/token/omitted-track warnings. Caption availability could not be fully verified; do not promise cookies or tokens will fix it. |
| `VIDEO_UNAVAILABLE`, `AUTH_REQUIRED`, `AGE_RESTRICTED`, `GEO_RESTRICTED` | Typed evidence where available or narrow tested extractor messages. Verify permitted browser/account access; no bypass guidance or automatic cookie import. |
| `UNSUPPORTED_LIVESTREAM` | Existing active/upcoming/post-live guard; retain its specific safe message. |
| `REMOTE_RATE_LIMITED` | Trusted HTTP 429 evidence. Wait before another attempt; do not treat it as billing quota or add workflow retries. |
| `REMOTE_ACCESS_DENIED` | Trusted HTTP 401/403 without a proven finer cause. Verify access/setup without guessing login, bot, or PO-token diagnosis. |
| `NETWORK_FAILED` | Typed DNS/transport/connect/read-timeout/TLS evidence. Check network/certificates; never disable TLS verification. |
| `YOUTUBE_EXTRACT_FAILED`, `SUBTITLE_DOWNLOAD_FAILED` | Phase-specific fallback. Check access and supported yt-dlp/runtime setup; never silently switch the selected caption track. |
| `SUBTITLE_INVALID`, `EMPTY_TRANSCRIPT` | Decode/parser/empty-text checks. Show a safe block index, not caption text; raw VTT is an explicit diagnostic option. |
| `PI_NOT_FOUND`, `PI_LAUNCH_FAILED`, `PI_INCOMPATIBLE` | Local discovery/launch or tested option incompatibility. Install/upgrade Pi or use raw; no weaker-isolation retry. |
| `PI_AUTH_FAILED`, `PI_MODEL_UNAVAILABLE`, `PI_RATE_LIMITED`, `PI_QUOTA_EXCEEDED` | Only positive, narrow, tested startup/errorMessage evidence. Login/configure provider, check chosen/default model, wait, or check quota respectively. Ambiguous cases remain `PI_FAILED`; no auto-login/model switch. |
| `PI_CONTEXT_LIMIT`, `PI_OUTPUT_INCOMPLETE` | Positive context-limit/compaction evidence or authoritative length stop. Reduce TOML chunk size, review an explicit model choice, or use raw; no automatic continuation/retry. |
| `PI_TIMEOUT`, `PI_ABORTED`, `PI_FAILED` | Per-chunk deadline, reported abort without local interruption, or unknown process/model fault. Show chunk position and generic provider/model/raw guidance. |
| `PI_PROTOCOL_INVALID`, `PI_OUTPUT_INVALID`, `PI_OUTPUT_LIMIT` | Bad/missing JSON completion, invalid body framing, empty text, or output bounds. Reject all buffered output and inspect supported Pi setup. |
| `CHUNK_LIMIT_EXCEEDED` | Planner cap exceeded; preview or explicitly change the cap, never truncate. |
| `OUTPUT_EXISTS`, `OUTPUT_FAILED` | Existing destination, permission, missing directory, disk-full, or filesystem failure. Preserve files and distinguish pre-commit failure from post-commit cleanup warning. |
| `MCP_BUSY`, `MCP_TIMEOUT`, `MCP_RESPONSE_LIMIT`, `INTERNAL_ERROR` | Worker supervision/unexpected failures; retain server availability without exposing worker output. |

- A subtitle-stage `DownloadError` is not an extraction-stage error. Preserve known HTTP status/typed causes with that stage; if wrapping loses evidence, use the subtitle fallback.
- Collect warnings with the yt-dlp logger in bounded memory. Recognized access-limitation warnings plus missing captions yield `YOUTUBE_ACCESS_LIMITED`; ordinary warnings do not fail a valid download. Unknown warnings do not justify a guessed cause.
- Preserve existing upstream retry settings; no whole-workflow/model retry. Access/input/runtime/parser errors do not start wrapper retry loops. Do not promise a total request/time budget from upstream retry limits.
- Local `KeyboardInterrupt` exits 130 after child cleanup, not as an authentication/network fault. MCP cancellation retains cancellation semantics; it is not a successful result. Broken pipes have no traceback, but stdout cannot be rolled back.

**Safe reporting**

- Allowlist code, phase, library/Pi version, exception class name, trusted HTTP status, local errno name, chunk index/count, stop reason, retry count, and sanitized relative frame identifiers/line numbers. No raw exception strings/attributes/tracebacks, signed URLs, headers, cookies, API keys, credentials, config contents, thinking, or caption/generated text, even in verbose mode.
- Do not forward raw yt-dlp/Pi warnings or stderr. Use static safe messages/hints; keep raw classifier input only in bounded temporary memory, then discard it. Prefer a generic error over imperfect regex secret redaction. Strip ANSI/control characters from displayable fields.
- CLI renders shared codes/hints. The worker serializes only `ErrorInfo` in its private error envelope; MCP renders `[CODE] MESSAGE; hint: ACTION` as an SDK execution error, not a successful document. Error results need not match successful output schemas. Startup failures remain stderr-only.
- Test fake bearer keys, cookies, authorization headers, signed queries, private paths, transcript/Markdown excerpts, ANSI sequences, misleading error-like titles, and unknown provider wording. Assert none leak through CLI/MCP diagnostics or error results. Python-generated YAML metadata is untouched.

### Stdio MCP server contract

**Startup and dependencies**

- `--mcp` is a URL-free, long-lived mode. Accept only `--config PATH`/`--no-config` and `--verbose` alongside it. Reject URL, doctor, preview, raw modes, output/no-clobber, model, and CLI chunk-cap flags with exit 2 before starting the protocol. Help/version retain normal early-exit behavior.
- Load/validate wrapper TOML once at startup. Read effective verbosity and the preview chunk size/cap. Ignore output mode, model, and Pi timeout for MCP behavior; they must never enable formatting. Tool arguments cannot select a config file or override server policy.
- Add `[project.optional-dependencies].mcp` with the latest stable official `mcp` version verified at implementation, using the same minimum-version/lock policy as other libraries. No third-party FastMCP or Python Pi SDK. Import SDK-dependent modules only after dispatching `--mcp`. A missing extra returns a concise stderr install hint and exit 1, with empty stdout; ordinary help/version/CLI/doctor still work.
- Use `from mcp.server import MCPServer`, `@server.tool(...)`, and `server.run(transport='stdio')`, matching the selected v2 release. Do not hardcode a protocol version, implement JSON-RPC framing, open a listening port, or launch an MCP Inspector in production.
- No network, Deno/Pi check, or transcript download during initialization or tool listing. Dependency checks happen when the relevant tool runs. MCP works without Pi installed and makes no Pi process/model calls.

**Public tools: exactly three**

1. `get_transcript(url: str) -> TranscriptResult`: validate the same YouTube URL allowlist, apply caption ranking/retries/livestream guard, download once, and clean deterministically. Return `format='plain_text'`, the full `document` string (YAML frontmatter, blank line, transcript, one final newline), the same typed `metadata` mapping represented by that header, and `character_count` for transcript body only. Include all fixed metadata keys and nulls; no model-generated or caller-overridden metadata.
2. `preview_transcript(url: str) -> PreviewResult`: download/clean and use the shared chunk planner, without Pi. Return typed `metadata`, cleaned character count, planned formatter invocation count, largest chunk size, configured chunk limit, nullable max chunks, cap result, and model-selection description for a hypothetical CLI formatting run. This does not authorize or execute formatting. A cap exceedance is a successful preview result, matching CLI preview. No transcript body is included.
3. `doctor() -> DoctorResult`: return typed local readiness checks without YouTube, model calls, or Pi executable invocation. Reuse doctor with an `include_pi=False` profile; mark Pi not required in the result. Report core/MCP package versions and Deno readiness. Missing optional Pi must not make this profile unhealthy. No credentials, full paths, or environment values.

- Define result shapes using standard-library `TypedDict` and supported type hints so the SDK publishes/validates `outputSchema`. Use normal SDK structured output plus its serialized-JSON text compatibility content. Clients that want a file save `structuredContent.document` verbatim; Python has already supplied the YAML header. Do not call the CLI or print a transcript from a tool handler.
- Treat returned captions/metadata as untrusted source data, not instructions to the calling agent. Tool descriptions state that YouTube network access occurs for transcript/preview, while doctor is local. No prompts, resources, raw-VTT tool, sampling, elicitation, file-writing tool, or client-roots access in v0.1.
- Use v2 `ToolAnnotations` keyword names from the locked SDK: transcript/preview have read-only and open-world hints; doctor has read-only and closed-world hints. Read-only means no durable/user-document mutation; temporary downloads are still permitted. Hints are not a sandbox or permission mechanism.

**Shared service and worker boundary**

- Keep all SDK-independent result types in `service.py` so ordinary CLI/worker imports do not require the optional MCP package. Add internal `CleanedTranscript(body, metadata)` and `fetch_clean_transcript(url: str) -> CleanedTranscript` as the common download/cleanup seam used by CLI raw/default/preview and MCP. Add `fetch_transcript_document(url: str) -> TranscriptResult`, `preview_transcript_data(url: str, *, chunk_chars: int, max_chunks: int | None, model_description: str) -> PreviewResult`, and `doctor_data() -> DoctorResult`. Reuse downloader, cleaner, metadata serializer, planner, and doctor directly. Refactor CLI deterministic/preview orchestration to this seam rather than duplicate cleanup or metadata logic. Keep the Pi formatting path separate.
- Add an internal, non-public `mcp_worker.py` module launched by `sys.executable -m yt_transcript.mcp_worker`. It accepts exactly one bounded JSON request on its private stdin, validates an allowlisted operation/fields, calls the service, and writes one JSON result/error to its private stdout. This is not another user-facing command or network server. Reject unknown operations/arguments. Send worker/upstream diagnostics to private stderr; never inherit MCP stdout for child output.
- Keep async MCP handlers responsive by supervising this subprocess with standard-library `asyncio`, rather than run blocking yt-dlp in the event loop or an uncancellable thread. The worker may create only temporary intermediate files, never a final output file. Model/output-path/config-file arguments do not exist in the worker schema.
- Allow one active worker at a time. A second concurrent expensive request gets a concise busy tool error instead of unbounded queueing. Initialization, tool listing, and protocol control remain responsive.
- Fixed v0.1 limits: URL length 4,096 characters, private request size 16 KiB, 300-second total operation timeout, document size 256 KiB in UTF-8, and a 1 MiB serialized tool-result limit including compatibility text. Enforce limits before returning; reject oversized results without truncation and recommend the deterministic CLI for larger transcripts. Protocol envelope overhead is outside the tool-result bound. Apply bounded reads to both worker pipes; drain stderr while retaining at most a 64 KiB private classification buffer. Never forward that buffer; publish only allowlisted diagnostic summaries.
- On timeout, request cancellation, disconnect, or server shutdown, terminate the active worker, wait up to two seconds, then kill/reap it if needed. The worker owns its temporary directory and handles termination cleanup. Never retry a cancelled operation or return buffered partial content. Test cleanup on supported platforms; abrupt OS termination may leave system temp files, so do not claim a universal cleanup guarantee. Cancellation cannot undo requests already sent to YouTube.

**Errors and transport safety**

- Let the SDK handle malformed protocol requests and tool-schema validation. Translate expected service errors into sanitized execution errors so the SDK returns `is_error=True` (`isError` on the wire); do not return them as successful documents. Use the shared `ErrorInfo` codes/phases/hints rather than a separate MCP classification system.
- Reserve SDK `MCPError` for protocol-level rejection, not ordinary download failures. Catch unexpected worker failures, report a generic internal tool error, and keep the server available for the next request. Never expose tracebacks, config values, signed subtitle URLs, tokens, or source transcript in default error output.
- Stdout is exclusively SDK protocol traffic from process start through shutdown. No banners, config reports, progress, version prints, transcript output, or application `print()` calls. All server logging uses stderr; logging must not duplicate returned document content.
- Use SDK-supported initialization, schema discovery, and stdio shutdown. A normal disconnect/EOF exits cleanly after worker cleanup. Startup config/extra errors occur before protocol startup with stderr-only diagnostics and nonzero process status. Tool failure does not terminate the server.
- Standard-library process supervision adds no dependency. CLI Pi model selection/default behavior and the existing file YAML contract remain unchanged.

Local development startup after package creation:

```bash
uv run --extra mcp yt-transcript --mcp --no-config
```

A common MCP client configuration can launch the local project with an absolute directory. Client-specific top-level configuration keys can differ; confirm the client's schema before copying this example:

```json
{
  "mcpServers": {
    "yt-transcript": {
      "command": "uv",
      "args": [
        "run", "--directory",
        "/home/nimendra/Documents/Projects/yt-transcript",
        "--extra", "mcp", "yt-transcript", "--mcp", "--no-config"
      ]
    }
  }
}
```

Do not document bare `uvx yt-transcript --mcp` as this project's invocation because that PyPI name belongs to another package. The README must also document a Git-source invocation with the MCP extra using the actual approved repository URL once available.

### Preview, chunk cap, doctor, and output protection

**Preview:** `yt-transcript URL --preview` performs the normal caption download, livestream guard, deterministic cleanup, and splitter, but never invokes Pi or emits a transcript. Require resolved Markdown mode; reject explicit raw flags, `-o`, and `--no-clobber`. Do not require Pi to be installed. A configured raw mode requires `--no-config` or a Markdown config file for preview.

- Print a fixed-order UTF-8 report to stdout: canonical URL, cleaned character count, planned formatter invocations, largest chunk in characters, configured chunk limit, effective maximum chunks (`unlimited` if absent), cap result (`within limit` or `exceeds limit`), and model selection (`Pi configured default` or the explicit selector). Diagnostics remain on stderr.
- Compute preview and execution from the same pure chunk planner. Do not estimate dollars or claim an exact token/provider-request count. Preview contacts YouTube and leaves no output file or session.
- Preview succeeds with exit 0 when the report is produced, even if it reports that the cap would block formatting. Extraction/parsing/config failures retain normal failure behavior. A later formatting run downloads again; preview is not a persistent cache or reservation.

**Chunk cap:** `--max-chunks N` and optional `pi.max_chunks` limit planned wrapper Pi invocations. Accept an integer from 1 through 1,000; default is no cap. CLI overrides TOML. Reject an explicit CLI cap in raw modes; ignore a TOML-only cap in raw modes after schema validation.

- After splitting the entire cleaned transcript and before the first Pi call, reject an actual formatting run that exceeds the cap with `formatting requires N chunks, exceeding max-chunks M; use --preview, --raw, or explicitly raise the cap`.
- Never truncate to the cap, format only the first chunks, or silently change chunk size/model. Exceeding the cap leaves stdout empty and existing files unchanged. Internal Pi/provider retries can exceed the planned invocation count in billable requests.

**Doctor:** `yt-transcript --doctor` needs no URL, ignores wrapper TOML loading, and makes no network/provider call. Reject a URL or other operation/config/output flags with doctor; permit `--verbose`. Missing dependencies are findings, not an early abort of the report. Dispatch doctor before importing downloader/YAML-dependent execution modules so a missing dependency can be reported rather than crash CLI startup.

- Add `doctor.py` with `run_doctor(*, include_pi: bool = True) -> DoctorReport` and `render_doctor(report: DoctorReport) -> str`. Report `ok`, `warning`, or `error` per check, plus an overall result. Exit 0 if there are no error findings, 1 if any check fails, and 2 for invalid flag combinations.
- Report wrapper, Python, yt-dlp, PyYAML, and yt-dlp-ejs versions using `importlib.metadata`. Report the installed yt-dlp EJS requirement and check exact version pins when present; if the requirement cannot be evaluated without private APIs, show a warning instead of claiming compatibility. Do not add a dependency solely for requirement parsing.
- Run bounded local `deno --version` and isolated `pi --version` commands with argument lists, UTF-8 capture, five-second timeouts, and temporary cwd. Deno must meet the upstream minimum verified for the selected stable yt-dlp release; Pi must meet the documented/tested CLI baseline. Version parse failure or a missing executable is an error with install/upgrade or `--raw` guidance.
- Run Pi's version check with resource/tool discovery disabled. Never invoke a prompt, login, auth-printing command, model catalog refresh, installer, or updater. Do not print environment values, absolute executable paths, credentials, or file contents.
- A passing report establishes local readiness, not provider authentication, video access, caption completeness, or LLM accuracy. `--raw` remains usable when only the Pi check fails.

**No-clobber:** `--no-clobber -o PATH` applies to Markdown, plain text, and raw VTT. It does not change YAML inclusion rules.

- Before extraction/Pi calls, validate the parent directory and reject an existing directory entry, including symlinks and broken symlinks. Validate basic destination usability without truncating or creating the final path.
- Write and close a completed sibling temporary file. Commit with `os.link(temp_path, destination)` so a destination created during processing also blocks publication. Then remove the temporary name. If hard-link publication is unsupported or denied, fail closed with a clear output error; never fall back to `os.replace` or a check-then-replace sequence.
- Distinguish pre-commit failure from cleanup failure after a successful link. If publication succeeded but temporary cleanup fails, preserve the final file and report a cleanup warning rather than claim the output was not written.
- `--no-clobber` is CLI-only; reject it without `-o`. Document filesystem limitations. Unflagged output retains the existing replacement policy.

### TOML configuration contract

Add `src/yt_transcript/config.py`. Parse with standard-library `tomllib`; configuration is data, never executable code.

Default discovery:

- If `XDG_CONFIG_HOME` is a nonempty absolute path, use `$XDG_CONFIG_HOME/yt-transcript/config.toml`.
- Otherwise use `Path.home() / '.config' / 'yt-transcript' / 'config.toml'`. Ignore relative XDG values as required by the specification. Use this documented path convention on supported platforms; do not add platform-specific discovery dependencies in v0.1.
- A missing auto-discovered file is normal and uses built-in defaults. If a discovered file exists but is unreadable or invalid, return a configuration error before any network or model call.
- An explicit `--config PATH` replaces discovery, not an additional merge layer. Expand `~`; resolve relative paths from the original caller's working directory, before Pi changes its working directory. A missing explicit file is an error.
- Do not scan the working directory, parent directories, `pyproject.toml`, or system-wide config locations. Do not auto-create or rewrite configuration.

Example with built-in defaults and no model override:

```toml
[output]
mode = "markdown"       # "markdown", "raw", or "raw-vtt"
verbose = false

[pi]
chunk_chars = 12000
timeout_seconds = 600
# max_chunks = 20       # Optional cap; omission means unlimited.
# Omit model to use Pi's configured default.
# model = "provider/model-id"  # Optional explicit override.
```

Schema and resolution:

- Allow only the optional `[output]` and `[pi]` tables and the keys shown above. Reject unknown tables/keys and wrong types instead of silently ignoring typos. An empty file or partial tables are valid.
- `output.mode`: string enum `markdown`, `raw`, or `raw-vtt`; built-in default `markdown`.
- `output.verbose`: boolean; built-in default `false`.
- `pi.model`: optional nonempty string after trimming. Omission means no wrapper override; empty/whitespace-only strings are errors. TOML has no null value, so remove the key to use Pi's default.
- `pi.chunk_chars`: integer from 1,000 through 50,000 inclusive; default 12,000. Reject booleans and floats. Higher limits can exceed model context/output limits; lower limits increase call count and cost.
- `pi.max_chunks`: optional integer from 1 through 1,000 inclusive; omission means unlimited. Reject booleans/floats. No TOML null or magic zero value.
- `pi.timeout_seconds`: integer from 1 through 3,600 inclusive; default 600 per chunk. Reject booleans and floats. A timeout does not prove the provider stopped processing or billing.
- Limit the config file to 64 KiB before parsing. Reject invalid UTF-8, invalid TOML, non-file paths, I/O errors, invalid schema values, and oversized files with concise configuration errors. Name the file and offending key when known; do not echo config values or file contents.
- Precedence is **explicit CLI flags > selected TOML file > built-in wrapper defaults**. Use parser defaults of `None` or `argparse.SUPPRESS` to distinguish omitted options from explicit options. Resolve into immutable `AppConfig(mode, verbose, model, chunk_chars, timeout_seconds, max_chunks)` before dependency checks or downloads.
- `--raw` and `--raw-vtt` override `output.mode`; `-v` overrides `output.verbose` to true; `--model` overrides `pi.model`; `--max-chunks` overrides `pi.max_chunks`. `-o`, `--preview`, `--doctor`, `--mcp`, and `--no-clobber` remain startup/CLI-only. Do not add URL, output path, API keys, credentials, executable paths, prompts, tool/resource flags, or metadata overrides to TOML.
- There is no separate `--markdown` or `--quiet` flag in v0.1. To restore Markdown/nonverbose behavior from a raw/verbose user config, use `--no-config`, edit the user file, or select another file with `--config`.
- Raw modes skip Pi and ignore the configured Pi model/chunk/timeout/cap settings after validating the file. A malformed config still fails unless `--no-config` is supplied. Help/version and doctor bypass loading even malformed files.
- Wrapper TOML does not modify Pi's own settings, auth files, or model catalog. Its absence must preserve the prior default behavior. `--no-config` affects only wrapper TOML, not Pi's user credentials/model defaults.
- YAML frontmatter remains derived only from video/caption metadata. TOML must not alter its schema, values, or inclusion rules. Chunk size and timeout affect only body formatting.

### File metadata contract

Use this fixed key order for default Markdown and `--raw` plain-text `-o` output:

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

The cleaned transcript starts here.
```

The values above illustrate the format, not a live extraction result.

- `url` is the canonical validated watch URL, without playlist or tracking parameters. `video_id` comes from that validated URL and must match the extracted video ID.
- `title` comes from `title`. `channel` uses `channel`, falling back to `uploader` when absent or blank. `channel_id` uses only `channel_id`, not the uploader handle. `channel_url` uses `channel_url`, falling back to `uploader_url` when absent or blank. Never label a handle as a channel ID.
- Read metadata from the processed video result already used to download the captions. No second extraction, oEmbed call, or sidecar JSON is needed.
- `upload_date` is the valid UTC `upload_date` converted from `YYYYMMDD` to a quoted `YYYY-MM-DD` string. If absent, derive it from a valid `timestamp` in UTC. If an explicit value is malformed, use `null` rather than guess. Do not substitute `release_date`, which has a different meaning.
- `duration_seconds` is a finite, nonnegative integer or float. Preserve fractional seconds and zero; invalid or unavailable values become `null`.
- `caption_language` is the exact selected language key. `caption_source` is `manual` or `automatic`. These describe the selected track, not a guarantee that its text is original English. Do not infer a translation flag solely from the language key.
- Include every key. Unavailable optional values use YAML `null`; missing optional metadata does not fail a valid transcript download.
- Add PyYAML as a runtime dependency for safe YAML serialization rather than maintain handwritten escaping. Use a local `yaml.SafeDumper` subclass with a double-quoted string representer; do not modify global representers. Dump the fixed-order mapping with Unicode enabled, key sorting disabled, block mapping style, and no automatic document markers. Wrap it with the two frontmatter delimiters explicitly. Missing values serialize as `null`. [YAML double-quoted scalar rules](https://yaml.org/spec/1.2.2/#73-flow-scalar-styles), [PyYAML safe dumping API](https://pyyaml.org/wiki/PyYAMLDocumentation)
- Parse test headers with `yaml.safe_load`. All strings are quoted so dates, `null`, `yes`, and numeric-looking titles stay strings. Test supplementary Unicode characters, including emoji, as well as ordinary Unicode.
- Exclude descriptions, tags, counts, thumbnails, extraction timestamps, cookies, signed subtitle URLs, tokens, and the full upstream info dictionary. Keep the header small, useful, and reproducible.
- Python owns the metadata. Never send the YAML header or upstream metadata dictionary to Pi. Serialize the original `VideoMetadata` and caption fields after formatting succeeds; Pi supplies only the body. Header bytes must be identical for Markdown and `--raw` output from the same download result.
- Join the header exactly once, after all formatted chunks succeed. Never add a header per chunk. Do not let Pi generate a competing header or replace any metadata field.

### Caption selection and download

Use one yt-dlp metadata extraction, followed by processing of the narrowed video result. Keep network and filesystem behavior in the downloader, not the cleaner.

Preference, among tracks with at least one VTT format:

1. Manual `en`.
2. Other manual keys beginning `en-`, sorted lexically.
3. Automatic `en-orig`, then other English keys ending `-orig`, sorted lexically.
4. Automatic `en`.
5. Other automatic keys beginning `en-`, sorted lexically.

Matching is case-insensitive, but preserve original keys for yt-dlp. A key must be exactly `en` or start with `en-`, not merely start with `en`. Regional variants have no product preference; lexical order makes ties deterministic.

- Select exactly one track. Keep only its VTT format entries in its source map and empty the other source map. This prevents manual captions from overriding an automatic selection with the same key.
- Use `TemporaryDirectory`, a fixed basename output template inside it, `skip_download=True`, `noplaylist=True`, `subtitlesformat='vtt'`, an anchored/escaped language selector, and only the selected source's write flag.
- Disable progress, metadata sidecars, postprocessors, persistent yt-dlp cache, and automatic remote EJS component downloads. Use a custom logger and stderr routing. Keep `ignoreerrors=False`.
- Set explicit upstream network policy: `socket_timeout=30`, `retries=3`, `extractor_retries=3`, and HTTP/extractor retry delays of 1, 2, then 4 seconds, capped at 4 seconds. Verify retry callback indexing against the selected stable release and fixture-test the delay sequence. Do not retry the complete wrapper workflow or repeat formatting. Authentication, unavailable-video, and PO-token failures remain explicit; upstream may not retry them. These limits are per supported upstream operation, not a total time/request budget. Keep network policy fixed in v0.1 rather than add more flags/config keys.
- Extract with `download=False, process=False`; require a video result. Before caption selection, reject `live_status='is_live'` with `active livestreams are not supported`, `is_upcoming` with `video has not started`, and `post_live` with `livestream processing is incomplete; try again later`. Accept completed `was_live`, `not_live`, or unknown status without claiming completeness. Apply the guard in all download modes, including preview/raw VTT. Select captions, narrow maps, and call `process_ie_result(..., download=True)` with captions-only options. Do not call private `_write_subtitles` directly or run a second metadata extraction.
- Read the selected result's `requested_subtitles[language]['filepath']`; require exactly one VTT file inside the temporary directory. Return its bytes, normalized video metadata, and selection metadata before cleanup.
- Missing English keys produce `no English subtitles found`. English keys with no VTT candidates produce `no English VTT subtitles found`. A selected track's download failure is an error, not silent switching to another track.
- Do not add cookies, authentication bypass, PO-token provisioning, or extractor-client hacks. Full dependency setup does not guarantee access to every video.

### VTT cleanup

Use a small block parser with a supported YouTube VTT subset, not a full browser renderer and not an FFmpeg conversion.

- Decode UTF-8 with optional BOM; accept LF and CRLF. Require `WEBVTT` and valid cue timing syntax, including optional hours and cue settings.
- Skip the header metadata and complete `NOTE`, `STYLE`, and `REGION` blocks. Ignore optional cue identifiers. Read only payloads attached to valid timing lines.
- Strip VTT timestamp, class, voice, and styling tags, then decode HTML entities. This order preserves escaped literal angle brackets. Collapse payload whitespace and join multiline cue text.
- Preserve cue start/end times internally. Reject malformed caption blocks with a concise parsing error. A valid file without nonempty text produces `empty transcript` in default and `--raw` modes; `--raw-vtt` still returns the original file.
- Manual captions join in cue order without text deduplication. Repetition in manual captions can be intentional.
- Automatic captions use largest suffix/prefix token overlap only within a rolling group. Consecutive cues form a group when their intervals overlap or their gap is at most 100 ms. Reset across larger gaps or backward start times.
- Compare exact decoded tokens, without case folding or punctuation removal. Limit the suffix search to the previous cue's token count, not the full transcript history. Require at least two matching tokens; allow an exact one-token duplicate only for overlapping intervals.
- Preserve repeated tokens within a cue. Append all text when no eligible overlap exists. Do not globally remove duplicate lines or repeated phrases.
- This is a conservative heuristic, not a guarantee of perfect speech reconstruction. Tests must show both rolling cleanup and preservation of intentional repetition.

### Pi formatting and chunking

Add `formatter.py` using shared `FormattingError`, plus `ensure_pi() -> str`, `split_transcript(transcript: str, *, max_chars: int = 12000) -> list[str]`, and `format_with_pi(transcript: str, model: str | None = None, *, chunk_chars: int = 12000, timeout_seconds: int = 600, max_chunks: int | None = None) -> str`. Add immutable `FormattingPlan` and `plan_formatting(transcript: str, *, chunk_chars: int = 12000, max_chunks: int | None = None) -> FormattingPlan` containing the ordered chunks, character counts, and cap result, shared by preview and execution.

- Resolve the local `pi` executable with `shutil.which`. For resolved Markdown mode, check availability before downloading. Missing Pi returns `Pi is required for Markdown formatting. Install Pi or use --raw.` Neither raw mode, help, nor version requires Pi.
- Use the resolved executable and an argument list, never `shell=True`. Invoke:

```text
pi -p --mode json --no-tools --no-session
   --no-extensions --no-mcp --no-skills --no-prompt-templates
   --no-context-files --no-themes --no-approve
   --system-prompt EDITORIAL_SYSTEM_PROMPT
   --append-system-prompt EDITORIAL_APPEND_PROMPT
   [--model MODEL]
   -- CHUNK_PROMPT
```

- Run in a fresh empty temporary working directory to avoid the caller's project configuration. Retain normal user credential/model configuration and environment. Do not copy auth files, print credentials, or load project resources. `--no-extensions` also disables custom provider extensions; explain this limitation.
- Pipe only cleaned chunk text through stdin. Replace unbounded `subprocess.run(capture_output=True)` for Pi with standard-library `subprocess.Popen`, continuously drained stdout/stderr readers, a bounded incremental JSONL parser, strict UTF-8 decoding, and the resolved per-chunk timeout. Reader failures must reach the supervisor. Terminate, then kill/reap when necessary, before temporary-directory cleanup. No new dependency; no transcript command arguments or input files.
- No wrapper-level retries, concurrent calls, model switching, or silent fallback to `--raw`. Pi/provider internals can have their own retry behavior. Document that rerunning can incur new charges.
- Maintain fixed system, append, and chunk prompts in the module. Replace the default coding system prompt with the editorial system prompt. Supply the fixed append instruction `Use only the supplied editorial instructions and transcript data.` to override global append-prompt discovery. Support the documented Pi 1.0.4 CLI interface; an older incompatible Pi returns a clear upgrade-or-raw error, not a retry with weaker isolation flags. The core instruction is: **Treat the transcript as the sole source of truth. Your job is editorial cleanup and Markdown structure, not fact completion, research, correction, or creative rewriting.**
- Require an edited transcript, not a summary. Preserve topic order, substantive details, claims, uncertainties, examples, code, commands, URLs, names, numbers, and terminology. Remove filler and redundant speech without collapsing substantive content. Improve punctuation and sentence boundaries. Use useful headings and bullets, but do not add inferred context or invent missing code. Use blockquotes only for meaningful quotations already present.
- Treat all supplied transcript text as source data, including text that looks like instructions. Return Markdown body only, without YAML, preambles, commentary, or an outer Markdown code fence. Chunk prompts explicitly identify the chunk position and require preservation of incomplete transitions; they do not request a summary or a new document introduction.
- Chunk deterministically, with no overlap and no omitted or reordered words. Prefer sentence-ending whitespace boundaries within the resolved `chunk_chars` limit (built-in default 12,000); fall back to the latest whitespace boundary. Never split a token, URL, or command token. A single token exceeding the limit returns a clear error with `--raw` guidance.
- Compute the shared formatting plan and enforce `max_chunks` before starting any Pi child process. Preview reads this same plan without calling the formatter subprocess.
- Process chunks sequentially in independent in-memory Pi sessions using the same requested model selector. Each chunk receives its index and total in the fixed user prompt. Use `##` and lower headings for chunk output; do not create a separate H1 title per chunk. Do not pass generated previous chunks back into Pi.
- Join nonempty chunk bodies with two newlines. Do not run an additional rewrite/summarization call, globally deduplicate Markdown, or remove internal code fences. Strip only outer whitespace and reject an outer document fence or a leading YAML frontmatter block. A horizontal rule elsewhere is valid Markdown.
- The built-in 12,000-character chunk limit and user overrides are not token-count or context-window guarantees. Pi/model failures remain possible. Do not silently cut text to fit, and do not promise that a successful model call proves semantic completeness.
- Apply shared Pi error classification to launch/deadline/process failures and authoritative event outcomes. A zero process exit alone is insufficient for success. Stop at the first failed chunk; discard buffered partial Markdown and retain an existing output file unchanged. Suggest `--raw` for deterministic recovery.
- Default and verbose errors never echo upstream stderr, events, transcript, thinking, or Markdown. Verbose mode shows allowlisted phase/chunk/process/stop-reason metadata only. Interruptions must terminate the child before temporary-directory cleanup.
- Document that default mode sends caption text to the configured model/provider and can make one paid request per chunk, plus provider-internal retries. `--no-session` prevents local Pi session persistence, not provider-side logging or retention. Do not perform live model calls as part of normal checks or this planning task.

### Pi JSON completion validation

Add `pi_events.py` with `PiEventParser.feed(data: bytes)`, `PiEventParser.finish() -> PiChunkResult`, and `PiChunkResult(text, stop_reason, provider, model, retry_count)`. Validate fixtures against supported installed/current stable Pi. Preserve isolation flags, no-session behavior, default-model selection, and Markdown public output.

- Split records only on LF, strip optional preceding CR, and decode UTF-8 incrementally. U+2028/U+2029 inside JSON strings are not record boundaries. Reject malformed/non-object JSON, invalid UTF-8, incomplete records, and unframed trailing bytes.
- Per-chunk limits: 1 MiB per record, 16 MiB total stdout event bytes, 1 MiB final Markdown text, and 64 KiB retained startup/error stderr. Drain both pipes continuously; terminate/reap on limits/deadline. No truncation or deadlock. Do not persist event streams or include them in logs.
- Require an initial session header and a settled run. Track authoritative assistant `message_end.message`; ignore user content, thinking/signatures, and text deltas for final output. Recovered intermediate errors do not contribute text. Extract only ordered text blocks from the final assistant message, not from every attempt.
- Success requires exit 0, `agent_settled`, a final assistant `stopReason='stop'`, valid nonempty text, and no forbidden recovery/tool event. Read through process EOF and reject inconsistent terminal state or execution after settlement. `agent_end` alone is insufficient.
- Reject `length` as `PI_OUTPUT_INCOMPLETE`, `error` as a positively classified provider fault or `PI_FAILED`, and `aborted` as `PI_ABORTED` unless a local interrupt owns cancellation. Reject `pending`, `toolUse`, `deferred`, missing, or unknown terminal reasons as `PI_PROTOCOL_INVALID`.
- Tool-call content/execution events violate isolation and fail immediately. Compaction start/recovery fails as `PI_CONTEXT_LIMIT` because source summarization violates the editorial contract; terminate the child. Unknown benign events may be ignored, but never establish success. Pi retry events remain allowed; retain safe attempt counts and use only the final successful message. No extra wrapper retry/model switching.
- Startup failures may have no events: use local process evidence and narrowly tested stderr recognition, otherwise generic launch/format errors. Provider `errorMessage` is not a stable typed taxonomy. Never inspect ordinary source/generated content to infer a failure.
- Discard ignored payloads promptly. A normal stop improves completion checks, but does not prove semantic completeness or factual accuracy. Detection/cancellation cannot undo already-started provider work or billing. JSON events never appear in public Markdown/YAML output.

### Package and test approach

Use Python >=3.14.7, version 0.1.0, a `src/` layout, Hatchling, and the entry point `yt-transcript = 'yt_transcript.cli:main'`. Runtime dependencies: `yt-dlp[default]` and PyYAML. Optional MCP runtime extra: official `mcp` SDK, with its transitive dependencies resolved by uv. Development dependencies: pytest and Ruff; install the MCP extra for the complete test suite. Use `pytest` with `asyncio.run` for async MCP tests, without requiring a new pytest async plugin. Use the latest stable releases of yt-dlp, PyYAML, pytest, Ruff, and Hatchling, plus the optional official MCP SDK, available when implementation starts. Exclude prereleases, development snapshots, and yanked releases. Verify each release's Python requirement against Python >=3.14.7; if the newest stable release requires raising the minimum Python version, ask the user before changing that requirement instead of silently choosing an older release. Declare the verified versions as minimum bounds in `pyproject.toml`, without speculative upper bounds. Resolve and record exact direct/transitive versions in `uv.lock` for reproducible development and tests. Do not automatically upgrade dependencies during CLI execution. Commit `uv.lock` when Git is established. Read the installed distribution version with `importlib.metadata`.

Check authoritative PyPI metadata at implementation time rather than treating versions recorded during planning as permanently latest: [yt-dlp](https://pypi.org/pypi/yt-dlp/json), [PyYAML](https://pypi.org/pypi/PyYAML/json), [pytest](https://pypi.org/pypi/pytest/json), [Ruff](https://pypi.org/pypi/ruff/json), [Hatchling](https://pypi.org/pypi/hatchling/json), [MCP SDK](https://pypi.org/pypi/mcp/json). Re-run offline tests, lint, formatting, and build checks after dependency upgrades. External Pi and Deno remain user-managed; document current stable installation guidance without installing or upgrading them automatically.

Use offline tests by default. Mock the downloader and formatter boundaries for CLI tests, the `YoutubeDL` factory for downloader orchestration tests, and supervised Pi process creation/executable discovery for formatter tests. Use version-pinned/synthetic JSONL fixtures and fake local processes for parser/supervisor checks. CI must not require Pi, authentication, or a model call. Isolate home/XDG config discovery in every test; never read the developer's real configuration. CLI tests unrelated to config use `--no-config` or a patched empty config location. Add one offline test using real `YoutubeDL.process_subtitles` against synthetic metadata so upstream selection behavior is not tested only through mocks.

## Scope

**In scope:** shared evidence-based error codes/safe diagnostics, bounded Pi JSON completion validation, package, optional deterministic return-only stdio MCP server, shared service/worker orchestration, bounded MCP operations/results, preview and optional chunk cap, offline doctor, atomic no-clobber output, bounded extraction retries, livestream guard, user-level TOML defaults and explicit config selection, deterministic caption selection, temporary downloads, pure-Python VTT cleanup, Pi editorial Markdown formatting, sequential long-transcript chunking, `--raw`, `--model`, unchanged YAML frontmatter for non-VTT files, CLI output/errors, offline tests, optional live smoke tests, build checks, README, MIT license, and Git-source run instructions.

**Out of scope:** HTTP/SSE MCP transports, remote hosting/authentication, MCP file writes, MCP Pi/model calls, MCP resources/prompts/sampling/elicitation, raw-VTT MCP tool, client-roots access, Markdown quality heuristics, translation-provenance detection, receipt sidecars, caption inspection, project/system config discovery, config-writing commands, executable or prompt overrides in TOML, language flags, playlists, batch video processing, timestamps in cleaned output, audio transcription, local translation, research or fact completion, summaries/style modes, model-generated metadata, caching, authentication flags, FFmpeg, Python Pi SDK integration, bundled Node/Pi, custom provider extensions, publishing, pushing, and automatic runtime installation.

## Tasks

All paths and symbols below are proposed new code, not existing repository interfaces.

- [x] **1. Create the package skeleton.** Add Hatchling configuration, project metadata, Python requirement, dependency groups, script entry point, pytest marker configuration, and Ruff settings. Add minimal importable package and CLI with working help/version. Check current stable PyPI releases and Python compatibility for the five core libraries/build tools plus the optional MCP SDK, then set verified minimum versions and run `uv lock --upgrade` and `uv sync --locked --group dev --extra mcp`. Record resolved versions in the implementation handoff. Add ignore rules for environments, caches, build output, and coverage files. **Files:** `pyproject.toml`, `uv.lock`, `.gitignore`, `src/yt_transcript/__init__.py`, `src/yt_transcript/cli.py`, `tests/test_cli.py`. **Seam:** `cli.main(argv: Sequence[str] | None = None) -> int` and installed console script. **Verify:** `uv run yt-transcript --help`, `uv run yt-transcript --version`, `uv run pytest tests/test_cli.py`.

- [x] **2. Establish shared error adapters and reporting.** Implement the common error types/code registry, phases, bounded cause walking, typed yt-dlp classification, conservative Pi recognizers, warning collector, CLI/MCP rendering, and diagnostic allowlist. Test direct/wrapped/cyclic/malformed causes, HTTP/geo/network evidence, known/unknown warnings, ambiguous 403, rate-limit versus quota evidence, private causes, exit mapping, and adversarial secret/content/control-sequence exclusion. Keep recognizers tied to captured/synthetic fixtures for the supported releases. **Files:** `src/yt_transcript/errors.py`, `tests/test_errors.py`, `tests/fixtures/errors/`. **Seam:** constructed upstream exceptions/records and pure rendering. **Verify:** `uv run pytest tests/test_errors.py`, with no network or model calls.

- [x] **3. Implement TOML loading and effective configuration.** Import shared `ConfigError` and add immutable `AppConfig`, `default_config_path() -> Path`, `load_config(path: Path | None = None, *, disabled: bool = False) -> AppConfig`, and `resolve_config(file_config: AppConfig, *, mode: str | None, verbose: bool | None, model: str | None, max_chunks: int | None) -> AppConfig`. Implement the discovery, explicit-file replacement, schema, size limit, type/range checks, and precedence above. Keep configuration loading independent of Pi and network behavior. Add a copyable example using built-in defaults, with the model omitted. Test XDG absolute/unset/empty/relative paths, no project discovery, missing default/explicit files, replacement rather than merge, empty/partial files, unknown keys/tables, invalid UTF-8/TOML, unreadable/non-file/oversized files, model omission/empty strings, bool-as-int rejection, numeric boundaries, raw-mode CLI precedence, optional chunk-cap bounds/absence/override, configured-model/cap suppression in raw modes, and disable-config behavior. **Files:** `src/yt_transcript/config.py`, `tests/test_config.py`, `config.example.toml`. **Seam:** temporary files, patched home/environment, and pure resolution. **Verify:** `uv run pytest tests/test_config.py`, with no network/Pi access.

- [x] **4. Implement URL validation and caption selection as pure functions.** Add `validate_youtube_url(url: str) -> str`, `select_english_track(info: Mapping[str, Any]) -> CaptionTrack`, and import shared `TranscriptError`. Represent language, manual/automatic source, and VTT format entries in `CaptionTrack`. Test URL host/path validation, playlist parameters on video URLs, every ranking level, lexical ties, original regional English, translated fallback, misleading language prefixes, missing captions, and English without VTT. **Files:** `src/yt_transcript/downloader.py`, `tests/test_downloader.py`. **Seam:** pure functions over URL strings and synthetic yt-dlp dictionaries. **Verify:** `uv run pytest tests/test_downloader.py`.

- [x] **5. Parse VTT into timed cues.** Add `Cue(start_ms, end_ms, text)` and `parse_vtt(vtt: str) -> list[Cue]`. Implement the parsing contract above. Add synthetic fixtures with explicit expected text, including text that resembles metadata or numeric identifiers inside a payload. **Files:** `src/yt_transcript/cleaner.py`, `tests/test_cleaner.py`, `tests/fixtures/manual.vtt`, `tests/fixtures/auto.vtt`, `tests/fixtures/edge_cases.vtt`. **Seam:** parser input/output without network or filesystem coupling. **Verify:** `uv run pytest tests/test_cleaner.py` covers BOM, CRLF, settings, hours, metadata blocks, tags, entities, multiline cues, Unicode, malformed timing, and empty cues.

- [x] **6. Add timing-aware rolling-caption cleanup.** Implement `clean_vtt(vtt: str, *, automatic: bool) -> str` using the parser and the overlap rules. Return text without the CLI's final newline. Test the user's three-cue example, duplicate rolling cues, contained cues, zero overlap, one-word boundaries, punctuation/case changes, long pause resets, backward timing, repeated words within a cue, and repeated manual sentences. **Files:** `src/yt_transcript/cleaner.py`, `tests/test_cleaner.py`, `tests/fixtures/auto.vtt`. **Seam:** `clean_vtt` with full VTT fixtures and explicit expected strings. **Verify:** `uv run pytest tests/test_cleaner.py`.

- [x] **7. Implement the captions-only downloader.** Add `VideoMetadata` and `extract_video_metadata(info: Mapping[str, Any], *, canonical_url: str) -> VideoMetadata` in `metadata.py`, with the fields and normalization rules in the file metadata contract. Add `DownloadedCaptions(vtt: bytes, language: str, automatic: bool, metadata: VideoMetadata)` and `download_english_vtt(url: str, *, verbose: bool = False) -> DownloadedCaptions`. Check Deno availability for downloads, but allow help/version without it. Use the extraction and processing flow specified above. Preserve raw bytes and normalize metadata from the processed result. Record extraction/selection/download phases and use the shared exception/warning adapter without raw logger forwarding. Test wrapped/missing causes, warning-only access limits versus absent candidates, ambiguous 403/explicit 429, safe TLS hints, and secret-free diagnostics alongside exact bounded retry options/delay callbacks, active/upcoming/post-live rejection before subtitle processing, completed/unknown live-status acceptance, both source types, narrow-map behavior, exact options, one extraction, missing/empty/non-VTT files, paths outside the temporary root, metadata failure, subtitle HTTP failure, and temporary cleanup on success and failure. Test missing optional metadata, channel/uploader fallbacks, channel-ID integrity, extracted-ID mismatch, valid/malformed upload dates, UTC timestamp conversion, and zero/fractional/invalid duration. Add the real offline `YoutubeDL.process_subtitles` compatibility test. **Files:** `src/yt_transcript/downloader.py`, `src/yt_transcript/metadata.py`, `tests/test_downloader.py`, `tests/test_metadata.py`. **Seam:** pure metadata normalization plus patched module-level `YoutubeDL` factory and one real upstream selection call. **Verify:** `uv run pytest tests/test_downloader.py tests/test_metadata.py`; no network access and no FFmpeg invocation.

- [x] **8. Format metadata-prefixed output files.** Add `format_transcript_file(metadata: VideoMetadata, body: str, *, language: str, automatic: bool) -> str`. Treat the body as already finalized Markdown or plain text; preserve internal Markdown layout. Emit the fixed-order YAML scalar header and body layout specified above. Use the local safe YAML dumper specified above; declare PyYAML as a runtime dependency in the package skeleton and verify its lockfile entry. Test exact layout, deterministic output, nulls, numeric durations, quoted dates, Unicode, colons, quotes, backslashes, embedded newlines, control characters, YAML-looking titles, and `---` inside text. Test Markdown headings, lists, and internal code fences without body reformatting. Parse the header with `yaml.safe_load` and assert original values/types. Assert identical header bytes for Markdown and plain-text bodies with identical metadata. **Files:** `src/yt_transcript/metadata.py`, `tests/test_metadata.py`, `pyproject.toml`, `uv.lock`. **Seam:** pure formatter and independent YAML parser. **Verify:** `uv run pytest tests/test_metadata.py`.

- [x] **9. Implement isolated Pi formatting, JSON validation, and chunking.** Implement the formatter interface, fixed JSON-mode argv/prompts, pipe supervision, incremental parser, chunking, and shared errors. Test stop/length/error/aborted at exit 0, missing settled/final message, split UTF-8, CRLF/U+2028/U+2029, malformed/partial/oversized records, ignored thinking/source text, successful retry recovery, compaction/tool violations, nonzero exit after valid events, deadline/cancellation, unknown terminal state, and pipe drainage/reaping without deadlock. Test lossless chunk coverage/order, sentence/whitespace boundaries, long tokens, single and multiple chunks, exact argv/stdin/UTF-8/timeout/cwd, model forwarding or absence of a model argument, resolved chunk size/timeout/cap forwarding, preview/execution planner equality, cap boundary and exceedance with zero subprocess calls, disabled resources, no metadata in prompts, no session persistence flag, Unicode Markdown, empty/fenced/frontmatter output, executable/launch failures, timeout, nonzero exit, decode failures, later-chunk failure, and interruption cleanup. Ensure mocks prove zero calls in deterministic raw paths and no extra combine/retry call. **Files:** `src/yt_transcript/formatter.py`, `src/yt_transcript/pi_events.py`, `tests/test_formatter.py`, `tests/test_pi_events.py`, `tests/fixtures/pi_events/`. **Seam:** pure splitter/parser plus patched process creation and fake local children. **Verify:** `uv run pytest tests/test_formatter.py tests/test_pi_events.py`, with no real Pi/model execution.

- [x] **10. Implement offline doctor and atomic output policies.** Implement the doctor report/checks and `write_output(path: Path, data: bytes, *, no_clobber: bool = False) -> None` in `output.py`. Test metadata/version discovery, missing tools, local subprocess argument isolation/timeouts, unsupported or unparsable versions, no network/auth calls, and complete multi-failure reports. Test replacement, existing regular/directory/symlink/broken-symlink destinations, early refusal, a competing destination created before publication, unsupported hard links, cleanup on failures, and post-publication temporary cleanup warnings. Use actual temporary filesystem tests plus targeted operation mocks. **Files:** `src/yt_transcript/doctor.py`, `src/yt_transcript/output.py`, `tests/test_doctor.py`, `tests/test_output.py`. **Seam:** local version checks and completed byte-output publication. **Verify:** `uv run pytest tests/test_doctor.py tests/test_output.py`, with no network or real tool execution in automated tests.

- [x] **11. Wire CLI output, configuration, and stable failures.** Implement all options and exit codes. Parse flags with unset sentinels, bypass config for help/version/doctor, handle URL-free doctor, resolve the selected TOML and CLI overrides, then validate URL/effective mode/preview/cap/no-clobber combinations and output destination before network access. Require Pi availability only for actual Markdown formatting, not preview. Download and clean once; call `format_with_pi` only in resolved Markdown mode, forwarding the effective model/chunk/timeout/cap settings. Preview downloads/cleans once and renders the shared formatting plan instead of invoking Pi. Route file output through `write_output` with the selected no-clobber policy. Use UTF-8 output independent of locale and byte output for raw VTT. Call `format_transcript_file` after all body processing succeeds, only for non-VTT `-o` output. Keep the metadata module outside the VTT cleaner. Use the tested output publication policy and implement clean interruption/broken-pipe handling. Render shared error codes/safe hints with evidence-based categories and phase-specific fallbacks; never dump upstream causes. Test incomplete Pi output despite exit 0, later-chunk failure without partial publication, secret-free verbose diagnostics, and exit 130 after child cleanup. Test default Markdown, `--raw`, and `--raw-vtt`, each with stdout and `-o`; `--config`/`--no-config` exclusivity, CLI-over-config precedence, invalid config failure before network, help/version with malformed config, configured raw modes without Pi, configured versus explicit model handling, forwarding of configured chunk size/timeout, no model argument by default, and rejected explicit raw/model combinations; preview report without Pi, cap-exceeded preview versus formatting behavior, raw/cap conflicts, no-clobber refusal before download, concurrent-destination handling, doctor exit codes and flag conflicts, all-mode livestream errors; frontmatter before file body, identical metadata across Markdown/plain modes, no frontmatter on stdout, exact raw-VTT file bytes, missing optional metadata, no extra extraction, no Pi calls in raw modes, missing Pi, later-chunk formatting failure and existing-file preservation, verbose logging, invalid URLs, no captions, missing Deno, unavailable/authentication/unknown errors, malformed/empty VTT, output permission failures, existing-file preservation, and stdout/stderr separation. **Files:** `src/yt_transcript/cli.py`, `src/yt_transcript/config.py`, `src/yt_transcript/downloader.py`, `tests/test_cli.py`. **Seam:** `main(argv)` with mocked `download_english_vtt`, `ensure_pi`, and `format_with_pi`, capture of stdout/stderr, and temporary destinations. **Verify:** `uv run pytest tests/test_cli.py`.

- [x] **12. Add the shared deterministic service and supervised worker.** Implement the service interfaces, typed results, metadata mapping, and internal worker protocol above, serializing only shared `ErrorInfo` fields for failures. Refactor deterministic CLI/preview calls to the service without changing output bytes, model selection, or Pi behavior. Add async worker supervision with fixed size/time/concurrency limits and terminate/kill/reap cleanup. Test one extraction, CLI/MCP header equality, safe worker argument allowlists, bounded pipe reading, noisy child output, busy behavior, timeout, cancellation, later reuse after failure, and temporary-file cleanup. **Files:** `src/yt_transcript/service.py`, `src/yt_transcript/mcp_worker.py`, `src/yt_transcript/mcp_server.py`, `src/yt_transcript/doctor.py`, `src/yt_transcript/cli.py`, `tests/test_service.py`, `tests/test_mcp_worker.py`, `tests/test_cli.py`. **Seam:** shared pure/operation functions and fake local worker processes, with mocked downloader/version checks. **Verify:** `uv run --extra mcp pytest tests/test_service.py tests/test_mcp_worker.py tests/test_cli.py`, without network/Pi execution.

- [x] **13. Register stdio MCP tools and CLI dispatch.** Implement `create_server(config: AppConfig) -> MCPServer` with an injectable worker-runner seam for tests, three typed tools/annotations, and `run_stdio_server(config: AppConfig) -> None`. Add lazy `--mcp` dispatch and startup flag validation. Assert tool input/output schemas, error results, untrusted-content descriptions, no Pi/file-write tools, config mode/model isolation, no checks on initialization/listing, byte-equal Python metadata headers, limits, and continued availability after a failed tool. Use official v2 in-memory `Client(server, raise_exceptions=True)` tests; separately launch a real stdio server with the SDK client to test initialize/list, invalid URL calls (no YouTube), protocol-only stdout, disconnect/shutdown, and invocation from outside the repository. Test missing MCP extra independently of core CLI help/version. Use subprocess fixtures with mocked operations for successful calls and cancellation; do not add a production fixture flag or environment backdoor. **Files:** `src/yt_transcript/mcp_server.py`, `src/yt_transcript/cli.py`, `pyproject.toml`, `uv.lock`, `tests/test_mcp_server.py`, `tests/test_mcp_stdio.py`, `tests/test_cli.py`. **Seam:** official SDK Client plus packaged stdio process. **Verify:** `uv run --extra mcp pytest tests/test_mcp_server.py tests/test_mcp_stdio.py tests/test_cli.py` and all offline checks; no live videos, real version tools, or model calls.

- [x] **14. Document setup and add optional live checks.** Write README with optional MCP extra installation, `--mcp` client startup, three tool schemas/results, document saving with existing YAML intact, stdio-only logging, no Pi/file-write behavior, server limits and cancellation caveats, Deno and external Pi setup, user-managed provider authentication, default Markdown versus `--raw` versus `--raw-vtt`, `--model`, user TOML location/schema/example/precedence, `--config` and `--no-config`, configurable chunk/timeout/cap limits, preview report and network/cost limitations, offline doctor and its readiness limits, no-clobber filesystem constraints, fixed download retry policy, livestream rejection messages, Pi-default-model preservation, isolation/custom-provider limitations, sequential chunk behavior and completeness limits, provider data transmission/retention and cost, no-session scope, local `uv run`, `uvx --from` Git-source usage, shell composition, options, the file frontmatter example and field meanings, missing-value rules, `-o` versus shell redirection, raw-VTT exclusion, shared error/recovery table, ambiguous access/provider diagnosis limits, JSON length-stop rejection/event privacy, selection rules, translation fallback, cleanup limits, and YouTube blocking/PO-token caveats. State that bare `uvx yt-transcript` refers to the unrelated PyPI project. Add MIT license with contributor attribution. Add an integration-marked test enabled only when `YT_TRANSCRIPT_TEST_URL` is set; run deterministic `--no-config --raw` mode for that supplied public video and assert nonempty clean text, no VTT markers, and clean stdout. Also run `--no-config --raw -o` mode, parse its frontmatter, assert the canonical video URL/ID and selected-caption fields, and assert nonempty transcript text after the header. A real default-mode Pi smoke test requires separate explicit operator approval for model spend and `YT_TRANSCRIPT_TEST_PI=1`; it must not run solely because a YouTube URL is set. That test checks Markdown body and unchanged file metadata, without claiming deterministic editorial quality. Do not require optional channel/date/duration fields to be present for every live video. Default tests skip it. **Files:** `README.md`, `LICENSE`, `config.example.toml`, `tests/test_integration.py`. **Seam:** installed CLI and real public-video extraction in an explicit opt-in test. **Verify:** `uv run pytest`; with Deno and an operator-supplied URL, `uv run pytest -m integration tests/test_integration.py`.

- [x] **15. Verify distribution artifacts and Git-first delivery.** Run all offline checks, build wheel/sdist, and check entry-point installation through `uvx --from . yt-transcript --help` and `--version`. Inspect wheel content for the package, entry point, license, and absence of development artifacts. Once the user supplies/configures a reachable Git remote and approves uploading the implementation, read its actual URL and test `uvx --from "git+$REMOTE_URL" yt-transcript --help`, then a supplied public video URL with `--no-config --raw`. Run default Pi mode only with separate explicit spend approval. Do not create a remote, push, or publish as part of implementation. **Files:** `pyproject.toml`, `README.md` only if packaging/docs corrections are needed. **Seam:** built distribution and isolated uv tool installation. **Verify:** `uv run --extra mcp pytest -m 'not integration'`, `uv run ruff check .`, `uv run ruff format --check .`, `uv build`, local uvx help/version. Git-source verification is a separate network gate until a remote exists.

## Verification and Acceptance

1. All offline tests pass without YouTube, Deno, FFmpeg, Pi, or a model being invoked. Help/version require neither Deno nor Pi; both raw modes bypass Pi.
2. Exactly one ranked English VTT track is downloaded. No video, audio, thumbnail, info JSON, or transcript cache is written.
3. The rolling-caption example becomes `so the first thing i want to talk about`. Repeated manual text and automatic phrases across a long pause remain intact.
4. Default stdout contains only edited Markdown with one final newline. `--raw` stdout contains deterministic plain text. `--raw-vtt` output is byte-for-byte identical to the selected downloaded VTT.
5. Default and `--raw` `-o` files start with parseable YAML frontmatter in fixed key order, followed by a blank line and the selected body. Header bytes are identical for the same metadata regardless of body mode. Values match the existing extraction; unavailable fields are `null`. Strings round-trip safely through a YAML parser.
6. File output leaves stdout empty. `--raw-vtt -o` files have no injected frontmatter. Shell redirection receives body-only stdout. Failures before output do not truncate an existing destination. Temporary subtitle files are removed on all paths.
7. Expected errors use stable codes/safe hints and existing exit meanings. Neither default nor verbose diagnostics include raw upstream exceptions, secrets, source/generated content, or event streams; verbose fields are allowlisted.
8. Run active diagnostics on changed Python files during implementation, then a full project check before handoff. Report unavailable diagnostic coverage rather than treating an empty cache as proof.
9. `uv build` succeeds, and isolated local-source uvx runs expose the expected help/version. An approved live check confirms current YouTube behavior, but is not a deterministic CI gate.
10. Pi tests prove exact disabled-tool/resource flags, stdin-only transcript transmission, model forwarding, sequential lossless input chunks, one header per completed file, and no output commit after a chunk failure. Prompt tests assert editorial-only instructions. Automated structural tests do not prove model faithfulness.
11. Live Pi checks require separate explicit approval. Documentation explains provider transmission, multiple-call cost, context/output limits, and lack of a sandbox guarantee.
12. TOML tests prove discovery/replacement/disable behavior, strict schema validation, CLI precedence, and failure before network/model access. With no model override in CLI or TOML, Pi receives no model argument. Raw modes never invoke Pi, even with a saved model preference. Header bytes are unaffected by configuration.
13. Preview produces the same chunk counts as actual planning with zero Pi calls and no output file. Cap exceedance prevents every formatting invocation and output commit. Reports call counts, not guaranteed billable requests or dollars.
14. Doctor is URL-free/offline, reports all local checks without exposing credentials or running a model, and uses bounded version commands. No-clobber rejects existing/racing destinations without replacing them, including raw VTT, and unsupported atomic publication fails closed.
15. Downloader tests prove bounded retry configuration and delay sequence, rejection of active/upcoming/post-live results, and acceptance of completed/unknown states. No wrapper-level or formatting retries are introduced.
16. MCP initialize/list succeeds without Deno/Pi/network checks. Exactly three deterministic tools are exposed, with typed input/output schemas; every successful structured tool result validates against its output schema, expected failures use error results, and stdout contains only protocol messages. Metadata/document output matches the deterministic CLI header, with no persistent final file or Pi call.
17. MCP tests cover tool errors without server death, URL/argument allowlists, config isolation, worker concurrency/size/time limits, cancellation/disconnect/reaping, and optional-extra startup errors. In-memory tests alone are not proof of stdio correctness; a real process test is required.
18. Pi success requires validated JSON completion and exit 0. Length/error/aborted/unsettled/compacted/tool-using runs never publish a document even at exit 0. Recovered attempts contribute only final successful text; parser/deadline failures reap children without partial output.
19. Error tests prove phase/cause precedence, cautious 403/absence classification, safe hints only with evidence, CLI/MCP code consistency, and adversarial redaction. Error handling never modifies source metadata.
20. Git-source execution is verified only after a reachable remote exists. PyPI publication and package renaming require a separate user-approved release plan.

## Implementation verification and remaining gates

- Parent continued implementation directly after the delegate stopped, as requested. Tasks 1 through 15 are complete for the user-approved private Git delivery. Offline checks use the selected Python 3.14.7 baseline. Optional live-video/model checks remain deferred because no operator test URL or model-spend approval was supplied.
- Final Python 3.14.7 checks: `uv run --extra mcp pytest -q -W error::pytest.PytestUnraisableExceptionWarning` reports **185 passed, 2 skipped**, without warnings. The skipped tests are opt-in live YouTube/Pi checks. Ruff lint/format checks pass. `pyright --project pyrightconfig.json` reports **0 errors, 0 warnings** across source and tests. The earlier Python 3.13.7 run passed 184 tests but is not the supported final baseline.
- `uv build` produces `dist/yt_transcript-0.1.0-py3-none-any.whl` and `dist/yt_transcript-0.1.0.tar.gz`. Refreshed local-source uvx help and normal uvx version pass. Final wheel inspection confirms Python >=3.14.7, application modules, console entry point, MIT license, and no tests/plans/environments. Wheel generator is Hatchling 1.32.4.
- Verified versions: yt-dlp 2026.8.19, PyYAML 6.0.3, yt-dlp-ejs 0.8.0, official MCP 2.3.0, pytest 9.1.1, Ruff 0.16.10, Hatchling 1.32.4.
- Active LSP delta/full probes were run. The session LSP reports unresolved sibling/venv imports despite successful runtime imports and clean project-configured Pyright. Its auxiliary rules also flag intentional Protocol declarations and numeric conversion inside a helper whose caller handles `ValueError`. LSP results are not claimed clean.
- Parent fixes add regression coverage for empty URL credentials, error-like titles, nested HTTP-cause precedence, stale Pi completion after a new assistant attempt, removal of retained thinking, worker descendants holding pipes after parent exit, malformed private operation types, ASCII VTT timing, oversized hours, and test type safety.
- Python 3.11.13 full-suite check in a separate temporary environment: **182 passed, 2 failed, 2 skipped**. The official MCP SDK/Pydantic rejects standard-library `typing.TypedDict` for schema generation on Python <3.12. Tool `outputSchema` and structured success results are consequently absent. This superseded interpreter also emitted a subprocess-transport cleanup warning. The user then approved the Python 3.14.7 baseline, and its full suite passes with unraisable warnings treated as errors. No Python 3.11 compatibility is claimed.
- No live YouTube or Pi/model calls or PyPI publication occurred. The user subsequently approved initializing Git on main, committing all project source/tests/docs/plan/lockfile, creating private GitHub repository `NMDRA/yt-transcript`, and pushing it. Initial implementation commit `e58e57c4f196068224012ea12498eef7e911d443` was pushed to `origin/main`; GitHub confirms the repository is private. Authenticated Git-source uvx help/version passed. Git-source installation with the MCP extra passed initialization, exact three-tool discovery, typed output schemas, and clean stdio shutdown without runtime/YouTube/Pi calls. uv 0.8.13 requires explicit `--python 3.14.7` for the MCP-extra source expression; README commands include it. Authentication uses an existing credential helper, not a token embedded in URLs or arguments. Live video/model checks remain separate gates.

## Open Questions

No unresolved implementation decisions. The user selected installed stable Python 3.14.7 and approved private GitHub delivery at `https://github.com/NMDRA/yt-transcript.git`. No public repository, PyPI publication, or live-model spend is approved.
