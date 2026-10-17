-- Metric 1: nurse-to-patient ratio (nurse hours per resident day, HPRD) by state.
-- CMS's proposed minimum is 3.48 total nurse HPRD, a useful benchmark line.
SELECT state, facilities, ROUND(nurse_hprd, 2) AS nurse_hprd, ROUND(rn_hprd, 2) AS rn_hprd
FROM v_state_staffing
ORDER BY nurse_hprd DESC
