"""Re-run only the C2 part of validation (drafts already generated). Usage: validate_c2.py <iid> ..."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import validate_variants as V
for iid in sys.argv[1:]:
    d = V.ROOT / "data/variants_full" / iid
    v = json.loads((d / "validation.json").read_text())
    inst = V.load_instance(iid); sif = V.SIF.format(iid); logs = d / "logs"
    cached = {x["sample"]: x for x in v.get("C2_samples", []) if x.get("generator") or x.get("exec_check") or x.get("reason")}
    v["C2_samples"], v["C2_valid"] = [], False
    for f in sorted((d / "gen").glob("C2.s*.json"), key=lambda p: int(p.stem.split(".s")[1])):
        rec = json.loads(f.read_text()); k = rec["sample"]
        if k in cached and not cached[k].get("valid"):      # already evaluated and rejected: keep the verdict
            v["C2_samples"].append(cached[k]); continue
        r = V.c2_static(rec, inst); r["generator"] = rec.get("generator"); r["parent_sample"] = rec.get("parent_sample")
        g2 = t2 = None
        if r["valid"]:
            ex, g2, t2 = V.c2_exec(inst, rec, sif, logs)
            r.update(exec_check=ex, valid=ex["valid"])
            if not ex["valid"]: r["reason"] = ex.get("reason")
        v["C2_samples"].append(r)
        if r["valid"]:
            (d / "C2.txt").write_text(inst["problem_statement"].rstrip("\n") + "\n\nUpdate from the maintainers: " + rec["requirement"].strip() + "\n")
            (d / "C2.gold.diff").write_text(g2); (d / "C2.test.diff").write_text(t2)
            v.update(C2_valid=True, C2_selected_sample=rec["sample"], C2_summary=rec.get("summary"),
                     C2_needs_human_unambiguity_check=r["needs_human_unambiguity_check"]); break
    (d / "validation.json").write_text(json.dumps(v, indent=1))
    print(iid, "C2_valid", v["C2_valid"], flush=True)
