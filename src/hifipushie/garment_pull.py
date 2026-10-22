"""PULL AND SMOOTH UNTIL IT WOULD STRETCH (C142 / C143; Joe 2026-10-21): how people put clothes on and set them, as
tools. "If I were
hand-editing, I'd try to just pull the point out and to the side, and let it go as far as it could without
stretching"; "Think of men pulling their shirts down along the G-line, popping cuffs, women pulling down skirts. It's
not a gravity simulation, it's a flatten-this-along-interesting-geometry without stretching it much thing, and it's how
humans put on clothes." "There's likely a 'smooth' operation ... those are the two main operations to styling the
clothing one is wearing." A fitted garment is posed by DRAGGING handles and smoothing, never by pinning handles at
guessed coordinates or by tuning stiffness. `style(M, X, held, ops)` runs a SEQUENCE of pull / turn / smooth ops
(earlier grips held where they ended; gripping one again picks it up).

`pull(M, X, held, handles, body=None, ...)` -> (X_new, info):
  - M: the fitted garment's mesh (pattern_form.on_form's "mesh": F, uv (each piece's flat pattern, m), piece, names,
    sew (pairs of vertices sewn together), points ({"piece:point": vertex})); X: its vertex positions (n, 3);
  - held: vertices that don't move (a mask (n,) or indices): what the other hand / the body holds still (the back,
    the sleeves, the fronts below the first fastened button, a tucked waist ...);
  - handles: [{"at": ..., "dir": ..., "side_from"?, "patch"?, "turn"?}], dragged TOGETHER (one distance for all:
    a symmetric pull keeps the mirror). "at" = what the hand grips (`grip`): a vertex or "piece:point" grabs an AREA,
    the cloth within `patch` (PATCH, 25 mm on its pattern), and the patch TURNS with the cloth (each step the point is
    dragged alone, the patch's start shape fitted rigidly (Kabsch) onto that solution and pinned, solved again: one
    vertex dragged pinched and twisted the collar's tip, 15-18 % / 60-80 deg; a rigid patch folded the cloth over at
    its edge, 18 / 28 faces); "piece:a..b" (the piece's border from a to b: a hem, a cuff's edge, a front edge) or a
    list moves as one. "dir" is a vector [x, y, z], a name, or a weighted mix {"side": 1, "out": 0.3, "up": 0.3}
    (each named unit vector x its weight, the sum normalised):
      "side": away from centre front / back (x = 0), the side taken from `side_from` (a landmark well off CF: a
              hinge, a neck point), else from the handle (a group's centroid); refused when that is within SIDE_MIN of
              x = 0 (where a band's two ends cross, the side of a point AT CF flips: the shirt spike's mirror bugs);
      "out": the body's outward normal at the nearest body vertex (needs `body` = (V, F) or an object with V and F/T);
      "up" / "down": +z / -z;
      "easy" or {"easy": base}: the cloth chooses: each step probes 9 directions round the base (default "side"),
              tilted toward the body normal / up by 0 / 35 / 70 deg, and takes the least stretch (~9x the time; on the
              shirt's points it went 81 mm with stretch falling). A tangent "along the plane" pulls the leaf taut (the
              shirt's point went 12 mm): a held leaf moves by swinging ACROSS its plane. Don't bake in out / up weights:
              up 0.3 put the shirt's points too high (Joe).
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
"max_move"), "path_mm", "gripped", "dirs" (unit vectors, the last step's), "pieces"}. `turn` turns grips about a line
(a band end swung open, a cuff popped); `smooth` flattens ripples; `hold_mask` builds `held`; reads: `crumple`,
`tip_read` (a point's tip: crumple, stretch max, twist), `folded` (folded-over faces near a point).

Known answers (tests/test_garment_pull.py): a slack strip pinned at one end, its free end pulled, stops within one
step of where its pattern length runs out (and two pulls in a sequence go as far as one); a rippled sheet smooths
without stretching; wf_simon's Simon shirt, closed fit: band ends turned 30 deg about Simon's hinges, collar points
pulled out / side / up (25 mm turning patches), collar + stand smoothed: points 142 apart, 64 / 60 below HPS, collar
crumple p95 0.28 mm, tips as clean as the closed collar's (spike y3: 147, 63 / 59, 0.28).
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
TURN_ROUNDS = 2  # a turning grip: fit-and-pin rounds per step
PATCH = 0.025  # m (pattern): the cloth a point handle grabs round the point (u25)
TURN_PATCH = 0.015  # m (pattern): a turn grips the cloth this near what it names (q40: the band end as an area)
HOLD_ITERS = 20  # a "relax" op's rounds
PROBE_ITERS = 4  # dir "easy": rounds per probed direction
MIRROR_REACH = 0.03  # m: a handle's mirror partner is the one whose lead is this near its mirror image
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


def body_normal_at(body, p: np.ndarray, mirrored: bool = True) -> np.ndarray:
    """The body's outward vertex normal nearest to p (area-weighted face normals). mirrored: averaged with the mirror
    image of the normal at p mirrored across x = 0, so mirrored handles get mirrored directions (the shirt's two "out"
    pulls differed, up 0.38 vs 0.32, and the right collar tip twisted 55-66 deg vs the left's 22)."""
    V, F = _body_vf(body)
    nn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], nn)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    tr = cKDTree(V)
    n = vn[tr.query(p)[1]]
    if mirrored:
        flip = np.array([-1.0, 1.0, 1.0])
        n = n + vn[tr.query(p * flip)[1]] * flip
    return n / (np.linalg.norm(n) + 1e-12)


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


