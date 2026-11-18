"""Draft B2 (strong task-preserving) and C2 (changed-requirement) variants with a local open-weight generator.

Generator: GLM-4-32B-0414 (MIT licence), served by vLLM on university GPUs. It is NOT one of the evaluated agents, so no
agent is tested on text its own weights wrote. Drafts are only candidates: every draft must pass
scripts/full/validate_variants.py (static + executable checks) before it can enter the study. The model's output is never
treated as validation evidence or as a human judgement.

B2 = meaning-preserving rewrite of the issue prose. Before the model sees the issue, every requirement-bearing span is
replaced by an opaque placeholder: fenced/indented code, tracebacks, inline code, URLs, file paths, dotted/underscored/
CamelCase identifiers, calls, numbers and quoted strings. The model rewrites the remaining prose (register, sentence
structure, paragraph order) and must keep every placeholder exactly once; the placeholders are then restored byte-for-byte.
So code, identifiers and literals are identical by construction, and the validator checks the prose really changed.

C2 = an explicit, testable change of the required behaviour. Given the issue, the gold patch, the hidden test patch and
the FAIL_TO_PASS tests, the model proposes (i) a requirement paragraph that is appended to the issue, (ii) search/replace
edits on top of the gold patch (the revised reference solution) and (iii) search/replace edits on top of the test patch
(the revised oracle). The validator builds both revised patches with git inside the task image and checks
executable conditions (see validate_variants.py).

Usage: python gen_variants.py <api_base> <served_name> <tasks_csv> <out_root> [n_samples=3] [kinds=B2,C2]
Writes <out_root>/<iid>/gen/{B2,C2}.s<k>.json (prompt hash, raw response, parsed fields, sampling settings).
"""
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/swe_bench_verified/data/test-00000-of-00001.parquet"
MAX_PROMPT_CHARS = 60000      # ~20k tokens: leaves room for the answer within a 32k context

def as_list(x):
    """FAIL_TO_PASS / PASS_TO_PASS are JSON strings in some dataset copies and arrays in others."""
    return list(json.loads(x)) if isinstance(x, str) else list(x)


# ------------------------------------------------------------------ B2 masking
FENCE = re.compile(r"```.*?```", re.S)
PROTECT = [
    re.compile(r"(?m)^(?: {4}|\t).*(?:\n(?: {4}|\t).*)*"),                       # indented code block
    re.compile(r"(?m)^(?:>>>|\.\.\.|\$ |In \[\d+\]:|Out\[\d+\]:).*$"),          # REPL / shell lines
    re.compile(r"(?ms)^Traceback \(most recent call last\):.*?(?=\n\s*\n|\Z)"),  # traceback
    re.compile(r"`[^`\n]+`"),                                                   # inline code
    re.compile(r"https?://\S+"),                                                # URLs
    re.compile(r"\"[^\"\n]{1,200}\"|'[^'\n]{1,200}'(?![a-z])"),               # quoted strings
    re.compile(r"(?<![\w/])(?:[\w.-]+/)+[\w.-]+"),                             # paths
    re.compile(r"\b[A-Za-z_][\w]*(?:\.[A-Za-z_]\w*)+(?:\(\))?"),                 # dotted names
    re.compile(r"\b[A-Za-z_]\w*\([^()\n]{0,80}\)"),                             # calls
    re.compile(r"\b\w*_\w*\b"),                                                 # underscored identifiers
    re.compile(r"\b[a-z]+[A-Z]\w*\b|\b[A-Z][a-z0-9]+[A-Z]\w*\b"),                # camelCase / CamelCase
    re.compile(r"\b[0-9a-f]{7,40}\b"),                                           # commit hashes
    re.compile(r"\b\d+(?:\.\d+)*\b"),                                           # numbers / versions
]
PH = re.compile(r"⟦P(\d+)⟧")


def mask(text):
    """Replace requirement-bearing spans by ⟦Pk⟧; return masked text and the span table."""
    spans = []

    def sub(m):   # a span that swallowed earlier placeholders is stored as the original text it covers
        spans.append(PH.sub(lambda q: spans[int(q.group(1)) - 1], m.group(0)))
        return f"⟦P{len(spans)}⟧"
    t = FENCE.sub(sub, text.replace("\r\n", "\n"))
    for rx in PROTECT:
        t = rx.sub(sub, t)
    # renumber the top-level placeholders in reading order
    order = [int(i) for i in PH.findall(t)]
    t = PH.sub(lambda m: f"⟦Q{order.index(int(m.group(1))) + 1}⟧", t).replace("⟦Q", "⟦P")
    return t, [spans[i - 1] for i in order]


def unmask(text, spans):
    for i in range(len(spans), 0, -1):   # longest index first so P1 does not match P10
        text = text.replace(f"⟦P{i}⟧", spans[i - 1])
    return text


B2_PROMPT = """You are rewriting a software bug report so that it says exactly the same thing in different words.

The report below contains placeholders of the form ⟦P1⟧, ⟦P2⟧, ... Each placeholder stands for code, an identifier, a
file name, a number, a URL or a quoted string. Rules:
1. Keep EVERY placeholder exactly once, unchanged (same number, same brackets). Do not add new placeholders.
2. Rewrite all other text substantially: change sentence structure, wording and register; you may reorder paragraphs or
   sentences (for example, put the expected behaviour before the observed behaviour) as long as the meaning is unchanged.
3. Do not add any information, hint, diagnosis or suggested fix that is not already in the report. Do not remove any
   information, requirement, example or detail.
4. Keep it a bug report written by a user of the project. Plain text or Markdown only.
Return only the rewritten report between <rewrite> and </rewrite>.

<report>
{masked}
</report>"""

