"""Executable oracle for SWE-bench Verified under Apptainer (no Docker).

run_oracle(instance, patch, sif) applies `patch` to /testbed inside a fresh writable-tmpfs instance of the
task image, runs the official eval script from the dataset, and grades the log with swebench's own
get_eval_report (same parser and rule as the official harness).

CLI (gate G1): python oracle.py <instance_id> <sif> <out_dir>   -> runs gold and empty patches.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
from swebench.harness.constants import TESTS_TIMEOUT
from swebench.harness.grading import get_eval_report
from swebench.harness.utils import make_test_spec

DATA = Path(__file__).resolve().parents[1] / "data/swe_bench_verified/data/test-00000-of-00001.parquet"


def load_instance(iid):
    d = pd.read_parquet(DATA)
    return d[d.instance_id == iid].iloc[0].to_dict()


def with_test_patch(inst, new_test_patch):
    """Instance whose grader applies `new_test_patch` instead of the original hidden tests. The dataset's precomputed
    `eval_script` embeds the original test patch and swebench ignores the `test_patch` column, so the text is replaced
    inside the script itself (asserted, so a silent no-op is impossible)."""
    old = inst["test_patch"]
    script = inst["eval_script"]
    assert old.strip() and old in script, "original test patch not found verbatim in eval_script"
    new = script.replace(old, new_test_patch)
    assert new != script or new_test_patch == old
    return dict(inst, test_patch=new_test_patch, eval_script=new)


def run_oracle(inst, patch, sif, log_path, timeout=3600, extra_setup=""):
    spec = make_test_spec(inst)
    with tempfile.TemporaryDirectory(dir="/share/gaise/qle3/apptainer_tmp") as td:
        td = Path(td)
        (td / "patch.diff").write_text(patch or "")
        (td / "eval.sh").write_text(spec.eval_script)
        apply = ("cd /testbed && if [ -s /work/patch.diff ]; then git apply -v /work/patch.diff || "
                 "patch --batch --fuzz=5 -p1 -i /work/patch.diff || echo '>>>>> Patch Apply Failed'; fi")
        cmd = ["apptainer", "exec", "--writable-tmpfs", "--containall", "--no-home", "--bind", f"{td}:/work",
               sif, "bash", "-lc", f"{extra_setup}\n{apply}\nbash /work/eval.sh"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)  # P3.19: agent output may hold non-UTF-8 bytes
            out, rc = p.stdout + "\n" + p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:  # P3.20: hung tests are unresolved, as in the official harness (TESTS_TIMEOUT marker)
            dec = lambda b: (b or b"").decode(errors="replace") if isinstance(b, bytes) else (b or "")
            out, rc = dec(e.stdout) + "\n" + dec(e.stderr) + f"\n{TESTS_TIMEOUT}\nTimeout error: {timeout} seconds exceeded.", "timeout"
        Path(log_path).write_text(out)
    pred = {"instance_id": inst["instance_id"], "model_name_or_path": "oracle", "model_patch": patch or ""}
    rep = get_eval_report(spec, pred, str(log_path), include_tests_status=True)
    return rep[inst["instance_id"]], rc


if __name__ == "__main__":
    iid, sif, out = sys.argv[1:4]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    inst = load_instance(iid)
    res = {}
    for name, patch in [("gold", inst["patch"]), ("empty", "")]:
        r, rc = run_oracle(inst, patch, sif, out / f"{iid}.{name}.log")
        res[name] = {"resolved": r.get("resolved"), "rc": rc, "applied": r.get("patch_successfully_applied"),
                     "tests_status": {k: {kk: len(vv) for kk, vv in v.items()} for k, v in r.get("tests_status", {}).items()}}
        print(name, json.dumps(res[name]), flush=True)
    (out / f"{iid}.oracle.json").write_text(json.dumps(res, indent=1))
