"""V6b: three-way check on 20 validation rows (author parser, fold 0, bg seed 211, 128 rows):
our brute-force exact interventional Shapley vs shap.explainers.Exact (independent shap code path,
Independent masker) vs shap.TreeExplainer(feature_perturbation='interventional')."""
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, str(Path(__file__).parent))
from v6_shap_additivity import FEATS, P, ROOT, exact_interventional, interventional

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
rows = []
for rep in ["author", "role_aware"]:
    df = pd.read_parquet(ROOT / f"results/tables/features_{rep}.parquet")
    X, y = df[FEATS].to_numpy(float), df.resolved.to_numpy(int)
    tr, va = next(StratifiedKFold(5, shuffle=True, random_state=42).split(X, y))
    model = lgb.LGBMClassifier(**P).fit(X[tr], y[tr])
    bg = X[tr][np.random.default_rng(211).choice(len(tr), 128, replace=False)]
    pick = np.random.default_rng(5).choice(len(va), 20, replace=False)
    Xe = X[va][pick]
    tree_sv, tree_ev = interventional(model, bg, Xe)
    f = lambda Z: model.predict(Z, raw_score=True)
    ex = shap.explainers.Exact(f, shap.maskers.Independent(bg, max_samples=128))
    e = ex(Xe)
    brute = np.array([exact_interventional(model.booster_, x, bg)[0] for x in Xe])
    margin, bgm = f(Xe), f(bg).mean()
    rows.append(dict(rep=rep,
                     brute_vs_shapExact_maxdev=float(np.abs(brute - e.values).max()),
                     brute_vs_tree_interventional_maxdev=float(np.abs(brute - tree_sv).max()),
                     shapExact_base_minus_bgmean=float(np.atleast_1d(e.base_values)[0] - bgm),
                     tree_ev_minus_bgmean=tree_ev - bgm,
                     brute_additivity=float(np.abs(brute.sum(1) + bgm - margin).max()),
                     tree_additivity_vs_bgmean=float(np.abs(tree_sv.sum(1) + bgm - margin).max()),
                     bcm_rows_brute=None))
    print(rows[-1], flush=True)
pd.DataFrame(rows).to_csv(out / "v6b_exact_crosscheck.csv", index=False)
