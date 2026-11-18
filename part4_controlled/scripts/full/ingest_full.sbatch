#!/bin/bash
# Re-grade (exp03 env, swebench) then ingest (bcm-validity venv) one results tree. CPU only. Never writes into <results_root>.
# Usage: sbatch scripts/full/ingest_full.sbatch <results_root> <out_dir> [variants_full_dir]
#SBATCH --job-name=ingest_full
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
P=/gpfs_common/share02/gaise/qle3/project_791
echo "host=$(hostname) start=$(date -Is) args=$*"
/share/gaise/qle3/envs/exp03/bin/python -u scripts/full/regrade.py $1 $2 ${3:-data/variants_full}
PYTHONPATH=src:$P/experiment_02_free_archive/src:$P/bcm-validity/src $P/bcm-validity/.venv/bin/python -u -m bcm03.ingest_full $1 $2
echo "end=$(date -Is)"
