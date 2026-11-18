"""Parser validation for Exp02 (writes results/tables/parser_* and results/validation/*).

1. Programmatic invariants per run: role-aware steps == tool-call messages; == non-empty trajectory[] actions
   minus harness steps; zero-step counts per representation; harness messages; multi-call messages.
2. Role leakage: fraction of role-aware steps that contain the system prompt, the instance template,
   'OBSERVATION:' or the problem statement (should be ~0); fraction of R1 'steps' that are non-agent messages.
3. Category distributions (BCM regex categories vs tool-semantic categories) per run.
4. Seeded audit sample: 40 trajectories stratified by run x outcome; per trajectory 1 random step ->
   human review sheet (first 24 rows) with empty human columns.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/src")
from bcm_validity.features import categorize  # noqa: E402
from bcm02.pipeline import COHORTS, load_cohort  # noqa: E402

OUT_T, OUT_V = Path("results/tables"), Path("results/validation")
OUT_V.mkdir(parents=True, exist_ok=True)
T = pd.read_parquet("data/interim/trajectories.parquet")
S = pd.read_parquet("data/interim/steps.parquet")
v1 = pd.read_parquet("data/raw/_meta/swe_bench_pro_hf/data/v1/test-00000-of-00001.parquet").set_index("instance_id")

# 1 invariants
inv = T.groupby("run").agg(
    n=("instance_id", "size"),
    r0_zero=("r0_n", lambda s: int((s == 0).sum())), r1_zero=("r1_n", lambda s: int((s == 0).sum())),
    r2_zero=("r2_n", lambda s: int((s == 0).sum())),
    r0_median_steps=("r0_n", "median"), r1_median_steps=("r1_n", "median"), r2_median_steps=("r2_n", "median"),
    frac_empty_thought=("frac_action_msgs_empty_content", "mean"),
    harness_msgs=("n_harness_msgs", "sum"), multi_call_msgs=("n_multi_call_msgs", "sum"),
    r2_eq_toolcall_msgs=("r2_n", "size"))
inv["r2_eq_toolcall_msgs"] = T.assign(ok=T.r2_n == (T.n_action_msgs - T.n_harness_msgs)).groupby("run").ok.mean()
inv["r2_eq_traj_nonempty_frac"] = T.assign(ok=T.r2_n == T.n_traj_nonempty_actions).groupby("run").ok.mean()
inv["r2_minus_traj_nonempty_max_abs"] = T.assign(d=(T.r2_n - T.n_traj_nonempty_actions).abs()).groupby("run").d.max()
inv.to_csv(OUT_T / "parser_invariants.csv")
print(inv.round(3).to_string())

# 2 role leakage on role-aware steps
sys_prompt = "You are a helpful assistant that can interact with a computer"
leak = []
for run, g in S.groupby("run"):
    a = g.action.fillna("")
    leak.append(dict(run=run, n_steps=len(g),
                     contains_system_prompt=float(a.str.contains(sys_prompt, regex=False).mean()),
                     contains_uploaded_files_tag=float(a.str.contains("<uploaded_files>", regex=False).mean()),
                     starts_with_OBSERVATION=float(a.str.startswith("OBSERVATION").mean()),
                     contains_pr_description_tag=float(a.str.contains("<pr_description>", regex=False).mean()),
                     empty=float((a.str.strip() == "").mean()),
                     median_action_len=float(g.action_len.median())))
# problem statement leakage (exact first 200 chars of issue text inside a step), sampled 20k steps
samp = S.sample(min(20000, len(S)), random_state=1)
ps = v1.problem_statement.str[:200]
hit = [ps.get(i, "") != "" and isinstance(ps.get(i), str) and len(ps.get(i)) > 50 and ps.get(i) in a
       for i, a in zip(samp.instance_id, samp.action.fillna(""))]
L = pd.DataFrame(leak)
L["problem_statement_in_step_frac_sampled"] = L.run.map(samp.assign(h=hit).groupby("run").h.mean())
L.to_csv(OUT_T / "parser_role_leakage.csv", index=False)
print(L.round(4).to_string(index=False))

# 3 categories
S["bcm_regex_category"] = [categorize(a) for a in S.action.fillna("")]
cat = pd.concat([S.groupby("run").bcm_regex_category.value_counts(normalize=True).unstack(fill_value=0).add_prefix("regex_"),
                 S.groupby("run").category.value_counts(normalize=True).unstack(fill_value=0).add_prefix("sem_")], axis=1)
cat.to_csv(OUT_T / "parser_category_distribution.csv")
agree = pd.crosstab(S.category, S.bcm_regex_category, normalize="index")
agree.to_csv(OUT_T / "parser_regex_vs_semantic_crosstab.csv")
print(cat.round(3).to_string()); print(agree.round(2).to_string())

# 4 audit sample + human review sheet
rng = np.random.default_rng(20261026)
runs = sorted(set(sum(COHORTS.values(), [])))
P = load_cohort("primary5")
pick = []
for run in COHORTS["primary5"] + COHORTS["paper50"]:
    g = T[(T.run == run) & T.in_v1]
    for res in [True, False]:
        gg = g[g.resolved == res]
        k = 3 if run in COHORTS["primary5"] else 2
        pick += list(rng.choice(gg.index, min(k, len(gg)), replace=False))
pick = pick[:40]
rows = []
for i in pick:
    r = T.loc[i]
    st = S[(S.run == r.run) & (S.instance_id == r.instance_id)]
    j = int(rng.integers(len(st))) if len(st) else -1
    s = st.iloc[j] if j >= 0 else None
    rows.append(dict(run=r.run, instance_id=r.instance_id, repo=r.repo, resolved=bool(r.resolved),
                     n_r0=int(r.r0_n), n_r1=int(r.r1_n), n_r2=int(r.r2_n), step_idx=j,
                     parsed_action=(s.action[:600] if s is not None else ""),
                     obs_excerpt=(s.obs_head[:300] if s is not None else ""),
                     semantic_category=(s.category if s is not None else ""),
                     bcm_regex_category=(categorize(s.action) if s is not None else ""),
                     human_is_agent_action="", human_expected_category="", human_notes=""))
A = pd.DataFrame(rows)
A.to_csv(OUT_V / "audit_40.csv", index=False)
A.head(24).to_csv(OUT_V / "human_review_sheet_24.csv", index=False)
print("audit rows", len(A))
