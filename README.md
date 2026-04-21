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

From PyPI:

```bash
pip install visual-base              # Kimi chat only
pip install "visual-base[mac]"       # Intel Mac — adds bub_eye screen recording
```

For local development:

```bash
uv sync                              # or: uv sync --extra mac (Intel Mac)
cp .env.example .env                 # fill in BUB_KIMI_* values
```

The first `uv run bub` / `visual-base` call that talks to Kimi will
detect a missing `kimi` binary and auto-install `kimi-cli` via
`uv tool install` — no separate step needed. Pre-warm it with
`just setup` / `just setup-mac` (e.g. in a Dockerfile layer).

On Intel Mac, macOS will prompt for **Screen Recording permission** the
first time `bub_eye` spawns ffmpeg. The grant is path-specific — re-grant
if you switch to a system ffmpeg via `BUB_EYE_FFMPEG`.

### Why `uv tool install` instead of bundling kimi-cli as a dependency?

`kimi-cli` is an application, not a library — `bub_kimi` shells out to
the `kimi` binary via `create_subprocess_exec`. Bundling it into the
same venv would pull in ~50 extra packages and pin `pydantic`/`typer`
to specific versions that constrain future `bub` upgrades.
`uv tool install` puts kimi-cli in its own venv under
`~/.local/bin/kimi`, which is already on `PATH` — `bub_kimi`'s
subprocess finds it there.

## Run

```bash
uv run bub --help
uv run visual-base --help   # alias for the same CLI
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
