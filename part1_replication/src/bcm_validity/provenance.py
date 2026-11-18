"""Data provenance tables for Report 02 (no rows are dropped anywhere)."""
import json

import numpy as np
import pandas as pd

from . import ROOT, load_config
from .experiments import SYSTEMS

TABLES = ROOT / "results/tables"
PAPER_COUNTS = dict(zip(SYSTEMS, [946, 2938, 116, 1191, 2000, 2000]))


def main():
    cfg = load_config()
    interim = ROOT / cfg["paths"]["interim"]
    idx = pd.concat([pd.read_parquet(interim / "source_index_swe_smith.parquet"),
                     pd.read_parquet(interim / "source_index_nebius.parquet")], ignore_index=True)
    fa = pd.read_parquet(TABLES / "features_author.parquet")
    fr = pd.read_parquet(TABLES / "features_role_aware.parquet")
    out = {}

    # --- full sources
    src = idx.groupby(["source", "agent_system"]).agg(
        rows=("resolved", "size"), success_rate=("resolved", "mean"),
        plain_format=("format", lambda f: int((f == "plain").sum())),
        structured_format=("format", lambda f: int((f == "structured").sum())),
        tasks=("instance_id", "nunique"),
        null_label=("resolved_raw", lambda r: int(r.isin(["None", "nan"]).sum())),
    ).reset_index()
    src.to_csv(TABLES / "prov_source_by_system.csv", index=False)
    dup_id = idx[idx["source"] == "swe_smith"]["source_row_id"].duplicated(keep=False)
    dup_hash = idx["raw_trajectory_hash"].duplicated(keep=False)
    out["source_rows"] = idx.groupby("source").size().to_dict()
    out["swe_smith_duplicate_traj_id_rows"] = int(dup_id.sum())
    out["duplicate_hash_rows_by_source"] = idx[dup_hash].groupby("source").size().to_dict()
    out["duplicate_hash_groups"] = int(idx[dup_hash]["raw_trajectory_hash"].nunique())
    cross = set(idx.loc[idx.source == "swe_smith", "raw_trajectory_hash"]) & set(
        idx.loc[idx.source == "nebius", "raw_trajectory_hash"])
    out["cross_source_identical_hashes"] = len(cross)
    neb = idx[idx.source == "nebius"]
    ex = pd.crosstab(neb["agent_system"], neb["exit_status"].fillna("None"))
    ex.to_csv(TABLES / "prov_nebius_exit_status_source.csv")

    # --- cohort vs paper counts
    co = fa.merge(fr[["author_row", "parse_status", "parse_format", "n_actions", "ends_with_submit"]],
                  on="author_row", suffixes=("_author", "_role"))
    meta = pd.read_csv(ROOT / "data/manifests/cohort_author_selection.csv")
    co = co.merge(meta[["author_row", "exit_status", "repo_key", "format", "n_messages"]], on="author_row")
    rows = []
    for s in SYSTEMS:
        g = co[co["agent_system"] == s]
        vc = g["instance_id"].value_counts()
        rows.append({
            "system": s, "n_cohort": len(g), "n_paper": PAPER_COUNTS[s], "count_delta": len(g) - PAPER_COUNTS[s],
            "success_rate": g["resolved"].mean(),
            "format_plain": int((g["format"] == "plain").sum()),
            "format_structured": int((g["format"] == "structured").sum()),
            "author_parse_empty": int((g["n_actions_author"] == 0).sum()),
            "author_parse_empty_success_rate": g.loc[g["n_actions_author"] == 0, "resolved"].mean(),
            "author_parse_nonempty_success_rate": g.loc[g["n_actions_author"] > 0, "resolved"].mean(),
            "role_parse_empty": int((g["n_actions_role"] == 0).sum()),
            "role_parse_error": int(g["parse_status_role"].str.startswith("error").sum()),
            "median_steps_author": g["n_actions_author"].median(),
            "median_steps_role": g["n_actions_role"].median(),
            "median_messages": g["n_messages"].median(),
            "ends_with_submit_role": int(g["ends_with_submit"].sum()),
            "nonsubmitted_exit_status": int((~g["exit_status"].fillna("").str.startswith("submitted")).sum())
            if g["source"].iloc[0] == "nebius" else None,
            "duplicate_hash_rows": int(g["raw_trajectory_hash"].duplicated(keep=False).sum()),
            "duplicate_source_row_id": int(g["source_row_id"].duplicated(keep=False).sum()),
            "n_tasks": g["instance_id"].nunique(), "tasks_ge3": int((vc >= 3).sum()),
            "max_runs_per_task": int(vc.max()), "n_repos": g["repo_key"].nunique(),
        })
    pd.DataFrame(rows).to_csv(TABLES / "prov_cohort_by_system.csv", index=False)

    # --- tasks / repositories across sources
    s_ids = set(co.loc[co.source == "swe_smith", "instance_id"])
    n_ids = set(co.loc[co.source == "nebius", "instance_id"])
    s_rep = set(co.loc[co.source == "swe_smith", "repo_key"])
    n_rep = set(co.loc[co.source == "nebius", "repo_key"])
    out["cohort_cross_source_instance_overlap"] = len(s_ids & n_ids)
    out["cohort_cross_source_repo_overlap"] = sorted(s_rep & n_rep)
    out["cohort_repos"] = {"swe_smith": len(s_rep), "nebius": len(n_rep)}
    shared = co.groupby("instance_id")["agent_system"].nunique()
    out["cohort_instances_shared_by_k_systems"] = shared.value_counts().sort_index().to_dict()
    out["cohort_duplicate_hash_rows"] = int(co["raw_trajectory_hash"].duplicated(keep=False).sum())
    sel = json.loads((ROOT / "data/manifests/selection_meta.json").read_text())
    out["nebius_selection"] = sel
    (TABLES / "prov_summary.json").write_text(json.dumps(out, indent=2, default=str))
    # exact-duplicate examples (for the report)
    d = co[co["raw_trajectory_hash"].duplicated(keep=False)].sort_values("raw_trajectory_hash")
    d[["author_row", "source", "source_row_id", "instance_id", "agent_system", "resolved",
       "raw_trajectory_hash"]].head(40).to_csv(TABLES / "prov_cohort_duplicate_examples.csv", index=False)
    print(json.dumps(out, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
