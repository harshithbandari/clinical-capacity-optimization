"""
Reshape pipeline outputs into TIDY, Tableau-native tables.

Tableau wants one row per mark with explicit dimensions and measures - not the wide,
pre-pivoted shapes that suit an HTML table. Anything wide gets melted here so the
workbook does the aggregation, which is what makes the vizzes interactive rather
than static pictures of numbers.
"""
import pandas as pd, numpy as np, json
from pathlib import Path

ROOT = Path("/home/claude/work")
OUT  = ROOT/"tableau"/"data"
for d in ["claims","clinical","supply"]: (OUT/d).mkdir(parents=True, exist_ok=True)

# ============================================================ CLAIMS
C = ROOT/"claims-denial-analytics"/"outputs"
claims = pd.read_csv(ROOT/"claims-denial-analytics"/"data"/"claims.csv")

k = pd.read_csv(C/"01_denial_kpis.csv").iloc[0]
pd.DataFrame([
 dict(kpi="First-pass denial rate", value=k.denial_rate_pct, unit="pct", sort=1),
 dict(kpi="First-pass resolution",  value=k.first_pass_resolution_pct, unit="pct", sort=2),
 dict(kpi="Revenue lost",           value=k.revenue_lost, unit="usd", sort=3),
 dict(kpi="% of allowed lost",      value=k.pct_allowed_lost, unit="pct", sort=4),
 dict(kpi="Days in A/R (all)",      value=k.days_in_ar, unit="days", sort=5),
 dict(kpi="Days in A/R (clean)",    value=k.days_in_ar_clean, unit="days", sort=6),
 dict(kpi="Days in A/R (denied)",   value=k.days_in_ar_denied, unit="days", sort=7),
 dict(kpi="Total allowed",          value=k.total_allowed, unit="usd", sort=8),
]).to_csv(OUT/"claims"/"kpis.csv", index=False)

pd.read_csv(C/"02_payer_scorecard.csv").to_csv(OUT/"claims"/"payer_scorecard.csv", index=False)
pd.read_csv(C/"03_denial_root_cause.csv").to_csv(OUT/"claims"/"denial_root_cause.csv", index=False)
pd.read_csv(C/"04_provider_facility.csv").to_csv(OUT/"claims"/"provider_outliers.csv", index=False)

# monthly trend at claim grain -> tidy fact table Tableau can slice any way
claims["month"] = claims.submitted_date.str.slice(0,7)
claims["lost"]  = np.where((claims.denied==1) & (claims.overturned.fillna(0)==0), claims.allowed_amount, 0.0)
claims["recovered"] = np.where(claims.overturned.fillna(0)==1, claims.allowed_amount, 0.0)
(claims.groupby(["month","payer","payer_type","service_line","facility_name"], as_index=False)
   .agg(claims=("claim_id","size"), denials=("denied","sum"),
        allowed=("allowed_amount","sum"), paid=("paid_amount","sum"),
        revenue_lost=("lost","sum"), revenue_recovered=("recovered","sum"),
        avg_days_to_payment=("days_to_payment","mean"))
   .assign(denial_rate_pct=lambda d: (d.denials/d.claims*100).round(2))
   .round(2).to_csv(OUT/"claims"/"monthly_fact.csv", index=False))

# A/R aging, long
ag = pd.read_csv(C/"05_ar_aging.csv")
ag.to_csv(OUT/"claims"/"ar_aging.csv", index=False)

# model + queue
pd.read_csv(C/"model_scores.csv").to_csv(OUT/"claims"/"model_scores.csv", index=False)
pd.read_csv(C/"model_lift_by_decile.csv").to_csv(OUT/"claims"/"model_lift.csv", index=False)
st = pd.read_csv(C/"queue_strategy_comparison.csv")
st.melt(id_vars=["strategy"], value_vars=["revenue_protected","net_benefit","review_cost"],
        var_name="metric", value_name="amount").to_csv(OUT/"claims"/"queue_strategy_long.csv", index=False)
st.to_csv(OUT/"claims"/"queue_strategy.csv", index=False)
pd.read_csv(C/"queue_sensitivity.csv").to_csv(OUT/"claims"/"queue_sensitivity.csv", index=False)

# ============================================================ CLINICAL
L = ROOT/"clinical-capacity-optimization"/"outputs"
panel = pd.read_csv(ROOT/"clinical-capacity-optimization"/"data"/"weekly_panel.csv")
panel.to_csv(OUT/"clinical"/"weekly_panel.csv", index=False)
u = pd.read_csv(L/"unit_baseline.csv"); u.to_csv(OUT/"clinical"/"unit_baseline.csv", index=False)
pd.read_csv(L/"noshow_risk_tiers.csv").to_csv(OUT/"clinical"/"noshow_tiers.csv", index=False)
pd.read_csv(L/"wait_driver_models.csv").to_csv(OUT/"clinical"/"wait_driver_models.csv", index=False)
pd.read_csv(L/"capacity_allocation.csv").to_csv(OUT/"clinical"/"capacity_allocation.csv", index=False)

# scenarios: melt optimised vs pro-rata into one long table so a single viz compares them
sc = pd.read_csv(L/"capacity_scenarios.csv")
long = []
for r in sc.itertuples():
    for lbl, w, wd, uo in [("Optimised allocation", r.mean_wait_opt, r.wait_days_optimised, r.units_over_standard_opt),
                           ("Pro-rata (uniform)",   r.mean_wait_prorata, r.wait_days_prorata, r.units_over_standard_prorata)]:
        long.append(dict(scenario=r.scenario, capacity_step_pct=round(r.step*100,1), allocation=lbl,
                         mean_wait_days=w, wait_days_total=wd, units_over_standard=uo))
