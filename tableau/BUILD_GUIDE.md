# Clinical Operations & Patient Capacity Optimization — Tableau build guide

The data in `tableau/data/` is already shaped for Tableau: one row per mark, explicit
dimensions and measures, no pre-pivoting. Every figure comes from the pipeline in `src/`.

## Connect

Tableau → **Connect → To a File → Text file** → pick a CSV from `tableau/data/`.
Add the others via **Data → New Data Source** (each sheet below names the file it uses).

## Dashboards

### 1 - Access Overview

| Sheet | Data file | Build |
|---|---|---|
| KPI tiles | `kpis.csv` | Rows: Kpi | Text: SUM(Value) | Mark: Text |
| Wait by unit | `unit_baseline.csv` | Rows: Unit | Columns: AVG(Wait) | Colour: Specialty | Reference line at 14 | sort desc |
| Utilisation vs wait | `unit_baseline.csv` | Columns: AVG(Util) | Rows: AVG(Wait) | Detail: Unit | Size: SUM(Demand) | Colour: Specialty | Mark: Circle |

### 2 - Drivers & No-show

| Sheet | Data file | Build |
|---|---|---|
| Wait driver models | `wait_driver_models.csv` | Rows: Model | Columns: AVG(R2) | Label: AVG(R2) | Mark: Bar |
| No-show tiers | `noshow_tiers.csv` | Columns: Tier | Rows: AVG(Rate) | Label: AVG(Vs Base) | Mark: Bar |
| Wait trend | `weekly_panel.csv` | Columns: Week (continuous) | Rows: AVG(Avg Wait Days) | Colour: Specialty | Mark: Line |

### 3 - Capacity Simulator

| Sheet | Data file | Build |
|---|---|---|
| Scenario mean wait | `capacity_scenarios_long.csv` | Columns: Capacity Step Pct | Rows: AVG(Mean Wait Days) | Colour: Allocation | Mark: Line | Reference line at 14 |
| Units over standard | `capacity_scenarios_long.csv` | Columns: Capacity Step Pct | Rows: AVG(Units Over Standard) | Colour: Allocation | Mark: Bar |
| Where capacity goes | `capacity_allocation.csv` | Rows: Unit | Columns: SUM(Share Of New Capacity) | Colour: Specialty | sort desc |

## Publish

**Server → Tableau Public → Save to Tableau Public As…**, sign in, name the viz.
