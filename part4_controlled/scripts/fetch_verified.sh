#!/bin/bash
set -euo pipefail
/share/gaise/qle3/envs/exp03/bin/python - <<'PY'
from huggingface_hub import HfApi, snapshot_download
for name in ["SWE-bench/SWE-bench_Verified"]:
    sha = HfApi().dataset_info(name).sha
    p = snapshot_download(name, repo_type="dataset", revision=sha, local_dir="data/swe_bench_verified")
    open("data/swe_bench_verified.revision", "w").write(sha + "\n")
    print(name, sha, p)
PY
find data/swe_bench_verified -type f | head
