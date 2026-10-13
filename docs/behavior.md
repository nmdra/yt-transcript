# Transcript behavior

[README](../README.md) · [CLI reference](cli.md) · [MCP setup](mcp.md)

## Pi isolation and completeness

Pi receives cleaned text through stdin.
With chapter or SponsorBlock boundary context, stdin contains JSON with applicable titles, times, annotations, and retained text.
Each retained source word belongs to one current chunk in the plan.
Optional read-only boundary context can repeat neighboring words as context. These words do not own output.
The complete serialized source input counts toward the source chunk limit.
Multi-chunk summary synthesis uses a separate limit described below.
Context overhead can increase the number of calls.
Pi does not receive YAML or the upstream metadata dictionary.

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
Documents and diagnostics never contain events, thinking, or raw stderr.

A normal stop does not prove factual accuracy or semantic completeness.
Offline structural tests do not prove that actual model edits keep the source meaning.

## Conservative spelling correction

Pi, OpenRouter, and DeepSeek receive the same spelling rules in all Markdown editorial modes, including summary notes and synthesis.
If the intended word is clear from the captions, the model may correct an unambiguous ordinary-word spelling error.
For example, `recieve the message` can become `receive the message`.
The model must keep the source meaning, certainty, and qualifications.

In retained text and included summary details, names, technical terms, numbers, units, URLs, code, commands, and identifiers must remain unchanged.
This requirement applies even if they appear misspelled.
Uncertain spellings must remain unchanged.
The model must not replace a correctly spelled word with a different word, resolve homophones, infer missing words, or repair technical claims.
This policy does not correct every speech-recognition error.

These rules are prompt instructions. They are not a deterministic spelling checker or a guarantee of model fidelity.
The policy adds no model calls, research, retries, or repair pass.
Raw captions, raw VTT, MCP plain text, metadata, and canonical chapter headings remain unchanged.

## Chapters, focused editing, and SponsorBlock

In standard and focused modes, valid supplied chapters become canonical `## [time] title` Markdown headings.
Cue-start alignment keeps caption order, crossings, gaps, and backward revisits.
For chapter-aware standard and focused calls, the model returns strict JSON with one `run_id` and Markdown `body` for each supplied run.
Python requires all run IDs exactly once in the supplied order. It rejects duplicate keys, extra fields, foreign IDs, and reordered or missing runs.
Python inserts the canonical headings from its source plan. The model does not copy heading text or Markdown escaping.
Each body can use `###` and lower headings. Code fences must close within that body, not in another run.
Standard mode requires a nonblank body for every run. Focused mode permits an empty body for a wholly removable run.
Python validates each run's Markdown structure, then validates the assembled chunk.
Then Python removes duplicate continuation headings.
The complete JSON response and rendered chunk retain the existing 1 MiB UTF-8 limits.
This private response format does not change CLI output, MCP schemas, metadata, or source filtering.
Nonchapter formatting and whole-video summaries keep their existing response formats.
Invalid output causes failure without a repair call or silent fallback.

```sh
yt-transcript URL --no-config --editorial-mode focused --preview
yt-transcript URL --no-config --editorial-mode focused --max-chunks 3 -o focused.md
yt-transcript URL --no-config --sponsorblock --preview
```

Standard mode remains the CLI default.
Focused editing is selective editing, not summarization.
Focused editing removes separable greetings, ads, interaction requests, housekeeping, and unrelated tangents.
Focused editing keeps substantive examples, technical product explanations, code, URLs, numbers, qualifications, relevant affiliations/disclosures, and ambiguous content.

Every retained source chunk still goes to the selected model backend.
Fully omitted chunks do not reduce planned calls.
If all output is omitted, publication fails.
Use standard or raw mode in this case.
Source chapter metadata remains complete even when focused editing omits a body section.
Fake-process tests do not prove actual model fidelity.

