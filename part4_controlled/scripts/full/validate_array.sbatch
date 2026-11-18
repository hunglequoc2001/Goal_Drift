#!/bin/bash
# Validate all variants of task number $SLURM_ARRAY_TASK_ID (1-based data row) of <tasks_csv>. CPU only.
# Usage: sbatch --array=1-N scripts/full/validate_array.sbatch <tasks_csv> [--skip-b2c2]
#SBATCH --job-name=validate_full
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH
export APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache APPTAINER_TMPDIR=/share/gaise/qle3/apptainer_tmp
IID=$(tail -n +2 "$1" | sed -n "${SLURM_ARRAY_TASK_ID}p" | cut -d, -f1)
echo "host=$(hostname) task=$IID start=$(date -Is)"
/share/gaise/qle3/envs/exp03/bin/python -u scripts/full/validate_variants.py "$IID" ${2:-}
echo "end=$(date -Is)"
