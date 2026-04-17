"""EyeChannel: life-cycle wrapper that ties FFmpegSupervisor into Bub's gateway.

The Channel send() is intentionally a no-op and on_receive is never called —
v1 is write-only (visual tape) with no inbound messages.
"""

from __future__ import annotations

import asyncio
import contextlib
import platform
import socket
from uuid import uuid4

from bub.channels import Channel
from loguru import logger

from bub_eye.settings import EyeSettings
from bub_eye.supervisor import FFmpegSupervisor
from bub_eye.tape import VisualWriter

_STOP_WAIT_S = 10.0


def _is_intel_mac() -> bool:
    return platform.system() == "Darwin" and platform.machine() in {"x86_64", "i386"}


class EyeChannel(Channel):
    name = "eye"

    def __init__(self, settings: EyeSettings) -> None:
        self._settings = settings
        self._internal_stop: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._bridge_task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        if not self._settings.enabled:
            return False
        if not _is_intel_mac():
            logger.warning(
                "bub-eye: disabled — v1 supports Intel Mac only (host: {} {})",
                platform.system(),
                platform.machine(),
            )
            return False
        return True

    async def start(self, stop_event: asyncio.Event) -> None:
        if not self.enabled:
            return

        async def bridge() -> None:
            await stop_event.wait()
            self._internal_stop.set()

        self._bridge_task = asyncio.create_task(bridge())

        run_id = uuid4().hex
        host = socket.gethostname()
        writer = VisualWriter(
            tape_dir=self._settings.tape_dir,
            segment_seconds=self._settings.segment_seconds,
            run_id=run_id,
            host=host,
        )
        supervisor = FFmpegSupervisor(self._settings, writer.on_new_segment)
        self._task = asyncio.create_task(supervisor.run(self._internal_stop))
        logger.info("bub-eye: channel started (run_id={})", run_id)

    async def stop(self) -> None:
        self._internal_stop.set()
        for task in (self._task, self._bridge_task):
            if task is None:
                continue
            try:
                await asyncio.wait_for(task, timeout=_STOP_WAIT_S)
            except asyncio.TimeoutError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        logger.info("bub-eye: channel stopped")
