"""Exp03 pilot analysis (gate G4): BCM, nulls, repeatability, invariance and adaptation contrasts.

Inputs: <in_dir>/attempts.parquet from bcm03.ingest.
BCM fits use the same estimator code as Exp02 (bcm02.pipeline.fit_predict; released LightGBM config and
standardised logistic), pooled over models as in the paper, task-grouped 5-fold CV (all variants of a task are
in the same fold, so no variant leaks its task into training). Two fit sets:
  AB = variants A + B1 (task-preserving; label = resolved),
  AC = variants A + C1 (task-changing; label = resolved, i.e. "tests pass after the agent's patch").
Ground-truth behaviour never uses BCM: category-sequence similarity (1 - normalised Levenshtein), Jaccard
of edited files and functions, outcome agreement, C1 decision (no edit of the gold-patch files).
Usage: python -m bcm03.analysis <in_dir> <out_dir> [n_real_seeds] [n_null_seeds]
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

from bcm02.pipeline import BCM12, SEM, bcm, fit_predict, permute

FEATS = {"r2": [f"r2_{f}" for f in BCM12], "r3": SEM}
FITSETS = {"AB": ["A", "B1"], "AC": ["A", "C1"]}
B = 2000


# ------------------------------------------------------------------ similarity measures (BCM-independent)
def lev_sim(a, b):
    a, b = a.split("|") if a else [], b.split("|") if b else []
    if not a and not b:
        return 1.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))


def jacc(a, b):
    a, b = set(filter(None, a.split("|"))), set(filter(None, b.split("|")))
    return 1.0 if not a and not b else len(a & b) / len(a | b)


BEH = {"seq_sim": lambda r, s: lev_sim(r.cat_seq, s.cat_seq),
       "file_jacc": lambda r, s: jacc(r.edited_files, s.edited_files),
       "func_jacc": lambda r, s: jacc(r.edited_funcs, s.edited_funcs),
       "outcome_agree": lambda r, s: float(r.resolved == s.resolved)}


def unit(phi):
    n = np.linalg.norm(phi, axis=1, keepdims=True)
    return np.where(n > 1e-9, phi / np.where(n > 1e-9, n, 1), np.nan)


# ------------------------------------------------------------------ attribution fits
def oof(T, rep, pred, seed, y=None):
    X = T[FEATS[rep]].to_numpy(float)
    y = T.resolved.to_numpy(int) if y is None else y
    g = T.instance_id.values
    phi, margin = np.full(X.shape, np.nan), np.full(len(y), np.nan)
    k = min(5, len(set(g)))
    if k < 2:
        return phi, margin, y
    for tr, va in StratifiedGroupKFold(k, shuffle=True, random_state=seed).split(X, y, g):
        if len(set(y[tr])) < 2:          # single-class training fold: attribution undefined
            continue
        p, m, _, _ = fit_predict(pred, X[tr], y[tr], X[va], g[tr], 8)
        phi[va], margin[va] = p, m
    return phi, margin, y


def a1_bcm(T, out, n_real, n_null):
    rows, keep = [], {}
    for fs, variants in FITSETS.items():
        S = T[T.variant.isin(variants)].reset_index(drop=True)
        for rep, pred in [("r2", "lgbm_paper"), ("r2", "logistic"), ("r3", "lgbm_paper")]:
            for scheme, seeds in [("real", range(n_real)), ("perm_model", range(1000, 1000 + n_null))]:
                for s in seeds:
                    y = None
                    if scheme == "perm_model":
                        y = permute(S.resolved.to_numpy(int), S.model.values, np.random.default_rng(s))
                    phi, margin, yy = oof(S, rep, pred, s if scheme == "real" else 0, y)
                    ok = ~np.isnan(margin)
                    r = dict(fitset=fs, rep=rep, predictor=pred, scheme=scheme, seed=s, n=len(S), n_scored=int(ok.sum()),
                             auc=roc_auc_score(yy[ok], margin[ok]) if ok.any() and 0 < yy[ok].sum() < ok.sum() else np.nan)
                    for m, g in S.groupby("model").groups.items():
                        g = np.asarray(g)
                        gg = g[ok[g]]
                        r[f"bcm|{m}"] = bcm(phi[gg]) if len(gg) > 1 else np.nan
                        for v in variants:
                            gv = gg[S.variant.values[gg] == v]
                            r[f"bcm_{v}|{m}"] = bcm(phi[gv]) if len(gv) > 1 else np.nan
                    rows.append(r)
                    if scheme == "real" and s == 0:
                        keep[(fs, rep, pred)] = (S, phi)
    R = pd.DataFrame(rows)
    R.to_csv(out / "a1_bcm_runs.csv", index=False)
    cols = [c for c in R.columns if c.startswith("bcm")]
    L = R.melt(id_vars=["fitset", "rep", "predictor", "scheme", "seed"], value_vars=cols, var_name="k", value_name="bcm")
    L[["subset", "model"]] = L.k.str.split("|", expand=True)
    real = L[L.scheme == "real"].groupby(["fitset", "rep", "predictor", "subset", "model"]).bcm.agg(["mean", "std"])
    null = L[L.scheme == "perm_model"].groupby(["fitset", "rep", "predictor", "subset", "model"]).bcm.agg(
        null_mean="mean", null_q025=lambda x: x.quantile(.025), null_q975=lambda x: x.quantile(.975))
    S = real.join(null).reset_index()
    S["real_minus_null"] = S["mean"] - S.null_mean
    S.to_csv(out / "a1_bcm_summary.csv", index=False)
    return keep


# ------------------------------------------------------------------ repeatability, invariance, adaptation
def pair_table(T, keep):
    """One row per unordered pair of attempts of the same model and task; behaviour + attribution similarity."""
    U = {}
    for (fs, rep, pred), (S, phi) in keep.items():
        u = unit(phi)
        U[(fs, rep, pred)] = {rid: u[i] for i, rid in enumerate(S.run_id)}
    rows = []
    for (m, t), g in T.groupby(["model", "instance_id"]):
        recs = list(g.itertuples())
        for r, s in itertools.combinations(recs, 2):
            kind = "".join(sorted([r.variant, s.variant], key=lambda v: {"A": 0, "B1": 1, "C1": 2}[v]))
            kind = {"AA": "AA", "B1B1": "BB", "C1C1": "CC", "AB1": "AB", "AC1": "AC", "B1C1": "BC"}[kind]
            row = dict(model=m, instance_id=t, repo=r.repo, kind=kind, a=r.run_id, b=s.run_id)
            for k, f in BEH.items():
                row[k] = f(r, s)
            for key, d in U.items():
                fs = key[0]
                if set([r.variant, s.variant]) <= set(FITSETS[fs]):
                    row[f"cos|{'|'.join(key)}"] = float(np.dot(d[r.run_id], d[s.run_id]))
            rows.append(row)
    return pd.DataFrame(rows)


def boot_mean(df, col, by="instance_id", seed=0):
    d = df.dropna(subset=[col])
    if d.empty:
        return np.nan, np.nan, np.nan
    per = d.groupby(by)[col].mean().to_numpy()
    rng = np.random.default_rng(seed)
    bs = per[rng.integers(0, len(per), (B, len(per)))].mean(1)
    return float(per.mean()), float(np.quantile(bs, .025)), float(np.quantile(bs, .975))


def a2_repeatability(P, out):
    """H1: across (model, task, variant) cells, does attribution repeatability track behavioural repeatability?"""
    same = P[P.kind.isin(["AA", "BB", "CC"])]
    cell = same.groupby(["model", "instance_id", "kind"]).mean(numeric_only=True).reset_index()
    cell.to_csv(out / "a2_cells.csv", index=False)
    rows = []
    for c in [c for c in cell.columns if c.startswith("cos|")]:
        for b in BEH:
            d = cell.dropna(subset=[c, b])
            if len(d) < 5 or d[b].nunique() < 2:
                continue
            rho = spearmanr(d[c], d[b]).statistic
            tasks = d.instance_id.unique()
            rng = np.random.default_rng(0)
            bs = []
            for _ in range(B):
                pick = rng.choice(tasks, len(tasks))
                dd = pd.concat([d[d.instance_id == t] for t in pick])
                if dd[b].nunique() > 1 and dd[c].nunique() > 1:
                    bs.append(spearmanr(dd[c], dd[b]).statistic)
            rows.append(dict(attribution=c, behaviour=b, n_cells=len(d), spearman=rho,
                             ci_lo=np.nanquantile(bs, .025), ci_hi=np.nanquantile(bs, .975)))
    pd.DataFrame(rows).to_csv(out / "a2_h1_spearman.csv", index=False)


def a3_contrasts(P, out):
    """H2/H3: within-A similarity vs A-B1 (should be equal) vs A-C1 (should differ), per model, task-clustered."""
    rows = []
    cols = list(BEH) + [c for c in P.columns if c.startswith("cos|")]
    for m, g in P.groupby("model"):
        for col in cols:
            for kind in ["AA", "AB", "AC", "BB", "CC"]:
                mu, lo, hi = boot_mean(g[g.kind == kind], col)
                rows.append(dict(model=m, measure=col, kind=kind, mean=mu, ci_lo=lo, ci_hi=hi))
            # paired by task: delta = sim(AA) - sim(A x variant)
            per = g.groupby(["instance_id", "kind"])[col].mean().unstack()
            for v in ["AB", "AC"]:
                if {"AA", v} <= set(per.columns):
                    dd = (per["AA"] - per[v]).dropna().to_numpy()
                    if len(dd):
                        bs = dd[np.random.default_rng(0).integers(0, len(dd), (B, len(dd)))].mean(1)
                        rows.append(dict(model=m, measure=col, kind=f"AA-{v}", mean=dd.mean(),
                                         ci_lo=np.quantile(bs, .025), ci_hi=np.quantile(bs, .975), n_tasks=len(dd)))
    pd.DataFrame(rows).to_csv(out / "a3_contrasts.csv", index=False)


def a4_adaptation(T, out):
    """C1 'already fixed': correct decision = leave the gold-patch files functionally unchanged and keep tests passing."""
    T = T.assign(c1_correct=lambda d: (~d.touches_gold_file) & d.resolved)
    S = T.groupby(["model", "variant"]).agg(
        n=("run_id", "size"), resolved=("resolved", "mean"), touches_gold_file=("touches_gold_file", "mean"),
        c1_correct=("c1_correct", "mean"), changed_lines=("n_changed_lines", "median"), steps=("n_steps", "mean"),
        submitted=("exit_status", lambda s: (s == "Submitted").mean()), ran_tests=("ran_tests", "mean")).reset_index()
    S.to_csv(out / "a4_adaptation.csv", index=False)


def a0_summary(T, out):
    S = T.groupby(["model", "variant"]).agg(
        n=("run_id", "size"), resolved=("resolved", "mean"),
        exit_submitted=("exit_status", lambda s: (s == "Submitted").mean()),
        exit_limits=("exit_status", lambda s: (s == "LimitsExceeded").mean()),
        steps=("n_steps", "mean"), format_compliance=("format_compliance", "mean"),
        agent_seconds=("agent_seconds", "mean")).reset_index()
    solved = T[T.resolved].groupby(["model", "variant"]).instance_id.nunique()
    S["n_tasks_solved"] = [solved.get((m, v), 0) for m, v in zip(S.model, S.variant)]
    S.to_csv(out / "a0_summary.csv", index=False)
    return S


def main(in_dir, out_dir, n_real=10, n_null=50):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    T = pd.read_parquet(Path(in_dir) / "attempts.parquet")
    T = T.sort_values("run_id").reset_index(drop=True)
    print(a0_summary(T, out).to_string())
    a4_adaptation(T, out)
    keep = a1_bcm(T, out, int(n_real), int(n_null))
    P = pair_table(T, keep)
    P.to_parquet(out / "pairs.parquet")
    a2_repeatability(P, out)
    a3_contrasts(P, out)
    json.dump(dict(n_attempts=len(T), models=sorted(T.model.unique()), n_pairs=len(P)), open(out / "meta.json", "w"))
    print("done ->", out)


if __name__ == "__main__":
    main(*sys.argv[1:])
