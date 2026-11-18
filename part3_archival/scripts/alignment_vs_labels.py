"""Does a trajectory's contribution to BCM (cosine to its model's mean attribution direction) track
observable behaviour? OLS within primary5, R2 / released LGBM / seed 0, model fixed effects, task-clustered SEs."""
import sys
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
sys.path.insert(0, "src")
from bcm02.analysis import units
from bcm02.pipeline import COHORTS, load_cohort

z = np.load("results/runs/oof_primary5_r2_lgbm_paper_grouped5_s0.npz", allow_pickle=True)
T = load_cohort("primary5")
u, ok = units(z["phi"])
al = np.full(len(T), np.nan)
for r in COHORTS["primary5"]:
    m = (z["run"] == r) & ok
    d = u[m].mean(0); d /= np.linalg.norm(d)
    al[m] = u[m] @ d
T["alignment"] = al
L = pd.read_csv("results/tables/task_labels.csv")
D = T[["run", "instance_id", "alignment"]].merge(L, on=["run", "instance_id"])
for c in ["ran_tests", "ran_scripts", "resolved"]:
    D[c] = D[c].fillna(False).astype(int)
D["recall"] = D.touched_ref_files_recall.fillna(0)
D["log_extra"] = np.log1p(D.touched_extra_files)
fit = smf.ols("alignment ~ C(run) + resolved + ran_tests + ran_scripts + recall + log_extra", D).fit(
    cov_type="cluster", cov_kwds={"groups": pd.factorize(D.instance_id)[0]})
out = fit.summary2().tables[1]
out.to_csv("results/tables/a10_alignment_vs_observable_behaviour.csv")
print(out.round(3).to_string()); print("R2", round(fit.rsquared, 3))
fit0 = smf.ols("alignment ~ C(run)", D).fit()
print("R2 model only", round(fit0.rsquared, 3))
