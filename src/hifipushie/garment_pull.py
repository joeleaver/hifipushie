"""PULL UNTIL IT WOULD STRETCH (C142; Joe 2026-10-21): how people put clothes on and set them, as a tool. "If I were
hand-editing, I'd try to just pull the point out and to the side, and let it go as far as it could without
stretching"; "Think of men pulling their shirts down along the G-line, popping cuffs, women pulling down skirts. It's
not a gravity simulation, it's a flatten-this-along-interesting-geometry without stretching it much thing, and it's how
humans put on clothes." A fitted garment is posed by DRAGGING handles, never by pinning them at guessed coordinates or
by tuning stiffness.

`pull(M, X, held, handles, body=None, ...)` -> (X_new, info):
  - M: the fitted garment's mesh (pattern_form.on_form's "mesh": F, uv (each piece's flat pattern, m), piece, names,
    sew (pairs of vertices sewn together), points ({"piece:point": vertex})); X: its vertex positions (n, 3);
  - held: vertices that don't move (a mask (n,) or indices): what the other hand / the body holds still (the back,
    the sleeves, the fronts below the first fastened button, a tucked waist ...);
  - handles: [{"at": ..., "dir": ..., "side_from": vertex | "piece:point" (optional)}], dragged TOGETHER (one
    distance for all: a symmetric pull keeps the mirror). "at" = what the hand grips, moved as one: a vertex,
    "piece:point", "piece:a..b" (the piece's border from a to b: a hem, a cuff's edge, a front edge) or a list of
    those. "dir" is a vector [x, y, z], a name, or a weighted mix {"side": 1, "out": 0.3, "up": 0.3} (each named
    unit vector x its weight, the sum normalised):
      "side": away from centre front / back (x = 0), the side taken from `side_from` (a landmark well off CF: a
              hinge, a neck point), else from the handle (a group's centroid); refused when that is within SIDE_MIN of
              x = 0 (where a band's two ends cross, the side of a point AT CF flips: the shirt spike's mirror bugs);
      "out": the body's outward normal at the nearest body vertex (needs `body` = (V, F) or an object with V and F/T);
      "up" / "down": +z / -z.
  - body: only for "out" (the solve itself ignores the body: no push-out; it dented the shirt's band).

The solve: per-face as-rigid-as-possible against the FLAT PATTERN (Liu et al. 2008 local / global: each triangle keeps
its own pattern shape; rest = its uv), sewn pairs welded into one vertex, bending free (every bending variant roughened
the shirt's collar, C142). FEW rounds per step on purpose, each from where the cloth was: the cloth moves as little as
it must (early stopping is the regulariser: the shirt pull with every solve run to convergence crumpled the collar to
p95 0.33 mm and stopped 16 mm short; 12 rounds per step keep 0.28). A step that reads over `tol` is re-solved up to
`confirm` more rounds and the CONVERGED read decides (an unconverged solve on a big move reads stretch the cloth
doesn't need: a slack strip stopped at 75 of its 100 mm without it); the few-rounds state is the one kept, and a
confirmed read doesn't lower the least (it is read another way).
First the free cloth relaxes against the pattern with the handles held where they are (`relax_iters`): its stretch is
the START. Then each step moves every handle `step` further along its direction and re-solves (`iters`). The pull
stops at the last step whose stretch is within `tol` of the LEAST stretch reached so far (the start included, read
after `iters`): a pull first takes up slack (the shirt's collar eased 4.41 -> 4.30 % over its first 36 mm), then
meets the knee where it starts to stretch (few-rounds reads 4.51 % at 45 mm, 4.84 at 48, 5.52 at 51, 6.01 at 54;
confirmed, 48 and 51 pass and 54 stops it: 51 mm, y3's place). Or at `max_move`
(reported: nothing stopped it). Last a `settle_iters` solve with the handles held where they stopped.

Stretch = p99 over same-piece edges of |3D length / pattern length - 1|, on `pieces` (default: every piece with a vertex
that is neither held nor a handle: held pieces don't move and would dilute the read).

info: {"moved_mm": {handle: mm}, "stretch_p99_start" / "_least" / "_end" (%), "steps", "stopped" ("stretch" |
"max_move"), "dirs" (unit vectors), "pieces"}. `turn` (below) turns grips about a line first (a band end swung open,
a cuff popped); `hold_mask` builds `held`; `crumple` reads smoothness; `vertices` resolves what a handle grips.

Known answers (tests/test_garment_pull.py): a slack strip pinned at one end, its free end pulled, stops within one
step of where its pattern length runs out; wf_simon's Simon shirt, closed fit, collar points pulled out / side / up,
after its band ends turned 30 deg about Simon's hinges, gives the shirt spike's y3 reads (points 147 apart, 63 / 59
below HPS, collar crumple p95 0.28 mm; y3: 147, 63 / 59, 0.28).
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree

STEP = 0.003  # m: a handle's move per step
TOL = 0.005  # stretch p99 allowed above the least the pull has reached (0.5 %: the shirt's knee, module docstring)
MAX_MOVE = 0.08  # m: the farthest a pull goes
ITERS = 12  # local / global rounds per step, from where the cloth was (few on purpose: module docstring)
RELAX_ITERS = 20  # before a pull / turn: the free cloth relaxed against the pattern
SETTLE_ITERS = 10  # after the pull: the cloth settled with the handles held where they stopped
CONFIRM_ITERS = 120  # a step that reads over tol is re-solved up to this many more rounds before the pull stops there
CONVERGED = 1e-5  # m: the confirm stops early once no vertex moves more than this in a round
SIDE_MIN = 0.015  # m: a "side" is taken only from a point at least this far off x = 0
_HE = ((0, 1, 2), (1, 2, 0), (2, 0, 1))


class FlatARAP:
    """Per-face ARAP against the flat pattern on the WELDED mesh (sewn pairs one vertex). W = welded positions."""

    def __init__(self, M: dict, X: np.ndarray):
        F = np.asarray(M["F"], int)
        uv = np.asarray(M["uv"], float)
        n0 = len(uv)
        par = np.arange(n0)

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        sew = np.asarray(M.get("sew") if M.get("sew") is not None else [], int).reshape(-1, 2)
        for a, b in sew:
            ra, rb = find(a), find(b)
            if ra != rb:
                par[rb] = ra
        root = np.array([find(i) for i in range(n0)])
        _, self.inv = np.unique(root, return_inverse=True)
        self.n = int(self.inv.max()) + 1
        U = uv[F]
        WF = self.inv[F]
        good = (WF[:, 0] != WF[:, 1]) & (WF[:, 1] != WF[:, 2]) & (WF[:, 0] != WF[:, 2])
        e1, e2 = U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]
        good &= np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 1e-10
        self.U, self.WF = U[good], WF[good]
        Wt, I, J = [], [], []
        for a, b, c in _HE:  # cot weight of half-edge (a, b) = 0.5 cot(angle at c), from the rest triangle
            p, q = self.U[:, a] - self.U[:, c], self.U[:, b] - self.U[:, c]
            cot = (p * q).sum(1) / np.maximum(np.abs(p[:, 0] * q[:, 1] - p[:, 1] * q[:, 0]), 1e-12)
            Wt.append(np.clip(0.5 * cot, 1e-4, 5.0))
            I.append(self.WF[:, a])
            J.append(self.WF[:, b])
        self.Wt = np.stack(Wt, 1)
        I, J = np.stack(I, 1).ravel(), np.stack(J, 1).ravel()
        w = self.Wt.ravel()
        Lw = coo_matrix((np.r_[w, w], (np.r_[I, J], np.r_[J, I])), shape=(self.n, self.n)).tocsr()
        self.L = (diags(np.asarray(Lw.sum(1)).ravel()) - Lw).tocsr()
        self._lu = {}

    def weld(self, X: np.ndarray) -> np.ndarray:
        W = np.zeros((self.n, 3))
        np.add.at(W, self.inv, X)
        return W / np.bincount(self.inv, minlength=self.n)[:, None]

    def unweld(self, W: np.ndarray) -> np.ndarray:
        return W[self.inv]

    def welded_mask(self, mask: np.ndarray) -> np.ndarray:
        out = np.zeros(self.n, bool)
        out[self.inv[np.asarray(mask, bool)]] = True
        return out

    def solve(self, Y: np.ndarray, fixed: np.ndarray, iters: int = ITERS, eps: float | None = None) -> np.ndarray:
        """Up to `iters` local / global rounds from Y, stopping once no vertex moves more than `eps` in one; vertices
        `fixed` (welded mask) stay where Y has them."""
        key = np.packbits(fixed).tobytes()
        fi, ci = np.where(~fixed)[0], np.where(fixed)[0]
        if key not in self._lu:
            Lf = self.L[fi]
            self._lu = {key: (splu(Lf[:, fi].tocsc()), Lf[:, ci].tocsr())}  # (one fixed set at a time: the pull's)
        lu, Lfc = self._lu[key]
        U, WF, Wt = self.U, self.WF, self.Wt
        Y = Y.copy()
        for _ in range(iters):
            S = np.zeros((len(WF), 3, 2))
            for k, (a, b, _c) in enumerate(_HE):
                S += Wt[:, k, None, None] * (Y[WF[:, a]] - Y[WF[:, b]])[:, :, None] * (U[:, a] - U[:, b])[:, None, :]
            Uu, _, Vt = np.linalg.svd(S, full_matrices=False)
            R = Uu @ Vt  # (m, 3, 2): each face's closest orthonormal map from its pattern to its current edges
            rhs = np.zeros((self.n, 3))
            for k, (a, b, _c) in enumerate(_HE):
                v = Wt[:, k, None] * np.einsum("mij,mj->mi", R, U[:, a] - U[:, b])
                np.add.at(rhs, WF[:, a], v)
                np.add.at(rhs, WF[:, b], -v)
            r = rhs[fi] - Lfc @ Y[ci]
            Yf = np.column_stack([lu.solve(r[:, k]) for k in range(3)])
            dmax = float(np.abs(Yf - Y[fi]).max()) if len(fi) else 0.0
            Y[fi] = Yf
            if eps is not None and dmax < eps:
                break
        return Y


def edge_stretch(M: dict, X: np.ndarray, pieces=None) -> np.ndarray:
    """|3D length / pattern length - 1| of every same-piece edge (on `pieces`, names or indices, when given)."""
    F = np.asarray(M["F"], int)
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    l0 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    ok = (l0 > 1e-5) & (pid[E[:, 0]] == pid[E[:, 1]])
    if pieces is not None:
        ok &= np.isin(pid[E[:, 0]], _piece_ids(M, pieces))
    E, l0 = E[ok], l0[ok]
    return np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / l0 - 1)


def stretch_p99(M: dict, X: np.ndarray, pieces=None) -> float:
    s = edge_stretch(M, X, pieces)
    return float(np.percentile(s, 99)) if len(s) else 0.0


def _piece_ids(M, pieces):
    nm = list(M["names"])
    return [p if isinstance(p, (int, np.integer)) else nm.index(p) for p in pieces]


def vertex(M: dict, at) -> int:
    """A vertex index, or "piece:point" (M["points"])."""
    if isinstance(at, (int, np.integer)):
        return int(at)
    P = M.get("points") or {}
    if at not in P:
        pre = at.split(":")[0] + ":"
        have = sorted(k for k in P if k.startswith(pre))
        raise ValueError(f"no garment point {at!r} (points on that piece: {', '.join(have) or 'none'})")
    return int(np.asarray(P[at]).reshape(-1)[0])


def vertices(M: dict, at) -> np.ndarray:
    """The vertices a handle grips: a vertex, "piece:point", "piece:a..b" (the piece's border from point a to b, the
    shorter way round: a hem, a cuff's edge, a front edge), or a list of those."""
    if isinstance(at, (list, tuple, np.ndarray)) and not isinstance(at, str):
        return np.unique(np.concatenate([vertices(M, a) for a in at]))
    if isinstance(at, str) and ".." in at:
        from .cloth_release import pin_vertices
        try:
            return np.asarray(pin_vertices(M, at), int)
        except KeyError as e:
            raise ValueError(str(e).strip("'\"")) from None
    return np.array([vertex(M, at)], int)


def _body_vf(body):
    if body is None:
        return None
    if isinstance(body, (tuple, list)):
        return np.asarray(body[0], float), np.asarray(body[1], int)
    return np.asarray(body.V, float), np.asarray(body.T if hasattr(body, "T") else body.F, int)


def body_normal_at(body, p: np.ndarray) -> np.ndarray:
    """The body's outward vertex normal nearest to p (area-weighted face normals)."""
    V, F = _body_vf(body)
    nn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], nn)
    _, j = cKDTree(V).query(p)
    return vn[j] / (np.linalg.norm(vn[j]) + 1e-12)


