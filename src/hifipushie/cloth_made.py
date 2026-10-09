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
         "thickness": 0.0016, "end_round": 0.014, "tilt": 38.0}
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
                near = (np.abs(sd) < reach) & (tang < (0.004 if L.get("sheet") else 1e9))
                if L.get("sheet"):
                    near &= sd > -0.012  # (behind a sheet by more: the sheet's other side, not through it)
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
    S = smooth_rows(S, 3, keep_rows=(0,))
    S[:, 1] = 0.5 * S[:, 1] + 0.5 * smooth_rows(S, 1, keep_rows=())[:, 1]
    st_uv = np.stack([np.repeat(s[:, None], ns + 1, 1), lens], -1).reshape(-1, 2)
    st_V, st_F = S.reshape(-1, 3), grid_faces(n, ns + 1)
    # the stand's own frame at its top: up along its last rows, out = its outward normal
    upt = _unit(S[:, -1] - S[:, -2])
    Tt = _unit(np.gradient(_smooth_curve(S[:, -1]), axis=0))
    outt = _unit(np.cross(Tt, upt))
    outt *= np.sign((outt * out).sum(1))[:, None]
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
    rf = p["fold"]
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
    layers = [{"V": bV, "F": bF}] + [dict(Lc, sheet=True) for Lc in cloth_layers] + [{"V": st_V, "F": st_Fo, "sheet": True}]
    uf = Under(layers, box)
    Dn = _unit(-ca * upt[idx] + sa * side)
    Fl, FN = march(arc[:, -1], Dn, outt[idx], np.c_[np.zeros(len(idx)), lens_f], uf, p["lay"], hug=0.003, step=0.003)
    G = np.concatenate([R[:, None], arc, Fl[:, 1:]], axis=1)
    G = smooth_rows(G, 2, keep_rows=tuple(range(0, na + 1)))
    tail = G[:, na + 1:].reshape(-1, 3)
    tail, _, _ = uf.settle(tail, p["lay"], hug=0.0)
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
                   axis: tuple, top_z: float | None = None, **kw) -> dict:
    """A jacket's notched collar built on its finished neck seam, ONE sheet: at the back a stand rising from the seam
    outside what is worn under it, rolled over, the fall lying down over the seam; from the neck's side the stand
    runs out to nothing where the roll line meets the seam, and past it the collar leaves the seam flat, as the
    continuation of the turned lapel it is sewn to, lying on the forepart / shoulder.
    chain_P: the seam in order (one gorge end, round the back, the other); into: the direction into the cloth each
    seam vertex is sewn to; gorge: which seam vertices are sewn to a turned lapel; inner: layers the stand must clear
    (the under garment, its collar); own: the jacket's own cloth (lapels pressed) the fall lies on; top_z: the stand's
    top at centre back no higher than this (the under collar's top less `show`).
    The sheet's face is the upper collar: toward the neck on the stand, outward on the fall and the ends."""
    p = dict(NOTCHED, **{"end": 0.034, "end_angle": 12.0, "tilt": 30.0})
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
    h = st * np.clip(1 - np.clip(np.abs(a) / am, 0, 1) ** 2.5, 0, 1)
    w = np.clip(h / (0.5 * st), 0, 1)
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
    S, _ = march(C, dir0, outn, np.maximum(lens_s, 1e-6 * np.arange(ns + 1)[None]), u_in, p["off"] * (1 - g) + p["lay"] * g,
                 hug=0.0, step=0.003)
    S[:, 0] = C
    S = smooth_rows(S, 2, keep_rows=(0,))
    upt = np.where((h > 0.004)[:, None], _unit(S[:, -1] - S[:, -2]), dir0)
    upt = _unit(_smooth_curve(upt, 2))
    Tt = _unit(np.gradient(_smooth_curve(S[:, -1]), axis=0))
    outt = _unit(outn - (outn * upt).sum(1)[:, None] * upt)
    R = S[:, -1]
    rf = p["fold"] * w
    thm = np.pi * w
    side = np.sign(a)[:, None] * Tt
    arc = np.zeros((n, na, 3))
    for j in range(1, na + 1):
        t = thm * j / na
        arc[:, j - 1] = R + (rf * (1 - np.cos(t)))[:, None] * outt + (rf * np.sin(t))[:, None] * upt
    arc_len = rf * thm
    d_end = _unit(np.cos(thm)[:, None] * upt + np.sin(thm)[:, None] * outt)
    uu = np.clip(np.abs(a) / half, 0, 1)
    Fw = p["fall"] + (p["end"] - p["fall"]) * (uu * uu * (3 - 2 * uu))
    alpha = np.radians(p["end_angle"]) * uu ** 3
    d_f = _unit(np.cos(alpha)[:, None] * d_end + np.sin(alpha)[:, None] * side)
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
    n0 = _unit(w[:, None] * outt + (1 - w)[:, None] * n_un)
    Fl, FN = march(arc[:, -1], d_f, n0, lens_f, u_f, p["lay"], hug=0.004, step=0.003)
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
    tail = G[:, 1:].reshape(-1, 3)
    tail, _, _ = Under(u_own.layers).settle(tail, p["lay"], hug=0.0)
    G[:, 1:] = tail.reshape(n, -1, 3)
    past = np.maximum(want - (h + arc_len)[:, None], 0)
    uvu = s[:, None] + np.sign(a)[:, None] * np.sin(alpha)[:, None] * past
    uv = np.stack([uvu, want], -1).reshape(-1, 2)
    Vg, Fg = G.reshape(-1, 3), grid_faces(n, m)
    kk = k_cb * m + m - 2
    cf = Fg[np.any(Fg == kk, axis=1)][0]
    if np.cross(Vg[cf[1]] - Vg[cf[0]], Vg[cf[2]] - Vg[cf[0]]) @ out[k_cb] < 0:
        Fg = Fg[:, ::-1]
    info = {"seam_mm": round(L * 1000, 1), "stand_cb_mm": round(st * 1000, 1), "fall_cb_mm": round(p["fall"] * 1000, 1),
            "roll_meets_seam_mm_from_cb": [round(float(am_l) * 1000, 1), round(float(am_r) * 1000, 1)],
            "top_cb_z": round(float(G[k_cb, :, 2].max()), 4), "stations": int(n), "stretch": stretch(Vg, Fg, uv), "params": p}
    return {"parts": [{"name": "collar", "V": Vg, "F": Fg, "uv": uv, "grid": (n, m), "seam_row": np.arange(n) * m}], "info": info}
