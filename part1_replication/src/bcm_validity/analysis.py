"""Post-hoc computations on stored runs: archival checks, E0 comparison, E (task
weighting), raw-feature baseline, paired task-cluster bootstrap, sensitivity summaries.

Usage: python -m bcm_validity.analysis [archival|e0|E|bootstrap|summary|all] [--rep ...]
"""
import argparse
import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import ROOT, load_config
from .bcm import bcm, bcm_from_units, bcm_weighted, between_task_bcm, unit_rows, within_task_bcm
from .experiments import (LLAMA, PAPER_GLOBAL, PAPER_TASKS, PAPER_WITHIN, PROPRIETARY, SHORT,
                          SYSTEMS, load_frozen, rank_agreement, run_path, separation)
from .features import FEATURES

TABLES = ROOT / "results/tables"
ARRAYS = ROOT / "results/arrays"
AUTHOR_FILES = ROOT / "external/colm-agent-eval/results/files"


def _w(df, name):
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / f"{name}.csv", index=False)
    print("wrote", name, flush=True)
    return df


# ------------------------------------------------------------------------ archival

def author_bootstrap(df_clustered, n_iterations=1000):
    """Exact re-implementation of the removed author bootstrap
    (git a35af8c^:experiments/exp1_inconsistency.py:9-62), using the O(nd)
    identity in place of the full cosine matrix (equal to 1e-10, see tests)."""
    np.random.seed(42)
    df = df_clustered.copy()
    if "subset_id" not in df.columns:
        df["subset_id"] = np.random.choice(["repo_A", "repo_B", "repo_C", "repo_D"], size=len(df))
    out = []
    for agent in df["agent_system"].unique():
        X = df.loc[df["agent_system"] == agent, FEATURES].to_numpy()
        n = len(X)
        U = X / np.linalg.norm(X, axis=1, keepdims=True)  # author code has no zero filter
        point = bcm_from_units(U)
        boots = []
        for _ in range(n_iterations):
            idx = np.random.choice(n, size=n, replace=True)
            boots.append(bcm_weighted(U, np.bincount(idx, minlength=n)))
        boots = np.array(boots)
        out.append({"system": agent, "n": n, "bcm": point, "bootstrap_mean": boots.mean(),
                    "ci_lower": np.percentile(boots, 2.5), "ci_upper": np.percentile(boots, 97.5)})
    return pd.DataFrame(out)


def stage_archival():
    shipped = pd.read_csv(AUTHOR_FILES / "shap_fingerprints.csv")
    feats = pd.read_csv(AUTHOR_FILES / "anomaly_analysis_summary.csv")
    proba = np.load(AUTHOR_FILES / "oof_proba.npy")
    empty = (feats["total_steps"] == 0).to_numpy()
    rows = []
    for s in SYSTEMS:
        m = (shipped["agent_system"] == s).to_numpy()
        X = shipped.loc[m, FEATURES].to_numpy()
        e = empty[m]
        u, _ = unit_rows(X)
        task = feats.loc[m, "instance_id"].to_numpy()
        wt, per = within_task_bcm(u, task, 3)
        rows.append({"system": s, "n": int(m.sum()), "n_empty_author_parse": int(e.sum()),
                     "success_rate": shipped.loc[m, "resolved"].mean(),
                     "bcm_global": bcm(X), "paper_global": PAPER_GLOBAL[s],
                     "bcm_nonempty_only": bcm(X[~e]), "bcm_empty_only": bcm(X[e]),
                     "n_distinct_empty_vectors": len(np.unique(X[e].round(10), axis=0)) if e.any() else 0,
                     "within_task": wt, "within_tasks_n": len(per), "paper_within": PAPER_WITHIN[s],
                     "paper_tasks": PAPER_TASKS[s]})
    t = pd.DataFrame(rows)
    t.attrs["auc"] = roc_auc_score(shipped["resolved"], proba)
    _w(t, "archival_shipped_artifacts")
    clustered = pd.read_csv(AUTHOR_FILES / "clustered_fingerprints.csv")
    boot = author_bootstrap(clustered)
    ref = pd.read_csv(AUTHOR_FILES / "agent_bcm_bootstrap_summary.csv").rename(columns={"agent": "system"})
    boot = boot.merge(ref[["system", "bootstrap_mean", "ci_lower", "ci_upper"]], on="system",
                      suffixes=("", "_shipped"))
    _w(boot, "archival_bootstrap_replication")
    json.dump({"shipped_pooled_auc": float(t.attrs["auc"]),
               "shipped_pooled_auc_nonempty": float(roc_auc_score(shipped["resolved"][~empty], proba[~empty]))},
              open(TABLES / "archival_auc.json", "w"), indent=2)


