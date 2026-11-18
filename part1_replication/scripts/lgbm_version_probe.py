"""Re-run the author CV with whatever LightGBM is installed; compare to shipped artifacts.

Usage: <env python> scripts/lgbm_version_probe.py <out.json>
Uses LightGBM's own pred_contrib (exact tree-path-dependent TreeSHAP) so shap is not needed."""
import json, sys
import lightgbm as lgb, numpy as np, pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
R = "/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/"
F = ["total_steps","mean_action_length","max_action_length","file_search_count","file_view_count","file_edit_count",
     "test_execution_count","action_entropy","consecutive_repetition_max","unique_action_ratio","error_flag_count","step_velocity"]
df = pd.read_csv(R + "external/colm-agent-eval/results/files/anomaly_analysis_summary.csv")  # author feature matrix, author order
X, y = df[F].to_numpy(), df["resolved"].to_numpy()
P_ship = np.load(R + "external/colm-agent-eval/results/files/oof_proba.npy")
S_ship = np.load(R + "external/colm-agent-eval/results/files/oof_shap_matrix.npy")
proba, shap, base = np.zeros(len(y)), np.zeros_like(X, dtype=float), {}
for k, (tr, va) in enumerate(StratifiedKFold(5, shuffle=True, random_state=42).split(X, y)):
    m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, max_depth=6, num_leaves=31,
                           random_state=42, n_jobs=-1, verbose=-1).fit(X[tr], y[tr])
    proba[va] = m.predict_proba(X[va])[:, 1]
    c = m.predict(X[va], pred_contrib=True)
    shap[va], base[k] = c[:, :-1], float(c[0, -1])
out = {"lightgbm": lgb.__version__, "numpy": np.__version__, "auc_pooled": roc_auc_score(y, proba),
       "auc_shipped": roc_auc_score(y, P_ship), "max_abs_proba_diff": float(np.abs(proba - P_ship).max()),
       "corr_proba": float(np.corrcoef(proba, P_ship)[0, 1]), "max_abs_shap_diff": float(np.abs(shap - S_ship).max()),
       "fold_base": base, "mean_abs_shap": np.abs(shap).mean(0).round(4).tolist()}
json.dump(out, open(sys.argv[1], "w"), indent=2); print(json.dumps(out))
