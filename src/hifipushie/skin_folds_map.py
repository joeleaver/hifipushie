"""A fold in the map: its own crease snapped, its paths, `fold_map`. Part of the skin's folds (skin_folds.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_folds
from .spec import SpecError
from .skin_folds import geometry_key, sided
from .skin_folds_surface import map_surface, surface

def own_crease(S, P: np.ndarray, ac: np.ndarray, nrm: np.ndarray, reach: float) -> tuple:
    """(offset mm per station, share): where the HEAD'S OWN crease lies across a path (the shape model's own fold: a
    middle-aged GNM head has a nasolabial crease of its own, and a fold laid on the nominal path beside it reads as
    two parallel cuts). Per station the skin's height profile across the path (seated points, height along the
    path's normal), its second derivative at a 2 mm scale: the most concave point within `reach` mm, where it is
    concave enough; a smooth curve through those (quadratic), 0 where the head has none. share: of stations with a
    crease."""
    from scipy.ndimage import gaussian_filter1d
    du = 0.5
    u = np.arange(-reach - 3.0, reach + 3.0 + 1e-6, du)
    Q = P[:, None, :] + 0.001 * u[None, :, None] * ac[:, None, :]
    X = S.seat(Q.reshape(-1, 3)).reshape(len(P), len(u), 3)
    h = ((X - P[:, None, :]) * nrm[:, None, :]).sum(-1) * 1000.0            # mm
    h = gaussian_filter1d(gaussian_filter1d(h, 2.0 / du, axis=1, mode="nearest"), 2.0, axis=0, mode="nearest")
    d2 = np.gradient(np.gradient(h, du, axis=1), du, axis=1)
    inner = np.abs(u) <= reach
    k = np.argmax(np.where(inner[None, :], d2, -np.inf), 1)
    val = d2[np.arange(len(P)), k]
    ok = (val >= skin_folds.SNAP_CURV) & (np.abs(u[k]) < reach - 0.75)
    share = float(ok.mean())
    if ok.sum() < max(6, skin_folds.SNAP_SHARE * len(P)):
        return np.zeros(len(P)), share
    t = np.linspace(0, 1, len(P))
    from scipy.ndimage import median_filter
    uu = median_filter(u[k], 7, mode="nearest")
    co = np.polyfit(t[ok], uu[ok], 2)
    off = np.clip(np.polyval(co, np.clip(t, t[ok].min(), t[ok].max())), -reach, reach)
    return off, share


def _resample(P: np.ndarray, step: float) -> np.ndarray:
    """A polyline as a smooth curve (Catmull-Rom) sampled every `step`."""
    P = np.asarray(P, float)
    if len(P) > 2:
        Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
        out = []
        for i in range(1, len(Q) - 2):
            for t in np.linspace(0, 1, 12, endpoint=False):
                p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
                out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        P = np.array(out + [P[-1]])
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    n = max(int(round(s[-1] / step)) + 1, 4)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, P[:, k]) for k in range(3)], 1)


def paths(spec: dict | None, part: str, J: dict, cfg: dict | None = None, names=None, S=None) -> dict:
    """{(name, side): {"P": (m, 3) stations on the skin every STATION, "across": (m, 3) unit vectors in the skin
    toward the fold's plus side, "t": 0..1 along, "amount": (m,) (the side's amount, 0 outside its extent, eased at the
    ends), "width", "roll"}}. cfg = options(skin["folds"]): the measured shift is applied; None: the landmark paths
    themselves (what the reader measures from), amount 1."""
    from .skin_zones import interocular
    io = interocular(J)
    S = S or surface(spec, part, J)
    out = {}
    for name in (names or (cfg if cfg is not None else skin_folds.FOLDS)):
        fd = skin_folds.FOLDS[name]
        o = (cfg or {}).get(name)
        for sd, sx in (((".L", 1.0), (".R", -1.0)) if sided(name) else (("", 1.0),)):
            try:
                # each control point is WALKED over the skin from its landmark (half-millimetre steps, re-seated): the
                # offset alone floats off the surface, and seating that along the wrap's ray (or onto the nearest
                # vertex) put a lid's fold several mm up the lid on one side and across the eye's corner on the other
                # (in the head's own frame; seated from the FRONT: the visible skin under the offset point. The first
                # version walked each point over a mesh from its landmark; on the exact field's closest point a lid's
                # landmark landed inside the lid and the tear trough ran round the socket)
                jn = lambda a: a[:-2] + sd if a.endswith(".L") else a  # noqa: E731
                # (a head with the 68 landmarks only has no lm_lid_*_in / _out: the path runs through the rest)
                cps = [(a, off) for a, off in fd["path"] if jn(a) in J or not a.split(".")[0].endswith(("_in", "_out"))]
                pl = np.array([np.asarray(J[jn(a)], float)
                               + io * (sx * off[0] * S.right - off[1] * S.front + off[2] * S.up) for a, off in cps])
                pl = S.seat(pl)
            except KeyError as err:
                raise SpecError(f"skin folds.{name}: needs joint {err.args[0]!r} (a GNM head's lm_* landmarks)")
            P = S.seat(_resample(pl, skin_folds.STATION))
            nrm = S.normal(P)
            tan = np.gradient(P, axis=0)
            tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-12)
            ac = np.cross(nrm, tan)
            ac /= np.maximum(np.linalg.norm(ac, axis=1, keepdims=True), 1e-12)
            plus = sx * fd["plus"][0] * S.right - fd["plus"][1] * S.front + fd["plus"][2] * S.up
            if float((ac @ plus).mean()) < 0:
                ac = -ac
            t = np.linspace(0, 1, len(P))
            snapped = None
            if fd.get("snap"):       # onto the head's own crease, where it has one
                cache = S.__dict__.setdefault("_snap", {})
                key = (name, sd, len(P))
                if key not in cache:
                    cache[key] = own_crease(S, P, ac, nrm, float(fd["snap"]))
                off, share = cache[key]
                snapped = (round(float(np.median(off)), 2), round(share, 2))
                if np.abs(off).max() > 0.05:
                    P = S.seat(P + 0.001 * off[:, None] * ac)
            amount = np.ones(len(P))
            if o is not None:
                q = o["sides"][sd]
                sh = np.interp(t, np.linspace(0, 1, len(q["shift"])), q["shift"]) * 0.001 if q["shift"] else np.zeros(len(t))
                if o.get("hood"):     # hooding: the line comes down toward the lashes over the outer half
                    u_ = np.clip((t - 0.4) / 0.5, 0, 1)
                    sh = sh - 0.001 * skin_folds.HOOD_DROP * o["hood"] * u_ * u_ * (3 - 2 * u_)
                if q["shift"] or o.get("hood"):
                    if fd.get("smooth"):     # (a fold's line is smooth: station-to-station steps in a measured shift kink it)
                        from scipy.ndimage import gaussian_filter1d
                        sh = gaussian_filter1d(sh, fd["smooth"] * 0.001 / skin_folds.STATION, mode="nearest")
                    P = S.seat(P + sh[:, None] * ac)
                e0, e1 = q["extent"]
                amount = o["amount"] * q["amount"] * ((t >= e0) & (t <= e1))
            if fd.get("smooth") and o is not None:   # (the line itself: what the map draws and the geometry sweeps)
                from scipy.ndimage import gaussian_filter1d
                P = S.seat(gaussian_filter1d(P, fd["smooth"] * 0.001 / skin_folds.STATION, axis=0, mode="nearest"))
                P = gaussian_filter1d(P, 1.5, axis=0, mode="nearest")
            ease = np.clip(np.minimum(t - (o["sides"][sd]["extent"][0] if o else 0.0), (o["sides"][sd]["extent"][1] if o else 1.0) - t) / 0.18, 0, 1)
            amount = amount * (0.25 + 0.75 * np.sin(0.5 * np.pi * ease))   # a fold fades toward its ends
            out[(name, sd)] = {"P": P, "across": ac, "t": t, "amount": amount, "width": (o or fd)["width"],
                               "roll": (o["roll"] if o else 1.0), "depth": (o["depth"] if o else 1.0), "normal": S.normal(P),
                               "hood": float((o or {}).get("hood", 0.0)), "snapped": snapped}
    return out


def fold_map(spec: dict, part: str, J: dict, cfg: dict) -> tuple[str, dict, dict]:
    """The fold map's file, the image dict's placement keys, stats. cfg = options(skin["folds"])."""
    from scipy.ndimage import gaussian_filter
    from scipy.spatial import cKDTree
    from . import skin_marks as sm, store
    from . import skin_marks_map, skin_marks_pores
    S = map_surface(spec, part, J)
    sp = S.sp
    geo = geometry_key(spec.get("skin") or {}) is not None
    key = hashlib.sha1(json.dumps([cfg, geo, np.asarray(S.V[:50]).round(5).tolist(), len(S.V), sp["img"], skin_folds.VERSION, sm.VERSION, skin_folds.FOLDS, skin_folds.OCCLUSION, skin_folds.OCC_WIDTH],
                                  sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = store.HOME / "_images" / f"mk_folds_{key}.png"
    stats_f = path.with_suffix(".json")
    if path.exists() and stats_f.exists():
        return str(path), sp["img"], json.loads(stats_f.read_text())
    W, H = sp["W"], sp["H"]
    out = np.zeros((H, W, 3), np.float32)
    ps = paths(spec, part, J, cfg)
    rows = skin_marks_pores._pixel_points(sp, S.V, S.Nall, step=2)
    stats = {"size": [W, H], "folds": {}}
    for (name, sd), q in ps.items():
        fd = skin_folds.FOLDS[name]
        if not (q["amount"] > 0).any():
            continue
        x = skin_marks_map.pix(sp, q["P"])
        reach = 0.001 * (max(q["width"] * 1.5 * 2.5, (fd["roll"][0] + 1.5 * fd["roll"][1]) if fd["roll"] else 0.0) + 2.0)
        pad = int(reach / skin_folds.PX * 1.6) + 4
        x0, x1 = max(int(np.nanmin(x[:, 0])) - pad, 0), min(int(np.nanmax(x[:, 0])) + pad, W)
        y0, y1 = max(int(np.nanmin(x[:, 1])) - pad, 0), min(int(np.nanmax(x[:, 1])) + pad, H)
        if x1 <= x0 or y1 <= y0:
            continue
        Q, ok, _ = rows(y0, y1)
        Q = Q.reshape(y1 - y0, W, 3)[:, x0:x1].reshape(-1, 3)
        ok = ok.reshape(y1 - y0, W)[:, x0:x1].ravel()
        # (the distance to the LINE: its stations a millimetre apart, measured to the nearest, drew a lid's fold as dashes)
        tt = np.linspace(0, 1, 10 * (len(q["P"]) - 1) + 1)
        fine = lambda arr: np.stack([np.interp(tt, q["t"], arr[:, k_]) for k_ in range(arr.shape[1])], 1)  # noqa: E731
        Pf, Af, amf = fine(q["P"]), fine(q["across"]), np.interp(tt, q["t"], q["amount"])
        d, i = cKDTree(Pf).query(Q)
        s = ((Q - Pf[i]) * Af[i]).sum(1)
        if geo:
            # the map's pixels lie on the surface WITH the relief, the line on the fold-free one: the distance is
            # measured IN the skin (the height over the line left out). In 3D a lid's crease lost its dark line
            # exactly where the fold's lip stands highest (mid-lid: 0.7 mm out, the line's sigma 0.3-0.6 mm)
            Nf = fine(q["normal"])
            Nf /= np.maximum(np.linalg.norm(Nf, axis=1, keepdims=True), 1e-12)
            hh = ((Q - Pf[i]) * Nf[i]).sum(1)
            d = np.sqrt(np.maximum(d * d - hh * hh, 0.0))
            # (and no cut ends: the colour eases in with the relief)
            on_ = np.flatnonzero(amf > 0)
            if len(on_):
                sp_ = float(np.median(np.linalg.norm(np.diff(Pf, axis=0), axis=1)))
                e_ = np.clip(np.minimum(np.arange(len(amf)) - on_[0], on_[-1] - np.arange(len(amf))) * sp_ / skin_folds.END, 0, 1)
                amf = amf * e_ * e_ * (3 - 2 * e_)
        a = amf[i] * ok
        sg = 0.001 * q["width"] / 2.355
        groove = a * fd["depth"] * np.exp(-0.5 * (d / sg) ** 2)
        shade = a * fd["shade"] * np.exp(-0.5 * (d / (2.6 * sg)) ** 2)
        tint = a * fd["tint"] * np.exp(-0.5 * (d / (0.8 * sg)) ** 2)
        roll = np.zeros_like(groove)
        if fd["roll"]:
            r0, rw, rk = fd["roll"]
            along = np.sqrt(np.maximum(d * d - s * s, 0.0))          # past the path's ends
            roll = a * rk * q["roll"] * np.exp(-0.5 * ((s - 0.001 * r0) / (0.001 * rw / 2.355)) ** 2) * np.exp(-0.5 * (along / (0.004)) ** 2)
        blk = out[y0:y1, x0:x1]
        shp = blk.shape[:2]
        # r: the groove's depth (x DEPTH); g: the roll (x BULGE); b: the darkening (crease line + soft shade, 0..1)
        if geo:   # r: the crease's occlusion instead of a painted groove
            groove = a * skin_folds.OCCLUSION[name] * np.exp(-0.5 * (d / (skin_folds.OCC_WIDTH.get(name, 0.6) * sg)) ** 2)
        blk[..., 0] = np.maximum(blk[..., 0], (groove / 1.5).reshape(shp))
        blk[..., 1] = np.maximum(blk[..., 1], (roll / 1.5).reshape(shp))
        blk[..., 2] = np.maximum(blk[..., 2], np.clip(np.maximum(tint, shade), 0, 1).reshape(shp))
        stats["folds"][name + sd] = {"stations": int(len(q["P"])), "amount": round(float(q["amount"].max()), 3)}
    for k in range(3):
        out[..., k] = gaussian_filter(out[..., k], 1.0)
    skin_marks_map._save(path, out)
    stats_f.write_text(json.dumps(stats))
    return str(path), sp["img"], stats
