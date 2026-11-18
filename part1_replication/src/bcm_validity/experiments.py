"""E0 baseline and sensitivity experiments A-D, G on frozen X/y.

Usage:  python -m bcm_validity.experiments <stage> [--rep author|role_aware]
Stages: e0, A, B, C, D, G_pilot, G.  Each run is checkpointed to
results/arrays/<stage>/<rep>/<run>.npz and skipped when present with a matching hash.
"""
import argparse
import json
import time

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from . import ROOT, load_config
from .bcm import bcm, between_task_bcm, unit_rows, within_task_bcm
from .features import FEATURES
from .model import cross_validate, explain, frozen_hash, make_lgbm

SYSTEMS = [
    "claude-3-5-sonnet-20241022", "claude-3-7-sonnet-20250219", "gpt-4o-2024-08-06",
    "swe-agent-llama-405b", "swe-agent-llama-70b", "swe-agent-llama-8b",
]
SHORT = dict(zip(SYSTEMS, ["Claude-3.5", "Claude-3.7", "GPT-4o", "Llama-405B", "Llama-70B", "Llama-8B"]))
PROPRIETARY = SYSTEMS[:3]
LLAMA = SYSTEMS[3:]
PAPER_GLOBAL = dict(zip(SYSTEMS, [0.833, 0.766, 0.814, 0.071, 0.065, 0.086]))
PAPER_WITHIN = dict(zip(SYSTEMS, [0.807, 0.564, 0.897, 0.348, 0.305, 0.319]))
PAPER_TASKS = dict(zip(SYSTEMS, [60, 60, 4, 100, 132, 261]))


# ----------------------------------------------------------------------------- data

def load_frozen(rep):
    cfg = load_config()
    df = pd.read_parquet(ROOT / cfg["paths"]["tables"] / f"features_{rep}.parquet")
    df = df.sort_values("author_row").reset_index(drop=True)
    df["task_key"] = df["source"] + ":" + df["instance_id"]
    meta = pd.read_csv(ROOT / "data/manifests/cohort_author_selection.csv", usecols=["author_row", "repo_key"])
    df = df.merge(meta, on="author_row", how="left", validate="one_to_one")
    assert df["repo_key"].notna().all() and (df["author_row"].to_numpy() == np.arange(len(df))).all()
    X = df[FEATURES].to_numpy(dtype=np.float64)
    y = df["resolved"].to_numpy(dtype=np.int64)
    return df, X, y, frozen_hash(X, y)


def stratified_splits(y, seed, n_splits=5):
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return list(skf.split(np.zeros(len(y)), y))


def grouped_splits(y, groups, seed, n_splits=5):
    sgk = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return list(sgk.split(np.zeros(len(y)), y, groups))


# -------------------------------------------------------------------------- metrics

def per_system(phi, df, y_used=None):
    rows = []
    for s in SYSTEMS:
        m = (df["agent_system"] == s).to_numpy()
        u, valid = unit_rows(phi[m])
        rows.append({"system": s, "n": int(m.sum()), "n_valid": int(valid.sum()),
                     "bcm": bcm(phi[m]),
                     "success_rate": float((y_used if y_used is not None else df["resolved"].to_numpy())[m].mean())})
    return rows


def ranking(values):
    """System order by descending BCM (ties broken by SYSTEMS order)."""
    return sorted(SYSTEMS, key=lambda s: (-values[s], SYSTEMS.index(s)))


def rank_agreement(base, other):
    from scipy.stats import kendalltau, spearmanr
    b = np.array([base[s] for s in SYSTEMS])
    o = np.array([other[s] for s in SYSTEMS])
    rev = sum(np.sign(b[i] - b[j]) != np.sign(o[i] - o[j])
              for i in range(6) for j in range(i + 1, 6))
    return {"kendall_tau": kendalltau(b, o).statistic, "spearman_rho": spearmanr(b, o).statistic,
            "pairs_reversed": int(rev), "frac_pairs_reversed": rev / 15}


def separation(values):
    return min(values[s] for s in PROPRIETARY) - max(values[s] for s in LLAMA)


# ------------------------------------------------------------------- checkpointing

def run_path(stage, rep, run):
    p = ROOT / "results/arrays" / stage / rep
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{run}.npz"


