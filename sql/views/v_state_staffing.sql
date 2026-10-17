-- One row per state for the quarter (valid facility-days only).
-- HPRD = nurse hours per resident day, the "nurse-to-patient ratio" this data supports.
CREATE OR REPLACE VIEW v_state_staffing AS
SELECT
    state,
    COUNT(DISTINCT ccn)                                    AS facilities,
    SUM(nurse_hours)                                       AS total_nurse_hours,
    SUM(census)                                            AS total_resident_days,
    SUM(contract_hours)                                    AS total_contract_hours,
    SUM(CASE WHEN certified_beds > 0 THEN census END)      AS resident_days_with_beds,
    SUM(CASE WHEN certified_beds > 0 THEN certified_beds END) AS bed_days,
    SUM(nurse_hours) / SUM(census)                         AS nurse_hprd,
    SUM(rn_hours) / SUM(census)                            AS rn_hprd,
    SUM(contract_hours) / SUM(nurse_hours)                 AS contract_share,
    SUM(CASE WHEN certified_beds > 0 THEN census END)
        / SUM(CASE WHEN certified_beds > 0 THEN certified_beds END) AS occupancy_rate
FROM gold_daily_staffing
WHERE is_valid_day
GROUP BY state
