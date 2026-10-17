-- Q1: What is the relationship between nurse staffing levels and occupancy rates?
-- Average staffing per occupancy band, plus the facility-level correlation coefficient
-- (Pearson r between nurse HPRD and occupancy; -1..1, 0 = no linear relationship).
WITH r AS (
    SELECT CORR(nurse_hours_per_resident_day, avg_occupancy_rate) AS correlation
    FROM v_facility_scorecard
)
SELECT s.occupancy_band,
       COUNT(*)                                     AS facilities,
       ROUND(AVG(s.nurse_hours_per_resident_day), 2) AS avg_hprd,
       ROUND(AVG(s.contract_share) * 100, 1)        AS avg_contract_pct,
       ROUND(MAX(r.correlation), 3)                 AS overall_correlation
FROM v_facility_scorecard s
CROSS JOIN r
GROUP BY s.occupancy_band
ORDER BY s.occupancy_band
