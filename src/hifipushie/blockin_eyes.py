"""The block-in's EYE step (blockin2, 2026-10-10; Joe: "we shouldn't really ever use our 'fix' [lidfold]. The fact that
it isn't there means we're not using GNM right"). GNM is built so the identity is the person's relaxed neutral and the
eye-region EXPRESSION is the lids' state; its lids have folds as identity + expression configurations (gnm_audit.md
finding 2, the audit's g11_crease_fit). So the eye step is one MAP solve over the identity (170) + GNM's symmetric
eye-region expression (left_k + right_k, k < NE), on the head as it ships (onemesh.head_template: the body's head, our
seated eyeball), driven by what the reference shows:
  - the lid margins against the iris (MediaPipe, iris radii: MRD1 / MRD2 style), sigma 0.05;
  - when the picture shows a fold line: the upper lid's SHAPE, its sections at the inner third / pupil / outer third
    matched to a crease template from GNM's own population (CREASE, sigma SIG_SHAPE; gnmcrease 2: the fold's shape is
    what reads, not its depth or the picture's darkness, which makeup supplies); crease=None keeps the old target (the
    line's height over the lashes vs the model's crease, sigma 0.3 mm, local depth at least D_LINE); hooded (no line):
    the visible platform;
  - the rest of the face held where the block-in put it (68 landmarks off the eyes, sigma 0.3 mm; brows 1 mm);
  - priors: |dc|^2 + |e|^2 (both unit variance).
No lidfold, no lid pose offsets: the result ships as base.head.identity + base.head.expression (eye-region pairs), the
lid pose (lid_upper / lid_lower) cleared.
"""
from __future__ import annotations

import copy

import numpy as np

NE = 20                 # symmetric eye-region expression pairs solved
SIG_LID = 0.05          # iris radii
SIG_TPS = 0.3           # mm
SIG_HOLD = 0.3          # mm (landmarks off the eyes); brows SIG_BROW
SIG_BROW = 1.0
D_LINE = 1.2            # mm: the crease's local depth when the picture shows a line (Tess: 0.7 solved to 0.74 and did not read dressed; 1.2 did)
SIG_LINE = 0.1
DARK_LINE = 0.15        # the picture's fold line darkness above which "a line is there"
HOODED_SHOW = 0.5       # mm: the visible platform when the picture shows no fold line (hooded: the fold covers it)
SIG_HOODED = 0.5
# The crease as a SHAPE (gnmcrease 2; Joe on the sampled heads: #376 / #540 read right dressed, the deepest solve
# (gd_T30, valley 1.64 mm) had the right darkness but the wrong fold). What separates them is the lid's cross-section,
# not depth or the picture's darkness: a low crease (2.4-3 mm over the margin), a short platform (1.7-2.4 mm) that
# barely recedes, and a full fold coming forward above it, the fold line parallel to the lashes; gd_T30 was a sunken lid
# (the platform 4 mm back into the socket, the crease the floor of the hollow at 5 mm). So when the picture shows a
# line, the step matches the upper lid's sections (inner third / pupil / outer third, relative to the lid margin,
# arclength 0.5-8 mm) to a template from GNM's own population (CREASE_SHAPES, blockin_crease.npz: "fold" = the mean of
# the 30 / 1200 sampled heads with a low, narrow, parallel crease; "s376" / "s540" = Joe's two). Any darkness still
# missing dressed is cosmetics (skin.makeup eyeshadow "crease"), not geometry.
CREASE = "s376"         # the default template when the picture shows a line ("fold" read puffier on Tess, gk_06; None: the old height + depth target)
SIG_SHAPE = 0.3         # mm per section point
SIG_LID_SHAPE = 0.02    # iris radii: the lid margins held harder with the shape term on (72 section points pulled the
                        # upper lid open 0.64 -> 0.75 vs the picture's 0.67 at SIG_LID)
SECTION_FR = (0.25, 0.5, 0.75)        # inner third, pupil, outer third (corner to corner)
SECTION_S = np.arange(0.5, 12.01, 0.5)  # mm of arclength from the lid margin (12: to 8 the lid matched but the fold's arc did not read)
SOCKET = ("orbital_rim", "lower_orbit", "eye_depth")   # the socket's readings held (humanmacro, population sd, on the
SIG_SOCKET = 0.15       # mesh WITH the expression): unheld, lt19's fold came with orbital_rim +1.1 / lower_orbit -0.9 sd
HOLD = [i for i in range(68) if not (36 <= i < 48 or 17 <= i < 27)]
BROWS = list(range(17, 27))