# ---------------------------------------------------------------------------- E0

def load_run(stage, rep, run):
    return dict(np.load(run_path(stage, rep, run), allow_pickle=True))


def raw_feature_baseline(df, X):
    rows = []
    mu, sd = X.mean(0), X.std(0)
    sd_safe = np.where(sd == 0, 1.0, sd)
    Zg = (X - mu) / sd_safe
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        Xs = X[m]
        sd_s = Xs.std(0)
        Zs = (Xs - Xs.mean(0)) / np.where(sd_s == 0, 1.0, sd_s)
        rows.append({"system": s, "zscore_cohort_ref": bcm(Zg[m]), "zscore_within_system": bcm(Zs),
                     "raw_unscaled": bcm(Xs), "n_zero_var_features_within_system": int((sd_s == 0).sum())})
    return pd.DataFrame(rows)


def stage_e0(rep):
    df, X, y, h = load_frozen(rep)
    out = load_run("E0", rep, "seed42")
    assert str(out["frozen_hash"]) == h
    phi = out["shap"]
    folds = json.loads(str(out["folds"]))
    rows = []
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        u, valid = unit_rows(phi[m])
        task = df.loc[m, "task_key"].to_numpy()[valid]
        wt, per = within_task_bcm(u, task, 3)
        empty = (df.loc[m, "n_actions"] == 0).to_numpy()
        rows.append({"rep": rep, "system": s, "n": int(m.sum()), "n_valid": int(valid.sum()),
                     "n_empty_parse": int(empty.sum()), "success_rate": y[m].mean(),
                     "bcm_global": bcm(phi[m]), "paper_global": PAPER_GLOBAL[s],
                     "delta_global": bcm(phi[m]) - PAPER_GLOBAL[s],
                     "bcm_global_nonempty": bcm(phi[m][~empty]),
                     "within_task": wt, "within_tasks_n": len(per), "paper_within": PAPER_WITHIN[s],
                     "delta_within": wt - PAPER_WITHIN[s], "paper_tasks": PAPER_TASKS[s]})
        pd.DataFrame({"system": s, "task_key": list(per), "bcm_task": list(per.values()),
                      "n_traj": [int((task == t).sum()) for t in per]}).to_csv(
            TABLES / f"E0_within_task_eligible_{rep}_{SHORT[s]}.csv", index=False)
    t = pd.DataFrame(rows)
    _w(t, f"E0_comparison_{rep}")
    raw = raw_feature_baseline(df, X)
    raw.insert(0, "rep", rep)
    _w(raw, f"E0_raw_feature_baseline_{rep}")
    pd.DataFrame(folds).to_csv(TABLES / f"E0_folds_{rep}.csv", index=False)
    perf = {"rep": rep, "auc_pooled": float(out["auc_pooled"]), "auc_mean_fold": float(out["auc_mean_fold"]),
            "frozen_hash": h, "n": int(len(y)), "n_pos": int(y.sum())}
    d_path = run_path("D", rep, "group_seed42")
    if d_path.exists():
        d = load_run("D", rep, "group_seed42")
        perf["auc_task_grouped_pooled"] = float(d["auc_pooled"])
        perf["auc_task_grouped_mean_fold"] = float(d["auc_mean_fold"])
    per_sys_auc = {}
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        per_sys_auc[s] = roc_auc_score(y[m], out["proba"][m]) if 0 < y[m].sum() < m.sum() else None
    perf["auc_within_system"] = per_sys_auc
    json.dump(perf, open(TABLES / f"E0_performance_{rep}.json", "w"), indent=2)
    # archival-style trajectory bootstrap on our own E0 (same author algorithm)
    tmp = df[["agent_system"]].copy()
    tmp[FEATURES] = phi
    _w(author_bootstrap(tmp), f"E0_archival_bootstrap_{rep}")
    archival_within_bootstrap(df, phi, rep)


