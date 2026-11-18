#!/bin/bash
# Serve the reviewer (Qwen3-Coder-30B-A3B-Instruct; a different family from the drafters) and run review_ai.py.
# Usage: sbatch [--gres=gpu:<type>:1] scripts/full/review_ai.sbatch <tasks_csv> [kinds]
#SBATCH --job-name=review_ai
#SBATCH --partition=gpu_partners
#SBATCH --account=gaise_gpu
#SBATCH --qos=short_gpu
#SBATCH --gres=gpu:rtx_6000_pro:1
#SBATCH --time=01:58:00
#SBATCH --mem=96G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load cuda
export HF_HOME=/share/gaise/qle3/hf_cache VLLM_CACHE_ROOT=/share/gaise/qle3/vllm_cache XDG_CACHE_HOME=/share/gaise/qle3/xdg_cache VLLM_USE_FLASHINFER_SAMPLER=0
PORT=$((20000 + SLURM_JOB_ID % 10000))
/share/gaise/qle3/envs/emse/bin/vllm serve /share/gaise/qle3/models/Qwen3-Coder-30B-A3B-Instruct --served-model-name reviewer --port $PORT --max-model-len 32768 --gpu-memory-utilization 0.92 --seed 0 > logs/vllm-$SLURM_JOB_ID.log 2>&1 &
VPID=$!; trap 'kill $VPID 2>/dev/null' EXIT
for i in $(seq 1 360); do curl -sf localhost:$PORT/v1/models >/dev/null && break; kill -0 $VPID 2>/dev/null || { echo vllm died; exit 1; }; sleep 5; done
/share/gaise/qle3/envs/exp03/bin/python -u scripts/full/review_ai.py http://localhost:$PORT/v1 reviewer $1 ${2:-B2,C2}
