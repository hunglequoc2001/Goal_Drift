# Exp02 executive summary: BCM on public SWE-bench Pro trajectories ($0)

**Question.** Does BCM's "agent behavioural consistency" signal survive on a single benchmark, with one scaffold,
one native trace schema and matched tasks? How much of it is tied to the outcome predictor rather than to
task-relevant agent behaviour?

**Data.** 9,139 public SWE-agent 1.1 trajectories (13 runs, 86 GB, anonymous download, checksummed).
Primary cohort: GPT-5, Claude Sonnet-4.5, Claude Haiku-4.5, GLM-4.5 (open-weight) and Gemini-2.5-Pro under the
identical 250-turn leaderboard config, on **715 matched tasks**. Secondary: GPT-5-high vs gpt-oss-120b vs Kimi-K2
(50-call config). **Each model has one attempt per task, so these results say nothing about repeatability.**

## Defensible claims
1. **Representation alone reverses the BCM ranking within one benchmark.** The original authors' loader drops
   steps whose thought text is empty. GPT-5 hides its reasoning, so 58% of its trajectories parse to zero steps,
   and GPT-5 ranks first (BCM 0.554 [0.538, 0.570]). Under role-aware parsing it ranks last (0.041 [0.031, 0.052]).
   Both orderings hold with bootstrap probability 1.00. The same happens to gpt-oss (0.494 → 0.016).
2. **On the clean cohort, BCM is reproduced without outcome information.** For all 5 primary models, real-label
   BCM (0.04–0.13) lies within the 5–95% band of 50 within-model label permutations, which keep each model's
   success rate but destroy the trajectory–outcome link. This holds with the released LightGBM and with
   logistic regression. Exception: tool-semantic features (R3), where 3 models modestly exceed their nulls.
3. **BCM magnitude is an artefact of pooling systems.** With the predictor fit on one system's trajectories
   alone, every system's BCM is 0.001–0.019, although those predictors are informative (within-system AUC
   0.61–0.77). BCM grows with the number of co-pooled systems. Kimi-K2 goes from 0.006 alone to 0.505 with two
   companions, because one length feature places all Kimi rows on one side of the pooled model.
4. **Task structure dominates.** Two *different* models on the *same* task have more similar attribution
   vectors (cosine up to 0.46) than one model across tasks (BCM ≤0.13). This is descriptive only, with one
   attempt per model-task.
5. **Magnitudes and ranks depend on measurement choices.** The predictor family changes magnitudes up to 4×.
   Kendall τ of the ranking across representation × predictor configurations ranges from −0.4 to +0.6.
   Within a fixed configuration, rankings are stable across CV seeds (τ 0.8–1.0) and between task-grouped CV
   and leave-one-repository-out CV.

## Not supported
- The original paper's "proprietary ≫ open-weight" consistency gap. In the matched cohort open GLM-4.5 lies
  between proprietary systems. In paper-50 the two open models are the highest and the lowest.
- Reading global BCM as an agent's stable, success-relevant decision pattern.

## Data-quality findings useful beyond BCM
Two S3 folders are mislabelled (Sonnet-4 ↔ Opus-4.1). 109 Sonnet-4.5 and 116 Gemini trajectories in the
"same-config" leaderboard runs used deviant limits. 14 tasks have official labels that contradict the official
rule on the archived outputs, consistently across models.

## Agreement with prior results
Consistent with Exp01 (parser artefacts, real ≤ null, predictor sensitivity) and Exp01-V (published numbers
come from a leaky model). New in Exp02: within-benchmark rank reversal, BCM ≈ 0 per system, and companion
dependence. Open for Exp03: whether BCM tracks *repeated-run* stability and *appropriate adaptation* on
controlled task variants, which archival data cannot test.

Reports: `PROVENANCE_DECISION.md`, `PARSER_VALIDATION.md`, `RESULTS.md`, `LIMITATIONS_AND_NOVELTY.md`,
`COST_AND_DATA_ACCESS.md`, `REPRODUCE.md`. Figures: `results/figures/` (captions in `CAPTIONS.md`).
