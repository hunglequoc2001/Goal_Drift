"""Exp02 analysis: aggregate pipeline runs into tables (results/tables/a_*.csv).

A1 main BCM table (mean and range over CV seeds) per cohort x representation x predictor
A2 paired task-cluster bootstrap (2000, seed 20261026) on fixed seed-0 OOF attributions: per-model BCM CI,
   pairwise differences, rank probabilities
A3 ranking stability across all real configurations (Kendall tau vs reference; pairwise flip rates)
A4 label-permutation controls: real vs null (median, 5-95%, add-one one-sided p)
A5 BCM vs within-model AUC across configurations (descriptive)
A6 matched-task cross-model attribution similarity: same task vs different task (descriptive)
A7 confounders: per-trajectory alignment with the model's mean attribution direction vs outcome, repo,
   language, reference-patch size, steps, exit status (OLS, task-clustered SEs)
Usage: python -m bcm02.analysis
"""
import glob
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import kendalltau

from .pipeline import COHORTS, feature_cols, load_cohort

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "results/runs"
OUT = ROOT / "results/tables"
SHORT = {"gpt-5-250-turns-10132025": "GPT-5", "claude-45sonnet-10132025": "Sonnet-4.5",
         "claude-45haiku-10222025": "Haiku-4.5", "glm-4p5-10222025": "GLM-4.5",
         "gemini-2-5-pro-preview-250-turns-debug-oct22": "Gemini-2.5-Pro", "claude-4sonnet-10132025": "Sonnet-4",
         "gpt-5-high-paper": "GPT-5-high", "gptoss-paper": "gpt-oss-120b", "kimi-paper": "Kimi-K2",
         "claude-opus-4-1-paper": "Sonnet-4 (paper)", "claude-sonnet-4-paper": "Opus-4.1 (paper)",
         "gemini-2-5-pro-preview-paper": "Gemini-2.5-Pro (paper)", "gpt-4o-paper": "GPT-4o (paper)"}
REP = {"r0": "R0 author SWE-smith loader", "r1": "R1 author all-messages loader", "r2": "R2 role-aware",
       "r3": "R3 tool-semantic"}
B = 2000


def load_runs():
    d = pd.concat([pd.read_csv(f) for f in glob.glob(str(RUNS / "runs_*.csv"))], ignore_index=True)
    return d


def long_form(d):
    rows = []
    for _, r in d.iterrows():
        for run in COHORTS[r.cohort]:
            rows.append(dict(cohort=r.cohort, rep=r.rep, predictor=r.predictor, cv=r.cv, scheme=r.scheme,
                             seed=r.seed, run=run, model=SHORT[run], bcm=r[f"bcm|{run}"],
                             auc_within=r.get(f"auc_within|{run}", np.nan), auc_pooled=r.auc_pooled,
                             zero_steps=r.get(f"zero_steps|{run}", np.nan), max_add_err=r.max_add_err))
    return pd.DataFrame(rows)


def a1_main(L):
    real = L[L.scheme == "real"]
    t = real.groupby(["cohort", "rep", "predictor", "cv", "model"]).agg(
        bcm_mean=("bcm", "mean"), bcm_min=("bcm", "min"), bcm_max=("bcm", "max"), n_seeds=("seed", "nunique"),
        auc_within=("auc_within", "mean"), auc_pooled=("auc_pooled", "mean"), zero_steps=("zero_steps", "first"),
        max_add_err=("max_add_err", "max")).reset_index()
    t.to_csv(OUT / "a1_main_bcm.csv", index=False)
    return t


def units(phi):
    n = np.linalg.norm(phi, axis=1)
    ok = n > 1e-9
    u = np.zeros_like(phi)
    u[ok] = phi[ok] / n[ok, None]
    return u, ok


