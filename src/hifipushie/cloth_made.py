"""Made pieces CONSTRUCTED on a finished drape (a spike, 2026-10-09: collars first).

A collar's shape comes from interfacing, pressing and a roll line. Held rigid in a sim it keeps every placement error;
draped it stands up or crumples; a 1-2 cm mesh with ~1 mm contact gaps can't hold 2 mm layers or a crisp fold. So the
garment's BODY is simulated and the made piece is built afterwards, as geometry, onto where its seam ended.

One interface for every made piece (collar, stand, lapel flap, cuff, placket, waistband, pocket flap, welt):
  seam    the piece's sewn edge on the drape: the seam's vertices as they ended, in order (`seam_chain`)
  pattern a grid of columns leaving that edge: per column its angle to the edge's normal and the lengths of its rows
          (the 2D outline, in metres: the uv)
  folds   where a column turns over (a roll of radius r about the edge's direction)
  on      what it lies on (`Under`: the body, the garment's own cloth, earlier made pieces), each with a clearance
and one operation, `march`: every column walks its pattern length across those surfaces from the seam, kept a
clearance off them and lying on them where they are near. No solver, no carried pins. Columns keep their pattern
lengths (isometric along a column; across columns as far as the surface is developable: `stretch` reports it).

`press_flap` is the same idea for a flap that is part of a draped piece (a lapel past its roll line): its vertices
are laid as their mirror image across the fold line on the piece's own cloth; no topology changes.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

SHIRT = {"stand": 0.027, "fall_over": 0.012, "points": 0.070, "spread": 32.0, "off": 0.004, "lay": 0.0015,
         "fold": 0.0022, "inset": 0.012, "open": 22.0, "step": 0.006, "rows_stand": 5, "rows_fall": 10,
         "thickness": 0.0016, "end_round": 0.014, "tilt": 12.0, "seam_smooth": 30, "bury": 0.03}
NOTCHED = {"stand": 0.024, "fall": 0.036, "show": 0.014, "lay": 0.002, "fold": 0.003, "step": 0.010, "rows_stand": 4,
           "rows_fall": 7, "thickness": 0.003, "off": 0.003}


def _unit(v):
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def closest(P: np.ndarray, V: np.ndarray, F: np.ndarray, k: int = 16):
    from .closures import _closest_on
    return _closest_on(np.asarray(P, float), V, F, k=k)


def outward(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """A closed mesh's faces wound so their normals point out (signed volume)."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    vol = float((a * np.cross(b, c)).sum())
    return F if vol > 0 else F[:, ::-1]


class Under:
    """What a made piece lies on: layers [{"V", "F" (wound outward), "sheet" (cloth: an open surface), "gap"}]."""

    def __init__(self, layers: list, box=None):
        self.layers = []
        for L in layers:
            V, F = np.asarray(L["V"], float), np.asarray(L["F"])
            if box is not None and len(F):
                c = V[F].mean(1)
                F = F[((c > box[0]) & (c < box[1])).all(1)]
            if len(F):
                self.layers.append(dict(L, V=V, F=F))

    def settle(self, P: np.ndarray, gap, hug: float = 0.0, reach: float = 0.04, rounds: int = 2):
        """P kept `gap` (+ each layer's own) outside every layer, and drawn in to it where a layer is within `hug`
        beyond: (P, the normal of the surface each point lies nearest over, its distance over it)."""
        P = np.array(P, float)
        gap = np.broadcast_to(np.asarray(gap, float), (len(P),))
        nrm = np.zeros_like(P)
        best = np.full(len(P), np.inf)
        for r in range(rounds):
            best[:] = np.inf
            for L in self.layers:
                Q, N, _ = closest(P, L["V"], L["F"])
                dv = P - Q
                sd = (dv * N).sum(1)
                tang = np.linalg.norm(dv - sd[:, None] * N, axis=1)
                g = gap + L.get("gap", 0.0)
                near = (np.abs(sd) < reach) & (tang < (0.008 if L.get("sheet") else 1e9))
                if L.get("sheet"):
                    near &= sd > -L.get("depth", 0.012)  # (behind a sheet by more: the sheet's other side, not through it)
                m = near & (sd < g)
                P[m] += (g[m] - sd[m])[:, None] * N[m]
                over = np.where(near, np.maximum(sd, g) - g, np.inf)
                b = over < best
                best[b], nrm[b] = over[b], N[b]
            if hug > 0 and r == rounds - 1:
                m = (best > 0) & (best < hug)
                P[m] -= best[m][:, None] * nrm[m]
                best[m] = 0.0
        return P, nrm, best


def march(P0, D0, N0, lengths, under: Under, gap, hug: float = 0.010, step: float = 0.003, axis=None,
          lean=None, gap_to=None, gap_over=None):
    """Columns walked from P0 [n, 3] in directions D0 over what is `under`: positions [n, m, 3] at each column's
    cumulative `lengths` [n, m] (measured along the path as walked: a column keeps its pattern length), and the
    surface normals there. gap [n] | scalar: the clearance; `gap_to` [n] with `gap_over` [n]: the clearance eases
    from gap to gap_to over that length (a stand leaving cloth 9 mm off the neck to hug it at 4);
    `lean` [n] = extra clearance per metre walked (a stand's open ends tip away)."""
    P0, D0, N0 = np.asarray(P0, float), _unit(np.asarray(D0, float)), _unit(np.asarray(N0, float))
    lengths = np.asarray(lengths, float)
    n = len(P0)
    gap = np.broadcast_to(np.asarray(gap, float), (n,)).copy()
    K = int(np.ceil(lengths.max() / step)) + 1
    path = np.zeros((K + 1, n, 3))
    pn = np.zeros((K + 1, n, 3))
    cum = np.zeros((K + 1, n))
    p, d, nn = P0.copy(), D0.copy(), N0.copy()
    path[0], pn[0] = p, nn
    for k in range(1, K + 1):
        q = p + step * d
        g = gap.copy()
        if gap_to is not None:
            t = np.clip(cum[k - 1] / np.maximum(gap_over, 1e-6), 0, 1)
            g = gap + (np.asarray(gap_to) - gap) * (t * t * (3 - 2 * t))
        if lean is not None:
            g = g + np.asarray(lean) * cum[k - 1]
        q, nq, over = under.settle(q, g, hug=hug)
        ok = np.isfinite(over) & (over < 1e-6) & ((nq * nn).sum(1) > -0.3)  # touching: lies on that surface
        nn = np.where(ok[:, None], _unit(0.5 * nn + 0.5 * nq), nn)
        dd = q - p
        dl = np.linalg.norm(dd, axis=1)
        dn = _unit(dd)
        dn = np.where(ok[:, None], _unit(dn - (dn * nn).sum(1)[:, None] * nn), d)  # (free: straight on, as cut)
        d = np.where((dl > 0.2 * step)[:, None], dn, d)
        cum[k] = cum[k - 1] + dl
        p = q
        path[k], pn[k] = p, nn
    m = lengths.shape[1]
    X, Nn = np.zeros((n, m, 3)), np.zeros((n, m, 3))
    for i in range(n):
        for a in range(3):
            X[i, :, a] = np.interp(lengths[i], cum[:, i], path[:, i, a])
            Nn[i, :, a] = np.interp(lengths[i], cum[:, i], pn[:, i, a])
    return X, _unit(Nn)


def grid_faces(n: int, m: int, off: int = 0) -> np.ndarray:
    i, j = np.meshgrid(np.arange(n - 1), np.arange(m - 1), indexing="ij")
    a = (i * m + j).ravel() + off
    return np.concatenate([np.c_[a, a + m, a + m + 1], np.c_[a, a + m + 1, a + 1]])


