"""Offline readiness checks. No provider, authentication, or video checks."""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from tempfile import TemporaryDirectory
from typing import Literal


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: Literal["ok", "warning", "error"]
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def healthy(self) -> bool:
        return all(check.status != "error" for check in self.checks)


def _tool(name: str, minimum: tuple[int, int, int], flags: list[str]) -> DoctorCheck:
    executable = shutil.which(name)
    if not executable:
        return DoctorCheck(name, "error", "not installed; install a compatible version")
    try:
        with TemporaryDirectory(prefix="yt-transcript-doctor-") as cwd:
            result = subprocess.run(
                [executable, *flags, "--version"],
                cwd=cwd,
                capture_output=True,
                timeout=5,
                encoding="utf-8",
                errors="strict",
            )
        match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", result.stdout[:65536])
        if result.returncode or not match:
            return DoctorCheck(name, "error", "version could not be verified")
        version = tuple(int(part) for part in match.groups())
        if version < minimum:
            return DoctorCheck(name, "error", "upgrade to a compatible version")
        return DoctorCheck(name, "ok", ".".join(match.groups()))
    except OSError, UnicodeError, subprocess.TimeoutExpired:
        return DoctorCheck(name, "error", "version check failed")


def run_doctor(*, include_pi: bool = True) -> DoctorReport:
    checks = [
        DoctorCheck(
            "Python",
            "ok" if sys.version_info >= (3, 14, 7) else "error",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    ]
    for name in ("yt-transcript", "yt-dlp", "PyYAML", "yt-dlp-ejs") + (
        () if include_pi else ("mcp",)
    ):
        try:
            value = metadata.version(name)
            # Metadata is local, but report only a version-shaped value.
            detail = (
                value
                if re.fullmatch(r"\d+(?:\.\d+){1,3}", value)
                else "installed (version unverified)"
            )
            checks.append(DoctorCheck(name, "ok", detail))
        except metadata.PackageNotFoundError:
            checks.append(DoctorCheck(name, "error", "not installed"))
    try:
        requirements = metadata.requires("yt-dlp") or []
        pins = [
            re.match(r"yt-dlp-ejs==([0-9.]+)(?:;|$)", requirement)
            for requirement in requirements
        ]
        pins = [pin for pin in pins if pin]
        if pins:
            expected = pins[0][1]
            compatible = metadata.version("yt-dlp-ejs") == expected
            checks.append(
                DoctorCheck(
                    "EJS requirement",
                    "ok" if compatible else "error",
                    f"requires {expected}",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "EJS requirement", "warning", "compatibility could not be verified"
                )
            )
    except metadata.PackageNotFoundError:
        checks.append(
            DoctorCheck("EJS requirement", "error", "required package is missing")
        )
    checks.append(_tool("deno", (2, 3, 0), []))
    if include_pi:
        flags = [
            "--no-tools",
            "--no-session",
            "--no-extensions",
            "--no-mcp",
            "--no-skills",
            "--no-prompt-templates",
            "--no-context-files",
            "--no-themes",
            "--no-approve",
            "--offline",
        ]
        checks.append(_tool("pi", (1, 0, 4), flags))
    else:
        checks.append(DoctorCheck("Pi", "ok", "not required"))
    return DoctorReport(tuple(checks))


def render_doctor(report: DoctorReport) -> str:
    lines = [f"{check.name}: {check.status}: {check.detail}" for check in report.checks]
    lines.append("overall: " + ("ok" if report.healthy else "error"))
    lines.append(
        "Local readiness only; access, authentication, and model accuracy are not verified."
    )
    return "\n".join(lines) + "\n"
