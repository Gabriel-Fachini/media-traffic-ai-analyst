"""Backward-compat shim — real implementation moved to app/core/analytics/models.py."""

from app.core.analytics.models import (
    ChannelPerformanceInput,
    ChannelPerformanceOutput,
    ChannelPerformanceRow,
    DateRangeInput,
    ToolInputBase,
    TrafficVolumeInput,
    TrafficVolumeOutput,
    TrafficVolumeRow,
)

__all__ = [
    "ChannelPerformanceInput",
    "ChannelPerformanceOutput",
    "ChannelPerformanceRow",
    "DateRangeInput",
    "ToolInputBase",
    "TrafficVolumeInput",
    "TrafficVolumeOutput",
    "TrafficVolumeRow",
]
