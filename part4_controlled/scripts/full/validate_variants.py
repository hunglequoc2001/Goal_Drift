"""Validate every variant of one task for the Exp03 full study (static + executable). One task per call; CPU only.

A  (G1)  gold patch resolves, empty patch does not (official eval script + swebench 5.0.2 grading).
B1       presentation-only rewrite (pilot procedure, scripts/make_variants.py): code blocks and identifier multiset identical.
C1       gold patch pre-applied and committed, issue unchanged: pre-patched + empty submission resolves.
B2       meaning-preserving prose rewrite drafted by the generator (gen_variants.py). Static checks, all pre-set:
         every placeholder exactly once (so code, identifiers, literals are byte-identical); no requirement-bearing token
         in the rewritten prose that is absent from A (nothing added); the prose really changed
         (word-sequence similarity <= 0.60) and its length is comparable (0.6-1.6x). The oracle is A's oracle (tests unchanged).
C2       changed requirement drafted by the generator. Static: edits only in files the gold/test patch touch, requirement
         paragraph present, no test names/paths in it, new test literals stated in it. Built with git inside the task image.
         Executable (all four required):
           (1) unchanged repo + revised tests        -> NOT resolved (the baseline fails),
           (2) revised gold + revised tests          -> resolved     (the new requirement is satisfiable),
           (3) ORIGINAL gold + revised tests         -> NOT resolved (the requirement really changed),
           (4) revised gold + ORIGINAL tests         -> recorded only (diagnostic: the two solutions are not interchangeable).
Samples are tried in index order and the first that passes everything is selected (no choice by hand).
Usage: python validate_variants.py <instance_id> [--skip-b2c2]
Writes data/variants_full/<iid>/{validation.json, B1.txt, B2.txt, C1.pre.diff, C2.txt, C2.gold.diff, C2.test.diff, logs/}.
"""
import difflib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_variants import b1, validate_b1  # noqa: E402  (pilot B1 procedure, unchanged)
from oracle import load_instance, run_oracle, with_test_patch  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from gen_variants import PH, PROTECT, FENCE, as_list  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SIF = "/share/gaise/qle3/sif/{}.sif"
TIMEOUT = 900
B2_MAX_SIM, B2_LEN = 0.60, (0.6, 1.6)
FILE_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)
LIT = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|\b\d+(?:\.\d+)?\b")

APPLY_EDITS = r'''
import json, sys
edits = json.load(open(sys.argv[1]))
ROOTDIR = sys.argv[2]
for e in edits:
    p = ROOTDIR + "/" + e["file"]
    s = open(p).read()
    n = s.count(e["search"])
    if n != 1:
        print("EDIT_FAIL %s count=%d" % (e["file"], n)); sys.exit(3)
    open(p, "w").write(s.replace(e["search"], e["replace"]))
print("EDITS_OK %d" % len(edits))
'''


def oracle(inst, patch, sif, log, **kw):
    """run_oracle with a hard timeout; a timed-out run counts as not resolved and is flagged."""
    try:
        rep, _ = run_oracle(inst, patch, sif, log, timeout=TIMEOUT, **kw)
        return bool(rep.get("resolved")), False
    except subprocess.TimeoutExpired:
        Path(log).write_text(f"TIMEOUT after {TIMEOUT}s")
        return False, True


def files_of(diff):
    return sorted({m.group(2) for m in FILE_RE.finditer(diff or "")})


def prose(masked):
    return re.findall(r"\w+", PH.sub(" ", masked).lower())


# ------------------------------------------------------------------ B2
def check_b2(rec, a_masked):
    r = dict(sample=rec["sample"], status=rec.get("status"), finish_reason=rec.get("finish_reason"))
    m = rec.get("rewrite_masked")
    if rec.get("status") != "generated" or not m or rec.get("finish_reason") != "stop":
        return dict(r, valid=False, reason="no complete rewrite")
    n = len(rec["spans"])
    got = Counter(int(x) for x in PH.findall(m))
    r["placeholders_exact"] = got == Counter(range(1, n + 1))
    r["stray_brackets"] = ("⟦" in PH.sub("", m)) or ("⟧" in PH.sub("", m))
    rest = PH.sub(" ", m)
    added = [x.group(0) for rx in [FENCE] + PROTECT for x in rx.finditer(rest)]
    r["new_protected_tokens"] = added[:20]
    pa, pb = prose(a_masked), prose(m)
    r["prose_similarity"] = round(difflib.SequenceMatcher(None, pa, pb, autojunk=False).ratio(), 3)
    r["prose_len_ratio"] = round(len(pb) / max(1, len(pa)), 3)
    r["valid"] = bool(r["placeholders_exact"] and not r["stray_brackets"] and not added
                      and r["prose_similarity"] <= B2_MAX_SIM and B2_LEN[0] <= r["prose_len_ratio"] <= B2_LEN[1])
    if not r["valid"]:
        r["reason"] = "; ".join(k for k, bad in [("placeholders", not r["placeholders_exact"]), ("brackets", r["stray_brackets"]),
                                                 ("new tokens", bool(added)), ("too similar", r["prose_similarity"] > B2_MAX_SIM),
                                                 ("length", not B2_LEN[0] <= r["prose_len_ratio"] <= B2_LEN[1])] if bad)
    return r