def _mask(held, n0):
    held = np.asarray(held)
    if held.dtype != bool:
        hm = np.zeros(n0, bool)
        hm[held.astype(int)] = True
        held = hm
    return held.copy()


def grip(M: dict, h: dict, held=None, patch_default: float | None = None) -> tuple[np.ndarray, int]:
    """(vertices, lead) a handle grips. A single point grabs the cloth within `patch` of it on its piece's pattern
    (default PATCH: a hand grabs an AREA; one vertex dragged pinched and twisted the collar's tip, C142); a border or a
    list grips those vertices (patch 0 unless given). The lead = the point itself, or the gripped vertex nearest the
    grip's middle on the pattern. A grip overlapping held cloth is REFUSED (the two fight: a corner pull sharing
    vertices with the held band end stretched 280 %, shirt spike). A point's patch TURNS
    with the cloth each step (handle "turn", default on for a point); a border / list moves as one (the hand holds its
    line: a turning border tilted the strip's end in-plane and stopped it 7 mm short)."""
    vs = vertices(M, h["at"])
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    if patch_default is None:
        patch_default = PATCH if len(vs) == 1 else 0.0
    patch = float(h.get("patch", patch_default))
    if len(vs) == 1:
        lead = int(vs[0])
    else:
        c = uv[vs].mean(0)
        lead = int(vs[np.argmin(np.linalg.norm(uv[vs] - c, axis=1))])
    if patch > 0:
        near = np.zeros(len(uv), bool)
        for v in vs:
            near |= (pid == pid[v]) & (np.linalg.norm(uv - uv[v], axis=1) <= patch)
        vs = np.where(near)[0]
    if held is not None and held[vs].any():  # (a grip and a hold on the same cloth fight: 280 % in the shirt spike)
        raise ValueError(f"handle {h['at']!r} grips {int(held[vs].sum())} held vertices (patch {patch * 1000:.0f} mm): "
                         "a grip overlapping a hold tears the cloth between them; shrink its patch, grip elsewhere or "
                         "hold less")
    return np.unique(vs), lead


def _kabsch(P0: np.ndarray, Q: np.ndarray):
    """Proper rotation R and t with R P0 + t ~ Q (det +1: it can't mirror)."""
    a0, b0 = P0.mean(0), Q.mean(0)
    U, _, Vt = np.linalg.svd((P0 - a0).T @ (Q - b0))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    return R, b0 - R @ a0