def archival_within_bootstrap(df, phi, rep, iters=1000):
    """Paper §3.6: resample eligible task instances with replacement (no author code exists)."""
    rng = np.random.default_rng(42)
    rows = []
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        u, valid = unit_rows(phi[m])
        task = df.loc[m, "task_key"].to_numpy()[valid]
        _, per = within_task_bcm(u, task, 3)
        vals = np.array([v for v in per.values() if not np.isnan(v)])
        if len(vals) == 0:
            continue
        boots = [vals[rng.integers(0, len(vals), len(vals))].mean() for _ in range(iters)]
        rows.append({"system": s, "within_task": vals.mean(), "n_tasks": len(vals),
                     "ci_lower": np.percentile(boots, 2.5), "ci_upper": np.percentile(boots, 97.5)})
    _w(pd.DataFrame(rows), f"E0_within_task_bootstrap_{rep}")


# ----------------------------------------------------------------------------- E

def stable_order(ids):
    return np.argsort([hashlib.sha256(str(i).encode()).hexdigest() for i in ids], kind="stable")


def stage_E(rep):
    cfg = load_config()
    df, X, y, h = load_frozen(rep)
    phi = load_run("E0", rep, "seed42")["shap"]
    k = cfg["experiments"]["E_task_balanced_k"]
    iters = cfg["experiments"]["E_stratified_resample_iters"]
    rng = np.random.default_rng(cfg["bcm"]["cluster_bootstrap_seed"] + 1)
    rows, dist = [], []
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        sub = df[m].reset_index(drop=True)
        u, valid = unit_rows(phi[m])
        sub = sub[valid].reset_index(drop=True)
        task = sub["task_key"].to_numpy()
        counts = pd.Series(task).value_counts()
        elig = set(counts[counts >= 3].index)
        em = np.isin(task, list(elig))
        wt, _ = within_task_bcm(u, task, 3)
        # task-balanced: exactly k runs per eligible task, chosen by sha256(source_row_id)
        bal_idx = []
        for t in sorted(elig):
            idx = np.flatnonzero(task == t)
            bal_idx += list(idx[stable_order(sub.loc[idx, "source_row_id"])][:k])
        bal_idx = np.array(bal_idx, dtype=int)
        small = ~em
        # stratified-by-task resampling: one trajectory per task, all tasks equal weight
        groups = [np.flatnonzero(task == t) for t in counts.index]
        one_per_task = []
        for _ in range(iters):
            pick = np.array([g[rng.integers(len(g))] for g in groups])
            one_per_task.append(bcm_from_units(u[pick]))
        one_per_task = np.array(one_per_task)
        dist.append(pd.DataFrame({"system": s, "iter": np.arange(iters), "bcm_one_per_task": one_per_task}))
        rows.append({
            "rep": rep, "system": s, "n_valid": len(u), "n_tasks": len(counts),
            "n_tasks_eligible_ge3": len(elig), "n_traj_in_eligible": int(em.sum()),
            "global_all": bcm_from_units(u),
            "global_eligible_cohort": bcm_from_units(u[em]),
            "between_task_eligible_cohort": between_task_bcm(u[em], task[em]),
            "within_task_macro": wt,
            "between_task_all": between_task_bcm(u, task),
            "task_balanced_k3": bcm_from_units(u[bal_idx]) if len(bal_idx) else np.nan,
            "n_task_balanced": len(bal_idx),
            "stratum_tasks_1or2_bcm": bcm_from_units(u[small]), "stratum_tasks_1or2_n": int(small.sum()),
            "stratum_tasks_1or2_ntasks": int((counts < 3).sum()),
            "one_per_task_mean": float(np.nanmean(one_per_task)),
            "one_per_task_ci_lower": float(np.nanpercentile(one_per_task, 2.5)),
            "one_per_task_ci_upper": float(np.nanpercentile(one_per_task, 97.5)),
            "max_runs_per_task": int(counts.max()), "median_runs_per_task": float(counts.median()),
        })
    _w(pd.DataFrame(rows), f"E_task_weighting_{rep}")
    pd.concat(dist).to_parquet(TABLES / f"E_one_per_task_dist_{rep}.parquet", index=False)


