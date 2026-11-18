#!/bin/bash
set -uo pipefail
/share/gaise/qle3/envs/exp03/bin/python - <<'PY'
from huggingface_hub import HfApi, snapshot_download
api = HfApi()
cands = ["Qwen/Qwen3-Coder-30B-A3B-Instruct", "mistralai/Devstral-Small-2507", "Qwen/Qwen2.5-Coder-32B-Instruct", "SWE-bench/SWE-agent-LM-32B"]
for m in cands:
    try:
        info = api.model_info(m, files_metadata=True)
        gb = sum((s.size or 0) for s in info.siblings if s.rfilename.endswith(".safetensors")) / 1e9
        print("AVAILABLE", m, info.sha, f"{gb:.1f}GB", "gated" if getattr(info, "gated", False) else "open", flush=True)
        if getattr(info, "gated", False):
            continue
        snapshot_download(m, revision=info.sha, local_dir=f"/share/gaise/qle3/models/{m.split('/')[-1]}",
                          allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*", "*.jinja", "tekken*"])
        open(f"/share/gaise/qle3/models/{m.split('/')[-1]}.revision", "w").write(info.sha + "\n")
        print("DOWNLOADED", m, flush=True)
    except Exception as e:
        print("FAIL", m, type(e).__name__, str(e)[:200], flush=True)
PY
du -sh /share/gaise/qle3/models/*
