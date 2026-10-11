"""Safe application errors. Upstream text is classification input, never output."""

import errno
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Any

CODES = frozenset(
    "INVALID_URL CONFIG_INVALID RUNTIME_MISSING RUNTIME_INCOMPATIBLE NO_ENGLISH_CAPTIONS NO_ENGLISH_VTT YOUTUBE_ACCESS_LIMITED VIDEO_UNAVAILABLE AUTH_REQUIRED AGE_RESTRICTED GEO_RESTRICTED UNSUPPORTED_LIVESTREAM REMOTE_RATE_LIMITED REMOTE_ACCESS_DENIED NETWORK_FAILED YOUTUBE_EXTRACT_FAILED SUBTITLE_DOWNLOAD_FAILED SUBTITLE_INVALID EMPTY_TRANSCRIPT PI_NOT_FOUND PI_LAUNCH_FAILED PI_INCOMPATIBLE PI_AUTH_FAILED PI_MODEL_UNAVAILABLE PI_RATE_LIMITED PI_QUOTA_EXCEEDED PI_CONTEXT_LIMIT PI_CONTEXT_MUTATED PI_OUTPUT_INCOMPLETE PI_TIMEOUT PI_ABORTED PI_FAILED PI_PROTOCOL_INVALID PI_OUTPUT_INVALID PI_OUTPUT_LIMIT CHUNK_LIMIT_EXCEEDED OUTPUT_EXISTS OUTPUT_FAILED MCP_BUSY MCP_TIMEOUT MCP_RESPONSE_LIMIT INTERNAL_ERROR".split()
)
PHASES = frozenset(
    "config runtime_check metadata_extract caption_select subtitle_download vtt_parse pi_start pi_response output mcp_worker".split()
)


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    hint: str | None = None
    phase: str = "runtime_check"
    retryable: bool = False
    chunk_index: int | None = None
    chunk_total: int | None = None


class AppError(Exception):
    def __init__(self, info: ErrorInfo, *, cause: BaseException | None = None):
        super().__init__(info.message)
        self.info = info
        self._cause = cause


class ConfigError(AppError):
    pass


class TranscriptError(AppError):
    pass


class FormattingError(AppError):
    pass


def error(code: str, message: str, *, phase: str, hint: str | None = None) -> AppError:
    return AppError(ErrorInfo(code, message, hint, phase))


def walk_causes(exc: BaseException):
    pending: list[tuple[Any, int]] = [(exc, 0)]
    seen = set()
    while pending:
        current, depth = pending.pop()
        if not isinstance(current, BaseException) or id(current) in seen or depth > 8:
            continue
        seen.add(id(current))
        yield current
        for name in ("__cause__", "__context__", "cause"):
            try:
                child = getattr(current, name, None)
            except Exception:
                child = None
            pending.append((child, depth + 1))
        try:
            info = getattr(current, "exc_info", None)
        except Exception:
            info = None
        if isinstance(info, (tuple, list)) and len(info) > 1:
            pending.append((info[1], depth + 1))


# Narrow synthetic recognizers for yt-dlp 2026.8.19 and Pi 1.0.4.
YOUTUBE_PATTERNS = (
    ("Sign in to confirm your age", "AGE_RESTRICTED"),
    ("Sign in to confirm you’re not a bot", "YOUTUBE_ACCESS_LIMITED"),
    ("Sign in to confirm you're not a bot", "YOUTUBE_ACCESS_LIMITED"),
    ("This video is private", "AUTH_REQUIRED"),
    ("Video unavailable", "VIDEO_UNAVAILABLE"),
    ("subtitles require a PO Token which was not provided", "YOUTUBE_ACCESS_LIMITED"),
    ("formats require a GVS PO Token which was not provided", "YOUTUBE_ACCESS_LIMITED"),
    ("PO Token required", "YOUTUBE_ACCESS_LIMITED"),
)
PI_PATTERNS = (
    ("No API key found for", "PI_AUTH_FAILED"),
    ("Model not found:", "PI_MODEL_UNAVAILABLE"),
    ("insufficient_quota", "PI_QUOTA_EXCEEDED"),
    ("rate_limit_exceeded", "PI_RATE_LIMITED"),
    ("context_length_exceeded", "PI_CONTEXT_LIMIT"),
    ("Unknown option: --no-", "PI_INCOMPATIBLE"),
)


