-- metric: activation_rate
-- version: 1
-- params: $start (timestamp), $end (timestamp), $window_days (int)
-- Usuários que atingiram o evento 'activated' dentro de $window_days após o
-- signup, dividido pelo total de signups no período [$start, $end).
WITH signups AS (
    SELECT user_id, signup_ts
    FROM users
    WHERE signup_ts >= $start AND signup_ts < $end
),
activations AS (
    SELECT user_id, MIN(event_ts) AS activated_ts
    FROM events
    WHERE event_type = 'activated'
    GROUP BY user_id
),
joined AS (
    SELECT
        s.user_id,
        a.activated_ts,
        (a.activated_ts IS NOT NULL
         AND a.activated_ts <= s.signup_ts + ($window_days * INTERVAL 1 DAY)
        ) AS activated_in_window
    FROM signups s
    LEFT JOIN activations a ON a.user_id = s.user_id
)
SELECT
    COUNT(*)                                          AS signups,
    COUNT(*) FILTER (WHERE activated_in_window)       AS activated,
    ROUND(
        COUNT(*) FILTER (WHERE activated_in_window) * 1.0
        / NULLIF(COUNT(*), 0), 4
    )                                                 AS activation_rate
FROM joined;
