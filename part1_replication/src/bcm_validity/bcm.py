"""Behavioral Consistency Metric (paper Eq. 3-6) with an O(nd) identity."""
import numpy as np

EPS = 1e-9


def unit_rows(phi, eps=EPS):
    """Return unit vectors of rows with norm > eps, plus the validity mask."""
    phi = np.asarray(phi, dtype=float)
    norms = np.linalg.norm(phi, axis=1)
    valid = norms > eps
    return phi[valid] / norms[valid, None], valid


def bcm_from_units(u):
    """BCM = (||sum u||^2 - n) / (n(n-1)); NaN (undefined) for n < 2."""
    n = len(u)
    if n < 2:
        return np.nan
    s = u.sum(axis=0)
    return float((s @ s - n) / (n * (n - 1)))


def bcm(phi, eps=EPS):
    return bcm_from_units(unit_rows(phi, eps)[0])


def bcm_bruteforce(phi, eps=EPS):
    """Reference implementation: mean strict upper triangle of the cosine matrix."""
    u, _ = unit_rows(phi, eps)
    n = len(u)
    if n < 2:
        return np.nan
    s = u @ u.T
    return float(s[np.triu_indices(n, k=1)].mean())


def bcm_weighted(u, w):
    """BCM over a multiset: row i appears w_i times (bootstrap). Pairs of distinct copies only."""
    w = np.asarray(w, dtype=float)
    n = w.sum()
    if n < 2:
        return np.nan
    s = (u * w[:, None]).sum(axis=0)
    # sum over ordered pairs of distinct copies = ||s||^2 - sum_i w_i (each u_i has unit norm)
    return float((s @ s - n) / (n * (n - 1)))


def between_task_bcm(u, task):
    """Mean cosine over pairs with different task IDs only."""
    task = np.asarray(task)
    n = len(u)
    if n < 2:
        return np.nan
    s = u.sum(axis=0)
    total = s @ s - n
    same, n_same_pairs = 0.0, 0
    for t in np.unique(task):
        m = task == t
        k = m.sum()
        if k > 1:
            st = u[m].sum(axis=0)
            same += st @ st - k
            n_same_pairs += k * (k - 1)
    n_between = n * (n - 1) - n_same_pairs
    if n_between == 0:
        return np.nan
    return float((total - same) / n_between)


def within_task_bcm(u, task, min_n=3):
    """Macro-average of per-task BCM over tasks with >= min_n valid vectors.

    Returns (mean, per_task dict)."""
    task = np.asarray(task)
    per = {}
    for t in np.unique(task):
        m = task == t
        if m.sum() >= min_n:
            per[t] = bcm_from_units(u[m])
    vals = [v for v in per.values() if not np.isnan(v)]
    return (float(np.mean(vals)) if vals else np.nan), per
