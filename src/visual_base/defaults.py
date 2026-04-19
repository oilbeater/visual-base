"""Distribution-wide defaults for visual-base.

Kept as plain constants for now — consumers read these explicitly rather
than through a hook. Promote to a `configure` entry point only when a
concrete need appears.
"""

from __future__ import annotations

DEFAULT_MODEL_PLUGIN = "kimi"
DEFAULT_SCHEDULE_PLUGIN = "schedule"
MAC_ONLY_PLUGINS = frozenset({"eye"})