def bcm_w(u, ok, w):
    """BCM of a bootstrap multiset (row i drawn w_i times), averaging only over pairs of copies of
    DIFFERENT original rows: (||s||^2 - sum w_i^2) / (n^2 - sum w_i^2). Copy-pairs of the same row would
    add spurious cosine-1 pairs. With w = 1 this equals the plain BCM."""
    w = w * ok
    n = w.sum()
    w2 = (w * w).sum()
    if n * n - w2 <= 0:
        return np.nan
    s = (u * w[:, None]).sum(0)
    return float((s @ s - w2) / (n * n - w2))


def a2_bootstrap(cohort, rep, pred, seed=0):
    f = RUNS / f"oof_{cohort}_{rep}_{pred}_grouped5_s{seed}.npz"
    if not f.exists():
        return None, None
    z = np.load(f, allow_pickle=True)
    phi, inst, run = z["phi"], z["instance_id"], z["run"]
    tasks = np.unique(inst)
    tix = np.searchsorted(tasks, inst)
    runs = COHORTS[cohort]
    U = {r: units(phi[run == r]) for r in runs}
    T_of = {r: tix[run == r] for r in runs}
    rng = np.random.default_rng(20261026)
    point = {r: bcm_w(*U[r], np.ones(len(T_of[r]))) for r in runs}
    boot = np.zeros((B, len(runs)))
    for b in range(B):
        cnt = np.bincount(rng.integers(0, len(tasks), len(tasks)), minlength=len(tasks)).astype(float)
        for j, r in enumerate(runs):
            boot[b, j] = bcm_w(*U[r], cnt[T_of[r]])
    rows = []
    for j, r in enumerate(runs):
        rows.append(dict(cohort=cohort, rep=rep, predictor=pred, model=SHORT[r], bcm=point[r],
                         lo=np.nanquantile(boot[:, j], .025), hi=np.nanquantile(boot[:, j], .975),
                         p_rank1=float(np.mean(np.argmax(boot, 1) == j)),
                         mean_rank=float(np.mean((-boot).argsort(1).argsort(1)[:, j] + 1))))
    pairs = []
    for (i, a), (j, b2) in itertools.combinations(enumerate(runs), 2):
        dlt = boot[:, i] - boot[:, j]
        pairs.append(dict(cohort=cohort, rep=rep, predictor=pred, a=SHORT[a], b=SHORT[b2],
                          diff=point[a] - point[b2], lo=np.nanquantile(dlt, .025), hi=np.nanquantile(dlt, .975),
                          p_a_gt_b=float(np.mean(dlt > 0))))
    return pd.DataFrame(rows), pd.DataFrame(pairs)


def a3_ranking(L):
    real = L[(L.scheme == "real")]
    rows = []
    for cohort, g in real.groupby("cohort"):
        ref = g[(g.rep == "r2") & (g.predictor == "lgbm_paper") & (g.cv == "grouped5") & (g.seed == 0)]
        if ref.empty:
            continue
        ref = ref.set_index("model").bcm
        for key, h in g.groupby(["rep", "predictor", "cv", "seed"]):
            v = h.set_index("model").bcm.reindex(ref.index)
            rows.append(dict(cohort=cohort, rep=key[0], predictor=key[1], cv=key[2], seed=key[3],
                             kendall_tau_vs_ref=kendalltau(ref.values, v.values).statistic,
                             order=" > ".join(v.sort_values(ascending=False).index)))
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "a3_ranking_stability.csv", index=False)
    flips = []
    for cohort, g in real.groupby("cohort"):
        piv = g.pivot_table(index=["rep", "predictor", "cv", "seed"], columns="model", values="bcm")
        for a, b in itertools.combinations(piv.columns, 2):
            for rep in piv.index.get_level_values(0).unique():
                p = piv.loc[rep]
                flips.append(dict(cohort=cohort, rep=rep, a=a, b=b, n_configs=len(p),
                                  frac_a_gt_b=float((p[a] > p[b]).mean())))
    pd.DataFrame(flips).to_csv(OUT / "a3_pairwise_order_by_rep.csv", index=False)
    return R


