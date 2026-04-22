# visual-base

> **The second brain from your eyes.**

Other "second brain" tools ask you to do the remembering — write the
note, hit the highlight, tag the page. Whatever you didn't capture is
gone; what you did is a biased sample.

`visual-base` records what your eyes actually land on — your screen,
continuously, as compressed video. The raw stream is the **single
source of truth**; every derived artifact — activity logs, search
indexes, future tool-use over the tape — comes *out* of it, never
replaces it. If it was on your screen, it's in the tape.

What ships:

- **`bub_eye`** — background screen recorder. macOS (Intel + Apple
  Silicon), hardware HEVC via `avfoundation`, ~10 MB per 15-min
  segment, near-zero CPU.
- **`bub_kimi`** — Kimi as the default agent for video understanding
  and daily-log generation.
- **`video-activity-log`** — turns any segment into an Obsidian-linkable
  daily log, one bullet per activity, with `[[wikilinks]]` on every
  site, app, person, and project it can identify.

## Install

```bash
uv tool install visual-base
```

`bub_eye`'s ffmpeg binary ships in the wheel via `imageio-ffmpeg`.
`kimi-cli` auto-installs as a separate uv tool on the first Kimi call.

Set up Kimi credentials once:

```bash
cp .env.example .env   # then fill in BUB_KIMI_*
```

macOS will prompt for **Screen Recording permission** the first time
`bub_eye` spawns ffmpeg. The grant is path-specific — re-grant if you
switch to a system ffmpeg via `BUB_EYE_FFMPEG`.

### For local development

```bash
uv sync
cp .env.example .env
uv run visual-base --help
```

`just setup` bundles `uv sync` with a pre-warmed `uv tool install
kimi-cli` for Dockerfile / CI caches.

## Run

```bash
uv tool run visual-base gateway
```

Starts the recorder and Kimi chat channel together. Everything lives
under `$BUB_HOME` (default `~/.bub/`):

- **Video segments** — `~/.bub/eye/segments/eye_YYYYMMDD_HHMMSS.mp4`
- **Daily activity logs** — `~/.bub/eye/logs/YYYY-MM-DD.md`
