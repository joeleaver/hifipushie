"""A sparse symmetric positive-definite factor: CHOLMOD (scikit-sparse) when it's installed, else scipy's splu.

scikit-sparse has no wheels: it builds from source against SuiteSparse and the Python headers (libsuitesparse-dev,
python3-dev). As a hard dependency it failed `uv tool install` on runner machines without them (oxidegen froze the
runner pin, 2026-11-15), so it is the optional extra `fast` (and in the dev group). Without it the solves are the same
maths on splu: the old path, ~10-20x slower a factor at 24k points (codified C429), same answers to solver tolerance.

`CholeskyFactor(A, lower=True, order=..., supernodal_mode=...)`, `.factorize(A)`, `.solve(b)`: the part of
sksparse.cholmod's interface the chain solvers use. A is the LOWER triangle (csc)."""
from __future__ import annotations

import scipy.sparse as sp
from scipy.sparse.linalg import splu

try:
    from sksparse.cholmod import CholeskyFactor
    BACKEND = "cholmod"
except ImportError:  # (no wheel: see the module docstring)
    BACKEND = "splu"

    class CholeskyFactor:
        """splu on the full symmetric matrix rebuilt from its lower triangle; the symbolic arguments are ignored."""

        def __init__(self, A, lower: bool = True, order: str | None = None, supernodal_mode: str | None = None):
            if not lower:
                raise ValueError("this stand-in takes the lower triangle")
            self.lu = None

        def factorize(self, A):
            L = sp.csc_matrix(A)
            self.lu = splu((L + L.T - sp.diags(L.diagonal())).tocsc())

        def solve(self, b):
            return self.lu.solve(b)