def a4_nulls(L):
    rows = []
    for (cohort, rep, pred), g in L[L.cv == "grouped5"].groupby(["cohort", "rep", "predictor"]):
        real = g[(g.scheme == "real")].groupby("model").bcm.mean()   # mean over CV seeds
        real0 = g[(g.scheme == "real") & (g.seed == 0)].set_index("model").bcm
        for sch in ["perm_model", "perm_model_repo", "perm_global"]:
            n = g[g.scheme == sch]
            if n.empty:
                continue
            for m, nn in n.groupby("model"):
                v = nn.bcm.dropna().values
                rows.append(dict(cohort=cohort, rep=rep, predictor=pred, null=sch, model=m, n_perm=len(v),
                                 real_bcm_seedmean=real.get(m), real_bcm_seed0=real0.get(m),
                                 null_median=np.median(v), null_q05=np.quantile(v, .05), null_q95=np.quantile(v, .95),
                                 p_real_le_null=(1 + (v <= real0.get(m)).sum()) / (1 + len(v)),
                                 p_real_ge_null=(1 + (v >= real0.get(m)).sum()) / (1 + len(v)),
                                 null_auc_within_median=nn.auc_within.median()))
    N = pd.DataFrame(rows)
    N.to_csv(OUT / "a4_permutation_controls.csv", index=False)
    return N


def a5_bcm_vs_auc(L):
    x = L[(L.predictor.isin(["lgbm_paper", "logistic", "lgbm_tuned"])) & (L.cv == "grouped5")].copy()
    x = x.groupby(["cohort", "rep", "predictor", "scheme", "model"]).agg(bcm=("bcm", "mean"),
                                                                     auc_within=("auc_within", "mean")).reset_index()
    x.to_csv(OUT / "a5_bcm_vs_within_auc.csv", index=False)
    from scipy.stats import spearmanr
    rows = []
    for (sch, pred), g in x.groupby(["scheme", "predictor"]):
        if len(g) > 4:
            rows.append(dict(scheme=sch, predictor=pred, n=len(g),
                             spearman=spearmanr(g.bcm, g.auc_within, nan_policy="omit").statistic))
    pd.DataFrame(rows).to_csv(OUT / "a5_bcm_vs_within_auc_corr.csv", index=False)


def a6_cross_model(cohort="primary5", rep="r2", pred="lgbm_paper"):
    z = np.load(RUNS / f"oof_{cohort}_{rep}_{pred}_grouped5_s0.npz", allow_pickle=True)
    phi, inst, run = z["phi"], z["instance_id"], z["run"]
    u, ok = units(phi)
    T = load_cohort(cohort)
    feats = T[feature_cols(rep)].to_numpy(float)
    assert (T.instance_id.values == inst).all() and (T.run.values == run).all()
    zf = (feats - feats.mean(0)) / np.where(feats.std(0) > 0, feats.std(0), 1)
    uz, okz = units(zf)
    rows = []
    runs = COHORTS[cohort]
    for space, U in [("attribution", u), ("standardised_features", uz)]:
        for a, b in itertools.combinations_with_replacement(runs, 2):
            A, Bm = U[run == a], U[run == b]
            ia, ib = inst[run == a], inst[run == b]
            assert (ia == ib).all()
            C = A @ Bm.T
            same = np.diag(C)
            off = C[~np.eye(len(C), dtype=bool)]
            rows.append(dict(space=space, a=SHORT[a], b=SHORT[b], same_task_mean_cos=float(same.mean()) if a != b else np.nan,
                             diff_task_mean_cos=float(off.mean()), gap=(float(same.mean() - off.mean()) if a != b else np.nan)))
    R = pd.DataFrame(rows)
    R.to_csv(OUT / f"a6_cross_model_similarity_{cohort}_{rep}_{pred}.csv", index=False)
    return R


