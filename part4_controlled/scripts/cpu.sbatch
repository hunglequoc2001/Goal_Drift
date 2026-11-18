#!/bin/bash
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH  # site module binds the load-time $PWD, which breaks --writable sandboxes
export APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache APPTAINER_TMPDIR=/share/gaise/qle3/apptainer_tmp HF_HOME=/share/gaise/qle3/hf_cache MSWEA_GLOBAL_CONFIG_DIR=/share/gaise/qle3/mswea_config
echo "host=$(hostname) start=$(date -Is) args=$*"
/share/gaise/qle3/envs/exp03/bin/python -u "$@"
echo "end=$(date -Is)"
