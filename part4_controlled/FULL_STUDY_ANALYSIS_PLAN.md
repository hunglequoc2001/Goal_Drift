# Exp03 full study: analysis plan (frozen before any confirmatory attempt is run)

Version 1.1, 2026-10-30 (v1.0 of 2026-10-27 updated with the accepted task counts, the staging gate outcome and the power results; no confirmatory data existed at either date). Implementation: `src/bcm03/ingest_full.py`, `src/bcm03/measures.py`, `src/bcm03/analysis_full.py`.
Design: `FULL_STUDY_FINAL_DESIGN.md`. Power: `results/full_prep/power/` (`src/bcm03/power.py`). Any deviation from this
plan is dated and justified in `../RESEARCH_DECISIONS.md` and reported as a deviation.

## 1. What BCM claims to measure, and what this study tests
BCM (Raichura & Banerjee) is a model-level score: the mean pairwise cosine between per-trajectory SHAP attribution vectors
of a success predictor fit on trace features, taken over a model's trajectories on different tasks. It is presented as
measuring how consistently an agent behaves. We test the evidence a valid consistency measure should produce, and we
keep three constructs apart:

| construct | question | measured from |
|---|---|---|
| behavioural consistency | do two runs of the same model on the same task do the same thing? | final repository state, tests, trace |
| task appropriateness | does the intervention fit the task (edit scope, editing only when needed, adapting to a changed requirement, no regressions)? | final state vs gold patch, C1/C2 oracles |
| final correctness | do the tests pass? | executable oracle |

A consistently failing agent can be consistent. So high BCM for a degenerate agent is not, on its own, evidence against
BCM. Qwen2.5-Coder-7B is a pre-registered degenerate-agent control, reported separately and excluded from pooled
validity estimates. The claims below are about the construct (consistency) and about whether BCM's attribution
geometry tracks it.

## 2. Units and data
- **Attempt.** One model × task × variant × seed run, in a fresh container. Analysed attempts are all confirmatory-phase
  attempts with a `result.json`. Infrastructure failures (health check failed, job killed) are rerun with the same seed
  and are never analysed as agent behaviour. Staging and pilot data are never pooled with confirmatory data.
- **Cell.** Model × task × variant. Pairs are the unordered pairs of attempts within a model × task: AA, AB (A × B),
  AC (A × C), and so on.
- **Clusters.** Task (primary resampling unit, shared by all models) and repository (sensitivity resampling unit).

## 3. Measures (definitions in `bcm03.measures`)
| measure | level | definition | task-grounded? |
|---|---|---|---|
| resolved | attempt | official SWE-bench grading of the submission | yes (correctness) |
| resolved_state | attempt | grading of the sandbox's final `git diff` (independent of submission format) | yes (correctness) |
| f2p_agree | pair | share of FAIL_TO_PASS tests with equal pass/fail status | yes |
| patch_sim_cond | pair | Jaccard of normalised changed source lines; defined only if both runs edited source | yes |
| func_jacc_cond | pair | Jaccard of edited file::function targets; defined only if both runs edited source | yes |
| edit_decision_agree | pair | both runs edited source, or neither did | partly (the edit-count feature encodes it) |
| outcome_concord | pair / cell | equal resolved status; reported with the cell solve rate and the chance-corrected concordance (kappa) | yes, but circular for attributions of a success predictor |
| seq_sim | pair | 1 − normalised Levenshtein distance of action-category sequences | **no**: trace-derived, same source as the BCM features |
| scope_precision / scope_recall | attempt | edited source files ∩ gold files / edited, resp. / gold | yes |
| harmful | attempt | at least one PASS_TO_PASS test fails | yes |
| c1_class | attempt | recognized_noop, recognized_noop_text_submission, inaction, harmless_edit, harmful_edit, other | yes (+ text heuristic, audited by humans) |
| c2_class | attempt | adapted (revised oracle passes), persisted_original (original oracle passes, revised fails), failed | yes |
| cos | pair | cosine of the two attempts' OOF attribution vectors (fit set as named) | (the object under test) |
| BCM | model | mean pairwise cosine over a model's attempts (the paper's definition) | (the object under test) |

File-level Jaccard is computed but not used as a primary measure: it is ≈1 for practically every editing pair on
SWE-bench Verified (pilot addendum A2).

## 4. Attribution pipeline (same code as the pilot and Exp02)
- **Fit sets.** A (primary); A+B2, A+B1 (invariance); A+C2 (adaptation). The predictor is pooled over models as in the
  paper. Label = resolved. For C2 the label comes from the revised oracle.
- **Predictors / representations.** Released LightGBM on R2 (BCM12 features on role-aware steps; **primary**).
  Standardised logistic regression on R2. Released LightGBM on R3 (semantic categories).
