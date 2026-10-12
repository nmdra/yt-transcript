import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from yt_transcript.errors import AppError
from yt_transcript.mcp_server import WorkerRunner
from yt_transcript.mcp_worker import RESULT_LIMIT, validate_request
from yt_transcript.metadata import VideoMetadata
from yt_transcript.service import CleanedTranscript


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "pi"},
        {"operation": []},
        {"operation": {}},
        {"operation": "doctor", "path": "private"},
        {"operation": "get_transcript", "url": "https://example.com"},
        {
            "operation": "get_transcript",
            "url": "https://youtu.be/abcdefghijk",
            "model": "x",
        },
    ],
)
def test_requests(payload):
    with pytest.raises((ValueError, AppError)):
        validate_request(payload)


@pytest.mark.parametrize("markdown", [False, True])
def test_dispatch_uses_explicit_formatting_options(monkeypatch, markdown):
    from dataclasses import asdict

    from yt_transcript import service
    from yt_transcript.mcp_policy import MCPFormattingPolicy
    from yt_transcript.mcp_worker import dispatch
    from yt_transcript.sponsorblock import SponsorBlockConfig

    request = {
        "operation": "get_transcript",
        "url": "https://youtu.be/abcdefghijk",
        "mode": "full",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
    }
    policy = MCPFormattingPolicy()
    if markdown:
        request.update(output_format="markdown", formatting=asdict(policy))
    captured = []
    expected = {"document": "body"}

    def fetch(url, mode, **kwargs):
        captured.append((url, mode, kwargs))
        return expected

    monkeypatch.setattr(service, "fetch_transcript_document", fetch)
    assert dispatch(validate_request(request)) is expected
    from yt_transcript.mcp_worker import report_progress
    from yt_transcript.transcript_cache import TranscriptCache

    assert isinstance(captured[0][2].pop("cache"), TranscriptCache)
    if markdown:
        assert captured[0][2].pop("on_progress") is report_progress
    assert captured == [
        (
            request["url"],
            "full",
            {
                "sponsorblock": SponsorBlockConfig(
                    enabled=False, categories=("sponsor",), timeout_seconds=10
                ),
                "output_format": "markdown" if markdown else "plain_text",
                "formatting": policy if markdown else None,
                "supervised": markdown,
            },
        )
    ]


def test_real_worker_invalid_request():
    result = subprocess.run(
        [sys.executable, "-m", "yt_transcript.mcp_worker"],
        input=b'{"operation":"pi","token":"secret"}',
        capture_output=True,
        timeout=5,
    )
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "CONFIG_INVALID"
    assert b"secret" not in result.stdout and not result.stderr


def install_child(tmp_path, monkeypatch, code):
    script = tmp_path / "child.py"
    script.write_text(code)
    original = asyncio.create_subprocess_exec
    processes = []

    async def launch(*args, **kwargs):
        process = await original(sys.executable, str(script), **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    return processes


def test_timeout_cancellation_cleanup_and_reuse(tmp_path, monkeypatch):
    marker = tmp_path / "marker"
    code = f"""import sys,time,signal
from tempfile import TemporaryDirectory
from pathlib import Path
def stop(*args): raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
    with TemporaryDirectory() as root:
        Path({str(marker)!r}).write_text(root)
        sys.stdin.buffer.read()
        sys.stderr.write('private' * 20000)
        sys.stderr.flush()
        time.sleep(30)
except KeyboardInterrupt: pass
"""
    processes = install_child(tmp_path, monkeypatch, code)

    async def check():
        runner = WorkerRunner(timeout_seconds=0.3)
        with pytest.raises(AppError) as exc:
            await runner.run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                }
            )
        assert exc.value.info.code == "MCP_TIMEOUT"
        assert processes[0].returncode is not None
        assert not Path(marker.read_text()).exists()
        runner.timeout_seconds = 10
        task = asyncio.create_task(
            runner.run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                }
            )
        )
        while len(processes) < 2:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        with pytest.raises(AppError) as exc:
            await runner.run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                }
            )
        assert exc.value.info.code == "MCP_BUSY"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[-1].returncode is not None
        assert not Path(marker.read_text()).exists()
        assert not runner._busy

    asyncio.run(check())


