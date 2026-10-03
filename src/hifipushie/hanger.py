"""Hangers and rails: general props a garment hangs on, the way a person hangs one.

A hung garment is dressed on the body first (cloth.build), then the hanger is put INSIDE it where the body's shoulders
were (arms under the shoulder seams, following the shoulders' slope; the hook up through the neck opening, curled over
a rail), the body is taken away and gravity settles the garment onto the hanger. Nothing pins the cloth: contact with
the hanger carries the weight. `support` and `on_hanger` measure that afterwards (the report's "hanger" line).

Garment state (cloth spec): {"hang": {"hanger": {...}, "rail": {...} | false}}; "hung" is the default hanger.
  hanger: kind "wood" (a shaped coat hanger: arms ~1.6 cm round at the centre broadening to 4 cm deep rounded shoulder
          ends) | "wire" (a 3.6 mm wire; too thin for coarse cloth meshes to rest on reliably), width m (tip to tip;
          default the body's shoulder points less 2 cm: a hanger sits inside the shoulder seams), bar (a trouser bar
          between the arms), slope deg (default the body's shoulder slope), clear m (how far under the shoulders'
          surface the arms' tops sit, default 8 mm), rise m (the hook's rod above the arms; default: clear of the
          garment's collar by 5 cm)
  rail:   a face-out bar the hook hangs on, running back from the hook: length m (0.45), radius m (0.0125), posts
          bool (true: a post down to the floor at its back end)
Frame: the model's (metres, Z up, the body faces -Y). The hanger's plane is the body's frontal plane (x-z); its hook
curls round the bar, which runs along y (front to back) behind it: nothing stands in front of the garment.
"""
from __future__ import annotations

import numpy as np

KINDS = {
    # radii (m): arm section depth (y) x height (z) at the centre and at the shoulder end, the end's rounded tip,
    # the hook wire, the bar
    "wood": {"centre": (0.008, 0.011), "end": (0.020, 0.013), "hook_r": 0.0028, "bar_r": 0.006, "colour": "#9a6b3f"},
    "wire": {"centre": (0.0018, 0.0018), "end": (0.0018, 0.0018), "hook_r": 0.0018, "bar_r": 0.0018,
             "colour": "#b8b8b8"},
}
HANGER_KEYS = {"kind", "width", "bar", "slope", "clear", "rise"}
RAIL_KEYS = {"length", "radius", "posts"}
RAIL_COLOUR = "#8c8f94"
CONTACT = 0.008  # cloth within this of the hanger touches it (cloth thickness + the solvers' contact distances)


def spec_of(state) -> dict | None:
    """The hanger + rail options of a garment state, or None when it isn't hung on a hanger (worn, draped, or the old
    pinned hang without a hanger)."""
    if state == "hung":
        return {"hanger": {}, "rail": {}}
    if isinstance(state, dict) and "hang" in state:
        hg = state["hang"] or {}
        if "hanger" in hg or not hg.get("pins"):
            rail = hg.get("rail", {})
            return {"hanger": dict(hg.get("hanger") or {}), "rail": None if rail is False else dict(rail or {})}
    return None


def validate(hg: dict, where: str) -> None:
    from .cloth import ClothError
    h = hg.get("hanger", {})
    if not isinstance(h, dict) or set(h) - HANGER_KEYS:
        raise ClothError(f"{where}: hanger is {{{', '.join(sorted(HANGER_KEYS))}}}")
    if h.get("kind", "wood") not in KINDS:
        raise ClothError(f"{where}: hanger kind is {' or '.join(KINDS)}")
    for k, lo, hi in (("width", 0.2, 0.7), ("clear", 0.0, 0.05), ("rise", 0.02, 0.4), ("slope", -5, 45)):
        if k in h and not (isinstance(h[k], (int, float)) and lo <= h[k] <= hi):
            raise ClothError(f"{where}: hanger {k} is {lo}..{hi}")
    r = hg.get("rail", {})
    if r is not False and (not isinstance(r, dict) or set(r) - RAIL_KEYS):
        raise ClothError(f"{where}: rail is false or {{{', '.join(sorted(RAIL_KEYS))}}}")


