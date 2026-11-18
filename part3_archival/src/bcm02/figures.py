"""Exp02 publication figures (PDF + PNG) from results/tables. Every figure states dataset, population,
parser, predictor and uncertainty procedure in its caption file (results/figures/CAPTIONS.md).
Colors: reference categorical palette, slots in fixed order per entity; identity is always also given by
axis position/labels (never color alone).
Usage: python -m bcm02.figures
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TAB, FIG = ROOT / "results/tables", ROOT / "results/figures"
FIG.mkdir(parents=True, exist_ok=True)
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
PRIMARY = ["GPT-5", "Sonnet-4.5", "Haiku-4.5", "GLM-4.5", "Gemini-2.5-Pro"]
PAPER50 = ["GPT-5-high", "gpt-oss-120b", "Kimi-K2"]
COLOR = {m: SLOTS[i] for i, m in enumerate(PRIMARY)}
COLOR.update({m: SLOTS[i] for i, m in enumerate(PAPER50)})
REPS = {"r0": "R0 author SWE-smith\nloader (thought text)", "r1": "R1 author all-\nmessages loader",
        "r2": "R2 role-aware\ntool actions", "r3": "R3 tool-semantic\ncategories"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
                     "font.family": "DejaVu Sans", "pdf.fonttype": 42})
CAPTIONS = []


def save(fig, name, caption):
    for ext in ["pdf", "png"]:
        fig.savefig(FIG / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    CAPTIONS.append(f"## {name}\n{caption}\n")


def fig1_representation():
    b = pd.read_csv(TAB / "a2_bootstrap_bcm.csv")
    b = b[(b.cohort == "primary5") & (b.predictor == "lgbm_paper")]
    fig, axes = plt.subplots(1, 4, figsize=(10, 2.8), sharey=True)
    for ax, (rep, lab) in zip(axes, REPS.items()):
        d = b[b.rep == rep].set_index("model").reindex(PRIMARY)
        y = np.arange(len(PRIMARY))
        for i, m in enumerate(PRIMARY):
            ax.plot([d.lo[m], d.hi[m]], [i, i], color=COLOR[m], lw=2, solid_capstyle="round")
            ax.plot(d.bcm[m], i, "o", ms=6, color=COLOR[m], mec="white", mew=1.2)
        ax.set_title(lab, fontsize=8.5, color=INK)
        ax.set_yticks(y, PRIMARY)
        ax.set_xlim(0, 0.62)
        ax.invert_yaxis()
        ax.set_xlabel("global BCM")
    save(fig, "fig1_bcm_by_representation",
         "SWE-bench Pro public archive, primary cohort (5 models, SWE-agent 1.1, 250-turn config, 715 matched tasks, "
         "one attempt per model-task). Same trajectories, four representations. Predictor: released BCM LightGBM, "
         "task-grouped 5-fold CV (seed 0); tree-path TreeSHAP. Points: BCM; bars: 95% paired task-cluster bootstrap "
         "(2,000 resamples, attributions held fixed). GPT-5 is ranked first under the authors' loader (R0) and last under "
         "role-aware parsing (R2): 58% of its R0 parses are empty because GPT-5's thought text is hidden.")


def fig2_nulls():
    n = pd.read_csv(TAB / "a4_permutation_controls.csv")
    panels = [("primary5", "r2", PRIMARY), ("primary5", "r0", PRIMARY), ("paper50", "r2", PAPER50)]
    fig, axes = plt.subplots(1, 3, figsize=(10, 2.8), gridspec_kw={"width_ratios": [5, 5, 3]})
    for ax, (c, rep, models) in zip(axes, panels):
        d = n[(n.cohort == c) & (n.rep == rep) & (n.predictor == "lgbm_paper")]
        for i, m in enumerate(models):
            for k, (null, dy, mk) in enumerate([("perm_model", -0.18, "s"), ("perm_global", 0.18, "^")]):
                r = d[(d.model == m) & (d.null == null)]
                if r.empty:
                    continue
                r = r.iloc[0]
                ax.plot([i + dy, i + dy], [r.null_q05, r.null_q95], color=MUTED if k == 0 else "#a3a29c", lw=2,
                        solid_capstyle="round")
                ax.plot(i + dy, r.null_median, mk, ms=4, color=MUTED if k == 0 else "#a3a29c")
            r = d[(d.model == m)].iloc[0]
            ax.plot(i, r.real_bcm_seed0, "o", ms=7, color=COLOR[m], mec="white", mew=1.2, zorder=3)
        ax.set_xticks(range(len(models)), models, rotation=30, ha="right")
        ax.set_title(f"{'primary cohort' if c == 'primary5' else 'paper-50 cohort'}, {rep.upper()}", fontsize=9)
        ax.set_ylabel("global BCM")
    axes[0].plot([], [], "o", color=INK, label="real labels")
    axes[0].plot([], [], "s-", color=MUTED, label="null: permuted within model (5-95%)")
    axes[0].plot([], [], "^-", color="#a3a29c", label="null: permuted globally (5-95%)")
    axes[0].legend(frameon=False, fontsize=7, loc="upper left")
    save(fig, "fig2_label_permutation_controls",
         "Real-label BCM (dot) vs. 50 pre-specified label permutations (seeds 1000-1049): within model (square, "
         "preserves each model's success rate) and global (triangle). Predictor: released BCM LightGBM, task-grouped "
         "5-fold CV; tree-path TreeSHAP. Under role-aware parsing in the primary cohort every model's real BCM lies "
         "inside its within-model null band: the BCM level is reproduced without any trajectory-outcome link inside a model.")


def fig3_ranks():
    a = pd.read_csv(TAB / "a1_main_bcm.csv")
    a = a[(a.cohort == "primary5") & (a.cv == "grouped5")]
    cfg = [(r, p) for r in ["r0", "r1", "r2", "r3"] for p in ["lgbm_paper", "lgbm_tuned", "logistic", "raw"]
           if not a[(a.rep == r) & (a.predictor == p)].empty]
    M = np.array([[a[(a.rep == r) & (a.predictor == p) & (a.model == m)].bcm_mean.iloc[0] for (r, p) in cfg]
                  for m in PRIMARY])
    R = (-M).argsort(0).argsort(0) + 1
    ABBR = {"lgbm_paper": "LGBM-paper", "lgbm_tuned": "LGBM-tuned", "logistic": "logistic", "raw": "raw"}
    fig, ax = plt.subplots(figsize=(8, 2.8))
    im = ax.imshow(R, cmap="Blues_r", vmin=1, vmax=7, aspect="auto")
    for i in range(R.shape[0]):
        for j in range(R.shape[1]):
            ax.text(j, i, f"{R[i, j]}\n{M[i, j]:.2f}", ha="center", va="center", fontsize=6.5,
                    color="white" if R[i, j] <= 2 else INK)
    ax.set_yticks(range(len(PRIMARY)), PRIMARY)
    ax.set_xticks(range(len(cfg)), [f"{r.upper()} {ABBR[p]}" for r, p in cfg], fontsize=7, rotation=40, ha="right")
    ax.grid(False)
    save(fig, "fig3_rank_by_configuration",
         "Model rank (1 = highest BCM) and BCM (mean over 10 task-grouped CV seeds; 3 for LGBM-tuned) for every "
         "representation x predictor configuration, primary cohort. 'raw' = train-fold z-scored features without a "
         "predictor. No model keeps its rank across configurations.")


def fig4_cross_model():
    s = pd.read_csv(TAB / "a6_cross_model_similarity_primary5_r2_lgbm_paper.csv")
    s = s[s.space == "attribution"]
    b = pd.read_csv(TAB / "a2_bootstrap_bcm.csv")
    b = b[(b.cohort == "primary5") & (b.rep == "r2") & (b.predictor == "lgbm_paper")].set_index("model").bcm
    K = len(PRIMARY)
    same, diff = np.full((K, K), np.nan), np.full((K, K), np.nan)
    for _, r in s.iterrows():
        i, j = PRIMARY.index(r.a), PRIMARY.index(r.b)
        if i == j:
            same[i, i] = b[r.a]
        else:
            same[i, j] = same[j, i] = r.same_task_mean_cos
        diff[i, j] = diff[j, i] = r.diff_task_mean_cos
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.3))
    for ax, Mx, t in [(axes[0], same, "same task (diagonal: within-model BCM)"), (axes[1], diff, "different tasks")]:
        ax.imshow(Mx, cmap="Blues", vmin=-0.1, vmax=0.5)
        for i in range(K):
            for j in range(K):
                ax.text(j, i, f"{Mx[i, j]:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if Mx[i, j] > 0.3 else INK)
        ax.set_xticks(range(K), PRIMARY, rotation=30, ha="right")
        ax.set_yticks(range(K), PRIMARY)
        ax.set_title(t, fontsize=9)
        ax.grid(False)
    save(fig, "fig4_cross_model_same_task_similarity",
         "Mean cosine between attribution vectors of two models' trajectories on the same task (left, off-diagonal) "
         "or on different tasks (right); diagonal of the left panel = the model's own global BCM (all cross-task pairs). "
         "Primary cohort, R2, released LightGBM, task-grouped CV seed 0. Descriptive only: one attempt per model-task, "
         "so this does not measure within-model repeatability. Two different models on the same task are more similar "
         "than one model across tasks.")


def fig5_bcm_vs_auc():
    x = pd.read_csv(TAB / "a5_bcm_vs_within_auc.csv")
    x = x[x.predictor.isin(["lgbm_paper", "logistic"])]
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    for sch, mk, col, lab in [("real", "o", SLOTS[0], "real labels"), ("perm_model", "s", MUTED, "within-model null (mean of 50)"),
                              ("perm_global", "^", "#a3a29c", "global null (mean of 50)")]:
        d = x[x.scheme == sch]
        ax.scatter(d.auc_within, d.bcm, marker=mk, s=18, color=col, edgecolor="white", linewidth=0.6, label=lab)
    ax.set_xlabel("within-model AUC of the success predictor")
    ax.set_ylabel("global BCM")
    ax.legend(frameon=False, fontsize=7)
    save(fig, "fig5_bcm_vs_within_model_auc",
         "Each point = one model x representation x predictor (LGBM, logistic) x label scheme (real; null medians "
         "over 50 permutations), all cohorts, task-grouped CV. BCM does not track the predictor's within-model "
         "discriminative ability; null models with chance-level within-model AUC reach the same BCM range.")


def fig6_companions():
    fig, axes = plt.subplots(1, 2, figsize=(9, 3), gridspec_kw={"width_ratios": [5, 3]})
    for ax, (c, models) in zip(axes, [("primary5", PRIMARY), ("paper50", PAPER50)]):
        d = pd.read_csv(TAB / f"a9_companions_{c}_r2.csv")
        for i, m in enumerate(models):
            g = d[d.model == m].groupby("k").bcm
            ks = np.array(sorted(d.k.unique())) + (i - len(models) / 2) * 0.06
            ax.vlines(ks, g.min(), g.max(), color=COLOR[m], lw=2)
            ax.plot(ks, g.median(), "o-", color=COLOR[m], ms=5, lw=1.5, mec="white", mew=1, label=m)
        ax.set_xticks(sorted(d.k.unique()))
        ax.set_ylabel("target system's global BCM")
        ax.set_title("primary cohort" if c == "primary5" else "paper-50 cohort", fontsize=9)
        ax.legend(frameon=False, fontsize=7)
    fig.supxlabel("number of systems pooled in the success predictor (incl. the target)", fontsize=9)
    save(fig, "fig6_bcm_depends_on_companion_systems",
         "Companion sensitivity. For every subset of systems containing the target, the released BCM LightGBM is fit "
         "on that subset only (task-grouped 5-fold CV, seed 0, R2 role-aware features, tree-path TreeSHAP); the target's "
         "trajectories and labels are identical in every fit. Points: median over subsets of that size; bars: min-max. "
         "Fit on a system alone (k = 1), every BCM is 0.001-0.019 although the predictor is informative "
         "(within-system AUC 0.61-0.77); BCM grows with the number of other systems in the pool.")


def main():
    fig1_representation()
    fig2_nulls()
    fig3_ranks()
    fig4_cross_model()
    fig5_bcm_vs_auc()
    fig6_companions()
    (FIG / "CAPTIONS.md").write_text("# Figure captions (Exp02)\n\n" + "\n".join(CAPTIONS))


if __name__ == "__main__":
    main()
