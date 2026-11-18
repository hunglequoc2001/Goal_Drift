"""Run one full-study attempt (model x task x variant x repeat) and grade it. Successor of scripts/run_agent.py (pilot),
which is kept unchanged as the record of what the pilot ran. Agent, prompts, sampling and environment are identical to
the pilot; the differences are bookkeeping and grading only:
  * variants B2/C2: problem text from data/variants_full/<iid>/; C2 is graded by its revised oracle (revised hidden tests)
    and, as a persistence diagnostic, also by the original oracle;
  * test-level status (FAIL_TO_PASS passed, PASS_TO_PASS failed) is stored, so regressions are measurable;
  * huge command outputs are truncated in the SAVED trajectory only (the agent already saw the harness-truncated
    observation; pilot §P9: one saved trajectory was 2.4 GB). The original length is recorded;
  * provenance: model revision, served name, GPU, Slurm job, sampling, and a hash of the problem text;
  * the final repository state (git diff of the sandbox when the agent stops) is saved and graded too, so final-state
    correctness does not depend on the agent submitting a well-formed diff (pilot addendum A1).

  * a pre-registered agent wall-clock cap (default 3600 s) ends the attempt as a failure (WallClockLimit).
  * --activate-testbed (added 2026-11-05, default off so the recorded runs stay reproducible): every agent command runs in
    the task's conda env `testbed`, as the grader does. Runs before this flag used the image's base Python 3.11.5, because
    each command is a fresh `bash -c` and nothing activated the env. Startup then verifies the interpreter and the import.

Usage: python run_attempt.py --model <served_name> --api-base <url> --instance <id> --variant A|B1|B2|C1|C2
         --sif <sif> --seed <int> --out <dir> [--problem-file f] [--pre-patch f] [--oracle-test-patch f]
         [--model-kwargs JSON] [--wall-cap s]
"""
import argparse
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path

import yaml
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.singularity import SingularityEnvironment
from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oracle import load_instance, run_oracle, with_test_patch  # noqa: E402

EXEC_ARGS = ["--contain", "--cleanenv", "--no-home", "--no-mount", "cwd"]
CFG = Path(sys.modules["minisweagent"].__file__).parent / "config/benchmarks/swebench_backticks.yaml"
KEEP = 20000        # chars kept from the head and from the tail of a saved raw command output
ACTIVATE = "source /opt/miniconda3/bin/activate >/dev/null 2>&1; conda activate testbed >/dev/null 2>&1\n"
TESTBED = "/opt/miniconda3/envs/testbed"
PKG = {"astropy": "astropy", "django": "django", "matplotlib": "matplotlib", "mwaskom": "seaborn", "psf": "requests",
       "pydata": "xarray", "pylint-dev": "pylint", "pytest-dev": "pytest", "scikit-learn": "sklearn", "sphinx-doc": "sphinx",
       "sympy": "sympy"}


class TestbedEnvironment(SingularityEnvironment):
    """Every command starts in the activated env; the prefix is not part of the agent's messages."""

    def execute(self, action, cwd="", *, timeout=None):
        return super().execute({**action, "command": ACTIVATE + action.get("command", "")}, cwd, timeout=timeout)


class WallClockLimit(BaseException):   # BaseException: mini-swe-agent's `except Exception` must not swallow it
    """Pre-registered per-attempt agent time cap; scored as a failure (the trajectory so far is kept and graded)."""


def _alarm(signum, frame):
    raise WallClockLimit("agent wall-clock cap reached")


def test_status(rep):
    ts = rep.get("tests_status") or {}
    f, p = ts.get("FAIL_TO_PASS", {}), ts.get("PASS_TO_PASS", {})
    return dict(f2p_pass=len(f.get("success", [])), f2p_total=len(f.get("success", [])) + len(f.get("failure", [])),
                p2p_fail=len(p.get("failure", [])), p2p_total=len(p.get("success", [])) + len(p.get("failure", [])),
                f2p_passed_ids=json.dumps(sorted(f.get("success", []))), p2p_failed_ids=json.dumps(sorted(p.get("failure", []))))


