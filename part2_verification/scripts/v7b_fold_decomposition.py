"""V7b: per-fold BCM of the paper's actual (shipped) attributions; folds differ in early-stopped tree counts."""
import numpy as np
import pandas as pd

ROOT = "/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/"
S = np.load(ROOT + "external/colm-agent-eval/results/files/oof_shap_matrix.npy")
p = np.load(ROOT + "external/colm-agent-eval/results/files/oof_proba.npy")
sel = pd.read_csv(ROOT + "data/manifests/cohort_author_selection.csv")
from sklearn.model_selection import StratifiedKFold
fold = np.empty(len(sel), int)
for k, (_, va) in enumerate(StratifiedKFold(5, shuffle=True, random_state=42).split(np.zeros(len(sel)), sel.resolved)):
    fold[va] = k
iters = {0: 173, 1: 225, 2: 66, 3: 82, 4: 4}   # from V7 (best_iteration per fold)


def bcm(phi):
    n = np.linalg.norm(phi, axis=1); u = phi[n > 1e-9] / n[n > 1e-9, None]; k = len(u); s = u.sum(0)
    return (s @ s - k) / (k * (k - 1)) if k > 1 else np.nan


rows = []
for g in sorted(sel.agent_system.unique()):
    m = (sel.agent_system == g).values
    r = {"system": g, "all": bcm(S[m]), "excluding_4tree_fold": bcm(S[m & (fold != 4)])}
    for k in range(5):
        r[f"fold{k}_({iters[k]}trees)"] = bcm(S[m & (fold == k)])
    rows.append(r)
out = pd.DataFrame(rows)
out.to_csv("results/v7b_fold_decomposition.csv", index=False)
print(out.round(3).to_string(index=False))
