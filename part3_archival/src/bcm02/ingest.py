"""Ingest the downloaded SWE-bench Pro archive into one row per (run, instance).

Outputs (data/interim/):
  trajectories.parquet  metadata, outcome, per-representation BCM features (prefix r0_/r1_/r2_),
                        semantic-category features (r3_), parse diagnostics
  steps.parquet         role-aware steps (one row per step: run, instance, idx, tool, category,
                        action[:2000], obs_head[:500])
Usage: python -m bcm02.ingest [n_procs]
"""
import ast
import glob
import hashlib
import json
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from bcm_validity.features import FEATURES, compute_features   # Exp01 features (validated vs authors)
from .parse import CATEGORIES, author_all, author_smith, role_aware, semantic_category

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
RUNS = {  # folder -> cohort (RESEARCH_DECISIONS P2.1-P2.4)
    "gpt-5-250-turns-10132025": "primary_250",
    "claude-45sonnet-10132025": "primary_250",
    "claude-4sonnet-10132025": "primary_250",
    "claude-45haiku-10222025": "primary_250",
    "glm-4p5-10222025": "primary_250",
    "gemini-2-5-pro-preview-250-turns-debug-oct22": "primary_250",
    "gpt-5-high-paper": "paper_50",
    "gptoss-paper": "paper_50",
    "kimi-paper": "paper_50",
    "claude-opus-4-1-paper": "paper_100",
    "claude-sonnet-4-paper": "paper_100",
    "gemini-2-5-pro-preview-paper": "paper_100",
    "gpt-4o-paper": "paper_100",
}
CONFIG_KEYS = ["agent.model.name", "agent.model.per_instance_call_limit", "agent.model.per_instance_cost_limit",
               "agent.model.max_input_tokens", "agent.model.temperature", "agent.model.top_p",
               "agent.model.completion_kwargs", "agent.tools.parse_function.type"]


