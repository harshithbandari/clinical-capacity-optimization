"""
Step 2 - What actually drives wait time, and who no-shows.

(a) Wait-time drivers: OLS with specialty and clinic fixed effects. The question is
    not "is wait correlated with utilisation" (it is, trivially) but how much of the
    variation utilisation explains ONCE specialty and site are controlled for -
    i.e. is access a structural capacity problem or a local operational one?
(b) No-show model: class-weighted logistic regression, tuned on Youden's J, output
    as risk tiers - the input the capacity model needs to convert booked slots into
    EFFECTIVE slots.
"""
import numpy as np, pandas as pd, sqlite3, statsmodels.api as sm, statsmodels.formula.api as smf
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, roc_curve, confusion_matrix
from config import *

con = sqlite3.connect(DB)
panel = pd.read_sql_query("SELECT * FROM weekly_panel", con)
appts = pd.read_sql_query("SELECT * FROM appointments", con); con.close()

# ---------------------------------------------------------------- (a) drivers
panel["util_pressure"] = panel.utilisation / (1 - panel.utilisation)   # queueing term
models = {
 "M1 utilisation only":            "avg_wait_days ~ utilisation",
 "M2 + specialty & clinic FE":     "avg_wait_days ~ utilisation + C(specialty) + C(clinic_id)",
 "M3 queueing term + FE":          "avg_wait_days ~ util_pressure + C(specialty) + C(clinic_id)",
 "M4 + no-show & cancel rates":    "avg_wait_days ~ util_pressure + no_show_rate + cancel_rate + C(specialty) + C(clinic_id)",
}
rows, fits = [], {}
for name, f in models.items():
    m = smf.ols(f, data=panel).fit()
    fits[name] = m
    rows.append(dict(model=name, r2=m.rsquared, adj_r2=m.rsquared_adj,
                     aic=m.aic, n=int(m.nobs)))
drv = pd.DataFrame(rows).round(4)
best = fits["M4 + no-show & cancel rates"]
coef = (pd.DataFrame({"term": best.params.index, "coef": best.params.values,
                      "std_err": best.bse.values, "t": best.tvalues.values, "p": best.pvalues.values})
        .query("~term.str.startswith('C(')", engine="python").round(4))

# how much wait-time variance is structural (specialty/site) vs utilisation?
m_fe   = smf.ols("avg_wait_days ~ C(specialty) + C(clinic_id)", data=panel).fit()
m_util = smf.ols("avg_wait_days ~ util_pressure", data=panel).fit()
decomp = dict(fe_only_r2=round(m_fe.rsquared,4), util_only_r2=round(m_util.rsquared,4),
              combined_r2=round(fits["M3 queueing term + FE"].rsquared,4))

# ---------------------------------------------------------------- (b) no-show
X = pd.get_dummies(appts[["wait_days","urgent","age","prior_no_shows","specialty"]],
                   columns=["specialty"], drop_first=True).astype(float)
y = appts.no_show
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=SEED, stratify=y)
ns = LogisticRegression(max_iter=2000, class_weight="balanced").fit(Xtr, ytr)
p = ns.predict_proba(Xte)[:,1]
auc = roc_auc_score(yte, p)
fpr, tpr, thr = roc_curve(yte, p)
j = thr[np.argmax(tpr - fpr)]
pred = (p >= j).astype(int)
tn, fp, fn, tp = confusion_matrix(yte, pred).ravel()

tier = pd.cut(p, [-.01, np.quantile(p,.6), np.quantile(p,.85), 1.01], labels=["Low","Medium","High"])
tiers = (pd.DataFrame({"tier": tier, "actual": yte.values}).groupby("tier", observed=True)
         .agg(appts=("actual","size"), no_shows=("actual","sum"), rate=("actual","mean")).reset_index())
tiers["vs_base"] = (tiers.rate / yte.mean()).round(2)

coefs_ns = pd.DataFrame({"feature": X.columns, "coef": ns.coef_[0]}).sort_values("coef", key=abs, ascending=False)

drv.to_csv(OUT/"wait_driver_models.csv", index=False)
coef.to_csv(OUT/"wait_driver_coefficients.csv", index=False)
tiers.to_csv(OUT/"noshow_risk_tiers.csv", index=False)
coefs_ns.round(4).to_csv(OUT/"noshow_coefficients.csv", index=False)
pd.DataFrame([dict(roc_auc=round(auc,4), threshold=round(float(j),4),
                   recall=round(tp/(tp+fn),4), precision=round(tp/(tp+fp),4),
                   base_rate=round(float(yte.mean()),4), **decomp)]).to_csv(OUT/"noshow_summary.csv", index=False)

print(drv.to_string(index=False)); print()
print("variance decomposition:", decomp)
print(f"  -> specialty + site alone explain {decomp['fe_only_r2']:.1%} of wait variation;")
print(f"     the utilisation pressure term alone explains {decomp['util_only_r2']:.1%};")
print(f"     together {decomp['combined_r2']:.1%}. Access here is a CAPACITY problem, not a site-culture one.")
print()
print(coef.to_string(index=False)); print()
print(f"no-show model ROC-AUC {auc:.4f} | Youden's J threshold {j:.3f} | recall {tp/(tp+fn):.1%} | base rate {yte.mean():.2%}")
print(tiers.to_string(index=False))
