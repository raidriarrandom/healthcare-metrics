# Glue Spark job: build the two Gold tables from Silver and save them to S3 as Parquet.
#
# Gold tables:
#   gold_daily_staffing   = one row per facility per day (staffing, census, occupancy, contract share, quality flag)
#   gold_facility_metrics = one row per facility for the quarter, joined with ProviderInfo,
#                           VBP readmission rates and the claims rehospitalization measure (521)
#
# Definitions (see docs/solution_design_doc.md):
#   nurse_hours    = RN + LPN + CNA direct-care hours (admin and director hours left out)
#   contract_share = contract hours / nurse hours (closest thing to overtime; PBJ has no overtime column)
#   occupancy_rate = census / certified beds
#   is_valid_day   = census > 0 AND nurse_hours > 0 AND nurse hours per resident <= 24
#                    (other rows are missing reports or impossible values). Facility metrics use valid days only.
#
# Incremental: if nothing new reached Silver since the last Gold build, the job stops early.

import json

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F


# ---------- Settings ----------
BUCKET = "healthcare-project122"
REGION = "us-west-1"
SILVER_STATE_KEY = "_state/silver_processed.json"
GOLD_STATE_KEY = "_state/gold_built.json"
SILVER = "s3://" + BUCKET + "/Silver/"


# ---------- The Gold SQL ----------
# Table 1: one row per facility per day
GOLD_DAILY_SQL = """
WITH base AS (
    SELECT
        s.ccn,
        s.workdate AS work_date,
        s.state,
        s.county_name,
        s.mdscensus AS census,
        s.hrs_rn + s.hrs_lpn + s.hrs_cna AS nurse_hours,
        s.hrs_rn AS rn_hours,
        s.hrs_lpn AS lpn_hours,
        s.hrs_cna AS cna_hours,
        s.hrs_rn_emp + s.hrs_lpn_emp + s.hrs_cna_emp AS employed_hours,
        s.hrs_rn_ctr + s.hrs_lpn_ctr + s.hrs_cna_ctr AS contract_hours,
        p.number_of_certified_beds AS certified_beds,
        p.ownership_type,
        p.provider_type
    FROM pbj_daily_staffing s
    LEFT JOIN provider_info p ON s.ccn = p.ccn
)
SELECT
    ccn, work_date, state, county_name, census, certified_beds, ownership_type, provider_type,
    nurse_hours, rn_hours, lpn_hours, cna_hours, employed_hours, contract_hours,
    nurse_hours / NULLIF(census, 0)          AS nurse_hours_per_resident_day,
    contract_hours / NULLIF(nurse_hours, 0)  AS contract_share,
    census / NULLIF(certified_beds, 0)       AS occupancy_rate,
    (census > 0 AND nurse_hours > 0 AND nurse_hours / census <= 24) AS is_valid_day
FROM base
"""

# Table 2: one row per facility (built from table 1)
GOLD_FACILITY_SQL = """
WITH day_counts AS (
    SELECT ccn,
           COUNT(*)                                     AS days_reported,
           SUM(CASE WHEN is_valid_day THEN 0 ELSE 1 END) AS days_excluded
    FROM gold_daily_staffing
    GROUP BY ccn
),
agg AS (
    SELECT
        ccn,
        MAX(state)                                      AS state,
        AVG(census)                                     AS avg_census,
        SUM(nurse_hours)                                AS total_nurse_hours,
        SUM(contract_hours)                             AS total_contract_hours,
        SUM(nurse_hours) / NULLIF(SUM(census), 0)       AS nurse_hours_per_resident_day,
        SUM(contract_hours) / NULLIF(SUM(nurse_hours), 0) AS contract_share,
        AVG(occupancy_rate)                             AS avg_occupancy_rate
    FROM gold_daily_staffing
    WHERE is_valid_day
    GROUP BY ccn
)
SELECT
    a.ccn,
    p.provider_name,
    a.state,
    p.ownership_type,
    p.provider_type,
    p.number_of_certified_beds AS certified_beds,
    p.overall_rating,
    p.staffing_rating,
    p.total_nursing_staff_turnover AS nursing_staff_turnover_pct,
    p.registered_nurse_turnover AS rn_turnover_pct,
    d.days_reported,
    d.days_excluded,
    a.avg_census,
    a.total_nurse_hours,
    a.total_contract_hours,
    a.nurse_hours_per_resident_day,
    a.contract_share,
    a.avg_occupancy_rate,
    v.performance_period_fy_2022_risk_standardized_readmission_rate AS readmission_rate_fy2022,
    c.adjusted_score AS short_stay_rehospitalization_score
FROM agg a
JOIN day_counts d ON a.ccn = d.ccn
LEFT JOIN provider_info p ON a.ccn = p.ccn
LEFT JOIN snf_vbp v ON a.ccn = v.ccn
LEFT JOIN (SELECT ccn, adjusted_score FROM quality_claims WHERE measure_code = '521') c ON a.ccn = c.ccn
"""


# ---------- Helper function ----------
def read_state_file(key):
    # Read a small JSON file from S3. Returns {} if it doesn't exist yet.
    try:
        response = s3.get_object(Bucket=BUCKET, Key=key)
        return json.loads(response["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {}


# ---------- Step 1: start Spark and connect to S3 ----------
spark_context = SparkContext.getOrCreate()
glue_context = GlueContext(spark_context)
spark = glue_context.spark_session
job = Job(glue_context)
job.init("healthcare-silver-to-gold", {})

s3 = boto3.client("s3", region_name=REGION)


# ---------- Step 2: stop early if Silver hasn't changed ----------
silver_state = read_state_file(SILVER_STATE_KEY)    # what Silver has processed so far
gold_state = read_state_file(GOLD_STATE_KEY)        # what Silver looked like at the last Gold build

if gold_state.get("silver_state") == silver_state:
    print("Silver unchanged since the last Gold build; nothing to do")
else:
    # ---------- Step 3: load the Silver tables Gold needs ----------
    # The staffing table: every ingest date
    pbj = spark.read.parquet(SILVER + "pbj_daily_staffing/")
    pbj.createOrReplaceTempView("pbj_daily_staffing")

    # Reference tables: only their newest ingest date (so an old copy never doubles the rows)
    for table in ["provider_info", "snf_vbp", "quality_claims"]:
        df = spark.read.parquet(SILVER + table + "/")
        newest_date = df.agg(F.max("ingest_date")).first()[0]
        df = df.filter(F.col("ingest_date") == newest_date)
        df.createOrReplaceTempView(table)


    # ---------- Step 4: build the two Gold tables with SQL ----------
    daily = spark.sql(GOLD_DAILY_SQL)
    daily = daily.cache()                     # keep it in memory: table 2 reads it again
    daily.createOrReplaceTempView("gold_daily_staffing")

    facility = spark.sql(GOLD_FACILITY_SQL)


    # ---------- Step 5: save both to S3 Gold ----------
    daily.write.mode("overwrite").parquet("s3://" + BUCKET + "/Gold/gold_daily_staffing/")
    print("wrote s3://" + BUCKET + "/Gold/gold_daily_staffing/")

    facility.write.mode("overwrite").parquet("s3://" + BUCKET + "/Gold/gold_facility_metrics/")
    print("wrote s3://" + BUCKET + "/Gold/gold_facility_metrics/")


    # ---------- Step 6: remember what Silver looked like for this build ----------
    s3.put_object(Bucket=BUCKET, Key=GOLD_STATE_KEY, Body=json.dumps({"silver_state": silver_state}))

job.commit()
