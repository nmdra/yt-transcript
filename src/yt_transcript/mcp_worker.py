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
        "get_transcript": {"operation", "url"},
        "preview_transcript": {
            "operation",
            "url",
            "chunk_chars",
            "max_chunks",
            "model_description",
        },
        "doctor": {"operation"},
    }
    if (
        not isinstance(operation, str)
        or operation not in allowed
        or set(request) != allowed[operation]
    ):
        raise ValueError
    if operation != "doctor":
        from .downloader import validate_youtube_url

        if not isinstance(request["url"], str):
            raise ValueError
        validate_youtube_url(request["url"])
    if operation == "preview_transcript":
        if (
            type(request["chunk_chars"]) is not int
            or not 1000 <= request["chunk_chars"] <= 50000
        ):
            raise ValueError
        cap = request["max_chunks"]
        if cap is not None and (type(cap) is not int or not 1 <= cap <= 1000):
            raise ValueError
        description = request["model_description"]
        if not isinstance(description, str) or len(description) > 4096:
            raise ValueError
    return request


def dispatch(request: dict) -> Mapping[str, Any]:
    from .service import doctor_data, fetch_transcript_document, preview_transcript_data

    operation = request["operation"]
    if operation == "doctor":
        return doctor_data()
    if operation == "get_transcript":
        return fetch_transcript_document(request["url"])
    return preview_transcript_data(
        request["url"],
        chunk_chars=request["chunk_chars"],
        max_chunks=request["max_chunks"],
        model_description=request["model_description"],
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
