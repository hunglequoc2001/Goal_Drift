#!/bin/bash
# Usage: sbatch scripts/analysis.sbatch <results_dir> <out_dir> [n_real_seeds] [n_null_seeds]
#SBATCH --job-name=analysis03
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=16
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
P=/gpfs_common/share02/gaise/qle3/project_791
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8} MPLBACKEND=Agg PYTHONPATH=src:$P/experiment_02_free_archive/src:$P/bcm-validity/src
PY=$P/bcm-validity/.venv/bin/python
echo "host=$(hostname) start=$(date -Is) args=$*"
$PY -u -m bcm03.ingest $1 $2
$PY -u -m bcm03.analysis $2 $2 ${3:-10} ${4:-50}
echo "end=$(date -Is)"
