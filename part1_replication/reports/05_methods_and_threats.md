# 05 — Methods, controls, and threats to validity

## Pipeline (all code in `src/bcm_validity/`, one CLI per stage, `Makefile` targets)

| Stage | Module | Output |
|---|---|---|
| Download (xfer partition) | `scripts/download_data.py` | `data/raw/`, `data/manifests/source_files.json` |
| Ingest, selection replay, parsing, features | `ingest.py`, `parsers.py`, `features.py` | `data/manifests/cohort_author_selection.csv`, `results/tables/features_{author,role_aware}.parquet` |
| Author scripts unchanged | `author_archival.py` | `runs/author_archival/`, `logs/author_archival/` |
| E0, A, B, C, D, G | `experiments.py`, `model.py`, `bcm.py` | `results/arrays/<stage>/<rep>/*.npz`, `results/tables/runs_<stage>_<rep>.csv` |
| E, bootstrap, summaries, archival checks | `analysis.py` | `results/tables/*` |
| Provenance | `provenance.py` | `results/tables/prov_*` |
| F manual validation | `validation.py` | `results/validation/` |
| Figures | `figures.py` | `results/figures/` (PDF, SVG, PNG) |

Every model run is checkpointed as one `.npz` holding OOF SHAP, probabilities, raw margins,
fold IDs, the fitted labels, parameters, per-fold base values and additivity errors, and the
frozen-data hash. A run is reused only if its stored hash equals the current matrix hash;
otherwise the stage aborts.

## Parser definitions

- **author** (`parsers.author_*`): bug-for-bug copies of `load_swebench.py:25-34` (SWE-smith) and
  `:73-85` (Nebius).
- **role_aware** (`parsers.role_aware_*`): one step per executed tool call. SWE-smith structured:
  `message_type=="action"` messages with a non-empty tool call, text = canonical command from
  `tool_calls`. SWE-smith plain: each `<function=…>` block, text = canonical command from its
  `<parameter>` tags (the same canonical form as the structured `action` field). Nebius: each
  `ai` message's last fenced block. System prompts, task statements, observations and harness
  exit messages are excluded. Error flags use the observation that follows each step.
  Category regexes are unchanged from the author code, so this variant changes *what a step is*,
  not the category dictionary (whose recall on commands is poor; see F).

## Model and attribution

`StratifiedKFold(5, shuffle=True, random_state=seed)`; `LGBMClassifier(n_estimators=200,
learning_rate=0.05, max_depth=6, num_leaves=31, random_state=42, n_jobs=4, verbose=-1)`.
TreeSHAP via `shap.TreeExplainer(model)` (tree-path-dependent). In shap 0.51 the binary
LightGBM output is a single (n, 12) log-odds array with a scalar `expected_value`.
Additivity `Σφ + φ0 = predict(raw_score=True)` is asserted for every fold (tolerance 1e-6) and
the maximum error stored. `predict_proba = sigmoid(margin)` is asserted (1e-9).

## Metric

`BCM = (‖Σ u_i‖² − n) / (n(n−1))`, `u_i = φ_i/‖φ_i‖`, rows with `‖φ_i‖ ≤ 1e-9` excluded, NaN
(undefined) for n < 2. Unit tests (`tests/test_bcm.py`): identical vectors → 1, orthogonal → 0,
`[e1,e1,−e1,−e1]` → −1/3 (a mathematical construct, not agent data), single/zero vectors →
undefined without NaN leakage, identity vs brute force ≤ 1e-10 on random and duplicated vectors,
weighted (bootstrap) form vs explicit expansion ≤ 1e-10, between- and within-task forms vs brute force.

## Uncertainty

- Archival: the authors' own trajectory bootstrap, recovered from git and re-run exactly.
- Primary: 2,000 task-cluster bootstrap replicates per system (clusters = `source:instance_id`),
  seed 20261023. The same replicate weights are applied to every stored run, so differences
  between a variant and the baseline are paired. Duplicated rows in a replicate add distinct-copy
  pairs (cos = 1), a known upward bias shared by all variants.
- Secondary: nested repository → task bootstrap for the baseline.
- No significance tests are run over the sensitivity sweep; contrasts M1–M3 (DECISIONS.md D7)
  are summarised descriptively with intervals.

## Threats to validity

1. **Source = scaffold = model family = parser.** All proprietary systems come from SWE-smith
   (SWE-agent with function calling, synthetic SWE-smith tasks); all Llama systems come from
   Nebius (SWE-agent with fenced-command format, real GitHub issues). The author parser also
   differs by source. No analysis here can attribute a proprietary-vs-Llama difference to the model.
2. **Task populations differ.** The two sources share no task. Repetition per task ranges from
   ≈1.2 runs/task (Claude-3.7) to ≈12 (Llama-405B).
3. **Joint predictor.** The success model is fitted on all systems together. Through features
   that differ by source (step counts, lengths), it can encode system identity. Stage C
   (label permutation) probes how much attribution geometry remains without outcome signal.
4. **SHAP explanation choices.** Tree-path-dependent vs interventional TreeSHAP (stage G).
   Cosine on log-odds attributions ignores magnitude, so rows whose attributions are small but
   identically signed count as fully consistent.
5. **Manual validation was done by the AI agent running this study**, not by a human annotator,
   on 60 records / 120 sampled steps. It should be repeated by a human before publication.
6. **Library versions.** The authors' package versions are unknown (README: "Python 3.10,
   Colab"). LightGBM/SHAP version drift could perturb SHAP values. The archival run compares
   against shipped artifacts to measure this (Report 03).
7. **Within-task CIs** (paper Table 3) have no author code; our version follows the paper text.
