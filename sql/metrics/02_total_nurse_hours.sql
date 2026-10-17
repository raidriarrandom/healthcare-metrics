-- Metric 2: total nurse hours (RN + LPN + CNA) by state and month.
SELECT month, state, facilities, ROUND(total_nurse_hours) AS total_nurse_hours
FROM v_monthly_state
ORDER BY month, total_nurse_hours DESC
