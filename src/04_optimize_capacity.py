"""
Step 4 - Capacity allocation.

Objective: minimise total PATIENT-WAIT-DAYS per week, sum_i demand_i * wait_i(cap_i),
where wait_i comes from the fitted curve in step 3.

wait_i is convex and decreasing in cap_i and the units are separable, so greedy
marginal allocation - repeatedly give the next slot to whichever unit buys the most
wait-days - is provably optimal. No solver needed, and it produces the marginal-value
curve an operations director actually wants to see.

Three questions are answered:
  1. If we add X% capacity, where should it go, and what does it buy?
  2. How much of that benefit is available for FREE by redistributing what we have?
  3. What capacity would it take to put every unit inside the 14-day standard?
"""
import numpy as np, pandas as pd, json
from config import *

u = pd.read_csv(OUT/"unit_baseline.csv")
val = pd.read_csv(OUT/"capacity_model_validation.csv").iloc[0]
b = float(val.beta_pressure)

dem = u.demand.to_numpy(float)
cap0 = u.eff_cap.to_numpy(float)
alpha = u.alpha.to_numpy(float)
names = u.unit.to_numpy()

def wait(cap):
    rho = np.clip(dem / np.maximum(cap, 1e-6), 0.02, 0.995)
    return alpha + b * (rho / (1 - rho))

def wait_days(cap):
    return float((dem * wait(cap)).sum())

BASE_WD = wait_days(cap0)
TOTAL_CAP = cap0.sum()
STEP = TOTAL_CAP * 0.0025          # allocate in 0.25%-of-system increments

def greedy(extra_total, cap_start=None, allow_removal=False, removal_budget=0.0):
    """Give each increment to the unit with the largest marginal wait-day saving."""
    cap = (cap0 if cap_start is None else cap_start).copy()
    added = np.zeros_like(cap)
    n = int(round(extra_total / STEP))
    for _ in range(n):
        cur = dem * wait(cap)
        gain = np.zeros_like(cap)
        for i in range(len(cap)):
            c2 = cap.copy(); c2[i] += STEP
            gain[i] = cur.sum() - float((dem * wait(c2)).sum())
        i = int(np.argmax(gain))
        cap[i] += STEP; added[i] += STEP
    return cap, added

def redistribute(budget_frac=0.10):
    """Move capacity from the slackest units to the tightest, net-zero new capacity.
    Take from the unit whose marginal wait-day COST is lowest, give to the unit whose
    marginal saving is highest, until no beneficial trade remains."""
    cap = cap0.copy()
    moved = 0.0
    limit = TOTAL_CAP * budget_frac
    while moved < limit:
        cur = float((dem * wait(cap)).sum())
        save, cost = np.zeros(len(cap)), np.full(len(cap), np.inf)
        for i in range(len(cap)):
            c2 = cap.copy(); c2[i] += STEP
            save[i] = cur - float((dem * wait(c2)).sum())
            if cap[i] - STEP > dem[i] * 1.02:        # never push a donor into overload
                c3 = cap.copy(); c3[i] -= STEP
                cost[i] = float((dem * wait(c3)).sum()) - cur
        g, d = int(np.argmax(save)), int(np.argmin(cost))
        if g == d or not np.isfinite(cost[d]) or save[g] <= cost[d]:
            break
        cap[g] += STEP; cap[d] -= STEP; moved += STEP
    return cap, moved

# ---------------------------------------------------------------- scenarios
rows = []
for step in CAPACITY_STEPS:
    extra = TOTAL_CAP * step
    cap_opt, added = (cap0.copy(), np.zeros_like(cap0)) if step == 0 else greedy(extra)
    cap_flat = cap0 * (1 + step)                     # the naive "everyone gets +X%"
    wd_o, wd_f = wait_days(cap_opt), wait_days(cap_flat)
    w_o, w_f = wait(cap_opt), wait(cap_flat)
    rows.append(dict(
        scenario=f"+{step:.0%} capacity", step=step,
        wait_days_optimised=round(wd_o, 0), wait_days_prorata=round(wd_f, 0),
        mean_wait_opt=round(float((dem*w_o).sum()/dem.sum()), 2),
        mean_wait_prorata=round(float((dem*w_f).sum()/dem.sum()), 2),
        pct_vs_base_opt=round((wd_o/BASE_WD - 1)*100, 2),
        pct_vs_base_prorata=round((wd_f/BASE_WD - 1)*100, 2),
        units_over_standard_opt=int((w_o > TARGET_WAIT_DAYS).sum()),
        units_over_standard_prorata=int((w_f > TARGET_WAIT_DAYS).sum()),
        patients_over_standard_opt=int(dem[w_o > TARGET_WAIT_DAYS].sum()),
        optimiser_advantage_wait_days=round(wd_f - wd_o, 0)))
