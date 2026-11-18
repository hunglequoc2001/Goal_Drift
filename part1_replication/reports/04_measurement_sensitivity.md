# 04 — Fixed-data measurement sensitivity (A–G)

All analyses use the frozen 9,191-row manifest. Every run's stored X/y hash equals the
baseline hash (author `8d972133…`, role-aware `9cedc52a…`); a mismatch would have aborted.
**Primary = author parser**; role-aware runs are NEW EXPERIMENT / representation sensitivity and
are never pooled with it. Changes in A–D and G are induced by the *measurement procedure*
(folds, predictor, labels, explainer); no trajectory changed. Pre-specified contrasts (DECISIONS D7):
M1 separation `S = min(proprietary) − max(Llama)`, M2 |ΔBCM| per system, M3 rank agreement with
seed 42. Intervals: 2,000-replicate task-cluster bootstrap, paired across variants.
Per-run tables: `results/tables/runs_<stage>_<rep>.csv`; summaries `sensitivity_runs_summary_<rep>.csv`,
`bootstrap_cluster_summary_<rep>.csv`.

## Headline table

| Stage | Author parser: AUC | S range | max |ΔBCM| | min Kendall τ (max pairs reversed /15) | Role-aware: AUC | S range | max |ΔBCM| | min τ (max rev.) |
|---|---|---|---|---|---|---|---|---|
| E0 baseline | 0.728 | 0.487 [0.394, 0.564] | — | — | 0.768 | 0.122 [0.058, 0.205] | — | — |
| A 11 fold seeds | 0.724–0.731 | 0.454–0.494 | 0.026 | 1.00 (0) | 0.762–0.768 | 0.083–0.122 | 0.036 | 0.87 (1) |
| B 9 LightGBM variants | 0.726–0.732 | 0.435–0.596 | 0.123 (GPT-4o) | 0.87 (1) | 0.766–0.771 | 0.084–0.135 | 0.097 | 0.87 (1) |
| B logistic L2 (exploratory) | 0.706 | −0.008 [−0.058, 0.051] | 0.458 | 0.33 (5) | 0.693 | −0.078 [−0.155, 0.002] | 0.236 | 0.60 (3) |
| D task-grouped CV | 0.712 | 0.427 [0.330, 0.516] | 0.044 | 1.00 (0) | 0.753 | 0.110 [0.051, 0.189] | 0.011 | 0.87 (1) |
| C within-system label null (10) | 0.611–0.628 | −0.067–0.267 | — | 0.20 (6) | 0.603–0.619 | −0.069–0.057 | — | 0.60 (3) |
| C global label null (10) | 0.485–0.503 | 0.035–0.190 | — | 0.47 (4) | 0.485–0.509 | −0.044–0.011 | — | −0.33 (10) |

## A. Fold-allocation sensitivity (core)

Per-system BCM range over 11 seeds (author): Claude-3.5 0.772–0.797, Claude-3.7 0.743–0.767,
GPT-4o 0.556–0.587, Llama-405B 0.092–0.111, Llama-70B 0.065–0.078, Llama-8B 0.082–0.095
(SD ≤ 0.010; `A_seed_stability_author.csv`). AUC 0.724–0.731. Ranking identical in all 11 runs.
Role-aware: ranges ≤ 0.043 (GPT-4o); one within-Llama pair flips in 7 of the 10 non-baseline seeds.
**Conclusion: fold assignment is not a material source of instability.** Figure: `fig2_seed_stability`.

## B. Predictor sensitivity (core; predictor-induced, not agent change)

All nine tree variants stay within the pre-specified ±0.03 AUC window (author 0.726–0.732),
so all count as competent. Shallow and regularized models raise GPT-4o by +0.111 [0.075, 0.143]
and +0.123 [0.087, 0.159] (paired task-cluster CIs). Llama-8B moves +0.014 to +0.024, and the
subsampled models raise all Llama values by +0.02 to +0.04. The proprietary–Llama separation
survives every tree variant (S ≥ 0.435). The only reversal is within Llama (Llama-405B vs
Llama-8B, shallow and regularized variants).

The exploratory standardized logistic model (AUC 0.706, also inside the ±0.03 window on the
author parser) **eliminates the separation** (S = −0.008 [−0.058, 0.051]; Llama BCMs 0.41–0.52).
Its exact linear attributions are not TreeSHAP and carry different semantics, so this is a
different-family check, not a replacement estimate. Still, it shows that the order-of-magnitude
gap belongs to the gradient-boosted predictor's attribution geometry, not to the trajectories
alone. Figure: `fig3_predictor_variants`.

## D. Task-grouped CV (core; generalization probe)

