# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add `--language` and `[captions].language` for caption language selection, with native tracks ranked above translated tracks and a primary-subtag fallback that never selects a different variant
- Add `caption_translated` to file metadata and to the MCP metadata result, so the wrapper reports every translated track
- Add `--json` for `--doctor`, `--preview`, `--raw`, Markdown mode, and errors, with one versioned document per stream
- Share the source-caption cache between the CLI and MCP, including `--cache` and `--no-cache` overrides

### Changed

- Raise the maximum `formatting.chunk_chars` from 50,000 to 200,000 for CLI and MCP; keep the 12,000-character default, token allowances, byte limits, and deadlines unchanged
- Publish package classifiers and project URLs, and state Python 3.14.7 or newer in the README
- Use the cache for CLI transcripts by default; `[cache].enabled` defaults to true for CLI and MCP
- Replace the English-only caption error codes with `NO_CAPTIONS` and `NO_VTT`; keep `NO_ENGLISH_CAPTIONS` and `NO_ENGLISH_VTT` recognized but unused
- Bump the source-caption cache payload version, so the wrapper does not reuse earlier snapshots

### Fixed

- Prevent chapter heading-copy failures by validating structured run bodies and inserting canonical headings in Python, without retries, repair, or partial publication
- Report fixed output validation reasons through CLI and MCP errors without exposing model text, and reject malformed Pi completion Unicode safely

## [1.1.0] - 2026-10-12

### Added

- Add direct DeepSeek Markdown formatting with an explicit model, environment-only API key, bounded supervised HTTP, and no automatic retry or fallback
- Add shared `formatting.thinking` and scalar `formatting.thinking_level` controls for Pi, OpenRouter, and DeepSeek without new CLI flags or public MCP arguments
- Add bounded `formatting.summary_synthesis_chars` for multi-chunk summary input, independent of source chunk size
- Add server-controlled `cache.path` for the SQLite database while preserving the existing default location

### Changed

- Automatically request medium thinking for each summarized Markdown stage unless explicitly disabled; map DeepSeek medium to high and preserve standard/focused Pi/OpenRouter defaults when omitted
- Report requested thinking policy in offline preview without promising provider capability or improved summary fidelity
- Allocate summary notes against the separate synthesis budget and request compact JSON with a conservative response target, without retries or truncation
- Show the selected Pi, OpenRouter, or DeepSeek backend in CLI model-call progress labels

### Fixed

- Identify summary validation stages and reasons with safe character counts instead of reporting invalid JSON notes as a Markdown failure

## [1.0.0] - 2026-10-12

### Added

- First stable release of the CLI and MCP interfaces, including Pi and OpenRouter Markdown backends
- Shared private SQLite source-caption cache for MCP, with bounded retention and unchanged CLI behavior
- Model-free MCP metadata, timestamp segment, literal search, and snapshot-bound paging tools while keeping `get_transcript` as the primary tool
- Optional Markdown model-call progress notifications without new tool arguments, background tasks, or changed deadlines

### Changed

- Clarify source-cache reuse, duration alignment, caption availability, and read-only chunk context in the guides using Simplified Technical English principles

## [0.2.0-dev.9] - 2026-10-12

### Changed

- Allow conservative ordinary-word spelling correction in Pi and OpenRouter Markdown prompts; preserve uncertain words, names, technical terms, protected literals, and source meaning without extra calls
- Raise the default OpenRouter output allowance from 8192 to 16384 tokens per model call; reasoning tokens can consume the allowance, and model-specific limits still apply

## [0.2.0-dev.8] - 2026-10-12

### Added

- Direct OpenRouter formatting for CLI and MCP Markdown without Pi, with an explicit model, environment-only API key, bounded responses, and supervised deadlines
- Provider-aware offline doctor checks and preview output
- Internal source-span IDs and strict bounded summary claims with same-call references, qualification arrays, all-empty-evidence rejection, and no public citations
- Opt-in CLI/Python read-only chunk context with whole-token windows and complete serialized budget accounting
- Synthetic offline fidelity fixtures, advisory comparison, and atomic saved-response evaluation reports; no live quality claim
- Opt-in `summarized` editorial mode for whole-video Markdown summaries, with bounded factual notes, a final synthesis call for multi-chunk input, and preview/cap/progress accounting for all model calls

