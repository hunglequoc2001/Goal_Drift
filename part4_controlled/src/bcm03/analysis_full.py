"""Exp03 full-study (and staging) analysis, implementing FULL_STUDY_ANALYSIS_PLAN.md. bcm03.analysis (pilot) is unchanged.

Inputs: <in_dir>/attempts.parquet from bcm03.ingest_full. Outputs: CSVs in <out_dir> (one per analysis block) + meta.json.

Blocks
  F0  descriptives per model x variant: solve rate (official and final-state), edits, regressions, context overflow,
      format compliance, submission validity; infrastructure exclusions.
  F1  BCM: pooled predictor as in the paper (released LightGBM, R2 features; standardised logistic; R3 LightGBM),
      task-grouped 5-fold CV, real (10 CV seeds) vs within-model and within-model x repository label-permutation nulls
      (50 seeds each). Pooled AUC and within-model AUC (only for models with both outcome classes; never imputed).
      Per-model-fit BCM as sensitivity. Task-cluster bootstrap CI of BCM over the fixed OOF attributions (seed 0).
  F1s SHAP validation: TreeSHAP additivity is asserted on every fold (bcm02.pipeline.tree_attr, tol 1e-6); in addition
      TreeSHAP is compared with LightGBM's own pred_contrib on each fit set; a configuration that fails either check is
      quarantined (written to shap_quarantine.csv and dropped from F1-F4).
  F2  repeatability within task (A): pair measures (task-grounded: patch_sim_cond, f2p_agree, func_jacc_cond,
      edit_decision_agree, outcome_concord with solve rate and chance-corrected concordance; trace-derived seq_sim),
      attribution-cosine decomposition within vs between task (what BCM averages).
  H1  attribution cosine vs task-grounded behaviour similarity: within-cell r (primary) and cell-level r, per model and
      pooled over non-degenerate models, task-cluster bootstrap.
  H2  invariance A vs B2 (and B1): D = S_AA - S_AB per task, per model and pooled; TOST at the pre-registered margins;
      solve-rate difference TOST; BCM on A vs B2 attempts within the A+B2 fit.
  H3  adaptation on C2: adapted / persisted_original / failed rates (task-cluster CIs) vs A solve rate.
  H4  can trace-based attributions tell adaptation from persistence? AUC of the A+C2 success-predictor margin for
      adapted vs persisted C2 attempts (pooled within model); BCM(A+C2) - BCM(A+B2) per model.
  C1  already-fixed decisions: class rates with CIs; human-review sample export.
  S   sensitivity: drop context-overflow attempts; final-state correctness instead of official; repository-cluster bootstrap.
Usage: python -m bcm03.analysis_full <in_dir> <out_dir> [n_real=10] [n_null=50] [n_boot=2000]
"""
import itertools
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from bcm02.pipeline import PAPER, bcm, permute, tree_attr
from bcm03.analysis import FEATS, oof, unit
from bcm03.measures import PAIR, cell_summary, pair_measures

MARGIN = {"patch_sim_cond": 0.05, "f2p_agree": 0.05, "func_jacc_cond": 0.05, "edit_decision_agree": 0.05,
          "outcome_concord": 0.05, "seq_sim": 0.05, "cos": 0.05, "solve_rate": 0.05}   # FULL_STUDY_ANALYSIS_PLAN §5
CONFIGS = [("r2", "lgbm_paper"), ("r2", "logistic"), ("r3", "lgbm_paper")]
DEGENERATE = {"qwen2.5-coder-7b"}            # pre-registered degenerate-agent control (pilot P3)
RNG = np.random.default_rng(20261027)


def fitsets(T):
    v = set(T.variant)
    fs = {"A": ["A"]}
    if "B2" in v:
        fs["AB2"] = ["A", "B2"]
    if "B1" in v:
        fs["AB1"] = ["A", "B1"]
    if "C2" in v:
        fs["AC2"] = ["A", "C2"]
    return fs