scen = pd.DataFrame(rows)

# ---------------------------------------------------------------- redistribution
cap_re, moved = redistribute()
w_re = wait(cap_re)
redis = dict(slots_moved=round(moved, 1), pct_of_system=round(moved/TOTAL_CAP*100, 2),
             wait_days=round(wait_days(cap_re), 0),
             pct_vs_base=round((wait_days(cap_re)/BASE_WD - 1)*100, 2),
             mean_wait=round(float((dem*w_re).sum()/dem.sum()), 2),
             units_over_standard=int((w_re > TARGET_WAIT_DAYS).sum()))
# what capacity increase buys the same benefit?
equiv = float(np.interp(redis["pct_vs_base"], scen.pct_vs_base_opt[::-1], scen.step[::-1]))
redis["equivalent_capacity_increase_pct"] = round(equiv*100, 2)

# ---------------------------------------------------------------- gap to standard
# alpha is the wait a unit would still have at ZERO congestion - scheduling template
# drag, backlog carry-over, referral triage. Capacity cannot touch it. Units whose
# alpha already exceeds the standard are structurally unreachable by adding slots,
# and saying so is the most useful output in this whole section.
structural = alpha > TARGET_WAIT_DAYS
reachable = ~structural
need = 0.0
cap_t = cap0.copy()
while (wait(cap_t)[reachable] > TARGET_WAIT_DAYS).any() and need < TOTAL_CAP * 1.5:
    w = np.where(reachable, wait(cap_t), -np.inf)
    i = int(np.argmax(np.where(w > TARGET_WAIT_DAYS, w, -np.inf)))
    cap_t[i] += STEP; need += STEP
gap = dict(extra_capacity_needed=round(need, 1),
           pct_of_system=round(need/TOTAL_CAP*100, 2),
           providers_equivalent=round(need / (u.eff_cap.sum()/u.providers.sum()), 1),
           reachable_units_within_standard=bool((wait(cap_t)[reachable] <= TARGET_WAIT_DAYS).all()),
           structurally_unreachable_units=int(structural.sum()),
           structurally_unreachable_names=[str(x) for x in names[structural]],
           structural_floor_days=[round(float(a),1) for a in alpha[structural]],
           patients_affected_structural=int(dem[structural].sum()))

# ---------------------------------------------------------------- where it goes
cap10, add10 = greedy(TOTAL_CAP * 0.10)
alloc = u[["unit","specialty","clinic_id","demand","eff_cap","util","wait"]].copy()
alloc["slots_added_at_plus10"] = add10.round(1)
alloc["share_of_new_capacity"] = (add10/add10.sum()*100).round(1)
alloc["wait_after"] = wait(cap10).round(2)
alloc["wait_reduction_days"] = (u.wait - wait(cap10)).round(2)
alloc["redistribution_delta"] = (cap_re - cap0).round(1)
alloc = alloc.sort_values("share_of_new_capacity", ascending=False)

scen.to_csv(OUT/"capacity_scenarios.csv", index=False)
alloc.to_csv(OUT/"capacity_allocation.csv", index=False)
json.dump(dict(base_wait_days=round(BASE_WD,0), total_capacity=round(TOTAL_CAP,1),
               beta=b, redistribution=redis, gap_to_standard=gap),
          open(OUT/"capacity_summary.json","w"), indent=2)

print(scen[["scenario","mean_wait_opt","mean_wait_prorata","pct_vs_base_opt",
            "pct_vs_base_prorata","units_over_standard_opt","optimiser_advantage_wait_days"]].to_string(index=False))
print()
print("REDISTRIBUTION (zero new capacity):")
for k,v in redis.items(): print(f"  {k:34s}: {v}")
print()
print("GAP TO THE 14-DAY STANDARD:")
for k,v in gap.items(): print(f"  {k:34s}: {v}")
if gap["structurally_unreachable_units"]:
    print(f"  -> {gap['structurally_unreachable_units']} unit(s) cannot reach the standard at ANY capacity:")
    for nm, fl in zip(gap["structurally_unreachable_names"], gap["structural_floor_days"]):
        print(f"       {nm}: floor {fl} days even at zero congestion")
print()
print("Where the first 10% of new capacity goes:")
print(alloc.head(8)[["unit","util","wait","share_of_new_capacity","wait_after","wait_reduction_days"]].to_string(index=False))
