"""V6: is shap 0.51's interventional TreeSHAP really non-additive on the role-aware features,
and if so, why?  Ground truth = brute-force exact interventional Shapley values
    v(S) = mean_b f(x_S, b_~S),  f = LightGBM raw margin (float64 predict)
over all 2^12 coalitions, for a sample of validation rows.

Hypothesis tested: shap casts data/thresholds to float32 while LightGBM compares in float64,
so rows whose feature value lies between float32(threshold) and threshold take different
paths. Check: (a) brute force agrees with model margin (additive by construction);
(b) shap agrees with brute force on additive rows only; (c) refitting on float32-representable
features (X.astype(float32).astype(float64)) removes the violations.

Usage: python v6_shap_additivity.py <out_dir>
"""
import itertools
import json
import math
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/gpfs_common/share02/gaise/qle3/project_791/bcm-validity")
FEATS = ["total_steps", "mean_action_length", "max_action_length", "file_search_count",
         "file_view_count", "file_edit_count", "test_execution_count", "action_entropy",
         "consecutive_repetition_max", "unique_action_ratio", "error_flag_count", "step_velocity"]
P = dict(n_estimators=200, learning_rate=0.05, max_depth=6, num_leaves=31, random_state=42,
         n_jobs=8, verbose=-1)


def exact_interventional(booster, x, bg):
    d = len(x)
    subsets = list(itertools.product([0, 1], repeat=d))
    masks = np.array(subsets, dtype=bool)                       # (2^d, d)
    v = np.empty(len(masks))
    for i, m in enumerate(masks):
        Z = bg.copy()
        Z[:, m] = x[m]
        v[i] = booster.predict(Z, raw_score=True).mean()
    idx = {s: i for i, s in enumerate(subsets)}
    phi = np.zeros(d)
    for i, s in enumerate(subsets):
        k = sum(s)
        for j in range(d):
            if s[j] == 0:
                w = math.factorial(k) * math.factorial(d - k - 1) / math.factorial(d)
                s2 = list(s)
                s2[j] = 1
                phi[j] += w * (v[idx[tuple(s2)]] - v[i])
    return phi, v[0]


def interventional(model, bg, Xva):
    ex = shap.TreeExplainer(model, data=bg, feature_perturbation="interventional", model_output="raw")
    sv = ex.shap_values(Xva, check_additivity=False)
    if isinstance(sv, list):
        sv = sv[1]
    return np.asarray(sv), float(np.atleast_1d(ex.expected_value)[-1])


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    res = {"shap": shap.__version__, "lightgbm": lgb.__version__}
    rows = []
    for rep in ["role_aware", "author"]:
        df = pd.read_parquet(ROOT / f"results/tables/features_{rep}.parquet")
        X, y = df[FEATS].to_numpy(float), df.resolved.to_numpy(int)
        for variant, Xv in [("float64", X), ("float32_rounded", X.astype(np.float32).astype(np.float64))]:
            tr, va = next(StratifiedKFold(5, shuffle=True, random_state=42).split(Xv, y))
            model = lgb.LGBMClassifier(**P).fit(Xv[tr], y[tr])
            bg = Xv[tr][np.random.default_rng(211).choice(len(tr), 128, replace=False)]
            sv, base = interventional(model, bg, Xv[va])
            margin = model.predict(Xv[va], raw_score=True)
            bg_mean = model.predict(bg, raw_score=True).mean()
            err = np.abs(sv.sum(1) + base - margin)
            err_bgmean = np.abs(sv.sum(1) + bg_mean - margin)
            r = dict(rep=rep, variant=variant, n_val=len(va),
                     frac_nonadditive_1e6=float((err_bgmean > 1e-6).mean()),
                     frac_nonadditive_1e6_vs_expected_value=float((err > 1e-6).mean()),
                     err_quantiles_vs_bgmean=np.quantile(err_bgmean, [0.5, 0.9, 0.99]).round(8).tolist(),
                     max_err=float(err_bgmean.max()),
                     expected_value_minus_bg_mean=float(base - bg_mean))
            if variant == "float64":
                rng = np.random.default_rng(7)
                order = np.argsort(err_bgmean)
                bad, good = order[-15:], order[:10]
                pick = np.concatenate([bad, good]).astype(int)
                b = model.booster_
                dev_bad, dev_good, add_bf = [], [], []
                for i in pick:
                    phi, v0 = exact_interventional(b, Xv[va][i], bg)
                    add_bf.append(abs(phi.sum() + v0 - margin[i]))
                    dev = float(np.abs(phi - sv[i]).max())
                    (dev_bad if i in set(bad) else dev_good).append(dev)
                r.update(worst_rows_err=err_bgmean[bad].round(6).tolist(), best_rows_err=err_bgmean[good].round(10).tolist(),
                         bruteforce_max_additivity_err=float(max(add_bf)),
                         shap_vs_exact_maxdev_15_worst_rows=float(max(dev_bad)) if dev_bad else None,
                         shap_vs_exact_maxdev_10_best_rows=float(max(dev_good)),
                         n_bruteforce_rows=len(pick))
                # float32 threshold-straddling diagnostic
                thr = b.dump_model()["tree_info"]
                straddle = 0
                th = []
                def walk(n):
                    if "split_feature" in n:
                        th.append((n["split_feature"], n["threshold"]))
                        walk(n["left_child"]); walk(n["right_child"])
                for t in thr:
                    walk(t["tree_structure"])
                th = np.array(th)
                x32 = Xv[va].astype(np.float32).astype(np.float64)
                for f, t in th:
                    f = int(f)
                    t32 = float(np.float32(t))
                    lo, hi = min(t, t32), max(t, t32)
                    straddle_rows = ((Xv[va][:, f] > lo) & (Xv[va][:, f] <= hi)) | ((x32[:, f] <= t) != (Xv[va][:, f] <= t))
                    straddle += straddle_rows.sum()
                r["val_row_threshold_straddles_float32"] = int(straddle)
            rows.append(r)
            print(json.dumps(r), flush=True)
    pd.DataFrame(rows).to_csv(out / "v6_additivity.csv", index=False)
    json.dump(res, open(out / "v6_meta.json", "w"))


if __name__ == "__main__":
    main(sys.argv[1])
