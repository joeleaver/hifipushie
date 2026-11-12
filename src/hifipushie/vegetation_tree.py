"""The tree as it grows: its nodes, the shadow grid, the envelope, paths along limbs, the limbs. Part of vegetation (vegetation.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import vegetation

class _Nodes:
    def __init__(self, cap=4096):
        self.n = 0
        self.cap = cap
        for k, (t, d) in vegetation._FIELDS.items():
            setattr(self, "_" + k, np.zeros((cap,) + ((3, 3) if d == 33 else (d,) if d else ()), t))

    def __getattr__(self, k):
        if k in vegetation._FIELDS:
            return getattr(self, "_" + k)[: self.n]
        raise AttributeError(k)

    def add(self, m, **kw):
        if self.n + m > self.cap:
            self.cap = max(2 * self.cap, self.n + m)
            for k in vegetation._FIELDS:
                a = getattr(self, "_" + k)
                b = np.zeros((self.cap,) + a.shape[1:], a.dtype)
                b[: self.n] = a[: self.n]
                setattr(self, "_" + k, b)
        s = slice(self.n, self.n + m)
        for k in vegetation._FIELDS:
            a = getattr(self, "_" + k)
            if k in kw:
                a[s] = kw[k]
            else:
                a[s] = 0
        self.n += m
        return np.arange(s.start, s.stop)

    def keep(self, mask):
        idx = np.flatnonzero(mask)
        new = -np.ones(self.n, np.int64)
        new[idx] = np.arange(len(idx))
        for k in vegetation._FIELDS:
            a = getattr(self, "_" + k)
            a[: len(idx)] = a[idx]
        self.n = len(idx)
        p = self.parent
        p[1:] = new[p[1:]]
        return new


def _per(lst, order):
    lst = lst if isinstance(lst, (list, tuple)) else [lst]
    o = np.minimum(np.asarray(order), len(lst) - 1)
    return np.asarray(lst, dtype=float)[o]


def _norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _compass(d):
    if isinstance(d, str):
        a = {"n": 0, "ne": 45, "e": 90, "se": 135, "s": 180, "sw": 225, "w": 270, "nw": 315}[d.lower()]
        return np.array([math.sin(math.radians(a)), math.cos(math.radians(a)), 0.0])  # +y north, +x east
    return np.asarray(d, float)


def _shadow(src, lo, dims, a, b, depth, tilt, weight=1.0, tail=vegetation.TAIL):
    """The shadow grid of leafy points src (cell units, origin lo), each casting `weight` (its internode's length:
    short internodes carry less leaf)."""
    C = np.zeros(dims)
    ij = np.clip((src - lo).astype(np.int64), 0, np.array(dims) - 1)
    np.add.at(C, (ij[:, 0], ij[:, 1], ij[:, 2]), weight)
    S = np.zeros(dims)
    for q in range(depth + 1):
        w = 2 * q + 1
        B = C if q == 0 else ndimage.uniform_filter(C, size=(w, w, 1), mode="constant") * (w * w)
        if q:
            sx, sy = int(round(q * tilt[0])), int(round(q * tilt[1]))
            if sx or sy:
                B = ndimage.shift(B, (sx, sy, 0), order=0, mode="constant")
            S[:, :, :-q] += a * b ** (-q) * B[:, :, q:]
        else:
            S += a * B
    # below the pyramid the shade fades instead of ending: cut off at `depth`, the light came back exactly that far
    # under every foliage layer and the next layer formed there (crowns in level bands `depth` cells apart)
    if tail > 0 and depth > 0 and dims[2] > depth + 1:
        last = a * b ** (-depth) * B
        acc = np.zeros(dims[:2])
        for z in range(dims[2] - 1, -1, -1):
            zs = z + depth + 1
            if zs < dims[2]:
                acc = tail * (acc + last[:, :, zs])
            S[:, :, z] += acc
    return S


def _inside(P, vol):
    """Points (m) inside a prune volume."""
    if "box" in vol:
        lo, hi = np.asarray(vol["box"][0], float), np.asarray(vol["box"][1], float)
        return np.all((P >= np.minimum(lo, hi)) & (P <= np.maximum(lo, hi)), axis=1)
    if "sphere" in vol:
        c, r = np.asarray(vol["sphere"][0], float), float(vol["sphere"][1])
        return np.linalg.norm(P - c, axis=1) <= r
    if "above" in vol:
        return P[:, 2] >= float(vol["above"])
    raise ValueError(f"prune volume needs box, sphere, above, below or under: {vol}")


def _envelope(P, env):
    """How far outside the envelope each point (m) is, in units of its softness (0 inside)."""
    if env is None:
        return np.zeros(len(P))
    z0, z1 = env.get("base", 0.0), env["top"]
    r = env["radius"]
    t = np.clip((P[:, 2] - z0) / max(z1 - z0, 1e-6), 0, 1)
    # `lean` [dx, dy]: how far the crown's middle has moved by its top (a wind-flagged wedge)
    c = np.asarray(env.get("center", [0, 0]), float)[None] + t[:, None] * np.asarray(env.get("lean", [0, 0]), float)[None]
    sh = env.get("shape", "ellipsoid")
    if sh == "ellipsoid":
        rr = r * np.sqrt(np.clip(1 - (2 * t - 1) ** 2, 0, 1))
    elif sh == "cone":
        rr = r * (1 - t)
    elif sh == "column":
        rr = r * np.ones_like(t)
    elif sh == "umbrella":  # a flat wide top over a narrow underside (a wind-clipped pine, an acacia)
        rr = r * np.clip(0.25 + 1.5 * t, 0, 1) * np.where(t > 0.9, np.sqrt(np.clip(1 - ((t - 0.9) / 0.1) ** 2, 0, 1)) * 0.3 + 0.7, 1.0)
    elif sh == "dome":  # widest low, rounded top
        rr = r * np.sqrt(np.clip(1 - t ** 2, 0, 1))
    elif sh == "profile":  # [[t, share of radius], ...] bottom to top
        pr = np.asarray(env["profile"], float)
        rr = r * np.interp(t, pr[:, 0], pr[:, 1])
    else:
        raise ValueError(f"envelope shape {sh!r}: ellipsoid, cone, column, dome, umbrella or profile")
    soft = env.get("soft", 0.15 * r)
    d = np.linalg.norm(P[:, :2] - c, axis=1) - rr
    d = np.maximum(d, np.maximum(P[:, 2] - z1, z0 - P[:, 2]))
    return np.clip(d / soft, 0, None)


def _path(pts, smooth=True):
    """A drawn path as a dense polyline + its arc lengths: through the points on a Catmull-Rom curve (a path of
    straight legs grew as a limb with corners)."""
    pts = np.asarray(pts, float)
    if smooth and len(pts) >= 3:
        P = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
        out = []
        for i in range(1, len(P) - 2):
            n = max(2, int(np.ceil(np.linalg.norm(P[i + 1] - P[i]) / 0.4)))
            t = (np.arange(n) / n)[:, None]
            out.append(0.5 * ((2 * P[i]) + (-P[i - 1] + P[i + 1]) * t + (2 * P[i - 1] - 5 * P[i] + 4 * P[i + 1] - P[i + 2]) * t ** 2
                              + (-P[i - 1] + 3 * P[i] - 3 * P[i + 1] + P[i + 2]) * t ** 3))
        pts = np.vstack(out + [pts[-1:]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return pts, np.concatenate([[0], np.cumsum(seg)])


def _along(pts, cum, s):
    s = np.clip(s, 0, cum[-1])
    i = min(np.searchsorted(cum, s, side="right") - 1, len(pts) - 2)
    t = (s - cum[i]) / max(cum[i + 1] - cum[i], 1e-12)
    return pts[i] + t * (pts[i + 1] - pts[i])


def ground_at(spec: dict, xy) -> np.ndarray:
    """The ground's height (m) under [x, y] points: `environment.ground` {"level": m at the plant's foot (0), "slope":
    deg, "toward": [x, y] the way it falls}. Nothing a plant grows or carries may lie under it."""
    g = ((spec.get("environment") or {}).get("ground") or {})
    xy = np.atleast_2d(np.asarray(xy, float))[:, :2]
    z = np.full(len(xy), float(g.get("level", 0.0)))
    if g.get("slope"):
        t = np.asarray(g.get("toward", [1, 0]), float)
        z = z - math.tan(math.radians(float(g["slope"]))) * (xy @ (t / max(np.linalg.norm(t), 1e-9)))
    return z


def steps_of(s: dict) -> int:
    return int(np.clip(round(s["age"] / s["habit"]["years_per_step"]), 2, 80))


def limb_id(key) -> str:
    """A limb's lasting name: from its bud's lineage, so the same bud has it whatever else changes on the tree."""
    v_, out = int(key) % 36 ** 4, ""
    for _ in range(4):
        out = "0123456789abcdefghijklmnopqrstuvwxyz"[v_ % 36] + out
        v_ //= 36
    return "L" + out


def find_limb(tree: dict, ref: str):
    """The axis a limb reference names: a guide's name, a limb id ("Lk7f3", lasting), or a compass name ("SW2", of
    this grown tree only). None when the tree has no such limb."""
    if ref in tree["guides"]:
        return tree["guides"][ref]
    if isinstance(ref, str) and len(ref) == 5 and ref[0] == "L":
        for ai, a in enumerate(tree["axes"]):
            if a["order"] == 1 and "node" in a and a["node"] < len(tree["key"]) and tree["axis"][a["node"]] == ai \
                    and limb_id(tree["key"][a["node"]]) == ref:
                return ai
    L = next((q for q in limbs(tree) if q["name"] == ref), None)
    return None if L is None else L["axis"]


def stout_path(tree: dict, n0: int, kids: dict | None = None) -> np.ndarray:
    """A limb as an eye follows it: from node n0 on through the stoutest child at every fork, to a shoot's end. (The
    growth's own axis often ends a metre out, where a side shoot took over.)"""
    if kids is None:
        kids = {}
        for i in range(1, len(tree["parent"])):
            kids.setdefault(int(tree["parent"][i]), []).append(i)
    rad, out, q = tree["radius"], [int(n0)], int(n0)
    while kids.get(q):
        q = max(kids[q], key=lambda c: rad[c])
        out.append(q)
    return np.array(out)


