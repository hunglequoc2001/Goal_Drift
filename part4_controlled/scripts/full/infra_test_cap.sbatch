#!/bin/bash
# Model-free infrastructure test of the full-study runner and driver (CPU only; fake_llm.py replaces vLLM).
# Checks: sandbox + health check, final-state capture and grading, text submissions, saved-output truncation, wall-clock
# cap, C1 pre-patch, lock takeover after a killed driver, skip of finished attempts, deadline guard. Also finishes any
# staging-pool validation that is missing. Usage: sbatch scripts/full/infra_test.sbatch
#SBATCH --job-name=infra_cap
#SBATCH --partition=compute_partners
#SBATCH --account=gaise_cpu
#SBATCH --qos=short
#SBATCH --time=01:59:00
#SBATCH --mem=48G
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -uo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH
export APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache MSWEA_GLOBAL_CONFIG_DIR=/share/gaise/qle3/mswea_config
B=/tmp; mkdir -p /scratch/$USER 2>/dev/null && B=/scratch/$USER; LOCAL=$B/infra_$SLURM_JOB_ID; mkdir -p $LOCAL/tmp $LOCAL/at; export TMPDIR=$LOCAL/tmp APPTAINER_TMPDIR=$LOCAL/at
df -h $LOCAL | tail -1
trap 'kill ${FPID:-} 2>/dev/null; rm -rf $LOCAL' EXIT
PY=/share/gaise/qle3/envs/exp03/bin/python
for iid in $(tail -n +2 configs/full/staging_pool.csv | cut -d, -f1); do
  [ -s data/variants_full/$iid/validation.json ] || $PY -u scripts/full/validate_variants.py $iid --skip-b2c2
done
PORT=$((30000 + SLURM_JOB_ID % 10000))
$PY scripts/full/fake_llm.py $PORT & FPID=$!; sleep 5
R=results/infra_test_$SLURM_JOB_ID; mkdir -p $R
$PY - <<PYEOF
import pandas as pd
rows=[]
def add(m,iid,v,s,**f):
    rows.append(dict(run_id=f"{m}__{iid}__{v}__s{s}",phase="infra_test",model_key=m,served_name=m,instance_id=iid,variant=v,seed=s,
                     taskset="test",order=len(rows),problem_file=f.get("pf",""),pre_patch=f.get("pp",""),oracle_test_patch=""))
for i in ["django__django-14672","sympy__sympy-24066"]:
    pass
    add("fake-gold",i,"C1",1,pp=f"data/variants_full/{i}/C1.pre.diff"); add("fake-gold",i,"B1",1,pf=f"data/variants_full/{i}/B1.txt")
add("fake-bigout","django__django-14672","A",1); add("fake-sleep","django__django-14672","A",1)
pd.DataFrame(rows).to_csv("$R/manifest.csv",index=False)
PYEOF
API=http://127.0.0.1:$PORT/v1
WALL_CAP=60 timeout 900 $PY -u scripts/full/driver.py $R/manifest.csv fake-sleep $API $R 1 0 0
grep -h '"exit_status"\|agent_seconds' $R/fake-sleep/*.result.json
