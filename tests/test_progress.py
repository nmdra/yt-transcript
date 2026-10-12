import io
import threading

import pytest

from yt_transcript.progress import TerminalProgress


def test_redirected_stderr_is_quiet():
    stream = io.StringIO()
    progress = TerminalProgress(stream)
    progress.stage("fetch")
    progress.chunks(1, 3)
    progress.close()
    assert stream.getvalue() == ""
    assert progress._thread is None


def test_terminal_spinner_bar_and_cleanup():
    stream = io.StringIO()
    progress = TerminalProgress(stream, enabled=True)
    progress.stage("fetch")
    progress.chunks(0, 3)
    progress.chunks(1, 3)
    progress.chunks(3, 3)
    progress.stage("output")
    progress.close()
    progress.close()
    text = stream.getvalue()
    assert "Fetching captions / filtering" in text
    assert "Model calls via pi 0/3" in text and "Model calls via pi 1/3" in text
    assert "[################] Model calls via pi 3/3" in text
    assert "Writing output" in text and "elapsed" in text
    assert progress._thread is not None and not progress._thread.is_alive()
    assert progress._width == 0


def test_warning_gets_its_own_line():
    stream = io.StringIO()
    progress = TerminalProgress(stream, enabled=True)
    progress.stage("fetch")
    progress.write_line("warning[SPONSORBLOCK_UNAVAILABLE]: source kept")
    progress.close()
    assert "warning[SPONSORBLOCK_UNAVAILABLE]: source kept\n" in stream.getvalue()


def test_dumb_terminal_is_quiet(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "dumb")
    progress = TerminalProgress(stream)
    progress.stage("fetch")
    progress.close()
    assert not stream.getvalue()


def test_progress_write_failure_does_not_fail_operation():
    class BrokenStream(io.StringIO):
        def write(self, value):
            raise OSError("private data")

    progress = TerminalProgress(BrokenStream(), enabled=True)
    progress.stage("fetch")
    progress.close()
    assert progress.enabled is False


def test_narrow_terminal(monkeypatch):
    import os

    stream = io.StringIO()
    monkeypatch.setattr(stream, "fileno", lambda: 2)
    monkeypatch.setattr(os, "get_terminal_size", lambda fd: os.terminal_size((20, 20)))
    progress = TerminalProgress(stream, enabled=True)
    progress.stage("fetch")
    progress.close()
    assert all(len(frame) <= 19 for frame in stream.getvalue().split("\r"))


@pytest.mark.parametrize("redraw", [False, True])
def test_terminal_shrink_clips_padding_and_cleanup(monkeypatch, redraw):
    import os

    columns = 80
    stream = io.StringIO()
    monkeypatch.setattr(stream, "fileno", lambda: 2)
    monkeypatch.setattr(
        os, "get_terminal_size", lambda fd: os.terminal_size((columns, 24))
    )
    progress = TerminalProgress(stream, enabled=True)
    progress._draw()
    stream.seek(0)
    stream.truncate()
    columns = 20
    if redraw:
        progress._draw()
    progress.close()
    assert all(len(frame) <= 19 for frame in stream.getvalue().split("\r"))
    assert progress._width == 0


def test_spinner_updates_while_operation_waits():
    changed = threading.Event()

    class RecordingStream(io.StringIO):
        def write(self, value):
            result = super().write(value)
            if len(self.getvalue().split("\r")) >= 3:
                changed.set()
            return result

    progress = TerminalProgress(RecordingStream(), enabled=True)
    progress.stage("fetch")
    try:
        assert changed.wait(2)
    finally:
        progress.close()


@pytest.mark.parametrize("failure,code", [(KeyboardInterrupt, 130), (RuntimeError, 1)])
def test_cli_failure_cleans_progress(monkeypatch, failure, code):
    from yt_transcript import cli, formatter, service

    monkeypatch.setattr(formatter, "ensure_pi", lambda: "pi")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(service, "fetch_clean_transcript", fail)
    stream = io.StringIO()
    monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(cli.sys, "stderr", stream)
    assert cli.main(["https://youtu.be/abcdefghijk", "--no-config"]) == code
    assert "elapsed" in stream.getvalue() and "error[" in stream.getvalue()


@pytest.mark.parametrize("provider", ["pi", "openrouter"])
def test_provider_label_in_spinner_and_count_bar(provider):
    stream = io.StringIO()
    progress = TerminalProgress(stream, enabled=True)
    progress.set_provider(provider)
    try:
        progress.stage("format")
        progress.chunks(1, 3)
    finally:
        progress.close()
    assert f"Model calls via {provider}" in stream.getvalue()
    assert f"Model calls via {provider} 1/3" in stream.getvalue()


@pytest.mark.parametrize(
    "saved,override,selected",
    [
        ("pi", "openrouter", "openrouter"),
        ("openrouter", "pi", "pi"),
        ("openrouter", None, "openrouter"),
    ],
)
def test_cli_progress_uses_resolved_provider(
    tmp_path, monkeypatch, saved, override, selected
):
    from yt_transcript import cli

    config = tmp_path / "config.toml"
    config.write_text(f'[formatting]\nprovider="{saved}"\nmodel="synthetic/model"\n')
    stream = io.StringIO()
    monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(cli.sys, "stderr", stream)

    def transcribe(args, config, progress):
        progress.stage("format")
        progress.chunks(1, 2)

    monkeypatch.setattr(cli, "_transcribe", transcribe)
    args = ["https://youtu.be/abcdefghijk", "--config", str(config)]
    if override is not None:
        args += ["--provider", override]
    assert cli.main(args) == 0
    assert f"Model calls via {selected} 1/2" in stream.getvalue()
