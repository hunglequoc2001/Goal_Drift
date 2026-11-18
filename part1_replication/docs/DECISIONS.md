# Decision and change log (BCM-01)

Entries are written before the corresponding results are inspected unless marked
"post hoc". Every consequential deviation from the brief or the paper is listed here.

## 2026-10-23 — written before any model was trained in this workspace

D1. **Sources pinned.** SWE-smith `tool` @ `08e109b4a59eaeebf80e4675cd125d42e7ac99a4`
(last commit 2025-07-19); Nebius `train` @ `68195a1450865274106246d0d0296a1d6807b88e`
(last commit 2024-12-23). Both pre-date the author repo (June 2026), so these are the
only revisions the authors could have loaded from `main`.

D2. **Already known before experiments (from the author's shipped artifacts, not our
runs).** The shipped matrix has 2,513/4,000 SWE-smith rows with an empty author parse.
This is why both representations below are carried through every experiment.

D3. **Two frozen matrices on one manifest.** The manifest is the author-replicated
9,191-row cohort (if our replication of the selection reproduces it). On it we freeze:
- `author` — features from the bug-for-bug author parser. **Primary** for A–E, because
  the research question is the stability of the *published* measurement.
- `role_aware` — features from the role-aware parser (src/bcm_validity/parsers.py).
  Every A–D/G analysis is repeated on it and labelled NEW EXPERIMENT /
  representation sensitivity. It is never pooled with `author` results.
Each matrix has its own SHA-256 over (X float64, y int64); every variant asserts its hash.

D4. **Paper-faithful feature rules where the paper is silent** follow the author code
(log2 entropy with +1e-9, edit>test>view>search precedence, zero features for empty
sequences). Validated by exact equality against the author's `extract_features` on all rows.

D5. **Role-aware error flags** are computed on the observation that follows each action
(error text lives in observations, which the role-aware step text excludes). All other
role-aware features use the same author regexes on the canonical command string, so the
change isolates *what counts as a step*, not the category dictionary.

D6. **Task key.** `source:instance_id`. SWE-smith instance IDs (synthetic
`owner__repo.commit.mutation`) and Nebius IDs (`owner__repo-PR`) live in different
namespaces; repository overlap is audited separately (`repo_key`) and reported, but tasks
are not merged across sources because no shared real-world issue ID exists.

D7. **Main pre-specified contrasts** (descriptive CIs, no significance tests over the sweep):
- M1 separation `S = min(BCM_proprietary) − max(BCM_llama)` per run.
- M2 per-system absolute change |BCM_variant − BCM_seed42-baseline|.
- M3 rank agreement with the seed-42 baseline ordering (Kendall tau-b, Spearman rho,
  fraction of the 15 system pairs reversed).
GPT-4o (n=116) is reported but flagged in every table.

D8. **Bootstrap.** 2,000 paired task-cluster replicates within each system (clusters =
task key), seed 20261023; the same replicate weights are applied to every stored SHAP
matrix so variant differences are paired. Duplicated rows in a replicate contribute pairs
of distinct copies (cos=1), matching the standard pair-bootstrap; documented as a known
upward bias. Secondary: nested repository→task bootstrap for the baseline only.

D9. **Archival intervals.** Table 2 CIs are recomputed with the author's own recovered
trajectory bootstrap (git `a35af8c^:experiments/exp1_inconsistency.py`, np.random.seed(42),
agent order of `clustered_fingerprints.csv`, RNG first consumed by the fake `subset_id`).
No code exists for Table 3 CIs; we implement the paper text (resample eligible tasks,
1,000 iterations, seed 42) and label it APPROXIMATE.

D10. **Raw-feature baseline reference population.** z-scores use the mean/SD (ddof=0) of
the full 9,191-row cohort (paper §5.1 does not specify). Sensitivity: per-system
z-scoring and unscaled raw cosine.

D11. **Predictor variants with AUC within ±0.03 of baseline** form the "competent"
subset (threshold from the brief, not tuned).

D12. **G backgrounds.** For background seed s and fold k, 128 rows are drawn without
replacement from that fold's training indices with `np.random.default_rng([s, k])`.

D13. **Compute.** All model fitting runs in Slurm jobs (login node is not used for
training). LightGBM `n_jobs=4`; author archival run uses its own `n_jobs=-1`.

D14. **umap-learn not installed.** `models/umap_projection.py` (descriptive Figure 3)
is recorded as not run; no BCM quantity depends on it.

## 2026-10-23 — added during execution

D15 (post hoc, before G results were inspected). shap 0.51 interventional TreeSHAP on the
role-aware fold-0 model is not exactly additive: 2/1,839 rows miss the LightGBM raw margin by up to
0.112, and `expected_value` differs from the mean background margin by 0.018, although shap's own
tree model reproduces LightGBM predictions exactly. The cause is inside shap's interventional routine
(tree-path-dependent attributions use LightGBM `pred_contrib` and are additive to 1e-14). An exact
replacement would need ~10^9 model evaluations. Resolution: G records per-row additivity error,
the expected-value gap, and the count of rows with error > 1e-6; BCM is reported on all rows and on
additive rows only. No row is dropped from the primary G numbers.

D16 (post hoc). The shipped author artifacts (AUC 0.690) are NOT reproduced by the shipped
script in this environment (AUC 0.7283; our independent E0 0.7285 on an identical X/y and identical
folds). Paper-target comparisons are therefore reported against both the shipped artifacts and the
fresh run. A historical-LightGBM probe (`scripts/lgbm_version_probe.py`) tests whether a library
version explains the gap; it does not alter any primary analysis.

D17 (post hoc, diagnostic). The author pipeline passes features through CSV
(`engineered_features_matrix.csv`), which merges 2 of 2,814 distinct `action_entropy` values
(differences ~1e-13). LightGBM bins change and per-row OOF probabilities move by up to 0.157
(thread count has no effect: n_jobs 1 vs 4 identical). This is the whole difference between the
author's unchanged run (`runs/author_archival`, AUC 0.7283) and our E0 (float64 parquet, AUC 0.7285).
Our frozen matrix keeps full float64 precision; the archival run is reported alongside it.
LightGBM 3.3.5, 4.0.0, 4.1.0, 4.3.0, 4.5.0, 4.6.0 and 4.7.0 give identical results on the shipped
CSV matrix (AUC 0.7284), so a LightGBM version does not explain the shipped AUC 0.690.