def _easy_dir(A, Y, fixed, leads, base, body, step, st, probe_iters):
    """'Let the cloth choose' (shirt spike w25): candidates = each handle's base direction tilted toward the body
    normal (+-0 / 35 / 70 deg) or up (+-35 / 70 deg), every handle the same tilt (a symmetric pull stays mirrored);
    each probed with a short solve, the least-stretch one taken for this step."""
    best = None
    for ax in ("n", "u"):
        for ang in (0, 35, -35, 70, -70):
            if (ax == "u" and ang == 0) or (ax == "n" and body is None and ang):
                continue
            cand, T, fx = [], Y.copy(), fixed.copy()
            for w, b in zip(leads, base):
                o = body_normal_at(body, Y[w]) if ax == "n" and body is not None else np.array([0.0, 0.0, 1.0])
                o = o - (o @ b) * b
                o /= np.linalg.norm(o) + 1e-12
                d = np.cos(np.radians(ang)) * b + np.sin(np.radians(ang)) * o
                cand.append(d)
                T[w] = Y[w] + step * d
                fx[w] = True
            s = st(A.solve(T, fx, probe_iters))
            if best is None or s < best[0]:
                best = (s, cand)
    return best[1]


def pull(M: dict, X: np.ndarray, held, handles: list[dict], body=None, step: float = STEP, tol: float = TOL,
         max_move: float = MAX_MOVE, iters: int = ITERS, relax_iters: int = RELAX_ITERS,
         settle_iters: int = SETTLE_ITERS, confirm: int = CONFIRM_ITERS, turn_rounds: int = TURN_ROUNDS,
         probe_iters: int = PROBE_ITERS, mirror: bool = True, pieces=None, log=None):
    """Drag `handles` until the cloth would stretch (module docstring). Returns (X_new, info)."""
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    if not handles:
        raise ValueError("handles: at least one {\"at\": ..., \"dir\": ...}")
    A = FlatARAP(M, X)
    Y = A.weld(X)
    grips = [grip(M, h, held) for h in handles]
    groups = [np.unique(A.inv[vs]) for vs, _ in grips]  # welded vertices each handle grips
    leads = [int(A.inv[ld]) for _, ld in grips]
    li = [int(np.where(g == w)[0][0]) for g, w in zip(groups, leads)]
    turning = [bool(h.get("turn", len(vertices(M, h["at"])) == 1)) and len(g) > 1 for h, g in zip(handles, groups)]
    gripped = np.zeros(len(X), bool)
    for vs, _ in grips:
        gripped[vs] = True
    fixed = A.welded_mask(held)
    if pieces is None:  # the pieces the pull can change: any with a free vertex
        pieces = sorted(set(np.asarray(M["piece"])[~held & ~gripped].tolist()))
    names = [list(M["names"])[p] if isinstance(p, (int, np.integer)) else p for p in pieces]
    st = lambda W: stretch_p99(M, A.unweld(W), pieces)
    fx_all = fixed.copy()
    for g in groups:
        fx_all[g] = True
    Y = A.solve(Y, fx_all, relax_iters)
    s0 = st(Y)
    easy, base = [], []
    for h, g, w in zip(handles, groups, leads):
        d = h.get("dir", "side")
        easy.append(d == "easy" or (isinstance(d, dict) and "easy" in d))
        if easy[-1]:
            d = "side" if d == "easy" else d["easy"]
        sx = float(X[vertex(M, h["side_from"])][0]) if h.get("side_from") is not None else \
            float(Y[g, 0].mean()) if len(g) > 1 else None
        base.append(direction(d, Y[w], sx, body))
    if mirror:  # (mirrored handles pulled the same way: the fit's own asymmetry tilted the two "out"s apart)
        flip = np.array([-1.0, 1.0, 1.0])
        L = np.array([Y[w] for w in leads])
        b0 = [d.copy() for d in base]
        for i in range(len(leads)):
            dj = np.linalg.norm(L - L[i] * flip, axis=1)
            j = int(np.argmin(dj))
            if j != i and dj[j] < MIRROR_REACH:
                v = b0[i] + b0[j] * flip
                base[i] = v / (np.linalg.norm(v) + 1e-12)
    if any(easy) and not all(easy):
        raise ValueError("'easy' is for every handle of a pull or none (they move together)")
    P0 = [Y[g].copy() for g in groups]  # each grip's shape at the start: fitted back on (turned) every step
    tgt = [Y[w].copy() for w in leads]
    dirs = list(base)
    good, steps, stopped, least, path = Y, 0, "max_move", s0, 0.0
    while path + step <= max_move + 1e-9:
        if all(easy) and easy:
            dirs = _easy_dir(A, good, fixed, leads, base, body, step, st, probe_iters)
        tg = [t + step * d for t, d in zip(tgt, dirs)]
        T, fx = good.copy(), fixed.copy()
        for g, p0, i, w, t, tu in zip(groups, P0, li, leads, tg, turning):
            if tu:
                T[w] = t
                fx[w] = True
            else:  # (a border / list grip moves as one: the hand holds its line)
                T[g] = good[g] + (t - good[w])
                fx[g] = True
        Yt = A.solve(T, fx, iters)
        # TURNING GRIP (C142): the lead dragged alone, then each grip's start shape fitted rigidly onto that solution
        # (it turns with the cloth: a rigid translated patch folded the cloth over at its edge), the lead on its
        # target, the grip pinned, solved again
        fx2 = fx.copy()
        for _ in range(turn_rounds if any(turning) else 0):
            T2 = Yt.copy()
            for g, p0, i, t, tu in zip(groups, P0, li, tg, turning):
                if not tu:
                    continue
                R, tr = _kabsch(p0, Yt[g])
                Pn = p0 @ R.T + tr
                T2[g] = Pn + (t - Pn[i])
                fx2[g] = True
            Yt = A.solve(T2, fx2, iters)
        s = st(Yt)
        if log:
            log(f"pull step {steps + 1}: {path * 1000 + step * 1000:.0f} mm, stretch p99 {s * 100:.2f} %")
        confirmed = s > least + tol and confirm
        if confirmed:  # (an unconverged solve on a big move reads stretch the cloth doesn't need: the converged read
            # decides; the few-rounds state is kept, so the cloth still moves as little as it must)
            s = st(A.solve(Yt, fx2, confirm, eps=CONVERGED))
        if s > least + tol:
            stopped = "stretch"
            break
        good, steps, tgt, path = Yt, steps + 1, tg, path + step
        if not confirmed:  # (the least is read the same way every step: a converged read is lower)
            least = min(least, s)
    fx_end = fixed.copy()
    for g in groups:
        fx_end[g] = True
    Y = A.solve(good, fx_end, settle_iters)
    Xn = A.unweld(Y)
    Xn[held] = X[held]  # (held vertices exactly where they were: welding averages a held vertex with its free twin)
    info = {"moved_mm": {str(h["at"]): round(float(np.linalg.norm(Y[w] - p0[i])) * 1000, 1)
                         for h, w, p0, i in zip(handles, leads, P0, li)},
            "path_mm": round(path * 1000, 1),
            "stretch_p99_start": round(s0 * 100, 2), "stretch_p99_least": round(least * 100, 2),
            "stretch_p99_end": round(stretch_p99(M, Xn, pieces) * 100, 2), "steps": steps,
            "step_mm": step * 1000, "tol_pct": tol * 100, "stopped": stopped,
            "gripped": {str(h["at"]): int(len(vs)) for h, (vs, _) in zip(handles, grips)},
            "dirs": {str(h["at"]): np.round(d, 3).tolist() for h, d in zip(handles, dirs)}, "pieces": names}
    return Xn, info


