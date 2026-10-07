"""Validated YouTube URLs and ranked English VTT tracks."""

import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from yt_dlp import YoutubeDL

from .chapters import snapshot_chapters
from .errors import (
    AppError,
    ErrorInfo,
    TranscriptError,
    WarningCollector,
    classify_ytdlp_error,
)
from .metadata import VideoMetadata, extract_video_metadata


@dataclass(frozen=True)
class CaptionTrack:
    language: str
    automatic: bool
    formats: tuple[dict[str, Any], ...]


def validate_youtube_url(url: str) -> str:
    def invalid():
        return TranscriptError(
            ErrorInfo(
                "INVALID_URL",
                "Expected a YouTube video URL.",
                "Use an HTTP(S) watch, shorts, embed, or youtu.be URL.",
                "config",
            )
        )

    if len(url) > 4096 or any(ord(c) <= 32 for c in url):
        raise invalid()
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            raise invalid()
        if parsed.hostname not in (
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
        ):
            raise invalid()
        if parsed.hostname == "youtu.be":
            video_id = parsed.path[1:]
        elif parsed.path == "/watch":
            ids = parse_qs(parsed.query).get("v", [])
            if len(ids) != 1:
                raise invalid()
            video_id = ids[0]
        else:
            match = re.fullmatch(
                r"/(?:shorts|embed)/([A-Za-z0-9_-]{11})/?", parsed.path
            )
            if not match:
                raise invalid()
            video_id = match[1]
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise invalid()
    except ValueError:
        raise invalid() from None
    return f"https://www.youtube.com/watch?v={video_id}"


def select_english_track(info: Mapping[str, Any]) -> CaptionTrack:
    candidates = []
    english = False
    for automatic, source in ((False, "subtitles"), (True, "automatic_captions")):
        tracks = info.get(source) or {}
        for language, formats in tracks.items():
            key = language.lower()
            if key != "en" and not key.startswith("en-"):
                continue
            english = True
            vtt = tuple(
                f for f in formats if isinstance(f, dict) and f.get("ext") == "vtt"
            )
            if not vtt:
                continue
            if not automatic:
                rank = 0 if key == "en" else 1
            elif key == "en-orig":
                rank = 2
            elif key.endswith("-orig"):
                rank = 3
            elif key == "en":
                rank = 4
            else:
                rank = 5
            candidates.append(
                (rank, key, language, CaptionTrack(language, automatic, vtt))
            )
    if not candidates:
        code = "NO_ENGLISH_VTT" if english else "NO_ENGLISH_CAPTIONS"
        message = (
            "no English VTT subtitles found"
            if english
            else "no English subtitles found"
        )
        raise TranscriptError(
            ErrorInfo(
                code,
                message,
                "No matching captions were returned; availability is not guaranteed.",
                "caption_select",
            )
        )
    return min(candidates, key=lambda candidate: candidate[:3])[3]


@dataclass(frozen=True)
class DownloadedCaptions:
    vtt: bytes
    language: str
    automatic: bool
    metadata: VideoMetadata


def retry_delay(n: int) -> int:
    # yt-dlp 2026.8.19 calls sleep_func with count - 1.
    return 2 ** min(max(n, 0), 2)


def ensure_deno() -> None:
    executable = shutil.which("deno")
    if not executable:
        raise TranscriptError(
            ErrorInfo(
                "RUNTIME_MISSING",
                "Deno is required for YouTube extraction.",
                "Install Deno >=2.3.0 and run --doctor.",
                "runtime_check",
            )
        )
    try:
        with TemporaryDirectory() as cwd:
            result = subprocess.run(
                [executable, "--version"],
                cwd=cwd,
                capture_output=True,
                timeout=5,
                check=False,
            )
        match = re.search(rb"deno (\d+)\.(\d+)\.(\d+)", result.stdout)
        if (
            result.returncode
            or not match
            or tuple(int(x) for x in match.groups()) < (2, 3, 0)
        ):
            raise ValueError
        from importlib.metadata import PackageNotFoundError, requires, version

        try:
            installed = version("yt-dlp-ejs")
            pins = [
                re.match(r"yt-dlp-ejs==([0-9.]+)(?:;|$)", requirement)
                for requirement in (requires("yt-dlp") or [])
            ]
            if any(pin and pin[1] != installed for pin in pins):
                raise ValueError
        except PackageNotFoundError:
            raise ValueError from None
    except OSError, ValueError, subprocess.TimeoutExpired:
        raise TranscriptError(
            ErrorInfo(
                "RUNTIME_INCOMPATIBLE",
                "Deno or EJS setup is not compatible.",
                "Install compatible Deno/EJS components and run --doctor.",
                "runtime_check",
            )
        ) from None


