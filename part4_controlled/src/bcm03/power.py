"""Pilot-informed hierarchical power and precision simulation for the Exp03 full study.

Every quantity is estimated from the 660-attempt pilot with the P8-corrected measures (bcm03.measures), then the full
study's statistics are simulated under candidate designs (tasks N, repeats R per condition, models M).

Pair similarities follow a dyadic (social-relations) model within a cell c = (model, task), attempts i, j:
    s_ij = mu_c + a_i + a_j + e_ij        (pairs that share an attempt covary)
Its components are estimated within cells with exact finite-R moment coefficients (moment_coefs), pooled over the
cells of a model; the task-shared part comes from cross-model covariances of cell means. They are reported
(pilot_parameters.json: reliabilities of cell means) and drive the invariance (TOST) simulation, which draws A and B
attempts per task and compares S_AB with the natural A-vs-A baseline S_AA.
H1 is simulated by hierarchical resampling of the pilot instead (see below).
Outcomes: logit p_mt = b_m + u_t + v_mt with a task-shared u, Bernoulli attempts.

Analyses simulated (decision rules are those of FULL_STUDY_ANALYSIS_PLAN.md):
  H1  pair-level within-cell correlation of attribution cosine x and a task-grounded behaviour similarity y over A pairs
      (task means removed), pooled over models; CI by task-cluster bootstrap; power for lower bound > 0 and > 0.1.
      Simulated by hierarchical resampling of the pilot (tasks with replacement, repeats without replacement),
      because the pilot cell means are too unreliable (reliability ~0-0.2 at R=5) to fit a parametric cell model.
  H2  TOST of D = mean_t[S_AA(t) - S_AB2(t)] within +-margin (90% CI), per model and pooled; solve-rate TOST too
  H3  precision of C2 adaptation rates (task-clustered); AUC(adapted vs persisted) precision
  BCM precision of per-model BCM and of real-minus-null, from pilot OOF attributions resampled by task
  B1/C1 diagnostic subsets: TOST power (B1) and rate precision (C1 verified-noop / harmful edit)
Usage: python -m bcm03.power <pilot_measures_dir> <pilot_analysis_dir> <out_dir> [n_sims]
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm, rankdata
from scipy.special import expit, logit

from bcm03.measures import PAIR, pair_measures

PRIMARY = ["devstral-small-2507", "qwen3-coder-30b-a3b", "swe-agent-lm-32b"]   # pilot models with outcome variance
COS = "cos|AB|r2|lgbm_paper"
RNG = np.random.default_rng(20261027)


# ------------------------------------------------------------------ pilot inputs
def pilot_pairs(T, P_old):
    """Pair table with the P8-corrected measures + the pilot's attribution cosines (same attempt pairs)."""
    rows = []
    for (m, t), g in T.groupby(["model", "instance_id"]):
        for r, s in itertools.combinations(list(g.itertuples()), 2):
            kind = "".join(sorted([r.variant, s.variant]))
            rows.append(dict(model=m, instance_id=t, repo=r.repo, kind=kind, a=r.run_id, b=s.run_id,
                             a_edit=r.edited, b_edit=s.edited, **pair_measures(r, s)))
    P = pd.DataFrame(rows)
    key = lambda d: d.a + "|" + d.b
    cos = dict(zip(key(P_old), P_old[COS]))
    cos.update(dict(zip(P_old.b + "|" + P_old.a, P_old[COS])))
    P["cos"] = key(P).map(cos)
    return P


def moment_coefs(R):
    """E[Q1], E[Q2] coefficients on (var_a, var_e) for one cell with R attempts (R >= 3).
    Q2 = mean over pairs of (s_ij - m)^2;  Q1 = mean over attempts of (sbar_i - m)^2, m = mean over pairs."""
    P = R * (R - 1) / 2
    return np.array([[(R - 2) ** 2 / (R * (R - 1)), (R - 2) / (R * (R - 1))],
                     [2 * (1 - 2 / R), (P - 1) / P]])


