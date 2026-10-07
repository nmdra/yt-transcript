# Troubleshooting

[README](../README.md) · [Installation](installation.md) · [CLI reference](cli.md)

Start with `yt-transcript --doctor`. It checks local readiness without fetching
captions or calling a model.

## Errors and recovery

Expected CLI failures use `error[CODE]: MESSAGE` and an optional safe hint. Verbose mode uses allowlisted diagnostic fields only.

| Codes | Action |
|---|---|
| `INVALID_URL`, `CONFIG_INVALID` | Correct the input or use `--no-config`. |
| `RUNTIME_MISSING`, `RUNTIME_INCOMPATIBLE` | Install compatible Deno/EJS components and run doctor. |
| `NO_ENGLISH_CAPTIONS`, `NO_ENGLISH_VTT` | No matching captions were returned. Availability is not fully proven. |
| `YOUTUBE_ACCESS_LIMITED` | Check permitted browser access. Captions can be omitted by access restrictions. |
| `VIDEO_UNAVAILABLE`, `AUTH_REQUIRED`, `AGE_RESTRICTED`, `GEO_RESTRICTED` | Check permitted browser/account access. No bypass is provided. |
| `REMOTE_RATE_LIMITED`, `NETWORK_FAILED` | Wait or check network/certificates. Keep TLS verification enabled. |
| `REMOTE_ACCESS_DENIED` | Check permitted access and runtime setup. A 403 alone does not prove authentication or token diagnosis. |
| `YOUTUBE_EXTRACT_FAILED`, `SUBTITLE_DOWNLOAD_FAILED` | Check supported yt-dlp/runtime setup and permitted access. |
| `UNSUPPORTED_LIVESTREAM` | Wait for a completed, processed recording. |
| `SUBTITLE_INVALID`, `EMPTY_TRANSCRIPT` | Use `--raw-vtt` to inspect captions separately. |
| `PI_NOT_FOUND`, `PI_LAUNCH_FAILED`, `PI_INCOMPATIBLE` | Install compatible Pi or use `--raw`. |
| `PI_AUTH_FAILED`, `PI_MODEL_UNAVAILABLE` | Configure the provider or the chosen/default model directly in Pi. |
| `PI_RATE_LIMITED`, `PI_QUOTA_EXCEEDED` | Wait or check provider quota. Rate limits and quota are distinct. |
| `PI_CONTEXT_LIMIT`, `PI_OUTPUT_INCOMPLETE` | Reduce chunk size, review the model choice, or use `--raw`. |
| `PI_TIMEOUT`, `PI_ABORTED`, `PI_FAILED` | Check provider/model setup or use deterministic output. |
| `PI_PROTOCOL_INVALID`, `PI_OUTPUT_INVALID`, `PI_OUTPUT_LIMIT` | Check compatible Pi setup. Buffered output is discarded. |
| `CHUNK_LIMIT_EXCEEDED` | Preview the plan or explicitly change the cap. No text is truncated. |
| `OUTPUT_EXISTS`, `OUTPUT_FAILED` | Choose a usable path and check filesystem support. |
| `MCP_BUSY`, `MCP_TIMEOUT`, `MCP_RESPONSE_LIMIT`, `INTERNAL_ERROR` | Wait or use the deterministic CLI. |

Unknown upstream wording receives a generic error, not a guessed authentication or billing cause. Private causes and raw warnings never enter CLI or MCP errors.

Exit codes are 0 for success, 2 for input/configuration errors, 1 for operation errors, and 130 for interruption.
