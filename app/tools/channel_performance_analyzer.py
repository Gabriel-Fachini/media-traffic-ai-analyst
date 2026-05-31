"""Backward-compat shim — real implementation moved to app/core/analytics/channel_performance.py."""

from app.core.analytics.channel_performance import channel_performance_analyzer
from app.core.analytics.queries import CHANNEL_PERFORMANCE_SQL

__all__ = ["CHANNEL_PERFORMANCE_SQL", "channel_performance_analyzer"]
