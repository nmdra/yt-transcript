# Transcript behavior

[README](../README.md) · [CLI reference](cli.md) · [MCP setup](mcp.md)

## Pi isolation and completeness

Pi receives cleaned text through stdin.
With chapter or SponsorBlock boundary context, stdin contains JSON with applicable titles, times, annotations, and retained text.
Text occurs once in each plan.
The complete serialized input counts toward the chunk limit.
Context overhead can increase the number of calls.
Pi receives neither YAML nor the upstream metadata dictionary.

The wrapper replaces the coding prompt with editorial instructions.
The wrapper supplies a fixed append prompt.
The wrapper disables tools, extensions, MCP, skills, templates, themes, and context files.

Pi runs in an empty temporary directory.
User credentials, compatible endpoints, and default model configuration remain available.
Custom provider extensions are not supported.

This isolation is not an operating-system sandbox.
This isolation does not guarantee protection against prompt injection.
Returned captions and generated Markdown remain untrusted data.

The wrapper reads bounded JSONL events internally.
Success requires process exit 0, `agent_settled`, and a final authoritative assistant message with `stopReason='stop'`.

Length stops, aborts, compaction, tool calls, missing completion, invalid JSON, and oversized output cause failure before publication.
Events, thinking, and raw stderr never appear in documents or diagnostics.

A normal stop does not prove factual accuracy or semantic completeness.
Offline structural tests do not prove that actual model edits keep the source meaning.

## Conservative spelling correction

Pi and OpenRouter receive the same spelling rules in all Markdown editorial modes, including summary notes and synthesis.
The model may correct an unambiguous ordinary-word spelling error when the intended word is clear from the captions.
For example, `recieve the message` can become `receive the message`.
The model must keep the source meaning, certainty, and qualifications.

In retained text and included summary details, names, technical terms, numbers, units, URLs, code, commands, and identifiers must remain unchanged, even if they appear misspelled.
Uncertain spellings must remain unchanged.
The model must not replace a correctly spelled word with a different word, resolve homophones, infer missing words, or repair technical claims.
This policy does not correct every speech-recognition error.

These are prompt instructions, not a deterministic spelling checker or a guarantee of model fidelity.
The policy adds no model calls, research, retries, or repair pass.
Raw captions, raw VTT, MCP plain text, metadata, and canonical chapter headings remain unchanged.

## Chapters, focused editing, and SponsorBlock

In standard and focused modes, valid supplied chapters become canonical `## [time] title` Markdown headings.
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

Every retained source chunk still goes to the selected model backend.
Fully omitted chunks do not reduce planned calls.
If all output is omitted, publication fails.
Use standard or raw in this case.
Source chapter metadata remains complete even when focused editing omits a body section.
Fake-process tests do not prove actual model fidelity.

CLI uses SponsorBlock only when enabled.
MCP filtered mode attempts SponsorBlock by default.
The fixed official HTTPS lookup sends only a four-character SHA-256 prefix of the video ID.
Then the wrapper matches the actual ID locally.
Prefix lookup does not guarantee anonymity.
The wrapper uses no cookies, credentials, redirects, full-ID fallback, submissions, votes, view reports, or persistent cache.
The wrapper makes one lookup attempt.
The socket timeout is not a total deadline.

Filtering occurs after global rolling cleanup.
The wrapper removes only complete nonzero cues contained in the selected interval union.
The wrapper keeps crossing cues and zero-duration cues.
The wrapper does not guess word timing or repeat cleanup.
Duration must be verified within one second.
If removal would empty the transcript, the wrapper keeps the transcript and gives a warning.
Community labels cannot guarantee correct promotion detection.

If the lookup or its data fails, the tool keeps captions and produces `warning[SPONSORBLOCK_UNAVAILABLE]`.
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
SponsorBlock receipts describe source filtering before the model, not later model deletions.
Raw and filtered headers can differ in receipt fields.
Equal headers require identical source snapshots and receipts.

