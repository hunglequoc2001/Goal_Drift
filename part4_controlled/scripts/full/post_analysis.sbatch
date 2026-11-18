#!/bin/bash
# Usage: sbatch scripts/full/post_analysis.sbatch <ingested_dir> <out_dir> [n_boot]
# Runs bcm03.analysis_missing then bcm03.analysis_human on an analysis_full output directory.
#SBATCH --job-name=post_analysis
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:30:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=16
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
P=/gpfs_common/share02/gaise/qle3/project_791
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8} MPLBACKEND=Agg PYTHONPATH=src:$P/experiment_02_free_archive/src:$P/bcm-validity/src
echo "host=$(hostname) start=$(date -Is) args=$*"
$P/bcm-validity/.venv/bin/python -u -m bcm03.analysis_missing $1 $2 ${3:-2000}
$P/bcm-validity/.venv/bin/python -u -m bcm03.analysis_human $1 $2 ${3:-2000}
echo "end=$(date -Is)"