def checkpointed_cv(stage, rep, run, X, y_fit, splits, params, h, n_jobs, groups=None, meta=None):
    path = run_path(stage, rep, run)
    if path.exists():
        z = np.load(path, allow_pickle=True)
        if str(z["frozen_hash"]) == h:
            return {k: z[k] for k in z.files}, True
        raise SystemExit(f"{path}: frozen hash mismatch — refusing to mix data versions")
    t0 = time.time()
    res = cross_validate(X, y_fit, splits, params, n_jobs=n_jobs, groups_check=groups)
    out = {"shap": res["shap"], "proba": res["proba"], "margin": res["margin"], "fold": res["fold"],
           "y_fit": y_fit, "frozen_hash": h, "auc_pooled": res["auc_pooled"],
           "auc_mean_fold": res["auc_mean_fold"], "folds": json.dumps(res["folds"]),
           "params": json.dumps(params), "meta": json.dumps(meta or {}),
           "seconds": time.time() - t0}
    np.savez_compressed(path, **out)
    return out, False


def record(rows, stage, rep, run, out, df, h, extra=None):
    y_fit = out["y_fit"]
    for r in per_system(out["shap"], df):
        rows.append({"stage": stage, "rep": rep, "run": run, **(extra or {}),
                     "auc_pooled": float(out["auc_pooled"]),
                     "auc_mean_fold": float(out["auc_mean_fold"]),
                     "frozen_hash": h, **r,
                     "fit_label_success_rate": float(y_fit[(df["agent_system"] == r["system"]).to_numpy()].mean())})


def save_rows(rows, stage, rep):
    p = ROOT / "results/tables" / f"runs_{stage}_{rep}.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    print("wrote", p, flush=True)


# --------------------------------------------------------------------------- stages

def stage_e0(rep, cfg, n_jobs):
    df, X, y, h = load_frozen(rep)
    params = cfg["baseline"]["lgbm"]
    out, cached = checkpointed_cv("E0", rep, "seed42", X, y, stratified_splits(y, 42), params, h, n_jobs)
    rows = []
    record(rows, "E0", rep, "seed42", out, df, h)
    save_rows(rows, "E0", rep)
    (ROOT / "data/manifests" / f"frozen_{rep}.json").write_text(json.dumps({
        "rep": rep, "frozen_hash": h, "n_rows": len(y), "features": FEATURES,
        "row_order": "author_row ascending", "n_pos": int(y.sum())}, indent=2))
    pd.DataFrame({"author_row": df["author_row"], "source_row_id": df["source_row_id"],
                  "fold_seed42": out["fold"]}).to_csv(
        ROOT / "data/manifests" / f"folds_seed42_{rep}.csv", index=False)
    print("E0", rep, "AUC", out["auc_pooled"], "cached" if cached else "", flush=True)


def stage_A(rep, cfg, n_jobs):
    df, X, y, h = load_frozen(rep)
    params = cfg["baseline"]["lgbm"]
    rows = []
    for seed in cfg["experiments"]["A_fold_seeds"]:
        run = f"fold_seed{seed}"
        out, _ = checkpointed_cv("A", rep, run, X, y, stratified_splits(y, seed), params, h, n_jobs)
        record(rows, "A", rep, run, out, df, h, {"fold_seed": seed})
        print("A", rep, run, round(float(out["auc_pooled"]), 4), flush=True)
    save_rows(rows, "A", rep)


def stage_B(rep, cfg, n_jobs):
    df, X, y, h = load_frozen(rep)
    base = cfg["baseline"]["lgbm"]
    splits = stratified_splits(y, 42)
    rows = []
    for name, over in cfg["experiments"]["B_variants"].items():
        seeds = cfg["experiments"]["B_subsample_seeds"] if name == "subsample" else [base["random_state"]]
        for s in seeds:
            params = {**base, **over, "random_state": s}
            run = f"{name}_rs{s}"
            out, _ = checkpointed_cv("B", rep, run, X, y, splits, params, h, n_jobs)
            record(rows, "B", rep, run, out, df, h, {"variant": name, "model_seed": s})
            print("B", rep, run, round(float(out["auc_pooled"]), 4), flush=True)
    rows += stage_B_logistic(rep, df, X, y, h, splits)
    save_rows(rows, "B", rep)


