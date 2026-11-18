"""Construct and validate pilot task variants.

B1 (task-preserving, presentation-only): neutral one-line framing + whitespace normalisation OUTSIDE code
   blocks (CRLF->LF, trailing spaces stripped, 3+ blank lines -> 2). Validation (static): every fenced/indented
   code block byte-identical; multiset of identifier-like tokens identical apart from the framing sentence.
C1 (task-changing, 'already fixed'): the gold source patch is pre-applied and committed; the issue text is
   unchanged. Validation (executable): with the pre-applied patch and an EMPTY agent submission, the oracle
   reports resolved (all FAIL_TO_PASS and PASS_TO_PASS pass). The correct decision is "no functional change needed";
   ground truth = tests still pass after the agent's patch (no regression) and the agent's patch size.
Writes data/variants/<iid>/{B1.txt, C1.pre.diff, validation.json}.
Usage: python make_variants.py configs/pilot_tasks.csv [--skip-exec]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from oracle import load_instance, run_oracle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRAME = "The following issue was reported by a user of the project.\n\n"
FENCE = re.compile(r"(```.*?```)", re.S)
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_\.]*")


def b1(text):
    parts = FENCE.split(text.replace("\r\n", "\n"))
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:          # code block: untouched
            out.append(p)
        else:
            p = "\n".join(l.rstrip() for l in p.split("\n"))
            p = re.sub(r"\n{3,}", "\n\n", p)
            out.append(p)
    return FRAME + "".join(out).strip("\n") + "\n"


def validate_b1(a, b):
    ca, cb = FENCE.findall(a.replace("\r\n", "\n")), FENCE.findall(b)
    ia = Counter(IDENT.findall(a))
    ib = Counter(IDENT.findall(b)) - Counter(IDENT.findall(FRAME))
    return dict(code_blocks_identical=ca == cb, n_code_blocks=len(ca), identifiers_identical=ia == ib,
                chars_a=len(a), chars_b=len(b))


def main(csv, skip_exec=False):
    tasks = pd.read_csv(csv)
    for iid in tasks.instance_id:
        inst = load_instance(iid)
        d = ROOT / "data/variants" / iid
        d.mkdir(parents=True, exist_ok=True)
        v = {}
        bt = b1(inst["problem_statement"])
        (d / "B1.txt").write_text(bt)
        v["B1"] = validate_b1(inst["problem_statement"], bt)
        (d / "C1.pre.diff").write_text(inst["patch"])
        if not skip_exec:
            sif = f"/share/gaise/qle3/sif/{iid}.sif"
            pre = inst["patch"]
            rep, rc = run_oracle(inst, "", sif, d / "C1.validation.log",
                                 extra_setup=f"cd /testbed && git apply <<'PREPATCH_EOF'\n{pre}\nPREPATCH_EOF")
            gold, _ = run_oracle(inst, inst["patch"], sif, d / "A.gold.log")
            empty, _ = run_oracle(inst, "", sif, d / "A.empty.log")
            v["A_gold_resolved"] = bool(gold.get("resolved"))
            v["A_empty_resolved"] = bool(empty.get("resolved"))
            v["C1_prepatched_empty_resolved"] = bool(rep.get("resolved"))
        v["B1_valid"] = v["B1"]["code_blocks_identical"] and v["B1"]["identifiers_identical"]
        v["C1_valid"] = v.get("C1_prepatched_empty_resolved")
        v["A_oracle_valid"] = v.get("A_gold_resolved") and not v.get("A_empty_resolved")
        (d / "validation.json").write_text(json.dumps(v, indent=1))
        print(iid, json.dumps({k: v.get(k) for k in ["A_oracle_valid", "B1_valid", "C1_valid"]}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], "--skip-exec" in sys.argv)