- **CV.** StratifiedGroupKFold by task, 5 folds, 10 CV seeds for real labels. All variants of a task share a fold.
- **Nulls (50 seeds each).** Labels permuted within model, and within model × repository.
- **AUC.** Pooled out-of-fold AUC. Within-model AUC only for models with both outcome classes in the fit set; it is
  never imputed.
- **SHAP validity.** Tree-path TreeSHAP with additivity asserted on every fold (tolerance 1e-6), plus agreement with
  LightGBM's own `pred_contrib` on each fit set. shap's interventional explainer is not used (Exp01-V V6). A
  configuration failing either check is quarantined (`shap_quarantine.csv`) and excluded.

## 5. Hypotheses, endpoints and decision rules
All CIs are percentile task-cluster bootstrap CIs (2000 resamples; tasks resampled jointly for all models), unless
stated. Co-primary endpoints within a family are Bonferroni-adjusted: H1 has 2 (decisions use 97.5% CIs), H2 has 4 (TOST at one-sided alpha 0.0125, i.e. 97.5% CIs), H3/H4 have 1 each. Everything not listed as primary is secondary and
reported as estimation without significance claims.

### H1 Convergent validity of attribution similarity (primary family)
Does attribution similarity between two runs on the same task track task-grounded similarity of what they did?
- **Statistic.** Within-cell correlation r_w between cos (A fit, R2, released LightGBM) and y over AA pairs, with cell
  means removed (removes task-level confounding), pooled over non-degenerate models.
- **Co-primary y.** `patch_sim_cond` and `f2p_agree`.
- **Decision.** H1 is supported for y if the Bonferroni-adjusted (97.5%) CI lower bound is > 0. The association is called
  substantive if the lower bound is > 0.1.
- **Trace reference.** r_w for the trace-derived `seq_sim`, and the gap Δ = r_w(seq_sim) − r_w(y) with CI. A large
  gap means attribution similarity mostly reflects shared trace structure, not task-grounded behaviour.
- **Secondary.** Per-model r_w. Cell-level (between-task) r. `edit_decision_agree`, `func_jacc_cond`,
  `outcome_concord` (noted as circular). Logistic and R3 attributions.

### H-BCM Does BCM reflect outcome-relevant agent behaviour?
- **Per model.** Real BCM vs the two permutation nulls (mean, 2.5–97.5% quantiles, add-one p). Task-cluster CI of
  BCM.
- **Decomposition.** Mean cos over same-task pairs vs different-task pairs (what BCM averages). Per-model-fit BCM.
- **Repeatability.** Within-task repeatability per model (task-grounded measures, solve rate, chance-corrected
  concordance) with CIs.
- **Model level.** BCM rank vs repeatability rank across the 5 non-degenerate models is **descriptive only** (n = 5).
  Pairwise model contrasts (paired by task) carry the inferential weight.
- **Degenerate control.** The 7B model is reported separately: BCM, repeatability, outcome classes.

### H2 Invariance under a task-preserving change (A vs B2; primary family)
- **Statistic.** D_t = S_AA(t) − S_AB2(t), with S the mean pair similarity. This is additional dissimilarity beyond
  the natural A-vs-A repeat variability.
- **Co-primary measures (equivalence claims).** `patch_sim_cond`, `f2p_agree`, `seq_sim`, cos (A+B2 fit). With 58 B2 tasks the pooled equivalence power at a true shift of 0 is ≈ 1.0 / 0.78 / 1.0 / 0.91 (Bonferroni); at a true shift of 0.025 it is 0.67 / 0.32 / 0.94 / 0.36.
- **Estimation only (no equivalence claim).** The solve-rate difference p_B2 − p_A: at 58 tasks the ±0.05 test has power 0.26 (Bonferroni), so its CI is reported and interpreted as precision, not as invariance.
- **TOST.** Equivalence is claimed if the Bonferroni-adjusted CI (97.5%; the 90% CI is also reported) of the mean of
  D_t (pooled over non-degenerate models; per model as secondary) lies within ±0.05 (§6). Difference is claimed if the 95% CI excludes 0. A result that is neither is
  inconclusive. A nonsignificant difference is never read as invariance.
- **Secondary.** `seq_sim`, `edit_decision_agree`. BCM on B2 attempts vs A attempts within the A+B2 fit.
  B1 (weak control) on its 20-task subset, pooled.

### H3 Appropriate adaptation to a changed requirement (A vs C2; primary family)
- **Endpoints.** Per model and pooled: the share of C2 attempts that **adapted** (revised oracle passes) and that
  **persisted** (implemented the original requirement: original oracle passes, revised fails), with task-cluster
  CIs. Reported next to the A solve rate on the same tasks.
