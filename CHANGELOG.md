# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Supplied YouTube chapter metadata and cue-level chapter context for Markdown and MCP
- Inline original-video timestamp blocks for MCP captions without chapters
- Opt-in focused Pi editing with conservative keep/remove rules and validated omissions
- Bounded read-only SponsorBlock lookup, complete-cue filtering, visible fallback, and actual removal receipts
- Optional MCP full mode that skips SponsorBlock

### Changed

- MCP now exposes only `get_transcript`; removed `preview_transcript` and `doctor` are a breaking client change
- MCP defaults to filtered captions with full-caption fallback when SponsorBlock cannot be used
- Metadata adds chapters and SponsorBlock receipts; raw versus filtered headers may differ
- Preview and formatting share the same complete contextual stdin plan; CLI defaults and existing flags stay unchanged

### Fixed

- Parse YouTube VTT captions with space-only payload lines instead of rejecting valid transcripts

[Unreleased]: https://github.com/nmdra/yt-transcript/compare/e58e57c4f196068224012ea12498eef7e911d443...HEAD
