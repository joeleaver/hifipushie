"""Garments built like a tailor builds them: pattern pieces drafted from the body's measurements, sewn round the body
and settled by Blender's cloth simulation (sewing springs), then checked for fit.

Spec `spec["cloth"][name]`:
  {"pattern": {"from": FreeSewing design ("simon", "carlton"...),
               "ease": {"chest": 0.12, ...} (fraction of the body measurement), "length", "sleeve_length",
               "options": {raw FreeSewing options}, "measurements": {overrides, mm} (a fixed size instead of the body's)},
   "pieces": {name: piece spec (pattern.from_spec) + "wrap"}, "seams": [[a, b], ...], "stitches": [[a, b]...]
             (own pieces, or added to a design's), "drop": [pieces of the design left out],
   "alter": [pattern ops], "fabric": preset name or {...}, "interfaced": [pieces], "color": "#rrggbb",
   "state": "worn" | {"hang": {"pins": ["piece:point", ...], "hook": [x, y, z]}},
   "resolution": m (triangle size, default 0.02)}

The garment is a recipe: ease is relative to the body and the draft is made to measure on whatever body it goes on
(`tailor.measure`). Nothing is warped from one body to another.

Build: `pieces()` -> flat pieces; `mesh()` -> one flat triangle mesh of all pieces (both sides of every seam sampled
with the same count: ease is spread evenly along it), sewing pairs; `place()` -> start positions round the body (each
piece wrapped onto the torso, an arm or the neck); `simulate()` runs blender_cloth.py (sewing springs, the flat
pattern as the rest shape, the body as collider) under resources.heavy; `fit()` measures strain against the flat
pattern, ease against the body, distance off the body.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, Delaunay, cKDTree

from . import pattern, tailor

DESIGNS = Path(__file__).with_name("cloth_designs.json")
SCRIPT = Path(__file__).with_name("blender_cloth.py")
VERSION = 1  # bump with any change to the mesh, placement or sim job: results are cached by it

# Blender cloth settings per fabric (mass per vertex at ~2 cm triangles, spring stiffnesses in Blender's units),
# the stretch past which the fabric is strained (fit check), interfaced pieces' bending multiplier (`stiff`).
FABRICS = {
    "shirting": {"mass": 0.15, "tension": 60, "compression": 15, "shear": 15, "bending": 0.1, "air": 1.0,
                 "limit": 0.03, "thickness": 0.0004, "stiff": 40},
    "jersey": {"mass": 0.2, "tension": 5, "compression": 5, "shear": 3, "bending": 0.02, "air": 1.0,
               "limit": 0.25, "thickness": 0.0007, "stiff": 30},
    "wool_coating": {"mass": 0.6, "tension": 40, "compression": 40, "shear": 20, "bending": 1.5, "air": 1.0,
                     "limit": 0.03, "thickness": 0.002, "stiff": 20},
    "denim": {"mass": 0.5, "tension": 40, "compression": 40, "shear": 30, "bending": 2.0, "air": 1.0,
              "limit": 0.02, "thickness": 0.001, "stiff": 10},
    "linen": {"mass": 0.25, "tension": 25, "compression": 25, "shear": 10, "bending": 0.3, "air": 1.0,
              "limit": 0.03, "thickness": 0.0005, "stiff": 20},
}


def designs() -> dict:
    return json.loads(DESIGNS.read_text())


def fabric(g: dict) -> dict:
    f = g.get("fabric", "shirting")
    if isinstance(f, str):
        if f not in FABRICS:
            raise ValueError(f"no fabric {f!r} (have {', '.join(FABRICS)})")
        return dict(FABRICS[f], name=f)
    base = dict(FABRICS[f.get("preset", "shirting")])
    base.update({k: v for k, v in f.items() if k != "preset"})
    return dict(base, name=f.get("preset", "custom"))


# ---------------------------------------------------------------- pieces


def pieces(g: dict, meas_mm: dict) -> dict:
    """{"pieces": {name: piece (+ "wrap")}, "seams", "stitches", "interfaced", "draft"}."""
    out, seams, stitches, interfaced, draft_info = {}, [], [], [], None
    pat = g.get("pattern")
    if pat:
        from . import freesewing
        tbl = designs().get(pat["from"])
        if tbl is None:
            raise ValueError(f"no design table for {pat['from']!r} in cloth_designs.json (have "
                             f"{', '.join(k for k in designs() if not k.startswith('_'))})")
        m = dict(meas_mm)
        m.update(pat.get("measurements") or {})
        opts = dict(pat.get("options") or {})
        words = tbl.get("words", {})
        for k, v in (pat.get("ease") or {}).items():
            if k not in words.get("ease", {}):
                raise ValueError(f"{pat['from']}: no ease at {k!r} (have {', '.join(words.get('ease', {}))})")
            opts[words["ease"][k]] = float(v)
        for k, v in pat.items():
            if k in words and k != "ease":
                opts[words[k]] = v
        d = freesewing.draft(pat["from"], m, opts, float(pat.get("sa", 10)))
        draft_info = {"design": pat["from"], "options": opts, "measurements": m}
        for nm, pd in tbl["pieces"].items():
            part = d["parts"].get(pd["part"])
            if part is None:
                raise ValueError(f"draft {pat['from']} has no part {pd['part']} (options turned it off?)")
            pc = pattern.from_freesewing(part, nm, fold=pd.get("fold"))
            if pd.get("mirror"):
                pc = pattern.mirror_x(pc)
            pc["wrap"] = dict(pd.get("wrap") or {})
            out[nm] = pc
        for nm in g.get("drop", []):
            out.pop(nm, None)
        out = pattern.apply(out, [op for op in tbl.get("alter", []) if op["piece"] in out])
        seams += tbl.get("seams", [])
        stitches += tbl.get("stitches", [])
        interfaced += tbl.get("interfaced", [])
    for nm, pd in (g.get("pieces") or {}).items():
        pc = pattern.from_spec(nm, pd)
        pc["wrap"] = dict(pd.get("wrap") or {})
        out[nm] = pc
    for nm in g.get("drop", []):
        out.pop(nm, None)
    out = pattern.apply(out, g.get("alter"))
    seams += g.get("seams", [])
    stitches += g.get("stitches", [])
    interfaced = list(dict.fromkeys(interfaced + list(g.get("interfaced", []))))
    keep = set(out)
    side_ok = lambda s: all(e.split(":")[0] in keep for e in ([s] if isinstance(s, str) else s))
    seams = [s for s in seams if side_ok(s[0]) and side_ok(s[1])]
    stitches = [s for s in stitches if side_ok(s[0]) and side_ok(s[1])]
    return {"pieces": out, "seams": seams, "stitches": stitches, "interfaced": [p for p in interfaced if p in keep],
            "draft": draft_info}


# ---------------------------------------------------------------- flat mesh


def _resample(L: np.ndarray, fracs) -> np.ndarray:
    seg = np.linalg.norm(np.diff(L, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    s = np.asarray(fracs) * cum[-1]
    return np.c_[np.interp(s, cum, L[:, 0]), np.interp(s, cum, L[:, 1])]


def _inside(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Even-odd point-in-polygon for points Q against the closed polygon P."""
    x, y = Q[:, 0][:, None], Q[:, 1][:, None]
    a, b = P[None, :, :], np.roll(P, -1, axis=0)[None, :, :]
    cond = (a[..., 1] > y) != (b[..., 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = a[..., 0] + (y - a[..., 1]) * (b[..., 0] - a[..., 0]) / (b[..., 1] - a[..., 1])
    return (np.sum(cond & (x < xc), axis=1) % 2) == 1


def _seg_dist(Q: np.ndarray, P: np.ndarray) -> np.ndarray:
    """Distance from points Q to the closed polyline P."""
    A, B = P, np.roll(P, -1, axis=0)
    out = np.full(len(Q), np.inf)
    for s in range(0, len(A), 256):
        a, b = A[s:s + 256][None], B[s:s + 256][None]
        ab = b - a
        t = np.clip(np.sum((Q[:, None] - a) * ab, -1) / np.maximum(np.sum(ab * ab, -1), 1e-18), 0, 1)
        d = np.linalg.norm(Q[:, None] - (a + t[..., None] * ab), axis=-1).min(1)
        out = np.minimum(out, d)
    return out


def mesh(B: dict, h: float = 0.02) -> dict:
    """One flat mesh of all pieces: {"uv" (n, 2) pattern coords, "piece" (n,) index, "names", "F" (m, 3),
    "sew" (k, 2) vertex pairs, "sew_seam" (k,) seam index, "stitch" (s, 2), "marks" {piece:mark: vertex},
    "points" {piece:point: vertex} (named outline points), "border" (n,) bool}."""
    pcs = B["pieces"]
    names = list(pcs)
    fixed = {nm: {} for nm in names}  # piece -> {forward arc (tuple of outline ids): samples (forward)}

    def put(nm, ix, pts):
        """Store an arc's samples forward; return its keys in the asked direction."""
        n = len(pcs[nm]["P"])
        fwd = len(ix) < 2 or ix[1] == (ix[0] + 1) % n
        fix = tuple(ix) if fwd else tuple(ix[::-1])
        fpts = pts if fwd else pts[::-1]
        if fix in fixed[nm] and len(fixed[nm][fix]) != len(fpts):
            raise ValueError(f"{nm}: an edge is sewn twice with different counts")
        fixed[nm][fix] = fpts
        m = len(pts) - 1
        return [(nm, fix, q if fwd else m - q) for q in range(m + 1)]

    # Each side of a seam is a chain of edges (one or more); a gap between two edges of a chain on the same piece
    # is folded away (a pleat or tuck: both its ends sew to the same point). Samples are laid at fractions of each
    # side's own length (ease spread evenly), and every junction of either side is a sample of both.
    sew_keys = []
    for si, (A, Bs) in enumerate(B["seams"]):
        sides = []
        for side in (A, Bs):
            chain = [side] if isinstance(side, str) else list(side)
            arcs = [_edge(pcs, e) for e in chain]
            lens = np.array([pattern.length(pcs[nm]["P"][ix]) for nm, ix in arcs])
            sides.append((arcs, np.r_[0, np.cumsum(lens)] / lens.sum()))
        n = max(2, int(math.ceil(max(pattern.length(pcs[nm]["P"][ix]) for s in sides for nm, ix in s[0]) * 0 +
                                 max(sum(pattern.length(pcs[nm]["P"][ix]) for nm, ix in s[0]) for s in sides) / h)))
        U = np.unique(np.round(np.r_[sides[0][1], sides[1][1]], 9))
        G = [0.0]
        for u0, u1 in zip(U[:-1], U[1:]):
            c = max(1, int(round(n * (u1 - u0))))
            G += list(np.linspace(u0, u1, c + 1)[1:])
        G = np.asarray(G)
        at = [[[] for _ in G] for _ in range(2)]  # per side, per global sample: its keys
        for k, (arcs, cum) in enumerate(sides):
            for j, (nm, ix) in enumerate(arcs):
                s0, s1 = cum[j], cum[j + 1]
                sel = np.where((G >= s0 - 1e-9) & (G <= s1 + 1e-9))[0]
                f = np.clip((G[sel] - s0) / max(s1 - s0, 1e-12), 0, 1)
                keys = put(nm, ix, _resample(pcs[nm]["P"][ix], f))
                for g, kk in zip(sel, keys):
                    at[k][g].append(kk)
        for g in range(len(G)):
            for ka in at[0][g]:
                for kb in at[1][g]:
                    sew_keys.append((si, ka, kb))
    uv, piece_of, F, border = [], [], [], []
    key_vid, points, marks = {}, {}, {}
    for pi, nm in enumerate(names):
        pc = pcs[nm]
        Pp = pc["P"]
        n = len(Pp)
        arcs = sorted(fixed[nm].items(), key=lambda kv: kv[0][0])
        for (ix, _), (ix2, _) in zip(arcs, arcs[1:] + arcs[:1]):
            if len(arcs) > 1 and ((ix2[0] - ix[0]) % n) < ((ix[-1] - ix[0]) % n):
                raise ValueError(f"{nm}: two sewn edges overlap ({ix[0]}..{ix[-1]} and {ix2[0]}..{ix2[-1]})")
        ring, rkeys, pending = [], [], []

        def emit(p, key):
            vid = len(uv) + len(ring)
            for pk in pending:
                key_vid[pk] = vid
            pending.clear()
            ring.append(p)
            if key is not None:
                key_vid[key] = vid
            rkeys.append(key)

        def free(i, j):
            path = [i]
            k = i
            while k != j:
                k = (k + 1) % n
                path.append(k)
            L = Pp[path]
            if len(path) < 2 or pattern.length(L) < 1e-9:
                return
            cnt = max(1, int(round(pattern.length(L) / h)))
            for p in _resample(L, np.linspace(0, 1, cnt + 1))[:-1]:
                emit(p, None)

        if not arcs:
            L = np.r_[Pp, Pp[:1]]
            cnt = max(3, int(round(pattern.length(L) / h)))
            for p in _resample(L, np.linspace(0, 1, cnt + 1))[:-1]:
                emit(p, None)
        else:
            for a, (ix, pts) in enumerate(arcs):
                for q in range(len(pts) - 1):
                    emit(pts[q], (nm, ix, q))
                pending.append((nm, ix, len(pts) - 1))
                nxt = arcs[(a + 1) % len(arcs)][0][0]
                if nxt != ix[-1]:
                    free(ix[-1], nxt)
            # the last arc's end resolves to the ring's first vertex
            for pk in pending:
                key_vid[pk] = len(uv)
            pending.clear()
        ring = np.asarray(ring)
        # interior: a hex lattice clear of the outline, plus marks (buttons, pins) inside the piece
        lo, hi = ring.min(0), ring.max(0)
        dy = h * math.sqrt(3) / 2
        rows = []
        for r, y in enumerate(np.arange(lo[1] + dy / 2, hi[1], dy)):
            xs = np.arange(lo[0] + (h / 2 if r % 2 else 0), hi[0], h)
            rows.append(np.c_[xs, np.full(len(xs), y)])
        Q = np.concatenate(rows) if rows else np.zeros((0, 2))
        if len(Q):
            Q = Q[_inside(ring, Q)]
            Q = Q[_seg_dist(Q, ring) > 0.6 * h]
        mk = {k: np.asarray(v, float) for k, v in pc["marks"].items()}
        mk = {k: v for k, v in mk.items() if len(v) == 2 and _inside(ring, v[None])[0]}
        if mk and len(Q):
            M = np.array(list(mk.values()))
            d = cKDTree(M).query(Q)[0]
            Q = Q[d > 0.5 * h]
        Mk = np.array(list(mk.values())) if mk else np.zeros((0, 2))
        X = np.r_[ring, Q, Mk]
        tri = Delaunay(X).simplices
        cen = X[tri].mean(1)
        tri = tri[_inside(ring, cen)]
        # drop slivers along the outline (all three on it and nearly flat)
        a, b, c = X[tri[:, 0]], X[tri[:, 1]], X[tri[:, 2]]
        ar = 0.5 * np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
        allb = np.all(tri < len(ring), axis=1)
        tri = tri[~(allb & (ar < 0.02 * h * h))]
        # orient counter-clockwise in the pattern (normals out of the pattern's face)
        a, b, c = X[tri[:, 0]], X[tri[:, 1]], X[tri[:, 2]]
        cw = ((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0]) < 0
        tri[cw] = tri[cw][:, [0, 2, 1]]
        base = len(uv)
        for k, i in pc["names"].items():  # named outline points -> nearest ring vertex
            points[f"{nm}:{k}"] = base + int(np.argmin(np.linalg.norm(ring - Pp[i], axis=1)))
        for j, k in enumerate(mk):
            marks[f"{nm}:{k}"] = base + len(ring) + len(Q) + j
        uv.extend(X)
        piece_of.extend([pi] * len(X))
        border.extend([True] * len(ring) + [False] * (len(Q) + len(Mk)))
        F.append(tri + base)
    sew = np.array([(key_vid[a], key_vid[b]) for _, a, b in sew_keys], dtype=np.int64).reshape(-1, 2)
    sew_seam = np.array([si for si, _, _ in sew_keys], dtype=np.int64)
    ok = sew[:, 0] != sew[:, 1]
    sew, sew_seam = sew[ok], sew_seam[ok]
    stitch = []
    for a, b in B["stitches"]:
        va = marks.get(a, points.get(a))
        vb = marks.get(b, points.get(b))
        if va is None or vb is None:
            raise KeyError(f"stitch {a} - {b}: no such point/mark (marks inside the piece only)")
        stitch.append((va, vb))
    F = np.concatenate(F)
    stitch = np.array(stitch, dtype=np.int64).reshape(-1, 2)
    # vertices no triangle uses (a mark the triangulation dropped) leave, with their seams/stitches
    used = np.zeros(len(uv), bool)
    used[F.ravel()] = True
    remap = -np.ones(len(uv), np.int64)
    remap[used] = np.arange(used.sum())
    ok = used[sew].all(1)
    sew, sew_seam = remap[sew[ok]], sew_seam[ok]
    stitch = remap[stitch[used[stitch].all(1)]] if len(stitch) else stitch
    return {"uv": np.asarray(uv)[used], "piece": np.asarray(piece_of)[used], "names": names, "F": remap[F],
            "sew": sew, "sew_seam": sew_seam, "stitch": stitch,
            "marks": {k: int(remap[v]) for k, v in marks.items() if used[v]},
            "points": {k: int(remap[v]) for k, v in points.items() if used[v]}, "border": np.asarray(border)[used]}


def _edge(pcs, spec: str):
    nm, arc = spec.split(":", 1)
    if nm not in pcs:
        raise KeyError(f"seam edge {spec!r}: no piece {nm!r} (have {', '.join(pcs)})")
    return nm, pattern.arc_indices(pcs[nm], arc)


# ---------------------------------------------------------------- the body


def body_mesh(spec: dict | None = None, params: dict | None = None) -> dict:
    """The body to dress: {"V", "F" (quads/polys), "J"}. From a MakeHuman body (params) or a model spec's base."""
    if params is not None:
        from . import makehuman
        b = makehuman.body(params)
        L, S = b["L"], b["S"]
        faces, k = [], 0
        for s in S:
            faces.append(list(L[k:k + s]))
            k += s
        return {"V": b["P"], "F": faces, "J": b["J"], "key": json.dumps(params, sort_keys=True)}
    from . import base as basemod, spec as specmod
    se = specmod.expand_mirror(spec)
    srf = basemod.surface(se, spec["base"])
    W, faces = srf["quads"]
    J = {k: np.asarray(v["pos"], float) for k, v in se["joints"].items()}
    return {"V": np.asarray(W), "F": [list(f) for f in faces], "J": J, "key": srf["key"]}


class Body:
    """Measured body + the surfaces pieces are wrapped onto."""

    def __init__(self, b: dict):
        self.V = np.asarray(b["V"], float)
        self.T = tailor.triangles(b["F"])
        self.J = {k: np.asarray(v, float) for k, v in b["J"].items()}
        self.m = tailor.measure(self.V, b["F"], self.J)
        self.at = {k: np.asarray(v) if isinstance(v, list) else v for k, v in self.m["at"].items()}
        self._hull = {}

    def normals(self):
        if not hasattr(self, "_vn"):
            V, T = self.V, self.T
            fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
            vn = np.zeros_like(V)
            for k in range(3):
                np.add.at(vn, T[:, k], fn)
            self._vn = vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)
            self._tree = cKDTree(V)
        return self._vn, self._tree

    def push_out(self, X: np.ndarray, gap: float, iters: int = 4) -> np.ndarray:
        """Start positions inside the body (or closer than gap) moved out along the body's normal: a cloth vertex
        that starts inside the collider is pushed further in, not out."""
        vn, tree = self.normals()
        X = X.copy()
        for _ in range(iters):
            _, i = tree.query(X, k=4)
            n = vn[i].mean(1)
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
            q = self.V[i].mean(1)
            s = np.sum((X - q) * n, 1)
            bad = s < gap
            if not bad.any():
                break
            X[bad] += (gap - s[bad])[:, None] * n[bad]
        return X

    # torso: offset convex hulls of the body's sections (arms and hands left out)
    def hull(self, z: float) -> np.ndarray | None:
        """The torso's section at z as a convex polygon (a tape round it): under the armpit the loops that aren't
        arms; above it the section (torso and arm roots are one loop there) clipped at the shoulder points."""
        zk = round(z / 0.005) * 0.005
        if zk not in self._hull:
            loops = tailor.slice_loops(self.V, self.T, [0, 0, zk], [0, 0, 1.0])
            xs = abs(float(self.at["shoulder.L"][0])) + 0.01
            if zk < self.at["armpit_z"]:
                pts = [L[:, :2] for L in loops if np.all(np.abs(L[:, 0]) < xs)]
            else:
                pts = [L[np.abs(L[:, 0]) < xs, :2] for L in loops if np.any(np.abs(L[:, 0]) < 0.06)]
            pts = np.concatenate(pts) if pts else None
            self._hull[zk] = pts[ConvexHull(pts).vertices] if pts is not None and len(pts) >= 3 else None
        return self._hull[zk]


def _offset_hull(H: np.ndarray, m: float) -> np.ndarray:
    """A convex polygon pushed out by m (vertex normals; fine for a gently curved hull)."""
    c = H.mean(0)
    P = np.r_[H[-1:], H, H[:1]]
    t = P[2:] - P[:-2]
    nrm = np.c_[t[:, 1], -t[:, 0]]
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    flip = np.sum(nrm * (H - c), 1) < 0
    nrm[flip] *= -1
    return H + m * nrm


def _arc_point(H: np.ndarray, start: np.ndarray, s: np.ndarray, sign: float) -> np.ndarray:
    """Points arc length s (signed) round the closed polygon H from its point nearest `start`, positive going the way
    x increases at the start."""
    i0 = int(np.argmin(np.linalg.norm(H - start, axis=1)))
    H = np.roll(H, -i0, axis=0)
    # direction: +s goes toward increasing x at the start
    if H[1, 0] < H[-1, 0]:
        H = np.r_[H[:1], H[1:][::-1]]
    Hc = np.r_[H, H[:1]]
    seg = np.linalg.norm(np.diff(Hc, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    per = cum[-1]
    ss = np.mod(sign * s, per)
    return np.c_[np.interp(ss, cum, Hc[:, 0]), np.interp(ss, cum, Hc[:, 1])]


def _piece_width_at(P: np.ndarray, y: float) -> float:
    xs = []
    A, Bn = P, np.roll(P, -1, axis=0)
    for a, b in zip(A, Bn):
        if (a[1] - y) * (b[1] - y) <= 0 and a[1] != b[1]:
            t = (y - a[1]) / (b[1] - a[1])
            xs.append(a[0] + t * (b[0] - a[0]))
    return (max(xs) - min(xs)) if len(xs) >= 2 else 0.0


def place(B: dict, M: dict, body: Body, gap: float = 0.012) -> np.ndarray:
    """Start positions: each piece wrapped round the body part its `wrap` names (torso front/back, arm.L/R, neck),
    lengths along the pattern kept along the wrap (the sim's rest shape is the flat pattern anyway)."""
    uv, pid = M["uv"], M["piece"]
    X = np.zeros((len(uv), 3))
    pcs = B["pieces"]
    names = M["names"]
    at = body.at
    hps = np.asarray(at["hps.L"])
    arm_z = at["armpit_z"]
    torso = [nm for nm in names if pcs[nm]["wrap"].get("to") == "torso"]
    # Torso pieces go on ONE vertical generalized cylinder (a plan curve extruded up): the convex hull of the torso's
    # sections from the hem to the shoulders, pushed out so its perimeter is the garment's widest girth. Arc length
    # along a fixed plan curve x height is an isometry, so the placed pieces have their flat pattern's lengths
    # (the cloth's rest shape is taken from them). Hulls per height made the pieces' rows jump between shapes.
    C = None
    if torso:
        ylo = min(pcs[nm]["P"][:, 1].min() for nm in torso)
        zs = np.arange(max(hps[2] + ylo, 0.05), hps[2] - 0.01, 0.02)
        pts = [h for z in zs if (h := body.hull(z)) is not None]
        Hu = np.concatenate(pts)
        Hu = Hu[ConvexHull(Hu).vertices]
        P0 = pattern.length(Hu, closed=True)
        ys = np.arange(ylo, 0.0, 0.01)
        Wmax = max(sum(_piece_width_at(pcs[nm]["P"], y) for nm in torso) for y in ys)
        # the fronts overlap at the closure: the girth is the total width less the overlap past centre front
        over = sum(min(abs(pcs[nm]["P"][:, 0].min()), abs(pcs[nm]["P"][:, 0].max())) for nm in torso
                   if pcs[nm]["wrap"].get("side", "front") == "front"
                   and abs(pcs[nm]["P"][:, 0].min() + pcs[nm]["P"][:, 0].max()) > 0.05)  # one-sided pieces
        m = float(np.clip((Wmax - over - P0) / (2 * np.pi), gap, 0.15))
        C = _offset_hull(Hu, m)
    placed = {}
    for k, nm in enumerate(names):
        w = pcs[nm]["wrap"]
        sel = pid == k
        U = uv[sel]
        to = w.get("to", "torso")
        if to == "torso":
            Cw = _offset_hull(C, float(w.get("out", 0.0))) if w.get("out") else C
            cy = 0.5 * (Cw[:, 1].max() + Cw[:, 1].min())
            if w.get("side", "front") == "front":
                start = Cw[np.argmin(np.abs(Cw[:, 0]) + 10 * np.maximum(Cw[:, 1] - cy, 0))]
            else:
                start = Cw[np.argmin(np.abs(Cw[:, 0]) + 10 * np.maximum(cy - Cw[:, 1], 0))]
            q = _arc_point(Cw, start, U[:, 0], 1.0)
            X[sel] = np.c_[q, hps[2] + U[:, 1]]
        elif to.startswith("arm."):
            side = to[4:]
            sh, el, wr = (body.J[f"{j}.{side}"] for j in ("shoulder", "elbow", "wrist"))
            axis = [sh, el, wr]
            seg = [np.linalg.norm(el - sh), np.linalg.norm(wr - el)]
            out_dir = np.array([1.0 if side == "L" else -1.0, 0, 0])
            P = pcs[nm]["P"]
            if "follow" in w:  # this piece's point goes where another (placed) piece's point went, and the
                # piece runs on toward the hand (a cuff: pattern +y toward the hand)
                other, op, mine = w["follow"]
                t_anchor = float(placed[other]["t"](uv[M["points"][f"{other}:{op}"]]))
                y_anchor = float(uv[M["points"][f"{nm}:{mine}"]][1])
                t_of = lambda Q, ta=t_anchor, ya=y_anchor: ta + (Q[..., 1] - ya)
            else:  # the top (sleeve cap) at t0 along shoulder -> elbow -> wrist, pattern -y down the arm
                ytop = P[:, 1].max()
                t0 = float(w.get("t0", -0.02))
                t_of = lambda Q, ytop=ytop, t0=t0: t0 + (ytop - Q[..., 1])
            placed[nm] = {"t": t_of}
            t = t_of(U)
            # a cylinder round the arm at the widest row's girth (isometric: the placed piece keeps its pattern's
            # lengths; a tapered sleeve's underarm edges meet at the widest row and the seam pulls the rest shut)
            yr = np.linspace(P[:, 1].min() + 1e-4, P[:, 1].max() - 1e-4, 60)
            wr_ = np.array([_piece_width_at(P, y) for y in yr])
            R = max(wr_.max() / (2 * np.pi), 0.5 * body.m["mm"]["wrist"] / 1000 / np.pi + gap) + float(w.get("out", 0))
            cx = 0.5 * (P[:, 0].max() + P[:, 0].min())
            out = np.zeros((len(U), 3))
            for i, (x, yv) in enumerate(U):
                ti = float(t[i])
                if ti <= seg[0]:
                    a, d = sh, (el - sh) / seg[0]
                    c = sh + d * ti
                else:
                    d = (wr - el) / seg[1]
                    c = el + d * (ti - seg[0])
                up = np.array([0, 0, 1.0]) + 0.6 * out_dir
                up -= d * (up @ d)
                up /= np.linalg.norm(up)
                fw = np.cross(d, up)
                if fw[1] > 0:  # pattern +x goes to the front of the arm (-Y)
                    fw = -fw
                ang = float(w.get("front", 1)) * (x - cx) / R
                out[i] = c + R * (np.cos(ang) * up + np.sin(ang) * fw)
            X[sel] = out
        elif to == "neck":
            nb, hd = body.J["neck"], body.J["head"]
            d = (hd - nb) / np.linalg.norm(hd - nb)
            P = pcs[nm]["P"]
            e = uv[M["points"][f"{nm}:{w.get('edge', 'bottomMid')}"]]
            width = P[:, 0].max() - P[:, 0].min()
            r_neck = body.m["mm"]["neck"] / 1000 / (2 * np.pi)
            R = max(width / (2 * np.pi), r_neck + gap)
            back = np.array([0, 1.0, 0]) - d * d[1]
            back /= np.linalg.norm(back)
            side = np.cross(d, back)
            if side[0] < 0:
                side = -side
            above = float(w.get("above", 0.0))
            fall = math.radians(float(w.get("fall", 0.0)))
            out = np.zeros((len(U), 3))
            for i, (x, y) in enumerate(U):
                ang = (x - e[0]) / R
                dy = y - e[1]
                radial = np.cos(ang) * back + np.sin(ang) * side
                if fall:
                    r = R + 0.004 + dy * math.cos(fall)
                    hgt = above - dy * math.sin(fall)
                else:
                    r, hgt = R, above + dy
                out[i] = nb + d * (0.005 + hgt) + r * radial
            X[sel] = out
        elif to == "flat":  # laid flat at a height (a tablecloth, a blanket): pattern x, y -> world x, y
            o = np.asarray(w.get("at", [0, 0, 1.0]), float)
            X[sel] = np.c_[U[:, 0] + o[0], U[:, 1] + o[1], np.full(len(U), o[2])]
        else:
            raise ValueError(f"piece {nm}: unknown wrap {to!r} (torso, arm.L, arm.R, neck, flat)")
    return body.push_out(X, gap)


def _snap(X: np.ndarray, B: dict, M: dict, sigma: float = 0.08) -> np.ndarray:
    """Each piece that isn't wrapped on the torso is moved toward the pieces it's sewn to (in order: sleeves onto the
    armholes, cuffs onto the sleeves, a stand onto the neckline, a collar onto the stand): the seam's gaps as a smooth
    displacement over the piece (Gaussian weights in pattern coordinates), full at the seam, fading away from it."""
    X = X.copy()
    names = M["names"]
    done = {k for k, nm in enumerate(names) if B["pieces"][nm]["wrap"].get("to", "torso") in ("torso", "flat")}
    pid, uv = M["piece"], M["uv"]
    sew = M["sew"]
    for _ in range(len(names)):
        progress = False
        for k, nm in enumerate(names):
            if k in done:
                continue
            a, b = pid[sew[:, 0]], pid[sew[:, 1]]
            m1 = (a == k) & np.isin(b, list(done))
            m2 = (b == k) & np.isin(a, list(done))
            own = np.r_[sew[m1, 0], sew[m2, 1]]
            oth = np.r_[sew[m1, 1], sew[m2, 0]]
            if not len(own):
                continue
            d = X[oth] - X[own]
            sel = np.where(pid == k)[0]
            D2 = np.sum((uv[sel][:, None] - uv[own][None]) ** 2, -1)
            W = np.exp(-D2 / (2 * sigma ** 2))
            disp = (W @ d) / (W.sum(1, keepdims=True) + math.exp(-2.0))
            X[sel] += disp
            done.add(k)
            progress = True
        if not progress:
            break
    return X


# ---------------------------------------------------------------- simulation


def _cache_dir() -> Path:
    from . import store
    d = store.HOME / "_cache" / "cloth"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build(g: dict, body_src: dict, name: str = "garment", log=print, frames: int | None = None,
          render: dict | None = None, out_dir: Path | None = None) -> dict:
    """Draft, mesh, place and simulate one garment on one body. Returns {"V" settled verts, "F", "uv", ...,
    "fit", "sizing"}; results cached by content."""
    body = Body(body_src)
    meas = body.m["mm"]
    Bp = pieces(g, meas)
    h = float(g.get("resolution", 0.02))
    M = mesh(Bp, h)
    X0 = place(Bp, M, body)
    fab = fabric(g)
    state = g.get("state", "worn")
    key = hashlib.sha1(json.dumps([VERSION, g, body_src.get("key"), frames, hashlib.sha1(SCRIPT.read_bytes())
                                   .hexdigest()], sort_keys=True, default=str).encode()).hexdigest()[:16]
    cache = _cache_dir() / f"{key}.npz"
    stiff = np.zeros(len(M["uv"]))
    for nm in Bp["interfaced"]:
        stiff[M["piece"] == M["names"].index(nm)] = 1.0
    res = {"pieces": Bp, "mesh": M, "X0": X0, "body": body, "fabric": fab, "key": key}
    if cache.exists() and not render:
        d = np.load(cache)
        res["V"] = d["V"]
        res["log"] = str(d["log"])
    else:
        job_dir = out_dir or (_cache_dir() / f"job_{key}")
        job_dir.mkdir(parents=True, exist_ok=True)
        np.savez(job_dir / "in.npz", X=X0, uv=M["uv"], F=M["F"], sew=M["sew"], stitch=M["stitch"], stiff=stiff,
                 piece=M["piece"], bodyV=body.V, bodyT=body.T, pins=np.zeros(0, np.int64))
        cfg = {"fabric": fab, "frames": int(frames or g.get("frames", 90)), "state": state, "name": name,
               "color": g.get("color", "#5b7fa6"), "render": render, "out": str(job_dir / "out.npz"),
               "self_collision": bool(g.get("self_collision", True)), "trace": g.get("_trace", [])}
        if isinstance(state, dict) and "hang" in state:
            cfg["pins"] = [M["points"].get(p, M["marks"].get(p)) for p in state["hang"].get("pins", [])]
            cfg["hook"] = state["hang"].get("hook")
        (job_dir / "job.json").write_text(json.dumps(cfg))
        from . import resources, render as rmod
        t = time.time()
        with resources.heavy(f"cloth {name}", log=log):
            r = subprocess.run([rmod.BLENDER, "-b", "--factory-startup", "--python", str(SCRIPT), "--",
                                str(job_dir / "job.json")], capture_output=True, text=True, timeout=3600)
        if r.returncode != 0 or not (job_dir / "out.npz").exists():
            raise RuntimeError(f"cloth sim failed:\n{(r.stdout + r.stderr)[-3000:]}")
        d = np.load(job_dir / "out.npz")
        res["V"] = d["V"]
        res["log"] = "\n".join(ln for ln in r.stdout.splitlines() if ln.startswith("cloth:"))
        log(f"cloth {name}: simulated in {time.time() - t:.0f} s")
        np.savez_compressed(cache, V=d["V"], log=res["log"])
    res["fit"] = fit(res)
    res["sizing"] = sizing(res)
    # the verdict reads both: a pattern smaller than the body (negative ease) can't show as a small garment in the
    # sim (the body holds it out), it shows as cloth stretched past its limit there
    tight = [r for r, v in res["sizing"]["rows"].items() if v["ease_mm"] < 0]
    strained = [r for r, v in res["fit"]["regions"].items() if (v.get("strain_p95") or 0) > res["fabric"]["limit"]]
    if tight:
        res["fit"]["verdict"] = "TOO SMALL: negative ease at " + ", ".join(
            f"{r} {res['sizing']['rows'][r]['ease_mm']:+.0f} mm" for r in tight) + (
            f"; strained at {', '.join(strained)}" if strained else "")
    elif strained:
        res["fit"]["verdict"] = "STRAINED at " + ", ".join(strained)
    return res


# ---------------------------------------------------------------- feedback


def edge_strain(V: np.ndarray, uv: np.ndarray, F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per triangle the largest principal stretch - 1 against the flat pattern (Green strain's singular values), and
    per vertex the max of its triangles."""
    a, b, c = F[:, 0], F[:, 1], F[:, 2]
    Dm = np.stack([uv[b] - uv[a], uv[c] - uv[a]], axis=2)  # (m, 2, 2)
    Ds = np.stack([V[b] - V[a], V[c] - V[a]], axis=2)  # (m, 3, 2)
    det = np.linalg.det(Dm)
    ok = np.abs(det) > 1e-12
    Fd = np.zeros((len(F), 3, 2))
    Fd[ok] = Ds[ok] @ np.linalg.inv(Dm[ok])
    s = np.linalg.svd(Fd, compute_uv=False)
    tri = s[:, 0] - 1.0
    tri[~ok] = 0
    vert = np.zeros(len(V))
    np.maximum.at(vert, F.ravel(), np.repeat(tri, 3))
    return tri, vert


REGIONS = ("neck", "chest", "waist", "hips", "seat", "biceps", "wrist")


def fit(res: dict) -> dict:
    """Strain past the fabric's limit, ease against the body at the tailor's girths (negative = too tight), and how
    far the cloth floats off the body. Per region numbers + per vertex arrays for the map."""
    V, M, body, fab = res["V"], res["mesh"], res["body"], res["fabric"]
    tri, vert = edge_strain(V, M["uv"], M["F"])
    limit = fab["limit"]
    from scipy.spatial import cKDTree as KD
    dist, _ = KD(body.V).query(V)
    out = {"strain_limit": limit, "strain_p95": float(np.percentile(tri, 95)), "strain_max": float(tri.max()),
           "over_limit_share": float(np.mean(tri > limit)), "regions": {}}
    tors = [k for k, nm in enumerate(M["names"]) if res["pieces"]["pieces"][nm]["wrap"].get("to", "torso") == "torso"]
    garment_T = M["F"][np.isin(M["piece"][M["F"][:, 0]], tors)]  # girths round the body pieces (not the sleeves)
    Z = np.array([0, 0, 1.0])
    for reg in ("chest", "waist", "hips", "seat"):
        zk = f"{reg}_z"
        if zk not in body.at:
            continue
        z = body.at[zk]
        loops = tailor.slice_loops(V, garment_T, [0, 0, z], Z)
        if not loops:
            continue
        P = np.concatenate(loops)
        gg = tailor.girth(P, Z) * 1000
        bb = body.m["mm"][reg]
        near = np.abs(V[:, 2] - z) < 0.02
        out["regions"][reg] = {"body_mm": bb, "garment_mm": round(gg, 1), "ease_mm": round(gg - bb, 1),
                               "ease": round((gg - bb) / bb, 3),
                               "strain_p95": float(np.percentile(vert[near], 95)) if near.any() else None}
    out["vertex_strain"] = vert
    out["vertex_dist"] = dist
    out["float_share"] = float(np.mean(dist > 0.05))
    out["verdict"] = "STRAINED" if out["over_limit_share"] > 0.05 else "fits"
    return out


def sizing(res: dict) -> dict:
    """The finished garment's measurements from the flat pattern (seam to seam, before the sim) vs the body's."""
    B, body = res["pieces"], res["body"]
    d = B.get("draft") or {}
    opts = d.get("options", {})
    rows = {}
    pcs = B["pieces"]
    torso = [nm for nm in pcs if pcs[nm]["wrap"].get("to") == "torso"]
    hps_z = body.at["hps.L"][2]
    for reg in ("chest", "waist", "hips", "seat"):
        zk = f"{reg}_z"
        if zk not in body.at or not torso:
            continue
        # each piece's width at the draft's own girth line where it has one, else at the body's height, less the
        # closure's overlap past centre front
        w = 0.0
        for nm in torso:
            L = pcs[nm]["lines"].get(reg)
            y = float(np.mean(L[:, 1])) if L is not None else body.at[zk] - hps_z  # the draft's line, or the body's
            # height (pattern y, hps at 0); the chest at the armhole's bottom (where a chest line ends: the outline
            # is still curving in at the line's own height)
            if reg == "chest" and "armhole" in pcs[nm]["names"]:
                y = float(pcs[nm]["P"][pcs[nm]["names"]["armhole"], 1]) - 0.002
            w += _piece_width_at(pcs[nm]["P"], y)
        overlap = sum(min(abs(pcs[nm]["P"][:, 0].min()), abs(pcs[nm]["P"][:, 0].max())) for nm in torso
                      if abs(pcs[nm]["P"][:, 0].min() + pcs[nm]["P"][:, 0].max()) > 0.05)
        g = (w - overlap) * 1000
        bb = body.m["mm"][reg]
        rows[reg] = {"body_mm": bb, "garment_mm": round(g, 1), "ease_mm": round(g - bb, 1),
                     "ease": round((g - bb) / bb, 3)}
    return {"options": opts, "rows": rows}


# ---------------------------------------------------------------- views


def strain_colors(strain: np.ndarray, limit: float) -> np.ndarray:
    """Linear RGB per vertex: slack blue -> fine green -> at the limit yellow -> 2x the limit red."""
    t = np.clip(strain / max(limit, 1e-6), -1, 2)
    stops = np.array([[-1, 0.05, 0.15, 0.6], [0, 0.1, 0.5, 0.12], [1, 0.9, 0.75, 0.02], [2, 0.8, 0.02, 0.02]])
    out = np.zeros((len(t), 3))
    for ch in range(3):
        out[:, ch] = np.interp(t, stops[:, 0], stops[:, ch + 1])
    return out


def render(objects: list, prefix: str, views=("front", "side", "back"), resolution: int = 700, box=None,
           aspect: float = 0.62) -> list:
    """objects: [{"name", "V", "F", "color" | "C" (linear RGB per vertex), "thickness"}] -> PNG paths."""
    from . import render as rmod
    prefix = str(prefix)
    d = Path(prefix).parent
    d.mkdir(parents=True, exist_ok=True)
    data, objs = {}, []
    for o in objects:
        data[o["name"] + "_V"] = np.asarray(o["V"], np.float64)
        data[o["name"] + "_F"] = np.asarray(o["F"])
        if o.get("C") is not None:
            data[o["name"] + "_C"] = np.asarray(o["C"], np.float32)
        objs.append({k: v for k, v in o.items() if k in ("name", "color", "thickness")})
    tag = Path(prefix).name
    np.savez(d / f"_{tag}_render.npz", **data)
    job = {"mode": "render", "data": f"_{tag}_render.npz", "objects": objs, "out_prefix": prefix,
           "views": list(views), "resolution": resolution, "aspect": aspect,
           "box": [list(map(float, box[0])), list(map(float, box[1]))] if box is not None else None}
    jp = d / f"_{tag}_render.json"
    jp.write_text(json.dumps(job))
    r = subprocess.run([rmod.BLENDER, "-b", "--factory-startup", "--python", str(SCRIPT), "--", str(jp)],
                       capture_output=True, text=True, timeout=900)
    (d / f"_{tag}_render.npz").unlink(missing_ok=True)
    jp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"cloth render failed:\n{(r.stdout + r.stderr)[-2000:]}")
    return [f"{prefix}_{v if isinstance(v, str) else v['name']}.png" for v in views]
