# Each stage runs as a Slurm job; nothing heavy runs on the login node.
SB = sbatch --partition=compute_partners --qos=short --time=01:59:00 --mem=64G scripts/slurm/run_stage.sbatch
PY = PYTHONPATH=src .venv/bin/python

.PHONY: test download ingest author e0 core secondary analysis figures reports
test:      ; $(PY) -m pytest -q
download:  ; sbatch scripts/slurm/download.sbatch
ingest:    ; $(SB) bcm_validity.ingest
author:    ; $(SB) bcm_validity.author_archival
e0:        ; for r in author role_aware; do $(SB) bcm_validity.experiments e0 --rep $$r; done
core:      ; for s in A B D; do for r in author role_aware; do $(SB) bcm_validity.experiments $$s --rep $$r; done; done
secondary: ; for s in C G_pilot; do for r in author role_aware; do $(SB) bcm_validity.experiments $$s --rep $$r; done; done
analysis:  ; $(SB) bcm_validity.analysis all --rep both
figures:   ; $(PY) -m bcm_validity.figures
