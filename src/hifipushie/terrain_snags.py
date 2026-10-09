"""Snags and limbs in the streams (pushieworld note 119: gdamp's 0.25 m water pass draws the V wake behind them and the
pile-up in front). Wood the water has to go round, as capsules resting on what holds them:
- "snag": a fallen stem whose butt lies on the bank and whose top slopes down into the water, pointing downstream
  (outer bends, where the cut bank drops trees in; steep wooded reaches, a few per 10 m near trees);
- "limb": a branch lying across the current: caught on the upstream side of a boulder standing in the water, lying on
  a bar's head with its end in the shallows, or wedged bank to bank across a narrow channel.
Each row carries its capsule: the axis's two end points (x0, y0, z0, x1, y1, z1; end 0 the lower) and its diameter.
An end rests on what holds it: the axis end is a radius over the ground (the bed under the water, a bank) at its own
column; nothing of the axis is inside the ground, the rock or a boulder's footprint between (a candidate that would be
is dropped, never lifted into the air)."""
from __future__ import annotations

import math

import numpy as np

from . import noise

KINDS = {
    "snag": {"scale": [2.0, 6.5], "squash": [1.0, 1.0], "diameter": [0.14, 0.4],
             "what": "a fallen stem (branches broken to stubs, maybe a root plate at the butt): butt on the bank, top "
                     "sloping down into the water, downstream; scale = its length, yaw = from the lower end to the "
                     "upper in plan (0 = +x); the capsule columns hold its axis and diameter"},
    "limb": {"scale": [1.0, 6.0], "squash": [1.0, 1.0], "diameter": [0.05, 0.2],
             "what": "a branch (forked or straight) lying across the current: caught on a boulder's upstream side, on "
                     "a bar's head, or wedged bank to bank; scale = its length; the capsule columns hold its axis and "
                     "diameter"},
}
SPACING = 2.0  # m: the candidates' lattice
CAP_COLS = 7  # x0, y0, z0, x1, y1, z1, diameter
CLEAR = 0.02  # m: an axis may come this close to the ground (between its ends) under its radius
LAST = {}  # the last call's candidates per placement: {where: [asked, rested]} (the report and tests read it)


