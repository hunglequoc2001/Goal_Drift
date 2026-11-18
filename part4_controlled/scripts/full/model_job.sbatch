#!/bin/bash
# One serving job for one model: start vLLM, then run that model's manifest rows with the full-study driver.
# Usage: sbatch --job-name=<phase>_<model_key> --gres=gpu:<type>:<n> [--partition/--qos/--time] \
#          scripts/full/model_job.sbatch <model_key> <manifest_csv> <results_root> [tp_override] [n_agents_override]
# Resumable (see driver.py). Normally launched through scripts/full/lanes.sh, which keeps <= 3 jobs queued; at exit the
# job hands off to its lane (resubmits itself if attempts are left, else starts the next model). Defaults: short_gpu, 2 h, 1 GPU.
# CPUs: 8 per GPU (the RTX 6000 Pro nodes have 64 cores for 8 GPUs; pilot jobs used ~2 cores at 8 agents).
#SBATCH --partition=gpu_partners
#SBATCH --account=gaise_gpu
#SBATCH --qos=short_gpu
#SBATCH --gres=gpu:rtx_6000_pro:1
#SBATCH --time=01:58:00
#SBATCH --mem=120G
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load cuda
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH  # site module binds the load-time $PWD, which breaks --writable sandboxes (P3.3)
export HF_HOME=/share/gaise/qle3/hf_cache APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache MSWEA_GLOBAL_CONFIG_DIR=/share/gaise/qle3/mswea_config VLLM_CACHE_ROOT=/share/gaise/qle3/vllm_cache XDG_CACHE_HOME=/share/gaise/qle3/xdg_cache VLLM_USE_FLASHINFER_SAMPLER=0
# agent sandboxes (~125k files each) on node-local disk only (P3.6)
LOCAL=/scratch/$USER/$SLURM_JOB_ID; mkdir -p $LOCAL/tmp $LOCAL/apptainer_tmp
export TMPDIR=$LOCAL/tmp APPTAINER_TMPDIR=$LOCAL/apptainer_tmp
trap 'kill ${VPID:-} 2>/dev/null; rm -rf $LOCAL' EXIT
live=$(squeue -u $USER -h -o %A | tr '\n' ' ')
for d in /scratch/$USER/*; do j=${d##*/}; [[ " $live " == *" $j "* ]] || rm -rf "$d"; done
df -h /scratch | tail -1
# node-local disk guard (2026-11-10/11: gpu40's /scratch was filled to 100% by another user, so every sandbox build failed):
# with too little free space, hand the lane to another node instead of failing every attempt here.
FREE_G=$(df --output=avail -BG /scratch | tail -1 | tr -dc 0-9)
if [ "${FREE_G:-0}" -lt ${MIN_SCRATCH_G:-200} ]; then
  echo "only ${FREE_G}G free on /scratch of $(hostname); resubmitting this lane elsewhere"
  # merge with any earlier --exclude (sbatch keeps only the last one, so excludes must accumulate in a single option)
  EX=$( (echo "${LANE_OPTS:-}" | grep -o -- '--exclude=[^ ]*' | cut -d= -f2 | tr ',' '\n'; hostname) | sort -u | paste -sd, )
  LANE_OPTS="$(echo "${LANE_OPTS:-}" | sed -E 's/--exclude=[^ ]*//g') --exclude=$EX" scripts/full/lanes.sh next $1 $2 $3 1; exit 0
fi
KEY=$1; MANIFEST=$2; RESULTS=$3
PY=/share/gaise/qle3/envs/exp03/bin/python
cfg() { $PY -c "import json,sys;print(json.load(open('configs/full/models.json'))['$KEY'].get('$1',''))"; }
# tensor-parallel size = number of allocated GPUs (override with TP_OVERRIDE)
DIR=$(cfg dir); TP=${TP_OVERRIDE:-${4:-$(nvidia-smi -L | wc -l)}}; NAG=${5:-$(cfg n_agents)}; GUARD=$(cfg guard_s); EXTRA=$(cfg extra_vllm)
export MODEL_REVISION=$(cfg revision) STUDY_PHASE=$(basename $RESULTS)
LEFT=$($PY -c "
import pandas as pd, os
M = pd.read_csv('$MANIFEST', keep_default_na=False); M = M[M.model_key == '$KEY']
print(sum(not os.path.exists(f'$RESULTS/$KEY/{r}.result.json') for r in M.run_id))")
echo "attempts left for $KEY: $LEFT"
[ "$LEFT" -gt 0 ] || { echo "nothing left; not starting vLLM"; scripts/full/lanes.sh next $KEY $MANIFEST $RESULTS 0; exit 0; }
PORT=$((20000 + SLURM_JOB_ID % 10000))
nvidia-smi --query-gpu=name,memory.total --format=csv
export PILOT_GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
DEADLINE=$(date -d "$(squeue -h -j $SLURM_JOB_ID -o %e)" +%s)
echo "key=$KEY tp=$TP agents=$NAG guard=$GUARD deadline=$DEADLINE gpu=$PILOT_GPU host=$(hostname)"
/share/gaise/qle3/envs/emse/bin/vllm serve $DIR --served-model-name $KEY --port $PORT --tensor-parallel-size $TP --max-model-len 32768 --gpu-memory-utilization 0.92 --seed 0 $EXTRA > logs/vllm-$SLURM_JOB_ID.log 2>&1 &
VPID=$!
for i in $(seq 1 360); do curl -sf localhost:$PORT/v1/models >/dev/null && break; kill -0 $VPID 2>/dev/null || { echo "vllm died"; tail -30 logs/vllm-$SLURM_JOB_ID.log; exit 1; }; sleep 5; done; echo "vllm ready after ~$((i*5))s"
$PY -u scripts/full/driver.py $MANIFEST $KEY http://localhost:$PORT/v1 $RESULTS $NAG $DEADLINE $GUARD ${PART:-0/1}
kill $VPID 2>/dev/null; wait $VPID 2>/dev/null || true
LEFT=$($PY -c "
import pandas as pd, os
M = pd.read_csv('$MANIFEST', keep_default_na=False); M = M[M.model_key == '$KEY']
print(sum(not os.path.exists(f'$RESULTS/$KEY/{r}.result.json') for r in M.run_id))")
echo "end=$(date -Is) attempts left for $KEY: $LEFT"
scripts/full/lanes.sh next $KEY $MANIFEST $RESULTS $LEFT
