# bcm-validity

Paper-faithful replication and fixed-trajectory measurement-validity audit of the Behavioral
Consistency Metric (Raichura & Banerjee, arXiv:2608.13598). Start with `reports/EXECUTIVE_SUMMARY.md`.

- `reports/` — 01 audit, 02 provenance, 03 replication, 04 sensitivity, 05 methods/threats
- `docs/DECISIONS.md` — pre-registered and post-hoc decisions; `configs/experiment.yaml` — all seeds/settings
- `src/bcm_validity/` — pipeline (one module per stage); `tests/` — QA tests (`make test`)
- `results/tables/`, `results/figures/`, `results/validation/` — outputs; `data/manifests/` — row IDs, hashes, folds
- Not in git: `data/raw`, `data/interim`, `results/arrays`, `runs/`, `external/` (author repo @ 61f98943)

Every stage runs as a Slurm job (`Makefile`; `scripts/slurm/run_stage.sbatch <module> [args]`).
Order: download → ingest → author → e0 → core (A, B, D) → secondary (C, G_pilot, then G) →
analysis → figures → `bcm_validity.smoke`.
