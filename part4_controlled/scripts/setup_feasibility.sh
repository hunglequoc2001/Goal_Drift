#!/bin/bash
# Exp03 feasibility setup (network; xfer node). Everything outside /home.
set -euo pipefail
module load apptainer/1.4.2-1 || module load apptainer
apptainer --version
ENV=/share/gaise/qle3/envs/exp03
if [ ! -x $ENV/bin/python ]; then /share/gaise/qle3/envs/emse/bin/python -m venv $ENV; fi
$ENV/bin/pip install -q --upgrade pip
$ENV/bin/pip install -q "mini-swe-agent" "swebench" "datasets" "openai" 2>&1 | tail -3
$ENV/bin/pip freeze > configs/exp03_env.lock
$ENV/bin/python -c "import minisweagent, pkgutil, minisweagent.environments as e; print('mini-swe-agent', minisweagent.__version__); print([m.name for m in pkgutil.iter_modules(e.__path__)])"
SIF=/share/gaise/qle3/sif; mkdir -p $SIF
t0=$(date +%s); apptainer pull -F $SIF/verified_astropy-12907.sif docker://swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest; echo "verified pull s=$(( $(date +%s)-t0 ))"
t0=$(date +%s); apptainer pull -F $SIF/pro_nodebb-04998908.sif docker://jefzda/sweap-images:nodebb.nodebb-NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5; echo "pro pull s=$(( $(date +%s)-t0 ))"
ls -la $SIF
$ENV/bin/python - <<'PY'
from huggingface_hub import snapshot_download
for m in ["Qwen/Qwen2.5-Coder-7B-Instruct"]:
    p = snapshot_download(m, local_dir=f"/share/gaise/qle3/models/{m.split('/')[-1]}", allow_patterns=["*.json","*.safetensors","*.txt","*.model","tokenizer*"])
    print("downloaded", p)
PY
du -sh /share/gaise/qle3/models/* $SIF/*
