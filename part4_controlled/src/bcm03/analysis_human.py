"""Exp03 sensitivity of H2 (B2) and H3 (C2) to the human review (two raters, VR and LC; human_review_filled*/).

A reviewed task is *flagged* when at least one rater gives an unfavourable content label:
  B2: same_requirements != yes, information_added != none, or information_removed != none
      (`natural` is not used: the raters agree no better than chance on it, kappa -0.05);
  C2: change_meaningful == no, or requirement_unambiguous / tests_match_requirement / revised_fix_correct != yes
      ('trivial' changes are kept: they are valid but small requirement changes).
Labels are the raters' own; the project lead's adjudication (human_review_filled/adjudications.csv) only adds a flag to a
task that is already flagged, so it does not change the subsets. Each analysis is run on two subsets:
  drop_flagged     all analysed tasks except the flagged ones (unreviewed tasks kept);
  reviewed_clean   only reviewed tasks that no rater flagged.
Writes <out_dir>/s_human_h2.csv, s_human_h3.csv and meta_human.json. Nothing existing is overwritten.
Usage: python -m bcm03.analysis_human <in_dir> <out_dir> [n_boot=2000]
"""
import json
import sys
from pathlib import Path

import pandas as pd

from bcm03.analysis_full import h2, h3_h4

ROOT = Path(__file__).resolve().parents[3]
SHEETS = {"VR": ROOT / "human_review_filled/{part}_reviewed.csv",
          "LC": ROOT / "human_review_filled_LC/human_review_blind_2026-11-04_LC/{part}/sheet.csv"}
BAD = {"exp03_b2_fidelity": lambda s: (s.human_same_requirements != "yes") | (s.human_information_added != "none")
                                      | (s.human_information_removed != "none"),
       "exp03_c2_validity": lambda s: (s.human_change_meaningful == "no") | (s.human_requirement_unambiguous != "yes")
                                      | (s.human_tests_match_requirement != "yes") | (s.human_revised_fix_correct != "yes")}


def flags(part):
    reviewed, flagged = set(), set()
    for rater, path in SHEETS.items():
        s = pd.read_csv(str(path).format(part=part), dtype=str)
        s = s.apply(lambda c: c.str.strip() if c.dtype == object else c)
        reviewed |= set(s.instance_id)
        flagged |= set(s.instance_id[BAD[part](s)])
    return reviewed, flagged


def main(in_dir, out_dir, n_boot=2000):
    n_boot, out = int(n_boot), Path(out_dir)
    T = pd.read_parquet(Path(in_dir) / "attempts.parquet").sort_values("run_id").reset_index(drop=True)
    P = pd.read_parquet(out / "pairs.parquet")
    meta, h2res, h3res = {}, [], []
    for part, var in [("exp03_b2_fidelity", "B2"), ("exp03_c2_validity", "C2")]:
        used = set(T[T.variant == var].instance_id)
        rev, fl = flags(part)
        subsets = {"drop_flagged": used - fl, "reviewed_clean": (used & rev) - fl}
        meta[var] = dict(analysed=len(used), reviewed_and_analysed=len(used & rev), flagged_and_analysed=sorted(used & fl),
                         **{f"n_{k}": len(v) for k, v in subsets.items()})
        for name, keep in subsets.items():
            tmp = out / f"_tmp_human_{var}_{name}"
            tmp.mkdir(exist_ok=True)
            if var == "B2":
                h2(T[(T.variant == "A") | ((T.variant == "B2") & T.instance_id.isin(keep))],
                   P[(P.kind == "AA") | ((P.kind == "AB2") & P.instance_id.isin(keep))], tmp, n_boot)
                f, acc = tmp / "h2_invariance.csv", h2res
            else:
                h3_h4(T[(T.variant != "C2") | T.instance_id.isin(keep)], {}, tmp, n_boot)
                f, acc = tmp / "h3_adaptation.csv", h3res
            acc.append(pd.read_csv(f).assign(subset=name, n_tasks_subset=len(keep)))
            for x in tmp.iterdir():
                x.unlink()
            tmp.rmdir()
    pd.concat(h2res).to_csv(out / "s_human_h2.csv", index=False)
    pd.concat(h3res).to_csv(out / "s_human_h3.csv", index=False)
    json.dump(dict(n_boot=n_boot, **meta), open(out / "meta_human.json", "w"), indent=1)
    print(json.dumps(meta, indent=1), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
