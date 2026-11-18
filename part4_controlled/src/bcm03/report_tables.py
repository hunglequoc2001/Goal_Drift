"""Markdown tables for reports/PILOT_REPORT.md, generated from results/analysis/pilot_full (no hand transcription).
Usage: python -m bcm03.report_tables <analysis_dir> > reports/pilot_tables.md"""
import re
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

D = Path(sys.argv[1])
ROOT = Path(__file__).resolve().parents[2]
SHORT = {"qwen2.5-coder-7b": "Qwen2.5-Coder-7B", "qwen3-coder-30b-a3b": "Qwen3-Coder-30B-A3B",
         "devstral-small-2507": "Devstral-Small-2507", "swe-agent-lm-32b": "SWE-agent-LM-32B"}


def md(df):
    """Markdown table without the optional `tabulate` dependency (the Exp01 venv is kept frozen)."""
    f = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(f(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines) + "\n"


T = pd.read_parquet(D / "attempts.parquet")
T["model"] = T.model.map(SHORT)
print("## T1 Outcomes per model x variant (n = 55 attempts per cell = 11 tasks x 5 seeds)\n")
a = pd.read_csv(D / "a0_summary.csv")
a["model"] = a.model.map(SHORT)
print(md(a[["model", "variant", "resolved", "n_tasks_solved", "exit_submitted", "exit_limits", "steps", "format_compliance", "agent_seconds"]]))

print("## T2 BCM (fit set A+B1, pooled predictor, task-grouped 5-fold CV; real = mean of 10 CV seeds; null = labels permuted within model, 50 seeds)\n")
S = pd.read_csv(D / "a1_bcm_summary.csv")
S = S[(S.fitset == "AB") & (S.subset == "bcm")].copy()
S["model"] = S.model.map(SHORT)
S["real<null_q025"] = S["mean"] < S.null_q025
print(md(S[["rep", "predictor", "model", "mean", "null_mean", "null_q025", "null_q975", "real<null_q025"]]))
R = pd.read_csv(D / "a1_bcm_runs.csv")
print("Pooled OOF AUC (mean over seeds):\n")
print(md(R.groupby(["fitset", "rep", "predictor", "scheme"]).auc.mean().reset_index()))

print("## T3 Repeatability within A (mean over the 11 tasks of the per-task mean pairwise similarity across the 5 seeds; CIs in results/analysis/pilot_full/a3_contrasts.csv)\n")
C = pd.read_csv(D / "a3_contrasts.csv")
C["model"] = C.model.map(SHORT)
k = C[C.kind.isin(["AA"]) & C.measure.isin(["seq_sim", "file_jacc", "func_jacc", "outcome_agree", "cos|AB|r2|lgbm_paper"])]
print(md(k.pivot(index="model", columns="measure", values="mean").reset_index()))

print("## T4 H1 within-model Spearman (cell = model x task x variant in {A, B1}; attribution = mean pairwise cosine)\n")
cells = pd.read_csv(D / "a2_cells.csv")
cells = cells[cells.kind.isin(["AA", "BB"])]
rows = []
for att in ["cos|AB|r2|lgbm_paper", "cos|AB|r2|logistic", "cos|AB|r3|lgbm_paper"]:
    for b in ["seq_sim", "file_jacc", "func_jacc", "outcome_agree"]:
        r = {"attribution": att, "behaviour": b}
        for m, g in cells.groupby("model"):
            g = g.dropna(subset=[att, b])
            r[SHORT[m]] = spearmanr(g[att], g[b]).statistic if g[b].nunique() > 1 else float("nan")
        d = cells.dropna(subset=[att, b]).copy()
        d["ra"], d["rb"] = d.groupby("model")[att].rank(), d.groupby("model")[b].rank()
        r["within-model pooled"] = spearmanr(d.ra, d.rb).statistic
        rows.append(r)
print(md(pd.DataFrame(rows)))
h = pd.read_csv(D / "a2_h1_spearman.csv")
print("Pooled across models (task-cluster bootstrap CI):\n")
print(md(h))

print("## T5 Invariance (B1) and adaptation (C1) contrasts: AA minus A x variant similarity, paired by task\n")
k = C[C.kind.isin(["AA-AB", "AA-AC"]) & C.measure.isin(["seq_sim", "file_jacc", "func_jacc", "cos|AB|r2|lgbm_paper", "cos|AC|r2|lgbm_paper"])]
k = k[~((k.kind == "AA-AB") & (k.measure == "cos|AC|r2|lgbm_paper")) & ~((k.kind == "AA-AC") & (k.measure == "cos|AB|r2|lgbm_paper"))]
print(md(k[["model", "kind", "measure", "mean", "ci_lo", "ci_hi"]]))

print("## T6 C1 'already fixed' decisions (share of 55 attempts)\n")
T["submitted"] = T.exit_status == "Submitted"
T["edits_gold_files"] = T.touches_gold_file
T["submitted_no_gold_edit"] = T.submitted & ~T.touches_gold_file
T["verified_noop"] = T.submitted_no_gold_edit & T.resolved
T["inaction"] = ~T.submitted & ~T.touches_gold_file
g = T[T.variant.isin(["A", "C1"])].groupby(["model", "variant"])[
    ["resolved", "edits_gold_files", "submitted_no_gold_edit", "verified_noop", "inaction"]].mean().reset_index()
print(md(g))
c = T[T.variant == "C1"]
print("C1 tests still pass, by whether the agent re-edited the gold files:\n")
print(md(c.groupby(["model", "touches_gold_file"]).resolved.agg(["mean", "size"]).reset_index()))

print("## T7 BCM over {A, C1} (H4, descriptive; 4 models only)\n")
S = pd.read_csv(D / "a1_bcm_summary.csv")
S = S[(S.fitset == "AC") & (S.subset == "bcm")].copy()
S["model"] = S.model.map(SHORT)
v = g[g.variant == "C1"].set_index("model").verified_noop
S["C1_verified_noop"] = S.model.map(v)
print(md(S[["rep", "predictor", "model", "mean", "null_mean", "null_q025", "null_q975", "C1_verified_noop"]]))
