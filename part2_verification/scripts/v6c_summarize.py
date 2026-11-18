"""Aggregate V6c: corrected (exact) interventional BCM per system/background vs tree-path and vs
Exp01's shap-0.51 interventional values (same rows, same backgrounds)."""
import glob

import numpy as np
import pandas as pd

ROOT = "/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/"
sel = pd.read_csv(ROOT + "data/manifests/cohort_author_selection.csv")


def bcm(phi):
    n = np.linalg.norm(phi, axis=1); u = phi[n > 1e-9] / n[n > 1e-9, None]; k = len(u); s = u.sum(0)
    return float((s @ s - k) / (k * (k - 1))) if k > 1 else np.nan


rows = []
for rep in ["author", "role_aware"]:
    tree = np.load(f"results/v5/phi_{rep}_paper_code.npy")
    for b in [211, 223, 227]:
        fs = sorted(glob.glob(f"results/v6c/exact_{rep}_bg{b}_fold*.npz"))
        if len(fs) != 5:
            print("missing", rep, b, len(fs)); continue
        ex = np.zeros_like(tree); old = np.zeros_like(tree); maxerr = 0
        for f in fs:
            z = np.load(f)
            ex[z["rows"]] = z["phi"]; old[z["rows"]] = z["shap_tree_interventional_phi"]; maxerr = max(maxerr, float(z["add_err"]))
        for g in sorted(sel.agent_system.unique()):
            m = (sel.agent_system == g).values
            cos = (ex[m] * tree[m]).sum(1) / (np.linalg.norm(ex[m], axis=1) * np.linalg.norm(tree[m], axis=1) + 1e-12)
            rows.append(dict(rep=rep, bg_seed=b, system=g, bcm_tree_path=bcm(tree[m]), bcm_exact_interventional=bcm(ex[m]),
                             bcm_shap051_interventional_exp01=bcm(old[m]), median_row_cos_exact_vs_tree=float(np.median(cos)),
                             max_abs_dev_shap051_vs_exact=float(np.abs(old[m] - ex[m]).max()), max_additivity_err=maxerr))
out = pd.DataFrame(rows)
out.to_csv("results/v6c_corrected_G.csv", index=False)
s = out.groupby(["rep", "system"]).agg(tree=("bcm_tree_path", "first"), exact_min=("bcm_exact_interventional", "min"),
                                        exact_max=("bcm_exact_interventional", "max"), exp01_min=("bcm_shap051_interventional_exp01", "min"),
                                        exp01_max=("bcm_shap051_interventional_exp01", "max"), cos=("median_row_cos_exact_vs_tree", "median"),
                                        dev=("max_abs_dev_shap051_vs_exact", "max"), adderr=("max_additivity_err", "max"))
print(s.round(3).to_string())
