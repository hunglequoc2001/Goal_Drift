"""AI-assisted independent review of accepted B2 / C2 variants (NOT human validation).

Reviewer = a local open-weight model from a different family than the drafters (drafters: GLM-4-32B, gpt-oss-120b).
Two passes per item with the two texts in opposite order (position-bias check). Each pass returns JSON with a verdict per
question, short evidence quotes, a reasoning string and a confidence in [0,1]. Items where the passes disagree, or any
verdict is a failure, or confidence < 0.7, go to the priority list for the human spot-check.
Output: data/variants_full/<iid>/review/<B2|C2>.p<k>.json
Usage: python review_ai.py <api_base> <served_name> <tasks_csv> [kinds=B2,C2]
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
VF = ROOT / "data/variants_full"
D = pd.read_parquet(ROOT / "data/swe_bench_verified/data/test-00000-of-00001.parquet").set_index("instance_id", drop=False)

B2_Q = """You are auditing a rewritten software bug report. Text A and Text B are two versions of the same issue.
One of them is the original and one is a rewrite whose code, identifiers and quoted strings were kept byte-identical.
Judge ONLY whether a developer would implement the same fix from either text.
Answer as JSON: {"same_requirements": "yes|no|unclear", "information_added": "none|hint|other", "information_removed": "none|detail|other",
"natural": "yes|no", "evidence": ["short quotes"], "reasoning": "2-4 sentences", "confidence": 0.0-1.0}
"hint" = the rewrite adds a diagnosis or fix suggestion not in the original. "detail" = the rewrite loses an expected or observed
behaviour, a condition or a step."""

C2_Q = """You are auditing a benchmark variant. An original GitHub issue was extended with a maintainer update that CHANGES the
required behaviour. You see the issue, the update, the original reference fix and tests, and the revised reference fix and tests.
Answer as JSON: {"change_meaningful": "yes|trivial|no", "requirement_unambiguous": "yes|no|unclear",
"tests_match_requirement": "yes|no|unclear", "revised_fix_correct": "yes|no|unclear", "artificial": "yes|no",
"evidence": ["short quotes or diff hunks"], "reasoning": "3-6 sentences", "confidence": 0.0-1.0}
change_meaningful: yes = a real, plausible design decision a maintainer could make; trivial = cosmetic (rename, whitespace);
no = nonsense or contradicts the issue. requirement_unambiguous: yes only if one reasonable implementation satisfies the update.
tests_match_requirement: yes only if the revised tests check exactly what the update says and nothing hidden.
artificial: yes if the change looks manipulated just to make tests fail on the original fix."""


def ask(client, name, prompt, k):
    r = client.chat.completions.create(model=name, messages=[{"role": "user", "content": prompt}], max_tokens=1500,
                                       temperature=0.0, seed=k)
    t = r.choices[0].message.content or ""
    m = re.search(r"\{.*\}", t, re.S)
    try:
        return json.loads(m.group(0)), t
    except Exception:
        return None, t


def one(client, name, iid, kind, p):
    out = VF / iid / "review" / f"{kind}.p{p}.json"
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    d = VF / iid
    inst = D.loc[iid]
    if kind == "B2":
        a, b = inst.problem_statement, (d / "B2.txt").read_text()
        if p == 1:
            a, b = b, a
        prompt = f"{B2_Q}\n\n<text_A>\n{a}\n</text_A>\n\n<text_B>\n{b}\n</text_B>"
    else:
        req = (d / "C2.txt").read_text().split("Update from the maintainers:")[-1].strip()
        parts = [("issue", inst.problem_statement), ("maintainer_update", req), ("original_fix", inst.patch),
                 ("original_tests", inst.test_patch), ("revised_fix", (d / "C2.gold.diff").read_text()),
                 ("revised_tests", (d / "C2.test.diff").read_text())]
        if p == 1:
            parts = parts[:2] + parts[4:] + parts[2:4]
        prompt = C2_Q + "".join(f"\n\n<{n}>\n{t[:12000]}\n</{n}>" for n, t in parts)
    js, raw = ask(client, name, prompt, p)
    out.write_text(json.dumps(dict(instance_id=iid, kind=kind, pass_=p, reviewer=name, parsed=js, raw=raw), indent=1))


def main(api, name, tasks_csv, kinds="B2,C2"):
    client = OpenAI(base_url=api, api_key="EMPTY", timeout=600)
    jobs = []
    for iid in pd.read_csv(tasks_csv).instance_id:
        f = VF / iid / "validation.json"
        v = json.loads(f.read_text()) if f.exists() else {}
        for kind in kinds.split(","):
            if v.get(f"{kind}_valid"):
                jobs += [(iid, kind, p) for p in (0, 1)]
    print(len(jobs), "review passes", flush=True)
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(lambda j: one(client, name, *j), jobs))
    print("done", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
