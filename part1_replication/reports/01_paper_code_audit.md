# 01 — Paper / README / code audit

Sources audited:
- Paper: arXiv:2608.13598 v1 (31 Jul 2026) and v2 (14 Sep 2026), `docs/paper/`. v1→v2 differences are
  editorial only (Hugging Face repository IDs spelled out in §3.2; acknowledgements added); a
  line-level diff shows no number, table, or method statement changes.
- Code: `external/colm-agent-eval` (= fork `external/tbf-eval`; identical tree), HEAD
  `61f98943803e4fd6820ec7df6eaa9fdb41c07b11` (2026-06-22, one day before the README's stated
  June 23 submission deadline). 102 commits, no tags, **no LICENSE file**.
- README: `external/colm-agent-eval/README.md` at the same SHA.

Path prefix below: `C/` = `external/colm-agent-eval/`. Line numbers refer to SHA 61f98943.
Status vocabulary: **MATCH**, **DIFF** (stated definitions differ), **GAP** (no code/text),
**BUG** (code cannot do what is stated), **ARTIFACT-MISMATCH** (shipped outputs cannot come
from shipped code).

## A. The twelve features

| # | Item | Paper (Table 1 / §3.3) | README (Stage 3 table) | Implementation | Difference / ambiguity | Audit resolution |
|---|---|---|---|---|---|---|
| 1 | total_steps | Number of messages (steps) | Total number of messages | `len(messages)` of the parsed sequence, `C/data/extract_features.py:16-17` | What counts as a "message" is decided by the loader, and differs by source (rows P1–P2). | MATCH in definition; the meaning is source-dependent (see P1/P2). Implemented as code. |
| 2 | mean_action_length | Mean character length of a message | Mean character length of actions | `np.mean(len(str(m)))`, `:33-34` | Same parse dependency. | MATCH. |
| 3 | max_action_length | Max character length of a single message | Max character length of any action | `np.max`, `:35` | — | MATCH. |
| 4 | file_search_count | **Fraction** of steps matching file-search patterns | "Regex-matched file search actions" (count implied by name) | `searches / total_messages`, regexes `:37-42`, precedence `:68-79` | Name says *count*, value is a fraction. Paper does not give the regexes or precedence. | Code rules adopted (fraction; edit>test>view>search precedence). |
| 5 | file_view_count | Fraction, view patterns | Regex-matched view/read | `views / total`, `:43-46` | Same. Pattern includes `widgets\.py`, an apparent leftover from one task. | Code adopted, documented. |
| 6 | file_edit_count | Fraction, edit patterns | Regex-matched edit/write | `edits / total`, `:47-50` | Same; `<<<<<<<` merge marker as edit signal. | Code adopted. |
| 7 | test_execution_count | Fraction, test patterns | Regex-matched test runs | `tests / total`, `:51-54` | Same. | Code adopted. |
| 8 | action_entropy | Shannon entropy over the distribution of **distinct messages** | Shannon entropy over **action categories** | `np.unique(message_strings)`, `-Σ p log2(p+1e-9)`, `:88-91` | **README DIFF**: categories vs distinct messages. Paper omits the log base; code uses log2 and a +1e-9 inside the log. | Paper/code definition used (distinct messages, log2, +1e-9). README version NOT implemented. |
| 9 | consecutive_repetition_max | Longest run of identical consecutive messages | Max run of consecutive identical **action types** | Run length over exact message strings, init 1, `:94-103`; empty sequence → 0, `:27` | **README DIFF** (types vs messages). Empty-sequence value 0 is code-only. On real data this feature is 1 for almost all non-empty rows (SHAP importance 0.0 in the authors' run, `C/results/unified_shap_predictor_output.txt`). | Paper/code used. |
| 10 | unique_action_ratio | Distinct messages / total messages | Unique actions / total actions | `len(counts)/total`, `:92` | — | MATCH. |
| 11 | error_flag_count | **Fraction** of steps matching error patterns | **Count** of error-pattern matches | `errors / total_messages`, regexes `:105-111` | **README DIFF** (count vs fraction). Last pattern `issue with the X class` is idiosyncratic. Matches are on *message* text; with the author parse, Nebius messages include observations (where tracebacks appear) but SWE-smith messages do not (row P1). | Paper/code (fraction) used. Representation asymmetry quantified in F. |
| 12 | step_velocity | Fraction of steps where the action **category changes** | "Steps per unit of sequence length" | transitions between consecutive categories / total_messages, `:113-117`; "other" is a category | **README DIFF** (completely different quantity). Paper says "transitions between consecutive categories"; code divides by n, not n−1. | Paper/code used (divide by n, "other" counts). |

## B. Data, model, metric, uncertainty, tables

| # | Item | Paper | README | Implementation | Difference / ambiguity | Audit resolution |
|---|---|---|---|---|---|---|
| P1 | SWE-smith parsing | "parsing its ordered action sequence" (§3.3) | "Downloads and merges" | Keeps `content` of messages with `message_type == "action"`, `C/data/load_swebench.py:25-34` | In the pinned `tool` split, records come in **two schemas**: plain `role/content` messages (no `message_type`, tool calls embedded as `<function=…>` text) and structured SWE-agent records. Plain records parse to **zero steps**. For structured records `content` is the assistant's *thought text*; the executed command (`action`/`tool_calls`) is ignored. | **BUG** (silent empty parse). Archival path kept bug-for-bug; corrected `role_aware` parser added and labelled (Report 03/04 F). Quantified in Report 02. |
| P2 | Nebius parsing | same | same | Keeps **every** message's `text`, or `system_prompt` when text is None, `:73-85` | Includes system prompt (≈ 5k chars), the issue text and every observation as "steps". So for Llama systems a "step" is any message, while for proprietary systems it is assistant thought text. | **DIFF** between sources: representation is perfectly confounded with proprietary-vs-Llama. Kept in archival path; role-aware alternative in F. |
| P3 | Filtering | "remove trajectories with incomplete logs, missing metadata, or absent termination indicators" (§3.2) | — | **No filter of any kind** in `load_swebench.py`; every sampled row is kept, including empty parses and non-submitted runs | Paper describes filters that the code does not implement. | **GAP**. Archival path replicates the code (no filters). Exclusion counts reported in Report 02 *without* dropping rows. |
| P4 | "Raw corpus ≈24,000" | §3.2 | — | SWE-smith `tool` has 24,100 rows; Nebius `train` has 80,036 | 24k matches SWE-smith alone; the combined corpus is ≈104k. | DIFF (descriptive). |
| P5 | SWE-smith sampling | not stated | up to 4,000, seed 42 | `df_smith.sample(n=4000, random_state=42)` over all models, `:100-101` | System counts (946/2,938/116) arise from random sampling of a 24,100-row pool, not from a design. | Replicated exactly. |
| P6 | Nebius selection | "restrict the data to six agent systems" | "up to 4 model systems with ≥500 trajectories" | groupby `model_name`, keep counts ≥ 500, take first 4 in sorted order, sample ≤2,000 each, `:53-64` | Only 3 systems qualify, so `[:4]` takes 3. | Replicated exactly. |
| P7 | Label | resolved status (§3.4) | — | SWE-smith `resolved in [True,"True",1]`; Nebius `target in [True,"True","True\n",1]`, `:19-20, :51` | None found. | MATCH. |
| P8 | Final shuffle | — | merged and shuffled | `concat` then `.sample(frac=1, random_state=42)`, `:106-107` | Row order determines the seed-42 folds. | Replicated; row order kept as `author_row`. |
| M1 | Predictor | LightGBM, 5-fold stratified CV (§3.4) | LightGBM 5-fold | `StratifiedKFold(5, shuffle=True, random_state=42)`; `LGBMClassifier(n_estimators=200, learning_rate=0.05, max_depth=6, num_leaves=31, random_state=42, n_jobs=-1)`, `C/model/behavioral_predictor_pipeline.py:30-44` | Hyperparameters not in paper. | Code adopted. |
| M2 | AUC | "mean cross-validated AUC-ROC of 0.690" | "Mean ROC-AUC (5-Fold): 0.6900" | `roc_auc_score(y, oof_proba)` — **pooled** OOF AUC, printed as "Mean ROC-AUC (5-Fold)", `:69-71` | Label says mean of folds; value is pooled. | We report both. |
| M3 | Threshold | — | "Optimized Threshold 0.370" | Hard-coded 0.370, `:65` | Not optimized in code. | Not used by BCM; noted. |
| M4 | Feature importances | — | README prints "TOP FEATURE IMPORTANCES" | Not printed by the shipped script | **ARTIFACT-MISMATCH**: `C/results/unified_shap_predictor_output.txt` contains output the shipped script cannot produce. | Noted. |
| S1 | Attribution | TreeSHAP, OOF, log-odds (§3.1, §3.5) | OOF SHAP | `shap.TreeExplainer(clf).shap_values(X_val)`; if a 2-element list, take `[1]`, `:51-58` | Tree-path-dependent (no background). shap ≥0.45 returns an (n,d) log-odds array for binary LightGBM, so the list branch is unused. Additivity is never checked. | Our pipeline asserts additivity against `predict(raw_score=True)` per fold (max error logged). |
| S2 | Saved fingerprints | — | `shap_fingerprints.csv` | Saves 12 SHAP columns + `resolved` only, `:86-88` | `metrics/bcm.py:34` groups by `agent_system`, which the script never writes, so `bcm.py` cannot run on the script's own output. The **shipped** `shap_fingerprints.csv` *does* contain `agent_system`. | **ARTIFACT-MISMATCH / BUG**. Confirmed by running the scripts unchanged (Report 03). |
| B1 | Zero-norm filter | exclude ‖φ‖ ≤ 1e-9 (Eq. 3) | — | `metrics/bcm.py`: none; `data/confound.py:15` and `experiments/exp3_drift.py:17-18`: yes | Inconsistent across scripts; inactive on the data (0 rows). | Implemented per paper. |
| B2 | n < 2 | undefined (Eq. 5) | — | `metrics/bcm.py:7-8, 11-12` and `metrics/clustering.py:12-13` return **1.0**; `confound.py:16` returns NaN | `bcm.py` reports perfect consistency for 1 vector. | Paper rule (undefined) implemented. |
| B3 | Global BCM grouping | per agent system, successes and failures together (§3.6) | "per-agent, per-outcome BCM" | `metrics/bcm.py:34` groups by **(agent_system, resolved)** | **DIFF**: `bcm.py` estimates a different quantity. Table 2 numbers come from `data/confound.py:20-27` (system only), whose output `C/results/confound_output.txt` is identical to Table 2 to 3 dp. | Paper estimand (system only) used; per-outcome values reported as the README quantity. |
| B4 | Within-task BCM | tasks with ≥3 trajectories, macro-average (Eq. 6) | — | `data/confound.py:20-27` (`instance_id` value_counts ≥ 3) | Paper: "SWE-bench instance". SWE-smith instance IDs are synthetic SWE-smith task IDs, not SWE-bench. | MATCH in code; task key `source:instance_id`. |
| U1 | Global CI | trajectory bootstrap, 1,000 iterations, 2.5/97.5 percentiles (§3.6) | Exp 1 "bootstraps BCM 1,000 times" | **Removed** from shipped `exp1_inconsistency.py` in commit `a35af8c` ("remove bootstrap logic"); recovered from `a35af8c^:experiments/exp1_inconsistency.py:9-62`. Uses `np.random.seed(42)`, no zero filter, RNG first consumed by a fake `subset_id`. | Shipped code cannot produce the README/paper CIs. | Recovered algorithm re-run on shipped artifacts reproduces all six shipped CIs exactly (Report 03). |
| U2 | Within-task CI | resample eligible tasks, 1,000 iterations (§3.6) | — | **No code anywhere in the 102-commit history.** | Table 3 CIs cannot be traced to code. | Implemented from paper text, labelled APPROXIMATE. |
| U3 | Exp 1 "success variance" | — | "Success Variance vs. BCM r=0.5907" | `subset_id` is **random fake repo labels** `np.random.choice(["repo_A",…,"repo_D"])`, `C/experiments/exp1_inconsistency.py:15-17` | Statistic is noise by construction. | Not used; flagged. |
| T1 | Table 2 | global BCM + CI + success | Exp 1 output | Numbers match `confound_output.txt` (point) and recovered bootstrap (CI). Paper GPT-4o point 0.814 = point estimate; README "0.8162" = bootstrap mean. | README mixes point and bootstrap mean. | Reproduced exactly from shipped artifacts (Report 03). |
| T2 | Table 3 | within-task BCM + CI + #tasks | — | Point and #tasks from `confound.py`; CI no code | See U2. | Points reproduced exactly from shipped artifacts. |
| T3 | Table 4 | difficulty terciles | Exp 3 | `experiments/exp3_drift.py`; bins from task resolution rate over the *merged* dataset; hard = rate ≤ q33 = 0 | Paper: "hard = unsolved under every observed execution" — matches code. | Re-run unchanged (Report 03). |
| T4 | Figures 2 and 4 | bar charts | — | `figures/global_vs_within.py:14-15`, `figures/difficulty_stratified.py:14-16` **hard-code** the numbers | Figures are not generated from data. | Noted. |
| X1 | Raw-feature baseline | z-scored raw features, BCM 0.28–0.54 (§5.1) | — | **No code** in the repository or its history | Reference population for z-scoring unspecified. | Implemented with cohort-wide z-scores plus sensitivity (Report 03/04). |
| X2 | Earlier "BCM" | — | — | `ce46d7b^:data/confound.py:23-27` defined BCM as `1 − std(action_entropy)`; `global_bcm_ref` hard-coded Table 2 values | Historical; replaced on 2026-06-22. | Noted for provenance. |
| X3 | Clustering | silhouette favours k=2 (0.58), k=3 (0.49) (§5.4) | k=2..8, final k=3 | `metrics/clustering.py` prints inertia only, no silhouette | Silhouette values have no code. | Out of scope; noted. |

## C. Verified facts vs. claims needing our runs

Items marked BUG/DIFF above are verified by reading code. Their quantitative consequences
(empty-parse share, BCM with and without empty rows, representation effects) are reported
in Reports 02–04 with the exact tables cited there.