StratifiedGroupKFold by `source:instance_id`: zero tasks span train/validation (asserted).
Fold positive rates 0.273–0.274 (stratification essentially perfect). AUC falls 0.728 → 0.712
(author) and 0.768 → 0.753 (role-aware), so some predictive signal is task-memorisation.
BCM moves ≤ 0.044 (GPT-4o −0.044 [−0.080, −0.007]); ranking unchanged. **Task leakage does not
drive the headline BCMs.**

## C. Outcome-label negative controls (mechanism)

Within-system permutation preserves each system's prevalence, so system identity still predicts
the label (null AUC 0.61–0.63 > 0.5). Global permutation leaves no signal (AUC 0.49–0.51).

| System | Author: real | within-system null (min–max) | global null | Role-aware: real | within-system null | global null |
|---|---|---|---|---|---|---|
| Claude-3.5 | 0.785 | 0.689–0.841 | 0.109–0.395 | 0.435 | 0.491–0.566 | 0.007–0.125 |
| Claude-3.7 | 0.759 | 0.713–0.851 | 0.157–0.480 | 0.516 | 0.570–0.735 | 0.021–0.121 |
| GPT-4o | 0.582 | 0.370–0.568 | 0.057–0.219 | 0.254 | 0.303–0.438 | 0.005–0.056 |
| Llama-405B | 0.095 | 0.145–0.386 | 0.009–0.045 | 0.109 | 0.297–0.407 | 0.006–0.069 |
| Llama-70B | 0.065 | 0.242–0.461 | 0.011–0.035 | 0.132 | 0.346–0.453 | 0.012–0.045 |
| Llama-8B | 0.084 | 0.267–0.449 | 0.007–0.032 | 0.109 | 0.283–0.389 | 0.009–0.037 |

Findings:
1. **Claude BCMs under the author parser are indistinguishable from the within-system null.**
   Breaking every trajectory–outcome link leaves them where they were (0.69–0.85 vs 0.76–0.79).
2. **For every Llama system, and for every system under the role-aware parser, real-label BCM is
   below the entire within-system null range.** Real outcome signal *lowers* BCM.
3. Under the author parser, even the global null (no signal at all) gives Claude 0.11–0.48 vs
   Llama ≤ 0.045. The source-specific feature distribution alone produces a separation.

Mechanism (`mechanism_shap_concentration.csv`). In the author E0, `total_steps` carries 39–51% of
squared SHAP norm for every system. Its sign agrees in 95–97% of proprietary rows, which are
mostly 0- or few-step empty parses, and in only 57–58% of Llama rows. Under the within-system null,
a source-identifying length feature (`max_action_length`: the Nebius parse contains a ≈5k-character
system prompt) takes over with ≥94% sign agreement in every system (inspected for permutation seed 101). Across systems, BCM tracks
*poor* within-system discrimination: author-parser within-system AUC is 0.47–0.56 for the
proprietary systems (BCM 0.58–0.79) and 0.71–0.88 for Llama (BCM 0.07–0.10). With six systems,
fully confounded by source, this is descriptive, not a causal law. Figure: `fig6_permutation_null`.

## E. Task sampling and weighting (descriptive)

Same frozen seed-42 SHAP vectors (`E_task_weighting_<rep>.csv`, eligible-task lists
`E0_within_task_eligible_<rep>_<system>.csv`).

| System | tasks (≥3 runs) | global | global, eligible cohort | between-task only, same cohort | within-task | task-balanced 3/task (n) | tasks with 1–2 runs (n) | one run/task, mean [95%] |
|---|---|---|---|---|---|---|---|---|
| Claude-3.5 | 676 (60) | 0.785 | 0.746 | 0.746 | 0.760 | 0.738 (180) | 0.795 (756) | 0.799 [0.784, 0.812] |
| Claude-3.7 | 2,483 (60) | 0.759 | 0.635 | 0.636 | 0.602 | 0.637 (180) | 0.768 (2,751) | 0.772 [0.766, 0.778] |
| GPT-4o | 93 (4) | 0.582 | 0.755 | 0.747 | 0.790 | 0.755 (12) | 0.562 (104) | 0.555 [0.537, 0.572] |
| Llama-405B | 100 (100) | 0.095 | 0.095 | 0.093 | 0.357 | 0.115 (300) | — (0) | 0.105 [0.072, 0.149] |
| Llama-70B | 1,384 (132) | 0.065 | 0.071 | 0.070 | 0.294 | 0.069 (396) | 0.064 (1,554) | 0.064 [0.061, 0.067] |
| Llama-8B | 515 (261) | 0.084 | 0.080 | 0.079 | 0.307 | 0.120 (783) | 0.105 (430) | 0.109 [0.095, 0.125] |

- Global BCM is almost entirely between-task pairs. Task-balancing (3 per task, or 1 per task)
  changes Llama values by ≤ 0.036. Proprietary values move more (Claude-3.7 0.759 → 0.637 on 180
  trajectories; GPT-4o 0.582 → 0.755 on 12 trajectories from 4 tasks). **Over-weighting of frequently attempted tasks does not explain the Llama values.**
