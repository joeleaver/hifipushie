"""The shapes: smooth minimum, one signed distance function per primitive kind (`SDF`: the table of them) and the modifiers of a combined field (`MODS`). Part of the SDF module (sdf.py has the grid, the evaluation and the meshing)."""
from __future__ import annotations

import numpy as np

from . import sdf
from .sheet import sd_sheet
from .softforms import sd_loft, sd_super
from .sdf import _smoothstep, field_at

def smin(a, b, k):
    """Smooth union, cubic: curvature stays continuous where a blend starts (the quadratic form is only
    C1, which leaves a faint edge in the highlights along every fillet boundary)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * h * k * (1.0 / 6.0)


def smin_var(a, b, k):
    """smin with a blend that differs from point to point (an array like a and b)."""
    k = np.maximum(k, 1e-9)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * h * k * (1.0 / 6.0)


def sides_mul(sides, pts: np.ndarray) -> np.ndarray:
    """How much of a mass's fill holds at each point (spec_hands._fuse_sides): all of it on the far half of the fuse,
    easing from the fuse's middle to the side's own part at that side's face."""
    c, R, items = sides
    q = (np.asarray(pts, float) - np.asarray(c, float)) / np.asarray(R, float)
    m = np.ones(q.shape[:-1])
    for ax, sgn, val in items:  # all of it up to the fuse's middle, then easing to the side's part at that side's
        t = np.clip(sgn * q[..., ax], 0.0, 1.0)  # face (a change in a narrow band at the middle left a ridge)
        m = m * (1.0 + (val - 1.0) * (t * t * (3 - 2 * t)))
    return m


def sd_cone(p: np.ndarray, pr: dict) -> np.ndarray:
    """Round cone along a bone, with an optionally elliptical cross-section."""
    q = (p - pr["a"]) @ pr["frame"].T  # columns: width, axis, height
    fw, fh = pr["flat"]
    bw, bh = pr.get("bow", (0.0, 0.0))
    if bw or bh:  # a bowed log: the cross-section's centre follows a parabola, 0 at the ends, `bow` mid-way
        # the centre line is a parabola along the bone and runs on along its tangent past the ends: clamped flat
        # there, its slope jumped at each end plane and a crease crossed any surface near one (a bowed shoulder cap)
        t = q[..., 1] / pr["len"]
        sag = np.where(t < 0.0, 4.0 * t, np.where(t > 1.0, 4.0 * (1.0 - t), 4.0 * t * (1.0 - t)))
        q = np.stack([q[..., 0] - bw * sag, q[..., 1], q[..., 2] - bh * sag], -1)
    x, y, z = q[..., 0] / fw, q[..., 1], q[..., 2] / fh
    r1, r2, h = pr["ra"], pr["rb"], pr["len"]
    b = np.clip((r1 - r2) / h, -0.999, 0.999)
    a = np.sqrt(1.0 - b * b)
    qx = np.sqrt(x * x + z * z)
    k = -b * qx + a * y
    d = np.where(k < 0.0, np.sqrt(qx * qx + y * y) - r1,
                 np.where(k > a * h, np.sqrt(qx * qx + (y - h) ** 2) - r2, a * qx + b * y - r1))
    if pr.get("cut"):  # flat ends at the joints (sawn logs, beams, dowels), edges rounded by `cut`
        rc = pr["cut"]
        side = np.where(k < 0.0, qx - r1, np.where(k > a * h, qx - r2, d))  # the flank, continued past the ends
        cap = np.abs(y - 0.5 * h) - 0.5 * h
        e0, e1 = side + rc, cap + rc
        d = np.hypot(np.maximum(e0, 0.0), np.maximum(e1, 0.0)) + np.minimum(np.maximum(e0, e1), 0.0) - rc
    return d * min(fw, fh, 1.0)


