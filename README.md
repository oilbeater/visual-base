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

`visual-base` depends on the external `kimi` CLI, which is a separate
Python application installed into its own isolated environment via
`uv tool install`. The `just` recipes below bundle both steps:

```bash
just setup          # uv sync + uv tool install kimi-cli
just setup-mac      # same, but with the bub-eye extra on Intel Mac
cp .env.example .env   # then fill in BUB_KIMI_* values
```

If you don't have `just` yet: `brew install just` on macOS, or see
[just's install guide](https://github.com/casey/just#installation).

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
