# Troubleshooting

[README](../README.md) · [Installation](installation.md) · [CLI reference](cli.md)

Start with `yt-transcript --doctor`.
Doctor checks local readiness.
Doctor does not fetch captions or call a model.

## Errors and recovery

Expected CLI failures use `error[CODE]: MESSAGE` and an optional safe hint.
Verbose mode uses only allowlisted diagnostic fields.

| Codes | Action |
|---|---|
| `INVALID_URL`, `CONFIG_INVALID` | Correct the input or use `--no-config`. |
| `RUNTIME_MISSING`, `RUNTIME_INCOMPATIBLE` | Install compatible Deno/EJS components. Run doctor. |
| `NO_ENGLISH_CAPTIONS`, `NO_ENGLISH_VTT` | The extraction returned no matching English track, or English tracks without a VTT format. This does not prove that the video has no English captions. Check permitted access and supported runtime setup. |
| `YOUTUBE_ACCESS_LIMITED` | Check permitted browser access. Access restrictions can cause captions to be omitted. |
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
| `PI_OUTPUT_INVALID` | Review the safe summary validation stage and reason when present. Invalid notes can be a JSON, schema, source-reference, or character-budget failure, not a Markdown failure. |
| `OPENROUTER_NOT_CONFIGURED` | Set an explicit model and OPENROUTER_API_KEY in the environment. No Pi is required. |
| `OPENROUTER_AUTH_FAILED` | Review permitted authentication/access. A 403 can also be a guardrail rejection. |
| `OPENROUTER_LIMITED` | Review rate, credit, and budget limits. No automatic retry occurs. |
| `OPENROUTER_FAILED` | Review network/TLS access and model availability. The tool does not expose raw HTTP error bodies. |
| `OPENROUTER_OUTPUT_INVALID`, `OPENROUTER_OUTPUT_INCOMPLETE` | The tool discarded output. Review safe summary validation details when present, and review model/token limits. Or explicitly request raw/plain text. |
| `OPENROUTER_TIMEOUT`, `OPENROUTER_CONTEXT_LIMIT` | Review formatting.chunk_chars, per-call limits, and the model. Completion and billing cancellation are not guaranteed. |
| `CHUNK_LIMIT_EXCEEDED` | Preview the plan or explicitly change the cap. The tool does not truncate text. |
| `OUTPUT_EXISTS`, `OUTPUT_FAILED` | Select a usable path. Check filesystem support. |
| `MCP_TIMEOUT` | The total worker deadline expired, including fetching and model calls. Review `mcp.markdown_timeout_seconds` and the client timeout, or explicitly request `output_format="plain_text"`. |
| `MCP_BUSY`, `MCP_RESPONSE_LIMIT`, `INTERNAL_ERROR` | Wait or use the deterministic CLI. |

If model processing fails, the tool includes a recovery warning.
CLI suggests `--raw`.
MCP suggests `output_format="plain_text"`.
The tool returns no partial document or automatic fallback.
If the failing chunk is known, MCP errors show that chunk.

## Summary note budget failures

A single source chunk produces Markdown directly.
Multiple source chunks produce private JSON notes before the final synthesis call.
An early `PI_OUTPUT_INVALID` or `OPENROUTER_OUTPUT_INVALID` can therefore mean that notes failed validation.
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
Increasing `max_chunks` alone does not increase note capacity.
The wrapper does not retry, repair, or truncate oversized notes.
A manual retry can incur new charges.

## Plain-text recovery

A new MCP plain-text request can reuse a valid source snapshot from the shared cache when the video and resolved mode/SponsorBlock policy match.
It fetches captions again if the cache is disabled or unavailable, or if no valid matching snapshot remains, including after expiry or eviction.
A failed effective SponsorBlock lookup is not cached for reuse.
CLI `--raw` fetches captions again.
Neither plain-text recovery path calls a model.
A fresh fetch can still fail because of network or caption errors.
Timeouts do not undo model charges already incurred.

If upstream wording is unknown, the tool returns a generic error.
The tool does not guess an authentication or billing cause.
Private causes and raw warnings never appear in CLI or MCP errors.

Exit codes are 0 for success, 2 for input/configuration errors, 1 for operation errors, and 130 for interruption.
