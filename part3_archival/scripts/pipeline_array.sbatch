#!/bin/bash
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=8
#SBATCH --array=1-93
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_02_free_archive
export OMP_NUM_THREADS=8 PYTHONPATH=src:/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/src
read c rep p cv sch s0 s1 < <(sed -n "${SLURM_ARRAY_TASK_ID}p" scripts/pipeline_tasks.txt)
echo "host=$(hostname) start=$(date -Is) $c $rep $p $cv $sch $s0 $s1"
/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/.venv/bin/python -u -m bcm02.pipeline $c $rep $p $cv $sch $s0 $s1 results/runs
echo "end=$(date -Is)"
