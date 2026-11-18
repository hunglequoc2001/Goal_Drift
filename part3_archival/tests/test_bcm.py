import numpy as np

from bcm02.analysis import bcm_w, units
from bcm02.pipeline import bcm


def brute(phi):
    u, _ = units(phi)
    c = u @ u.T
    return c[np.triu_indices(len(u), 1)].mean()


def test_bcm_identity_and_weights():
    rng = np.random.default_rng(0)
    phi = rng.normal(size=(40, 12))
    assert abs(bcm(phi) - brute(phi)) < 1e-12
    u, ok = units(phi)
    assert abs(bcm_w(u, ok, np.ones(40)) - brute(phi)) < 1e-12
    w = rng.integers(0, 3, 40).astype(float)
    # explicit multiset, excluding pairs of copies of the same row
    idx = np.repeat(np.arange(40), w.astype(int))
    c = u[idx] @ u[idx].T
    same = idx[:, None] == idx[None, :]
    assert abs(bcm_w(u, ok, w) - c[~same].mean()) < 1e-12
