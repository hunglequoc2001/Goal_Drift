#!/bin/bash
# Usage: sbatch scripts/full/power.sbatch <pilot_measures_dir> <pilot_analysis_dir> <out_dir> [n_sims]
#SBATCH --job-name=power03
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
P=/gpfs_common/share02/gaise/qle3/project_791
export OMP_NUM_THREADS=8 PYTHONPATH=src:$P/experiment_02_free_archive/src:$P/bcm-validity/src
echo "host=$(hostname) start=$(date -Is) args=$*"
$P/bcm-validity/.venv/bin/python -u -m bcm03.power "$@"
echo "end=$(date -Is)"
