# Transcript behavior

[README](../README.md) · [CLI reference](cli.md) · [MCP setup](mcp.md)

## Pi isolation and completeness

Pi receives cleaned text through stdin. With chapter or SponsorBlock boundary context, stdin contains JSON with relevant titles, times, annotations, and retained text. Text occurs once in each plan, and the complete serialized input counts toward the chunk limit. Context overhead can increase calls. Pi receives neither YAML nor the upstream metadata dictionary.

The wrapper replaces the coding prompt with editorial instructions. It supplies a fixed append prompt and disables tools, extensions, MCP, skills, templates, themes, and context files.

Pi runs in an empty temporary directory. User credentials, compatible endpoints, and default model configuration remain available. Custom provider extensions are not supported.

This isolation is not an operating-system sandbox or a prompt-injection guarantee. Returned captions and generated Markdown remain untrusted data.

The wrapper reads bounded JSONL events internally. Success requires process exit 0, `agent_settled`, and a final authoritative assistant message with `stopReason='stop'`.

Length stops, aborts, compaction, tool calls, missing completion, invalid JSON, and oversized output fail before publication. Events, thinking, and raw stderr never enter documents or diagnostics.

A normal stop does not prove factual accuracy or semantic completeness. Offline structural tests do not prove faithful actual LLM edits.


## Chapters, focused editing, and SponsorBlock

Valid supplied chapters become canonical `## [time] title` Markdown headings. Cue-start alignment preserves caption order, crossings, gaps, and backward revisits. Python validates headings outside correctly closed code fences before removing duplicate continuation headings. Invalid output fails without a repair call or silent fallback.

```sh
yt-transcript URL --no-config --editorial-mode focused --preview
yt-transcript URL --no-config --editorial-mode focused --max-chunks 3 -o focused.md
yt-transcript URL --no-config --sponsorblock --preview
```

Standard remains the CLI default. Focused is selective editing, not summarization. It removes separable greetings, ads, interaction requests, housekeeping, and unrelated tangents. It keeps substantive examples, technical product explanations, code, URLs, numbers, qualifications, relevant affiliation/disclosures, and ambiguous content. Every retained source chunk still goes to Pi. Fully omitted chunks do not save planned calls. If all output is omitted, publication fails; use standard or raw. Source chapter metadata remains complete even when focused editing omits a body section. Fake-process tests do not establish actual model fidelity.

SponsorBlock is opt-in on CLI and attempted by default for MCP filtered mode. The fixed official HTTPS lookup sends only a four-character SHA-256 prefix of the video ID, then matches the actual ID locally. Prefix lookup is not an anonymity guarantee. No cookies, credentials, redirects, full-ID fallback, submissions, votes, view reports, or persistent cache are used. One lookup attempt is made; socket timeout is not a total deadline.

Filtering happens after global rolling cleanup. Remove only complete nonzero cues contained in the selected interval union. Keep crossing/zero-duration cues; do not guess word timing or rerun cleanup. Duration must be verified within one second. If removal would empty the transcript, keep it and warn. Community labels cannot guarantee correct promotion detection.

Lookup/data failure keeps captions and emits `warning[SPONSORBLOCK_UNAVAILABLE]`. MCP puts the warning in metadata; CLI also uses stderr. Intentional disablement and no returned segments need no failure warning. Focused editing can independently remove non-substantive text after deterministic fallback.

`--raw --sponsorblock` can query metadata but never removes words. Its receipt says `not_applied`. Raw VTT always skips lookup and rejects explicit `--sponsorblock`.

Metadata records lookup status separately from actual removal. Segment receipts use `removed`, `partial`, `kept`, `no_matching_captions`, or `not_applied`, with removed/retained-overlap cue counts. Aggregate counts use unique fragments rather than sums across overlapping segments. `removed` refers to matching caption fragments, not every spoken promotional word. Pi receipts describe source filtering before the model, not later model deletions. Raw and filtered headers can differ in receipt fields; equality requires identical source snapshots and receipts.

