"""Backward-compat shim — real implementation moved to app/core/router/decision.py."""

from app.core.router.decision import (
    RouterClarificationReason,
    RouterDecision,
    RouterIntent,
    RouterNormalizedParams,
    RouterRefusalReason,
)

__all__ = [
    "RouterClarificationReason",
    "RouterDecision",
    "RouterIntent",
    "RouterNormalizedParams",
    "RouterRefusalReason",
]