# ---------------------------------------------------------------------- bootstrap

def all_runs(rep):
    runs = []
    for stage in ["E0", "A", "B", "C", "D"]:
        d = ARRAYS / stage / rep
        if d.exists():
            for p in sorted(d.glob("*.npz")):
                if "_fold" not in p.stem:
                    runs.append((stage, p.stem))
    return runs


def cluster_weights(df, B, seed):
    """Per system: B x n_rows weights from resampling the system's task clusters."""
    rng = np.random.default_rng(seed)
    W = {}
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        codes, uniq = pd.factorize(df.loc[m, "task_key"])
        T = len(uniq)
        C = np.stack([np.bincount(rng.integers(0, T, T), minlength=T) for _ in range(B)])
        W[s] = C[:, codes].astype(np.float64)
    return W


def nested_weights(df, B, seed):
    """Per system: resample repositories, then tasks within each sampled repository."""
    rng = np.random.default_rng(seed)
    W = {}
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        sub = df[m]
        tcodes, tasks = pd.factorize(sub["task_key"])
        task_repo = sub.groupby("task_key")["repo_key"].first().reindex(tasks).to_numpy()
        rcodes, repos = pd.factorize(task_repo)
        by_repo = [np.flatnonzero(rcodes == r) for r in range(len(repos))]
        C = np.zeros((B, len(tasks)))
        for b in range(B):
            for r in rng.integers(0, len(repos), len(repos)):
                g = by_repo[r]
                np.add.at(C[b], g[rng.integers(0, len(g), len(g))], 1)
        W[s] = C[:, tcodes]
    return W


def boot_bcm(W, U, valid):
    Wv = W * valid[None, :]
    S = Wv @ U
    N = Wv.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(N >= 2, ((S * S).sum(1) - N) / (N * (N - 1)), np.nan)


def stage_bootstrap(rep):
    cfg = load_config()
    df, X, y, h = load_frozen(rep)
    B = cfg["bcm"]["cluster_bootstrap_iters"]
    W = cluster_weights(df, B, cfg["bcm"]["cluster_bootstrap_seed"])
    runs = all_runs(rep)
    out = np.full((len(runs), B, len(SYSTEMS)), np.nan)
    point = np.full((len(runs), len(SYSTEMS)), np.nan)
    for r, (stage, run) in enumerate(runs):
        z = load_run(stage, rep, run)
        assert str(z["frozen_hash"]) == h, f"{stage}/{run} hash mismatch"
        for j, s in enumerate(SYSTEMS):
            m = (df["agent_system"] == s).to_numpy()
            phi = z["shap"][m]
            norms = np.linalg.norm(phi, axis=1)
            valid = (norms > 1e-9).astype(float)
            U = np.where(valid[:, None] > 0, phi / np.where(norms == 0, 1, norms)[:, None], 0.0)
            out[r, :, j] = boot_bcm(W[s], U, valid)
            point[r, j] = bcm(phi)
    np.savez_compressed(ARRAYS / f"bootstrap_cluster_{rep}.npz", boot=out, point=point,
                        runs=np.array([f"{a}/{b}" for a, b in runs]), systems=np.array(SYSTEMS),
                        frozen_hash=h)
    base_i = [f"{a}/{b}" for a, b in runs].index("E0/seed42")
    rows = []
    for r, (stage, run) in enumerate(runs):
        for j, s in enumerate(SYSTEMS):
            d = out[r, :, j] - out[base_i, :, j]
            rows.append({"rep": rep, "stage": stage, "run": run, "system": s, "bcm": point[r, j],
                         "ci_lower": np.nanpercentile(out[r, :, j], 2.5),
                         "ci_upper": np.nanpercentile(out[r, :, j], 97.5),
                         "diff_vs_baseline": point[r, j] - point[base_i, j],
                         "diff_ci_lower": np.nanpercentile(d, 2.5), "diff_ci_upper": np.nanpercentile(d, 97.5)})
        sep = np.nanmin(out[r, :, :3], axis=1) - np.nanmax(out[r, :, 3:], axis=1)
        rows.append({"rep": rep, "stage": stage, "run": run, "system": "SEPARATION_min_prop_minus_max_llama",
                     "bcm": separation(dict(zip(SYSTEMS, point[r]))),
                     "ci_lower": np.nanpercentile(sep, 2.5), "ci_upper": np.nanpercentile(sep, 97.5)})
    _w(pd.DataFrame(rows), f"bootstrap_cluster_summary_{rep}")
    # pairwise P(system i > system j) at baseline under the task-cluster bootstrap
    b0 = out[base_i]
    P = np.array([[np.nanmean(b0[:, i] > b0[:, j]) for j in range(6)] for i in range(6)])
    _w(pd.DataFrame(P, index=SYSTEMS, columns=SYSTEMS).reset_index(names="system"),
       f"bootstrap_baseline_pairwise_prob_{rep}")
    # nested repo -> task bootstrap for the baseline only
    Wn = nested_weights(df, B, cfg["bcm"]["cluster_bootstrap_seed"] + 7)
    z = load_run("E0", rep, "seed42")
    nrows = []
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        phi = z["shap"][m]
        norms = np.linalg.norm(phi, axis=1)
        valid = (norms > 1e-9).astype(float)
        U = np.where(valid[:, None] > 0, phi / np.where(norms == 0, 1, norms)[:, None], 0.0)
        bb = boot_bcm(Wn[s], U, valid)
        nrows.append({"system": s, "bcm": bcm(phi), "n_repos": df.loc[m, "repo_key"].nunique(),
                      "ci_lower": np.nanpercentile(bb, 2.5), "ci_upper": np.nanpercentile(bb, 97.5)})
    _w(pd.DataFrame(nrows), f"bootstrap_nested_repo_task_{rep}")


