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
Progress is disabled for redirected stderr, `TERM=dumb`, help/version, doctor, and MCP.
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

Watch, shorts, and embed URLs are supported.
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
| `formatting.provider` | `pi` (default) or `openrouter` |
| `openrouter.max_output_tokens` | Integer 1 through 131072; default 16384 |
| `formatting.model` | Nonempty selector string, or omit the key |
| `formatting.chunk_chars` | Integer 1,000 through 50,000 |
| `formatting.timeout_seconds` | Integer 1 through 3,600, per model call |
| `formatting.max_chunks` | Integer 1 through 1,000, or omit for unlimited; includes summary synthesis |
| `formatting.editorial_mode` | `standard` (default), `focused`, or `summarized` |
| `mcp.markdown_timeout_seconds` | Integer 300 through 3,600; total MCP Markdown deadline, default 300; ignored by CLI |
| `sponsorblock.enabled` | Optional boolean; unset means CLI off, MCP filtered on |
| `sponsorblock.categories` | Nonempty unique list: `sponsor`, `selfpromo`, `interaction`, `intro`, `outro`, `preview` |
| `sponsorblock.timeout_seconds` | Integer 1 through 30, per socket operation |

`--raw`, `--raw-vtt`, `--model`, `--max-chunks`, and `-v` override their corresponding defaults.
There is no `--markdown` or `--quiet` flag.

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
The old table is rejected rather than merged.
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
Only the final summary is published; intermediate notes are not returned.
`--max-chunks` counts all these calls.
For example, three input chunks require a cap of at least four.
Notes are strict private claims objects with source IDs from the same call and qualification arrays.
Per-chunk budgets include schema and ID framing and JSON escaping.
After minimum claim framing, at least 256 usable serialized characters must remain.
The final synthesis input must fit `formatting.chunk_chars`.
An infeasible note budget fails with `PI_CONTEXT_LIMIT` or `OPENROUTER_CONTEXT_LIMIT` before model calls.
Oversized or invalid notes cause failure without truncation, a repair call, or a partial summary.
If all evidence is empty, processing fails before synthesis.
The formatter rejects final output that contains canonical internal IDs.
Valid references do not prove factual support or complete caveats.
Small chunks can create too many notes for one bounded synthesis input.
Use preview to check the plan.
A larger cap alone does not solve this input limit.

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
The tool never truncates the token.
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
8. Configured chunk limit
9. Maximum chunks
10. Cap result
11. Provider
12. Model selection
13. Editorial mode

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
OpenRouter uses independent HTTP completions.

Standard and focused modes join completed bodies without a final synthesis call.
They do not summarize or remove duplicates across the complete Markdown document.
They do not send earlier generated chunks to Pi.
Summarized mode uses bounded notes and a final synthesis call when there is more than one source chunk.
Preview includes that call.
The call's exact input length depends on the generated notes.

If a single token is larger than the chunk limit, formatting fails.
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
For OpenRouter, doctor checks that an API key and model are present.
Doctor does not check OpenRouter authentication.

Version commands use isolated directories and five-second deadlines.
Doctor does not run a model, access YouTube, or run authentication commands.
Doctor checks that the OpenRouter key is present without displaying the key.

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
