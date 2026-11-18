# Exp03 full study: final design (proposed; awaiting researcher review)

Status 2026-10-30: **not launched.** Manifest `configs/full/manifests/confirmatory_v1.csv` (+ `.meta.json` with file hashes),
design `configs/full/designs/confirmatory_v1.json`. Analysis plan: `FULL_STUDY_ANALYSIS_PLAN.md`. Readiness:
`FULL_STUDY_READINESS_REPORT.md`. Cost: `FULL_STUDY_COST_ESTIMATE.md`.

## 1. Recommendation in one table

| | Original (D0) | Proposed in brief (D1) | **Final (this design)** |
|---|---|---|---|
| Attempts | 15,000 | 6,680 | **4,645** |
| Models | 6 | 6 (4 primary) | **5** (4 primary + 7B control) |
| Tasks, A | 100 | 100 | 99 (+12 C2-extension tasks) |
| Tasks, B2 | 100 | 100 | **58** (accepted B2) |
| Tasks, C2 | 100 | 100 | **45** (33 main + 12 extension; accepted C2) |
| B1 / C1 | 100 / 100 | 20 / 20 | 20 / 20 |
| Repeats A / B2 / C2 / B1,C1 | 5 / 5 / 5 / 5 | 5 / 4 / 4 / 3 | 5 / 4 / 4 / 3 (7B control: A, 3) |
| Model GPU-h (steady) | 136 | 67 | **48.5** (60.6 with 25% scheduling overhead; 107 at pilot efficiency) |

The reduction below D1 is driven by what the validation could actually accept, not by an attempt target: only 58 of the
99 main tasks have a B2 that passed all checks, and 45 tasks have a C2 that passed all checks. gpt-oss-120b failed the
staging gate and is out; Qwen2.5-Coder-32B passed it.

## 2. Models (`configs/full/models.json`, revisions pinned)
Primary (all conditions): Qwen3-Coder-30B-A3B-Instruct, Devstral-Small-2507, SWE-agent-LM-32B, Qwen2.5-Coder-32B-Instruct.
Control (A only, 3 repeats): Qwen2.5-Coder-7B-Instruct, the pre-specified degenerate agent.
Excluded after staging: gpt-oss-120b (format compliance 0.656 < 0.90 gate: 10 of 22 attempts end in `RepeatedFormatError` under the
text-based action format). Llama-3.3-70B-Instruct was not usable (gated, manual approval, no HF token on this account), so there is **no
~70B model**; this limits the scale-contrast claim to ≤ 32B dense and the 30B MoE.
Scaffold, prompts, sampling (T 0.7, top-p 0.8, 4096 max tokens, 50 steps, 32k context, 3600 s agent cap) are identical for every model.
GPU type may differ between attempts (1 × RTX 6000 Pro, H200, or 2 × RTX 6000 Pro with TP=2 for the 32B models); each result records `gpu` and `slurm_job`.

## 3. Tasks
- **Main sample (99 tasks).** Seeded stratified draw (`scripts/full/select_tasks.py`, seed 20261027): repository × difficulty strata, Django capped at 30,
  pilot tasks excluded, `>4 hours` tasks excluded. A task is replaced by the next task in the same stratum only if its original oracle fails
  (gold resolves, empty does not). One stratum (psf/requests, easy) had no replacement left, so the sample has 99 tasks, not 100.
- **B2 set (58 tasks):** main tasks whose B2 passed all checks. **C2 set (45 tasks):** 33 main tasks plus 12 *extension* tasks: tasks in the seeded candidate pool
  that were not needed to fill a main quota and have a valid original oracle and a valid C2. Extension tasks also receive A runs (their C2 baseline).
- **B1/C1 subset (20 tasks):** the first 20 main tasks in a seeded random order with valid B1 and C1.
- **Selection bias (documented, to be analysed).** Acceptance rates differ by repository (C2: Django 14/42, pydata 7/10, sympy 7/28, scikit-learn 5/12,
  astropy 5/11, sphinx 5/14, matplotlib 1/14, pytest 1/9 among candidate tasks). B2 and C2 results therefore describe tasks for which a valid transformation could be built, not
  all of SWE-bench Verified. The analysis compares accepted with rejected tasks on A outcomes (plan §8).

## 4. Variants and their validation
| Variant | How built | Acceptance |
|---|---|---|
| A | original | gold resolves, empty does not (swebench grader) |
| B1 | whitespace + neutral framing sentence | code blocks and identifier multiset identical |
| B2 | prose rewritten by a local model; code, identifiers, paths, numbers, quoted strings masked and restored byte-for-byte | every placeholder exactly once, nothing protected added, prose similarity ≤ 0.6, length 0.6–1.6× |
| C1 | gold patch pre-applied and committed | pre-patched + empty submission resolves |
| C2 | local-model draft of an update paragraph + edits to reference fix and tests; up to 3 drafting cycles (first drafts, a targeted-revision round with machine-measured feedback, fresh drafts plus a second revision round) | executable: unchanged repo fails; revised fix passes; original fix fails the revised tests; static: update does not mention tests, states every new test literal, edits only files the patches already change |
C2 criteria were never changed between cycles. A validator bug (revised tests were not applied by the grader) was found and fixed before any C2 verdict used here; every verdict
comes from the corrected oracle, which asserts that the replacement took effect.
**AI-assisted review** (Qwen3-Coder-30B-A3B, two passes in opposite order) found no C2 unfavourable on its main questions but is a weak screen (see readiness report).
**Human validation of B2 fidelity and C2 meaning is outstanding**; sheets are in `../human_review/`.

