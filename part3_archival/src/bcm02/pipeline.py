"""BCM pipeline for Exp02: matched-task cohort -> task-grouped OOF success predictor -> attributions -> BCM.

Predictors (attribution in parentheses; all on the log-odds/margin scale, fit on training folds only):
  lgbm_paper   released BCM script hyperparameters (tree-path TreeSHAP; additivity asserted)
  lgbm_tuned   grid chosen by inner task-grouped 3-fold CV on the training fold only (tree-path TreeSHAP)
  logistic     train-fold standardised L2 logistic (exact linear attribution w*(z - mean_train z))
  raw          no predictor: train-fold z-scored features (the paper's raw-feature baseline, train-referenced)
CV schemes: grouped5 (StratifiedGroupKFold by task, seed r), loro (leave one repository out).
Label schemes: real | perm_model | perm_model_repo | perm_global (seeded).

Usage (one job = one config list line): python -m bcm02.pipeline <cohort> <rep> <predictor> <cv> <scheme> <seed0> <seed1> <out_dir>
"""
import itertools
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
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[2]
BCM12 = ["total_steps", "mean_action_length", "max_action_length", "file_search_count", "file_view_count",
         "file_edit_count", "test_execution_count", "action_entropy", "consecutive_repetition_max",
         "unique_action_ratio", "error_flag_count", "step_velocity"]
SEM = ["r3_frac_search", "r3_frac_view", "r3_frac_edit", "r3_frac_test", "r3_frac_run", "r3_frac_vcs",
       "r3_frac_install", "r3_frac_submit", "r3_frac_other", "r3_n_steps", "r3_first_edit_pos",
       "r3_first_test_pos", "r3_first_run_pos", "r3_n_category_switches"]
PAPER = dict(n_estimators=200, learning_rate=0.05, max_depth=6, num_leaves=31, random_state=42, verbose=-1)
GRID = [dict(PAPER, num_leaves=nl, max_depth=md, n_estimators=ne, learning_rate=lr, min_child_samples=mc)
        for nl, md, ne, lr, mc in itertools.product([7, 31], [3, 6], [100, 300], [0.03, 0.1], [20, 50])]
TOL = 1e-6


def feature_cols(rep):
    return SEM if rep == "r3" else [f"{rep}_{f}" for f in BCM12]


COHORTS = {  # pre-registered 2026-10-26 before any Exp02 BCM was computed (RESEARCH_DECISIONS P2.8)
    "primary5": ["gpt-5-250-turns-10132025", "claude-45sonnet-10132025", "claude-45haiku-10222025",
                 "glm-4p5-10222025", "gemini-2-5-pro-preview-250-turns-debug-oct22"],
    "primary6": ["gpt-5-250-turns-10132025", "claude-45sonnet-10132025", "claude-45haiku-10222025",
                 "glm-4p5-10222025", "gemini-2-5-pro-preview-250-turns-debug-oct22", "claude-4sonnet-10132025"],
    "paper50": ["gpt-5-high-paper", "gptoss-paper", "kimi-paper"],
    "paper100": ["claude-opus-4-1-paper", "claude-sonnet-4-paper", "gemini-2-5-pro-preview-paper", "gpt-4o-paper"],
}


def load_cohort(cohort, include_disputed=False):
    if cohort.endswith("_cfgclean"):   # sensitivity: drop tasks where any cohort member ran with a deviant config
        T = load_cohort(cohort[:-len("_cfgclean")], include_disputed)
        bad = set(pd.read_csv(ROOT / "data/manifests/config_deviant_tasks.csv").instance_id)
        return T[~T.instance_id.isin(bad)].reset_index(drop=True)
    """Matched-task cohort: v1 tasks with a trajectory for every run in the cohort, minus the 14 tasks
    whose official label disagrees with the official rule on the archived outputs (all models)."""
    T = pd.read_parquet(ROOT / "data/interim/trajectories.parquet")
    runs = COHORTS[cohort]
    T = T[T.run.isin(runs) & T.in_v1].copy()
    cnt = T.groupby("instance_id").run.nunique()
    keep = set(cnt[cnt == len(runs)].index)
    if not include_disputed:
        keep -= set(pd.read_csv(ROOT / "data/manifests/disputed_instances.csv").instance_id)
    T = T[T.instance_id.isin(keep)].sort_values(["instance_id", "run"]).reset_index(drop=True)
    T["model_label"] = T["cfg.agent.model.name"].str.strip('"').str.split("/").str[-1]
    return T


def bcm(phi):
    n = np.linalg.norm(phi, axis=1)
    u = phi[n > 1e-9] / n[n > 1e-9, None]
    k = len(u)
    s = u.sum(0)
    return float((s @ s - k) / (k * (k - 1))) if k > 1 else np.nan


def splits(T, y, cv, seed):
    g = T.instance_id.values
    if cv == "grouped5":
        return list(StratifiedGroupKFold(5, shuffle=True, random_state=seed).split(np.zeros(len(y)), y, g))
    if cv == "loro":
        return [(np.flatnonzero(T.repo.values != r), np.flatnonzero(T.repo.values == r)) for r in sorted(T.repo.unique())]
    raise ValueError(cv)


