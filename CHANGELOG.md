# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.6...HEAD
[0.2.0-dev.6]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.5...v0.2.0-dev.6
[0.2.0-dev.5]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.4...v0.2.0-dev.5
[0.2.0-dev.4]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.3...v0.2.0-dev.4
[0.2.0-dev.3]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.2...v0.2.0-dev.3
[0.2.0-dev.2]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.1...v0.2.0-dev.2
[0.2.0-dev.1]: https://github.com/nmdra/yt-transcript/releases/tag/v0.2.0-dev.1
