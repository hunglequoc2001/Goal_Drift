#!/bin/bash
#SBATCH --partition=xfer
#SBATCH --account=gaise_cpu
#SBATCH --qos=xfer
#SBATCH --time=12:00:00
#SBATCH --mem=20G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
export HF_HOME=/share/gaise/qle3/hf_cache PIP_CACHE_DIR=/share/gaise/qle3/pip_cache APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache APPTAINER_TMPDIR=/share/gaise/qle3/apptainer_tmp XDG_CACHE_HOME=/share/gaise/qle3/xdg_cache
mkdir -p $HF_HOME $PIP_CACHE_DIR $APPTAINER_CACHEDIR $APPTAINER_TMPDIR $XDG_CACHE_HOME
echo "host=$(hostname) start=$(date -Is) cmd=$*"
"$@"
echo "end=$(date -Is)"
