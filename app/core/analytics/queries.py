from __future__ import annotations

from app.core.schema_catalog import DATASET_ID

TRAFFIC_VOLUME_SQL = f"""
SELECT
    COALESCE(traffic_source, 'Unknown') AS traffic_source,
    COUNT(DISTINCT id) AS user_count
FROM `{DATASET_ID}.users`
WHERE DATE(created_at) BETWEEN @start_date AND @end_date
    AND (
            @traffic_source IS NULL
            OR LOWER(COALESCE(traffic_source, 'Unknown')) = LOWER(@traffic_source)
    )
GROUP BY COALESCE(traffic_source, 'Unknown')
ORDER BY user_count DESC
"""

CHANNEL_PERFORMANCE_SQL = f"""
SELECT
    COALESCE(u.traffic_source, 'Unknown') AS traffic_source,
    -- Each order can have multiple order_items rows, so DISTINCT avoids overcounting.
    COUNT(DISTINCT o.order_id) AS total_orders,
    COALESCE(ROUND(SUM(CAST(oi.sale_price AS NUMERIC)), 2), 0) AS total_revenue
FROM `{DATASET_ID}.users` u
INNER JOIN `{DATASET_ID}.orders` o
    ON u.id = o.user_id
INNER JOIN `{DATASET_ID}.order_items` oi
    ON o.order_id = oi.order_id
WHERE DATE(o.created_at) BETWEEN @start_date AND @end_date
    AND o.status = 'Complete'
    AND (
            @traffic_source IS NULL
            OR LOWER(COALESCE(u.traffic_source, 'Unknown')) = LOWER(@traffic_source)
    )
GROUP BY COALESCE(u.traffic_source, 'Unknown')
ORDER BY total_revenue DESC, total_orders DESC
"""
