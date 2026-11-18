# Experiment 02: zero-cost archival study of BCM on SWE-bench Pro

Start with `reports/EXECUTIVE_SUMMARY.md`. Budget: `BUDGET_LEDGER.md` ($0).

- `src/bcm02/`: `parse.py` (R0–R3 representations), `ingest.py`, `pipeline.py` (cohorts, CV, predictors, nulls),
  `analysis.py` (tables a0–a8), `companions.py` (a9), `task_labels.py`, `figures.py`
- `scripts/`: download (`s3_inventory.py`, `s3_download.py`, `fetch_meta.sh`), validation (`validate_outcomes.py`,
  `parser_validation.py`, `alignment_vs_labels.py`), Slurm wrappers, `run_all.sh`
- `data/manifests/`: inventories, checksums, cohort exclusions, provenance table. `data/raw`, `data/interim`
  are not versioned (re-downloadable).
- `results/`: `runs/` (per-run CSVs + OOF attribution matrices), `tables/`, `figures/`, `validation/`
- `reports/`: COST_AND_DATA_ACCESS, PROVENANCE_DECISION, PARSER_VALIDATION, RESULTS, LIMITATIONS_AND_NOVELTY,
  REPRODUCE, EXECUTIVE_SUMMARY
