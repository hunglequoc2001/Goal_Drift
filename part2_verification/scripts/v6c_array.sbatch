#!/bin/bash
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=16
#SBATCH --array=1-30
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_01_verification
export OMP_NUM_THREADS=16 PYTHONPATH=/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/src
read rep b k < <(sed -n "${SLURM_ARRAY_TASK_ID}p" scripts/v6c_tasks.txt)
echo "host=$(hostname) start=$(date -Is) $rep $b $k"
/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/.venv/bin/python -u scripts/v6c_exact_interventional_full.py results/v6c $rep $b $k
echo "end=$(date -Is)"