def smooth(M: dict, X: np.ndarray, held, pieces, lam: float = 0.5, iters: int = 6, rounds: int = 20,
           tol: float = TOL, stretch_pieces=None):
    """SMOOTH (C143; Joe: "a 'smooth' operation ... in conjunction with the 'pull' operation ... those are the two
    main operations to styling the clothing one is wearing"): a hand flattening ripples. In the brushed `pieces`
    (minus `held`) alternate (a) fair: each vertex `lam` of the way toward its one-ring centroid ALONG ITS NORMAL only,
    (b) restore: the flat-pattern solve (`iters` rounds) with everything outside the brush held. Stops when the stretch
    (on `stretch_pieces`; default the pull's read, every piece with free cloth) would exceed the least so far + `tol`
    (the pull's rule) or the roughness (p95 of the fair's normal distance, the
    crumple read) stops dropping. Shirt spike sm1: collar + stand roughness p95 0.67 -> 0.32 mm, stretch +0.3 pt.
    Returns (X_new, info: rounds, rough p95 start / end (mm), stretch p99 start / end (%))."""
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    A = FlatARAP(M, X)
    Y = A.weld(X)
    brush = A.welded_mask(np.isin(np.asarray(M["piece"]), _piece_ids(M, pieces)))
    keep = ~brush | A.welded_mask(held)
    WF = A.WF
    Ew = np.unique(np.sort(np.r_[WF[:, [0, 1]], WF[:, [1, 2]], WF[:, [2, 0]]], 1), axis=0)
    cnt = np.zeros(A.n)
    np.add.at(cnt, Ew[:, 0], 1)
    np.add.at(cnt, Ew[:, 1], 1)

    def normal_offset(Yc):
        fn = np.cross(Yc[WF[:, 1]] - Yc[WF[:, 0]], Yc[WF[:, 2]] - Yc[WF[:, 0]])
        vn = np.zeros_like(Yc)
        for k in range(3):
            np.add.at(vn, WF[:, k], fn)
        vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
        S = np.zeros_like(Yc)
        np.add.at(S, Ew[:, 0], Yc[Ew[:, 1]])
        np.add.at(S, Ew[:, 1], Yc[Ew[:, 0]])
        o = ((S / np.maximum(cnt, 1)[:, None] - Yc) * vn).sum(1)
        return o[:, None] * vn, np.abs(o)

    sp = stretch_pieces  # (default: the pull's read, every piece with free cloth: one rule for both operations)
    if sp is None:
        sp = sorted(set(np.asarray(M["piece"])[~held].tolist()))
    st = lambda W: stretch_p99(M, A.unweld(W), sp)
    free = ~keep
    s0 = least = st(Y)
    r0 = rr = float(np.percentile(normal_offset(Y)[1][free], 95))
    k = 0
    for k in range(1, rounds + 1):
        mv, _ = normal_offset(Y)
        T = Y.copy()
        T[free] += lam * mv[free]
        Yt = A.solve(T, keep, iters)
        rt = float(np.percentile(normal_offset(Yt)[1][free], 95))
        s = st(Yt)
        if s > least + tol or rt > rr * 0.995:
            k -= 1
            break
        Y, rr, least = Yt, rt, min(least, s)
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    return Xn, {"rounds": k, "rough_p95_mm": [round(r0 * 1000, 3), round(rr * 1000, 3)],
                "stretch_p99": [round(s0 * 100, 2), round(st(Y) * 100, 2)], "pieces": list(pieces)}


