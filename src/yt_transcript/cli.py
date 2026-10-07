"""Command-line orchestration. Stdout receives only completed output."""

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

from . import __version__
from .config import AppConfig, load_config, resolve_config
from .errors import AppError, ErrorInfo, render_cli_error, render_diagnostics
from .progress import TerminalProgress


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Argparse's default message can echo secrets from arbitrary argv values.
        raise _invalid("Invalid command-line arguments. Use --help.")


def _parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(description="English YouTube transcript processor")
    parser.add_argument("url", nargs="?")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--mcp", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--no-clobber", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--raw", dest="mode", action="store_const", const="raw")
    modes.add_argument("--raw-vtt", dest="mode", action="store_const", const="raw-vtt")
    parser.add_argument("--model")
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--editorial-mode", choices=("standard", "focused"))
    sponsor = parser.add_mutually_exclusive_group()
    sponsor.add_argument("--sponsorblock", action="store_true", default=None)
    sponsor.add_argument("--no-sponsorblock", dest="sponsorblock", action="store_false")
    configs = parser.add_mutually_exclusive_group()
    configs.add_argument("--config", type=Path)
    configs.add_argument("--no-config", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true", default=None)
    return parser


def _invalid(message: str) -> AppError:
    return AppError(ErrorInfo("CONFIG_INVALID", message, phase="config"))


def _emit(data: bytes) -> None:
    # Real stdout uses explicit UTF-8 bytes, independent of terminal locale.
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        buffer.flush()
    else:
        sys.stdout.write(data.decode("utf-8"))
        sys.stdout.flush()


def _broken_pipe_exit() -> int:
    # Prevent a second failing flush and traceback during interpreter shutdown.
    try:
        descriptor = sys.stdout.fileno()
        null = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null, descriptor)
        finally:
            os.close(null)
    except AttributeError, OSError, ValueError:
        pass
    return 1


