"""Background screen-recording plugin for Bub."""

__all__ = ["EyeImpl"]


def __getattr__(name: str) -> object:
    if name == "EyeImpl":
        from bub_eye.plugin import EyeImpl

        return EyeImpl
    raise AttributeError(f"module 'bub_eye' has no attribute {name!r}")
