"""Pre-registered task sampling for the Exp03 full study (seeded; run once; output is frozen in configs/full/).

Population: SWE-bench Verified (rev in data/swe_bench_verified.revision), minus the 12 pilot tasks (they informed the
design, so they are kept out of the confirmatory sample and serve as the staging pool), minus the 3 '>4 hours' tasks.
Allocation of the 100 confirmatory tasks over repositories: proportional to Verified, with django capped at 30
(Verified is 46% django; the cap keeps repository-level variance estimable), largest-remainder rounding.
Within a repository, tasks are drawn proportionally to its difficulty buckets.
Every repository stratum gets a seeded random ORDER over all of its eligible tasks. Tasks enter the study in that order;
a task that fails executable validation (G1 oracle) is replaced by the next task of the same stratum
(repository x difficulty). So the sample never depends on agent outcomes or on hand-picking.
The first ceil(1.3 * quota) tasks of each stratum are 'candidates' whose images are pulled and validated.
Outputs: configs/full/task_order.csv (all eligible tasks, with stratum, rank, quota, candidate flag).
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261027
N, DJANGO_CAP, OVERSAMPLE = 100, 30, 1.3


def largest_remainder(w, total):
    raw = w / w.sum() * total
    base = np.floor(raw).astype(int)
    rem = total - base.sum()
    base[np.argsort(-(raw - base), kind="stable")[:rem]] += 1
    return base


def main():
    d = pd.read_parquet(ROOT / "data/swe_bench_verified/data/test-00000-of-00001.parquet")
    pilot = set(pd.read_csv(ROOT / "configs/pilot_tasks.csv").instance_id)
    E = d[~d.instance_id.isin(pilot) & (d.difficulty != ">4 hours")].copy()
    full = d[d.difficulty != ">4 hours"]
    rc = full.repo.value_counts().sort_index()
    q = pd.Series(0, index=rc.index)
    q["django/django"] = DJANGO_CAP
    other = rc.drop("django/django")
    q[other.index] = largest_remainder(other.to_numpy(float), N - DJANGO_CAP)
    rows = []
    rng = np.random.default_rng(SEED)
    for repo, g in E.groupby("repo"):
        dc = full[full.repo == repo].difficulty.value_counts().sort_index()
        dq = pd.Series(largest_remainder(dc.to_numpy(float), int(q[repo])) if q[repo] else 0, index=dc.index)
        for diff, gg in g.groupby("difficulty"):
            order = rng.permutation(sorted(gg.instance_id))
            quota = int(dq.get(diff, 0))
            ncand = math.ceil(OVERSAMPLE * quota) if quota else 0
            for rank, iid in enumerate(order):
                rows.append(dict(instance_id=iid, repo=repo, difficulty=diff, stratum=f"{repo}|{diff}", rank=rank,
                                 stratum_quota=quota, candidate=rank < ncand))
    O = pd.DataFrame(rows).merge(d[["instance_id", "image"]], on="instance_id")
    O = O.sort_values(["stratum", "rank"]).reset_index(drop=True)
    out = ROOT / "configs/full"
    out.mkdir(parents=True, exist_ok=True)
    O.to_csv(out / "task_order.csv", index=False)
    C = O[O.candidate]
    C[["instance_id", "repo", "difficulty", "image"]].to_csv(out / "candidates.csv", index=False)
    print(O.groupby("stratum").agg(quota=("stratum_quota", "first"), eligible=("instance_id", "size"),
                                   candidates=("candidate", "sum")).to_string())
    print("quota total", O.groupby("stratum").stratum_quota.first().sum(), "candidates", len(C))


if __name__ == "__main__":
    main()
