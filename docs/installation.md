# Installation

[README](../README.md) · [MCP setup](mcp.md) · [Troubleshooting](troubleshooting.md)

These instructions install the tool in an isolated uv tool environment for your user account.
The instructions do not require sudo.
The installation does not change the project's development environment.

## OpenRouter requirements

Pi is the default Markdown backend.
This release can instead use OpenRouter with an explicit model and `OPENROUTER_API_KEY` in the environment.
This backend does not require Pi or an additional HTTP dependency.
Python, Deno, and caption-extraction dependencies remain unchanged.
Before you run requests that can incur charges, read the [provider guide](cli.md#providers).
Keep existing credentials and backend settings unless you approve a change.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.14.7 for the commands below; the package accepts Python 3.14.7 or newer
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) 2.3.0 or newer on `PATH`
- Access to the `nmdra/yt-transcript` repository and release assets
- [Pi](https://pi.dev) 1.0.4 or a newer compatible release for the Pi Markdown backend or Pi MCP integration

You do not need Pi to process raw captions or extract MCP plain text.
Explicit MCP Markdown output requires a ready server-selected backend and POSIX worker supervision.
You need a Pi client to connect the server to Pi.
First, check the installed runtime versions.
Then install missing runtimes from their official sources.

Use `uv python find --system 3.14.7` to check the interpreter.
Older uv releases, including 0.8.13, cannot download Python 3.14.7 from their bundled registry.
Install that runtime separately.
Do not select another version without telling the user.

Pi's npm installer requires Node.js 22.19 or newer:

```sh
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Set up provider authentication directly in Pi through `/login`.
Set the default model through `/model`.
Installation, doctor, and listing MCP tools do not require a model call.
Keep credentials out of URLs, shell arguments, and project files.

## Quick Git-source install

Install from the pinned source tag:

```sh
uv tool install --python 3.14.7 \
  'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git@v1.0.0'
yt-transcript --version
yt-transcript --help
yt-transcript --doctor
```

This command installs `1.0.0` with the MCP extra.
The command pins the application source to the stable release tag.
uv selects compatible dependencies from package metadata.
uv does not use the repository lockfile for this installation.
If you need dependency versions that match the release, use the wheel method below.

Bare `uvx yt-transcript` and `uv tool install yt-transcript` select an unrelated PyPI project.
Always specify this repository or its verified release wheel.

## Verified wheel with release-matched dependencies

Use this method for the agent installation prompt in the README.
The method requires the [GitHub CLI](https://cli.github.com/).
This repository and the approved `v1.0.0` release are public.
Authenticate if the CLI requests authentication or access is unavailable.
Do not put tokens in commands or download URLs.

The following POSIX-shell example stores assets in your user data directory.
If the release directory already contains files, verify the files before you reuse them.
Alternatively, select a new directory.
`gh release download` does not overwrite existing files.

```sh
release_dir="$HOME/.local/share/yt-transcript/releases/v1.0.0"
mkdir -p "$release_dir"
gh release download v1.0.0 --repo nmdra/yt-transcript --dir "$release_dir"
(cd "$release_dir" && sha256sum --check SHA256SUMS)
```

On macOS, use `shasum -a 256 --check SHA256SUMS` instead of `sha256sum`.
Continue only when the wheel and source archive checksums both pass.
Checksums detect changed bytes.
Trust in the release still depends on the authenticated GitHub source.

Extract constraints without unpacking or executing the source archive:

```sh
python_path=$(uv python find --system 3.14.7)
"$python_path" - "$release_dir" <<'PY'
from pathlib import Path
import sys
import tarfile
import tomllib

folder = Path(sys.argv[1])
with tarfile.open(folder / "yt_transcript-1.0.0.tar.gz") as archive:
    stream = archive.extractfile("yt_transcript-1.0.0/uv.lock")
    assert stream is not None
    lock = tomllib.loads(stream.read().decode("utf-8"))
packages = {row["name"]: row["version"] for row in lock["package"]}
assert packages.pop("yt-transcript") == "1.0.0"
(folder / "runtime-constraints.txt").write_text(
    "".join(f"{name}=={version}\n" for name, version in sorted(packages.items())),
    encoding="utf-8",
)
PY
```

Install the verified wheel with the MCP extra:

```sh
wheel_url=$("$python_path" -c \
  'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().as_uri())' \
  "$release_dir/yt_transcript-1.0.0-py3-none-any.whl")
uv tool install --no-config --no-python-downloads --python "$python_path" \
  --constraints "$release_dir/runtime-constraints.txt" \
  "yt-transcript[mcp] @ $wheel_url"
yt-transcript --version
yt-transcript --doctor
```

These constraints select exact versions for required dependencies.
The constraints do not install every package in the development lockfile.
`--offline` is optional when all required packages are already cached.
While the uv tool receipt refers to these files, keep the assets and constraints.

## PATH and MCP setup

uv normally makes the executable available in `~/.local/bin`.
Check your configured location with `uv tool dir --bin`.
Make sure that location is on `PATH`.
Use `command -v yt-transcript` to find the installed command.
Then use the installed command's absolute path in [Pi's MCP configuration](mcp.md).

Doctor checks Python, yt-dlp, PyYAML, EJS compatibility, Deno, and selected-backend readiness.
A healthy report shows local readiness only.
The report does not verify video access or model authentication.
Do not run a live video or paid Markdown job as an installation check.

## Updates and uninstall

Updates are explicit.
Before you replace an existing installation, review the target release and changelog.
Repeat the selected installation method.
Use the target version's tag, asset names, and lockfile.
Ask before you use `--force` to replace executables.
Do not use an unqualified upgrade command that could select the unrelated PyPI project.

To remove this tool and its Pi MCP entry:

```sh
pi mcp remove yt-transcript
uv tool uninstall yt-transcript
```

After you change MCP configuration, run `/reload` in an active Pi session.
When you remove the tool, saved transcripts, release assets, and configuration backups remain.