def limbs(tree: dict, count: int = 12, min_share: float = 0.12) -> list[dict]:
    """The tree's main limbs, named so they can be talked about and taken over: first-order branches, the stoutest
    `count` whose base is at least `min_share` of the trunk's radius there. A drawn limb has its guide's name; a grown
    one is named by where its end points and its rank up the trunk ("SW2" = the second limb up that ends to the
    south-west). Names are of THIS grown tree: an edit that regrows it may rename them; take_limb makes one a guide,
    which keeps its name and shape."""
    P, par, ax, rad = tree["pos"], tree["parent"], tree["axis"], tree["radius"]
    yps = tree["spec"]["habit"]["years_per_step"]
    gname = {ai: g for g, ai in tree["guides"].items()}
    kids = {}
    for i in range(1, len(par)):
        kids.setdefault(int(par[i]), []).append(i)
    out = []
    for ai, a in enumerate(tree["axes"]):
        if a["order"] != 1 or "node" not in a:
            continue
        n0 = a["node"]
        if n0 >= len(P) or tree["order"][n0] != 1 or ax[n0] != ai:
            continue
        nodes = np.flatnonzero(ax == ai)
        if len(nodes) < 3:
            continue
        base = int(par[n0])
        if rad[n0] < min_share * rad[base] and ai not in gname:
            continue
        sub, stack = [], [int(n0)]
        while stack:
            q = stack.pop()
            sub.append(q)
            stack.extend(kids.get(q, ()))
        sub = np.array(sub)
        far = P[sub][np.argmax(np.linalg.norm(P[sub] - P[base], axis=1))]
        d = far - P[base]
        nodes = stout_path(tree, n0, kids)
        seg = np.linalg.norm(np.diff(np.vstack([P[base], P[nodes]]), axis=0), axis=1).sum()
        out.append({"axis": ai, "guide": gname.get(ai), "at": P[base].round(2).tolist(), "height": round(float(P[base][2]), 2),
                    "diameter": round(float(2 * rad[n0]), 3), "length": round(float(seg), 2), "end": P[nodes[-1]].round(2).tolist(),
                    "reach": round(float(np.linalg.norm(P[sub][:, :2] - P[1][:2], axis=1).max()), 2), "low": round(float(P[sub][:, 2].min()), 2),
                    "high": round(float(P[sub][:, 2].max()), 2), "nodes": int(len(sub)),
                    "born_year": round(float(tree["born"][n0] * yps), 1), "key": str(int(tree["key"][n0])),
                    "id": gname.get(ai) or limb_id(tree["key"][n0]),
                    "compass": _compass_name(d)})
    out.sort(key=lambda L: -L["diameter"])
    keep = [L for L in out if L["guide"]] + [L for L in out if not L["guide"]][:count]
    keep.sort(key=lambda L: L["height"])
    seen = {}
    for L in keep:
        if L["guide"]:
            L["name"] = L["guide"]
        else:
            seen[L["compass"]] = seen.get(L["compass"], 0) + 1
            L["name"] = f"{L['compass']}{seen[L['compass']]}"
    return keep


def _compass_name(d) -> str:
    if np.linalg.norm(d[:2]) < 0.25 * abs(d[2]):
        return "UP"
    a = math.degrees(math.atan2(d[0], d[1])) % 360  # +y = north, +x = east
    return ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[int((a + 22.5) // 45) % 8]


def limb_path(tree: dict, limb: dict, points: int = 7) -> list:
    """A limb's own axis as a guide path: from where it leaves the trunk to its end, `points` of them evenly along."""
    nodes = stout_path(tree, tree["axes"][limb["axis"]]["node"])
    pts = np.vstack([tree["pos"][tree["parent"][nodes[0]]], tree["pos"][nodes]])
    cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    k = int(max(3, min(points, len(pts))))
    return [_along(pts, cum, t).round(3).tolist() for t in np.linspace(0, cum[-1], k)]
