#!/bin/bash
# Public metadata: SWE-bench Pro HF dataset (pinned revision recorded), official repo (eval script, traj README), nilenso notes.
set -euo pipefail
cd data/raw/_meta
export HF_HOME=/share/gaise/qle3/hf_cache
/share/gaise/qle3/envs/emse/bin/python -I - <<'PY'
from huggingface_hub import snapshot_download, HfApi
info = HfApi().dataset_info("ScaleAI/SWE-bench_Pro")
print("hf_sha", info.sha)
p = snapshot_download("ScaleAI/SWE-bench_Pro", repo_type="dataset", revision=info.sha, local_dir="swe_bench_pro_hf")
open("swe_bench_pro_hf.revision", "w").write(info.sha + "\n")
PY
rm -rf SWE-bench_Pro-os && git clone --depth 1 https://github.com/scaleapi/SWE-bench_Pro-os.git && git -C SWE-bench_Pro-os rev-parse HEAD > SWE-bench_Pro-os.sha
rm -rf nilenso && git clone --depth 1 https://github.com/nilenso/swe-bench-pro-cost-token-time-analysis.git nilenso && git -C nilenso rev-parse HEAD > nilenso.sha
ls -la; du -sh *