def sd_ellipsoid(p: np.ndarray, pr: dict) -> np.ndarray:
    q = (p - pr["c"]) @ pr["rot"]  # world -> local
    r = pr["size"]
    k0 = np.linalg.norm(q / r, axis=-1)
    k1 = np.maximum(np.linalg.norm(q / (r * r), axis=-1), 1e-9)
    return k0 * (k0 - 1.0) / k1


def sd_lids(p: np.ndarray, pr: dict) -> np.ndarray:
    """Both eyelids of one eye: a solid ball around the eyeball (front part only) with an almond opening.
    The opening is a lens between two arcs meeting at the eye corners, measured by direction from the eye
    centre, so its walls are radial and meet the eyeball at right angles (a thin wedge there would alias).
    Local frame as for ellipsoids: the eye faces local -y, local +z is up."""
    q = (p - pr["c"]) @ pr["rot"]
    r, rho = pr["r"], pr["round"]
    dist = np.linalg.norm(q, axis=-1)
    ball = dist - pr["ro"]
    back = q[..., 1] - 0.3 * r
    if pr["closed"]:
        lid = ball
    else:
        s = r / np.maximum(dist, 1e-9)            # project onto the eyeball's sphere
        x, z = q[..., 0] * s, q[..., 2] * s
        up = np.hypot(x, z - pr["cu"]) - pr["Ru"]  # inside the upper arc's circle = below the upper margin
        lo = np.hypot(x, z - pr["cl"]) - pr["Rl"]
        lens = np.maximum(up, lo) * np.minimum(dist, pr["ro"]) / r
        lid = np.maximum(ball + rho, -lens + rho) - rho
    return np.maximum(lid + rho, back + rho) - rho


def sd_box(p: np.ndarray, pr: dict) -> np.ndarray:
    """Box with half-extents `size` in its local frame (as for ellipsoids), edges rounded by `round`."""
    q = np.abs((p - pr["c"]) @ pr["rot"]) - (pr["size"] - pr["round"])
    out = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
    return out + np.minimum(q.max(axis=-1), 0.0) - pr["round"]


def _path_closest(q: np.ndarray, P: np.ndarray):
    """For points q (m, 3), the closest point on polyline P (K, 3): segment index j, parameter t, point c."""
    if len(P) == 1:
        z = np.zeros(len(q), int)
        return z, np.zeros(len(q)), np.broadcast_to(P[0], q.shape)
    a, d = P[:-1], P[1:] - P[:-1]
    x = q[:, None, :] - a[None]
    t = np.clip((x * d).sum(-1) / np.maximum((d * d).sum(1), 1e-18), 0.0, 1.0)
    j = np.argmin(((x - t[..., None] * d) ** 2).sum(-1), axis=1)
    tj = t[np.arange(len(q)), j]
    return j, tj, a[j] + tj[:, None] * d[j]


def mod_displace(cur: np.ndarray, p: np.ndarray, pr: dict, chunk: int = 4096) -> np.ndarray:
    """A stroke: push the surface out (depth > 0, clay) or in (depth < 0, crease) along its normal.

    Like a sculpting brush, a stroke is a dense trail of dabs, summed: each sample i of the path adds
    depth_i * profile(distance across the surface / width_i), weighted by the arc length it stands for and
    normalised so a long straight stroke reaches `depth`. Distance is measured across the surface (each
    sample's normal component left out), so the bump follows curvature. A sum of smooth dabs is smooth
    everywhere (measuring from the nearest point of a polyline instead kinks the surface at every sample,
    which shows as stripes), and the trail tapers off naturally over about a width at each end.
    Each dab fades out past `reach` along its normal, so it doesn't print through to the far side of a limb."""
    P, N, W, D, ds = pr["pts"], pr["nrm"], pr["width"], pr["depth"], pr["ds"]
    prof = sdf.PROFILES[pr["profile"]][0]
    H = pr["reach"]
    gain = D * ds / (W * pr["norm"]) if len(P) > 1 else D  # a single point is one dab at full depth
    flat = p.reshape(-1, 3)
    c0 = cur.reshape(-1)
    out = c0.copy()
    # only dabs within reach matter: the K nearest samples (K covers a width's worth of path either side)
    K, R = pr["k"], pr["radius"]
    for s in range(0, len(flat), chunk):
        q = flat[s:s + chunk].astype(np.float64)
        dist, idx = pr["tree"].query(q, k=K, distance_upper_bound=R)
        idx = idx.reshape(len(q), K)
        ok = idx < len(P)
        if not ok.any():
            continue
        j = np.where(ok, idx, 0)
        r = q[:, None, :] - P[j]                                   # (m, K, 3)
        h = (r * N[j]).sum(-1)
        lat = np.sqrt(np.maximum((r * r).sum(-1) - h * h, 0.0)) / W[j]
        k = np.where(ok & (lat < 1.0), prof(np.minimum(lat, 1.0)), 0.0)
        k *= 1 - _smoothstep(np.clip((np.abs(h) - H) / H, 0, 1))
        out[s:s + chunk] = c0[s:s + chunk] - (k * gain[j]).sum(1)
    return out.reshape(cur.shape)


