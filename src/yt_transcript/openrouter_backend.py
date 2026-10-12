"""One bounded OpenRouter completion, supervised without Pi or an HTTP SDK."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import TYPE_CHECKING

from .config import OpenRouterConfig
from .errors import FormattingError, classify_openrouter_failure, decode_worker_error
from .json_tools import strict_json_loads

if TYPE_CHECKING:
    from .formatter import ChunkRequest

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
INPUT_LIMIT = 1024 * 1024
HTTP_LIMIT = 2 * 1024 * 1024
TEXT_LIMIT = 1024 * 1024
HELPER_LIMIT = 8 * 1024 * 1024


def ensure_openrouter(model: str | None) -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if (
        not isinstance(model, str)
        or not model.strip()
        or len(model) > 4096
        or not key.strip()
        or not key.isascii()
        or any(ord(c) < 32 or ord(c) == 127 for c in key)
    ):
        raise classify_openrouter_failure(
            "OPENROUTER_NOT_CONFIGURED", phase="runtime_check"
        )


def validate_request(value: object) -> dict:
    fields = {
        "system_prompt",
        "append_system_prompt",
        "instruction",
        "source",
        "model",
        "timeout_seconds",
        "max_output_tokens",
    }
    if not isinstance(value, dict) or set(value) not in (
        fields,
        fields | {"thinking", "thinking_level"},
    ):
        raise ValueError("Invalid completion request.")
    for name in (
        "system_prompt",
        "append_system_prompt",
        "instruction",
        "source",
        "model",
    ):
        if not isinstance(value[name], str) or len(value[name]) > INPUT_LIMIT:
            raise ValueError("Invalid completion request.")
    if not value["model"].strip() or len(value["model"]) > 4096:
        raise ValueError("Invalid completion request.")
    for name, maximum in (("timeout_seconds", 3600), ("max_output_tokens", 131072)):
        if type(value[name]) is not int or not 1 <= value[name] <= maximum:
            raise ValueError("Invalid completion request.")
    thinking = value.get("thinking")
    level = value.get("thinking_level")
    if thinking is not None and type(thinking) is not bool:
        raise ValueError("Invalid completion request.")
    if thinking is True:
        if type(level) is not str or level not in ("low", "medium", "high"):
            raise ValueError("Invalid completion request.")
    elif level is not None:
        raise ValueError("Invalid completion request.")
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code, "Redirect rejected.", headers, fp
        )


def _status_failure(status: object) -> FormattingError:
    code = "OPENROUTER_FAILED"
    if type(status) is int:
        if status in (401, 403):
            code = "OPENROUTER_AUTH_FAILED"
        elif status in (402, 429):
            code = "OPENROUTER_LIMITED"
    return classify_openrouter_failure(code)


def parse_response(raw: bytes) -> str:
    try:
        if len(raw) > HTTP_LIMIT:
            raise ValueError
        data = strict_json_loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        if "error" in data:
            error = data["error"]
            raise _status_failure(
                error.get("code") if isinstance(error, dict) else None
            )
        choices = data["choices"]
        if (
            not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
        ):
            raise ValueError
        choice = choices[0]
        message = choice["message"]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError
        if (
            message.get("tool_calls")
            or message.get("function_call")
            or message.get("refusal")
        ):
            raise ValueError
        if choice.get("finish_reason") != "stop":
            raise classify_openrouter_failure("OPENROUTER_OUTPUT_INCOMPLETE")
        content = message["content"]
        if (
            not isinstance(content, str)
            or not content.strip()
            or len(content.encode("utf-8")) > TEXT_LIMIT
        ):
            raise ValueError
        return content.strip()
    except ValueError, UnicodeError, KeyError, TypeError:
        raise classify_openrouter_failure("OPENROUTER_OUTPUT_INVALID") from None


def complete_http(payload: dict) -> str:
    payload = validate_request(payload)
    ensure_openrouter(payload["model"])
    body = {
        "model": payload["model"],
        "stream": False,
        "max_tokens": payload["max_output_tokens"],
        "messages": [
            {
                "role": "system",
                "content": payload["system_prompt"]
                + "\n"
                + payload["append_system_prompt"],
            },
            {
                "role": "user",
                "content": payload["instruction"]
                + "\n\n<transcript_data>\n"
                + payload["source"]
                + "\n</transcript_data>",
            },
        ],
        "provider": {
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
        },
    }
    if payload.get("thinking") is not None:
        body["reasoning"] = {
            "enabled": payload["thinking"],
            "effort": payload["thinking_level"] if payload["thinking"] else "none",
            "exclude": True,
        }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    request.add_unredirected_header(
        "Authorization", "Bearer " + os.environ["OPENROUTER_API_KEY"].strip()
    )
    try:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=payload["timeout_seconds"]) as response:
            if response.status != 200:
                raise _status_failure(response.status)
            if (
                response.headers.get("Content-Encoding", "identity").lower()
                != "identity"
            ):
                raise classify_openrouter_failure("OPENROUTER_OUTPUT_INVALID")
            raw = bytearray()
            while len(raw) <= HTTP_LIMIT:
                block = response.read(min(8192, HTTP_LIMIT + 1 - len(raw)))
                if not block:
                    break
                raw.extend(block)
        return parse_response(bytes(raw))
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise _status_failure(status) from None
    except TimeoutError:
        raise classify_openrouter_failure("OPENROUTER_TIMEOUT") from None
    except urllib.error.URLError as exc:
        raise classify_openrouter_failure(
            "OPENROUTER_TIMEOUT"
            if isinstance(exc.reason, TimeoutError)
            else "OPENROUTER_FAILED"
        ) from None
    except OSError, ValueError, UnicodeError:
        raise classify_openrouter_failure() from None


def complete(request: ChunkRequest, config: OpenRouterConfig | None = None) -> str:
    from .formatter import terminate_child

    deadline = time.monotonic() + request.timeout_seconds
    ensure_openrouter(request.model)
    payload = asdict(request)
    payload.pop("own_process_group")
    payload["max_output_tokens"] = (config or OpenRouterConfig()).max_output_tokens
    try:
        validate_request(payload)
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(raw) > INPUT_LIMIT:
            raise ValueError
    except ValueError, UnicodeError:
        raise classify_openrouter_failure("OPENROUTER_CONTEXT_LIMIT") from None
    if time.monotonic() >= deadline:
        raise classify_openrouter_failure("OPENROUTER_TIMEOUT")
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "yt_transcript.openrouter_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix" and request.own_process_group,
        )
    except OSError:
        raise classify_openrouter_failure(phase="openrouter_start") from None
    assert (
        process.stdin is not None
        and process.stdout is not None
        and process.stderr is not None
    )
    failures: queue.SimpleQueue[BaseException] = queue.SimpleQueue()
    output = bytearray()
    stdin, stdout, stderr = process.stdin, process.stdout, process.stderr

    def reader(pipe, keep: bool):
        try:
            while block := pipe.read1(8192):
                if keep:
                    if len(output) + len(block) > HELPER_LIMIT:
                        raise classify_openrouter_failure("OPENROUTER_OUTPUT_INVALID")
                    output.extend(block)
                # Stderr is drained, never retained or displayed.
        except BaseException as exc:
            failures.put(exc)
        finally:
            pipe.close()

    def writer():
        try:
            stdin.write(raw)
            stdin.flush()
        except BrokenPipeError:
            pass
        except BaseException as exc:
            failures.put(exc)
        finally:
            stdin.close()

    threads = [
        threading.Thread(target=reader, args=(stdout, True), daemon=True),
        threading.Thread(target=reader, args=(stderr, False), daemon=True),
        threading.Thread(target=writer, daemon=True),
    ]
    try:
        for thread in threads:
            thread.start()
        while process.poll() is None or any(t.is_alive() for t in threads):
            if not failures.empty():
                exc = failures.get()
                if isinstance(exc, FormattingError):
                    raise exc
                raise classify_openrouter_failure("OPENROUTER_OUTPUT_INVALID")
            if time.monotonic() >= deadline:
                raise classify_openrouter_failure("OPENROUTER_TIMEOUT")
            time.sleep(0.01)
        if not failures.empty() or process.returncode:
            raise classify_openrouter_failure("OPENROUTER_OUTPUT_INVALID")
        try:
            envelope = strict_json_loads(output.decode("utf-8"))
            if not isinstance(envelope, dict):
                raise ValueError
            if set(envelope) == {"error"}:
                info = decode_worker_error(envelope["error"])
                if not info.code.startswith("OPENROUTER_"):
                    raise ValueError
                raise FormattingError(info)
            if set(envelope) != {"text"} or not isinstance(envelope["text"], str):
                raise ValueError
            text = envelope["text"]
            if not text.strip() or len(text.encode("utf-8")) > TEXT_LIMIT:
                raise ValueError
        except ValueError, UnicodeError, TypeError:
            raise classify_openrouter_failure("OPENROUTER_OUTPUT_INVALID") from None
        if time.monotonic() >= deadline:
            raise classify_openrouter_failure("OPENROUTER_TIMEOUT")
        return text
    finally:
        terminate_child(process, own_process_group=request.own_process_group)
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=2)
        output.clear()
