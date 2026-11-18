"""Run the author's scripts unchanged against the pinned local datasets.

Nothing under external/ is edited. A bootstrap patches datasets.load_dataset so the
hub repo IDs resolve to the pinned local snapshots, then executes each script with
runpy in a fresh subprocess inside runs/author_archival/ (the scripts use relative
tbf/ paths). Exit codes, stdout, stderr and timings are recorded for every script.
"""
import json
import subprocess
import sys
import time

from . import ROOT, load_config

SCRIPTS = [
    "data/load_swebench.py",
    "data/extract_features.py",
    "model/behavioral_predictor_pipeline.py",
    "metrics/bcm.py",
    "metrics/clustering.py",
    "models/umap_projection.py",
    "data/confound.py",
    "experiments/exp1_inconsistency.py",
    "experiments/exp2_gaming.py",
    "experiments/exp3_drift.py",
    "figures/plot_all.py",
]

BOOTSTRAP = r'''
import runpy, sys, datasets
LOCAL = {LOCAL!r}
_orig = datasets.load_dataset
def _pinned(path, *args, split=None, **kwargs):
    if path in LOCAL:
        files = LOCAL[path]
        if split not in files:  # same failure the hub raises for an unknown split
            raise ValueError(f"Unknown split {{split!r}} for pinned {{path}}; available {{list(files)}}")
        return _orig("parquet", data_files={{split: files[split]}}, split=split)
    return _orig(path, *args, split=split, **kwargs)
datasets.load_dataset = _pinned
sys.argv = [{script!r}]
runpy.run_path({script!r}, run_name="__main__")
'''


def main():
    cfg = load_config()
    # Pinned shards for the split the author requests; sorted order = hub order.
    local = {d["repo_id"]: {d["split"]: sorted(str(p) for p in (ROOT / cfg["paths"]["raw"] / k).glob(d["pattern"]))}
             for k, d in cfg["datasets"].items() if isinstance(d, dict)}
    run_dir = ROOT / "runs/author_archival"
    log_dir = ROOT / "logs/author_archival"
    for p in (run_dir / "tbf/data", run_dir / "tbf/models", log_dir):
        p.mkdir(parents=True, exist_ok=True)
    status = []
    for rel in SCRIPTS:
        script = str(ROOT / "external/colm-agent-eval" / rel)
        code = BOOTSTRAP.format(LOCAL=local, script=script)
        t0 = time.time()
        proc = subprocess.run([sys.executable, "-c", code], cwd=run_dir,
                              capture_output=True, text=True)
        name = rel.replace("/", "__")
        (log_dir / f"{name}.stdout").write_text(proc.stdout)
        (log_dir / f"{name}.stderr").write_text(proc.stderr)
        err = proc.stderr.strip().splitlines()[-1] if proc.returncode else ""
        status.append({"script": rel, "returncode": proc.returncode,
                       "seconds": round(time.time() - t0, 1), "last_error_line": err})
        print(status[-1], flush=True)
    (log_dir / "status.json").write_text(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
