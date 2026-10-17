-- Q4: What trends can you identify in patient length of stay over time?
-- The data has no admission or discharge dates, so length of stay cannot be calculated.
-- The closest available signal is resident census over time (residents present each day):
-- weekly average daily census, staffing per resident and occupancy across Q2 2024.
SELECT date_trunc('week', work_date)             AS week_start,
       ROUND(AVG(total_census))                  AS avg_daily_census,
       ROUND(SUM(total_nurse_hours) / SUM(total_census), 3) AS nurse_hprd,
       ROUND(AVG(occupancy_rate) * 100, 2)       AS occupancy_pct
FROM v_daily_national
GROUP BY 1
ORDER BY 1
