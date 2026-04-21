"""Scan-tick worker that auto-triggers `video-activity-log` on finalized segments."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from bub.channels.message import ChannelMessage
from bub.types import MessageHandler
from loguru import logger

from bub_eye.settings import EyeSettings
from bub_eye.understand.merge import daily_log_path, merge_segment_file
from bub_eye.understand.state import (
    SegmentState,
    list_finalized_segments,
    load_state,
    md_is_idle,
    md_output_path,
    retry_due,
    save_state,
    stale_processing,
)


class SegmentUnderstander:
    """One asyncio task, serial, scans segments_dir on an interval.

    Each tick:
      1. lists finalized segments (newest is excluded),
      2. heals drift when ``<video>.md`` already exists,
      3. resets stale ``processing`` (crash recovery),
      4. injects an inbound ``ChannelMessage`` for any pending or retry-due segment,
      5. returns without waiting for the turn — completion is detected on a future tick
         by the presence of ``<video>.md``.
    """

    def __init__(self, settings: EyeSettings, message_handler: MessageHandler) -> None:
        self._settings = settings
        self._handler = message_handler

    @property
    def enabled(self) -> bool:
        return self._settings.auto_understand_enabled

    async def run(self, stop_event: asyncio.Event) -> None:
        if not self.enabled:
            logger.info(
                "bub-eye: auto-understand disabled (BUB_EYE_AUTO_UNDERSTAND_ENABLED=false)"
            )
            return
        self._settings.understand_state_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "bub-eye: auto-understand starting (state_dir={}, scan_interval={}s)",
            self._settings.understand_state_dir,
            self._settings.understand_scan_interval_seconds,
        )
        while not stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("bub-eye: auto-understand tick failed")
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self._settings.understand_scan_interval_seconds,
                )
                break
            except asyncio.TimeoutError:
                pass
        logger.info("bub-eye: auto-understand stopped")

    async def tick(self, *, now: float | None = None) -> None:
        """One scan pass. Exposed for tests."""
        current = time.time() if now is None else now
        segments = list_finalized_segments(
            self._settings.segments_dir,
            now=current,
            grace_seconds=self._settings.understand_finalize_grace_seconds,
        )
        for video in segments:
            await self._process_segment(video, now=current)

    async def _process_segment(self, video: Path, *, now: float) -> None:
        state_dir = self._settings.understand_state_dir
        state = load_state(state_dir, video)

        if self._heal_from_md(video, state):
            save_state(state_dir, video, state)
            return

        if stale_processing(
            state,
            now=now,
            timeout=self._settings.understand_processing_timeout_seconds,
        ):
            logger.warning(
                "bub-eye: {} stuck in processing > {}s, marking failed",
                video.name,
                self._settings.understand_processing_timeout_seconds,
            )
            state.mark("failed", last_error="processing timeout", bump_attempts=True)
            save_state(state_dir, video, state)

        should_inject = state.status == "pending" or retry_due(
            state,
            now=now,
            retry_after=self._settings.understand_retry_after_seconds,
            max_attempts=self._settings.understand_max_attempts,
        )
        if should_inject:
            await self._inject(video, state)

    def _heal_from_md(self, video: Path, state: SegmentState) -> bool:
        """If `<video>.md` exists and state isn't terminal, set it to done/idle.

        Non-idle segments are also merged into the daily ``YYYY-MM-DD.md`` log.
        """
        if state.terminal:
            return False
        md = md_output_path(video)
        if not md.exists():
            return False
        if md_is_idle(md):
            state.mark("idle")
            logger.info(
                "bub-eye: {} is idle (phase-0 marker), state → idle", video.name
            )
            return True

        self._merge_into_daily(video, md)
        state.mark("done")
        logger.info("bub-eye: {} understood, state → done", video.name)
        return True

    def _merge_into_daily(self, video: Path, segment_md: Path) -> None:
        """Best-effort append of this segment's bullets into the daily log."""
        daily = daily_log_path(self._settings.understand_logs_dir, video)
        if daily is None:
            logger.warning(
                "bub-eye: {} has no date-shaped filename; skipping daily merge",
                video.name,
            )
            return
        try:
            merge_segment_file(segment_md, video, daily)
        except Exception:
            logger.exception(
                "bub-eye: failed to merge {} into {}", segment_md.name, daily
            )
            return
        logger.info("bub-eye: merged {} → {}", video.name, daily)

    async def _inject(self, video: Path, state: SegmentState) -> None:
        session_id = f"eye-{video.stem}"
        content = self._settings.understand_trigger_phrase.format(
            video=str(video.resolve())
        )
        message = ChannelMessage(
            session_id=session_id,
            channel="eye",
            content=content,
        )
        state_dir = self._settings.understand_state_dir
        try:
            await self._handler(message)
        except Exception as exc:
            logger.warning(
                "bub-eye: inject failed for {} ({}); will retry on next tick",
                video.name,
                exc,
            )
            state.mark("pending", last_error=f"inject error: {exc}")
            save_state(state_dir, video, state)
            return

        state.mark("processing")
        save_state(state_dir, video, state)
        logger.info(
            "bub-eye: queued understand for {} (session={}, attempt={})",
            video.name,
            session_id,
            state.attempts + 1,
        )
