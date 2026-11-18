#!/bin/bash
# GPU step of the C2 repair cycle. Usage: sbatch [--gres=gpu:<type>:1] repair_gen.sbatch <tasks_csv> <round>
#SBATCH --job-name=repair_gen
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
/share/gaise/qle3/envs/emse/bin/vllm serve /share/gaise/qle3/models/gpt-oss-120b --served-model-name gpt-oss-120b --port $PORT --max-model-len 32768 --gpu-memory-utilization 0.92 --seed 0 > logs/vllm-$SLURM_JOB_ID.log 2>&1 &
VPID=$!; trap 'kill $VPID 2>/dev/null' EXIT
for i in $(seq 1 360); do curl -sf localhost:$PORT/v1/models >/dev/null && break; kill -0 $VPID 2>/dev/null || { echo vllm died; exit 1; }; sleep 5; done
# optional extra fresh drafts first (set FRESH_C2=<csv>, FRESH_B2=<csv>)
export GEN_MAXTOK=16000 GEN_BODY='{"reasoning_effort":"medium"}' GEN_OFFSET=20
[ -z "${FRESH_C2:-}" ] || /share/gaise/qle3/envs/exp03/bin/python -u scripts/full/gen_variants.py http://localhost:$PORT/v1 gpt-oss-120b $FRESH_C2 data/variants_full 4 C2
[ -z "${FRESH_B2:-}" ] || /share/gaise/qle3/envs/exp03/bin/python -u scripts/full/gen_variants.py http://localhost:$PORT/v1 gpt-oss-120b $FRESH_B2 data/variants_full 4 B2
unset GEN_OFFSET
GEN_MAXTOK=14000 GEN_BODY='{"reasoning_effort":"medium"}' /share/gaise/qle3/envs/exp03/bin/python -u scripts/full/repair_c2.py gen http://localhost:$PORT/v1 gpt-oss-120b $1 $2