def shrink(messages):
    n = 0
    for m in messages:
        ex = m.get("extra") if isinstance(m, dict) else None
        ro = ex.get("raw_output") if isinstance(ex, dict) else None
        if isinstance(ro, str) and len(ro) > 2 * KEEP:
            ex["raw_output"] = ro[:KEEP] + f"\n[... {len(ro) - 2 * KEEP} chars removed when saving ...]\n" + ro[-KEEP:]
            ex["raw_output_original_chars"] = len(ro)
            n += 1
    return n


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
    ap.add_argument("--pre-patch", default="", help="patch applied and committed before the agent starts (C1)")
    ap.add_argument("--oracle-test-patch", default="", help="revised hidden-test patch that defines the oracle (C2)")
    ap.add_argument("--model-kwargs", default="{}", help="extra JSON model kwargs (pre-registered per model)")
    ap.add_argument("--wall-cap", type=int, default=3600, help="agent wall-clock cap in seconds (0 = none)")
    ap.add_argument("--activate-testbed", action="store_true", help="run agent commands in the task's testbed env")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    run_id = f"{a.model.replace('/', '_')}__{a.instance}__{a.variant}__s{a.seed}"
    inst = load_instance(a.instance)
    task = Path(a.problem_file).read_text() if a.problem_file else inst["problem_statement"]
    cfg = yaml.safe_load(CFG.read_text())
    cfg["agent"].update(step_limit=a.step_limit, cost_limit=0)
    mk = {"api_base": a.api_base, "api_key": "EMPTY", "temperature": a.temperature, "top_p": a.top_p,
          "seed": a.seed, "max_tokens": a.max_tokens, "drop_params": True, **json.loads(a.model_kwargs)}
    model = LitellmTextbasedModel(model_name=f"hosted_vllm/{a.model}", cost_tracking="ignore_errors", model_kwargs=mk,
                                  **{k: v for k, v in cfg["model"].items() if k not in ("model_name", "model_kwargs")})
    envcfg = {k: v for k, v in cfg["environment"].items() if k != "environment_class"}
    env = (TestbedEnvironment if a.activate_testbed else SingularityEnvironment)(image=a.sif, executable="apptainer", exec_args=EXEC_ARGS, **envcfg)
    hc_cmd = "cd /testbed && git status --short && python --version"
    if a.activate_testbed:
        pk = PKG[a.instance.split("__")[0]]
        hc_cmd += f" && python -c 'import sys, {pk}; assert sys.prefix == \"{TESTBED}\"; assert {pk}.__file__.startswith(\"/testbed/\")'"
    hc = env.execute({"command": hc_cmd})
    if hc["returncode"] != 0:   # infrastructure failure: never let the agent see a broken environment
        (out / f"{run_id}.infra_fail.json").write_text(json.dumps(hc))
        env.cleanup()
        raise SystemExit(f"environment health check failed: {hc['output'][:500]}")
    t0 = time.time()
    pre = Path(a.pre_patch).read_text() if a.pre_patch else ""
    if pre:
        # --contain gives every exec a fresh /tmp, so the patch goes in via a heredoc (pilot P3.8)
        r = env.execute({"command": f"cd /testbed && git apply <<'PREPATCH_EOF' && git status --short\n{pre}\nPREPATCH_EOF"})
        assert r["returncode"] == 0 and r["output"].strip(), r
        env.execute({"command": "cd /testbed && git add -A && git -c user.email=x@y -c user.name=x commit -qm base"})
    agent = DefaultAgent(model, env, **cfg["agent"])
    exit_status, submission, err = None, "", ""
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(a.wall_cap)
    try:
        info = agent.run(task)
        exit_status, submission = info.get("exit_status"), info.get("submission") or ""
    except (Exception, WallClockLimit) as e:  # keep failures as data (WallClockLimit: nothing submitted)
        exit_status, err = type(e).__name__, str(e)[:2000]
    signal.alarm(0)
    agent_secs = time.time() - t0
    n_shrunk = shrink(agent.messages)
    # final repository state (relative to the committed start state), independent of what the agent "submitted"
    st = env.execute({"command": "cd /testbed && git add -A && git diff --cached"})
    state_diff = st["output"] if st["returncode"] == 0 else None
    agent.save(out / f"{run_id}.traj.json", {"info": {"exit_status": exit_status, "submission": submission,
                                                      "state_diff": state_diff, "error": err, "variant": a.variant,
                                                      "seed": a.seed, "model": a.model, "instance_id": a.instance}})
    env.cleanup()
    setup = f"cd /testbed && git apply <<'PREPATCH_EOF'\n{pre}\nPREPATCH_EOF" if pre else ""
    g_inst = with_test_patch(inst, Path(a.oracle_test_patch).read_text()) if a.oracle_test_patch else inst
    t1 = time.time()
    rep, rc = run_oracle(g_inst, submission, a.sif, out / f"{run_id}.eval.log", extra_setup=setup)
    res = dict(run_id=run_id, model=a.model, instance_id=a.instance, variant=a.variant, seed=a.seed,
               exit_status=exit_status, n_calls=agent.n_calls, submission_len=len(submission),
               resolved=bool(rep.get("resolved")), patch_applied=rep.get("patch_successfully_applied"),
               oracle_kind="revised_C2" if a.oracle_test_patch else "original", **test_status(rep), oracle_timed_out=rc == "timeout",
               agent_seconds=round(agent_secs, 1), error=err, temperature=a.temperature, top_p=a.top_p,
               step_limit=a.step_limit, max_tokens=a.max_tokens, wall_cap=a.wall_cap, model_kwargs=json.loads(a.model_kwargs),
               problem_sha256=hashlib.sha256(task.encode()).hexdigest(), saved_outputs_truncated=n_shrunk,
               activate_testbed=a.activate_testbed, slurm_job=os.environ.get("SLURM_JOB_ID"), gpu=os.environ.get("PILOT_GPU"),
               model_revision=os.environ.get("MODEL_REVISION"), phase=os.environ.get("STUDY_PHASE"))
    if a.oracle_test_patch:   # C2 persistence diagnostic: did the agent implement the ORIGINAL requirement instead?
        rep0, _ = run_oracle(inst, submission, a.sif, out / f"{run_id}.eval_orig.log", extra_setup=setup)
        res["resolved_orig_oracle"] = bool(rep0.get("resolved"))
    # final-state correctness: grade the sandbox state diff when it differs from the submission (e.g. text submissions)
    res["state_equals_submission"] = state_diff is not None and state_diff.strip() == submission.strip()
    if state_diff is None:
        res["resolved_state"] = None
    elif res["state_equals_submission"]:
        res["resolved_state"] = res["resolved"]
    else:
        rs, _ = run_oracle(g_inst, state_diff, a.sif, out / f"{run_id}.eval_state.log", extra_setup=setup)
        res["resolved_state"] = bool(rs.get("resolved"))
    res["grade_seconds"] = round(time.time() - t1, 1)
    (out / f"{run_id}.result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
