# CLI reference

[README](../README.md) · [Installation](installation.md) · [Troubleshooting](troubleshooting.md)

These commands use the installed executable.
If you use a development checkout, use `uv run yt-transcript` instead.

## Output modes

```sh
yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config
yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --raw
yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --raw-vtt -o captions.vtt
yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --model provider/model-id -o transcript.md
```

| Mode | Body | AI model | File metadata |
|---|---|---|---|
| Default | Edited Markdown | Yes | YAML with `-o` |
| `--raw` | One normalized paragraph | No | YAML with `-o` |
| `--raw-vtt` | Unchanged VTT bytes | No | None |

Stdout contains only the transcript body.
File output leaves stdout empty.
All non-VTT bodies end with one newline.

Terminal stderr shows a spinner while the tool retrieves and filters captions.
Then stderr shows a bar with completed model calls and elapsed time.
Summarized mode includes the final synthesis call in this count.
Progress does not estimate download bytes, tokens, cost, or completion time.
The tool disables progress for redirected stderr, `TERM=dumb`, help/version, doctor, and MCP.
Progress never appears in transcripts or files.

Use `-o` for Python-generated YAML metadata.
Raw and Markdown file headers include the nullable video `description`.
See [Metadata files](behavior.md#metadata-files) for the field contract.
Descriptions stay out of stdout bodies, model input, preview, and raw VTT.
Shell redirection receives only the transcript body:

```sh
yt-transcript URL --no-config --raw > body.txt
yt-transcript URL --no-config --raw -o transcript.txt
yt-transcript URL --no-config --raw | wc -w
```

The URL must contain an 11-character video ID.
Supported hosts are `youtube.com`, `www.youtube.com`, `m.youtube.com`, and `youtu.be`.

The tool supports watch, shorts, and embed URLs.
A playlist parameter on a video URL does not enable playlist downloads.

## Configuration

The wrapper reads `$XDG_CONFIG_HOME/yt-transcript/config.toml` when `XDG_CONFIG_HOME` is an absolute, nonempty path.
Otherwise, the wrapper reads `~/.config/yt-transcript/config.toml`.

The wrapper ignores relative XDG paths.
The wrapper never searches project files or parent directories.
If the default file is missing, the wrapper uses built-in defaults.

`--config PATH` selects one file instead of configuration discovery.
`--no-config` disables wrapper configuration.
These flags do not change Pi configuration or credentials.

The wrapper applies settings in this priority order:
- Explicit CLI flags
- The selected TOML file
- Built-in defaults

```toml
[output]
mode = "markdown"       # "markdown", "raw", or "raw-vtt"
verbose = false

[formatting]
chunk_chars = 12000
summary_synthesis_chars = 50000
timeout_seconds = 600
editorial_mode = "standard"  # "standard", "focused", or "summarized"
# max_chunks = 20
# Omit model to use Pi's configured default.
# model = "provider/model-id"

[sponsorblock]
# Omit enabled: CLI off, MCP filtered on. Explicit false disables both.
# enabled = false
categories = ["sponsor", "selfpromo", "interaction"]
timeout_seconds = 10
```

Unknown keys, invalid types, malformed TOML, and files larger than 64 KiB cause errors.
The wrapper does not create configuration files.

| Key | Valid values |
|---|---|
| `output.mode` | `markdown`, `raw`, `raw-vtt` |
| `output.verbose` | Boolean |
| `formatting.provider` | `pi` (default), `openrouter`, or `deepseek` |
| `openrouter.max_output_tokens` | Integer 1 through 131072; default 16384 |
| `deepseek.max_output_tokens` | Integer 1 through 393216; default 16384 |
| `formatting.thinking` | Optional strict Boolean; summarized auto-enables when omitted |
| `formatting.thinking_level` | Optional scalar `low`, `medium`, or `high`; see thinking policy |
| `formatting.model` | Nonempty selector string, or omit the key |
| `formatting.chunk_chars` | Integer 1,000 through 50,000; default 12,000; source input limit |
| `formatting.summary_synthesis_chars` | Integer 1,000 through 500,000; default 50,000; multi-chunk summary synthesis input limit |
| `formatting.timeout_seconds` | Integer 1 through 3,600, per model call |
| `formatting.max_chunks` | Integer 1 through 1,000, or omit for unlimited; includes summary synthesis |
| `formatting.editorial_mode` | `standard` (default), `focused`, or `summarized` |
| `cache.path` | Empty or omitted keeps the existing cache location; otherwise an absolute SQLite filename with optional `~` expansion; MCP only |
| `mcp.markdown_timeout_seconds` | Integer 300 through 3,600; total MCP Markdown deadline, default 300; ignored by CLI |
| `sponsorblock.enabled` | Optional boolean; unset means CLI off, MCP filtered on |
| `sponsorblock.categories` | Nonempty unique list: `sponsor`, `selfpromo`, `interaction`, `intro`, `outro`, `preview` |
| `sponsorblock.timeout_seconds` | Integer 1 through 30, per socket operation |

`--raw`, `--raw-vtt`, `--model`, `--max-chunks`, and `-v` override their corresponding defaults.
There is no `--markdown` or `--quiet` flag.
Set `chunk_chars` and `summary_synthesis_chars` in `[formatting]` in TOML.
There is no `--chunk-chars` or `--summary-synthesis-chars` flag.

After schema checks, raw modes ignore saved formatting preferences.
An explicit model, chunk cap, or editorial-mode flag conflicts with raw output.
`--editorial-mode` overrides TOML.
The mutually exclusive `--sponsorblock` / `--no-sponsorblock` flags also override TOML.
The existing CLI structure and defaults remain unchanged.

Without an explicit model in TOML or CLI, every Pi call omits `--model`.
Pi selects its configured default.
The wrapper never selects a fallback model.

Help and version ignore wrapper TOML.
Doctor loads the selected TOML without network requests.
A malformed configuration still blocks raw mode unless you supply `--no-config`.

## Providers

Pi remains the default.
To use OpenRouter, select it explicitly:

```sh
uv run yt-transcript URL --no-config --provider openrouter --model openai/gpt-4o -o transcript.md
```

Set `OPENROUTER_API_KEY` in the process environment.
Never put the key in TOML or command arguments.
OpenRouter requires an explicit model and no Pi installation.
Raw modes require neither a model nor credentials.
Preview requires a selected OpenRouter model, but no API key.
Preview does not make a model request.

**TOML migration:** rename `[pi]` to `[formatting]`.
The wrapper rejects the old table instead of merging it.
Add `provider = "openrouter"` or keep the default `"pi"`.
The `[openrouter]` table accepts only `max_output_tokens`.
Its default is 16384, and its range is 1–131072.
The wrapper sends this value as `max_tokens`.
The supported limits depend on the model.
Reasoning tokens can use the allowance.
Truncated or empty output causes failure without repair.

The wrapper sends one nonstreaming HTTPS request per completion through a supervised Python helper.
It rejects redirects, HTTP error bodies, tool calls, and incomplete output.
A monotonic deadline applies to the helper and HTTP work.
Socket timeouts alone do not enforce this deadline.
The wrapper does not retry or change providers automatically.
Requests disable OpenRouter upstream fallback, require parameter support, and request providers with `data_collection="deny"`.
These settings can leave no available route.
The settings do not guarantee zero retention, accuracy, or a fixed upstream identity.
Transcript text reaches OpenRouter and its selected upstream provider.
Calls can incur charges, including work completed after a local timeout.

These features are included in dev8. When updating from dev7, rename `[pi]` to `[formatting]` and keep your existing settings.

### Direct DeepSeek

```sh
# Set DEEPSEEK_API_KEY in the process environment first.
yt-transcript URL --no-config --provider deepseek --model deepseek-flash -o transcript.md
```

DeepSeek requires an explicit model and no Pi installation.
`deepseek-flash` and `deepseek-v4-pro` are examples, not a fixed model catalog.
The key comes only from `DEEPSEEK_API_KEY` in the helper environment.
Never put it in TOML, command arguments, or MCP tool arguments.
Preview requires an explicit model but no key; doctor checks local model/key presence, not authentication.
Raw modes need neither.

The fixed endpoint is `https://api.deepseek.com/chat/completions`.
The supervised helper uses standard-library HTTP with one nonstreaming request per planned call and no new dependency.
It rejects redirects and makes no retry, repair call, or provider fallback.
`[deepseek]` accepts only `max_output_tokens`, default 16384, integer range 1–393216.
The model must support the requested allowance.
Thinking shares this allowance with visible text; enabling it does not raise the limit.
Invalid, oversized, empty, or incomplete output fails without partial publication.
See [byte limits](behavior.md#backend-independent-formatting).

Transcript text reaches DeepSeek directly.
OpenRouter's `data_collection="deny"` routing request does not apply.
Consult DeepSeek's privacy policy; the wrapper gives no equivalent retention guarantee.
A local timeout cannot undo charges already incurred.

### Thinking policy

Configure thinking in TOML only. There are no new CLI thinking flags or public MCP arguments.
Both settings are optional; keep them commented to use the automatic policy:

```toml
[formatting]
# thinking = false
# thinking_level = "medium"
```

`thinking` must be a Boolean. `thinking_level` must be one scalar string: `low`, `medium`, or `high`, not an array.
TOML has no null value; omit the key instead.

| `thinking` | Editorial mode | Requested policy |
|---|---|---|
| Omitted | Standard/focused | Preserve Pi/OpenRouter defaults; DeepSeek off |
| Omitted | Summarized | On at configured level, otherwise medium |
| `true` | Any | On at configured level, otherwise medium |
| `false` | Any | Off; a valid configured level stays inactive |

A level alone is valid in summarized mode because automatic thinking enables it.
In standard/focused mode it requires `thinking = true`, unless explicit false keeps it inactive.
Otherwise formatting reports a safe configuration error rather than silently enabling paid behavior.
Raw and model-free MCP operations validate configuration but never call a model because of these settings.
Direct summaries, each notes call, and final synthesis all use the same requested level.

Pi receives `--thinking off` or the selected level; omission in standard/focused adds no flag.
OpenRouter receives explicit reasoning enabled/effort settings with response reasoning excluded; default preservation adds no reasoning field.
DeepSeek receives `thinking.type` enabled or disabled and maps low/medium/high to low/high/high when enabled.
Medium therefore requests high from DeepSeek.
These are requested states, not verified provider behavior or equal token budgets.
Pi and OpenRouter can clamp or map levels or reject unsupported parameters.
Some models cannot disable reasoning.
OpenRouter still requires parameter support and disables upstream fallback.

Thinking can increase cost, latency, and token competition with visible output.
Reasoning exclusion hides response content but does not disable thinking or billing.
The wrapper does not raise token limits automatically, add calls, retry, repair, or return partial output.
Automatic summary thinking is application policy, not evidence of improved fidelity.

## Editorial modes

`standard` produces an edited transcript and remains the default.
`focused` produces an edited transcript with separable non-substantive material removed.
`summarized` produces one whole-video summary, not an edited transcript.

```sh
uv run yt-transcript URL --no-config --editorial-mode summarized --preview
uv run yt-transcript URL --no-config --editorial-mode summarized --max-chunks 20 -o summary.md
```

The summary prompt targets 400–700 words for substantial videos and fewer words for short sources.
It requests `## Summary`, `## Key points`, and an optional `## Conclusions and caveats` section.
Python checks these headings and requires nonempty section bodies.
The length target and factual quality are not guaranteed.
The prompt prioritizes the main ideas, important results, and source qualifications.
It treats captions, chapter titles, and intermediate notes as untrusted data.
Video descriptions are not model input.
The summary body does not retain canonical chapter headings; source chapter metadata stays unchanged.

One input chunk needs one summary call.
Multiple input chunks need one factual-note call per chunk and one final synthesis call.
The tool publishes only the final summary.
The tool does not return intermediate notes.
`--max-chunks` counts all these calls.
For example, three input chunks require a cap of at least four.
Notes are strict private claims objects with source IDs from the same call and qualification arrays.
Per-chunk budgets include schema and ID framing and JSON escaping.
After minimum claim framing, at least 256 usable serialized characters must remain.
Source chunks must fit `formatting.chunk_chars`.
The complete final notes envelope must fit the independent `formatting.summary_synthesis_chars` limit.
The notes prompt requests compact JSON and targets 75% of each allocated hard response limit.
The hard limit still applies to the raw response and the compact serialized claims.
An infeasible note budget fails with `PI_CONTEXT_LIMIT`, `OPENROUTER_CONTEXT_LIMIT`, or `DEEPSEEK_CONTEXT_LIMIT` before model calls.
Oversized or invalid notes cause failure without truncation, a repair call, or a partial summary.
If all evidence is empty, processing fails before synthesis.
The formatter rejects final output that contains canonical internal IDs.
Valid references do not prove factual support or complete caveats.
Small chunks can create too many notes for one bounded synthesis input.
Use preview to check the plan.
A larger cap alone does not solve this input limit.
Increase `formatting.summary_synthesis_chars` only when the selected model supports the larger request.
The setting counts characters, not model tokens, and does not include instructions or the output allowance.
It does not extend any deadline or guarantee valid notes.

All modes keep the existing isolation, per-call timeout, metadata, and atomic file-output rules.
Raw modes and MCP plain text do not summarize.

## Read-only chunk continuity

```sh
uv run yt-transcript URL --no-config --boundary-context-chars 100 --preview
uv run yt-transcript URL --no-config --editorial-mode focused --boundary-context-chars 100 -o transcript.md
```

The integer range is 0–1000 characters per neighboring side.
The default is zero.
The explicit flag requires standard/focused Markdown, including preview.
It is invalid with raw output, summarized mode, doctor, or MCP launch, even when set to zero.
There is no TOML key or public MCP argument for context.
MCP retains zero context.

Read-only windows contain adjacent retained caption words, not earlier model output.
Only the current payload owns output.
Do not copy context into the document.
Before splitting, planning reserves space for JSON framing and worst-case escapes.
Planning then reports actual serialized sizes and call counts.
This can increase calls or cause a planning-limit error.
Context windows contain only whole words that fit their character limit.
If an adjacent word does not fit, the tool omits it from that context window instead of truncating it.
Current text is not omitted this way.
If a current word cannot fit the remaining source budget after reserved context and framing, planning fails instead of truncating the word.
At 1000 characters per side, a 12000-character source budget cannot cover worst-case context plus current text.
A larger chunk limit is not a model capability or completion guarantee.
Explicit context adds `boundary context characters per side` to preview.
Model context leakage cannot be fully detected.
See [fidelity limits](behavior.md#internal-summary-evidence-and-continuity).

## Preview and cost controls

```sh
yt-transcript URL --no-config --preview
yt-transcript URL --no-config --max-chunks 10 -o transcript.md
```

Preview downloads and cleans captions.
Preview never calls a model.
Preview shows these fields in a fixed order:

1. Canonical URL
2. Full cleaned character count
3. Retained input character count
4. SponsorBlock status
5. Removed cue count
6. Planned formatter invocations
7. Largest serialized source chunk size
8. Configured source chunk limit
9. Configured summary synthesis limit
10. Planned synthesis invocations
11. Summary notes hard output limit, or `not applicable`
12. Maximum chunks
13. Cap result
14. Provider
15. Model selection
16. Editorial mode

Preview also reports requested thinking state/level and the DeepSeek medium-to-high mapping when applicable.
It does not verify that a model honors the request.

Preview requires Markdown mode and no output path.
If the plan exceeds the cap, preview still returns a successful report.
Actual formatting rejects a plan that exceeds the cap before any model call.

Preview is not a cache or a reservation.
A later run downloads captions again.
Invocation counts are not token counts, dollar estimates, or exact provider-request counts.

The formatter splits text on sentence boundaries or whitespace.
The formatter does not split tokens.
Current chunks that own output do not overlap.
Optional read-only source windows can repeat neighboring words.
Pi sends chunks in sequence through independent in-memory sessions.
OpenRouter and DeepSeek use independent HTTP completions.

Standard and focused modes join completed bodies without a final synthesis call.
They do not summarize or remove duplicates across the complete Markdown document.
They do not send earlier generated chunks to Pi.
Summarized mode uses bounded notes and a final synthesis call when there is more than one source chunk.
Preview includes that call.
The call's exact input length depends on the generated notes.

If a single token exceeds the chunk limit, formatting fails.
The formatter does not truncate the token.
Character limits do not guarantee a compatible context window or output limit.

**Default Markdown sends caption text to the configured model/provider.**
This can incur one paid call per source chunk, plus Pi/provider-internal retries.
Multi-chunk summarized output can incur one additional paid synthesis call.

A repeated run can incur new charges.
A timeout or cancellation cannot undo provider work or billing.
The wrapper does not retry model calls.

Model-processing failures print a warning on stderr.
The warning suggests `--raw` for plain text without an AI model.
The wrapper does not write a partial processed document or automatic fallback.
MCP uses `output_format="plain_text"` for the same explicit recovery.
The total MCP Markdown deadline is separate from CLI per-chunk timeouts.

`--no-session` prevents local Pi session persistence.
This flag does not prevent provider-side logging or retention.

## Doctor and file safety

```sh
yt-transcript --doctor
yt-transcript URL --no-config --raw -o transcript.txt --no-clobber
```

Doctor is local and loads the selected wrapper TOML.
To skip this file, use --no-config.
Doctor reports Python, package versions, EJS compatibility, Deno, and selected-backend readiness without network requests.
Doctor accepts --provider, --model, --config, and --no-config.
For OpenRouter and DeepSeek, doctor checks that an API key and model are present.
Doctor does not check provider authentication.

Version commands use isolated directories and five-second deadlines.
Doctor does not run a model, access YouTube, or run authentication commands.
Doctor checks that the selected direct-provider key is present without displaying the key.

A healthy report shows local readiness only.
The report does not verify video access, provider authentication, caption completeness, or model accuracy.

File output uses a completed sibling temporary file.
By default, publication atomically replaces the destination after success.
Failures before output leave existing files unchanged.

`--no-clobber` requires `-o`.
Before extraction, this flag rejects existing entries, including broken symlinks.
Atomic hard-link publication also rejects a destination created during processing.

Filesystems without usable hard links fail closed.
There is no replacement fallback.
A cleanup failure after publication produces a warning.
The cleanup failure is not reported as a publication failure.

The output parent directory must exist.
Stdout is not transactional.
A failed stdout write can leave partial bytes in a pipe.
