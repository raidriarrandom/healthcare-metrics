# Data Dictionary

Database: Glue Data Catalog `healthcare-project` (us-west-1). Bucket: `s3://healthcare-project122/`.
Full CMS column definitions for the supporting files: `NH_Data_Dictionary.pdf` (in the source Drive folder).

## Layers

| Layer | S3 prefix | Format | Catalog tables | Grain |
|---|---|---|---|---|
| Bronze | `Bronze/<table>/ingest_date=YYYY-MM-DD/` | CSV, exactly as downloaded | `bronze_<table>` | as in the source file |
| Silver | `Silver/<table>/ingest_date=YYYY-MM-DD/` | Parquet (snappy) | `silver_<table>` | as in the source file, cleaned |
| Gold | `Gold/<table>/` | Parquet (snappy) | `gold_daily_staffing`, `gold_facility_metrics` | facility-day, facility |
| Serving | Athena views | n/a | `v_state_staffing`, `v_monthly_state`, `v_daily_national`, `v_facility_scorecard` | state, state-month, day, facility |
| State | `_state/` | JSON | n/a | ingest manifest, Silver and Gold bookkeeping |

## Source files → Bronze/Silver tables

| Source file | Table | One row per | Used for |
|---|---|---|---|
| `PBJ_Daily_Nurse_Staffing_Q2_2024.csv` | `pbj_daily_staffing` | facility per day | all staffing metrics (master file) |
| `NH_ProviderInfo_Oct2024.csv` | `provider_info` | facility | certified beds (occupancy), ownership/provider type, star ratings, turnover |
| `FY_2024_SNF_VBP_Facility_Performance.csv` | `snf_vbp` | facility | 30-day readmission rate |
| `NH_QualityMsr_Claims_Oct2024.csv` | `quality_claims` | facility per measure | short-stay rehospitalization (measure 521) |
| `NH_QualityMsr_MDS_Oct2024.csv` | `quality_mds` | facility per measure | loaded, not used by the current metrics |
| `NH_Penalties_Oct2024.csv` | `penalties` | penalty | loaded, not used by the current metrics |
| any other CSV added to the Drive folder | name derived from the file name, e.g. `NH_HealthCitations_Oct2024.csv` → `health_citations` | as in the file | available for future metrics |

### Silver cleaning rules (all tables)

- Column names → snake_case (`Hrs_RNDON` → `hrs_rndon`, `CMS Certification Number (CCN)` → `ccn`)
- Facility key `PROVNUM` / `CMS Certification Number (CCN)` → **`ccn`**, text, zero-padded to 6 characters
- Empty strings → null; columns that are 100% null are dropped
- Columns whose values are all numeric → `double`; date-named columns → `date`
- ID-like columns (zip, FIPS, phone, `*_code`, `*_id`, footnotes) stay text so leading zeros survive
- Exact duplicate rows removed
- `ingest_date` partition column = the day the file was ingested from Drive

### `silver_pbj_daily_staffing` (master file)

| Column | Type | Description |
|---|---|---|
| `ccn` | string | Provider number (PROVNUM), unique facility ID, 6 characters |
| `provname` | string | Facility name |
| `city`, `state`, `county_name` | string | Location |
| `county_fips` | string | County FIPS code |
| `cy_qtr` | string | Calendar year quarter (`2024Q2`) |
| `workdate` | date | Work date |
| `mdscensus` | double | Residents in the facility that day (MDS census) |
| `hrs_rndon`, `_emp`, `_ctr` | double | RN Director of Nursing hours: total, employed, contract |
| `hrs_rnadmin`, `_emp`, `_ctr` | double | RN administrative hours |
| `hrs_rn`, `_emp`, `_ctr` | double | Registered Nurse direct-care hours |
| `hrs_lpnadmin`, `_emp`, `_ctr` | double | LPN administrative hours |
| `hrs_lpn`, `_emp`, `_ctr` | double | Licensed Practical Nurse direct-care hours |
| `hrs_cna`, `_emp`, `_ctr` | double | Certified Nursing Assistant hours |
| `hrs_natrn`, `_emp`, `_ctr` | double | Nurse aide in training hours |
| `hrs_medaide`, `_emp`, `_ctr` | double | Medication aide hours |
| `ingest_date` | string | Partition: ingestion date |

