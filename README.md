# visual-base

A [Bub](https://github.com/bubbuild/bub) distribution focused on:

- **Kimi** as the default model (via the `bub-kimi` plugin)
- **Local screen-visual capture** through `bub-eye` (Intel Mac only)

`visual-base` pins a specific commit of upstream `bub` and vendors
`bub-kimi` and `bub-eye` as workspace members because those plugins are
maintained here rather than upstream.

## Platform matrix

| Plugin | Linux | Intel Mac | Apple Silicon |
| --- | --- | --- | --- |
| `bub-kimi` | yes | yes | yes |
| `bub-eye` | no | yes | no |

`bub-eye` is gated behind the `mac` extra.

## Install

```bash
uv sync                     # or: uv sync --extra mac (Intel Mac, pulls bub-eye)
cp .env.example .env        # then fill in BUB_KIMI_* values
```

The first `uv run bub` that actually talks to Kimi will detect a missing
`kimi` binary and auto-install `kimi-cli` via `uv tool install` — no
separate step needed. If you want to pre-warm it (e.g. in a Dockerfile
layer), the `justfile` exposes `just setup` / `just setup-mac` which
front-load the install.

### Why `uv tool install` instead of bundling kimi-cli as a dependency?

`kimi-cli` is an application, not a library — `bub-kimi` shells out to
the `kimi` binary via `create_subprocess_exec`. Bundling it into the
same venv would pull in ~50 extra packages and pin `pydantic`/`typer`
to specific versions that would constrain future `bub` upgrades.
`uv tool install` puts kimi-cli in its own venv under `~/.local/bin/kimi`,
which is already on `PATH` — bub-kimi's subprocess finds it there.

## Run

```bash
uv run bub --help
uv run visual-base --help   # alias for the same CLI
```

## Layout

```
pyproject.toml       # workspace root; pins bub to a specific commit
src/visual_base/     # distribution-level defaults and version
packages/bub-kimi/   # vendored plugin (was oilbeater/bub-contrib @ feat/bub-kimi)
packages/bub-eye/    # vendored plugin (was oilbeater/bub-contrib @ feat/bub-eye-v1-intel-mac)
```

## Upgrading the pinned `bub`

Bump `[tool.uv.sources].bub.rev` in `pyproject.toml` to the new SHA, run
`uv lock --upgrade-package bub`, run the test suite, and commit the lock
change separately.
