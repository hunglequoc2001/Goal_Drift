#!/bin/bash
#SBATCH --job-name=bcm-download
#SBATCH --partition=xfer
#SBATCH --account=gaise_cpu
#SBATCH --qos=xfer
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=2
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/bcm-validity
export HF_HOME=/share/gaise/qle3/hf_cache
.venv/bin/python -c "import yaml" 2>/dev/null || { echo "pyyaml missing"; exit 1; }
.venv/bin/python scripts/download_data.py
