"""Step 5's GORGE MARK on step 4's turned flap (R3f-9, C508): the lapels and the collar are ONE flap (toile_flap.py); the
gorge line (where the collar meets the lapel: from the gorge point on the neck edge out to the notch, along the lapel's
top) is its gorge column, and marking it splits the flap into the collar (behind it) and the two lapels (below it).
Both sides of the gorge seam are the same toile vertices: equal by construction (gorge_row reports it).

parts(Z) -> the split as toile.npz-like arrays: "collar:V/F" + "collar_grid" (rows, columns, the roll row: the collar's
rectangular grid, as cut_collar reads it) and "lapel.L:V/F", "lapel.R:V/F" (each a grid: the roll -> the outer edge,
the gorge -> the break; cut_flap unfolds them onto the fronts). load(path): toile.npz with the split added. Nothing here
knows a garment."""
from __future__ import annotations

import numpy as np

from .toile_flap import _grid_faces


def _blocks(Z):
    nr, ncf, ks, nl = (int(x) for x in Z["flap_layout"])
    V = np.asarray(Z["flap:V"], float)
    n0 = nr * ncf
    X = V[:n0].reshape(nr, ncf, 3)
    m = (nr - ks) * (nl - 1)
    YL = np.concatenate([X[ks:, -1:], V[n0: n0 + m].reshape(nr - ks, nl - 1, 3)], axis=1)
    YR = np.concatenate([X[ks:, :1], V[n0 + m: n0 + 2 * m].reshape(nr - ks, nl - 1, 3)], axis=1)
    return X, YL, YR, (nr, ncf, ks, nl)


def parts(Z) -> dict:
    """{name: array} of the flap split at its gorge marks (module doc)."""
    X, YL, YR, (nr, ncf, ks, nl) = _blocks(Z)
    G = lambda Y: _grid_faces(np.arange(Y.shape[0] * Y.shape[1]).reshape(Y.shape[:2]))
    return {"collar:V": X.reshape(-1, 3), "collar:F": G(X), "collar_grid": np.array([nr, ncf, ks]),
            "lapel.L:V": YL.reshape(-1, 3), "lapel.L:F": G(YL), "lapel.R:V": YR.reshape(-1, 3), "lapel.R:F": G(YR)[:, ::-1]}


def load(path) -> dict:
    """toile.npz as a dict, its flap (if any) split at the gorge marks."""
    Z = dict(np.load(path))
    if "flap:V" in Z and "flap_layout" in Z:
        Z.update(parts(Z))
    return Z


def gorge_row(Z) -> dict | None:
    """The gorge mark: its length on the collar's side and the lapel's (3D, both halves); None without a flap."""
    if "flap:V" not in Z or "flap_layout" not in Z:
        return None
    X, YL, YR, (nr, ncf, ks, nl) = _blocks(Z)
    L = lambda P: round(float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()) * 1000, 1)
    v = {"L": [L(X[ks:, -1]), L(YL[:, 0])], "R": [L(X[ks:, 0]), L(YR[:, 0])]}
    ok = all(abs(a - b) < 0.05 for a, b in v.values())
    return {"id": "gorge", "status": "PASS" if ok else "FAIL", "back_to": "4",
            "value": "; ".join(f"{s}: collar {a} / lapel {b} mm" for s, (a, b) in v.items()),
            "target": "the gorge mark splits the flap into the collar and the lapels; both sides one line (equal)",
            "why": "" if ok else "the gorge's two sides differ: the flap is not one piece at the gorge (step 4)"}