def _get(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def semantic_features(cats):
    n = len(cats)
    c = Counter(cats)
    f = {f"r3_frac_{k}": (c[k] / n if n else 0.0) for k in CATEGORIES}
    f["r3_n_steps"] = n
    first = {k: (cats.index(k) / n if k in cats else 1.0) for k in ["edit", "test", "run"]}
    f.update({f"r3_first_{k}_pos": v for k, v in first.items()})
    f["r3_n_category_switches"] = sum(a != b for a, b in zip(cats, cats[1:])) / n if n else 0.0
    return f


def process(path):
    run = path.split("/")[-4]
    inst = path.split("/")[-2]
    raw = open(path, "rb").read()
    t = json.loads(raw)
    rc = t["replay_config"]
    rc = json.loads(rc) if isinstance(rc, str) else rc
    h, info = t["history"], t.get("info", {})
    ms = info.get("model_stats") or {}
    if isinstance(ms, str):
        try:
            ms = ast.literal_eval(ms)
        except (ValueError, SyntaxError):
            ms = {}
    r0 = author_smith(h)
    r1 = author_all(h)
    ra = role_aware(h)
    cats = [semantic_category(s) for s in ra["steps"]]
    traj_actions = [x.get("action", "") for x in t.get("trajectory", [])]
    row = dict(run=run, cohort=RUNS[run], instance_id=inst, traj_sha256=hashlib.sha256(raw).hexdigest(),
               model=_get(rc, "agent.model.name"), exit_status=info.get("exit_status"),
               submission_nonempty=bool((info.get("submission") or "").strip()),
               swe_agent_version=info.get("swe_agent_version"), swe_rex_version=info.get("swe_rex_version"),
               api_calls=ms.get("api_calls"), instance_cost=ms.get("instance_cost"),
               tokens_sent=ms.get("tokens_sent"), tokens_received=ms.get("tokens_received"),
               n_history=len(h), n_traj_steps=len(traj_actions),
               n_traj_nonempty_actions=sum(1 for a in traj_actions if (a or "").strip()),
               n_action_msgs=ra["n_action_msgs"], n_harness_msgs=ra["n_harness_msgs"],
               n_multi_call_msgs=ra["n_multi_call_msgs"],
               frac_action_msgs_empty_content=float(np.mean([not (m.get("content") or "").strip() for m in h
                                                             if m.get("message_type") == "action"]) if ra["n_action_msgs"] else np.nan),
               r0_n=len(r0), r1_n=len(r1), r2_n=len(ra["steps"]))
    for k in CONFIG_KEYS:
        row["cfg." + k] = json.dumps(_get(rc, k), sort_keys=True)
    for prefix, steps, err in [("r0_", r0, None), ("r1_", r1, None), ("r2_", ra["steps"], ra["obs"])]:
        for k, v in compute_features(steps, err).items():
            row[prefix + k] = v
    row.update(semantic_features(cats))
    steps = [dict(run=run, instance_id=inst, idx=i, tool=tl, category=c, action=s[:2000], action_len=len(s),
                  obs_head=o[:500], obs_len=len(o))
             for i, (s, o, tl, c) in enumerate(zip(ra["steps"], ra["obs"], ra["tools"], cats))]
    return row, steps


def outcomes():
    v1 = pd.read_parquet(RAW / "_meta/swe_bench_pro_hf/data/v1/test-00000-of-00001.parquet").set_index("instance_id")
    rows = []
    for run in RUNS:
        for inst in v1.index:
            p = RAW / run / "eval" / inst / "_output.json"
            rec = dict(run=run, instance_id=inst, eval_file=p.exists())
            if p.exists():
                try:
                    o = json.load(open(p))
                    passed = {x["name"] for x in o.get("tests", []) if x.get("status") == "PASSED"}
                    need = set(eval(v1.loc[inst, "fail_to_pass"])) | set(eval(v1.loc[inst, "pass_to_pass"]))
                    rec.update(n_tests_reported=len(o.get("tests", [])), n_required=len(need),
                               resolved=need <= passed, eval_parse_ok=True)
                except Exception as e:  # corrupt output: keep, flag
                    rec.update(eval_parse_ok=False, eval_error=str(e)[:200], resolved=False)
            else:
                rec["resolved"] = False
            rows.append(rec)
    return pd.DataFrame(rows)


def main(nproc=32):
    out = ROOT / "data/interim"
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(f for r in RUNS for f in glob.glob(str(RAW / r / "traj" / "*" / "*.traj")))
    print("traj files", len(files), flush=True)
    rows, steps = [], []
    with Pool(nproc) as pool:
        for i, (row, st) in enumerate(pool.imap_unordered(process, files, chunksize=4)):
            rows.append(row)
            steps.extend(st)
            if i % 500 == 0:
                print(i, flush=True)
    T = pd.DataFrame(rows)
    O = outcomes()
    T = T.merge(O, on=["run", "instance_id"], how="left", validate="one_to_one")
    T["has_eval_row"] = T["eval_file"].notna()
    v1 = pd.read_parquet(RAW / "_meta/swe_bench_pro_hf/data/v1/test-00000-of-00001.parquet")
    meta = v1[["instance_id", "repo", "repo_language", "issue_specificity", "issue_categories"]].copy()
    meta["ref_patch_lines"] = v1.patch.str.count("\n")
    meta["ref_patch_files"] = v1.patch.str.count("diff --git")
    meta["n_fail_to_pass"] = v1.fail_to_pass.map(lambda s: len(eval(s)))
    meta["issue_specificity"] = meta.issue_specificity.astype(str)
    meta["issue_categories"] = meta.issue_categories.astype(str)
    T = T.merge(meta, on="instance_id", how="left")
    T["in_v1"] = T.repo.notna()
    T.to_parquet(out / "trajectories.parquet", index=False)
    O.to_parquet(out / "outcomes_all_v1.parquet", index=False)
    pd.DataFrame(steps).to_parquet(out / "steps.parquet", index=False)
    print(T.groupby("run").agg(n=("instance_id", "size"), resolved=("resolved", "mean")).round(3).to_string())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 32)
