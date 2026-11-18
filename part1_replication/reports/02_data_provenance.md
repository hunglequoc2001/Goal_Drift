# 02 — Data provenance, schema, and cohort reconstruction

**Status: EXACT REPRODUCTION of the author cohort.** All 9,191 rows match the author's shipped
feature matrix (`external/colm-agent-eval/results/files/anomaly_analysis_summary.csv`) in row
order, `instance_id`, `agent_system`, label and all 12 features (max abs diff 1e-12, CSV rounding).
Manifest: `data/manifests/cohort_author_selection.csv` (column `author_row` = author row order).

## 1. Pinned sources

| Source | HF repo | Revision (pinned) | Last commit | Split used | Rows | Files |
|---|---|---|---|---|---|---|
| A | `SWE-bench/SWE-smith-trajectories` | `08e109b4a59eaeebf80e4675cd125d42e7ac99a4` | 2025-07-19 | `tool` | 24,100 | 8 parquet shards |
| B | `nebius/SWE-agent-trajectories` | `68195a1450865274106246d0d0296a1d6807b88e` | 2024-12-23 | `train` | 80,036 | 12 parquet shards |

Both revisions are older than every author commit (June 2026), so they are the revisions the
authors' `load_dataset(...)` calls resolved to. SHA-256 and byte size of every shard:
`data/manifests/source_files.json`. Downloads ran on the `xfer` partition
(`scripts/slurm/download.sbatch`); raw data lives in `data/raw/` (not in git).

## 2. Real schemas (sampled rows; full-source counts in `results/tables/prov_source_by_system.csv`)

**SWE-smith `tool`** fields: `messages` (JSON string), `instance_id`, `resolved` (bool), `model`,
`traj_id`, `patch`. The `messages` lists come in **two schemas inside the same split**:

| Format | Message keys | Where the executed command lives | Full source | Cohort |
|---|---|---|---|---|
| plain | `role`, `content` | `<function=NAME><parameter=K>V</parameter></function>` inside assistant `content`; observations are `user` messages starting `OBSERVATION:` | 14,984 / 24,100 | 2,513 / 4,000 |
| structured | `role`, `content`, `message_type`, `agent`, plus `thought`, `action`, `tool_calls` (actions) or `tool_call_ids` (observations) | `action` / `tool_calls`; `content` = `thought` (natural language) | 9,116 / 24,100 | 1,487 / 4,000 |

Plain records have no `message_type` key, so the author filter `message_type == "action"`
(`load_swebench.py:29`) returns nothing for them. **Every plain record parses to zero steps;
every structured record parses to ≥1 step.** The empty-parse set is exactly the plain set (2,513 rows).
SWE-smith instance IDs are synthetic SWE-smith tasks (`owner__repo.commit.mutation_id`), not
SWE-bench instances as the paper states.

**Nebius `train`** fields: `instance_id`, `model_name`, `target` (bool), `trajectory` (list of structs
`role ∈ {system,user,ai}`, `text`, `system_prompt`, `mask`, `cutoff_date`), `exit_status`,
`generated_patch`, `eval_logs`. The SWE-agent command is the last fenced code block in each `ai`
message (every `ai` message in the cohort has one, except 1 Llama-8B record).

## 3. Selection replay (code: `src/bcm_validity/ingest.py`, replicating `load_swebench.py`)

| System | Source pool | Selected | Paper | Δ | Success rate | Plain format (empty author parse) | Tasks | Tasks with ≥3 runs (paper) | Max runs/task | Repos |
|---|---|---|---|---|---|---|---|---|---|---|
| Claude-3.5 | 5,751 | 946 | 946 | 0 | 0.428 | 507 (53.6%) | 676 | 60 (60) | 6 | 68 |
| Claude-3.7 | 17,715 | 2,938 | 2,938 | 0 | 0.384 | 1,990 (67.7%) | 2,483 | 60 (60) | 4 | 127 |
| GPT-4o | 634 | 116 | 116 | 0 | 0.250 | 16 (13.8%) | 93 | 4 (4) | 3 | 10 |
| Llama-405B | 1,191 | 1,191 (all) | 1,191 | 0 | 0.259 | 0 | 100 | 100 (100) | 15 | 49 |
| Llama-70B | 74,792 | 2,000 | 2,000 | 0 | 0.167 | 0 | 1,384 | 132 (132) | 6 | 681 |
| Llama-8B | 4,053 | 2,000 | 2,000 | 0 | 0.154 | 0 | 515 | 261 (261) | 26 | 370 |

