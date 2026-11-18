"""Run one agent attempt (model x task x variant x repeat) and grade it with the executable oracle.

Scaffold: mini-swe-agent 2.4.6 DefaultAgent, text-based (backtick) action format from its official
swebench_backticks.yaml, identical for all models; SingularityEnvironment (apptainer) on the task's
official image (local SIF); model served locally by vLLM (OpenAI-compatible API).
Writes <out>/<run_id>.traj.json (full message history) and <out>/<run_id>.result.json.

Usage: python run_agent.py --model <served_name> --api-base http://host:port/v1 --instance <id>
         --variant A --problem-file <txt or ''> --sif <path> --seed <int> --out <dir> [--step-limit 50]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.singularity import SingularityEnvironment
from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel

sys.path.insert(0, str(Path(__file__).parent))
from oracle import load_instance, run_oracle  # noqa: E402

EXEC_ARGS = ["--contain", "--cleanenv", "--no-home", "--no-mount", "cwd"]
CFG = Path(sys.modules["minisweagent"].__file__).parent / "config/benchmarks/swebench_backticks.yaml"


def main():
    ap = argparse.ArgumentParser()
    for a in ["--model", "--api-base", "--instance", "--variant", "--sif", "--out"]:
        ap.add_argument(a, required=True)
    ap.add_argument("--problem-file", default="")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--step-limit", type=int, default=50)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--top-p", type=float, default=0.8)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--pre-patch", default="", help="patch applied to /testbed before the agent starts (variant C1)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    run_id = f"{a.model.replace('/', '_')}__{a.instance}__{a.variant}__s{a.seed}"
    inst = load_instance(a.instance)
    task = Path(a.problem_file).read_text() if a.problem_file else inst["problem_statement"]
    cfg = yaml.safe_load(CFG.read_text())
    cfg["agent"].update(step_limit=a.step_limit, cost_limit=0)
    model = LitellmTextbasedModel(
        model_name=f"hosted_vllm/{a.model}", cost_tracking="ignore_errors",
        model_kwargs={"api_base": a.api_base, "api_key": "EMPTY", "temperature": a.temperature, "top_p": a.top_p,
                      "seed": a.seed, "max_tokens": a.max_tokens, "drop_params": True},
        **{k: v for k, v in cfg["model"].items() if k not in ("model_name", "model_kwargs")})
    envcfg = {k: v for k, v in cfg["environment"].items() if k != "environment_class"}
    env = SingularityEnvironment(image=a.sif, executable="apptainer", exec_args=EXEC_ARGS, **envcfg)
    hc = env.execute({"command": "cd /testbed && git status --short && python --version"})
    if hc["returncode"] != 0:   # infrastructure failure: never let the agent see a broken environment
        (out / f"{run_id}.infra_fail.json").write_text(json.dumps(hc))
        env.cleanup()
        raise SystemExit(f"environment health check failed: {hc['output'][:500]}")
    t0 = time.time()
    if a.pre_patch:
        # --contain gives every exec a fresh /tmp, so the patch goes in via a heredoc (as in oracle.py)
        pre_txt = Path(a.pre_patch).read_text()
        r = env.execute({"command": f"cd /testbed && git apply <<'PREPATCH_EOF' && git status --short\n{pre_txt}\nPREPATCH_EOF"})
        assert r["returncode"] == 0 and r["output"].strip(), r   # applied and the working tree changed
        # hide the pre-applied change from `git diff` so the agent sees the repo as committed state
        env.execute({"command": "cd /testbed && git add -A && git -c user.email=x@y -c user.name=x commit -qm base"})
    agent = DefaultAgent(model, env, **cfg["agent"])
    exit_status, submission, err = None, "", ""
    try:
        info = agent.run(task)
        exit_status, submission = info.get("exit_status"), info.get("submission") or ""
    except Exception as e:  # keep failures as data
        exit_status, err = type(e).__name__, str(e)[:2000]
    agent_secs = time.time() - t0
    agent.save(out / f"{run_id}.traj.json", {"info": {"exit_status": exit_status, "submission": submission,
                                                      "error": err, "variant": a.variant, "seed": a.seed,
                                                      "model": a.model, "instance_id": a.instance}})
    env.cleanup()
    # grade: for C1 the oracle must start from the pre-patched repo, i.e. pre_patch + submission
    pre = Path(a.pre_patch).read_text() if a.pre_patch else ""
    rep, rc = run_oracle(inst, submission, a.sif, out / f"{run_id}.eval.log",
                         extra_setup=(f"cd /testbed && git apply <<'PREPATCH_EOF'\n{pre}\nPREPATCH_EOF" if pre else ""))
    res = dict(run_id=run_id, model=a.model, instance_id=a.instance, variant=a.variant, seed=a.seed,
               exit_status=exit_status, n_calls=agent.n_calls, submission_len=len(submission),
               resolved=bool(rep.get("resolved")), patch_applied=rep.get("patch_successfully_applied"),
               agent_seconds=round(agent_secs, 1), error=err,
               temperature=a.temperature, top_p=a.top_p, step_limit=a.step_limit,
               slurm_job=os.environ.get("SLURM_JOB_ID"), gpu=os.environ.get("PILOT_GPU"))
    (out / f"{run_id}.result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