def mod_flatten(cur: np.ndarray, p: np.ndarray, pr: dict) -> np.ndarray:
    """Plane off whatever stands above a plane (through pts, a point or a segment, normal nrm), fully
    within `width` of pts and fading out over `soft` beyond; only material up to `height` above the plane
    is touched, so a hand hanging in front of a thigh isn't shaved. The plane meets the surface in a
    smooth edge of radius `blend`."""
    P, n = pr["pts"], pr["nrm"][0]
    q = p.reshape(-1, 3)
    _, _, c = _path_closest(q, P)
    r = q - c
    h = r @ n
    lat = np.linalg.norm(r - h[:, None] * n, axis=1)
    wgt = 1 - _smoothstep(np.clip((lat - pr["width"]) / pr["soft"], 0, 1))
    wgt *= 1 - _smoothstep(np.clip((h - pr["height"]) / pr["height"], 0, 1))
    c0 = cur.reshape(-1)
    hp = (q - P[0]) @ n
    shaved = -smin(-c0, -hp, pr["blend"])  # smooth max(cur, height above the plane)
    return (c0 + wgt * (shaved - c0)).reshape(cur.shape)


def sd_cylinder(p: np.ndarray, pr: dict) -> np.ndarray:
    """Cylinder along its local z: radii size[0], size[1] (elliptical if they differ: then a lower bound),
    half-height size[2], edges rounded by `round`."""
    q = (p - pr["c"]) @ pr["rot"]
    rx, ry, hz = pr["size"]
    rnd = pr["round"]
    r = min(rx, ry)
    radial = np.hypot(q[..., 0] * (r / rx), q[..., 1] * (r / ry)) - (r - rnd)
    axial = np.abs(q[..., 2]) - (hz - rnd)
    out = np.hypot(np.maximum(radial, 0.0), np.maximum(axial, 0.0))
    return out + np.minimum(np.maximum(radial, axial), 0.0) - rnd


def sd_blade(p: np.ndarray, pr: dict) -> np.ndarray:
    """A thin sheet (ear, leaf, fin, feather, blade) in its local frame: across x (half width size[0]), along y
    (half length size[1]), thickness z (half size[2]), edges fully rounded. The outline is an almond, narrowed
    toward +y by `taper` (0..1: the tip's width is 1 - taper of the base's), cupped (`cup` m: the side edges lift
    toward +z, an ear's hollow) and bent (`bend` m: the +y tip lifts toward +z). Bent sheets are evaluated in
    the bent frame and the field divided by the bend's largest stretch, so it never over-estimates distance."""
    q = (p - pr["c"]) @ pr["rot"]
    W, L, T = pr["size"]
    taper, cup, bend = pr.get("taper", 0.0), pr.get("cup", 0.0), pr.get("bend", 0.0)
    x, y, z = q[..., 0], q[..., 1], q[..., 2]
    yl = np.clip(y / L, -1.0, 1.0)
    z = z - cup * (x / W) ** 2 - bend * ((yl + 1) / 2) ** 2
    a = W * np.maximum(1.0 - taper * (yl + 1) / 2, 0.05) - T  # the flat core's outline, T inside the edge
    b = L - T
    k0 = np.hypot(x / a, y / b)
    k1 = np.hypot(x / a ** 2, y / b ** 2)
    e = k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)  # ~signed distance to the core's outline in the sheet's plane
    h = np.abs(z)
    d = np.hypot(np.maximum(e, 0.0), h) + np.minimum(np.maximum(e, h), 0.0) - T
    return d / pr.get("lip", 1.0)


