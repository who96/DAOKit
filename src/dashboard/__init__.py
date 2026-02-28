from __future__ import annotations

"""Dashboard module exports."""

__all__ = ["create_app"]


def __getattr__(name: str):
    if name == "create_app":
        from dashboard.server import create_app

        globals()["create_app"] = create_app
        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
