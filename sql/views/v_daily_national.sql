-- One row per day, all facilities: drives the trend charts (daily and weekly).
CREATE OR REPLACE VIEW v_daily_national AS
SELECT
    work_date,
    day_of_week(work_date)                                 AS iso_day_of_week,
    COUNT(DISTINCT ccn)                                    AS facilities,
    SUM(census)                                            AS total_census,
    SUM(nurse_hours)                                       AS total_nurse_hours,
    SUM(nurse_hours) / SUM(census)                         AS nurse_hprd,
    SUM(contract_hours) / SUM(nurse_hours)                 AS contract_share,
    SUM(CASE WHEN certified_beds > 0 THEN census END)
        / SUM(CASE WHEN certified_beds > 0 THEN certified_beds END) AS occupancy_rate
FROM gold_daily_staffing
WHERE is_valid_day
GROUP BY work_date
