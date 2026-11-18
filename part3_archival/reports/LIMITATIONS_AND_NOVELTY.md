# Limitations and novelty (Exp02)

## Limitations / validity threats
1. **One attempt per model-task.** Nothing here measures within-model repeatability or run-to-run variance.
   Same-task similarity (§6 of RESULTS) mixes task-induced and stochastic variation.
2. **Archived systems are not interventions.** "Model" bundles weights, API provider, context window
   (128k–1M), reasoning settings (GPT-5 `high`) and hidden-reasoning behaviour. Contrasts are descriptive.
3. **Few open-weight systems.** GLM-4.5 (primary), gpt-oss-120b and Kimi-K2 (paper-50). Open vs proprietary
   is 1-vs-4 and 2-vs-1. No group-level open/proprietary claim is made.
4. **Config irregularities inside "same-config" runs**: 109 Sonnet-4.5 trajectories with an 85-call limit and 116
   Gemini trajectories with a 900k context. Handled by the `primary5_cfgclean` sensitivity (496 tasks); conclusions unchanged.
5. **Outcome labels.** Recomputed with the official rule. 98–99% agreement where official labels exist. 14
   disputed tasks are excluded. Three primary models have no official file. Paper-100 "Opus" labels
   agree only 83% with an official file of the same name (possibly a different run).
6. **Features.** The 12 BCM features are reproduced as defined by the original paper and code, including
   its regex categoriser. That categoriser labels 42–66% of real tool actions "other", so BCM inherits a weak
   feature set. R3 is our own categoriser: deterministic and unit-tested, but not human-validated.
7. **Bootstrap scope.** Task-cluster bootstrap CIs hold the fitted attributions fixed. CV-seed variability is
   reported separately. Neither covers model-selection uncertainty.
8. **Human validation pending.** The review sheets (24 parsed steps; 40 paired tasks × 5 models) have
   empty human columns. AI spot checks are not human annotation.
9. **Single benchmark.** SWE-bench Pro public set (11 repositories, Go/Python/JS/TS). The task-language
   effect on BCM (Python −0.16 alignment) shows that population composition matters.

## Novelty relative to existing work
**Nilenso (2025), "SWE-bench Pro: Comparative Analysis of GPT-5 vs Claude Sonnet 4.5 trajectories"**
(`data/raw/_meta/nilenso`, sha 1169deb).
- *Overlap:* the same archives (GPT-5 and Sonnet-4.5 250-turn runs), the same `.traj` schema, per-model step,
  cost, token and tool-usage profiles. They also found that GPT-5's `message.content` is empty and that this
  breaks a downstream metric (`tokens_received` undercount, 7–8×). We credit this observation.
- *Difference:* they describe *how models behave* (cost, length, tool mix) and make no claim about consistency
  measurement. We ask whether a published **behavioural-consistency metric** measures what it claims. We test
  it with matched tasks, controlled representations, alternative predictors, label-permutation nulls,
  task-grouped CV, bootstrap, ranking stability, and a companion-pooling experiment. The empty-content
  phenomenon matters to us only because it silently drives the BCM ranking (GPT-5 rank 1 → 5).
- *Extension:* we add 4 more models in the same config (Haiku-4.5, Sonnet-4, GLM-4.5, Gemini) and the
  paper-config cohorts with two open-weight models. We also document folder mislabelling and within-run
  config deviations that affect any analysis of these archives.

**Raichura & Banerjee (arXiv:2608.13598), BCM.** We reproduce their pipeline exactly (Exp01-V: bit-exact
regeneration of their shipped artifacts). New relative to them: (a) the metric's dependence on pooled
companions (BCM ≈ 0 per system), (b) BCM ≈ within-model label-permutation null on a clean cohort,
(c) representation-driven rank reversal within one benchmark.

**Contribution statement for the paper.** A construct-validity analysis of cross-task behavioural
consistency measurement under controlled trace instrumentation. Concrete, reproducible failure paths
(parser asymmetry, hidden reasoning, leaky model selection, explainer defects), a mechanism (attribution
concentration created by pooling heterogeneous systems), and diagnostics any agent-consistency metric
should report: per-system and companion-sensitivity values, within-system null, within-system AUC, and
representation sensitivity.
