"""Private one-request worker. Not a public protocol or command."""

import json
import signal
import sys
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from .errors import AppError, ErrorInfo

REQUEST_LIMIT = 16 * 1024
DOCUMENT_LIMIT = 256 * 1024
RESULT_LIMIT = 1024 * 1024


def validate_request(request: object) -> dict:
    if not isinstance(request, dict):
        raise ValueError
    operation = request.get("operation")
    allowed = {
        "get_transcript": {"operation", "url", "mode", "sponsorblock"},
    }
    if (
        not isinstance(operation, str)
        or operation not in allowed
        or set(request) != allowed[operation]
    ):
        raise ValueError
    from .downloader import validate_youtube_url

    if not isinstance(request["url"], str):
        raise ValueError
    validate_youtube_url(request["url"])
    from .sponsorblock import validate_policy

    if not isinstance(request["mode"], str) or request["mode"] not in (
        "filtered",
        "full",
    ):
        raise ValueError
    validate_policy(request["sponsorblock"])
    return request


def dispatch(request: dict) -> Mapping[str, Any]:
    from .service import fetch_transcript_document
    from .sponsorblock import validate_policy

    return fetch_transcript_document(
        request["url"],
        request["mode"],
        sponsorblock=validate_policy(request["sponsorblock"]),
    )


def main() -> int:
    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        raw = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
        if len(raw) > REQUEST_LIMIT:
            raise ValueError
        request = validate_request(json.loads(raw.decode("utf-8")))
        result = dispatch(request)
        if len(result.get("document", "").encode("utf-8")) > DOCUMENT_LIMIT:
            raise AppError(
                ErrorInfo(
                    "MCP_RESPONSE_LIMIT",
                    "Document exceeds the MCP size limit.",
                    "Use the deterministic CLI for larger transcripts.",
                    "mcp_worker",
                )
            )
        envelope = {"result": result}
        encoded = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        if len(encoded) > RESULT_LIMIT:
            raise AppError(
                ErrorInfo(
                    "MCP_RESPONSE_LIMIT",
                    "Result exceeds the MCP size limit.",
                    "Use the deterministic CLI for larger transcripts.",
                    "mcp_worker",
                )
            )
    except AppError as exc:
        encoded = json.dumps({"error": asdict(exc.info)}).encode()
    except ValueError, UnicodeError:
        encoded = json.dumps(
            {
                "error": asdict(
                    ErrorInfo(
                        "CONFIG_INVALID",
                        "Invalid private worker request.",
                        phase="mcp_worker",
                    )
                )
            }
        ).encode()
    except KeyboardInterrupt:
        return 130
    except Exception:
        encoded = json.dumps(
            {
                "error": asdict(
                    ErrorInfo(
                        "INTERNAL_ERROR", "Worker operation failed.", phase="mcp_worker"
                    )
                )
            }
        ).encode()
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
