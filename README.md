# visual-base

A [Bub](https://github.com/bubbuild/bub) distribution focused on:

- **Kimi** as the default model (via the `bub-kimi` plugin)
- **Local screen-visual capture** through `bub-eye` (Intel Mac only)
- **Scheduled tasks** through `bub-schedule`

`visual-base` pins specific commits of upstream `bub` and `bub-contrib`,
and vendors `bub-kimi` and `bub-eye` as workspace members because those
plugins are maintained here rather than upstream.

## Platform matrix

| Plugin | Linux | Intel Mac | Apple Silicon |
| --- | --- | --- | --- |
| `bub-kimi` | yes | yes | yes |
| `bub-schedule` | yes | yes | yes |
| `bub-eye` | no | yes | no |

`bub-eye` is gated behind the `mac` extra.

## Install

```bash
uv sync                # core: bub + bub-kimi + bub-schedule
uv sync --extra mac    # adds bub-eye on Intel Mac
cp .env.example .env   # then fill in BUB_KIMI_* values
```

## Run

```bash
uv run bub --help
uv run visual-base --help   # alias for the same CLI
```

## Layout

```
pyproject.toml       # workspace root; pins bub + bub-schedule to specific commits
src/visual_base/     # distribution-level defaults and version
packages/bub-kimi/   # vendored plugin (was oilbeater/bub-contrib @ feat/bub-kimi)
packages/bub-eye/    # vendored plugin (was oilbeater/bub-contrib @ feat/bub-eye-v1-intel-mac)
```

## Upgrading the pinned `bub`

Bump `[tool.uv.sources].bub.rev` in `pyproject.toml` to the new SHA, run
`uv lock --upgrade-package bub`, run the test suite, and commit the lock
change separately.