def test_markdown_cap_error_survives_worker_transport(tmp_path, monkeypatch):
    from dataclasses import asdict

    from yt_transcript.mcp_policy import MCPFormattingPolicy

    install_child(
        tmp_path,
        monkeypatch,
        "import json,sys\nfrom dataclasses import asdict\n"
        "from yt_transcript.errors import AppError\n"
        "from yt_transcript.formatter import format_with_pi\n"
        "sys.stdin.buffer.read()\n"
        "try: format_with_pi('word '*1000,chunk_chars=1000,max_chunks=3)\n"
        "except AppError as exc: print(json.dumps({'error':asdict(exc.info)}))\n",
    )

    async def check():
        with pytest.raises(AppError) as exc:
            await WorkerRunner().run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                    "output_format": "markdown",
                    "formatting": asdict(MCPFormattingPolicy(chunk_chars=1000)),
                }
            )
        assert exc.value.info.code == "CHUNK_LIMIT_EXCEEDED"
        assert "requires 5 chunks, exceeding max-chunks 3" in exc.value.info.message
        assert (
            exc.value.info.hint
            == "Raise the chunk cap explicitly, or use raw/plain-text output."
        )

    asyncio.run(check())


@pytest.mark.parametrize(
    "markdown,limit,fails",
    [(False, 2, True), (True, 2, False), (True, 0.05, True), (True, None, True)],
)
def test_format_specific_deadline(tmp_path, monkeypatch, markdown, limit, fails):
    from dataclasses import asdict

    from yt_transcript.mcp_policy import MCPFormattingPolicy

    processes = install_child(
        tmp_path,
        monkeypatch,
        "import json,sys,time\nrequest=json.load(sys.stdin)\ntime.sleep(0.2)\nprint(json.dumps({'result':{'document':'body'}}))\n",
    )
    request = {
        "operation": "get_transcript",
        "url": "https://youtu.be/abcdefghijk",
        "mode": "full",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
    }
    if markdown:
        request.update(
            output_format="markdown", formatting=asdict(MCPFormattingPolicy())
        )

    async def check():
        runner = WorkerRunner(timeout_seconds=0.05, markdown_timeout_seconds=limit)
        if fails:
            with pytest.raises(AppError) as exc:
                await runner.run(request)
            assert exc.value.info.code == "MCP_TIMEOUT"
            assert exc.value.info.hint is not None
            assert "total worker deadline" in exc.value.info.hint
        else:
            assert await runner.run(request) == {"document": "body"}
        assert all(p.returncode is not None for p in processes)
        assert not runner._busy
        runner.timeout_seconds = 2
        runner.markdown_timeout_seconds = 2
        assert await runner.run(request) == {"document": "body"}

    asyncio.run(check())


@pytest.mark.parametrize(
    "unit,repeats,limit_stage",
    [
        ('😀\n\\"', 1000, None),
        ("x", RESULT_LIMIT, "private"),
        ("😀", 60000, "public"),
        ('\n\\"', 90000, "public"),
    ],
    ids=["fits", "private-envelope", "public-unicode", "public-escaping"],
)
def test_description_result_limits_and_reuse(
    tmp_path, monkeypatch, caplog, unit, repeats, limit_stage
):
    description = "MCP_SIZE_DESCRIPTION_SENTINEL" + unit * repeats
    cleaned = CleanedTranscript(
        "body",
        VideoMetadata(
            "https://www.youtube.com/watch?v=abcdefghijk",
            "abcdefghijk",
            description=description,
        ),
        "en",
        False,
    )
    result = {
        "format": "plain_text",
        "document": "body",
        "metadata": cleaned.mapping(),
        "character_count": 4,
    }
    envelope_size = len(
        json.dumps({"result": result}, ensure_ascii=False).encode("utf-8")
    )
    compatibility = json.dumps(result, ensure_ascii=False)
    public_size = len(
        json.dumps(
            {
                "structuredContent": result,
                "content": [{"type": "text", "text": compatibility}],
            }
        ).encode("utf-8")
    )
    if limit_stage == "private":
        assert envelope_size > RESULT_LIMIT
    else:
        assert envelope_size < RESULT_LIMIT
        assert (public_size > RESULT_LIMIT) == (limit_stage == "public")
    processes = install_child(
        tmp_path,
        monkeypatch,
        "import json\nfrom yt_transcript import mcp_worker as worker\n"
        f"result = json.loads({json.dumps(result, ensure_ascii=False)!r})\n"
        "def dispatch(request):\n"
        "    if request['mode'] == 'filtered':\n"
        "        result['metadata']['description'] = 'Recovered description'\n"
        "    return result\n"
        "worker.dispatch = dispatch\nraise SystemExit(worker.main())\n",
    )
    request = {
        "operation": "get_transcript",
        "url": "https://youtu.be/abcdefghijk",
        "mode": "full",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
    }

    async def check():
        runner = WorkerRunner(timeout_seconds=5)
        if limit_stage:
            with pytest.raises(AppError) as exc:
                await runner.run(request)
            assert exc.value.info.code == "MCP_RESPONSE_LIMIT"
            assert "MCP_SIZE_DESCRIPTION_SENTINEL" not in str(exc.value)
            expected_message = (
                "Result exceeds the MCP size limit."
                if limit_stage == "private"
                else "Tool result exceeds the MCP size limit."
            )
            assert exc.value.info.message == expected_message
        else:
            returned = await runner.run(request)
            assert returned == result
            assert returned["metadata"]["description"] == description
        assert len(processes) == 1 and processes[0].returncode == 0
        assert not runner._busy and runner._process is None
        recovered = await runner.run({**request, "mode": "filtered"})
        assert recovered["document"] == "body"
        assert recovered["metadata"]["description"] == "Recovered description"
        assert len(processes) == 2 and processes[1].returncode == 0
        assert not runner._busy and runner._process is None

    asyncio.run(check())
    assert "MCP_SIZE_DESCRIPTION_SENTINEL" not in caplog.text


