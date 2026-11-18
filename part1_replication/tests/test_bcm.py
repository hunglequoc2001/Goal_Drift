import numpy as np
import pytest

from bcm_validity.bcm import (bcm, bcm_bruteforce, bcm_weighted, between_task_bcm,
                              unit_rows, within_task_bcm)


def test_identical_vectors():
    v = np.array([[0.5, -0.2, 0.1, 0.9]] * 3)
    assert bcm(v) == pytest.approx(1.0, abs=1e-12)


def test_orthogonal():
    assert bcm(np.eye(2)) == pytest.approx(0.0, abs=1e-12)


def test_antipodal_construct():
    e1 = np.array([1.0, 0, 0])
    assert bcm(np.array([e1, e1, -e1, -e1])) == pytest.approx(-1 / 3, abs=1e-12)


def test_undefined_single_and_zero():
    assert np.isnan(bcm(np.array([[1.0, 2.0]])))
    assert np.isnan(bcm(np.zeros((5, 3))))
    # zero rows excluded, not NaN-propagating
    v = np.vstack([np.zeros(3), [1, 0, 0], [1, 0, 0]])
    assert bcm(v) == pytest.approx(1.0)
    assert np.isnan(bcm(np.vstack([np.full(3, 1e-12), [1, 0, 0]])))


@pytest.mark.parametrize("seed", range(5))
def test_identity_matches_bruteforce(seed):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(200, 12))
    x[50:80] = x[0]  # duplicate vectors
    x[90:95] = 0.0
    assert abs(bcm(x) - bcm_bruteforce(x)) <= 1e-10


def test_weighted_equals_expanded():
    rng = np.random.default_rng(1)
    u, _ = unit_rows(rng.normal(size=(30, 12)))
    w = rng.integers(0, 4, size=30)
    expanded = np.repeat(u, w, axis=0)
    assert abs(bcm_weighted(u, w) - bcm_bruteforce(expanded)) <= 1e-10


def test_between_and_within():
    rng = np.random.default_rng(2)
    u, _ = unit_rows(rng.normal(size=(40, 12)))
    task = rng.integers(0, 8, size=40)
    s = u @ u.T
    diff = task[:, None] != task[None, :]
    assert abs(between_task_bcm(u, task) - s[diff].mean()) <= 1e-10
    m, per = within_task_bcm(u, task, 3)
    for t, val in per.items():
        assert abs(val - bcm_bruteforce(u[task == t])) <= 1e-10
