# Troubleshooting

[README](../README.md) · [Installation](installation.md) · [CLI reference](cli.md)

Start with `yt-transcript --doctor`.
Doctor checks local readiness.
Doctor does not fetch captions or call a model.

## Errors and recovery

Expected CLI failures use `error[CODE]: MESSAGE` and an optional safe hint.
Verbose mode uses only diagnostic fields from the allowlist.

| Codes | Action |
|---|---|
| `INVALID_URL`, `CONFIG_INVALID` | Correct the input or use `--no-config`. |
| `RUNTIME_MISSING`, `RUNTIME_INCOMPATIBLE` | Install compatible Deno/EJS components. Run doctor. |
| `NO_CAPTIONS`, `NO_VTT` | Extraction returned no track for the requested language, or returned matching tracks without a VTT format. This does not prove that the video has no captions in that language. Check the requested language, permitted access, and supported runtime setup. `NO_ENGLISH_CAPTIONS` and `NO_ENGLISH_VTT` are deprecated aliases that 1.1.0 no longer emits. |
| `YOUTUBE_ACCESS_LIMITED` | Check permitted browser access. Access restrictions can cause extraction to omit captions. |
| `VIDEO_UNAVAILABLE`, `AUTH_REQUIRED`, `AGE_RESTRICTED`, `GEO_RESTRICTED` | Check permitted browser/account access. The tool provides no bypass. |
| `REMOTE_RATE_LIMITED`, `NETWORK_FAILED` | Wait or check the network/certificates. Keep TLS verification enabled. |
| `REMOTE_ACCESS_DENIED` | Check permitted access and runtime setup. A 403 alone does not prove an authentication or token cause. |
| `YOUTUBE_EXTRACT_FAILED`, `SUBTITLE_DOWNLOAD_FAILED` | Check supported yt-dlp/runtime setup and permitted access. |
| `UNSUPPORTED_LIVESTREAM` | Wait for a completed, processed recording. |
| `SUBTITLE_INVALID`, `EMPTY_TRANSCRIPT` | Use `--raw-vtt` to inspect captions separately. |
| `PI_NOT_FOUND`, `PI_LAUNCH_FAILED`, `PI_INCOMPATIBLE` | Install compatible Pi or use `--raw`. |
| `PI_AUTH_FAILED`, `PI_MODEL_UNAVAILABLE` | Configure the provider or the selected/default model directly in Pi. |
| `PI_RATE_LIMITED`, `PI_QUOTA_EXCEEDED` | Wait or check provider quota. Rate limits and quota are distinct. |
| `PI_CONTEXT_LIMIT`, `PI_OUTPUT_INCOMPLETE` | Smaller chunks or a suitable model can help. Smaller chunks increase calls and delay. Use CLI `--raw` or MCP `output_format="plain_text"` to avoid Pi. |
| `PI_CONTEXT_MUTATED` | Pi attempted compaction or context changes. Complete formatting cannot be verified. Review Pi/model compatibility or request plain text. Do not accept summarized source as a complete transcript. |
| `PI_TIMEOUT`, `PI_ABORTED`, `PI_FAILED` | Check provider/model setup or use deterministic output. |
| `PI_PROTOCOL_INVALID`, `PI_OUTPUT_LIMIT` | Check compatible Pi setup. The tool discards buffered output. |
| `PI_OUTPUT_INVALID` | Review the fixed output validation reason or safe summary validation details when present. Notes can fail JSON, schema, source-reference, or character-budget validation rather than Markdown validation. |
| `OPENROUTER_NOT_CONFIGURED` | Set an explicit model and OPENROUTER_API_KEY in the environment. Pi is not required. |
| `OPENROUTER_AUTH_FAILED` | Review permitted authentication/access. A 403 can also be a guardrail rejection. |
| `OPENROUTER_LIMITED` | Review rate, credit, and budget limits. No automatic retry occurs. |
| `OPENROUTER_FAILED` | Review network/TLS access and model availability. The tool does not expose raw HTTP error bodies. |
| `OPENROUTER_OUTPUT_INVALID`, `OPENROUTER_OUTPUT_INCOMPLETE` | The tool discarded output. Review safe summary validation details when present, and review model/token limits. Or explicitly request raw/plain text. |
| `OPENROUTER_TIMEOUT`, `OPENROUTER_CONTEXT_LIMIT` | Review formatting.chunk_chars, per-call limits, and the model. Completion and billing cancellation are not guaranteed. |
| `DEEPSEEK_NOT_CONFIGURED` | Set an explicit model and DEEPSEEK_API_KEY only in the environment. Pi is not required. |
| `DEEPSEEK_AUTH_FAILED` | Review permitted authentication/access. Doctor checks presence, not authentication. |
| `DEEPSEEK_LIMITED` | Review rate, balance, and budget limits. No automatic retry occurs. |
| `DEEPSEEK_FAILED` | Review network/TLS access and model availability. The tool does not expose raw HTTP error bodies. |
| `DEEPSEEK_OUTPUT_INVALID`, `DEEPSEEK_OUTPUT_INCOMPLETE` | The tool discarded output. Review safe validation details and model/token limits, or explicitly request raw/plain text. |
| `DEEPSEEK_TIMEOUT`, `DEEPSEEK_CONTEXT_LIMIT` | Review source/synthesis limits, per-call deadline, and model support. Local timeout does not undo billing. |
| `CHUNK_LIMIT_EXCEEDED` | Preview the plan or explicitly change the cap. The tool does not truncate text. |
| `OUTPUT_EXISTS`, `OUTPUT_FAILED` | Select a usable path. Check filesystem support. |
| `MCP_TIMEOUT` | The total worker deadline expired, including fetching and model calls. Review `mcp.markdown_timeout_seconds` and the client timeout, or explicitly request `output_format="plain_text"`. |
| `MCP_BUSY`, `MCP_RESPONSE_LIMIT`, `INTERNAL_ERROR` | Wait or use the deterministic CLI. |

