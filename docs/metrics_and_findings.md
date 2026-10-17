# Step 5: Metrics, Answers to the 4 Questions, and Conclusions

All numbers come from the Gold layer through Athena (`python scripts/run_metrics.py` reproduces them; raw outputs in
`results/`). Scope: 14,562 nursing homes, 52 states/territories, Apr 1 – Jun 30 2024, valid facility-days only
(3,314 of 1,325,324 days excluded as unreported or impossible; see `eda_report.md`).

**National picture:** 364 M nurse hours (RN + LPN + CNA) · **3.30 nurse hours per resident day** (RN alone: 0.42) ·
**77.8 %** occupancy · **7.7 %** of hours worked by contract staff · **63 %** of facilities below the CMS minimum of 3.48 HPRD.

## Which spec metrics this data can and cannot support

The spec says "you don't have data to solve all the metrics; pick 3–5". PBJ is one row per facility per day with total
hours by role, employed vs contract. That decides what is possible:

| Spec metric | Possible? | Why / how |
|---|---|---|
| Nurse-to-patient ratio by hospital, state | ✅ **Metric 1** | As nurse hours per resident day (HPRD). No headcounts, so not literally "nurses per patient" |
| …by department | ❌ | No department field |
| Total hours worked by hospital, state, month | ✅ **Metric 2** | Direct from PBJ |
| % nurses working overtime | ❌ (proxy) | No overtime or per-nurse data. Proxy: contract-hours share (Metric 4, Q2) |
| Shifts per nurse | ❌ | No shifts, no individual nurses |
| Occupancy rate trends | ✅ **Metric 3** | Census ÷ certified beds (Provider Info). Trend within Q2 only, since there's one quarter of data |
| Bed utilization by department | ❌ | No departments |
| Staffing vs occupancy | ✅ Metric 3 + Q1 | |
| Top 10 hospitals by patient throughput | ✅ (dashboard) | Average daily census; no admissions/discharges |
| Lowest staffing vs patient load | ✅ (dashboard) | Lowest HPRD among facilities with ≥ 20 residents |
| Patient satisfaction, complaint ratio | ❌ | Not in the files (Provider Info has complaint *counts*, not per-nurse) |
| Average length of stay | ❌ | No admission/discharge dates (see Q4) |
| Readmission rates / correlation with staffing | ✅ **Metric 5** | SNF VBP 30-day readmission rate + claims rehospitalization measure, by facility |
| Payroll cost, cost per stay, overtime cost, revenue | ❌ | No wages, costs or revenue anywhere |
| Shift utilization by time of day, peak hours | ❌ | Daily totals only; day-of-week is the finest grain (shown on the dashboard) |
| Permanent vs contract staff | ✅ **Metric 4** | `_emp` vs `_ctr` hours |
| Nurse attrition | ✅ (in Metric 5) | Provider Info total nursing staff turnover % (one snapshot, not a trend) |

## The 5 metrics

### Metric 1: Nurse-to-patient ratio (HPRD) by state (`sql/metrics/01`)
- National **3.30** HPRD. Highest: **AK 5.41**, OR 4.20, PR 4.12, ND 4.08, HI 3.99, CA 3.98.
- Lowest: **MO 2.41**, TX 2.68, OK 2.80, IN 2.82, NM 2.83, IL 3.03.
- RN time is a small slice: 0.42 of the 3.30 hours. CNAs do most of the direct care.
- **63 %** of facilities average below CMS's 3.48 HPRD minimum (2024 rule).

### Metric 2: Total nurse hours by state and month (`02`)
- 119.6 M (Apr), 124.3 M (May), 120.2 M (Jun). May is higher because it has 31 days and 23 weekdays.
- Largest: CA (11.8 M in April), NY (9.9 M), FL (7.8 M), TX (6.8 M), PA (6.7 M).

### Metric 3: Occupancy and staffing vs patient load (`03`)
- National occupancy **77.8 %**. Highest: ND 90.0 %, WV 89.2 %, AK 88.1 %, NY 87.5 %, CA 87.3 %.
  Lowest: MT 61.0 %, OK 61.5 %, PR 61.9 %, OR 62.5 %.
- Low-staffing states are also mostly low-occupancy (MO 69 %, TX 65 %, OK 61 %). Empty beds do not translate into more
  hours per resident there.

### Metric 4: Permanent vs contract staff (`04`)
- Nationally **92.3 % employed / 7.7 % contract** (12 employed hours per contract hour).
- Highest contract dependence: **VT 32 %**, ME 18 %, NH 17 %, PA 15 %, NJ 15 %. Northeast states rely on agency staff most.

### Metric 5: Staffing vs quality and attrition (`05`)

