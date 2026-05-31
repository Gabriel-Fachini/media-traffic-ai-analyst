"""Backward-compat shim — real implementation moved to app/core/router/classifier.py."""

from app.core.router.classifier import (
    build_router_thread_context,
    classify_question,
)

__all__ = ["build_router_thread_context", "classify_question"]