def _seg2(px, py, ax, ay, bx, by):
    """Distance from 2D points to segments a-b (arrays broadcast)."""
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / np.maximum(dx * dx + dy * dy, 1e-12), 0.0, 1.0)
    return np.hypot(px - ax - t * dx, py - ay - t * dy)


def sd_collar(p: np.ndarray, pr: dict) -> np.ndarray:
    """A shirt collar turned down over its stand, swept round a neck (local frame: z up the neck, -y front). Each
    half-plane round the axis holds the same 2D profile, two strokes of cloth `t` thick (half): the stand rising
    from the neckline (an ellipse rx, ry) `stand` high, leaning out `lean` m, and the fall folded over its top and
    running back down and out at `spread` degrees off vertical (`spread_back` at the back, where the fall lies
    on the upper back instead of the shoulders' slope), `fall` long, longer toward the front ends
    (`points` m more at the front, easing in over the front third). The front stays open `gap` degrees each side of
    the centre line (the fall's ends: the collar points; the stand closes `stand_gap`). Divided by `lip` (the
    profile varies round the axis, so the field is slightly steeper than 1)."""
    q = (p - pr["c"]) @ pr["rot"]
    x, y, z = q[..., 0], q[..., 1], q[..., 2]
    rx, ry = pr["rx"], pr["ry"]
    rho = np.hypot(x, y)
    th = np.arctan2(x, -y)  # 0 at the front
    ath = np.abs(th)
    r0 = rx * ry / np.maximum(np.hypot(ry * np.sin(th), rx * np.cos(th)), 1e-9)
    hs, t, lean = pr["stand"], pr["t"], pr["lean"]
    back = (0.5 * (1 - np.cos(th))) ** 2  # 0 at the front, 1/4 at the sides, 1 at the back
    sp = np.radians(pr["spread"] + (pr["spread_back"] - pr["spread"]) * back)
    front = np.clip(1 - ath / (np.pi / 3), 0, 1)
    fl = pr["fall"] + pr["points"] * front * front * (3 - 2 * front)
    bx, by = r0 + lean, hs  # the fold: the stand's top
    ds = _seg2(rho, z, r0, 0.0, bx, by)
    df = _seg2(rho, z, bx + t, by, bx + t + fl * np.sin(sp), by - fl * np.cos(sp))
    d = np.minimum(ds, df) - t
    # the front opening: the fall's ends (collar points) at `gap`, the stand's at `stand_gap`, as arc lengths
    g = np.where(df < ds, np.radians(pr["gap"]), np.radians(pr["stand_gap"]))
    d = np.maximum(d, (g - ath) * np.maximum(rho, 1e-3))
    return d / pr["lip"]