def cell_stats(g, cx, cy=None):
    """Within-cell moments for one cell's pairs (columns a, b, cx[, cy])."""
    g = g.dropna(subset=[cx] + ([cy] if cy else []))
    ids = sorted(set(g.a) | set(g.b))
    R = len(ids)
    if R < 3 or len(g) != R * (R - 1) / 2:
        return None
    m = {c: g[c].mean() for c in [cx] + ([cy] if cy else [])}
    sb = {c: np.array([g.loc[(g.a == i) | (g.b == i), c].mean() for i in ids]) - m[c] for c in m}
    y = cy or cx
    q1 = float(np.mean(sb[cx] * sb[y]))
    q2 = float(np.mean((g[cx] - m[cx]) * (g[y] - m[y])))
    return dict(R=R, mx=m[cx], my=m[y], q1=q1, q2=q2)


def components(P, kind, cx, cy=None, models=PRIMARY):
    """Pooled method-of-moments estimates of (var_a, var_e) [or covariances if cy], cell-mean noise and true
    between-cell (co)variance, per model and pooled over models."""
    out = {}
    for m in models:
        S = [s for (_, g) in P[(P.model == m) & (P.kind == kind)].groupby("instance_id")
             if (s := cell_stats(g, cx, cy)) is not None]
        if len(S) < 4:
            continue
        C = sum(moment_coefs(s["R"]) for s in S)
        q = np.array([sum(s["q1"] for s in S), sum(s["q2"] for s in S)])
        va, ve = np.linalg.solve(C, q)
        if cy is None:
            va, ve = max(va, 0.0), max(ve, 0.0)
        noise = np.mean([4 * va / s["R"] + ve / (s["R"] * (s["R"] - 1) / 2) for s in S])
        mx, my = np.array([s["mx"] for s in S]), np.array([s["my"] for s in S])
        cov_obs = float(np.cov(mx, my)[0, 1])
        out[m] = dict(n_cells=len(S), R_mean=float(np.mean([s["R"] for s in S])), var_a=float(va), var_e=float(ve),
                      noise_cellmean=float(noise), cov_cellmeans=cov_obs, true_cov=cov_obs - noise,
                      mean_x=float(mx.mean()), mean_y=float(my.mean()))
    return out


def task_share(P, kind, col, models=PRIMARY):
    """Share of the between-cell variance that is common to all models on a task (cross-model covariance of cell means)."""
    M = P[(P.kind == kind)].groupby(["instance_id", "model"])[col].mean().unstack()[models].dropna()
    covs = [np.cov(M[a], M[b])[0, 1] for a, b in itertools.combinations(models, 2)]
    var = np.mean([M[m].var() for m in models])
    return float(np.clip(np.mean(covs) / var, 0, 1)) if var > 0 else 0.0


def outcome_params(T, models=PRIMARY):
    """Logit-normal task heterogeneity of solve rates on A (moment matching per model) and task-shared fraction."""
    A = T[(T.variant == "A") & T.model.isin(models)]
    out = {}
    for m, g in A.groupby("model"):
        p_t = g.groupby("instance_id").resolved.mean()
        p = p_t.mean()
        best = None
        for s in np.linspace(0, 4, 81):
            z = RNG.standard_normal(20000)
            b = logit(np.clip(p, 0.01, 0.99))
            for _ in range(20):   # match the mean
                b += logit(np.clip(p, 0.01, 0.99)) - logit(np.clip(expit(b + s * z).mean(), 0.01, 0.99))
            q = expit(b + s * z)
            v = q.var() + np.mean(q * (1 - q)) / g.groupby("instance_id").size().mean()
            if best is None or abs(v - p_t.var(ddof=0)) < best[0]:
                best = (abs(v - p_t.var(ddof=0)), s, b)
        out[m] = dict(p=float(p), sigma=float(best[1]), b=float(best[2]))
    W = A.groupby(["instance_id", "model"]).resolved.mean().unstack()[models]
    lw = logit(W.clip(0.05, 0.95))
    out["task_share"] = float(np.clip(np.mean([np.cov(lw[a], lw[b])[0, 1] for a, b in itertools.combinations(models, 2)])
                                      / np.mean([lw[m].var() for m in models]), 0, 1))
    return out


# ------------------------------------------------------------------ simulators
def within_cell_r(df, x, y):
    """Pair-level association with task (cell) means removed: Pearson of within-cell-centred x and y, pooled over cells
    and models. Removes task-level confounding (tasks on which everything is similar)."""
    d = df.dropna(subset=[x, y])
    if len(d) < 10:
        return np.nan
    g = d.groupby("cell")
    xc, yc = d[x] - g[x].transform("mean"), d[y] - g[y].transform("mean")
    den = np.sqrt((xc ** 2).sum() * (yc ** 2).sum())
    return float((xc * yc).sum() / den) if den > 0 else np.nan