def recognized_error(text: str, patterns, *, youtube: bool = False) -> str | None:
    """Match known error prefixes, not error-looking titles within a message."""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text[:65536]).strip()
    text = re.sub(r"^(?:ERROR|Error):\s*", "", text)
    if youtube:
        text = re.sub(r"^\[youtube\]\s*", "", text)
        text = re.sub(r"^[A-Za-z0-9_-]{11}:\s*", "", text)
        if re.match(
            r"^(?:Some [A-Za-z0-9_-]+ client subtitles require a PO Token"
            r"|[A-Za-z0-9_-]+ client [A-Za-z0-9_-]+ formats require a GVS PO Token)"
            r" which was not provided(?:\.|$)",
            text,
        ):
            return "YOUTUBE_ACCESS_LIMITED"
    return next((code for pattern, code in patterns if text.startswith(pattern)), None)


HINTS = {
    "NETWORK_FAILED": "Check network access and certificates; keep TLS verification enabled.",
    "REMOTE_RATE_LIMITED": "Wait before another attempt.",
    "REMOTE_ACCESS_DENIED": "Verify permitted access and the supported runtime setup.",
    "YOUTUBE_ACCESS_LIMITED": "Caption availability could not be fully verified. Check permitted browser access.",
    "GEO_RESTRICTED": "Verify permitted access from your location.",
    "AGE_RESTRICTED": "Verify permitted browser and account access.",
    "AUTH_REQUIRED": "Verify permitted browser and account access.",
    "VIDEO_UNAVAILABLE": "Verify that the video is available through permitted browser access.",
}


def classify_ytdlp_error(exc: BaseException, *, phase: str) -> TranscriptError:
    from yt_dlp.networking.exceptions import HTTPError, TransportError
    from yt_dlp.utils import GeoRestrictedError

    code = None
    causes = list(walk_causes(exc))
    # Inspect all status/geo evidence before a less specific transport wrapper.
    for cause in causes:
        if isinstance(cause, GeoRestrictedError):
            code = "GEO_RESTRICTED"
            break
        if isinstance(cause, HTTPError):
            if cause.status == 429:
                code = "REMOTE_RATE_LIMITED"
            elif cause.status in (401, 403):
                code = "REMOTE_ACCESS_DENIED"
            if code:
                break
    if code is None and any(
        isinstance(
            cause,
            (
                TransportError,
                TimeoutError,
                ConnectionError,
                socket.gaierror,
                ssl.SSLError,
            ),
        )
        for cause in causes
    ):
        code = "NETWORK_FAILED"
    if code is None:
        for cause in causes:
            try:
                text = str(cause)[:65536]
            except Exception:
                text = ""
            code = recognized_error(text, YOUTUBE_PATTERNS, youtube=True)
            if code:
                break
    code = code or (
        "SUBTITLE_DOWNLOAD_FAILED"
        if phase == "subtitle_download"
        else "YOUTUBE_EXTRACT_FAILED"
    )
    return TranscriptError(
        ErrorInfo(
            code,
            "YouTube operation failed.",
            HINTS.get(
                code, "Check permitted access and supported yt-dlp/runtime setup."
            ),
            phase,
            code in ("NETWORK_FAILED", "REMOTE_RATE_LIMITED"),
        ),
        cause=exc,
    )


