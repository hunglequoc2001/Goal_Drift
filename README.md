# What Does the Behavioral Consistency Metric Measure? — Replication Package

This repository accompanies the paper *What Does the Behavioral Consistency Metric Measure? A Construct-Validity
Study of Attribution-Based Consistency for Software Engineering Agents*. It contains the code, configurations,
task variants, human labels and result tables needed to reproduce every table and figure in the paper.

The Behavioral Consistency Metric (BCM; Banerjee & Raichura, arXiv:2608.13598) is the mean pairwise cosine similarity
of SHAP attributions from a classifier that predicts agent success from trajectory features. The study tests whether
BCM measures agent behaviour or the parser, predictor and tasks behind it.

## Repository layout

| Folder | Study part | Reproduces | Entry point |
|---|---|---|---|
| `part1_replication/` | Part 1: rerun and stage-by-stage audit of the released BCM pipeline (9,191 trajectories) | RQ1, RQ2 (Section IV-A/B) | `Makefile` (`make ingest e0 core secondary analysis`), `README.md` |
| `part2_verification/` | Part 2: independent re-implementation and checks (shipped-model search, permutation nulls, SHAP checks) | RQ1, RQ2 | `scripts/v1_*.py` … `v9_*.py`, `VERIFICATION_REPORT.md` |
| `part3_archival/` | Part 3: BCM on 9,139 public SWE-bench Pro trajectories under one scaffold | RQ1, RQ2 | `scripts/run_all.sh`, `README.md`, `reports/REPRODUCE.md` |
| `part4_controlled/` | Part 4: controlled experiment, 5 open-weight agents, 4,645 attempts on 111 SWE-bench Verified tasks | RQ2–RQ5, Fig. 1, Tables II–III | see below |
| `human_review/` | Part 5: blind review package, codebooks, both raters' labels, agreement | Table IV | see below |

## Part 4: controlled experiment

- `configs/full/models.json`: model registry (Hugging Face IDs and pinned revisions, GPU, sampling).
- `configs/full/manifests/confirmatory_v2_envfix.csv`: the per-attempt manifest (model, task, variant, seed) of the reported run.
- `data/swe_bench_verified/`: SWE-bench Verified snapshot (revision in `swe_bench_verified.revision`).
- `data/variants_full/<task>/`: task variants (`B1.txt`, `B2.txt`, `C1.pre.diff`, `C2.txt`, `C2.gold.diff`,
  `C2.test.diff`), drafting outputs (`gen/`), AI-review outputs (`review/`) and execution-validation results
  (`validation.json`).
- `scripts/full/`: task selection (`select_tasks.py`), variant generation and validation (`gen_variants.py`,
  `validate_b2.py`, `validate_c2.py`), the agent harness (`run_attempt.py`, `driver.py`, `model_job.sbatch`, `lanes.sh`),
  grading (`regrade.py`) and analysis wrappers (`ingest_full.sbatch`, `analysis_full.sbatch`, `post_analysis.sbatch`).
- `src/bcm03/`: measures and analysis (`measures.py`, `ingest_full.py`, `analysis_full.py`, `analysis_missing.py`,
  `analysis_human.py`).
- `results/ingest/`: per-attempt table (`attempts.parquet`) and per-step table (`steps.parquet`).
- `results/analysis/`: every output table used in the paper, for example `f1_bcm_summary.csv` (Fig. 1, Table III),
  `f2_repeatability.csv` (Table III), `h1_*.csv` (RQ3), `h2_invariance.csv` (RQ4), `h3_adaptation.csv`,
  `h4_adaptation_auc.csv`, `c1_decisions.csv` (RQ5), `s_human_h2.csv`, `s_human_h3.csv` (human-flag sensitivity),
  `s_gpu_covariate.csv`, `s_selection.csv`, `s_repo_bootstrap.csv`.
- `FULL_STUDY_ANALYSIS_PLAN.md`: the analysis plan fixed before the controlled attempts were run.

Reproduce the analysis from the included tables (CPU only):

```bash
cd part4_controlled
sbatch scripts/full/analysis_full.sbatch results/ingest results/analysis 10 50 2000
sbatch scripts/full/post_analysis.sbatch  results/ingest results/analysis 2000
```

Rerunning the agents requires the official SWE-bench images (converted to Apptainer SIFs by `scripts/pull_images.sh`),
the five models at the revisions in `models.json`, and GPUs (one RTX PRO 6000 or H200 per model; two RTX cards for the
32B models). Launch with `scripts/full/lanes.sh start <queue> configs/full/manifests/confirmatory_v2_envfix.csv <results_dir> <n_lanes>`
and `ACTIVATE_TESTBED=1`.

## Part 5: human review

- `human_review/blind_package/`: exactly what the raters received (no automatic or AI verdicts, no outcomes, model names
  replaced by codes), with `REVIEWER_GUIDE.md`. `model_code_key.csv` maps the codes back to runs.
- `human_review/labels/R1/`, `labels/R2/`: both raters' labels. Raters are two PhD students of our lab and are
  identified only as R1 and R2. Neither used AI tools.
- `human_review/labels/adjudications.csv`: the single project-lead adjudication.
- `human_review/ai_review/`: the local reviewer model's verdicts, compared with the human labels in the paper.
- `human_review/agreement/`: agreement, Cohen's κ and Gwet's AC1 per question (Table IV).

## Data not stored in this repository

- **Agent trajectories of Part 4** (about 6 GB) and the per-variant validation logs (about 0.7 GB) exceed GitHub's
  limits and will be deposited in a long-term archive; the per-attempt and per-step tables in `results/ingest/` contain
  every quantity used in the analysis.
- **Part 3 trajectories** are public. `part3_archival/scripts/s3_inventory.py` and `s3_download.py` download them;
  `part3_archival/data/manifests/` and `data/raw_meta/*.sha` verify their checksums.
- **The released BCM code** belongs to its authors and is not redistributed. Part 1 uses
  `https://github.com/pranilraichura/colm-agent-eval` at commit `61f98943803e4fd6820ec7df6eaa9fdb41c07b11`; clone it into
  `part1_replication/external/colm-agent-eval`.

## Software

Python 3.11; LightGBM 4.7.0; shap 0.51.0; scikit-learn 1.9.1; mini-SWE-agent 2.4.6; swebench 5.0.2; vLLM 0.32.0;
Apptainer 1.4.2. Lock files: `part1_replication/requirements.lock`, `part3_archival/requirements.lock`,
`part4_controlled/configs/exp03_env.lock`. Jobs were run with Slurm; `.sbatch` files show the resources used.
All inference ran on local GPUs; the study used no paid model APIs.

## Models (Hugging Face, pinned revisions)

| Model | Revision |
|---|---|
| Qwen/Qwen3-Coder-30B-A3B-Instruct | b2cff646eb4bb1d68355c01b18ae02e7cf42d120 |
| mistralai/Devstral-Small-2507 | bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39 |
| SWE-bench/SWE-agent-LM-32B | 6b6b924ea6f17aeff85e5228772df8fff3aab62d |
| Qwen/Qwen2.5-Coder-32B-Instruct | 381fc969f78efac66bc87ff7ddeadb7e73c218a7 |
| Qwen/Qwen2.5-Coder-7B-Instruct | c03e6d358207e414f1eca0bb1891e29f1db0e242 |
