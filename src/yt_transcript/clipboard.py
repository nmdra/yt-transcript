"""Copy serialized output through an installed system clipboard command."""

import os
import shutil
import subprocess
import sys

from yt_transcript.errors import AppError, error


def _unavailable(hint: str) -> AppError:
    return error(
        "OUTPUT_FAILED",
        "The system clipboard is unavailable.",
        phase="output",
        hint=hint,
    )


def clipboard_command() -> list[str]:
    """Resolve a clipboard command before downloading or generating output."""
    if sys.platform == "darwin":
        if executable := shutil.which("pbcopy"):
            return [executable]
        raise _unavailable("Install or restore pbcopy, or omit --copy.")

    if sys.platform == "win32":
        executable = shutil.which("powershell.exe") or shutil.which("pwsh")
        if executable:
            return [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$ErrorActionPreference = 'Stop'; "
                "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false); "
                "$text = [Console]::In.ReadToEnd(); Set-Clipboard -Value $text",
            ]
        raise _unavailable("Install PowerShell, or omit --copy.")

    if sys.platform.startswith("linux"):
        if os.environ.get("WAYLAND_DISPLAY"):
            if executable := shutil.which("wl-copy"):
                return [executable, "--type", "text/plain;charset=utf-8"]
        if os.environ.get("DISPLAY"):
            if executable := shutil.which("xclip"):
                return [executable, "-selection", "clipboard"]
            if executable := shutil.which("xsel"):
                return [executable, "--clipboard", "--input"]
        if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
            raise _unavailable(
                "Run in a desktop session with WAYLAND_DISPLAY or DISPLAY set, "
                "or omit --copy."
            )
        raise _unavailable(
            "Install wl-clipboard for Wayland, or xclip or xsel for X11, "
            "or omit --copy."
        )

    raise _unavailable(
        "Use --copy on macOS, Windows, or a Linux desktop, or omit --copy."
    )


def copy_output(data: bytes, command: list[str]) -> None:
    """Copy exact output bytes without exposing child output or error details."""
    # pbcopy decodes stdin using the locale, not necessarily UTF-8.
    environment = None
    if sys.platform == "darwin":
        environment = {**os.environ, "LC_ALL": "en_US.UTF-8"}
    try:
        subprocess.run(
            command,
            input=data,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            env=environment,
            timeout=10,
            check=True,
        )
    except OSError, subprocess.SubprocessError:
        raise error(
            "OUTPUT_FAILED",
            "Could not copy output to the system clipboard.",
            phase="output",
            hint="Check that the desktop clipboard is available, or omit --copy.",
        ) from None
