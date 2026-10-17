"""Step 5: run every metric and question query in Athena and save the results.

Writes results/<query name>.csv and prints each result, so the numbers in docs/metrics_and_findings.md
can be reproduced. Usage:  AWS_PROFILE=admin python scripts/run_metrics.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from athena_client import run_query  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    pd.set_option("display.width", 200, "display.max_columns", 20, "display.max_rows", 30)
    for path in sorted((ROOT / "sql" / "metrics").glob("*.sql")) + sorted((ROOT / "sql" / "questions").glob("*.sql")):
        df = run_query(path.read_text())
        df.to_csv(out_dir / f"{path.stem}.csv", index=False)
        print(f"\n=== {path.stem} ({len(df)} rows)\n{df.head(12).to_string(index=False)}")


if __name__ == "__main__":
    main()
