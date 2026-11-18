#!/bin/bash
#SBATCH --job-name=bcm-envs
#SBATCH --partition=xfer
#SBATCH --account=gaise_cpu
#SBATCH --qos=xfer
#SBATCH --time=01:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=2
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err
cd /gpfs_common/share02/gaise/qle3/project_791/bcm-validity
bash scripts/build_lgbm_envs.sh
