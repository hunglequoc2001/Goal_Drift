"""Full-study driver for ONE served model: runs the manifest rows of that model, N agents in parallel.

Inherits the pilot driver's recovery rules (scripts/pilot_driver.py):
  * an attempt whose result.json exists is skipped, so any job can be resubmitted at any time;
  * attempts are claimed with O_EXCL lock files holding the Slurm job id; a lock whose job is no longer RUNNING is
    stale and is taken over, so several jobs (parallel chains) can drive the same model;
  * an attempt killed by infrastructure (job end, node failure) leaves no result.json and is rerun from scratch with the
    same seed.
New:
  * deadline-aware claiming: no new attempt is started when less than GUARD seconds remain before the Slurm job ends,
    so attempts are not killed by the time limit (fewer reruns, no bias towards short attempts);
  * a pre-registered per-attempt agent wall-clock cap (run_attempt.py --wall-cap, default 3600 s) is scored as a
    failure, not rerun (0/660 pilot attempts exceeded 46 min);
  * manifest order = seed-major (all tasks and variants at seed 1, then seed 2, ...), so an interrupted study still
    holds complete low-index replicates;
  * a heartbeat file per job (<results>/_heartbeat/<job>.json) with counts, for monitoring.
Usage: python driver.py <manifest_csv> <model_key> <api_base> <results_root> <n_agents> [deadline_epoch] [guard_s] [part/n]
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
JOB = os.environ.get("SLURM_JOB_ID", f"pid{os.getpid()}")
SIF = "/share/gaise/qle3/sif/{}.sif"


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


class State:
    def __init__(self, out, deadline, guard):
        self.out, self.deadline, self.guard = out, deadline, guard
        self.c = dict(done_before=0, claimed_elsewhere=0, ran=0, failed_rc=0, skipped_deadline=0)
        self.lock = Lock()
        self.hb = out / "_heartbeat" / f"{JOB}.json"
        self.hb.parent.mkdir(parents=True, exist_ok=True)

    def bump(self, k):
        with self.lock:
            self.c[k] += 1
            self.hb.write_text(json.dumps(dict(job=JOB, t=time.time(), deadline=self.deadline, **self.c)))


def run(row, api, st, model_kwargs, wall_cap):
    out = st.out / row.model_key
    rid = row.run_id
    if (out / f"{rid}.result.json").exists():
        return rid, st.bump("done_before")
    if st.deadline and time.time() > st.deadline - st.guard:
        return rid, st.bump("skipped_deadline")
    out.mkdir(parents=True, exist_ok=True)
    lock = out / f"{rid}.lock"
    if not claim(lock):
        return rid, st.bump("claimed_elsewhere")
    cmd = [sys.executable, "-u", str(ROOT / "scripts/full/run_attempt.py"), "--model", row.served_name, "--api-base", api,
           "--instance", row.instance_id, "--variant", row.variant, "--sif", SIF.format(row.instance_id),
           "--seed", str(row.seed), "--out", str(out), "--model-kwargs", json.dumps(model_kwargs),
           "--wall-cap", str(wall_cap)]
    if os.environ.get("ACTIVATE_TESTBED") == "1":
        cmd.append("--activate-testbed")
    for flag, col in [("--problem-file", "problem_file"), ("--pre-patch", "pre_patch"), ("--oracle-test-patch", "oracle_test_patch")]:
        v = getattr(row, col)
        if isinstance(v, str) and v:
            cmd += [flag, str(ROOT / v)]
    with open(out / f"{rid}.stdout.log", "w") as log:
        try:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd="/tmp", timeout=wall_cap + 1800)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "driver-timeout"
    lock.unlink(missing_ok=True)
    st.bump("ran" if rc == 0 else "failed_rc")
    return rid, rc


def main(manifest, model_key, api, results_root, n_agents, deadline=0, guard=1800, part="0/1"):
    M = pd.read_csv(manifest, keep_default_na=False)
    M = M[M.model_key == model_key].sort_values("order").reset_index(drop=True)
    reg = json.loads((ROOT / "configs/full/models.json").read_text()).get(model_key, {})   # {} only for fake test models
    i, k = map(int, part.split("/"))
    r = (len(M) * i) // k
    rows = list(M.iloc[r:].itertuples()) + list(M.iloc[:r].itertuples())
    st = State(Path(results_root).resolve(), float(deadline), float(guard))
    print(f"{len(rows)} attempts for {model_key}, part {part}, job {JOB}, deadline {deadline}, guard {guard}", flush=True)
    with ThreadPoolExecutor(int(n_agents)) as ex:
        cap = int(os.environ.get("WALL_CAP", reg.get("wall_cap_s", 3600)))   # env override only for infrastructure tests
        for rid, rc in ex.map(lambda row: run(row, api, st, reg.get("model_kwargs", {}), cap), rows):
            if rc not in (None,):
                print(rid, rc, flush=True)
    print("summary", json.dumps(st.c), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
