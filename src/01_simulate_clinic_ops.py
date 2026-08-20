"""
Step 1 - Simulate 18 months of clinic operations.

Two grains are produced:
  appointments  - one row per appointment (patient-level: wait, no-show, urgency)
  weekly_panel  - specialty x clinic x week (demand, capacity, utilisation, wait)

Wait time is generated from a queueing relationship, w = a * rho/(1-rho), because
that is how access behaves in practice: wait is flat while there is slack and then
goes vertical near full utilisation. Step 3 *re-fits* that relationship from the
data rather than reusing the generator's constants - the model has to earn it.
"""
import numpy as np, pandas as pd, sqlite3
from datetime import date, timedelta
from config import *

rng = np.random.default_rng(SEED)
start = date(2025, 3, 3)

clinic_ids = [c[0] for c in CLINICS]
clinic_mix = np.array([0.34, 0.24, 0.27, 0.15])

# persistent unit-level effects: scheduling-template quality and site efficiency.
# Without these the wait equation would be a pure function of utilisation and any
# regression would recover it perfectly - which is not what real access data looks like.
site_eff = {c[0]: float(rng.normal(1.0, 0.11)) for c in CLINICS}
panel, appts = [], []
aid = 0
for spec, base_dem, n_prov, slots_pp, mins, ns_base, amp, urgent_share in SPECIALTIES:
    # providers spread across clinics
    prov_alloc = rng.multinomial(n_prov, clinic_mix)
    for ci, clinic in enumerate(clinic_ids):
        provs = int(prov_alloc[ci])
        if provs == 0: continue
        dem_share = provs / n_prov
        template_mismatch = float(rng.normal(0, 2.4))   # unit-level scheduling drag, in days
        # some units are chronically over-referred relative to their panel, others
        # carry slack - this is the spread the optimiser exists to exploit
        load_factor = float(np.clip(rng.normal(1.0, 0.12), 0.72, 1.22))
        backlog = 0.0
        for t in range(WEEKS):
            season = 1 + amp * np.sin(2*np.pi*(t % 52)/52 - 0.9)
            trend  = 1 + 0.0016 * t
            demand = DEMAND_SCALE * base_dem * dem_share * load_factor * season * trend * rng.normal(1, 0.09)
            demand = max(1.0, demand)

            booked_slots = provs * slots_pp * rng.normal(1, 0.05)
            ns_rate = float(np.clip(rng.normal(ns_base, 0.018), 0.02, 0.45))
            cancels = float(np.clip(rng.normal(CANCEL_BASE, 0.015), 0.0, 0.30))
            # effective capacity: no-shows waste slots, overbooking claws some back,
            # cancellations that arrive early enough get refilled
            eff_cap = booked_slots * (1 - ns_rate*(1 - OVERBOOK_RECOVERY)
                                        - cancels*(1 - CANCEL_REFILL))
            rho = float(np.clip(demand / max(eff_cap, 1), 0.30, 0.965))
            # queueing pressure, then everything real life adds on top of it
            structural = 2.5 + 1.15 * (rho/(1-rho)) * site_eff[clinic]
            backlog = 0.72 * backlog + max(0.0, demand - eff_cap) * 0.08   # carry-over
            wait = (structural + template_mismatch + backlog) * rng.lognormal(0, 0.17) \
                   + rng.normal(0, 1.9)
            wait = float(np.clip(wait, 1.0, 90))

            panel.append((t, (start+timedelta(weeks=t)).isoformat(), spec, clinic, provs,
                          round(booked_slots,1), round(eff_cap,1), round(demand,1),
                          round(rho,4), round(wait,2), round(ns_rate,4), round(cancels,4), mins))

            # patient-level rows (sampled, not every appointment, to keep the file sane)
            n_appt = int(min(demand, eff_cap) * 0.28)
            for _ in range(n_appt):
                urgent = rng.random() < urgent_share
                w = max(0.5, wait * (0.35 if urgent else 1.06) * rng.lognormal(0, 0.35))
                age = int(np.clip(rng.normal(54, 18), 1, 98))
                prior_ns = int(rng.poisson(0.42))
                lead = w
                p_ns = 1/(1+np.exp(-(-2.90 + 0.014*lead + 0.42*prior_ns - 0.011*(age-54)
                                     + (0.55 if not urgent else -0.35)
                                     + (0.62 if spec=="Behavioral health" else 0))))
                appts.append((f"APT-{aid:07d}", t, spec, clinic, round(w,2), int(urgent),
                              age, prior_ns, mins, int(rng.random() < p_ns)))
                aid += 1

panel = pd.DataFrame(panel, columns=["week","week_start","specialty","clinic_id","providers",
    "booked_slots","effective_capacity","demand","utilisation","avg_wait_days",
    "no_show_rate","cancel_rate","appt_minutes"])
appts = pd.DataFrame(appts, columns=["appt_id","week","specialty","clinic_id","wait_days",
    "urgent","age","prior_no_shows","appt_minutes","no_show"])

con = sqlite3.connect(DB)
panel.to_sql("weekly_panel", con, if_exists="replace", index=False)
appts.to_sql("appointments", con, if_exists="replace", index=False)
pd.DataFrame(CLINICS, columns=["clinic_id","clinic_name","clinic_type"]).to_sql("clinics", con, if_exists="replace", index=False)
con.commit(); con.close()
panel.to_csv(DATA/"weekly_panel.csv", index=False)
appts.to_csv(DATA/"appointments.csv", index=False)

print(f"weekly panel rows : {len(panel):,}  ({panel.specialty.nunique()} specialties x {panel.clinic_id.nunique()} clinics x {WEEKS} weeks)")
print(f"appointments      : {len(appts):,}")
print(f"mean utilisation  : {panel.utilisation.mean():.3f}   (p90 {panel.utilisation.quantile(.9):.3f})")
print(f"mean wait (days)  : {panel.avg_wait_days.mean():.1f}   median {panel.avg_wait_days.median():.1f}")
print(f"no-show rate      : {appts.no_show.mean():.2%}")
print(f"specialties over {TARGET_WAIT_DAYS}d mean wait: "
      f"{(panel.groupby('specialty').avg_wait_days.mean() > TARGET_WAIT_DAYS).sum()} of {panel.specialty.nunique()}")
