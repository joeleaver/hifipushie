"""sparse_chol: CHOLMOD when scikit-sparse is installed, else an splu stand-in with the same interface and answers."""
import importlib
import sys

import numpy as np
import pytest
import scipy.sparse as sp

from hifipushie import sparse_chol


def _spd(n=60, seed=3):
    rng = np.random.default_rng(seed)
    R = sp.random(n, n, density=0.08, random_state=rng, format="csr")
    A = R @ R.T + sp.identity(n) * 0.5
    L = sp.tril(A, format="csc")
    L.sort_indices()
    return A.tocsr(), L


def _standin(monkeypatch):
    monkeypatch.setitem(sys.modules, "sksparse", None)
    monkeypatch.setitem(sys.modules, "sksparse.cholmod", None)
    mod = importlib.reload(sparse_chol)
    assert mod.BACKEND == "splu"
    return mod


def test_the_splu_standin_solves_like_cholmod(monkeypatch):
    A, L = _spd()
    b = np.arange(A.shape[0] * 3, dtype=float).reshape(-1, 3)
    try:
        mod = _standin(monkeypatch)
        F = mod.CholeskyFactor(L, lower=True, order="metis", supernodal_mode="supernodal")
        F.factorize(L)
        x = F.solve(b)
        assert np.allclose(A @ x, b, atol=1e-8)
        F.factorize(L * 2.0)  # refactored with new values, same pattern (how the solvers use it)
        assert np.allclose(A @ F.solve(b), b / 2.0, atol=1e-8)
    finally:
        monkeypatch.undo()
        importlib.reload(sparse_chol)


def test_cholmod_when_installed():
    pytest.importorskip("sksparse.cholmod")
    assert sparse_chol.BACKEND == "cholmod"
    A, L = _spd()
    F = sparse_chol.CholeskyFactor(L, lower=True, order="metis", supernodal_mode="supernodal")
    F.factorize(L)
    b = np.ones(A.shape[0])
    assert np.allclose(A @ F.solve(b), b, atol=1e-8)