def _names():
    from . import base as basemod
    n = [str(x) for x in basemod._gnm_data()["expression_names"]]
    return [f"left_eye_region_{k:03d}" for k in range(NE)], [f"right_eye_region_{k:03d}" for k in range(NE)], n


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
    from onemesh.head_template (the subject's LEFT eye, +x)."""

    def __init__(self, ht):
        from . import base as basemod
        g = basemod._gnm_data()
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
        ri = 0.51 * r * 0.985                     # the drawn iris (blockin.lid_model's)
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
        if res:
            mid = res[len(res) // 2]
            out.update(show=mid["show"], height=mid["height"], depth=float(np.mean([q["depth"] for q in res])),
                       local=float(np.mean([q["local"] for q in res])),
                       hsoft=float(np.nanmean([q["hsoft"] for q in res])), lsoft=float(np.mean([q["lsoft"] for q in res])),
                       drop=float(np.mean([q["drop"] for q in res])), vis=float(np.nanmean([q["vis"] for q in res])))
        else:
            out.update(show=np.nan, height=np.nan, depth=0.0, local=0.0, hsoft=np.nan, lsoft=0.0, drop=0.0, vis=np.nan)
        return out

    def sections(self, ht, fractions=SECTION_FR):
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
        out = np.full((len(fractions), len(SECTION_S), 2), np.nan)
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
            s = np.clip(SECTION_S, 0, dd[-1])
            out[k] = np.c_[np.interp(s, dd, P[:, 0]), np.interp(s, dd, P[:, 1])]
        return out


_SHAPES: dict = {}


def crease_shape(name: str) -> np.ndarray:
    """A crease template's sections (len(SECTION_FR), len(SECTION_S), 2) mm: "fold" | "s376" | "s540"."""
    if not _SHAPES:
        from pathlib import Path
        z = np.load(Path(__file__).with_name("blockin_crease.npz"))
        _SHAPES.update({k: z[k] for k in z.files if k not in ("S", "members")})
    if name not in _SHAPES:
        raise ValueError(f"eye step: no crease template {name!r} (have {', '.join(k for k in _SHAPES if not k.endswith('_sd'))})")
    return _SHAPES[name]


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


# ---- the picture's evidence ----------------------------------------------------------------------------------------

def photo_evidence(img, view: dict) -> dict:
    """{"up", "lo"} (iris radii, both eyes' mean), {"tps" (mm at the 11.7 mm iris), "dark"} (median over the middle
    columns of both eyes), from MediaPipe + lidfold.read_lid on the front picture."""
    from . import blockin as bi, lidfold
    lp = bi.lid_photo(img, view)
    if not lp:
        raise ValueError("eye step: the detector found no face (irises) on the front picture")
    P = np.asarray(bi.detect_view(img, view), float)
    cols = lidfold.read_lid(img, P)
    tps = [c["tps"] for e in cols for c in e if np.isfinite(c.get("tps", np.nan)) and c.get("dark", 0) >= DARK_LINE]
    dk = [c["dark"] for e in cols for c in e]
    hooded = len(tps) < 2   # no fold line in most columns: the fold hangs over the platform
    # the fold line's path across the lid: per column (inner third, pupil, outer third), both eyes' lines that read
    tcols = []
    for k in range(3):
        v = [e[k]["tps"] for e in cols if np.isfinite(e[k].get("tps", np.nan)) and e[k].get("dark", 0) >= DARK_LINE]
        tcols.append(float(np.median(v)) if v else np.nan)
    return {"up": float(np.mean([lp[s]["upper"] for s in lp])), "lo": float(np.mean([lp[s]["lower"] for s in lp])),
            "tps": float(np.median(tps)) if not hooded else HOODED_SHOW, "dark": float(np.median(dk)) if dk else 0.0,
            "hooded": hooded, "tps_cols": tcols, "columns": cols}


def crease_target(name: str, heights) -> np.ndarray:
    """A crease template's PROFILE carried to the picture's fold line: per section, the template's crease (its most
    recessed point 1.2-6 mm up) is moved to heights[k] (mm over the margin; NaN: the template's own) by stretching the
    platform under it vertically and lifting the fold above it unchanged, then resampled at SECTION_S. The fold's make
    (crest over the crease, a short platform that doesn't recede, the line parallel to the lashes) comes from the
    template, its height and path from the picture (gnmcrease 2: the templates' own height, ~2.5 mm, was #376's, not the
    person's)."""
    T = crease_shape(name)
    out = np.empty_like(T)
    for k in range(len(T)):
        P = np.r_[[[0.0, 0.0]], T[k]]
        low = (P[:, 1] > 1.2) & (P[:, 1] < 6.0)
        ic = int(np.argmin(np.where(low, P[:, 0], np.inf)))
        hc = P[ic, 1]
        H = float(heights[k]) if heights is not None and np.isfinite(heights[k]) else hc
        Q = P.copy()
        f = max(H, 0.5) / max(hc, 0.3)
        Q[:ic + 1, 1] *= f
        Q[ic + 1:, 1] += (f - 1.0) * hc
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        s = np.clip(SECTION_S, 0, d[-1])
        out[k] = np.c_[np.interp(s, d, Q[:, 0]), np.interp(s, d, Q[:, 1])]
    return out


def socket(c, expression: dict) -> dict:
    """The socket readings (SOCKET, humanmacro z-scores) of identity c with the head's expression applied: GNM's mesh
    (humanmacro.head) + the expression basis, so a lid tucked back by the eye-region expression counts."""
    from . import base as basemod, humanmacro as hm
    g = basemod._gnm_data()
    names = {str(n): i for i, n in enumerate(g["expression_names"])}
    V = hm.head(np.asarray(c, float))
    for k, v in (expression or {}).items():
        if v and k in names:
            if k not in _EB:
                B = np.asarray(g["expression_basis"][names[k]], float)
                _EB[k] = np.stack([B[..., 0], -B[..., 2], B[..., 1]], -1)   # (humanmacro's world frame)
            V = V + float(v) * _EB[k]
    z = hm.read(V=V)
    return {k: float(z[k]) for k in SOCKET}


_EB: dict = {}


# ---- the solve -----------------------------------------------------------------------------------------------------

def _head(base, c, e, Ln, Rn):
    from . import blockin as bi, onemesh
    b = copy.deepcopy(base)
    bi.set_identity({"base": b}, c)
    ex = {**{Ln[k]: round(float(e[k]), 6) for k in range(NE)}, **{Rn[k]: round(float(e[k]), 6) for k in range(NE)}}
    b["head"]["expression"] = {k: v for k, v in ex.items() if v}
    ht = onemesh.head_template(b)
    for kk in [k for k in onemesh._CACHE if isinstance(k, tuple) and k and k[0] == "head_t"]:
        onemesh._CACHE.pop(kk, None)   # (each evaluation is a new head: don't keep hundreds)
    return ht, b


def solve(base: dict, ev: dict, iters: int = 6, log=print, d_line: float | None = None,
          hold_socket: float | None = SIG_SOCKET, crease: str | None = "default") -> dict:
    """identity + eye expression for evidence ev (photo_evidence). base: the block-in's base (its lid pose cleared
    here). crease: when the picture shows a line, the fold's SHAPE to match (a crease_shape template name; "default" =
    CREASE; None = the old target: the line's height + d_line, the crease's least local depth in mm, default D_LINE);
    hold_socket: the socket readings' sigma (sd; None = not held). Returns {"c", "expression", "read0", "read", "cost",
    "dc", "e", "socket0", "socket", "crease", "shape0" / "shape" (section rms vs the template, mm)}."""
    crease = CREASE if crease == "default" else crease
    use_shape = bool(crease) and not ev.get("hooded") and np.isfinite(ev.get("tps", np.nan))
    shape = None
    sig_lid = SIG_LID_SHAPE if use_shape else SIG_LID
    d_line = D_LINE if d_line is None else float(d_line)
    from . import blockin as bi
    Ln, Rn, _ = _names()
    b0 = copy.deepcopy(base)
    pose = dict(b0["head"].get("pose") or {})
    pose.pop("lid_upper", None)
    pose.pop("lid_lower", None)
    b0["head"]["pose"] = pose
    if not pose:
        b0["head"].pop("pose", None)
    c0 = bi.identity({"base": b0})
    e0 = np.zeros(NE)
    ex0 = b0["head"].get("expression") or {}
    for k in range(NE):
        e0[k] = 0.5 * (float(ex0.get(Ln[k], 0.0)) + float(ex0.get(Rn[k], 0.0)))
    ht0, _ = _head(b0, c0, e0, Ln, Rn)
    rd = Reader(ht0)
    heights = None
    if use_shape:
        # the picture's fold line (mm at an 11.7 mm iris) -> ours, per column; a column with no line takes the median
        k_iris = rd.read(ht0)["r_iris_mm"] / 5.85
        tc = [t if np.isfinite(t) else ev["tps"] for t in (ev.get("tps_cols") or [ev["tps"]] * 3)]
        heights = [t * k_iris for t in tc]
        shape = crease_target(crease, heights)
    ex_other = {k: v for k, v in ex0.items() if k not in set(Ln) | set(Rn)}

    def sock(c, e):
        return socket(c, {**ex_other, **{Ln[k]: e[k] for k in range(NE)}, **{Rn[k]: e[k] for k in range(NE)}})
    s0 = sock(c0, e0)
    L0 = np.asarray(ht0["lm68"], float)
    tps_k = None

    def resid(x):
        ht, _ = _head(b0, c0 + x[:170], e0 + x[170:], Ln, Rn)
        q = rd.read(ht)
        r = [(q["up"] - ev["up"]) / sig_lid if np.isfinite(q["up"]) else 50.0,
             (q["lo"] - ev["lo"]) / sig_lid if np.isfinite(q["lo"]) else 50.0]
        if shape is not None:
            d = (rd.sections(ht) - shape) / SIG_SHAPE
            r += list(np.where(np.isfinite(d), d, 20.0).ravel())
        elif np.isfinite(ev.get("tps", np.nan)):
            want = ev["tps"] * q["r_iris_mm"] / (5.85)   # the picture's mm at an 11.7 mm iris -> ours
            if ev.get("hooded"):
                r.append((q["vis"] - want) / SIG_HOODED if np.isfinite(q["vis"]) else 20.0)
            else:
                r.append((q["hsoft"] - want) / SIG_TPS if np.isfinite(q["hsoft"]) else 20.0)
                r.append(min(q["lsoft"] - d_line, 0.0) / SIG_LINE)
        L = np.asarray(ht["lm68"], float)
        if hold_socket:
            s = sock(c0 + x[:170], e0 + x[170:])
            r += [(s[k] - s0[k]) / hold_socket for k in SOCKET]
        r += list(((L[HOLD] - L0[HOLD]) * 1000 / SIG_HOLD).ravel())
        r += list(((L[BROWS] - L0[BROWS]) * 1000 / SIG_BROW).ravel())
        return np.array(r), q
    n = 170 + NE
    x = np.zeros(n)
    lam = 0.01
    r, q0 = resid(x)
    log(f"eye step start: picture up {ev['up']:.2f} lo {ev['lo']:.2f} tps {ev.get('tps', np.nan):.2f} mm dark "
        f"{ev.get('dark', 0):.2f} | model up {q0['up']:.2f} lo {q0['lo']:.2f} show {q0['show']:.2f} mm crease local "
        f"{q0['local']:.2f} mm at {q0['height']:.1f}")
    f = float(r @ r + x @ x)
    for it in range(iters):
        J = np.zeros((len(r), n))
        h = 0.25
        for j in range(n):
            ej = np.zeros(n)
            ej[j] = h
            J[:, j] = (resid(x + ej)[0] - r) / h
        while True:
            step = np.linalg.solve(J.T @ J + (1 + lam) * np.eye(n), -(J.T @ r + x))
            xn = x + step
            rn, qn = resid(xn)
            fn = float(rn @ rn + xn @ xn)
            if fn < f:
                x, r, f, lam = xn, rn, fn, lam * 0.5
                break
            lam *= 4
            if lam > 1e4:
                break
        q = resid(x)[1]
        log(f"  it {it}: cost {f:.2f} |dc| {np.linalg.norm(x[:170]):.2f} |e| {np.linalg.norm(e0 + x[170:]):.2f} | up "
            f"{q['up']:.2f} lo {q['lo']:.2f} platform {q['vis']:.2f} (hood {q['drop']:.2f}) crease {q['lsoft']:.2f} mm at {q['hsoft']:.2f}")
        if lam > 1e4:
            break
    q = resid(x)[1]
    e = e0 + x[170:]
    s1 = sock(c0 + x[:170], e)
    log("  socket " + ", ".join(f"{k} {s0[k]:+.2f} -> {s1[k]:+.2f}" for k in SOCKET))

    def shape_rms(c, e):
        if shape is None:
            return float("nan")
        d = rd.sections(_head(b0, c, e, Ln, Rn)[0]) - shape
        return float(np.sqrt(np.nanmean(np.sum(d ** 2, -1))))
    sh0, sh1 = shape_rms(c0, e0), shape_rms(c0 + x[:170], e)
    if shape is not None:
        log(f"  crease shape ({crease}): section rms {sh0:.2f} -> {sh1:.2f} mm")
    return {"socket0": s0, "socket": s1, "c": c0 + x[:170], "expression": {**{Ln[k]: round(float(e[k]), 5) for k in range(NE) if abs(e[k]) > 1e-5},
                                              **{Rn[k]: round(float(e[k]), 5) for k in range(NE) if abs(e[k]) > 1e-5}},
            "read0": q0, "read": q, "cost": f, "dc": float(np.linalg.norm(x[:170])), "e": float(np.linalg.norm(e)),
            "pose": pose, "crease": crease if shape is not None else None, "shape0": sh0, "shape": sh1, "heights": heights}


def eye_step(name: str, out: str | None = None, seen: str = "", iters: int = 6, log=print) -> dict:
    """The block-in step: solve, then write it as a new model (blockin.step with the identity / expression set)."""
    from PIL import Image
    from . import blockin as bi, store
    rj = bi._refs(name)
    vi = bi._front(rj)
    v = rj["views"][vi]
    ev = photo_evidence(Image.open(v["image"]).convert("RGB"), v)
    base = store.load(name)["base"]
    s = solve(base, ev, iters=iters, log=log)
    rep = bi.step(name, {}, out=out, seen=seen or "lids and fold vs the picture (eye step)",
                  why=(f"eye step (identity + GNM eye-region expression; no lidfold, no lid pose): picture up "
                       f"{ev['up']:.2f} lo {ev['lo']:.2f} iris radii, fold line {ev['tps']:.2f} mm (dark {ev['dark']:.2f}); "
                       f"model {s['read']['up']:.2f} / {s['read']['lo']:.2f}, platform {s['read']['show']:.2f} mm, "
                       f"crease {s['read']['local']:.2f} mm deep; |dc| {s['dc']:.2f}, |e| {s['e']:.2f}"),
                  _identity=s["c"], _head_set={"expression": s["expression"], "pose": s["pose"] or None})
    rep["eyes"] = {"evidence": {k: v for k, v in ev.items() if k != "columns"},
                   **{k: s[k] for k in ("read0", "read", "dc", "e", "crease", "shape0", "shape", "heights")}}
    return rep


def text(e: dict) -> str:
    """The eye step's report (eye_step's rep["eyes"])."""
    ev, a, b = e["evidence"], e["read0"], e["read"]
    fold = (f"no fold line on the picture (hooded: the platform target {HOODED_SHOW} mm visible)" if ev.get("hooded")
            else f"fold line {ev['tps']:.2f} mm over the lashes (at an 11.7 mm iris), darkness {ev['dark']:.2f}")
    return (f"EYE STEP (identity + GNM eye-region expression, the rest of the face held; no lidfold, no lid pose): "
            f"picture lids {ev['up']:.2f} / {ev['lo']:.2f} iris radii, {fold}\n"
            f"  model before: lids {a['up']:.2f} / {a['lo']:.2f}, platform {a['show']:.2f} mm, crease {a['lsoft']:.2f} mm deep "
            f"at {a['hsoft']:.2f} mm\n"
            f"  model after:  lids {b['up']:.2f} / {b['lo']:.2f}, platform {b['show']:.2f} mm, crease {b['lsoft']:.2f} mm deep "
            f"at {b['hsoft']:.2f} mm | |dc| {e['dc']:.2f}, eye expression |e| {e['e']:.2f}"
            + (f"\n  crease SHAPE: the {e['crease']!r} template's fold carried to the picture's line ("
               + "/".join(f"{h:.1f}" for h in (e.get("heights") or [])) + " mm over the margin, inner/pupil/outer): section rms "
               f"{e['shape0']:.2f} -> {e['shape']:.2f} mm. The picture's line darkness is not a target: add any missing "
               f"darkness with skin.makeup eyeshadow's \"crease\"" if e.get("crease") else ""))
