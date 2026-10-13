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

The tool shows a spinner on terminal stderr while it retrieves and filters captions.
Then the tool shows a bar on stderr with completed model calls and elapsed time.
In summarized mode, this count includes the final synthesis call.
Progress does not estimate download bytes, tokens, cost, or completion time.
The tool disables progress for redirected stderr, `TERM=dumb`, help/version, doctor, and MCP.
Progress never appears in transcripts or files.

Use `-o` for Python-generated YAML metadata.
Raw and Markdown file headers include the nullable video `description`.
See [Metadata files](behavior.md#metadata-files) for the field contract.
The tool excludes descriptions from stdout bodies, model input, preview, and raw VTT.
Shell redirection receives only the transcript body:

```sh
yt-transcript URL --no-config --raw > body.txt
yt-transcript URL --no-config --raw -o transcript.txt
yt-transcript URL --no-config --raw | wc -w
```

The URL must contain an 11-character video ID.
Supported hosts are `youtube.com`, `www.youtube.com`, `m.youtube.com`, and `youtu.be`.

The tool supports watch, shorts, and embed URLs.
A playlist parameter in a video URL does not enable playlist downloads.

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
| `formatting.chunk_chars` | Integer 1,000 through 200,000; default 12,000; source input limit |
| `formatting.summary_synthesis_chars` | Integer 1,000 through 500,000; default 50,000; multi-chunk summary synthesis input limit |
| `formatting.timeout_seconds` | Integer 1 through 3,600, per model call |
| `formatting.max_chunks` | Integer 1 through 1,000, or omit for unlimited; includes summary synthesis |
| `formatting.editorial_mode` | `standard` (default), `focused`, or `summarized` |
| `captions.language` | One BCP-47-shaped tag of 2 through 63 characters, with letters and digits separated by hyphens; default `en` |
| `cache.path` | Omit the key or set an empty value to keep the current cache location. For a different location, set an absolute SQLite filename. The `~` character expands to the home directory. |
| `mcp.markdown_timeout_seconds` | Integer 300 through 3,600; total MCP Markdown deadline, default 300; ignored by CLI |
| `sponsorblock.enabled` | Optional boolean; unset means CLI off, MCP filtered on |
| `sponsorblock.categories` | Nonempty unique list: `sponsor`, `selfpromo`, `interaction`, `intro`, `outro`, `preview` |
| `sponsorblock.timeout_seconds` | Integer 1 through 30, per socket operation |

`--raw`, `--raw-vtt`, `--model`, `--max-chunks`, `--language`, and `-v` each override the corresponding configured value.
There is no `--markdown` or `--quiet` flag.
Set `chunk_chars` and `summary_synthesis_chars` in `[formatting]` in TOML.
There is no `--chunk-chars` or `--summary-synthesis-chars` flag.
Larger source chunks need enough model context, output capacity, and time for the complete response.
The 200,000-character maximum does not increase token allowances, byte limits, or deadlines.
`--no-config` still uses the 12,000-character built-in default.

`--language` selects one caption language for one run.
`captions.language` sets the default for the CLI and for MCP.
The wrapper always prefers a native track.
If only a YouTube-provided translated track exists, the wrapper uses that track.
The wrapper then reports the translation in verbose output, in file metadata, and in JSON.
If a region or script tag has no track, the wrapper falls back to the primary subtag only.
Therefore, `--language en-US` accepts `en` and never accepts `en-GB`.
The wrapper never translates locally.
See the [caption selection contract](behavior.md#caption-selection-and-cleanup).

After the wrapper checks the schema, raw modes ignore saved formatting preferences.
An explicit model, chunk cap, or editorial-mode flag conflicts with raw output.
`--editorial-mode` overrides TOML.
The mutually exclusive `--sponsorblock` / `--no-sponsorblock` flags also override TOML.
The mutually exclusive `--cache` / `--no-cache` flags override `cache.enabled` for one run.
The existing CLI structure and defaults remain unchanged.

Without an explicit model in TOML or CLI, every Pi call omits `--model`.
Pi selects its configured default.
The wrapper never selects a fallback model.

Help and version ignore wrapper TOML.
Doctor loads the selected TOML without network requests.
A malformed configuration still blocks raw mode unless you supply `--no-config`.

## Providers

Pi is the default Markdown backend. OpenRouter and DeepSeek are direct API alternatives.
See the [provider guide](providers.md) for setup, API keys, token limits, privacy, and request behavior.

### Thinking policy

Configure thinking in TOML, not through CLI flags.
Summarized mode requests medium thinking unless you explicitly disable it.
See the [thinking policy](providers.md#thinking-policy) for the full settings and provider mappings.

## Editorial modes

`standard` produces an edited transcript and is the default.
`focused` produces an edited transcript that excludes separable non-substantive material.
`summarized` produces one whole-video summary, not an edited transcript.

```sh
uv run yt-transcript URL --no-config --editorial-mode summarized --preview
uv run yt-transcript URL --no-config --editorial-mode summarized --max-chunks 20 -o summary.md
```

The summary prompt requests 400–700 words for substantial videos and fewer words for short sources.
It requests `## Summary`, `## Key points`, and an optional `## Conclusions and caveats` section.
Python checks these headings and requires nonempty section bodies.
The length target and factual quality are not guaranteed.
The prompt prioritizes the main ideas, important results, and source qualifications.
It treats captions, chapter titles, and intermediate notes as untrusted data.
Video descriptions are not model input.
The summary body does not retain canonical chapter headings.
Source chapter metadata stays unchanged.

One input chunk needs one summary call.
Multiple input chunks need one factual-note call per chunk and one final synthesis call.
The tool publishes only the final summary.
The tool does not return intermediate notes.
`--max-chunks` counts all these calls.
For example, three input chunks require a cap of at least four.
Notes are strict private claims objects with source IDs from the same call and qualification arrays.
Per-chunk budgets include schema framing, ID framing, and JSON escaping.
After minimum claim framing, at least 256 usable serialized characters must remain.
Source chunks must fit `formatting.chunk_chars`.
The complete final notes envelope must fit the independent `formatting.summary_synthesis_chars` limit.
The notes prompt requests compact JSON and aims for 75% of each allocated hard response limit.
The hard limit still applies to the raw response and the compact serialized claims.
If the notes budget is insufficient, processing fails with `PI_CONTEXT_LIMIT`, `OPENROUTER_CONTEXT_LIMIT`, or `DEEPSEEK_CONTEXT_LIMIT` before model calls.
Oversized or invalid notes cause failure without truncation, a repair call, or a partial summary.
If all evidence is empty, processing fails before synthesis.
The formatter rejects final output that contains canonical internal IDs.
Valid references do not prove that facts have support or that caveats are complete.
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
The flag is invalid with raw output, summarized mode, doctor, or MCP launch, even when set to zero.
There is no TOML key or public MCP argument for context.
MCP retains zero context.

Read-only windows contain adjacent retained caption words, not earlier model output.
Only the current payload owns output.
Do not copy context into the document.
Before splitting, planning reserves space for JSON framing and worst-case escapes.
Planning then reports actual serialized sizes and call counts.
This planning process can increase calls or cause a planning-limit error.
Context windows contain only whole words that fit their character limit.
If an adjacent word does not fit, the tool omits it from that context window instead of truncating it.
Current text is not omitted this way.
If a current word cannot fit the source budget that remains after planning reserves context and framing, planning fails instead of truncating the word.
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

Preview also reports the requested thinking state/level and the DeepSeek medium-to-high mapping when applicable.
It does not verify that a model honors the request.

Preview requires Markdown mode and no output path.
If the plan exceeds the cap, preview still returns a successful report.
Actual formatting rejects a plan that exceeds the cap before any model call.

Preview is not a reservation.
A later run reuses the shared source-caption snapshot if the video, the language, and the resolved SponsorBlock policy match.
If no valid snapshot remains, a later run downloads the captions again.
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
This can cause charges for one call per source chunk, plus Pi/provider-internal retries.
Multi-chunk summarized output can cause charges for one additional synthesis call.

A repeated run can cause new charges.
A timeout or cancellation cannot undo provider work or billing.
The wrapper does not retry model calls.

Model-processing failures print a warning on stderr.
The warning suggests `--raw` for plain text without an AI model.
The wrapper does not write a partial processed document or an automatic fallback.
MCP uses `output_format="plain_text"` for the same explicit recovery.
The total MCP Markdown deadline is separate from CLI per-chunk timeouts.

`--no-session` prevents local Pi session persistence.
This flag does not prevent provider-side logging or retention.

## JSON output

```sh
yt-transcript --doctor --json
yt-transcript URL --no-config --preview --json
yt-transcript URL --no-config --raw --json
```

`--json` writes one JSON document to each stream.
Every document includes `schema_version` (currently `1`) and `command`.
Stdout receives the result document.
Stderr receives one error document, or no output.
The wrapper disables progress and all other stderr text.
Both streams therefore stay parseable.
A SponsorBlock warning goes in the document, not to stderr.
Exit codes do not change.
Do not use `--json` with `--raw-vtt` or with `--mcp`.

| Command | Document |
|---|---|
| `--doctor` | `healthy`, `checks` with `name`, `status`, and `detail`, and a readiness `note` |
| `--preview` | The canonical URL, the caption language and provenance, the cache state, the SponsorBlock state, character counts, the plan, and the selected provider, model, editorial mode, and thinking state |
| `--raw` | The metadata fields below, `body`, `character_count`, and `cues` with original times |
| Markdown mode | The same metadata fields and `body`; no `cues` |
| Any failure | `error` with `code`, `phase`, `retryable`, chunk position, `message`, `hint`, and `diagnostic` only with `--verbose` |

Doctor and preview output never contains caption text or descriptions.
Transcript output contains the description only with `-o`. This rule matches the file metadata rule.
With `-o`, the file contains the JSON document. It does not contain the YAML header and body.
The preview document omits the source chunks of the plan.

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
By default, the tool atomically replaces the destination after success.
Failures before output leave existing files unchanged.

`--no-clobber` requires `-o`.
Before extraction, this flag rejects existing entries, including broken symlinks.
Atomic hard-link publication also rejects a destination created during processing.

Filesystems without usable hard links fail closed.
There is no replacement fallback.
A cleanup failure after publication produces a warning.
The tool does not report the cleanup failure as a publication failure.

The output parent directory must exist.
Stdout is not transactional.
A failed stdout write can leave partial bytes in a pipe.