### Changed

- **Breaking:** Replace the `[pi]` TOML table with `[formatting]`; add provider selection and a separate `[openrouter]` output-token setting

## [0.2.0-dev.7] - 2026-10-08

### Added

- Nullable video `description` in CLI YAML headers and MCP metadata, including compatibility JSON; keep extractor text unchanged and separate from transcript bodies and Pi input

## [0.2.0-dev.6] - 2026-10-07

### Changed

- Publish normal public GitHub releases after CI checks and checksum verification, without a private-repository guard or manual exception
- Rewrite the README and guides using Simplified Technical English principles, with technical requirements, commands, and limits unchanged
- Simplify caption processing and MCP internals without changing public APIs, output, filtering, or process cleanup

## [0.2.0-dev.5] - 2026-10-07

### Added

- Server-only `mcp.markdown_timeout_seconds` setting for a bounded total Markdown deadline from 300 through 3600 seconds, retaining the 300-second default
- CLI and MCP recovery warnings suggest raw/plain-text requests when Pi processing fails, without automatic fallback or retry

### Changed

- **Breaking:** MCP `document` contains only the transcript body; metadata remains in `metadata`, and CLI file output retains YAML frontmatter
- Distinguish forbidden Pi context changes as `PI_CONTEXT_MUTATED` from provider or planning limits as `PI_CONTEXT_LIMIT`

### Fixed

- Include validated chunk positions in MCP formatting errors and explain total worker timeout recovery

## [0.2.0-dev.4] - 2026-10-07

### Changed

- Raise the default MCP Markdown chunk cap from 3 to 20; explicit Markdown requests can make up to 20 sequential Pi calls

## [0.2.0-dev.3] - 2026-10-07

### Changed

- Make the installation prompt client-neutral with links to official MCP client setup guides

### Fixed

- Keep CLI transcription working when the optional progress thread cannot start
- Preserve safe MCP Markdown error explanations, hints, and validated chunk-limit counts
- Clip terminal progress padding and cleanup after a window resize

## [0.2.0-dev.2] - 2026-10-07

### Added

- Automatic terminal-only CLI progress with a fetch spinner, completed Pi chunk bar, and elapsed time on stderr
- Explicit MCP `output_format="markdown"` for bounded Pi editing; plain text remains the no-model default
- POSIX worker-group supervision for MCP Pi calls, with safe cancellation and no silent formatting fallback

## [0.2.0-dev.1] - 2026-10-07

### Added

- Supplied YouTube chapter metadata and cue-level chapter context for Markdown and MCP
- Inline original-video timestamp blocks for MCP captions without chapters
- Opt-in focused Pi editing with conservative keep/remove rules and validated omissions
- Bounded read-only SponsorBlock lookup, complete-cue filtering, visible fallback, and actual removal receipts
- Optional MCP full mode that skips SponsorBlock
- Private GitHub releases with wheel/source archives and SHA-256 checksums after offline acceptance checks

### Changed

- **Breaking:** MCP now exposes only `get_transcript`; `preview_transcript` and `doctor` are removed
- **Breaking:** MCP defaults to filtered captions with full-caption fallback when SponsorBlock cannot be used
- Metadata adds chapters and SponsorBlock receipts; raw versus filtered headers may differ
- Preview and formatting share the same complete contextual stdin plan; CLI defaults and existing flags stay unchanged

### Fixed

- Parse YouTube VTT captions with space-only payload lines instead of rejecting valid transcripts

[Unreleased]: https://github.com/nmdra/yt-transcript/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/nmdra/yt-transcript/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.9...v1.0.0
[0.2.0-dev.9]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.8...v0.2.0-dev.9
[0.2.0-dev.8]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.7...v0.2.0-dev.8
[0.2.0-dev.7]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.6...v0.2.0-dev.7
[0.2.0-dev.6]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.5...v0.2.0-dev.6
[0.2.0-dev.5]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.4...v0.2.0-dev.5
[0.2.0-dev.4]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.3...v0.2.0-dev.4
[0.2.0-dev.3]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.2...v0.2.0-dev.3
[0.2.0-dev.2]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.1...v0.2.0-dev.2
[0.2.0-dev.1]: https://github.com/nmdra/yt-transcript/releases/tag/v0.2.0-dev.1
