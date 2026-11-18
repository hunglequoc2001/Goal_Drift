"""V7: identify which predictor configuration produced the authors' shipped artifacts.

Inputs (read-only):
  - author feature CSV produced by the unchanged author pipeline in Exp01
    (bcm-validity/runs/author_archival/tbf/data/engineered_features_matrix.csv)
  - shipped artifacts external/colm-agent-eval/results/files/{oof_proba,oof_shap_matrix}.npy
Candidate configurations come from the author repo's git history
(model/predictor.py @48fcfd0 vs model/behavioral_predictor_pipeline.py @61f9894).

Usage: python v7_shipped_model_search.py <out_dir>
"""
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/gpfs_common/share02/gaise/qle3/project_791/bcm-validity")
SHIP = ROOT / "external/colm-agent-eval/results/files"
FEATS = ["total_steps", "mean_action_length", "max_action_length", "file_search_count",
         "file_view_count", "file_edit_count", "test_execution_count", "action_entropy",
         "consecutive_repetition_max", "unique_action_ratio", "error_flag_count", "step_velocity"]

SHIPPED_SCRIPT = dict(n_estimators=200, learning_rate=0.05, max_depth=6, num_leaves=31,
                      random_state=42, n_jobs=-1, verbose=-1)
HIST_48FCFD0 = dict(n_estimators=1500, learning_rate=0.005, num_leaves=15, max_depth=4,
                    subsample=0.80, colsample_bytree=0.80, min_child_samples=30,
                    reg_alpha=2.0, reg_lambda=10.0, objective="binary", metric="auc",
                    random_state=42, n_jobs=-1, verbose=-1)


def bcm(phi):
    n = np.linalg.norm(phi, axis=1)
    u = phi[n > 1e-9] / n[n > 1e-9, None]
    k = len(u)
    s = u.sum(0)
    return float((s @ s - k) / (k * (k - 1))) if k > 1 else np.nan


def run(X, y, params, early_stop_on_val, spw):
    p = dict(params)
    if spw:
        p["scale_pos_weight"] = (y == 0).sum() / (y == 1).sum()
    oof_p = np.zeros(len(y))
    oof_s = np.zeros_like(X, dtype=float)
    info = []
    for k, (tr, va) in enumerate(StratifiedKFold(5, shuffle=True, random_state=42).split(X, y)):
        clf = lgb.LGBMClassifier(**p)
        if early_stop_on_val:
            clf.fit(X[tr], y[tr], eval_set=[(X[va], y[va])],
                    callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)])
        else:
            clf.fit(X[tr], y[tr])
        oof_p[va] = clf.predict_proba(X[va])[:, 1]
        ex = shap.TreeExplainer(clf)
        sv = ex.shap_values(X[va])
        if isinstance(sv, list):
            sv = sv[1]
        oof_s[va] = sv
        info.append({"fold": k, "best_iteration": int(clf.best_iteration_ or p["n_estimators"]),
                     "expected_value": float(np.atleast_1d(ex.expected_value)[-1]),
                     "fold_auc": float(roc_auc_score(y[va], oof_p[va]))})
    return oof_p, oof_s, info


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(ROOT / "runs/author_archival/tbf/data/engineered_features_matrix.csv")
    X, y = df[FEATS].to_numpy(), df["resolved"].to_numpy().astype(int)
    sys_ = df["agent_system"].to_numpy()
    sp, ss = np.load(SHIP / "oof_proba.npy"), np.load(SHIP / "oof_shap_matrix.npy")
    ship_base = np.unique(np.round(np.log(sp / (1 - sp)) - ss.sum(1), 5))
    configs = {
        "shipped_script_200trees": (SHIPPED_SCRIPT, False, False),
        "hist48fcfd0_es_on_val_spw": (HIST_48FCFD0, True, True),
        "hist48fcfd0_no_es_spw": (HIST_48FCFD0, False, True),
        "hist48fcfd0_es_on_val_no_spw": (HIST_48FCFD0, True, False),
    }
    rows = []
    for name, (params, es, spw) in configs.items():
        t = time.time()
        p, s, info = run(X, y, params, es, spw)
        r = {"config": name, "auc_pooled": roc_auc_score(y, p),
             "auc_mean_fold": float(np.mean([i["fold_auc"] for i in info])),
             "corr_proba_vs_shipped": float(np.corrcoef(p, sp)[0, 1]),
             "max_abs_proba_diff": float(np.abs(p - sp).max()),
             "max_abs_shap_diff": float(np.abs(s - ss).max()),
             "crm_shap_all_zero": bool((s[:, FEATS.index("consecutive_repetition_max")] == 0).all()),
             "best_iterations": [i["best_iteration"] for i in info],
             "expected_values": [round(i["expected_value"], 5) for i in info],
             "seconds": round(time.time() - t, 1)}
        for g in sorted(set(sys_)):
            r[f"bcm_{g}"] = bcm(s[sys_ == g])
            r[f"bcm_shipped_{g}"] = bcm(ss[sys_ == g])
        rows.append(r)
        np.savez_compressed(out / f"{name}.npz", proba=p, shap=s)
        print(json.dumps(r, default=str), flush=True)
    pd.DataFrame(rows).to_csv(out / "v7_shipped_model_search.csv", index=False)
    json.dump({"shipped_implied_base_values": ship_base.tolist(),
               "lightgbm": lgb.__version__, "shap": shap.__version__},
              open(out / "v7_meta.json", "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
