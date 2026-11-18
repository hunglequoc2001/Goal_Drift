#!/bin/bash
# Usage: sbatch --job-name=<name> scripts/xfer.sbatch <cmd...>   (network jobs; xfer partition)
#SBATCH --partition=xfer
#SBATCH --account=gaise_cpu
#SBATCH --qos=xfer
#SBATCH --time=12:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_02_free_archive
echo "host=$(hostname) start=$(date -Is) cmd=$*"
"$@"
echo "end=$(date -Is)"
