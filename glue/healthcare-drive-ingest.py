# Glue Python shell job: copy NEW or CHANGED CSV files from Google Drive into S3 Bronze.
#
# How it knows what's new:
#   Google Drive gives every file an md5 "fingerprint". After each run we save the
#   fingerprints in S3 (_state/drive_manifest.json). Next run, a file is copied only if
#   it isn't in that list yet, or its fingerprint changed.
#
# Glue job parameter needed: --additional-python-modules google-api-python-client,google-auth

import json
from datetime import date

import boto3
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from googleapiclient.discovery import build


# ---------- Settings ----------
BUCKET = "healthcare-project122"
DRIVE_FOLDER_ID = "18ApfX4tckd3X1k0PReXibvfoCXoYqDP-"
SECRET_ID = "healthcare-project/drive-service-account"
REGION = "us-west-1"
MANIFEST_KEY = "_state/drive_manifest.json"

# Short table names for the files the metrics use.
# Any other CSV gets a name made from its file name (see make_table_name).
TABLES = {
    "PBJ_Daily_Nurse_Staffing_Q2_2024.csv": "pbj_daily_staffing",
    "NH_ProviderInfo_Oct2024.csv": "provider_info",
    "FY_2024_SNF_VBP_Facility_Performance.csv": "snf_vbp",
    "NH_QualityMsr_Claims_Oct2024.csv": "quality_claims",
    "NH_QualityMsr_MDS_Oct2024.csv": "quality_mds",
    "NH_Penalties_Oct2024.csv": "penalties",
    "NH_StateUSAverages_Oct2024.csv": "state_us_averages",
    "Skilled_Nursing_Facility_Quality_Reporting_Program_Provider_Data_Oct2024.csv": "snf_qrp_provider",
}


def make_table_name(file_name):
    # Example: "NH_HealthCitations_Oct2024.csv" -> "health_citations"
    if file_name in TABLES:
        return TABLES[file_name]

    name = file_name.replace(".csv", "")

    # Remove "NH_" at the start
    if name.startswith("NH_"):
        name = name[3:]

    # Remove a month tag at the end, like "_Oct2024" (3 letters + 4 digits)
    last_part = name.split("_")[-1]
    if len(last_part) == 7 and last_part[:3].isalpha() and last_part[3:].isdigit():
        name = name[:-8]   # 8 = the underscore + 7 characters

    # Put "_" between a lowercase letter and a capital: HealthCitations -> Health_Citations
    table = ""
    previous = ""
    for letter in name:
        if letter.isupper() and previous.islower():
            table = table + "_"
        table = table + letter
        previous = letter

    return table.lower()


# ---------- Step 1: connect to AWS and Google Drive ----------
s3 = boto3.client("s3", region_name=REGION)

# The Google service account key lives in Secrets Manager, never in the code
secrets = boto3.client("secretsmanager", region_name=REGION)
secret_text = secrets.get_secret_value(SecretId=SECRET_ID)["SecretString"]

credentials = service_account.Credentials.from_service_account_info(
    json.loads(secret_text),
    scopes=["https://www.googleapis.com/auth/drive.readonly"],
)
drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
download_session = AuthorizedSession(credentials)


# ---------- Step 2: load last run's fingerprints ----------
try:
    response = s3.get_object(Bucket=BUCKET, Key=MANIFEST_KEY)
    manifest = json.loads(response["Body"].read())
except s3.exceptions.NoSuchKey:
    manifest = {}   # first run ever: nothing saved yet


# ---------- Step 3: list every file in the Drive folder ----------
# Drive returns up to 100 files per page, so keep asking until there are no more pages.
drive_files = []
page_token = None
while True:
    response = drive.files().list(
        q="'" + DRIVE_FOLDER_ID + "' in parents and trashed = false",
        fields="nextPageToken, files(id, name, md5Checksum, modifiedTime, size)",
        pageSize=100,
        pageToken=page_token,
    ).execute()
    for f in response["files"]:
        drive_files.append(f)
    page_token = response.get("nextPageToken")
    if page_token is None:
        break


# ---------- Step 4: keep only CSVs that are new or changed ----------
changed = []
for f in drive_files:
    name = f["name"]
    if not name.lower().endswith(".csv"):
        continue                                   # skip the PDF and other non-CSV files
    if name not in manifest:
        changed.append(f)                          # new file
    elif manifest[name]["md5Checksum"] != f["md5Checksum"]:
        changed.append(f)                          # same name, different contents

print(len(changed), "new/changed file(s):", [f["name"] for f in changed])


# ---------- Step 5: copy each changed file into Bronze ----------
today = date.today().isoformat()                   # e.g. "2026-10-23"

for f in changed:
    table = make_table_name(f["name"])
    key = "Bronze/" + table + "/ingest_date=" + today + "/" + f["name"]
    url = "https://www.googleapis.com/drive/v3/files/" + f["id"] + "?alt=media"

    # Stream the file from Drive straight into S3, piece by piece,
    # so a 220 MB file never has to fit in the job's memory.
    with download_session.get(url, stream=True) as download:
        download.raise_for_status()                # stop if Drive returned an error
        download.raw.decode_content = True         # Drive sends it zipped; unzip on the way
        s3.upload_fileobj(download.raw, BUCKET, key)

    # Remember this file's fingerprint
    manifest[f["name"]] = {
        "md5Checksum": f["md5Checksum"],
        "modifiedTime": f["modifiedTime"],
        "s3_key": key,
    }
    print("uploaded s3://" + BUCKET + "/" + key)


# ---------- Step 6: save the fingerprints LAST ----------
# If the job crashed above, the old fingerprints stay, so missed files are retried next run.
if len(changed) > 0:
    s3.put_object(Bucket=BUCKET, Key=MANIFEST_KEY, Body=json.dumps(manifest, indent=2))
