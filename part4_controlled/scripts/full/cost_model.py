"""GPU-hour and wall-clock model for full-study designs, grounded in the pilot's Slurm and per-attempt records.

Inputs (all measured in the pilot, scripts/full/pilot_cost_audit.py):
  slot time per attempt (setup + agent + grading) by model, at 8 concurrent agents per vLLM server;
  vLLM start-up per job (median by model); throughput scaling 1 -> 8 -> 32 concurrent requests (results/bench_*.json).
Job model (simulated, 2 h short_gpu jobs or long gpu-QOS jobs): start-up, then k agent slots run attempts drawn from the
model's empirical slot-time distribution; a slot claims a new attempt only if more than `guard` seconds remain; an
attempt still running at the time limit is killed (wasted, rerun later). GPU-hours per completed attempt =
job GPU-hours / completed attempts. Concurrency k > 8 slows each agent by the per-sequence decode slowdown read off the
benchmark (linear between 8 and 32 concurrent requests), applied to the agent part of the slot only.
Models without pilot data: Qwen2.5-Coder-32B = SWE-agent-LM-32B (same architecture, conservative);
gpt-oss-120b = 2 x Qwen3-Coder-30B-A3B slot time (similar active size, hidden reasoning tokens). Staging gate S4
replaces these assumptions with measurements.
Usage: python cost_model.py [design_json ...]   -> results/full_prep/cost_model.json + printed table
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RNG = np.random.default_rng(1)
PILOT = {"qwen3-coder-30b-a3b": "qwen3-coder-30b-a3b", "devstral-small-2507": "devstral-small-2507",
         "swe-agent-lm-32b": "swe-agent-lm-32b", "qwen2.5-coder-7b": "qwen2.5-coder-7b",
         "qwen2.5-coder-32b": "swe-agent-lm-32b", "gpt-oss-120b": "qwen3-coder-30b-a3b"}
SCALE = {"gpt-oss-120b": 2.0}
GPUS_PER_JOB = {"swe-agent-lm-32b": 1, "qwen2.5-coder-32b": 1}   # on H200 (TP=1); TP=2 on RTX doubles this


def slowdown(model, k):
    b = json.loads((ROOT / f"results/bench_{PILOT[model]}.json").read_text())
    per = {int(c): v["out_tok_per_s"] / int(c) for c, v in b.items()}
    s32 = per[8] / per[32]
    return 1.0 if k <= 8 else 1 + (s32 - 1) * (min(k, 32) - 8) / 24


def simulate_job(slots, agent_frac, k, sd, startup, T, guard, n_jobs=400):
    done, gpu_s = 0, 0.0
    for _ in range(n_jobs):
        end_all = startup
        for _ in range(k):
            t = startup
            while t < T - guard:
                d = RNG.choice(slots)
                d = d * (1 - agent_frac) + d * agent_frac * sd
                if t + d <= T:
                    done += 1
                    t += d
                else:            # killed by the time limit
                    t = T
            end_all = max(end_all, min(t, T))
        gpu_s += end_all
    return gpu_s / done        # GPU-seconds per completed attempt (1 GPU per job)


def per_attempt(model, k, T=7080, guard=None):
    A = pd.read_csv(ROOT / "results/full_prep/pilot_cost_attempts.csv")
    J = pd.read_csv(ROOT / "results/full_prep/pilot_cost_jobs.csv")
    g = A[A.model == PILOT[model]]
    slots = g.slot_s.dropna().to_numpy() * SCALE.get(model, 1.0)
    agent_frac = float((g.agent_s / g.slot_s).clip(0, 1).mean())
    startup = float(J[J.model == PILOT[model]].vllm_startup_s.median())
    guard = guard if guard is not None else float(np.quantile(slots, 0.99))
    sd = slowdown(model, k)
    s = simulate_job(slots, agent_frac, k, sd, startup, T, guard)
    steady = float(np.mean(slots * (1 - agent_frac) + slots * agent_frac * sd)) / k
    return dict(model=model, k=k, slowdown=round(sd, 3), guard_s=round(guard), startup_s=startup,
                gpu_min_per_attempt=s / 60 * GPUS_PER_JOB.get(model, 1), steady_gpu_min=steady / 60 * GPUS_PER_JOB.get(model, 1),
                efficiency=steady / s, mean_slot_s=float(slots.mean()))


def design_cost(design, table):
    rows = []
    for cond in design["conditions"]:
        for m in cond["models"]:
            n = cond["n_tasks"] * cond["repeats"]
            rows.append(dict(variant=cond["variant"], model=m, attempts=n, gpu_h=n * table[m] / 60))
    D = pd.DataFrame(rows)
    return D


def main(*design_files):
    K = {"qwen3-coder-30b-a3b": 16, "devstral-small-2507": 12, "swe-agent-lm-32b": 12, "qwen2.5-coder-32b": 12,
         "qwen2.5-coder-7b": 16, "gpt-oss-120b": 16}
    rows = []
    for m, k in K.items():
        for kk in sorted({8, k}):
            for T, label in [(7080, "short_gpu_2h"), (3 * 86400 - 600, "gpu_qos_3d")]:
                r = per_attempt(m, kk, T)
                r["job"] = label
                rows.append(r)
    C = pd.DataFrame(rows)
    out = ROOT / "results/full_prep"
    C.to_csv(out / "cost_per_attempt.csv", index=False)
    print(C.round(3).to_string())
    plan = C[(C.job == "short_gpu_2h") & (C.k == C.model.map(K))].set_index("model").gpu_min_per_attempt.to_dict()
    res = {}
    for f in design_files:
        d = json.loads(Path(f).read_text())
        D = design_cost(d, plan)
        res[d["name"]] = dict(attempts=int(D.attempts.sum()), gpu_h=float(D.gpu_h.sum()),
                              by_model=D.groupby("model")[["attempts", "gpu_h"]].sum().round(1).to_dict("index"),
                              by_variant=D.groupby("variant")[["attempts", "gpu_h"]].sum().round(1).to_dict("index"))
        for conc in [3, 6, 10]:
            res[d["name"]][f"wall_days_at_{conc}_gpus"] = float(D.gpu_h.sum() / conc / 24)
        print(d["name"], json.dumps({k: v for k, v in res[d["name"]].items() if k not in ("by_model", "by_variant")}))
    (out / "cost_model.json").write_text(json.dumps(dict(per_attempt_plan=plan, designs=res), indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
