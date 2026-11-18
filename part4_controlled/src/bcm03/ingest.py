"""Ingest Exp03 controlled-agent runs into one row per attempt plus one row per step.

Native schema (mini-swe-agent 1.1 trajectories): every assistant message carries its executed command in
extra.actions; the next user message is its observation (<returncode>..</returncode><output>..). Format-error
and exception messages from the harness are counted but are not steps. No text heuristics decide what a
step is, so there is no parser ambiguity of the kind found in Exp01/02.

Features: identical code to Exp02 (r2_ = BCM12 on role-aware steps with observation-based error flags,
r3_ = semantic-category features), so BCM is computed exactly as in the archival study.
Ground-truth behaviour (independent of BCM): edited files/functions from the submitted diff, overlap with
the gold patch's files, category sequence, test running, outcome from the executable oracle.

Usage: python -m bcm03.ingest <results/pilot> <out_dir>
"""
import glob
import json
import re
import sys
from pathlib import Path

import pandas as pd

from bcm_validity.features import compute_features
from bcm02.ingest import semantic_features
from bcm02.parse import semantic_category

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/swe_bench_verified/data/test-00000-of-00001.parquet"
FILE_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)
HUNK_RE = re.compile(r"^@@ [^@]* @@ ?(.*)$", re.M)
FUNC_RE = re.compile(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
RC_RE = re.compile(r"<returncode>(-?\d+)</returncode>")


def diff_targets(diff):
    """(modified existing files, new files, file::function targets) of a unified git diff."""
    mod, new, funcs = set(), set(), set()
    for block in re.split(r"(?=^diff --git )", diff or "", flags=re.M):
        m = FILE_RE.search(block)
        if not m:
            continue
        f = m.group(2)
        if re.search(r"^new file mode", block, re.M):
            new.add(f)
            continue
        mod.add(f)
        for ctx in HUNK_RE.findall(block):
            g = FUNC_RE.search(ctx)
            funcs.add(f"{f}::{g.group(1) if g else '<module>'}")
    return mod, new, funcs


def changed_lines(diff):
    return sum(1 for l in (diff or "").splitlines()
               if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))


def parse_traj(t):
    steps, obs = [], []
    msgs = t["messages"]
    n_format = n_exc = n_assistant = 0
    for i, m in enumerate(msgs):
        if m["role"] == "user" and i > 1:
            c = str(m.get("content") or "")
            n_format += c.startswith("Format error")
            n_exc += c.startswith("<exception>")
        if m["role"] != "assistant":
            continue
        n_assistant += 1
        acts = (m.get("extra") or {}).get("actions") or []
        nxt = next((msgs[j] for j in range(i + 1, len(msgs)) if msgs[j]["role"] in ("user", "exit")), None)
        o = str(nxt.get("content") or "") if nxt is not None else ""
        for a in acts:
            steps.append(str(a.get("command", "")).strip())
            obs.append(o)
    rcs = [int(m.group(1)) if (m := RC_RE.match(o)) else None for o in obs]
    return steps, obs, rcs, dict(n_assistant=n_assistant, n_format_errors=n_format, n_exceptions=n_exc)


def process(res_path, gold):
    res = json.loads(Path(res_path).read_text())
    rid = res["run_id"]
    tj = Path(res_path).with_name(rid + ".traj.json")
    t = json.loads(tj.read_text())
    steps, obs, rcs, diag = parse_traj(t)
    sub = t.get("info", {}).get("submission") or ""
    cats = [semantic_category(s) for s in steps]
    mod, new, funcs = diff_targets(sub)
    gfiles, _, gfuncs = diff_targets(gold[res["instance_id"]])
    row = dict(res, **diag, n_steps=len(steps), cat_seq="|".join(cats),
               edited_files="|".join(sorted(mod)), new_files="|".join(sorted(new)), edited_funcs="|".join(sorted(funcs)),
               n_changed_lines=changed_lines(sub), touches_gold_file=bool(mod & gfiles),
               gold_file_recall=len(mod & gfiles) / len(gfiles) if gfiles else float("nan"),
               ran_tests="test" in cats, nonzero_rc_frac=(sum(1 for r in rcs if r not in (0, None)) / len(rcs)) if rcs else 0.0,
               format_compliance=(len(steps) / (len(steps) + diag["n_format_errors"])) if steps or diag["n_format_errors"] else float("nan"))
    for k, v in compute_features(steps, obs).items():
        row["r2_" + k] = v
    row.update(semantic_features(cats))
    srows = [dict(run_id=rid, idx=i, category=c, action=s[:2000], returncode=r, obs_head=o[:300])
             for i, (s, o, r, c) in enumerate(zip(steps, obs, rcs, cats))]
    return row, srows


def main(results_dir, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    gold = pd.read_parquet(DATA, columns=["instance_id", "patch", "repo"])
    repo = dict(zip(gold.instance_id, gold.repo))
    gold = dict(zip(gold.instance_id, gold.patch))
    rows, steps = [], []
    for p in sorted(glob.glob(f"{results_dir}/*/*.result.json")):
        r, s = process(p, gold)
        rows.append(r)
        steps += s
    infra = [dict(run_id=Path(p).name.replace(".infra_fail.json", ""), model_dir=Path(p).parent.name)
             for p in sorted(glob.glob(f"{results_dir}/*/*.infra_fail.json"))]
    T = pd.DataFrame(rows)
    T["repo"] = T.instance_id.map(repo)
    T.to_parquet(out / "attempts.parquet")
    pd.DataFrame(steps).to_parquet(out / "steps.parquet")
    pd.DataFrame(infra, columns=["run_id", "model_dir"]).to_csv(out / "infra_failures.csv", index=False)
    print(f"{len(T)} attempts, {len(steps)} steps, {len(infra)} infra failures -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
