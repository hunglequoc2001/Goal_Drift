"""Flatten replay_config for each run's smoke trajectories and report keys that differ across runs.
Usage: python -I compare_configs.py <out_csv>"""
import glob
import json
import sys
from collections import defaultdict


def flat(d, p=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from flat(v, f"{p}.{k}" if p else k)
    elif isinstance(d, list) and d and all(isinstance(x, dict) for x in d):
        for i, v in enumerate(d):
            yield from flat(v, f"{p}[{i}]")
    else:
        yield p, json.dumps(d, sort_keys=True)[:300]


vals = defaultdict(dict)   # key -> run -> set(values)
info = {}
for f in sorted(glob.glob("data/raw/*/traj/*/*.traj")):
    run = f.split("/")[2]
    t = json.load(open(f))
    rc = t["replay_config"]
    rc = json.loads(rc) if isinstance(rc, str) else rc
    for k, v in flat(rc):
        if k.startswith("agent.name") or "problem_statement" in k or "deployment.image" in k or "base_commit" in k or k.startswith("env.repo") or k.endswith(".id") or "output_dir" in k:
            continue
        vals[k].setdefault(run, set()).add(v)
    i = t.get("info", {})
    info.setdefault(run, set()).add((i.get("swe_agent_version"), i.get("swe_rex_version"), str(t.get("environment"))[:60]))
runs = sorted({r for k in vals for r in vals[k]})
with open(sys.argv[1], "w") as out:
    out.write("key\t" + "\t".join(runs) + "\n")
    for k in sorted(vals):
        per = [" | ".join(sorted(vals[k].get(r, {"<absent>"}))) for r in runs]
        if len(set(per)) > 1:
            out.write(k + "\t" + "\t".join(per) + "\n")
for r in runs:
    print(r, info[r])
