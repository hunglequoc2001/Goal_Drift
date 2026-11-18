"""Why is BCM high or low? Per system: share of squared SHAP norm per feature, sign
agreement of the dominant feature, and BCM after removing one feature at a time."""
import numpy as np
import pandas as pd

from . import ROOT
from .bcm import bcm
from .experiments import SYSTEMS, load_frozen, run_path
from .features import FEATURES


def main():
    rows, drop = [], []
    for rep in ("author", "role_aware"):
        df, X, y, h = load_frozen(rep)
        for stage, run in (("E0", "seed42"), ("C", "within_system_perm101"), ("C", "global_perm101")):
            z = np.load(run_path(stage, rep, run), allow_pickle=True)
            assert str(z["frozen_hash"]) == h
            phi = z["shap"]
            for s in SYSTEMS:
                m = (df["agent_system"] == s).to_numpy()
                P = phi[m]
                share = (P ** 2).sum(0) / (P ** 2).sum()
                j = int(np.argmax(share))
                sgn = np.sign(P[:, j])
                rows.append({"rep": rep, "run": f"{stage}/{run}", "system": s, "bcm": bcm(P),
                             "dominant_feature": FEATURES[j], "dominant_share": share[j],
                             "dominant_same_sign_frac": max((sgn > 0).mean(), (sgn < 0).mean()),
                             **{f"share_{f}": share[k] for k, f in enumerate(FEATURES)}})
                if run == "seed42":
                    for k, f in enumerate(FEATURES):
                        drop.append({"rep": rep, "system": s, "feature_removed": f,
                                     "bcm_without": bcm(np.delete(P, k, axis=1)), "bcm_full": bcm(P)})
    pd.DataFrame(rows).to_csv(ROOT / "results/tables/mechanism_shap_concentration.csv", index=False)
    pd.DataFrame(drop).to_csv(ROOT / "results/tables/mechanism_leave_one_feature_out.csv", index=False)


if __name__ == "__main__":
    main()
