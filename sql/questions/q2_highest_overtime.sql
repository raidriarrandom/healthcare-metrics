-- Q2: Which facilities have the highest overtime hours?
-- PBJ has no overtime field, so contract (agency) hours are the proxy: hours the facility could not
-- cover with its own employees. Top 10 by total contract hours, with their share of all nurse hours.
SELECT provider_name, state, ownership_type,
       ROUND(total_contract_hours)         AS contract_hours,
       ROUND(contract_share * 100, 1)      AS contract_pct,
       ROUND(nurse_hours_per_resident_day, 2) AS nurse_hprd
FROM gold_facility_metrics
ORDER BY total_contract_hours DESC
LIMIT 10
