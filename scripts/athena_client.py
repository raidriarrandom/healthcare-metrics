"""Tiny Athena helper shared by deploy.py, run_metrics.py and the Streamlit dashboard."""
from __future__ import annotations

import time

import boto3
import pandas as pd

REGION = "us-west-1"
DATABASE = "healthcare-project"
WORKGROUP = "healthcare-analytics"


def run_query(sql: str, session: boto3.Session | None = None) -> pd.DataFrame:
    """Run one statement in the project workgroup and return its rows (empty frame for DDL)."""
    athena = (session or boto3.Session()).client("athena", region_name=REGION)
    qid = athena.start_query_execution(
        QueryString=sql, QueryExecutionContext={"Database": DATABASE}, WorkGroup=WORKGROUP
    )["QueryExecutionId"]

    delay = 0.5
    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(delay)
        delay = min(delay * 2, 5)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(f"Athena query {qid} {status['State']}: {status.get('StateChangeReason')}")

    rows, columns, token = [], None, None
    while True:
        kwargs = {"QueryExecutionId": qid, "MaxResults": 1000, **({"NextToken": token} if token else {})}
        page = athena.get_query_results(**kwargs)
        if columns is None:
            meta = page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            columns = [(c["Name"], c["Type"]) for c in meta]
            page_rows = page["ResultSet"]["Rows"][1:]  # first row of the first page is the header
        else:
            page_rows = page["ResultSet"]["Rows"]
        rows += [[d.get("VarCharValue") for d in r["Data"]] for r in page_rows]
        token = page.get("NextToken")
        if not token:
            break

    df = pd.DataFrame(rows, columns=[n for n, _ in columns or []])
    for name, typ in columns or []:  # Athena returns strings; restore numbers and dates
        if typ in ("double", "float", "decimal", "bigint", "integer", "smallint", "tinyint"):
            df[name] = pd.to_numeric(df[name])
        elif typ in ("date", "timestamp"):
            df[name] = pd.to_datetime(df[name])
    return df
