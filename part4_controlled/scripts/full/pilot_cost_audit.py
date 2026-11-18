"""Cost audit of the Exp03 pilot from Slurm accounting + per-attempt files (FULL_STUDY_COST_ESTIMATE.md inputs).

Per attempt: setup (container start, health check, C1 pre-patch) = first stdout timestamp -> first trajectory message;
agent = result.json agent_seconds; grading = traj.json mtime -> result.json mtime. Slot time = setup + agent + grading
(the time one of the 8 concurrent agent slots on a GPU job is occupied).
Per job (sacct): elapsed, vLLM start-up (from the job log), attempts completed in that job (result.json slurm_job).
Writes results/full_prep/pilot_cost_attempts.csv, pilot_cost_jobs.csv, pilot_cost_summary.json.
Only round-2 data (results/pilot) are used; round 1 is quarantined.
"""
import datetime as dt
import glob
import json
import os
import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/full_prep"
TS = re.compile(r"^(\d\d):(\d\d):(\d\d) ", re.M)


def attempts():
    rows = []
    for p in glob.glob(str(ROOT / "results/pilot/*/*.result.json")):
        r = json.load(open(p))
        base = p[:-len(".result.json")]
        t_end = os.path.getmtime(p)
        t_traj = os.path.getmtime(base + ".traj.json")
        txt = open(base + ".stdout.log", errors="replace").read(20000)
        m = TS.search(txt)
        start = None
        if m:
            d = dt.datetime.fromtimestamp(t_end).replace(hour=int(m[1]), minute=int(m[2]), second=int(m[3]))
            start = d.timestamp()
            if start > t_end:                      # attempt started before midnight
                start -= 86400
        slot = t_end - start if start else None
        rows.append(dict(model=r["model"], variant=r["variant"], slurm_job=r.get("slurm_job"), gpu=r.get("gpu"),
                         exit_status=r["exit_status"], n_calls=r["n_calls"], agent_s=r["agent_seconds"],
                         grade_s=t_end - t_traj, slot_s=slot, end=t_end,
                         traj_mb=os.path.getsize(base + ".traj.json") / 1e6,
                         files_mb=sum(os.path.getsize(f) for f in glob.glob(base + ".*")) / 1e6))
    A = pd.DataFrame(rows)
    A["setup_s"] = A.slot_s - A.agent_s - A.grade_s
    return A


def jobs():
    ids = sorted({re.search(r"-(\d+)\.out$", f)[1] for f in glob.glob(str(ROOT / "logs/pilot_*-15*.out"))})
    out = subprocess.run(["sacct", "-X", "-P", "-n", "-j", ",".join(ids), "-o",
                          "JobID,JobName,AllocTRES,NodeList,Start,End,ElapsedRaw,State"], capture_output=True, text=True).stdout
    rows = []
    for l in out.strip().splitlines():
        jid, name, tres, node, st, en, el, state = l.split("|")
        log = (ROOT / f"logs/{name}-{jid}.out").read_text(errors="replace")
        m = re.search(r"vllm ready after ~(\d+)s", log)
        g = re.search(r"gres/gpu:([a-z0-9_]+)=(\d+)", tres)
        rows.append(dict(job=jid, model=name.replace("pilot_", ""), gpu_type=g[1] if g else None, n_gpu=int(g[2]) if g else 0,
                         node=node, start=st, end=en, elapsed_s=int(el), state=state,
                         vllm_startup_s=int(m[1]) if m else None))
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    A, J = attempts(), jobs()
    n = A.groupby("slurm_job").size()
    J["attempts_done"] = J.job.map(n).fillna(0).astype(int)
    A.to_csv(OUT / "pilot_cost_attempts.csv", index=False)
    J.to_csv(OUT / "pilot_cost_jobs.csv", index=False)
    s = {}
    for m, g in A.groupby("model"):
        jm = J[J.model == m]
        s[m] = dict(attempts=len(g), slot_s_mean=g.slot_s.mean(), slot_s_median=g.slot_s.median(), slot_s_p95=g.slot_s.quantile(.95),
                    agent_s_mean=g.agent_s.mean(), setup_s_mean=g.setup_s.mean(), grade_s_mean=g.grade_s.mean(),
                    steady_gpu_min_per_attempt_at8=g.slot_s.mean() / 8 / 60,
                    jobs=len(jm), gpu_hours_all_jobs=float((jm.elapsed_s * jm.n_gpu).sum() / 3600),
                    gpu_hours_round2_jobs=float((jm[jm.job.astype(int) >= 1570465].elapsed_s * jm.n_gpu).sum() / 3600),
                    vllm_startup_s_median=jm.vllm_startup_s.median(), traj_mb_mean=g.traj_mb.mean(), traj_mb_max=g.traj_mb.max(),
                    files_mb_median=g.files_mb.median(), files_mb_mean=g.files_mb.mean(),
                    by_gpu={k: dict(n=len(v), slot_s_mean=v.slot_s.mean(), agent_s_mean=v.agent_s.mean()) for k, v in g.groupby("gpu")})
    (OUT / "pilot_cost_summary.json").write_text(json.dumps(s, indent=1, default=float))
    print(json.dumps(s, indent=1, default=float))
    print(J.to_string())


if __name__ == "__main__":
    main()
