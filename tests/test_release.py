import re
import runpy
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
prepare_release = runpy.run_path(str(ROOT / "scripts/release.py"))["prepare_release"]


def release_files(root, *, version="0.2.0.dev1", heading="0.2.0-dev.1"):
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "yt-transcript"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        f'[[package]]\nname = "yt-transcript"\nversion = "{version}"\n'
        'source = { editable = "." }\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n## [{heading}] - 2026-10-07\n\n"
        "### Added\n\n- Test release\n\n"
        "## [0.1.0] - 2026-01-01\n\n- Old release\n\n"
        "[Unreleased]: https://example.invalid\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "tag,version,development",
    [("v0.2.0-dev.1", "0.2.0.dev1", True), ("v1.2.3", "1.2.3", False)],
)
def test_prepare_release(tmp_path, tag, version, development):
    release_files(tmp_path, version=version, heading=tag[1:])
    assert prepare_release(tag, root=tmp_path) == (
        version,
        development,
        "### Added\n\n- Test release\n",
    )


@pytest.mark.parametrize(
    "tag",
    [
        "0.2.0-dev.1",
        "v0.2.0.dev1",
        "v0.2.0-dev.0",
        "v0.2.0-dev.01",
        "v00.2.0",
        "v0.2.0-rc.1",
        "v0.2.0-dev.1\nprerelease=false",
    ],
)
def test_invalid_tag(tmp_path, tag):
    with pytest.raises(ValueError, match="Use a vX.Y.Z"):
        prepare_release(tag, root=tmp_path)


def test_project_version_mismatch(tmp_path):
    release_files(tmp_path, version="0.1.0")
    with pytest.raises(ValueError, match="Package version"):
        prepare_release("v0.2.0-dev.1", root=tmp_path)


def test_lock_version_mismatch(tmp_path):
    release_files(tmp_path)
    lock = tmp_path / "uv.lock"
    lock.write_text(lock.read_text().replace("0.2.0.dev1", "0.1.0"))
    with pytest.raises(ValueError, match="Locked project version"):
        prepare_release("v0.2.0-dev.1", root=tmp_path)


def test_changelog_entry_required(tmp_path):
    release_files(tmp_path, heading="0.1.0")
    with pytest.raises(ValueError, match="dated changelog"):
        prepare_release("v0.2.0-dev.1", root=tmp_path)


def test_notes_exclude_comparison_links(tmp_path):
    release_files(tmp_path)
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().split("## [0.1.0]")[0])
    with changelog.open("a") as file:
        file.write("[Unreleased]: https://example.invalid\n")
    assert prepare_release("v0.2.0-dev.1", root=tmp_path)[2] == (
        "### Added\n\n- Test release\n"
    )


def test_release_cli(tmp_path):
    release_files(tmp_path)
    output = tmp_path / "outputs"
    output.write_text("previous=value\n")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/release.py"),
            "v0.2.0-dev.1",
            "--notes",
            "dist/release-notes.md",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == (
        "previous=value\nversion=0.2.0.dev1\nprerelease=true\n"
    )
    assert (tmp_path / "dist/release-notes.md").read_text() == (
        "### Added\n\n- Test release\n"
    )


def test_repository_release_versions():
    current = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    tag = "v" + re.sub(r"\.dev([0-9]+)$", r"-dev.\1", current)
    version, development, notes = prepare_release(tag, root=ROOT)
    assert version == current and development == (".dev" in current)
    assert notes.strip() and "[Unreleased]:" not in notes


def test_workflow_release_boundaries():
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    assert workflow["on"] == {"push": {"tags": ["v*"]}}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    build, publish = workflow["jobs"]["build"], workflow["jobs"]["publish"]
    assert publish["needs"] == "build"
    assert publish["permissions"] == {"contents": "write"}
    for job in (build, publish):
        for step in job["steps"]:
            if "uses" in step:
                revision = step["uses"].split("@")[1]
                assert len(revision) == 40
                assert all(c in "0123456789abcdef" for c in revision)
    checks = next(s["run"] for s in build["steps"] if "pytest" in s.get("run", ""))
    assert "not integration" in checks and "pyright@1.1.412" in checks
    release = publish["steps"][-1]
    assert release["env"]["RELEASE_TAG"] == "${{ github.ref_name }}"
    assert "--verify-tag" in release["run"]
    assert "--prerelease --latest=false" in release["run"]
    assert publish["name"] == "Publish GitHub release"
    assert ".private" not in release["run"]
    checksum_step = publish["steps"][-2]
    assert checksum_step["run"] == "sha256sum --check SHA256SUMS"
    assert checksum_step["working-directory"] == "dist"
    assert "--clobber" not in release["run"]
    assert "pypi" not in release["run"].lower()