C2_PROMPT = """You are helping build a benchmark that tests whether a coding agent follows a CHANGED requirement.

Below are a GitHub issue, the reference fix (gold patch) and the hidden tests that check the fix (test patch).
Design ONE small, natural change to the required behaviour such that:
  (a) the change is stated explicitly and unambiguously in a short paragraph that will be appended to the issue as an
      update from the maintainers; a developer who reads only the issue plus that paragraph must know exactly what to do;
  (b) the original gold patch would then be WRONG (at least one hidden test of the listed FAIL_TO_PASS tests, revised
      by you, fails on it), while the revised gold patch passes all revised tests;
  (c) the revised solution changes only files that the gold patch already changes, and stays a plausible design choice
      for this project (e.g. a different exception type or message, a different return value, format or default,
      inclusive instead of exclusive bounds, a different keyword name, warning instead of error);
  (d) the paragraph does not mention tests, test names, file names of tests, or the gold patch, and does not contain code
      of the solution beyond the exact names/values the new behaviour requires;
  (e) the paragraph explicitly says that it supersedes any conflicting expectation in the issue.
Edits are search/replace operations applied AFTER the original patch has been applied. Copy every <search> text exactly
from lines shown in the patch (without the leading '+', '-' or ' ' diff marker); each <search> must occur exactly once
in the patched file. Do not rename, add or remove test functions; only change what the listed tests expect.

Answer in exactly this format:
<summary>one sentence describing the change</summary>
<requirement>the paragraph to append to the issue</requirement>
<source_edit file="path/in/repo.py"><search>...</search><replace>...</replace></source_edit>
(one or more source_edit blocks)
<test_edit file="path/to/test_file.py"><search>...</search><replace>...</replace></test_edit>
(one or more test_edit blocks)

<issue>
{issue}
</issue>

<gold_patch>
{patch}
</gold_patch>

<test_patch>
{test_patch}
</test_patch>

<fail_to_pass_tests>
{f2p}
</fail_to_pass_tests>"""

TAG = lambda t: re.compile(rf"<{t}>(.*?)</{t}>", re.S)
EDIT = re.compile(r'<(source_edit|test_edit) file="([^"]+)">\s*<search>(.*?)</search>\s*<replace>(.*?)</replace>\s*</\1>', re.S)


def parse_c2(txt):
    s, r = TAG("summary").search(txt), TAG("requirement").search(txt)
    edits = [dict(kind=k, file=f, search=a.strip("\n"), replace=b.strip("\n")) for k, f, a, b in EDIT.findall(txt)]
    return dict(summary=s.group(1).strip() if s else None, requirement=r.group(1).strip() if r else None,
                source_edits=[e for e in edits if e["kind"] == "source_edit"],
                test_edits=[e for e in edits if e["kind"] == "test_edit"])


def one(client, name, kind, inst, k, out):
    k = k + int(os.environ.get("GEN_OFFSET", 0))      # sample index offset keeps generators' drafts apart
    f = out / inst["instance_id"] / "gen" / f"{kind}.s{k}.json"
    if f.exists():
        return f.name, "exists"
    f.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(instance_id=inst["instance_id"], kind=kind, sample=k, generator=name, temperature=0.7, top_p=0.95, seed=k)
    if kind == "B2":
        masked, spans = mask(inst["problem_statement"])
        prompt = B2_PROMPT.format(masked=masked)
        rec.update(masked=masked, spans=spans)
        max_tokens = 4096
    else:
        f2p = "\n".join(as_list(inst["FAIL_TO_PASS"]))
        prompt = C2_PROMPT.format(issue=inst["problem_statement"], patch=inst["patch"], test_patch=inst["test_patch"], f2p=f2p)
        max_tokens = int(os.environ.get("GEN_MAXTOK", 4096))
    rec["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
    if len(prompt) > MAX_PROMPT_CHARS:
        rec.update(status="skipped_prompt_too_long", prompt_chars=len(prompt))
        f.write_text(json.dumps(rec, indent=1))
        return f.name, rec["status"]
    try:
        r = client.chat.completions.create(model=name, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens,
                                           temperature=0.7, top_p=0.95, seed=k,
                                           extra_body=json.loads(os.environ.get("GEN_BODY", "{}")))
        txt = r.choices[0].message.content or ""
        rec.update(raw=txt, finish_reason=r.choices[0].finish_reason, usage=r.usage.model_dump() if r.usage else None)
    except Exception as e:
        rec.update(status="error", error=f"{type(e).__name__}: {str(e)[:500]}")
        f.write_text(json.dumps(rec, indent=1))
        return f.name, rec["status"]
    if kind == "B2":
        m = TAG("rewrite").search(txt)
        rec["rewrite_masked"] = m.group(1).strip("\n") if m else None
        rec["rewrite"] = unmask(rec["rewrite_masked"], rec["spans"]) if m else None
    else:
        rec.update(parse_c2(txt))
    rec["status"] = "generated"
    f.write_text(json.dumps(rec, indent=1))
    return f.name, rec["status"]


def main(api, name, tasks_csv, out_root, n_samples=3, kinds="B2,C2"):
    client = OpenAI(base_url=api, api_key="EMPTY", timeout=900)
    D = pd.read_parquet(DATA).set_index("instance_id", drop=False)
    ids = list(pd.read_csv(tasks_csv).instance_id)
    out = Path(out_root)
    jobs = [(kind, D.loc[i].to_dict(), k) for i in ids for kind in kinds.split(",") for k in range(int(n_samples))]
    print(f"{len(jobs)} generations for {len(ids)} tasks", flush=True)
    with ThreadPoolExecutor(24) as ex:
        for r in ex.map(lambda j: one(client, name, j[0], j[1], j[2], out), jobs):
            print(*r, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