def _sweep_frame(q: np.ndarray, pr: dict):
    """Nearest point on the sweep's polyline: returns (n, u, a, s): offsets along the path's outward (N) and up (U)
    directions there, the overshoot past either end (>= 0, 0 inside), and the arc length (m)."""
    P, T, L, S = pr["P"], pr["T"], pr["L"], pr["S"]
    r0 = q[:, None, :] - P[None, :-1, :]  # (n, m, 3)
    t = np.clip(np.einsum("nmk,mk->nm", r0, T) / L[None], 0.0, 1.0)
    d2 = ((r0 - t[..., None] * (T * L[:, None])[None]) ** 2).sum(-1)
    i = np.argmin(d2, 1)
    ti = t[np.arange(len(q)), i]
    C = P[i] + ti[:, None] * T[i] * L[i][:, None]
    r = q - C
    w = ti[:, None]
    N = (1 - w) * pr["N"][i] + w * pr["N"][i + 1]
    U = (1 - w) * pr["U"][i] + w * pr["U"][i + 1]
    n, u = (r * N).sum(1), (r * U).sum(1)
    a = np.zeros(len(q))
    last = len(L) - 1
    st = (i == 0) & (ti <= 0.0)
    a[st] = np.maximum(-(r[st] * T[0]).sum(1), 0.0)
    en = (i == last) & (ti >= 1.0)
    a[en] = np.maximum((r[en] * T[last]).sum(1), 0.0)
    s = S[i] + ti * L[i]
    return n, u, a, s


def sd_sweep(p: np.ndarray, pr: dict) -> np.ndarray:
    """A 2D profile swept along a polyline (a neckline, a placket's edge), each path vertex carrying its own frame
    (N outward, U up) and profile numbers, interpolated by arc length; `mirror` evaluates at |x| (a path on the left
    half makes both sides, e.g. a collar from the nape round to one front end). Profiles:
    "collar": a folded collar: the stand from `sink` below the path up `stand` (leaning out `lean`), the fall folded
      over its top running `fall` m out and down at `phi` rad off the stand's line, both `t` (half) thick; past the
      path's far end the fall reaches forward by `point` x its distance down the fall (the collar point).
    "band": a rounded rectangle n in [n0, n1], u in [u0, u1], corners `round` (a placket strip; with a wide n0 and
      op subtract, the hole a neckline cuts).
    Ends are capped where the path stops, except the start with `open_start` (a mirrored path starting on x = 0: the
    other half carries on there). Divided by `lip`."""
    sh = p.shape[:-1]
    q = p.reshape(-1, 3).astype(np.float64)
    if pr.get("mirror"):
        q = q.copy()
        q[:, 0] = np.abs(q[:, 0])
    out = np.empty(len(q))
    V = pr["V"]
    for c0 in range(0, len(q), 2048):
        qq = q[c0:c0 + 2048]
        n, u, a, s = _sweep_frame(qq, pr)
        # signed distance along the path to the nearer capped end (past it: the overshoot)
        tot = pr["Sv"][-1]
        if pr.get("open_start"):
            a = np.where(s < tot * 0.5, 0.0, a)
            inner = tot - s
        else:
            inner = np.minimum(s, tot - s)
        a = np.where(a > 0, a, -inner)
        val = {k: np.interp(s, pr["Sv"], v) for k, v in V.items()}
        if pr["profile"] == "collar":
            t, hs, lean, fl, phi, sink = (val[k] for k in ("t", "stand", "lean", "fall", "phi", "sink"))
            bx = lean
            ds = _seg2(n, u, 0.0, -sink, bx, hs)
            fx0, fy0 = bx + t, hs
            fx1, fy1 = fx0 + fl * np.sin(phi), fy0 - fl * np.cos(phi)
            df = _seg2(n, u, fx0, fy0, fx1, fy1)
            # how far down the fall (0 at the fold, 1 at its edge): the point reaches forward past the end with it
            dx, dy = fx1 - fx0, fy1 - fy0
            v = np.clip(((n - fx0) * dx + (u - fy0) * dy) / np.maximum(dx * dx + dy * dy, 1e-12), 0, 1)
            end = (s > tot * 0.5) | bool(pr.get("open_start"))
            af = np.where(end, a - val["point"] * fl * v, a)
            d2 = np.where(df < ds, df, ds) - t
            aa = np.where(df < ds, af, a)
        else:
            n0, n1, u0, u1, rnd = (val[k] for k in ("n0", "n1", "u0", "u1", "round"))
            cn, cu = (n0 + n1) / 2, (u0 + u1) / 2
            hn, hu = (n1 - n0) / 2 - rnd, (u1 - u0) / 2 - rnd
            ex, ey = np.abs(n - cn) - hn, np.abs(u - cu) - hu
            d2 = np.hypot(np.maximum(ex, 0), np.maximum(ey, 0)) + np.minimum(np.maximum(ex, ey), 0) - rnd
            aa = a
        out[c0:c0 + 2048] = np.hypot(np.maximum(d2, 0), np.maximum(aa, 0)) + np.minimum(np.maximum(d2, aa), 0)
    return (out / pr["lip"]).reshape(sh)


