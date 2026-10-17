"""Deploy the Healthcare pipeline to AWS (safe to re-run).

1. Upload glue/*.py to the Glue assets bucket (the jobs already point at these keys)
2. Create/update the Glue workflow that runs the whole pipeline daily:
     06:00 PT  drive-ingest -> bronze-to-silver -> silver-gold + silver crawler -> gold crawler
                           \-> bronze crawler
3. Create the Athena workgroup (results go to s3://healthcare-project122/athena-results/)
4. Create/replace the Athena views in sql/views/

Usage:  AWS_PROFILE=admin python scripts/deploy.py [--run] [--skip-views]
  --run         also start the workflow once now
  --skip-views  skip step 4 (first deploy only: the views need the Gold columns the first run creates)
"""
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).parent))
from athena_client import REGION, WORKGROUP, run_query  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS_BUCKET = "aws-glue-assets-499502048569-us-west-1"
DATA_BUCKET = "healthcare-project122"
WORKFLOW = "healthcare-daily-pipeline"
SCHEDULE = "cron(0 13 * * ? *)"  # 13:00 UTC = 06:00 PDT / 05:00 PST

INGEST, SILVER, GOLD = "healthcare-drive-ingest", "healthcare-bronze-to-silver", "healthcare-silver-gold"
CRAWLER_BRONZE, CRAWLER_SILVER, CRAWLER_GOLD = (
    "healthcare-crawler-bronze", "heatlhcare-crawler-silver", "healthcare-crawler-gold")


def after(job: str) -> dict:
    return {"Logical": "AND", "Conditions": [{"LogicalOperator": "EQUALS", "JobName": job, "State": "SUCCEEDED"}]}


TRIGGERS = [
    {"Name": "healthcare-daily-start", "Type": "SCHEDULED", "Schedule": SCHEDULE,
     "Actions": [{"JobName": INGEST}]},
    {"Name": "healthcare-after-ingest", "Type": "CONDITIONAL", "Predicate": after(INGEST),
     "Actions": [{"JobName": SILVER}, {"CrawlerName": CRAWLER_BRONZE}]},
    {"Name": "healthcare-after-silver", "Type": "CONDITIONAL", "Predicate": after(SILVER),
     "Actions": [{"JobName": GOLD}, {"CrawlerName": CRAWLER_SILVER}]},
    {"Name": "healthcare-after-gold", "Type": "CONDITIONAL", "Predicate": after(GOLD),
     "Actions": [{"CrawlerName": CRAWLER_GOLD}]},
]


def upload_scripts(s3) -> None:
    for path in sorted((ROOT / "glue").glob("*.py")):
        s3.upload_file(str(path), ASSETS_BUCKET, f"scripts/{path.name}")
        print(f"uploaded s3://{ASSETS_BUCKET}/scripts/{path.name}")


def ensure_workflow(glue) -> None:
    try:
        glue.create_workflow(Name=WORKFLOW, Description="Daily: Google Drive -> Bronze -> Silver -> Gold -> catalog")
        print(f"created workflow {WORKFLOW}")
    except glue.exceptions.AlreadyExistsException:
        print(f"workflow {WORKFLOW} exists")

    for t in TRIGGERS:
        update = {k: v for k, v in t.items() if k in ("Schedule", "Predicate", "Actions")}
        try:
            glue.create_trigger(WorkflowName=WORKFLOW, StartOnCreation=True, **t)
            print(f"created trigger {t['Name']}")
        except glue.exceptions.AlreadyExistsException:
            glue.update_trigger(Name=t["Name"], TriggerUpdate=update)
            print(f"updated trigger {t['Name']}")


def ensure_workgroup(athena) -> None:
    config = {
        "ResultConfiguration": {"OutputLocation": f"s3://{DATA_BUCKET}/athena-results/"},
        "EnforceWorkGroupConfiguration": True,
        "BytesScannedCutoffPerQuery": 10 * 1024**3,  # guard rail: no query may scan more than 10 GB
    }
    try:
        athena.create_work_group(Name=WORKGROUP, Configuration=config,
                                 Description="Healthcare metrics: views, metric queries, dashboard")
        print(f"created Athena workgroup {WORKGROUP}")
    except athena.exceptions.InvalidRequestException as e:
        if "already" not in str(e).lower():
            raise
        print(f"Athena workgroup {WORKGROUP} exists")


def create_views() -> None:
    for path in sorted((ROOT / "sql" / "views").glob("*.sql")):
        run_query(path.read_text())
        print(f"created view {path.stem}")


def main() -> None:
    session = boto3.Session(region_name=REGION)
    upload_scripts(session.client("s3"))
    ensure_workflow(session.client("glue"))
    ensure_workgroup(session.client("athena"))
    if "--skip-views" not in sys.argv:
        create_views()
    if "--run" in sys.argv:
        run_id = session.client("glue").start_workflow_run(Name=WORKFLOW)["RunId"]
        print(f"started workflow run {run_id}")


if __name__ == "__main__":
    main()
