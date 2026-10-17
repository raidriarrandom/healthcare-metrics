-- Q3: Average staffing levels by state and facility ("hospital") type.
-- Type = CMS ownership type (For profit / Non profit / Government, with sub-types).
SELECT state,
       split_part(ownership_type, ' - ', 1)       AS ownership_group,
       COUNT(DISTINCT ccn)                         AS facilities,
       ROUND(SUM(nurse_hours) / SUM(census), 2)    AS nurse_hprd,
       ROUND(SUM(rn_hours) / SUM(census), 2)       AS rn_hprd
FROM gold_daily_staffing
WHERE is_valid_day AND ownership_type IS NOT NULL
GROUP BY 1, 2
ORDER BY state, ownership_group