def download_english_vtt(url: str, *, verbose: bool = False) -> DownloadedCaptions:
    canonical = validate_youtube_url(url)
    ensure_deno()
    logger = WarningCollector()
    phase = "metadata_extract"
    with TemporaryDirectory(prefix="yt-transcript-") as directory:
        root = Path(directory).resolve()
        options = {
            # Extraction is process=False; these flags surface omitted-track warnings.
            # Only the selected source remains enabled at the processing/download step.
            "writesubtitles": True,
            "writeautomaticsub": True,
            "skip_download": True,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "logger": logger,
            "outtmpl": str(root / "captions.%(ext)s"),
            "subtitlesformat": "vtt",
            "cachedir": False,
            "remote_components": set(),
            "ignoreerrors": False,
            "postprocessors": [],
            "writethumbnail": False,
            "writeinfojson": False,
            "socket_timeout": 30,
            "retries": 3,
            "extractor_retries": 3,
            "retry_sleep_functions": {"http": retry_delay, "extractor": retry_delay},
        }
        try:
            with YoutubeDL(cast(Any, options)) as ydl:
                info: Any = ydl.extract_info(canonical, download=False, process=False)
                if not isinstance(info, dict) or info.get("_type", "video") != "video":
                    raise TranscriptError(
                        ErrorInfo(
                            "YOUTUBE_EXTRACT_FAILED",
                            "Expected one video result.",
                            phase=phase,
                        )
                    )
                messages = {
                    "is_live": "active livestreams are not supported",
                    "is_upcoming": "video has not started",
                    "post_live": "livestream processing is incomplete; try again later",
                }
                if info.get("live_status") in messages:
                    raise TranscriptError(
                        ErrorInfo(
                            "UNSUPPORTED_LIVESTREAM",
                            messages[info["live_status"]],
                            phase=phase,
                        )
                    )
                phase = "caption_select"
                try:
                    track = select_english_track(info)
                except TranscriptError:
                    if logger.access_limited:
                        raise TranscriptError(
                            ErrorInfo(
                                "YOUTUBE_ACCESS_LIMITED",
                                "Caption availability could not be fully verified.",
                                "Check permitted browser access and supported runtime setup.",
                                phase,
                            )
                        ) from None
                    raise
                chapter_input = snapshot_chapters(info.get("chapters"))
                narrowed = dict(info)
                narrowed.pop("chapters", None)
                narrowed["subtitles"] = (
                    {} if track.automatic else {track.language: list(track.formats)}
                )
                narrowed["automatic_captions"] = (
                    {track.language: list(track.formats)} if track.automatic else {}
                )
                ydl.params.update(
                    writesubtitles=not track.automatic,
                    writeautomaticsub=track.automatic,
                    subtitleslangs=["^" + re.escape(track.language) + "$"],
                )
                phase = "subtitle_download"
                processed = ydl.process_ie_result(cast(Any, narrowed), download=True)
                requested = processed.get("requested_subtitles") or {}
                if set(requested) != {track.language}:
                    raise ValueError
                selected = requested[track.language]
                path = Path(selected["filepath"])
                resolved = path.resolve(strict=True)
                if (
                    selected.get("ext") != "vtt"
                    or not resolved.is_relative_to(root)
                    or resolved.suffix.lower() != ".vtt"
                    or not resolved.is_file()
                ):
                    raise ValueError
                files = list(root.glob("*.vtt"))
                if len(files) != 1 or files[0].resolve() != resolved:
                    raise ValueError
                raw = resolved.read_bytes()
                if not raw:
                    raise ValueError
                metadata = extract_video_metadata(
                    processed, canonical_url=canonical, chapter_input=chapter_input
                )
                return DownloadedCaptions(
                    raw, track.language, track.automatic, metadata
                )
        except AppError:
            raise
        except Exception as exc:
            raise classify_ytdlp_error(exc, phase=phase) from None