def test_response_limit_reaps(tmp_path, monkeypatch):
    processes = install_child(
        tmp_path,
        monkeypatch,
        "import sys,time\nsys.stdin.buffer.read()\nsys.stdout.buffer.write(b'x' * 1200000)\nsys.stdout.flush()\ntime.sleep(30)\n",
    )

    async def check():
        with pytest.raises(AppError) as exc:
            await WorkerRunner(timeout_seconds=5).run(
                {
                    "operation": "get_transcript",
                    "url": "https://youtu.be/abcdefghijk",
                    "mode": "full",
                    "sponsorblock": {
                        "enabled": False,
                        "categories": ["sponsor"],
                        "timeout_seconds": 10,
                    },
                }
            )
        assert exc.value.info.code == "MCP_RESPONSE_LIMIT"
        assert processes[0].returncode is not None

    asyncio.run(check())


def test_progress_parser_bounds_and_monotonicity():
    async def check():
        pipe = asyncio.StreamReader()
        records = []

        async def progress(done, total):
            records.append((done, total))

        def record(done, total=4, **extra):
            return (
                b"YT_PROGRESS\t"
                + json.dumps(
                    {"done": done, "total": total, "stage": "formatting", **extra}
                ).encode()
                + b"\n"
            )

        pipe.feed_data(b"PRIVATE_NOISE" * 100000 + b"\n")
        pipe.feed_data(record(0) + record(1) + record(1) + record(0))
        pipe.feed_data(record(True) + record(2, total=5) + record(2, secret="PRIVATE"))
        pipe.feed_data(
            b'YT_PROGRESS\t{"done":2,"done":3,"total":4,"stage":"formatting"}\n'
        )
        pipe.feed_data(b"YT_PROGRESS\t" + b"x" * 1000 + b"\n")
        pipe.feed_data(record(2) + record(4) + b"unfinished")
        pipe.feed_eof()
        await WorkerRunner()._read_progress(pipe, progress)
        assert records == [(0, 4), (1, 4), (2, 4), (4, 4)]

    asyncio.run(check())


def test_progress_budget_and_optional_callback_failure(caplog):
    async def check():
        records = []

        async def progress(done, total):
            records.append(done)

        pipe = asyncio.StreamReader()
        for i in range(3000):
            pipe.feed_data(
                b"YT_PROGRESS\t"
                + json.dumps({"done": i, "total": 3000, "stage": "formatting"}).encode()
                + b"\n"
            )
        pipe.feed_eof()
        await WorkerRunner()._read_progress(pipe, progress)
        assert 0 < len(records) < 3000
        calls = []

        async def fail(done, total):
            calls.append(done)
            raise RuntimeError("PRIVATE_PROGRESS_TRANSPORT")

        pipe = asyncio.StreamReader()
        pipe.feed_data(
            b'YT_PROGRESS\t{"done":0,"total":2,"stage":"formatting"}\nYT_PROGRESS\t{"done":1,"total":2,"stage":"formatting"}\n'
        )
        pipe.feed_eof()
        await WorkerRunner()._read_progress(pipe, fail)
        assert calls == [0]

    asyncio.run(check())
    assert "PRIVATE_PROGRESS_TRANSPORT" not in caplog.text


