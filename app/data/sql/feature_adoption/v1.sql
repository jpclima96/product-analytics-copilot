-- metric: feature_adoption
-- version: 1
-- params: $start (timestamp), $end (timestamp)
-- Para cada feature: usuários únicos que usaram a feature dividido pelo total de
-- usuários ativos (login/feature_used/session_start) no período [$start, $end).
WITH active AS (
    SELECT COUNT(DISTINCT user_id) AS active_users
    FROM events
    WHERE event_type IN ('login', 'feature_used', 'session_start')
      AND event_ts >= $start AND event_ts < $end
),
feat AS (
    SELECT
        json_extract_string(properties, '$.feature_name') AS feature_name,
        COUNT(DISTINCT user_id) AS users
    FROM events
    WHERE event_type = 'feature_used'
      AND event_ts >= $start AND event_ts < $end
    GROUP BY 1
)
SELECT
    f.feature_name,
    f.users,
    (SELECT active_users FROM active) AS active_users,
    ROUND(
        f.users * 1.0 / NULLIF((SELECT active_users FROM active), 0), 4
    ) AS adoption_rate
FROM feat f
ORDER BY f.users DESC;
