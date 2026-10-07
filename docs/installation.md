# Installation

[README](../README.md) · [MCP setup](mcp.md) · [Troubleshooting](troubleshooting.md)

These instructions use an isolated, user-level uv tool environment. They do not
require sudo or change the project's development environment.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.14.7 for the commands below; the package accepts Python 3.14.7 or newer
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) 2.3.0 or newer on `PATH`
- Access to the `nmdra/yt-transcript` repository and release assets
- [Pi](https://pi.dev) 1.0.4 or a newer compatible release for Markdown editing or Pi MCP integration

Raw captions and MCP plain-text extraction do not need Pi to process captions.
Explicit MCP Markdown output requires Pi and POSIX worker supervision. A Pi client
is required when you want to connect the server to Pi. Install missing
runtimes from their official sources after checking existing versions.

Use `uv python find --system 3.14.7` to check the interpreter. Older uv releases,
including 0.8.13, cannot download Python 3.14.7 from their bundled registry.
Install that runtime separately rather than silently choosing another version.

Pi's npm installer requires Node.js 22.19 or newer:

```sh
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Set up provider authentication and the default model directly in Pi through
`/login` and `/model`. Installation, doctor, and MCP tool listing need no model
call. Keep credentials out of URLs, shell arguments, and project files.

## Quick Git-source install

Install from the pinned source tag:

```sh
uv tool install --python 3.14.7 \
  'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git@v0.2.0-dev.4'
yt-transcript --version
yt-transcript --help
yt-transcript --doctor
```

This installs `0.2.0.dev4` with the MCP extra and pins the application source to
the development release tag. uv resolves compatible dependencies from package
metadata; it does not use the repository lockfile for this installation.
Use the wheel method below when you need release-matched dependency versions.

Bare `uvx yt-transcript` and `uv tool install yt-transcript` select an unrelated
PyPI project. Always supply this repository or its verified release wheel.

## Verified wheel with release-matched dependencies

Use this method for the copy-paste agent prompt in the README. It needs the
[GitHub CLI](https://cli.github.com/). This repository and the approved
`v0.2.0-dev.4` release are public. Authenticate if the CLI requests it or access
is unavailable. Do not place tokens in
commands or download URLs.

The following POSIX-shell example stores assets under your user data directory.
If that release directory already contains files, verify and reuse them or choose
a fresh directory. `gh release download` refuses to overwrite existing files.

```sh
release_dir="$HOME/.local/share/yt-transcript/releases/v0.2.0-dev.4"
mkdir -p "$release_dir"
gh release download v0.2.0-dev.4 --repo nmdra/yt-transcript --dir "$release_dir"
(cd "$release_dir" && sha256sum --check SHA256SUMS)
```

On macOS, use `shasum -a 256 --check SHA256SUMS` instead of `sha256sum`. Continue
only when both wheel and source archive checksums pass. Checksums detect changed
bytes; trust in the release still depends on your authenticated GitHub source.

Extract constraints without unpacking or executing the source archive:

```sh
python_path=$(uv python find --system 3.14.7)
"$python_path" - "$release_dir" <<'PY'
from pathlib import Path
import sys
import tarfile
import tomllib

folder = Path(sys.argv[1])
with tarfile.open(folder / "yt_transcript-0.2.0.dev4.tar.gz") as archive:
    stream = archive.extractfile("yt_transcript-0.2.0.dev4/uv.lock")
    assert stream is not None
    lock = tomllib.loads(stream.read().decode("utf-8"))
packages = {row["name"]: row["version"] for row in lock["package"]}
assert packages.pop("yt-transcript") == "0.2.0.dev4"
(folder / "runtime-constraints.txt").write_text(
    "".join(f"{name}=={version}\n" for name, version in sorted(packages.items())),
    encoding="utf-8",
)
PY
```

Install the verified wheel, including the MCP extra:

```sh
wheel_url=$("$python_path" -c \
  'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().as_uri())' \
  "$release_dir/yt_transcript-0.2.0.dev4-py3-none-any.whl")
uv tool install --no-config --no-python-downloads --python "$python_path" \
  --constraints "$release_dir/runtime-constraints.txt" \
  "yt-transcript[mcp] @ $wheel_url"
yt-transcript --version
yt-transcript --doctor
```

These constraints select exact versions for required dependencies; they do not
install every package listed in the development lockfile. `--offline` is optional
when all required packages are already cached. Retain the assets and constraints
while the uv tool receipt refers to them.

## PATH and MCP setup

uv normally exposes the executable in `~/.local/bin`. Check your configured
location with `uv tool dir --bin`, and make sure it is on `PATH`. Resolve the
installed command with `command -v yt-transcript` before using an absolute path
in [Pi's MCP configuration](mcp.md).

Doctor checks Python, yt-dlp, PyYAML, EJS compatibility, Deno, and Pi. A healthy
report proves local readiness, not video access or model authentication.
Do not run a live video or paid Markdown job as an installation check.

## Updates and uninstall

Updates are explicit. Review the target release and changelog before replacing
an existing installation. Repeat the chosen method with that version's tag,
asset names, and lockfile. Ask before using `--force` to replace executables.
Avoid an unqualified upgrade command that could select the unrelated PyPI project.

To remove this tool and its Pi MCP entry:

```sh
pi mcp remove yt-transcript
uv tool uninstall yt-transcript
```

Run `/reload` in an active Pi session after changing MCP configuration. Removing
the tool does not remove saved transcripts, release assets, or configuration backups.