def direction(d, p: np.ndarray, side_x: float | None = None, body=None) -> np.ndarray:
    """A handle's unit pull direction at p: a vector, a name ("side", "out", "up", "down") or a mix {name: w}."""
    if isinstance(d, str):
        d = {d: 1.0}
    if isinstance(d, dict):
        v = np.zeros(3)
        for k, w in d.items():
            if k == "side":
                sx = p[0] if side_x is None else side_x
                if abs(sx) < SIDE_MIN:
                    raise ValueError(f"'side' from a point {abs(sx) * 1000:.0f} mm off centre (x = 0): take the side "
                                     f"from a landmark well off CF (side_from: a hinge, a neck point), never a point "
                                     f"at CF, where the band's ends cross")
                v += w * np.array([np.sign(sx), 0.0, 0.0])
            elif k == "out":
                if body is None:
                    raise ValueError("'out' (the body normal) needs the body")
                v += w * body_normal_at(body, p)
            elif k in ("up", "down"):
                v += w * np.array([0.0, 0.0, 1.0 if k == "up" else -1.0])
            else:
                raise ValueError(f"no direction {k!r} (side, out, up, down, or a vector [x, y, z])")
    else:
        v = np.asarray(d, float).reshape(3)
    nv = np.linalg.norm(v)
    if nv < 1e-9:
        raise ValueError(f"direction {d!r} is zero")
    return v / nv


