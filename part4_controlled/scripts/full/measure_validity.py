"""Discriminative validity of behaviour measures on pilot A pairs, and how much of the attribution-behaviour association
is explained by raw trace-feature similarity (shared-source confound).
For each pair of A attempts (same model, same task): fsim = cosine of the two attempts' z-scored R2 feature vectors
(z-scored over all pilot A attempts). Reported per behaviour measure y (pooled over non-degenerate models):
  n, share of pairs at the ceiling (y==1) and at the floor (y==0), SD of y, between-task share of variance (ICC-like),
  within-cell Pearson r(cos, y)   and   partial r(cos, y | fsim)  and  r(fsim, y).
"""
import numpy as np, pandas as pd
P = pd.read_parquet("results/full_prep/power/pilot_pairs_v2.parquet")
T = pd.read_parquet("results/analysis/pilot_v2_measures/attempts.parquet").set_index("run_id")
F = [c for c in T.columns if c.startswith("r2_")]
A = T[T.variant == "A"]
Z = (A[F] - A[F].mean()) / A[F].std().replace(0, 1)
Z = Z.fillna(0)
P = P[(P.kind == "AA") & (P.model != "qwen2.5-coder-7b")].copy()
u = Z.loc[P.a].to_numpy(); v = Z.loc[P.b].to_numpy()
P["fsim"] = (u * v).sum(1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1) + 1e-9)
P["cell"] = P.model + "|" + P.instance_id
def cen(d, c): return d[c] - d.groupby("cell")[c].transform("mean")
def pr(x, y, z):
    rx = x - np.polyval(np.polyfit(z, x, 1), z); ry = y - np.polyval(np.polyfit(z, y, 1), z)
    return float(np.corrcoef(rx, ry)[0, 1])
rows = []
for y in ["seq_sim", "edit_decision_agree", "outcome_concord", "f2p_agree", "patch_sim_cond", "func_jacc_cond", "file_jacc_cond"]:
    if y not in P: continue
    d = P.dropna(subset=["cos", y, "fsim"]).copy()
    if len(d) < 30: continue
    c = cen(d, "cos"), cen(d, y), cen(d, "fsim")
    tot = d[y].var(); within = (d[y] - d.groupby("cell")[y].transform("mean")).var()
    rows.append(dict(measure=y, n_pairs=len(d), ceiling_share=float((d[y] >= .999).mean()), floor_share=float((d[y] <= .001).mean()),
                     sd=float(d[y].std()), between_cell_var_share=float(1 - within / tot) if tot > 0 else np.nan,
                     r_cos_y=float(np.corrcoef(c[0], c[1])[0, 1]), r_fsim_y=float(np.corrcoef(c[2], c[1])[0, 1]),
                     r_cos_fsim=float(np.corrcoef(c[0], c[2])[0, 1]), partial_r_cos_y_given_fsim=pr(c[0].to_numpy(), c[1].to_numpy(), c[2].to_numpy())))
R = pd.DataFrame(rows); R.to_csv("results/full_prep/measures/measure_validity_pilot.csv", index=False)
print(R.round(3).to_string())