pd.DataFrame(long).to_csv(OUT/"clinical"/"capacity_scenarios_long.csv", index=False)

summ = json.load(open(L/"capacity_summary.json")); red = summ["redistribution"]; gap = summ["gap_to_standard"]
pd.DataFrame([
 dict(kpi="Mean wait (today)", value=round(float(sc.iloc[0].mean_wait_opt),2), unit="days", sort=1),
 dict(kpi="Units over standard", value=int((u.wait>14).sum()), unit="count", sort=2),
 dict(kpi="Patients over standard", value=int(u.loc[u.wait>14,"demand"].sum()), unit="count", sort=3),
 dict(kpi="Mean utilisation", value=round(float(u.util.mean())*100,2), unit="pct", sort=4),
 dict(kpi="Wait-days per week", value=round(float(summ["base_wait_days"]),0), unit="count", sort=5),
 dict(kpi="Slots moved (redistribution)", value=red["pct_of_system"], unit="pct", sort=6),
 dict(kpi="Wait-day cut from redistribution", value=abs(red["pct_vs_base"]), unit="pct", sort=7),
 dict(kpi="Equivalent capacity increase", value=red["equivalent_capacity_increase_pct"], unit="pct", sort=8),
]).to_csv(OUT/"clinical"/"kpis.csv", index=False)

# ============================================================ SUPPLY
S = ROOT/"supply-chain-control-tower"/"outputs"
D = ROOT/"supply-chain-control-tower"/"data"
pd.read_csv(S/"forecast_league_table.csv").to_csv(OUT/"supply"/"forecast_league.csv", index=False)
pd.read_csv(S/"forecast_scores_by_series.csv").to_csv(OUT/"supply"/"forecast_by_series.csv", index=False)
pd.read_csv(S/"inventory_policy.csv").to_csv(OUT/"supply"/"inventory_policy.csv", index=False)
pd.read_csv(D/"demand_weekly.csv").to_csv(OUT/"supply"/"demand_weekly.csv", index=False)

cp = pd.read_csv(S/"policy_comparison.csv", index_col=0).reset_index().rename(columns={"index":"policy","policy":"policy"})
cp.columns = ["policy"]+list(cp.columns[1:])
cost_long = cp.melt(id_vars=["policy"],
                    value_vars=["holding_cost","ordering_cost","transport_cost","stockout_cost"],
                    var_name="cost_line", value_name="amount")
cost_long["cost_line"] = cost_long.cost_line.str.replace("_"," ").str.title()
cost_long["policy"] = cost_long.policy.replace({"proposed":"Proposed policy","reactive_baseline":"Reactive baseline"})
cost_long.to_csv(OUT/"supply"/"policy_cost_long.csv", index=False)
cp.to_csv(OUT/"supply"/"policy_comparison.csv", index=False)

sup = pd.read_csv(D/"supplier_performance.csv")
scen = pd.read_csv(S/"scenario_results.csv")
mix = json.loads(scen.iloc[0].supplier_mix.replace("'", '"'))
(sup.groupby("supplier", as_index=False)
    .agg(otif=("on_time_in_full","mean"), lead_time_wks=("lead_time_wks","mean"),
         lead_time_sd=("lead_time_wks","std"), fill_rate=("fill_rate","mean"))
    .assign(units_awarded=lambda d: d.supplier.map(mix).fillna(0).astype(int))
    .round(4).to_csv(OUT/"supply"/"supplier_scorecard.csv", index=False))

scen[["scenario","status","total_cost","holding_cost","stockout_cost","purchase_cost",
      "transport_cost","ordering_cost","po_lines","units_short","service_level",
      "avg_inventory_units","cost_vs_base_pct","service_delta_pp"]].to_csv(OUT/"supply"/"scenarios.csv", index=False)

lg = pd.read_csv(S/"forecast_league_table.csv"); b = cp[cp.policy=="reactive_baseline"].iloc[0]; p = cp[cp.policy=="proposed"].iloc[0]
pd.DataFrame([
 dict(kpi="Forecast WMAPE (champion)", value=round(float(lg.iloc[0].wmape_pct),2), unit="pct", sort=1),
 dict(kpi="Forecast WMAPE (naive)", value=round(float(lg[lg.model=='naive'].wmape_pct.iloc[0]),2), unit="pct", sort=2),
 dict(kpi="Fill rate (proposed)", value=round(float(p.fill_rate)*100,2), unit="pct", sort=3),
 dict(kpi="Fill rate (baseline)", value=round(float(b.fill_rate)*100,2), unit="pct", sort=4),
 dict(kpi="Quarterly cost saving", value=round(float(b.total_cost-p.total_cost),0), unit="usd", sort=5),
 dict(kpi="Annualised saving", value=round(float(b.total_cost-p.total_cost)*4,0), unit="usd", sort=6),
 dict(kpi="Working capital released", value=round(float(b.inventory_value-p.inventory_value),0), unit="usd", sort=7),
 dict(kpi="Optimised service level", value=round(float(scen.iloc[0].service_level)*100,2), unit="pct", sort=8),
]).to_csv(OUT/"supply"/"kpis.csv", index=False)

for d in ["claims","clinical","supply"]:
    fs = sorted((OUT/d).glob("*.csv"))
    print(f"{d:9s}: {len(fs)} tables")
    for f in fs:
        df = pd.read_csv(f); print(f"    {f.name:32s} {len(df):>6,} rows x {len(df.columns)} cols")
