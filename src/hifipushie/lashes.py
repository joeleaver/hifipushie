"""Eyelashes as geometry (eyedetail, 2026-10-09; the user, at Tess's front close-up: "We also just don't seem to have
the eye detail we need"): game-ready lash ribbons, upper and lower, rooted on the built head's lid margins.

How shipped game heads do it (MetaHuman, Unreal's Digital Human, most AAA heads): the lashes are their own mesh, a
few thousand triangles of thin strips rooted along the lid margin's front edge, bound to the lid so a blink carries
them, with a dark, slightly glossy material; the painted lash line on the skin is the roots' density under them.
Here each lash is one tapered ribbon (`segments` quads, flat side facing forward, its width along the lid), opaque:
no alpha atlas to sort or cut, sharp in close-ups, and at a distance the lashes' sub-pixel coverage reads as the
dark frame round the eye (what the photograph shows). ~1.5k triangles per eye at the defaults.

Anatomy (oculoplastic / trichology references): upper lashes 90-160 in 2-3 irregular rows, 8-12 mm long (longest
in the middle and outer third, short at the inner canthus), leaving the margin forward and a little down and curling
up; lower 70-80, 6-7 mm, finer and paler, angled down and out; none over the inner ~12% (the punctum, caruncle).
Lashes group in small clumps (their tips touch), cross a little, and the outer ones sweep outward.

The margin (`lid_lines`): the eye opening as seen along the head's forward axis is where the eyeball stands in front
of the skin (the skin runs on into the socket, there is no edge loop: base.eye_opening's method), traced round each
eye from its centre; the lash line is that rim, a little out onto the lid (the upper margin faces down, so from the
front its edge IS the lash line; the lower margin faces up, so its lash line lies ~0.5 mm below the visible rim).
Purely geometric: it follows any head (sliders, pose, identity) the field is built from.

spec["base"]["lashes"] = false | true | {"upper": {...}, "lower": {...}, "color", "roughness", "seed", "segments"};
per lid: "count", "length" (mm, the longest), "curl" (deg over the length), "lift" (deg at the root, + = away from
the eye's middle line), "flare" (deg the outer ones sweep outward), "thickness" (mm at the root), "clump" (0..1),
"offset" (mm out from the visible rim), "taper_out" (0.25: how much shorter the outermost quarter gets; negative =
longer toward the outer corner: an eye that reads long). Default ON for one-mesh human heads (base.body.source "human").
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

VERSION = 21  # 21: taper_out; 5: a fully closed lid roots on its closed line, never a fold slit; 4: the lid line's piece scored by size and height (a fold's slit was taken); 3: a blink's slit joined, the largest piece taken (projskin); 2: seated on the filled front map (holes in the sampled skin threw points off)
DEFAULTS = {
    "upper": {"count": 230, "length": 9.0, "curl": 62.0, "lift": -12.0, "flare": 24.0, "thickness": 0.15,
              "clump": 0.6, "clump_size": [3, 6], "vary": 0.35, "rows": 0.25, "offset": 0.15, "start": 0.08, "end": 1.0, "taper_out": 0.25},
    "lower": {"count": 75, "length": 3.0, "curl": 10.0, "lift": 55.0, "flare": 16.0, "thickness": 0.04,
              "clump": 0.5, "clump_size": [2, 4], "vary": 0.45, "rows": 0.15, "offset": 0.5, "start": 0.2, "end": 0.97, "taper_out": 0.25},
    "color": "#120e0c", "lower_color": "#3a302a", "roughness": 0.5, "seed": 0, "segments": 4,
}
_CACHE: dict = {}


def wanted(spec: dict) -> dict | None:
    """The lashes' settings if the spec's base head gets them, else None."""
    b = spec.get("base") or {}
    v = b.get("lashes")
    if v is False:
        return None
    if v is None:  # default: one-mesh humans
        if (b.get("body") or {}).get("source") != "human" or not b.get("head"):
            return None
        v = {}
    if v is True:
        v = {}
    bad = set(v) - set(DEFAULTS)
    if bad:
        from .spec import SpecError
        raise SpecError(f"base.lashes: unknown keys {sorted(bad)} (have {', '.join(DEFAULTS)})")
    out = {k: (dict(_by_body(DEFAULTS[k], b.get("body") or {}, k), **(v.get(k) or {})) if isinstance(DEFAULTS[k], dict)
               else v.get(k, DEFAULTS[k])) for k in DEFAULTS}
    for lid in ("upper", "lower"):
        bad = set(v.get(lid) or {}) - set(DEFAULTS[lid])
        if bad:
            from .spec import SpecError
            raise SpecError(f"base.lashes.{lid}: unknown keys {sorted(bad)} (have {', '.join(DEFAULTS[lid])})")
    return out


def _by_body(d: dict, body: dict, lid: str) -> dict:
    """A lid's defaults for the body's sex and age (given keys win over these): men's lashes ~12% shorter and less
    curled (the defaults are a young woman's), and from ~30 years they thin and shorten (by 70: a quarter fewer,
    15% shorter, less curl). body.sex 1 = male (the default, as the body), 0 = female."""
    sex = float(np.clip(body.get("sex", 1.0), 0, 1))  # (the body's own default: male)
    old = float(np.clip((float(body.get("age", 25)) - 30) / 40, 0, 1))
    d = dict(d)
    d["length"] = round(d["length"] * (1 - 0.12 * sex) * (1 - 0.15 * old), 3)
    d["count"] = int(round(d["count"] * (1 - 0.1 * sex) * (1 - 0.25 * old)))
    d["curl"] = round(d["curl"] * (1 - (0.2 if lid == "upper" else 0.1) * sex) * (1 - 0.2 * old), 2)
    return d


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-15)


def _frame(head, c):
    fwd = _unit(np.asarray(head["forward"], float))
    up = np.array([0.0, 0.0, 1.0])
    up = _unit(up - (up @ fwd) * fwd)
    side = np.cross(up, fwd)  # with fwd = -y and up = z: side = +x (the subject's left)
    return fwd, up, side


def _dense(head, c, reach=0.026, per=10, seed=0):
    """Points sampled on the head's faces near the eye (vertices alone leave gaps the opening leaks through)."""
    W = np.asarray(head["verts"], float)
    F = head["faces"]
    near = np.linalg.norm(W - c, axis=1) < reach
    T = np.array([(f[0], f[j], f[j + 1]) for f in F if any(near[v] for v in f) for j in range(1, len(f) - 1)])
    rng = np.random.default_rng(seed)
    a, b = rng.random((2, per))
    sw = a + b > 1
    a[sw], b[sw] = 1 - a[sw], 1 - b[sw]
    A, B, C = W[T[:, 0]], W[T[:, 1]], W[T[:, 2]]
    P = A[:, None] + a[None, :, None] * (B - A)[:, None] + b[None, :, None] * (C - A)[:, None]
    return np.r_[P.reshape(-1, 3), W[np.unique(T)]]  # (faces' vertices only: no stray points)