The Nebius rule "≥500 rows, first 4 in sorted order" selects exactly the three Llama systems.
SWE-smith system counts are whatever `sample(n=4000, random_state=42)` drew from a 24,100-row pool.
Llama-405B is the entire population of that system (100 tasks × ≈12 runs each); Claude-3.7 is
almost one run per task (2,483 tasks for 2,938 runs). **Task repetition structure therefore differs
by an order of magnitude between systems**, which matters for every global-BCM comparison (Report 04 E).

## 4. Integrity audit (no rows dropped anywhere)

| Check | Result |
|---|---|
| Missing labels | 0 in both sources |
| Duplicate `traj_id` (SWE-smith, full source) | 0 |
| Identical raw-trajectory hashes (within or across sources, full sources) | 0 |
| Duplicate `source_row_id` or hash in cohort | 0 |
| Cross-source shared `instance_id` | 0 (disjoint namespaces) |
| Cross-source shared repositories | 31 repos appear in both sources (`prov_summary.json`) |
| Instances shared by ≥2 systems | 413 (all within one source: e.g. Llama-70B/8B 162, Claude-3.5/3.7 99, all three Llama 33) |
| Nebius non-`submitted*` exit status in cohort | 405B 27, 70B 170, 8B 84 (early_exit / exit_context / exit_cost / exit_format) |
| SWE-smith trajectories whose last role-aware action is not `submit` | Claude-3.5 50, Claude-3.7 74, GPT-4o 24 (the 4 such records in the manual sample end with a harness message "Exit due to cost limit" / "…total execution time exceeded") |
| Author-parse empty | 2,513 (all SWE-smith, = plain format) |
| Role-aware parse empty / error | 1 (Llama-8B; no fenced command in any `ai` turn) / 0 |

The paper says trajectories with "incomplete logs, missing metadata, or absent termination
indicators" were removed (§3.2). The code removes nothing, and the shipped matrix contains the
non-terminal records listed above. We keep them in every analysis (exact replication) and report
counts here rather than create an undocumented subset.

Empty-parse rows are **not** outcome-neutral: author-parse-empty success rate vs non-empty is
Claude-3.5 0.481 vs 0.367, Claude-3.7 0.370 vs 0.411, GPT-4o 0.000 (0/16) vs 0.290.

## 5. What the author parser calls a "step"

Median steps per trajectory (author parse → role-aware parse): Claude-3.5 0 → 14.5,
Claude-3.7 0 → 30, GPT-4o 3.5 → 19, Llama-405B 55 → 27, Llama-70B 35 → 17, Llama-8B 53 → 26.

For Nebius, the author "steps" are *all* messages. In the 30 manually reviewed Nebius records
(`results/validation/F_author_parse_composition.csv`): 30 system prompts (median 4,873 chars;
regex category edit 100%), 30 issue texts (edit 100%, error 33%), 860 environment observations
(regex category view 66% / edit 34%, error 29%) and 890 agent turns. For SWE-smith structured
records the author steps are the assistant's natural-language thought text (median 130 chars).
**The two sources are therefore measured with different instruments, and the instrument boundary
coincides exactly with proprietary-vs-Llama.**

## 6. Reproducibility metadata

- Python 3.11.17; key packages in `requirements.lock` (lightgbm 4.7.0, shap 0.51.0,
  scikit-learn 1.9.1, numpy 2.4.6, pandas 3.0.6, datasets 5.0.1); `docs/environment.json`.
- Frozen matrices and hashes: `data/manifests/frozen_{author,role_aware}.json`; fold assignments
  `data/manifests/folds_seed42_{rep}.csv`.
- Independent features equal the author `extract_features` on all 9,191 author-parsed rows
  (checked inside `ingest.py`, 0 mismatches).
