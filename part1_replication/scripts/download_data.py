"""Download pinned dataset revisions (run on the xfer partition)."""
import hashlib, json, pathlib, sys, time
import yaml
from huggingface_hub import snapshot_download

ROOT = pathlib.Path(__file__).resolve().parents[1]
cfg = yaml.safe_load((ROOT / "configs/experiment.yaml").read_text())
out = {}
for key, d in cfg["datasets"].items():
    if not isinstance(d, dict):
        continue
    t0 = time.time()
    local = ROOT / cfg["paths"]["raw"] / key
    snapshot_download(repo_id=d["repo_id"], repo_type="dataset", revision=d["revision"],
                      allow_patterns=[d["pattern"], "README.md"], local_dir=local)
    files = {}
    for p in sorted(local.glob(d["pattern"])):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 22), b""):
                h.update(chunk)
        files[p.name] = {"bytes": p.stat().st_size, "sha256": h.hexdigest()}
    out[key] = {"repo_id": d["repo_id"], "revision": d["revision"], "files": files,
                "seconds": round(time.time() - t0, 1)}
    print(key, len(files), "files", out[key]["seconds"], "s", flush=True)
(ROOT / cfg["paths"]["manifests"]).mkdir(parents=True, exist_ok=True)
(ROOT / cfg["paths"]["manifests"] / "source_files.json").write_text(json.dumps(out, indent=2))
