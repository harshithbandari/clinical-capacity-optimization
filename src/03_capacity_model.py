"""
Step 3 - Fit the capacity -> wait-time curve, and validate it out of sample.

The scenario simulator is only worth anything if the wait response to capacity is
LEARNED rather than assumed. So:
  * fit  wait = a + b * rho/(1-rho)  with unit fixed effects, on the first 65 weeks
  * hold out the last 13 weeks and score the prediction there
  * the fitted b is what the optimiser uses to price a marginal slot
"""
import numpy as np, pandas as pd, sqlite3, statsmodels.formula.api as smf
from sklearn.metrics import mean_absolute_error, r2_score
from config import *

con = sqlite3.connect(DB)
panel = pd.read_sql_query("SELECT * FROM weekly_panel", con); con.close()
panel["unit"] = panel.specialty + " @ " + panel.clinic_id
panel["util_pressure"] = panel.utilisation / (1 - panel.utilisation)

split = WEEKS - HOLDOUT_WEEKS
tr, te = panel[panel.week < split].copy(), panel[panel.week >= split].copy()

fit = smf.ols("avg_wait_days ~ util_pressure + C(unit)", data=tr).fit()
te["pred_wait"] = fit.predict(te)
tr["pred_wait"] = fit.predict(tr)

val = dict(
    train_r2=round(fit.rsquared, 4),
    holdout_r2=round(r2_score(te.avg_wait_days, te.pred_wait), 4),
    holdout_mae_days=round(mean_absolute_error(te.avg_wait_days, te.pred_wait), 2),
    holdout_mean_wait=round(te.avg_wait_days.mean(), 2),
    beta_pressure=round(float(fit.params["util_pressure"]), 4),
    beta_se=round(float(fit.bse["util_pressure"]), 4),
    train_weeks=int(split), holdout_weeks=int(HOLDOUT_WEEKS))

# ---- unit-level baseline used by the optimiser (recent 13 weeks = current state)
recent = panel[panel.week >= split]
units = (recent.groupby(["unit", "specialty", "clinic_id"])
         .agg(demand=("demand", "mean"), eff_cap=("effective_capacity", "mean"),
              booked=("booked_slots", "mean"), providers=("providers", "mean"),
              util=("utilisation", "mean"), wait=("avg_wait_days", "mean"),
              no_show=("no_show_rate", "mean"), appt_min=("appt_minutes", "mean"))
         .reset_index())

# Baseline utilisation is the MEAN OF WEEKLY rho, not mean(demand)/mean(capacity) -
# rho is a convex function of capacity, so the ratio of means understates congestion
# (Jensen). Effective capacity is then back-solved from the observed rho so the
# baseline is internally consistent with what the units actually experienced.
b = float(fit.params["util_pressure"])
units["eff_cap"] = units.demand / units.util
units["alpha"] = units.wait - b * (units.util / (1 - units.util))

def wait_at(cap, demand, alpha):
    rho = np.clip(demand / np.maximum(cap, 1e-6), 0.05, 0.995)
    return alpha + b * (rho / (1 - rho))

units["wait_check"] = wait_at(units.eff_cap, units.demand, units.alpha)
units["patient_weeks"] = units.demand           # patients arriving per week
units["wait_days_total"] = units.demand * units.wait   # patient-days of waiting per week

units.round(4).to_csv(OUT/"unit_baseline.csv", index=False)
pd.DataFrame([val]).to_csv(OUT/"capacity_model_validation.csv", index=False)

print("capacity->wait model")
for k, v in val.items(): print(f"  {k:20s}: {v}")
print()
print(f"marginal wait sensitivity beta = {b:.3f} days per unit of rho/(1-rho)")
print()
print(units[["unit","demand","eff_cap","util","wait","wait_check"]]
      .sort_values("wait", ascending=False).head(10).to_string(index=False))
print()
over = units[units.wait > TARGET_WAIT_DAYS]
print(f"units above the {TARGET_WAIT_DAYS}-day access standard: {len(over)} of {len(units)}")
print(f"patients/week waiting longer than standard: {over.demand.sum():,.0f} of {units.demand.sum():,.0f} "
      f"({over.demand.sum()/units.demand.sum():.1%})")
