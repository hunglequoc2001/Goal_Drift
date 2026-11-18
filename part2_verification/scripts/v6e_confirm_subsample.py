"""V6e: confirm the root cause found in V6d. shap.TreeExplainer(model, data=bg) wraps bg in maskers.Independent(bg),
whose default max_samples=100 silently subsamples a background with more than 100 rows. V6/V6b used 128 rows, so shap
explained against a different 100-row background than the brute-force reference.
Checks (V6b setting: fold 0, bg seed 211, 128 rows, 20 validation rows):
  a ex.data.shape and whether its rows are a subset of bg
  b ex.expected_value - LightGBM mean margin over ex.data           (expected 0)
  c brute-force exact interventional over ex.data vs TreeExplainer (expected ~1e-12)
  d fix: data=maskers.Independent(bg, max_samples=len(bg)) -> brute over full bg vs TreeExplainer (expected ~1e-12)
Writes <out>/v6e_confirm.csv.
"""
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, str(Path(__file__).parent))
from v6_shap_additivity import FEATS, P, ROOT, exact_interventional

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
rows = []
for rep in ["author", "role_aware"]:
    df = pd.read_parquet(ROOT / f"results/tables/features_{rep}.parquet")
    X, y = df[FEATS].to_numpy(float), df.resolved.to_numpy(int)
    tr, va = next(StratifiedKFold(5, shuffle=True, random_state=42).split(X, y))
    model = lgb.LGBMClassifier(**P).fit(X[tr], y[tr])
    B = model.booster_
    bg = X[tr][np.random.default_rng(211).choice(len(tr), 128, replace=False)]
    Xe = X[va][np.random.default_rng(5).choice(len(va), 20, replace=False)]
    f = lambda Z: B.predict(Z, raw_score=True)
    sv1 = lambda e: np.asarray(e.shap_values(Xe, check_additivity=False)[1] if isinstance(e.shap_values(Xe[:1], check_additivity=False), list)
                               else e.shap_values(Xe, check_additivity=False))
    ex = shap.TreeExplainer(model, data=bg, feature_perturbation="interventional", model_output="raw")
    used = np.asarray(ex.data)
    subset = all((np.abs(bg - r).sum(1) == 0).any() for r in used)
    tree = sv1(ex)
    brute_used = np.array([exact_interventional(B, x, used)[0] for x in Xe])
    brute_full = np.array([exact_interventional(B, x, bg)[0] for x in Xe])
    exf = shap.TreeExplainer(model, data=shap.maskers.Independent(bg, max_samples=len(bg)),
                             feature_perturbation="interventional", model_output="raw")
    treef = sv1(exf)
    rows.append(dict(rep=rep, bg_rows_passed=len(bg), bg_rows_used_by_shap=len(used), used_rows_subset_of_bg=subset,
                     ev_minus_mean_over_used=float(np.ravel(ex.expected_value)[-1] - f(used).mean()),
                     ev_minus_mean_over_passed=float(np.ravel(ex.expected_value)[-1] - f(bg).mean()),
                     tree_vs_brute_over_used_maxdev=float(np.abs(tree - brute_used).max()),
                     tree_vs_brute_over_passed_maxdev=float(np.abs(tree - brute_full).max()),
                     fixed_bg_rows_used=len(np.asarray(exf.data)),
                     fixed_ev_minus_mean_over_passed=float(np.ravel(exf.expected_value)[-1] - f(bg).mean()),
                     fixed_tree_vs_brute_over_passed_maxdev=float(np.abs(treef - brute_full).max())))
    print(rows[-1], flush=True)
pd.DataFrame(rows).to_csv(out / "v6e_confirm.csv", index=False)
