"""bub-eye pluggy entry point."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from bub import hookimpl
from bub.channels import Channel
from bub.types import MessageHandler

from bub_eye.channel import EyeChannel
from bub_eye.settings import build_settings

if TYPE_CHECKING:
    from bub.framework import BubFramework


class EyeImpl:
    """Plugin shim. Holds a live reference to the framework so the
    workspace value read at ``provide_channels`` time is the post-CLI
    one (``--workspace`` has already been applied by then).
    """

    def __init__(self, framework: "BubFramework | None" = None) -> None:
        self._framework = framework

    @hookimpl
    def provide_channels(self, message_handler: MessageHandler) -> list[Channel]:
        workspace = (
            self._framework.workspace
            if self._framework is not None
            else Path.cwd().resolve()
        )
        settings = build_settings(workspace)
        return [EyeChannel(settings, message_handler=message_handler)]
