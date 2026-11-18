#!/bin/bash
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=8
#SBATCH --array=1-24
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_01_verification
export OMP_NUM_THREADS=8 PYTHONPATH=/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/src
read rep pred sch s0 s1 < <(sed -n "${SLURM_ARRAY_TASK_ID}p" scripts/v5_tasks.txt)
echo "host=$(hostname) start=$(date -Is) $rep $pred $sch $s0 $s1"
/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/.venv/bin/python -u scripts/v5_independent_pipeline.py results/v5 $rep $pred $sch $s0 $s1
echo "end=$(date -Is)"