def cell_level_r(df, x, y):
    """Between-task association within model: Pearson of cell means after removing model means."""
    c = df.dropna(subset=[x, y]).groupby(["model", "cell"])[[x, y]].mean()
    c = c - c.groupby("model").transform("mean")
    return float(c[x].corr(c[y])) if len(c) > 5 else np.nan


def _h1_stats(D, y, N, M, W):
    """Within-cell and cell-level r for the resampled data D and for each row of bootstrap task weights W (B x N)."""
    d = D.dropna(subset=["cos", y])
    g = d.groupby("cell")
    xc, yc = (d.cos - g.cos.transform("mean")).to_numpy(), (d[y] - g[y].transform("mean")).to_numpy()
    t = d.tidx.to_numpy()
    S = np.zeros((3, N))
    for k, v in enumerate([xc * yc, xc * xc, yc * yc]):
        np.add.at(S[k], t, v)
    w_est = S[0].sum() / np.sqrt(S[1].sum() * S[2].sum())
    WS = W @ S.T
    w_bs = WS[:, 0] / np.sqrt(WS[:, 1] * WS[:, 2])
    c = d.groupby(["midx", "tidx"])[["cos", y]].mean().reset_index()
    num = np.zeros(len(W) + 1)
    sxx, syy = np.zeros(len(W) + 1), np.zeros(len(W) + 1)
    Wf = np.vstack([np.ones(N), W])
    for m in range(M):
        cm = c[c.midx == m]
        if len(cm) < 3:
            continue
        w = Wf[:, cm.tidx.to_numpy()]
        x, yy = cm.cos.to_numpy(), cm[y].to_numpy()
        sw = w.sum(1)
        mx, my = (w @ x) / sw, (w @ yy) / sw
        num += w @ (x * yy) - sw * mx * my
        sxx += w @ (x * x) - sw * mx * mx
        syy += w @ (yy * yy) - sw * my * my
    cl = num / np.sqrt(sxx * syy)
    return w_est, w_bs, cl[0], cl[1:]


def boot_h1(P, y, N, R, M, n_sims=200, n_boot=500, kind="AA"):
    """Hierarchical resampling of the pilot: N tasks drawn with replacement (shared by all models), M models drawn from
    the pilot's primary models, R of the 5 repeats per cell drawn without replacement; the statistics and their
    task-cluster bootstrap CIs are computed as in the analysis plan (within_cell_r, cell_level_r)."""
    A = P[(P.kind == kind) & P.model.isin(PRIMARY)].copy()
    A["ia"], A["ib"] = A.a.str.extract(r"__s(\d+)$")[0].astype(int), A.b.str.extract(r"__s(\d+)$")[0].astype(int)
    tasks = sorted(A.instance_id.unique())
    by = {k: g for k, g in A.groupby(["model", "instance_id"])}
    res = {"within": [], "cell": []}
    for _ in range(n_sims):
        T = RNG.choice(tasks, N)
        Ms = RNG.choice(PRIMARY, M) if M > len(PRIMARY) else RNG.permutation(PRIMARY)[:M]
        parts = []
        for mi, m in enumerate(Ms):
            for ti, t in enumerate(T):
                g = by.get((m, t))
                if g is None:
                    continue
                keep = set(RNG.choice(np.arange(1, 6), R, replace=False))
                gg = g[g.ia.isin(keep) & g.ib.isin(keep)]
                parts.append(gg[["cos", y]].assign(cell=mi * N + ti, midx=mi, tidx=ti))
        D = pd.concat(parts, ignore_index=True)
        W = RNG.multinomial(N, np.full(N, 1 / N), n_boot).astype(float)
        we, wb, ce, cb = _h1_stats(D, y, N, M, W)
        res["within"].append((we, *np.nanquantile(wb, [.025, .975, .0125])))
        res["cell"].append((ce, *np.nanquantile(cb, [.025, .975, .0125])))
    out = []
    for name, r in res.items():
        r = np.array(r)
        out.append(dict(measure=y, level=name, N=N, R=R, M=M, mean_est=float(np.nanmean(r[:, 0])),
                        median_ci_halfwidth=float(np.nanmedian((r[:, 2] - r[:, 1]) / 2)),
                        power_lo_gt0=float(np.mean(r[:, 1] > 0)), power_lo_gt01=float(np.mean(r[:, 1] > 0.1)),
                        power_bonf_lo_gt0=float(np.mean(r[:, 3] > 0))))
    return out


