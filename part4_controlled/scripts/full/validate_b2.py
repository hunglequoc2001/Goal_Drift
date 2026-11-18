"""Re-check B2 drafts (static checks only; no oracle needed). First passing sample in index order is selected."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import validate_variants as V
from gen_variants import mask
n = 0
for d in sorted((V.ROOT / "data/variants_full").glob("*")):
    f = d / "validation.json"
    if not f.exists(): continue
    v = json.loads(f.read_text())
    if not v.get("A_valid"): continue
    inst = V.load_instance(d.name); a_masked, _ = mask(inst["problem_statement"])
    v["B2_samples"], v["B2_valid"] = [], False; v.pop("B2_selected_sample", None)
    for g in sorted((d / "gen").glob("B2.s*.json"), key=lambda p: int(p.stem.split(".s")[1])):
        rec = json.loads(g.read_text()); r = V.check_b2(rec, a_masked); r["generator"] = rec.get("generator")
        v["B2_samples"].append(r)
        if r["valid"]:
            (d / "B2.txt").write_text(rec["rewrite"].rstrip("\n") + "\n"); v.update(B2_valid=True, B2_selected_sample=rec["sample"]); break
    f.write_text(json.dumps(v, indent=1)); n += v["B2_valid"]
print("B2 valid:", n)
