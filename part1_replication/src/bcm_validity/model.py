"""Cross-validated success predictor and out-of-fold TreeSHAP attributions.

All attributions explain the POSITIVE (resolved) class on the raw-margin / log-odds
scale. For a binary LGBMClassifier, shap 0.51 TreeExplainer.shap_values returns an
(n, d) array in log-odds with a scalar expected_value; older versions returned a
[neg, pos] list, which the author code unwraps with ``shap_vals[1]``
(behavioral_predictor_pipeline.py:54-56). ``_positive_class`` handles both and
additivity against ``predict(raw_score=True)`` is asserted for every fold.
"""
import hashlib

import lightgbm as lgb
import numpy as np
import shap
from sklearn.metrics import roc_auc_score

ADDITIVITY_TOL = 1e-6


def frozen_hash(X, y):
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(X, dtype=np.float64).tobytes())
    h.update(np.ascontiguousarray(y, dtype=np.int64).tobytes())
    return h.hexdigest()


def _positive_class(vals, base):
    if isinstance(vals, list):
        vals, base = vals[1], np.atleast_1d(base)[1]
    vals = np.asarray(vals)
    if vals.ndim == 3:  # (n, d, classes)
        vals, base = vals[:, :, 1], np.atleast_1d(base)[1]
    base = float(np.atleast_1d(base)[-1]) if np.ndim(base) else float(base)
    return vals, base


def make_lgbm(params, n_jobs):
    return lgb.LGBMClassifier(**params, n_jobs=n_jobs)


def explain(model, X_eval, background=None, check=True):
    if background is None:
        explainer = shap.TreeExplainer(model)
    else:
        explainer = shap.TreeExplainer(model, data=background,
                                       feature_perturbation="interventional",
                                       model_output="raw")
    vals, base = _positive_class(explainer.shap_values(X_eval, check_additivity=False),
                                 explainer.expected_value)
    margin = model.predict(X_eval, raw_score=True)
    err = np.abs(vals.sum(axis=1) + base - margin).max()
    if check and err > ADDITIVITY_TOL:
        raise AssertionError(f"SHAP additivity violated: max |sum+base-margin| = {err:.3e}")
    return vals, base, float(err), margin


def cross_validate(X, y, splits, params, n_jobs=4, groups_check=None):
    """Fit one model per fold; return OOF proba, margin, SHAP, fold ids and per-fold info.

    ``splits`` is a list of (train_idx, val_idx). ``groups_check`` (array of group
    keys) asserts that no group spans train and validation."""
    n, d = X.shape
    oof_p = np.full(n, np.nan)
    oof_m = np.full(n, np.nan)
    oof_s = np.full((n, d), np.nan)
    fold = np.full(n, -1)
    info = []
    for k, (tr, va) in enumerate(splits):
        if groups_check is not None:
            overlap = set(groups_check[tr]) & set(groups_check[va])
            if overlap:
                raise AssertionError(f"fold {k}: {len(overlap)} groups in both train and validation")
        assert np.all(fold[va] == -1), "validation folds overlap"
        model = make_lgbm(params, n_jobs).fit(X[tr], y[tr])
        p = model.predict_proba(X[va])[:, 1]
        vals, base, err, margin = explain(model, X[va])
        assert np.allclose(1 / (1 + np.exp(-margin)), p, atol=1e-9), "proba/margin mismatch"
        oof_p[va], oof_m[va], oof_s[va], fold[va] = p, margin, vals, k
        info.append({"fold": k, "n_train": len(tr), "n_val": len(va),
                     "pos_train": int(y[tr].sum()), "pos_val": int(y[va].sum()),
                     "base_value": base, "additivity_max_err": err,
                     "auc": roc_auc_score(y[va], p) if 0 < y[va].sum() < len(va) else np.nan})
    assert np.all(fold >= 0) and not np.isnan(oof_s).any(), "some rows never validated"
    return {"proba": oof_p, "margin": oof_m, "shap": oof_s, "fold": fold, "folds": info,
            "auc_pooled": roc_auc_score(y, oof_p),
            "auc_mean_fold": float(np.nanmean([f["auc"] for f in info]))}