# ------------------------------------------------------------------------ summary

def stage_summary(rep):
    """Aggregate A/B/C/D run tables into M1-M3 summaries."""
    base = pd.read_csv(TABLES / f"runs_E0_{rep}.csv")
    bv = dict(zip(base["system"], base["bcm"]))
    out = []
    for stage in ["A", "B", "C", "D"]:
        p = TABLES / f"runs_{stage}_{rep}.csv"
        if not p.exists():
            continue
        t = pd.read_csv(p)
        for run, g in t.groupby("run", sort=False):
            v = dict(zip(g["system"], g["bcm"]))
            ra = rank_agreement(bv, v)
            out.append({"rep": rep, "stage": stage, "run": run, "auc_pooled": g["auc_pooled"].iloc[0],
                        "auc_mean_fold": g["auc_mean_fold"].iloc[0],
                        "separation": separation(v), **ra,
                        "max_abs_change": max(abs(v[s] - bv[s]) for s in SYSTEMS),
                        **{f"bcm_{SHORT[s]}": v[s] for s in SYSTEMS},
                        **{k: g[k].iloc[0] for k in ("variant", "null_type", "fold_seed") if k in g}})
    s = pd.DataFrame(out)
    _w(s, f"sensitivity_runs_summary_{rep}")
    if (TABLES / f"runs_A_{rep}.csv").exists():
        a = pd.read_csv(TABLES / f"runs_A_{rep}.csv")
        q = a.groupby("system")["bcm"].agg(
            ["min", "max", "median", "std", lambda x: x.quantile(.75) - x.quantile(.25)]).reset_index()
        q.columns = ["system", "min", "max", "median", "sd", "iqr"]
        q["range"] = q["max"] - q["min"]
        _w(q, f"A_seed_stability_{rep}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--rep", default="author")
    a = ap.parse_args()
    reps = ["author", "role_aware"] if a.rep == "both" else [a.rep]
    if a.stage in ("archival", "all"):
        stage_archival()
    for rep in reps:
        if a.stage in ("e0", "all"):
            stage_e0(rep)
        if a.stage in ("E", "all"):
            stage_E(rep)
        if a.stage in ("bootstrap", "all"):
            stage_bootstrap(rep)
        if a.stage in ("summary", "all"):
            stage_summary(rep)


if __name__ == "__main__":
    main()
