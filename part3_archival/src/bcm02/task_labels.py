"""Observable, non-BCM behavioural labels per trajectory (no LLM, no BCM):
  touched_ref_files_recall  fraction of files changed by the reference patch that the submitted patch also changes
  touched_extra_files       number of non-test files changed that the reference does not change
  ran_tests / ran_scripts   any R3 'test' / 'run' step
  edited_before_reading     first edit precedes any view/search step
The reference patch is ONE valid fix, so file recall is a localisation indicator, not correctness (correctness =
executable `resolved`). Writes results/tables/task_labels.csv and a 40-task x 5-model paired human-review
sheet results/validation/paired_tasks_40.csv.
Usage: python -m bcm02.task_labels"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .pipeline import COHORTS, load_cohort

ROOT = Path(__file__).resolve().parents[2]
FILE_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(_test\.go$)|(\.test\.[jt]sx?$)|(\.spec\.[jt]sx?$)|(^|/)test_[^/]+\.py$")


def files(patch):
    return {b for a, b in FILE_RE.findall(patch or "")}


def main():
    v1 = pd.read_parquet(ROOT / "data/raw/_meta/swe_bench_pro_hf/data/v1/test-00000-of-00001.parquet").set_index("instance_id")
    T = load_cohort("primary5")
    S = pd.read_parquet(ROOT / "data/interim/steps.parquet", columns=["run", "instance_id", "idx", "category"])
    S = S[S.run.isin(COHORTS["primary5"])]
    first = S.groupby(["run", "instance_id"]).apply(lambda g: pd.Series(dict(
        ran_tests=bool((g.category == "test").any()), ran_scripts=bool((g.category == "run").any()),
        edited_before_reading=bool((g.category == "edit").any()) and
        g.idx[g.category == "edit"].min() < g.idx[g.category.isin(["view", "search"])].min()
        if g.category.isin(["view", "search"]).any() else bool((g.category == "edit").any()))), include_groups=False).reset_index()
    rows = []
    for r in T.itertuples():
        p = ROOT / "data/raw" / r.run / "eval" / r.instance_id / "_patch.diff"
        sub = files(p.read_text(errors="replace")) if p.exists() else set()
        sub_src = {f for f in sub if not TEST_PATH.search(f)}
        ref = {f for f in files(v1.loc[r.instance_id, "patch"]) if not TEST_PATH.search(f)}
        rows.append(dict(run=r.run, instance_id=r.instance_id, n_ref_files=len(ref), n_sub_src_files=len(sub_src),
                         touched_ref_files_recall=(len(ref & sub_src) / len(ref)) if ref else np.nan,
                         touched_extra_files=len(sub_src - ref), patch_file_found=p.exists()))
    L = pd.DataFrame(rows).merge(first, on=["run", "instance_id"], how="left").merge(
        T[["run", "instance_id", "resolved", "repo", "repo_language"]], on=["run", "instance_id"])
    L.to_csv(ROOT / "results/tables/task_labels.csv", index=False)
    print(L.groupby("run")[["touched_ref_files_recall", "touched_extra_files", "ran_tests", "ran_scripts",
                            "edited_before_reading", "resolved"]].mean().round(3).to_string())
    print(L.groupby("resolved").touched_ref_files_recall.mean().round(3))
    rng = np.random.default_rng(20261027)
    tasks = rng.choice(sorted(L.instance_id.unique()), 40, replace=False)
    sheet = L[L.instance_id.isin(tasks)].sort_values(["instance_id", "run"]).copy()
    sheet["human_localisation_correct(y/n/unclear)"] = ""
    sheet["human_strategy_note"] = ""
    sheet.to_csv(ROOT / "results/validation/paired_tasks_40.csv", index=False)


if __name__ == "__main__":
    main()