`_emp` = employed directly by the facility, `_ctr` = contract (agency) staff. For every role, total = `_emp` + `_ctr` (verified in the EDA).

## Gold tables

### `gold_daily_staffing`: one row per facility per day

| Column | Type | Definition |
|---|---|---|
| `ccn` | string | Facility ID |
| `work_date` | date | Day |
| `state`, `county_name` | string | Location (from PBJ) |
| `census` | double | Residents that day (`mdscensus`) |
| `certified_beds` | double | Federally certified beds (Provider Info) |
| `ownership_type` | string | e.g. `For profit - Corporation`, `Non profit - Church related`, `Government - County` |
| `provider_type` | string | `Medicare and Medicaid`, `Medicare`, `Medicaid` |
| `nurse_hours` | double | `hrs_rn + hrs_lpn + hrs_cna` (direct care; admin and DON hours excluded) |
| `rn_hours`, `lpn_hours`, `cna_hours` | double | The three components |
| `employed_hours` | double | Employed RN + LPN + CNA hours |
| `contract_hours` | double | Contract RN + LPN + CNA hours |
| `nurse_hours_per_resident_day` | double | `nurse_hours / census` (HPRD, the nurse-to-patient ratio) |
| `contract_share` | double | `contract_hours / nurse_hours` |
| `occupancy_rate` | double | `census / certified_beds` |
| `is_valid_day` | boolean | `census > 0 AND nurse_hours > 0 AND HPRD <= 24`. False for unreported (0 hours) or impossible days |

### `gold_facility_metrics`: one row per facility (Q2 2024, valid days only)

| Column | Type | Definition |
|---|---|---|
| `ccn`, `provider_name`, `state` | string | Facility |
| `ownership_type`, `provider_type` | string | Facility type (Provider Info) |
| `certified_beds` | double | Certified beds |
| `overall_rating`, `staffing_rating` | double | CMS five-star ratings (1–5) |
| `nursing_staff_turnover_pct` | double | Total nursing staff turnover % (Provider Info) |
| `rn_turnover_pct` | double | Registered nurse turnover % |
| `days_reported` | bigint | Days the facility appears in PBJ |
| `days_excluded` | bigint | Of those, days with `is_valid_day = false` (left out of every metric below) |
| `avg_census` | double | Average residents per day (patient throughput) |
| `total_nurse_hours`, `total_contract_hours` | double | Sums over the quarter |
| `nurse_hours_per_resident_day` | double | `SUM(nurse_hours) / SUM(census)` |
| `contract_share` | double | `SUM(contract_hours) / SUM(nurse_hours)` |
| `avg_occupancy_rate` | double | Average daily occupancy |
| `readmission_rate_fy2022` | double | SNF VBP risk-standardized 30-day readmission rate, FY2022 performance period (0.21 = 21%) |
| `short_stay_rehospitalization_score` | double | Claims measure 521: % of short-stay residents re-hospitalized after a nursing home admission (risk-adjusted) |

## Athena views (serving layer, `sql/views/`)

| View | Grain | Columns |
|---|---|---|
| `v_state_staffing` | state | facilities, total_nurse_hours, total_resident_days, total_contract_hours, resident_days_with_beds, bed_days, nurse_hprd, rn_hprd, contract_share, occupancy_rate (the raw sums let the dashboard re-weight any selection of states exactly) |
| `v_monthly_state` | month × state | facilities, total_nurse_hours, avg_daily_census, nurse_hprd, contract_share, occupancy_rate |
| `v_daily_national` | day | iso_day_of_week, facilities, total_census, total_nurse_hours, nurse_hprd, contract_share, occupancy_rate |
| `v_facility_scorecard` | facility | all `gold_facility_metrics` columns + `hprd_quartile` (1 = lowest staffing) + `occupancy_band` |

All ratios in the views are weighted: Σhours ÷ Σcensus, not an average of facility ratios, so big and small facilities count in proportion to their residents.

## State files (`_state/`)

| File | Written by | Purpose |
|---|---|---|
| `drive_manifest.json` | drive-ingest | Drive file name → md5, modified time, S3 key. A file is re-downloaded only when its md5 changes |
| `silver_processed.json` | bronze-to-silver | Bronze key → ETag already cleaned. Only new Bronze files are processed |
| `gold_built.json` | silver-gold | Copy of the Silver state at the last Gold build. Gold is skipped when Silver has not changed |
