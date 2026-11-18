#!/bin/bash
# Usage: sbatch --job-name=pilot_<name> scripts/pilot_model.sbatch <model_dir> <served_name> <tp> [max_model_len]
# Resumable: finished attempts are skipped, so 2 h short_gpu jobs can be chained with --dependency=afterany.
# Partition/QOS/GPU can be overridden on the sbatch command line; EXTRA_VLLM adds model-specific serve flags.
#SBATCH --partition=gpu
#SBATCH --account=gaise_gpu
#SBATCH --qos=gpu
#SBATCH --gres=gpu:h100:1
#SBATCH --time=12:00:00
#SBATCH --mem=128G
#SBATCH --cpus-per-task=32
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load cuda
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH  # site module binds the load-time $PWD, which breaks --writable sandboxes
export HF_HOME=/share/gaise/qle3/hf_cache APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache APPTAINER_TMPDIR=/share/gaise/qle3/apptainer_tmp MSWEA_GLOBAL_CONFIG_DIR=/share/gaise/qle3/mswea_config VLLM_CACHE_ROOT=/share/gaise/qle3/vllm_cache XDG_CACHE_HOME=/share/gaise/qle3/xdg_cache VLLM_USE_FLASHINFER_SAMPLER=0
# Per-attempt agent sandboxes (~125k files each) MUST be on node-local disk, never on shared GPFS
# (round 1 exceeded the GPFS quota; results/pilot_INVALID_quota_round1/README.md).
LOCAL=/scratch/$USER/$SLURM_JOB_ID; mkdir -p $LOCAL/tmp $LOCAL/apptainer_tmp
export TMPDIR=$LOCAL/tmp APPTAINER_TMPDIR=$LOCAL/apptainer_tmp
trap 'kill ${VPID:-} 2>/dev/null; rm -rf $LOCAL' EXIT
# remove sandboxes left by my earlier jobs on this node that were killed before their trap finished
live=$(squeue -u $USER -h -o %A | tr '\n' ' ')
for d in /scratch/$USER/*; do j=${d##*/}; [[ " $live " == *" $j "* ]] || rm -rf "$d"; done
df -h /scratch | tail -1
MODEL=$1; NAME=$2; TP=${3:-1}; MAXLEN=${4:-32768}; PORT=$((20000 + SLURM_JOB_ID % 10000))
nvidia-smi --query-gpu=name,memory.total --format=csv
export PILOT_GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
/share/gaise/qle3/envs/emse/bin/vllm serve $MODEL --served-model-name $NAME --port $PORT --tensor-parallel-size $TP --max-model-len $MAXLEN --gpu-memory-utilization 0.92 --seed 0 ${EXTRA_VLLM:-} > logs/vllm-$SLURM_JOB_ID.log 2>&1 &
VPID=$!
for i in $(seq 1 360); do curl -sf localhost:$PORT/v1/models >/dev/null && break; kill -0 $VPID 2>/dev/null || { echo "vllm died"; tail -30 logs/vllm-$SLURM_JOB_ID.log; exit 1; }; sleep 5; done; echo "vllm ready after ~$((i*5))s"
[ -s results/bench_$NAME.json ] || /share/gaise/qle3/envs/exp03/bin/python scripts/bench_vllm.py http://localhost:$PORT/v1 $NAME > results/bench_$NAME.json || true
/share/gaise/qle3/envs/exp03/bin/python -u scripts/pilot_driver.py $NAME http://localhost:$PORT/v1 configs/pilot_tasks.csv results/pilot/$NAME 8 1-5 ${PART:-0/1}
echo "end=$(date -Is)"