def style(M: dict, X: np.ndarray, held, ops: list[dict], body=None, log=None):
    """Styling as a SEQUENCE of hand moves (C142-C144): ops [{"pull": {"handles": [...], step / tol / max_move ...}}
    | {"turn": {"turns": [...], steps ...}} | {"smooth": {"pieces": [...], lam / rounds / tol ...}} | {"relax":
    {iters}} (the free cloth against its pattern) | {"hold": {...}} (hold_region: kept where it is NOW for every later
    op; relax first: holding the unrelaxed closed collar locked in its strain, p99 7.5 vs 6.1 %; "feather_to": the
    band beyond the hold drawn back after every later pull / turn)], each from where
    the last left the cloth; what a pull or turn gripped is HELD where it ended for every later op (Joe: move these
    apart a little, then push the points a little more); a pull that grips them again picks them up. Returns
    (X_new, [info per op])."""
    X = np.asarray(X, float)
    base = _mask(held, len(X))
    placed = np.zeros(len(X), bool)  # what earlier ops gripped: held where they left it
    feathers = []  # (vertices, share, positions at the hold) of each feathered hold
    infos = []
    for op in ops:
        (kind, a), = op.items()
        a = dict(a)
        if kind == "pull":
            hs = a.pop("handles")
            mine = np.zeros(len(X), bool)
            for h in hs:  # (picking a point up again releases it)
                mine[grip(M, h, base)[0]] = True
            X, inf = pull(M, X, base | (placed & ~mine), hs, body=body, log=log, **a)
            placed |= mine
        elif kind == "turn":
            ts = a.pop("turns")
            mine = np.zeros(len(X), bool)
            for t in ts:  # (the whole gripped area stays where the turn left it, not just the named vertices)
                mine[grip(M, t, None, TURN_PATCH)[0]] = True
            X, inf = turn(M, X, base | (placed & ~mine), ts, body=body, **a)
            placed |= mine
        elif kind == "smooth":
            X, inf = smooth(M, X, base | placed, a.pop("pieces"), **a)
        elif kind == "relax":
            X, inf = relax(M, X, base | placed, **a)
        elif kind == "hold":
            mine = hold_region(M, X, **a)
            placed |= mine
            inf = {"held": int(mine.sum())}
            if a.get("feather_to") is not None:
                fv, fw = feather_weights(M, X, a["pieces"], a["within_deg"], a["feather_to"], a.get("of", "back"),
                                         a.get("center"))
                fv, fw = fv[~(base | placed)[fv]], fw[~(base | placed)[fv]]
                feathers.append((fv, fw, X.copy()))
                inf["feathered"] = int(len(fv))
        else:
            raise ValueError(f"no styling op {kind!r} (pull, turn, smooth, relax, hold)")
        if kind in ("pull", "turn") and feathers:  # (the feathered band drawn back after each move)
            for fv, fw, ref in feathers:
                keep = ~placed[fv]
                X = feather(M, X, base | placed, fv[keep], fw[keep], ref)
        infos.append({kind: inf})
    return X, infos


