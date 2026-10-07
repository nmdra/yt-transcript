# Troubleshooting

[README](../README.md) · [Installation](installation.md) · [CLI reference](cli.md)

Start with `yt-transcript --doctor`.
Doctor checks local readiness without fetching captions or calling a model.

## Errors and recovery

Expected CLI failures use `error[CODE]: MESSAGE` and an optional safe hint.
Verbose mode uses only allowlisted diagnostic fields.

| Codes | Action |
|---|---|
| `INVALID_URL`, `CONFIG_INVALID` | Correct the input or use `--no-config`. |
| `RUNTIME_MISSING`, `RUNTIME_INCOMPATIBLE` | Install compatible Deno/EJS components. Run doctor. |
| `NO_ENGLISH_CAPTIONS`, `NO_ENGLISH_VTT` | No matching captions were returned. This does not fully prove caption availability. |
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
| `PI_PROTOCOL_INVALID`, `PI_OUTPUT_INVALID`, `PI_OUTPUT_LIMIT` | Check compatible Pi setup. Buffered output is discarded. |
| `CHUNK_LIMIT_EXCEEDED` | Preview the plan or explicitly change the cap. No text is truncated. |
| `OUTPUT_EXISTS`, `OUTPUT_FAILED` | Select a usable path. Check filesystem support. |
| `MCP_TIMEOUT` | The total worker deadline expired, including fetching and Pi calls. Review `mcp.markdown_timeout_seconds` and the client timeout, or explicitly request `output_format="plain_text"`. |
| `MCP_BUSY`, `MCP_RESPONSE_LIMIT`, `INTERNAL_ERROR` | Wait or use the deterministic CLI. |

Pi-processing failures include a recovery warning.
CLI suggests `--raw`.
MCP suggests `output_format="plain_text"`.
The tool returns no partial document or automatic fallback.
MCP errors show the failing chunk when available.

A new plain-text request fetches captions again but does not call Pi.
The request can still fail because of network or caption errors.
Timeouts do not undo model charges already incurred.

Unknown upstream wording receives a generic error.
The tool does not guess an authentication or billing cause.
Private causes and raw warnings never appear in CLI or MCP errors.

Exit codes are 0 for success, 2 for input/configuration errors, 1 for operation errors, and 130 for interruption.
