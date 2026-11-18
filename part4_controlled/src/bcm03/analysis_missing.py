"""Exp03 full study: the six pre-registered outputs missing from bcm03.analysis_full (FULL_STUDY_RESULTS.md §9).

Reads the ingest (<in_dir>/attempts.parquet) and the analysis_full outputs (<out_dir>/pairs.parquet, h1/f1 CSVs used as
reference checks). Writes only new files into <out_dir>; nothing produced by analysis_full is overwritten.

  1 h1_gap.csv              H1 trace reference: Δ = r_w(seq_sim) − r_w(y), task-cluster bootstrap (joint resamples).
  2 h1_partial.csv          H1 partial within-cell r(cos, y | fsim), fsim = cosine of the two attempts' z-scored R2
                            feature vectors (z over all A attempts), as in scripts/full/measure_validity.py (P3.10).
  3 s_repo_bootstrap.csv    Repository-cluster bootstrap (plan §8) of the primary endpoints: H1 r_w and Δ, per-model
                            BCM (A fit, R2, released LightGBM, CV seed 0), H2 D for the 4 co-primary measures.
  4 s_gpu_covariate.csv     GPU type as a covariate of repeatability (plan §8, P3.15); estimable only within a model.
  5 s_h2_b2_unflagged.csv   H2 on B2 tasks that neither AI-review pass flagged as adding information (plan §8);
                            the flagged complement is reported alongside (descriptive).
  6 s_selection.csv         Accepted vs rejected B2/C2 main tasks on A solve and edit rate (plan §8), and
    s_acceptance_strata.csv acceptance rates by repository and by difficulty.
Within-cell correlations are bootstrapped from per-cluster sufficient statistics (cell-centred cross-product sums), which
is exact for cluster resampling because a resampled copy of a cell has the same centred values.
Usage: python -m bcm03.analysis_missing <in_dir> <out_dir> [n_boot=2000]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from bcm02.pipeline import bcm
from bcm03.analysis import FEATS, oof
from bcm03.analysis_full import DEGENERATE, MARGIN, h2

ROOT = Path(__file__).resolve().parents[2]
RNG = np.random.default_rng(20261103)
COPRIMARY_H1 = ["patch_sim_cond", "f2p_agree"]
H1_Y = ["patch_sim_cond", "f2p_agree", "edit_decision_agree", "func_jacc_cond", "outcome_concord", "seq_sim"]
COS_A = ["cos|A|r2|lgbm_paper", "cos|A|r2|logistic", "cos|A|r3|lgbm_paper"]
H2_COPRIMARY = ["patch_sim_cond", "f2p_agree", "seq_sim", "cos|AB2|r2|lgbm_paper"]
Q = {"lo": .025, "hi": .975, "lo_bonf": .0125, "hi_bonf": .9875}


# ------------------------------------------------------------------ cluster-bootstrap machinery
def weights(clusters, n_boot):
    """(n_boot x k) multinomial resample counts over k clusters."""
    k = len(clusters)
    return np.stack([np.bincount(RNG.integers(0, k, k), minlength=k) for _ in range(n_boot)]).astype(float)


def centred_moments(d, cols, cluster, clusters):
    """Per-cluster sums of products of cell-centred columns: array (k, p, p)."""
    X = (d[cols] - d.groupby("cell")[cols].transform("mean")).to_numpy(float)
    idx = pd.Index(clusters).get_indexer(d[cluster])
    M = np.zeros((len(clusters), len(cols), len(cols)))
    np.add.at(M, idx, X[:, :, None] * X[:, None, :])
    return M


def corr(M):
    """Correlation matrix (..., p, p) from summed cross products."""
    s = np.sqrt(np.einsum("...ii->...i", M))
    with np.errstate(invalid="ignore", divide="ignore"):    # degenerate resamples (no within-cell variance) -> NaN
        return M / (s[..., :, None] * s[..., None, :])


def partial(R):
    """partial r(0,1 | 2) from a (..., 3, 3) correlation matrix."""
    r01, r02, r12 = R[..., 0, 1], R[..., 0, 2], R[..., 1, 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        return (r01 - r02 * r12) / np.sqrt((1 - r02 ** 2) * (1 - r12 ** 2))


def qs(b, prefix=""):
    return {f"{prefix}{k}": float(np.nanquantile(b, q)) for k, q in Q.items()}


def aa_pairs(P, T):
    A = P[P.kind == "AA"].copy()
    A["cell"] = A.model + "|" + A.instance_id
    # fsim: cosine of z-scored R2 feature vectors (z over all A attempts), as in measure_validity.py
    TA = T[T.variant == "A"].set_index("run_id")
    F = FEATS["r2"]
    Z = ((TA[F] - TA[F].mean()) / TA[F].std().replace(0, 1)).fillna(0)
    u, v = Z.loc[A.a].to_numpy(), Z.loc[A.b].to_numpy()
    A["fsim"] = (u * v).sum(1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1) + 1e-9)
    return A


def scopes(A):
    return [("pooled_nondegenerate", A[~A.model.isin(DEGENERATE)])] + [(m, g) for m, g in A.groupby("model")]


# ------------------------------------------------------------------ 1 + 2 + 3a: H1 gap, partial r, repo bootstrap of H1
def h1_extra(A, out, n_boot, ref):
    gap, par, repo = [], [], []
    for c in COS_A:
        for scope, d0 in scopes(A):
            for unit in ["instance_id", "repo"]:
                cl = np.array(sorted(d0[unit].unique()))
                W = weights(cl, n_boot)
                # r_w for every y on its own available pairs, bootstrapped with the same cluster weights
                rw, rb = {}, {}
                for y in H1_Y:
                    d = d0.dropna(subset=[c, y])
                    if len(d) < 10:
                        continue
                    M = centred_moments(d, [c, y], unit, cl)
                    rw[y] = float(corr(M.sum(0))[0, 1])
                    rb[y] = corr(np.einsum("bk,kij->bij", W, M))[:, 0, 1]
                if unit == "instance_id" and c == "cos|A|r2|lgbm_paper" and scope == "pooled_nondegenerate":
                    for y, r in rw.items():          # point estimates must equal analysis_full's h1 table
                        assert abs(r - ref[y]) < 1e-9, (y, r, ref[y])
                for y in [k for k in rw if k != "seq_sim"]:
                    if "seq_sim" not in rw:
                        continue
                    row = dict(attribution=c, behaviour=y, scope=scope, resampling=unit, n_clusters=len(cl),
                               r_w_seq_sim=rw["seq_sim"], r_w_y=rw[y], gap=rw["seq_sim"] - rw[y],
                               **qs(rb["seq_sim"] - rb[y], "gap_"))
                    (gap if unit == "instance_id" else repo).append(dict(row, endpoint="h1_gap"))
                if unit == "repo":
                    for y, r in rw.items():
                        repo.append(dict(attribution=c, behaviour=y, scope=scope, resampling=unit, n_clusters=len(cl),
                                         endpoint="h1_r_w", estimate=r, **qs(rb[y])))
                    continue
                # partial r(cos, y | fsim), task-cluster bootstrap
                for y in H1_Y:
                    d = d0.dropna(subset=[c, y, "fsim"])
                    if len(d) < 10:
                        continue
                    M = centred_moments(d, [c, y, "fsim"], unit, cl)
                    R, Rb = corr(M.sum(0)), corr(np.einsum("bk,kij->bij", W, M))
                    par.append(dict(attribution=c, behaviour=y, scope=scope, n_pairs=len(d), n_tasks=d.instance_id.nunique(),
                                    r_w=R[0, 1], r_fsim_y=R[1, 2], r_cos_fsim=R[0, 2], partial_r=float(partial(R)),
                                    **qs(partial(Rb), "partial_"), co_primary=y in COPRIMARY_H1))
    pd.DataFrame(gap).to_csv(out / "h1_gap.csv", index=False)
    pd.DataFrame(par).to_csv(out / "h1_partial.csv", index=False)
    return repo


# ------------------------------------------------------------------ 3b: repo bootstrap of BCM
def bcm_repo(T, n_boot, ref):
    S = T[T.variant == "A"].reset_index(drop=True)          # identical to analysis_full.f1 fit set "A"
    phi, margin, _ = oof(S, "r2", "lgbm_paper", 0)
    ok = ~np.isnan(margin)
    rows = []
    for m in sorted(S.model.unique()):
        g = np.flatnonzero((S.model.values == m) & ok)
        est = bcm(phi[g])
        assert abs(est - ref[m]) < 1e-9, (m, est, ref[m])   # must reproduce f1_bcm_runs (A, r2, lgbm_paper, real, seed 0)
        idx = np.flatnonzero((S.model.values == m) & ~np.isnan(phi).any(1))
        repos = S.repo.values[idx]
        ur = np.unique(repos)
        grp = [idx[repos == r] for r in ur]
        bs = [bcm(phi[np.concatenate([grp[i] for i in RNG.integers(0, len(ur), len(ur))])]) for _ in range(n_boot)]
        rows.append(dict(endpoint="bcm", attribution="A|r2|lgbm_paper", scope=m, resampling="repo", n_clusters=len(ur),
                         estimate=est, **qs(bs)))
    return rows


# ------------------------------------------------------------------ 3c: repo bootstrap of H2 D
def h2_repo(P, n_boot):
    rows = []
    for col in H2_COPRIMARY:
        per = P[P.kind.isin(["AA", "AB2"])].groupby(["model", "instance_id", "repo", "kind"])[col].mean().unstack()
        D = (per["AA"] - per["AB2"]).dropna().rename("D").reset_index()
        for scope, d in [("pooled_nondegenerate", D[~D.model.isin(DEGENERATE)].groupby(["instance_id", "repo"]).D.mean().reset_index())] + \
                        [(m, g) for m, g in D.groupby("model")]:
            ur = np.array(sorted(d.repo.unique()))
            grp = [d.D.values[d.repo.values == r] for r in ur]
            bs = [np.concatenate([grp[i] for i in RNG.integers(0, len(ur), len(ur))]).mean() for _ in range(n_boot)]
            q = qs(bs)
            mg = MARGIN.get(col.split("|")[0], 0.05)
            rows.append(dict(endpoint="h2_D_B2", attribution=col if col.startswith("cos") else "", behaviour=col, scope=scope,
                             resampling="repo", n_clusters=len(ur), estimate=d.D.mean(), **q, margin=mg,
                             equivalent_bonf=bool(-mg < q["lo_bonf"] and q["hi_bonf"] < mg)))
    return rows


# ------------------------------------------------------------------ 4: GPU covariate
def gpu_covariate(T, A, out, n_boot):
    rows = []
    for m, g in T.groupby("model"):
        types = g.gpu.value_counts()
        base = dict(model=m, gpu_types="; ".join(f"{k}: {v}" for k, v in types.items()), n_gpu_types=len(types))
        if len(types) < 2:
            rows.append(dict(base, estimable=False, reason="one GPU type for every attempt of this model; covariate is constant"))
            continue
        gp = T.set_index("run_id").gpu
        d0 = A[A.model == m].assign(same_gpu=lambda x: (gp.loc[x.a].values == gp.loc[x.b].values).astype(float))
        for y in H1_Y:
            d = d0.dropna(subset=[y])
            cl = np.array(sorted(d.instance_id.unique()))
            M = centred_moments(d, [y, "same_gpu"], "instance_id", cl)
            if M[:, 1, 1].sum() == 0:
                rows.append(dict(base, measure=y, estimable=False, reason="same_gpu constant within every task"))
                continue
            Mb = np.einsum("bk,kij->bij", weights(cl, n_boot), M)
            slope = lambda X: X[..., 0, 1] / X[..., 1, 1]    # within-task difference same-GPU minus mixed-GPU pairs
            rows.append(dict(base, measure=y, estimable=True, within_task_diff_same_minus_mixed=float(slope(M.sum(0))),
                             **qs(slope(Mb))))
    pd.DataFrame(rows).to_csv(out / "s_gpu_covariate.csv", index=False)


# ------------------------------------------------------------------ 5: H2 on unflagged B2 tasks
def b2_flags(tasks):
    """True if at least one AI-review pass says the B2 rewrite added information."""
    f = {}
    for t in tasks:
        passes = [json.loads(p.read_text())["parsed"] for p in sorted((ROOT / f"data/variants_full/{t}/review").glob("B2.p*.json"))]
        assert len(passes) == 2, (t, len(passes))
        f[t] = any(p.get("information_added", "none") != "none" for p in passes)
    return f


def h2_unflagged(T, P, out, n_boot):
    flag = b2_flags(sorted(T[T.variant == "B2"].instance_id.unique()))
    res = []
    for subset, keep in [("unflagged", {t for t, v in flag.items() if not v}), ("flagged", {t for t, v in flag.items() if v})]:
        T2 = T[(T.variant == "A") | ((T.variant == "B2") & T.instance_id.isin(keep))]
        P2 = P[(P.kind == "AA") | ((P.kind == "AB2") & P.instance_id.isin(keep))]
        tmp = out / f"_tmp_h2_{subset}"
        tmp.mkdir(exist_ok=True)
        h2(T2, P2, tmp, n_boot)
        r = pd.read_csv(tmp / "h2_invariance.csv")
        (tmp / "h2_invariance.csv").unlink()
        tmp.rmdir()
        res.append(r.assign(subset=subset, n_tasks_subset=len(keep), co_primary=r.measure.isin(H2_COPRIMARY)))
    pd.concat(res).to_csv(out / "s_h2_b2_unflagged.csv", index=False)
    return {k: int(v) for k, v in pd.Series(flag).value_counts().items()}


# ------------------------------------------------------------------ 6: selection
def selection(T, out, n_boot):
    meta = json.loads((ROOT / "configs/full/manifests/confirmatory_v1.csv.meta.json").read_text())["tasksets"]
    main = meta["main"]
    diff = pd.read_csv(ROOT / "configs/full/task_order.csv").drop_duplicates("instance_id").set_index("instance_id").difficulty
    acc = pd.DataFrame(dict(instance_id=main, B2=[t in set(meta["B2"]) for t in main], C2=[t in set(meta["C2"]) for t in main]))
    A = T[(T.variant == "A") & T.instance_id.isin(main)]
    acc["repo"] = acc.instance_id.map(A.drop_duplicates("instance_id").set_index("instance_id").repo)
    acc["difficulty"] = acc.instance_id.map(diff)
    rows = []
    for scope, g in [("pooled_nondegenerate", A[~A.model.isin(DEGENERATE)])] + [(m, x) for m, x in A.groupby("model")]:
        cell = g.groupby("instance_id")[["resolved", "edited"]].mean().astype(float).reindex(main)
        for v in ["B2", "C2"]:
            a = acc.set_index("instance_id")[v]
            for meas, col in [("A_solve_rate", "resolved"), ("A_edit_rate", "edited")]:
                x, y = cell[col][a].dropna().to_numpy(), cell[col][~a].dropna().to_numpy()
                bs = [RNG.choice(x, len(x)).mean() - RNG.choice(y, len(y)).mean() for _ in range(n_boot)]
                rows.append(dict(variant=v, scope=scope, measure=meas, n_accepted=len(x), n_rejected=len(y),
                                 accepted_mean=x.mean(), rejected_mean=y.mean(), diff_accepted_minus_rejected=x.mean() - y.mean(),
                                 **qs(bs, "diff_")))
    pd.DataFrame(rows).to_csv(out / "s_selection.csv", index=False)
    st = []
    for by in ["repo", "difficulty"]:
        for k, g in acc.groupby(by):
            st.append(dict(stratum_type=by, stratum=k, n_main_tasks=len(g), B2_accepted=int(g.B2.sum()), B2_rate=g.B2.mean(),
                           C2_accepted=int(g.C2.sum()), C2_rate=g.C2.mean()))
    st.append(dict(stratum_type="all", stratum="all", n_main_tasks=len(acc), B2_accepted=int(acc.B2.sum()), B2_rate=acc.B2.mean(),
                   C2_accepted=int(acc.C2.sum()), C2_rate=acc.C2.mean()))
    pd.DataFrame(st).to_csv(out / "s_acceptance_strata.csv", index=False)


def main(in_dir, out_dir, n_boot=2000, skip_fit=False):
    n_boot, out = int(n_boot), Path(out_dir)
    T = pd.read_parquet(Path(in_dir) / "attempts.parquet").sort_values("run_id").reset_index(drop=True)
    P = pd.read_parquet(out / "pairs.parquet")
    h1 = pd.read_csv(out / "h1_attribution_vs_behaviour.csv")
    ref_h1 = h1[(h1.scope == "pooled_nondegenerate") & (h1.attribution == "cos|A|r2|lgbm_paper")].set_index("behaviour").within_r
    f1 = pd.read_csv(out / "f1_bcm_runs.csv")
    r0 = f1[(f1.fitset == "A") & (f1.rep == "r2") & (f1.predictor == "lgbm_paper") & (f1.scheme == "real") & (f1.seed == 0)].iloc[0]
    ref_bcm = {c.split("|")[1]: r0[c] for c in f1.columns if c.startswith("bcm|")}
    A = aa_pairs(P, T)
    repo = h1_extra(A, out, n_boot, ref_h1)
    print("h1 done", flush=True)
    if not skip_fit:
        repo += bcm_repo(T, n_boot, ref_bcm)
    print("bcm done", flush=True)
    repo += h2_repo(P, n_boot)
    pd.DataFrame(repo).to_csv(out / "s_repo_bootstrap.csv", index=False)
    gpu_covariate(T, A, out, n_boot)
    flags = h2_unflagged(T, P, out, n_boot)
    selection(T, out, n_boot)
    json.dump(dict(n_boot=n_boot, seed=20261103, skip_fit=bool(skip_fit), b2_flag_counts=flags,
                   files=["h1_gap.csv", "h1_partial.csv", "s_repo_bootstrap.csv", "s_gpu_covariate.csv", "s_h2_b2_unflagged.csv",
                          "s_selection.csv", "s_acceptance_strata.csv"]), open(out / "meta_missing.json", "w"), indent=1)
    print("done ->", out, flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(*[x for x in a if x != "--skip-fit"], skip_fit="--skip-fit" in a)
