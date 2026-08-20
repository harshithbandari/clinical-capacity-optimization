# Tableau Implementation Specification — Clinical Operations & Patient Capacity Optimization

Deterministic build spec. Every field name below matches a column in `tableau/data/` exactly.
Nothing here requires judgement calls; follow it top to bottom and the workbook is reproducible.

**Target:** 4 dashboards, 11 worksheets, 1200 × 850 fixed size.
**Tableau version:** 2021.4 or later. No extensions, no web connectors.

---

## 1 · Data sources

Connect each CSV as a **separate** text-file data source (Data → New Data Source → Text file).
Do **not** join them — each worksheet uses exactly one source. Set every source to **Extract**.

| # | Data source name | File | Rows | Used by |
|---|---|---|---|---|
| DS1 | `Access KPIs` | `data/kpis.csv` | 8 | WS1 |
| DS2 | `Unit Baseline` | `data/unit_baseline.csv` | 26 | WS2, WS3, WS9 |
| DS3 | `Weekly Panel` | `data/weekly_panel.csv` | 2,028 | WS5, WS6 |
| DS4 | `Wait Driver Models` | `data/wait_driver_models.csv` | 4 | WS4 |
| DS5 | `No-show Tiers` | `data/noshow_tiers.csv` | 3 | WS7 |
| DS6 | `Capacity Scenarios` | `data/capacity_scenarios_long.csv` | 10 | WS8, WS10 |
| DS7 | `Capacity Allocation` | `data/capacity_allocation.csv` | 26 | WS11 |

**Field role corrections after connecting** (Tableau will guess wrong on these):

| Data source | Field | Change to |
|---|---|---|
| DS1 | `sort` | Dimension, Discrete |
| DS2, DS7 | `unit`, `specialty`, `clinic_id` | Dimension |
| DS3 | `specialty`, `clinic_id`, `week_start` | Dimension |
| DS3 | `week` | Dimension, **Continuous** |
| DS4 | `model` | Dimension |
| DS5 | `tier` | Dimension |
| DS6 | `scenario`, `allocation` | Dimension |
| DS6 | `capacity_step_pct` | Dimension, **Continuous** |

---

## 2 · Parameters

| Parameter name | Data type | Current value | Allowable | Used in |
|---|---|---|---|---|
| `p_Access Standard (days)` | Float | `14` | Range 7 – 30, step 1 | CF2, CF3, reference lines |

Create once; it is shared across data sources.

---

## 3 · Calculated fields

Create in the data source named in brackets. Names are exact — dashboards reference them.

**[DS2 · Unit Baseline]**

```
CF1  Over Standard
     IF [wait] > [p_Access Standard (days)] THEN "Over standard" ELSE "Within standard" END

CF2  Wait vs Standard
     [wait] - [p_Access Standard (days)]

CF3  Structurally Unreachable
     // alpha is the modeled wait at zero congestion; if it already exceeds the
     // standard, no capacity increase can bring the unit inside it.
     IF [alpha] > [p_Access Standard (days)] THEN "Cannot meet standard at any capacity"
     ELSE "Reachable with capacity" END

CF4  Patients Over Standard
     IF [wait] > [p_Access Standard (days)] THEN [demand] ELSE 0 END

CF5  Utilisation Band
     IF [util] >= 0.95 THEN "Critical (>=95%)"
     ELSEIF [util] >= 0.90 THEN "High (90-95%)"
     ELSEIF [util] >= 0.80 THEN "Moderate (80-90%)"
     ELSE "Slack (<80%)" END
```

**[DS1 · Access KPIs]**

```
CF6  KPI Display Value
     IF [unit] = "pct"   THEN STR(ROUND([value],2)) + "%"
     ELSEIF [unit] = "days" THEN STR(ROUND([value],1)) + " d"
     ELSE STR(ROUND([value],0)) END
```

**[DS6 · Capacity Scenarios]**

```
CF7  Capacity Step Label
     "+" + STR(ROUND([capacity_step_pct],0)) + "%"

CF8  Is Optimised
     [allocation] = "Optimised allocation"
```

**[DS3 · Weekly Panel]**

```
CF9  Queueing Pressure
     // the transform that raises explanatory power from R2 0.489 to 0.853
     [utilisation] / (1 - [utilisation])
```

