#!/bin/bash
# Usage: sbatch scripts/full/analysis_human.sbatch <ingested_dir> <out_dir> [n_boot]
#SBATCH --job-name=analysis_human
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=00:45:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=16
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
P=/gpfs_common/share02/gaise/qle3/project_791
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8} MPLBACKEND=Agg PYTHONPATH=src:$P/experiment_02_free_archive/src:$P/bcm-validity/src
echo "host=$(hostname) start=$(date -Is) args=$*"
$P/bcm-validity/.venv/bin/python -u -m bcm03.analysis_human "$@"
echo "end=$(date -Is)"
