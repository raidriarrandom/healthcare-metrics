-- One row per state per month: total hours, staffing ratio, occupancy and contract share over time.
CREATE OR REPLACE VIEW v_monthly_state AS
SELECT
    date_trunc('month', work_date)                         AS month,
    state,
    COUNT(DISTINCT ccn)                                    AS facilities,
    SUM(nurse_hours)                                       AS total_nurse_hours,
    SUM(census) / COUNT(DISTINCT work_date)                AS avg_daily_census,
    SUM(nurse_hours) / SUM(census)                         AS nurse_hprd,
    SUM(contract_hours) / SUM(nurse_hours)                 AS contract_share,
    SUM(CASE WHEN certified_beds > 0 THEN census END)
        / SUM(CASE WHEN certified_beds > 0 THEN certified_beds END) AS occupancy_rate
FROM gold_daily_staffing
WHERE is_valid_day
GROUP BY 1, 2