def pull(M: dict, X: np.ndarray, held, handles: list[dict], body=None, step: float = STEP, tol: float = TOL,
         max_move: float = MAX_MOVE, iters: int = ITERS, relax_iters: int = RELAX_ITERS,
         settle_iters: int = SETTLE_ITERS, confirm: int = CONFIRM_ITERS, pieces=None, log=None):
    """Drag `handles` until the cloth would stretch (module docstring). Returns (X_new, info)."""
    X = np.asarray(X, float)
    n0 = len(X)
    held = np.asarray(held)
    if held.dtype != bool:
        hm = np.zeros(n0, bool)
        hm[held.astype(int)] = True
        held = hm
    if not handles:
        raise ValueError("handles: at least one {\"at\": ..., \"dir\": ...}")
    A = FlatARAP(M, X)
    Y = A.weld(X)
    groups = [np.unique(A.inv[vertices(M, h["at"])]) for h in handles]  # welded vertices each handle grips
    hv = np.concatenate([vertices(M, h["at"]) for h in handles])
    bad = [str(h["at"]) for h in handles if held[vertices(M, h["at"])].any()]
    if bad:
        raise ValueError("a handle grips held cloth: " + ", ".join(bad))
    fixed = A.welded_mask(held)
    for g in groups:
        fixed[g] = True
    if pieces is None:  # the pieces the pull can change: any with a free vertex
        free = ~held
        free[hv] = False
        pieces = sorted(set(np.asarray(M["piece"])[free].tolist()))
    names = [list(M["names"])[p] if isinstance(p, (int, np.integer)) else p for p in pieces]
    st = lambda W: stretch_p99(M, A.unweld(W), pieces)
    Y = A.solve(Y, fixed, relax_iters)
    s0 = st(Y)
    dirs = []
    for h, g in zip(handles, groups):
        sx = None
        if h.get("side_from") is not None:
            sx = float(X[vertex(M, h["side_from"])][0])
        elif len(g) > 1:
            sx = float(Y[g, 0].mean())
        dirs.append(direction(h.get("dir", "side"), Y[g].mean(0), sx, body))
    pos = [Y[g].copy() for g in groups]
    moved, good, steps, stopped, least = 0.0, Y, 0, "max_move", s0
    while moved + step <= max_move + 1e-9:
        T = good.copy()
        for g, p, d in zip(groups, pos, dirs):
            T[g] = p + (moved + step) * d  # (a handle moves as one: the hand grips it)
        Yt = A.solve(T, fixed, iters)
        s = st(Yt)
        if log:
            log(f"pull step {steps + 1}: {(moved + step) * 1000:.0f} mm, stretch p99 {s * 100:.2f} %")
        confirmed = s > least + tol and confirm
        if confirmed:  # (an unconverged solve on a big move reads stretch the cloth doesn't need: the converged read
            # decides; the few-rounds state is kept, so the cloth still moves as little as it must)
            s = st(A.solve(Yt, fixed, confirm, eps=CONVERGED))
        if s > least + tol:
            stopped = "stretch"
            break
        moved, good, steps = moved + step, Yt, steps + 1
        if not confirmed:  # (the least is read the same way every step: a converged read is lower)
            least = min(least, s)
    Y = A.solve(good, fixed, settle_iters)
    Xn = A.unweld(Y)
    Xn[held] = X[held]  # (held vertices exactly where they were: welding averages a held vertex with its free twin)
    info = {"moved_mm": {str(h["at"]): round(float(np.linalg.norm(Y[g] - p, axis=1).mean()) * 1000, 1)
                         for h, g, p in zip(handles, groups, pos)},
            "stretch_p99_start": round(s0 * 100, 2), "stretch_p99_least": round(least * 100, 2),
            "stretch_p99_end": round(stretch_p99(M, Xn, pieces) * 100, 2), "steps": steps,
            "step_mm": step * 1000, "tol_pct": tol * 100, "stopped": stopped,
            "dirs": {str(h["at"]): np.round(d, 3).tolist() for h, d in zip(handles, dirs)}, "pieces": names}
    return Xn, info


