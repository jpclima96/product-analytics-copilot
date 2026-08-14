-- metric: onboarding_funnel
-- version: 1
-- params: $start (timestamp), $end (timestamp)
-- Conversão passo-a-passo do onboarding: usuários distintos por passo,
-- % do topo do funil e % do passo anterior.
WITH steps AS (
    SELECT
        CAST(json_extract_string(properties, '$.step') AS INTEGER) AS step,
        user_id
    FROM events
    WHERE event_type = 'onboarding_step_completed'
      AND event_ts >= $start AND event_ts < $end
),
counts AS (
    SELECT step, COUNT(DISTINCT user_id) AS users
    FROM steps
    GROUP BY step
)
SELECT
    step,
    users,
    ROUND(
        users * 1.0 / NULLIF(
            first_value(users) OVER (
                ORDER BY step
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            ), 0), 4
    ) AS pct_of_top,
    ROUND(
        users * 1.0 / NULLIF(LAG(users) OVER (ORDER BY step), 0), 4
    ) AS pct_of_prev
FROM counts
ORDER BY step;
