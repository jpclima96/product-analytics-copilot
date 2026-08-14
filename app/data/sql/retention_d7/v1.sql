-- metric: retention_d7
-- version: 1
-- params: $start (timestamp), $end (timestamp)
-- Dos usuários que fizeram signup em [$start, $end - 8 dias], a fração que teve
-- pelo menos um evento de atividade (login/feature_used/session_start) no dia 7
-- exato após o signup, janela [D+7, D+8). Coortes sem 8 dias completos de
-- observação são excluídas para não deflacionar a métrica.
WITH cohort AS (
    SELECT user_id, signup_ts
    FROM users
    WHERE signup_ts >= $start
      AND signup_ts + INTERVAL 8 DAY <= $end
),
d7_active AS (
    SELECT DISTINCT c.user_id
    FROM cohort c
    JOIN events e ON e.user_id = c.user_id
    WHERE e.event_type IN ('login', 'feature_used', 'session_start')
      AND e.event_ts >= c.signup_ts + INTERVAL 7 DAY
      AND e.event_ts <  c.signup_ts + INTERVAL 8 DAY
)
SELECT
    COUNT(*)                                          AS cohort_users,
    COUNT(a.user_id)                                  AS retained_d7,
    ROUND(COUNT(a.user_id) * 1.0 / NULLIF(COUNT(*), 0), 4) AS retention_d7
FROM cohort c
LEFT JOIN d7_active a ON a.user_id = c.user_id;