The CLI uses SponsorBlock only when enabled.
MCP filtered mode attempts SponsorBlock by default.
The fixed official HTTPS lookup sends only a four-character SHA-256 prefix of the video ID.
Then the wrapper matches the actual ID locally.
Prefix lookup does not guarantee anonymity.
SponsorBlock lookup uses no cookies, credentials, redirects, full-ID fallback, submissions, votes, view reports, or separate persistent cache.
MCP can store and reuse the lookup result with captions in its shared source cache.
The wrapper makes one lookup attempt.
The socket timeout is not a total deadline.

Filtering occurs after global rolling cleanup.
The wrapper removes only complete nonzero cues contained in the selected interval union.
The wrapper keeps crossing cues and zero-duration cues.
The wrapper does not guess word timing or repeat cleanup.
The wrapper converts both video durations to milliseconds.
For each accepted segment, the submitted SponsorBlock duration must differ from the extracted video duration by at most 1,000 ms.
A difference of exactly one second is accepted.
This tolerance checks duration alignment, not the time taken by the lookup.
If removal would empty the transcript, the wrapper keeps the transcript and gives a warning.
Community labels cannot guarantee correct promotion detection.

If the lookup or its data fails, the tool keeps the captions and produces `warning[SPONSORBLOCK_UNAVAILABLE]`.
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
Standard mode remains the default.
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
Source chunks use `formatting.chunk_chars`.
Multi-chunk summaries use `formatting.summary_synthesis_chars` for the complete final notes envelope.
The synthesis limit defaults to 50,000 characters and allows integers from 1,000 through 500,000.
Python reserves space for JSON framing, then divides the remaining limit among note calls.
The notes prompt requests compact JSON and targets 75% of each hard response limit to leave space for estimation errors.
This prompt target is not a deterministic guarantee.
Python rejects impossible budgets before model calls and rejects oversized notes without truncation.
The final synthesis input must fit the separate synthesis limit.
Both settings count characters, not tokens, and exclude model instructions.
A model must support the complete request and its output allowance.
Character budgets do not override the existing UTF-8 transport and completion-size limits.
Larger budgets can increase latency and cost or exceed the selected model's context window.
Notes use independent backend calls.
Completed note calls can incur charges even if synthesis later fails.
Only the final synthesis call receives the notes as validated private evidence objects.
The notes are never published as transcript output.

Python validates final headings and nonempty bodies.
Python does not prove summary accuracy or enforce the target word count.
If processing fails, it publishes no partial notes, summary, or automatic fallback.
The final summary uses its own headings rather than canonical chapter headings.
Source chapter metadata, descriptions, and SponsorBlock receipts remain unchanged.
Removal receipts still describe source filtering, not what the summary includes or omits.

### Summary thinking policy

When thinking settings are omitted, summarized Markdown requests thinking at medium in every stage.
This includes direct summary, each notes call, and final synthesis.
Explicit `formatting.thinking = false` requests off for every mode, regardless of a valid configured level.
Explicit true uses `formatting.thinking_level`, or medium if you omit the level.
The level is one scalar string: low, medium, or high.
A level alone is valid for automatic summarized thinking.
Standard/focused require explicit true for an active level. With explicit false, the level is inactive.
Omitted settings preserve Pi/OpenRouter defaults for standard/focused and request DeepSeek off.
DeepSeek maps medium to high.
Pi/OpenRouter may clamp, map, or reject settings, and some models cannot turn reasoning off.
Preview reports requested policy, not confirmed provider behavior.