def crumple(M: dict, X: np.ndarray, piece, ring_min: int = 5) -> np.ndarray:
    """Crumple read (mm): each vertex's distance from its one-ring centroid along its normal, on `piece`, fold rows
    and border vertices (fewer than `ring_min` neighbours) left out. Smooth cloth at 2 mm reads ~0.0x; the shirt
    spike's closed collar 0.14 p95, y3 0.28, pinned variants 0.34-0.72."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    k = _piece_ids(M, [piece])[0]
    fold = np.zeros(len(X), bool)
    for fd in M.get("folds") or []:
        for r in fd["rows"]:
            fold[np.asarray(r, int)] = True
    nrm = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    vn = np.zeros_like(X)
    for j in range(3):
        np.add.at(vn, F[:, j], nrm)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    E = E[pid[E[:, 0]] == pid[E[:, 1]]]
    S, c = np.zeros_like(X), np.zeros(len(X))
    np.add.at(S, E[:, 0], X[E[:, 1]])
    np.add.at(S, E[:, 1], X[E[:, 0]])
    np.add.at(c, E[:, 0], 1)
    np.add.at(c, E[:, 1], 1)
    lap = np.abs(((S / np.maximum(c, 1)[:, None] - X) * vn).sum(1)) * 1000
    return lap[(pid == k) & ~fold & (c >= ring_min)]


def _rodrigues(p: np.ndarray, axis: np.ndarray, th: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return p @ (np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K).T


def turn(M: dict, X: np.ndarray, held, turns: list[dict], body=None, steps: int = 6, iters: int = 20,
         relax_iters: int = RELAX_ITERS, pieces=None):
    """TURN what a hand grips about a line, staged (a band end swung open about its hinge, a cuff popped up about its
    fold): each turn {"at": grip (as a pull handle's "at"), "about": [point a, point b] (vertices / "piece:point"),
    "deg": angle, "toward": direction (as a pull's "dir"; default "side") the grip's centroid should start moving
    along (picks the sense), "side_from"?}. The free cloth relaxes against the pattern first, then `steps` steps each
    turn a further deg / steps (grips rigid, held still) and re-solve (`iters`). Returns (X_new, info: start / end
    stretch p99 (%), per turn the sense and how far the grip's centroid went (mm)). Keep the turned grips HELD in a
    following pull (they stay where the hand put them)."""
    X = np.asarray(X, float)
    held = np.asarray(held)
    if held.dtype != bool:
        hm = np.zeros(len(X), bool)
        hm[held.astype(int)] = True
        held = hm
    A = FlatARAP(M, X)
    Y = A.weld(X)
    fixed = A.welded_mask(held)
    plan = []
    for t in turns:
        g = np.unique(A.inv[vertices(M, t["at"])])
        a, b = (Y[A.inv[vertex(M, q)]] for q in t["about"])
        c = Y[g].mean(0)
        sx = float(X[vertex(M, t["side_from"])][0]) if t.get("side_from") is not None else float(a[0] + b[0]) / 2
        d = direction(t.get("toward", "side"), c, sx, body)
        sense = max((1, -1), key=lambda q: float(((a + _rodrigues((c - a)[None], b - a, q * 0.05))[0] - c) @ d))
        plan.append((g, a, b - a, sense * np.radians(t["deg"]), Y[g].copy(), sense))
        fixed[g] = True
    if pieces is None:
        free = ~A.unweld(fixed)
        pieces = sorted(set(np.asarray(M["piece"])[free].tolist()))
    Y = A.solve(Y, fixed, relax_iters)
    s0 = stretch_p99(M, A.unweld(Y), pieces)
    for k in range(1, steps + 1):
        T = Y.copy()
        for g, a, ax, th, p0, _s in plan:
            T[g] = a + _rodrigues(p0 - a, ax, th * k / steps)
        Y = A.solve(T, fixed, iters)
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    info = {"stretch_p99_start": round(s0 * 100, 2), "stretch_p99_end": round(stretch_p99(M, Xn, pieces) * 100, 2),
            "turns": {str(t["at"]): {"sense": s, "moved_mm": round(float(np.linalg.norm(Y[g].mean(0) - p0.mean(0)))
                                                                    * 1000, 1)}
                      for t, (g, _a, _x, _t, p0, s) in zip(turns, plan)}}
    return Xn, info


def hold_mask(M: dict, X: np.ndarray, free, below=None, margin: float = 0.005) -> np.ndarray:
    """What stays still: every piece not in `free`, and on the free pieces whatever lies more than `margin` below
    `below` (z): a garment point "piece:point", or "closure:<name>" = that closure's top fastened button (the shirt's
    fronts below the first button stay closed)."""
    pid = np.asarray(M["piece"])
    held = ~np.isin(pid, _piece_ids(M, free))
    if below:
        if below.startswith("closure:"):
            cn = below.split(":", 1)[1]
            zs = [X[np.asarray(v, int)].mean(0)[2] for c in M.get("closures") or [] if c.get("name") == cn
                  for v in (c.get("v") or [])]
            if not zs:
                have = sorted({c.get("name") for c in M.get("closures") or []})
                raise ValueError(f"no fastened closure {cn!r} (closures: {', '.join(map(str, have)) or 'none'})")
            zb = max(zs)
        else:
            zb = float(X[vertex(M, below)][2])
        held |= X[:, 2] < zb - margin
    return held
