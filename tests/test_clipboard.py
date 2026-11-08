import subprocess
from unittest.mock import Mock

import pytest

from yt_transcript import clipboard
from yt_transcript.errors import AppError


@pytest.fixture
def platform_tools(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    available = set()
    which = Mock(
        side_effect=lambda name: f"/tools/{name}" if name in available else None
    )
    monkeypatch.setattr(clipboard.shutil, "which", which)
    return available, which


@pytest.mark.parametrize(
    ("platform", "tool", "arguments"),
    [
        ("darwin", "pbcopy", []),
        ("linux", "wl-copy", ["--type", "text/plain;charset=utf-8"]),
        ("linux", "xclip", ["-selection", "clipboard"]),
        ("linux", "xsel", ["--clipboard", "--input"]),
    ],
)
def test_platform_selection(monkeypatch, platform_tools, platform, tool, arguments):
    available, _ = platform_tools
    available.add(tool)
    monkeypatch.setattr(clipboard.sys, "platform", platform)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    assert clipboard.clipboard_command() == [f"/tools/{tool}", *arguments]


def test_wayland_preferred_over_x11(monkeypatch, platform_tools):
    available, which = platform_tools
    available.update({"wl-copy", "xclip", "xsel"})
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    assert clipboard.clipboard_command() == [
        "/tools/wl-copy",
        "--type",
        "text/plain;charset=utf-8",
    ]
    which.assert_called_once_with("wl-copy")


def test_xclip_preferred_over_xsel(monkeypatch, platform_tools):
    available, _ = platform_tools
    available.update({"xclip", "xsel", "wl-copy"})
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    assert clipboard.clipboard_command() == ["/tools/xclip", "-selection", "clipboard"]


@pytest.mark.parametrize("tool", ["powershell.exe", "pwsh"])
def test_windows_reads_utf8_stdin(monkeypatch, platform_tools, tool):
    available, _ = platform_tools
    available.add(tool)
    monkeypatch.setattr(clipboard.sys, "platform", "win32")
    command = clipboard.clipboard_command()
    assert command[0] == f"/tools/{tool}"
    assert "-NoProfile" in command
    assert "-NonInteractive" in command
    assert command[-2] == "-Command"
    assert "$ErrorActionPreference = 'Stop'" in command[-1]
    assert (
        "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)"
        in command[-1]
    )
    assert "[Console]::In.ReadToEnd()" in command[-1]
    assert "Set-Clipboard -Value $text" in command[-1]


@pytest.mark.parametrize(
    ("platform", "environment", "hint"),
    [
        ("darwin", {}, "pbcopy"),
        ("win32", {}, "PowerShell"),
        ("linux", {}, "desktop session"),
        ("linux", {"WAYLAND_DISPLAY": "wayland-0"}, "wl-clipboard"),
        ("linux", {"DISPLAY": ":0"}, "xclip"),
        ("freebsd14", {}, "macOS, Windows, or a Linux desktop"),
    ],
)
def test_unavailable_has_safe_actionable_error(
    monkeypatch, platform_tools, platform, environment, hint
):
    monkeypatch.setattr(clipboard.sys, "platform", platform)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(AppError) as caught:
        clipboard.clipboard_command()
    info = caught.value.info
    assert info.code == "OUTPUT_FAILED"
    assert info.phase == "output"
    assert info.hint is not None
    assert hint in info.hint
    assert "omit --copy" in info.hint


@pytest.mark.parametrize("environment", [{}, {"DISPLAY": ""}, {"WAYLAND_DISPLAY": ""}])
def test_installed_tools_require_display(monkeypatch, platform_tools, environment):
    available, which = platform_tools
    available.update({"wl-copy", "xclip", "xsel"})
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(AppError, match="clipboard is unavailable"):
        clipboard.clipboard_command()
    which.assert_not_called()


def test_copy_passes_exact_unicode_bytes_and_suppresses_child_output(monkeypatch):
    run = Mock()
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(clipboard.subprocess, "run", run)
    data = "日本語 café 😀\n\n".encode()
    command = ["/tools/wl-copy"]
    clipboard.copy_output(data, command)
    run.assert_called_once_with(
        command,
        input=data,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        env=None,
        timeout=10,
        check=True,
    )


def test_macos_forces_utf8_locale_and_preserves_environment(monkeypatch):
    run = Mock()
    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    monkeypatch.setattr(clipboard.subprocess, "run", run)
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("CLIPBOARD_TEST", "preserved")
    data = "日本語 café 😀\n".encode()
    clipboard.copy_output(data, ["/usr/bin/pbcopy"])
    options = run.call_args.kwargs
    assert options["input"] == data
    assert options["env"]["LC_ALL"] == "en_US.UTF-8"
    assert options["env"]["CLIPBOARD_TEST"] == "preserved"
    assert clipboard.os.environ["LC_ALL"] == "C"


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CalledProcessError(
            1, ["secret"], output=b"private transcript", stderr=b"private stderr"
        ),
        OSError("private transcript"),
        subprocess.TimeoutExpired(["secret"], 10, output=b"private transcript"),
    ],
)
def test_process_failure_is_safe(monkeypatch, failure):
    monkeypatch.setattr(clipboard.subprocess, "run", Mock(side_effect=failure))
    with pytest.raises(AppError) as caught:
        clipboard.copy_output(b"private transcript", ["/tools/wl-copy"])
    info = caught.value.info
    assert info.code == "OUTPUT_FAILED"
    assert info.phase == "output"
    assert info.hint is not None
    assert "omit --copy" in info.hint
    assert "private" not in str(caught.value)
    assert "secret" not in repr(info)
    assert caught.value.__suppress_context__ is True
