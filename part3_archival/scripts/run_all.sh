#!/bin/bash
# Regenerate Exp02 end to end on Hazel (Slurm). Each stage waits for the previous one (sbatch --wait).
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_02_free_archive
PY=/share/gaise/qle3/envs/emse/bin/python
sbatch --wait --job-name=inv   scripts/xfer.sbatch $PY -I scripts/s3_inventory.py data/manifests/s3_inventory.csv.new   # optional re-listing (do not overwrite pinned listing)
sbatch --wait --job-name=meta  scripts/xfer.sbatch bash scripts/fetch_meta.sh
sbatch --wait --job-name=bulk  scripts/xfer.sbatch $PY -I scripts/s3_download.py data/manifests/bulk_keys.csv 16
sbatch --wait --job-name=ingest scripts/run_py.sbatch -m bcm02.ingest 32
sbatch --wait --job-name=val   --mem=16G --cpus-per-task=2 scripts/run_py.sbatch scripts/validate_outcomes.py
sbatch --wait --job-name=pval  --mem=64G --cpus-per-task=4 scripts/run_py.sbatch scripts/parser_validation.py
sbatch --wait --job-name=pipe  scripts/pipeline_array.sbatch
for rep in r0 r2 r3; do sbatch --wait --job-name=cfgclean --cpus-per-task=8 --mem=16G scripts/run_py.sbatch -m bcm02.pipeline primary5_cfgclean $rep lgbm_paper grouped5 real 0 10 results/runs; done
sbatch --wait --job-name=cfgclean --cpus-per-task=8 --mem=16G scripts/run_py.sbatch -m bcm02.pipeline primary5_cfgclean r2 lgbm_paper grouped5 perm_model 1000 1050 results/runs
sbatch --wait --job-name=analysis --cpus-per-task=4 --mem=32G scripts/run_py.sbatch -m bcm02.analysis
sbatch --wait --job-name=analysis2 --cpus-per-task=4 --mem=32G scripts/run_py.sbatch -c "import sys; sys.path.insert(0,'src'); from bcm02.analysis import main_extra; main_extra()"
for c in primary5 paper50; do sbatch --wait --job-name=comp --cpus-per-task=8 --mem=16G scripts/run_py.sbatch -m bcm02.companions $c r2; done
sbatch --wait --job-name=labels --cpus-per-task=4 --mem=32G scripts/run_py.sbatch -m bcm02.task_labels
sbatch --wait --job-name=align --cpus-per-task=2 --mem=16G scripts/run_py.sbatch scripts/alignment_vs_labels.py
sbatch --wait --job-name=figs  --cpus-per-task=2 --mem=8G scripts/run_py.sbatch -m bcm02.figures