# ---------------------------------------------------------------- geometry


def _top(body, x: float, y: float, ceiling: float) -> float | None:
    """The body's upper surface under (x, y) below `ceiling` (a vertical ray down: the shoulder under the jaw)."""
    V, T = body.V, body.T
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    near = (np.minimum(np.minimum(A[:, 0], B[:, 0]), C[:, 0]) <= x) & (np.maximum(np.maximum(A[:, 0], B[:, 0]), C[:, 0]) >= x) \
        & (np.minimum(np.minimum(A[:, 1], B[:, 1]), C[:, 1]) <= y) & (np.maximum(np.maximum(A[:, 1], B[:, 1]), C[:, 1]) >= y)
    A, B, C = A[near], B[near], C[near]
    if not len(A):
        return None
    # barycentric in the xy projection
    v0, v1 = (B - A)[:, :2], (C - A)[:, :2]
    v2 = np.array([x, y]) - A[:, :2]
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    ok = np.abs(den) > 1e-14
    u = np.where(ok, (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / np.where(ok, den, 1), -1)
    w = np.where(ok, (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / np.where(ok, den, 1), -1)
    inside = (u >= 0) & (w >= 0) & (u + w <= 1)
    z = (A[:, 2] + u * (B[:, 2] - A[:, 2]) + w * (C[:, 2] - A[:, 2]))[inside]
    z = z[z < ceiling]
    return float(z.max()) if len(z) else None


def fit(body, opts: dict | None = None, garment_X: np.ndarray | None = None) -> dict:
    """A hanger (and rail) placed inside the dressed garment: arms under the body's shoulders (their tops `clear`
    under the surface, along the line hps -> shoulder point), the hook rising at the neck's centre through the
    garment's neck opening to clear its collar (garment_X: the garment's start positions), curled over a rail.
    Returns {"segments": [(a, b, (ry, rz) at a, at b, part)], "kind", "colour", "arms": {side: (centre, tip)},
    "rod": (a, b), "rail": [(a, b, r, part)], "width", "slope_deg", "notes"}."""
    ro = (opts or {}).get("rail", {})  # None / False: no rail
    opts = dict((opts or {}).get("hanger") or {})
    kind = opts.get("kind", "wood")
    K = KINDS[kind]
    at = body.at
    hps, sh = np.asarray(at["hps.L"], float), np.asarray(at["shoulder.L"], float)
    cf, cb = np.asarray(at["cf_neck"], float), np.asarray(at["cb_neck"], float)
    x0 = float(body.J["neck"][0]) if "neck" in body.J else 0.0
    yc = 0.5 * (cf[1] + cb[1])
    half = float(opts["width"]) / 2 if "width" in opts else float(sh[0] - x0) - 0.01
    clear = float(opts.get("clear", 0.008))
    ys = lambda x: yc + (sh[1] - yc) * np.clip(x / max(sh[0] - x0, 1e-3), 0, 1)  # noqa: E731 (arms follow the shoulders)
    # the shoulders' upper surface between the neck's side and the tip
    xs = np.linspace(hps[0] - x0 + 0.01, half, 8)
    tops = [(x, _top(body, x0 + x, ys(x), hps[2] + 0.03)) for x in xs]
    tops = np.array([(x, z) for x, z in tops if z is not None])
    if len(tops) >= 3:
        b, a = np.polyfit(tops[:, 0], tops[:, 1], 1)
    else:  # no surface found: the tape's line hps -> shoulder point
        b = (sh[2] - hps[2]) / max(sh[0] - hps[0], 1e-3)
        a = hps[2] - b * (hps[0] - x0)
    if "slope" in opts:  # a set slope through the shoulders' mid-point
        xm = 0.5 * (hps[0] - x0 + half)
        zm = a + b * xm
        b = -np.tan(np.radians(float(opts["slope"])))
        a = zm - b * xm
    rz_of = lambda t: K["centre"][1] + (K["end"][1] - K["centre"][1]) * t ** 2  # noqa: E731
    ry_of = lambda t: K["centre"][0] + (K["end"][0] - K["centre"][0]) * t ** 2  # noqa: E731
    segs, arms = [], {}
    ts = np.array([0.0, 0.2, 0.4, 0.6, 0.75, 0.88, 1.0])
    for side, sg in (("L", 1.0), ("R", -1.0)):
        P = []
        for t in ts:
            x = t * half
            # the end's top under the surface by `clear`: the arm's centre a radius lower
            P.append([x0 + sg * x, ys(x), a + b * x - clear - rz_of(t)])
        P = np.asarray(P)
        for k in range(len(ts) - 1):
            segs.append((P[k], P[k + 1], (ry_of(ts[k]), rz_of(ts[k])), (ry_of(ts[k + 1]), rz_of(ts[k + 1])), f"arm.{side}"))
        arms[side] = (P[0], P[-1])
    zc = arms["L"][0][2]
    centre = np.array([x0, yc, zc])
    if opts.get("bar"):
        xb = 0.85 * half
        zb = a + b * xb - clear - 2 * rz_of(0.85) - 0.035
        for sg in (1.0, -1.0):
            top = np.array([x0 + sg * xb, ys(xb), a + b * xb - clear - rz_of(0.85)])
            segs.append((top, np.array([x0 + sg * xb, ys(xb), zb]), (K["bar_r"],) * 2, (K["bar_r"],) * 2, "bar"))
        segs.append((np.array([x0 - xb, ys(xb), zb]), np.array([x0 + xb, ys(xb), zb]), (K["bar_r"],) * 2,
                     (K["bar_r"],) * 2, "bar"))
    # the hook: a rod up through the neck opening, then a curl over the rail
    hr = K["hook_r"]
    rail_r = float(ro.get("radius", 0.0125)) if isinstance(ro, dict) else 0.0125
    if "rise" in opts:
        z_rod = zc + float(opts["rise"])
    else:
        z_rod = zc + 0.07
        if garment_X is not None:  # clear of the collar standing round the neck
            Xg = np.asarray(garment_X, float)
            near = np.hypot(Xg[:, 0] - x0, Xg[:, 1] - yc) < 0.12
            if near.any():
                z_rod = max(z_rod, float(Xg[near, 2].max()) + 0.05)
    rod = (centre + [0, 0, K["centre"][1] * 0.5], np.array([x0, yc, z_rod]))
    segs.append((rod[0], rod[1], (hr, hr), (hr, hr), "hook"))
    Rh = rail_r + hr + 0.004
    C = np.array([x0 + Rh, yc, z_rod])
    ang = np.linspace(np.pi, -np.pi / 5, 12)
    curl = C + Rh * np.c_[np.cos(ang), np.zeros_like(ang), np.sin(ang)]
    for k in range(len(curl) - 1):
        segs.append((curl[k], curl[k + 1], (hr, hr), (hr, hr), "hook"))
    rail = []
    if isinstance(ro, dict):
        # a face-out bar (a shop's display arm, a coat stand's peg): from just in front of the hook back to a post
        # behind the garment, so nothing stands in front of it (a through rail put a post before the coat's face)
        L = float(ro.get("length", 0.45))
        rc = C + [0, 0, Rh - hr - rail_r - 0.001]  # resting on the curl's inner top
        ra, rb = rc - [0, 0.04, 0], rc + [0, L, 0]
        rail.append((ra, rb, rail_r, "rail"))
        if ro.get("posts", True):
            rail.append((rb, np.array([rb[0], rb[1], 0.0]), rail_r, "post"))
    return {"segments": segs, "kind": kind, "colour": K["colour"], "arms": arms, "rod": rod, "rail": rail,
            "width": 2 * half, "slope_deg": float(np.degrees(np.arctan(-b))), "centre": centre, "hook_top": C + [0, 0, Rh]}


def from_job(job: dict) -> dict:
    """The hanger dict as a job carries it (json: lists) back to arrays."""
    h = dict(job["hanger"])
    h["segments"] = [(np.asarray(a), np.asarray(b), tuple(ra), tuple(rb), p) for a, b, ra, rb, p in h["segments"]]
    h["rail"] = [(np.asarray(a), np.asarray(b), float(r), p) for a, b, r, p in h["rail"]]
    h["arms"] = {k: (np.asarray(v[0]), np.asarray(v[1])) for k, v in h["arms"].items()}
    h["rod"] = (np.asarray(h["rod"][0]), np.asarray(h["rod"][1]))
    return h


def to_job(h: dict) -> dict:
    j = lambda a: np.asarray(a, float).tolist()  # noqa: E731
    return {"segments": [(j(a), j(b), list(ra), list(rb), p) for a, b, ra, rb, p in h["segments"]],
            "rail": [(j(a), j(b), float(r), p) for a, b, r, p in h["rail"]],
            "arms": {k: (j(v[0]), j(v[1])) for k, v in h["arms"].items()}, "rod": (j(h["rod"][0]), j(h["rod"][1])),
            "kind": h["kind"], "colour": h["colour"], "width": h["width"], "slope_deg": h["slope_deg"]}


def _seg_d(P, a, b, ra, rb):
    """Distance-like field of a tapered segment with an elliptical section (depth along y, height along the section's
    other axis): exact on its zero set for straight sections, a fair distance near it."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ax = b - a
    L = np.linalg.norm(ax)
    d = ax / max(L, 1e-12)
    t = np.clip((P - a) @ d / max(L, 1e-12), 0, 1)
    q = P - (a + np.outer(t * L, d))
    # section frame: u ~ world y (depth) orthogonal to the axis, v the rest
    u = np.array([0.0, 1.0, 0.0]) - d * d[1]
    if np.linalg.norm(u) < 1e-6:
        u = np.array([1.0, 0.0, 0.0]) - d * d[0]
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    ry = ra[0] + (rb[0] - ra[0]) * t
    rz = ra[1] + (rb[1] - ra[1]) * t
    e = np.sqrt(((q @ u) / ry) ** 2 + ((q @ v) / rz) ** 2 + ((q @ d) / np.minimum(ry, rz)) ** 2)
    return (e - 1.0) * np.minimum(ry, rz)


def field(P: np.ndarray, h: dict, parts: tuple | None = None, rail: bool = True, with_part: bool = False):
    """Distance from points to the hanger (and rail): negative inside. with_part: also the nearest part's name per
    point."""
    from .sdf import smin
    P = np.atleast_2d(np.asarray(P, float))
    D, names = [], []
    for a, b, ra, rb, p in h["segments"]:
        if parts is None or p in parts:
            D.append(_seg_d(P, a, b, ra, rb))
            names.append(p)
    if rail:
        for a, b, r, p in h["rail"]:
            if parts is None or p in parts:
                D.append(_seg_d(P, a, b, (r, r), (r, r)))
                names.append(p)
    D = np.asarray(D)
    k = np.argmin(D, axis=0)
    d = D[0]
    for x in D[1:]:
        d = smin(d, x, 0.004)
    return (d, np.asarray(names)[k]) if with_part else d


def meshes(h: dict, voxel: float = 0.0025) -> list:
    """[{"name", "V", "F", "color"}]: the hanger as one closed mesh (its own field meshed: arms, hook, bar), the rail
    and posts as another."""
    from skimage import measure
    out = []
    for nm, parts, rail, col in (("hanger", None, False, h["colour"]), ("rail", ("rail", "post"), True, RAIL_COLOUR)):
        segs = [s for s in h["segments"] if parts is None or s[4] in parts] if not rail else []
        rl = h["rail"] if rail else []
        if not segs and not rl:
            continue
        pts = [np.r_[s[0], s[1]].reshape(2, 3) for s in segs] + [np.r_[r[0], r[1]].reshape(2, 3) for r in rl]
        pts = np.concatenate(pts)
        lo, hi = pts.min(0) - 0.03, pts.max(0) + 0.03
        vx = voxel if not rail else 0.004
        n = np.ceil((hi - lo) / vx).astype(int) + 1
        if rail:  # the rail and posts are plain tubes: meshed as cylinders, not a field over 2 m
            V, F = [], []
            for a, b, r, _ in rl:
                Vt, Ft = tube(a, b, r)
                F.append(Ft + sum(len(v) for v in V))
                V.append(Vt)
            out.append({"name": nm, "V": np.concatenate(V), "F": np.concatenate(F), "color": col})
            continue
        g = np.stack(np.meshgrid(*[lo[k] + vx * np.arange(n[k]) for k in range(3)], indexing="ij"), -1).reshape(-1, 3)
        f = field(g, h, rail=False).reshape(n)
        V, F, _, _ = measure.marching_cubes(f, 0.0, spacing=(vx,) * 3)
        V, F = V + lo, F.astype(np.int64)
        # normals out (colliders push cloth to the side their faces face: inward faces held the cloth INSIDE the arms
        # and the coat climbed up them)
        if np.einsum("ij,ij->i", V[F[:, 0]], np.cross(V[F[:, 1]], V[F[:, 2]])).sum() < 0:
            F = F[:, ::-1].copy()
        out.append({"name": nm, "V": V, "F": F, "color": col})
    return out


def tube(a, b, r, n=20):
    """A closed cylinder (end fans) round a -> b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    u = np.cross(d, [1, 0, 0] if abs(d[0]) < 0.9 else [0, 1, 0])
    u /= np.linalg.norm(u)
    w = np.cross(d, u)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.outer(np.cos(ang), u) + np.outer(np.sin(ang), w)
    V = np.r_[a + r * ring, b + r * ring, [a], [b]]
    F = [[i, (i + 1) % n, n + (i + 1) % n] for i in range(n)] + [[i, n + (i + 1) % n, n + i] for i in range(n)]
    F += [[2 * n, (i + 1) % n, i] for i in range(n)] + [[2 * n + 1, n + i, n + (i + 1) % n] for i in range(n)]
    return V, np.asarray(F, np.int64)


def inside_body(h: dict, body) -> float:
    """How far the hanger's arms and bar stand OUT of the body at worst (m; <= 0: wholly inside, as they must be while
    the garment is dressed): sampled along each segment's surface, signed by the body's nearest vertex normal."""
    vn, tree = body.normals()
    P = []
    for a, b, ra, rb, p in h["segments"]:
        if p == "hook":
            continue
        for t in np.linspace(0, 1, 6):
            c = a + (b - a) * t
            r = max(ra[0] + (rb[0] - ra[0]) * t, ra[1] + (rb[1] - ra[1]) * t)
            for o in ([0, 0, 1], [0, 1, 0], [0, -1, 0], [0, 0, -1]):
                P.append(c + r * np.asarray(o, float))
    P = np.asarray(P)
    _, i = tree.query(P, k=6)
    s = np.sum((P[:, None] - body.V[i]) * vn[i], -1).mean(1)
    return float(s.max())


# ---------------------------------------------------------------- the measures


def _rays(O: np.ndarray, D: np.ndarray, V: np.ndarray, F: np.ndarray, maxd: float) -> np.ndarray:
    """First hit distance of each ray (O, D unit) on the triangles (inf: none within maxd). Moller-Trumbore over the
    triangles near the rays."""
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    out = np.full(len(O), np.inf)
    cen = (A + B + C) / 3
    for k in range(len(O)):
        o, d = O[k], D[k]
        rel = cen - o
        along = rel @ d
        perp = np.linalg.norm(rel - np.outer(along, d), axis=1)
        sel = (along > -0.02) & (along < maxd + 0.02) & (perp < 0.03)
        if not sel.any():
            continue
        a, b, c = A[sel], B[sel], C[sel]
        e1, e2 = b - a, c - a
        pv = np.cross(d, e2)
        det = np.sum(e1 * pv, 1)
        ok = np.abs(det) > 1e-14
        inv = 1.0 / np.where(ok, det, 1)
        tv = o - a
        u = np.sum(tv * pv, 1) * inv
        qv = np.cross(tv, e1)
        v = (qv @ d) * inv
        t = np.sum(e2 * qv, 1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-5) & (t < maxd)
        if hit.any():
            out[k] = t[hit].min()
    return out


def _areas(V, F):
    a = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    w = np.zeros(len(V))
    for k in range(3):
        np.add.at(w, F[:, k], a / 3)
    return w


def support(V: np.ndarray, M: dict, h: dict | None, pins=(), V_prev: np.ndarray | None = None,
            frames_apart: int = 1) -> dict:
    """What carries the garment's weight. Supports: vertices touching the hanger/rail (within CONTACT, by part) and
    pinned vertices. Each vertex's mass (its area share) goes to the support nearest to it over the cloth (seams
    joined): a fair stand-in for the load path of cloth hanging from a few contact patches. Returns {"share":
    {"pins", "arm.L", "arm.R", "hook", "bar", "rail", "post"}, "touch": {part: vertices}, "unsupported", "moving_mm"
    (largest move per frame over the last frames, when V_prev is given), "floor": share of the cloth near z = 0}."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    V = np.asarray(V, float)
    F = M["F"]
    m = _areas(V, F)
    lab = np.full(len(V), "", object)
    touch = {}
    if h is not None:
        d, part = field(V, h, with_part=True)
        tc = d < CONTACT
        lab[tc] = part[tc]
        for p in np.unique(part[tc]):
            touch[str(p)] = int(np.sum(tc & (part == p)))
    pins = np.asarray(pins, np.int64)
    if len(pins):
        lab[pins] = "pins"
        touch["pins"] = len(pins)
    src = np.where(lab != "")[0]
    out = {"touch": touch, "share": {}, "unsupported": 1.0}
    if len(src):
        E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]], M["sew"]] if len(M["sew"]) else \
            np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
        w = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1) + 1e-6
        G = coo_matrix((np.r_[w, w], (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(len(V),) * 2).tocsr()
        dist, _, source = dijkstra(G, indices=src, min_only=True, return_predecessors=True)
        reach = np.isfinite(dist)
        tot = m.sum()
        for p in np.unique(lab[src]):
            out["share"][str(p)] = float(m[reach & (lab[np.where(reach, source, 0)] == p)].sum() / tot)
        out["unsupported"] = float(m[~reach].sum() / tot)
    if V_prev is not None:
        out["moving_mm"] = float(np.percentile(np.linalg.norm(V - V_prev, axis=1), 99) / max(frames_apart, 1) * 1000)
    out["floor"] = float(m[V[:, 2] < 0.02].sum() / m.sum())
    return out


def on_hanger(V: np.ndarray, M: dict, h: dict) -> dict:
    """Is the hanger INSIDE the garment? From points along each arm (40-90% out), rays forward (-y), back (+y) and up
    must all meet the cloth within 25 / 25 / 10 cm (a coat floating in front of its hanger has nothing behind the arms);
    the hook's rod must leave through the neck opening: no cloth crosses the rod, and round the rod at the garment's
    top the cloth surrounds it (horizontal rays in 8 directions, 6+ meet cloth within 15 cm). Returns {"arms": {side:
    {"front", "back", "up"} hit fractions}, "hook": {"crossings", "surround", "above_mm"}, "ok", "why"}."""
    V = np.asarray(V, float)
    F = M["F"]
    res = {"arms": {}, "hook": {}}
    why = []
    for side, (c, tip) in h["arms"].items():
        P = np.array([c + (tip - c) * t for t in (0.4, 0.55, 0.7, 0.85, 0.95)])
        hits = {}
        for nm, dvec, mx in (("front", [0, -1, 0], 0.25), ("back", [0, 1, 0], 0.25), ("up", [0, 0, 1], 0.10)):
            D = np.tile(np.asarray(dvec, float), (len(P), 1))
            hits[nm] = float(np.mean(np.isfinite(_rays(P, D, V, F, mx))))
        res["arms"][side] = hits
        bad = [k for k, v in hits.items() if v < 0.6]
        if bad:
            why.append(f"arm {side}: no cloth {'/'.join(bad)} of it")
    a, b = h["rod"]
    # rod vs cloth: segments along the rod against every triangle near it
    A_, B_, C_ = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    cen = (A_ + B_ + C_) / 3
    near = np.hypot(cen[:, 0] - a[0], cen[:, 1] - a[1]) < 0.05
    cross = 0
    if near.any():
        d = b - a
        L = np.linalg.norm(d)
        cross = int(np.sum(np.isfinite(_rays(a[None], (d / L)[None], V, F[near], L))))
        # count every crossing, not only the first: march the rod in pieces
        cross = 0
        zs = np.linspace(0, L, 25)
        for k in range(len(zs) - 1):
            o = a + d / L * zs[k]
            cross += int(np.isfinite(_rays(o[None], (d / L)[None], V, F[near], zs[k + 1] - zs[k]))[0])
    # the garment's top round the rod
    rr = np.hypot(V[:, 0] - a[0], V[:, 1] - a[1]) < 0.12
    ztop = float(V[rr, 2].max()) if rr.any() else -np.inf
    # the neck opening round the rod: cloth near the garment's top (within 4 cm under it, 15 cm of the rod) in each of
    # 8 sectors round it (a collar round the hook fills all 8; a coat hanging in front of it only the front ones)
    band = rr & (V[:, 2] > ztop - 0.04) & (np.hypot(V[:, 0] - a[0], V[:, 1] - a[1]) < 0.15)
    az = np.arctan2(V[band, 1] - a[1], V[band, 0] - a[0])
    sur = int(len(np.unique(np.floor((az + np.pi) / (2 * np.pi) * 8).astype(int) % 8)))
    res["hook"] = {"crossings": cross, "surround": sur, "above_mm": round((b[2] - ztop) * 1000, 1)}
    if cross:
        why.append(f"the hook's rod crosses the cloth {cross}x (not through the neck opening)")
    if sur < 6:
        why.append(f"the cloth surrounds the hook at the collar in only {sur}/8 directions")
    if b[2] < ztop - 0.01:
        why.append("the hook doesn't come out above the garment")
    res["ok"] = not why
    res["why"] = why
    return res


def verdict(sup: dict, onh: dict | None) -> tuple[bool, str]:
    """(ok, one line) for the report: hung = carried by the hanger's arms (both shoulders), the hanger inside."""
    s = sup["share"]
    arms = s.get("arm.L", 0) + s.get("arm.R", 0)
    hook = s.get("hook", 0)
    pins = s.get("pins", 0)
    why = []
    if pins > 0.05:
        why.append(f"pins carry {pins * 100:.0f}%")
    if min(s.get("arm.L", 0), s.get("arm.R", 0)) < 0.15:
        why.append(f"not on both shoulders (left arm {s.get('arm.L', 0) * 100:.0f}%, right {s.get('arm.R', 0) * 100:.0f}%)")
    if sup["unsupported"] > 0.05 or sup.get("floor", 0) > 0.02:
        why.append(f"{max(sup['unsupported'], sup.get('floor', 0)) * 100:.0f}% of it isn't hanging from anything")
    if sup.get("moving_mm", 0) > 2.0:
        why.append(f"still moving ({sup['moving_mm']:.1f} mm/frame)")
    if onh is not None and not onh["ok"]:
        why += onh["why"]
    line = (f"supported by: arms {arms * 100:.0f}% (L {s.get('arm.L', 0) * 100:.0f}, R {s.get('arm.R', 0) * 100:.0f}), "
            f"hook {hook * 100:.0f}%, bar {s.get('bar', 0) * 100:.0f}%, rail {(s.get('rail', 0) + s.get('post', 0)) * 100:.0f}%, "
            f"pins {pins * 100:.0f}%; touching: " + ", ".join(f"{k} {v}" for k, v in sup["touch"].items())
            + (f"; moving {sup['moving_mm']:.1f} mm/frame" if "moving_mm" in sup else ""))
    if onh is not None:
        line += ("; arms inside (front/back/up hits): " + ", ".join(
            f"{k} {v['front']:.1f}/{v['back']:.1f}/{v['up']:.1f}" for k, v in onh["arms"].items())
            + f"; hook: {onh['hook']['crossings']} crossings, surrounded {onh['hook']['surround']}/8, "
            f"{onh['hook']['above_mm']:.0f} mm above the cloth")
    return not why, ("ON THE HANGER: " if not why else "NOT ON ITS HANGER (" + "; ".join(why) + "): ") + line
