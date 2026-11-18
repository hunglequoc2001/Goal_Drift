"""Build the attempt manifest of one phase (staging or confirmatory) from a design file and the validation results.

Task sets (rules fixed before any full-study attempt was run; FULL_STUDY_FINAL_DESIGN.md §3):
  main      confirmatory: within each repository x difficulty stratum of configs/full/task_order.csv, tasks enter in
            seeded rank order if A_valid (G1 oracle), until the stratum quota is filled; a stratum that runs out is
            reported as a shortfall (never filled by hand);
  B2 / C2   main tasks whose B2 / C2 variant passed validation;
  sub       B1/C1 diagnostic subset: main tasks in a seeded random order, first n with B1_valid and C1_valid;
  staging   staging-pool tasks (pilot tasks, never confirmatory) with A, B1, C1, B2 and C2 all valid, in seeded order,
            at most one task per repository, first n.
Rows are ordered seed-major (all tasks/variants at seed 1 first) so that an interrupted run keeps complete replicates.
Writes <out_csv> and <out_csv>.meta.json (counts, sha256 of the design and of every variant file referenced).
Usage: python make_manifest.py <design_json> <out_csv>
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
VF = ROOT / "data/variants_full"
VORDER = {"A": 0, "B1": 1, "B2": 2, "C1": 3, "C2": 4}


def val(iid):
    f = VF / iid / "validation.json"
    return json.loads(f.read_text()) if f.exists() else {}


def main_set(order):
    chosen, short = [], {}
    for st, g in order.groupby("stratum", sort=True):
        q = int(g.stratum_quota.iloc[0])
        got = [i for i in g.sort_values("rank").instance_id if val(i).get("A_valid")][:q]
        chosen += got
        if len(got) < q:
            short[st] = q - len(got)
    return chosen, short


def files(iid, variant):
    rel = lambda p: str(p.relative_to(ROOT))
    d = VF / iid
    return dict(problem_file=rel(d / f"{variant}.txt") if variant in ("B1", "B2", "C2") else "",
                pre_patch=rel(d / "C1.pre.diff") if variant == "C1" else "",
                oracle_test_patch=rel(d / "C2.test.diff") if variant == "C2" else "")


def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def main(design_json, out_csv):
    D = json.loads(Path(design_json).read_text())
    rng = np.random.default_rng(D.get("seed", 20261027))
    order = pd.read_csv(ROOT / "configs/full/task_order.csv")
    sets, meta = {}, dict(design=D["name"], design_sha256=hashlib.sha256(Path(design_json).read_bytes()).hexdigest())
    if D["phase"] == "confirmatory":
        main_ids, short = main_set(order)
        sets["main"] = main_ids
        sets["B2"] = [i for i in main_ids if val(i).get("B2_valid")]
        # C2 extension: candidate-pool tasks (seeded rank order, flagged `candidate`) that were not needed to fill a main
        # quota, with a valid original oracle and a valid C2. They get A runs too (taskset `ext`) as the C2 baseline.
        ext = [i for i in order[order.candidate].sort_values(["stratum", "rank"]).instance_id
               if i not in set(main_ids) and val(i).get("A_valid") and val(i).get("C2_valid")]
        sets["ext"] = ext
        sets["C2"] = [i for i in main_ids if val(i).get("C2_valid")] + ext
        perm = list(rng.permutation(main_ids))
        sets["sub"] = [i for i in perm if val(i).get("B1_valid") and val(i).get("C1_valid")][:D.get("n_sub", 20)]
        meta["stratum_shortfall"] = short
    else:
        pool = list(pd.read_csv(ROOT / "configs/full/staging_pool.csv").instance_id)
        ok = [i for i in rng.permutation(pool) if all(val(i).get(k) for k in ["A_valid", "B1_valid", "C1_valid", "B2_valid", "C2_valid"])]
        seen, st = set(), []
        for i in ok:
            r = i.split("__")[0]
            if r not in seen:
                st.append(i)
                seen.add(r)
        sets["staging"] = st[:D.get("n_staging_tasks", 4)]
        sets["pool_A"] = [i for i in pool if val(i).get("A_valid")]
    rank = {i: k for k, i in enumerate(sets.get("main", []) + sets.get("ext", []) + sets.get("staging", []) + sets.get("pool_A", []))}
    rows = []
    for c in D["conditions"]:
        for iid in sets[c["taskset"]]:
            for m in c["models"]:
                for s in range(1, c["repeats"] + 1):
                    rows.append(dict(run_id=f"{m}__{iid}__{c['variant']}__s{s}", phase=D["phase"], model_key=m, served_name=m,
                                     instance_id=iid, variant=c["variant"], seed=s, taskset=c["taskset"],
                                     order=(s * 10 ** 6 + rank.get(iid, 0) * 10 + VORDER[c["variant"]]), **files(iid, c["variant"])))
    M = pd.DataFrame(rows).drop_duplicates("run_id").sort_values("order").reset_index(drop=True)
    M.to_csv(out_csv, index=False)
    refs = sorted({p for col in ["problem_file", "pre_patch", "oracle_test_patch"] for p in M[col] if p})
    meta.update(n_attempts=len(M), tasksets={k: v for k, v in sets.items()},
                counts=M.groupby(["variant", "model_key"]).size().unstack(fill_value=0).to_dict(),
                files_sha256={p: sha(p) for p in refs})
    Path(str(out_csv) + ".meta.json").write_text(json.dumps(meta, indent=1))
    print(D["name"], len(M), "attempts;", {k: len(v) for k, v in sets.items()}, "shortfall:", meta.get("stratum_shortfall"))


if __name__ == "__main__":
    main(*sys.argv[1:])