def test_progress_callback_timeout_reaps_worker(tmp_path, monkeypatch):
    processes = install_child(
        tmp_path,
        monkeypatch,
        'import sys,time\nsys.stdin.buffer.read()\nsys.stderr.write(\'YT_PROGRESS\\t{"done":0,"total":1,"stage":"formatting"}\\n\');sys.stderr.flush()\ntime.sleep(30)\n',
    )

    async def check():
        async def slow(done, total):
            await asyncio.sleep(30)

        request = {
            "operation": "get_transcript",
            "url": "https://youtu.be/abcdefghijk",
            "mode": "full",
            "sponsorblock": {
                "enabled": False,
                "categories": ["sponsor"],
                "timeout_seconds": 10,
            },
        }
        runner = WorkerRunner(timeout_seconds=0.1)
        with pytest.raises(AppError) as exc:
            await runner.run(request, on_progress=slow)
        assert exc.value.info.code == "MCP_TIMEOUT"
        assert not runner._busy and runner._process is None
        assert processes[0].returncode is not None

    asyncio.run(check())


@pytest.mark.parametrize(
    "operation,extra,code",
    [
        (
            "get_transcript_segment",
            {"start_seconds": True, "end_seconds": 4},
            "SEGMENT_RANGE_INVALID",
        ),
        (
            "get_transcript_segment",
            {"start_seconds": 0, "end_seconds": 901},
            "SEGMENT_RANGE_INVALID",
        ),
        (
            "search_transcript",
            {"query": " ", "max_results": 10},
            "SEARCH_QUERY_INVALID",
        ),
        (
            "search_transcript",
            {"query": "x", "max_results": True},
            "SEARCH_QUERY_INVALID",
        ),
        (
            "get_transcript_page",
            {"cursor": "private", "max_chars": 1000},
            "CACHE_CURSOR_INVALID",
        ),
        ("get_transcript_page", {"cursor": None, "max_chars": True}, "CONFIG_INVALID"),
    ],
)
def test_retrieval_request_rejects_invalid_parameters(operation, extra, code):
    request = {
        "operation": operation,
        "url": "https://youtu.be/abcdefghijk",
        "mode": "filtered",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
        **extra,
    }
    with pytest.raises(AppError) as exc:
        validate_request(request)
    assert exc.value.info.code == code


def test_private_policy_accepts_only_complete_legacy_or_new_shapes():
    from dataclasses import asdict

    from yt_transcript.mcp_policy import MCPFormattingPolicy, validate_formatting_policy

    current = asdict(MCPFormattingPolicy())
    new_fields = {"deepseek_max_output_tokens", "thinking", "thinking_level"}
    legacy = {key: value for key, value in current.items() if key not in new_fields}
    assert len(legacy) == 8 and len(current) == 11
    assert validate_formatting_policy(legacy) == MCPFormattingPolicy()
    assert validate_formatting_policy(current) == MCPFormattingPolicy()
    for key in new_fields:
        with pytest.raises(ValueError):
            validate_formatting_policy({**legacy, key: current[key]})
        with pytest.raises(ValueError):
            validate_formatting_policy({k: v for k, v in current.items() if k != key})
    with pytest.raises(ValueError):
        validate_formatting_policy({**current, "api_key": "PRIVATE"})


def test_dispatch_preserves_optional_thinking_controls(monkeypatch):
    from dataclasses import asdict

    from yt_transcript import service
    from yt_transcript.mcp_policy import MCPFormattingPolicy
    from yt_transcript.mcp_worker import dispatch

    policy = MCPFormattingPolicy(
        provider="deepseek",
        model="model",
        editorial_mode="summarized",
        deepseek_max_output_tokens=393216,
        thinking_level="high",
    )
    request = {
        "operation": "get_transcript",
        "url": "https://youtu.be/abcdefghijk",
        "mode": "full",
        "sponsorblock": {
            "enabled": False,
            "categories": ["sponsor"],
            "timeout_seconds": 10,
        },
        "output_format": "markdown",
        "formatting": asdict(policy),
    }
    captured = []
    monkeypatch.setattr(
        service,
        "fetch_transcript_document",
        lambda *args, **kwargs: captured.append(kwargs) or {"document": "body"},
    )
    dispatch(validate_request(request))
    assert captured[0]["formatting"] == policy
    assert captured[0]["formatting"].thinking is None
    assert not {"thinking", "thinking_level", "deepseek"} & captured[0].keys()