def sim_tost(par, N, RA, RB, M, delta, margin, tau=0.0, n_sims=2000, task_share_=0.5):
    """Equivalence of S_AA vs S_AB per task (dyadic simulation of A and B attempts, natural A-vs-A baseline)."""
    va, ve = par["var_a"], par["var_e"]
    idxAA = list(itertools.combinations(range(RA), 2))
    acc_m, acc_p, acc_mb, acc_pb, hw = [], [], [], [], []
    for _ in range(n_sims):
        Dm = np.zeros((M, N))
        shared = RNG.standard_normal(N) * tau * np.sqrt(task_share_)
        for m in range(M):
            a = RNG.standard_normal((N, RA)) * np.sqrt(va)
            b = RNG.standard_normal((N, RB)) * np.sqrt(va)
            eAA = RNG.standard_normal((N, len(idxAA))) * np.sqrt(ve)
            eAB = RNG.standard_normal((N, RA, RB)) * np.sqrt(ve)
            sAA = np.stack([a[:, i] + a[:, j] for i, j in idxAA], 1) + eAA
            dt = delta + shared + RNG.standard_normal(N) * tau * np.sqrt(1 - task_share_)
            sAB = a[:, :, None] + b[:, None, :] + eAB - dt[:, None, None]
            Dm[m] = sAA.mean(1) - sAB.mean((1, 2))
        for D, acc, accb in [(Dm[0], acc_m, acc_mb), (Dm.mean(0), acc_p, acc_pb)]:
            se = D.std(ddof=1) / np.sqrt(N)
            acc.append(-margin < D.mean() - 1.645 * se and D.mean() + 1.645 * se < margin)
            accb.append(-margin < D.mean() - 2.241 * se and D.mean() + 2.241 * se < margin)
        hw.append(1.645 * Dm[0].std(ddof=1) / np.sqrt(N))
    return dict(N=N, RA=RA, RB=RB, M=M, delta=delta, margin=margin, tau=tau, p_equiv_one_model=float(np.mean(acc_m)),
                p_equiv_pooled=float(np.mean(acc_p)), p_equiv_one_model_bonf=float(np.mean(acc_mb)),
                p_equiv_pooled_bonf=float(np.mean(acc_pb)), median_90ci_halfwidth_one_model=float(np.median(hw)))


def sim_rate_diff(op, N, RA, RB, M, delta_p, margin, n_sims=2000):
    """TOST on solve-rate difference (B - A), paired by task, logit-normal task heterogeneity."""
    acc_m, acc_p, acc_pb, hw = [], [], [], []
    ms = [k for k in op if k != "task_share"]
    ts = op["task_share"]
    for _ in range(n_sims):
        ut = RNG.standard_normal(N)
        D = []
        for m in range(M):
            q = op[ms[m % len(ms)]]
            u = q["sigma"] * (np.sqrt(ts) * ut + np.sqrt(1 - ts) * RNG.standard_normal(N))
            pA = expit(q["b"] + u)
            pB = np.clip(pA + delta_p, 0, 1)
            D.append(RNG.binomial(RB, pB) / RB - RNG.binomial(RA, pA) / RA)
        D = np.array(D)
        for d, acc in [(D[0], acc_m), (D.mean(0), acc_p)]:
            se = d.std(ddof=1) / np.sqrt(N)
            acc.append(-margin < d.mean() - 1.645 * se and d.mean() + 1.645 * se < margin)
        sp = D.mean(0).std(ddof=1) / np.sqrt(N)
        acc_pb.append(-margin < D.mean(0).mean() - 2.241 * sp and D.mean(0).mean() + 2.241 * sp < margin)
        hw.append(1.645 * D[0].std(ddof=1) / np.sqrt(N))
    return dict(N=N, RA=RA, RB=RB, M=M, delta_p=delta_p, margin=margin, p_equiv_one_model=float(np.mean(acc_m)),
                p_equiv_pooled=float(np.mean(acc_p)), p_equiv_pooled_bonf=float(np.mean(acc_pb)),
                median_90ci_halfwidth_one_model=float(np.median(hw)))