def lid_lines(head: dict, cell: float = 0.0002, n: int = 360) -> list:
    """Per eye (head["eyes"] order): {"centre", "fwd", "up", "side", "inner" (unit, toward the nose), "rim": (n, 3)
    the opening's rim on the skin per angle, "theta", "rho" (m, in the front plane), "front" (the skin's depth
    there), "corners": (inner index, outer index)}."""
    from scipy import ndimage
    out = []
    r = float(head["eye_r"])
    for c in head["eyes"]:
        c = np.asarray(c, float)
        fwd, up, side = _frame(head, c)
        P = _dense(head, c)
        d = P - c
        u, v, depth = d @ side, d @ up, d @ fwd
        m = depth > -0.006
        nn = int(0.02 / cell)
        iu, iv = np.floor(u[m] / cell).astype(int) + nn, np.floor(v[m] / cell).astype(int) + nn
        ok = (iu >= 0) & (iu < 2 * nn) & (iv >= 0) & (iv < 2 * nn)
        front = np.full((2 * nn, 2 * nn), -9.0)
        np.maximum.at(front, (iu[ok], iv[ok]), depth[m][ok])
        front = ndimage.maximum_filter(front, size=3)
        g = (np.arange(2 * nn) - nn + 0.5) * cell
        q = r * r - g[:, None] ** 2 - g[None, :] ** 2
        ball = np.where(q > 0, np.sqrt(np.maximum(q, 0)), -np.inf)
        eg = head.get("eye_gnm")
        if eg and eg.get("cornea_r") and eg.get("apex"):
            # GNM's OWN eyeball (native heads) is IN the head's mesh, cornea and all: its cornea stands ~1.5 mm proud of
            # the sphere, so the sphere test took the cornea for skin in front of the ball and found no opening (an older head:
            # ~240 crumbs, a lower rim 0.2 mm long, every lower lash at one point). The eyeball's own surface = the sphere
            # or the cornea's cap, with 0.3 mm of slack (the eye's surface vertices are themselves in the map)
            cr, ap = float(eg["cornea_r"]), float(eg["apex"])
            qc = cr * cr - g[:, None] ** 2 - g[None, :] ** 2
            cap = np.where(qc > 0, np.sqrt(np.maximum(qc, 0)) + (ap - cr), -np.inf)
            ball = np.maximum(ball, cap) + 0.0003
        opening = (ball > front) & (q > 0)
        # a nearly closed lid (a blink) leaves a thin slit, broken into small pieces at this cell size: joined along the
        # lid's own direction (the grid's first axis = `side`), else one tiny piece was taken and every lash rooted on it
        # (a clump sticking out of the closed lid). A wide-open opening is unchanged by this closing.
        opening = opening | (ndimage.binary_closing(opening, structure=np.ones((int(0.003 / cell) | 1, 1), bool)) & (q > 0))
        lab, nlab = ndimage.label(opening)
        # the CLOSED-lid rules (the lowest big piece is the lid line; a thin piece means the seam is found in the skin)
        # only when the head says the lids are (nearly) shut: on an OPEN hooded eye (an older head: a 3.5 mm tall opening
        # under the ball's centre) they took a crumb under the eye and every lower lash went to one point
        closed = float(head.get("eye_open", 1.0)) < 0.0015
        band_origin, seam2 = None, None
        seed_lab = lab[nn, nn]
        if nlab > 1:   # the piece that is the LID LINE: large, and lying where a closing lid's margin lies (a little below
            # the ball's middle). A blink also opens other pieces (a deep lid fold's slit dips behind the ball's sphere):
            # taken as "the largest", the lashes rooted along the fold, a wiggly black line over the closed lid
            vv = np.broadcast_to(g[None, :], lab.shape)
            best, seed_lab = -1.0, seed_lab
            sizes = np.bincount(lab.ravel(), minlength=nlab + 1)
            big = max(int(sizes[1:].max()), 1)
            for k in range(1, nlab + 1):
                if sizes[k] < 0.2 * big:     # (the fold's slit, deepened, opens wide pieces ABOVE the lid line in a blink:
                    continue                 # among the big pieces the LOWEST is the lid line; the lashes stood on the
                                             # fold's slit, a black line over Tess's and a test head's closed lids)
                m_ = lab == k
                n_ = int(m_.sum())
                if n_ < 4:
                    continue
                vc = float(vv[m_].mean())
                if vc > 0.25 * r:      # high on the ball: a fold's slit, never the lid line
                    continue
                sc = n_ * np.exp(-((vc + 0.15 * r) / (0.35 * r)) ** 2) * (np.exp(-vc / (0.1 * r)) if closed else 1.0)   # closed: lower wins
                if sc > best:
                    best, seed_lab = sc, k
            if best < 0:
                seed_lab = -1
        narrow = False
        if seed_lab > 0:   # a piece much narrower than the eye is a FRAGMENT of a nearly closed slit, not the lid line: every
            # lash rooted round it stood out of the closed lid as one clump (Tess, an older test head, a test head)
            ii_ = np.nonzero(lab == seed_lab)[0]
            narrow = len(ii_) > 0 and (float(g[ii_].max() - g[ii_].min()) < 0.9 * r) and nlab > 1
            jj_ = np.nonzero(lab == seed_lab)[1]
            # a THIN piece (a slit, not an open eye's opening) may be the fold's slit over a fully closed seam: the
            # lid line is then found in the skin (the lowest valley), never on the piece
            narrow = narrow or (closed and len(jj_) > 0 and float(g[jj_].max() - g[jj_].min()) < 0.25 * r)
        if closed or seed_lab == -1 or narrow or (seed_lab > 0 and float(np.broadcast_to(g[None, :], lab.shape)[lab == seed_lab].mean()) > 0.25 * r):
            # a CLOSED lid (the head says so; whatever crumbs of opening are left, an older test head's blink had one 0.2 mm crumb and
            # no lashes at all) or a FULLY closed lid: no opening left but a fold's slit. The lashes root on the closed lid line: a thin band
            # across the ball a little below its middle (where the margins meet), as wide as the ball shows
            # (at the slit's OWN height when pieces of it show: at the fixed -0.15 r the lashes stood as a hard black line
            # above Tess's closed lid line)
            # THE SEAM from the skin itself: per column across the eye, the LOWEST valley in the skin's depth over the ball
            # (where the margins meet; the fold's slit is a valley too, but above it). At the slit pieces' height (v7) or a
            # fixed -0.15 r the lashes stood as a hard black line ~2.5 mm over Tess's, a test head's and a test head's seams.
            vb = np.full(2 * nn, np.nan)
            ff = ndimage.gaussian_filter(np.where(front < -1, np.nan_to_num(front, nan=-1), front), 1.0)
            dv = max(int(round(0.001 / cell)), 1)
            jv = np.flatnonzero((g > -0.75 * r) & (g < 0.25 * r))
            for i in np.flatnonzero(np.abs(g) < 0.85 * r):
                col = ff[i]
                bestd = 0.00005   # the DEEPEST valley (the seam's gap; the lowest one was the lower lid's own fold: the
                for j in jv[jv - dv >= 0]:   # lash row sat ~1 mm under a test head's and a test head's seams)
                    if j + dv >= len(col):
                        continue
                    dep_ = min(col[j - dv], col[j + dv]) - col[j]
                    if col[j] > -1 and dep_ > bestd and col[j] <= col[j - 1] and col[j] <= col[j + 1]:
                        bestd, vb[i] = dep_, g[j]
            lm = head.get("lm68")
            if lm is not None:   # THE SEAM FROM THE LANDMARKS when the head has them: a closed lid's margins meet on the
                # lower lid's line (it hardly moves in a blink; the corners hold): the skin's valleys also found the fold
                # (above) and the lower lid's own fold (below): the lash row sat over / under the seam on three heads
                lm = np.asarray(lm, float)
                sets = ((36, 41, 40, 39), (42, 47, 46, 45))
                pts = min((lm[list(st_)] for st_ in sets), key=lambda P_: float(np.linalg.norm(P_.mean(0) - c)))
                du, dv_ = (pts - c) @ side, (pts - c) @ up
                o_ = np.argsort(du)
                k_ = np.polyfit(du[o_], dv_[o_], 2 if len(o_) >= 4 else 1)
                vb = np.polyval(k_, g)
            okc = np.isfinite(vb)
            if lm is None and okc.sum() >= 5:
                ii_ = np.arange(2 * nn)
                vb = np.interp(ii_, ii_[okc], ndimage.median_filter(vb[okc], 5))
                # a smooth seam (a staircase of per-column picks broke the band into steps: every ray left it at once)
                vb = ndimage.gaussian_filter1d(vb, 0.0015 / cell, mode="nearest")
                # ... and as a lid's line is: a smooth curve (a quadratic across the eye: the per-column valleys wobbled
                # and the lash row waved along Tess's closed lid)
                sel_ = (np.abs(g) < 0.8 * r) & okc
                if sel_.sum() >= 6:
                    vb = np.polyval(np.polyfit(g[sel_], vb[sel_], 2), g)
            elif lm is None:
                vb = np.full(2 * nn, -0.15 * r)
            band = (np.abs(g[None, :] - vb[:, None]) < 3.0 * cell) & (q > 0) & (np.abs(g[:, None]) < 0.85 * r)
            band_origin = (float(nn), float(np.argmin(np.abs(g - vb[nn]))))
            uu = np.abs(g) < 0.8 * r
            seam2 = np.c_[g[uu], vb[uu]]   # the seam itself as the closed lid's rim (rays from its middle left a curved seam)
            lab = band.astype(int)
            seed_lab = 1
        if seed_lab == 0:  # the opening needn't cover the ball's centre (a hooded or low-set lid): the component with
            # most cells near it
            near = (np.hypot(g[:, None], g[None, :]) < 0.5 * r) & (lab > 0)
            if not near.any():
                raise ValueError("lashes: no eye opening found (closed lids?)")
            seed_lab = np.bincount(lab[near]).argmax()
        op = lab == seed_lab
        ci, cj = np.nonzero(op)  # rays from the opening's own middle (the ball's centre can lie under a lid)
        oi, oj = float(ci.mean()), float(cj.mean())
        if band_origin is not None:   # a closed lid's seam band: from the seam's own middle (the band's mean lies off a curved seam)
            oi, oj = band_origin
        o2 = np.array([(oi - nn + 0.5) * cell, (oj - nn + 0.5) * cell])
        th = np.linspace(0, 2 * np.pi, n, endpoint=False)
        rho = np.zeros(n)
        steps = np.arange(0, 0.02, cell * 0.25)
        for k, t in enumerate(th):
            x = oi + np.cos(t) * steps / cell
            y = oj + np.sin(t) * steps / cell
            inside = op[np.clip(x.astype(int), 0, 2 * nn - 1), np.clip(y.astype(int), 0, 2 * nn - 1)]
            j = np.argmin(inside) if not inside.all() else len(steps) - 1
            rho[k] = steps[max(j - 1, 0)] + 0.5 * cell
        # smooth along the rim (grid steps), circularly
        # a lone ray escaping through a gap of the traced opening rooted a lash bundle ~8 mm under an older test head's left eye
        # (a white star in front light, a dark dash at 3/4): outliers off by a running median first
        rho = ndimage.median_filter(rho, size=9, mode="wrap")
        rho = ndimage.gaussian_filter1d(rho, 2.0, mode="wrap")
        inner = -np.sign(c[0]) * side if abs(c[0]) > 1e-6 else side
        U = np.cos(th)[:, None] * side + np.sin(th)[:, None] * up
        out.append({"centre": c, "fwd": fwd, "up": up, "side": side, "inner": inner, "theta": th, "rho": rho, "closed": closed, "seam2": seam2,
                    "dirs": U, "front": front, "cell": cell, "nn": nn, "o2": o2,
                    # (for seating points on the skin: cells the samples missed take their neighbours' depth; the
                    # opening above is traced on the unfilled map, which the filling would shrink)
                    "front_filled": np.where(front < -1, ndimage.maximum_filter(front, size=11), front),
                    "corners": (int(np.argmax((U * rho[:, None]) @ inner)), int(np.argmin((U * rho[:, None]) @ inner)))})
    return out


