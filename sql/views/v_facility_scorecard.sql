-- One row per facility with staffing and occupancy bands, used for rankings and the scatter charts.
CREATE OR REPLACE VIEW v_facility_scorecard AS
SELECT
    f.*,
    NTILE(4) OVER (ORDER BY f.nurse_hours_per_resident_day) AS hprd_quartile,
    CASE
        WHEN f.avg_occupancy_rate < 0.60 THEN '1: <60%'
        WHEN f.avg_occupancy_rate < 0.75 THEN '2: 60-75%'
        WHEN f.avg_occupancy_rate < 0.90 THEN '3: 75-90%'
        ELSE '4: 90%+'
    END AS occupancy_band
FROM gold_facility_metrics f
WHERE f.avg_occupancy_rate IS NOT NULL
  AND f.nurse_hours_per_resident_day IS NOT NULL
