"""V6d: root cause of the shap 0.51 TreeExplainer(interventional) offset with LightGBM 4.7 (V6/V6b).
Same model/background as V6b (author + role-aware parser, fold 0, bg seed 211, 128 rows).

Hypothesis: shap's internal TreeEnsemble evaluates some rows differently from LightGBM, so the interventional
expected value (mean of shap's own tree outputs over the background) differs from LightGBM's mean margin.
Steps
  1 per row: LightGBM raw margin vs shap's own TreeEnsemble prediction (ex.model.predict) on bg and validation rows;
    also tree-path TreeExplainer expected_value vs bg mean.
  2 per tree: LightGBM per-tree leaf (pred_leaf) vs shap's traversal of the same tree (re-implemented from
    ex.model.children_left/right, features, thresholds, values) -> first disagreeing tree/node per row.
  3 at each disagreeing node: LightGBM decision_type, missing_type, default_left, threshold, the row's value, and
    whether value == threshold, value is 0 / NaN.
  4 fixes: re-evaluate after (a) replacing <= by < , (b) treating zeros as missing, to see which reproduces LightGBM.
Writes <out>/v6d_rows.csv, v6d_nodes.csv, v6d_summary.json.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, str(Path(__file__).parent))
from v6_shap_additivity import FEATS, P, ROOT

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)


def lgb_nodes(booster):
    """{tree: {split_index: node dict}} from LightGBM's own dump."""
    res = {}
    for t, info in enumerate(booster.dump_model()["tree_info"]):
        d = {}
        def walk(n):
            if "split_index" in n:
                d[n["split_index"]] = n
                walk(n["left_child"]); walk(n["right_child"])
        walk(info["tree_structure"])
        res[t] = d
    return res


def shap_traverse(m, t, x, op="le", zero_missing=False):
    """Leaf value and path of shap's TreeEnsemble tree t for row x. Missing (NaN) follows children_default."""
    cl, cr, cd = m.children_left[t], m.children_right[t], m.children_default[t]
    f, th, v = m.features[t], m.thresholds[t], m.values[t]
    n, path = 0, []
    while cl[n] >= 0:
        xv = x[f[n]]
        path.append(n)
        if np.isnan(xv) or (zero_missing and xv == 0):
            n = cd[n]
        elif (xv <= th[n]) if op == "le" else (xv < th[n]):
            n = cl[n]
        else:
            n = cr[n]
    return float(v[n].ravel()[0]), path


summary, row_rec, node_rec = {}, [], []
for rep in ["author", "role_aware"]:
    df = pd.read_parquet(ROOT / f"results/tables/features_{rep}.parquet")
    X, y = df[FEATS].to_numpy(float), df.resolved.to_numpy(int)
    tr, va = next(StratifiedKFold(5, shuffle=True, random_state=42).split(X, y))
    model = lgb.LGBMClassifier(**P).fit(X[tr], y[tr])
    B = model.booster_
    bg = X[tr][np.random.default_rng(211).choice(len(tr), 128, replace=False)]
    ex_i = shap.TreeExplainer(model, data=bg, feature_perturbation="interventional", model_output="raw")
    ex_t = shap.TreeExplainer(model)
    m = ex_i.model
    lgb_bg = B.predict(bg, raw_score=True)
    s = dict(shap_version=shap.__version__, lgb_version=lgb.__version__,
             n_trees_lgb=B.num_trees(), n_trees_shap=len(m.children_left),
             tree_ev_interventional_minus_bgmean=float(np.atleast_1d(ex_i.expected_value)[-1] - lgb_bg.mean()),
             shap_model_predict_bg_mean_minus_lgb=float(np.mean(m.predict(bg)) - lgb_bg.mean()),
             base_offset=float(np.ravel(m.base_offset)[0]) if hasattr(m, "base_offset") else None,
             tree_path_ev_minus_lgb_train_mean=float(np.atleast_1d(ex_t.expected_value)[-1] - B.predict(X[tr], raw_score=True).mean()))
    # per tree, per row
    tv_lgb = np.stack([B.predict(bg, raw_score=True, start_iteration=t, num_iteration=1) for t in range(B.num_trees())], 1)
    for op, zm in [("le", False), ("lt", False), ("le", True)]:
        tv_shap = np.array([[shap_traverse(m, t, x, op, zm)[0] for t in range(len(m.children_left))] for x in bg])
        s[f"bg_mean_diff_{op}{'_zero_missing' if zm else ''}"] = float((tv_shap.sum(1) - tv_lgb.sum(1)).mean())
        s[f"n_tree_row_mismatch_{op}{'_zero_missing' if zm else ''}"] = int((np.abs(tv_shap - tv_lgb) > 1e-9).sum())
    # sanity: our traversal must equal shap's own predict
    tv_shap = np.array([[shap_traverse(m, t, x)[0] for t in range(len(m.children_left))] for x in bg])
    s["our_traversal_vs_shap_predict_maxdiff"] = float(np.abs(tv_shap.sum(1) + (np.ravel(m.base_offset)[0] if hasattr(m, "base_offset") else 0) - m.predict(bg)).max())
    mis = np.argwhere(np.abs(tv_shap - tv_lgb) > 1e-9)
    s["n_tree_row_mismatch"] = len(mis)
    s["n_rows_with_mismatch"] = int(len(np.unique(mis[:, 0]))) if len(mis) else 0
    s["per_tree_constant_offset"] = float(np.median(tv_shap - tv_lgb))   # e.g. init score folded into tree 0
    s["tree0_offset"] = float(np.median(tv_shap[:, 0] - tv_lgb[:, 0]))
    # locate first diverging node: walk LightGBM's tree with the row, compare with shap path
    for i, t in mis[:200]:
        x = bg[i]
        nd = B.dump_model()["tree_info"][t]["tree_structure"]
        while "split_index" in nd:
            xv, th = x[nd["split_feature"]], nd["threshold"]
            if nd["decision_type"] != "<=":
                break
            miss = nd["missing_type"]
            is_missing = np.isnan(xv) or (miss == "Zero" and abs(xv) <= 1e-35)
            go_left = nd["default_left"] if (is_missing and miss != "None") else (xv <= th)
            # shap's view of this split: same feature/threshold?
            node_rec.append(dict(rep=rep, row=int(i), tree=int(t), feature=FEATS[nd["split_feature"]], value=xv, threshold=th,
                                 value_eq_threshold=bool(xv == th), value_is_zero=bool(xv == 0), missing_type=miss,
                                 default_left=nd["default_left"], lgb_left=bool(go_left),
                                 plain_le_left=bool(xv <= th), disagree_plain=bool(go_left != (xv <= th))))
            nd = nd["left_child"] if go_left else nd["right_child"]
    summary[rep] = s
    print(rep, json.dumps(s, indent=1), flush=True)
    row_rec += [dict(rep=rep, row=i, lgb=float(a), shap=float(b)) for i, (a, b) in enumerate(zip(lgb_bg, m.predict(bg)))]

pd.DataFrame(row_rec).to_csv(out / "v6d_rows.csv", index=False)
N = pd.DataFrame(node_rec)
N.to_csv(out / "v6d_nodes.csv", index=False)
if len(N):
    print(N[N.disagree_plain].groupby(["rep", "missing_type", "value_is_zero", "value_eq_threshold"]).size(), flush=True)
json.dump(summary, open(out / "v6d_summary.json", "w"), indent=1)
