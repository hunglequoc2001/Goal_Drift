"""Stage 1: index pinned sources, replicate the author cohort selection, parse, featurize.

Selection replicates external/colm-agent-eval/data/load_swebench.py:
  SWE-smith tool split, all rows, pandas .sample(n=4000, random_state=42)        (:100-101)
  Nebius train, systems with >=500 rows in groupby order, first 4, .sample(2000) (:53-64)
  concat, .sample(frac=1.0, random_state=42)                                     (:106-107)
"""
import hashlib
import importlib.util
import json
import re
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import ROOT, load_config
from .features import FEATURES, compute_features
from .parsers import (author_nebius_actions, author_swe_smith_actions,
                      role_aware_nebius, role_aware_swe_smith)


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def repo_key(source, instance_id):
    """Canonical repository key used for cross-source audits."""
    if source == "swe_smith":
        return instance_id.split(".")[0].lower()
    return re.sub(r"-\d+$", "", instance_id).lower()


def read_source(key, cfg):
    d = cfg["datasets"][key]
    files = sorted((ROOT / cfg["paths"]["raw"] / key).glob(d["pattern"]))
    frames = []
    for f in files:
        t = pq.read_table(f)
        df = pd.DataFrame({c: t.column(c).to_pylist() for c in t.column_names})
        df["shard"] = f.name
        df["offset"] = np.arange(len(df))
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["source"] = key
    df["source_revision"] = d["revision"]
    return df


def index_swe_smith(df):
    out = pd.DataFrame({
        "source": df["source"], "source_revision": df["source_revision"],
        "shard": df["shard"], "offset": df["offset"],
        "source_row_id": df["traj_id"], "instance_id": df["instance_id"],
        "agent_system": df["model"],
        "resolved_raw": df["resolved"],
        "raw_trajectory_hash": [sha256(m) for m in df["messages"]],
    })
    out["n_messages"] = [len(json.loads(m)) for m in df["messages"]]
    out["format"] = ["structured" if '"message_type"' in m else "plain" for m in df["messages"]]
    out["exit_status"] = None
    return out


def index_nebius(df):
    raw = [json.dumps(t, sort_keys=True, ensure_ascii=False) for t in df["trajectory"]]
    hashes = [sha256(r) for r in raw]
    out = pd.DataFrame({
        "source": df["source"], "source_revision": df["source_revision"],
        "shard": df["shard"], "offset": df["offset"],
        "source_row_id": [f"{s}:{o}:{h[:16]}" for s, o, h in zip(df["shard"], df["offset"], hashes)],
        "instance_id": df["instance_id"], "agent_system": df["model_name"],
        "resolved_raw": df["target"], "raw_trajectory_hash": hashes,
        "n_messages": [len(t) for t in df["trajectory"]],
        "format": "swe-agent", "exit_status": df["exit_status"],
    })
    return out


def author_label_smith(v):
    return 1 if v in [True, "True", 1] else 0          # load_swebench.py:19-20


def author_label_nebius(v):
    return 1 if v in [True, "True", "True\n", 1] else 0  # load_swebench.py:51


def select_cohort(idx_s, idx_n, cfg):
    ds, dn = cfg["datasets"]["swe_smith"], cfg["datasets"]["nebius"]
    s = idx_s.reset_index(drop=True).copy()
    s["global_idx"] = s.index
    s_sample = s.sample(n=min(ds["sample_n"], len(s)), random_state=ds["sample_seed"])
    n = idx_n.reset_index(drop=True).copy()
    n["global_idx"] = n.index
    counts = n.groupby("agent_system").size()
    valid = counts[counts >= dn["min_count"]].index.tolist()
    selected = valid[: dn["max_systems"]]
    parts = []
    for sysname in selected:
        sub = n[n["agent_system"] == sysname]
        parts.append(sub.sample(n=min(dn["sample_n_per_system"], len(sub)), random_state=dn["sample_seed"]))
    combined = pd.concat([s_sample] + parts, ignore_index=True)
    combined = combined.sample(frac=1.0, random_state=cfg["datasets"]["combined_shuffle_seed"]).reset_index(drop=True)
    combined["author_row"] = np.arange(len(combined))
    meta = {"nebius_counts": counts.to_dict(), "nebius_valid": valid, "nebius_selected": selected}
    return combined, meta