def _arc(L, lid):
    """Indices along one lid's rim, inner corner -> outer corner, through the top (upper) or bottom (lower)."""
    n = len(L["theta"])
    i0, i1 = L["corners"]
    a = [(i0 + k) % n for k in range((i1 - i0) % n + 1)]
    b = [(i0 - k) % n for k in range((i0 - i1) % n + 1)]
    va = np.mean([L["dirs"][i] @ L["up"] for i in a])
    up_arc, lo_arc = (a, b) if va > 0 else (b, a)
    return np.array(up_arc if lid == "upper" else lo_arc)


def _on_skin(L, P2):
    """2D front-plane points (m) -> the skin's 3D point there (the front-most skin in the cell)."""
    nn, cell = L["nn"], L["cell"]
    iu = np.clip(np.floor(P2[:, 0] / cell).astype(int) + nn, 0, 2 * nn - 1)
    iv = np.clip(np.floor(P2[:, 1] / cell).astype(int) + nn, 0, 2 * nn - 1)
    dep = L.get("front_filled", L["front"])[iu, iv]
    return L["centre"] + P2[:, :1] * L["side"] + P2[:, 1:] * L["up"] + dep[:, None] * L["fwd"]


def build(head: dict, cfg: dict, sides=(".L", ".R")) -> dict:
    """The lash ribbons for both eyes: {"verts", "tris", "normal", "uv" (along, across), "along" (0 root .. 1 tip),
    "root" (each vertex's root point), "lid" (0 upper, 1 lower), "eye" (0, 1), "col" (per-vertex colour)}."""
    rng = np.random.default_rng(int(cfg.get("seed", 0)))
    seg = int(cfg.get("segments", 4))
    V, T, Nn, UV, AL, RT, LID, EYE, COL = [], [], [], [], [], [], [], [], []
    CUR: dict = {"upper": [], "lower": []}
    lines = lid_lines(head)
    r_ball = float(head["eye_r"])
    tree = head["tree"]
    HN = np.asarray(head["normals"], float)
    HV = np.asarray(head["verts"], float)
    for ei, L in enumerate(lines):
        c = L["centre"]
        for li, lid in enumerate(("upper", "lower")):
            p = cfg[lid]
            col = np.array(_hex(cfg["color"] if lid == "upper" else cfg.get("lower_color", cfg["color"])))
            if lid == "lower" and L.get("closed"):   # a closed eye: the lower lashes lie tucked under the upper lid's;
                continue                             # both rows on one seam drew a hard black streak (Tess)
            idx = _arc(L, lid)
            rim2 = L["o2"] + np.c_[(L["dirs"][idx] @ L["side"]) * L["rho"][idx], (L["dirs"][idx] @ L["up"]) * L["rho"][idx]]
            if L.get("closed") and L.get("seam2") is not None and len(L["seam2"]) > 8:
                # a closed lid's lashes along the whole seam, inner corner -> outer (the ray-traced rim covered its middle
                # third: a short clump in the middle of Tess's closed lid)
                sm = np.asarray(L["seam2"], float)
                isg = float(np.sign(L["inner"] @ L["side"])) or 1.0
                rim2 = sm[np.argsort(-sm[:, 0] * isg)]
                idx = np.arange(len(rim2))
            seglen = np.r_[0, np.cumsum(np.linalg.norm(np.diff(rim2, axis=0), axis=1))]
            span = float(np.linalg.norm(rim2[-1] - rim2[0])) if len(rim2) > 1 else 0.0
            if len(idx) < 4 or span < 0.6 * r_ball:
                # a degenerate rim (corners found next to each other): every lash of this lid was rooted at ONE point
                # (~200 lower lashes as a tuft 10 mm under an older test head's left eye). Not laid, and LOUD: a sheet with it
                # is not shown (mismatched eyes read wrong at close range); the cause is to be found, not hidden
                print(f"LASHES WARNING: eye {ei} {lid} lid's rim is degenerate (span {span * 1000:.1f} mm): its lashes NOT laid", flush=True)
                continue
            s_all = seglen / seglen[-1]
            # the lash line itself (no scatter): where the painted root tone goes (skin.hair.lashes with geometry)
            sc = np.linspace(p["start"], p["end"], 24)
            C2 = np.c_[np.interp(sc, s_all, rim2[:, 0]), np.interp(sc, s_all, rim2[:, 1])]
            oc = (C2 - L["o2"]) / np.maximum(np.linalg.norm(C2 - L["o2"], axis=1, keepdims=True), 1e-9)
            CUR[lid].append(_on_skin(L, C2 + oc * p["offset"] * 1e-3))
            cnt = int(p["count"])
            s = np.sort(rng.uniform(p["start"], p["end"], cnt))
            s = np.clip(s + rng.normal(0, 0.004, cnt), 0, 1)
            # roots: the rim moved out onto the lid by `offset` (2D), a little scatter across the margin (rows)
            P2 = np.c_[np.interp(s, s_all, rim2[:, 0]), np.interp(s, s_all, rim2[:, 1])]
            out2 = (P2 - L["o2"]) / np.maximum(np.linalg.norm(P2 - L["o2"], axis=1, keepdims=True), 1e-9)
            rows = rng.normal(0.0, float(p["rows"]) * 1e-3, cnt)  # irregular rows across the margin
            P2 = P2 + out2 * (p["offset"] * 1e-3 + np.abs(rows))[:, None]
            roots = _on_skin(L, P2) - (np.abs(rows) * 0.6)[:, None] * L["fwd"]  # back rows sit a little deeper
            # along the margin: the tangent; "out" = away from the opening in the front plane
            tan2 = np.c_[np.gradient(P2[:, 0]), np.gradient(P2[:, 1])]
            tan = _unit(tan2[:, :1] * L["side"] + tan2[:, 1:] * L["up"])
            outv = _unit(out2[:, :1] * L["side"] + out2[:, 1:] * L["up"])
            if L.get("closed"):   # a closed eye's lashes hang DOWN over the seam (out of the thin band "out" is up: they
                # stood up into the closed lid and were pushed out of the skin as a short black streak at the seam)
                outv = np.tile(-L["up"], (len(outv), 1))
            # length profile: short at the inner canthus, longest over the middle-outer third, a little shorter outside
            prof = (0.5 + 0.5 * np.clip((s - p["start"]) / 0.45, 0, 1) ** 0.8) * (1 - float(p.get("taper_out", 0.25)) * np.clip((s - 0.75) / 0.25, 0, 1) ** 2)
            length = p["length"] * 1e-3 * prof * rng.uniform(1.0 - float(p["vary"]), 1.08, cnt)
            lift = np.radians(p["lift"] + rng.normal(0, 5, cnt))
            curl = np.radians(p["curl"] * rng.uniform(0.75, 1.2, cnt))
            # the outer lashes sweep outward (toward the outer corner), the inner ones a little toward the nose
            sweep = np.radians(p["flare"] * np.clip((s - 0.35) / 0.65, -0.4, 1) + rng.normal(0, 4, cnt))
            outer = -L["inner"]
            t = np.linspace(0, 1, seg + 1)
            ang = lift[:, None] + curl[:, None] * t[None] ** 1.4  # (cnt, seg+1)
            # direction along the lash per sample, integrated (forward, curling out from the opening)
            D = np.cos(ang)[..., None] * L["fwd"] + np.sin(ang)[..., None] * outv[:, None, :]
            sw = np.tan(sweep)[:, None, None] * t[None, :, None] * (outer - (outer @ L["fwd"]) * L["fwd"])[None, None]
            D = _unit(D + sw)
            step = (length / seg)[:, None, None]
            Pp = roots[:, None, :] + np.concatenate([np.zeros((cnt, 1, 3)), np.cumsum(D[:, :-1] * step, axis=1)], 1)
            # clumps: groups of 2-4 neighbours whose tips draw together
            k = 0
            while k < cnt:
                g = int(rng.integers(int(p["clump_size"][0]), int(p["clump_size"][1]) + 1))
                j = slice(k, min(k + g, cnt))
                tip = Pp[j, -1].mean(0)
                Pp[j] += float(p["clump"]) * (t[None, :, None] ** 2) * (tip - Pp[j, -1])[:, None, :]
                k += g
            # keep clear of the eyeball (+0.3 mm) and of the skin (each point at least 0.15 mm out along the skin's
            # normal at its nearest vertex)
            for _ in range(2):
                dc = Pp - c
                rr = np.linalg.norm(dc, axis=-1, keepdims=True)
                Pp = np.where(rr < r_ball + 3e-4, c + dc / rr * (r_ball + 3e-4), Pp)
                flat = Pp[:, 1:].reshape(-1, 3)
                _, ni = tree.query(flat)
                sd = ((flat - HV[ni]) * HN[ni]).sum(1)
                push = np.clip(1.5e-4 - sd, 0, 0.003)
                flat = flat + push[:, None] * HN[ni]
                Pp[:, 1:] = flat.reshape(cnt, seg, 3)
            # the ribbon: width along the lid (tangent made square to the lash), tapering to a fine tip
            Dl = np.gradient(Pp, axis=1)
            Dl = _unit(Dl)
            Wd = _unit(tan[:, None, :] - (Dl * tan[:, None, :]).sum(-1, keepdims=True) * Dl)
            wid = p["thickness"] * 1e-3 * (1 - 0.85 * t ** 1.5)
            A = Pp - 0.5 * wid[None, :, None] * Wd
            B = Pp + 0.5 * wid[None, :, None] * Wd
            Nr = _unit(np.cross(Wd, Dl))
            Nr = np.where(((Nr * L["fwd"]).sum(-1, keepdims=True) < 0), -Nr, Nr)
            base = sum(len(x) for x in V)
            V.append(np.stack([A, B], 2).reshape(-1, 3))  # per lash: seg+1 pairs
            Nn.append(np.repeat(Nr, 2, axis=1).reshape(-1, 3))
            UV.append(np.c_[np.repeat(np.repeat(t[None], cnt, 0), 2, 1).ravel(), np.tile([0.0, 1.0], cnt * (seg + 1))])
            AL.append(np.repeat(np.repeat(t[None], cnt, 0), 2, 1).ravel())
            RT.append(np.repeat(roots, 2 * (seg + 1), 0))
            LID.append(np.full(cnt * 2 * (seg + 1), li))
            EYE.append(np.full(cnt * 2 * (seg + 1), ei))
            COL.append(np.tile(col, (cnt * 2 * (seg + 1), 1)))
            per = 2 * (seg + 1)
            q = np.arange(seg)
            a0, b0, a1, b1 = 2 * q, 2 * q + 1, 2 * q + 2, 2 * q + 3
            quad = np.stack([np.c_[a0, b0, b1], np.c_[a0, b1, a1]], 1).reshape(-1, 3)
            T.append((base + np.arange(cnt)[:, None, None] * per + quad[None]).reshape(-1, 3))
    return {"verts": np.concatenate(V), "tris": np.concatenate(T).astype(np.int32), "normal": np.concatenate(Nn),
            "uv": np.concatenate(UV), "along": np.concatenate(AL), "root": np.concatenate(RT),
            "lid": np.concatenate(LID), "eye": np.concatenate(EYE), "col": np.concatenate(COL),
            "curves": CUR}


