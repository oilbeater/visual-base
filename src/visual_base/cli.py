"""visual-base CLI entry.

When the user passes ``--workspace`` (or ``-w``) the bub framework's own
typer parsing handles it. Otherwise we resolve a sticky default
workspace from :class:`VisualBaseSettings` (env var → toml config file →
``$BUB_HOME/visual-base/default``) and ``chdir`` into it before importing
``bub.__main__``, because :class:`bub.framework.BubFramework` snapshots
``Path.cwd()`` as its workspace during module import.
"""

from __future__ import annotations

import os
import sys

from visual_base.settings import VisualBaseSettings


def _has_explicit_workspace_flag(argv: list[str]) -> bool:
    return any(
        arg == "--workspace" or arg == "-w" or arg.startswith("--workspace=")
        for arg in argv
    )


def main() -> None:
    if not _has_explicit_workspace_flag(sys.argv[1:]):
        workspace = VisualBaseSettings().resolve_workspace()
        workspace.mkdir(parents=True, exist_ok=True)
        os.chdir(workspace)

    from bub.__main__ import app

    app()


if __name__ == "__main__":
    main()