def load_author_extract():
    path = ROOT / "external/colm-agent-eval/data/extract_features.py"
    spec = importlib.util.spec_from_file_location("author_extract_features", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.extract_features


def main():
    cfg = load_config()
    t0 = time.time()
    interim = ROOT / cfg["paths"]["interim"]
    manifests = ROOT / cfg["paths"]["manifests"]
    tables = ROOT / cfg["paths"]["tables"]
    for p in (interim, manifests, tables):
        p.mkdir(parents=True, exist_ok=True)

    raw_s = read_source("swe_smith", cfg)
    print("swe_smith rows", len(raw_s), round(time.time() - t0), "s", flush=True)
    raw_n = read_source("nebius", cfg)
    print("nebius rows", len(raw_n), round(time.time() - t0), "s", flush=True)
    idx_s, idx_n = index_swe_smith(raw_s), index_nebius(raw_n)
    idx_s["resolved"] = idx_s["resolved_raw"].map(author_label_smith)
    idx_n["resolved"] = idx_n["resolved_raw"].map(author_label_nebius)
    for df in (idx_s, idx_n):
        df["repo_key"] = [repo_key(s, i) for s, i in zip(df["source"], df["instance_id"])]
        df["resolved_raw"] = df["resolved_raw"].astype(str)
    idx_s.to_parquet(interim / "source_index_swe_smith.parquet", index=False)
    idx_n.to_parquet(interim / "source_index_nebius.parquet", index=False)
    print("indexed", round(time.time() - t0), "s", flush=True)

    cohort, meta = select_cohort(idx_s, idx_n, cfg)
    (manifests / "selection_meta.json").write_text(json.dumps(meta, indent=2, default=str))

    author_extract = load_author_extract()
    rows_author, rows_role, raw_keep, mismatches = [], [], [], 0
    for r in cohort.itertuples(index=False):
        if r.source == "swe_smith":
            rec = raw_s.iloc[r.global_idx]
            assert rec["traj_id"] == r.source_row_id
            raw = rec["messages"]
            a_steps = author_swe_smith_actions(raw)
            try:
                steps, obs, fmt = role_aware_swe_smith(raw)
                status = "ok" if steps else "empty"
            except Exception as e:  # recorded, never silently dropped
                steps, obs, fmt, status = [], [], "error", f"error:{type(e).__name__}"
        else:
            rec = raw_n.iloc[r.global_idx]
            traj = rec["trajectory"]
            raw = json.dumps(traj, sort_keys=True, ensure_ascii=False)
            assert sha256(raw) == r.raw_trajectory_hash
            a_steps = author_nebius_actions(traj)
            try:
                steps, obs, fmt = role_aware_nebius(traj)
                status = "ok" if steps else "empty"
            except Exception as e:
                steps, obs, fmt, status = [], [], "error", f"error:{type(e).__name__}"
        fa = compute_features(a_steps)
        ref = author_extract(json.dumps(a_steps))
        if not all(np.isclose(fa[k], ref[k], rtol=0, atol=1e-12) for k in FEATURES):
            mismatches += 1
        fr = compute_features(steps, error_texts=obs)
        base = {"author_row": r.author_row, "source": r.source, "source_revision": r.source_revision,
                "source_row_id": r.source_row_id, "instance_id": r.instance_id,
                "agent_system": r.agent_system, "resolved": r.resolved,
                "raw_trajectory_hash": r.raw_trajectory_hash}
        rows_author.append({**base, "parse_status": "ok" if a_steps else "empty_author_parse",
                            "n_actions": len(a_steps), **fa})
        rows_role.append({**base, "parse_status": status, "parse_format": fmt,
                          "n_actions": len(steps),
                          "ends_with_submit": bool(steps) and steps[-1].strip().startswith("submit"), **fr})
        raw_keep.append({**base, "raw": raw, "author_steps": json.dumps(a_steps),
                         "role_steps": json.dumps(steps),
                         "role_obs_head": json.dumps([o[:1500] for o in obs])})
    print("featurized", len(cohort), "author-feature mismatches vs author code:", mismatches,
          round(time.time() - t0), "s", flush=True)
    if mismatches:
        raise SystemExit("independent features disagree with author extract_features")

    keep_cols = ["author_row", "source", "source_revision", "source_row_id", "shard", "offset",
                 "global_idx", "instance_id", "repo_key", "agent_system", "resolved",
                 "resolved_raw", "raw_trajectory_hash", "format", "exit_status", "n_messages"]
    cohort[keep_cols].to_csv(manifests / "cohort_author_selection.csv", index=False)
    pd.DataFrame(rows_author).to_parquet(tables / "features_author.parquet", index=False)
    pd.DataFrame(rows_role).to_parquet(tables / "features_role_aware.parquet", index=False)
    pd.DataFrame(raw_keep).to_parquet(interim / "cohort_raw.parquet", index=False)
    print("done", round(time.time() - t0), "s", flush=True)


if __name__ == "__main__":
    main()