| Staffing quartile | Avg HPRD | 30-day readmission | Short-stay rehospitalization | Star rating | Nursing staff turnover |
|---|---|---|---|---|---|
| Q1 (lowest) | 2.44 | 20.30 % | 23.2 % | 2.35 | 52.7 % |
| Q2 | 3.05 | 20.34 % | 23.5 % | 2.55 | 50.5 % |
| Q3 | 3.47 | 20.26 % | 23.3 % | 2.95 | 48.1 % |
| Q4 (highest) | 4.49 | 19.94 % | 22.6 % | 3.57 | 43.7 % |

- Correlation (facility level): staffing vs star rating **+0.33**, vs turnover **−0.24**, vs readmission **−0.07**.
- Better-staffed homes have clearly **higher ratings and lower turnover**; readmissions improve only slightly
  (−0.36 points from Q1 to Q4). Readmissions depend on many things besides nurse hours.

## Answers to the 4 questions

### Q1. What is the relationship between nurse staffing levels and occupancy rates?
**Almost none at the facility level.** The correlation between HPRD and occupancy is **0.011**. Average HPRD is flat
across occupancy bands: 3.37 (<60 %), 3.30 (60–75 %), 3.35 (75–90 %), 3.42 (90 %+). Facilities staff to the residents
they have, not to their bed count. Full homes (90 %+) use the least contract labor (6.3 % vs 7.4–7.7 %), which suggests
stable, full facilities keep their own staff. At the state level, the lowest-staffed states (MO, TX, OK) also have low
occupancy.

### Q2. Which hospitals have the highest overtime hours for nurses?
PBJ has no overtime field, so **contract (agency) hours** are the proxy: hours a facility could not cover with its own
employees. Top 5 by contract hours in Q2 2024:

1. Isabella Geriatric Center (NY): 73,473 h (37 % of its nurse hours)
2. Pleasant Acres Rehabilitation and Nursing Center (PA): 73,236 h (71 %)
3. Queens Boulevard Extended Care Facility (NY): 65,864 h (70 %)
4. Brighton Rehabilitation and Wellness Center (PA): 61,080 h (57 %)
5. The Plaza Rehab and Nursing Center (NY): 59,624 h (32 %)

Full top 10 in `results/q2_highest_overtime.csv`. NY and PA dominate. Coral Reef Subacute Care Center (FL) reports
100 % contract hours, which is either a fully outsourced model or a reporting issue.

### Q3. What are the average staffing levels by state and hospital type?
Nationally by ownership type: **Non profit 3.66** HPRD (RN 0.55), **Government 3.59** (RN 0.52), **For profit 3.19**
(RN 0.38). For-profit homes are 73 % of facilities and have ~13 % less nursing time per resident and ~30 % less RN time.
The same order holds in almost every state, e.g. AL: for profit 3.21 / government 3.91 / non profit 3.70; AR: 3.41 / 4.47 / 4.10.
All 153 state × type combinations: `results/q3_staffing_by_state_and_type.csv` and the dashboard.

### Q4. What trends can you identify in patient length of stay over time?
**Length of stay cannot be calculated from this data:** there are no admission or discharge dates, only a daily count
of residents. The closest signals:
- **Census** (residents present) is very stable and rising slightly: 1.210 M (week of Apr 1) → 1.216 M (week of Jun 24), +0.5 %.
- **Staffing per resident** rose slightly too: 3.27 → 3.31 HPRD.
- **Strong weekly cycle:** HPRD peaks Tue–Wed (~3.44) and drops on weekends (Sat 3.10, Sun 3.04): about 9 % less care per resident than the weekday
  average (3.39), and 12 % less than midweek, with the same residents.
To measure length of stay, the pipeline would need MDS admission/discharge assessments, which are not in the files provided.

## Conclusions and recommendations

1. **Most facilities are below the federal staffing minimum** (63 % under 3.48 HPRD). Target MO, TX, OK, IN, NM first.
2. **Weekend staffing gap:** ~9 % fewer nurse hours per resident on Sat/Sun than on weekdays, with the same census. Weekend shift
   incentives are the cheapest lever.
3. **Ownership matters:** for-profit homes staff ~0.47 HPRD below non-profits; worth tying to contract terms or oversight.
4. **Contract labor is concentrated** (VT, ME, NH, PA, NJ, and a handful of NY/PA homes). Converting agency hours to
   employees there lowers cost and turnover risk.
5. **Higher staffing goes with better ratings and lower turnover**, a quality case for staffing investment; the
   readmission effect is small, so readmission programs need more than staffing.

Caveat: the lowest-HPRD facilities (e.g. under 0.2 HPRD with 100+ residents) are almost certainly under-reporting
rather than truly unstaffed; they should be verified with the facility before acting.
