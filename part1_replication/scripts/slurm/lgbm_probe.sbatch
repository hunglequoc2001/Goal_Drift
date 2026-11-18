#!/bin/bash
#SBATCH --job-name=bcm-lgbm-probe
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=00:30:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err
cd /gpfs_common/share02/gaise/qle3/project_791/bcm-validity
mkdir -p results/tables/lgbm_version_probe
.venv/bin/python scripts/lgbm_version_probe.py results/tables/lgbm_version_probe/lgbm-current.json
for d in /share/gaise/qle3/envs/bcm_lgbm/lgbm-*; do
  $d/bin/python scripts/lgbm_version_probe.py results/tables/lgbm_version_probe/$(basename $d).json || echo "FAILED $d"
done