# ------------------------------------------------------------------ C2
def c2_static(rec, inst):
    r = dict(sample=rec["sample"], status=rec.get("status"), finish_reason=rec.get("finish_reason"))
    req, se, te = rec.get("requirement"), rec.get("source_edits") or [], rec.get("test_edits") or []
    if rec.get("status") != "generated" or not req or not se or not te:
        return dict(r, valid=False, reason="missing requirement or edits")
    gfiles, tfiles = set(files_of(inst["patch"])), set(files_of(inst["test_patch"]))
    r["source_files_ok"] = all(e["file"] in gfiles for e in se)
    r["test_files_ok"] = all(e["file"] in tfiles for e in te)
    r["req_chars"] = len(req)
    tnames = {re.split(r"[\s(:\[]", t.split("::")[-1])[0] for t in as_list(inst["FAIL_TO_PASS"]) + as_list(inst["PASS_TO_PASS"])}
    tnames = {t for t in tnames if t.startswith("test")}
    r["req_mentions_tests"] = bool(re.search(r"\btests?\b|\bunit test", req, re.I)) or any(t in req for t in tnames) \
        or any(Path(f).name in req for f in tfiles)
    new_lits = set()
    for e in te:
        new_lits |= set(LIT.findall(e["replace"])) - set(LIT.findall(e["search"])) - set(LIT.findall(inst["test_patch"]))
    norm = lambda s: s.strip("'\"")
    req_n = req.replace("`", "")
    r["new_test_literals"] = sorted(new_lits)[:20]
    r["new_literals_stated"] = all(norm(l) in req_n for l in new_lits)
    r["needs_human_unambiguity_check"] = not new_lits
    r["supersedes_clause"] = bool(re.search(r"supersed|instead of|replac|rather than|override", req, re.I))
    r["valid"] = bool(r["source_files_ok"] and r["test_files_ok"] and 40 <= len(req) <= 1500 and not r["req_mentions_tests"]
                      and r["new_literals_stated"])
    if not r["valid"]:
        r["reason"] = "; ".join(k for k, bad in [("source files", not r["source_files_ok"]), ("test files", not r["test_files_ok"]),
                                                 ("length", not 40 <= len(req) <= 1500), ("mentions tests", r["req_mentions_tests"]),
                                                 ("literals not stated", not r["new_literals_stated"])] if bad)
    return r


def build_c2(inst, rec, sif, logdir):
    """Apply gold patch (resp. test patch) + the drafted edits inside the image; git produces the revised diffs."""
    gfiles, tfiles = files_of(inst["patch"]), files_of(inst["test_patch"])
    with tempfile.TemporaryDirectory(dir="/share/gaise/qle3/apptainer_tmp") as td:
        td = Path(td)
        (td / "gold.diff").write_text(inst["patch"])
        (td / "test.diff").write_text(inst["test_patch"])
        (td / "src.json").write_text(json.dumps(rec["source_edits"]))
        (td / "tst.json").write_text(json.dumps(rec["test_edits"]))
        (td / "apply_edits.py").write_text(APPLY_EDITS)
        q = lambda fs: " ".join(f"'{f}'" for f in fs)
        sh = f"""set -e
PY=/opt/miniconda3/bin/python
cp -a /testbed /work/tb && cd /work/tb   # build on real disk: the image's writable tmpfs is only 64 MB
git apply /work/gold.diff
$PY /work/apply_edits.py /work/src.json /work/tb
git add -A -- {q(gfiles)}
git diff --cached -- {q(gfiles)} > /work/rev_gold.diff
git reset -q --hard
git apply /work/test.diff
$PY /work/apply_edits.py /work/tst.json /work/tb
git add -A -- {q(tfiles)}
git diff --cached -- {q(tfiles)} > /work/rev_test.diff
"""
        p = subprocess.run(["apptainer", "exec", "--writable-tmpfs", "--containall", "--no-home", "--bind", f"{td}:/work",
                            sif, "bash", "-lc", sh], capture_output=True, text=True, timeout=600)
        (logdir / f"C2.s{rec['sample']}.build.log").write_text(p.stdout + "\n" + p.stderr)
        if p.returncode != 0:
            return None, None, (p.stdout + p.stderr)[-500:]
        return (td / "rev_gold.diff").read_text(), (td / "rev_test.diff").read_text(), None


