"""Targeted revision of REJECTED C2 drafts (acceptance criteria unchanged; see validate_variants.py).

Two modes.
  prep <tasks_csv>              CPU, in the task image: for every file touched by a rejected draft's edits, save the
                                post-patch text around the edit sites (gold applied for source files, test patch applied
                                for test files), so the drafter can copy search strings exactly -> variants_full/<iid>/ctx/*.json
  gen <api> <name> <tasks_csv> [round]
                                GPU: for each rejected task, take up to 2 rejected drafts (priority: executable failures, then
                                unstated literals, then edit failures, then unparsable), show the model its draft plus the
                                machine-measured failure (and file excerpts / test-log tails), and ask for a corrected draft.
                                Output: C2.s<100*round+k>.json (generator + parent sample recorded).
A repaired draft goes through exactly the same static + executable acceptance as a first draft. No human edits.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gen_variants import C2_PROMPT, EDIT, TAG, parse_c2, as_list  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
VF = ROOT / "data/variants_full"
CTX_LINES = 60


def reason_class(s):
    r = str(s.get("reason", ""))
    ex = (s.get("exec_check") or {}).get("exec")
    if ex:
        return "exec"
    if "EDIT_FAIL" in r or "build failed" in r:
        return "edit_fail"
    if "literals" in r:
        return "literal"
    if "mentions tests" in r:
        return "mentions_tests"
    return "unparsable"


PRIORITY = ["exec", "literal", "mentions_tests", "edit_fail", "unparsable"]


def pick(v, n=2):
    c = [s for s in v.get("C2_samples", []) if not s.get("valid")]
    c.sort(key=lambda s: (PRIORITY.index(reason_class(s)), s["sample"]))
    return c[:n]


# ------------------------------------------------------------------ prep (CPU)
def prep(tasks):
    for iid in tasks:
        d = VF / iid
        v = json.loads((d / "validation.json").read_text()) if (d / "validation.json").exists() else {}
        if v.get("C2_valid") or not v.get("A_valid"):
            continue
        files = {}
        for s in pick(v):
            rec = json.loads((d / "gen" / f"C2.s{s['sample']}.json").read_text())
            for e in (rec.get("source_edits") or []) + (rec.get("test_edits") or []):
                files[e["file"]] = e["kind"]
        if not files or (d / "ctx.json").exists():
            continue
        from oracle import load_instance
        inst = load_instance(iid)
        with tempfile.TemporaryDirectory(dir="/share/gaise/qle3/apptainer_tmp") as td:
            td = Path(td)
            (td / "gold.diff").write_text(inst["patch"])
            (td / "test.diff").write_text(inst["test_patch"])
            (td / "files.json").write_text(json.dumps(files))
            (td / "dump.py").write_text(
                "import json,subprocess\nF=json.load(open('/work/files.json'));out={}\n"
                "for f,k in F.items():\n"
                "    try: out[f]=open('/work/tb/'+f).read()\n"
                "    except Exception as e: out[f]=None\n"
                "json.dump(out,open('/work/ctx_full.json','w'))\n")
            sh = ("cp -a /testbed /work/tb && cd /work/tb && git apply /work/gold.diff && git apply /work/test.diff && "
                  "/opt/miniconda3/bin/python /work/dump.py")
            subprocess.run(["apptainer", "exec", "--writable-tmpfs", "--containall", "--no-home", "--bind", f"{td}:/work",
                            f"/share/gaise/qle3/sif/{iid}.sif", "bash", "-lc", sh], capture_output=True, text=True, timeout=600)
            full = json.loads((td / "ctx_full.json").read_text()) if (td / "ctx_full.json").exists() else {}
        # excerpts: +-CTX_LINES around every hunk of the (gold|test) patch in that file, else file head
        ex = {}
        for f, txt in full.items():
            if txt is None:
                continue
            lines = txt.splitlines()
            patch = inst["patch"] if files[f] == "source_edit" else inst["test_patch"]
            blk = re.search(rf"diff --git a/{re.escape(f)} b/.*?(?=^diff --git |\Z)", patch, re.S | re.M)
            starts = [int(m) for m in re.findall(r"^@@ -\d+(?:,\d+)? \+(\d+)", blk.group(0), re.M)] if blk else [1]
            keep = set()
            for st in starts:
                keep |= set(range(max(0, st - CTX_LINES), min(len(lines), st + CTX_LINES)))
            ex[f] = "\n".join(lines[i] for i in sorted(keep))[:14000]
        (d / "ctx.json").write_text(json.dumps(ex))
        print("ctx", iid, list(ex), flush=True)


# ------------------------------------------------------------------ gen (GPU)
def feedback(iid, s, rec):
    d = VF / iid
    c = reason_class(s)
    if c == "exec":
        ex = s["exec_check"]["exec"]
        msgs = []
        if ex["base_revtests"]:
            msgs.append("With the UNCHANGED repository your revised tests already PASS, so they do not check the new behaviour. "
                        "Edit the tests so that they assert the new behaviour and therefore fail without your source change.")
        if not ex["revgold_revtests"]:
            tail = ""
            lg = d / "logs" / f"C2.s{s['sample']}.revgold_revtests.log"
            if lg.exists():
                t = lg.read_text(errors="replace").splitlines()
                tail = "\n".join(t[-35:])[-3500:]
            msgs.append("With your revised reference fix the revised tests FAIL. The last lines of the test run were:\n" + tail)
        if ex["gold_revtests"]:
            msgs.append("The ORIGINAL reference fix also passes your revised tests, so the requirement did not really change. "
                        "The revised tests must FAIL on the original reference fix.")
        return "\n\n".join(msgs)
    if c == "literal":
        return ("Your update paragraph does not state these literals that your revised tests introduce: "
                + json.dumps(s.get("new_test_literals")) + ". The paragraph must state every new literal value exactly.")
    if c == "mentions_tests":
        return "The update paragraph must not mention tests, test names or test files. Describe only the required behaviour."
    if c == "edit_fail":
        return ("One of your <search> texts was not found exactly once in the patched file (" + str(s.get("reason"))[:300] +
                "). Copy each <search> verbatim from the file excerpts below, including indentation, and make it unique.")
    return "Your answer could not be parsed. Use exactly the requested tags: summary, requirement, source_edit(s), test_edit(s)."


def one(client, name, iid, s, k, rnd):
    d = VF / iid
    out = d / "gen" / f"C2.s{100 * rnd + k}.json"
    if out.exists():
        return
    inst = pd.read_parquet(ROOT / "data/swe_bench_verified/data/test-00000-of-00001.parquet").set_index("instance_id").loc[iid]
    parent = json.loads((d / "gen" / f"C2.s{s['sample']}.json").read_text())
    ctx = json.loads((d / "ctx.json").read_text()) if (d / "ctx.json").exists() else {}
    base = C2_PROMPT.format(issue=inst.problem_statement, patch=inst.patch, test_patch=inst.test_patch,
                            f2p="\n".join(as_list(inst.FAIL_TO_PASS)))
    prev = parent.get("raw") or ""
    cx = "".join(f'\n<file_after_patches path="{f}">\n{t}\n</file_after_patches>' for f, t in ctx.items())
    prompt = (base + "\n\nYOUR PREVIOUS ANSWER WAS REJECTED BY AUTOMATIC CHECKS.\n<previous_answer>\n" + prev[-6000:] +
              "\n</previous_answer>\n<check_result>\n" + feedback(iid, s, parent) + "\n</check_result>" + cx +
              "\n\nProduce a corrected full answer in the same format. Keep the change meaningful, natural and unambiguous; do not weaken it.")
    rec = dict(instance_id=iid, kind="C2", sample=100 * rnd + k, parent_sample=s["sample"], round=rnd, generator=name,
               failure_class=reason_class(s), prompt_chars=len(prompt))
    if len(prompt) > 90000:
        rec["status"] = "skipped_prompt_too_long"
    else:
        try:
            r = client.chat.completions.create(model=name, messages=[{"role": "user", "content": prompt}], max_tokens=int(os.environ.get("GEN_MAXTOK", 16000)),
                                               temperature=0.7, top_p=0.95, seed=100 * rnd + k,
                                               extra_body=json.loads(os.environ.get("GEN_BODY", "{}")))
            txt = r.choices[0].message.content or ""
            rec.update(raw=txt, finish_reason=r.choices[0].finish_reason, status="generated", **parse_c2(txt))
        except Exception as e:
            rec.update(status="error", error=f"{type(e).__name__}: {str(e)[:300]}")
    out.write_text(json.dumps(rec, indent=1))


def gen(api, name, tasks_csv, rnd=1):
    from openai import OpenAI
    client = OpenAI(base_url=api, api_key="EMPTY", timeout=1200)
    jobs = []
    for iid in pd.read_csv(tasks_csv).instance_id:
        f = VF / iid / "validation.json"
        v = json.loads(f.read_text()) if f.exists() else {}
        if v.get("C2_valid") or not v.get("A_valid"):
            continue
        for k, s in enumerate(pick(v)):
            jobs.append((iid, s, k, int(rnd)))
    print(len(jobs), "repair drafts", flush=True)
    with ThreadPoolExecutor(12) as ex:
        list(ex.map(lambda j: one(client, name, *j), jobs))


if __name__ == "__main__":
    if sys.argv[1] == "prep":
        prep(list(pd.read_csv(sys.argv[2]).instance_id))
    else:
        gen(*sys.argv[2:])
