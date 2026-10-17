"""Draw the pipeline architecture as docs/architecture.png and docs/architecture.drawio (same layout).

Usage:  python scripts/generate_architecture_diagram.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs"
# AWS category colours
ORANGE, GREEN, PURPLE, PINK, RED, GREY = "#ED7100", "#7AA116", "#8C4FFF", "#E7157B", "#DD344C", "#545B64"

# id: (x, y, w, h, label, colour)   coordinates in a 1400 x 640 canvas, y downwards
NODES = {
    "drive":   (20, 250, 150, 80, "Google Drive\nfolder: master +\nsupporting CSVs", GREY),
    "sched":   (230, 40, 210, 70, "Glue Workflow\nscheduled trigger 06:00 PT", PINK),
    "secret":  (230, 470, 210, 70, "Secrets Manager\nDrive service account", RED),
    "ingest":  (230, 250, 210, 80, "Glue Python shell\nhealthcare-drive-ingest\n(md5 manifest = incremental)", ORANGE),
    "bronze":  (500, 250, 170, 80, "S3 Bronze\nraw CSV\ningest_date=…", GREEN),
    "silver_j": (730, 130, 200, 80, "Glue Spark\nbronze-to-silver\n(clean, types, dedupe)", ORANGE),
    "silver":  (730, 250, 200, 80, "S3 Silver\nParquet\none table per file", GREEN),
    "gold_j":  (990, 130, 190, 80, "Glue Spark\nsilver-gold\n(Spark SQL metrics)", ORANGE),
    "gold":    (990, 250, 190, 80, "S3 Gold\ngold_daily_staffing\ngold_facility_metrics", GREEN),
    "catalog": (730, 400, 450, 60, "Glue Crawlers → Glue Data Catalog (bronze_ / silver_ / gold_ tables)", PURPLE),
    "athena":  (1230, 250, 150, 80, "Athena\nworkgroup + views", PURPLE),
    "app":     (1230, 470, 150, 80, "Streamlit\ndashboard\n(boto3 → Athena)", GREY),
    "logs":    (500, 560, 680, 50, "CloudWatch Logs (every job and crawler)  ·  IAM role healthcare-project-glue-role (least privilege)", PINK),
}
EDGES = [
    ("drive", "ingest", "Drive API"), ("secret", "ingest", "creds"), ("sched", "ingest", "daily"),
    ("ingest", "bronze", "new/changed files"), ("bronze", "silver_j", ""), ("silver_j", "silver", "Parquet"),
    ("silver", "gold_j", ""), ("gold_j", "gold", "Parquet"), ("gold", "athena", "SQL"),
    ("silver", "catalog", ""), ("gold", "catalog", ""), ("catalog", "athena", "schemas"), ("athena", "app", "queries"),
]


def anchor(node, other):
    x, y, w, h = NODES[node][:4]
    ox, oy, ow, oh = NODES[other][:4]
    cx, cy, ocx, ocy = x + w / 2, y + h / 2, ox + ow / 2, oy + oh / 2
    if abs(ocx - cx) * h > abs(ocy - cy) * w:  # mostly horizontal
        return (x + w if ocx > cx else x, cy)
    return (cx if abs(ocx - cx) < w / 2 else (cx + (w / 4 if ocx > cx else -w / 4)), y + h if ocy > cy else y)


def png() -> None:
    fig, ax = plt.subplots(figsize=(14, 6.6))
    ax.set_xlim(0, 1400)
    ax.set_ylim(640, 0)
    ax.axis("off")
    ax.set_title("Healthcare Metrics Pipeline: AWS architecture (Medallion data lake)", fontsize=14, weight="bold")
    for x, y, w, h, label, colour in NODES.values():
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=2,rounding_size=8",
                                    facecolor=colour + "22", edgecolor=colour, linewidth=2))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=8.5)
    for a, b, label in EDGES:
        p, q = anchor(a, b), anchor(b, a)
        ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=14, color="#333", linewidth=1.3))
        if label:
            ax.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 - 8, label, ha="center", fontsize=7.5, color="#333",
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 1})
    fig.tight_layout()
    fig.savefig(DOCS / "architecture.png", dpi=130)
    print(f"wrote {DOCS / 'architecture.png'}")


def drawio() -> None:
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for nid, (x, y, w, h, label, colour) in NODES.items():
        style = f"rounded=1;whiteSpace=wrap;html=1;fillColor={colour}22;strokeColor={colour};strokeWidth=2;fontSize=11;"
        value = escape(label).replace("\n", "&lt;br&gt;")
        cells.append(f'<mxCell id="{nid}" value="{value}" style="{style}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for i, (a, b, label) in enumerate(EDGES):
        cells.append(f'<mxCell id="e{i}" value="{escape(label)}" style="endArrow=block;html=1;fontSize=10;" '
                     f'edge="1" parent="1" source="{a}" target="{b}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    xml = ('<mxfile host="generate_architecture_diagram.py"><diagram name="Architecture" id="arch">'
           '<mxGraphModel dx="1400" dy="640" grid="1" gridSize="10" page="1" pageWidth="1400" pageHeight="660">'
           f'<root>{"".join(cells)}</root></mxGraphModel></diagram></mxfile>')
    (DOCS / "architecture.drawio").write_text(xml)
    print(f"wrote {DOCS / 'architecture.drawio'}")


if __name__ == "__main__":
    png()
    drawio()
