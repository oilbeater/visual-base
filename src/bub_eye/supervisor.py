"""FFmpeg watchdog: spawn, monitor, restart."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger

from bub_eye.ffmpeg import build_command, detect_screen_index, resolve_ffmpeg
from bub_eye.settings import EyeSettings

_PROGRESS_TIMEOUT_S = 15.0
_POLL_INTERVAL_S = 2.0
_BACKOFF_INITIAL_S = 2.0
_BACKOFF_CAP_S = 30.0
_TERMINATE_WAIT_S = 5.0


class FFmpegSupervisor:
    """Long-lived async loop that keeps one ffmpeg alive per run.

    On each spawn:
      * watches `-progress pipe:1` output as a liveness heartbeat
      * kills ffmpeg if the heartbeat goes silent for > _PROGRESS_TIMEOUT_S
      * on any exit, sleeps with exponential backoff before respawning
    """

    def __init__(self, settings: EyeSettings) -> None:
        self._settings = settings
        self._backoff = _BACKOFF_INITIAL_S

    async def run(self, stop_event: asyncio.Event) -> None:
        assert self._settings.segments_dir is not None, (
            "segments_dir must be resolved before supervisor.run; "
            "use bub_eye.settings.build_settings(workspace) or set BUB_EYE_SEGMENTS_DIR"
        )
        self._settings.segments_dir.mkdir(parents=True, exist_ok=True)
        try:
            ffmpeg = resolve_ffmpeg(self._settings)
        except Exception as exc:
            logger.error("bub-eye: cannot resolve ffmpeg binary: {}", exc)
            return

        try:
            screen_index = (
                self._settings.display_index
                if self._settings.display_index is not None
                else detect_screen_index(ffmpeg)
            )
        except Exception as exc:
            logger.error("bub-eye: failed to detect avfoundation screen: {}", exc)
            return

        logger.info(
            "bub-eye: supervisor starting (ffmpeg={}, screen={})", ffmpeg, screen_index
        )

        while not stop_event.is_set():
            run_id = uuid4().hex
            run_start = datetime.now(UTC).isoformat()
            cmd = build_command(self._settings, ffmpeg, screen_index, run_id, run_start)
            logger.info("bub-eye: spawning ffmpeg run_id={}", run_id)

            returncode = await self._run_once(cmd, stop_event)

            if returncode == 0:
                self._backoff = _BACKOFF_INITIAL_S
            else:
                logger.warning(
                    "bub-eye: ffmpeg exited rc={}; backing off {:.0f}s",
                    returncode,
                    self._backoff,
                )

            if stop_event.is_set():
                break

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._backoff)
                break
            except asyncio.TimeoutError:
                pass
            self._backoff = min(self._backoff * 2, _BACKOFF_CAP_S)

        logger.info("bub-eye: supervisor exiting")

    async def _run_once(self, cmd: list[str], stop_event: asyncio.Event) -> int:
        env = os.environ.copy()
        env["TZ"] = "UTC"

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        assert proc.stdout is not None

        last_progress = time.monotonic()

        async def watch_progress() -> None:
            nonlocal last_progress
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    return
                if b"frame=" in line or b"out_time_ms=" in line:
                    last_progress = time.monotonic()

        async def drain_stderr() -> None:
            assert proc.stderr is not None
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                logger.debug("ffmpeg[{}]: {}", proc.pid, line.decode(errors="replace").rstrip())

        progress_task = asyncio.create_task(watch_progress())
        stderr_task = asyncio.create_task(drain_stderr())

        try:
            while proc.returncode is None and not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=_POLL_INTERVAL_S)
                    break
                except asyncio.TimeoutError:
                    pass

                if time.monotonic() - last_progress > _PROGRESS_TIMEOUT_S:
                    logger.warning(
                        "bub-eye: ffmpeg progress silent > {}s, killing pid={}",
                        _PROGRESS_TIMEOUT_S,
                        proc.pid,
                    )
                    proc.kill()
                    break
        finally:
            progress_task.cancel()
            stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task

            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_WAIT_S)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

        return proc.returncode or 0