---

## 4 · Worksheets

Formatting defaults applied to all: font Tableau Book 9pt; gridlines off; row/column
dividers off; zero lines light grey; tooltips per spec below; titles as given.

### WS1 — `KPI Tiles`  (DS1)
- Rows: `sort` (discrete) · Columns: none
- Marks: **Text**. Text: `AGG(KPI Display Value)` — use ATTR if Tableau requires aggregation
- Detail: `kpi`
- Sort: `sort` ascending
- Format: hide row/column headers; title per tile from `kpi`
- Tooltip: `<kpi>` newline `<CF6 KPI Display Value>`

### WS2 — `Wait by Unit`  (DS2)
- Rows: `unit` · Columns: `AVG(wait)`
- Marks: **Bar**. Colour: `CF1 Over Standard` (Over = #C0392B, Within = #2E86AB)
- Label: `AVG(wait)`, format `0.0" d"`
- Sort: `unit` by `AVG(wait)` **descending**
- Reference line: Constant = `p_Access Standard (days)`, per pane, label "14-day standard", dashed, grey
- Axis title: `Mean wait (days)`
- Tooltip: `<unit>` / `Specialty: <specialty>` / `Mean wait: <AVG(wait)>` / `Utilisation: <AVG(util)>` / `Demand: <SUM(demand)> patients/week`

### WS3 — `Utilisation vs Wait`  (DS2)
- Columns: `AVG(util)` · Rows: `AVG(wait)`
- Marks: **Circle**. Detail: `unit` · Size: `SUM(demand)` · Colour: `CF5 Utilisation Band`
- Colour order: Slack #6BAED6, Moderate #2E86AB, High #E8A33D, Critical #C0392B
- Reference line (Y): Constant = `p_Access Standard (days)`, dashed
- X axis: fixed 0.50 – 1.00, format `0%`; title `Utilisation`
- Y axis: title `Mean wait (days)`
- Tooltip: `<unit>` / `Utilisation <AVG(util)>` / `Wait <AVG(wait)> days` / `Demand <SUM(demand)>/wk` / `Structural floor <AVG(alpha)> days`

### WS4 — `Wait Driver Model Comparison`  (DS4)
- Rows: `model` · Columns: `AVG(r2)`
- Marks: **Bar**, single colour #2E86AB
- Label: `AVG(r2)`, format `0.000`
- Sort: `model` by `AVG(r2)` ascending (so the queueing model reads last/highest)
- Axis: fixed 0 – 1, title `R²`
- Tooltip: `<model>` / `R² <AVG(r2)>` / `Adjusted R² <AVG(adj_r2)>` / `AIC <AVG(aic)>` / `n = <AVG(n)>`

### WS5 — `Wait Trend by Specialty`  (DS3)
- Columns: `week` (continuous) · Rows: `AVG(avg_wait_days)`
- Marks: **Line**. Colour: `specialty`
- Reference line (Y): Constant = `p_Access Standard (days)`, dashed
- Axis titles: `Week`, `Mean wait (days)`
- Tooltip: `<specialty>` / `Week <week>` / `Mean wait <AVG(avg_wait_days)> days` / `Utilisation <AVG(utilisation)>`

### WS6 — `Utilisation vs Queueing Pressure`  (DS3)
- Columns: `AVG(utilisation)` · Rows: `AVG(CF9 Queueing Pressure)`
- Marks: **Circle**, opacity 40%, Detail: `specialty`, `clinic_id`
- X axis format `0%`; Y axis title `ρ / (1 − ρ)`
- Caption: "Wait is flat while there is slack, then rises steeply as utilisation approaches 100%. This is why a uniform capacity increase wastes most of its benefit."
- Tooltip: `<specialty> @ <clinic_id>` / `Utilisation <AVG(utilisation)>` / `Pressure <AVG(CF9)>` / `Wait <AVG(avg_wait_days)> days`

### WS7 — `No-show Risk Tiers`  (DS5)
- Columns: `tier` · Rows: `AVG(rate)`
- Marks: **Bar**. Colour: `tier` (Low #6BAED6, Medium #E8A33D, High #C0392B)
- Label: `AVG(vs_base)`, format `0.00"×"`
- Sort: manual Low, Medium, High
- Y axis format `0%`, title `No-show rate`
- Tooltip: `<tier> risk` / `Rate <AVG(rate)>` / `<AVG(vs_base)>× base rate` / `<SUM(appts)> appointments, <SUM(no_shows)> no-shows`

### WS8 — `Scenario — Mean Wait`  (DS6)
- Columns: `capacity_step_pct` (continuous) · Rows: `AVG(mean_wait_days)`
- Marks: **Line**, size medium, markers on. Colour: `allocation`
  (Optimised allocation #2E86AB, Pro-rata (uniform) #8C8C8C)
- Reference line (Y): Constant = `p_Access Standard (days)`, dashed
- X axis: title `Capacity added (%)`, format `0"%"`
- Tooltip: `<allocation>` / `Capacity +<capacity_step_pct>%` / `Mean wait <AVG(mean_wait_days)> days` / `Units over standard <AVG(units_over_standard)>`

### WS9 — `Structural Constraint Detail`  (DS2)
- Rows: `unit` · Columns: `AVG(alpha)`
- Marks: **Bar**. Colour: `CF3 Structurally Unreachable`
  (Cannot meet = #C0392B, Reachable = #B8C4CE)
- Filter: `CF3` — keep both, but sort `unit` by `AVG(alpha)` descending
- Reference line: Constant = `p_Access Standard (days)`, dashed, label "Standard"
- Axis title: `Structural floor α (days at zero congestion)`
- Tooltip: `<unit>` / `Structural floor <AVG(alpha)> days` / `Current wait <AVG(wait)> days` / `Demand <SUM(demand)> patients/week` / `<CF3>`

### WS10 — `Scenario — Units Over Standard`  (DS6)
- Columns: `capacity_step_pct` (continuous) · Rows: `AVG(units_over_standard)`
- Marks: **Bar**, side-by-side. Colour: `allocation` (same palette as WS8)
- Y axis title: `Units above the 14-day standard`
- Tooltip: `<allocation>` / `Capacity +<capacity_step_pct>%` / `<AVG(units_over_standard)> of 26 units over standard`

### WS11 — `Where Capacity Goes`  (DS7)
- Rows: `unit` · Columns: `SUM(share_of_new_capacity)`
- Marks: **Bar**, single colour #2E86AB
- Sort: `unit` by `SUM(share_of_new_capacity)` descending
- Filter: `share_of_new_capacity` ≥ 0.1 (hides units receiving nothing)
- Axis format `0.0"%"`, title `Share of a +10% capacity increase`
- Tooltip: `<unit>` / `Receives <SUM(share_of_new_capacity)>% of new capacity` / `Wait <SUM(wait)> → <SUM(wait_after)> days` / `Reduction <SUM(wait_reduction_days)> days` / `Redistribution move <SUM(redistribution_delta)> slots`

---

## 5 · Dashboards

All: size **Fixed 1200 × 850**. Every dashboard carries the data-note text object at the bottom
(height 40px), and a title text object at the top (height 60px).

**Mandatory data note, verbatim, on every dashboard:**

> Data note: Simulated healthcare operations environment; capacity, wait times and patient-flow
> metrics are modeled for analytical demonstration.

### DB1 — `1 · Executive Access Overview`
```
Title bar (h 60)   "Clinical Operations & Patient Capacity Optimization"
                   subtitle "Access performance across 26 specialty × clinic units · 78 weeks"
KPI strip (h 130)  WS1 KPI Tiles, full width
Row 2   (h 380)    WS2 Wait by Unit (w 55%) | WS3 Utilisation vs Wait (w 45%)
Row 3   (h 200)    WS5 Wait Trend by Specialty, full width
Data note (h 40)
```
- Filter object: `p_Access Standard (days)` parameter control, floating top-right

### DB2 — `2 · Capacity & Access Drivers`
```
Title bar (h 60)   "What drives wait time"
Row 1   (h 330)    WS4 Wait Driver Model Comparison (w 45%) | WS7 No-show Risk Tiers (w 55%)
Row 2   (h 380)    WS6 Utilisation vs Queueing Pressure, full width
Data note (h 40)
```
- Text object under WS4: "Replacing a linear utilisation term with the queueing transform ρ/(1−ρ) raises R² from 0.489 to 0.853. Adding no-show and cancellation rates adds nothing and worsens AIC."

### DB3 — `3 · Capacity Optimization`
```
Title bar (h 60)   "Where capacity should sit"
Row 1   (h 300)    WS8 Scenario — Mean Wait (w 50%) | WS10 Scenario — Units Over Standard (w 50%)
Row 2   (h 380)    WS11 Where Capacity Goes, full width
Data note (h 40)
```
- Text callout, floating over Row 1: **"Redistributing 5.5% of existing slots cuts total wait-days 20.5% — modeled as equivalent to a 4.07% capacity increase, with no new slots."**

### DB4 — `4 · Structural Constraints`
```
Title bar (h 60)   "The limit of what capacity can do"
Row 1   (h 430)    WS9 Structural Constraint Detail, full width
Row 2   (h 280)    WS3 Utilisation vs Wait (reused), full width
Data note (h 40)
```
- Text object: "Two units carry a structural floor above the 14-day standard (14.4 and 14.7 days at zero congestion). 678 patients/week sit behind them. These need scheduling-template redesign, not additional slots."

### Dashboard actions

| # | Type | Source | Target | Field | Run on |
|---|---|---|---|---|---|
| A1 | Filter | DB1 · WS2 | DB1 · WS3 | `unit` | Select |
| A2 | Highlight | DB1 · WS3 | DB1 · WS2 | `unit` | Hover |
| A3 | Filter | DB1 · WS2 | DB1 · WS5 | `specialty` | Select |
| A4 | Highlight | DB3 · WS8 | DB3 · WS10 | `allocation` | Hover |
| A5 | Filter | DB4 · WS9 | DB4 · WS3 | `unit` | Select |

Set every action's clearing behaviour to **Show all values**.

---

## 6 · Formatting standards

- Palette: primary #2E86AB, alert #C0392B, warn #E8A33D, neutral #8C8C8C, muted #B8C4CE
- Numbers: days `0.0" d"`; percentages `0.0%`; counts `#,##0`; R² `0.000`
- No gridlines, no borders on worksheet objects, 8px padding
- Dashboard background #FFFFFF; title 16pt semibold; subtitle 11pt #5A6570
- Every axis has an explicit title. No default "AVG(...)" titles anywhere.

---

## 7 · Validation checks

Run these before publishing. Each compares a dashboard figure against `outputs/`.

| # | Check | Expected | Source of truth |
|---|---|---|---|
| V1 | WS1 mean wait tile | `15.91` days | `outputs/capacity_scenarios.csv`, row `+0% capacity` |
| V2 | WS2 count of bars above the reference line | `11` | `outputs/unit_baseline.csv` where `wait > 14` |
| V3 | WS2 total bars | `26` | `outputs/unit_baseline.csv` row count |
| V4 | WS4 highest R² | `0.8532` for `M3 queueing term + FE` | `outputs/wait_driver_models.csv` |
| V5 | WS4 lowest R² | `0.4894` for `M1 utilisation only` | `outputs/wait_driver_models.csv` |
| V6 | WS7 High tier ratio | `2.18×` | `outputs/noshow_risk_tiers.csv` |
| V7 | WS8 optimised mean wait at +5% | `11.90` days | `outputs/capacity_scenarios.csv` |
| V8 | WS8 pro-rata mean wait at +5% | `12.85` days | `outputs/capacity_scenarios.csv` |
| V9 | WS9 units above the standard line | `2` | `outputs/capacity_summary.json` → `gap_to_standard.structurally_unreachable_units` |
| V10 | WS9 the two α values | `14.4` and `14.7` | `outputs/capacity_summary.json` → `structural_floor_days` |
| V11 | WS11 top recipient share | `30.0%` (Primary care @ CLN-01) | `outputs/capacity_allocation.csv` |
| V12 | Data note visible on all 4 dashboards | yes | this document |

Any mismatch means the extract is stale — rerun `src/90_build_tableau_extracts.py` and refresh.

---

## 8 · Publishing

Server → Tableau Public → Save to Tableau Public As.

- Workbook name: `Clinical Operations & Patient Capacity Optimization`
- Show sheets: **dashboards only** (hide all 11 worksheets)
- Set DB1 as the default view before saving
- After publishing, open the public URL in a logged-out browser and re-run V1, V2, V9 and V12