def relax(M: dict, X: np.ndarray, held, iters: int = HOLD_ITERS):
    """The free (not held) cloth relaxed against its flat pattern (`iters` rounds), nothing gripped. Returns (X_new,
    info: stretch p99 start / end (%), on the pieces with free cloth)."""
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    A = FlatARAP(M, X)
    sp = sorted(set(np.asarray(M["piece"])[~held].tolist()))
    s0 = stretch_p99(M, X, sp)
    Xn = A.unweld(A.solve(A.weld(X), A.welded_mask(held), iters))
    Xn[held] = X[held]
    return Xn, {"stretch_p99": [round(s0 * 100, 2), round(stretch_p99(M, Xn, sp) * 100, 2)]}


def _ring_angle(M: dict, X: np.ndarray, pieces, of: str = "back", center=None) -> np.ndarray:
    """|angle| (deg) of every vertex round a vertical axis through `center`'s x-y centroid (a piece; default the first
    of `pieces`), 0 at CB ("of": "back", +y: the creature faces -y) or CF ("front")."""
    pid = np.asarray(M["piece"])
    c = X[pid == _piece_ids(M, [center or pieces[0]])[0]][:, :2].mean(0)
    ref = {"back": 1.0, "front": -1.0}[of]
    return np.abs(np.degrees(np.arctan2(X[:, 0] - c[0], ref * (X[:, 1] - c[1]))))


def feather_weights(M: dict, X: np.ndarray, pieces, from_deg: float, to_deg: float, of: str = "back",
                    center=None) -> tuple[np.ndarray, np.ndarray]:
    """(vertices, share): `pieces`' vertices between `from_deg` and `to_deg` round the ring, each with a share fading
    1 -> 0 on a cosine ramp across that band (a hand pressing firm at the back, lighter toward the front)."""
    ang = _ring_angle(M, X, pieces, of, center)
    on = np.isin(np.asarray(M["piece"]), _piece_ids(M, pieces))
    v = np.where(on & (ang >= from_deg) & (ang < to_deg))[0]
    t = 1 - (ang[v] - from_deg) / (to_deg - from_deg)
    return v, 0.5 - 0.5 * np.cos(np.pi * t)


