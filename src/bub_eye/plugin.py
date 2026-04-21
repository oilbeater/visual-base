"""bub-eye pluggy entry point."""

from __future__ import annotations

from bub import hookimpl
from bub.channels import Channel
from bub.types import MessageHandler

from bub_eye.channel import EyeChannel
from bub_eye.settings import EyeSettings


class EyeImpl:
    def __init__(self) -> None:
        self._settings = EyeSettings()

    @hookimpl
    def provide_channels(self, message_handler: MessageHandler) -> list[Channel]:
        return [EyeChannel(self._settings, message_handler=message_handler)]


main = EyeImpl()
