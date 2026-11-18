"""Publication figures. Each answers one question from the brief; all read results/tables."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import ROOT  # noqa: E402
from .experiments import SHORT, SYSTEMS  # noqa: E402

T = ROOT / "results/tables"
F = ROOT / "results/figures"
COL = dict(zip(SYSTEMS, ["#1b4f9c", "#3f7fd6", "#7fb0f0", "#b5431d", "#e07a3f", "#f2b27a"]))
REP_LABEL = {"author": "author parser (archival)", "role_aware": "role-aware parser (NEW)"}
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.bbox": "tight", "figure.dpi": 150, "font.family": "DejaVu Sans"})


def save(fig, name):
    F.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(F / f"{name}.{ext}", dpi=300 if ext == "png" else None)
    plt.close(fig)
    print("figure", name)


def n_label(rep):
    c = pd.read_csv(T / f"E0_comparison_{rep}.csv")
    return {r.system: int(r.n) for r in c.itertuples()}


def fig_reproduction():
    """Q: do our runs reproduce Tables 2 and 3, and what do the parser variants do?"""
    arch = pd.read_csv(T / "archival_shipped_artifacts.csv").set_index("system")
    reps = {rep: pd.read_csv(T / f"E0_comparison_{rep}.csv").set_index("system")
            for rep in ("author", "role_aware")}
    boot = {rep: pd.read_csv(T / f"bootstrap_cluster_summary_{rep}.csv").query("run=='seed42' and stage=='E0'")
            .set_index("system") for rep in reps}
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    x = np.arange(6)
    series = [("Paper", arch["paper_global"], arch["paper_within"], "#999999", None),
              ("Shipped artifacts", arch["bcm_global"], arch["within_task"], "#555555", None),
              ("Ours, author parser", reps["author"]["bcm_global"], reps["author"]["within_task"], "#1b4f9c", "author"),
              ("Ours, role-aware parser", reps["role_aware"]["bcm_global"], reps["role_aware"]["within_task"], "#b5431d", "role_aware")]
    w = 0.2
    for ax, which, title in [(axes[0], 1, "Global BCM (Table 2)"), (axes[1], 2, "Within-task BCM, tasks with ≥3 runs (Table 3)")]:
        for k, (lab, g, wi, c, rep) in enumerate(series):
            v = (g if which == 1 else wi).reindex(SYSTEMS).to_numpy()
            ax.bar(x + (k - 1.5) * w, v, w, color=c, label=lab)
            if rep and which == 1:
                b = boot[rep].reindex(SYSTEMS)
                ax.errorbar(x + (k - 1.5) * w, v, yerr=[v - b["ci_lower"], b["ci_upper"] - v],
                            fmt="none", ecolor="black", lw=0.7, capsize=1.5)
        ax.set_xticks(x, [SHORT[s] for s in SYSTEMS], rotation=30)
        ax.set_title(title)
        ax.axhline(0, color="black", lw=0.5)
    axes[0].set_ylabel("BCM")
    axes[0].legend(fontsize=7, frameon=False)
    n = n_label("author")
    fig.suptitle("Reproduction of Tables 2–3. Cohort n = 9,191 (" +
                 ", ".join(f"{SHORT[s]} {n[s]}" for s in SYSTEMS) +
                 "). Error bars: 95% task-cluster bootstrap (2,000).", fontsize=8)
    save(fig, "fig1_reproduction")


def fig_seed_stability():
    """Q (A): how much does BCM move when only the fold assignment changes?"""
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    for ax, rep in zip(axes, ("author", "role_aware")):
        a = pd.read_csv(T / f"runs_A_{rep}.csv")
        base = a[a.fold_seed == 42].set_index("system")["bcm"]
        for i, s in enumerate(SYSTEMS):
            v = a[a.system == s]["bcm"].to_numpy()
            ax.scatter(np.full(len(v), i) + np.random.default_rng(i).uniform(-0.12, 0.12, len(v)), v,
                       s=12, color=COL[s], zorder=3)
            ax.plot([i - 0.25, i + 0.25], [base[s]] * 2, color="black", lw=1)
        auc = a.groupby("fold_seed")["auc_pooled"].first()
        ax.set_xticks(range(6), [SHORT[s] for s in SYSTEMS], rotation=30)
        ax.set_title(f"{REP_LABEL[rep]}\nOOF AUC {auc.min():.3f}–{auc.max():.3f} over 11 fold seeds", fontsize=8)
        ax.set_ylabel("Global BCM")
    fig.suptitle("A. Fold-allocation sensitivity: 11 StratifiedKFold seeds, identical X/y and LightGBM (bar = seed 42)", fontsize=8)
    save(fig, "fig2_seed_stability")


def fig_predictor():
    """Q (B): does BCM depend on which competent predictor is explained?"""
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=False)
    marker = {"baseline": "o", "shallow": "v", "deep": "^", "regularized": "s", "subsample": "D",
              "logreg_l2_exploratory": "x"}
    for ax, rep in zip(axes, ("author", "role_aware")):
        b = pd.read_csv(T / f"runs_B_{rep}.csv")
        base_auc = b[b.variant == "baseline"]["auc_pooled"].iloc[0]
        ax.axvspan(base_auc - 0.03, base_auc + 0.03, color="#eeeeee", zorder=0)
        for (s, v), g in b.groupby(["system", "variant"]):
            ax.scatter(g["auc_pooled"], g["bcm"], color=COL[s], marker=marker[v], s=22,
                       label=v if s == SYSTEMS[0] else None)
        ax.set_xlabel("pooled OOF AUROC (grey: baseline ±0.03, pre-specified)")
        ax.set_ylabel("Global BCM")
        ax.set_title(REP_LABEL[rep], fontsize=8)
    handles = [plt.Line2D([], [], marker=marker[v], ls="", color="black", label=v) for v in marker] + \
              [plt.Line2D([], [], marker="o", ls="", color=COL[s], label=SHORT[s]) for s in SYSTEMS]
    axes[1].legend(handles=handles, fontsize=6.5, frameon=False, loc="center left", bbox_to_anchor=(1, 0.5))
    fig.suptitle("B. Predictor sensitivity (seed-42 folds, frozen X/y). Changes are predictor-induced, not agent behaviour.", fontsize=8)
    save(fig, "fig3_predictor_variants")


def fig_rank_heatmap():
    """Q: how often do pairwise system orderings flip across A/B/D runs and under the bootstrap?"""
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), constrained_layout=True)
    for ax, rep in zip(axes[:2], ("author", "role_aware")):
        base = pd.read_csv(T / f"runs_E0_{rep}.csv").set_index("system")["bcm"]
        runs = pd.concat([pd.read_csv(T / f"runs_{s}_{rep}.csv") for s in ("A", "B", "D")])
        # tree-model runs only; the exploratory logistic model is a different family
        runs = runs[~runs.run.isin(["fold_seed42", "baseline_rs42", "logreg_l2"])]
        R = np.zeros((6, 6))
        nr = runs.run.nunique()
        for _, g in runs.groupby("run"):
            v = g.set_index("system")["bcm"]
            for i, si in enumerate(SYSTEMS):
                for j, sj in enumerate(SYSTEMS):
                    if i != j and np.sign(base[si] - base[sj]) != np.sign(v[si] - v[sj]):
                        R[i, j] += 1
        R /= nr
        im = ax.imshow(R, vmin=0, vmax=1, cmap="Reds")
        for i in range(6):
            for j in range(6):
                if i != j:
                    ax.text(j, i, f"{R[i, j]:.2f}", ha="center", va="center", fontsize=6.5)
        ax.set_xticks(range(6), [SHORT[s] for s in SYSTEMS], rotation=45)
        ax.set_yticks(range(6), [SHORT[s] for s in SYSTEMS])
        ax.set_title(f"Fraction of {nr} A/B/D tree-model runs reversing\nseed-42 order — {REP_LABEL[rep]}", fontsize=8)
    P = pd.read_csv(T / "bootstrap_baseline_pairwise_prob_author.csv").set_index("system").reindex(SYSTEMS)[SYSTEMS].to_numpy()
    axes[2].imshow(P, vmin=0, vmax=1, cmap="Blues")
    for i in range(6):
        for j in range(6):
            if i != j:
                axes[2].text(j, i, f"{P[i, j]:.2f}", ha="center", va="center", fontsize=6.5)
    axes[2].set_xticks(range(6), [SHORT[s] for s in SYSTEMS], rotation=45)
    axes[2].set_yticks(range(6), [SHORT[s] for s in SYSTEMS])
    axes[2].set_title("P(row BCM > column BCM), author baseline,\n2,000 task-cluster bootstrap replicates", fontsize=8)
    fig.colorbar(im, ax=axes[1], fraction=0.04, label="reversal fraction")
    fig.suptitle("Ranking stability. Proprietary systems (SWE-smith source) vs Llama (Nebius source): "
                 "model, scaffold and data source are confounded.", fontsize=8)
    save(fig, "fig4_ranking_heatmap")


def fig_task_weighting():
    """Q (E): how do pair-weighting and task-balancing change the score on the same cohort?"""
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    cols = [("global_all", "global, all"), ("global_eligible_cohort", "global, eligible-task cohort"),
            ("between_task_eligible_cohort", "between-task pairs only (same cohort)"),
            ("within_task_macro", "within-task (macro)"), ("task_balanced_k3", "task-balanced, 3 runs/task"),
            ("one_per_task_mean", "one run per task (mean of 2,000)")]
    for ax, rep in zip(axes, ("author", "role_aware")):
        e = pd.read_csv(T / f"E_task_weighting_{rep}.csv").set_index("system").reindex(SYSTEMS)
        x = np.arange(6)
        w = 0.13
        for k, (c, lab) in enumerate(cols):
            ax.bar(x + (k - 2.5) * w, e[c], w, label=lab, color=plt.cm.viridis(k / 6))
        ax.set_xticks(x, [f"{SHORT[s]}\n{int(e.loc[s, 'n_tasks_eligible_ge3'])} tasks≥3" for s in SYSTEMS], fontsize=7)
        ax.set_title(REP_LABEL[rep], fontsize=8)
        ax.axhline(0, color="black", lw=0.5)
    axes[0].set_ylabel("BCM")
    axes[0].legend(fontsize=6.5, frameon=False)
    fig.suptitle("E. Task sampling and weighting on the frozen seed-42 SHAP vectors (descriptive)", fontsize=8)
    save(fig, "fig5_task_weighting")


def fig_null():
    """Q (C): what BCM does the pipeline produce when outcome labels are permuted?"""
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, rep in zip(axes, ("author", "role_aware")):
        c = pd.read_csv(T / f"runs_C_{rep}.csv")
        base = pd.read_csv(T / f"runs_E0_{rep}.csv").set_index("system")["bcm"]
        for i, s in enumerate(SYSTEMS):
            for k, (nt, mk) in enumerate([("within_system", "o"), ("global", "^")]):
                v = c[(c.system == s) & (c.null_type == nt)]["bcm"]
                ax.scatter(np.full(len(v), i + (k - 0.5) * 0.3), v, s=10, marker=mk, color=COL[s],
                           alpha=0.8, label=f"{nt.replace('_', '-')} permutation" if i == 0 else None)
            ax.plot([i - 0.35, i + 0.35], [base[s]] * 2, color="black", lw=1.2, label="real labels" if i == 0 else None)
        auc = c.groupby("null_type")["auc_pooled"].agg(["min", "max"])
        ax.set_xticks(range(6), [SHORT[s] for s in SYSTEMS], rotation=30)
        ax.set_title(f"{REP_LABEL[rep]}\nnull AUC within-system {auc.loc['within_system','min']:.3f}–{auc.loc['within_system','max']:.3f}; "
                     f"global {auc.loc['global','min']:.3f}–{auc.loc['global','max']:.3f}", fontsize=7.5)
        ax.axhline(0, color="grey", lw=0.5)
    axes[0].set_ylabel("Global BCM")
    axes[0].legend(fontsize=7, frameon=False)
    fig.suptitle("C. Outcome-label negative controls: 10 within-system and 10 global permutations (never pooled)", fontsize=8, y=1.06)
    save(fig, "fig6_permutation_null")


def fig_parser():
    """Q (F): how much of BCM is set by the parser, at fixed raw trajectories?"""
    a = pd.read_csv(T / "E0_comparison_author.csv").set_index("system").reindex(SYSTEMS)
    r = pd.read_csv(T / "E0_comparison_role_aware.csv").set_index("system").reindex(SYSTEMS)
    ra = pd.read_csv(T / "E0_raw_feature_baseline_author.csv").set_index("system").reindex(SYSTEMS)
    rr = pd.read_csv(T / "E0_raw_feature_baseline_role_aware.csv").set_index("system").reindex(SYSTEMS)
    fig, ax = plt.subplots(figsize=(8, 3.4))
    x = np.arange(6)
    series = [(a["bcm_global"], "SHAP, author parser", "#1b4f9c"),
              (a["bcm_global_nonempty"], "SHAP, author parser, non-empty rows only", "#7fb0f0"),
              (r["bcm_global"], "SHAP, role-aware parser", "#b5431d"),
              (ra["zscore_cohort_ref"], "z-scored raw features, author parser", "#888888"),
              (rr["zscore_cohort_ref"], "z-scored raw features, role-aware parser", "#cccccc")]
    w = 0.16
    for k, (v, lab, c) in enumerate(series):
        ax.bar(x + (k - 2) * w, v, w, label=lab, color=c)
    ax.set_xticks(x, [SHORT[s] for s in SYSTEMS])
    ax.axhline(0, color="black", lw=0.5)
    ax.set_ylabel("Global BCM")
    ax.legend(fontsize=7, frameon=False, ncol=2)
    ax.set_title("F. Representation audit at fixed raw trajectories (differences are parser-induced)", fontsize=8)
    save(fig, "fig7_parser_representation")


def fig_background():
    """Q (G): does the explainer reference distribution change the scores?"""
    reps = [r for r in ("author", "role_aware") if (T / f"runs_G_{r}.csv").exists()]
    stage = "G"
    if not reps:
        reps = [r for r in ("author", "role_aware") if (T / f"runs_G_pilot_{r}.csv").exists()]
        stage = "G_pilot"
    if not reps:
        return
    fig, axes = plt.subplots(1, len(reps), figsize=(5 * len(reps), 3.4), squeeze=False)
    for ax, rep in zip(axes[0], reps):
        g = pd.read_csv(T / f"runs_{stage}_{rep}.csv")
        for i, s in enumerate(SYSTEMS):
            v = g[g.system == s]
            ax.scatter(np.full(len(v), i), v["bcm"], color=COL[s], s=14, label="interventional (3 backgrounds)" if i == 0 else None)
            ax.scatter([i + 0.25], [v["bcm_tree_path_dependent_same_rows"].iloc[0]], marker="_", s=120,
                       color="black", label="tree-path-dependent" if i == 0 else None)
        ax.set_xticks(range(6), [f"{SHORT[s]}\ncos={g[g.system == s]['median_cos_to_tree_path'].median():.2f}" for s in SYSTEMS], fontsize=7)
        ax.set_title(f"{REP_LABEL[rep]} ({stage})", fontsize=8)
        ax.set_ylabel("Global BCM")
    axes[0][0].legend(fontsize=7, frameon=False)
    fig.suptitle("G. Explainer reference-distribution sensitivity (same seed-42 models and rows; cos = median per-row cosine to tree-path SHAP)", fontsize=8)
    save(fig, f"fig8_background_{stage}")


def main():
    for f in (fig_reproduction, fig_seed_stability, fig_predictor, fig_rank_heatmap,
              fig_task_weighting, fig_null, fig_parser, fig_background):
        try:
            f()
        except FileNotFoundError as e:
            print("skip", f.__name__, "missing", e.filename)


if __name__ == "__main__":
    main()
