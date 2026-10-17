-- Metric 3: occupancy rate (census / certified beds) by state, next to staffing,
-- so states where staffing is out of line with patient load stand out.
SELECT state, facilities,
       ROUND(occupancy_rate * 100, 1) AS occupancy_pct,
       ROUND(nurse_hprd, 2)           AS nurse_hprd
FROM v_state_staffing
ORDER BY occupancy_pct DESC
