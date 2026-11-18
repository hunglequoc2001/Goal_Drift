"""Re-grade saved eval logs with the official grader to recover test-level status (needed for pilot attempts, whose
result.json stores only `resolved`). Reads only; writes <out_dir>/grades.csv. Runs in the exp03 env (swebench 5.0.2).
For C2 attempts the grader is built from the revised test patch, and the original-oracle log (if any) is graded too.
Usage: python regrade.py <results_root> <out_dir> [variants_full_dir]
"""
import glob
import json
import sys
from pathlib import Path

import pandas as pd
from swebench.harness.grading import get_eval_report
from swebench.harness.utils import make_test_spec
import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oracle import with_test_patch

DATA = Path(__file__).resolve().parents[2] / "data/swe_bench_verified/data/test-00000-of-00001.parquet"


def grade(inst, submission, log):
    spec = make_test_spec(inst)
    pred = {"instance_id": inst["instance_id"], "model_name_or_path": "x", "model_patch": submission or ""}
    rep = get_eval_report(spec, pred, str(log), include_tests_status=True)[inst["instance_id"]]
    ts = rep.get("tests_status") or {}
    f, p = ts.get("FAIL_TO_PASS", {}), ts.get("PASS_TO_PASS", {})
    return dict(resolved_regrade=bool(rep.get("resolved")),
                f2p_pass=len(f.get("success", [])), f2p_total=len(f.get("success", [])) + len(f.get("failure", [])),
                p2p_fail=len(p.get("failure", [])), p2p_total=len(p.get("success", [])) + len(p.get("failure", [])),
                f2p_passed_ids=json.dumps(sorted(f.get("success", []))), p2p_failed_ids=json.dumps(sorted(p.get("failure", []))))


def main(results_root, out_dir, variants_full=None):
    D = {r["instance_id"]: r for r in pd.read_parquet(DATA).to_dict("records")}
    rows = []
    for p in sorted(glob.glob(f"{results_root}/*/*.result.json")):
        res = json.loads(Path(p).read_text())
        base = p[:-len(".result.json")]
        sub = (json.loads(Path(base + ".traj.json").read_text()).get("info", {}) or {}).get("submission") or ""
        inst = D[res["instance_id"]]
        if res["variant"] == "C2":
            inst = with_test_patch(inst, (Path(variants_full) / res["instance_id"] / "C2.test.diff").read_text())
        rows.append(dict(run_id=res["run_id"], resolved=res["resolved"], **grade(inst, sub, base + ".eval.log")))
    G = pd.DataFrame(rows)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    G.to_csv(Path(out_dir) / "grades.csv", index=False)
    print(len(G), "graded; resolved mismatches:", int((G.resolved != G.resolved_regrade).sum()))


if __name__ == "__main__":
    main(*sys.argv[1:])