def smooth_rows(X: np.ndarray, passes: int = 2, keep_rows=(0,), w: float = 0.5) -> np.ndarray:
    """A grid [n, m, 3] smoothed along its stations (axis 0), ends and the kept rows held."""
    X = X.copy()
    for _ in range(passes):
        Y = X.copy()
        Y[1:-1] = (1 - w) * X[1:-1] + w * 0.5 * (X[:-2] + X[2:])
        for r in keep_rows:
            Y[:, r] = X[:, r]
        X = Y
    return X


def stretch(V: np.ndarray, F: np.ndarray, uv: np.ndarray) -> dict:
    """Edge lengths as laid over their pattern lengths (1 = isometric)."""
    E = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1), axis=0)
    l3 = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
    l2 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    r = l3[l2 > 1e-5] / l2[l2 > 1e-5]
    return {"p05": round(float(np.percentile(r, 5)), 3), "p50": round(float(np.median(r)), 3),
            "p95": round(float(np.percentile(r, 95)), 3), "max": round(float(r.max()), 3)}


def solid(V: np.ndarray, F: np.ndarray, th: float) -> tuple:
    """A sheet as a closed slab: the sheet, a copy th along its normals' back, a rim round its boundary."""
    vn = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for a in range(3):
        np.add.at(vn, F[:, a], fn)
    vn = _unit(vn)
    n = len(V)
    V2 = np.concatenate([V, V - th * vn])
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(E, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    B = E[cnt[inv.ravel()] == 1]
    rim = np.concatenate([np.c_[B[:, 0], B[:, 0] + n, B[:, 1]], np.c_[B[:, 1], B[:, 0] + n, B[:, 1] + n]])
    return V2, np.concatenate([F, F[:, ::-1] + n, rim])


def seam_chain(V: np.ndarray, M: dict, made: tuple, order: str | None = None, tol: float = 0.0008) -> dict:
    """The sewn edge of the made piece(s) `made` (names) against the rest of the garment, as it ended: {"idx": the
    other side's vertices in order along the made piece's pattern, "P", "made_idx", "s" (pattern arc on the made
    piece)}. From the mesh's sewn pairs when it has them, else from seam vertices lying together (a cleaned result
    welds its seams). `order`: the made piece whose pattern x orders the chain (default the first)."""
    names = list(M["names"])
    piece = np.asarray(M["piece"])
    mk = [names.index(nm) for nm in made if nm in names]
    is_made = np.isin(piece, mk)
    pairs = None
    if M.get("sew") is not None and len(M["sew"]):
        sw = np.asarray(M["sew"]).reshape(-1, 2)
        a, b = is_made[sw[:, 0]], is_made[sw[:, 1]]
        pr = np.concatenate([sw[a & ~b], sw[b & ~a][:, ::-1]])
        if len(pr):
            pairs = pr
    if pairs is None:
        im, io = np.where(is_made)[0], np.where(~is_made)[0]
        d, j = cKDTree(V[io]).query(V[im])
        pairs = np.c_[im[d < tol], io[j[d < tol]]]
    ok = piece[pairs[:, 0]] == names.index(order or made[0])
    pairs = pairs[ok]
    uv = np.asarray(M["uv"])[pairs[:, 0]]
    ax = int(np.argmax(np.ptp(uv, axis=0)))
    o = np.argsort(uv[:, ax])
    pairs, uv = pairs[o], uv[o]
    _, first = np.unique(pairs[:, 0], return_index=True)
    first = np.sort(first)
    pairs, uv = pairs[first], uv[first]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(uv, axis=0), axis=1))]
    return {"idx": pairs[:, 1], "made_idx": pairs[:, 0], "P": 0.5 * (V[pairs[:, 0]] + V[pairs[:, 1]]), "s": s, "uv": uv}


def _stations(P: np.ndarray, col: float) -> tuple:
    """The chain's vertices plus points on its edges so no two stations are further than col apart: (points, arc,
    which are the chain's own)."""
    out, own = [P[0]], [True]
    for a, b in zip(P[:-1], P[1:]):
        k = max(1, int(np.ceil(np.linalg.norm(b - a) / col)))
        for j in range(1, k + 1):
            out.append(a + (b - a) * j / k)
            own.append(j == k)
    out = np.array(out)
    return out, np.r_[0, np.cumsum(np.linalg.norm(np.diff(out, axis=0), axis=1))], np.array(own)


def _smooth_curve(P: np.ndarray, passes: int = 6) -> np.ndarray:
    Q = P.copy()
    for _ in range(passes):
        Q[1:-1] = 0.5 * Q[1:-1] + 0.25 * (Q[:-2] + Q[2:])
    return Q


def _frames(Cs: np.ndarray, axis_p: np.ndarray, axis_d: np.ndarray) -> tuple:
    """Along a neckline: tangent, up the neck (the axis' direction square to the tangent), out from the axis."""
    T = _unit(np.gradient(Cs, axis=0))
    rad = Cs - (axis_p + ((Cs - axis_p) @ axis_d)[:, None] * axis_d)
    out = _unit(rad - (rad * T).sum(1)[:, None] * T)
    up = _unit(axis_d - (T @ axis_d)[:, None] * T)
    up = _unit(up - (up * out).sum(1)[:, None] * out * 0.0)
    return T, up, out


