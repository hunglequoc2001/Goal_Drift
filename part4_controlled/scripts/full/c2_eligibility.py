"""Static eligibility for MECHANICAL C2 (changed observable literal), over all 500 Verified tasks.
A task is eligible if the gold patch ADDS a message-like string literal L (>= 2 words, 8-120 chars, no '%'-only/format-only,
not in any removed or context line of either patch) that the hidden tests assert: L (or the whole literal) occurs in an
ADDED test line that contains an assertion marker (assert*, raises, match=, ==, in ). One literal per task (the first
in file order). The literal must be unique in the added gold lines (occurs once) so a text substitution is unambiguous.
Writes configs/full/c2_eligible.csv (instance_id, repo, literal, gold_lines, test_lines, in_issue).
"""
import io, json, re, tokenize
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
ASSERT = re.compile(r"assert|raises|match\s*=|==|\bin\b|warns|pytest\.fail", re.I)
def lines(p, sign): return [l[1:] for l in p.splitlines() if l.startswith(sign) and not l.startswith(sign * 3)]
def ctx(p): return [l[1:] for l in p.splitlines() if l.startswith(" ")]
def strs(line):
    out = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(line.strip() + "\n").readline):
            if t.type == tokenize.STRING:
                m = re.match(r"^[rbufRBUF]*('''|\"\"\"|'|\")(.*)\1$", t.string, re.S)
                if m: out.append(m.group(2))
    except Exception: pass
    return out
def main():
    d = pd.read_parquet(ROOT / "data/swe_bench_verified/data/test-00000-of-00001.parquet")
    rows = []
    for r in d.itertuples():
        ga, gr, gc = lines(r.patch, "+"), lines(r.patch, "-"), ctx(r.patch)
        ta, tr, tc = lines(r.test_patch, "+"), lines(r.test_patch, "-"), ctx(r.test_patch)
        other = "\n".join(gr + gc + tr + tc)
        for i, gl in enumerate(ga):
            for s in strs(gl):
                if not (8 <= len(s) <= 120) or len(s.split()) < 2 or not re.search("[A-Za-z]{3}", s) or "\\" in s: continue
                if s in other or sum(s in x for x in ga) != 1: continue
                hit = [t for t in ta if s in t and ASSERT.search(t)]
                if hit:
                    rows.append(dict(instance_id=r.instance_id, repo=r.repo, difficulty=r.difficulty, literal=s,
                                     gold_lines=1, test_lines=len(hit), in_issue=s in r.problem_statement))
                    break
            else: continue
            break
    E = pd.DataFrame(rows)
    E.to_csv(ROOT / "configs/full/c2_eligible.csv", index=False)
    print(len(E), "eligible;", E.repo.value_counts().to_dict(), "in_issue", int(E.in_issue.sum()))
main()