- **Estimation target.** Pooled 95% CI half-width ≤ 0.06 (§7). No directional hypothesis about agents is needed. The
  C2 data exist for H4.

### H4 Do trace attributions distinguish adaptation from persistence? (primary family)
- **Statistic.** AUC of the A+C2 success predictor's out-of-fold margin (centred within model) for adapted vs
  persisted C2 attempts, pooled over non-degenerate models.
- **Decision.** "Attributions cannot tell adaptation from persistence" if the 90% CI ⊂ [0.40, 0.60]. "They can" if
  the 95% CI excludes 0.5. Otherwise inconclusive.
- **Feasibility caveat.** With 45 C2 tasks (720 attempts) and 30% adapted, the 95% half-width of the AUC is ±0.08 / ±0.09 / ±0.14 when 15% / 10% / 4% of attempts persist. Staging saw 1 persisted of 24. If fewer than 50 persisted attempts accrue, H4 is reported as inconclusive and not tested.
- **Secondary.** BCM(A+C2) − BCM(A+B2) per model.

### C1 Already-fixed decisions (secondary, diagnostic)
- Class rates per model with CIs on the 20-task subset, using final-state correctness.
- All `other` and text-submission attempts and a seeded sample of the rest go to human review. A rate is reported as
  human-validated only after review.

## 6. Equivalence margins (pre-registered)
The ±0.05 margin applies to all similarity measures on [0, 1] and to the solve rate. Reasons:
1. **Smaller than a small standardized effect.** It is 0.1–0.27 pair-level SDs of the natural A-vs-A distribution in
   the pilot (patch_sim 0.32, seq_sim 0.19, cos 0.47), so it is below Cohen's "small" (0.2 SD) for the noisiest
   measures and comparable for seq_sim.
2. **Benchmark-relevant.** 5 percentage points of solve rate is below typical gaps between adjacent systems on public
   SWE-bench leaderboards.
3. **Attainable.** At 100 tasks the pooled 90% CI half-width is about 0.01–0.02, so the test can conclude in either
   direction (`power_h2_tost.csv`).

The margin is fixed. It is not tuned after seeing data.

## 7. Precision and power (from `results/full_prep/power/`)
See FULL_STUDY_FINAL_DESIGN.md §5 for the numbers behind the chosen design. Power for detecting an effect and the
precision of an estimate are reported separately. Where a hypothesis would be underpowered under a design, the claim
it could support is downgraded to estimation.

## 8. Exclusions and sensitivity analyses (pre-registered)
- **Context overflow** (`ContextWindowExceededError`) and the 3600 s agent wall-clock cap count as failures, as in
  the official harness. Sensitivity: refit with these attempts dropped (`s_sensitivity.csv`).
- **Correctness definition.** Final-state correctness (`resolved_state`) instead of the official submission grading,
  for C1 and as a sensitivity everywhere.
- **Resampling unit.** Repository-cluster bootstrap instead of task-cluster.
- **Excluded models.** Models failing the staging inclusion gate (solve ≥ 3 distinct staging-pool tasks on A, format
  compliance ≥ 0.90) are excluded from all analyses. Outcome of the gate (staging, 22 A attempts each): Qwen2.5-Coder-32B passes (4 tasks, 0.955); gpt-oss-120b **fails** (4 tasks, format compliance 0.656) and is excluded. Staging data are reported, not pooled.
- **Excluded tasks.** Tasks whose variant fails validation do not enter that condition. They remain in A.
- **Tasks.** A: 99 main tasks (+12 C2-extension tasks, used only as the C2 baseline). B2: 58 tasks. C2: 45 tasks (33 main + 12 extension). B1/C1: 20-task subset. Task sets are fixed by `make_manifest.py` from the validation results and are not changed after launch.
- **B2 sensitivity.** H2 repeated on B2 tasks for which neither AI-review pass flagged an added hint (reviewer is oversensitive; treated as sensitivity, not as a filter).
- **Hardware covariate.** `gpu` (H200 or 2×RTX 6000 Pro for the 32B models) is added as a covariate in a sensitivity analysis of repeatability.
- **Selection.** Accepted vs rejected B2/C2 tasks are compared on A solve rate and edit rate; repository- and difficulty-stratified acceptance rates are reported.

## 9. What will not be claimed
- No causal claims beyond the manipulations (B2, C2, C1).
- No claim that BCM is invalid because the degenerate control scores high.
- No human-validated claim about B2 fidelity, C2 meaning or C1 recognition until the human-review sheets
  (`../human_review/`) are completed. Until then those claims are qualified as "validated by executable and automatic
  checks only".
- No generalisation beyond SWE-bench Verified Python tasks, one scaffold (mini-swe-agent), fixed sampling
  (T = 0.7, top_p = 0.8) and the six models.