def feather(M: dict, X: np.ndarray, held, verts: np.ndarray, share: np.ndarray, ref: np.ndarray, rounds: int = 3,
            iters: int = 8) -> np.ndarray:
    """FEATHERED HOLD (C144, the spike's f2): `rounds` times, each of `verts` drawn its `share` of the way back to `ref`
    (its held position), pinned, the rest re-solved against the pattern. A hard hold border kinked the collar's edge
    (29 deg at the border); feathered from 70 to 130 deg: 18 deg, the sides still hugging."""
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    A = FlatARAP(M, X)
    Y = A.weld(X)
    w = A.welded_mask(held)
    vw = A.inv[verts]
    for _ in range(rounds):
        T = Y.copy()
        cur = A.unweld(Y)[verts]
        tgt = cur + share[:, None] * (ref[verts] - cur)
        acc, cnt = np.zeros((A.n, 3)), np.zeros(A.n)
        np.add.at(acc, vw, tgt)
        np.add.at(cnt, vw, 1)
        m = cnt > 0
        T[m] = acc[m] / cnt[m, None]
        fx = w | m
        Y = A.solve(T, fx, iters)
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    return Xn


def hold_region(M: dict, X: np.ndarray, pieces=None, within_deg: float | None = None, of: str = "back",
                center=None, at=None, feather_to: float | None = None) -> np.ndarray:
    """A region the hand / body keeps still (C144; Joe: the collar "should mostly hug the neck on the back and sides;
    the flare is all toward the front"): the vertices of `pieces` within `within_deg` of CB ("of": "back", +y: the
    creature faces -y) or CF ("front") round a vertical axis through `center` (a piece name: its x-y centroid; default
    the first piece's), plus whatever `at` names (vertex / "piece:point" / "piece:a..b" / a list). Angles read on X
    as it is now. Shirt spike h110 / q40: band + collar within 110 deg of CB held, the side hug 70 mm vs 68 closed
    (unheld: the opened front's slack spread round the ring, the fall 8 / 14 mm further off the neck at CB / side).
    `feather_to` (deg; used by style()): the band from within_deg to feather_to is not held but FEATHERED back after
    each pull / turn (`feather`): a hard border kinked the collar's edge 29 deg (q40); held to 70, feathered to 130:
    18 deg (f2)."""
    X = np.asarray(X, float)
    pid = np.asarray(M["piece"])
    out = np.zeros(len(X), bool)
    if pieces:
        on = np.isin(pid, _piece_ids(M, pieces))
        if within_deg is None:
            out |= on
        else:
            out |= on & (_ring_angle(M, X, pieces, of, center) < within_deg)
    if at is not None:
        out[vertices(M, at)] = True
    return out


