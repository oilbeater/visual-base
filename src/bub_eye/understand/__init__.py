"""Auto-understand subsystem for bub-eye.

After a segment is finalized on disk, a worker here injects a model turn
into the gateway so kimi can run the `video-activity-log` skill on it.
Tracks per-segment status in JSON files to survive restarts and failures.
"""

from bub_eye.understand.worker import SegmentUnderstander

__all__ = ["SegmentUnderstander"]