def classify_pi_failure(
    text: str = "",
    *,
    phase: str = "pi_response",
    code: str | None = None,
    chunk_index: int | None = None,
    chunk_total: int | None = None,
) -> FormattingError:
    code = code or recognized_error(text, PI_PATTERNS) or "PI_FAILED"
    messages = {
        "PI_NOT_FOUND": "Pi is required for Markdown formatting. Install Pi or use --raw.",
        "PI_INCOMPATIBLE": "Pi does not support the required isolated formatter interface.",
        "PI_LAUNCH_FAILED": "The Pi formatter process could not start.",
        "PI_AUTH_FAILED": "Pi provider authentication is not configured.",
        "PI_MODEL_UNAVAILABLE": "Pi could not select the requested or default model.",
        "PI_RATE_LIMITED": "The Pi provider reported a rate limit.",
        "PI_QUOTA_EXCEEDED": "The Pi provider reported insufficient quota.",
        "PI_ABORTED": "Pi formatting was aborted.",
        "PI_TIMEOUT": "Pi formatting exceeded the chunk deadline.",
        "PI_OUTPUT_INCOMPLETE": "Pi output stopped before completion.",
        "PI_CONTEXT_LIMIT": "Pi input exceeded a context or chunk-planning limit.",
        "PI_CONTEXT_MUTATED": "Pi attempted to change or summarize source context; complete formatting cannot be verified.",
        "PI_PROTOCOL_INVALID": "Pi did not return a valid settled JSON completion.",
        "PI_OUTPUT_INVALID": "Pi returned an invalid Markdown body.",
        "PI_OUTPUT_LIMIT": "Pi output exceeded the configured safety bound.",
        "CHUNK_LIMIT_EXCEEDED": "Transcript exceeds the configured chunk cap.",
    }
    hints = {
        "PI_NOT_FOUND": "Install Pi or use --raw.",
        "PI_INCOMPATIBLE": "Upgrade to a compatible Pi release or use --raw.",
        "PI_LAUNCH_FAILED": "Check Pi installation and executable permissions or use --raw.",
        "PI_AUTH_FAILED": "Configure the provider credentials directly in Pi or use --raw.",
        "PI_MODEL_UNAVAILABLE": "Check the selected or saved default model in Pi or use --raw.",
        "PI_RATE_LIMITED": "Wait before another attempt or use --raw.",
        "PI_QUOTA_EXCEEDED": "Check provider billing and quota or use --raw.",
        "PI_CONTEXT_LIMIT": "Smaller pi.chunk_chars or a suitable model may help; smaller chunks increase calls. Or use --raw.",
        "PI_CONTEXT_MUTATED": "Review Pi/model compatibility. Smaller pi.chunk_chars may help but increase calls. Or use --raw.",
        "PI_OUTPUT_INCOMPLETE": "Reduce pi.chunk_chars in TOML, review the model choice, or use --raw.",
        "CHUNK_LIMIT_EXCEEDED": "Raise the chunk cap explicitly, or use raw/plain-text output.",
    }
    return FormattingError(
        ErrorInfo(
            code,
            messages.get(code, "Pi formatting failed."),
            hints.get(code, "Check Pi/provider/model setup or use --raw."),
            phase,
            code in ("PI_TIMEOUT", "PI_RATE_LIMITED"),
            chunk_index,
            chunk_total,
        )
    )


class WarningCollector:
    def __init__(self):
        self._warnings: list[str] = []
        self._size = 0

    def warning(self, message: str):
        text = str(message)[: max(0, 65536 - self._size)]
        self._size += len(text)
        if text:
            self._warnings.append(text)

    def debug(self, message: str):
        pass

    def error(self, message: str):
        self.warning(message)

    @property
    def access_limited(self) -> bool:
        return any(
            recognized_error(text, YOUTUBE_PATTERNS, youtube=True)
            == "YOUTUBE_ACCESS_LIMITED"
            for text in self._warnings
        )


def _is_formatting_failure(code: str) -> bool:
    return code.startswith("PI_") or code == "CHUNK_LIMIT_EXCEEDED"


def render_cli_error(exc: AppError) -> str:
    info = exc.info
    position = (
        f" (chunk {info.chunk_index}/{info.chunk_total})" if info.chunk_index else ""
    )
    result = f"error[{info.code}]: {info.message}{position}\n"
    if info.hint:
        result += f"hint: {info.hint}\n"
    if _is_formatting_failure(info.code):
        result += "warning: No Pi-processed transcript was returned. Retry with --raw for plain text without Pi.\n"
    return result


def render_mcp_error(info: ErrorInfo) -> str:
    position = ""
    if (
        type(info.chunk_index) is int
        and type(info.chunk_total) is int
        and 1 <= info.chunk_index <= info.chunk_total <= 100000
    ):
        position = f" (chunk {info.chunk_index}/{info.chunk_total})"
    # Adapt only trusted Pi recovery text, not unrelated hints such as --raw-vtt.
    formatting_failure = _is_formatting_failure(info.code)
    hint, message = info.hint, info.message
    if formatting_failure:
        hint = hint.replace("--raw", 'output_format="plain_text"') if hint else None
        message = message.replace("--raw", 'output_format="plain_text"')
    if info.code == "CHUNK_LIMIT_EXCEEDED":
        message = message.split("; use --preview", 1)[0]
        hint = 'Raise server pi.max_chunks explicitly, or request output_format="plain_text".'
    result = f"[{info.code}] {message}{position}" + (f"; hint: {hint}" if hint else "")
    if formatting_failure:
        result += '; warning: No Pi-processed transcript was returned. Retry get_transcript with output_format="plain_text" for plain text without Pi.'
    elif info.code == "MCP_TIMEOUT":
        result += '; warning: No transcript was returned. If Markdown was requested, retry with output_format="plain_text" to skip Pi.'
    return result