def sim_rate_precision(sigma, ts, N, R, M, p, n_sims=2000):
    """95% CI half-width of a per-model attempt rate and of the pooled rate (task-cluster), logit-normal tasks."""
    b = logit(p)
    for _ in range(30):
        b += logit(p) - logit(expit(b + sigma * RNG.standard_normal(20000)).mean())
    hw1, hwp = [], []
    for _ in range(n_sims):
        ut = RNG.standard_normal(N)
        Y = []
        for m in range(M):
            pm = expit(b + sigma * (np.sqrt(ts) * ut + np.sqrt(1 - ts) * RNG.standard_normal(N)))
            Y.append(RNG.binomial(R, pm) / R)
        Y = np.array(Y)
        hw1.append(1.96 * Y[0].std(ddof=1) / np.sqrt(N))
        hwp.append(1.96 * Y.mean(0).std(ddof=1) / np.sqrt(N))
    return dict(N=N, R=R, M=M, p=p, sigma=sigma, ci95_halfwidth_one_model=float(np.median(hw1)),
                ci95_halfwidth_pooled=float(np.median(hwp)))


def auc_precision(n_pos, n_neg, auc=0.5):
    """Hanley-McNeil SE of an AUC, times a task-cluster design effect of 1.5 (conservative)."""
    q1, q2 = auc / (2 - auc), 2 * auc ** 2 / (1 + auc)
    se = np.sqrt((auc * (1 - auc) + (n_pos - 1) * (q1 - auc ** 2) + (n_neg - 1) * (q2 - auc ** 2)) / (n_pos * n_neg))
    return float(1.96 * se * np.sqrt(1.5))


# ------------------------------------------------------------------ BCM precision from pilot attributions
def bcm_precision(phi_by_model, task_by_model, Ns, n_boot=2000):
    """Task-cluster bootstrap of BCM (U-statistic over attempts) with tasks resampled to size N from the pilot."""
    from bcm02.pipeline import bcm
    out = []
    for m, phi in phi_by_model.items():
        tasks = task_by_model[m]
        ut = np.unique(tasks)
        groups = [np.flatnonzero(tasks == t) for t in ut]
        for N in Ns:
            bs = []
            for _ in range(n_boot):
                pick = RNG.integers(0, len(ut), N)
                idx = np.concatenate([groups[k] for k in pick])
                bs.append(bcm(phi[idx]))
            out.append(dict(model=m, N=N, bcm_boot_mean=float(np.mean(bs)), bcm_se=float(np.std(bs)),
                            ci95_halfwidth=float(1.96 * np.std(bs))))
    return pd.DataFrame(out)


