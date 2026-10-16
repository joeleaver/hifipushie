"""Post-construct finish (2026-10-16, dress-garrett): `cloth.<g>.finish = {"file", "key"}` is a hand finish of the
garment AS CONSTRUCTED (after construct's lapel press and made pieces), keyed on that result (cloth.finish_key) and
applied through cloth.finish_apply: closed seams move as one, crossings the move makes (self, body, the garment under)
go back. Synthetic sheets here; the real-model check (dg_garrett's jacket) is in docs/notes/cloth.md.
Run: uv run python tests/test_cloth_finish.py"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hifipushie import cloth  # noqa: E402


def sheets(n=9, h=0.02):
    """Two n x n grids side by side (x 0..L and L..2L at z 0), sewn along x = L (duplicate vertices)."""
    V, F, piece = [], [], []
    for p in range(2):
        o = len(V)
        for j in range(n):
            for i in range(n):
                V.append((p * (n - 1) * h + i * h, j * h, 0.0))
                piece.append(p)
        for j in range(n - 1):
            for i in range(n - 1):
                a = o + j * n + i
                F += [(a, a + 1, a + n), (a + 1, a + n + 1, a + n)]
    sew = [(j * n + n - 1, n * n + j * n) for j in range(n)]
    M = {"F": np.array(F), "sew": np.array(sew), "stitch": np.zeros((0, 2), int), "piece": np.array(piece),
         "names": ["a", "b"]}
    return np.array(V, float), M


def plane(z, lo=-1.0, hi=1.0):
    return (np.array([(lo, lo, z), (hi, lo, z), (hi, hi, z), (lo, hi, z)], float), np.array([(0, 1, 2), (0, 2, 3)]))


def test_seam_moves_as_one():
    V, M = sheets()
    off = np.zeros_like(V)
    a = M["sew"][4, 0]
    off[a, 2] = 0.004  # one side of a closed seam only
    V2, rep = cloth.finish_apply(V, off, M, body=plane(-0.05))
    b = M["sew"][4, 1]
    assert abs(V2[b, 2] - 0.004) < 1e-9 and np.linalg.norm(V2[a] - V2[b]) < 1e-9, (V2[a], V2[b])
    assert "refused" not in rep and rep["moved"] == 2, rep
    print("ok seam moves as one")


def test_crossing_goes_back():
    V, M = sheets()
    off = np.zeros_like(V)
    n = 9
    sink = [j * n + i for j in (3, 4, 5) for i in (3, 4, 5)]  # a patch of sheet a pushed through the body
    off[sink, 2] = -0.08
    lift = [n * n + j * n + i for j in (3, 4, 5) for i in (5, 6)]  # a clean move on sheet b
    off[lift, 2] = 0.003
    body = plane(-0.05)
    V2, rep = cloth.finish_apply(V, off, M, body=body)
    assert "refused" not in rep, rep
    assert not cloth._layer_crossing_verts(V2, M["F"], *body).any()
    assert np.allclose(V2[sink], V[sink]), "the crossing patch goes back"
    assert np.allclose(V2[lift, 2], 0.003), "the clean move stays"
    assert rep["kept_back"] >= len(sink), rep
    # the garment under: a move into it goes back too
    under = plane(0.01, 0.0, 0.5)
    off2 = np.zeros_like(V)
    off2[lift, 2] = 0.03
    V3, rep3 = cloth.finish_apply(V, off2, M, under=(under[0], under[1]))
    assert not (cloth._layer_crossing_verts(V3, M["F"], *under) & ~cloth._layer_crossing_verts(V, M["F"], *under)).any()
    print("ok crossing goes back", rep, rep3)


def test_key():
    V, _ = sheets()
    k = cloth.finish_key(V)
    assert k == cloth.finish_key(V.copy()) and len(k) == 16
    W = V.copy()
    W[3, 1] += 1e-4
    assert cloth.finish_key(W) != k
    assert "finish" in cloth.GARMENT_KEYS and "finish" in cloth.NOT_SIM
    print("ok key")


if __name__ == "__main__":
    test_seam_moves_as_one()
    test_crossing_goes_back()
    test_key()
