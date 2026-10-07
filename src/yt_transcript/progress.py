"""Best-effort terminal progress, separate from document and protocol output."""

import os
import threading
import time
from typing import Literal, TextIO

Stage = Literal["fetch", "format", "output"]
LABELS: dict[Stage, str] = {
    "fetch": "Fetching captions / filtering",
    "format": "Pi chunks",
    "output": "Writing output",
}


class TerminalProgress:
    def __init__(self, stream: TextIO, *, enabled: bool | None = None):
        self.stream = stream
        if enabled is None:
            try:
                enabled = stream.isatty() and os.environ.get("TERM") != "dumb"
            except AttributeError, OSError, ValueError:
                enabled = False
        self.enabled = enabled
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stage: Stage = "fetch"
        self._completed = 0
        self._total = 0
        self._started = 0.0
        self._frame = 0
        self._width = 0

    def stage(self, stage: Stage) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._stage = stage
            if self._thread is None and not self._stop.is_set():
                self._started = time.monotonic()
                self._thread = threading.Thread(target=self._animate, daemon=True)
                self._thread.start()
            self._draw()

    def chunks(self, completed: int, total: int) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._stage = "format"
            self._completed, self._total = completed, total
            self._draw()

    def write_line(self, text: str) -> None:
        with self._lock:
            self._clear()
            self.stream.write(text + "\n")
            self.stream.flush()
            if self.enabled and self._thread is not None:
                self._draw()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        with self._lock:
            self._clear()
            self.enabled = False

    def _animate(self) -> None:
        while not self._stop.wait(0.1):
            with self._lock:
                if self.enabled:
                    self._draw()

    def _draw(self) -> None:
        try:
            elapsed = max(0, int(time.monotonic() - self._started))
        except ValueError, OverflowError:
            self.enabled = False
            return
        minutes, seconds = divmod(elapsed, 60)
        spinner = "|/-\\"[self._frame % 4]
        self._frame += 1
        if self._stage == "format" and self._total:
            filled = 16 * self._completed // self._total
            bar = "#" * filled + "-" * (16 - filled)
            label = f"[{bar}] Pi chunks {self._completed}/{self._total}"
        else:
            label = f"{spinner} {LABELS[self._stage]}"
        text = f"{label} | {minutes:02}:{seconds:02} elapsed"
        try:
            try:
                columns = os.get_terminal_size(self.stream.fileno()).columns
            except AttributeError, OSError, ValueError:
                columns = 80
            text = text[: max(0, columns - 1)]
            width = max(self._width, len(text))
            self.stream.write("\r" + text.ljust(width))
            self.stream.flush()
            self._width = len(text)
        except OSError, ValueError:
            self.enabled = False

    def _clear(self) -> None:
        if self._width:
            try:
                self.stream.write("\r" + " " * self._width + "\r")
                self.stream.flush()
            except OSError, ValueError:
                self.enabled = False
            self._width = 0
