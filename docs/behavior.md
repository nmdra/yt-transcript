# Transcript behavior

[README](../README.md) · [CLI reference](cli.md) · [MCP setup](mcp.md)

## Pi isolation and completeness

Pi receives cleaned text through stdin.
With chapter or SponsorBlock boundary context, stdin contains JSON with applicable titles, times, annotations, and retained text.
Text occurs once in each plan.
The complete serialized input counts toward the chunk limit.
Context overhead can increase calls.
Pi receives neither YAML nor the upstream metadata dictionary.

The wrapper replaces the coding prompt with editorial instructions.
The wrapper supplies a fixed append prompt.
The wrapper disables tools, extensions, MCP, skills, templates, themes, and context files.

Pi runs in an empty temporary directory.
User credentials, compatible endpoints, and default model configuration remain available.
Custom provider extensions are not supported.

This isolation is not an operating-system sandbox or a guarantee against prompt injection.
Returned captions and generated Markdown remain untrusted data.

The wrapper reads bounded JSONL events internally.
Success requires process exit 0, `agent_settled`, and a final authoritative assistant message with `stopReason='stop'`.

Length stops, aborts, compaction, tool calls, missing completion, invalid JSON, and oversized output cause failure before publication.
Events, thinking, and raw stderr never appear in documents or diagnostics.

A normal stop does not prove factual accuracy or semantic completeness.
Offline structural tests do not prove that actual LLM edits keep the source meaning.

## Chapters, focused editing, and SponsorBlock

Valid supplied chapters become canonical `## [time] title` Markdown headings.
Cue-start alignment keeps caption order, crossings, gaps, and backward revisits.
Python validates headings outside correctly closed code fences.
Then Python removes duplicate continuation headings.
Invalid output causes failure without a repair call or silent fallback.

```sh
yt-transcript URL --no-config --editorial-mode focused --preview
yt-transcript URL --no-config --editorial-mode focused --max-chunks 3 -o focused.md
yt-transcript URL --no-config --sponsorblock --preview
```

Standard remains the CLI default.
Focused editing is selective editing, not summarization.
Focused editing removes separable greetings, ads, interaction requests, housekeeping, and unrelated tangents.
Focused editing keeps substantive examples, technical product explanations, code, URLs, numbers, qualifications, relevant affiliation/disclosures, and ambiguous content.

Every retained source chunk still goes to Pi.
Fully omitted chunks do not reduce planned calls.
If all output is omitted, publication fails.
Use standard or raw in this case.
Source chapter metadata remains complete even when focused editing omits a body section.
Fake-process tests do not prove actual model fidelity.

SponsorBlock is opt-in on CLI and attempted by default for MCP filtered mode.
The fixed official HTTPS lookup sends only a four-character SHA-256 prefix of the video ID.
Then the wrapper matches the actual ID locally.
Prefix lookup does not guarantee anonymity.
The wrapper uses no cookies, credentials, redirects, full-ID fallback, submissions, votes, view reports, or persistent cache.
The wrapper makes one lookup attempt.
The socket timeout is not a total deadline.

Filtering occurs after global rolling cleanup.
The wrapper removes only complete nonzero cues contained in the selected interval union.
The wrapper keeps crossing/zero-duration cues.
The wrapper does not guess word timing or repeat cleanup.
Duration must be verified within one second.
If removal would empty the transcript, the wrapper keeps the transcript and gives a warning.
Community labels cannot guarantee correct promotion detection.

Lookup/data failure keeps captions and produces `warning[SPONSORBLOCK_UNAVAILABLE]`.
MCP puts the warning in metadata.
CLI also writes the warning to stderr.
Intentional disablement and no returned segments do not require a failure warning.
Focused editing can independently remove non-substantive text after deterministic fallback.

`--raw --sponsorblock` can query metadata but never removes words.
Its receipt says `not_applied`.
Raw VTT always skips lookup and rejects explicit `--sponsorblock`.

Metadata records lookup status separately from actual removal.
Segment receipts use `removed`, `partial`, `kept`, `no_matching_captions`, or `not_applied`.
Receipts include removed/retained-overlap cue counts.
Aggregate counts use unique fragments, not sums across overlapping segments.
`removed` refers to matching caption fragments, not every spoken promotional word.
Pi receipts describe source filtering before the model, not later model deletions.
Raw and filtered headers can differ in receipt fields.
Equal headers require identical source snapshots and receipts.