def shirt_collar(chain_P: np.ndarray, body: dict, cloth_layers: list, axis: tuple, **kw) -> dict:
    """A shirt collar worn open, built on a finished neckline. chain_P: the neckline seam's points in order from one
    front end round the back to the other; body {"V", "F"}; cloth_layers: the shirt's own cloth [{"V", "F" wound
    outward}] (what the fall lies on); axis (point, direction) of the neck.
    stand: its height at centre back (rounded off over end_round at its ends), rising from the seam where the seam
    ended and easing to `off` from the neck; `open` deg: how far its ends tip away from the neck (an unbuttoned stand);
    fall: stand + fall_over deep at centre back, folded over the stand's top on a roll of radius `fold`, its leaf
    edge running out to `points` long at the ends, the front edge turned `spread` deg from square to the roll line,
    its ends `inset` short of the stand's; laid `lay` off what is under it.
    -> {"parts": [{"name", "V", "F", "uv", "grid": (n, m)}], "info"} (sheets: `solid` gives them thickness)."""
    p = dict(SHIRT, **{k: v for k, v in kw.items() if v is not None})
    ap, ad = np.asarray(axis[0], float), _unit(np.asarray(axis[1], float))
    C, s, own = _stations(np.asarray(chain_P, float), p["step"])
    n = len(C)
    L = s[-1]
    Cs = _smooth_curve(C)
    T, up, out = _frames(Cs, ap, ad)
    bV, bF = np.asarray(body["V"], float), outward(np.asarray(body["V"], float), np.asarray(body["F"]))
    box = (C.min(0) - 0.22, C.max(0) + 0.22)
    ub = Under([{"V": bV, "F": bF}], box)
    Qb, Nb, _ = closest(C, ub.layers[0]["V"], ub.layers[0]["F"])
    d0 = np.clip(((C - Qb) * Nb).sum(1), 0.0, 0.03)
    e = np.minimum(s, L - s)  # arc from the nearer end
    h = p["stand"] * (0.6 + 0.4 * np.sqrt(np.clip(1 - (1 - np.clip(e / p["end_round"], 0, 1)) ** 2, 0, 1)))
    ns = p["rows_stand"]
    lens = h[:, None] * np.linspace(0, 1, ns + 1)[None, :]
    # the stand rises along the neck's axis from where the seam ended, tipped in so its top comes `off` the neck
    # (a seam lying on the shoulder's slope is centimetres from the neck), its unbuttoned ends tipped out by `open`
    top = Cs + h[:, None] * up
    Qt, _, _ = closest(top, ub.layers[0]["V"], ub.layers[0]["F"])
    dt = ((top - Qt) * out).sum(1)
    tilt = np.arctan2(np.clip(dt - p["off"], -0.004, 0.03), h)
    opn = np.radians(p["open"]) * np.clip(1 - e / (0.28 * L), 0, 1) ** 2
    tilt = np.clip(_smooth_curve(tilt[:, None], 8)[:, 0], np.radians(-8), np.radians(p["tilt"])) - opn
    dirs = _unit(np.cos(tilt)[:, None] * up - np.sin(tilt)[:, None] * out)
    S, SN = march(C, dirs, out, lens, ub, np.minimum(d0, p["off"]), hug=0.0, step=0.003)
    S[:, 0] = C
    ease = (_smooth_curve(C, p["seam_smooth"]) - C)[:, None, :] * (np.linspace(0, 1, ns + 1) ** 0.7)[None, :, None]
    S = S + ease
    S, _, _ = ub.settle(S.reshape(-1, 3), 0.0015)
    S = S.reshape(n, ns + 1, 3)
    S[:, 0] = C
    S = smooth_rows(S, 3, keep_rows=(0,))
    st_uv = np.stack([np.repeat(s[:, None], ns + 1, 1), lens], -1).reshape(-1, 2)
    st_V, st_F = S.reshape(-1, 3), grid_faces(n, ns + 1)
    # the stand's own frame at its top: up along its last rows, out = its outward normal
    upt = _unit(S[:, -1] - S[:, -2])
    Tt = _unit(np.gradient(_smooth_curve(S[:, -1]), axis=0))
    outt = _unit(out - (out * upt).sum(1)[:, None] * upt)
    Tt = _unit(np.cross(upt, outt)) * np.sign((np.cross(upt, outt) * Tt).sum(1))[:, None]
    fn = np.cross(st_V[st_F[:, 1]] - st_V[st_F[:, 0]], st_V[st_F[:, 2]] - st_V[st_F[:, 0]])
    k0 = n // 2 * (ns + 1) + ns // 2
    cf = st_F[np.any(st_F == k0, axis=1)][0]
    sgn = np.sign(np.cross(st_V[cf[1]] - st_V[cf[0]], st_V[cf[2]] - st_V[cf[0]]) @ out[n // 2])
    st_Fo = st_F if sgn > 0 else st_F[:, ::-1]
    # the fall: stations inside the collar's ends
    sel = np.where(e >= p["inset"] - 1e-9)[0]
    i0, i1 = sel[0], sel[-1]
    idx = np.arange(i0, i1 + 1)
    R = S[idx, -1]
    a = s[idx] - 0.5 * (s[i0] + s[i1])  # the roll line's arc from centre back
    Lh = 0.5 * (s[i1] - s[i0])
    f_cb = p["stand"] + p["fall_over"]
    sp = np.radians(p["spread"])
    px, py = p["points"] * np.sin(sp), p["points"] * np.cos(sp)
    u = np.abs(a) / Lh
    x1 = u * (Lh + px)
    b1 = f_cb + (py - f_cb) * (u ** 2.2)
    col = np.hypot(x1 - np.abs(a), b1)
    alpha = np.arctan2(x1 - np.abs(a), b1)
    side = np.sign(a)[:, None] * Tt[idx]  # along the roll line toward this column's own end
    rf = max(p["fold"], 0.5 * (p["lay"] + 2 * p["thickness"]))
    na = 4
    th = np.linspace(0, np.pi, na + 1)[1:]
    ca, sa = np.cos(alpha)[:, None], np.sin(alpha)[:, None]
    arc = np.zeros((len(idx), na, 3))
    for j, t in enumerate(th):
        arc[:, j] = (R + rf * (1 - np.cos(t))[..., None] * outt[idx] + rf * np.sin(t) * ca * upt[idx]
                     + (rf * t) * sa * side)
    arc_len = np.pi * rf
    nf = p["rows_fall"]
    rest = np.maximum(col - arc_len, 0.004)
    lens_f = rest[:, None] * np.linspace(0, 1, nf + 1)[None, 1:]
    layers = [{"V": bV, "F": bF}] + [dict(Lc, sheet=True, depth=p["bury"]) for Lc in cloth_layers] + [{"V": st_V, "F": st_Fo, "sheet": True}]
    uf = Under(layers, box)
    Dn = _unit(-ca * upt[idx] + sa * side)
    lay = p["lay"] + p["thickness"]  # (the sheet is the piece's outer face: its thickness lies under it)
    Fl, FN = march(arc[:, -1], Dn, outt[idx], np.c_[np.zeros(len(idx)), lens_f], uf, lay, hug=0.003, step=0.003)
    G = np.concatenate([R[:, None], arc, Fl[:, 1:]], axis=1)
    G = smooth_rows(G, 2, keep_rows=tuple(range(0, na + 1)))
    tail = G[:, na + 1:].reshape(-1, 3)
    tail, _, _ = uf.settle(tail, lay, hug=0.0)
    G[:, na + 1:] = tail.reshape(len(idx), -1, 3)
    m = G.shape[1]
    frac = np.concatenate([[0.0], np.tile((rf * th)[None], (len(idx), 1))[0] * 0, np.zeros(nf)])  # placeholder
    along = np.concatenate([np.zeros((len(idx), 1)), np.tile(rf * th, (len(idx), 1)), arc_len + lens_f], axis=1)
    tt = along / col[:, None]
    fu = np.sign(a)[:, None] * (np.abs(a)[:, None] + tt * (x1 - np.abs(a))[:, None])
    fv = tt * b1[:, None]
    fa_uv = np.stack([fu, -fv], -1).reshape(-1, 2)
    fa_V, fa_F = G.reshape(-1, 3), grid_faces(len(idx), m)
    c2 = fa_F[len(fa_F) // 4]
    k1 = (len(idx) // 2) * m + m - 2
    cf = fa_F[np.any(fa_F == k1, axis=1)][0]
    nrm = np.cross(fa_V[cf[1]] - fa_V[cf[0]], fa_V[cf[2]] - fa_V[cf[0]])
    if nrm @ FN[len(idx) // 2, -1] < 0:
        fa_F = fa_F[:, ::-1]
    info = {"neckline_mm": round(L * 1000, 1), "stand_mm": round(p["stand"] * 1000, 1), "fall_cb_mm": round(f_cb * 1000, 1),
            "points_mm": round(p["points"] * 1000, 1), "stations": int(n), "seam_vertices": int(own.sum() + 1),
            "stand_off_neck_top_mm": round(float(np.median(((S[:, -1] - closest(S[:, -1], ub.layers[0]["V"], ub.layers[0]["F"])[0]) ** 2).sum(1) ** 0.5) * 1000), 1),
            "stand_stretch": stretch(st_V, st_F, st_uv), "fall_stretch": stretch(fa_V, fa_F, fa_uv), "params": p}
    return {"parts": [{"name": "stand", "V": st_V, "F": st_Fo, "uv": st_uv, "grid": (n, ns + 1), "seam_row": np.arange(n) * (ns + 1)},
                      {"name": "collar", "V": fa_V, "F": fa_F, "uv": fa_uv, "grid": (len(idx), m)}],
            "info": info, "roll": R, "stations": {"s": s, "idx": idx}}


def press_flap(V: np.ndarray, F: np.ndarray, uv: np.ndarray, flap: np.ndarray, line: tuple, lay: float = 0.003,
               wedge: float = 0.35, out: np.ndarray | None = None) -> np.ndarray:
    """A flap of a draped piece PRESSED onto its own cloth across a fold line: each flap vertex goes to its mirror
    image across the line in the pattern, on the piece as it lies (the triangle of the base that holds the image),
    `lay` off it on the side `out` (per-vertex outward normals of the piece; default the faces' own), easing to
    nothing at the line by `wedge` (m of lift per m from the line). V, F, uv: the piece; flap: its vertices past the
    line; line (point, direction) in the pattern. Vertices whose image falls off the base keep the nearest base
    triangle's plane (the flap past the piece's edge lies in the cloth's own plane run on)."""
    p0, d = np.asarray(line[0], float), _unit(np.asarray(line[1], float))
    nrm2 = np.array([-d[1], d[0]])
    rel = uv[flap] - p0
    dist = rel @ nrm2
    img = uv[flap] - 2 * dist[:, None] * nrm2[None]
    isf = np.zeros(len(V), bool)
    isf[flap] = True
    Fb = F[~isf[F].any(1)]
    A, B, C = uv[Fb[:, 0]], uv[Fb[:, 1]], uv[Fb[:, 2]]
    cen = (A + B + C) / 3
    _, cand = cKDTree(cen).query(img, k=min(12, len(Fb)))
    cand = cand.reshape(len(img), -1)
    best = np.full(len(img), -np.inf)
    W = np.zeros((len(img), 3))
    tri = np.zeros(len(img), int)
    for j in range(cand.shape[1]):
        t = cand[:, j]
        v0, v1, v2 = B[t] - A[t], C[t] - A[t], img - A[t]
        den = v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0]
        den = np.where(np.abs(den) > 1e-14, den, 1e-14)
        b1 = (v2[:, 0] * v1[:, 1] - v2[:, 1] * v1[:, 0]) / den
        b2 = (v0[:, 0] * v2[:, 1] - v0[:, 1] * v2[:, 0]) / den
        w = np.c_[1 - b1 - b2, b1, b2]
        q = w.min(1)
        mm = q > best
        best[mm], W[mm], tri[mm] = q[mm], w[mm], t[mm]
    W = np.clip(W, -1.5, 2.5)  # (off the base: the triangle's plane run on, but not far)
    W /= W.sum(1, keepdims=True)
    f = Fb[tri]
    X = (W[:, :, None] * V[f]).sum(1)
    fn = _unit(np.cross(V[f[:, 1]] - V[f[:, 0]], V[f[:, 2]] - V[f[:, 0]]))
    if out is not None:
        fn *= np.sign((fn * out[f].mean(1)).sum(1))[:, None]
    Vn = V.copy()
    Vn[flap] = X + np.minimum(lay, wedge * np.abs(dist))[:, None] * fn
    return Vn


def into_cloth(V: np.ndarray, F: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Per vertex of a seam chain: the unit direction into the cloth it belongs to (toward its mesh neighbours,
    two rings), as the cloth lies."""
    nb = {int(i): set() for i in idx}
    for ring in range(2):
        cur = {i: set(v) | {i} for i, v in nb.items()}
        look = np.unique(np.concatenate([list(v) for v in cur.values()]))
        sel = F[np.isin(F, look).any(1)]
        adj = {}
        for t in sel:
            for a in t:
                adj.setdefault(int(a), set()).update(int(b) for b in t)
        for i in nb:
            for j in list(cur[i]):
                nb[i] |= adj.get(j, set())
            nb[i].discard(i)
    D = np.array([V[list(nb[int(i)])].mean(0) - V[int(i)] if nb[int(i)] else np.zeros(3) for i in idx])
    return _unit(D)


def _dist(under: Under, P: np.ndarray) -> np.ndarray:
    """How far each point stands outside the nearest layer under it (inf where nothing is near)."""
    best = np.full(len(P), np.inf)
    for L in under.layers:
        Q, N, _ = closest(P, L["V"], L["F"])
        dv = P - Q
        sd = (dv * N).sum(1)
        tang = np.linalg.norm(dv - sd[:, None] * N, axis=1)
        ok = (tang < (0.006 if L.get("sheet") else 1e9)) & (sd > -0.02)
        best = np.where(ok & (sd < best), sd, best)
    return best


def notched_collar(chain_P: np.ndarray, into: np.ndarray, gorge: np.ndarray, body: dict, inner: list, own: list,
                   axis: tuple, top_z: float | None = None, pattern: dict | None = None, ends: list | None = None,
                   **kw) -> dict:
    """A jacket's notched collar built on its finished neck seam, ONE sheet: at the back a stand rising from the seam
    outside what is worn under it, rolled over, the fall lying down over the seam; from the neck's side the stand
    runs out to nothing where the roll line meets the seam, and past it the collar leaves the seam flat, as the
    continuation of the turned lapel it is sewn to, lying on the forepart / shoulder.
    chain_P: the seam in order (one gorge end, round the back, the other); into: the direction into the cloth each
    seam vertex is sewn to; gorge: which seam vertices are sewn to a turned lapel; inner: layers the stand must clear
    (the under garment, its collar); own: the jacket's own cloth (lapels pressed) the fall lies on; top_z: the stand's
    top at centre back no higher than this (the under collar's top less `show`).
    The sheet's face is the upper collar: toward the neck on the stand, outward on the fall and the ends.
    pattern (`collar_pattern`: the drafted outline): the columns run from the sewn edge to the outer edge as cut
    (the end edges are the first and last columns: the NOTCH's collar side is the draft's), the stand's height per
    station is the draft's roll line, the uv is the pattern's own.
    ends: [{"side": -1 | +1 (which end, by the chain's order), "edge_a": the collar's sewn edge in its pattern where
    it is sewn to this front (neck point -> gorge end), "edge_b": the front's edge at the same pairs, "uv_a", "uv_b":
    the two pieces' pattern vertices, "line": (point, direction) the lapel's roll line in the front's pattern, "V",
    "F", "uv": the front as it lies with its lapel pressed (F: its base, flap left out), "out": per-vertex outward
    normals, "lay", "wedge", "before", "after"}]: past where the roll line meets the seam the collar is laid as ONE
    surface with the turned lapel: each point carried across the gorge seam into the front's pattern, mirrored
    across the lapel's roll line and laid on the forepart as a board (`on_pattern`), blended in over `before` m
    of seam ahead of the meeting point and `after` m past it."""
    p = dict(NOTCHED, **{"end": 0.034, "end_angle": 12.0, "tilt": 15.0, "stand_power": 2.0})
    p.update({k: v for k, v in kw.items() if v is not None})
    ap, ad = np.asarray(axis[0], float), _unit(np.asarray(axis[1], float))
    Pc = np.asarray(chain_P, float)
    sc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Pc, axis=0), axis=1))]
    C, s, _own = _stations(Pc, p["step"])
    n, L = len(C), s[-1]
    g = np.interp(s, sc, np.asarray(gorge, float))
    g = np.clip(_smooth_curve(g[:, None], 3)[:, 0], 0, 1)
    I = _unit(np.stack([np.interp(s, sc, into[:, k]) for k in range(3)], 1))
    mid = 0.5 * L
    a = s - mid
    half = np.where(a < 0, mid, L - mid)
    lo, hi = (g > 0.5) & (a < 0), (g > 0.5) & (a > 0)
    am_l = mid - s[np.where(lo)[0].max()] if lo.any() else mid
    am_r = s[np.where(hi)[0].min()] - mid if hi.any() else L - mid
    am = np.where(a < 0, am_l, am_r)
    Cs = _smooth_curve(C)
    T, up, out = _frames(Cs, ap, ad)
    bV, bF = np.asarray(body["V"], float), outward(np.asarray(body["V"], float), np.asarray(body["F"]))
    box = (C.min(0) - 0.2, C.max(0) + 0.2)
    u_in = Under([{"V": bV, "F": bF}] + [dict(Lc, sheet=True) for Lc in inner], box)
    st = p["stand"]
    k_cb = int(np.argmin(np.abs(a)))
    if top_z is not None:  # the stand no taller than leaves the under collar showing
        st = float(np.clip((top_z - C[k_cb, 2]) / max(up[k_cb, 2], 0.3), 0.008, st))
    h = st * np.clip(1 - np.clip(np.abs(a) / am, 0, 1) ** p["stand_power"], 0, 1) * (1 - g)
    pat = None
    if pattern is not None:  # the draft's own columns: sewn edge -> outer edge, the stand up to its roll line
        pe = np.asarray(pattern["edge"], float)
        Eu = np.stack([np.interp(s, sc, pe[:, k]) for k in range(2)], 1)
        po = np.asarray(pattern["outer"], float)
        ao = _arc(po)
        Ou = _at_arc(po, s / L * ao[-1])
        colv = Ou - Eu
        coll = np.maximum(np.linalg.norm(colv, axis=1), 1e-6)
        tE = _unit(np.gradient(Eu, axis=0))
        hp = np.zeros(n)
        if pattern.get("roll") is not None:
            pr = np.asarray(pattern["roll"], float)
            rr = np.linspace(0, 1, 160)
            for i in range(n):
                pts = Eu[i] + rr[:, None] * colv[i]
                dd = np.abs(edge_coords(pts, pr)[1])
                sr = edge_coords(pts, pr)[0]
                dd = np.where((sr < 0) | (sr > _arc(pr)[-1]), np.inf, dd)
                j = int(np.argmin(dd))
                hp[i] = rr[j] * coll[i] if dd[j] < 0.0015 else 0.0
        if hp[k_cb] > 1e-4:
            h = hp * min(1.0, st / hp[k_cb])
            st = float(h[k_cb])
        pat = {"E": Eu, "col": colv, "len": coll,
               "alpha": np.arcsin(np.clip(np.sign(a) * (colv / coll[:, None] * tE).sum(1), -0.95, 0.95))}
    w = np.clip(h / 0.008, 0, 1)
    w = w * w * (3 - 2 * w)
    top = Cs + h[:, None] * up
    dt = _dist(u_in, top)
    dt = np.where(np.isfinite(dt), dt, 0.02)
    tilt = np.arctan2(np.clip(dt - p["off"], -0.004, 0.03), np.maximum(h, 0.004))
    tilt = np.clip(_smooth_curve(tilt[:, None], 8)[:, 0], np.radians(-8), np.radians(p["tilt"]))
    d_st = _unit(np.cos(tilt)[:, None] * up - np.sin(tilt)[:, None] * out)
    u_own = Under([{"V": bV, "F": bF}] + [dict(Lc, sheet=True) for Lc in inner] + [dict(Lc, sheet=True) for Lc in own], box)
    _, n_un, _ = u_own.settle(C + 0.004 * out, 0.0)
    n_un = np.where((np.linalg.norm(n_un, axis=1) > 0.5)[:, None], n_un, out)
    flat = _unit(-I - (-I * n_un).sum(1)[:, None] * n_un)  # leaving the seam along the cloth, away from the lapel
    dir0 = _unit((1 - g)[:, None] * d_st + g[:, None] * flat)
    outn = _unit((1 - g)[:, None] * out + g[:, None] * n_un)
    ns, na, nf = p["rows_stand"], 4, p["rows_fall"]
    lens_s = h[:, None] * np.linspace(0, 1, ns + 1)[None]
    S, _ = march(C, d_st, out, np.maximum(lens_s, 1e-6 * np.arange(ns + 1)[None]), u_in, p["off"] * (1 - g) + 0.001 * g,
                 hug=0.0, step=0.003)
    S[:, 0] = C
    S = smooth_rows(S, 2, keep_rows=(0,))
    upt = np.where((h > 0.004)[:, None], _unit(S[:, -1] - S[:, -2]), d_st)
    upt = _unit(_smooth_curve(upt, 2))
    Tt = _unit(np.gradient(_smooth_curve(S[:, -1]), axis=0))
    outt = _unit(outn - (outn * upt).sum(1)[:, None] * upt)
    R = S[:, -1]
    rf = np.minimum(p["fold"], 0.45 * h)
    thm = np.full(n, np.pi)
    side = np.sign(a)[:, None] * Tt
    arc = np.zeros((n, na, 3))
    for j in range(1, na + 1):
        t = thm * j / na
        arc[:, j - 1] = R + (rf * (1 - np.cos(t)))[:, None] * outt + (rf * np.sin(t))[:, None] * upt
    arc_len = rf * thm
    d_end = _unit((1 - g)[:, None] * (-upt) + g[:, None] * flat)
    uu = np.clip(np.abs(a) / half, 0, 1)
    Fw = p["fall"] + (p["end"] - p["fall"]) * (uu * uu * (3 - 2 * uu))
    alpha = np.radians(p["end_angle"]) * uu ** 3
    if pat is not None:
        Fw, alpha = np.maximum(pat["len"] - h, 0.004), pat["alpha"]
    d_f =_unit(np.cos(alpha)[:, None] * d_end + np.sin(alpha)[:, None] * side)
    stand_layer = []
    keep = h > 0.006
    if keep.sum() > 2:
        ks = np.where(keep)[0]
        sV, sF = S[ks[0]:ks[-1] + 1].reshape(-1, 3), grid_faces(ks[-1] - ks[0] + 1, ns + 1)
        fnm = np.cross(sV[sF[:, 1]] - sV[sF[:, 0]], sV[sF[:, 2]] - sV[sF[:, 0]])
        o3 = np.repeat(out[ks[0]:ks[-1] + 1], ns + 1, 0)[sF].mean(1)
        sF = np.where(((fnm * o3).sum(1) < 0)[:, None], sF[:, ::-1], sF)
        stand_layer = [{"V": sV, "F": sF, "sheet": True}]
    u_f = Under(u_own.layers + stand_layer)
    rest = np.maximum(Fw - arc_len, 0.004)
    lens_f = rest[:, None] * np.linspace(0, 1, nf + 1)[None]
    n0 = _unit((1 - g)[:, None] * outt + g[:, None] * n_un)
    lay = p["lay"] + p["thickness"]
    Fl, FN = march(arc[:, -1], d_f, n0, lens_f, u_f, lay, hug=0.004, step=0.003)
    # one polyline per column in pattern length; the rows are read off it
    poly = np.concatenate([S, arc, Fl[:, 1:]], axis=1)
    plen = np.concatenate([lens_s, h[:, None] + arc_len[:, None] * (np.arange(1, na + 1) / na)[None],
                           (h + arc_len)[:, None] + lens_f[:, 1:]], axis=1)
    tot = plen[:, -1]
    m = ns + na + nf + 1
    uni = tot[:, None] * np.linspace(0, 1, m)[None]
    want = w[:, None] * plen + (1 - w)[:, None] * uni
    G = np.zeros((n, m, 3))
    for i in range(n):
        pl = np.maximum.accumulate(plen[i] + 1e-9 * np.arange(m))
        for k in range(3):
            G[i, :, k] = np.interp(want[i], pl, poly[i, :, k])
    G = smooth_rows(G, 2, keep_rows=(0,))
    past = np.maximum(want - (h + arc_len)[:, None], 0)
    uvu = s[:, None] + np.sign(a)[:, None] * np.sin(alpha)[:, None] * past
    uv = np.stack([uvu, want], -1)
    if pat is not None:
        uv = pat["E"][:, None] + pat["col"][:, None] * (want / np.maximum(tot, 1e-9)[:, None])[..., None]
    wE = np.zeros(n)
    einfo = []
    for e in ends or []:
        if pat is None:
            break
        sd_ = float(e["side"])
        ea, eb = np.asarray(e["edge_a"], float), np.asarray(e["edge_b"], float)
        # where the roll line meets the seam: the lapel's roll line through the front's sewn edge
        p0, d2 = np.asarray(e["line"][0], float), _unit(np.asarray(e["line"][1], float))
        n2 = np.array([-d2[1], d2[0]])
        sgn = (eb - p0) @ n2
        kx = int(np.argmin(np.abs(sgn)))
        s_meet_a = _arc(ea)[kx]
        # the stations' arc along this end's edge_a (in the collar's pattern)
        sa_st, _ = edge_coords(pat["E"], ea)
        mine = np.sign(a) == sd_
        t = (sa_st - s_meet_a + e.get("before", 0.03)) / (e.get("before", 0.03) + e.get("after", 0.015))
        t = np.clip(t, 0, 1)
        we = np.where(mine, t * t * (3 - 2 * t), 0.0)
        sel = np.where(we > 0)[0]
        if not len(sel):
            continue
        pts = uv[sel].reshape(-1, 2)
        img = sewn_image(pts, ea, eb, np.asarray(e["uv_a"], float), np.asarray(e["uv_b"], float))
        # ONE fold line: the lapel's roll line run on by the collar's own roll line (carried into the front's pattern)
        xc = p0 + ((eb[kx] - p0) @ d2) * d2
        away = d2 * np.sign((np.asarray(e["uv_b"], float).mean(0) - xc) @ d2)
        fold = [xc + 0.6 * away, xc]
        if pattern.get("roll") is not None:
            pr = np.asarray(pattern["roll"], float)
            sr, _ = edge_coords(pr, ea)
            keep = np.where((sr > 0.004) & (sr < s_meet_a - 0.004))[0]
            if len(keep):
                ri = sewn_image(pr[keep], ea, eb, np.asarray(e["uv_a"], float), np.asarray(e["uv_b"], float))
                ri = ri[np.argsort(-sr[keep])]  # from the meeting point back toward the neck point
                fold += list(ri)
        fold = np.array(fold)
        fs, fd_ = edge_coords(img, fold)
        past_ = edge_coords(pts, ea)[0] > s_meet_a
        flap_side = np.sign(np.median(fd_[past_])) if past_.any() else np.sign(np.median(fd_))
        dist = np.maximum(fd_ * flap_side, 0.0)  # (the collar's end lies on the flap's side of the fold)
        fT = _unit(_at_arc(fold, fs + 1e-4) - _at_arc(fold, fs - 1e-4))
        mir = img - 2 * (dist * flap_side)[:, None] * np.stack([-fT[:, 1], fT[:, 0]], 1)
        X, Nn = on_pattern(np.asarray(e["V"], float), np.asarray(e["F"]), np.asarray(e["uv"], float), mir, e.get("out"),
                           board=e.get("board", 0.02))
        X = X + np.minimum(e.get("lay", 0.003), e.get("wedge", 0.35) * dist)[:, None] * Nn
        X = X.reshape(len(sel), m, 3)
        # the seam row is the seam as it lies (the pressed lapel's own edge): the board is carried onto it
        dl = (C[sel] - X[:, 0])[:, None, :] * np.exp(-(want[sel] / 0.03) ** 2)[..., None]
        einfo.append({"side": sd_, "stations": int(len(sel)), "seam_carry_max_mm": round(float(np.linalg.norm(C[sel] - X[:, 0], axis=1).max()) * 1000, 1),
                      "meets_seam_at_mm": round(float(s_meet_a) * 1000, 1)})
        X = X + dl
        G[sel] = (1 - we[sel])[:, None, None] * G[sel] + we[sel][:, None, None] * X
        wE = np.maximum(wE, we)
    gp = np.where(want[:, 1:] > (h + arc_len)[:, None] + 1e-9, lay, 0.001)
    gp = np.where(wE[:, None] > 0.5, np.minimum(gp, 0.0015 + p["thickness"]), gp)
    if wE.any():
        mix = ((wE > 0) & (wE < 1)).astype(float)
        for _ in range(int(p.get("blend_reach", 2))):
            mix[1:-1] = np.maximum(mix[1:-1], np.maximum(mix[:-2], mix[2:]))
        mix = _smooth_curve(mix[:, None], 2)[:, 0]
        rowf = np.clip(np.arange(m) / 3.0, 0, 1)  # (the seam row stays, the first rows follow it)
        for _ in range(int(p.get("blend_smooth", 5))):  # (two lays meet in the blend: evened along the seam)
            Y = G.copy()
            Y[1:-1] = 0.5 * G[1:-1] + 0.25 * (G[:-2] + G[2:])
            G = G + (mix[:, None, None] * rowf[None, :, None]) * (Y - G)
        he = float(p.get("end_hug", 0.006))
        if he > 0:  # the end lies DOWN on what is under it (a board bridges hollows only that deep)
            en = np.where(wE > 0.5)[0]
            te = G[en, 1:].reshape(-1, 3)
            te, _, _ = Under(u_own.layers).settle(te, gp[en].ravel(), hug=he)
            G[en, 1:] = te.reshape(len(en), -1, 3)
            Y = G.copy()
            Y[1:-1] = 0.5 * G[1:-1] + 0.25 * (G[:-2] + G[2:])
            Y[:, 1:-1] = 0.5 * Y[:, 1:-1] + 0.25 * (Y[:, :-2] + Y[:, 2:])
            G[en[1:-1], 1:] = Y[en[1:-1], 1:]
    tail = G[:, 1:].reshape(-1, 3)
    tail, _, _ = Under(u_own.layers).settle(tail, gp.ravel(), hug=0.0)
    G[:, 1:] = tail.reshape(n, -1, 3)
    uv = uv.reshape(-1, 2)
    Vg, Fg = G.reshape(-1, 3), grid_faces(n, m)
    kk = k_cb * m + m - 2
    cf = Fg[np.any(Fg == kk, axis=1)][0]
    if np.cross(Vg[cf[1]] - Vg[cf[0]], Vg[cf[2]] - Vg[cf[0]]) @ out[k_cb] < 0:
        Fg = Fg[:, ::-1]
    info = {"seam_mm": round(L * 1000, 1), "stand_cb_mm": round(st * 1000, 1), "fall_cb_mm": round(p["fall"] * 1000, 1),
            "roll_meets_seam_mm_from_cb": [round(float(am_l) * 1000, 1), round(float(am_r) * 1000, 1)],
            "top_cb_z": round(float(G[k_cb, :, 2].max()), 4), "stations": int(n), "stretch": stretch(Vg, Fg, uv),
            "ends": einfo, "params": p}
    return {"parts": [{"name": "collar", "V": Vg, "F": Fg, "uv": uv, "grid": (n, m), "seam_row": np.arange(n) * m}], "info": info}


# ---- a made piece's END lying in the plane of the turned flap it is sewn to (a notched collar past its roll line)

def boundary_loop(F: np.ndarray) -> np.ndarray:
    """The longest boundary loop of a piece's triangles, as ordered vertex ids."""
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(E, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    B = E[cnt[inv.ravel()] == 1]
    nxt = {}
    for a, b in B:
        nxt.setdefault(int(a), []).append(int(b))
    best, seen = [], set()
    for a0 in list(nxt):
        if a0 in seen:
            continue
        loop, a = [a0], a0
        seen.add(a0)
        while True:
            cand = [b for b in nxt.get(a, []) if b not in seen]
            if not cand:
                break
            a = cand[0]
            seen.add(a)
            loop.append(a)
        if len(loop) > len(best):
            best = loop
    return np.array(best, np.int64)


def _arc(P: np.ndarray) -> np.ndarray:
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]


def _at_arc(P: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Points at arc lengths s along the polyline P, run on straight past its ends."""
    a = _arc(P)
    s = np.asarray(s, float)
    out = np.stack([np.interp(s, a, P[:, k]) for k in range(P.shape[1])], -1)
    d0, d1 = _unit(P[1] - P[0]), _unit(P[-1] - P[-2])
    lo, hi = s < 0, s > a[-1]
    out[lo] = P[0] + s[lo][:, None] * d0
    out[hi] = P[-1] + (s[hi] - a[-1])[:, None] * d1
    return out


def edge_coords(P: np.ndarray, E: np.ndarray) -> tuple:
    """2D points against a polyline E (run on straight past its ends): (arc along it, signed distance, + to the
    left of its direction)."""
    P, E = np.asarray(P, float), np.asarray(E, float)
    a = _arc(E)
    best = np.full(len(P), np.inf)
    s, d = np.zeros(len(P)), np.zeros(len(P))
    for k in range(len(E) - 1):
        t = E[k + 1] - E[k]
        ln = np.linalg.norm(t)
        t = t / ln
        u = (P - E[k]) @ t
        lo = -np.inf if k == 0 else 0.0
        hi = np.inf if k == len(E) - 2 else ln
        uc = np.clip(u, lo, hi)
        q = E[k] + uc[:, None] * t
        dist = np.linalg.norm(P - q, axis=1)
        m = dist < best
        r = P - E[k]
        sd = t[0] * r[:, 1] - t[1] * r[:, 0]
        best[m], s[m] = dist[m], a[k] + uc[m]
        d[m] = np.where(np.abs(uc - u)[m] < 1e-12, sd[m], np.sign(sd[m] + 1e-15) * dist[m])
    return s, d


def _inside_sign(uv_piece: np.ndarray, E: np.ndarray) -> float:
    """Which side of the edge E the piece's own cloth lies on, next to it (+1 left, -1 right)."""
    a = _arc(E)
    s, d = edge_coords(uv_piece, E)
    m = (s > 0) & (s < a[-1]) & (np.abs(d) > 0.004) & (np.abs(d) < 0.03)
    if not m.any():
        m = (np.abs(d) > 0.002)
    return 1.0 if np.median(d[m]) > 0 else -1.0


def sewn_image(P: np.ndarray, edge_a: np.ndarray, edge_b: np.ndarray, uv_a: np.ndarray, uv_b: np.ndarray) -> np.ndarray:
    """Pattern points P of piece a carried into piece b's pattern across the seam that sews a's edge_a to b's edge_b
    (paired polylines, same order): the same arc along the seam, the same distance from it, on the side of b's edge
    away from b's cloth. (The two pieces laid edge to edge on the table: where a's points lie in b's frame.)"""
    sa, sb = _arc(edge_a), _arc(edge_b)
    s, d = edge_coords(P, edge_a)
    d = d * _inside_sign(uv_a, edge_a)  # > 0: into a's cloth
    sB = np.interp(s, sa, sb) + np.where(s < 0, s, 0) + np.where(s > sa[-1], s - sa[-1], 0)
    Q = _at_arc(edge_b, sB)
    eps = 1e-4
    T = _unit(_at_arc(edge_b, sB + eps) - _at_arc(edge_b, sB - eps))
    left = np.stack([-T[:, 1], T[:, 0]], 1)
    return Q - (d * _inside_sign(uv_b, edge_b))[:, None] * left


def on_pattern(V: np.ndarray, F: np.ndarray, uv: np.ndarray, img: np.ndarray, out: np.ndarray | None = None,
               board: float = 0.02) -> tuple:
    """Where pattern points `img` of a piece lie in space, on the piece as it lies (V, its triangles F, pattern uv):
    (points, unit normals). A BOARD, not the cloth's every wrinkle: a weighted plane fit (Gaussian, `board` m in the
    pattern) through the piece's vertices round each point, so points past the piece's edge lie in its plane run on
    and an interfaced end bridges the hollows of what it lies on. out: per-vertex normals that say which side is up."""
    vid = np.unique(F)
    tree = cKDTree(uv[vid])
    k = min(40, len(vid))
    dd, jj = tree.query(img, k=k)
    X, N = np.zeros((len(img), 3)), np.zeros((len(img), 3))
    for i in range(len(img)):
        sg = max(board, 1.2 * dd[i, min(3, k - 1)])
        w = np.exp(-(dd[i] / sg) ** 2)
        ids = vid[jj[i]]
        A = np.c_[uv[ids] - img[i], np.ones(k)]
        W = w[:, None]
        coef, *_ = np.linalg.lstsq(A * W, V[ids] * W, rcond=None)
        X[i] = coef[2]
        nn = np.cross(coef[0], coef[1])
        if out is not None:
            o = (w[:, None] * out[ids]).sum(0)
            if nn @ o < 0:
                nn = -nn
        N[i] = nn
    return X, _unit(N)


def collar_pattern(uv: np.ndarray, F_piece: np.ndarray, chain_made: np.ndarray, roll_row: np.ndarray | None = None,
                   corner_within: float = 0.07, corner_deg: float = 25.0) -> dict:
    """A collar's drafted outline read off its pattern mesh: {"edge": the sewn (neck) edge's uv in chain order,
    "outer": the outer edge from the corner of the first end to the corner of the last (the end edges are the lines
    edge[0] -> outer[0], edge[-1] -> outer[-1]), "roll": the roll line's uv}."""
    loop = boundary_loop(F_piece)
    ch = np.asarray(chain_made, np.int64)
    pos = {int(v): i for i, v in enumerate(loop)}
    i0, i1 = pos[int(ch[0])], pos[int(ch[-1])]
    n = len(loop)
    fwd = [loop[(i1 + k) % n] for k in range((i0 - i1) % n + 1)]
    bwd = [loop[(i1 - k) % n] for k in range((i1 - i0) % n + 1)]
    inner = set(int(v) for v in ch[1:-1])
    path = fwd if not (set(int(v) for v in fwd) & inner) else bwd
    path = np.array(path[::-1], np.int64)  # from the first end round the outside to the last
    P = uv[path]
    a = _arc(P)

    def corner(Pp, ap):
        best = 0
        for j in range(1, len(Pp) - 1):
            if ap[j] > corner_within:
                break
            u, v = _unit(Pp[j] - Pp[j - 1]), _unit(Pp[j + 1] - Pp[j])
            if np.degrees(np.arccos(np.clip(u @ v, -1, 1))) > corner_deg:
                best = j
        return best
    c0 = corner(P, a)
    c1 = len(P) - 1 - corner(P[::-1], a[-1] - a[::-1])
    return {"edge": uv[ch], "outer": P[c0:c1 + 1], "roll": None if roll_row is None else uv[np.asarray(roll_row, np.int64)]}


# ---- wiring: what cloth.build calls after its clean-up (garment key `construct`)

CONSTRUCT = {"lapels": True, "collar": False, "lapel_lay": 0.003, "wedge": 0.35}


def away(V: np.ndarray, F: np.ndarray, bV: np.ndarray, bFo: np.ndarray) -> np.ndarray:
    """Faces wound so their normals point away from the body (bFo wound outward)."""
    if not len(F):
        return F
    cen = V[F].mean(1)
    Q, N, _ = closest(cen, bV, bFo)
    out = cen - Q
    out = np.where((np.linalg.norm(out, axis=1) > 0.002)[:, None], out, N)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    return np.where(((fn * out).sum(1) < 0)[:, None], F[:, ::-1], F)


def _weld(V: np.ndarray, F: np.ndarray, tol: float = 0.0006) -> np.ndarray:
    pr = cKDTree(V).query_pairs(tol, output_type="ndarray")
    root = np.arange(len(V))

    def find(i):
        while root[i] != i:
            i = root[i]
        return i
    for a_, b_ in pr:
        ra, rb = find(a_), find(b_)
        if ra != rb:
            root[max(ra, rb)] = min(ra, rb)
    rm = np.array([find(i) for i in range(len(V))])
    Fg = rm[F]
    return Fg[(Fg[:, 0] != Fg[:, 1]) & (Fg[:, 1] != Fg[:, 2]) & (Fg[:, 0] != Fg[:, 2])]


def options(g: dict) -> dict | None:
    """The garment's `construct` key resolved (None: nothing is constructed): true / {} = the defaults (lapels
    pressed, the collar as simulated), false = off, {"lapels", "collar", "lapel_lay", "wedge", "collar_options"}."""
    c = g.get("construct", True)
    if c is False or c is None:
        return None
    return dict(CONSTRUCT, **(c if isinstance(c, dict) else {}))


def lapel_flaps(M: dict) -> list:
    """Folds named lapel*: [{"piece", "sel" (its vertices), "flap", "line" (point, direction in the pattern)}]."""
    names, piece, uv = list(M["names"]), np.asarray(M["piece"]), np.asarray(M["uv"])
    out = []
    for fd in M.get("folds") or []:
        if not str(fd.get("name", "")).startswith("lapel") or fd.get("piece") not in names or not fd.get("rows"):
            continue
        sel = np.where(piece == names.index(fd["piece"]))[0]
        row = np.asarray(fd["rows"][0], np.int64)
        p0 = uv[row].mean(0)
        _, _, vt = np.linalg.svd(uv[row] - p0)
        d2 = vt[0]
        sd = (uv[sel] - p0) @ np.array([-d2[1], d2[0]])
        side = 1.0 if (sd > 1e-6).sum() < (sd < -1e-6).sum() else -1.0  # (the flap is the smaller side)
        out.append({"piece": fd["piece"], "sel": sel, "flap": sel[side * sd > 1e-6], "line": (p0, d2)})
    return out


def construct(V: np.ndarray, M: dict, bV: np.ndarray, bT: np.ndarray, g: dict, under: dict | None = None) -> tuple:
    """A finished (cleaned) garment's made parts constructed on its drape: (V, made | None).
    lapels: every flap past a fold named lapel* is PRESSED onto its forepart (`press_flap`: vertices move, ids and
    topology stay, so looks, the scene, the export, the tells and the under garment's tuck all read it).
    collar (off by default): a collar sewn to those fronts is built from its drafted outline (`notched_collar`
    with pattern and ends) as its own mesh: made["parts"] = [{"name", "V", "F", "uv", "thickness", "replaces"}];
    the simulated piece stays in V (hidden by what draws made["parts"]). under: {"V", "F", "made" (per vertex: its
    collar / stand)} the garment worn under it, as it lies."""
    opt = options(g)
    flaps = lapel_flaps(M) if opt else []
    if not opt or not flaps or not (opt["lapels"] or opt["collar"]):
        return V, None
    V = np.array(V, float)
    F = np.asarray(M["F"])
    uv = np.asarray(M["uv"])
    bFo = outward(np.asarray(bV, float), np.asarray(bT))
    made = {"lapels": [], "parts": [], "info": {}}
    for L in flaps:
        Fp = away(V, F[np.isin(F, L["sel"]).all(1)], bV, bFo)
        isf = np.zeros(len(V), bool)
        isf[L["flap"]] = True
        Fb = Fp[~isf[Fp].any(1)]
        if not len(L["flap"]) or not len(Fb):
            continue
        bn = np.zeros_like(V)
        fn = np.cross(V[Fb[:, 1]] - V[Fb[:, 0]], V[Fb[:, 2]] - V[Fb[:, 0]])
        for a_ in range(3):
            np.add.at(bn, Fb[:, a_], fn)
        L.update(Fp=Fp, Fb=Fb, out=_unit(bn))
        before = V[L["flap"]].copy()
        V = press_flap(V, Fp, uv, L["flap"], L["line"], lay=opt["lapel_lay"], wedge=opt["wedge"], out=L["out"])
        made["lapels"].append({"piece": L["piece"], "vertices": int(len(L["flap"])),
                               "moved_mm": round(float(np.median(np.linalg.norm(V[L["flap"]] - before, axis=1))) * 1000, 1)})
    names, piece = list(M["names"]), np.asarray(M["piece"])
    if opt["collar"] and "collar" in names and M.get("sew") is not None and any("Fb" in L for L in flaps):
        mj = piece == names.index("collar")
        ch = seam_chain(V, M, ("collar",))
        Fnc = F[~mj[F].any(1)]
        own = away(V, _weld(V, Fnc), bV, bFo)
        flap_all = np.zeros(len(V), bool)
        for L in flaps:
            flap_all[L["flap"]] = True
        Fc = F[mj[F].all(1)]
        roll = [fd for fd in M.get("folds") or [] if fd.get("piece") == "collar" and fd.get("rows")]
        pat = collar_pattern(uv, Fc, ch["made_idx"], np.asarray(roll[0]["rows"][0], np.int64) if roll else None)
        part = piece[ch["idx"]]
        ends = []
        for L in flaps:
            ii = np.where(part == names.index(L["piece"]))[0]
            if len(ii) < 2 or "Fb" not in L:
                continue
            sd_ = 1.0 if ii.mean() > 0.5 * len(part) else -1.0
            ii = ii if sd_ > 0 else ii[::-1]
            ends.append({"side": sd_, "edge_a": ch["uv"][ii], "edge_b": uv[ch["idx"][ii]], "uv_a": uv[mj], "uv_b": uv[L["sel"]],
                         "line": L["line"], "V": V, "F": L["Fb"], "uv": uv, "out": L["out"], "lay": opt["lapel_lay"]})
        P = V[ch["idx"]]
        c = P.mean(0)
        _, _, vt = np.linalg.svd(P - c)
        ax = vt[2] * np.sign(vt[2][2])
        inner, top_z = [], None
        kw = dict(opt.get("collar_options") or {})
        show = kw.pop("show", NOTCHED["show"])
        if under is not None:
            uV, uF = np.asarray(under["V"], float), np.asarray(under["F"])
            inner = [{"V": uV, "F": away(uV, uF, bV, bFo)}]
            um = under.get("made")
            if um is not None and np.any(um):
                cb = uV[np.asarray(um, bool)]
                cb = cb[(np.abs(cb[:, 0] - c[0]) < 0.025) & (cb[:, 1] > c[1])]
                if len(cb):
                    top_z = float(cb[:, 2].max()) - show
        nc = notched_collar(P, into_cloth(V, F, ch["idx"]), flap_all[ch["idx"]], {"V": np.asarray(bV, float), "F": bFo}, inner,
                            [{"V": V, "F": own}], (c, ax), top_z=top_z, pattern=pat, ends=ends, **kw)
        pt = nc["parts"][0]
        made["parts"].append({"name": "collar", "V": pt["V"], "F": pt["F"], "uv": pt["uv"], "grid": pt["grid"],
                              "thickness": float(nc["info"]["params"]["thickness"]), "replaces": ["collar"]})
        made["info"]["collar"] = {k: v for k, v in nc["info"].items() if k != "params"}
    return V, made


def drawn(res: dict, V: np.ndarray | None = None) -> tuple:
    """What draws a result with constructed parts: (faces of the garment's own mesh to draw: `replaces` pieces left
    out, [(name, V, F) closed slabs of the constructed parts])."""
    M = res["mesh"]
    F = np.asarray(M["F"])
    made = res.get("made") or {}
    parts = []
    hide = np.zeros(len(M["piece"]), bool)
    for pt in made.get("parts") or []:
        for nm in pt.get("replaces") or []:
            if nm in M["names"]:
                hide |= np.asarray(M["piece"]) == list(M["names"]).index(nm)
        parts.append((pt["name"],) + solid(pt["V"], pt["F"], pt["thickness"]))
    return hide, parts