def tip_read(M: dict, X: np.ndarray, point, near: float = 0.015, mid: float = 0.04) -> dict:
    """A point's tip (shirt spike tip.py): within `near` (pattern) of the point on its piece, crumple p95 (mm) and edge
    stretch max (%), and the twist (deg) between the cloth's mean normal there and at `mid` from the point (the
    leaf's middle). A point dragged by one vertex: 15-18 % / 60-80 deg; the closed collar 2-3 % / 15-28 deg."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    o = vertex(M, point)
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
    d = np.linalg.norm(uv - uv[o], axis=1)
    on = pid == pid[o]
    nr = on & (d < near) & (c >= 3)
    en = nr[E[:, 0]] & nr[E[:, 1]]
    l0 = np.maximum(np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1), 1e-9)
    stv = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / l0 - 1) * 100
    md = on & (np.abs(d - mid) < 0.005)
    a, b = vn[nr].mean(0), vn[md].mean(0)
    tw = np.degrees(np.arccos(np.clip(abs(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12), -1, 1)))
    return {"crumple_p95_mm": round(float(np.percentile(lap[nr], 95)), 3),
            "stretch_max_pct": round(float(stv[en].max()), 1), "twist_deg": round(float(tw), 1)}


def folded(M: dict, X: np.ndarray, point, radius: float = 0.025, deg: float = 120.0) -> int:
    """Folded-over faces near a point (shirt spike flips.py): faces of the point's piece within `radius` (pattern) whose
    dihedral with an edge neighbour exceeds `deg`, fold rows left out. The closed collar: 0; a rigid patch: 18 / 28."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    o = vertex(M, point)
    fold = np.zeros(len(X), bool)
    for fd in M.get("folds") or []:
        for r in fd["rows"]:
            fold[np.asarray(r, int)] = True
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    fn /= np.linalg.norm(fn, axis=1)[:, None] + 1e-15
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    fi = np.tile(np.arange(len(F)), 3)
    key = np.sort(E, 1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    ks, fs = key[order], fi[order]
    same = (ks[1:] == ks[:-1]).all(1)
    a, b = fs[:-1][same], fs[1:][same]
    e = ks[:-1][same]
    ok = ~(fold[e[:, 0]] & fold[e[:, 1]])
    a, b = a[ok], b[ok]
    ang = np.degrees(np.arccos(np.clip((fn[a] * fn[b]).sum(1), -1, 1)))
    worst = np.zeros(len(F))
    np.maximum.at(worst, a, ang)
    np.maximum.at(worst, b, ang)
    m = (pid[F[:, 0]] == pid[o]) & (np.linalg.norm(uv[F].mean(1) - uv[o], axis=1) < radius)
    return int((m & (worst > deg)).sum())


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
    fold): each turn {"at": grip (as a pull handle's "at"; it grips the cloth within "patch" (TURN_PATCH, 15 mm on the
    pattern) of what it names: the band end's 3 corner vertices turned alone pinched a lobe at its top corner, 21 %
    vs 3 % closed, Joe's arrow), "about": [point a, point b] (vertices / "piece:point"),
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
        g = np.unique(A.inv[grip(M, t, held, TURN_PATCH)[0]])
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


def edge_turns(M: dict, X: np.ndarray, piece: str, mid: str, end: str, center=None, window: float = 0.015,
               skip_deg: float = 12.0, min_deg: float = 15.0) -> dict:
    """The side-view swoop of a piece's free outer edge (shirt spike profile.py; Joe: "one continuous swoop instead of
    three different angles"): the piece's border vertices that aren't sewn, on `end`'s side of `mid` (pattern x),
    ordered from mid; the turn (deg) of the edge's direction in the side plane (y, z) over `window` (m, 3D arc); the
    largest and where it is (deg round the ring from CB about `center`'s centroid), the point's own corner (the last
    `skip_deg`) and the `min_deg` round CB (the two halves meet there: the closed collar turns 19 / 31 deg at CB) left
    out. A hard hold border: 29 deg at 79 deg from CB (q40); feathered: 18 (f2)."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    k = _piece_ids(M, [piece])[0]
    Ek = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    Ek = Ek[(pid[Ek[:, 0]] == k) & (pid[Ek[:, 1]] == k)]
    u, c = np.unique(Ek, axis=0, return_counts=True)
    bv = np.unique(u[c == 1])
    sew = set(np.asarray(M.get("sew") if M.get("sew") is not None else [], int).ravel().tolist())
    outer = np.array([i for i in bv if i not in sew])
    m0, e0 = vertex(M, mid), vertex(M, end)
    o = outer[np.sign(uv[outer, 0] - uv[m0, 0]) == np.sign(uv[e0, 0] - uv[m0, 0])]
    o = o[np.argsort(np.abs(uv[o, 0] - uv[m0, 0]))]
    yz = X[o][:, [1, 2]]
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(X[o], axis=0), axis=1))]
    ang = np.degrees(np.arctan2(X[o, 0] - 0, X[o, 1] - 0))
    if center is not None:
        cc = X[pid == _piece_ids(M, [center])[0]][:, :2].mean(0)
        ang = np.degrees(np.arctan2(X[o, 0] - cc[0], X[o, 1] - cc[1]))
    turns = []
    for i in range(len(o)):
        a = np.searchsorted(arc, arc[i] - window / 2)
        b = np.searchsorted(arc, arc[i] + window / 2) - 1
        if a >= i or b <= i:
            continue
        d1, d2 = yz[i] - yz[a], yz[b] - yz[i]
        t = np.degrees(np.arccos(np.clip(d1 @ d2 / (np.linalg.norm(d1) * np.linalg.norm(d2) + 1e-12), -1, 1)))
        turns.append((t, ang[i]))
    turns = np.array(turns)
    turns = turns[(np.abs(turns[:, 1]) < np.abs(ang[-1]) - skip_deg) & (np.abs(turns[:, 1]) >= min_deg)]
    j = int(np.argmax(turns[:, 0]))
    return {"max_turn_deg": round(float(turns[j, 0]), 1), "at_deg": round(float(turns[j, 1]), 1),
            "p50_deg": round(float(np.median(turns[:, 0])), 1)}
