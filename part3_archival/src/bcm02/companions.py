"""Companion sensitivity: a model's BCM depends on which OTHER models share the pooled predictor.
For every subset (size >= 1) of a cohort, fit the released LightGBM with task-grouped 5-fold CV
(seed 0) on that subset only and record each member's BCM (tree-path TreeSHAP), R2 features.
Trajectories and labels of the target model are identical across subsets.
Usage: python -m bcm02.companions <cohort> <rep>"""
import itertools
import sys

import numpy as np
import pandas as pd

from .analysis import OUT, SHORT
from .pipeline import COHORTS, load_cohort, run_once


def main(cohort, rep):
    T = load_cohort(cohort)
    runs = COHORTS[cohort]
    rows = []
    for k in range(1, len(runs) + 1):
        for sub in itertools.combinations(runs, k):
            S = T[T.run.isin(sub)].reset_index(drop=True)
            if S.resolved.nunique() < 2:
                continue
            r, phi, margin, y = run_once(S, rep, "lgbm_paper", "grouped5", "real", 0)
            for m in sub:
                rows.append(dict(cohort=cohort, rep=rep, subset=" + ".join(SHORT[x] for x in sub), k=k,
                                 model=SHORT[m], bcm=r[f"bcm|{m}"], auc_within=r[f"auc_within|{m}"]))
            print(k, sub, flush=True)
    D = pd.DataFrame(rows)
    D.to_csv(OUT / f"a9_companions_{cohort}_{rep}.csv", index=False)
    print(D.groupby("model").bcm.agg(["min", "median", "max"]).round(3))


if __name__ == "__main__":
    main(*sys.argv[1:3])