def cluster_boot(values_by_cluster, stat=np.mean, n=2000):
    """Percentile CI of stat over clusters (list of per-cluster arrays or scalars)."""
    v = [np.atleast_1d(x) for x in values_by_cluster if np.size(x)]
    if len(v) < 2:
        return np.nan, np.nan
    k = len(v)
    bs = [stat(np.concatenate([v[i] for i in RNG.integers(0, k, k)])) for _ in range(n)]
    return tuple(np.nanquantile(bs, [.025, .975]))


# ------------------------------------------------------------------ F0
def f0(T, out):
    S = T.groupby(["model", "variant"]).agg(
        n=("run_id", "size"), n_tasks=("instance_id", "nunique"), solve_rate=("resolved", "mean"),
        solve_rate_state=("resolved_state", lambda s: s.astype(float).mean()) if "resolved_state" in T else ("resolved", "mean"),
        edit_rate=("edited", "mean"), harmful_rate=("harmful", "mean") if "harmful" in T else ("edited", "size"),
        context_overflow=("context_overflow", "mean"), format_compliance=("format_compliance", "mean"),
        text_submission=("sub_kind", lambda s: (s == "text").mean()),
        submitted=("submitted", "mean"), steps=("n_steps", "mean"), agent_seconds=("agent_seconds", "mean")).reset_index()
    solved = T[T.resolved].groupby(["model", "variant"]).instance_id.nunique()
    S["n_tasks_solved"] = [solved.get((m, v), 0) for m, v in zip(S.model, S.variant)]
    S.to_csv(out / "f0_descriptives.csv", index=False)
    return S


# ------------------------------------------------------------------ F1 + SHAP validation
def shap_check(S, rep):
    """TreeSHAP (tree-path) vs LightGBM pred_contrib on a model fit to all rows of the fit set."""
    X, y = S[FEATS[rep]].to_numpy(float), S.resolved.to_numpy(int)
    if len(set(y)) < 2:
        return dict(rep=rep, ok=None, reason="single class")
    m = lgb.LGBMClassifier(**dict(PAPER, n_jobs=8)).fit(X, y)
    try:
        phi, margin, add_err = tree_attr(m, X)
    except AssertionError as e:
        return dict(rep=rep, ok=False, reason=str(e))
    pc = m.booster_.predict(X, pred_contrib=True)[:, :-1]
    d = float(np.abs(pc - phi).max())
    return dict(rep=rep, ok=bool(d < 1e-6 and add_err < 1e-6), additivity_err=add_err, max_abs_diff_vs_pred_contrib=d)