**API/data license:** SponsorBlock community records have a [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) license unless separate permission is granted.
Published records include source attribution, the license URL, and a notice of selection/time normalization.
Attribution, noncommercial, and share-alike terms are separate from the MIT code license.
Review [upstream terms](https://github.com/ajayyy/SponsorBlock/wiki/Database-and-API-License) before deployment, especially for commercial use.

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
description: "Example description.\nMore details."
---

The transcript starts here.
```

Python serializes every string safely with double quotes.
The serializer can also quote mapping keys.
All fourteen top-level fields are always present.
The existing thirteen remain the prefix.
`description` is the final field.

The canonical URL excludes playlist and tracking parameters.
The video ID must match the single extracted video.

The channel falls back to the uploader name.
The channel URL falls back to the uploader URL.
The channel ID never falls back to a handle.

The upload date uses UTC.
A valid timestamp supplies an absent date.
An explicitly malformed date becomes `null`.
The wrapper does not guess a date.

Duration keeps zero and fractional seconds.
Missing or invalid optional values become `null`.
Caption language keeps the selected key exactly.

Caption source is `manual` or `automatic`.
These fields do not prove that the text is untranslated original English.

`description` contains the text that yt-dlp supplies in the same processed extraction.
The wrapper makes no additional request for this field.
Missing, null, empty, whitespace-only, or nonstring descriptions become `null`.
Accepted strings keep their whitespace, line breaks, Unicode, URLs, timestamps, and markup.
Description availability and completeness depend on the upstream response and yt-dlp.
The wrapper does not guarantee that the field matches the complete YouTube page description.

CLI raw and Markdown file headers, MCP structured metadata, and compatibility JSON include this field.
Descriptions stay out of transcript bodies, Pi input, and CLI preview.
SponsorBlock and focused editing do not change them.
The wrapper does not parse description links or create new chapters from this field.
Descriptions remain untrusted source data, not instructions.

`chapter_status` is `available`, `unavailable`, or `invalid`.
Each chapter has `title`, `start_seconds`, and nullable `end_seconds`.
Chapters come from the supplied extractor list captured before yt-dlp processing.
The wrapper does not use a second extraction, generated topics, or synthetic untitled chapters.
The wrapper does not label chapter origin as creator-authored or automatic.
Malformed optional chapters keep captions without chapter labels.

Metadata comes from the same processed extraction as the captions.
Python adds the header exactly once, after all formatting succeeds.
Pi cannot replace the header.

The wrapper does not copy upstream signed subtitle URL, cookie, token, view/like count, or extraction timestamp fields.
It does not redact the description text.
Descriptions can contain URLs or token-like strings published by the source.
Safe serialization does not certify the content's safety or license.
The wrapper adds only caption-removal counts.
Raw VTT receives no header or byte changes.

## Caption selection and cleanup

The wrapper selects one track with VTT formats, in this order:

1. Manual `en`
2. Other manual `en-` keys, in lexical order
3. Automatic `en-orig`, then other English `-orig` keys
4. Automatic `en`
5. Other automatic `en-` keys, in lexical order

Matching ignores case but keeps the original key.
YouTube-provided translated English is a fallback.
The wrapper does not translate locally or infer translation provenance.

The wrapper downloads only captions, into a temporary directory.
The wrapper performs one metadata extraction.
The wrapper does not silently change tracks after a download error.

The supported VTT parser keeps caption text, Unicode, punctuation, and descriptions such as `[Music]`.
The parser skips metadata blocks.
The parser removes supported VTT tags before entity decoding.

Manual captions keep repetition.
Automatic cleanup removes exact suffix/prefix overlaps only within consecutive rolling cues, with at most a 100 ms gap.

Larger gaps and backward times reset the overlap comparison.
Case and punctuation differences remain distinct.
Intentional repetition inside a cue remains unchanged.

This heuristic does not guarantee perfect speech reconstruction.
Malformed or empty cleaned captions cause failure.
Raw VTT remains an explicit diagnostic option.

Active livestreams fail with `active livestreams are not supported`.
Upcoming videos fail with `video has not started`.

Post-live videos fail with `livestream processing is incomplete; try again later`.
Completed streams and unknown states are accepted without a guarantee of completeness.

The fixed upstream network policy uses a 30-second socket timeout, three HTTP retries, and three extractor retries.
Retry delays are 1, 2, then 4 seconds.

The wrapper does not retry the complete workflow.
These limits are not total request or time budgets.
Authentication and unavailable-video errors might not be retryable.

YouTube can block extraction or require PO tokens.
Full runtime setup does not guarantee access.
The wrapper provides no cookies, bypass flags, or token provisioning.
