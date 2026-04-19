# CLAUDE.md

Guidance for Claude Code working in the `visual-base` distribution.

## What this repo is

A Bub distribution. It is **not** the core framework (`bub`) and **not**
the community plugin monorepo (`bub-contrib`). It vendors two plugins
(`bub-kimi`, `bub-eye`) that are not expected to land upstream, and
pins specific commits of the upstream ones.

The sibling checkouts `../bub/` and `../bub-contrib/` are independent
git repos used for reference. Never edit them from here.

## Dependency pins

- `bub` is pinned to a specific commit in `[tool.uv.sources]`. Do not
  switch to `branch = "main"` — `bub-eye` is tightly coupled to
  tape/channel internals.
- `bub-schedule` is pulled from `bub-contrib` at a pinned commit via
  `subdirectory = "packages/bub-schedule"`.
- To upgrade: bump the SHA, run `uv lock --upgrade-package <name>`,
  run tests, commit the lock diff separately.

## Plugin platform rules

`bub-eye` requires Intel Mac (ffmpeg + `hevc_videotoolbox`). It lives
under `[project.optional-dependencies].mac` so `uv sync` on Linux will
not pull it. Do not move it to the main `dependencies` list.

## Branch policy

Follow the user's global rule: never commit directly to `main`.
Always branch off `main` into `feat/*` or `fix/*` and land via PR.

## Commit policy

Every commit must carry `Signed-off-by: Mengxin Liu <liumengxinfly@gmail.com>`.
