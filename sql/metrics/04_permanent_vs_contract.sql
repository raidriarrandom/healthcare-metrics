-- Metric 4: ratio of permanent (employed) to contract staff hours, by state.
SELECT state,
       ROUND((1 - contract_share) * 100, 1)        AS employed_pct,
       ROUND(contract_share * 100, 1)              AS contract_pct,
       ROUND((1 - contract_share) / NULLIF(contract_share, 0), 1) AS employed_to_contract_ratio
FROM v_state_staffing
ORDER BY contract_pct DESC