- Within-task > between-task for all Llama systems (+0.22 to +0.26), as the paper reports. In the
  role-aware representation this persists (+0.18 / +0.18 / +0.13). Same-task pairs share issue,
  repository and difficulty, so a higher same-task cosine is expected for any policy that adapts
  to the task. It does not by itself show "global fragmentation".
- Proprietary eligible cohorts are tiny (12–190 trajectories), and GPT-4o rests on 4 tasks.
  Figure: `fig5_task_weighting`.

## F. Parser / representation audit (secondary)

At fixed raw trajectories, replacing the author parse with role-aware tool-action extraction:
- changes global BCM by −0.350 / −0.243 / −0.328 (proprietary) and +0.014 / +0.067 / +0.025 (Llama);
- raises AUC 0.728 → 0.768 and within-system AUC for proprietary systems from ≈0.5 to 0.59–0.69;
- shrinks separation S from 0.487 [0.394, 0.564] to 0.122 [0.058, 0.205] (still > 0).

Manual validation (`results/validation/`, 30 records/source, stratified by system and length,
annotated by the AI agent): role-aware step extraction is correct in 60/60 records. The only
agent turns without a step were 4 harness exit messages ("Exit due to cost limit"), which the
author parser counts as actions. The author category regexes produce no false positives in a
120-step random sample, but recall on commands is low (Nebius 0.13, SWE-smith 0.75). Over all
1,883 sampled steps, the regexes assign a category to 17% (Nebius) / 53% (SWE-smith) of steps,
against 90% / 77% under a tool-semantic labeller. Under the author parse, 100% of Nebius system
prompts and issue texts and 100% of observations receive edit/view categories.
The standardized raw-feature cosine depends on centring (Report 03 §5). Figure: `fig7_parser_representation`.

## G. Explainer reference distribution (secondary; explainer perturbation)

Same seed-42 models and rows. Interventional TreeSHAP with three 128-row backgrounds drawn from
each fold's training rows (seeds 211/223/227; IDs stored in `results/arrays/G/<rep>/bg*.npz`).
Pilot (300 rows/system) then full cohort.

| System | Author: tree-path | interventional (3 bg) | Role-aware: tree-path | interventional |
|---|---|---|---|---|
| Claude-3.5 | 0.785 | 0.768–0.788 | 0.435 | 0.387–0.438 |
| Claude-3.7 | 0.759 | 0.768–0.784 | 0.516 | 0.530–0.561 |
| GPT-4o | 0.582 | 0.535–0.576 | 0.254 | 0.250–0.290 |
| Llama-405B | 0.095 | 0.135–0.147 | 0.109 | 0.173–0.190 |
| Llama-70B | 0.065 | 0.108–0.116 | 0.132 | 0.193–0.208 |
| Llama-8B | 0.084 | 0.116–0.130 | 0.109 | 0.172–0.191 |

Per-row cosine to tree-path attributions: median 0.92–0.97. Ranking of proprietary vs Llama is
unchanged. Llama BCMs rise by 38–78% relative, which matters for any ratio-style reading
("an order of magnitude lower"). **Author parser: interventional SHAP additive on all rows.
Role-aware: shap 0.51's interventional routine is non-additive on 20–40% of rows per background
(max error 0.33), and its `expected_value` is off from the mean background margin by up to 0.16
under both parsers (DECISIONS D15).** BCM on additive rows only is close (Claude-3.7
0.516–0.560), but the role-aware G numbers should be treated as unreliable.
Figure: `fig8_background_G`.

## Ranking reversals (`fig4_ranking_heatmap`)

Across 19 tree-model A/B/D runs (author), no proprietary–Llama pair ever reverses. Within-group
pairs are unstable: Llama-405B vs Llama-8B in 11% of runs, and in 29% of task-cluster bootstrap
replicates at baseline. Role-aware: Llama-405B vs Llama-8B reverses in 58% of runs. Claude-3.5 vs
Claude-3.7 is ordered with bootstrap probability 0.95 (author) but in the opposite direction
under the role-aware parser.

## Summary against the decision rules

- Core tests A/B/D: the published *ordering between groups* is robust to folds, competent tree
  predictors and task-grouped CV; *magnitudes* move up to 0.12 (GPT-4o), and within-group order
  is fragile.
- That robustness does not transfer across a different-family predictor, a corrected parser, or
  the label nulls. The separation is ≈0 under the logistic model and shrinks 4× under the role-aware
  parser. Within-system label permutation reproduces the Claude values.
- Mechanism: the headline separation is mostly produced by (i) source-specific parsing, including
  2,513 empty parses that share one SHAP vector per fold, and (ii) a joint predictor that encodes
  source via length features. It is not produced by success-relevant behavioural structure within
  the proprietary systems, which the predictor cannot discriminate (within-system AUC ≈ 0.5).
