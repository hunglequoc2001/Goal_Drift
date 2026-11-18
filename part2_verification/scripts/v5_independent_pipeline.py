"""V5/V8: independent re-implementation of predictor -> OOF attribution -> BCM, with label nulls.

Independent of bcm_validity.model / experiments (only the validated feature tables are reused).

Predictors
  paper_code     released script: LGBM 200 trees, lr .05, depth 6, 31 leaves; tree-path TreeSHAP
  paper_actual   historical config @48fcfd0 that exactly regenerates the shipped artifacts
                 (V7): early stopping on the VALIDATION fold, scale_pos_weight; tree-path TreeSHAP
  logistic       train-fold standardised L2 logistic; exact linear attribution w*(z - mean_train z)
Label schemes
  real | perm_system (within agent_system) | perm_system_repo (within agent_system x repo,
  strata with >=2 rows and both classes are shuffled; other rows keep labels) | perm_global
Every fold asserts additivity |sum(phi) + base - margin| < 1e-6 on every validation row.

Usage: python v5_independent_pipeline.py <out_dir> <rep> <predictor> <scheme> <seed0> <seed1>
       runs seeds in [seed0, seed1); scheme=real ignores seeds and runs once.
"""
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/gpfs_common/share02/gaise/qle3/project_791/bcm-validity")
FEATS = ["total_steps", "mean_action_length", "max_action_length", "file_search_count",
         "file_view_count", "file_edit_count", "test_execution_count", "action_entropy",
         "consecutive_repetition_max", "unique_action_ratio", "error_flag_count", "step_velocity"]
PAPER_CODE = dict(n_estimators=200, learning_rate=0.05, max_depth=6, num_leaves=31,
                  random_state=42, n_jobs=8, verbose=-1)
PAPER_ACTUAL = dict(n_estimators=1500, learning_rate=0.005, num_leaves=15, max_depth=4,
                    subsample=0.80, colsample_bytree=0.80, min_child_samples=30, reg_alpha=2.0,
                    reg_lambda=10.0, objective="binary", metric="auc", random_state=42,
                    n_jobs=8, verbose=-1)
TOL = 1e-6


def bcm(phi):
    n = np.linalg.norm(phi, axis=1)
    u = phi[n > 1e-9] / n[n > 1e-9, None]
    k = len(u)
    s = u.sum(0)
    return float((s @ s - k) / (k * (k - 1))) if k > 1 else np.nan


def fit_fold(pred, Xtr, ytr, Xva, yva):
    if pred == "logistic":
        mu, sd = Xtr.mean(0), Xtr.std(0)
        sd[sd == 0] = 1.0
        Ztr, Zva = (Xtr - mu) / sd, (Xva - mu) / sd
        clf = LogisticRegression(C=1.0, max_iter=5000).fit(Ztr, ytr)
        w = clf.coef_[0]
        phi = (Zva - Ztr.mean(0)) * w
        base = clf.intercept_[0] + Ztr.mean(0) @ w
        margin = clf.decision_function(Zva)
        return phi, base, margin, 1 / (1 + np.exp(-margin)), -1
    p = dict(PAPER_CODE if pred == "paper_code" else PAPER_ACTUAL)
    kw = {}
    if pred == "paper_actual":
        p["scale_pos_weight"] = (ytr == 0).sum() / (ytr == 1).sum()
        kw = dict(eval_set=[(Xva, yva)], callbacks=[lgb.early_stopping(50, verbose=False)])
    clf = lgb.LGBMClassifier(**p).fit(Xtr, ytr, **kw)
    ex = shap.TreeExplainer(clf)
    phi = ex.shap_values(Xva)
    if isinstance(phi, list):
        phi = phi[1]
    base = float(np.atleast_1d(ex.expected_value)[-1])
    margin = clf.predict(Xva, raw_score=True)
    return phi, base, margin, clf.predict_proba(Xva)[:, 1], int(clf.best_iteration_ or p["n_estimators"])


def permute(y, strata, rng):
    y = y.copy()
    for s in pd.unique(strata):
        idx = np.flatnonzero(strata == s)
        if len(idx) > 1:
            y[idx] = rng.permutation(y[idx])
    return y


def run_once(X, y, df, pred, scheme, seed):
    n = len(y)
    if scheme == "perm_system":
        y = permute(y, df.agent_system.values, np.random.default_rng(seed))
    elif scheme == "perm_system_repo":
        y = permute(y, (df.agent_system + "|" + df.repo_key).values, np.random.default_rng(seed))
    elif scheme == "perm_global":
        y = np.random.default_rng(seed).permutation(y)
    phi = np.zeros((n, X.shape[1]))
    proba = np.zeros(n)
    fold_info = []
    for k, (tr, va) in enumerate(StratifiedKFold(5, shuffle=True, random_state=42).split(X, y)):
        f_phi, base, margin, p, it = fit_fold(pred, X[tr], y[tr], X[va], y[va])
        err = float(np.abs(f_phi.sum(1) + base - margin).max())
        assert err < TOL, f"additivity {err}"
        phi[va], proba[va] = f_phi, p
        fold_info.append({"fold": k, "iters": it, "add_err": err})
    sysv = df.agent_system.values
    nonempty = df.total_steps.values > 0
    r = {"predictor": pred, "scheme": scheme, "seed": seed,
         "auc_pooled": roc_auc_score(y, proba),
         "max_add_err": max(f["add_err"] for f in fold_info),
         "iters": [f["iters"] for f in fold_info]}
    for g in sorted(set(sysv)):
        m = sysv == g
        r[f"bcm|{g}"] = bcm(phi[m])
        r[f"bcm_nonempty|{g}"] = bcm(phi[m & nonempty])
        r[f"auc_within|{g}"] = roc_auc_score(y[m], proba[m]) if 0 < y[m].sum() < m.sum() else np.nan
    return r, phi


def main(out, rep, pred, scheme, s0, s1):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(ROOT / f"results/tables/features_{rep}.parquet")
    sel = pd.read_csv(ROOT / "data/manifests/cohort_author_selection.csv")
    assert (sel.instance_id.values == df.instance_id.values).all()
    df["repo_key"] = sel.repo_key.values
    X, y = df[FEATS].to_numpy(float), df.resolved.to_numpy(int)
    seeds = [0] if scheme == "real" else range(int(s0), int(s1))
    rows = []
    for s in seeds:
        t = time.time()
        r, phi = run_once(X, y, df, pred, scheme, s)
        r["rep"], r["seconds"] = rep, round(time.time() - t, 1)
        rows.append(r)
        if scheme == "real":
            np.save(out / f"phi_{rep}_{pred}.npy", phi)
        print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
    pd.DataFrame(rows).to_csv(out / f"v5_{rep}_{pred}_{scheme}_{s0}_{s1}.csv", index=False)


if __name__ == "__main__":
    main(*sys.argv[1:7])