def tree_attr(model, X):
    ex = shap.TreeExplainer(model)
    phi = ex.shap_values(X)
    if isinstance(phi, list):
        phi = phi[1]
    base = float(np.atleast_1d(ex.expected_value)[-1])
    margin = model.predict(X, raw_score=True)
    err = float(np.abs(np.asarray(phi).sum(1) + base - margin).max())
    assert err < TOL, f"TreeSHAP additivity {err}"
    return np.asarray(phi), margin, err


def fit_predict(pred, Xtr, ytr, Xva, gtr, n_jobs):
    if pred in ("logistic", "raw"):
        mu, sd = Xtr.mean(0), Xtr.std(0)
        sd[sd == 0] = 1.0
        Ztr, Zva = (Xtr - mu) / sd, (Xva - mu) / sd
        if pred == "raw":
            return Zva, np.full(len(Xva), np.nan), 0.0, None
        clf = LogisticRegression(C=1.0, max_iter=5000).fit(Ztr, ytr)
        w = clf.coef_[0]
        phi = (Zva - Ztr.mean(0)) * w
        margin = clf.decision_function(Zva)
        err = float(np.abs(phi.sum(1) + clf.intercept_[0] + Ztr.mean(0) @ w - margin).max())
        assert err < TOL
        return phi, margin, err, None
    params = dict(PAPER, n_jobs=n_jobs)
    chosen = None
    if pred == "lgbm_tuned":
        inner = list(StratifiedGroupKFold(3, shuffle=True, random_state=7).split(Xtr, ytr, gtr))
        best = -1
        for i, p in enumerate(GRID):
            aucs = []
            for itr, iva in inner:
                m = lgb.LGBMClassifier(**dict(p, n_jobs=n_jobs)).fit(Xtr[itr], ytr[itr])
                aucs.append(roc_auc_score(ytr[iva], m.predict_proba(Xtr[iva])[:, 1]))
            if np.mean(aucs) > best:
                best, chosen = np.mean(aucs), i
        params = dict(GRID[chosen], n_jobs=n_jobs)
    m = lgb.LGBMClassifier(**params).fit(Xtr, ytr)
    phi, margin, err = tree_attr(m, Xva)
    return phi, margin, err, chosen


def permute(y, strata, rng):
    y = y.copy()
    for s in pd.unique(strata):
        idx = np.flatnonzero(strata == s)
        if len(idx) > 1:
            y[idx] = rng.permutation(y[idx])
    return y


def run_once(T, rep, pred, cv, scheme, seed, n_jobs=8):
    X = T[feature_cols(rep)].to_numpy(float)
    y = T.resolved.to_numpy(int)
    if scheme == "perm_model":
        y = permute(y, T.run.values, np.random.default_rng(seed))
    elif scheme == "perm_model_repo":
        y = permute(y, (T.run + "|" + T.repo).values, np.random.default_rng(seed))
    elif scheme == "perm_global":
        y = np.random.default_rng(seed).permutation(y)
    cv_seed = seed if scheme == "real" else 0
    phi = np.full(X.shape, np.nan)
    margin = np.full(len(y), np.nan)
    errs, chosen = [], []
    for tr, va in splits(T, y, cv, cv_seed):
        assert not set(T.instance_id.values[tr]) & set(T.instance_id.values[va])
        p, m, e, c = fit_predict(pred, X[tr], y[tr], X[va], T.instance_id.values[tr], n_jobs)
        phi[va], margin[va] = p, m
        errs.append(e)
        chosen.append(c)
    assert not np.isnan(phi).any()
    r = dict(rep=rep, predictor=pred, cv=cv, scheme=scheme, seed=seed, n=len(y),
             auc_pooled=roc_auc_score(y, margin) if pred != "raw" else np.nan,
             max_add_err=max(errs), tuned_choice=json.dumps(chosen))
    for run, g in T.groupby("run").groups.items():
        g = np.asarray(g)
        r[f"bcm|{run}"] = bcm(phi[g])
        r[f"auc_within|{run}"] = (roc_auc_score(y[g], margin[g]) if pred != "raw" and 0 < y[g].sum() < len(g) else np.nan)
        r[f"zero_steps|{run}"] = int((T[f"{rep}_total_steps" if rep != "r3" else "r3_n_steps"].values[g] == 0).sum())
    return r, phi, margin, y


COHORTS["primary5_cfgclean"] = COHORTS["primary5"]


def main(cohort, rep, pred, cv, scheme, s0, s1, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    T = load_cohort(cohort)
    rows = []
    for seed in range(int(s0), int(s1)):
        t = time.time()
        r, phi, margin, y = run_once(T, rep, pred, cv, scheme, seed)
        r["cohort"], r["seconds"] = cohort, round(time.time() - t, 1)
        rows.append(r)
        if scheme == "real":
            np.savez_compressed(out / f"oof_{cohort}_{rep}_{pred}_{cv}_s{seed}.npz", phi=phi, margin=margin, y=y,
                                instance_id=T.instance_id.values, run=T.run.values)
        print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
    pd.DataFrame(rows).to_csv(out / f"runs_{cohort}_{rep}_{pred}_{cv}_{scheme}_{s0}_{s1}.csv", index=False)


if __name__ == "__main__":
    main(*sys.argv[1:9])