def sd_csg(p: np.ndarray, pr: dict, pre: np.ndarray | None = None) -> np.ndarray:
    """An element with its own solid ops (spec_hands._csg): optionally hollowed to a wall, then its targeted cuts.
    An instance's element takes its noise (lumpy, chips) in the prefab's frame ("frame": world -> prefab m, t and
    the instance's scale), so every instance of a prefab is the same shape. With "warp" (deform.py: the model's
    style deformation), everything is evaluated at the undeformed point and the field divided by its stretch."""
    wp = pr.get("warp")
    p0 = p  # where the point is in the world: a trim (reshape.py) cuts there, after any bending
    if wp is not None:
        if pre is not None:  # the caller undeformed these points once for all its primitives
            p = pre
        else:
            from .deform import undeform
            sh = p.shape
            p = undeform(wp[0], p.reshape(-1, 3)).reshape(sh)
    d = SDF[pr["kind"]](p, pr["p"])
    fr = pr.get("frame")
    q, s = (p, 1.0) if fr is None else (p @ fr[0].T + fr[1], fr[2])
    if pr.get("lumpy"):  # knots, axe marks, an uneven stone: noise on the surface itself (amount << scale)
        from .noise import fbm
        amt, sc, seed, octv = pr["lumpy"]
        d = d + s * amt * (2.0 * fbm(q.reshape(-1, 3), sc, octv, seed).reshape(d.shape) - 1.0)
    if pr.get("chips"):  # chunks knocked out: noise above a threshold carves up to `depth`, steep-walled
        from .noise import fbm
        depth, sc, lo, w, seed, edges = pr["chips"]
        c = fbm(q.reshape(-1, 3), sc, 3, seed).reshape(d.shape)
        t = np.clip((c - lo) / w, 0.0, 1.0)
        carve = s * depth * t * t * (3 - 2 * t)
        if edges:  # mostly on edges and corners: the element's own convexity (Laplacian over a chip's size)
            h = 0.5 * sc * s
            base = SDF[pr["kind"]]
            axes = np.eye(3) if fr is None else fr[0] * s  # the prefab's axes, so instances chip alike
            lap = sum(base(p + h * e, pr["p"]) + base(p - h * e, pr["p"]) for e in axes) - 6 * d
            carve = carve * np.clip(lap / (1.2 * h), 0.0, 1.0)
        d = np.maximum(d, d + carve)
    if pr["hollow"]:
        d = np.maximum(d, -d - pr["hollow"])
    for op, kind, params, k in pr["cuts"]:
        c = SDF[kind](p, params)
        d = -smin(-d, c, k) if op == "subtract" else -smin(-d, -c, k)
    if wp is not None:
        d = d / wp[1]
    for a, n, k in pr.get("trims", ()):  # what stands on the plane's far side goes
        d = -smin(-d, -((p0 - a) @ n), k)
    return d


