"""Healthcare staffing dashboard (Step 6). Reads the Gold layer through Athena views.

Run:  AWS_PROFILE=admin streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from athena_client import run_query  # noqa: E402

CMS_MINIMUM_HPRD = 3.48  # CMS 2024 minimum staffing rule: total nurse hours per resident day
SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
DOW = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}

st.set_page_config(page_title="Nursing Home Staffing", layout="wide")


@st.cache_data(ttl=3600, show_spinner="Querying Athena…")
def q(sql: str) -> pd.DataFrame:
    return run_query(sql)


state_df = q("SELECT * FROM v_state_staffing")
monthly = q("SELECT * FROM v_monthly_state")
daily = q("SELECT * FROM v_daily_national ORDER BY work_date")
facilities = q("SELECT * FROM v_facility_scorecard")
state_dow = q("""
    SELECT state, day_of_week(work_date) AS dow, SUM(nurse_hours) / SUM(census) AS nurse_hprd
    FROM gold_daily_staffing WHERE is_valid_day GROUP BY 1, 2""")

# ---------- filters ----------
st.sidebar.header("Filters")
states = st.sidebar.multiselect("State", sorted(state_df["state"]), placeholder="All states")
groups = sorted(facilities["ownership_type"].dropna().str.split(" - ").str[0].unique())
ownership = st.sidebar.multiselect("Ownership type (facility charts)", groups, placeholder="All types")
min_census = st.sidebar.slider("Min. average residents (facility rankings)", 0, 100, 20)
st.sidebar.caption("Data: CMS Payroll-Based Journal, Q2 2024 (Apr–Jun), plus CMS Provider Info, "
                   "SNF VBP and claims quality measures (Oct 2024 release).")


def by_state(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["state"].isin(states)] if states else df


fac = by_state(facilities)
fac = fac.assign(ownership_group=fac["ownership_type"].str.split(" - ").str[0])
if ownership:
    fac = fac[fac["ownership_group"].isin(ownership)]
sel_state = by_state(state_df)

# ---------- KPIs (re-weighted from the state sums so they match the SQL exactly) ----------
st.title("Nursing Home Staffing & Operations")
st.caption("Staffing = RN + LPN + CNA direct-care hours. HPRD = nurse hours per resident day "
           "(the nurse-to-patient ratio this data supports). Excludes unreported / impossible facility-days.")
hours = sel_state["total_nurse_hours"].sum()
hprd = hours / sel_state["total_resident_days"].sum()
k = st.columns(5)
k[0].metric("Facilities", f"{int(sel_state['facilities'].sum()):,}")
k[1].metric("Nurse HPRD", f"{hprd:.2f}", f"{hprd - CMS_MINIMUM_HPRD:+.2f} vs CMS 3.48")
k[2].metric("Total nurse hours", f"{hours / 1e6:,.1f} M")
k[3].metric("Occupancy", f"{sel_state['resident_days_with_beds'].sum() / sel_state['bed_days'].sum():.1%}")
k[4].metric("Contract share of hours", f"{sel_state['total_contract_hours'].sum() / hours:.1%}")

tabs = st.tabs(["Staffing", "Facility performance", "Trends", "Quality & outcomes", "The 4 questions"])

# ---------- Staffing ----------
with tabs[0]:
    c1, c2 = st.columns(2)
    s = sel_state.sort_values("nurse_hprd", ascending=False)
    fig = px.bar(s, x="state", y="nurse_hprd", title="Nurse-to-patient ratio (HPRD) by state",
                 labels={"nurse_hprd": "Nurse HPRD"}, hover_data={"rn_hprd": ":.2f", "facilities": True})
    fig.add_hline(y=CMS_MINIMUM_HPRD, line_dash="dash", annotation_text="CMS minimum 3.48")
    c1.plotly_chart(fig, use_container_width=True)
    m = by_state(monthly).copy()
    m["month"] = m["month"].dt.strftime("%b %Y")
    top = m.groupby("state")["total_nurse_hours"].sum().nlargest(15).index
    fig = px.bar(m[m["state"].isin(top)], x="state", y="total_nurse_hours", color="month", barmode="group",
                 title="Total nurse hours by state and month (top 15 states)",
                 labels={"total_nurse_hours": "Nurse hours"})
    c2.plotly_chart(fig, use_container_width=True)

    big = fac[fac["avg_census"] >= min_census]
    cols = ["provider_name", "state", "ownership_type", "avg_census", "nurse_hours_per_resident_day",
            "contract_share", "avg_occupancy_rate"]
    c1, c2 = st.columns(2)
    c1.subheader("Lowest staffing vs patient load")
    c1.dataframe(big.nsmallest(10, "nurse_hours_per_resident_day")[cols], hide_index=True)
    c2.subheader("Highest contract-staff dependence (overtime proxy)")
    c2.dataframe(big.nlargest(10, "contract_share")[cols], hide_index=True)

# ---------- Facility performance ----------
with tabs[1]:
    c1, c2 = st.columns(2)
    s = sel_state.sort_values("occupancy_rate", ascending=False)
    fig = px.bar(s, x="state", y="occupancy_rate", title="Occupancy rate (census / certified beds) by state",
                 labels={"occupancy_rate": "Occupancy"})
    fig.update_yaxes(tickformat=".0%")
    c1.plotly_chart(fig, use_container_width=True)
    fig = px.scatter(fac[fac["avg_occupancy_rate"] <= 1.2], x="avg_occupancy_rate", y="nurse_hours_per_resident_day",
                     color="ownership_group", opacity=0.35,
                     hover_data=["provider_name", "state"], title="Staffing vs occupancy, one dot per facility",
                     labels={"avg_occupancy_rate": "Occupancy", "nurse_hours_per_resident_day": "Nurse HPRD",
                             "ownership_group": "Ownership"})
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(range=[0, 10])
    c2.plotly_chart(fig, use_container_width=True)
    band = fac.groupby("occupancy_band").agg(facilities=("ccn", "count"),
                                             avg_hprd=("nurse_hours_per_resident_day", "mean"),
                                             avg_contract=("contract_share", "mean")).reset_index()
    fig = px.bar(band, x="occupancy_band", y="avg_hprd", text_auto=".2f",
                 title="Average staffing by occupancy band", labels={"avg_hprd": "Nurse HPRD", "occupancy_band": "Occupancy"})
    st.plotly_chart(fig, use_container_width=True)
    st.subheader("Top 10 facilities by patient throughput (average daily residents)")
    st.dataframe(fac.nlargest(10, "avg_census")[["provider_name", "state", "certified_beds", "avg_census",
                                                 "avg_occupancy_rate", "nurse_hours_per_resident_day"]], hide_index=True)

# ---------- Trends ----------
with tabs[2]:
    c1, c2 = st.columns(2)
    fig = px.line(daily, x="work_date", y="nurse_hprd", title="National nurse HPRD by day (weekends dip)",
                  labels={"nurse_hprd": "Nurse HPRD", "work_date": ""})
    c1.plotly_chart(fig, use_container_width=True)
    weekly = daily.set_index("work_date").resample("W-MON", label="left", closed="left").agg(
        {"total_census": "mean", "occupancy_rate": "mean"}).reset_index()
    fig = px.line(weekly, x="work_date", y="total_census", markers=True,
                  title="Average daily resident census by week", labels={"total_census": "Residents", "work_date": "Week of"})
    c2.plotly_chart(fig, use_container_width=True)

    m = by_state(monthly)
    heat = m.pivot_table(index="state", columns=m["month"].dt.strftime("%b"), values="nurse_hprd")
    heat = heat[[c for c in ["Apr", "May", "Jun"] if c in heat.columns]].sort_values(heat.columns[0], ascending=False)
    c1, c2 = st.columns(2)
    fig = px.imshow(heat, aspect="auto", color_continuous_scale="Blues", text_auto=".2f",
                    title="Heatmap: nurse HPRD by state and month", height=1100)
    c1.plotly_chart(fig, use_container_width=True)
    d = by_state(state_dow)
    heat = d.pivot_table(index="state", columns="dow", values="nurse_hprd").rename(columns=DOW)
    heat = heat.sort_values("Mon", ascending=False)
    fig = px.imshow(heat, aspect="auto", color_continuous_scale="Blues", text_auto=".2f",
                    title="Heatmap: nurse HPRD by state and day of week", height=1100)
    c2.plotly_chart(fig, use_container_width=True)

# ---------- Quality ----------
with tabs[3]:
    quart = fac.groupby("hprd_quartile").agg(
        facilities=("ccn", "count"), avg_hprd=("nurse_hours_per_resident_day", "mean"),
        readmission=("readmission_rate_fy2022", "mean"), rehosp=("short_stay_rehospitalization_score", "mean"),
        stars=("overall_rating", "mean"), turnover=("nursing_staff_turnover_pct", "mean")).reset_index()
    quart["hprd_quartile"] = "Q" + quart["hprd_quartile"].astype(str)
    c1, c2, c3 = st.columns(3)
    fig = px.bar(quart, x="hprd_quartile", y="readmission", text_auto=".2%",
                 title="30-day readmission rate by staffing quartile", labels={"hprd_quartile": "Staffing quartile (Q1 = lowest)", "readmission": "Readmission rate"})
    fig.update_yaxes(tickformat=".1%")
    c1.plotly_chart(fig, use_container_width=True)
    fig = px.bar(quart, x="hprd_quartile", y="stars", text_auto=".2f", title="Average star rating by staffing quartile",
                 labels={"hprd_quartile": "Staffing quartile (Q1 = lowest)", "stars": "Overall rating (1-5)"})
    c2.plotly_chart(fig, use_container_width=True)
    fig = px.bar(quart, x="hprd_quartile", y="turnover", text_auto=".1f", title="Nursing staff turnover % by staffing quartile",
                 labels={"hprd_quartile": "Staffing quartile (Q1 = lowest)", "turnover": "Turnover %"})
    c3.plotly_chart(fig, use_container_width=True)
    st.dataframe(quart.round(4), hide_index=True)
    st.caption("Readmissions: SNF VBP risk-standardized 30-day rate (FY2022 performance period). "
               "Rehospitalization: claims measure 521 (short-stay residents re-hospitalized after admission). "
               "Turnover: CMS Provider Info, total nursing staff turnover.")

# ---------- Questions ----------
with tabs[4]:
    for f in sorted((SQL_DIR / "questions").glob("*.sql")):
        sql = f.read_text()
        title = next(line for line in sql.splitlines() if line.startswith("-- Q")).lstrip("- ")
        st.subheader(title)
        st.dataframe(q(sql), hide_index=True)
        with st.expander("SQL"):
            st.code(sql, language="sql")
    st.info("Full written answers and conclusions: docs/metrics_and_findings.md")
