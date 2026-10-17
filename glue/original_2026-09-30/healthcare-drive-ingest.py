"""Glue Python shell job: incrementally copy CSVs from a Google Drive folder to S3 Bronze.

Incremental rule: a file is downloaded only if it is new or its Drive md5Checksum differs
from the value recorded in the manifest (s3://<bucket>/_state/drive_manifest.json).
The manifest is written only after every changed file uploaded successfully.

Bucket, folder, secret and region default to the values in DEFAULTS at the bottom; a Glue job
parameter of the same name (--bucket, --drive_folder_id, --secret_id, --region) overrides them.
Required job parameter: --additional-python-modules google-api-python-client,google-auth
"""
import json
import sys
from datetime import date

import boto3
from botocore.exceptions import ClientError

MANIFEST_KEY = "_state/drive_manifest.json"
# Source file name -> Bronze table folder. Files not listed here are ignored (e.g. the PDF).
TABLES = {
    "PBJ_Daily_Nurse_Staffing_Q2_2024.csv": "pbj_daily_staffing",
    "NH_ProviderInfo_Oct2024.csv": "provider_info",
    "FY_2024_SNF_VBP_Facility_Performance.csv": "snf_vbp",
    "NH_QualityMsr_Claims_Oct2024.csv": "quality_claims",
    "NH_QualityMsr_MDS_Oct2024.csv": "quality_mds",
    "NH_Penalties_Oct2024.csv": "penalties",
}


def files_to_sync(drive_files: list[dict], manifest: dict) -> list[dict]:
    """Return the Drive files that are new or changed since the manifest was written."""
    return [
        f for f in drive_files
        if f["name"] in TABLES and manifest.get(f["name"], {}).get("md5Checksum") != f.get("md5Checksum")
    ]


def load_manifest(s3, bucket: str) -> dict:
    try:
        body = s3.get_object(Bucket=bucket, Key=MANIFEST_KEY)["Body"].read()
        return json.loads(body)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return {}
        raise


def drive_service_and_session(secret_json: str):
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(
        json.loads(secret_json), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False), AuthorizedSession(creds)


def list_folder(service, folder_id: str) -> list[dict]:
    files, token = [], None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, md5Checksum, modifiedTime, size)",
            pageSize=100, pageToken=token,
        ).execute()
        files.extend(resp["files"])
        token = resp.get("nextPageToken")
        if not token:
            return files


def main(args: dict) -> None:
    s3 = boto3.client("s3", region_name=args["region"])
    secret = boto3.client("secretsmanager", region_name=args["region"]).get_secret_value(
        SecretId=args["secret_id"])["SecretString"]
    service, session = drive_service_and_session(secret)

    manifest = load_manifest(s3, args["bucket"])
    changed = files_to_sync(list_folder(service, args["drive_folder_id"]), manifest)
    print(f"{len(changed)} new/changed file(s): {[f['name'] for f in changed]}")

    today = date.today().isoformat()
    for f in changed:
        key = f"Bronze/{TABLES[f['name']]}/ingest_date={today}/{f['name']}"
        url = f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media"
        with session.get(url, stream=True) as resp:
            resp.raise_for_status()
            resp.raw.decode_content = True  # Drive sends gzip; without this the gzipped bytes land in S3 as ".csv"
            s3.upload_fileobj(resp.raw, args["bucket"], key)  # streamed, not held in memory
        manifest[f["name"]] = {"md5Checksum": f["md5Checksum"], "modifiedTime": f["modifiedTime"], "s3_key": key}
        print(f"uploaded s3://{args['bucket']}/{key}")

    if changed:  # manifest written last: a failed upload leaves the file to be retried next run
        s3.put_object(Bucket=args["bucket"], Key=MANIFEST_KEY, Body=json.dumps(manifest, indent=2).encode())


DEFAULTS = {
    "bucket": "healthcare-project122",
    "drive_folder_id": "18ApfX4tckd3X1k0PReXibvfoCXoYqDP-",
    "secret_id": "healthcare-project/drive-service-account",
    "region": "us-west-1",
}


if __name__ == "__main__":
    from awsglue.utils import getResolvedOptions  # only available inside Glue

    args = dict(DEFAULTS)
    overrides = [k for k in DEFAULTS if f"--{k}" in sys.argv]  # job parameters win over the defaults
    if overrides:
        args.update(getResolvedOptions(sys.argv, overrides))
    main(args)
