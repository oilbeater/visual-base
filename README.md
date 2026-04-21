# visual-base

A [Bub](https://github.com/bubbuild/bub) distribution focused on:

- **Kimi** as the default model (via the bundled `bub_kimi` plugin)
- **Local screen-visual capture** through the bundled `bub_eye` plugin (Intel Mac only)

`visual-base` is published to PyPI as a single wheel that ships both
plugins as top-level modules and registers them as `bub` entry points.
`bub` itself is tracked via the usual PyPI release channel
(`bub>=0.3.6,<0.4`).

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

The first `uv run bub` / `visual-base` call that actually talks to
Kimi will detect a missing `kimi` binary and auto-install `kimi-cli`
via `uv tool install` — no separate step needed. To pre-warm it (e.g.
in a Dockerfile layer), use `just setup` / `just setup-mac`.

### Why `uv tool install` instead of bundling kimi-cli as a dependency?

`kimi-cli` is an application, not a library — `bub_kimi` shells out to
the `kimi` binary via `create_subprocess_exec`. Bundling it into the
same venv would pull in ~50 extra packages and pin `pydantic`/`typer`
to specific versions that would constrain future `bub` upgrades.
`uv tool install` puts kimi-cli in its own venv under `~/.local/bin/kimi`,
which is already on `PATH` — `bub_kimi`'s subprocess finds it there.

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
