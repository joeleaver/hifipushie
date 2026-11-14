"""The beard: zones, density, direction, the hairs' tones, the stubble map. Part of the skin's drawn marks (skin_marks.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_marks
from .skin_marks import _ramp
from .skin_marks_map import (
    _px_m, _save, curvature_at, draw, frames, head_mesh, jacobians, outward, pix, scatter, sphere,
)

# ---- the beard -------------------------------------------------------------------------------------------------------
class _Poly:
    """A closed 2D outline: contains_points(q, radius) = inside, or within radius of it (radius > 0)."""

    def __init__(self, pts):
        self.a = np.asarray(pts, float)
        self.b = np.roll(self.a, -1, 0)

    def contains_points(self, q, radius=0.0):
        q = np.asarray(q, float)
        inside = np.zeros(len(q), bool)
        dmin = np.full(len(q), np.inf)
        for a, b in zip(self.a, self.b):
            cross = ((a[1] > q[:, 1]) != (b[1] > q[:, 1]))
            xi = a[0] + (q[:, 1] - a[1]) * (b[0] - a[0]) / ((b[1] - a[1]) if b[1] != a[1] else 1e-12)
            inside ^= cross & (q[:, 0] < xi)
            if radius > 0:
                ab = b - a
                t = np.clip(((q - a) @ ab) / max(ab @ ab, 1e-18), 0, 1)
                dmin = np.minimum(dmin, np.linalg.norm(q - (a + t[:, None] * ab), axis=1))
        return inside | (dmin < radius) if radius > 0 else inside


def _lips_path(J):
    from .skin import OUTLINES, OUTLINES_DENSE
    names = OUTLINES_DENSE["lips"] if "verm_u00" in J else OUTLINES["lips"]
    return _Poly([[J[n][0], J[n][2]] for n in names if n in J])


def beard_zones(J: dict):
    """zones(P) -> {zone: 0..1}: the beard area as a soft partition (the six sum to 1 at every point), from the
    face's landmarks: moustache (over the mouth's line, between the corners), chin and soul_patch (under it, between
    the corners), jaw (beside the mouth below its line), cheeks (beside it above), neck (under the jaw's edge).
    `hair.stubble.zones` weighs the growth by them; skin_read reads the picture's beard shadow by them."""
    from .skin_zones import interocular
    io = interocular(J)
    L = lambda n: np.asarray(J[n], float)  # noqa: E731
    mc, ll = L("lm_mouth_corner.L"), L("lm_lip_lower")
    chain = [L(f"lm_jaw_{k}.L") for k in range(2, 8)] + [L("lm_chin")]
    jx = np.array([abs(p[0]) for p in chain])[::-1]
    jz = np.array([p[2] for p in chain])[::-1]

    def zones(P):
        q = np.asarray(P, float).copy()
        q[:, 0] = np.abs(q[:, 0])
        neck = _ramp(np.interp(q[:, 0], jx, jz) - q[:, 2], 0.05 * io, 0.2 * io)
        rest = 1 - neck
        lat = _ramp(q[:, 0], abs(mc[0]) - 0.05 * io, abs(mc[0]) + 0.2 * io)
        up = _ramp(q[:, 2], mc[2] - 0.05 * io, mc[2] + 0.15 * io)
        low = rest * (1 - lat) * (1 - up)
        soul = low * np.exp(-((q[:, 0] / (0.16 * io)) ** 2 + ((q[:, 2] - (ll[2] - 0.2 * io)) / (0.13 * io)) ** 2))
        return {"moustache": rest * (1 - lat) * up, "chin": low - soul, "soul_patch": soul, "jaw": rest * lat * (1 - up),
                "cheeks": rest * lat * up, "neck": neck}
    return zones


def beard_density(J: dict, o: dict, curv=None):
    """density(P, N) -> 0..1: where the beard grows and how thickly, from the face's landmarks (interocular units) and,
    given `curv` (a function P -> head_curvature at those points), the surface's own forms. o = the stubble's options
    (cheek_line, neckline, trim, cheeks, patchy, density, seed).

    Untrimmed growth has no edge: the density tapers over 2-3 cm into sparse single hairs (Joe, 2026-10-09: "the edges
    are too hard, and don't follow the face shapes the way that stubble does"), with a few stragglers past it; only
    `trim` makes a line. The upper boundary runs under the cheekbone (a curve from the sideburn, sagging to the
    nostril's level mid-cheek, up to the moustache's corner), the neckline follows the jaw's underside and fades down
    the neck, the cheek's rounded front and the nasolabial bulge are thinner (convex), the moustache, chin and jaw
    full, the lower lip's corners sparse beside a denser soul patch."""
    from .skin_zones import interocular
    from .paint_patterns import noise
    io = interocular(J)
    L = lambda n: np.asarray(J[n], float)  # noqa: E731
    trim = float(o["trim"])
    # the boundaries' half-width: ~2.2 cm across untrimmed, ~4 mm trimmed (a trimmer's line still thins over a few mm:
    # at ~1 mm the designer / heavy cheek line and neckline read as a decal's edge in the 5th blind read)
    soft = io * (0.06 + 0.26 * (1 - trim))
    cl, nl = float(o["cheek_line"]), float(o["neckline"])
    nose_b, nos, mc = L("lm_nose_base"), L("lm_nostril.L"), L("lm_mouth_corner.L")
    j1 = L("lm_jaw_1.L")
    y_ax = j1[1] + 0.3 * io                       # a vertical axis inside the head: angle round it from the front

    def theta(q):
        return np.degrees(np.arctan2(q[:, 0], -(q[:, 1] - y_ax)))
    # the upper boundary as a height over that angle: sideburn front, mid-cheek under the zygoma, moustache corner
    S = j1 + io * np.array([-0.04, -0.28, 0.05 + cl])
    M = mc + io * np.array([0.3, -0.02, 0.45 + 0.6 * cl])
    Cm = 0.5 * (S + M)
    Cm[2] = nos[2] - 0.02 * io + 0.8 * cl * io      # (a straight S-M line cut across the cheekbone's front)
    tS, tM, tC = (float(theta(p[None])[0]) for p in (S, M, Cm))
    tC = 0.5 * (tS + tM)

    def z_top(t):
        t = np.clip(t, tM, tS)
        return (S[2] * (t - tM) * (t - tC) / ((tS - tM) * (tS - tC)) + M[2] * (t - tS) * (t - tC) / ((tM - tS) * (tM - tC)) +
                Cm[2] * (t - tS) * (t - tM) / ((tC - tS) * (tC - tM)))
    # the jaw's edge (its landmark chain, mirrored to the chin) as a height over |x|: the neckline hangs below it
    chain = [L(f"lm_jaw_{k}.L") for k in range(2, 8)] + [L("lm_chin")]
    jx = np.array([abs(p[0]) for p in chain])[::-1]
    jz = np.array([p[2] for p in chain])[::-1]
    lips = _lips_path(J)
    y_ear = j1[1]
    ztop_sb = L("lm_jaw_0.L")[2] - 0.05 * io
    cheeks, patchy, seed = float(o["cheeks"]), float(o["patchy"]), int(o.get("seed", 0))

    def region(q, P, grow):
        """1 inside the beard's area, its boundaries feathered by `soft` and moved out by `grow` (m)."""
        t = theta(q)
        # (from the moustache's top to the cheek's: over ~2 cm untrimmed; 9 mm made a box with hard sides under the nose
        # on Garrett, skin3)
        kl = 0.18 * io * (1 - trim)
        lat = _ramp(q[:, 0], M[0] - 0.12 * io - kl, M[0] + 0.02 * io + kl)
        top_c = _ramp(q[:, 2] - grow, z_top(t) + soft, z_top(t) - soft)
        top_m = _ramp(q[:, 2] - grow, nos[2] + 0.02 * io + soft, nos[2] + 0.02 * io - soft)
        d = lat * top_c + (1 - lat) * top_m
        drop = np.interp(q[:, 0], jx, jz) - q[:, 2]           # how far below the jaw's edge
        d *= _ramp(drop - grow, (0.55 + nl) * io + soft, (0.55 + nl) * io - soft)
        d *= _ramp(q[:, 2] - grow, ztop_sb + 0.1 * io, ztop_sb - 0.1 * io)
        back = y_ear + io * (0.04 + 0.35 * _ramp(q[:, 2], L("lm_jaw_3.L")[2], L("lm_jaw_4.L")[2] - 0.2 * io))
        d *= _ramp(q[:, 1] - 0.5 * grow, back + 0.06 * io, back - 0.06 * io)
        return d

    def dens(P, Nrm):
        q = P.copy()
        q[:, 0] = np.abs(q[:, 0])
        d = region(q, P, 0.0)
        if trim < 0.5:   # stragglers: a few single hairs out past the fade
            d = np.maximum(d, 0.06 * (1 - 2 * trim) * region(q, P, 1.4 * soft))
        nose = _ramp(q[:, 2], nose_b[2] - 0.005 * io, nose_b[2] + 0.04 * io) * _ramp(q[:, 0], nos[0] + 0.2 * io, nos[0] + 0.06 * io)
        d *= 1 - nose
        front = q[:, 1] < mc[1] + 0.25 * io
        d[front & lips.contains_points(P[:, [0, 2]], radius=0.0004)] = 0
        # zones: the cheek (out beside the mouth, above the jaw) thinner; the neck a little thinner
        jaw = _ramp(q[:, 2], mc[2] - 0.1 * io, mc[2] + 0.35 * io)
        side = _ramp(q[:, 0], mc[0] + 0.05 * io, mc[0] + 0.35 * io)
        cheek = jaw * side
        w = 1 - (1 - cheeks) * cheek
        if curv is not None:   # rounded forms carry less: the cheek's front, the nasolabial bulge
            k = curv(P)
            w *= 1 - 0.45 * _ramp(k, 0.6, 1.8) * np.maximum(cheek, _ramp(q[:, 0], mc[0] - 0.05 * io, mc[0] + 0.1 * io) * jaw)
        # round the mouth: sparse at the lower lip's corners and the connector beside them, a denser soul patch
        g = lambda cx, cz, rx, rz: np.exp(-(((q[:, 0] - cx) / rx) ** 2 + ((q[:, 2] - cz) / rz) ** 2))  # noqa: E731
        w *= 1 - (0.3 + 0.4 * patchy) * g(mc[0] + 0.14 * io, mc[2] - 0.2 * io, 0.12 * io, 0.14 * io)
        w *= 1 - 0.35 * g(mc[0] - 0.05 * io, mc[2] - 0.22 * io, 0.1 * io, 0.1 * io)
        w = np.minimum(w * (1 + 0.15 * g(0.0, L("lm_lip_lower")[2] - 0.2 * io, 0.12 * io, 0.12 * io)), 1.0)
        w *= 1 - 0.2 * np.exp(-(q[:, 0] / (0.045 * io)) ** 2) * _ramp(q[:, 2], mc[2], mc[2] + 0.1 * io)   # the philtrum
        w *= 1 - 0.2 * _ramp(np.interp(q[:, 0], jx, jz) - q[:, 2], 0.15 * io, 0.6 * io)                  # the neck
        if patchy > 0:
            nz = noise(P, {"scale": 0.014, "octaves": 2, "seed": 300 + seed})
            pn = min(patchy, 0.3)   # a few random gaps in any beard
            w *= (1 - pn) + pn * _ramp(nz, 0.44, 0.52)   # (hair there or missing, not a stain: sharp gaps keeping sparse single hairs)
            pa = float(np.clip((patchy - 0.25) / 0.5, 0, 1))
            if pa > 0:
                # a patchy beard grows where a beard comes in first: the moustache along the upper lip, a soul patch,
                # the chin's underside and the jaw's front edge; the cheeks and the connectors beside the mouth stay
                # bare (ref_33). Random noise blobs there read as stains (four blind reads).
                lu, ll = L("lm_lip_upper"), L("lm_lip_lower")
                z_lip = np.interp(q[:, 0], [0.0, mc[0]], [lu[2], mc[2]])
                mous = (_ramp(q[:, 0], mc[0] + 0.06 * io, mc[0] - 0.04 * io) * _ramp(q[:, 2], z_lip - 0.01 * io, z_lip + 0.04 * io)
                        * _ramp(q[:, 2], nose_b[2] - 0.02 * io, nose_b[2] - 0.1 * io))
                soul = _ramp(q[:, 0], 0.14 * io, 0.06 * io) * _ramp(q[:, 2], ll[2] - 0.02 * io, ll[2] - 0.07 * io) * _ramp(q[:, 2], ll[2] - 0.32 * io, ll[2] - 0.22 * io)
                e = np.interp(q[:, 0], jx, jz) - q[:, 2]     # below the jaw's edge (> 0)
                band = _ramp(e, -0.22 * io, -0.06 * io) * _ramp(e, 0.4 * io, 0.22 * io) * _ramp(q[:, 0], mc[0] + 0.75 * io, mc[0] + 0.25 * io)
                anat = np.maximum.reduce([mous, 0.85 * soul, 0.9 * band])
                fine_nz = noise(P, {"scale": 0.005, "octaves": 2, "seed": 310 + seed})
                keep = anat * (0.5 + 0.5 * _ramp(fine_nz, 0.3, 0.7))   # thinning inside the patches: fewer hairs, not blotches
                w *= (1 - pa) + pa * keep
        if zw:   # hair.stubble.zones: the growth weighed zone by zone (a goatee, bare cheeks, a moustache alone)
            u = bz(P)
            w = w * sum(float(zw.get(k, 1.0)) * u[k] for k in skin_marks.BEARD_ZONES)
        return np.clip(d * w * float(o["density"]), 0, 1)
    zw = {k: v for k, v in (o.get("zones") or {}).items() if abs(float(v) - 1.0) > 1e-6}
    bz = beard_zones(J) if zw else None
    return dens


def beard_direction(J: dict, P: np.ndarray, Nrm: np.ndarray) -> np.ndarray:
    """The way hair grows (a world vector; projected on the skin later): down, out from the philtrum on the moustache,
    toward the throat under the chin."""
    from .skin_zones import interocular
    io = interocular(J)
    mc = np.asarray(J["lm_mouth_corner.L"], float)
    nb = np.asarray(J["lm_nose_base"], float)
    g = np.tile(np.array([0.0, 0.35, -1.0]), (len(P), 1))
    must = _ramp(P[:, 2], mc[2] - 0.05 * io, mc[2] + 0.1 * io) * _ramp(np.abs(P[:, 0]), mc[0] + 0.5 * io, mc[0]) * \
        _ramp(P[:, 2], nb[2] + 0.05 * io, nb[2] - 0.05 * io)
    g[:, 0] += 0.9 * np.sign(P[:, 0]) * _ramp(np.abs(P[:, 0]), 0.0, 0.25 * io) * must
    g[:, 1] += 0.8 * np.clip(-Nrm[:, 2], 0, 1)    # under the chin: toward the throat
    # cheeks: a little forward, toward the chin
    g[:, 1] -= 0.3 * _ramp(np.abs(P[:, 0]), mc[0], mc[0] + 0.5 * io) * (1 - must)
    return g


def hair_tones(fine: np.ndarray, white: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    """Each stubble hair's tone (0 dark .. 1 white: its cover splits between the dark and the white channel) and its
    edge weight, from `fine` (0 at the beard's fading edge .. 1 where it is full) and whether it is a white hair.

    Where a beard thins out, terminal hair gives way to vellus: fewer hairs, and each one finer, LIGHTER and fainter.
    Before (r15, Garrett) the fade kept the dark hairs' full darkness and 35% of their cover, and the grey share fell
    away from the chin, so the beard's top edge was a line of separate black specks over a pale patch, while the photo's
    grey stubble is a fine light speckle that thins into the cheek. A greying beard's hairs also range from grey to white,
    not two classes (0.75-1 white, 0-0.15 near-black read as chalk blobs and pepper)."""
    n = len(fine)
    dark = rng.uniform(0.0, 0.2, n) + 0.5 * (1 - fine)            # pigmented; vellus at the fade: a light grey, not a speck
    tone = np.clip(np.where(white, rng.uniform(0.55, 1.0, n), dark), 0, 1)
    ew = 0.12 + 0.88 * fine ** 2                                  # cover falls with the density (fine ** 2 ~ density / .6)
    return tone, ew


def stubble_map(spec: dict, part: str, J: dict, o: dict) -> tuple[str, dict, dict]:
    """The stubble map's file, the image dict's placement keys, and stats. o: the resolved options (length m, density,
    grey, patchy, trim, cheeks, cheek_line, neckline, size, seed)."""
    from . import store
    from scipy.ndimage import gaussian_filter
    sp = sphere(J, (-80.0, 52.0), 230.0, 0.00006 if o["length"] < 0.003 else 0.00008)
    V, N, F = head_mesh(spec, part, J)
    key = hashlib.sha1(json.dumps([o, np.asarray(V[:50]).round(5).tolist(), len(V), sp["img"], skin_marks.VERSION, skin_marks.SUB_DASH, skin_marks.SUB_GAP],
                                  sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = store.HOME / "_images" / f"mk_stubble_{key}.png"
    stats_f = path.with_suffix(".json")
    if path.exists() and stats_f.exists():
        return str(path), sp["img"], json.loads(stats_f.read_text())
    rng = np.random.default_rng(900 + int(o.get("seed", 0)))
    dens = beard_density(J, o, curvature_at(spec, part, J))
    P, Nrm, d = scatter(V, N, F, dens, skin_marks.HAIRS_PER_M2 * float(o.get("count", 1.0)), rng)   # (count: more hairs, not a darker shadow)
    keep = outward(sp, P, Nrm, V)   # (no hairs on skin facing in: the mouth's inside, a lip's inner roll)
    P, Nrm, d = P[keep], Nrm[keep], d[keep]
    n = len(P)
    W, H = sp["W"], sp["H"]
    R = np.zeros((H, W), np.float32)
    G = np.zeros((H, W), np.float32)
    if n:
        g = beard_direction(J, P, Nrm)
        ang = rng.normal(0, np.radians(11), n)              # each hair its own way, a little (the grain reads)
        t1, t2 = frames(Nrm, g)
        x0, A = jacobians(sp, P, t1, t2)
        # where the beard thins out (its fading edges, stragglers) the hairs are finer, shorter and lighter: terminal
        # beard hair gives way to vellus
        fine = np.clip(d / 0.6, 0, 1) ** 0.5
        Lh = float(o["length"]) * rng.lognormal(0, 0.22, n) * (0.55 + 0.45 * fine)  # grown since the shave, unevenly
        elev = np.radians(np.clip(62 - 5.5 * Lh * 1000, 18, 62))                 # short stubble stands up (dots, short dashes); longer lies flatter
        proj = Lh * np.cos(elev)
        wid = 0.000105 * float(o["size"]) * rng.uniform(0.8, 1.2, n) * (0.5 + 0.5 * fine)
        curl = rng.normal(0, 1, n) * np.clip(Lh / 0.006, 0, 1.2) * 0.25          # bend (rad over the hair's length)
        ca, sa = np.cos(ang), np.sin(ang)
        pxm = _px_m(A)
        # (grey comes in first on the chin and round the mouth, last on the upper cheeks: a uniform share read as
        # "chalk scratches" evenly over the jaw, skin3's 6th blind read)
        from .skin_zones import interocular
        io = interocular(J)
        chin = np.exp(-(((P - (np.asarray(J["lm_chin"], float) + [0.0, 0.0, 0.3 * io])) / (np.array([0.55, 0.6, 0.45]) * io)) ** 2).sum(1))
        # (r16: 0.6 + 0.8 x chin left the moustache and the beard's top nearly all dark hairs, black pepper over a pale chin
        # on Garrett, whose photo greys evenly: the chin comes first, but only a little)
        gz = 0.85 + 0.3 * chin
        white = rng.random(n) < np.clip(float(o["grey"]) * gz / gz.mean(), 0, 1)   # (the share overall stays `grey`)
        tone, ew = hair_tones(fine, white, rng)
        reach = proj + wid + 2 * pxm

        def shape(i, s, t):
            a = ca[i] * s + sa[i] * t           # along the hair
            b = -sa[i] * s + ca[i] * t          # across
            l = max(proj[i], 0.5 * wid[i])
            b = b - curl[i] * a * a / max(l, 1e-6) * 0.5
            aa = 0.5 * pxm[i]
            hw = 0.5 * wid[i]
            hwa = hw * (1 - 0.35 * np.clip(a / l, 0, 1))   # tapering a little
            across = _ramp(np.abs(b), hwa + aa, np.maximum(hwa - aa, 0.0))
            ends = _ramp(a, -aa - 0.25 * wid[i], aa - 0.25 * wid[i] + 1e-9) * _ramp(a, l + aa, l - aa)
            cov = across * ends
            if proj[i] < wid[i]:            # a cut stub: a round dot
                r = np.hypot(s, t)
                cov = _ramp(r, hw + aa, max(hw - aa, 0.0))
            root = _ramp(np.hypot(s, t), 0.75 * wid[i] + aa, max(0.75 * wid[i] - aa, 0.0))   # the follicle: a dark dot where it leaves the skin
            return np.maximum(cov, root) * min(1.0, (wid[i] / max(pxm[i], 1e-9)) ** 0.5 + 0.35)  # sub-pixel hairs read fainter
        # (cut flush, a fresh shave's stubs are barely there: their darkness grows with the length up to 0.3 mm)
        flush = np.clip(Lh / 0.0003, 0.15, 1.0)
        draw(R, x0, A, reach, shape, (1 - tone) * 0.95 * ew * flush)
        draw(G, x0, A, reach, shape, tone * 0.95 * ew)
        # the shaft under the skin: a dark hair runs ~1 mm on at a slant below the surface before its follicle, seen
        # through the epidermis as a soft grey dash behind the exit point (what makes a 1-day shadow read as a field of
        # dashes at a distance, not a smooth wash: skin3 measured the beard's 1 mm-scale L contrast at 1/4-1/8 of
        # ref_30 / ref_29's with the stubs alone). A white hair is invisible under the skin.
        ls = 0.0013 * rng.uniform(0.7, 1.3, n)
        ws = 0.5 * np.maximum(1.8 * wid, 0.0002)

        def sub_shape(i, s, t):
            a = ca[i] * s + sa[i] * t
            b = -sa[i] * s + ca[i] * t
            aa = 0.5 * pxm[i]
            fade = np.clip(1 + a / ls[i], 0, 1) ** 0.7      # 1 at the exit, 0 where it's too deep to see
            return _ramp(np.abs(b), ws[i] + aa, max(ws[i] * 0.3, 0.0)) * _ramp(a, aa, -aa) * fade
        Sd = np.zeros((H, W), np.float32)
        draw(Sd, x0, A, ls + ws + 2 * pxm, sub_shape, (1 - tone) * (0.25 + 0.75 * fine ** 2))
        # the shadow: the EXPECTED density of dark roots (hair in the skin), from a dense sample of the density field
        # (not the drawn roots' count: blurred enough to hide its Poisson noise, ~3 mm, it fell off 3 mm short of every
        # edge and left a pale band over the lip), each sample weighted by 1 / its pixel's area on the skin
        K = 12
        Pc, Nc, dc = scatter(V, N, F, dens, K * skin_marks.HAIRS_PER_M2, np.random.default_rng(950 + int(o.get("seed", 0))), keep_all=True)
        keep = outward(sp, Pc, Nc, V)
        Pc, Nc, dc = Pc[keep], Nc[keep], dc[keep]
        _, Ac = jacobians(sp, Pc, *frames(Nc, np.tile([1.0, 0, 0], (len(Pc), 1))))
        xi = np.round(pix(sp, Pc)).astype(int)
        area = np.abs(Ac[:, 0, 0] * Ac[:, 1, 1] - Ac[:, 0, 1] * Ac[:, 1, 0])
        Bd = np.zeros((H, W), np.float32)
        Ba = np.zeros((H, W), np.float32)
        # (the dark hairs' share ** 0.6: a salt-and-pepper beard still reads as a shadow, ref_28's beard - cheek dL ~ -9)
        np.add.at(Bd, (xi[:, 1], xi[:, 0]), (dc * (1 - float(o["grey"])) ** 0.6 * area).astype(np.float32))
        np.add.at(Ba, (xi[:, 1], xi[:, 0]), area.astype(np.float32))
        pm = float(np.median(pxm))
        Bd, Ba = gaussian_filter(Bd, 0.0012 / pm), gaussian_filter(Ba, 0.0012 / pm)
        # the average density over the samples (two skins over one pixel, a lip's inner roll over its outer, count
        # once: a head whose mesh doubled there summed to a full shadow over its whole face), where there is skin
        avg = Bd / np.maximum(Ba, 1e-6)
        support = np.clip(Ba / (0.5 * K * skin_marks.HAIRS_PER_M2), 0, 1)
        Bs = np.clip(avg * support / 0.7, 0, 1) ** 1.2   # full at ~70% of a full dark beard; thin edges fade faster
        # the shadow carries the shafts' grain: gaps between them lighter, the shafts darker (the layer's opacity is
        # raised to match: skin_features_hair._stubble_map), so the mean stays the measured beard-minus-cheek darkening
        Bs = Bs * (skin_marks.SUB_GAP + (1 - skin_marks.SUB_GAP) * np.clip(skin_marks.SUB_DASH * Sd, 0, 1))
    else:
        Bs = np.zeros((H, W), np.float32)
        pm = 0.0
    _save(path, np.dstack([R, G, Bs]))
    stats = {"hairs": int(n), "px_mm": round(pm * 1000, 4), "size": [W, H], "white": round(float(np.mean(white)) if n else 0.0, 3)}
    stats_f.write_text(json.dumps(stats))
    return str(path), sp["img"], stats