def c2_exec(inst, rec, sif, logdir):
    gold2, test2, err = build_c2(inst, rec, sif, logdir)
    if err:
        return dict(valid=False, reason=f"build failed: {err}"), None, None
    inst2 = with_test_patch(inst, test2)
    k = rec["sample"]
    res, tos = {}, []
    for name, ins, patch in [("base_revtests", inst2, ""), ("revgold_revtests", inst2, gold2),
                             ("gold_revtests", inst2, inst["patch"]), ("revgold_origtests", inst, gold2)]:
        res[name], to = oracle(ins, patch, sif, logdir / f"C2.s{k}.{name}.log")
        if to:
            tos.append(name)
    r = dict(exec=res, timeouts=tos, gold_diff_changed=gold2.strip() != inst["patch"].strip(), test_diff_changed=test2.strip() != inst["test_patch"].strip())
    r["valid"] = bool(not res["base_revtests"] and res["revgold_revtests"] and not res["gold_revtests"]
                      and r["gold_diff_changed"] and r["test_diff_changed"] and not tos)
    if not r["valid"]:
        r["reason"] = "exec: " + json.dumps(res)
    return r, gold2, test2


# ------------------------------------------------------------------ main
def main(iid, skip_b2c2=False):
    inst = load_instance(iid)
    d = ROOT / "data/variants_full" / iid
    logs = d / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    sif = SIF.format(iid)
    v = dict(instance_id=iid, sif=sif)
    if not Path(sif).exists():
        v["error"] = "SIF missing"
        (d / "validation.json").write_text(json.dumps(v, indent=1))
        print(iid, "SIF missing")
        return
    # A (G1)
    (v["A_gold_resolved"], to1), (v["A_empty_resolved"], to2) = (oracle(inst, inst["patch"], sif, logs / "A.gold.log"),
                                                                 oracle(inst, "", sif, logs / "A.empty.log"))
    v["A_timeout"] = to1 or to2
    v["A_valid"] = v["A_gold_resolved"] and not v["A_empty_resolved"] and not v["A_timeout"]
    # B1 (pilot procedure)
    bt = b1(inst["problem_statement"])
    (d / "B1.txt").write_text(bt)
    v["B1"] = validate_b1(inst["problem_statement"], bt)
    v["B1_valid"] = bool(v["B1"]["code_blocks_identical"] and v["B1"]["identifiers_identical"])
    # C1
    pre = inst["patch"]
    (d / "C1.pre.diff").write_text(pre)
    v["C1_valid"], _ = oracle(inst, "", sif, logs / "C1.validation.log",
                              extra_setup=f"cd /testbed && git apply <<'PREPATCH_EOF'\n{pre}\nPREPATCH_EOF")
    if not skip_b2c2 and v["A_valid"]:
        from gen_variants import mask
        a_masked, _ = mask(inst["problem_statement"])
        v["B2_samples"], v["B2_valid"] = [], False
        for f in sorted((d / "gen").glob("B2.s*.json")):
            rec = json.loads(f.read_text())
            r = check_b2(rec, a_masked)
            v["B2_samples"].append(r)
            if r["valid"]:
                (d / "B2.txt").write_text(rec["rewrite"].rstrip("\n") + "\n")
                v.update(B2_valid=True, B2_selected_sample=rec["sample"])
                break
        v["C2_samples"], v["C2_valid"] = [], False
        for f in sorted((d / "gen").glob("C2.s*.json")):
            rec = json.loads(f.read_text())
            r = c2_static(rec, inst)
            if r["valid"]:
                ex, gold2, test2 = c2_exec(inst, rec, sif, logs)
                r.update(exec_check=ex, valid=ex["valid"])
                if not ex["valid"]:
                    r["reason"] = ex.get("reason")
            v["C2_samples"].append(r)
            if r["valid"]:
                text = inst["problem_statement"].rstrip("\n") + "\n\nUpdate from the maintainers: " + rec["requirement"].strip() + "\n"
                (d / "C2.txt").write_text(text)
                (d / "C2.gold.diff").write_text(gold2)
                (d / "C2.test.diff").write_text(test2)
                v.update(C2_valid=True, C2_selected_sample=rec["sample"], C2_summary=rec.get("summary"),
                         C2_needs_human_unambiguity_check=r["needs_human_unambiguity_check"])
                break
    (d / "validation.json").write_text(json.dumps(v, indent=1))
    print(iid, json.dumps({k: v.get(k) for k in ["A_valid", "B1_valid", "C1_valid", "B2_valid", "C2_valid"]}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], "--skip-b2c2" in sys.argv)
