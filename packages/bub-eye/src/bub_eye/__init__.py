"""Background screen-recording plugin for Bub."""

__all__ = ["main"]


def __getattr__(name: str) -> object:
    if name == "main":
        from bub_eye.plugin import main

        return main
    raise AttributeError(f"module 'bub_eye' has no attribute {name!r}")
