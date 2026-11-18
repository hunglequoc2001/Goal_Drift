#!/bin/bash
# Validate every candidate task in parallel inside ONE job (3-job cap). Resumable: tasks whose validation.json already
# has C2_valid are skipped. Usage: sbatch validate_par.sbatch <tasks_csv>
#SBATCH --job-name=validate_par
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=96G
#SBATCH --cpus-per-task=16
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH
export APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache APPTAINER_TMPDIR=/share/gaise/qle3/apptainer_tmp
todo() { for i in $(tail -n +2 "$1" | cut -d, -f1); do grep -qs '"C2_valid"' data/variants_full/$i/validation.json || echo $i; done; }
todo $1 | xargs -P 14 -I{} sh -c '/share/gaise/qle3/envs/exp03/bin/python -u scripts/full/validate_variants.py {} || echo FAILED {}'
