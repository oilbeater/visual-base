# bub-eye

A visual "eye" plugin for [Bub](https://bub.build): records the screen in the background via `ffmpeg`, rotates short video segments to disk, and appends one `event` entry per segment to an independent **visual tape**.

**Status**: v1, Intel Mac only. Acquires and persists; does not yet feed the tape into the model. Consumption hooks (tool / prompt injection) will land in a later version.

## What it does

- Starts an `ffmpeg` subprocess under a watchdog when Bub's gateway comes up.
- Captures the primary display via `-f avfoundation` and decimates with `-vf fps=N` (default 1 fps).
- Writes rotating `eye_YYYYMMDD_HHMMSS.mp4` segments (default 60 s each, HEVC via `hevc_videotoolbox` at 1200 kbps, 720p).
- Appends one `TapeEntry.event(name="vision/segment", data={path, start, end, ...})` per closed segment into a dedicated tape directory.
- Restarts `ffmpeg` with exponential backoff if it exits or its progress pipe goes silent for > 15 s (covers sleep/wake, permission revocation, display changes).

## What it does NOT do (v1)

- No model consumption path: no `build_prompt` injection, no `@tool` exposure.
- No perceptual-hash deduplication or segment cleanup — every segment becomes one tape entry.
- No Linux / Windows / Apple Silicon support. On anything other than Intel Mac the channel disables itself with a warning.
- No hardware encoding (videotoolbox is not in the `imageio-ffmpeg` build).
- No CLI subcommand, no system-tray UI.

## Install

Inside the `bub-contrib` workspace:

```bash
uv sync
```

To install standalone:

```bash
uv pip install git+https://github.com/bubbuild/bub-contrib.git#subdirectory=packages/bub-eye
```

## First-run checklist (macOS)

1. `imageio-ffmpeg` ships its own `ffmpeg` binary. The path is what macOS will ask to grant Screen Recording permission to:

   ```bash
   uv run python -c "from imageio_ffmpeg import get_ffmpeg_exe; print(get_ffmpeg_exe())"
   ```

2. Run `bub gateway` once. macOS will show a Screen Recording permission dialog for the printed `ffmpeg` path (or fail silently with a black recording). Grant it in **System Settings → Privacy & Security → Screen Recording**, then restart `bub gateway`.

3. If `imageio-ffmpeg`'s bundled build lacks `avfoundation` support on your machine, set `BUB_EYE_FFMPEG` to a system `ffmpeg`:

   ```bash
   brew install ffmpeg
   export BUB_EYE_FFMPEG="$(which ffmpeg)"
   ```

## Configuration (`BUB_EYE_*`)

| Variable | Default | Description |
|---|---|---|
| `BUB_EYE_ENABLED` | `true` | Master switch. `false` → channel reports `enabled=False`. |
| `BUB_EYE_FFMPEG` | — | Override `ffmpeg` binary path. Falls back to `imageio-ffmpeg`. |
| `BUB_EYE_FRAMERATE` | `1` | Capture fps (supports fractional, e.g. `0.5`). 1–2 is plenty for visual analysis. |
| `BUB_EYE_SEGMENT_SECONDS` | `60` | Target length of each segment. |
| `BUB_EYE_CODEC` | `hevc_videotoolbox` | Video codec. See *Codec & sizing* below. |
| `BUB_EYE_BITRATE` | `1200k` | Target bitrate for hardware / bitrate-based codecs. Ignored by `libx264`. |
| `BUB_EYE_CRF` | `28` | Constant Rate Factor for `libx264`. Ignored by hardware codecs. |
| `BUB_EYE_SCALE_HEIGHT` | `720` | Output height (preserves aspect). `-1` disables scaling. |
| `BUB_EYE_SEGMENTS_DIR` | `~/.bub/eye/segments` | Where `.mp4` files go. |
| `BUB_EYE_TAPE_DIR` | `~/.bub/eye/tapes` | Directory for the visual tape (`visual__<host_hash>.jsonl` inside). |
| `BUB_EYE_DISPLAY_INDEX` | — | Manual avfoundation screen index. Auto-detected if unset. |

## Codec & sizing

The default `hevc_videotoolbox` uses Apple's hardware HEVC encoder (available on every Intel Mac with Quick Sync and every Apple Silicon Mac). Compared to software H.264, expect:

- **CPU**: ≈ 0% vs. tens of percent on a single core.
- **File size**: ≈ 9 MB per 60 s at 1200 kbps HEVC 720p, stable regardless of screen activity.

Switch to `libx264` (software H.264) only if your `ffmpeg` build lacks videotoolbox support. In that mode bitrate is unbounded — dynamic content (video playback, scrolling, animations) can balloon a single segment past 100 MB because `libx264` is driven by CRF quality, not a rate cap.

Other useful overrides:

- `BUB_EYE_CODEC=h264_videotoolbox` — hardware H.264 if a downstream tool can't handle HEVC.
- `BUB_EYE_BITRATE=600k` — halve the file size at the cost of more blocking on high-motion content.

## Observability

- `tail -f ~/.bub/eye/tapes/visual__*.jsonl` — watch new entries append.
- `ls -lhtr ~/.bub/eye/segments/` — watch new segments land.
- `uv run bub hooks` — confirms the `bub-eye` entry point is discovered.

## Troubleshooting

- **Permission denied / black screen**: re-check Screen Recording grant for the exact `ffmpeg` path `imageio-ffmpeg` resolved to. The grant is path-specific.
- **`No avfoundation capture screen found`**: run `ffmpeg -f avfoundation -list_devices true -i ""` manually and set `BUB_EYE_DISPLAY_INDEX` to the `[N]` printed on the `Capture screen` line.
- **ffmpeg keeps restarting**: watchdog triggers if the progress pipe is silent > 15 s (ffmpeg hung) or the binary exits with non-zero. Check the Bub log for `bub-eye: ffmpeg exited rc=...`.

## Roadmap

- v2: perceptual-hash dedup, idle-segment GC.
- v2+: `@tool` for model querying, `build_prompt` injection of recent context.
- v2+: Apple Silicon, Linux (PipeWire / x11grab), Windows (gdigrab) input backends.
