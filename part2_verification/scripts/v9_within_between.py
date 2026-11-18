"""V9: within-task vs between-task BCM from the independent V5 attributions (paper_code, both parsers).
Within-task: macro mean of per-task BCM over tasks with >=3 rows; between-task: mean cosine over
cross-task pairs on the SAME eligible rows. Task-cluster bootstrap (1000, seed 9) for the difference."""
import numpy as np
import pandas as pd

ROOT = "/gpfs_common/share02/gaise/qle3/project_791/bcm-validity/"


def units(phi):
    n = np.linalg.norm(phi, axis=1)
    return phi[n > 1e-9] / n[n > 1e-9, None], n > 1e-9


def pair_stats(u, t):
    tot = u.sum(0) @ u.sum(0) - len(u)
    within_sum, within_pairs, per = 0.0, 0, []
    for k in np.unique(t):
        m = t == k
        s = u[m].sum(0)
        w = s @ s - m.sum()
        within_sum += w
        within_pairs += m.sum() * (m.sum() - 1)
        per.append(w / (m.sum() * (m.sum() - 1)))
    between = (tot - within_sum) / (len(u) * (len(u) - 1) - within_pairs)
    return float(np.mean(per)), float(between)


rows = []
sel = pd.read_csv(ROOT + "data/manifests/cohort_author_selection.csv")
for rep in ["author", "role_aware"]:
    phi = np.load(f"results/v5/phi_{rep}_paper_code.npy")
    for s in sorted(sel.agent_system.unique()):
        m = (sel.agent_system == s).values
        u, ok = units(phi[m])
        t = sel.instance_id.values[m][ok]
        vc = pd.Series(t).value_counts()
        elig = np.isin(t, vc[vc >= 3].index)
        if elig.sum() < 6:
            continue
        ue, te = u[elig], t[elig]
        w, b = pair_stats(ue, te)
        rng = np.random.default_rng(9)
        tasks = np.unique(te)
        idx = {k: np.flatnonzero(te == k) for k in tasks}
        diffs = []
        for _ in range(1000):
            pick = rng.choice(tasks, len(tasks))
            ii = np.concatenate([idx[k] for k in pick])
            tt = np.concatenate([np.full(len(idx[k]), j) for j, k in enumerate(pick)])
            w_, b_ = pair_stats(ue[ii], tt)
            diffs.append(w_ - b_)
        rows.append(dict(rep=rep, system=s, n_tasks=len(tasks), n_rows=int(elig.sum()), within=w, between=b,
                         diff=w - b, diff_lo=np.quantile(diffs, .025), diff_hi=np.quantile(diffs, .975)))
out = pd.DataFrame(rows)
out.to_csv("results/v9_within_between.csv", index=False)
print(out.round(3).to_string(index=False))
