"""Instance-level agreement of recomputed outcomes (official rule on archived _output.json + v1 test lists)
with the official eval_results.json in SWE-bench_Pro-os@66f92766 traj/<run>/."""
import json
from pathlib import Path

import pandas as pd

T = pd.read_parquet("data/interim/trajectories.parquet")
O = pd.read_parquet("data/interim/outcomes_all_v1.parquet")
rows, dis = [], []
for d in sorted(Path("data/raw/_meta/SWE-bench_Pro-os/traj").iterdir()):
    f = d / "eval_results.json"
    if not f.exists():
        continue
    off = pd.Series(json.load(open(f)), name="official").rename_axis("instance_id").reset_index()
    for run in [d.name] + ([] if d.name in set(O.run) else []):
        if run not in set(O.run):
            rows.append(dict(official_folder=d.name, note="no archived run with this folder name", n_official=len(off)))
            continue
        ours = O[O.run == run][["instance_id", "resolved", "eval_file"]]
        m = off.merge(ours, on="instance_id", how="outer", indicator=True)
        both = m[m._merge == "both"]
        trajs = set(T[T.run == run].instance_id)
        r = dict(official_folder=d.name, n_official=len(off), n_official_in_v1=int((m._merge == "both").sum()),
                 n_official_not_in_v1=int((m._merge == "left_only").sum()),
                 agree=int((both.official == both.resolved).sum()),
                 official_true_ours_false=int((both.official & ~both.resolved.astype(bool)).sum()),
                 official_false_ours_true=int((~both.official.astype(bool) & both.resolved.astype(bool)).sum()),
                 ours_resolved_not_in_official=int(m[(m._merge == "right_only") & m.resolved.astype(bool)].shape[0]),
                 official_rate=off.official.mean(), ours_rate_on_traj=T[T.run == run].resolved.mean(),
                 official_rate_on_traj=both[both.instance_id.isin(trajs)].official.mean())
        rows.append(r)
        x = both[both.official != both.resolved].assign(run=run)
        dis.append(x)
R = pd.DataFrame(rows)
R.to_csv("results/tables/outcome_validation.csv", index=False)
pd.concat(dis).to_csv("results/tables/outcome_disagreements.csv", index=False)
pd.set_option("display.width", 250)
print(R.round(3).to_string(index=False))
