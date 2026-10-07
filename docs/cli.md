# CLI reference

[README](../README.md) · [Installation](installation.md) · [Troubleshooting](troubleshooting.md)

These commands use the installed executable. In a development checkout, use
`uv run yt-transcript` instead.

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

Stdout contains only the body. File output leaves stdout empty. All non-VTT bodies end with one newline.

Use `-o` for Python-generated YAML metadata. Shell redirection receives the body only:

```sh
yt-transcript URL --no-config --raw > body.txt
yt-transcript URL --no-config --raw -o transcript.txt
yt-transcript URL --no-config --raw | wc -w
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
editorial_mode = "standard"  # "standard" or "focused"
# max_chunks = 20
# Omit model to use Pi's configured default.
# model = "provider/model-id"

[sponsorblock]
# Omit enabled: CLI off, MCP filtered on. Explicit false disables both.
# enabled = false
categories = ["sponsor", "selfpromo", "interaction"]
timeout_seconds = 10
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
| `pi.editorial_mode` | `standard` (default) or `focused` |
| `sponsorblock.enabled` | Optional boolean; unset means CLI off, MCP filtered on |
| `sponsorblock.categories` | Nonempty unique list: `sponsor`, `selfpromo`, `interaction`, `intro`, `outro`, `preview` |
| `sponsorblock.timeout_seconds` | Integer 1 through 30, per socket operation |

`--raw`, `--raw-vtt`, `--model`, `--max-chunks`, and `-v` override their corresponding defaults. There is no `--markdown` or `--quiet` flag.

Raw modes ignore saved Pi preferences after schema checks. An explicit model, chunk cap, or editorial-mode flag conflicts with raw output. `--editorial-mode` and the mutually exclusive `--sponsorblock` / `--no-sponsorblock` flags override TOML. The existing CLI shape and defaults remain unchanged.

Without an explicit model in TOML or CLI, every Pi call omits `--model`. Pi chooses its configured default. The wrapper never selects a fallback model.

Help, version, and doctor ignore wrapper TOML. A malformed configuration still blocks raw mode unless `--no-config` is supplied.


## Preview and cost controls

```sh
yt-transcript URL --no-config --preview
yt-transcript URL --no-config --max-chunks 10 -o transcript.md
```

Preview downloads and cleans captions, but never calls Pi. It shows these fields in a fixed order:

1. Canonical URL
2. Full cleaned character count
3. Retained input character count
4. SponsorBlock status
5. Removed cue count
6. Planned formatter invocations
7. Largest serialized stdin chunk size
8. Configured chunk limit
9. Maximum chunks
10. Cap result
11. Model selection
12. Editorial mode

Preview requires Markdown mode and no output path. A cap exceedance is a successful preview report. Actual formatting rejects the cap before any Pi call.

Preview is not a cache or a reservation. A later run downloads again. Invocation counts are not token counts, dollar estimates, or exact provider-request counts.

The formatter splits on sentence boundaries or whitespace without token splits or overlap. It sends chunks sequentially through independent in-memory Pi sessions.

The formatter joins completed bodies without a final synthesis call. It does not summarize, globally deduplicate Markdown, or pass earlier generated chunks to Pi.

A single token larger than the chunk limit fails rather than truncates. Character limits do not guarantee a compatible context window or output limit.

**Default Markdown sends caption text to the configured model/provider.** It can incur one paid call per chunk, plus Pi/provider-internal retries.

A repeated run can incur new charges. A timeout or cancellation cannot undo provider work or billing. No wrapper-level model retries occur.

`--no-session` prevents local Pi session persistence. It does not prevent provider-side logging or retention.


## Doctor and file safety

```sh
yt-transcript --doctor
yt-transcript URL --no-config --raw -o transcript.txt --no-clobber
```

Doctor is local and ignores wrapper TOML. It reports Python, package versions, EJS compatibility, Deno, and Pi readiness.

Version commands use isolated directories and five-second deadlines. Doctor does not run a model or access YouTube, credentials, or authentication commands.

A healthy report establishes local readiness only. It does not establish video access, provider authentication, caption completeness, or model accuracy.

File output uses a completed sibling temporary file. Default publication atomically replaces the destination after success. Pre-output failures leave existing files unchanged.

`--no-clobber` requires `-o`. It rejects existing entries, including broken symlinks, before extraction. Atomic hard-link publication also rejects a destination created during processing.

Filesystems without usable hard links fail closed. There is no replacement fallback. A cleanup failure after publication produces a warning, not a false publication failure.

The output parent directory must exist. Stdout is not transactional. A failed stdout write can leave partial bytes in a pipe.
