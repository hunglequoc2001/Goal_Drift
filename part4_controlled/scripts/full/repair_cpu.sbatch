#!/bin/bash
# CPU step of the C2 repair cycle. Usage: sbatch repair_cpu.sbatch prep|validate <tasks_csv>
#SBATCH --job-name=repair_cpu
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=16
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH
export APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache APPTAINER_TMPDIR=/share/gaise/qle3/apptainer_tmp
PY=/share/gaise/qle3/envs/exp03/bin/python
if [ "$1" = prep ]; then
  tail -n +2 $2 | cut -d, -f1 | xargs -P 14 -I{} sh -c "echo instance_id > /tmp/t_{}.csv; echo {} >> /tmp/t_{}.csv; $PY -u scripts/full/repair_c2.py prep /tmp/t_{}.csv; rm /tmp/t_{}.csv"
else   # validate: tasks that still lack a valid C2 (parallel, one task per process)
  for i in $(tail -n +2 $2 | cut -d, -f1); do f=data/variants_full/$i/validation.json; grep -qs '"C2_valid": true' $f || { grep -qs '"A_valid": true' $f && echo $i; }; done \
   | xargs -P 14 -n 1 $PY -u scripts/full/validate_c2.py
fi