def stage_B_logistic(rep, df, X, y, h, splits):
    """EXPLORATORY: standardized L2 logistic regression with exact linear logit attributions
    phi_ij = w_j (x_ij - mean_train_j) / sd_train_j (interventional SHAP for a linear model
    with the training mean as reference)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    path = run_path("B", rep, "logreg_l2")
    if not path.exists():
        shap_ = np.zeros_like(X)
        proba = np.zeros(len(y))
        for tr, va in splits:
            mu, sd = X[tr].mean(0), X[tr].std(0)
            sd[sd == 0] = 1.0
            Z = (X - mu) / sd
            clf = LogisticRegression(C=1.0, max_iter=5000).fit(Z[tr], y[tr])
            shap_[va] = Z[va] * clf.coef_[0]
            proba[va] = clf.predict_proba(Z[va])[:, 1]
            margin = clf.decision_function(Z[va])
            base = clf.intercept_[0] + (Z[tr].mean(0) * clf.coef_[0]).sum()
            assert np.allclose(shap_[va].sum(1) + base, margin, atol=1e-8)
        np.savez_compressed(path, shap=shap_, proba=proba, y_fit=y, frozen_hash=h,
                            auc_pooled=roc_auc_score(y, proba), auc_mean_fold=np.mean(
                                [roc_auc_score(y[va], proba[va]) for _, va in splits]))
    out = dict(np.load(path, allow_pickle=True))
    rows = []
    record(rows, "B", rep, "logreg_l2", out, df, h, {"variant": "logreg_l2_exploratory", "model_seed": -1})
    return rows


def permute_within_system(y, systems, seed):
    rng = np.random.default_rng(seed)
    yp = y.copy()
    for s in np.unique(systems):
        idx = np.flatnonzero(systems == s)
        yp[idx] = y[rng.permutation(idx)]
    return yp


def stage_C(rep, cfg, n_jobs):
    df, X, y, h = load_frozen(rep)
    params = cfg["baseline"]["lgbm"]
    systems = df["agent_system"].to_numpy()
    rows = []
    for kind, seeds in [("within_system", cfg["experiments"]["C_within_system_perm_seeds"]),
                        ("global", cfg["experiments"]["C_global_perm_seeds"])]:
        for seed in seeds:
            yp = permute_within_system(y, systems, seed) if kind == "within_system" \
                else np.random.default_rng(seed).permutation(y)
            if kind == "within_system":
                for s in SYSTEMS:
                    m = systems == s
                    assert yp[m].sum() == y[m].sum()
            run = f"{kind}_perm{seed}"
            out, _ = checkpointed_cv("C", rep, run, X, yp, stratified_splits(yp, 42), params, h, n_jobs,
                                     meta={"null": kind, "perm_seed": seed})
            record(rows, "C", rep, run, out, df, h, {"null_type": kind, "perm_seed": seed})
            print("C", rep, run, round(float(out["auc_pooled"]), 4), flush=True)
    save_rows(rows, "C", rep)


def stage_D(rep, cfg, n_jobs):
    df, X, y, h = load_frozen(rep)
    params = cfg["baseline"]["lgbm"]
    groups = df["task_key"].to_numpy()
    g = cfg["experiments"]["D_group_cv"]
    splits = grouped_splits(y, groups, g["random_state"], g["n_splits"])
    out, _ = checkpointed_cv("D", rep, "group_seed42", X, y, splits, params, h, n_jobs, groups=groups)
    rows = []
    record(rows, "D", rep, "group_seed42", out, df, h)
    save_rows(rows, "D", rep)
    folds = json.loads(str(out["folds"]))
    pd.DataFrame(folds).to_csv(ROOT / "results/tables" / f"D_fold_balance_{rep}.csv", index=False)
    print("D", rep, round(float(out["auc_pooled"]), 4), flush=True)


def stage_G(rep, cfg, n_jobs, pilot):
    """Interventional TreeSHAP with fold-specific 128-row training backgrounds."""
    df, X, y, h = load_frozen(rep)
    params = cfg["baseline"]["lgbm"]
    ex = cfg["experiments"]
    splits = stratified_splits(y, 42)
    base = np.load(run_path("E0", rep, "seed42"), allow_pickle=True)
    assert str(base["frozen_hash"]) == h
    eval_mask = np.ones(len(y), bool)
    if pilot:
        rng = np.random.default_rng(ex["G_pilot_seed"])
        eval_mask[:] = False
        for s in SYSTEMS:
            idx = np.flatnonzero(df["agent_system"].to_numpy() == s)
            eval_mask[rng.choice(idx, min(ex["G_pilot_rows_per_system"], len(idx)), replace=False)] = True
    stage = "G_pilot" if pilot else "G"
    rows = []
    for bseed in ex["G_background_seeds"]:
        run = f"bg{bseed}"
        path = run_path(stage, rep, run)
        if path.exists():
            z = dict(np.load(path, allow_pickle=True))
        else:
            phi = np.full_like(X, np.nan)
            bg_ids, errs, bases, ev_gaps = {}, [], [], []
            row_err_all = np.full(len(y), np.nan)
            for k, (tr, va) in enumerate(splits):
                fold_ck = run_path(stage, rep, f"{run}_fold{k}")
                if fold_ck.exists():
                    f = np.load(fold_ck)
                    phi[f["rows"]] = f["phi"]
                    row_err_all[f["rows"]] = f["row_err"]
                    bg_ids[k] = f["bg"].tolist()
                    errs.append(float(f["err"])); bases.append(float(f["base"])); ev_gaps.append(float(f["ev_gap"]))
                    continue
                model = make_lgbm(params, n_jobs).fit(X[tr], y[tr])
                refit_diff = np.abs(model.predict_proba(X[va])[:, 1] - base["proba"][va]).max()
                assert refit_diff < 1e-6, f"refit differs from E0 model by {refit_diff:.2e}"
                bg = np.sort(np.random.default_rng([bseed, k]).choice(tr, ex["G_background_size"], replace=False))
                assert not set(bg) & set(va)
                rows_k = va[eval_mask[va]]
                # shap 0.51 interventional TreeSHAP is not exactly additive on a few rows
                # (DECISIONS.md D15): check per row, record, never abort or drop silently.
                vals, b, err, margin = explain(model, X[rows_k], background=X[bg], check=False)
                row_err = np.abs(vals.sum(1) + b - margin)
                ev_gap = b - float(model.predict(X[bg], raw_score=True).mean())
                phi[rows_k] = vals
                row_err_all[rows_k] = row_err
                bg_ids[k] = bg.tolist(); errs.append(err); bases.append(b); ev_gaps.append(ev_gap)
                np.savez_compressed(fold_ck, rows=rows_k, phi=vals, bg=bg, err=err, base=b,
                                    row_err=row_err, ev_gap=ev_gap)
                print(stage, rep, run, "fold", k, "err", f"{err:.2e}", flush=True)
            z = {"shap": phi, "eval_mask": eval_mask, "frozen_hash": h, "y_fit": y,
                 "auc_pooled": base["auc_pooled"], "auc_mean_fold": base["auc_mean_fold"],
                 "background_ids": json.dumps({str(k): v for k, v in bg_ids.items()}),
                 "additivity_max_err": max(errs), "base_values": np.array(bases),
                 "row_err": row_err_all, "expected_value_gap": np.array(ev_gaps)}
            np.savez_compressed(path, **z)
        m = z["eval_mask"]
        phi_tp = base["shap"][m]
        phi_iv = z["shap"][m]
        cos = (phi_tp * phi_iv).sum(1) / (np.linalg.norm(phi_tp, axis=1) * np.linalg.norm(phi_iv, axis=1) + 1e-300)
        sub = df[m].reset_index(drop=True)
        ok = z["row_err"][m] <= 1e-6
        for r_iv, r_tp in zip(per_system(phi_iv, sub), per_system(phi_tp, sub)):
            sm = (sub["agent_system"] == r_iv["system"]).to_numpy()
            r_iv["bcm_additive_rows_only"] = bcm(phi_iv[sm & ok])
            r_iv["n_nonadditive_rows"] = int((sm & ~ok).sum())
            rows.append({"stage": stage, "rep": rep, "run": run, "background_seed": bseed,
                         "frozen_hash": h, **r_iv, "bcm_tree_path_dependent_same_rows": r_tp["bcm"],
                         "median_cos_to_tree_path": float(np.median(cos[sm])),
                         "mean_cos_to_tree_path": float(np.mean(cos[sm])),
                         "additivity_max_err": float(z["additivity_max_err"]),
                         "max_abs_expected_value_gap": float(np.abs(z["expected_value_gap"]).max())})
    save_rows(rows, stage, rep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--rep", default="author")
    ap.add_argument("--n-jobs", type=int, default=None)
    a = ap.parse_args()
    cfg = load_config()
    n_jobs = a.n_jobs or cfg["baseline"]["n_jobs"]
    t0 = time.time()
    if a.stage == "G_pilot":
        stage_G(a.rep, cfg, n_jobs, pilot=True)
    elif a.stage == "G":
        stage_G(a.rep, cfg, n_jobs, pilot=False)
    else:
        {"e0": stage_e0, "A": stage_A, "B": stage_B, "C": stage_C, "D": stage_D}[a.stage](a.rep, cfg, n_jobs)
    print("stage", a.stage, a.rep, "done in", round(time.time() - t0, 1), "s", flush=True)


if __name__ == "__main__":
    main()
