# Exp03 design: controlled open-weight agents (draft v0.1, 2026-10-26; pre-pilot)

## Why this experiment
Exp01/01-V/02 show that BCM, as operationalised, is driven by representation, predictor pooling and task
structure. Archival data cannot answer two questions central to construct validity:
1. **Repeatability.** Does a system behave the same way on the *same* task across independent runs, and does
   BCM (or any attribution-based score) track that?
2. **Appropriate adaptation vs spurious change.** When a task changes in a way that *should not* matter
   (task-preserving variant), does behaviour stay the same? When it changes in a way that *should* matter
   (task-changing variant), does behaviour change in the right direction? Does BCM reward the first and
   penalise the second, or does it confuse them?

Ground truth is defined **without BCM**, from executable tests, patch targets and action sequences.

## Research questions and pre-specified hypotheses
- RQ3.1 (repeatability). For each model, within-task across-run similarity of (a) behavioural profiles
  (action-category sequences, edited files/functions, test-running behaviour) and (b) BCM attribution vectors.
  H1: attribution-vector repeatability correlates with behavioural repeatability across tasks
  (Spearman > 0.3). Falsified if ≤ 0.1 with CI excluding 0.3.
- RQ3.2 (invariance). For task-preserving variants (B), behaviour and outcome distributions should match the
  original (A) within run-to-run noise. H2: |Δ| between A and B is not larger than the A-vs-A' split-half
  difference (equivalence test, pre-set margin).
- RQ3.3 (adaptation). For task-changing variants (C), the correct decision changes and is verified by tests.
  H3: behavioural measures detect the change, i.e. A-vs-C differences exceed A-vs-B. H4 (critical for BCM):
  global BCM computed over {A, C} trajectories is *lower* for agents that adapt correctly than for agents that
  do not. That would show BCM penalising correct adaptation.
- RQ3.4 (BCM vs ground truth). Compare BCM and per-trajectory alignment with the independently established
  properties above, using partial correlations controlling for task difficulty (empirical solve rate),
  repository and model capability.

## Dataset (justification)
**Primary: SWE-bench Verified** (500 human-validated Python tasks, public per-instance images
`swebench/sweb.eval.x86_64.*`, official harness).
- Open-weight 7–32B coding models solve a non-trivial fraction. This gives outcome variance within model,
  which BCM needs (success predictor). On SWE-bench Pro, small open models are expected to be near 0%.
- Python-only allows AST-checked semantics-preserving transformations.
- Human-validated FAIL_TO_PASS/PASS_TO_PASS oracles.
**Secondary (continuity with Exp02): a SWE-bench Pro Python subset** (qutebrowser/openlibrary/ansible), only if
pilot solve rates are > 5%.
Task sampling: stratified over repositories and the Verified difficulty buckets. Tasks that no pilot model
solves in any run, or that every model always solves, are not dropped; they are kept and reported, because
difficulty is a covariate.

## Scaffold and instrumentation (identical for all models)
mini-swe-agent (bash-only agent, the reference minimal SWE scaffold), Singularity/Apptainer environment running the
task's official image, local vLLM OpenAI-compatible server. Logged per step: raw model output, parsed command,
observation (truncated identically), return code, wall time and tokens. Native role-aware schema from the start,
so no parser ambiguity. Step limit 50 (pilot; revisit), temperature fixed per model at its recommended sampling
value (T = 0.7 default), top_p = 0.8, distinct sampling seed per run. Repeats are independent runs with fresh containers.

## Task variants (each validated by execution before use)
- **A original.**
- **B task-preserving.**
  - B1 *statement rewrite*: deterministic restructuring of the issue (section reordering, formatting changes,
    renaming of user-example local variables that are absent from the gold patch and tests). Validation: an
    automated check that every identifier appearing in the gold patch/tests that is mentioned in A is still
    mentioned in B1, plus human review of all B1 texts.
  - B2 *repository noise*: semantics-preserving edits away from the fix site (e.g. formatting-only changes in
    unrelated modules). Validation: full test-suite results identical before/after, and the gold patch still
    applies and passes.
- **C task-changing.**
  - C1 *already fixed*: the gold source patch is pre-applied and the issue text is unchanged. The correct
    decision is to verify and make no functional change. Validation: FAIL_TO_PASS pass at start. Ground truth:
    tests still pass and no regression after the agent's patch.
  - C2 *changed requirement*: for tasks whose gold patch introduces a literal that tests assert (error type,
    message, return value), the issue text and the hidden tests are changed consistently to a different
    literal. Validation: the mutated gold patch passes mutated tests **and** the original gold patch fails
    them. The decision demonstrably changed.
Only variants passing validation enter the study, and the validation logs are stored.

## Models (final choice after the throughput benchmark; target scales ≈7B / 14B / 32B / 70B)
Candidates: Qwen2.5-Coder-7B/14B/32B-Instruct (same family across scale), Qwen3-Coder-30B-A3B (agentic MoE),
Devstral-Small (24B, agentic), SWE-agent-LM-32B (trained on SWE-smith trajectories, linking to the Exp01 data),
Llama-3.3-70B-Instruct (70B, different family). Selection criteria: pilot solve rate > 0 on ≥ 3 tasks,
tool-format compliance > 90% of steps, throughput.

## Pilot (gates before scaling)
2–3 models × 12 tasks (≥ 6 repositories) × variants {A, B1, C1} × 5 repeats ≈ 360–540 runs.
Gates: (G1) every image runs under Apptainer and gold/empty patches give the expected oracle results on all
pilot tasks; (G2) variant validation passes; (G3) ≥ 95% of runs complete with valid logs; (G4) the analysis
pipeline runs end to end on pilot data (BCM, nulls, repeatability, invariance/adaptation contrasts);
(G5) measured GPU-hours per run to size the full study.

## Full study (sized after the pilot)
Power target: detect a Spearman 0.3 (H1) with 80% power, giving ≥ 85 tasks per model. Equivalence (H2) and
adaptation (H3) contrasts are analysed with task-clustered mixed models. Provisional sizing: 4–6 models × 100 tasks
× {A, B1, B2, C1, C2 where valid} × 5 repeats ≈ 8–15k runs, contingent on G5.

## Analysis plan (summary)
Same BCM pipeline as Exp02 (role-aware native schema, released LGBM + alternatives, task-grouped CV,
nulls), computed **per model** and **pooled**, with companion sensitivity. Ground-truth measures:
run-to-run Jaccard of edited files and functions, normalised edit distance of action-category sequences,
outcome agreement, and invariance/adaptation contrasts. Statistics: task-clustered bootstrap, mixed-effects
models (task, repository random effects), pre-registered equivalence margins. No LLM judges. Any semantic
labels from a local model are used only after validation against human labels on a sample.
