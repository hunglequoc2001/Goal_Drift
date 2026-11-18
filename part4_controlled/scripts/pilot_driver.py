"""Drive the pilot for ONE served model: tasks x validated variants x seeds, N agents in parallel.
Each attempt is an isolated subprocess (scripts/run_agent.py). An attempt whose result.json exists is skipped,
so the driver can be resumed. Several jobs may drive the same model at once: each attempt is claimed with
an O_EXCL lock file that records the Slurm job id, and a lock whose job is no longer running is stale and
is taken over. The job list is rotated by <part>/<n_parts>, so parallel jobs start at different points.
Only variants whose validation.json marks them valid are run.
Usage: python pilot_driver.py <served_name> <api_base> <tasks_csv> <out_dir> [n_parallel] [seeds e.g. 1-5] [part/n_parts]
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
JOB = os.environ.get("SLURM_JOB_ID", f"pid{os.getpid()}")


def jobs(tasks_csv, seeds):
    out = []
    for iid in pd.read_csv(tasks_csv).instance_id:
        vdir = ROOT / "data/variants" / iid
        v = json.loads((vdir / "validation.json").read_text()) if (vdir / "validation.json").exists() else {}
        if not v.get("A_oracle_valid"):
            print("SKIP task (oracle not validated):", iid, flush=True)
            continue
        variants = [("A", "", "")]
        if v.get("B1_valid"):
            variants.append(("B1", str(vdir / "B1.txt"), ""))
        if v.get("C1_valid"):
            variants.append(("C1", "", str(vdir / "C1.pre.diff")))
        for var, prob, pre in variants:
            for s in seeds:
                out.append((iid, var, prob, pre, s))
    return out


def _job_running(jid):
    if not jid.isdigit():
        return False
    r = subprocess.run(["squeue", "-h", "-j", jid, "-o", "%T"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() in {"RUNNING", "COMPLETING"}


def claim(lock):
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, JOB.encode())
        os.close(fd)
        return True
    except FileExistsError:
        owner = lock.read_text().strip()
        if owner == JOB or _job_running(owner):
            return False
        lock.write_text(JOB)          # stale lock from a killed job: take over
        return True


def run(model, api, out, job):
    iid, var, prob, pre, s = job
    rid = f"{model}__{iid}__{var}__s{s}"
    if (out / f"{rid}.result.json").exists():
        return rid, "done-before"
    lock = out / f"{rid}.lock"
    if not claim(lock):
        return rid, "claimed-elsewhere"
    cmd = [sys.executable, "-u", str(ROOT / "scripts/run_agent.py"), "--model", model, "--api-base", api,
           "--instance", iid, "--variant", var, "--sif", f"/share/gaise/qle3/sif/{iid}.sif", "--seed", str(s),
           "--out", str(out)]
    if prob:
        cmd += ["--problem-file", prob]
    if pre:
        cmd += ["--pre-patch", pre]
    with open(out / f"{rid}.stdout.log", "w") as log:
        p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd="/tmp", timeout=7200)
    lock.unlink(missing_ok=True)
    return rid, p.returncode


def main(model, api, tasks_csv, out, n=8, seeds="1-5", part="0/1"):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    a, b = map(int, seeds.split("-"))
    J = jobs(tasks_csv, range(a, b + 1))
    i, k = map(int, part.split("/"))
    r = (len(J) * i) // k
    J = J[r:] + J[:r]
    print(f"{len(J)} attempts for {model}, part {part} starts at {r}, job {JOB}", flush=True)
    with ThreadPoolExecutor(int(n)) as ex:
        for rid, rc in ex.map(lambda j: run(model, api, out, j), J):
            print(rid, rc, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
