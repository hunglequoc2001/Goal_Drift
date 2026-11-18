#!/bin/bash
# Lane launcher that respects the user's cap of 3 concurrent Slurm jobs (memory: slurm-max-3-jobs).
# A queue file lists one model job per line:  <model_key> <sbatch options...>
# `lanes.sh start <queue> <manifest> <results> <n_lanes>` submits the first n_lanes lines (refuses if my running+pending
# jobs + n_lanes > 3). Each model_job.sbatch, when it exits, calls `lanes.sh next`: if its model still has attempts
# left it resubmits itself, otherwise it pops the next queue line. So at most n_lanes jobs are ever queued
# (the successor is submitted in the last seconds of its predecessor).
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
CAP=${LANE_CAP:-3}   # LANE_CAP raised only with the user's explicit approval (confirmatory_v2_envfix: 6, 2026-11-10)
mine() { squeue -u $USER -h -o "%j" | grep -vcE '^(scen|lora)' || true; }   # the user's own scen_*/lora_* jobs are not mine
submit() {  # <model_key> <manifest> <results> <queue> <sbatch opts...>
  local key=$1 man=$2 res=$3 q=$4; shift 4
  # lane settings go through the environment (--export=ALL), not the --export list: a comma inside LANE_OPTS
  # (e.g. --exclude=gpu40,gpu41) would otherwise split the list and truncate the successor's options (2026-11-11)
  LANE_QUEUE=$q LANE_ROUND=${ROUND:-0} LANE_OPTS="$*" ACTIVATE_TESTBED=${ACTIVATE_TESTBED:-0} LANE_CAP=$CAP \
  sbatch --parsable --job-name=$(basename $res)_$key --export=ALL "$@" \
    scripts/full/model_job.sbatch $key $man $res
}
case $1 in
  start)
    Q=$2; MAN=$3; RES=$4; N=$5
    [ $(( $(mine) + N )) -le $CAP ] || { echo "would exceed $CAP jobs ($(mine) queued)"; exit 1; }
    for i in $(seq 1 $N); do
      line=$(flock $Q.lock sh -c "head -1 $Q; sed -i 1d $Q")
      [ -n "$line" ] || break
      submit $(echo $line | cut -d' ' -f1) $MAN $RES $Q $(echo $line | cut -d' ' -f2-)
    done ;;
  next)   # called by model_job.sbatch at exit: <key> <manifest> <results> <left>
    KEY=$2; MAN=$3; RES=$4; LEFT=$5; Q=${LANE_QUEUE:-}
    [ -n "$Q" ] || exit 0
    if [ "$LEFT" -gt 0 ]; then
      ROUND=$(( ${LANE_ROUND:-0} + 1 ))   # guard against a model that never finishes (e.g. repeated infra failures)
      [ $ROUND -le 25 ] || { echo "lane stopped: $KEY still has $LEFT attempts after 25 jobs"; exit 0; }
      submit $KEY $MAN $RES $Q ${LANE_OPTS:-}; exit 0
    fi
    ROUND=0
    line=$(flock $Q.lock sh -c "head -1 $Q; sed -i 1d $Q")
    [ -n "$line" ] && submit $(echo $line | cut -d' ' -f1) $MAN $RES $Q $(echo $line | cut -d' ' -f2-) || echo "lane done" ;;
esac
