# Development and releases

[README](../README.md) · [Installation](installation.md) · [Changelog](../CHANGELOG.md)

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) through its official instructions.

From this project directory, run:

```sh
uv sync --locked --group dev --extra mcp
uv run yt-transcript --help
uv run yt-transcript --version
```

Install [Deno](https://docs.deno.com/runtime/getting_started/installation/) separately. Deno must be on `PATH`. The selected yt-dlp release supports Deno 2.3.0 or newer.

The `yt-dlp[default]` dependency supplies EJS scripts. The locked yt-dlp 2026.8.19 release requires yt-dlp-ejs 0.8.0. Automatic remote EJS component downloads are disabled.

For Markdown, install [Pi](https://pi.dev) separately. The formatter supports the Pi 1.0.4 CLI interface or newer compatible releases.

Pi offers an official installer and an npm package. The npm method requires Node.js 22.19 or newer:

```sh
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Authenticate directly in Pi through `/login`. Select or save a default model through `/model`. This wrapper never installs runtimes or changes credentials.


## Public GitHub releases

The first development release is `v0.2.0-dev.1`. Its Python package version is
`0.2.0.dev1`. This repository and its GitHub releases are public:

```sh
uvx --from 'git+https://github.com/nmdra/yt-transcript.git@v0.2.0-dev.1' yt-transcript --version
```

GitHub releases attach a wheel, source archive, and `SHA256SUMS`. They do not bundle
Python, Deno, Pi, or provider credentials. Public assets can be downloaded without
repository access credentials; authenticate if the GitHub CLI requests it or API
limits require it. Nothing goes to PyPI.

The tag-triggered `.github/workflows/release.yml` accepts `vX.Y.Z` for stable
releases and `vX.Y.Z-dev.N` for development prereleases, with `N` greater than zero.
Before tagging, set the matching `pyproject.toml` version (`X.Y.Z` or `X.Y.Z.devN`),
update the root project version in `uv.lock`, and add a dated `CHANGELOG.md` entry
under the tag version without `v`. Commit and push those changes, then push the
tag. The workflow rejects version or changelog mismatches, runs only offline
checks, builds packages, and publishes only after checks pass. Development
releases do not replace the latest stable release. Existing releases/assets are
not overwritten. The publish job verifies artifact checksums and creates a normal
GitHub release using the workflow token. No private-repository guard or manual
public-release exception is required.

CI uses the pinned Python version in `.python-version`, uv 0.8.13, Hatchling
1.32.4, Pyright 1.1.412, and locked project dependencies. GitHub Actions are pinned
to commit hashes. No live YouTube, SponsorBlock, or Pi validation runs in CI.


## Development and distribution

```sh
uv run --extra mcp pytest -m 'not integration'
uv run ruff check .
uv run ruff format --check .
uv build
uvx --from . yt-transcript --help
uvx --from . yt-transcript --version
```

The lockfile records exact development dependencies. Runtime execution never upgrades them automatically. Automated tests use synthetic metadata and local child processes, without YouTube or Pi calls.

Live checks require an operator-supplied public URL:

```sh
YT_TRANSCRIPT_TEST_URL='https://youtu.be/VIDEO_ID' uv run pytest -m integration tests/test_integration.py
```

A live Pi check requires fresh spend approval, `YT_TRANSCRIPT_TEST_PI=1`, `YT_TRANSCRIPT_TEST_EDITORIAL_MODE=standard` or `focused`, and a preview-approved `YT_TRANSCRIPT_TEST_MAX_CHUNKS` from 1 through 1000. It runs only the chosen mode. A URL alone never enables a model call.

Chapter checks also require `YT_TRANSCRIPT_TEST_CHAPTERS=1` and a confirmed chapter-bearing URL. SponsorBlock checks require a segment-bearing URL, `YT_TRANSCRIPT_TEST_SPONSORBLOCK=1`, and `YT_TRANSCRIPT_TEST_SPONSORBLOCK_LICENSE_OK=1` after operator license confirmation. Offline tests enable none of these gates.

The Git source is the public repository [nmdra/yt-transcript](https://github.com/nmdra/yt-transcript). Cloning it does not require repository access credentials.

```sh
uvx --python 3.14.7 --from 'git+https://github.com/nmdra/yt-transcript.git' yt-transcript --help
uvx --python 3.14.7 --from 'yt-transcript[mcp] @ git+https://github.com/nmdra/yt-transcript.git' yt-transcript --mcp --no-config
```

The explicit Python selector also works with older uv releases that select an incompatible interpreter for the MCP extra.

Keep credentials out of URLs and command arguments. PyPI publication and live model checks still require separate approval.
