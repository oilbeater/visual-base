# CLAUDE.md

Guidance for Claude Code working in the `visual-base` distribution.

## What this repo is

A Bub distribution published to PyPI as a single `visual-base` package.
It bundles the framework plus two plugins (`bub-kimi`, `bub-eye`) as
top-level modules inside the same wheel. It is **not** the core
framework (`bub`) and **not** the community plugin monorepo
(`bub-contrib`) — those are separate upstreams.

The sibling checkouts `../bub/` and `../bub-contrib/` are independent
git repos used for reference. Never edit them from here.

## Package layout

```
pyproject.toml       # hatchling build, publishes visual-base to PyPI
LICENSE              # MIT
src/visual_base/     # distribution-level defaults and version
src/bub_kimi/        # Kimi CLI plugin (entry-point: bub.kimi)
src/bub_eye/         # Screen-capture plugin (entry-point: bub.eye)
src/skills/          # Builtin skills shipped with the wheel
tests/               # One test file per plugin
```

The three top-level packages (`bub_kimi`, `bub_eye`, `skills`) are
bundled into the single `visual-base` distribution via
`[tool.hatch.build.targets.wheel].packages`. Do not re-introduce a
workspace — everything lives inside the one wheel.

## Dependency rules

- `bub>=0.3.6,<0.4` — track upstream PyPI releases. Bump the floor when
  you need new framework APIs; bump the ceiling when bub makes a breaking
  minor release.
- `loguru` and `pydantic-settings` are always installed — `bub_eye`
  imports them at plugin-load time, even on Linux where the channel
  then reports `enabled=False`.
- **No optional extras.** Heavy external deps that only a subset of users
  need (`kimi-cli`, `imageio-ffmpeg`) are auto-installed on first use by
  the relevant plugin:
  - `bub_kimi.plugin._ensure_kimi_installed` → `uv tool install kimi-cli`
  - `bub_eye.ffmpeg._ensure_imageio_ffmpeg_installed` → `uv pip install --python sys.executable imageio-ffmpeg`
  Both guard with a module-level flag so they only probe once per process,
  and both raise `RuntimeError` with an actionable message if `uv` itself
  is missing or the install fails.

## Plugin platform rules

`bub_eye` requires Intel Mac (ffmpeg + `hevc_videotoolbox`). On any
other host `EyeChannel.enabled` returns `False` after a log line, which
means `resolve_ffmpeg` is never called and the lazy imageio-ffmpeg
install never fires — Linux / Apple Silicon users don't download the
heavy binary.

## Publishing to PyPI

Releases are driven by `.github/workflows/release.yml`, triggered by
pushing a `v<version>` tag. The workflow:

1. Runs ruff + pytest.
2. Checks the tag matches `project.version` in `pyproject.toml`.
3. Builds sdist + wheel via `uv build`.
4. Publishes via PyPI trusted publisher (OIDC, environment `pypi`).

Before the first release, configure a Pending publisher on PyPI
pointing at `oilbeater/visual-base` → `release.yml` → environment `pypi`.
Bumping the version: edit `pyproject.toml`, commit, `git tag vX.Y.Z`,
`git push --tags`.

## Branch policy

This repo is an exception to the user's global rule: commit directly to
`main` by default. Only branch off into `feat/*` / `fix/*` when the user
explicitly asks (or when the change clearly warrants a review cycle —
e.g. cross-repo coordination, risky migrations).

## Commit policy

Every commit must carry `Signed-off-by: Mengxin Liu <liumengxinfly@gmail.com>`.
