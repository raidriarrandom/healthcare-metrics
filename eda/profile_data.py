"""Steps 1 and 2: verify the source files, then profile them (missing values, duplicates, outliers).

Reads every CSV in the data folder (default: ../../data, the project's data/ folder outside the repo),
compares each file's MD5 with the Google Drive checksum in docs/drive_manifest.json, and writes
  docs/eda_report.md           the report
  docs/images/*.png            the charts it links to

Usage:  python eda/profile_data.py [data_dir]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "data"
DOCS, IMAGES = ROOT / "docs", ROOT / "docs" / "images"
MASTER = "PBJ_Daily_Nurse_Staffing_Q2_2024.csv"
KEY_NAMES = ["PROVNUM", "CMS Certification Number (CCN)"]
NURSE_COLS = ["Hrs_RN", "Hrs_LPN", "Hrs_CNA"]


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    # CMS files are Windows-1252; key columns stay text so leading zeros survive
    return pd.read_csv(path, encoding="cp1252", low_memory=False, dtype={k: str for k in KEY_NAMES})


def integrity(files: list[Path], manifest: dict) -> pd.DataFrame:
    rows = []
    for p in files:
        local = md5(p)
        drive = manifest.get(p.name, {}).get("md5Checksum")
        try:
            df = read_csv(p)
            opened, n_rows, n_cols = "yes", len(df), df.shape[1]
        except Exception as e:  # a corrupt file is a finding, not a crash
            opened, n_rows, n_cols = f"no ({e.__class__.__name__})", None, None
        rows.append({"file": p.name, "size_mb": round(p.stat().st_size / 1e6, 1), "opens": opened,
                     "rows": n_rows, "columns": n_cols,
                     "md5_matches_drive": "n/a (not in manifest)" if drive is None else ("yes" if drive == local else "NO")})
    return pd.DataFrame(rows)


def missing_profile(df: pd.DataFrame) -> pd.Series:
    return (df.isna().mean() * 100).sort_values(ascending=False)


def iqr_outliers(s: pd.Series) -> tuple[int, float, float]:
    q1, q3 = s.quantile([0.25, 0.75])
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    return int(((s < lo) | (s > hi)).sum()), lo, hi


def chart_missing(name: str, miss: pd.Series) -> str | None:
    miss = miss[miss > 0].head(25)
    if miss.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, max(2.5, 0.28 * len(miss))))
    ax.barh(miss.index[::-1], miss.values[::-1], color="#4C78A8")
    ax.set_xlabel("% of rows missing")
    ax.set_title(f"{Path(name).stem}: % missing (top {len(miss)} columns)", fontsize=10)
    fig.tight_layout()
    out = f"missing_{Path(name).stem}.png"
    fig.savefig(IMAGES / out, dpi=110)
    plt.close(fig)
    return out


def chart_hist(series: pd.Series, title: str, xlabel: str, out: str, clip: float | None = None) -> str:
    s = series.dropna()
    if clip is not None:
        s = s.clip(upper=clip)
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.hist(s, bins=60, color="#4C78A8")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("facility-days" if "PBJ" in title else "count")
    fig.tight_layout()
    fig.savefig(IMAGES / out, dpi=110)
    plt.close(fig)
    return out


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def profile_master(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    nurse = df[NURSE_COLS].sum(axis=1)
    hprd = nurse / df["MDScensus"].where(df["MDScensus"] > 0)
    dates = pd.to_datetime(df["WorkDate"].astype(str), format="%Y%m%d")
    n_out, lo, hi = iqr_outliers(hprd.dropna())
    contract = df[[f"{c}_ctr" for c in NURSE_COLS]].sum(axis=1).sum() / nurse.sum()
    consistent = all((df[c] - df[f"{c}_emp"] - df[f"{c}_ctr"]).abs().max() < 0.01 for c in NURSE_COLS)

    images = [
        chart_hist(df["MDScensus"], "PBJ: daily resident census per facility", "residents", "hist_census.png"),
        chart_hist(hprd, "PBJ: nurse hours per resident day (clipped at 10)", "HPRD", "hist_hprd.png", clip=10),
    ]
    by_day = pd.DataFrame({"date": dates, "census": df["MDScensus"], "nurse": nurse}).groupby("date").sum()
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.plot(by_day.index, by_day["nurse"] / by_day["census"], color="#4C78A8")
    ax.set_title("PBJ: national nurse HPRD by day (weekend dips are visible)")
    ax.set_ylabel("HPRD")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(IMAGES / "trend_daily_hprd.png", dpi=110)
    plt.close(fig)
    images.append("trend_daily_hprd.png")

    facts = [
        f"- Rows: **{len(df):,}**, columns: **{df.shape[1]}**, facilities: **{df['PROVNUM'].nunique():,}**, "
        f"states/territories: **{df['STATE'].nunique()}**",
        f"- Dates: **{dates.min():%Y-%m-%d} to {dates.max():%Y-%m-%d}** ({dates.nunique()} days, Q2 2024 only)",
        f"- Missing values: **{int(df.isna().sum().sum()):,}** cells",
        f"- Exact duplicate rows: **{int(df.duplicated().sum()):,}**; duplicate facility+date: "
        f"**{int(df.duplicated(['PROVNUM', 'WorkDate']).sum()):,}**",
        f"- Negative hours: **{int((df.filter(like='Hrs_') < 0).sum().sum()):,}**",
        f"- Facility-days with census 0: **{int((df['MDScensus'] == 0).sum()):,}**",
        f"- Facility-days with census > 0 but 0 RN+LPN+CNA hours (likely unreported): "
        f"**{int(((df['MDScensus'] > 0) & (nurse == 0)).sum()):,}**",
        f"- Nurse HPRD: median **{hprd.median():.2f}**, max **{hprd.max():.0f}**; "
        f"**{int((hprd > 24).sum())}** facility-days above 24 (impossible: more than 24 hours per resident per day)",
        f"- IQR outlier rule on HPRD (outside {lo:.2f} to {hi:.2f}): **{n_out:,}** facility-days "
        f"({n_out / hprd.notna().sum():.1%}). Most are legitimately high or low staffing, so only the impossible "
        f"and unreported rows are excluded, via `is_valid_day` in Gold",
        f"- `Hrs_X = Hrs_X_emp + Hrs_X_ctr` holds for RN, LPN and CNA: **{'yes' if consistent else 'no'}**",
        f"- Contract staff share of RN+LPN+CNA hours: **{contract:.1%}**",
    ]
    return facts, images


def main() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA.glob("*.csv"))
    if not files:
        sys.exit(f"no CSV files in {DATA}")
    manifest = json.loads((DOCS / "drive_manifest.json").read_text())
    print(f"profiling {len(files)} files in {DATA}")

    integ = integrity(files, manifest)
    out = ["# Steps 1–2: Source Data Integrity and Initial Data Analysis", "",
           "Generated by `eda/profile_data.py`. Re-run it after adding files to `data/`.", "",
           "## Step 1: Integrity check", "",
           "Every file was opened with pandas, its rows were counted, and its MD5 was compared with the checksum "
           "Google Drive reports for the same file (recorded by the ingest job in `drive_manifest.json`).", "",
           md_table(integ), ""]

    out += ["## Schema and relationships", "",
            "The facility key is the 6-character CMS Certification Number: `PROVNUM` in PBJ, "
            "`CMS Certification Number (CCN)` in the supporting files. It is text (leading zeros matter). "
            "In Silver it is renamed `ccn` and zero-padded to 6 characters in every table, so all joins use `ccn`.", ""]
    schema_rows = []
    frames = {}
    for p in files:
        df = read_csv(p)
        frames[p.name] = df
        key = next((k for k in KEY_NAMES if k in df.columns), None)
        grain = "facility per day" if p.name == MASTER else (
            "facility" if key and not df.duplicated(key).any() else "facility per measure/event" if key else "state")
        schema_rows.append({"file": p.name, "key column": key or "(none: state level)", "grain (one row per)": grain,
                            "distinct facilities": df[key].nunique() if key else "",
                            "facilities also in PBJ": ""})
    pbj_ids = set(frames[MASTER]["PROVNUM"]) if MASTER in frames else set()
    for r in schema_rows:
        k = r["key column"]
        if k in KEY_NAMES and pbj_ids:
            r["facilities also in PBJ"] = f"{len(set(frames[r['file']][k]) & pbj_ids):,}"
    out += [md_table(pd.DataFrame(schema_rows)), ""]

    out += ["## Step 2: Missing values, duplicates, outliers", ""]
    if MASTER in frames:
        facts, images = profile_master(frames[MASTER])
        out += [f"### {MASTER} (master file)", "", *facts, ""]
        out += [f"![{i}](images/{i})" for i in images] + [""]

    summary = []
    for name, df in frames.items():
        miss = missing_profile(df)
        summary.append({"file": name, "rows": f"{len(df):,}", "cells missing": f"{df.isna().mean().mean():.1%}",
                        "columns >50% missing": int((miss > 50).sum()), "fully empty columns": int((miss == 100).sum()),
                        "duplicate rows": int(df.duplicated().sum())})
        img = chart_missing(name, miss)
        if name != MASTER:
            out += [f"### {name}", ""]
            out += [f"![missing values](images/{img})", ""] if img else ["No missing values.", ""]
    out += ["### Summary across files", "", md_table(pd.DataFrame(summary)), ""]

    if "NH_ProviderInfo_Oct2024.csv" in frames:
        beds = frames["NH_ProviderInfo_Oct2024.csv"]["Number of Certified Beds"]
        n_out, lo, hi = iqr_outliers(beds.dropna())
        out += ["### Certified beds (needed for occupancy)", "",
                f"- Median **{beds.median():.0f}** beds, max **{beds.max():.0f}**; IQR outliers: **{n_out}** "
                f"facilities above {hi:.0f} beds (large facilities, kept)", ""]
        out += [f"![beds](images/{chart_hist(beds, 'ProviderInfo: certified beds per facility', 'beds', 'hist_beds.png')})", ""]

    out += ["## What this means for the pipeline", "",
            "- Silver: snake_case names, `ccn` key padded to 6, empty strings to null, fully empty columns dropped, "
            "types inferred, exact duplicates removed.",
            "- Gold: `is_valid_day` excludes census-0 days, unreported days (0 nurse hours) and impossible HPRD (> 24). "
            "Facility and state metrics use valid days only.",
            "- PBJ has no overtime, shift, cost, department, time-of-day or length-of-stay fields; "
            "see `docs/metrics_and_findings.md` for which spec metrics are possible.", ""]

    (DOCS / "eda_report.md").write_text("\n".join(out))
    print(f"wrote {DOCS / 'eda_report.md'} and {len(list(IMAGES.glob('*.png')))} charts")


if __name__ == "__main__":
    main()
