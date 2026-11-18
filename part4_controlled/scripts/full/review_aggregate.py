"""Aggregate AI reviews (review_ai.py) into
  human_review/<part>/sheet_ai_review.csv   completed AI-assisted sheet (columns prefixed ai_), kept SEPARATE from the
                                            empty human sheet.csv (never filled by AI; never labelled human-verified)
  human_review/PRIORITY_SPOTCHECK.csv       items for the human spot-check, with reasons
Priority reasons: the two passes disagree on any verdict; any verdict is a failure (B2: not same_requirements / hint /
detail / unnatural; C2: not meaningful / ambiguous / tests mismatch / fix incorrect / artificial); min confidence < 0.7;
unparsable review; C2 whose automatic check flagged `needs_human_unambiguity_check`.
Usage: python review_aggregate.py
"""
import json
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]; VF = ROOT / "data/variants_full"; OUT = ROOT.parent / "human_review"
Q = {"B2": ["same_requirements", "information_added", "information_removed", "natural"],
     "C2": ["change_meaningful", "requirement_unambiguous", "tests_match_requirement", "revised_fix_correct", "artificial"]}
GOOD = {"same_requirements": "yes", "information_added": "none", "information_removed": "none", "natural": "yes",
        "change_meaningful": "yes", "requirement_unambiguous": "yes", "tests_match_requirement": "yes",
        "revised_fix_correct": "yes", "artificial": "no"}
rows, prio = [], []
for kind in ["B2", "C2"]:
    for d in sorted(VF.glob("*")):
        ps = [json.loads(f.read_text()) for f in sorted((d / "review").glob(f"{kind}.p*.json"))] if (d / "review").exists() else []
        if not ps: continue
        v = json.loads((d / "validation.json").read_text())
        pr = [p.get("parsed") for p in ps]
        row = dict(kind=kind, instance_id=d.name, reviewer=ps[0]["reviewer"], n_passes=len(ps), parsed_passes=sum(x is not None for x in pr))
        reasons = []
        if row["parsed_passes"] < len(ps): reasons.append("unparsable review pass")
        for q in Q[kind]:
            vals = [x.get(q) for x in pr if x]
            row[f"ai_{q}"] = vals[0] if len(set(vals)) == 1 else "disagree:" + "/".join(map(str, vals))
            if len(set(vals)) > 1: reasons.append(f"passes disagree on {q}")
            elif vals and vals[0] != GOOD[q]: reasons.append(f"{q}={vals[0]}")
        conf = [float(x.get("confidence", 0)) for x in pr if x]
        row["ai_min_confidence"] = min(conf) if conf else None
        if conf and min(conf) < 0.7: reasons.append("low confidence")
        row["ai_reasoning_p0"] = (pr[0] or {}).get("reasoning", "")
        row["ai_evidence_p0"] = json.dumps((pr[0] or {}).get("evidence", []))
        if kind == "C2" and v.get("C2_needs_human_unambiguity_check"): reasons.append("auto: new test literals could not be matched to the update text")
        row["suspected_invalid"] = bool(any(("=no" in r or "artificial=yes" in r or "trivial" in r) for r in reasons))
        row["priority_reasons"] = "; ".join(reasons)
        rows.append(row)
        if reasons: prio.append(dict(kind=kind, instance_id=d.name, n_reasons=len(reasons), reasons=row["priority_reasons"], folder=f"exp03_{'b2_fidelity' if kind=='B2' else 'c2_validity'}/items"))
for kind, part in [("B2", "exp03_b2_fidelity"), ("C2", "exp03_c2_validity")]:
    S = pd.DataFrame([r for r in rows if r["kind"] == kind])
    (OUT / part).mkdir(parents=True, exist_ok=True)
    S.to_csv(OUT / part / "sheet_ai_review.csv", index=False)
    print(kind, len(S), "reviewed;", int(S.suspected_invalid.sum()) if len(S) else 0, "suspected invalid")
P = pd.DataFrame(prio).sort_values("n_reasons", ascending=False)
P.to_csv(OUT / "PRIORITY_SPOTCHECK.csv", index=False); print(len(P), "items for spot-check")