def a7_confounders(cohort="primary5", rep="r2", pred="lgbm_paper"):
    z = np.load(RUNS / f"oof_{cohort}_{rep}_{pred}_grouped5_s0.npz", allow_pickle=True)
    phi, run = z["phi"], z["run"]
    u, ok = units(phi)
    T = load_cohort(cohort)
    al = np.full(len(T), np.nan)
    for r in COHORTS[cohort]:
        m = (run == r) & ok
        mean_dir = u[m].mean(0)
        mean_dir /= np.linalg.norm(mean_dir)
        al[m] = u[m] @ mean_dir
    T["alignment"] = al
    T["model"] = T.run.map(SHORT)
    T["log_ref_lines"] = np.log1p(T.ref_patch_lines)
    T["log_steps"] = np.log1p(T[f"{rep}_total_steps"] if rep != "r3" else T.r3_n_steps)
    T["exit_clean"] = T.exit_status.fillna("").eq("submitted")
    T["resolved_i"] = T.resolved.astype(int)
    d = T.dropna(subset=["alignment"])
    f = "alignment ~ C(model) + resolved_i + C(repo_language) + log_ref_lines + log_steps + exit_clean"
    fit = smf.ols(f, d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.instance_id)[0]})
    co = fit.summary2().tables[1].reset_index().rename(columns={"index": "term"})
    co.to_csv(OUT / f"a7_alignment_ols_{cohort}_{rep}_{pred}.csv", index=False)
    by = d.groupby(["model", "repo"]).alignment.mean().unstack()
    by.to_csv(OUT / f"a7_alignment_by_repo_{cohort}_{rep}_{pred}.csv")
    var = d.groupby("model").apply(lambda g: pd.Series(dict(
        frac_var_between_repo=float(g.groupby("repo").alignment.transform("mean").var() / g.alignment.var()),
        mean_alignment=g.alignment.mean())), include_groups=False)
    var.to_csv(OUT / f"a7_alignment_variance_{cohort}_{rep}_{pred}.csv")
    return co, var


def main():
    d = load_runs()
    L = long_form(d)
    L.to_csv(OUT / "a0_long.csv", index=False)
    a1_main(L)
    bs, pr = [], []
    for cohort in COHORTS:
        for rep in ["r0", "r1", "r2", "r3"]:
            for pred in ["lgbm_paper", "logistic", "raw"]:
                b, p = a2_bootstrap(cohort, rep, pred)
                if b is not None:
                    bs.append(b)
                    pr.append(p)
    pd.concat(bs).to_csv(OUT / "a2_bootstrap_bcm.csv", index=False)
    pd.concat(pr).to_csv(OUT / "a2_bootstrap_pairwise.csv", index=False)
    a3_ranking(L)
    a4_nulls(L)
    a5_bcm_vs_auc(L)
    for rep in ["r0", "r2", "r3"]:
        a6_cross_model(rep=rep)
        a7_confounders(rep=rep)
    print("done")


if __name__ == "__main__":
    main()


def a8_mechanism(cohort, rep, pred="lgbm_paper"):
    """Which features carry each model's attribution mass, and how uniformly signed are they?
    share = fraction of total squared attribution norm; sign_agree = max(frac positive, frac negative)."""
    z = np.load(RUNS / f"oof_{cohort}_{rep}_{pred}_grouped5_s0.npz", allow_pickle=True)
    phi, run = z["phi"], z["run"]
    cols = feature_cols(rep)
    rows = []
    for r in COHORTS[cohort]:
        p = phi[run == r]
        sq = (p ** 2).sum(0)
        for j, c in enumerate(cols):
            pos = (p[:, j] > 0).mean()
            rows.append(dict(cohort=cohort, rep=rep, predictor=pred, model=SHORT[r], feature=c,
                             share=float(sq[j] / sq.sum()), sign_agree=float(max(pos, (p[:, j] < 0).mean())),
                             mean_phi=float(p[:, j].mean())))
    return pd.DataFrame(rows)


def main_extra():
    for rep in ["r3"]:
        a6_cross_model(rep=rep)
        a7_confounders(rep=rep)
    m = pd.concat([a8_mechanism(c, rep) for c in ["primary5", "paper50"] for rep in ["r0", "r2", "r3"]])
    m.to_csv(OUT / "a8_mechanism.csv", index=False)
