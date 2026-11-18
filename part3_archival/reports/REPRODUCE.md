# Reproduce Exp02

**One command** (Hazel HPC, Slurm; each stage waits for the previous one):
```bash
bash /gpfs_common/share02/gaise/qle3/project_791/experiment_02_free_archive/scripts/run_all.sh
```

Requirements
- Disk: ≈90 GB for raw archives (`data/raw`), ≈2 GB interim, <1 GB results. Network: public HTTPS only
  (Slurm `xfer` partition). No AWS/HF credentials.
- Compute: CPU only. Ingest takes ≈4 min on 32 cores. The pipeline array is 93 tasks × ≤2 h on 8 cores (most
  finish in minutes; the 50-seed nulls and the tuned LGBM are the longest). Analysis, companions and figures
  take a few minutes each. Peak RAM ≈12 GB (ingest).
- Environment: Python 3.11.17 at `bcm-validity/.venv`; full package list in `requirements.lock`
  (lightgbm 4.7.0, shap 0.51.0, scikit-learn 1.9.1, numpy 2.4.6, pandas 3.0.6, statsmodels 0.15.0). Downloads
  use `/share/gaise/qle3/envs/emse` (stdlib urllib, huggingface_hub). Feature extraction imports
  `bcm-validity/src/bcm_validity/features.py` at git `63da902`.
- Tests: `PYTHONPATH=src:../bcm-validity/src ../bcm-validity/.venv/bin/python -m pytest -q tests/` (5 tests).

Pins and seeds
- Data: S3 listing `data/manifests/s3_inventory.csv` (2026-10-26), downloaded keys with ETag + SHA-256
  `data/manifests/bulk_keys.csv.done.csv`; HF `ScaleAI/SWE-bench_Pro@2d52cb3d…` split v1;
  `SWE-bench_Pro-os@66f92766`.
- Cohort definitions: `src/bcm02/pipeline.py::COHORTS`; exclusions `data/manifests/disputed_instances.csv`,
  `data/manifests/config_deviant_tasks.csv`.
- Seeds: CV seeds 0–9 (task-grouped), permutation seeds 1000–1049, bootstrap 20261026 (2,000), audit
  sample 20261026, paired-task sheet 20261027, tuned-LGBM inner CV 7, LGBM `random_state=42`.
- Every per-fold OOF attribution matrix of every real-label run is saved: `results/runs/oof_*.npz` (phi, margin,
  y, instance_id, run).

Outputs: `results/tables/` (a0–a10, parser_*, outcome_*, task_labels), `results/figures/` (fig1–fig6 +
`CAPTIONS.md`), `results/validation/` (human-review sheets), `reports/`.
