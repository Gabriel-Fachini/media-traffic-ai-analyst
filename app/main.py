"""Backward-compat shim — canonical location is app/api/routes.py."""
from __future__ import annotations

from app.api.deps import LLM_TIMEOUT_ERROR_MESSAGE as LLM_TIMEOUT_ERROR_MESSAGE
from app.api.deps import get_query_graph as get_query_graph
from app.api.routes import app as app

__all__ = ["app", "LLM_TIMEOUT_ERROR_MESSAGE", "get_query_graph"]
