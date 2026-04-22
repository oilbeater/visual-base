"""EyeChannel: life-cycle wrapper that ties FFmpegSupervisor into Bub's gateway.

The Channel.send() is intentionally a no-op and on_receive is never called —
EyeChannel only writes (mp4 segments on disk) and injects auto-understand turns
back into the gateway via the `message_handler` it receives at plugin-provide
time.
"""

from __future__ import annotations

import asyncio
import contextlib
import platform
from uuid import uuid4

from bub.channels import Channel
from bub.types import MessageHandler
from loguru import logger

from bub_eye.settings import EyeSettings
from bub_eye.supervisor import FFmpegSupervisor
from bub_eye.understand import SegmentUnderstander

_STOP_WAIT_S = 10.0


def _is_mac() -> bool:
    return platform.system() == "Darwin"


class EyeChannel(Channel):
    name = "eye"

    def __init__(
        self,
        settings: EyeSettings,
        message_handler: MessageHandler | None = None,
    ) -> None:
        self._settings = settings
        self._message_handler = message_handler
        self._internal_stop: asyncio.Event = asyncio.Event()
        self._supervisor_task: asyncio.Task[None] | None = None
        self._understand_task: asyncio.Task[None] | None = None
        self._bridge_task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        if not self._settings.enabled:
            return False
        if not _is_mac():
            logger.warning(
                "bub-eye: disabled — macOS only (host: {} {})",
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
        supervisor = FFmpegSupervisor(self._settings)
        self._supervisor_task = asyncio.create_task(supervisor.run(self._internal_stop))
        logger.info("bub-eye: channel started (run_id={})", run_id)

        if self._message_handler is not None and self._settings.auto_understand_enabled:
            understander = SegmentUnderstander(self._settings, self._message_handler)
            self._understand_task = asyncio.create_task(
                understander.run(self._internal_stop)
            )

    async def stop(self) -> None:
        self._internal_stop.set()
        for task in (self._supervisor_task, self._understand_task, self._bridge_task):
            if task is None:
                continue
            try:
                await asyncio.wait_for(task, timeout=_STOP_WAIT_S)
            except asyncio.TimeoutError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        logger.info("bub-eye: channel stopped")
