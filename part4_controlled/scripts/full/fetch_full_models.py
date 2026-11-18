"""Full-study model access check and download (runs on the xfer partition; no HF token is configured).

1. Records gating/licence/availability for the planned ~70B model and its alternatives (results/full_prep/model_access.json).
2. Downloads, pinned to the current revision, the ungated models the full study needs that are not yet on disk:
   - openai/gpt-oss-120b           (pre-specified alternative 6th agent if Llama-3.3-70B is inaccessible; Apache-2.0)
   - zai-org/GLM-4-32B-0414         (variant generator for B2/C2; not an evaluated agent; MIT)
Usage: python fetch_full_models.py [--check-only]
"""
import json
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/full_prep"
CHECK = ["meta-llama/Llama-3.3-70B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "openai/gpt-oss-120b",
         "zai-org/GLM-4-32B-0414", "THUDM/GLM-4-32B-0414", "Qwen/Qwen2.5-Coder-32B-Instruct"]
GET = {"openai/gpt-oss-120b": "gpt-oss-120b", "zai-org/GLM-4-32B-0414": "GLM-4-32B-0414"}


def main(check_only):
    OUT.mkdir(parents=True, exist_ok=True)
    api, rec = HfApi(), {}
    for m in CHECK:
        r = {}
        try:
            info = api.model_info(m, files_metadata=True)
            r.update(sha=info.sha, gated=getattr(info, "gated", None), private=info.private,
                     license=(info.card_data or {}).get("license") if info.card_data else None,
                     safetensors_gb=round(sum((s.size or 0) for s in info.siblings if s.rfilename.endswith(".safetensors")) / 1e9, 1))
            try:   # can THIS account (no token) actually fetch a file?
                hf_hub_download(m, "config.json", revision=info.sha, cache_dir="/share/gaise/qle3/hf_cache/access_probe")
                r["download_ok"] = True
            except Exception as e:
                r["download_ok"], r["download_error"] = False, f"{type(e).__name__}: {str(e)[:300]}"
        except Exception as e:
            r["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        rec[m] = r
        print(m, json.dumps(r), flush=True)
    (OUT / "model_access.json").write_text(json.dumps(rec, indent=1))
    if check_only:
        return
    for m, local in GET.items():
        r = rec.get(m, {})
        if not r.get("download_ok"):
            print("SKIP (not downloadable)", m, flush=True)
            continue
        dst = Path("/share/gaise/qle3/models") / local
        snapshot_download(m, revision=r["sha"], local_dir=str(dst),
                          allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "tokenizer*", "*.jinja"],
                          ignore_patterns=["original/*", "metal/*"])
        (dst.parent / f"{local}.revision").write_text(r["sha"] + "\n")
        print("DOWNLOADED", m, r["sha"], flush=True)


if __name__ == "__main__":
    main("--check-only" in sys.argv)