def _transcribe(
    args: argparse.Namespace, config: AppConfig, progress: TerminalProgress
) -> None:
    verbose = config.verbose
    if not args.url:
        raise _invalid("A YouTube video URL is required.")
    from .downloader import download_english_vtt, validate_youtube_url
    from .formatter import ensure_pi, format_with_pi, plan_transcript_formatting
    from .output import validate_output, write_output
    from .service import fetch_clean_transcript

    canonical = validate_youtube_url(args.url)
    if args.no_clobber and args.output is None:
        raise _invalid("--no-clobber requires --output.")
    if config.mode != "markdown" and (
        args.model is not None
        or args.max_chunks is not None
        or args.editorial_mode is not None
    ):
        raise _invalid("Explicit formatter flags require Markdown mode.")
    if args.preview and (
        config.mode != "markdown" or args.output is not None or args.no_clobber
    ):
        raise _invalid("--preview requires Markdown mode and no output path.")
    if args.output:
        validate_output(args.output, no_clobber=args.no_clobber)
    if config.mode == "markdown" and not args.preview:
        ensure_pi()
    if config.mode == "raw-vtt" and args.sponsorblock:
        raise _invalid("--sponsorblock cannot be used with --raw-vtt.")
    progress.stage("fetch")
    if config.mode == "raw-vtt":
        raw_download = download_english_vtt(canonical, verbose=verbose)
        data = raw_download.vtt
        if verbose:
            progress.write_line(
                "caption: selected English VTT; source="
                + ("automatic" if raw_download.automatic else "manual")
            )
    else:
        downloaded = fetch_clean_transcript(
            canonical, sponsorblock=config.sponsorblock.resolved()
        )
        effective = config.mode == "markdown"
        body = downloaded.effective_body if effective else downloaded.body
        lookup = (
            downloaded.projection.lookup
            if effective and downloaded.projection
            else downloaded.metadata.sponsorblock
        )
        if lookup.warning:
            progress.write_line(lookup.warning)
        if verbose:
            progress.write_line(
                "caption: selected English VTT; source="
                + ("automatic" if downloaded.automatic else "manual")
            )
        if args.preview:
            plan = plan_transcript_formatting(
                body,
                sections=downloaded.effective_sections,
                chunk_chars=config.chunk_chars,
                max_chunks=config.max_chunks,
            )
            lines = [
                f"canonical URL: {canonical}",
                f"cleaned characters: {len(downloaded.body)}",
                f"retained input characters: {len(body)}",
                f"SponsorBlock status: {lookup.status}",
                f"removed cues: {downloaded.projection.receipt.removed_cue_count if downloaded.projection else 0}",
                f"planned formatter invocations: {len(plan.chunks)}",
                f"largest chunk characters: {max(plan.character_counts, default=0)}",
                f"configured chunk limit: {config.chunk_chars}",
                f"maximum chunks: {config.max_chunks if config.max_chunks is not None else 'unlimited'}",
                f"cap result: {'within limit' if plan.within_cap else 'exceeds limit'}",
                f"model selection: {config.model or 'Pi configured default'}",
                f"editorial mode: {config.editorial_mode}",
            ]
            progress.close()
            _emit(("\n".join(lines) + "\n").encode("utf-8"))
            return
        if config.mode == "markdown":
            progress.stage("format")
            body = format_with_pi(
                body,
                model=config.model,
                chunk_chars=config.chunk_chars,
                timeout_seconds=config.timeout_seconds,
                max_chunks=config.max_chunks,
                sections=downloaded.effective_sections,
                editorial_mode=config.editorial_mode,
                on_progress=progress.chunks if progress.enabled else None,
            )
        document = (
            downloaded.document(body, effective=effective)
            if args.output
            else body.rstrip() + "\n"
        )
        data = document.encode("utf-8")
    if args.output:
        progress.stage("output")
        write_output(args.output, data, no_clobber=args.no_clobber)
    else:
        progress.close()
        _emit(data)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    except AppError as exc:
        sys.stderr.write(render_cli_error(exc))
        return 2
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return _broken_pipe_exit()
    verbose = bool(args.verbose)
    progress = TerminalProgress(
        sys.stderr, enabled=False if args.mcp or args.doctor else None
    )
    try:
        restricted = (
            args.url is not None
            or args.preview
            or args.output is not None
            or args.no_clobber
            or args.mode is not None
            or args.model is not None
            or args.max_chunks is not None
            or args.sponsorblock is not None
            or args.editorial_mode is not None
        )
        if args.doctor:
            if restricted or args.mcp or args.config is not None or args.no_config:
                raise _invalid("--doctor permits only --verbose.")
            from .doctor import render_doctor, run_doctor

            report = run_doctor()
            _emit(render_doctor(report).encode("utf-8"))
            return 0 if report.healthy else 1
        if args.mcp and restricted:
            raise _invalid("--mcp permits only config selection and --verbose.")
        file_config = load_config(args.config, disabled=args.no_config)
        config = (
            replace(
                file_config,
                verbose=args.verbose
                if args.verbose is not None
                else file_config.verbose,
            )
            if args.mcp
            else resolve_config(
                file_config,
                mode=args.mode,
                verbose=args.verbose,
                model=args.model,
                max_chunks=args.max_chunks,
                sponsorblock=args.sponsorblock,
                editorial_mode=args.editorial_mode,
            )
        )
        verbose = config.verbose
        if args.mcp:
            try:
                from .mcp_server import run_stdio_server

                run_stdio_server(config)
            except ModuleNotFoundError as exc:
                if exc.name and (exc.name == "mcp" or exc.name.startswith("mcp.")):
                    raise AppError(
                        ErrorInfo(
                            "RUNTIME_MISSING",
                            "The optional MCP extra is required.",
                            "Install this project with the mcp extra.",
                            "runtime_check",
                        )
                    ) from None
                raise
            return 0
        _transcribe(args, config, progress)
        return 0
    except AppError as exc:
        progress.close()
        sys.stderr.write(render_cli_error(exc))
        if verbose:
            sys.stderr.write(render_diagnostics(exc))
        return 2 if exc.info.code in ("INVALID_URL", "CONFIG_INVALID") else 1
    except KeyboardInterrupt:
        progress.close()
        sys.stderr.write("error[INTERRUPTED]: Operation interrupted.\n")
        return 130
    except BrokenPipeError:
        progress.close()
        return _broken_pipe_exit()
    except OSError:
        progress.close()
        sys.stderr.write("error[OUTPUT_FAILED]: Output could not be written.\n")
        return 1
    except Exception:
        progress.close()
        sys.stderr.write("error[INTERNAL_ERROR]: Operation failed unexpectedly.\n")
        return 1
    finally:
        progress.close()