If model processing fails, the tool includes a recovery warning.
CLI suggests `--raw`.
MCP suggests `output_format="plain_text"`.
The tool returns no partial document or automatic fallback.
MCP errors show the failing chunk when it is known.

## Output validation reasons

Invalid model output can include a fixed `Validation reason` in CLI and MCP errors.
The reason identifies the failed check. It does not include captions, chapter titles, model output, private reasoning, credentials, or raw provider errors.
The existing error code and failing chunk position remain unchanged.

| Reason | Meaning |
|---|---|
| `completion_empty_text` | Pi reported a normal stop but returned no nonblank visible text. Thinking alone is not a transcript. |
| `body_empty_text`, `body_yaml_header`, `body_outer_fence` | The response was empty, started with YAML front matter, or used a whole-response code fence. |
| `chapter_heading_mismatch` | The assembled Markdown contained unexpected or mismatched chapter headings. Python inserts canonical headings; model bodies must not add `##` headings. |
| `chapter_missing_headings`, `chapter_preamble`, `chapter_empty_body` | Structure checks found no chapter headings, text before the first heading, or an empty chapter body in standard mode. |
| `chapter_invalid_json`, `chapter_invalid_schema`, `chapter_invalid_run_ids` | The model did not return strict chapter-body JSON, used invalid fields/types, or failed to return all supplied run IDs exactly once in order. |
| `chapter_level_one_heading`, `chapter_setext_heading` | The response used a forbidden heading style. |
| `chapter_invalid_fence`, `chapter_unclosed_fence` | A chapter response contained an invalid or unclosed code fence. |
| `transcript_unexpected_omission`, `transcript_empty_output` | The response used an invalid omission marker or left no retained transcript body. |
| `summary_empty_output`, `summary_unexpected_omission`, `summary_invalid_structure`, `summary_empty_evidence`, `summary_private_id` | The summary was empty, used an omission marker, failed heading/body checks, had no notes evidence, or contained a private source ID. |

Chapter-aware standard and focused calls return private JSON bodies. Python supplies the final chapter headings, including their punctuation and escaping.
Invalid JSON or Markdown still fails without repair. Nonchapter and summary response formats remain unchanged.

