"""Smoke check: stored artifacts are reproducible from the frozen inputs."""
import json

import numpy as np
import pandas as pd

from . import ROOT, load_config
from .bcm import bcm
from .experiments import SYSTEMS, load_frozen, run_path, stratified_splits
from .model import explain, make_lgbm


def main():
    cfg = load_config()
    for rep in ("author", "role_aware"):
        df, X, y, h = load_frozen(rep)
        man = json.loads((ROOT / f"data/manifests/frozen_{rep}.json").read_text())
        assert man["frozen_hash"] == h, f"{rep}: frozen hash changed"
        z = np.load(run_path("E0", rep, "seed42"), allow_pickle=True)
        tr, va = stratified_splits(y, 42)[0]
        m = make_lgbm(cfg["baseline"]["lgbm"], 4).fit(X[tr], y[tr])
        vals, _, err, _ = explain(m, X[va])
        dp = np.abs(m.predict_proba(X[va])[:, 1] - z["proba"][va]).max()
        ds = np.abs(vals - z["shap"][va]).max()
        assert dp < 1e-12 and ds < 1e-12, (dp, ds)
        n_checked = 0
        for stage in ("E0", "A", "B", "C", "D"):
            t = pd.read_csv(ROOT / f"results/tables/runs_{stage}_{rep}.csv")
            for run, g in t.groupby("run"):
                phi = np.load(run_path(stage, rep, run), allow_pickle=True)["shap"]
                for r in g.itertuples():
                    msk = (df["agent_system"] == r.system).to_numpy()
                    assert abs(bcm(phi[msk]) - r.bcm) < 1e-12, (stage, run, r.system)
                    n_checked += 1
        b = np.load(ROOT / f"results/arrays/bootstrap_cluster_{rep}.npz")
        assert str(b["frozen_hash"]) == h
        print(f"{rep}: hash ok; fold-0 refit |dproba|={dp:.1e} |dshap|={ds:.1e} additivity={err:.1e}; "
              f"{n_checked} stored BCM values recomputed exactly; bootstrap hash ok", flush=True)
    print("SMOKE CHECK PASSED")


if __name__ == "__main__":
    main()