def main(meas_dir, ana_dir, out_dir, n_sims=300):
    n_sims = int(n_sims)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    T = pd.read_parquet(Path(meas_dir) / "attempts.parquet")
    P_old = pd.read_parquet(Path(ana_dir) / "pairs.parquet")
    P = pilot_pairs(T, P_old)
    P.to_parquet(out / "pilot_pairs_v2.parquet")
    est = {}
    # ---- parameter estimation (A cells = 'AA' pairs)
    for y in ["patch_sim_cond", "f2p_agree", "func_jacc_cond", "outcome_concord", "edit_decision_agree", "seq_sim"]:
        cx = components(P, "AA", "cos")
        cy = components(P, "AA", y)
        cxy = components(P, "AA", "cos", y)
        er = T[(T.variant == "A") & T.model.isin(PRIMARY)].groupby(["model", "instance_id"]).edited.mean().to_numpy()
        rows = {}
        for m in cx:
            if m not in cy or m not in cxy:
                continue
            tx, ty = max(cx[m]["true_cov"], 1e-6), max(cy[m]["true_cov"], 1e-6)
            rows[m] = dict(vax=cx[m]["var_a"], vex=cx[m]["var_e"], vay=cy[m]["var_a"], vey=cy[m]["var_e"],
                           cov_a=cxy[m]["var_a"], cov_e=cxy[m]["var_e"], tvx=tx, tvy=ty,
                           rho_obs_pearson_cellmeans=cxy[m]["cov_cellmeans"] / np.sqrt(cx[m]["cov_cellmeans"] * cy[m]["cov_cellmeans"]),
                           rho_true_disattenuated=float(np.clip(cxy[m]["true_cov"] / np.sqrt(tx * ty), -1, 1)),
                           reliability_x_R5=tx / (tx + cx[m]["noise_cellmean"]), reliability_y=ty / (ty + cy[m]["noise_cellmean"]),
                           n_cells=cy[m]["n_cells"], R_mean_y=cy[m]["R_mean"], mean_y=cy[m]["mean_y"])
        est[y] = dict(per_model=rows, task_share=task_share(P, "AA", y), edit_rates=er.tolist() if "cond" in y else None)
    est["cos_task_share"] = task_share(P, "AA", "cos")
    est["outcome"] = outcome_params(T)
    # invariance noise for TOST, per measure: A-vs-A dyadic components (natural repeat variability)
    est["tost"] = {}
    for y in ["patch_sim_cond", "f2p_agree", "outcome_concord", "edit_decision_agree", "seq_sim", "cos"]:
        c = components(P, "AA", y)
        est["tost"][y] = dict(var_a=float(np.mean([v["var_a"] for v in c.values()])),
                              var_e=float(np.mean([v["var_e"] for v in c.values()])),
                              sd_pair=float(P[P.kind == "AA"][y].std()))
    # observed pilot B1 effects (D = S_AA - S_AB1) and their between-task SD
    D = []
    for y in ["patch_sim_cond", "f2p_agree", "outcome_concord", "edit_decision_agree", "seq_sim", "cos"]:
        g = P[P.model.isin(PRIMARY)].groupby(["model", "instance_id", "kind"])[y].mean().unstack()
        d = (g["AA"] - g["AB1"]).dropna()
        D.append(dict(measure=y, mean_D=d.mean(), sd_task_D=d.std(), n=len(d)))
    D = pd.DataFrame(D)
    D.to_csv(out / "pilot_B1_D.csv", index=False)
    # calibration: does the dyadic model reproduce the pilot's between-task SD of D (A-vs-B1, R=5, one model)?
    cal = []
    for r in D.itertuples():
        if r.measure in est["tost"]:
            sim = sim_tost(est["tost"][r.measure], 33, 5, 5, 1, 0.0, 0.05, 0.0, n_sims=500)
            cal.append(dict(measure=r.measure, pilot_sd_task_D=r.sd_task_D,
                            model_sd_task_D=sim["median_90ci_halfwidth_one_model"] * np.sqrt(33) / 1.645))
    pd.DataFrame(cal).to_csv(out / "tost_calibration.csv", index=False)
    (out / "pilot_parameters.json").write_text(json.dumps(est, indent=1, default=float))

    # ---- H1 (pilot effect + precision; power at other effects follows from the precision)
    P["cell"] = P.model + "|" + P.instance_id
    obs = [dict(measure=y, model=m, within_cell_r=within_cell_r(P[(P.kind == "AA") & (P.model == m)], "cos", y),
                cell_level_r=cell_level_r(P[(P.kind == "AA") & (P.model == m)], "cos", y))
           for y in ["patch_sim_cond", "f2p_agree", "func_jacc_cond", "edit_decision_agree", "outcome_concord", "seq_sim"]
           for m in PRIMARY + ["qwen2.5-coder-7b"]]
    pd.DataFrame(obs).to_csv(out / "pilot_h1_observed.csv", index=False)
    H1 = []
    for y in ["patch_sim_cond", "f2p_agree", "edit_decision_agree", "seq_sim"]:
        for N, R, M in [(100, 5, 4), (100, 4, 4), (100, 3, 4), (60, 5, 4), (50, 5, 4), (100, 5, 5), (30, 5, 4)]:
            H1 += boot_h1(P, y, N, R, M, n_sims=n_sims)
            print("H1", H1[-2], H1[-1], flush=True)
    pd.DataFrame(H1).to_csv(out / "power_h1.csv", index=False)

    # ---- H2 (B2 TOST) and B1 subset
    H2 = []
    for y in ["patch_sim_cond", "f2p_agree", "edit_decision_agree", "seq_sim", "cos"]:
        par = est["tost"][y]
        margin = 0.05
        for (N, RA, RB, M) in [(100, 5, 5, 4), (100, 5, 4, 4), (100, 5, 3, 4), (60, 5, 4, 4), (20, 5, 3, 4), (20, 5, 5, 4)]:
            for delta, tau in [(0.0, 0.0), (0.0, 0.05), (0.025, 0.05), (0.05, 0.05), (0.1, 0.05)]:
                H2.append(dict(measure=y, sd_pair=par["sd_pair"],
                               **sim_tost(par, N, RA, RB, M, delta, margin, tau, n_sims=max(500, n_sims))))
        print("H2", y, flush=True)
    for (N, RA, RB, M) in [(100, 5, 5, 4), (100, 5, 4, 4), (100, 5, 3, 4), (60, 5, 4, 4), (20, 5, 3, 4)]:
        for dp in [0.0, 0.025, 0.05, 0.1]:
            for margin in [0.05, 0.075]:
                H2.append(dict(measure="solve_rate", **sim_rate_diff(est["outcome"], N, RA, RB, M, dp, margin,
                                                                     n_sims=max(500, n_sims))))
    pd.DataFrame(H2).to_csv(out / "power_h2_tost.csv", index=False)

    # ---- H3/H4 and C1 precision
    sig = float(np.mean([v["sigma"] for k, v in est["outcome"].items() if k != "task_share"]))
    ts = est["outcome"]["task_share"]
    H3 = []
    for N, R, M in [(100, 4, 4), (100, 5, 4), (80, 4, 4), (60, 4, 4), (60, 5, 4), (40, 5, 4), (20, 3, 4), (20, 5, 4), (30, 4, 4)]:
        for p in [0.07, 0.15, 0.3, 0.45]:
            H3.append(sim_rate_precision(sig, ts, N, R, M, p, n_sims=max(500, n_sims)))
    H3 = pd.DataFrame(H3)
    H3.to_csv(out / "precision_rates.csv", index=False)
    A4 = []
    for N, R, M in [(100, 4, 4), (80, 4, 4), (60, 4, 4), (60, 5, 4), (40, 5, 4)]:
        n = N * R * M
        for fa, fp in [(0.25, 0.15), (0.15, 0.25), (0.3, 0.1)]:
            A4.append(dict(N=N, R=R, M=M, frac_adapted=fa, frac_persisted=fp, n_adapted=n * fa, n_persisted=n * fp,
                           auc_ci95_halfwidth_pooled=auc_precision(n * fa, n * fp),
                           auc_ci95_halfwidth_one_model=auc_precision(n * fa / M, n * fp / M)))
    pd.DataFrame(A4).to_csv(out / "precision_h4_auc.csv", index=False)

    # ---- BCM: precision of per-model BCM and of real - null, scaled from the pilot (A+B1 fit, released LightGBM, R2)
    from bcm03.analysis import oof
    S = T[T.variant.isin(["A", "B1"])].sort_values("run_id").reset_index(drop=True)
    phi, margin, _ = oof(S, "r2", "lgbm_paper", 0)
    ok = ~np.isnan(margin)
    models = sorted(S.model.unique())
    B = bcm_precision({m: phi[ok & (S.model.values == m)] for m in models},
                      {m: S.instance_id.values[ok & (S.model.values == m)] for m in models}, [11, 20, 50, 60, 100])
    runs = pd.read_csv(Path(ana_dir) / "a1_bcm_runs.csv")
    nul = runs[(runs.fitset == "AB") & (runs.rep == "r2") & (runs.predictor == "lgbm_paper") & (runs.scheme == "perm_model")]
    real = runs[(runs.fitset == "AB") & (runs.rep == "r2") & (runs.predictor == "lgbm_paper") & (runs.scheme == "real")]
    B["null_sd_scaled"] = [nul[f"bcm|{m}"].std() * np.sqrt(11 / n) for m, n in zip(B.model, B.N)]
    B["pilot_real_minus_null"] = [real[f"bcm|{m}"].mean() - nul[f"bcm|{m}"].mean() for m in B.model]
    # z of the pilot-size effect at N tasks (sampling SE of real and null SD combined), and power at that effect
    B["se_diff"] = np.sqrt(B.bcm_se ** 2 + B.null_sd_scaled ** 2)
    B["power_detect_pilot_effect"] = norm.cdf(np.abs(B.pilot_real_minus_null) / B.se_diff - 1.96)
    B["power_detect_0.05"] = norm.cdf(0.05 / B.se_diff - 1.96)
    B.to_csv(out / "precision_bcm.csv", index=False)
    print("done ->", out, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
