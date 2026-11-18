"""Summarize V5: real BCM vs 50-seed label-permutation nulls (empirical one-sided p, null quantiles)."""
import glob
import sys

import numpy as np
import pandas as pd

d = pd.concat([pd.read_csv(f) for f in glob.glob("results/v5/v5_*.csv")], ignore_index=True)
systems = sorted(c.split("|")[1] for c in d.columns if c.startswith("bcm|"))
short = {s: s.replace("claude-3-5-sonnet-20241022", "Claude-3.5").replace("claude-3-7-sonnet-20250219", "Claude-3.7")
         .replace("gpt-4o-2024-08-06", "GPT-4o").replace("swe-agent-llama-", "Llama-").replace("405b", "405B")
         .replace("70b", "70B").replace("8b", "8B") for s in systems}
rows = []
for (rep, pred), g in d.groupby(["rep", "predictor"]):
    real = g[g.scheme == "real"].iloc[0]
    for s in systems:
        r = dict(rep=rep, predictor=pred, system=short[s], real_bcm=real[f"bcm|{s}"],
                 real_bcm_nonempty=real[f"bcm_nonempty|{s}"], real_auc_within=real[f"auc_within|{s}"],
                 real_auc_pooled=real["auc_pooled"])
        for sch in ["perm_system", "perm_system_repo", "perm_global"]:
            nul = g[g.scheme == sch][f"bcm|{s}"].dropna().values
            r[f"{sch}_n"] = len(nul)
            r[f"{sch}_q05"], r[f"{sch}_median"], r[f"{sch}_q95"] = np.quantile(nul, [0.05, 0.5, 0.95])
            # one-sided: is real BCM greater than null? / less than null?  (add-one estimator)
            r[f"{sch}_p_greater"] = (1 + (nul >= r["real_bcm"]).sum()) / (1 + len(nul))
            r[f"{sch}_p_less"] = (1 + (nul <= r["real_bcm"]).sum()) / (1 + len(nul))
            r[f"{sch}_null_auc_pooled_median"] = g[g.scheme == sch]["auc_pooled"].median()
        rows.append(r)
out = pd.DataFrame(rows)
out.to_csv("results/v5_permutation_summary.csv", index=False)
pd.set_option("display.width", 250)
cols = ["rep", "predictor", "system", "real_bcm", "real_auc_within", "perm_system_q05", "perm_system_median",
        "perm_system_q95", "perm_system_p_less", "perm_system_p_greater", "perm_system_repo_median", "perm_system_repo_p_less", "perm_global_median"]
print(out[cols].round(3).to_string(index=False))
# separation S = min(proprietary) - max(Llama), real and under nulls
prop = [s for s in systems if "llama" not in s]
lla = [s for s in systems if "llama" in s]
sep = []
for (rep, pred, sch), g in d.groupby(["rep", "predictor", "scheme"]):
    S = g[[f"bcm|{s}" for s in prop]].min(axis=1) - g[[f"bcm|{s}" for s in lla]].max(axis=1)
    sep.append(dict(rep=rep, predictor=pred, scheme=sch, n=len(S), S_median=S.median(),
                    S_q05=S.quantile(0.05), S_q95=S.quantile(0.95), auc_pooled_median=g.auc_pooled.median(),
                    max_add_err=g.max_add_err.max()))
sep = pd.DataFrame(sep)
sep.to_csv("results/v5_separation_summary.csv", index=False)
print(sep.round(3).to_string(index=False))
