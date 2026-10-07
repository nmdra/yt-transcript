"""Validate release versions and extract curated notes without network access."""

import argparse
import re
import tomllib
from pathlib import Path

TAG_PATTERN = re.compile(
    r"v(?P<base>(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))"
    r"(?:-dev\.(?P<dev>[1-9][0-9]*))?"
)


def prepare_release(tag: str, *, root: Path = Path(".")) -> tuple[str, bool, str]:
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError("Use a vX.Y.Z or vX.Y.Z-dev.N tag, with N greater than zero.")
    development = match["dev"] is not None
    version = match["base"] + (f".dev{match['dev']}" if development else "")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    if project["version"] != version:
        raise ValueError("Package version does not match release tag.")
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked_versions = [
        package["version"]
        for package in lock["package"]
        if package["name"] == project["name"]
        and package.get("source") == {"editable": "."}
    ]
    if locked_versions != [version]:
        raise ValueError("Locked project version does not match release tag.")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(
        rf"^## \[{re.escape(tag[1:])}\] - [0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\n"
        r"(?P<notes>.*?)(?=^## |^\[Unreleased\]:|\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    if section is None or not section["notes"].strip():
        raise ValueError("A dated changelog entry with release notes is required.")
    return version, development, section["notes"].strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--notes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        version, development, notes = prepare_release(args.tag)
    except ValueError as exc:
        parser.error(str(exc))
    args.notes.parent.mkdir(parents=True, exist_ok=True)
    args.notes.write_text(notes, encoding="utf-8")
    with args.output.open("a", encoding="utf-8") as output:
        output.write(f"version={version}\nprerelease={str(development).lower()}\n")


if __name__ == "__main__":
    main()
