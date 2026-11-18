#!/bin/bash
# Usage: sbatch validate_c2.sbatch <tasks_csv>   (one job, serial)
#SBATCH --job-name=validate_c2
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH
export APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache APPTAINER_TMPDIR=/share/gaise/qle3/apptainer_tmp
/share/gaise/qle3/envs/exp03/bin/python -u scripts/full/validate_c2.py $(tail -n +2 "$1" | cut -d, -f1 | tr '\n' ' ')
