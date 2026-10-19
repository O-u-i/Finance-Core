"""Stable ASGI entrypoint for the Workspace-scoped v3 application."""

from finance_core.app_v3 import app, create_app

__all__ = ["app", "create_app"]