Thinking can increase latency and cost and use tokens that would otherwise be available for visible output.
The output-token allowance does not increase automatically.
No extra model calls, retries, repair calls, or partial publication are added.
Automatic thinking is a selected application policy, not evidence that reasoning improves transcript-summary fidelity.
Raw, plain-text MCP, and retrieval paths remain model-free.
See [thinking configuration](cli.md#thinking-policy).

## Internal summary evidence and continuity

Python assigns a private ID and one source-call owner to each summary source span.
Timed source origins retain source indices, run order, original cue times, and split-word ranges.
Untimed source origins use normalized-text offsets and null timestamps.
Retained caption text does not contain the ID namespace.
Removed captions and descriptions are never added to the registry.
A split cue keeps its original interval.
The wrapper does not infer finer timing.

Multi-chunk note calls return strict JSON with exactly `claims`.
Each claim has `statement`, unique same-call `source_ids`, and a `qualifications` array.
Limits are 64 claims per call, 16 IDs per claim, and 16 qualifications per claim.
Empty claims are allowed.
If all evidence is empty, processing fails before the synthesis call.
Duplicate keys, forged/cross-call references, invalid schemas, fences, commentary, and oversized notes fail without repair.
The wrapper serializes validated objects, IDs, and qualifications directly into the final notes envelope, not as quoted Markdown strings.

Planning counts source IDs, claim/schema framing, JSON escapes, and chunk indices.
Each note call must have at least 256 serialized characters available after minimum claim framing.
An infeasible synthesis budget fails before model execution.
ID framing can change source partitions and call counts.
One planned source chunk still uses one direct summary call.
N chunks use N note calls plus one synthesis.
No hierarchical synthesis, judging, repair, or retry calls are added.
Final summary validation rejects canonical private IDs rather than removing them silently.
Only the validated final Markdown is published.
Metadata and public MCP fields remain unchanged.

Reference membership does not establish entailment or truth.
Empty qualification arrays are structurally valid and can omit a needed caveat.
The final synthesis still has a fixed compression budget and sees notes rather than all captions.
Offline annotations and human review remain necessary.
Real-model fidelity has not been verified.

CLI and Python standard or focused formatting can use bounded read-only neighboring captions when enabled.
The default value of zero keeps their old source payload shapes without private ID fields.
Nonzero context wraps existing current data with `previous_context` and `following_context`.
Only current words own output.
Only current runs determine canonical headings.
Context windows use whole tokens, never chapter titles, descriptions, removed captions, or earlier model output.
The wrapper reserves space for worst-case JSON escaping before deterministic repartitioning.
If a neighbor token is larger than its window, the wrapper omits it.
The wrapper does not truncate it.
Context can increase calls or leave no room for a current token.
A model can still copy context into its output.
Prompts and heading validation do not prove output ownership.
The wrapper does not repair duplication automatically.

`compare_fidelity` and the [offline evaluator](development.md#offline-fidelity-evaluation) report advisory literal/annotation differences.
They never reject a production transcript, launch a model, retry, or publish a sidecar.

## Backend-independent formatting

All three backends use the same source prompts, chapter validation, omission rules, and summary assembly.
Descriptions are never model input.
Pi keeps the isolated subprocess contract above.
OpenRouter and DeepSeek use one bounded nonstreaming HTTPS completion per planned call through a supervised Python helper.
The helper rejects tool calls, redirects, invalid or oversized responses, and non-stop completions.
The wrapper makes no automatic retry or provider switch and publishes no partial result.
Direct DeepSeek uses standard-library HTTP at the fixed HTTPS endpoint `https://api.deepseek.com/chat/completions`.
It requires an explicit model and reads `DEEPSEEK_API_KEY` only from the helper environment.
Its byte ceilings are 1 MiB helper input, 2 MiB HTTP response including reasoning, 1 MiB visible completion text, and 8 MiB helper output.
OpenRouter also limits HTTP responses to 2 MiB and visible completion text to 1 MiB.
Reasoning still counts toward the HTTP response limit even when it is suppressed from documents.
Oversized responses fail without truncation or raised limits.
Private reasoning never becomes document text, notes evidence, diagnostics, cache data, or input to later independent calls.
Hiding private reasoning does not disable reasoning or charges.
DeepSeek sends captions directly to DeepSeek, not through OpenRouter's `data_collection="deny"` route.
The wrapper gives no equivalent provider retention guarantee.
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
caption_translated: false
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
All fifteen top-level fields are always present.
The first fourteen fields keep their order.
`description` is the final field.

The canonical URL excludes playlist and tracking parameters.
The video ID must match the single extracted video.

The channel falls back to the uploader name.
The channel URL falls back to the uploader URL.
The channel ID never falls back to a handle.

The upload date uses UTC.
If the date is absent, a valid timestamp supplies it.
An explicitly malformed date becomes `null`.
The wrapper does not guess a date.

Duration preserves zero and fractional seconds.
Missing or invalid optional values become `null`.
Caption language keeps the selected key exactly.

Caption source is `manual` or `automatic`.
`caption_translated` reports whether YouTube translated the selected track.
The value is `true` for a translated track.
The value is `false` when the track URL is usable and has no `tlang` parameter.
The value is `null` when no usable URL exists.
A `true` value means that YouTube machine-translated the text.
A `false` value does not prove editorial accuracy.

`description` contains the text that yt-dlp supplies in the same processed extraction.
The wrapper makes no additional request for this field.
If a description is missing, null, empty, whitespace-only, or not a string, the wrapper sets it to `null`.
Accepted strings keep their whitespace, line breaks, Unicode, URLs, timestamps, and markup.
Description availability and completeness depend on the upstream response and yt-dlp.
The wrapper does not guarantee that the field matches the complete YouTube page description.

CLI raw and Markdown file headers, MCP structured metadata, and compatibility JSON include this field.
Descriptions are not included in transcript bodies, model input, or CLI preview.
SponsorBlock and focused editing do not change descriptions.
The wrapper does not parse description links or create new chapters from this field.
Descriptions remain untrusted source data. They are not instructions.

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

The wrapper selects one track with VTT formats for the requested language `L`. It uses this order:

1. Manual `L`
2. Other manual `L-` keys, in lexical order
3. Automatic `L-orig`, then other `L-` keys that end in `-orig`
4. Automatic `L`
5. Other automatic `L-` keys, in lexical order

Track matching ignores case. It keeps the original key.
`L` comes from `--language` or from `[captions].language`. The default is `en`.
Every native track ranks above every translated track.
If no native track exists, the wrapper uses a YouTube-provided translated track.
If a request carries a region or script subtag and finds no track, the wrapper retries the primary subtag only.
The fallback accepts only the exact primary key and its `-orig` marker.
The fallback never substitutes a different variant.
Therefore, `zh-Hant` never returns `zh-Hans`, and `pt-BR` never returns `pt-PT`.
Likewise, `en-US` reaches `en` or `en-orig`, and `pt-BR` reaches `pt` or `pt-orig`.
The wrapper reports the selected key in file metadata and in verbose output.
The wrapper reports whether the selected track is a YouTube translation.
The wrapper reads the `tlang` query parameter on the format URL of the selected track.
`caption_translated` is `true` for a translation.
It is `false` when the track URL is usable and has no `tlang` parameter, and `null` when no usable URL exists.
The wrapper does not translate locally.
Translated tracks receive no quality guarantee. They can be less accurate than native tracks.

The wrapper downloads only captions, into a temporary directory.
The wrapper performs one metadata extraction.
The wrapper does not silently change tracks after a download error.

The supported VTT parser keeps caption text, Unicode, punctuation, and descriptions such as `[Music]`.
The parser skips metadata blocks.
The parser removes supported VTT tags before entity decoding.

Manual captions keep repetition.
Automatic cleanup removes exact suffix/prefix overlaps only within consecutive rolling cues with a gap of at most 100 ms.

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

Version 1.0.0 includes deterministic metadata, segment, search, and page tools.
They share source-caption snapshots with MCP `get_transcript`, without calling a model.
Cache rehydration preserves original cues, chapters, descriptions, filtering receipts, and source order.
The cache does not store a failed effective SponsorBlock lookup as a successful filtered snapshot.
The wrapper formats Markdown again on each explicit request.
The cache stores only source data.
The CLI and MCP use the same cache, the same default database, and the same `[cache]` policy.
The CLI and MCP therefore reuse the same snapshots.
The wrapper reuses a snapshot only if the video, the requested language, the mode, and the resolved SponsorBlock policy match.
`--no-cache` disables reuse for one CLI run.
`--cache` enables reuse for one CLI run, even if the configured policy disables it.
See [MCP retrieval tools](mcp.md#retrieval-tools) and [cache privacy and limits](mcp.md#local-source-cache).
