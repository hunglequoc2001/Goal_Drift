"""V6c: corrected Exp01 stage G. Exact interventional Shapley values (all 2^12 coalitions) for every
row, using the SAME seed-42 folds, paper_code LightGBM model and the SAME 128-row backgrounds that
Exp01 stored (bcm-validity/results/arrays/G/<rep>/bg<seed>_fold<k>.npz). Validated against
shap.explainers.Exact in V6b (max dev 1.7e-14).

Usage: python v6c_exact_interventional_full.py <out_dir> <rep> <bg_seed> <fold>
"""
import sys
import time
from math import factorial
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/gpfs_common/share02/gaise/qle3/project_791/bcm-validity")
FEATS = ["total_steps", "mean_action_length", "max_action_length", "file_search_count",
         "file_view_count", "file_edit_count", "test_execution_count", "action_entropy",
         "consecutive_repetition_max", "unique_action_ratio", "error_flag_count", "step_velocity"]
P = dict(n_estimators=200, learning_rate=0.05, max_depth=6, num_leaves=31, random_state=42,
         n_jobs=16, verbose=-1)


def shapley_from_values(v, d):
    """v: (n, 2^d) coalition values indexed by bitmask -> (n, d) exact Shapley values."""
    masks = np.arange(2 ** d)
    size = np.array([bin(m).count("1") for m in masks])
    w = np.array([factorial(k) * factorial(d - k - 1) / factorial(d) if k < d else 0.0 for k in size])
    phi = np.zeros((v.shape[0], d))
    for j in range(d):
        without = masks[(masks >> j) & 1 == 0]
        phi[:, j] = (v[:, without | (1 << j)] - v[:, without]) @ w[without]
    return phi


def main(out, rep, bseed, fold):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    fold = int(fold)
    df = pd.read_parquet(ROOT / f"results/tables/features_{rep}.parquet")
    X, y = df[FEATS].to_numpy(float), df.resolved.to_numpy(int)
    tr, va = list(StratifiedKFold(5, shuffle=True, random_state=42).split(X, y))[fold]
    g = np.load(ROOT / f"results/arrays/G/{rep}/bg{bseed}_fold{fold}.npz")
    assert np.array_equal(np.sort(g["rows"]), np.sort(va)), "Exp01 validation rows differ"
    bg_idx = g["bg"]
    assert not set(bg_idx) & set(va)
    booster = lgb.LGBMClassifier(**P).fit(X[tr], y[tr]).booster_
    bg = X[bg_idx]
    d, B = X.shape[1], len(bg)
    masks = np.arange(2 ** d)
    bits = ((masks[:, None] >> np.arange(d)) & 1).astype(bool)        # (2^d, d)
    rows = g["rows"]
    v = np.empty((len(rows), 2 ** d))
    t = time.time()
    chunk = 64
    for c0 in range(0, len(rows), chunk):
        xs = X[rows[c0:c0 + chunk]]                                    # (c, d)
        c = len(xs)
        for m in masks:
            Z = np.repeat(bg[None], c, axis=0)                         # (c, B, d)
            Z[:, :, bits[m]] = xs[:, None, bits[m]]
            v[c0:c0 + c, m] = booster.predict(Z.reshape(-1, d), raw_score=True).reshape(c, B).mean(1)
        print(f"rows {c0 + c}/{len(rows)} {time.time() - t:.0f}s", flush=True)
    phi = shapley_from_values(v, d)
    margin = booster.predict(X[rows], raw_score=True)
    base = booster.predict(bg, raw_score=True).mean()
    err = float(np.abs(phi.sum(1) + base - margin).max())
    assert err < 1e-8, err
    np.savez_compressed(out / f"exact_{rep}_bg{bseed}_fold{fold}.npz", rows=rows, phi=phi, base=base,
                        add_err=err, shap_tree_interventional_phi=g["phi"])
    print("done additivity", err, "maxdev vs Exp01 tree-interventional", float(np.abs(phi - g["phi"]).max()))


if __name__ == "__main__":
    main(*sys.argv[1:5])
