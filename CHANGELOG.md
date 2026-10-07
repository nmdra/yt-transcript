# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.3...HEAD
[0.2.0-dev.3]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.2...v0.2.0-dev.3
[0.2.0-dev.2]: https://github.com/nmdra/yt-transcript/compare/v0.2.0-dev.1...v0.2.0-dev.2
[0.2.0-dev.1]: https://github.com/nmdra/yt-transcript/releases/tag/v0.2.0-dev.1
