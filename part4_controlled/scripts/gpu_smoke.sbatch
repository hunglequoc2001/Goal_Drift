#!/bin/bash
#SBATCH --partition=gpu_partners
#SBATCH --account=gaise_gpu
#SBATCH --qos=short_gpu
#SBATCH --gres=gpu:rtx_6000_pro:1
#SBATCH --time=01:50:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load cuda
module load apptainer/1.4.2-1
unset APPTAINER_BINDPATH  # site module binds the load-time $PWD, which breaks --writable sandboxes
export HF_HOME=/share/gaise/qle3/hf_cache APPTAINER_CACHEDIR=/share/gaise/qle3/apptainer_cache APPTAINER_TMPDIR=/share/gaise/qle3/apptainer_tmp MSWEA_GLOBAL_CONFIG_DIR=/share/gaise/qle3/mswea_config VLLM_CACHE_ROOT=/share/gaise/qle3/vllm_cache XDG_CACHE_HOME=/share/gaise/qle3/xdg_cache
export VLLM_USE_FLASHINFER_SAMPLER=0
export TMPDIR=${TMPDIR:-/tmp}; df -h $TMPDIR | tail -1; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
MODEL=/share/gaise/qle3/models/Qwen2.5-Coder-7B-Instruct; NAME=qwen2.5-coder-7b; PORT=$((20000 + SLURM_JOB_ID % 10000))
/share/gaise/qle3/envs/emse/bin/vllm serve $MODEL --served-model-name $NAME --port $PORT --max-model-len 32768 --gpu-memory-utilization 0.90 --seed 0 > logs/vllm-$SLURM_JOB_ID.log 2>&1 &
VPID=$!
for i in $(seq 1 240); do curl -sf localhost:$PORT/v1/models >/dev/null && break; kill -0 $VPID 2>/dev/null || { echo "vllm died"; tail -30 logs/vllm-$SLURM_JOB_ID.log; exit 1; }; sleep 5; done; echo "vllm ready after ~$((i*5))s"
# throughput benchmark: 32 concurrent 1k-token completions
/share/gaise/qle3/envs/exp03/bin/python scripts/bench_vllm.py http://localhost:$PORT/v1 $NAME > results/bench_$NAME.json; cat results/bench_$NAME.json
/share/gaise/qle3/envs/exp03/bin/python -u scripts/run_agent.py --model $NAME --api-base http://localhost:$PORT/v1 --instance astropy__astropy-12907 --variant A --sif /share/gaise/qle3/sif/verified_astropy-12907.sif --seed 1 --out results/smoke --step-limit 50
echo "end=$(date -Is)"
