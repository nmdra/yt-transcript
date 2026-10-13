"""Private one-request worker. Not a public protocol or command."""

import json
import signal
import sys
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from .config import validate_cache_policy, validate_language_tag
from .errors import AppError, ErrorInfo
from .json_tools import strict_json_loads

REQUEST_LIMIT = 16 * 1024
DOCUMENT_LIMIT = 256 * 1024
RESULT_LIMIT = 1024 * 1024


def validate_request(request: object) -> dict:
    if not isinstance(request, dict):
        raise ValueError
    operation = request.get("operation")
    fields = {"operation", "url", "mode", "sponsorblock"}
    if operation == "get_transcript":
        if "output_format" in request or "formatting" in request:
            fields |= {"output_format", "formatting"}
    elif operation == "get_video_info":
        if request.get("mode") != "filtered":
            raise ValueError
    elif operation == "get_transcript_segment":
        fields |= {"start_seconds", "end_seconds"}
    elif operation == "search_transcript":
        fields |= {"query", "max_results"}
    elif operation == "get_transcript_page":
        fields |= {"cursor", "max_chars"}
    else:
        raise ValueError
    if "cache" in request:
        fields.add("cache")
    if "language" in request:
        fields.add("language")
    if set(request) != fields:
        raise ValueError
    validate_cache_policy(request.get("cache", {}))
    validate_language_tag(request.get("language", "en"))
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
    from .service import (
        validate_page_request,
        validate_search_query,
        validate_segment_range,
    )

    if operation == "get_transcript_segment":
        validate_segment_range(request["start_seconds"], request["end_seconds"])
    elif operation == "search_transcript":
        validate_search_query(request["query"], request["max_results"])
    elif operation == "get_transcript_page":
        validate_page_request(request["cursor"], request["max_chars"])
    if "output_format" in request:
        from .mcp_policy import validate_formatting_policy

        if request["output_format"] != "markdown":
            raise ValueError
        validate_formatting_policy(request["formatting"])
    return request


def dispatch(request: dict) -> Mapping[str, Any]:
    from . import service
    from .mcp_policy import validate_formatting_policy
    from .sponsorblock import validate_policy
    from .transcript_cache import TranscriptCache

    sponsorblock = validate_policy(request["sponsorblock"])
    cache = TranscriptCache(**asdict(validate_cache_policy(request.get("cache", {}))))
    options: dict[str, Any] = {
        "sponsorblock": sponsorblock,
        "cache": cache,
        "language": request.get("language", "en"),
    }
    operation = request["operation"]
    if operation == "get_transcript":
        markdown = request.get("output_format") == "markdown"
        formatting = (
            validate_formatting_policy(request["formatting"]) if markdown else None
        )
        if markdown:
            options["on_progress"] = report_progress
        return service.fetch_transcript_document(
            request["url"],
            request["mode"],
            output_format="markdown" if markdown else "plain_text",
            formatting=formatting,
            supervised=markdown,
            **options,
        )
    if operation == "get_video_info":
        return service.get_video_info(request["url"], **options)
    if operation == "get_transcript_segment":
        return service.get_transcript_segment(
            request["url"],
            request["start_seconds"],
            request["end_seconds"],
            request["mode"],
            **options,
        )
    if operation == "search_transcript":
        return service.search_transcript(
            request["url"],
            request["query"],
            request["mode"],
            request["max_results"],
            **options,
        )
    if operation == "get_transcript_page":
        return service.get_transcript_page(
            request["url"],
            request["cursor"],
            request["max_chars"],
            request["mode"],
            **options,
        )
    raise ValueError


def report_progress(done: int, total: int) -> None:
    record = {"done": done, "total": total, "stage": "formatting"}
    print(
        "YT_PROGRESS\t" + json.dumps(record, separators=(",", ":")),
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        raw = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
        if len(raw) > REQUEST_LIMIT:
            raise ValueError
        request = validate_request(strict_json_loads(raw.decode("utf-8")))
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
        from .service import validate_service_result

        validate_service_result(request["operation"], result)
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