def sd_shell(p: np.ndarray, pr: dict) -> np.ndarray:
    """Another part's surface pushed out by `offset` (clothing). Solid by default: the inside is hidden in
    the part below, and a thin sheet a voxel or two thick would alias. With `thickness`, only the layer from
    offset - thickness to offset. Its own region primitives are intersected with it afterwards."""
    fb = field_at(pr["prims"], p, margin=pr["offset"] + 0.01)
    out = fb - pr["offset"]
    return out if not pr["thickness"] else np.maximum(out, pr["offset"] - pr["thickness"] - fb)


SDF = {"cone": sd_cone, "ellipsoid": sd_ellipsoid, "lids": sd_lids, "box": sd_box, "cylinder": sd_cylinder,
       "blade": sd_blade, "collar": sd_collar, "sweep": sd_sweep, "super": sd_super, "loft": sd_loft, "sheet": sd_sheet,
       "csg": sd_csg, "shell": sd_shell, "base": lambda p, pr: _sd_base(p, pr),
       "gnmpiece": lambda p, pr: _sd_gnm_piece(p, pr)}


def _sd_gnm_piece(p, pr):
    from .base_gnm_parts import sd_gnm_piece
    return sd_gnm_piece(p, pr)


def _sd_base(p, pr):
    from .base_surface import sd_base
    return sd_base(p, pr)
def mod_fold(cur: np.ndarray, p: np.ndarray, pr: dict, chunk: int = 4096) -> np.ndarray:
    """The upper lid's fold (lidfold.py): along a line on the skin (pts, normals nrm, `up` the across direction up the
    lid, `along` the line's tangent), the surface moved along its normal by a profile of the signed distance across
    (lidfold.profile: platform in, a narrow deep crease, the fold's roll out). Smooth along the line: a normalised
    Gaussian over the nearest samples (sigma `sa`), so neither samples nor chords show; it fades over the line's ends
    (`taper` per sample) and past `reach` along the normal."""
    from .lidfold import profile
    P, N, U, T = pr["pts"], pr["nrm"], pr["up"], pr["along"]
    flat = p.reshape(-1, 3)
    c0 = cur.reshape(-1)
    out = c0.copy()
    K, R, sa, H = pr["k"], pr["radius"], pr["sa"], pr["reach"]
    for s in range(0, len(flat), chunk):
        q = flat[s:s + chunk].astype(np.float64)
        dist, idx = pr["tree"].query(q, k=K, distance_upper_bound=R)
        idx = idx.reshape(len(q), K)
        ok = idx < len(P)
        if not ok.any():
            continue
        j = np.where(ok, idx, 0)
        r = q[:, None, :] - P[j]
        h = (r * N[j]).sum(-1)
        t = (r * U[j]).sum(-1)
        a = (r * T[j]).sum(-1)
        w = np.where(ok, np.exp(-0.5 * (a / sa) ** 2), 0.0)
        ws = w.sum(1)
        d = (w * profile(t, pr, j)).sum(1) / np.maximum(ws, 1e-12)
        tap = (w * pr["taper"][j]).sum(1) / np.maximum(ws, 1e-12)
        fade = np.clip(ws / (0.3 * pr["wfull"]), 0, 1) * tap  # (the ends fade by taper; ws itself follows the
        # samples' local spacing, and as the fade it corrugated a fold where they bunched)
        hn = (w * np.abs(h)).sum(1) / np.maximum(ws, 1e-12)
        fade = fade * (1 - _smoothstep(np.clip((hn - H) / H, 0, 1)))
        out[s:s + chunk] = c0[s:s + chunk] - d * fade
    return out.reshape(cur.shape)


def mod_tissue(cur: np.ndarray, p: np.ndarray, pr: dict) -> np.ndarray:
    """A soft-tissue fold (skin_folds.py: skin.folds as geometry): a groove + roll profile swept along a path on the
    skin, kept off the lid margins / the lip line and clear of the eyeballs."""
    from .skin_folds_geometry import mod_tissue as f
    return f(cur, p, pr)


MODS = {"displace": mod_displace, "flatten": mod_flatten, "fold": mod_fold, "tissue": mod_tissue}  # op "modify": reshape what's been combined so far