## 5. Attempt allocation (4,645)
| Condition | Models | Tasks | Repeats | Attempts |
|---|---|---|---|---|
| A, main | 4 primary | 99 | 5 | 1,980 |
| A, C2-extension | 4 primary | 12 | 5 | 240 |
| A, 7B control | 7B | 99 | 3 | 297 |
| B2 | 4 primary | 58 | 4 | 928 |
| C2 | 4 primary | 45 | 4 | 720 |
| B1 (weak control) | 4 primary | 20 | 3 | 240 |
| C1 (already fixed) | 4 primary | 20 | 3 | 240 |
| **Total** | | | | **4,645** |

Why these repeats. A keeps 5: H1, repeatability and BCM-null analyses use A pairs and power falls with fewer repeats (changed-line similarity, N=100: 0.79 at R=5, 0.72 at R=4 after
Bonferroni). B2 and C2 keep 4: the cluster is the task, so a 5th repeat adds little precision (the pooled B2 equivalence and C2 rate half-widths are set by the task count), while the repeat count
still gives 4 attempts per cell for C2 class rates. No targeted extra repeats are justified: the binding constraint is the number of accepted tasks, which repeats cannot buy.

## 6. Power and precision with the *accepted* task counts (pilot-informed simulation, `results/full_prep/power/`)
| Question | Design | Result |
|---|---|---|
| H1: attribution cosine vs changed-line similarity (pilot r ≈ 0.13), 97.5% CI lower bound > 0 | N=99, R=5 | power ≈ 0.79 |
| H1: vs FAIL_TO_PASS test agreement (pilot r ≈ 0.17) | N=99, R=5 | power ≈ 0.94 |
| H2: A vs B2 equivalence within ±0.05 (pooled, Bonferroni, true shift 0) | N=58 | changed-line sim ≈ 1.00, sequence sim ≈ 1.00, attribution cosine ≈ 0.91, test agreement ≈ 0.78 |
| same, true shift 0.025 | N=58 | ≈ 0.67 (changed-line), 0.94 (sequence), 0.36 (cosine), 0.32 (test agreement) |
| H2: solve-rate equivalence within ±0.05 | N=58 | 0.62 unadjusted, 0.26 Bonferroni, **not adequately powered** |
| H3: C2 class rates, 95% CI half-width | N=45, 16 attempts per task across models | ≈ ±0.05 pooled; ≈ ±0.06 (rate 0.15) to ±0.09 (rate 0.30) per model (interpolated between the simulated N=30 and N=60) |
| H4: AUC adapted vs persisted, 95% CI half-width | N=45, 720 attempts, adapted 30% | ±0.08 if persisted 15%, ±0.09 if 10%, **±0.14 if persisted 4%** (staging: 1 of 24 C2 attempts persisted) |
| BCM per model, task-cluster CI half-width | N=99 | ≈ ±0.01 (Devstral), ±0.03 (SWE-agent-LM), ±0.04 (Qwen3-30B-A3B) |
Original D0 would have had N=100 for B2/C2 (Bonferroni-adjusted equivalence power at N=100: test agreement 0.97, solve rate 0.72); that sample size cannot be reached because transformations are rejected, not because of the attempt budget.

## 7. Claims and their status
| Claim | Status under this design |
|---|---|
| BCM vs its label-permutation nulls on controlled repeats (RQ2) | **supported** (N=99, 5 repeats, nulls 50 seeds) |
| Attribution similarity vs task-grounded similarity beyond raw trace-feature similarity (H1) | **supported for test agreement; moderate power for changed-line similarity** |
| Invariance of behaviour and attributions under B2 (H2), similarity measures | **supported** (equivalence testable); weaker for test agreement and cosine under a small shift |
| Invariance of the *solve rate* under B2 | **estimation only** (no equivalence claim) |
| Adaptation rates under C2 (H3) | **supported as estimation**, for tasks with an accepted C2 only |
| Attributions cannot tell adaptation from persistence (H4) | **weak**: depends on the persistence rate; likely inconclusive if it stays near 4% |
| Scale effects including a ~70B model | **unsupported** (no 70B model) |
| B2/C2 fidelity and meaning as *human-validated* | **unsupported until the human sheets are completed** |
| Generalisation beyond SWE-bench Verified Python, mini-SWE-agent, T=0.7 | not claimed |

## 8. Execution
Lane launcher (≤ 3 Slurm jobs, `scripts/full/lanes.sh`), per-model jobs of ≤ 2 h on `gpu_partners`/`short_gpu`, resumable by result files, lock files, deadline guard, per-attempt 3600 s cap.
Node-local sandboxes. Checkpoint = result files; backup to `/rs1/researchers/b/bxu22/qle3/` after each model completes (`rsync` of `results/confirmatory_v1`).
Launch command (do not run before approval): see FULL_STUDY_READINESS_REPORT.md §5.
