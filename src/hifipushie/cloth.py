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
SIM_NOISE = 0.06  # the strain a well-fitting garment shows in the sim (see build's verdict)
VERSION = 1  # bump with any change to the mesh, placement or sim job: results are cached by it

# Blender cloth settings per fabric (mass per vertex at ~2 cm triangles, spring stiffnesses in Blender's units),
# the stretch past which the fabric is strained (fit check), interfaced pieces' bending multiplier (`stiff`).
FABRICS = {
    "shirting": {"mass": 0.15, "tension": 60, "compression": 15, "shear": 15, "bending": 0.1, "air": 1.0,
                 "limit": 0.03, "thickness": 0.0004, "stiff": 40},
    "jersey": {"mass": 0.2, "tension": 5, "compression": 5, "shear": 3, "bending": 0.02, "air": 1.0,
               "limit": 0.25, "thickness": 0.0007, "stiff": 30},
    "wool_coating": {"mass": 0.5, "tension": 80, "compression": 40, "shear": 30, "bending": 2.0, "air": 1.0,
                     "limit": 0.03, "thickness": 0.002, "stiff": 20},
    "denim": {"mass": 0.5, "tension": 40, "compression": 40, "shear": 30, "bending": 2.0, "air": 1.0,
              "limit": 0.02, "thickness": 0.001, "stiff": 10},
    "linen": {"mass": 0.25, "tension": 25, "compression": 25, "shear": 10, "bending": 0.3, "air": 1.0,
              "limit": 0.03, "thickness": 0.0005, "stiff": 20},
}

H_REF = 0.02  # the triangle size the presets' per-vertex masses are for


