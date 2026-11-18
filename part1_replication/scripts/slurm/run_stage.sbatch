#!/bin/bash
# Usage: sbatch --job-name=<name> scripts/slurm/run_stage.sbatch <python module> [args...]
#SBATCH --partition=compute
#SBATCH --account=gaise_cpu
#SBATCH --qos=normal
#SBATCH --time=06:00:00
#SBATCH --mem=96G
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/bcm-validity
export PYTHONPATH=src OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8} MPLBACKEND=Agg
echo "host=$(hostname) start=$(date -Is) args=$*"
lscpu | grep -E 'Model name|^CPU\(s\)' || true
/usr/bin/time -v .venv/bin/python -u -m "$@"
echo "end=$(date -Is)"
