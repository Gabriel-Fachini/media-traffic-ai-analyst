"""Backward-compat shim — real implementation moved to app/core/analytics/traffic_volume.py."""

from app.core.analytics.queries import TRAFFIC_VOLUME_SQL
from app.core.analytics.traffic_volume import traffic_volume_analyzer

__all__ = ["TRAFFIC_VOLUME_SQL", "traffic_volume_analyzer"]