ALTERATIONS = {
    # a belly: the front from hps to the seat over the surface is longer than the back (drafts make them equal);
    # the difference past 25 mm (a broad chest alone reads ~20) is spread into the front at the waist, hinged at the side seam (so the side seam
    # keeps its length and the front hem drops back level instead of riding up over the belly)
    "large_abdomen": lambda m: max(0.0, (m.get("hpsToSeatFront", 0) - m.get("hpsToSeatBack", 0) - 25.0) / 1000.0),
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
        # standard fit alterations, from the body's numbers (pattern "alterations": "auto" (default) | [names] |
        # "none"): each is a general pattern op whose amount a rule reads off the tape
        want = pat.get("alterations", "auto")
        applied = {}
        for nm, op in (tbl.get("fit_alterations") or {}).items():
            if want == "none" or (isinstance(want, list) and nm not in want):
                continue
            amount = ALTERATIONS[nm](meas_mm)
            if amount <= 0:
                continue
            out = pattern.apply(out, [dict(op, amount=amount)])
            applied[nm] = round(amount * 1000, 1)
        draft_info["alterations"] = applied
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
    interfaced = interfaced + [e for e in g.get("interfaced", []) if e not in interfaced]
    keep = set(out)
    side_ok = lambda s: all(e.split(":")[0] in keep for e in ([s] if isinstance(s, str) else s))
    seams = [s for s in seams if side_ok(s[0]) and side_ok(s[1])]
    stitches = [s for s in stitches if side_ok(s[0]) and side_ok(s[1])]
    return {"pieces": out, "seams": seams, "stitches": stitches, "interfaced": [p for p in interfaced
                                                                                    if (p if isinstance(p, str) else p["piece"]) in keep],
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
    # one triangle size for every piece (per piece sizes are supported through `ph`, seams sampled at their finest
    # piece's). Finer collars and cuffs (7 mm) crumpled MORE: Blender's bending springs are per edge, so the same
    # settings on a finer mesh are a softer cloth
    ph = {nm: h for nm in names}
    sew_keys = []
    for si, (A, Bs) in enumerate(B["seams"]):
        sides = []
        for side in (A, Bs):
            chain = [side] if isinstance(side, str) else list(side)
            arcs = [_edge(pcs, e) for e in chain]
            lens = np.array([pattern.length(pcs[nm]["P"][ix]) for nm, ix in arcs])
            sides.append((arcs, np.r_[0, np.cumsum(lens)] / lens.sum()))
        hs = min(ph[nm] for s in sides for nm, _ in s[0])
        n = max(2, int(math.ceil(max(sum(pattern.length(pcs[nm]["P"][ix]) for nm, ix in s[0]) for s in sides) / hs)))
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
        h = ph[nm]
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
        for k, v in list(mk.items()):  # a mark just off the outline (a button on a spread slash) comes back in
            if len(v) == 2 and not _inside(ring, v[None])[0] and _seg_dist(v[None], ring)[0] < 2 * h:
                c = ring.mean(0)
                for _ in range(20):
                    v = v + 0.1 * h * (c - v) / max(np.linalg.norm(c - v), 1e-9)
                    if _inside(ring, v[None])[0] and _seg_dist(v[None], ring)[0] > 0.4 * h:
                        break
                mk[k] = v
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
        sliver = allb & (ar < 0.02 * h * h)
        kept = np.zeros(len(X), bool)
        kept[tri[~sliver].ravel()] = True
        sliver &= ~np.any(~kept[tri], axis=1)  # never orphan an outline vertex (a named point sits on it)
        tri = tri[~sliver]
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
    uv_n, pid_n, border_n = np.asarray(uv)[used], np.asarray(piece_of)[used], np.asarray(border)[used]
    # named outline points: the nearest kept outline vertex of their piece (Delaunay drops coincident points)
    pts_n = {}
    for k in points:
        nm, pt = k.split(":", 1)
        pi = names.index(nm)
        cand = np.where((pid_n == pi) & border_n)[0]
        q = pcs[nm]["P"][pcs[nm]["names"][pt]]
        pts_n[k] = int(cand[np.argmin(np.linalg.norm(uv_n[cand] - q, axis=1))])
    return {"uv": uv_n, "piece": pid_n, "names": names, "F": remap[F],
            "sew": sew, "sew_seam": sew_seam, "stitch": stitch,
            "marks": {k: int(remap[v]) for k, v in marks.items() if used[v]},
            "points": pts_n, "border": border_n}


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

    def arm_axis(self, side: str):
        """Along shoulder -> elbow -> wrist (t in m): each section's centre minus the joints' line (offsets, smoothed)
        and its largest radius. Near the shoulder the section runs into the torso: the first clean one is used."""
        key = ("arm", side)
        if key in self._hull:
            return self._hull[key]
        sh, el, wr = (self.J[f"{j}.{side}"] for j in ("shoulder", "elbow", "wrist"))
        s0, s1 = np.linalg.norm(el - sh), np.linalg.norm(wr - el)
        ts = np.arange(-0.05, s0 + s1 + 0.12, 0.02)  # on past the wrist over the hand (a cuff reaches it)
        offs, rm = np.zeros((len(ts), 3)), np.zeros(len(ts))
        ok = np.zeros(len(ts), bool)
        for i, t in enumerate(ts):
            if t <= s0:
                d, p = (el - sh) / s0, sh + (el - sh) * t / s0
            else:
                d, p = (wr - el) / s1, el + (wr - el) * (t - s0) / s1
            L = tailor.section(self.V, self.T, p, d, p) if t > 0.06 else None
            # a section that runs into the torso (a heavy arm against its side) isn't the arm's: skipped
            if L is None or not tailor._encloses(L, p, d) or np.max(np.linalg.norm(L - p, axis=1)) > 0.10:
                continue
            c = L.mean(0)
            if np.linalg.norm(c - p) > 0.03:
                continue
            offs[i] = c - p
            rm[i] = np.max(np.linalg.norm(L - c, axis=1))
            ok[i] = True
        if ok.any():
            offs = np.array([np.interp(ts, ts[ok], offs[ok, k]) for k in range(3)]).T
            rm = np.interp(ts, ts[ok], rm[ok])
            kern = np.exp(-0.5 * (np.arange(-3, 4) / 1.5) ** 2)
            kern /= kern.sum()
            offs = np.array([np.convolve(np.pad(offs[:, k], 3, mode="edge"), kern, "valid") for k in range(3)]).T
        self._hull[key] = (ts, offs, rm)
        return self._hull[key]

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
            g = np.broadcast_to(np.asarray(gap, float), (len(X),))  # per vertex (a closed cuff hugs the wrist)
            bad = s < g
            if not bad.any():
                break
            X[bad] += (g[bad] - s[bad])[:, None] * n[bad]
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
                # out past the shoulder point over the arm's root: clipped at it, the pieces round the armhole
                # started inside the deltoid
                pts = [L[np.abs(L[:, 0]) < xs + 0.05, :2] for L in loops if np.any(np.abs(L[:, 0]) < 0.06)]
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


def _densify(H: np.ndarray, step: float) -> np.ndarray:
    """A closed polygon with extra vertices along its edges, at most `step` apart (its corners kept)."""
    out = []
    for a, b in zip(H, np.roll(H, -1, axis=0)):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        out.append(a + (b - a) * (np.arange(n) / n)[:, None])
    return np.concatenate(out)


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


LAYER = 0.004  # how far an overlapping layer starts outside the one under it
CLEAR = 0.008  # the least start clearance from the body (Blender: cloth 3 mm + body 4 mm collision distances)


def _closed_girth(M: dict, nm: str) -> float:
    """A piece stitched to itself (a cuff's button and buttonhole): its girth when closed, the distance across it
    between the stitched vertices in the flat (0 if it doesn't close on itself)."""
    return _closure(M, nm)[0]


def _closure(M: dict, nm: str) -> tuple[float, float]:
    """(closed girth, x of the stitched point nearer the piece's low x) of a piece stitched to itself."""
    k = M["names"].index(nm)
    best, xlo = 0.0, 0.0
    for a, b in np.asarray(M["stitch"]).reshape(-1, 2):
        if M["piece"][a] == k and M["piece"][b] == k:
            d = float(abs(M["uv"][a, 0] - M["uv"][b, 0]))
            if d > best:
                best, xlo = d, float(min(M["uv"][a, 0], M["uv"][b, 0]))
    return best, xlo


def place(B: dict, M: dict, body: Body, gap: float = 0.012, _blouse: dict | None = None) -> np.ndarray:
    """Start positions: each piece wrapped round the body part its `wrap` names (torso front/back, arm.L/R, neck),
    lengths along the pattern kept along the wrap (the sim's rest shape is the flat pattern anyway).
    _blouse {piece: (t of its hem, excess)}: a sleeve whose cuff had to sit further up the arm than its hem is
    placed with the excess folded in under itself (a fold is isometric), so the hem meets the cuff; set by a first
    pass. (Left as a gap, sewing dragged the sleeve, and with it the shirt, 28 mm up the body.)"""
    shifts = {}
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
    dzs = {}
    for nm in torso:
        w = pcs[nm]["wrap"]
        if "align" in w:  # [my point, other piece, its point]: hang this piece so the two are level (a coat's
            mine, other, op = w["align"]  # skirt from the bodice's waist)
            dzs[nm] = float(uv[M["points"][f"{other}:{op}"]][1] - uv[M["points"][f"{nm}:{mine}"]][1])
    if torso:
        ylo = min(pcs[nm]["P"][:, 1].min() + dzs.get(nm, 0) for nm in torso)
        zs = np.arange(max(hps[2] + ylo, 0.05), hps[2] - 0.01, 0.02)
        pts = [h for z in zs if (h := body.hull(z)) is not None]
        Hu = np.concatenate(pts)
        Hu = Hu[ConvexHull(Hu).vertices]
        P0 = pattern.length(Hu, closed=True)
        # the girth where the pieces must meet round the chest (a coat's flared skirt would make it a tent)
        ys = np.arange(max(ylo, -0.45), -0.25, 0.01)
        Wmax = max(sum(_piece_width_at(pcs[nm]["P"], y - dzs.get(nm, 0)) for nm in torso) for y in ys)
        # the fronts overlap at the closure: the girth is the total width less the overlap past centre front
        over = sum(min(abs(pcs[nm]["P"][:, 0].min()), abs(pcs[nm]["P"][:, 0].max())) for nm in torso
                   if pcs[nm]["wrap"].get("side", "front") == "front"
                   and abs(pcs[nm]["P"][:, 0].min() + pcs[nm]["P"][:, 0].max()) > 0.05)  # one-sided pieces
        m = float(np.clip((Wmax - over - P0) / (2 * np.pi), gap, 0.15))
        # densified: each piece starts at the hull's point nearest its centre line, and a convex hull's front is
        # one long edge between the pecs (its nearest vertex was 69 mm off centre: the bodice started turned round
        # the body and sewing dragged it back ~10 cm, lifting the armholes and the sleeves with them)
        C = _densify(_offset_hull(Hu, m), 0.002)
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
            X[sel] = np.c_[q, hps[2] + U[:, 1] + dzs.get(nm, 0.0)]
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
            elif "align" in w:  # level with another placed piece's point (a two-piece sleeve's under sleeve)
                mine, other, op = w["align"]
                t_anchor = float(placed[other]["t"](uv[M["points"][f"{other}:{op}"]]))
                y_anchor = float(uv[M["points"][f"{nm}:{mine}"]][1])
                t_of = lambda Q, ta=t_anchor, ya=y_anchor: ta + (ya - Q[..., 1])
            else:  # the top (sleeve cap) at t0 along shoulder -> elbow -> wrist, pattern -y down the arm
                ytop = P[:, 1].max()
                # the cap's top at the shoulder point (the tape's shoulder-to-wrist starts there), not at the joint:
                # from the joint the whole sleeve sat ~4 cm down the arm and its cuff closed round the hand
                spt = np.asarray(body.at["shoulder.L"], float) * ([1, 1, 1] if side == "L" else [-1, 1, 1])
                t0 = float(w.get("t0", min(-0.02, float((spt - sh) @ (el - sh)) / seg[0])))
                t_of = lambda Q, ytop=ytop, t0=t0: t0 + (ytop - Q[..., 1])
            placed[nm] = {"t": t_of}
            t = t_of(U)
            # a cylinder round the arm at the widest row's girth (isometric: the placed piece keeps its pattern's
            # lengths; a tapered sleeve's underarm edges meet at the widest row and the seam pulls the rest shut)
            # (pieces sharing the arm, e.g. a two-piece sleeve, share one cylinder: their widths side by side)
            def widest(Pq):
                yr = np.linspace(Pq[:, 1].min() + 1e-4, Pq[:, 1].max() - 1e-4, 60)
                return max(_piece_width_at(Pq, y) for y in yr)
            if "follow" in w:
                girth = widest(P)
            else:
                girth = sum(widest(pcs[o]["P"]) for o in names if pcs[o]["wrap"].get("to") == to
                            and "follow" not in pcs[o]["wrap"])
            R = max(girth / (2 * np.pi), 0.5 * body.m["mm"]["wrist"] / 1000 / np.pi + gap) + float(w.get("out", 0))
            # round the arm's own sections' centres, not the joints' line (a heavy arm's flesh hangs off it, and
            # pushing the start out of the body bakes stretch into the rest shape)
            ts, offs, rmax = body.arm_axis(side)
            # where the arm is fatter than the sleeve's cylinder (a heavy deltoid, the hand under a cuff) the whole
            # piece stands further out on one cylinder (still isometric: the underarm seam opens and the sewing
            # closes it, shrinking the sleeve onto the arm); pushing rows out of the body stretched the rest shape
            tt = t_of(U)
            # round the arm's own bent axis (shoulder -> elbow -> wrist + each section's centre), on one radius that
            # clears the arm over the piece's length. (Tried: a straight cylinder clear of the 45 deg elbow crushed
            # the sleeve; a filleted elbow with generators reparameterised put 30% shear into the rest shape: a
            # torus isn't developable. The sharp bend distorts least where it matters.)
            on = (ts >= tt.min() - 0.02) & (ts <= tt.max() + 0.02) & (ts > 0.06)
            Rp = max(R, float(rmax[on].max()) + gap if on.any() else R)
            cx = 0.5 * (P[:, 0].max() + P[:, 0].min())
            # a piece buttoned to itself (a cuff) starts closed: round its closed girth (the stitched marks' distance
            # along it) on a slight spiral, the overlap one layer outside, arc length kept along it. (Laid open round
            # the hand, 108 mm apart, the stitch snapped a stiff cuff shut and crumpled it.)
            closed = _closed_girth(M, nm)
            if closed:
                # r grows by LAYER over the closed girth (dr/dx = kk) and the stitched points, `closed` apart along
                # the piece, land one turn apart: ln(r_hi / r_lo) / kk = 2 pi
                kk = LAYER / closed
                x_lo = _closure(M, nm)[1]
                r_lo = LAYER / math.expm1(2 * np.pi * kk)
                x0 = P[:, 0].min()
                Rc = r_lo - kk * (x_lo - x0)  # the radius at the piece's low end
                th = np.log((Rc + kk * (U[:, 0] - x0)) / Rc) / kk
                th -= float(np.log((Rc + kk * (cx - x0)) / Rc) / kk)
                rr = Rc + kk * (U[:, 0] - x0)
                # it can't sit over the hand's base (wider than it: the push out of the body opened it 13 mm and
                # the cuff stretched 30-70% there): back up the arm to where it fits; the sleeve blouses into it
                past = ts > seg[0] + 0.5 * seg[1]
                if past.any():
                    i0 = int(np.argmin(np.where(past, rmax, np.inf)))
                    wide = np.where((np.arange(len(ts)) > i0) & (rmax >= Rc - 0.002))[0]
                    t_lim = float(ts[wide[0]]) - 0.005 if len(wide) else float(ts[-1])
                    if t.max() > t_lim:
                        if "follow" in w and t.max() - t_lim > 0.01:
                            shifts[w["follow"][0]] = (t_anchor, float(t.max() - t_lim))
                        t = t - (t.max() - t_lim)
            rad = np.full(len(U), Rp)
            if _blouse and nm in _blouse:  # the excess turned in under the sleeve round a U of radius LAYER / 2
                t_h, ex = _blouse[nm]
                rho = LAYER / 2
                t_f = t_h - ex / 2 - np.pi * rho / 2
                sf = t - t_f
                bend = (sf > 0) & (sf < np.pi * rho)
                back = sf >= np.pi * rho
                t = t.copy()
                t[bend] = t_f + rho * np.sin(sf[bend] / rho)
                rad[bend] = Rp - rho * (1 - np.cos(sf[bend] / rho))
                t[back] = t_f - (sf[back] - np.pi * rho)
                rad[back] = Rp - 2 * rho
            out = np.zeros((len(U), 3))
            for i, (x, yv) in enumerate(U):
                ti = float(t[i])
                if ti <= seg[0]:
                    d = (el - sh) / seg[0]
                    c = sh + d * ti
                else:
                    d = (wr - el) / seg[1]
                    c = el + d * (ti - seg[0])
                c = c + np.array([np.interp(ti, ts, offs[:, k]) for k in range(3)])
                up = np.array([0, 0, 1.0]) + 0.6 * out_dir
                up -= d * (up @ d)
                up /= np.linalg.norm(up)
                fw = np.cross(d, up)
                if fw[1] > 0:  # pattern +x goes to the front of the arm (-Y)
                    fw = -fw
                if closed:
                    ang = float(w.get("front", 1)) * th[i] + math.radians(float(w.get("turn", 0)))
                    out[i] = c + rr[i] * (np.cos(ang) * up + np.sin(ang) * fw)
                    continue
                ang = float(w.get("front", 1)) * (x - cx) / Rp + math.radians(float(w.get("turn", 0)))
                out[i] = c + rad[i] * (np.cos(ang) * up + np.sin(ang) * fw)
            X[sel] = out
        elif to == "neck":
            nb, hd = body.J["neck"], body.J["head"]
            d = (hd - nb) / np.linalg.norm(hd - nb)
            P = pcs[nm]["P"]
            e = uv[M["points"][f"{nm}:{w.get('edge', 'bottomMid')}"]]
            width = P[:, 0].max() - P[:, 0].min()
            r_neck = body.m["mm"]["neck"] / 1000 / (2 * np.pi)
            R = max(width / (2 * np.pi), r_neck + gap)
            # stand clear of the neck over the piece's own heights (the neck isn't round: a cylinder at its girth
            # cut into the trapezius and the start was pushed out, stretching the rest shape)
            above = float(w.get("above", 0.0))
            for hgt in np.linspace(0.005 + above + (P[:, 1].min() - e[1]), 0.005 + above + (P[:, 1].max() - e[1]), 6):
                o = nb + d * hgt
                L = tailor.section(body.V, body.T, o, d, o)
                if L is not None and tailor._encloses(L, o, d):
                    rr = np.linalg.norm((L - o) - np.outer((L - o) @ d, d), axis=1).max()
                    if rr < 0.15:
                        R = max(R, rr + gap)
            back = np.array([0, 1.0, 0]) - d * d[1]
            back /= np.linalg.norm(back)
            side = np.cross(d, back)
            if side[0] < 0:
                side = -side
            above = float(w.get("above", 0.0))
            # "fold": [rise, layer] a turned-down collar: up `rise` from its sewn edge, then folded down outside
            # itself `layer` further out (placed folded, so the rest shape holds the fold; arc length kept per row)
            fold = w.get("fold")
            out = np.zeros((len(U), 3))
            for i, (x, y) in enumerate(U):
                dy = y - e[1]
                r, hgt = R, above + dy
                if fold and dy > fold[0]:
                    r, hgt = R + fold[1], above + fold[0] - (dy - fold[0])
                ang = (x - e[0]) / r
                radial = np.cos(ang) * back + np.sin(ang) * side
                out[i] = nb + d * (0.005 + hgt) + r * radial
            X[sel] = out
        elif to == "flat":  # laid flat at a height (a tablecloth, a blanket): pattern x, y -> world x, y
            o = np.asarray(w.get("at", [0, 0, 1.0]), float)
            X[sel] = np.c_[U[:, 0] + o[0], U[:, 1] + o[1], np.full(len(U), o[2])]
        else:
            raise ValueError(f"piece {nm}: unknown wrap {to!r} (torso, arm.L, arm.R, neck, flat)")
    gaps = np.full(len(X), gap)
    for k, nm in enumerate(names):
        if B["pieces"][nm]["wrap"].get("to", "").startswith("arm.") and _closed_girth(M, nm):
            gaps[pid == k] = CLEAR  # outside the collision zone (cloth + body distance): inside it, the impulses launched the torso 15 cm up
    if shifts and _blouse is None:
        return place(B, M, body, gap, _blouse=shifts)
    Xp = body.push_out(X, gaps)
    mv = np.linalg.norm(Xp - X, axis=1)
    # what pushing the start out of the body moved: it becomes stretch in the rest shape (rest = placed)
    B["push"] = {nm: round(float(mv[pid == k].max() * 1000), 1) for k, nm in enumerate(names) if mv[pid == k].max() > 0.002}
    return Xp


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


def _assembly(Bp: dict, M: dict, body: Body) -> dict | None:
    """The sim's stage 0 (blender_cloth): the pieces wrapped on the torso are sewn first, everything else held where
    it was placed against the body (the sleeves, the collar), as a shirt is made."""
    wraps = {nm: Bp["pieces"][nm]["wrap"].get("to", "torso") for nm in M["names"]}
    torso = np.isin(M["piece"], [k for k, nm in enumerate(M["names"]) if wraps[nm] == "torso"])
    if torso.all() or not torso.any():
        return None
    # pieces that close round a limb (cuffs) are held while everything is sewn (stage 1), as a tailor holds the cuff
    # setting a sleeve: the cap's underarm starts ~8 cm down an A-posed arm, and closing it dragged one sleeve's cuff
    # up to the elbow (marginal: one side of a symmetric pair did, the other not)
    hold = [k for k, nm in enumerate(M["names"]) if wraps[nm].startswith("arm.") and _closed_girth(M, nm)]
    return {"fixed": np.where(~torso)[0].tolist(), "hold": np.where(np.isin(M["piece"], hold))[0].tolist()}


def interfacing(Bp: dict, M: dict) -> np.ndarray:
    """Per vertex 0..1: how interfaced (stiffer in bending, shear and stretch). An entry is a whole piece by name, or
    a band {"piece", "near": a line / point / mark of it, "within": m} (a cut-on placket: the strip along the centre
    front), feathered over its last third."""
    stiff = np.zeros(len(M["uv"]))
    for e in Bp["interfaced"]:
        nm = e if isinstance(e, str) else e["piece"]
        sel = M["piece"] == M["names"].index(nm)
        if isinstance(e, str):
            stiff[sel] = 1.0
            continue
        pc = Bp["pieces"][nm]
        ref = e["near"]
        if isinstance(ref, str) and ref not in (pc.get("lines") or {}):  # a point or mark
            L = np.asarray([pc["P"][pattern.index_of(pc, ref)] if ref in pc["names"] else pc["marks"][ref]], float)
        else:  # a line name or [point, point]
            L = np.asarray(pattern._line(pc, ref), float)
        Q = M["uv"][sel]
        if len(L) == 1:
            d = np.linalg.norm(Q - L[0], axis=1)
        else:
            a, b = L[:-1], L[1:]
            ab = b - a
            t = np.clip(np.einsum("qkd,kd->qk", Q[:, None] - a[None], ab) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
            d = np.linalg.norm(Q[:, None] - (a[None] + t[..., None] * ab[None]), axis=2).min(1)
        w = float(e.get("within", 0.02))
        stiff[sel] = np.maximum(stiff[sel], np.clip((w - d) / (w / 3), 0, 1))
    return stiff


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
    # Blender's cloth mass is per vertex: the presets are per vertex at 2 cm triangles, so a finer mesh keeps the
    # garment's weight (and so its stretch and drape under gravity) by scaling it with the area a vertex carries
    fab["mass"] = float(fab["mass"]) * (h / H_REF) ** 2
    # lighter vertices on the same springs ring twice as fast per halving of h: more substeps (quality 6 at 1 cm
    # crumpled one interfaced cuff of a symmetric pair into a ball, the other not: an instability)
    fab.setdefault("quality", int(round(6 * max(1.0, H_REF / h))))
    state = g.get("state", "worn")
    code = hashlib.sha1(b"".join(Path(__file__).with_name(f).read_bytes() for f in
                                 ("cloth.py", "blender_cloth.py", "pattern.py", "cloth_designs.json"))).hexdigest()
    # the sim's inputs themselves (start positions, pattern, seams): a draft or placement change reaches the key
    inputs = hashlib.sha1(X0.tobytes() + M["uv"].tobytes() + M["sew"].tobytes()).hexdigest()
    key = hashlib.sha1(json.dumps([VERSION, g, body_src.get("key"), frames, code, inputs], sort_keys=True,
                                  default=str).encode()).hexdigest()[:16]
    cache = _cache_dir() / f"{key}.npz"
    stiff = interfacing(Bp, M)
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
               "self_collision": bool(g.get("self_collision", True)), "trace": g.get("_trace", []),
               **{k: g[k] for k in ("sew_force", "sew_frames", "worn_frames", "settle_frames") if k in g}}
        if g.get("assemble", True):
            cfg["assemble"] = _assembly(Bp, M, body)
        if isinstance(state, dict) and "hang" in state:
            pins = [M["points"].get(p, M["marks"].get(p)) for p in state["hang"].get("pins", [])]
            if None in pins:
                raise KeyError(f"hang pins: no such point/mark in {state['hang'].get('pins')}")
            # a hanger loop holds a patch, not a vertex: every vertex within `radius` of a pin (start positions)
            rad = float(state["hang"].get("radius", 0.03))
            near = np.unique(np.concatenate([np.where(np.linalg.norm(X0 - X0[p], axis=1) < rad)[0] for p in pins]))
            cfg["pins"] = [int(i) for i in near]
            cfg["hook"] = state["hang"].get("hook")
            cfg["rack"] = state["hang"].get("rack")  # [[a, b, radius], ...] colliders (a coat rack's pole, arms)
            cfg["pin_spread"] = state["hang"].get("spread", 0.3)
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
        if out_dir is None and not os.environ.get("HIFIPUSHIE_CLOTH_KEEP"):  # the job's files (MBs) go
            import shutil
            shutil.rmtree(job_dir, ignore_errors=True)
    res["fit"] = fit(res)
    res["integrity"] = integrity(res["V"], M, Bp, X0)
    res["sizing"] = sizing(res)
    # the verdict reads both: a pattern smaller than the body (negative ease) can't show as a small garment in the
    # sim (the body holds it out), it shows as cloth stretched past its limit there
    tight = [r for r, v in res["sizing"]["rows"].items() if v["ease"] < -0.01]  # under the body by over 1%
    # mass-spring cloth stretches a few % under its own seams and gravity (a well-fitting shirt read 1-6% across
    # its front): strained = past the fabric's limit by more than that floor (SIM_NOISE)
    strained = [r for r, v in res["fit"]["regions"].items()
                if (v.get("strain_p95") or 0) > res["fabric"]["limit"] + SIM_NOISE]
    if tight:
        res["fit"]["verdict"] = "TOO SMALL: negative ease at " + ", ".join(
            f"{r} {res['sizing']['rows'][r]['ease_mm']:+.0f} mm" for r in tight) + (
            f"; strained at {', '.join(strained)}" if strained else "")
    elif strained:
        res["fit"]["verdict"] = "STRAINED at " + ", ".join(strained)
    ig = res["integrity"]
    if ig["corrupt_pieces"] or ig["twisted_seams"]:  # a tangled garment's fit means nothing: said first
        res["fit"]["verdict"] = ("CORRUPT: " + ", ".join(
            f"{p} ({ig['pieces'][p]['crumpled'] * 100:.0f}% crumpled, {ig['pieces'][p]['intersections']} crossings)"
            for p in ig["corrupt_pieces"]) + (f"; twisted seams {ig['twisted_seams']}" if ig["twisted_seams"] else "")
            + " | " + res["fit"]["verdict"])
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


def _seg_tri(P0, P1, A, B, C, eps=1e-9):
    """Segments P0-P1 against triangles ABC (row-wise): True where the segment crosses the triangle's interior
    (Moller-Trumbore with the segment's own length as the parameter range)."""
    d = P1 - P0
    e1, e2 = B - A, C - A
    h = np.cross(d, e2)
    a = np.sum(e1 * h, 1)
    ok = np.abs(a) > eps
    f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
    s = P0 - A
    u = f * np.sum(s * h, 1)
    q = np.cross(s, e1)
    v = f * np.sum(d * q, 1)
    t = f * np.sum(e2 * q, 1)
    m = 1e-3  # stay off shared edges and vertices
    return ok & (u > m) & (v > m) & (u + v < 1 - m) & (t > m) & (t < 1 - m)


def integrity(V: np.ndarray, M: dict, B: dict | None = None, X0: np.ndarray | None = None) -> dict:
    """Is the settled cloth still a garment? Per piece: self-intersections (an edge of the cloth crossing a triangle
    of it, the piece itself or any other: tangled or passed-through cloth), crumpled triangles (squashed under a
    third of their pattern area, or folded flat: a neighbour turned more than 160 deg), and per seam whether its two
    sides run the same way (a twisted seam: one side's order reversed). Numbers, so a corrupted garment never reads
    as settled."""
    F, uv = M["F"], M["uv"]
    pid = M["piece"][F[:, 0]]
    names = M["names"]
    # crumpled: area against the pattern's
    a3 = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    du1, du2 = uv[F[:, 1]] - uv[F[:, 0]], uv[F[:, 2]] - uv[F[:, 0]]
    a2 = 0.5 * np.abs(du1[:, 0] * du2[:, 1] - du1[:, 1] * du2[:, 0])
    if X0 is not None:  # against the start, which holds the made-in folds (across a collar's fold a triangle is thin)
        a2 = np.minimum(a2, 0.5 * np.linalg.norm(np.cross(X0[F[:, 1]] - X0[F[:, 0]], X0[F[:, 2]] - X0[F[:, 0]]), axis=1))
    squashed = a3 < a2 / 3
    # folded flat: adjacent triangles of one piece whose normals turn > 160 deg
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    tid = np.tile(np.arange(len(F)), 3)
    key = np.sort(E, 1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    ks, ts = key[order], tid[order]
    same = np.all(ks[1:] == ks[:-1], axis=1)
    t1, t2 = ts[:-1][same], ts[1:][same]
    folded_t = np.zeros(len(F), bool)
    flip = np.sum(n[t1] * n[t2], 1) < -0.94
    if X0 is not None:  # folds the garment was made with (a turned-down collar placed folded) don't count
        n0 = np.cross(X0[F[:, 1]] - X0[F[:, 0]], X0[F[:, 2]] - X0[F[:, 0]])
        n0 /= np.linalg.norm(n0, axis=1, keepdims=True) + 1e-12
        flip &= ~(np.sum(n0[t1] * n0[t2], 1) < -0.5)
    folded_t[t1[flip]] = True
    folded_t[t2[flip]] = True
    # self-intersections: every unique edge against nearby triangles that don't share its vertices
    ue = np.unique(key, axis=0)
    # a seam's two sides meet: an edge touching a triangle through a sewn (or stitched) partner isn't a crossing
    rep = np.arange(len(V))
    links = np.r_[M["sew"], M["stitch"]] if len(M["stitch"]) else M["sew"]
    for _ in range(4):  # union-find by repeated min over the pairs (chains of seams meet at corners)
        np.minimum.at(rep, links[:, 0], rep[links[:, 1]])
        np.minimum.at(rep, links[:, 1], rep[links[:, 0]])

    def crossings(Vx):
        cen = Vx[F].mean(1)
        rad = np.max(np.linalg.norm(Vx[F] - cen[:, None], axis=2), axis=1)
        mid = 0.5 * (Vx[ue[:, 0]] + Vx[ue[:, 1]])
        half = 0.5 * np.linalg.norm(Vx[ue[:, 0]] - Vx[ue[:, 1]], axis=1)
        cand = cKDTree(cen).query_ball_point(mid, r=float(half.max() + rad.max()))
        ei = np.repeat(np.arange(len(ue)), [len(c) for c in cand])
        ti = np.fromiter((t for c in cand for t in c), dtype=np.int64, count=len(ei))
        Rt = rep[F[ti]]
        keep = ~((Rt == rep[ue[ei, 0]][:, None]).any(1) | (Rt == rep[ue[ei, 1]][:, None]).any(1))
        ei, ti = ei[keep], ti[keep]
        hit = np.zeros(len(ei), bool)
        for s0 in range(0, len(ei), 200000):
            sl = slice(s0, s0 + 200000)
            T = F[ti[sl]]
            hit[sl] = _seg_tri(Vx[ue[ei[sl], 0]], Vx[ue[ei[sl], 1]], Vx[T[:, 0]], Vx[T[:, 1]], Vx[T[:, 2]])
        he, ht = ei[hit], ti[hit]
        # right at a seam the two sides fold against each other at the resolution of a triangle (a real seam has
        # its allowance there): crossings within a triangle's size of a seam don't count as tangles
        if len(he) and len(links):
            sv = np.unique(links.ravel())
            dseam, _ = cKDTree(Vx[sv]).query(0.5 * (Vx[ue[he, 0]] + Vx[ue[he, 1]]))
            hsz = float(np.median(np.linalg.norm(Vx[ue[:, 0]] - Vx[ue[:, 1]], axis=1)))
            far = dseam > 1.5 * hsz
            he, ht = he[far], ht[far]
        return he, ht
    hit_e, hit_t = crossings(V)
    carried = 0
    if X0 is not None:  # crossings already in the start (a sleeve laid round a bent elbow overlaps itself inside
        s_e, s_t = crossings(X0)  # the crook) are the placement's: reported apart, the sim's own counted
        start = set(zip(s_e.tolist(), s_t.tolist()))
        new = np.array([(e, t) not in start for e, t in zip(hit_e.tolist(), hit_t.tolist())], bool)
        carried = int((~new).sum()) if len(new) else 0
        if len(new):
            hit_e, hit_t = hit_e[new], hit_t[new]
    out = {"pieces": {}, "twisted_seams": [], "self_intersections": int(len(hit_t)),
           "crossings_from_placement": carried}
    epid = M["piece"][ue[:, 0]]
    pairs = {}
    for a_, b_ in zip(epid[hit_e], pid[hit_t]):
        k_ = " / ".join(sorted({names[a_], names[b_]}))
        pairs[k_] = pairs.get(k_, 0) + 1
    out["crossing_pairs"] = dict(sorted(pairs.items(), key=lambda kv: -kv[1]))
    # where: the crossings' positions (for a close-up)
    out["crossing_at"] = (0.5 * (V[ue[hit_e, 0]] + V[ue[hit_e, 1]])).round(3).tolist()[:50]
    for k, nm in enumerate(names):
        s = pid == k
        if not s.any():
            continue
        out["pieces"][nm] = {
            "crumpled": round(float(np.mean(squashed[s] | folded_t[s])), 4),
            "intersections": int(np.sum(epid[hit_e] == k) + np.sum(pid[hit_t] == k)),
        }
    # seam twist: along each seam, the two sides' directions in the placed start must agree
    if B is not None and X0 is not None and len(M["sew"]):
        for si, sd in enumerate(B["seams"]):
            p = M["sew"][M["sew_seam"] == si]
            if len(p) < 3:
                continue
            da = np.diff(X0[p[:, 0]], axis=0)
            db = np.diff(X0[p[:, 1]], axis=0)
            dots = np.sum(da * db, 1)
            if np.mean(dots < 0) > 0.5:
                out["twisted_seams"].append(str(sd))
    bad = [nm for nm, v in out["pieces"].items() if v["crumpled"] > 0.03 or v["intersections"] > 20]
    out["corrupt_pieces"] = bad
    return out


def fit(res: dict) -> dict:
    """Strain past the fabric's limit, ease against the body at the tailor's girths (negative = too tight), and how
    far the cloth floats off the body. Per region numbers + per vertex arrays for the map."""
    V, M, body, fab = res["V"], res["mesh"], res["body"], res["fabric"]
    tri_pat, vert_pat = edge_strain(V, M["uv"], M["F"])  # against the flat pattern
    # against the cloth's rest shape (its start positions): the stretch the garment is under on this body. The
    # start can't be laid round a bent arm or the neck without some distortion (a torus isn't developable), and
    # the sim keeps that as rest; it is reported apart (`placement_p95`) and doesn't count against the fit
    F_ = M["F"]
    X0 = res["X0"]
    eds = [(0, 1), (1, 2), (2, 0)]
    tri = np.max([np.linalg.norm(V[F_[:, a]] - V[F_[:, b]], axis=1) /
                  np.maximum(np.linalg.norm(X0[F_[:, a]] - X0[F_[:, b]], axis=1), 1e-9) for a, b in eds], axis=0) - 1
    vert = np.zeros(len(V))
    np.maximum.at(vert, F_.ravel(), np.repeat(tri, 3))
    tri_place, _ = edge_strain(X0, M["uv"], M["F"])
    # a button's stitch is a point load (a real button spreads it over its shank and the placket's layers): the
    # triangles round stitch vertices are left out of the numbers (still coloured in the map)
    pin = np.zeros(len(V), bool)
    if len(M["stitch"]):
        pin[M["stitch"].ravel()] = True
    ring = pin[M["F"]].any(1)
    pin2 = pin.copy()
    pin2[M["F"][ring].ravel()] = True
    pin3 = pin2.copy()  # two rings: a button pulls a little patch
    pin3[M["F"][pin2[M["F"]].any(1)].ravel()] = True
    pin2 = pin3
    # seams: a sewing spring holds its two vertices together with a stiff short spring; the ring of triangles on
    # each side of a seam carries that, not the garment's fit (measured: torso interiors 1-3%, seam rings 3-7%
    # on a well-fitting shirt), so the girth regions are read off the pieces' interiors
    seamv = np.zeros(len(V), bool)
    seamv[M["sew"].ravel()] = True
    pin2 = pin2 | seamv
    pin2[M["F"][seamv[M["F"]].any(1)].ravel()] = True
    use = ~pin2[M["F"]].any(1)
    trU = tri[use]
    limit = fab["limit"]
    from scipy.spatial import cKDTree as KD
    dist, _ = KD(body.V).query(V)
    out = {"strain_limit": limit, "strain_p95": float(np.percentile(trU, 95)), "strain_max": float(trU.max()),
           "over_limit_share": float(np.mean(trU > limit)), "regions": {},
           "placement_p95": float(np.percentile(tri_place, 95)),
           "pattern_strain_p95": float(np.percentile(tri_pat[use], 95))}
    vert = vert.copy()
    vU = np.zeros(len(V))
    np.maximum.at(vU, M["F"][use].ravel(), np.repeat(trU, 3))
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
        near = (np.abs(V[:, 2] - z) < 0.03) & np.isin(M["piece"], tors) & ~pin2  # the body pieces round that girth
        # across the front and back, away from the sides: under the arm the sleeve's pull shows (a shirt that fits
        # read 6-19% there, the same shirt 1-2% across the front); a garment too small is strained all round
        if near.any():
            near &= np.abs(V[:, 0]) < 0.6 * np.abs(V[near, 0]).max()
        out["regions"][reg] = {"body_mm": bb, "garment_mm": round(gg, 1), "ease_mm": round(gg - bb, 1),
                               "ease": round((gg - bb) / bb, 3),
                               "strain_p95": float(np.percentile(vU[near], 95)) if near.any() else None}
    out["vertex_strain"] = vert
    out["vertex_dist"] = dist
    out["float_share"] = float(np.mean(dist > 0.05))
    out["verdict"] = "fits"  # set by build from the sizing and the girth regions
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
        w, per = 0.0, {}
        for nm in torso:
            P = pcs[nm]["P"]
            dz = 0.0
            al = pcs[nm]["wrap"].get("align")
            if al:  # a piece hung from another's point (a coat's skirt): its own pattern y is shifted
                mine, other, op = al
                dz = float(pcs[other]["P"][pcs[other]["names"][op], 1] - P[pcs[nm]["names"][mine], 1])
            L = pcs[nm]["lines"].get(reg)
            y = float(np.mean(L[:, 1])) if L is not None else body.at[zk] - hps_z - dz  # the draft's line, or the
            # body's height (pattern y, hps at 0); the chest at the armhole's bottom (where a chest line ends: the
            # outline is still curving in at the line's own height)
            if reg == "chest" and "armhole" in pcs[nm]["names"]:
                y = float(P[pcs[nm]["names"]["armhole"], 1]) - 0.002
            wi = _piece_width_at(P, y)
            if wi > 0 and abs(P[:, 0].min() + P[:, 0].max()) > 0.05:
                # a piece drawn from its centre line out (x = 0 the centre front/back): what lies past the centre
                # is an overlap (a closure, a lapel, a pleat's underlay), not girth
                xs = []
                for a_, b_ in zip(P, np.roll(P, -1, axis=0)):
                    if (a_[1] - y) * (b_[1] - y) <= 0 and a_[1] != b_[1]:
                        xs.append(a_[0] + (y - a_[1]) / (b_[1] - a_[1]) * (b_[0] - a_[0]))
                if xs:
                    sgn = 1.0 if P[:, 0].max() > -P[:, 0].min() else -1.0
                    wi = max(0.0, max(sgn * x for x in xs))
            per[nm] = round(wi * 1000, 1)
            w += wi
        g = w * 1000
        bb = body.m["mm"][reg]
        rows[reg] = {"body_mm": bb, "garment_mm": round(g, 1), "ease_mm": round(g - bb, 1),
                     "ease": round((g - bb) / bb, 3), "pieces_mm": per}
    return {"options": opts, "rows": rows}


# ---------------------------------------------------------------- the model: scene and export


def atlas_uv(M: dict, margin: float = 0.01) -> tuple[np.ndarray, float]:
    """The flat pattern as the uv: every piece at one scale (texel density the same everywhere), packed in rows
    (tallest first) into the unit square. Returns (uv (n, 2), metres per uv unit)."""
    uv, pid = M["uv"], M["piece"]
    boxes = []
    for k in range(len(M["names"])):
        P = uv[pid == k]
        boxes.append((k, P.min(0), np.ptp(P, 0)))
    order = sorted(boxes, key=lambda b: -b[2][1])
    area = sum((b[2][0] + margin) * (b[2][1] + margin) for b in boxes)
    width = max(math.sqrt(area) * 1.15, max(b[2][0] for b in boxes) + 2 * margin)
    x = y = margin  # a margin round the atlas too: pieces on its edge bleed under mip/bilinear sampling
    row_h = 0.0
    place = {}
    for k, lo, size in order:
        if x + size[0] + margin > width:
            x, y, row_h = margin, y + row_h + margin, 0.0
        place[k] = (x, y, lo)
        x += size[0] + margin
        row_h = max(row_h, size[1])
    side = max(width, y + row_h + margin)
    out = np.zeros_like(uv)
    for k, (x0, y0, lo) in place.items():
        s = pid == k
        out[s] = (uv[s] - lo + [x0, y0]) / side
    return out, side


def garments(name: str, spec: dict, log=print) -> list:
    """Every garment of a model (spec["cloth"]: {name: garment}) sewn and settled on the model's own body (its base:
    MakeHuman or the template, measured by `tailor`), cached by content."""
    out = []
    gs = spec.get("cloth") or {}
    if not gs:
        return out
    src = body_mesh(spec=spec)
    for gname, g in gs.items():
        res = build(g, src, f"{name}:{gname}", log=log)
        log(f"cloth {gname}: {res['fit']['verdict']}")
        out.append((gname, g, res))
    return out


def scene_job(name: str, spec: dict, log: list | None = None) -> list:
    """What blender_cloth.show needs per garment: its settled mesh + pattern uv in an npz beside the model."""
    from . import store
    say = (log.append if isinstance(log, list) else print)
    entries = []
    for gname, g, res in garments(name, spec, say):
        uv, _ = atlas_uv(res["mesh"])
        path = store._dir(name) / f"cloth_{gname}.npz"
        np.savez(path, verts=res["V"].astype(np.float32), faces=res["mesh"]["F"].astype(np.int32),
                 uv=uv.astype(np.float32))
        entries.append({"name": f"cloth:{gname}", "key": res["key"], "npz": str(path),
                        "color": g.get("color", "#8fb3d9"), "thickness": fabric(g).get("thickness", 0.0008),
                        "roughness": float(g.get("roughness", 0.85))})
    return entries


def export_part(name: str, spec: dict, out_dir, texture: int = 1024, log=print) -> list:
    """The garments as export parts (as asset.lowpoly makes them: verts, corner_vert, uv, normal, tangent, sign) and
    their maps. Two-sided: the outer face and an inner one a cloth's thickness in (a coat open at the front shows
    its inside). The uv is the flat pattern (`atlas_uv`); the base colour carries the seams as a slightly darker
    line (a seam's shadow) so the pattern reads on the model."""
    from PIL import Image, ImageDraw
    from . import hair as hairmod
    out_dir = Path(out_dir)
    parts = []
    for gname, g, res in garments(name, spec, log):
        M, V = res["mesh"], res["V"].astype(np.float64)
        F = M["F"]
        uv, side = atlas_uv(M)
        # vertex normals (area weighted)
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        vn = np.zeros_like(V)
        for k in range(3):
            np.add.at(vn, F[:, k], fn)
        vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
        # which way is out: away from the body
        from scipy.spatial import cKDTree as KD
        body = res["body"]
        _, ni = KD(body.V).query(V)
        flip = np.sum(vn * (V - body.V[ni]), 1) < 0
        if np.mean(flip) > 0.5:
            F = F[:, [0, 2, 1]]
            vn = -vn
        th = float(fabric(g).get("thickness", 0.0008))
        Vin = V - vn * th
        Vall = np.r_[V, Vin]
        Fall = np.r_[F, F[:, [0, 2, 1]] + len(V)]
        UVall = np.r_[uv, uv]
        UVc = UVall[Fall.ravel()]  # per corner
        n, tt, sg = hairmod._tangents(Vall, Fall, UVc)
        part = {"verts": Vall.astype(np.float32), "corner_vert": Fall.ravel().astype(np.int64),
                "uv": UVc.astype(np.float32),
                "normal": n.astype(np.float32), "tangent": tt.astype(np.float32), "sign": sg.astype(np.float32)}
        # maps: the colour, seams drawn a little darker, flat normal, ORM (rough cloth)
        rgb = tuple(int(g.get("color", "#8fb3d9").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        img = Image.new("RGB", (texture, texture), rgb)
        d = ImageDraw.Draw(img)
        dark = tuple(int(c * 0.8) for c in rgb)
        border = M["border"]
        for k in range(len(M["names"])):
            sel = np.where((M["piece"] == k) & border)[0]
            if len(sel) < 3:
                continue
            ring = uv[sel] * texture
            ring[:, 1] = texture - ring[:, 1]
            d.line([tuple(p) for p in ring] + [tuple(ring[0])], fill=dark, width=max(1, texture // 512))
        files = {"basecolor": out_dir / f"cloth_{gname}_basecolor.png", "orm": out_dir / f"cloth_{gname}_orm.png",
                 "normal": out_dir / f"cloth_{gname}_normal.png",
                 "specular": out_dir / f"cloth_{gname}_specular_gltf.png"}
        img.save(files["basecolor"])
        rough = int(255 * float(g.get("roughness", 0.85)))
        Image.new("RGB", (16, 16), (255, rough, 0)).save(files["orm"])
        Image.new("RGB", (16, 16), (128, 128, 255)).save(files["normal"])
        Image.new("RGBA", (16, 16), (255, 255, 255, 128)).save(files["specular"])
        log(f"cloth {gname}: {len(Fall)} triangles (two-sided), pattern uv at {texture / side:.0f} texels/m")
        parts.append((f"cloth_{gname}", part, files))
    return parts


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
