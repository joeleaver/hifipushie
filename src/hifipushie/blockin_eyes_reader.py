"""The model's readers (world frame: Z up, faces -Y): slices, chains, `Reader`, the crease's shape, the profile. Part of the block-in's eyes (blockin_eyes.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import blockin_eyes

# ---- the model's readers (world frame: Z up, faces -Y) -----------------------------------------------------------
def _tris(faces):
    out = []
    for f in faces:
        for i in range(1, len(f) - 1):
            out.append((f[0], f[i], f[i + 1]))
    return np.asarray(out, int)


def _slice(V, F, x):
    s = V[:, 0] - x
    sf = s[F]
    pos = sf > 0
    cnt = pos.sum(1)
    sel = (cnt == 1) | (cnt == 2)
    Fs, ss = F[sel], sf[sel]
    segs = []
    for r in range(len(Fs)):
        pts = []
        for e0, e1 in ((0, 1), (1, 2), (2, 0)):
            a, b = ss[r, e0], ss[r, e1]
            if (a > 0) != (b > 0):
                t = a / (a - b)
                pts.append(V[Fs[r, e0]] + t * (V[Fs[r, e1]] - V[Fs[r, e0]]))
        if len(pts) == 2:
            segs.append(pts)
    return segs


def _chain(segs, tol=1e-7):
    from collections import defaultdict
    key = lambda p: tuple(np.round(p / tol).astype(np.int64))  # noqa: E731
    adj, pts = defaultdict(list), {}
    for a, b in segs:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        adj[ka].append(kb)
        adj[kb].append(ka)
        pts[ka], pts[kb] = a, b
    seen, lines = set(), []
    for s in [k for k in adj if len(adj[k]) == 1] + list(adj):
        if s in seen:
            continue
        line, cur = [s], s
        seen.add(s)
        while True:
            nxt = [n for n in adj[cur] if n not in seen]
            if not nxt:
                break
            cur = nxt[0]
            seen.add(cur)
            line.append(cur)
        lines.append(np.array([pts[k] for k in line]))
    return lines


class Reader:
    """Lid margins vs our drawn iris, and the upper lid's sagittal profile (crease, visible platform), on head dicts
    from onemesh_head.head_template (the subject's LEFT eye, +x)."""

    def __init__(self, ht):
        from . import base_identity
        g = base_identity._gnm_data()
        V = np.asarray(ht["verts"], float)
        F = _tris(ht["faces"])
        # the head's rows are GNM's skin vertices in order (+ the lid loops appended): the margin = skin rows next to
        # the eye socket's lining (GNM's eye_sockets group), as the audit's Lids reader
        sk = np.flatnonzero(np.asarray(g["skin"]))
        sock = np.zeros(len(V), bool)
        sock[:len(sk)] = np.asarray(g["groups"]["eye_sockets"])[sk] > 0.5
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
        m = sock[e[:, 0]] != sock[e[:, 1]]
        ring = np.unique(np.where(sock[e[m, 0]], e[m, 1], e[m, 0]))
        c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
        r = float(ht["eye_r"])
        self.ring = ring[np.linalg.norm(V[ring] - c, axis=1) < 2.0 * r]
        self.skin = ~sock
        F = F[np.all(self.skin[F], axis=1)]
        self.tri = F[np.all(np.linalg.norm(V[F] - c, axis=2) < 0.04, axis=1)]

    def read(self, ht):
        V = np.asarray(ht["verts"], float)
        c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
        r = float(ht["eye_r"])
        fwd = np.asarray(ht["forward"], float)
        up = np.array([0, 0, 1.0]) - fwd * fwd[2]
        up /= np.linalg.norm(up)
        lat = np.cross(up, fwd)
        ri = 0.51 * r * 0.985                     # the drawn iris (blockin_lid_measure.lid_model's)
        pole = c + r * fwd
        R = V[self.ring]
        x, z = (R - pole) @ lat, (R - pole) @ up
        near = np.abs(x) < 0.3 * ri
        out = {"r_iris_mm": ri * 1000}

        def at(sel):
            if not sel.any():
                return np.nan
            o = np.argsort(x[sel])
            return float(np.interp(0.0, x[sel][o], z[sel][o]))
        zm = 0.5 * (z.max() + z.min())   # the upper / lower lid split at the opening's middle (a lid may be past the pole)
        zu, zl = at(near & (z > zm)), at(near & (z < zm))
        out["up"], out["lo"] = zu / ri, -zl / ri
        # the upper lid's profile in the plane through the pupil (and +-4 mm): (forward, up), margin first
        res = []
        for dx in (-0.004, 0.0, 0.004):
            x0 = float(pole[0] + dx)
            best = None
            for L in _chain(_slice(V, self.tri, x0)):
                d = np.linalg.norm(L - c, axis=1)
                ok = (d > r + 0.0003) & ((L - c) @ up > -0.001) & ((L - c) @ fwd > 0) & ((L - c) @ up < 0.03)
                runs, cur = [], []
                for i, o in enumerate(ok):
                    if o:
                        cur.append(i)
                    elif cur:
                        runs.append(cur)
                        cur = []
                if cur:
                    runs.append(cur)
                for rr in runs:
                    if best is None or len(rr) > len(best[1]):
                        best = (L, rr)
            if best is None:
                continue
            L, rr = best
            P = np.c_[(L[rr] - c) @ fwd, (L[rr] - c) @ up]
            if P[0, 1] > P[-1, 1]:
                P = P[::-1]
            res.append(_profile(P))
            res[-1]["narrow"] = _profile(P, w_mm=0.75)["lsoft"]
        out["narrow"] = float(np.mean([q["narrow"] for q in res])) if res else 0.0
        if res:
            mid = res[len(res) // 2]
            out.update(show=mid["show"], height=mid["height"], depth=float(np.mean([q["depth"] for q in res])),
                       local=float(np.mean([q["local"] for q in res])),
                       hsoft=float(np.nanmean([q["hsoft"] for q in res])), lsoft=float(np.mean([q["lsoft"] for q in res])),
                       drop=float(np.mean([q["drop"] for q in res])), vis=float(np.nanmean([q["vis"] for q in res])))
        else:
            out.update(show=np.nan, height=np.nan, depth=0.0, local=0.0, hsoft=np.nan, lsoft=0.0, drop=0.0, vis=np.nan)
        return out

    def margins(self, ht, cols=blockin_eyes.RULER_COLS):
        """The eye ruler's measures read straight off the mesh (the subject's left eye; the eye frame: u = mm toward the
        outer corner, v = mm up, from the iris centre = the ball's forward pole; a level front view): the margin ring's
        top / bottom at cols ("up", "lo"; NaN outside the ring), its lateral end ("ring_out": (u, v)), the anatomical
        inner canthus = GNM's lm68 inner corner ("inner": (u, v)), the ring's medial end ("ring_in")."""
        from .eye_ruler import _poly_cross
        V = np.asarray(ht["verts"], float)
        c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
        fwd = np.asarray(ht["forward"], float)
        pole = c + float(ht["eye_r"]) * fwd
        R = (V[self.ring] - pole) * 1000
        uv = np.c_[R[:, 0], R[:, 2]]
        ang = np.arctan2(uv[:, 1] - uv[:, 1].mean(), uv[:, 0] - uv[:, 0].mean())
        poly = uv[np.argsort(ang)]
        up, lo = [], []
        for x in cols:
            ys = _poly_cross(poly, float(x))
            up.append(max(ys) if len(ys) >= 2 else np.nan)
            lo.append(min(ys) if len(ys) >= 2 else np.nan)
        L = (np.asarray(ht["lm68"], float) - pole) * 1000
        io, ii = int(np.argmax(uv[:, 0])), int(np.argmin(uv[:, 0]))
        return {"up": np.array(up), "lo": np.array(lo), "ring_out": uv[io], "ring_in": uv[ii],
                "inner": np.array([L[42, 0], L[42, 2]]), "outer_lm": np.array([L[45, 0], L[45, 2]])}

    def sections(self, ht, fractions=blockin_eyes.SECTION_FR):
        """The upper lid's sagittal sections at fractions of the corner-to-corner width (the subject's left eye, lm68
        42 -> 45), each (forward, up) mm relative to the lid margin at SECTION_S of arclength: (len(fractions), S, 2);
        a column with no section is NaN."""
        V = np.asarray(ht["verts"], float)
        c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
        r = float(ht["eye_r"])
        fwd = np.asarray(ht["forward"], float)
        up = np.array([0, 0, 1.0]) - fwd * fwd[2]
        up /= np.linalg.norm(up)
        L68 = np.asarray(ht["lm68"], float)
        xi, xo = L68[42, 0], L68[45, 0]
        out = np.full((len(fractions), len(blockin_eyes.SECTION_S), 2), np.nan)
        for k, f in enumerate(fractions):
            best = None
            for L in _chain(_slice(V, self.tri, xi + f * (xo - xi))):
                d = np.linalg.norm(L - c, axis=1)
                ok = (d > r + 0.0003) & ((L - c) @ up > -0.004) & ((L - c) @ fwd > -0.004) & ((L - c) @ up < 0.03)
                runs, cur = [], []
                for i, o in enumerate(ok):
                    if o:
                        cur.append(i)
                    elif cur:
                        runs.append(cur)
                        cur = []
                if cur:
                    runs.append(cur)
                for rr in runs:
                    if best is None or len(rr) > len(best[1]):
                        best = (L, rr)
            if best is None:
                continue
            L, rr = best
            P = np.c_[(L[rr] - c) @ fwd, (L[rr] - c) @ up] * 1000
            if P[0, 1] > P[-1, 1]:
                P = P[::-1]
            P = P - P[0]
            dd = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
            s = np.clip(blockin_eyes.SECTION_S, 0, dd[-1])
            out[k] = np.c_[np.interp(s, dd, P[:, 0]), np.interp(s, dd, P[:, 1])]
        return out


def crease_shape(name: str) -> np.ndarray:
    """A crease template's sections (len(SECTION_FR), len(SECTION_S), 2) mm: "fold" | "s376" | "s540"."""
    if not blockin_eyes._SHAPES:
        from pathlib import Path
        z = np.load(Path(__file__).with_name("blockin_crease.npz"))
        blockin_eyes._SHAPES.update({k: z[k] for k in z.files if k not in ("S", "members")})
    if name not in blockin_eyes._SHAPES:
        raise ValueError(f"eye step: no crease template {name!r} (have {', '.join(k for k in blockin_eyes._SHAPES if not k.endswith('_sd'))})")
    return blockin_eyes._SHAPES[name]


def _profile(P, w_mm=2.5, lo=2.0, hi=12.0):
    """A lid profile (forward, up; m; margin first): the crease = the deepest narrow valley 2-12 mm over the margin
    (local depth inside the chord +-w), its height; the visible platform (front view) below the fold."""
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    s = np.arange(0, d[-1], 0.0001)
    Q = np.c_[np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])]
    k = int(round(w_mm / 0.1))
    n = len(Q)
    dep = np.full(n, np.nan)
    for i in range(k, n - k):
        a, b, p = Q[i - k], Q[i + k], Q[i]
        ab = b - a
        Ln = np.linalg.norm(ab)
        if Ln > 1e-9:
            nrm = np.array([ab[1], -ab[0]]) / Ln
            dep[i] = -((p - a) @ nrm)
    h = (Q[:, 1] - Q[0, 1]) * 1000
    # the hood: the fold hanging back DOWN over the platform (the profile drops below the height it had reached); the
    # visible platform ends at the overhang's lowest point (soft arg-max over the drop, tau 0.15 mm)
    drop = np.maximum.accumulate(h) - h
    wd = np.exp((drop - drop.max()) / 0.15)
    hood = (float(drop.max()), float((wd * h).sum() / wd.sum()))   # (its height blends in with the drop: see vis)
    ok = (h > lo) & (h < hi) & np.isfinite(dep)
    if not ok.any():
        return {"local": 0.0, "height": np.nan, "show": float(h.max()) if len(h) else np.nan, "depth": 0.0,
                "hsoft": np.nan, "lsoft": 0.0, "drop": hood[0], "vis": hood[1] if np.isfinite(hood[1]) else float(h.max())}
    # smooth reads for the solver (the arg-max and the visibility jump between valleys): the valley's height and depth as
    # a soft max over the local depth (tau 0.15 mm)
    dd, hh = dep[ok] * 1000, h[ok]
    wv = np.exp((dd - dd.max()) / 0.15)
    hsoft = float((wv * hh).sum() / wv.sum())
    lsoft = float(dd.max() + 0.15 * np.log(wv.mean()))
    i = np.flatnonzero(ok)[np.argmax(dep[ok])]
    above = Q[i:]
    below = Q[:i + 1]
    # visible from the front: a point below the crease shows unless a point of the fold above stands in front of it
    # at (about) the same height
    vis = [q for q in below[::5] if not np.any((np.abs(above[:, 1] - q[1]) < 0.0004) & (above[:, 0] > q[0] + 1e-4))]
    show = (max(q[1] for q in vis) - Q[0, 1]) * 1000 if vis else 0.0
    return {"local": float(dep[i] * 1000), "height": float(h[i]), "show": float(show), "depth": float(dep[i] * 1000),
            "hsoft": hsoft, "lsoft": lsoft, "drop": hood[0],
            # the visible platform: the crease's height without a hood, the overhang's lowest point with one (blended
            # over a 0.1 -> 0.6 mm drop: no jump for the solver)
            "vis": float(hsoft + np.clip((hood[0] - 0.1) / 0.5, 0, 1) * (hood[1] - hsoft))}