def _ss(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _rot(v, deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.c_[c * v[:, 0] - s * v[:, 1], s * v[:, 0] + c * v[:, 1]]


def rest(field, rocks, p0, p1, d):
    """Seat capsules with plan ends p0, p1 (n, 2) and diameters d: each axis end a radius over the ground at its
    column. (z0, z1, ok): ok = nothing of the axis between is under the ground (+ CLEAR), in the rock (the field) or
    in a boulder row's footprint (`rocks`: river_rock rows x, y, z, kind, scale, yaw, squash, ..., sink)."""
    h0, _ = field.column(p0[:, 0], p0[:, 1])
    h1, _ = field.column(p1[:, 0], p1[:, 1])
    z0, z1 = h0 + 0.5 * d, h1 + 0.5 * d
    n = len(p0)
    ok = np.ones(n, bool)
    if not n:
        return z0, z1, ok
    L = np.linalg.norm(p1 - p0, axis=1)
    m = int(max(4, math.ceil(L.max() / 0.2)))
    t = np.linspace(0.0, 1.0, m + 1)[1:-1]
    P = p0[:, None, :] + (p1 - p0)[:, None, :] * t[None, :, None]
    Z = z0[:, None] + (z1 - z0)[:, None] * t[None, :]
    hz, _ = field.column(P[..., 0].ravel(), P[..., 1].ravel())
    ok &= ((Z - 0.5 * d[:, None]).ravel() >= hz - CLEAR).reshape(n, -1).all(1)
    v = field.value(np.c_[P.reshape(-1, 2), (Z - 0.5 * d[:, None] + CLEAR).ravel()]).reshape(n, -1)
    ok &= (v > 0).all(1)  # (the axis's underside in the air: not through rock relief or a volume)
    if rocks is not None and len(rocks):
        from scipy.spatial import cKDTree
        from .terrain_stream import FOOTPRINT
        fp = FOOTPRINT["river_rock"]
        tree = cKDTree(rocks[:, :2])
        rmax = 0.5 * float(rocks[:, 4].max()) + 0.3
        Q = np.c_[P.reshape(-1, 2), Z.ravel()]
        rr = np.repeat(0.5 * d, P.shape[1])
        for qi, js in enumerate(tree.query_ball_point(Q[:, :2], rmax)):
            if not js:
                continue
            R = rocks[js]
            a = np.radians(R[:, 5])
            dx, dy = Q[qi, 0] - R[:, 0], Q[qi, 1] - R[:, 1]
            u = (dx * np.cos(a) + dy * np.sin(a)) / (0.5 * R[:, 4] * fp["plan"][0] + rr[qi])
            w = (-dx * np.sin(a) + dy * np.cos(a)) / (0.5 * R[:, 4] * fp["plan"][1] + rr[qi])
            base = R[:, 2] - R[:, 10]
            top = fp["height"] * R[:, 4] * R[:, 6]
            zz = (Q[qi, 2] - base) / (top + rr[qi])
            if np.any((u * u + w * w + np.clip(zz, 0, None) ** 2 < 1.0) & (Q[qi, 2] >= base - rr[qi])):
                ok[qi // P.shape[1]] = False
    return z0, z1, ok


def lean(field, pa, u, lmin, lmax, d, step=0.1):
    """A stem with its lower end on the ground at pa (n, 2), lying along plan directions u (n, 2) up a slope: its upper
    end where it comes to rest, the point between lmin and lmax m whose ground (+ a radius) makes the steepest line
    from the lower end (every other point of the ground between lies under that line: a stick leaning on a bank lies
    on its lip, the part beyond would float, so it ends there). (pb (n, 2), length (n,)); length NaN where the
    steepest point is nearer than lmin (the bank rises on: nothing to rest on)."""
    n = len(pa)
    if not n:
        return pa.copy(), np.zeros(0)
    s = np.arange(step, float(np.max(lmax)) + 1e-9, step)
    P = pa[:, None, :] + u[:, None, :] * s[None, :, None]
    hz, _ = field.column(P[..., 0].ravel(), P[..., 1].ravel())
    ha, _ = field.column(pa[:, 0], pa[:, 1])
    slope = (hz.reshape(n, -1) - ha[:, None]) / s[None, :]
    slope = np.where(s[None, :] <= np.asarray(lmax)[:, None] + 1e-9, slope, -np.inf)
    k = np.argmax(slope, axis=1)
    L = s[k]
    L = np.where(L >= np.asarray(lmin) - 1e-9, L, np.nan)
    return pa + u * np.nan_to_num(L)[:, None], L


def snags(S, field, rocks, trees_xy, zone_box, seed=19, dens=1.0):
    """Snag and limb rows (terrain_stream's 11 columns) and their capsules (n, CAP_COLS), for the box
    [x0, x1, y0, y1] of the stream zone. rocks: the river_rock rows placed (the boulders limbs catch on, and must
    not pass through); trees_xy: tree positions (wooded reaches), or None."""
    from .terrain_stream import KINDS as SK, PLACES, _thin
    kinds = list(SK)
    zx0, zx1, zy0, zy1 = zone_box
    rows, caps = [], []
    LAST.clear()

    def lattice(k):
        sp = SPACING
        xs = np.arange(np.floor(zx0 / sp) - 1, np.ceil(zx1 / sp) + 2) * sp
        ys = np.arange(np.floor(zy0 / sp) - 1, np.ceil(zy1 / sp) + 2) * sp
        gx, gy = np.meshgrid(xs, ys)
        xy = np.c_[gx.ravel(), gy.ravel()]
        ii, jj = np.rint(xy[:, 0] / sp).astype(np.int64), np.rint(xy[:, 1] / sp).astype(np.int64)
        H = lambda a: noise._hash(ii, jj, np.full(len(xy), a, np.int64), seed + k)
        xy = xy + (np.c_[H(1), H(2)] - 0.5) * 0.9 * sp
        q = S.in_zone(xy[:, 0], xy[:, 1])
        q = q[(xy[q, 0] >= zx0) & (xy[q, 0] < zx1) & (xy[q, 1] >= zy0) & (xy[q, 1] < zy1)]
        return xy[q], [H(a)[q] for a in range(3, 10)]

    def bank_dir(xy, g):
        """Unit plan vectors toward the nearer bank (sd rises) across the flow."""
        n = np.c_[-g["t"][:, 1], g["t"][:, 0]]
        a = S.sample(xy + n)["sd"]
        b = S.sample(xy - n)["sd"]
        return np.where((a >= b)[:, None], n, -n)

    def emit(kind, p0, p1, d, place, keep, where):
        LAST.setdefault(where, [0, 0])
        LAST[where][0] += int(keep.sum())
        if not keep.any():
            return
        p0, p1, d, place = p0[keep], p1[keep], d[keep], place[keep]
        z0, z1, ok = rest(field, rocks, p0, p1, d)
        lower = z1 < z0  # (end 0 the lower)
        p0, p1 = np.where(lower[:, None], p1, p0), np.where(lower[:, None], p0, p1)
        z0, z1 = np.where(lower, z1, z0), np.where(lower, z0, z1)
        p0, p1, z0, z1, d, place = p0[ok], p1[ok], z0[ok], z1[ok], d[ok], place[ok]
        LAST[where][1] += int(ok.sum())
        if not len(p0):
            return
        mid = 0.5 * (p0 + p1)
        hm, _ = field.column(mid[:, 0], mid[:, 1])
        L = np.linalg.norm(p1 - p0, axis=1)
        yaw = np.degrees(np.arctan2(p1[:, 1] - p0[:, 1], p1[:, 0] - p0[:, 0]))
        lv = S.sample(mid)["level"]
        R = np.c_[mid, hm, np.full(len(mid), kinds.index(kind)), L, np.mod(yaw, 360.0), np.ones(len(mid)),
                  place, S.river_of(mid), lv - hm, np.zeros(len(mid))]
        rows.append(R)
        caps.append(np.c_[p0, z0, p1, z1, d])

    # snags: top on the bed in the water, the stem leaning up onto the bank of an outer bend (or any bank of a steep
    # wooded reach), pointing downstream: its butt where it comes to rest on the bank (`lean`)
    xy, (u_k, u_l, u_a, u_d, u_s, u_w, _) = lattice(1)
    if len(xy):
        g = S.sample(xy)
        wood = np.zeros(len(xy))
        if trees_xy is not None and len(trees_xy):
            from scipy.spatial import cKDTree
            dt, _ = cKDTree(trees_xy).query(xy, distance_upper_bound=14.0)
            wood = _ss(14.0, 6.0, dt)
        e = g["energy"]
        water = (g["sd"] < -0.3) & (g["sd"] > -0.75 * g["w"] - 0.3) & (g["ford"] < 0.25)
        p = water * (0.08 * _ss(0.2, 0.7, -g["bend"]) + 0.5 * wood * _ss(0.3, 0.6, e) + 0.03 * wood)
        keep = u_k < np.clip(p * dens, 0, 1)
        nb = bank_dir(xy, g)
        th = 25.0 + 30.0 * u_a  # (deg off square to the bank: the top downstream of the butt)
        up = nb * np.cos(np.radians(th))[:, None] - g["t"] * np.sin(np.radians(th))[:, None]
        lo, hi = KINDS["snag"]["scale"]
        lmax = lo + (hi - lo) * u_l ** 1.2
        p1, L = lean(field, xy, up, np.full(len(xy), lo), lmax, 0.0)
        keep &= np.isfinite(L)
        L = np.nan_to_num(L, nan=lo)
        keep &= S.sample(p1)["sd"] > 0.0  # (its butt on the bank, out of the water)
        d0, d1 = KINDS["snag"]["diameter"]
        d = d0 + (d1 - d0) * np.clip(0.3 * u_d + 0.7 * (L - lo) / (hi - lo), 0, 1)
        emit("snag", xy, p1, d, np.full(len(xy), PLACES.index("water")), keep, "snag: bank into the water")
    # limbs caught on the upstream side of boulders standing in the water, across the current
    if rocks is not None and len(rocks):
        R = rocks[(rocks[:, 7] == PLACES.index("water")) & (rocks[:, 4] > 0.7)]
        if len(R):
            ii = np.rint(R[:, 0] * 10).astype(np.int64)
            jj = np.rint(R[:, 1] * 10).astype(np.int64)
            H = lambda a: noise._hash(ii, jj, np.full(len(R), a, np.int64), seed + 41)
            g = S.sample(R[:, :2])
            lo, hi = KINDS["limb"]["scale"]
            L = np.clip(lo + (hi - lo) * H(2) ** 1.3, lo, np.minimum(hi, 2.0 * g["w"] + 0.5))
            d0, d1 = KINDS["limb"]["diameter"]
            d = d0 + (d1 - d0) * (0.4 * H(3) + 0.6 * (L - lo) / (hi - lo))
            c = R[:, :2] - g["t"] * (0.5 * R[:, 4:5] + 0.5 * d[:, None] + 0.08)
            ax = _rot(np.c_[-g["t"][:, 1], g["t"][:, 0]], 50.0 * (H(4) - 0.5))
            p0, p1 = c - 0.5 * L[:, None] * ax, c + 0.5 * L[:, None] * ax
            emit("limb", p0, p1, d, np.full(len(R), PLACES.index("water")), H(1) < 0.22 * dens,
                 "limb: on a boulder")
    xy, (u_k, u_l, u_a, u_d, u_s, u_w, u_b) = lattice(2)
    if len(xy):
        g = S.sample(xy)
        pool, riffle, bar = S.forms(xy, g)
        h, _ = field.column(xy[:, 0], xy[:, 1])
        dep = g["level"] - h
        lo, hi = KINDS["limb"]["scale"]
        d0, d1 = KINDS["limb"]["diameter"]
        # limbs on a bar's head, along the flow, one end in the shallows
        head = bar * _ss(0.3, 0.8, g["bend"]) * _ss(0.35, -0.05, dep) * (g["sd"] < 0.8) * (g["ford"] < 0.25)
        # (its lower end in the shallows, leaning up the bar: along the flow, toward the bank a little)
        ax = _rot(g["t"], 60.0 * (u_a - 0.5))
        ax = ax * np.sign(np.einsum("ij,ij->i", ax, bank_dir(xy, g)) + 1e-9)[:, None]
        p1, L = lean(field, xy, ax, np.full(len(xy), lo), lo + (hi - lo) * u_l ** 1.5, 0.0)
        okb = np.isfinite(L)
        L = np.nan_to_num(L, nan=lo)
        d = d0 + (d1 - d0) * np.clip(0.4 * u_d + 0.6 * (L - lo) / (hi - lo), 0, 1)
        emit("limb", xy, p1, d, np.full(len(xy), PLACES.index("bar")),
             okb & (u_k < np.clip(0.18 * head * dens, 0, 1)), "limb: bar head")
        # limbs wedged bank to bank across a narrow channel (both ends on the banks, the middle over the water)
        narrow = (g["w"] < 2.2) & (g["sd"] < -0.2) & (g["u"] < 0.5) & (g["ford"] < 0.25)
        nb = bank_dir(xy, g)
        ctr = xy - nb * (g["w"] + g["sd"])[:, None]  # (the channel's middle: sd = -w there)
        ax = _rot(nb, 40.0 * (u_b - 0.5))
        reach = (g["w"] + 0.6 + 0.8 * u_w) / np.maximum(np.cos(np.radians(40.0 * (u_b - 0.5))), 0.5)
        p0, p1 = ctr - reach[:, None] * ax, ctr + reach[:, None] * ax
        ok = narrow & (S.sample(p0)["sd"] > 0.1) & (S.sample(p1)["sd"] > 0.1)
        L = 2 * reach
        d = np.clip(d0 + (d1 - d0) * (0.5 * u_d + 0.3 * L / hi), d0, d1)
        wood = 1.0
        if trees_xy is not None and len(trees_xy):
            from scipy.spatial import cKDTree
            dt, _ = cKDTree(trees_xy).query(xy, distance_upper_bound=14.0)
            wood = 0.4 + 0.6 * _ss(14.0, 6.0, dt)
        emit("limb", p0, p1, d, np.full(len(xy), PLACES.index("water")),
             ok & (L <= hi) & (u_s < np.clip(0.12 * wood * dens, 0, 1)), "limb: wedged across")
    if not rows:
        return np.zeros((0, 11)), np.zeros((0, CAP_COLS))
    R, C = np.concatenate(rows), np.concatenate(caps)
    # (no two pieces in one place: the bigger stays; capsules kept with their rows)
    tag = np.arange(len(R), dtype=float)
    Rt = np.c_[R, tag]
    Rk = _thin(Rt, 0.3)
    idx = Rk[:, -1].astype(int)
    return R[idx], C[idx]


def manifest_kinds() -> dict:
    return {k: {"scale_m": v["scale"], "diameter_m": v["diameter"], "squash": v["squash"], "what": v["what"],
                "z": "surface (the ground or bed under its middle); the capsule's ends rest on the bed, a bank or a "
                     "boulder",
                "footprint": {"shape": "capsule", "ends": "x0, y0, z0, x1, y1, z1 (the axis; end 0 the lower)",
                              "diameter": "diameter"},
                "asset": ("a bare stem, 1 m long along +x at scale 1 (the row's scale is its length), unit diameter "
                          "scaled to the row's diameter: " + ("broken branch stubs along it, a root plate or a "
                                                              "snapped butt at -x, the top tapering to +x"
                                                              if k == "snag" else
                                                              "straight or forked at the +x end, a few twigs"))}
            for k, v in KINDS.items()}
