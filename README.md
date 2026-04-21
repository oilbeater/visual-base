# visual-base

> **Your brain is what you see.**

Most "second brain" tools assume *you* will do the work of remembering —
write the note, hit the highlight key, tag the page, file it under the
right section. Whatever you didn't capture in the moment is gone.
Whatever you did capture is a sample of what you chose to notice: a
biased slice of a day you'll never get back.

`visual-base` starts from the opposite premise. It runs quietly in the
background and records *what your eyes actually land on* — your screen,
continuously, as compressed video. The browsing you forgot you did, the
terminal error that flashed and closed, the Slack thread you scrolled
past on the way to somewhere else, the Figma panel you stared at for
thirty seconds. The raw stream **is** the archive. Structure comes
*out* of it, not into it.

On top of the stream, `visual-base` ships:

- **`bub_eye`** — a background screen recorder. Intel Mac, hardware
  HEVC via `avfoundation`, ~135 MB per 15-min 720p segment, self-restarts
  across sleep / wake / permission changes, near-zero CPU.
- **`bub_kimi`** — Kimi as the default chat model, via the `kimi` CLI.
- **`video-activity-log`** — a skill that turns any recorded segment into
  an Obsidian-linkable daily log. One bullet per coherent activity;
  `[[wikilinks]]` on every site, app, person, and project it can
  identify; an ffmpeg-based idle preflight short-circuits locked-screen
  segments before the model ever sees them.

Nothing here asks you to be disciplined. If it was on your screen, it's
in the tape.

## Status

**v0.1 — Intel Mac only, recording-first.** `bub_eye` captures to
`~/.bub/eye/segments/`. The `video-activity-log` skill reads individual
segments on demand. Model-side ingestion of the full stream — searching
across days, a `@tool` over the tape, prompt injection of recent context
— is on the roadmap but not in this release. So are Apple Silicon and
Linux capture backends.

## Install

One command, any platform:

```bash
uv tool install visual-base
```

This puts the `visual-base` / `bub` CLIs on your PATH inside an isolated
tool venv. On Intel Mac, the first time `bub_eye` actually starts
recording, it auto-installs `imageio-ffmpeg` into that venv. On all
platforms, the first Kimi call auto-installs `kimi-cli` as a separate uv
tool. You never need to touch `pip`, manage extras, or resolve
dependency conflicts by hand.

Set up Kimi credentials once:

```bash
cp .env.example .env   # then fill in BUB_KIMI_*
```

On Intel Mac, macOS will prompt for **Screen Recording permission** the
first time `bub_eye` spawns ffmpeg. The grant is path-specific — re-grant
if you switch to a system ffmpeg via `BUB_EYE_FFMPEG`.

### For local development

Clone the repo and let `uv` sync the workspace:

```bash
uv sync
cp .env.example .env
uv run visual-base --help
```

`just setup` bundles `uv sync` with a pre-warmed `uv tool install
kimi-cli` for Dockerfile layers or CI caches.

### Why auto-install instead of bundling as a dependency?

`kimi-cli` is an application, not a library, and `imageio-ffmpeg` ships
a 70 MB ffmpeg binary that only Intel Mac actually uses. Bundling either
into the wheel would either pin `pydantic`/`typer` to specific versions
that constrain future `bub` upgrades, or force every Linux / Apple
Silicon user to download the Mac-only binary for nothing. Auto-installing
via `uv` at first use keeps the base wheel small and each heavy dep
gated to the machine that needs it.

## Run

```bash
uv tool run visual-base --help
uv tool run bub --help          # same CLI, alternate name
```

Inside a cloned repo:

```bash
uv run visual-base --help
```

## Layout

```
pyproject.toml       # hatchling build, publishes visual-base to PyPI
LICENSE              # MIT
src/visual_base/     # distribution-level defaults and version
src/bub_kimi/        # Kimi CLI plugin (entry-point: bub.kimi)
src/bub_eye/         # Screen-capture plugin (entry-point: bub.eye)
src/skills/          # Builtin skills shipped with the wheel
tests/               # ruff + pytest run against the flat layout
```

## Releasing

Tag-driven. Edit `version` in `pyproject.toml`, commit, then:

```bash
git tag v0.1.0
git push --tags
```

`.github/workflows/release.yml` runs ruff + pytest, checks the tag
matches the project version, builds sdist + wheel with `uv build`, and
publishes via PyPI trusted publisher (OIDC). A Pending publisher for
`oilbeater/visual-base` → `release.yml` → environment `pypi` must be
configured on PyPI first.