def _hex(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def for_spec(spec: dict, cfg: dict | None = None) -> dict | None:
    """The lashes of a spec's base head (world space, as the field is built), cached by the head and settings."""
    from . import base as basemod
    from .spec import expand_mirror
    cfg = cfg or wanted(spec)
    if cfg is None:
        return None
    s = expand_mirror(spec)
    head = basemod.head_of(s, s["base"])
    if head is None:
        return None
    key = hashlib.sha1(json.dumps([cfg, VERSION], sort_keys=True).encode()
                       + np.round(np.asarray(head["verts"], float), 6).tobytes()).hexdigest()[:16]
    if key not in _CACHE:
        if len(_CACHE) > 4:
            _CACHE.pop(next(iter(_CACHE)))
        out = build(head, cfg)
        out["key"] = key
        _CACHE[key] = out
    return _CACHE[key]


def scene_job(name: str, spec: dict, cache_dir) -> dict | None:
    """The scene's lash object: the mesh written into the scene cache (content-named), and its material."""
    cfg = wanted(spec)
    if cfg is None:
        return None
    m = for_spec(spec, cfg)
    if m is None:
        return None
    f = cache_dir / f"lashes_{m['key']}.npz"
    if not f.exists():
        np.savez(f, **{k: v for k, v in m.items() if k not in ("key", "curves")})
    return {"key": m["key"], "npz": str(f), "roughness": float(cfg["roughness"]), "tris": int(len(m["tris"]))}


def triangles(spec: dict) -> int:
    """How many triangles the lashes take (both eyes), without building them: export budgets subtract it."""
    cfg = wanted(spec)
    if cfg is None:
        return 0
    return 2 * 2 * int(cfg["segments"]) * (int(cfg["upper"]["count"]) + int(cfg["lower"]["count"]))


def export_part(spec: dict, out_dir, log=print):
    """The lashes as an export part (asset's low-poly dict: verts, corner_vert, uv, normal, tangent, sign) with tiny
    maps (upper colour | lower colour, roughness, no relief), and per vertex its lash's root and eye centre
    ("lash_root", "lash_centre": what shapes_from_lids turns them with; asset pops them before writing). Two-sided
    material (asset's look "double_sided"). None without lashes."""
    from pathlib import Path

    from PIL import Image

    from . import base as basemod
    from . import hair as hairmod
    from .spec import expand_mirror
    cfg = wanted(spec)
    if cfg is None:
        return None
    m = for_spec(spec, cfg)
    if m is None:
        return None
    s = expand_mirror(spec)
    head = basemod.head_of(s, s["base"])
    V = np.asarray(m["verts"], np.float64)
    T = np.asarray(m["tris"], np.int64)
    uv_v = np.c_[np.where(m["lid"] == 0, 0.25, 0.75), 0.1 + 0.8 * m["along"]]
    UVc = uv_v[T.ravel()]
    _, tt, sg = hairmod._tangents(V, T, UVc)
    nv = np.asarray(m["normal"], np.float64)[T.ravel()]  # the ribbons' own normals (facing forward), not the faces'
    tt = tt - np.sum(tt * nv, 1, keepdims=True) * nv
    tt /= np.linalg.norm(tt, axis=1, keepdims=True) + 1e-12
    part = {"verts": V.astype(np.float32), "corner_vert": T.ravel(), "uv": UVc.astype(np.float32),
            "normal": nv.astype(np.float32), "tangent": tt.astype(np.float32), "sign": sg.astype(np.float32),
            "lash_root": np.asarray(m["root"], np.float64),
            "lash_centre": np.asarray(head["eyes"], np.float64)[m["eye"]]}
    out_dir = Path(out_dir)
    files = {k: out_dir / f"lashes_{k}.png" for k in ("basecolor", "normal", "orm", "specular")}
    up, lo = (tuple(int(round(255 * c)) for c in _hex(h)) for h in (cfg["color"], cfg.get("lower_color", cfg["color"])))
    im = Image.new("RGB", (16, 16), up)
    im.paste(lo, (8, 0, 16, 16))
    im.save(files["basecolor"])
    Image.new("RGB", (16, 16), (128, 128, 255)).save(files["normal"])
    Image.new("RGB", (16, 16), (255, int(255 * float(cfg["roughness"])), 0)).save(files["orm"])
    Image.new("RGBA", (16, 16), (255, 255, 255, 128)).save(files["specular"])
    per = 2 * (int(cfg["segments"]) + 1)
    log(f"lashes: {len(T)} triangles ({int((m['lid'] == 0).sum() // per)} upper, {int((m['lid'] == 1).sum() // per)} "
        "lower lashes), two-sided")
    return "lashes", part, files


def shapes_from_lids(part: dict, skin: list, names) -> dict:
    """The lashes' face shapes from the lids': each lash turns rigidly about its eye's horizontal (x) axis by the angle
    its root's nearest lid vertex turns about it (a blink rolls the lid over the ball; the lashes ride the margin),
    plus what is left of the root's move as a shift. skin: [(verts (n, 3), {name: delta (n, 3)})] of the parts that
    carry the lids. Returns {name: (verts, 3) delta}. (Blender axes: -y forward, z up.)"""
    from scipy.spatial import cKDTree
    R = np.asarray(part["lash_root"], np.float64)
    C = np.asarray(part["lash_centre"], np.float64)
    V = np.asarray(part["verts"], np.float64)
    allX = np.concatenate([x for x, _ in skin])
    _, k = cKDTree(allX).query(R)
    out = {}
    for nm in names:
        D = np.concatenate([sh.get(nm, np.zeros((len(x), 3))) for x, sh in skin])
        dr = D[k]
        if not np.abs(dr).max() > 1e-9:
            out[nm] = np.zeros_like(V)
            continue
        a0, a1 = R - C, R + dr - C
        ang = np.arctan2(a1[:, 2], -a1[:, 1]) - np.arctan2(a0[:, 2], -a0[:, 1])  # forward toward up
        c, s_ = np.cos(ang), np.sin(ang)

        def rot(q):
            return np.c_[q[:, 0], c * q[:, 1] + s_ * q[:, 2], -s_ * q[:, 1] + c * q[:, 2]]
        shift = (R + dr) - (C + rot(a0))
        out[nm] = (C + rot(V - C) + shift) - V
    return out
