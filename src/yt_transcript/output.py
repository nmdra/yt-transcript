"""Atomic completed-file publication, including no-replace hard links."""

import os
import sys
import tempfile
from pathlib import Path

from .errors import AppError, ErrorInfo


def validate_output(path: Path, *, no_clobber: bool = False) -> None:
    if not path.parent.is_dir():
        raise AppError(
            ErrorInfo(
                "OUTPUT_FAILED", "Output parent directory must exist.", phase="output"
            )
        )
    if no_clobber and os.path.lexists(path):
        raise AppError(
            ErrorInfo(
                "OUTPUT_EXISTS",
                "Output destination already exists.",
                "Choose another output path.",
                "output",
            )
        )
    if path.is_dir():
        raise AppError(
            ErrorInfo(
                "OUTPUT_FAILED", "Output destination is a directory.", phase="output"
            )
        )
    # Check usability without opening or truncating the final name.
    try:
        writable = os.access(path.parent, os.W_OK)
    except OSError:
        writable = False
    if not writable:
        raise AppError(
            ErrorInfo(
                "OUTPUT_FAILED",
                "Output parent directory is not writable.",
                phase="output",
            )
        )


def write_output(path: Path, data: bytes, *, no_clobber: bool = False) -> None:
    validate_output(path, no_clobber=no_clobber)
    temporary: Path | None = None
    committed = False
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
        if no_clobber:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
            temporary = None
        committed = True
    except FileExistsError:
        raise AppError(
            ErrorInfo(
                "OUTPUT_EXISTS",
                "Output destination already exists.",
                "Choose another output path.",
                "output",
            )
        ) from None
    except OSError:
        raise AppError(
            ErrorInfo(
                "OUTPUT_FAILED",
                "Could not publish output.",
                "Check permissions, free space, and hard-link support for --no-clobber.",
                "output",
            )
        ) from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                if committed:
                    sys.stderr.write(
                        "warning: Output was published, but temporary-file cleanup failed.\n"
                    )
