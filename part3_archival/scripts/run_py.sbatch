#!/bin/bash
# Usage: sbatch --job-name=<name> scripts/run_py.sbatch -m bcm02.<module> [args] | <script.py> [args]
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=128G
#SBATCH --cpus-per-task=32
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_02_free_archive
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8} MPLBACKEND=Agg PYTHONPATH=src:/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/src
echo "host=$(hostname) start=$(date -Is) args=$*"
/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/.venv/bin/python -u "$@"
echo "end=$(date -Is)"
