"""GnmFace's frame, solve and carry (a mixin of GnmFace). Part of face shapes (faceshapes.py has the overview; the class is faceshapes_gnm.GnmFace)."""
from __future__ import annotations

import numpy as np

from . import faceshapes
from .faceshapes import family

class _GnmSolve:
    """GnmFace's frame, solve and carry: GNM's own frame for the head, the expression solve, the tongue,
    projecting a shape onto GNM's basis, and carrying offsets onto a piece."""

    # ---- GNM's frame, the solve, the carry ---------------------------------------------------------------------

    def _setup(self):
        if self._gnm:
            return self._gnm
        from scipy.spatial import cKDTree

        from . import base_identity
        g = base_identity._gnm_data()
        c = self.head["carry"]
        V = c["V"]
        Wlm = np.zeros((68, len(V)))
        for i, r in enumerate(g["lm68"]):
            for v, w in zip(r[0::2], r[1::2]):
                Wlm[i, int(v)] += float(w)
        names = [str(n) for n in g["expression_names"]]
        regions = {k: [i for i, n in enumerate(names) if n.startswith(k)] for k in ("lower_face", "left_eye", "right_eye")}
        X0 = Wlm @ V
        wg = float(X0[54, 0] - X0[48, 0])
        self._gnm = {"g": g, "c": c, "Wlm": Wlm, "regions": regions, "X0": X0, "wg": wg,
                     "tree": cKDTree(self.head["verts"])}
        return self._gnm

    def _solve(self, moves: dict, region: str, hold: float = faceshapes.HOLD, prior: float = faceshapes.SOLVE_RIDGE) -> np.ndarray:
        """GNM vertex offsets (its frame) that move landmarks by `moves` ({id: [x, y, z] in mouth widths}) holding
        the rest: ridge least squares over the region's expression components (linear in them, as pose_expression)."""
        G = self._setup()
        comps = G["regions"]["lower_face"] if region == "mouth" else G["regions"]["left_eye"] + G["regions"]["right_eye"]
        B = G["g"]["expression_basis"][comps]
        A = np.einsum("ln,cnd->ldc", G["Wlm"], B).reshape(68 * 3, len(comps))
        t = np.zeros((68, 3))
        w = np.full((68, 3), hold)
        for i, d in moves.items():
            t[i] += np.asarray(d, float) * G["wg"]
            w[i] = 1.0
        w, t = w.ravel(), t.ravel()
        Aw = A * w[:, None]
        cf = np.linalg.solve(Aw.T @ Aw + prior * np.eye(len(comps)), Aw.T @ (t * w))
        self._last = dict(zip(comps, cf))  # (shape_coeffs: a shape IS these expression coefficients)
        return np.tensordot(cf, B, 1)

    TONGUE_OUT = 0.006  # m (world): how far past the lips' front the tongue's tip comes at tongueOut 1
    TONGUE_COMPS = 6    # GNM's leading tongue components used (000 = out, 001 / 002 = up, 003 = sideways ...)

    def _tongue_out(self) -> tuple:
        """GNM's own tongue pushed out: the least change of its leading tongue components (GNM frame offsets of
        every vertex, and the coefficients) that brings the tongue's front TONGUE_OUT past the lips, a little down."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        names = [str(n) for n in g["expression_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("tongue_") and n != "tongue_mean"][:self.TONGUE_COMPS]
        tg = np.flatnonzero(np.asarray(g["groups"]["tongue"]) > 0.5)
        front = tg[V[tg, 2] > np.percentile(V[tg, 2], 92)]
        A = np.stack([g["expression_basis"][i][front].mean(0) for i in comps], 1).astype(float)  # (3, n)
        X0 = G["X0"]
        reach = float(max(X0[51][2], X0[57][2]) - V[front, 2].mean()) + self.TONGUE_OUT / float(G["c"]["s"])
        t = np.array([0.0, -0.2 * reach, reach])
        cf = A.T @ np.linalg.solve(A @ A.T + 1e-9 * np.eye(3), t)  # (min norm)
        return np.tensordot(cf, g["expression_basis"][comps], 1), dict(zip(comps, cf))

    def _tongue_shape(self, down: float, back: float, bow: float) -> np.ndarray:
        """GNM's own tongue reshaped (GNM-frame offsets of every vertex): the least change of its leading tongue
        components that moves the tip (front 10%) down / back and bows the dorsum's mid-line up over its sides."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        names = [str(n) for n in g["expression_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("tongue_") and n != "tongue_mean"][:self.TONGUE_COMPS]
        tg = np.flatnonzero(np.asarray(g["groups"]["tongue"]) > 0.5)
        T = V[tg]; z0, z1 = T[:, 2].min(), T[:, 2].max(); L = z1 - z0; w = np.ptp(T[:, 0]); xm = np.median(T[:, 0])
        tip = T[:, 2] > z1 - 0.1 * L; top = (T[:, 1] > np.percentile(T[:, 1], 60)) & ~tip & (T[:, 2] > z0 + 0.3 * L)
        mid = top & (np.abs(T[:, 0] - xm) < 0.12 * w); side = top & (np.abs(T[:, 0] - xm) > 0.28 * w)
        B = np.asarray(g["expression_basis"])[comps][:, tg]  # (n, k, 3)
        A = np.stack([B[:, tip, 1].mean(1), B[:, tip, 2].mean(1), B[:, mid, 1].mean(1) - B[:, side, 1].mean(1)], 0)
        t = np.array([-down, -back, bow]) / float(G["c"]["s"])
        cf = A.T @ np.linalg.solve(A @ A.T + 1e-9 * np.eye(3), t)
        return np.tensordot(cf, np.asarray(g["expression_basis"])[comps], 1)

    def _project(self, d: np.ndarray, name: str) -> dict:
        """Least-squares GNM expression coefficients of a shape's vertex offsets d, over the shape's own regions."""
        G = self._setup()
        R = G["regions"]
        ids = {"mouth": R["lower_face"], "eye": R["left_eye"] + R["right_eye"]}.get(family(name),
                                                                                    R["lower_face"] + R["left_eye"] + R["right_eye"])
        n = min(len(d), G["g"]["expression_basis"].shape[1])
        A = np.asarray(G["g"]["expression_basis"][ids][:, :n], float).reshape(len(ids), -1)
        cf = np.linalg.solve(A @ A.T + 1e-6 * np.eye(len(ids)), A @ np.asarray(d[:n], float).ravel())
        names = G["g"]["expression_names"]
        return {str(names[i]): float(v) for i, v in zip(ids, cf)}

    def shape_coeffs(self, name: str) -> dict:
        """A shape as GNM EXPRESSION COEFFICIENTS {component name: value}: what base.head.expression takes to pose the
        model in that shape (every component then follows: skin, lower teeth, tongue). A shape built as vertex offsets
        (jawOpen, the smile, cheekSquint) is projected on the basis: the nearest parameter mix. NO_COEFFS (a designed
        offset, no expression in GNM) and the eyeLook turns have none: {}."""
        g = self._setup()["g"]
        names = [str(n) for n in g["expression_names"]]
        if family(name) == "look":
            return {}
        if name in faceshapes.NO_COEFFS:
            return {}
        mv, region = self._gnm_moves(name)
        if region is None:
            out = self._project(mv, name)
        else:
            self._solve(mv, region, prior=faceshapes.JAW_PRIOR if name in faceshapes.JAW_PRIORED else faceshapes.SOLVE_RIDGE)
            out = {names[i]: float(v) for i, v in self._last.items()}
        if name == "tongueOut" and self.gnm_mouth:
            out.update({names[i]: float(v) for i, v in self._tongue_out()[1].items()})
        return {k: round(v * self.amount.get(name, 1.0), 5) for k, v in out.items() if abs(v) > 1e-6}

    def _piece_onto(self, X: np.ndarray, dV: np.ndarray, kind: str, lower=None) -> np.ndarray:
        """World offsets of a GNM mouth part's export vertices X (kind "teeth" | "tongue" | "sock") from GNM's own
        offsets dV: inverse distance over the 4 nearest vertices of the GNM piece the vertex belongs to (teeth:
        `lower` (per vertex, True = the lower row) when the part says which row it is, else the nearest piece: a
        tooth row never takes the other row's move)."""
        from scipy.spatial import cKDTree

        from . import base_gnm_parts
        G = self._setup()
        mp = base_gnm_parts.gnm_mouth(self.head)
        dW = self._by_index(dV)  # (a piece takes an expression's offsets as the skin does: base_gnm_parts._gnm_pieces)
        names = {"teeth": ("teeth_upper", "teeth_lower"), "tongue": ("tongue",), "sock": ("sock",)}[kind]
        trees = G.setdefault("piece_trees", {})
        for n in names:
            if n not in trees:
                trees[n] = cKDTree(mp[n]["verts"])
        if kind == "teeth" and lower is not None:
            best = np.asarray(lower, bool).astype(int)
        elif len(names) > 1:
            best = np.argmin(np.stack([trees[n].query(X)[0] for n in names]), 0)
        else:
            best = np.zeros(len(X), int)
        out = np.zeros_like(X)
        for j, n in enumerate(names):
            m = best == j
            if m.any():
                d, i = trees[n].query(X[m], k=4)
                out[m] = (dW[mp[n]["ids"][i]] * self._idw(d)[..., None]).sum(1)
        return out
