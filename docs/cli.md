# CLI reference

[README](../README.md) · [Installation](installation.md) · [Troubleshooting](troubleshooting.md)

These commands use the installed executable.
In a development checkout, use `uv run yt-transcript` instead.

## Output modes

```sh
yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config
yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --raw
yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --raw-vtt -o captions.vtt
yt-transcript 'https://youtu.be/YE7VzlLtp-4' --no-config --model provider/model-id -o transcript.md
```

| Mode | Body | Pi | File metadata |
|---|---|---|---|
| Default | Edited Markdown | Yes | YAML with `-o` |
| `--raw` | One normalized paragraph | No | YAML with `-o` |
| `--raw-vtt` | Unchanged VTT bytes | No | None |

Stdout contains only the transcript body.
File output leaves stdout empty.
All non-VTT bodies end with one newline.

Terminal stderr shows a spinner during caption retrieval/filtering.
Then stderr shows a bar with completed Pi calls and elapsed time.
Summarized mode includes the final synthesis call in this count.
Progress does not estimate download bytes, tokens, cost, or completion time.
Progress is disabled for redirected stderr, `TERM=dumb`, help/version, doctor, and MCP.
Progress never appears in transcripts or files.

Use `-o` for Python-generated YAML metadata.
Raw and Markdown file headers include the nullable video `description`.
See [Metadata files](behavior.md#metadata-files) for the field contract.
Descriptions stay out of stdout bodies, Pi input, preview, and raw VTT.
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

The wrapper applies settings in this order of priority: explicit CLI flags, the selected TOML file, then built-in defaults.

```toml
[output]
mode = "markdown"       # "markdown", "raw", or "raw-vtt"
verbose = false

[pi]
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
| `pi.model` | Nonempty selector string, or omit the key |
| `pi.chunk_chars` | Integer 1,000 through 50,000 |
| `pi.timeout_seconds` | Integer 1 through 3,600, per Pi call |
| `pi.max_chunks` | Integer 1 through 1,000, or omit for unlimited; includes summary synthesis |
| `pi.editorial_mode` | `standard` (default), `focused`, or `summarized` |
| `mcp.markdown_timeout_seconds` | Integer 300 through 3,600; total MCP Markdown deadline, default 300; ignored by CLI |
| `sponsorblock.enabled` | Optional boolean; unset means CLI off, MCP filtered on |
| `sponsorblock.categories` | Nonempty unique list: `sponsor`, `selfpromo`, `interaction`, `intro`, `outro`, `preview` |
| `sponsorblock.timeout_seconds` | Integer 1 through 30, per socket operation |

`--raw`, `--raw-vtt`, `--model`, `--max-chunks`, and `-v` override their corresponding defaults.
There is no `--markdown` or `--quiet` flag.

Raw modes ignore saved Pi preferences after schema checks.
An explicit model, chunk cap, or editorial-mode flag conflicts with raw output.
`--editorial-mode` overrides TOML.
The mutually exclusive `--sponsorblock` / `--no-sponsorblock` flags also override TOML.
The existing CLI structure and defaults remain unchanged.

Without an explicit model in TOML or CLI, every Pi call omits `--model`.
Pi selects its configured default.
The wrapper never selects a fallback model.

Help, version, and doctor ignore wrapper TOML.
A malformed configuration still blocks raw mode unless you supply `--no-config`.

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
Notes have per-chunk budgets that include JSON escaping.
The final synthesis input must fit `pi.chunk_chars`.
An infeasible note budget fails with `PI_CONTEXT_LIMIT` before model calls.
Oversized or invalid notes fail without truncation, a repair call, or a partial summary.
Small chunks can create too many notes for one bounded synthesis input.
Use preview to check the plan; a larger cap alone does not solve this input limit.

All modes keep the existing isolation, per-call timeout, metadata, and atomic file-output rules.
Raw modes and MCP plain text do not summarize.

## Preview and cost controls

```sh
yt-transcript URL --no-config --preview
yt-transcript URL --no-config --max-chunks 10 -o transcript.md
```

Preview downloads and cleans captions.
Preview never calls Pi.
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
11. Model selection
12. Editorial mode

Preview requires Markdown mode and no output path.
If the plan exceeds the cap, preview still returns a successful report.
Actual formatting rejects a plan that exceeds the cap before any Pi call.

Preview is not a cache or a reservation.
A later run downloads captions again.
Invocation counts are not token counts, dollar estimates, or exact provider-request counts.

The formatter splits text on sentence boundaries or whitespace.
The formatter does not split tokens or overlap chunks.
The formatter sends chunks sequentially through independent in-memory Pi sessions.

Standard and focused modes join completed bodies without a final synthesis call.
They do not summarize or remove duplicates across the complete Markdown document.
They do not send earlier generated chunks to Pi.
Summarized mode uses bounded notes and a final synthesis call when there is more than one source chunk.
Preview includes that call; its exact input length depends on generated notes.

If a single token is larger than the chunk limit, formatting fails.
The formatter does not truncate the token.
Character limits do not guarantee a compatible context window or output limit.

**Default Markdown sends caption text to the configured model/provider.**
This can incur one paid call per source chunk, plus Pi/provider-internal retries.
Multi-chunk summarized output can incur one additional paid synthesis call.

A repeated run can incur new charges.
A timeout or cancellation cannot undo provider work or billing.
The wrapper does not retry model calls.

Pi-processing failures print a warning on stderr.
The warning suggests `--raw` for plain text without Pi.
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

Doctor is local and ignores wrapper TOML.
Doctor reports Python, package versions, EJS compatibility, Deno, and Pi readiness.

Version commands use isolated directories and five-second deadlines.
Doctor does not run a model or access YouTube, credentials, or authentication commands.

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
