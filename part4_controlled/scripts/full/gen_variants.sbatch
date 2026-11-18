#!/bin/bash
# Serve the variant generator (GLM-4-32B-0414, not an evaluated agent) and draft B2/C2 candidates.
# Usage: [GEN_EXTRA="--quantization fp8"] sbatch scripts/full/gen_variants.sbatch <tasks_csv> [n_samples] [kinds]
# (fp8 weights let the generator run on 48 GB L40/L40S cards; drafts are validated by execution either way)
#SBATCH --job-name=gen_variants
#SBATCH --partition=gpu_partners
#SBATCH --account=gaise_gpu
#SBATCH --qos=short_gpu
#SBATCH --gres=gpu:rtx_6000_pro:1
#SBATCH --time=01:58:00
#SBATCH --mem=96G
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
cd /gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents
module load cuda
export HF_HOME=/share/gaise/qle3/hf_cache VLLM_CACHE_ROOT=/share/gaise/qle3/vllm_cache XDG_CACHE_HOME=/share/gaise/qle3/xdg_cache VLLM_USE_FLASHINFER_SAMPLER=0
PORT=$((20000 + SLURM_JOB_ID % 10000))
/share/gaise/qle3/envs/emse/bin/vllm serve ${GEN_DIR:-/share/gaise/qle3/models/GLM-4-32B-0414} --served-model-name ${GEN_NAME:-glm-4-32b-0414} --port $PORT --max-model-len 32768 --gpu-memory-utilization 0.92 --seed 0 ${GEN_EXTRA:-} > logs/vllm-$SLURM_JOB_ID.log 2>&1 &
VPID=$!; trap 'kill $VPID 2>/dev/null' EXIT
for i in $(seq 1 360); do curl -sf localhost:$PORT/v1/models >/dev/null && break; kill -0 $VPID 2>/dev/null || { echo "vllm died"; tail -30 logs/vllm-$SLURM_JOB_ID.log; exit 1; }; sleep 5; done; echo "vllm ready after ~$((i*5))s"
/share/gaise/qle3/envs/exp03/bin/python -u scripts/full/gen_variants.py http://localhost:$PORT/v1 ${GEN_NAME:-glm-4-32b-0414} $1 data/variants_full ${2:-3} ${3:-B2,C2}
echo "end=$(date -Is)"