**API/data license:** SponsorBlock community records have a [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) license unless separate permission is granted.
Published records include source attribution, the license URL, and a notice of selection/time normalization.
Attribution, noncommercial, and share-alike terms are separate from the MIT code license.
Review [upstream terms](https://github.com/ajayyy/SponsorBlock/wiki/Database-and-API-License) before deployment, especially for commercial use.

## Summarized editing

`--editorial-mode summarized` or `formatting.editorial_mode = "summarized"` selects a whole-video summary for Markdown output.
Standard remains the default.
Raw and MCP plain-text output stay deterministic.
The prompt targets 400–700 words, with shorter output for short sources.
It requests an overview, key points, and supported conclusions or caveats.
Names, numbers, uncertainty, and necessary qualifications must remain accurate when included.
The prompt forbids outside facts and treats all source content and intermediate notes as untrusted data.
These instructions do not guarantee model fidelity or resistance to prompt injection.

A single source chunk goes directly to one summary call.
For multiple chunks, Python plans factual-note calls and one final synthesis call.
The existing invocation cap includes synthesis.
The existing per-call and MCP total deadlines still apply.
Each note has a bounded serialized character budget.
Python rejects impossible budgets before model calls and rejects oversized notes without truncation.
The final synthesis input fits the configured stdin character limit.
Notes use independent backend calls and are passed only to the final synthesis call as validated private evidence objects.
They are never published as transcript output.

Python validates final headings and nonempty bodies.
Python does not prove summary accuracy or enforce the target word count.
Failures publish no partial notes, summary, or automatic fallback.
The final summary uses its own headings rather than canonical chapter headings.
Source chapter metadata, descriptions, and SponsorBlock receipts remain unchanged.
Removal receipts still describe source filtering, not what the summary includes or omits.

## Internal summary evidence and continuity

Python assigns a private ID and one source-call owner to each summary source span.
Timed source origins retain source indices, run order, original cue times, and split-word ranges.
Untimed source origins use normalized-text offsets and null timestamps.
The ID namespace is absent from retained caption text.
Removed captions and descriptions are never added to the registry.
A split cue keeps its original interval; no finer timing is inferred.

Multi-chunk note calls return strict JSON with exactly `claims`.
Each claim has `statement`, unique same-call `source_ids`, and a `qualifications` array.
Limits are 64 claims per call, 16 IDs per claim, and 16 qualifications per claim.
Empty claims are allowed.
If all evidence is empty, processing fails before synthesis.
Duplicate keys, forged/cross-call references, invalid schemas, fences, commentary, and oversized notes fail without repair.
Validated objects, IDs, and qualifications are serialized directly into the final notes envelope, not quoted Markdown strings.

Planning counts source IDs, claim/schema framing, JSON escapes, and chunk indices.
Each note call must have at least 256 serialized characters available after minimum claim framing.
An infeasible synthesis budget fails before model execution.
ID framing can change source partitions and call counts.
One planned source chunk still uses one direct summary call.
N chunks use N note calls plus one synthesis.
No hierarchical synthesis, judging, repair, or retry calls are added.
Final summaries reject canonical private IDs rather than remove them silently.
Only the validated final Markdown is published.
Metadata and public MCP fields remain unchanged.

Reference membership does not establish entailment or truth.
Empty qualification arrays are structurally valid and can omit a needed caveat.
The final synthesis still has a fixed compression budget and sees notes rather than all captions.
Offline annotations and human review remain necessary.
Real-model fidelity has not been verified.

CLI and Python standard or focused formatting can use bounded read-only neighboring captions when enabled.
The default zero keeps their old source payload shapes without private ID fields.
Nonzero context wraps existing current data with `previous_context` and `following_context`.
Only current words own output.
Only current runs determine canonical headings.
Windows use whole tokens, never chapter titles, descriptions, removed captions, or earlier model output.
Worst-case JSON escaping is reserved before deterministic repartitioning.
A neighbor token larger than its window is omitted, not truncated.
Context can increase calls or leave no room for a current token.
A model can still copy context into its output.
Prompts and heading validation do not prove output ownership.
The wrapper does not repair duplication automatically.

`compare_fidelity` and the [offline evaluator](development.md#offline-fidelity-evaluation) report advisory literal/annotation differences.
They never reject a production transcript, launch a model, retry, or publish a sidecar.

## Backend-independent formatting

Both backends use the same source prompts, chapter validation, omission rules, and summary assembly.
Descriptions are never model input.
Pi keeps the isolated subprocess contract above.
OpenRouter uses one bounded nonstreaming HTTPS completion through a supervised Python helper.
It rejects tool calls, redirects, invalid or oversized responses, and non-stop completions.
The wrapper makes no automatic retry or provider switch and publishes no partial result.
HTTP response and completion text bounds are 2 MiB and 1 MiB respectively.
A local deadline cannot cancel provider billing or establish factual accuracy.

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
If a description is missing, null, empty, whitespace-only, or not a string, it becomes `null`.
Accepted strings keep their whitespace, line breaks, Unicode, URLs, timestamps, and markup.
Description availability and completeness depend on the upstream response and yt-dlp.
The wrapper does not guarantee that the field matches the complete YouTube page description.

CLI raw and Markdown file headers, MCP structured metadata, and compatibility JSON include this field.
Descriptions are not included in transcript bodies, model input, or CLI preview.
SponsorBlock and focused editing do not change descriptions.
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

The wrapper does not copy upstream signed subtitle URL, cookie, token, view count, like count, or extraction timestamp fields.
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


## MCP source retrieval and caching

The unreleased development checkout adds deterministic metadata, segment, search, and page tools.
They share source-caption snapshots with MCP `get_transcript`, without calling a model.
Cache rehydration preserves original cues, chapters, descriptions, filtering receipts, and source order.
A failed effective SponsorBlock lookup is not persisted as a successful filtered snapshot.
Markdown is formatted again on each explicit request; only source data is cached.
CLI processing remains unchanged.
See [MCP retrieval tools](mcp.md#retrieval-tools) and [cache privacy and limits](mcp.md#local-source-cache).