def decode_worker_error(payload: object) -> ErrorInfo:
    """Validate the private error envelope, never forward arbitrary child text."""
    if not isinstance(payload, dict) or set(payload) != set(
        ErrorInfo.__dataclass_fields__
    ):
        raise ValueError("Invalid worker error envelope")
    if payload["code"] not in CODES or payload["phase"] not in PHASES:
        raise ValueError("Invalid worker error code")
    for key in ("chunk_index", "chunk_total"):
        value = payload[key]
        if value is not None and (type(value) is not int or not 1 <= value <= 100000):
            raise ValueError("Invalid worker chunk position")
    index, total = payload["chunk_index"], payload["chunk_total"]
    if (index is None) != (total is None) or (index is not None and index > total):
        raise ValueError("Invalid worker chunk position")
    if type(payload["retryable"]) is not bool:
        raise ValueError("Invalid worker retry flag")
    messages = {
        "Expected a YouTube video URL.",
        "YouTube operation failed.",
        "Caption availability could not be fully verified.",
        "Expected one video result.",
        "Extracted video ID does not match the requested video.",
        "no English VTT subtitles found",
        "no English subtitles found",
        "empty transcript",
        "active livestreams are not supported",
        "video has not started",
        "livestream processing is incomplete; try again later",
        "Missing WebVTT header.",
        "Captions are not valid UTF-8.",
        "Deno is required for YouTube extraction.",
        "Deno or EJS setup is not compatible.",
        "MCP Markdown output requires POSIX process supervision.",
        "Document exceeds the MCP size limit.",
        "Result exceeds the MCP size limit.",
        "Invalid private worker request.",
        "Worker operation failed.",
    }
    message = payload["message"]
    if not isinstance(message, str) or (
        message not in messages
        and not re.fullmatch(
            r"Invalid (?:caption block|timing in block) [0-9]+\.", message
        )
    ):
        message = "Worker operation failed."
    hints = set(HINTS.values()) | {
        "Use an HTTP(S) watch, shorts, embed, or youtu.be URL.",
        "Check permitted access and supported yt-dlp/runtime setup.",
        "Check permitted browser access and supported runtime setup.",
        "No matching captions were returned; availability is not guaranteed.",
        "Use --raw-vtt to inspect captions separately.",
        "Install Deno >=2.3.0 and run --doctor.",
        "Install compatible Deno/EJS components and run --doctor.",
        "Use the deterministic CLI for larger transcripts.",
        "Use plain_text output on this platform.",
    }
    hint = (
        payload["hint"]
        if isinstance(payload["hint"], str) and payload["hint"] in hints
        else None
    )
    code = payload["code"]
    if _is_formatting_failure(code):
        safe = classify_pi_failure(code=code).info
        message, hint = safe.message, safe.hint
        if code == "CHUNK_LIMIT_EXCEEDED" and isinstance(payload["message"], str):
            counts = re.fullmatch(
                r"formatting requires ([1-9][0-9]{0,5}) (?:chunks|Pi calls), exceeding max-chunks "
                r"([1-9][0-9]{0,3}); use --preview, --raw, or explicitly raise the cap",
                payload["message"],
            )
            if counts:
                try:
                    required, cap = int(counts[1]), int(counts[2])
                except ValueError:
                    pass
                else:
                    if cap <= 1000 and cap < required <= 100000:
                        message = payload["message"]
    return ErrorInfo(
        code,
        message,
        hint,
        payload["phase"],
        payload["retryable"],
        payload["chunk_index"],
        payload["chunk_total"],
    )


def render_diagnostics(exc: AppError, **fields: Any) -> str:
    safe = {
        "code": exc.info.code if exc.info.code in CODES else "INTERNAL_ERROR",
        "phase": exc.info.phase if exc.info.phase in PHASES else "mcp_worker",
    }
    for key in ("chunk_index", "chunk_total"):
        value = getattr(exc.info, key)
        if value is not None:
            safe[key] = str(value)
    # Each field has a constrained vocabulary. Arbitrary caller text is discarded.
    for key in ("http_status", "retry_count", "line"):
        value = fields.get(key)
        if type(value) is int and 0 <= value <= 100000:
            safe[key] = str(value)
    for key in ("library_version", "pi_version"):
        value = fields.get(key)
        if isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", value):
            safe[key] = value
    value = fields.get("stop_reason")
    if value in (
        "stop",
        "length",
        "error",
        "aborted",
        "pending",
        "toolUse",
        "deferred",
    ):
        safe["stop_reason"] = value
    value = fields.get("errno")
    if type(value) is int and value in errno.errorcode:
        safe["errno"] = errno.errorcode[value]
    return "diagnostic: " + " ".join(f"{k}={v}" for k, v in safe.items()) + "\n"
