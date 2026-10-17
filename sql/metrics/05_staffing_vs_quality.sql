-- Metric 5: does more staffing go with better outcomes? Facilities split into staffing quartiles
-- (1 = lowest HPRD) against 30-day readmissions (SNF VBP), short-stay rehospitalization (claims 521),
-- star rating and nursing staff turnover (attrition).
SELECT hprd_quartile,
       COUNT(*)                                          AS facilities,
       ROUND(AVG(nurse_hours_per_resident_day), 2)       AS avg_hprd,
       ROUND(AVG(readmission_rate_fy2022) * 100, 2)      AS readmission_pct,
       ROUND(AVG(short_stay_rehospitalization_score), 2) AS rehospitalization_pct,
       ROUND(AVG(overall_rating), 2)                     AS avg_star_rating,
       ROUND(AVG(nursing_staff_turnover_pct), 1)         AS staff_turnover_pct
FROM v_facility_scorecard
GROUP BY hprd_quartile
ORDER BY hprd_quartile
