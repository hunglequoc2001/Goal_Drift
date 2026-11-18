#!/bin/bash
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --job-name=test_c1
#SBATCH --output=logs/%x-%j.out
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load apptainer/1.4.2-1; unset APPTAINER_BINDPATH
export MSWEA_GLOBAL_CONFIG_DIR=/share/gaise/qle3/mswea_config TMPDIR=/share/gaise/qle3/tmp/test_c1_$SLURM_JOB_ID; mkdir -p $TMPDIR
for t in django__django-14672 sympy__sympy-24066; do /share/gaise/qle3/envs/exp03/bin/python scripts/test_c1_setup.py $t; done
rm -rf $TMPDIR