These reasons identify structural failures. They do not prove a cause such as authentication failure, an output-token limit, or incorrect model content.
A successful retry does not establish why an earlier response failed.
A manual retry can incur new charges.
The tool does not retry automatically, repair the response, relax validation, or publish partial output.
Use CLI `--raw` or MCP `output_format="plain_text"` to avoid model processing.

## Thinking and DeepSeek checks

If configuration fails, use a Boolean for `formatting.thinking` and one scalar string (`low`, `medium`, or `high`) for `formatting.thinking_level`.
Do not use an array or a string such as `"false"` for the Boolean.
A level alone is valid for summarized mode.
In standard/focused mode, explicitly set thinking to true to use a level, or to false to keep it inactive.
Explicit false always overrides automatic summary thinking.
When you omit both thinking settings, summarized mode requests medium in all stages.
When you omit both thinking settings in standard/focused modes, these modes keep Pi/OpenRouter defaults and request DeepSeek off.
DeepSeek maps medium to high.
Preview shows the requested policy.
It does not prove that the selected model honors the policy.
Pi/OpenRouter may clamp or map levels, reject unsupported settings, or use a model that cannot disable reasoning.

Thinking can use the output allowance and increase latency or cost.
The wrapper does not raise token limits automatically.
Reasoning suppression does not disable billing.
If output is incomplete, review the model's supported output limit and your configured allowance.
`deepseek.max_output_tokens` defaults to 16384 and accepts integers from 1 through 393216.
A larger allowance does not guarantee valid or complete output.
The tool does not retry, repair, use a provider fallback, or publish partial output.
DeepSeek response limits include private reasoning: 2 MiB total HTTP response and 1 MiB visible text.
Helper input/output limits are 1 MiB and 8 MiB respectively.
Oversized output causes failure instead of truncation.

DeepSeek requires an explicit model and environment-only `DEEPSEEK_API_KEY`.
Never print or paste the key into configuration, arguments, or diagnostics.
Direct requests do not use OpenRouter's `data_collection="deny"` routing policy.
Do not assume the same retention guarantees.
There is no evidence here that thinking improves summary fidelity.
Raw and plain-text recovery and retrieval tools do not use a model.
The cache stores source captions, not provider output.

## Summary note budget failures

A single source chunk produces Markdown directly.
Multiple source chunks produce private JSON notes before the final synthesis call.
An early `PI_OUTPUT_INVALID`, `OPENROUTER_OUTPUT_INVALID`, or `DEEPSEEK_OUTPUT_INVALID` can therefore mean that notes failed validation.
A successful short-video summary does not test the multi-chunk notes path.

`formatting.chunk_chars` limits each source input.
`formatting.summary_synthesis_chars` independently limits the complete final notes envelope.
Python divides the synthesis budget among source-note calls, including JSON framing.
Safe budget diagnostics report actual and allowed character counts, not response text.
A large model context window does not override these application limits.

Set both limits in `[formatting]` in TOML, not with `--chunk-chars`:

```toml
[formatting]
chunk_chars = 30000
summary_synthesis_chars = 50000
```

The synthesis setting allows integers from 1,000 through 500,000 and defaults to 50,000.
Larger synthesis budgets require a model that supports the full request, instructions, and output allowance.
Both settings count characters, not tokens.
Smaller source chunks can increase calls and reduce the notes budget per call.
Increasing `max_chunks` alone does not increase the notes budget.
The wrapper does not retry, repair, or truncate oversized notes.
A manual retry can cause new charges.

## Plain-text recovery

A new CLI or MCP request can reuse a valid source snapshot from the shared cache when the video, requested language, mode, and SponsorBlock policy match.
The request fetches captions again if the cache is disabled or unavailable, or if no valid matching snapshot remains, including after expiry or eviction.
A failed effective SponsorBlock lookup is not cached for reuse.
CLI `--no-cache` and `[cache].enabled = false` disable reuse.
Neither plain-text recovery path calls a model.
A fresh fetch can still fail because of network or caption errors.
Timeouts do not undo model charges already incurred.

If upstream wording is unknown, the tool returns a generic error.
The tool does not guess an authentication or billing cause.
Private causes and raw warnings never appear in CLI or MCP errors.

Exit codes are 0 for success, 2 for input/configuration errors, 1 for operation errors, and 130 for interruption.
