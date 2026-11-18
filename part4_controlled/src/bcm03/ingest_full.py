"""Full-study ingest: bcm03.ingest rows (features, edits, sequences; unchanged) + task-grounded oracle detail.

Added per attempt:
  f2p_pass/f2p_total/p2p_fail/p2p_total  test-level status from the official grader (read from result.json when the
                                         full-study runner stored it, otherwise from <out_dir>/grades.csv written by
                                         scripts/full/regrade.py, which re-grades the saved eval log),
  resolved_orig_oracle                   C2 only: the submission graded by the ORIGINAL tests (persistence diagnostic),
  recognition_text                       assistant text says the problem is already solved (heuristic; C1 audit aid),
  context_overflow                       exit by ContextWindowExceededError,
  measures.attempt_measures columns      edited, scope, harmful, c1_class, c2_class.
Usage: python -m bcm03.ingest_full <results_root> <out_dir>
"""
import glob
import json
import sys
from pathlib import Path

import pandas as pd

from bcm03.ingest import DATA, diff_targets, process
from bcm03.measures import SEP, attempt_measures, claims_noop, patch_lines, recognition_evidence, sub_kind


STATUS = ["f2p_pass", "f2p_total", "p2p_fail", "p2p_total"]
IDS = ["f2p_passed_ids", "p2p_failed_ids"]


def main(results_root, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    D = pd.read_parquet(DATA)
    gold = dict(zip(D.instance_id, D.patch))
    repo = dict(zip(D.instance_id, D.repo))
    G = pd.read_csv(out / "grades.csv").set_index("run_id") if (out / "grades.csv").exists() else None
    rows, steps = [], []
    for p in sorted(glob.glob(f"{results_root}/*/*.result.json")):
        row, s = process(p, gold)
        row = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row.items()}   # parquet cannot store empty structs
        res = json.loads(Path(p).read_text())
        base = p[:-len(".result.json")]
        t = json.loads(Path(base + ".traj.json").read_text())
        if "f2p_total" in res:
            row.update({k: res[k] for k in STATUS + IDS if k in res})
        elif G is not None and res["run_id"] in G.index:
            row.update({k: int(G.loc[res["run_id"], k]) for k in STATUS})
            row.update({k: G.loc[res["run_id"], k] for k in IDS if k in G.columns})
        sub = (t.get("info") or {}).get("submission") or ""
        row["sub_kind"], row["sub_claims_noop"] = sub_kind(sub), claims_noop(sub) if sub_kind(sub) == "text" else False
        row["submitted"] = res.get("exit_status") == "Submitted"
        diff = (t.get("info") or {}).get("state_diff")
        row["src_patch_lines"] = SEP.join(sorted(patch_lines(diff if diff is not None else sub)))
        if "state_diff" in (t.get("info") or {}):          # full study: final repository state of the sandbox
            mod, new, funcs = diff_targets(t["info"]["state_diff"])
            row.update(state_files="|".join(sorted(mod)), state_new_files="|".join(sorted(new)), state_funcs="|".join(sorted(funcs)))
            row["resolved_state"] = res.get("resolved_state")
        row["resolved_orig_oracle"] = res.get("resolved_orig_oracle")
        row["recognition_text"] = recognition_evidence(t["messages"])
        row["context_overflow"] = res.get("exit_status") == "ContextWindowExceededError"
        row["oracle_kind"] = res.get("oracle_kind", "original")
        rows.append(row)
        steps += s
    T = pd.DataFrame(rows)
    T["repo"] = T.instance_id.map(repo)
    gfiles = {i: diff_targets(g)[0] for i, g in gold.items()}
    T = attempt_measures(T, gfiles)
    infra = [dict(run_id=Path(p).name.replace(".infra_fail.json", ""), model_dir=Path(p).parent.name)
             for p in sorted(glob.glob(f"{results_root}/*/*.infra_fail.json"))]
    T.to_parquet(out / "attempts.parquet")
    pd.DataFrame(steps).to_parquet(out / "steps.parquet")
    pd.DataFrame(infra, columns=["run_id", "model_dir"]).to_csv(out / "infra_failures.csv", index=False)
    print(f"{len(T)} attempts, {len(steps)} steps, {len(infra)} infra failures -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