def f1(T, out, n_real, n_null, n_boot):
    rows, keep, quarantine, checks = [], {}, set(), []
    for fs, variants in fitsets(T).items():
        S = T[T.variant.isin(variants)].reset_index(drop=True)
        for rep in ["r2", "r3"]:
            c = dict(fitset=fs, **shap_check(S, rep))
            checks.append(c)
            if c["ok"] is False:
                quarantine |= {(fs, rep, "lgbm_paper")}
        strata = {"perm_model": S.model.values, "perm_model_repo": (S.model + "|" + S.repo).values}
        for rep, pred in CONFIGS:
            if (fs, rep, pred) in quarantine:
                continue
            for scheme, seeds in [("real", range(n_real)), ("perm_model", range(1000, 1000 + n_null)),
                                  ("perm_model_repo", range(2000, 2000 + n_null))]:
                for s in seeds:
                    y = None if scheme == "real" else permute(S.resolved.to_numpy(int), strata[scheme], np.random.default_rng(s))
                    try:
                        phi, margin, yy = oof(S, rep, pred, s if scheme == "real" else 0, y)
                    except AssertionError as e:          # additivity failure inside a fold: quarantine the config
                        quarantine |= {(fs, rep, pred)}
                        checks.append(dict(fitset=fs, rep=rep, predictor=pred, ok=False, reason=f"fold: {e}"))
                        break
                    ok = ~np.isnan(margin)
                    r = dict(fitset=fs, rep=rep, predictor=pred, scheme=scheme, seed=s, n=len(S), n_scored=int(ok.sum()),
                             auc_pooled=roc_auc_score(yy[ok], margin[ok]) if 0 < yy[ok].sum() < ok.sum() else np.nan)
                    for m, g in S.groupby("model").groups.items():
                        g = np.asarray(g)
                        gg = g[ok[g]]
                        r[f"bcm|{m}"] = bcm(phi[gg]) if len(gg) > 1 else np.nan
                        yg = yy[gg]
                        r[f"auc_within|{m}"] = roc_auc_score(yg, margin[gg]) if 0 < yg.sum() < len(gg) else np.nan
                        for v in variants:
                            gv = gg[S.variant.values[gg] == v]
                            r[f"bcm_{v}|{m}"] = bcm(phi[gv]) if len(gv) > 1 else np.nan
                    rows.append(r)
                    if scheme == "real" and s == 0:
                        keep[(fs, rep, pred)] = (S, phi, margin)
    R = pd.DataFrame(rows)
    R.to_csv(out / "f1_bcm_runs.csv", index=False)
    pd.DataFrame(checks).to_csv(out / "f1s_shap_checks.csv", index=False)
    pd.DataFrame(sorted(quarantine), columns=["fitset", "rep", "predictor"]).to_csv(out / "shap_quarantine.csv", index=False)
    # summary: real vs nulls, with task-cluster CI of BCM over fixed OOF attributions (seed 0)
    summ = []
    for (fs, rep, pred), g in R.groupby(["fitset", "rep", "predictor"]):
        if (fs, rep, pred) in quarantine or (fs, rep, pred) not in keep:
            continue
        S, phi, _ = keep[(fs, rep, pred)]
        for col in [c for c in R.columns if c.startswith("bcm|") or c.startswith("auc_within|")]:
            m = col.split("|")[1]
            real = g[g.scheme == "real"][col]
            row = dict(fitset=fs, rep=rep, predictor=pred, stat=col.split("|")[0], model=m,
                       real_mean=real.mean(), real_cv_sd=real.std())
            for sc in ["perm_model", "perm_model_repo"]:
                nul = g[g.scheme == sc][col]
                row.update({f"{sc}_mean": nul.mean(), f"{sc}_q025": nul.quantile(.025), f"{sc}_q975": nul.quantile(.975),
                            f"{sc}_p_two_sided": (np.sum(np.abs(nul - nul.mean()) >= abs(real.mean() - nul.mean())) + 1) / (len(nul) + 1)})
            if col.startswith("bcm|"):
                idx = np.flatnonzero((S.model.values == m) & ~np.isnan(phi).any(1))
                tasks = S.instance_id.values[idx]
                ut = np.unique(tasks)
                if len(ut) > 1:
                    grp = [idx[tasks == t] for t in ut]
                    bs = [bcm(phi[np.concatenate([grp[i] for i in RNG.integers(0, len(ut), len(ut))])]) for _ in range(n_boot // 4)]
                    row["bcm_task_boot_lo"], row["bcm_task_boot_hi"] = np.nanquantile(bs, [.025, .975])
            summ.append(row)
    pd.DataFrame(summ).to_csv(out / "f1_bcm_summary.csv", index=False)
    pooled = R.groupby(["fitset", "rep", "predictor", "scheme"]).auc_pooled.agg(["mean", "std"]).reset_index()
    pooled.to_csv(out / "f1_auc_pooled.csv", index=False)
    # sensitivity: predictor fit separately per model (Exp02 finding: BCM ~ 0 when fit per system)
    per = []
    for m, Sm in T[T.variant == "A"].groupby("model"):
        Sm = Sm.reset_index(drop=True)
        if Sm.resolved.nunique() < 2 or Sm.instance_id.nunique() < 4:
            per.append(dict(model=m, bcm_per_model_fit=np.nan, reason="single class or < 4 tasks"))
            continue
        phi, margin, _ = oof(Sm, "r2", "lgbm_paper", 0)
        ok = ~np.isnan(margin)
        per.append(dict(model=m, bcm_per_model_fit=bcm(phi[ok]), n_scored=int(ok.sum())))
    pd.DataFrame(per).to_csv(out / "f1_bcm_per_model_fit.csv", index=False)
    return keep, quarantine


# ------------------------------------------------------------------ pair table (behaviour + attributions)
def pairs(T, keep):
    U = {k: dict(zip(S.run_id, unit(phi))) for k, (S, phi, _) in keep.items()}
    rows = []
    for (m, t), g in T.groupby(["model", "instance_id"]):
        for r, s in itertools.combinations(list(g.itertuples()), 2):
            kind = "".join(sorted([r.variant, s.variant]))
            row = dict(model=m, instance_id=t, repo=r.repo, kind=kind, a=r.run_id, b=s.run_id, **pair_measures(r, s))
            for (fs, rep, pred), d in U.items():
                if r.run_id in d and s.run_id in d:
                    row[f"cos|{fs}|{rep}|{pred}"] = float(np.dot(d[r.run_id], d[s.run_id]))
            rows.append(row)
    return pd.DataFrame(rows)


def cross_task_cos(T, keep, out):
    """Decomposition of what BCM averages: mean attribution cosine of same-task pairs vs different-task pairs, per model."""
    rows = []
    for (fs, rep, pred), (S, phi, _) in keep.items():
        u = unit(phi)
        for m in S.model.unique():
            idx = np.flatnonzero((S.model.values == m) & ~np.isnan(u).any(1))
            if len(idx) < 3:
                continue
            C = u[idx] @ u[idx].T
            inst = np.asarray(S.instance_id, dtype=object)[idx]
            same = inst[:, None] == inst[None, :]
            iu = np.triu_indices(len(idx), 1)
            rows.append(dict(fitset=fs, rep=rep, predictor=pred, model=m, bcm=float(C[iu].mean()),
                             cos_same_task=float(C[iu][same[iu]].mean()) if same[iu].any() else np.nan,
                             cos_diff_task=float(C[iu][~same[iu]].mean()), share_pairs_same_task=float(same[iu].mean())))
    pd.DataFrame(rows).to_csv(out / "f2_cos_decomposition.csv", index=False)


# ------------------------------------------------------------------ F2 / H1
def f2_h1(T, P, out, n_boot):
    A = P[P.kind == "AA"]
    rows = []
    for m, g in A.groupby("model"):
        for k in PAIR:
            lo, hi = cluster_boot([x[k].dropna().to_numpy() for _, x in g.groupby("instance_id")], n=n_boot)
            rows.append(dict(model=m, measure=k, task_grounded=PAIR[k][1], mean=g[k].mean(), ci_lo=lo, ci_hi=hi,
                             n_pairs=int(g[k].notna().sum()), n_tasks=int(g.dropna(subset=[k]).instance_id.nunique())))
    cs = T[T.variant == "A"].groupby(["model", "instance_id"]).apply(cell_summary).reset_index()
    for m, g in cs.groupby("model"):
        for k in ["solve_rate", "outcome_concord", "concord_chance", "concord_kappa", "edit_rate"]:
            lo, hi = cluster_boot([[v] for v in g[k].dropna()], n=n_boot)
            rows.append(dict(model=m, measure=f"cell_{k}", task_grounded=True, mean=g[k].mean(), ci_lo=lo, ci_hi=hi,
                             n_tasks=int(g[k].notna().sum())))
    pd.DataFrame(rows).to_csv(out / "f2_repeatability.csv", index=False)
    # H1: within-cell r (primary) and cell-level r
    h = []
    cos_cols = [c for c in P.columns if c.startswith("cos|A|")]
    for c in cos_cols:
        for y in [k for k in PAIR]:
            for scope, models in [("pooled_nondegenerate", sorted(set(A.model) - DEGENERATE))] + [(m, [m]) for m in sorted(A.model.unique())]:
                d = A[A.model.isin(models)].dropna(subset=[c, y]).copy()
                if len(d) < 10:
                    continue
                d["cell"] = d.model + "|" + d.instance_id
                r_w, r_c = _within(d, c, y), _cell(d, c, y)
                tasks = d.instance_id.unique()
                grp = {t: d[d.instance_id == t] for t in tasks}
                bw, bc = [], []
                for _ in range(n_boot // 4):
                    pick = RNG.choice(tasks, len(tasks))
                    dd = pd.concat([grp[t].assign(cell=grp[t].cell + f"#{i}") for i, t in enumerate(pick)])
                    bw.append(_within(dd, c, y))
                    bc.append(_cell(dd, c, y))
                h.append(dict(attribution=c, behaviour=y, task_grounded=PAIR[y][1], scope=scope, n_pairs=len(d),
                              n_tasks=len(tasks), within_r=r_w, within_lo=np.nanquantile(bw, .025), within_hi=np.nanquantile(bw, .975),
                              within_lo_bonf2=np.nanquantile(bw, .0125), within_hi_bonf2=np.nanquantile(bw, .9875),
                              cell_r=r_c, cell_lo=np.nanquantile(bc, .025), cell_hi=np.nanquantile(bc, .975)))
    pd.DataFrame(h).to_csv(out / "h1_attribution_vs_behaviour.csv", index=False)


def _within(d, x, y):
    g = d.groupby("cell")
    xc, yc = d[x] - g[x].transform("mean"), d[y] - g[y].transform("mean")
    den = np.sqrt((xc ** 2).sum() * (yc ** 2).sum())
    return float((xc * yc).sum() / den) if den > 0 else np.nan


def _cell(d, x, y):
    c = d.groupby(["model", "cell"])[[x, y]].mean()
    c = c - c.groupby("model").transform("mean")
    return float(c[x].corr(c[y])) if len(c) > 3 else np.nan


# ------------------------------------------------------------------ H2 invariance
def h2(T, P, out, n_boot):
    rows = []
    for bv in ["B2", "B1"]:
        ab = "A" + bv
        if ab not in set(P.kind):
            continue
        meas = [k for k in PAIR] + [c for c in P.columns if c.startswith(f"cos|A{bv}|")]
        for col in meas:
            per = P[P.kind.isin(["AA", ab])].groupby(["model", "instance_id", "kind"])[col].mean().unstack()
            if not {"AA", ab} <= set(per.columns):
                continue
            D = (per["AA"] - per[ab]).dropna().rename("D").reset_index()
            for scope, d in [("pooled_nondegenerate", D[~D.model.isin(DEGENERATE)].groupby("instance_id").D.mean())] + \
                            [(m, g.set_index("instance_id").D) for m, g in D.groupby("model")]:
                if len(d) < 2:
                    continue
                se = d.std(ddof=1) / np.sqrt(len(d))
                mg = MARGIN.get(col.split("|")[0], 0.05)
                lo, hi = d.mean() - 1.645 * se, d.mean() + 1.645 * se
                la, ha = d.mean() - 2.241 * se, d.mean() + 2.241 * se       # Bonferroni over 4 co-primary endpoints
                l95, h95 = d.mean() - 1.96 * se, d.mean() + 1.96 * se
                rows.append(dict(variant=bv, measure=col, scope=scope, n_tasks=len(d), D_mean=d.mean(), ci90_lo=lo, ci90_hi=hi,
                                 ci_bonf_lo=la, ci_bonf_hi=ha, margin=mg, equivalent_90=bool(-mg < lo and hi < mg),
                                 equivalent_bonf=bool(-mg < la and ha < mg), different_95=bool(l95 > 0 or h95 < 0)))
        # solve-rate difference (B - A), paired by task
        sr = T[T.variant.isin(["A", bv])].groupby(["model", "instance_id", "variant"]).resolved.mean().unstack()
        if bv in sr:
            d0 = (sr[bv] - sr["A"]).dropna().rename("d").reset_index()
            for scope, d in [("pooled_nondegenerate", d0[~d0.model.isin(DEGENERATE)].groupby("instance_id").d.mean())] + \
                            [(m, g.set_index("instance_id").d) for m, g in d0.groupby("model")]:
                if len(d) < 2:
                    continue
                se = d.std(ddof=1) / np.sqrt(len(d))
                lo, hi = d.mean() - 1.645 * se, d.mean() + 1.645 * se
                la, ha = d.mean() - 2.241 * se, d.mean() + 2.241 * se
                mg = MARGIN["solve_rate"]
                rows.append(dict(variant=bv, measure="solve_rate_diff", scope=scope, n_tasks=len(d), D_mean=d.mean(),
                                 ci90_lo=lo, ci90_hi=hi, ci_bonf_lo=la, ci_bonf_hi=ha, margin=mg,
                                 equivalent_90=bool(-mg < lo and hi < mg), equivalent_bonf=bool(-mg < la and ha < mg),
                                 different_95=bool(d.mean() - 1.96 * se > 0 or d.mean() + 1.96 * se < 0)))
    pd.DataFrame(rows).to_csv(out / "h2_invariance.csv", index=False)


# ------------------------------------------------------------------ H3 / H4 adaptation, C1
def rate_ci(g, col, n_boot):
    v = [x[col].dropna().astype(float).to_numpy() for _, x in g.groupby("instance_id")]
    lo, hi = cluster_boot(v, n=n_boot)
    return g[col].astype(float).mean(), lo, hi


def h3_h4(T, keep, out, n_boot):
    C = T[T.variant == "C2"]
    rows = []
    if len(C):
        for m, g in C.groupby("model"):
            for cls in ["adapted", "persisted_original", "failed"]:
                mu, lo, hi = rate_ci(g.assign(x=g.c2_class == cls), "x", n_boot)
                rows.append(dict(model=m, measure=cls, mean=mu, ci_lo=lo, ci_hi=hi, n=len(g), n_tasks=g.instance_id.nunique()))
            a = T[(T.variant == "A") & (T.model == m) & T.instance_id.isin(g.instance_id)]
            mu, lo, hi = rate_ci(a, "resolved", n_boot)
            rows.append(dict(model=m, measure="A_solve_rate_same_tasks", mean=mu, ci_lo=lo, ci_hi=hi, n=len(a)))
    pd.DataFrame(rows).to_csv(out / "h3_adaptation.csv", index=False)
    h4 = []
    for (fs, rep, pred), (S, phi, margin) in keep.items():
        if fs != "AC2":
            continue
        d = S.assign(margin=margin)
        d = d[(d.variant == "C2") & d.c2_class.isin(["adapted", "persisted_original"]) & d.margin.notna()]
        for scope, g in [("pooled_nondegenerate", d[~d.model.isin(DEGENERATE)])] + [(m, x) for m, x in d.groupby("model")]:
            y = (g.c2_class == "adapted").astype(int).to_numpy()
            if 0 < y.sum() < len(y):
                # within-model centring of the margin so pooling does not mix model base rates
                z = (g.margin - g.groupby("model").margin.transform("mean")).to_numpy()
                auc = roc_auc_score(y, z)
                tasks = g.instance_id.unique()
                bs = []
                for _ in range(n_boot // 4):
                    gg = pd.concat([g[g.instance_id == t] for t in RNG.choice(tasks, len(tasks))])
                    yy = (gg.c2_class == "adapted").astype(int).to_numpy()
                    if 0 < yy.sum() < len(yy):
                        bs.append(roc_auc_score(yy, (gg.margin - gg.groupby("model").margin.transform("mean")).to_numpy()))
                h4.append(dict(rep=rep, predictor=pred, scope=scope, n_adapted=int(y.sum()), n_persisted=int(len(y) - y.sum()),
                               auc_adapted_vs_persisted=auc, ci_lo=np.nanquantile(bs, .025) if bs else np.nan,
                               ci_hi=np.nanquantile(bs, .975) if bs else np.nan))
    pd.DataFrame(h4).to_csv(out / "h4_adaptation_auc.csv", index=False)


def c1(T, out, n_boot):
    C = T[T.variant == "C1"]
    rows = []
    for m, g in C.groupby("model"):
        for cls in sorted(C.c1_class.dropna().unique()):
            mu, lo, hi = rate_ci(g.assign(x=g.c1_class == cls), "x", n_boot)
            rows.append(dict(model=m, c1_class=cls, mean=mu, ci_lo=lo, ci_hi=hi, n=len(g)))
        mu, lo, hi = rate_ci(g.assign(x=g.c1_correct_decision.astype(float)), "x", n_boot)
        rows.append(dict(model=m, c1_class="correct_decision_any_format", mean=mu, ci_lo=lo, ci_hi=hi, n=len(g)))
    pd.DataFrame(rows).to_csv(out / "c1_decisions.csv", index=False)


# ------------------------------------------------------------------ sensitivity
def sensitivity(T, out, n_real):
    rows = []
    variants = [("drop_context_overflow", T[~T.context_overflow]),
                ("final_state_correctness", T.assign(resolved=T.resolved_state.astype("boolean").fillna(T.resolved).astype(bool))
                 if "resolved_state" in T else None)]
    for name, S0 in variants:
        if S0 is None:
            continue
        S = S0[S0.variant == "A"].reset_index(drop=True)
        if S.resolved.nunique() < 2:
            continue
        for s in range(min(n_real, 3)):
            phi, margin, yy = oof(S, "r2", "lgbm_paper", s)
            ok = ~np.isnan(margin)
            r = dict(sensitivity=name, seed=s, n=len(S),
                     auc_pooled=roc_auc_score(yy[ok], margin[ok]) if 0 < yy[ok].sum() < ok.sum() else np.nan)
            for m in S.model.unique():
                g = np.flatnonzero((S.model.values == m) & ok)
                r[f"bcm|{m}"] = bcm(phi[g]) if len(g) > 1 else np.nan
            rows.append(r)
    pd.DataFrame(rows).to_csv(out / "s_sensitivity.csv", index=False)


def main(in_dir, out_dir, n_real=10, n_null=50, n_boot=2000):
    n_real, n_null, n_boot = int(n_real), int(n_null), int(n_boot)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    T = pd.read_parquet(Path(in_dir) / "attempts.parquet").sort_values("run_id").reset_index(drop=True)
    print(f0(T, out).to_string(), flush=True)
    keep, quarantine = f1(T, out, n_real, n_null, n_boot)
    P = pairs(T, keep)
    P.to_parquet(out / "pairs.parquet")
    cross_task_cos(T, keep, out)
    f2_h1(T, P, out, n_boot)
    h2(T, P, out, n_boot)
    h3_h4(T, keep, out, n_boot)
    c1(T, out, n_boot)
    sensitivity(T, out, n_real)
    json.dump(dict(n_attempts=len(T), models=sorted(T.model.unique()), variants=sorted(T.variant.unique()),
                   n_tasks=int(T.instance_id.nunique()), n_pairs=len(P), quarantined=[list(q) for q in sorted(quarantine)],
                   n_real=n_real, n_null=n_null, n_boot=n_boot), open(out / "meta.json", "w"), indent=1)
    print("done ->", out, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