**API/data license:** SponsorBlock community records are [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) unless separate permission is granted. Published records include source attribution, license URL, and a notice of selection/time normalization. Attribution, noncommercial, and share-alike terms are separate from the MIT code license. Review [upstream terms](https://github.com/ajayyy/SponsorBlock/wiki/Database-and-API-License) before deployment, especially commercial use.


## Metadata files

Default and raw `-o` files share this fixed schema:

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
chapter_status: "unavailable"
chapters: []
sponsorblock:
  enabled: false
  status: "disabled"
  categories: ["sponsor", "selfpromo", "interaction"]
  segments: []
  warning: null
  reason_code: null
  source: null
  license_url: null
  changes: null
  removal_applied: false
  removal_stage: "none"
  removed_cue_count: 0
  retained_overlap_cue_count: 0
---

The transcript starts here.
```

Python serializes every string safely with double quotes. The serializer can also quote mapping keys. All thirteen top-level fields are always present; the original ten remain the prefix.

The canonical URL excludes playlist and tracking parameters. The video ID must match the single extracted video.

The channel falls back to the uploader name. The channel URL falls back to the uploader URL. The channel ID never falls back to a handle.

The upload date uses UTC. A valid timestamp supplies an absent date. An explicitly malformed date becomes `null` rather than a guessed date.

Duration preserves zero and fractional seconds. Missing or invalid optional values become `null`. Caption language retains the selected key exactly.

Caption source is `manual` or `automatic`. These fields do not prove that the text is untranslated original English.

`chapter_status` is `available`, `unavailable`, or `invalid`. Each chapter has `title`, `start_seconds`, and nullable `end_seconds`. Chapters come from the supplied extractor list captured before yt-dlp processing. No second extraction, generated topics, or synthetic untitled chapters are used. Origin is not labelled creator-authored or automatic. Malformed optional chapters preserve captions without chapter labels.

Metadata comes from the same processed extraction as the captions. Python adds the header exactly once, after all formatting succeeds. Pi cannot replace it.

Descriptions, signed subtitle URLs, cookies, tokens, view/like counts, and extraction timestamps are excluded. Only caption-removal counts are added. Raw VTT receives no header or byte changes.


## Caption selection and cleanup

The wrapper chooses one track with VTT formats, in this order:

1. Manual `en`
2. Other manual `en-` keys, in lexical order
3. Automatic `en-orig`, then other English `-orig` keys
4. Automatic `en`
5. Other automatic `en-` keys, in lexical order

Matching ignores case but preserves the original key. YouTube-provided translated English is a fallback. The wrapper does not translate locally or infer translation provenance.

The wrapper downloads captions only into a temporary directory. It performs one metadata extraction and does not silently switch tracks after a download error.

The supported VTT parser retains caption text, Unicode, punctuation, and descriptions such as `[Music]`. It skips metadata blocks and strips supported VTT tags before entity decoding.

Manual captions preserve repetition. Automatic cleanup removes exact suffix/prefix overlaps only within consecutive rolling cues, with at most a 100 ms gap.

Larger gaps and backward times reset the overlap comparison. Case and punctuation differences remain distinct. Intentional repetition inside a cue remains intact.

This heuristic does not guarantee perfect speech reconstruction. Malformed or empty cleaned captions fail. Raw VTT remains an explicit diagnostic path.

Active livestreams fail with `active livestreams are not supported`. Upcoming videos fail with `video has not started`.

Post-live videos fail with `livestream processing is incomplete; try again later`. Completed streams and unknown states are accepted without a completeness promise.

The fixed upstream network policy uses a 30-second socket timeout, three HTTP retries, and three extractor retries. Retry delays are 1, 2, then 4 seconds.

There is no whole-workflow retry. These limits are not total request or time budgets. Authentication and unavailable-video errors are not guaranteed retryable.

YouTube can block extraction or require PO tokens. Full runtime setup does not guarantee access. The wrapper provides no cookies, bypass flags, or token provisioning.
