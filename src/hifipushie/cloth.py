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
import threading
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


def _seg_dist(Q: np.ndarray, P: np.ndarray, closed: bool = True) -> np.ndarray:
    """Distance from points Q to the polyline P (closed unless closed=False)."""
    A, B = (P, np.roll(P, -1, axis=0)) if closed else (P[:-1], P[1:])
    out = np.full(len(Q), np.inf)
    for s in range(0, len(A), 256):
        a, b = A[s:s + 256][None], B[s:s + 256][None]
        ab = b - a
        t = np.clip(np.sum((Q[:, None] - a) * ab, -1) / np.maximum(np.sum(ab * ab, -1), 1e-18), 0, 1)
        d = np.linalg.norm(Q[:, None] - (a + t[..., None] * ab), axis=-1).min(1)
        out = np.minimum(out, d)
    return out


def _fold_line(B: dict, nm: str, h: float) -> np.ndarray | None:
    """Where a folded piece (wrap "fold": [rise, layer]) turns over in the flat: its sewn edge (the seam side naming
    it, to another piece) offset into the piece by `rise` and by `rise` + half / all of the U's length, sampled every
    0.7 h. Matches place()'s fold (a half circle one layer across; on a cone the circle's offset is the same curve)."""
    w = B["pieces"][nm].get("wrap") or {}
    if not w.get("fold"):
        return None
    rise = float(w["fold"][0])
    pcs = B["pieces"]
    for A, Bs in B["seams"]:
        for side, other in ((A, Bs), (Bs, A)):
            chain = [side] if isinstance(side, str) else list(side)
            oc = [other] if isinstance(other, str) else list(other)
            if all(e.split(":")[0] == nm for e in chain) and all(e.split(":")[0] != nm for e in oc):
                L = np.concatenate([pcs[nm]["P"][_edge(pcs, e)[1]] for e in chain])
                L = _resample(L, np.linspace(0, 1, max(3, int(pattern.length(L) / (0.7 * h)) + 1)))
                t = np.gradient(L, axis=0)
                nrm = np.c_[-t[:, 1], t[:, 0]]
                nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
                P = pcs[nm]["P"]
                c = P.mean(0)
                if np.mean(np.sum((c - L) * nrm, 1)) < 0:  # toward the piece
                    nrm = -nrm
                arc = np.pi * float(w["fold"][1]) / 2  # the U's length (place(): a half circle one layer across)
                return np.concatenate([L + (rise + f * arc) * nrm for f in (0.0, 0.5, 1.0)])
    return None


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
        # a piece placed folded (a turned-down collar) gets a row of vertices on its fold line, so edges run along
        # the crease: 1 cm edges across a 6 mm fold were shortened up to 52% in the rest shape and the band crimped
        fl = _fold_line(B, nm, h)
        if fl is not None and len(fl):
            fl = fl[_inside(ring, fl) & (_seg_dist(fl, ring) > 0.45 * h)]
            if len(fl) and len(Q):
                Q = Q[cKDTree(fl).query(Q)[0] > 0.5 * h]
            Q = np.r_[Q, fl] if len(fl) else Q
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
        self._faces = b["F"]
        self._m = None
        self._hull = {}

    @property
    def m(self) -> dict:
        """The tailor's tape (tailor.measure); a collider that isn't a body (a table under a tablecloth) measures
        nothing: {"mm": {}, "at": {}} (pieces wrapped on a torso, an arm or the neck need a body)."""
        if self._m is None:
            try:
                self._m = tailor.measure(self.V, self._faces, self.J)
            except (KeyError, ValueError, IndexError, TypeError):
                self._m = {"mm": {}, "at": {}, "body": False}
        return self._m

    @property
    def at(self) -> dict:
        if not hasattr(self, "_at"):
            self._at = {k: np.asarray(v) if isinstance(v, list) else v for k, v in self.m["at"].items()}
        return self._at

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

    def neck_rows(self) -> list:
        """Sections across the neck axis every 5 mm (-40..+120 mm from the neck joint): girth, centroid offset from
        the axis, largest radius from the centroid, and whether it is the neck (girth within 8% of the narrowest,
        in the run round it; above that the plane cuts the jaw, below it the trapezius)."""
        if "neck_rows" in self._hull:
            return self._hull["neck_rows"]
        nb, hd = self.J["neck"], self.J["head"]
        d = (hd - nb) / np.linalg.norm(hd - nb)
        rows = []
        for h in np.arange(-0.04, 0.125, 0.005):
            o = nb + d * h
            L = tailor.section(self.V, self.T, o, d, o)
            if L is None or not tailor._encloses(L, o, d):
                continue
            c = L.mean(0)
            v = L - c
            rows.append({"h": float(h), "girth": float(tailor.girth(L, d)), "off": c - o,
                         "r": float(np.linalg.norm(v - np.outer(v @ d, d), axis=1).max())})
        g = np.array([r["girth"] for r in rows])
        i0 = int(np.argmin(g))
        for r in rows:
            r["neck"] = False
        for step in (1, -1):
            i = i0
            while 0 <= i < len(rows) and g[i] <= 1.08 * g[i0]:
                rows[i]["neck"] = True
                i += step
        self._hull["neck_rows"] = rows
        return rows

    def neck_radius(self, h: float) -> float | None:
        """The neck's largest radius round its centre at height h up its axis, if the section there is the neck."""
        rows = [r for r in self.neck_rows() if r["neck"]]
        if not rows or h < rows[0]["h"] - 0.003 or h > rows[-1]["h"] + 0.003:
            return None
        return float(np.interp(h, [r["h"] for r in rows], [r["r"] for r in rows]))

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


def _sewn_arc(B: dict, M: dict, nm: str, R: float):
    """(centre, radius) of the circle through a neck piece's sewn edge in the flat (the edge sewn to a piece not on
    the neck, else to any other piece), or None if it is near straight (radius > 3 m) or tighter than a cone allows."""
    k = M["names"].index(nm)
    sew = np.asarray(M["sew"])
    pid = M["piece"]
    mine = np.r_[sew[pid[sew[:, 0]] == k, 0], sew[pid[sew[:, 1]] == k, 1]]
    other = np.r_[sew[pid[sew[:, 0]] == k, 1], sew[pid[sew[:, 1]] == k, 0]]
    keep = pid[other] != k
    far = keep & np.array([B["pieces"][M["names"][pid[o]]]["wrap"].get("to") != "neck" for o in other], bool)
    pts = M["uv"][np.unique(mine[far] if far.any() else mine[keep])]
    if len(pts) < 5:
        return None
    A = np.c_[2 * pts, np.ones(len(pts))]
    sol, *_ = np.linalg.lstsq(A, (pts ** 2).sum(1), rcond=None)
    c = sol[:2]
    rho = float(np.sqrt(sol[2] + c @ c))
    if rho > 3.0 or rho <= R * 1.02:
        return None
    return c, rho


def _neck_frame(body: "Body", nb: np.ndarray, d: np.ndarray, R: float) -> tuple[float, np.ndarray]:
    """(height up the neck axis where a band of radius R can sit, the axis' origin moved onto the neck's centre).
    The neck joint sits ~22 mm behind the neck's centre, and from 40 mm up the sections cut the jaw."""
    rows = body.neck_rows()
    origin = nb + np.mean([r["off"] for r in rows if r["neck"]], axis=0)
    base = None
    for r in rows:
        if r["neck"] and r["girth"] <= 2 * np.pi * (R - CLEAR / 2):
            base = r["h"]
            break
    if base is None:
        base = min((r for r in rows if r["neck"]), key=lambda r: r["girth"])["h"]
    return float(base), origin


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
    torso = [nm for nm in names if pcs[nm]["wrap"].get("to") == "torso"]
    needs_body = [nm for nm in names if pcs[nm]["wrap"].get("to", "torso") != "flat"]
    if needs_body and not body.m["at"]:
        raise ValueError(f"pieces {needs_body} are wrapped on a body (torso, arm, neck) but the model has none to "
                         'measure (a "base" body): give them "wrap": {"to": "flat", "at": [x, y, z]} to drape them')
    at = body.at
    hps = np.asarray(at["hps.L"]) if "hps.L" in at else np.zeros(3)
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
    neck_base = None  # height up the neck axis where the neck pieces' sewn edges start (shared: a collar on a stand)
    neck_tilt = None  # the neck pieces' axis (shared; wrap "tilt")
    placed_neck = []
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
            d1, d2 = (el - sh) / seg[0], (wr - el) / seg[1]

            def at_t(ti, ang, r):
                """The point at arc position t along the bent axis, angle ang round it, radius r; and its radial."""
                if ti <= seg[0]:
                    d, c = d1, sh + d1 * ti
                else:
                    d, c = d2, el + d2 * (ti - seg[0])
                c = c + np.array([np.interp(ti, ts, offs[:, k]) for k in range(3)])
                up = np.array([0, 0, 1.0]) + 0.6 * out_dir
                up -= d * (up @ d)
                up /= np.linalg.norm(up)
                fw = np.cross(d, up)
                if fw[1] > 0:  # pattern +x goes to the front of the arm (-Y)
                    fw = -fw
                u = np.cos(ang) * up + np.sin(ang) * fw
                return c + r * u, u
            # The inside of the elbow: round the kinked axis each segment's cylinder runs past the mitre plane there
            # by r (u . n) tan(theta / 2), so the two overlapped in a wedge (58 crossings in every start; the sim grew
            # them into tangled sleeves, CORRUPT). That excess length (the sleeve is straight, the arm bent) is laid
            # as a fin standing out from the crook (a hairpin one layer across), which the sim folds into the
            # half-lock fold a bent sleeve has.
            cth = float(np.clip(d1 @ d2, -1, 1))
            nin = d2 - d1 * cth
            nin = nin / max(np.linalg.norm(nin), 1e-9)
            tan_h = math.tan(math.acos(cth) / 2)
            for i, (x, yv) in enumerate(U):
                ti = float(t[i])
                if closed:
                    ang = float(w.get("front", 1)) * th[i] + math.radians(float(w.get("turn", 0)))
                    out[i] = at_t(ti, ang, rr[i])[0]
                    continue
                ang = float(w.get("front", 1)) * (x - cx) / Rp + math.radians(float(w.get("turn", 0)))
                p, u = at_t(ti, ang, rad[i])
                _, u1 = at_t(seg[0] - 1e-6, ang, rad[i])
                dl = rad[i] * max(0.0, float(u1 @ nin)) * tan_h
                mg = 0.6 * dl  # the fin's feet stand back from the mitre plane on each side (its legs never touch)
                if dl > 1e-4 and seg[0] - dl - mg < ti < seg[0] + dl + mg and not w.get("no_fin"):
                    f = (ti - (seg[0] - dl - mg)) / (2 * (dl + mg))  # 0 .. 1 round the hairpin
                    b1, ua = at_t(seg[0] - dl - mg, ang, rad[i])
                    b2, ub = at_t(seg[0] + dl + mg + 1e-6, ang, rad[i])
                    base = b1 * (1 - f) + b2 * f
                    db = (d1 + d2) / np.linalg.norm(d1 + d2)
                    ur = ua + ub
                    ur = ur - (ur @ db) * db  # out in the mitre plane, between the two cylinders (radially out from
                    ur /= np.linalg.norm(ur)  # one of them it rose into the forearm's)
                    span = 0.5 * np.linalg.norm(b2 - b1)
                    height = math.sqrt(max((dl + mg) ** 2 - span ** 2, 0.0))  # the legs keep the length
                    p = base + height * math.sin(math.pi * f) * ur
                out[i] = p
            X[sel] = out
        elif to == "neck":
            nb, hd = body.J["neck"], body.J["head"]
            d = (hd - nb) / np.linalg.norm(hd - nb)
            P = pcs[nm]["P"]
            e = uv[M["points"][f"{nm}:{w.get('edge', 'bottomMid')}"]]
            width = P[:, 0].max() - P[:, 0].min()
            # the band at its own girth (a stand closes round the neck at its length / 2 pi), standing where the
            # neck is narrow enough for it, as the bodice's neckline (the same length) settles there too. Clearing
            # the neck from its joint up put a 400 mm stand at r 103 mm (the trapezius' flare), 62% of the circle,
            # and sewing re-bent the interfaced band to r 60: ruffles.
            R = width / (2 * np.pi)
            above = float(w.get("above", 0.0))
            if neck_base is None:
                neck_base, nb = _neck_frame(body, nb, d, R)
            else:
                nb = neck_base[1]
                neck_base = neck_base[0]
                # sewn to a neck piece already placed (a collar on its stand): its sewn edge where that piece's edge
                # is. The design's fixed "above" (3 cm) left a collar 2 cm above a lowered stand
                k_ = names.index(nm)
                sw = M["sew"]
                prev = [names.index(o) for o in placed_neck]
                pv = np.r_[sw[(pid[sw[:, 0]] == k_) & np.isin(pid[sw[:, 1]], prev), 1],
                           sw[(pid[sw[:, 1]] == k_) & np.isin(pid[sw[:, 0]], prev), 0]]
                if len(pv) >= 3 and not w.get("fixed_above"):
                    above = float(np.median((X[pv] - nb) @ (neck_tilt if neck_tilt is not None else d))) - neck_base
            # still clear of the neck over the piece's own heights (sections that are the neck: the jaw above it is
            # left to the collision)
            for hgt in np.linspace(neck_base + above + (P[:, 1].min() - e[1]),
                                   neck_base + above + (P[:, 1].max() - e[1]), 6):
                rc = body.neck_radius(hgt)
                if rc is not None:
                    R = max(R, rc + CLEAR / 2)
            # wrap "tilt" (deg, + tips the front down; shared by the neck pieces): the band's axis turned from the
            # neck's about the side axis. Off by default: on the thin body (a 3 cm neck under the jaw) no tilt from
            # -15 to 25 deg cleared a 3 cm stand + collar better than square (the collar pushed 19-34 mm: the open
            # thin-collar crumple); the tilt that clears a ring of the band's radius best is used.
            if neck_tilt is None:
                neck_tilt = d
                if "tilt" in w:
                    # the tilt (forward, about the side axis) that keeps the neck pieces' whole height clearest of
                    # the body: rings at the band's radius from its base to the top of the tallest neck piece
                    sd0 = np.cross(d, np.array([0, 1.0, 0]) - d * d[1])
                    sd0 /= np.linalg.norm(sd0)
                    htop = max(float(pcs[o]["wrap"].get("above", 0.0)) + (  # a turned collar's top is its fold
                        sum(map(float, pcs[o]["wrap"]["fold"])) if pcs[o]["wrap"].get("fold")
                        else float(np.ptp(pcs[o]["P"][:, 1]))) for o in names if pcs[o]["wrap"].get("to") == "neck")
                    phis = np.linspace(0, 2 * np.pi, 48, endpoint=False)

                    def push_at(dd):
                        bk = np.array([0, 1.0, 0]) - dd * dd[1]
                        bk /= np.linalg.norm(bk)
                        sdv = np.cross(dd, bk)
                        ring = np.outer(np.cos(phis), bk) + np.outer(np.sin(phis), sdv)
                        P = np.concatenate([nb + dd * (neck_base + hh) + R * ring
                                            for hh in np.linspace(0, htop, 5)])
                        return float(np.linalg.norm(body.push_out(P, CLEAR) - P, axis=1).max())
                    cands = [math.radians(float(w["tilt"]))] if "tilt" in w else \
                        [math.radians(a) for a in range(-10, 45, 5)]
                    best = None
                    for th_ in cands:  # rotate d about the side axis: + tips the front down
                        dd = d * math.cos(th_) + np.cross(sd0, d) * math.sin(th_)
                        dd /= np.linalg.norm(dd)
                        pp = push_at(dd)
                        if best is None or pp < best[0] - 1e-3 or (abs(pp - best[0]) <= 1e-3 and abs(th_) < abs(best[1])):
                            best = (pp, th_, dd)
                    neck_tilt = best[2]
            d = neck_tilt
            back = np.array([0, 1.0, 0]) - d * d[1]
            back /= np.linalg.norm(back)
            side = np.cross(d, back)
            if side[0] < 0:
                side = -side
            # "fold": [rise, layer] a turned-down collar: up `rise` from its sewn edge, then folded down outside
            # itself `layer` further out (placed folded, so the rest shape holds the fold; arc length kept per row)
            fold = w.get("fold")
            # a curved band (a stand, a collar: its sewn edge an arc in the flat) lies isometrically on a cone, not a
            # cylinder: the sewn edge's circle (centre c, radius rho) rolls round the base at R, the band narrowing
            # toward the apex. On a cylinder its ends started high and sewing bent the band in its plane: ruffles.
            cone = _sewn_arc(B, M, nm, R)
            out = np.zeros((len(U), 3))
            for i, (x, y) in enumerate(U):
                if cone is not None:  # centre above the band: apex above, narrowing up; below: flaring up
                    c, rho = cone
                    up = 1.0 if c[1] > e[1] else -1.0
                    rr = float(np.hypot(x - c[0], y - c[1]))
                    phi = math.atan2(x - c[0], up * (c[1] - y)) - math.atan2(e[0] - c[0], up * (c[1] - e[1]))
                    sa = R / rho
                    ca = math.sqrt(max(0.0, 1 - sa * sa))
                    tt = up * (rho - rr)  # distance up the band from the sewn edge
                    dy = tt * ca
                    rad = R - up * tt * sa
                    ang = phi * rho / R
                else:
                    dy, rad, ang = y - e[1], R, (x - e[0]) / R
                r, hgt = rad, above + dy
                if fold and dy > fold[0]:  # the fall turned down outside the stand round a U one layer across
                    sf, rho_f = dy - fold[0], fold[1] / 2
                    if sf < np.pi * rho_f:
                        r = rad + rho_f * (1 - math.cos(sf / rho_f))
                        hgt = above + fold[0] + rho_f * math.sin(sf / rho_f)
                    else:
                        r, hgt = rad + fold[1], above + fold[0] - (sf - np.pi * rho_f)
                radial = np.cos(ang) * back + np.sin(ang) * side
                out[i] = nb + d * (neck_base + hgt) + r * radial
            X[sel] = out
            neck_base = (neck_base, nb)
            placed_neck.append(nm)
        elif to == "flat":  # laid flat at a height (a tablecloth, a blanket): pattern x, y -> world x, y
            o = np.asarray(w.get("at", [0, 0, 1.0]), float)
            X[sel] = np.c_[U[:, 0] + o[0], U[:, 1] + o[1], np.full(len(U), o[2])]
        else:
            raise ValueError(f"piece {nm}: unknown wrap {to!r} (torso, arm.L, arm.R, neck, flat)")
    gaps = np.full(len(X), gap)
    for k, nm in enumerate(names):
        wto = B["pieces"][nm]["wrap"].get("to", "")
        if (wto.startswith("arm.") and _closed_girth(M, nm)) or wto == "neck":  # bands hugging the body
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


NOT_SIM = ("color", "roughness", "cleanup", "detail", "sculpt", "note")  # garment keys that never change the sim


def _fabric_at(g: dict, h: float) -> dict:
    fab = fabric(g)
    # Blender's cloth mass is per vertex: the presets are per vertex at 2 cm triangles, so a finer mesh keeps the
    # garment's weight (and so its stretch and drape under gravity) by scaling it with the area a vertex carries
    fab["mass"] = float(fab["mass"]) * (h / H_REF) ** 2
    # lighter vertices on the same springs ring twice as fast per halving of h: more substeps (quality 6 at 1 cm
    # crumpled one interfaced cuff of a symmetric pair into a ball, the other not: an instability)
    fab.setdefault("quality", int(round(6 * max(1.0, H_REF / h))))
    return fab


def _blender_job(job_dir: Path, cfg: dict, arrays: dict, name: str, log, progress, timeout: float = 3600) -> tuple:
    """Run blender_cloth.py on a job (under resources.heavy), streaming its "cloth:" lines to `progress`.
    Returns (out.npz contents, the log lines without progress)."""
    from . import resources, render as rmod
    job_dir.mkdir(parents=True, exist_ok=True)
    np.savez(job_dir / "in.npz", **arrays)
    cfg = dict(cfg, out=str(job_dir / "out.npz"))
    (job_dir / "job.json").write_text(json.dumps(cfg))
    (job_dir / "out.npz").unlink(missing_ok=True)
    progress(f"waiting for the heavy-job slot ({cfg.get('mode', 'sim')})")
    with resources.heavy(f"cloth {name}", log=log):
        progress(f"started {cfg.get('mode', 'sim')}")
        t = time.time()
        p = subprocess.Popen([rmod.BLENDER, "-b", "--factory-startup", "--python", str(SCRIPT), "--",
                              str(job_dir / "job.json")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        lines = []
        try:
            for line in p.stdout:
                lines.append(line.rstrip())
                if line.startswith("cloth:"):
                    progress(line[6:].strip())
                if time.time() - t > timeout:
                    p.kill()
                    raise RuntimeError(f"cloth sim {name}: over {timeout:.0f} s, stopped")
            p.wait(timeout=60)
        finally:
            if p.poll() is None:
                p.kill()
    if p.returncode != 0 or not (job_dir / "out.npz").exists():
        raise RuntimeError("cloth sim failed:\n" + "\n".join(lines[-40:]))
    d = dict(np.load(job_dir / "out.npz"))
    return d, [ln for ln in lines if ln.startswith("cloth:") and not ln.startswith("cloth: progress")]


def transfer(Ms: dict, Vs: np.ndarray, M: dict) -> np.ndarray:
    """A garment settled on one mesh carried onto another mesh of the same pattern (finer): each vertex takes the
    barycentric blend of the coarse triangle of its own piece under it in pattern coordinates (outline vertices just
    outside the coarse outline clamp onto its nearest triangle). Lies exactly on the coarse surface, so it carries no
    crossings the coarse garment hasn't."""
    out = np.zeros((len(M["uv"]), 3))
    for k in range(len(M["names"])):
        Fc = Ms["F"][Ms["piece"][Ms["F"][:, 0]] == k]
        sel = np.where(M["piece"] == k)[0]
        if not len(sel):
            continue
        Q = M["uv"][sel]
        A, B, C = Ms["uv"][Fc[:, 0]], Ms["uv"][Fc[:, 1]], Ms["uv"][Fc[:, 2]]
        kk = min(12, len(Fc))
        _, cand = cKDTree((A + B + C) / 3).query(Q, k=kk)
        cand = cand.reshape(len(Q), kk)
        a, b, c = A[cand], B[cand], C[cand]
        v0, v1, v2 = b - a, c - a, Q[:, None] - a
        d00, d01, d11 = (v0 * v0).sum(-1), (v0 * v1).sum(-1), (v1 * v1).sum(-1)
        d20, d21 = (v2 * v0).sum(-1), (v2 * v1).sum(-1)
        den = np.where(np.abs(d00 * d11 - d01 * d01) > 1e-18, d00 * d11 - d01 * d01, 1e-18)
        w1 = (d11 * d20 - d01 * d21) / den
        w2 = (d00 * d21 - d01 * d20) / den
        W = np.stack([1 - w1 - w2, w1, w2], -1)
        best = np.argmax(W.min(-1), axis=1)
        w = np.clip(W[np.arange(len(Q)), best], 0, None)
        w /= w.sum(1, keepdims=True)
        T = Fc[cand[np.arange(len(Q)), best]]
        out[sel] = np.einsum("nk,nkd->nd", w, Vs[T])
    return out


def build(g: dict, body_src: dict, name: str = "garment", log=print, frames: int | None = None,
          render: dict | None = None, out_dir: Path | None = None, cached_only: bool = False, progress=None) -> dict | None:
    """Draft, mesh, place and simulate one garment on one body, then clean it up. Returns {"V" final verts, "V_sim"
    the sim's own, "mesh", "fit", "integrity", "sizing", "shape", ...}; the sim is cached by content (keys that only
    change the look or the clean-up never re-simulate). cached_only: None when it hasn't been simulated.
    quality "final" (default): the whole sim at `coarse` (2 cm), then carried onto the `resolution` mesh (1 cm) and
    settled there (refine): the coarse-then-fine particle distance artists use. "draft": the coarse sim alone."""
    progress = progress or (lambda s: None)
    body = Body(body_src)
    Bp = pieces(g, body.m["mm"] if g.get("pattern") else {})
    h = float(g.get("resolution", 0.01))  # 2 cm made blobby, faceted folds
    quality = g.get("quality", "final")
    hc = float(g.get("coarse", 0.02))
    refine = quality == "final" and hc > 1.4 * h
    if quality == "draft":
        h = max(h, hc)
    hs = hc if refine else h
    Ms = mesh(Bp, hs)
    Xs = place(Bp, Ms, body)
    push = dict(Bp.get("push") or {})
    if refine:
        M = mesh(Bp, h)
        # the fine mesh's rest shape is the coarse one's placement carried onto it (the same surface, sampled finer):
        # placed again at 1 cm, its cuff spiral and pushed-off rows differed from the coarse rest the sim had settled,
        # and easing between the two crumpled one interfaced cuff
        X0 = transfer(Ms, Xs, M)
    else:
        M, X0 = Ms, Xs
    fab_s, fab = _fabric_at(g, hs), _fabric_at(g, h)
    state = g.get("state", "worn")
    hang = isinstance(state, dict) and "hang" in state
    code = hashlib.sha1(SCRIPT.read_bytes()).hexdigest()
    # keyed on the sim's inputs themselves (start positions, pattern, triangles, seams, stitches, interfacing, both
    # meshes) and the Blender side's code, not on cloth.py: a change there that moves nothing doesn't re-simulate
    inputs = hashlib.sha1(b"".join(np.ascontiguousarray(a).tobytes() for a in (
        Xs, Ms["uv"], Ms["F"], Ms["sew"], Ms["stitch"], interfacing(Bp, Ms),
        *((X0, M["uv"], M["F"], M["sew"], M["stitch"]) if refine else ())))).hexdigest()
    gs = {k: v for k, v in g.items() if k not in NOT_SIM}
    key = hashlib.sha1(json.dumps([VERSION, gs, body_src.get("key"), frames, code, inputs, fab_s, fab], sort_keys=True,
                                  default=str).encode()).hexdigest()[:16]
    cache = _cache_dir() / f"{key}.npz"
    res = {"pieces": Bp, "mesh": M, "X0": X0, "body": body, "fabric": fab, "key": key, "refined": refine,
           "coarse_mesh": Ms if refine else None, "hung": hang}
    if cache.exists() and not render:
        d = np.load(cache)
        res["V_sim"] = d["V"]
        res["V_coarse"] = d["Vc"] if "Vc" in d else None
        res["log"] = str(d["log"])
    elif cached_only:
        return None
    else:
        t = time.time()
        job_dir = out_dir or (_cache_dir() / f"job_{key}")
        stiff_s = interfacing(Bp, Ms)
        cfg = {"fabric": fab_s, "frames": int(frames or g.get("frames", 90)), "state": state, "name": name,
               "color": g.get("color", "#5b7fa6"), "render": render,
               "self_collision": bool(g.get("self_collision", True)), "trace": g.get("_trace", []),
               **{k: g[k] for k in ("sew_force", "sew_frames", "worn_frames", "settle_frames", "self_collision_sew",
                                    "hang_frames", "hang_sew_force") if k in g}}
        if g.get("assemble", True):
            cfg["assemble"] = _assembly(Bp, Ms, body)
        pins_of = None
        if hang:
            def pins_of(Mx, Xx):
                pins = [Mx["points"].get(p, Mx["marks"].get(p)) for p in state["hang"].get("pins", [])]
                if None in pins:
                    raise KeyError(f"hang pins: no such point/mark in {state['hang'].get('pins')}")
                # a hanger loop holds a patch, not a vertex: every vertex within `radius` of a pin (start positions)
                rad = float(state["hang"].get("radius", 0.03))
                return np.unique(np.concatenate([np.where(np.linalg.norm(Xx - Xx[p], axis=1) < rad)[0]
                                                 for p in pins]))
            cfg["pins"] = [int(i) for i in pins_of(Ms, Xs)]
            cfg["hook"] = state["hang"].get("hook")
            cfg["rack"] = state["hang"].get("rack")  # [[a, b, radius], ...] colliders (a coat rack's pole, arms)
            cfg["pin_spread"] = state["hang"].get("spread", 0.3)
        arrays = dict(X=Xs, uv=Ms["uv"], F=Ms["F"], sew=Ms["sew"], stitch=Ms["stitch"], stiff=stiff_s,
                      piece=Ms["piece"], bodyV=body.V, bodyT=body.T, pins=np.zeros(0, np.int64))
        progress(f"sim at {hs * 100:.1f} cm: {len(Xs)} verts")
        d, lines = _blender_job(job_dir, cfg, arrays, name, log, progress)
        Vs = d["V"]
        Vc = None
        if refine:
            Vc = Vs
            S = transfer(Ms, Vs, M)
            rcfg = {"mode": "refine", "fabric": fab, "self_collision": bool(g.get("self_collision", True)),
                    "refine_frames": int(g.get("refine_frames", 40)), "refine_ease": int(g.get("refine_ease", 15)),
                    "body": not hang}
            pins = np.zeros(0, np.int64)
            if hang:
                pins = pins_of(M, X0)
                rcfg["pins"] = [int(i) for i in pins]
                rcfg["rack"] = state["hang"].get("rack")
            progress(f"refine at {h * 100:.1f} cm: {len(X0)} verts")
            d2, lines2 = _blender_job(job_dir, rcfg, dict(X=X0, S=S, uv=M["uv"], F=M["F"], sew=M["sew"],
                                                          stitch=M["stitch"], stiff=interfacing(Bp, M),
                                                          bodyV=body.V, bodyT=body.T), name, log, progress)
            Vs = d2["V"]
            lines = lines + lines2
        res["V_sim"], res["V_coarse"] = Vs, Vc
        res["log"] = "\n".join(lines)
        log(f"cloth {name}: simulated in {time.time() - t:.0f} s")
        np.savez_compressed(cache, V=Vs, log=res["log"], **({"Vc": Vc} if Vc is not None else {}))
        if out_dir is None and not os.environ.get("HIFIPUSHIE_CLOTH_KEEP"):  # the job's files (MBs) go
            import shutil
            shutil.rmtree(job_dir, ignore_errors=True)
    Bp["push"] = push
    # the clean-up pass (what artists do in ZBrush/Blender after the sim): crinkle smoothed, big folds kept, seams
    # welded, the cloth kept off the body
    cu = g.get("cleanup", {})
    res["V"], res["cleanup"] = cleanup(res["V_sim"], M, None if hang else body,  # hung: the body is gone
                                       cu if isinstance(cu, dict) else {"smooth": 0}
                                       if cu is False else {}, stiff=interfacing(Bp, M))
    sc = g.get("sculpt")
    if sc and sc.get("key") == key:
        f = Path(sc["file"])
        if f.exists():
            off = np.load(f)["offset"]
            if off.shape == res["V"].shape:
                res["V"] = res["V"] + off
                res["sculpt_offset"] = off
                res["sculpted"] = int(np.sum(np.linalg.norm(off, axis=1) > 2e-4))
    elif sc:
        res["sculpt_stale"] = True  # hand edits made on another sim of this garment: not applied
    res["shape"] = {"sim": shape_numbers(res["V_sim"], M), "final": shape_numbers(res["V"], M)}
    res["fit"] = fit(res)
    res["integrity"] = integrity(res["V"], M, Bp, X0)
    ig_sim = integrity(res["V_sim"], M, Bp, X0)
    res["integrity"]["sim"] = {"self_intersections": ig_sim["self_intersections"],
                               "corrupt_pieces": ig_sim["corrupt_pieces"],
                               "crumpled": {p: v["crumpled"] for p, v in ig_sim["pieces"].items() if v["crumpled"] > 0.01}}
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


# ---------------------------------------------------------------- clean-up


def _graph(M: dict) -> tuple[np.ndarray, np.ndarray]:
    """Undirected neighbour pairs of the cloth: triangle edges plus seam pairs (the two sides of a seam smooth as one
    surface)."""
    F = M["F"]
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    # (not the button stitches: they join two layers lying on each other, which smoothing would pull together)
    E = np.unique(np.sort(np.r_[E, M["sew"]], 1), axis=0)
    return E[:, 0], E[:, 1]


def _laplace(V: np.ndarray, a: np.ndarray, b: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    S = np.zeros_like(V)
    n = np.zeros(len(V))
    np.add.at(S, a, V[b])
    np.add.at(S, b, V[a])
    np.add.at(n, a, 1)
    np.add.at(n, b, 1)
    L = S / np.maximum(n, 1)[:, None] - V
    return L if w is None else L * w[:, None]


def taubin(V: np.ndarray, M: dict, n: int, lam: float = 0.5, mu: float = -0.53, w=None) -> np.ndarray:
    a, b = _graph(M)
    X = V.copy()
    for _ in range(n):
        X = X + lam * _laplace(X, a, b, w)
        X = X + mu * _laplace(X, a, b, w)
    return X


def shape_numbers(V: np.ndarray, M: dict) -> dict:
    """What the surface reads as, in numbers an artist judges by eye: crinkle (the median angle between neighbouring
    triangles inside the pieces, deg: fine sim noise and frozen buckles; ~2-4 reads smooth at 1 cm, 6+ crinkled),
    crinkle_mm (rms of what 3 Taubin passes remove: the sub-3-edge waviness), folds_mm (rms height of the folds:
    the surface against itself smoothed over ~15 cm; a few mm = flat/shrink-wrapped, 10+ = clear folds)."""
    F = M["F"]
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    tid = np.tile(np.arange(len(F)), 3)
    key = np.sort(E, 1)
    o = np.lexsort((key[:, 1], key[:, 0]))
    ks, ts = key[o], tid[o]
    same = np.all(ks[1:] == ks[:-1], axis=1)
    t1, t2 = ts[:-1][same], ts[1:][same]
    ang = np.degrees(np.arccos(np.clip(np.sum(n[t1] * n[t2], 1), -1, 1)))
    inner = ~M["border"]
    hi = taubin(V, M, 3)
    h = float(np.median(np.linalg.norm(V[F[:, 0]] - V[F[:, 1]], axis=1)))
    lo = taubin(V, M, int(np.clip(round((0.15 / (0.7 * max(h, 1e-3))) ** 2), 10, 600)), lam=0.5, mu=0.0)  # plain Laplacian: removes the folds too (Taubin would keep them)
    # along the smoothed surface's normal only: plain smoothing also slides the cloth in its own plane (open edges
    # pull in), which isn't a fold
    fl = np.cross(lo[F[:, 1]] - lo[F[:, 0]], lo[F[:, 2]] - lo[F[:, 0]])
    vn = np.zeros_like(lo)
    for k in range(3):
        np.add.at(vn, F[:, k], fl)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
    d_lo = np.abs(np.sum((V - lo) * vn, 1))[inner]
    d_hi = np.abs(np.sum((V - hi) * vn, 1))[inner]
    return {"crinkle_deg": round(float(np.median(ang)), 2), "crinkle_p90_deg": round(float(np.percentile(ang, 90)), 1),
            "crinkle_mm": round(float(np.sqrt(np.mean(d_hi ** 2)) * 1000), 2),
            "folds_mm": round(float(np.sqrt(np.mean(d_lo ** 2)) * 1000), 1)}


CLEANUP = {"smooth": 4, "weld": True, "clear": 0.003, "keep": 0.004}


def cleanup(V: np.ndarray, M: dict, body: "Body", opts: dict, stiff: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """The pass artists make after the sim: the fine crinkle (frozen buckles a triangle or two across) smoothed away by
    Taubin passes (a band-limited smoothing that doesn't shrink the cloth: the folds, many triangles across, stay),
    seams welded (both sides at their midpoint), and anything the smoothing pulled toward the body pushed back out to
    `clear`. opts: {"smooth": passes (0 = off), "weld": bool, "clear": m, "keep": m}. stiff (per vertex 0..1, the
    interfacing): interfaced pieces (collars, cuffs, plackets) aren't smoothed: they don't crinkle, and smoothing
    their tight folds and overlaps crumpled them (a cuff 2 -> 6%)."""
    o = dict(CLEANUP, **(opts or {}))
    X = np.asarray(V, float).copy()
    # passes are for 1 cm triangles: a smoothing's reach grows with the edge length times sqrt(passes)
    h = float(np.median(np.linalg.norm(X[M["F"][:, 0]] - X[M["F"][:, 1]], axis=1)))
    n = int(round(float(o["smooth"]) * min(1.0, (0.01 / max(h, 1e-4)) ** 2)))
    if n > 0:
        S = taubin(X, M, n, w=None if stiff is None else np.clip(1 - stiff, 0, 1))
        # never more than `keep` from the sim's surface: crinkle is a few mm deep, a move past that flattens a fold
        D = S - X
        L = np.linalg.norm(D, axis=1)
        cap = float(o["keep"])
        X = X + D * np.minimum(1.0, cap / np.maximum(L, 1e-12))[:, None]
    if o["weld"] and len(M["sew"]):
        s = M["sew"]
        # only seams the sim closed (a gap over 1.5 triangles is a seam it couldn't close: welding it drags cloth)
        s = s[np.linalg.norm(X[s[:, 0]] - X[s[:, 1]], axis=1) < 1.5 * h]
        mid = 0.5 * (X[s[:, 0]] + X[s[:, 1]])
        X[s[:, 0]] = mid
        X[s[:, 1]] = mid
    if o["clear"] and body is not None and len(body.V):
        vn, tree = body.normals()
        _, i = tree.query(X)
        s_ = np.sum((X - body.V[i]) * vn[i], 1)
        bad = s_ < o["clear"]
        bad &= np.linalg.norm(X - body.V[i], axis=1) < 0.05  # only near the body (far vertices: a hang, a drape)
        if bad.any():
            X[bad] = body.push_out(X[bad], o["clear"])
    moved = np.linalg.norm(X - V, axis=1)
    return X, {"passes": n, "moved_p95_mm": round(float(np.percentile(moved, 95) * 1000), 2),
               "moved_max_mm": round(float(moved.max() * 1000), 2)}


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
        # candidate pairs: an edge can only cross a triangle whose centre is within its half length + the triangle's
        # radius. One search radius for all from the largest of each overshot by orders of magnitude on a start with a
        # few stretched triangles (70M pairs, 11 s a call): typical triangles by a tree over their centres with each
        # edge's own radius, the few big ones (> 3x the median) against the edges' midpoints
        big = rad > 3 * np.median(rad)
        sm = np.where(~big)[0]
        r_sm = float(rad[sm].max()) if len(sm) else 0.0
        pairs = cKDTree(cen[sm]).query_ball_point(mid, r=half + r_sm, return_sorted=False) if len(sm) else [[]] * len(ue)
        ei = np.repeat(np.arange(len(ue)), [len(c) for c in pairs])
        ti = sm[np.fromiter((t for c in pairs for t in c), dtype=np.int64, count=len(ei))]
        bi = np.where(big)[0]
        if len(bi):
            eb = cKDTree(mid).query_ball_point(cen[bi], r=rad[bi] + float(half.max()), return_sorted=False)
            ti = np.r_[ti, np.repeat(bi, [len(c) for c in eb])]
            ei = np.r_[ei, np.fromiter((e for c in eb for e in c), dtype=np.int64, count=sum(len(c) for c in eb))]
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
    # the sim's own surface: strain is physics (the clean-up's smoothing and welds aren't the fabric stretching)
    V, M, body, fab = res.get("V_sim", res["V"]), res["mesh"], res["body"], res["fabric"]
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
    for reg in (() if res.get("hung") else ("chest", "waist", "hips", "seat")):  # hung: no body to fit
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
    if not torso or "hps.L" not in body.at:
        return {"options": opts, "rows": rows}
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


class ClothError(ValueError):
    pass


GARMENT_KEYS = {"pattern", "pieces", "seams", "stitches", "drop", "alter", "fabric", "interfaced", "color", "roughness",
                "state", "resolution", "coarse", "quality", "frames", "self_collision", "self_collision_sew", "assemble",
                "sew_force", "sew_frames", "worn_frames", "settle_frames", "hang_frames", "hang_sew_force", "refine_frames",
                "refine_ease", "cleanup", "detail", "sculpt", "note", "_trace"}
WRAPS = ("torso", "arm.L", "arm.R", "neck", "flat")


def _is_hex(c) -> bool:
    return isinstance(c, str) and len(c.lstrip("#")) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in c.lstrip("#"))


def validate(spec: dict) -> None:
    """Cheap checks of spec["cloth"] (no draft, no sim): every key known, designs/fabrics/wraps/states that exist,
    numbers in range. Raises ClothError naming the garment and the key."""
    gs = spec.get("cloth")
    if gs is None:
        return
    if not isinstance(gs, dict):
        raise ClothError('cloth is {garment name: garment}, e.g. {"shirt": {"pattern": {"from": "simon"}}}')
    names = [k for k in designs() if not k.startswith("_")]
    for gn, g in gs.items():
        where = f"cloth {gn!r}"
        if not isinstance(g, dict):
            raise ClothError(f"{where}: a garment is an object (pattern or pieces + seams, fabric, state...)")
        bad = set(g) - GARMENT_KEYS
        if bad:
            raise ClothError(f"{where}: unknown keys {sorted(bad)} (have {', '.join(sorted(GARMENT_KEYS - {'_trace'}))})")
        pat = g.get("pattern")
        if pat is None and not g.get("pieces"):
            raise ClothError(f'{where}: needs "pattern": {{"from": design}} ({", ".join(names)}) or own "pieces" + "seams"')
        if pat is not None:
            if not isinstance(pat, dict) or pat.get("from") not in names:
                raise ClothError(f'{where}: pattern is {{"from": one of {names}, "ease": {{...}}, "length"...}}')
            words = designs()[pat["from"]].get("words", {})
            okp = {"from", "ease", "options", "measurements", "alterations", "sa"} | set(words)
            bad = set(pat) - okp
            if bad:
                raise ClothError(f"{where}: pattern keys {sorted(bad)} unknown for {pat['from']} (have {sorted(okp)})")
            for k, v in (pat.get("ease") or {}).items():
                if k not in words.get("ease", {}):
                    raise ClothError(f"{where}: no ease at {k!r} for {pat['from']} (have {', '.join(words.get('ease', {}))})")
                if not isinstance(v, (int, float)) or not -0.3 < v < 1.5:
                    raise ClothError(f"{where}: ease {k} is a fraction of the body measurement (-0.3..1.5), got {v!r}")
        f = g.get("fabric", "shirting")
        if isinstance(f, str):
            if f not in FABRICS:
                raise ClothError(f"{where}: no fabric {f!r} (have {', '.join(FABRICS)})")
        elif isinstance(f, dict):
            if f.get("preset", "shirting") not in FABRICS:
                raise ClothError(f"{where}: fabric preset {f.get('preset')!r} unknown (have {', '.join(FABRICS)})")
            bad = set(f) - set(FABRICS["shirting"]) - {"preset", "quality", "sewing", "stiff_tension", "rest"}
            if bad:
                raise ClothError(f"{where}: fabric keys {sorted(bad)} unknown (have {sorted(FABRICS['shirting'])})")
        else:
            raise ClothError(f"{where}: fabric is a preset name or {{\"preset\", overrides}}")
        st = g.get("state", "worn")
        if isinstance(st, dict):
            if len(st) != 1 or next(iter(st)) not in ("hang", "drape"):
                raise ClothError(f'{where}: state is "worn", "hung", "draped", {{"hang": {{...}}}} or {{"drape": {{...}}}}')
            if "hang" in st:
                hg = st["hang"]
                if not isinstance(hg.get("pins"), list) or not hg["pins"]:
                    raise ClothError(f'{where}: hang needs "pins": ["piece:point", ...] (a named outline point or mark)')
                if not (isinstance(hg.get("hook"), list) and len(hg["hook"]) == 3):
                    raise ClothError(f'{where}: hang needs "hook": [x, y, z]')
                for r in hg.get("rack") or []:
                    if not (isinstance(r, list) and len(r) == 3 and len(r[0]) == 3 and len(r[1]) == 3):
                        raise ClothError(f"{where}: each rack collider is [[x, y, z], [x, y, z], radius]")
            else:
                ov = (st["drape"] or {}).get("over", "model")
                if ov not in ("model", "body"):
                    raise ClothError(f'{where}: drape "over" is "model" (its whole surface) or "body" (its base body)')
        elif st not in ("worn", "hung", "draped"):
            raise ClothError(f'{where}: state is "worn", "hung", "draped" or an object (see guide(topic="cloth"))')
        if st == "hung":
            raise ClothError(f'{where}: "hung" needs where: {{"hang": {{"pins": ["stand:bottomLeft"], "hook": [x, y, z], '
                             '"rack": [[a, b, r], ...]}}}')
        if g.get("quality", "final") not in ("draft", "final"):
            raise ClothError(f'{where}: quality is "draft" (one coarse sim, ~1 min) or "final" (coarse then refined)')
        for k, lo, hi in (("resolution", 0.004, 0.05), ("coarse", 0.008, 0.05)):
            if k in g and not (isinstance(g[k], (int, float)) and lo <= g[k] <= hi):
                raise ClothError(f"{where}: {k} is a triangle size in m ({lo}..{hi})")
        if "color" in g and not _is_hex(g["color"]):
            raise ClothError(f'{where}: color is "#rrggbb"')
        cu = g.get("cleanup")
        if cu is not None and cu is not False:
            if not isinstance(cu, dict) or set(cu) - set(CLEANUP):
                raise ClothError(f"{where}: cleanup is false or {{{', '.join(CLEANUP)}}} (defaults {CLEANUP})")
        dt = g.get("detail")
        if dt is not None and dt is not False:
            if not isinstance(dt, dict) or set(dt) - set(DETAIL):
                raise ClothError(f"{where}: detail is false or {{{', '.join(DETAIL)}}} (defaults {DETAIL})")
        for pn, pd in (g.get("pieces") or {}).items():
            to = (pd.get("wrap") or {}).get("to", "torso")
            if to not in WRAPS:
                raise ClothError(f"{where}: piece {pn!r} wrap to {to!r} unknown (have {', '.join(WRAPS)})")
        needs_body = bool(pat) or any((pd.get("wrap") or {}).get("to", "torso") != "flat"
                                      for pd in (g.get("pieces") or {}).values())
        if needs_body and not spec.get("base"):
            raise ClothError(f'{where}: pieces wrapped on a body need the model to have one ("base"); a tablecloth or a '
                             'blanket on a prop: pieces with "wrap": {"to": "flat", "at": [x, y, z]} and state "draped"')
        for s in g.get("seams") or []:
            if not (isinstance(s, list) and len(s) == 2):
                raise ClothError(f'{where}: each seam is [side, side], a side "piece:from>to" or a list of them')


def _state(g: dict) -> dict | str:
    st = g.get("state", "worn")
    if st == "draped":
        return {"drape": {}}
    return st


def model_body(name: str, spec: dict, g: dict) -> dict:
    """The collider a garment settles on: the model's base body (worn, hung: dressed on it first), or for a drape
    over the "model" the model's whole built surface (a table under a tablecloth, a bed under a blanket)."""
    st = _state(g)
    over = st["drape"].get("over", "model") if isinstance(st, dict) and "drape" in st else "body"
    if over == "body" and spec.get("base"):
        return body_mesh(spec=spec)
    from . import spec as specmod, store
    meta = store.build(name, int((st.get("drape") or {}).get("resolution", 192)) if isinstance(st, dict) else 192)
    z = np.load(store._dir(name) / "build" / "mesh.npz")
    se = specmod.expand_mirror(spec)
    J = {k: np.asarray(v["pos"], float) for k, v in se.get("joints", {}).items() if isinstance(v.get("pos"), list)}
    return {"V": np.asarray(z["verts"], float), "F": np.asarray(z["faces"]), "J": J, "key": f"model:{meta.get('key')}"}


def _garment_for_sim(g: dict) -> dict:
    """The garment as build() takes it: the named states turned into their objects."""
    out = dict(g)
    out["state"] = _state(g)
    return out


# ---------------------------------------------------------------- jobs (dress runs in the background)

_JOBS: dict = {}
_JLOCK = threading.Lock()


def progress_path(name: str, gname: str) -> Path:
    from . import store
    return store._dir(name) / f"cloth_{gname}.progress"


def _job_id(g: dict) -> str:
    return hashlib.sha1(json.dumps(g, sort_keys=True, default=str).encode()).hexdigest()[:10]


def status(name: str, gname: str, g: dict | None = None) -> dict:
    """{"state": "running" | "done" | "failed" | "idle", "lines": the last progress lines, "seconds"}."""
    with _JLOCK:
        j = _JOBS.get((name, gname))
    lines = []
    p = progress_path(name, gname)
    if p.exists():
        lines = p.read_text().splitlines()[-6:]
    if j is None:
        return {"state": "idle", "lines": lines}
    out = {"state": j["state"], "lines": lines, "seconds": round((j.get("end") or time.time()) - j["start"]),
           "stale": g is not None and j["id"] != _job_id(g)}
    if j.get("error"):
        out["error"] = j["error"]
    return out


def _run_job(name: str, gname: str, g: dict, jid: str) -> None:
    from . import store
    p = progress_path(name, gname)
    t0 = time.time()

    def say(s):
        with open(p, "a") as f:
            f.write(f"[{time.time() - t0:6.0f}s] {s}\n")
    try:
        spec = store.load(name)
        say(f"dressing {gname} ({g.get('quality', 'final')})")
        src = model_body(name, spec, g)
        res = build(_garment_for_sim(g), src, f"{name}:{gname}", log=say, progress=say)
        say(f"done: {res['fit']['verdict']}")
        state = "done"
        err = None
    except Exception as e:  # reported through status()
        import traceback
        say(f"FAILED: {type(e).__name__}: {e}")
        say(traceback.format_exc().splitlines()[-3] if traceback.format_exc() else "")
        state, err = "failed", f"{type(e).__name__}: {e}"
    with _JLOCK:
        j = _JOBS.get((name, gname))
        if j is not None and j["id"] == jid:
            j.update(state=state, end=time.time(), error=err)


def cached(name: str, spec: dict, gname: str):
    """The garment's built result if its sim is cached, else None (never simulates)."""
    g = spec["cloth"][gname]
    src = model_body(name, spec, g)
    return build(_garment_for_sim(g), src, f"{name}:{gname}", log=lambda *_: None, cached_only=True)


def dress(name: str, which: list | None = None, wait: float = 0.0) -> dict:
    """Start (in the background) the sims of the model's garments that aren't cached, then wait up to `wait` s.
    Returns {garment: status}."""
    from . import store
    spec = store.load(name)
    gs = spec.get("cloth") or {}
    which = list(which or gs)
    for gn in which:
        if gn not in gs:
            raise ClothError(f"no garment {gn!r} (have {', '.join(gs) or 'none'})")
    for gn in which:
        g = gs[gn]
        jid = _job_id(g)
        with _JLOCK:
            j = _JOBS.get((name, gn))
            if j is not None and j["id"] == jid and j["state"] in ("running", "done"):
                continue
        if cached(name, spec, gn) is not None:
            with _JLOCK:
                _JOBS[(name, gn)] = {"id": jid, "state": "done", "start": time.time(), "end": time.time()}
            continue
        progress_path(name, gn).write_text("")
        with _JLOCK:
            _JOBS[(name, gn)] = {"id": jid, "state": "running", "start": time.time()}
        threading.Thread(target=_run_job, args=(name, gn, g, jid), daemon=True, name=f"cloth {name}:{gn}").start()
    t = time.time()
    while time.time() - t < wait:
        if all(status(name, gn)["state"] != "running" for gn in which):
            break
        time.sleep(1.0)
    return {gn: status(name, gn, gs[gn]) for gn in which}


# ---------------------------------------------------------------- the report


def report(gname: str, res: dict) -> str:
    """The text an agent judges a garment by: verdict, sizing, fit, integrity, surface numbers, what was done."""
    L = [f"{gname}: {res['fit']['verdict']}"]
    sz = res["sizing"]["rows"]
    if sz:
        L.append("  ease from the flat pattern (garment - body at the tailor's girths; negative = TOO SMALL): "
                 + ", ".join(f"{k} {v['ease_mm']:+.0f} mm ({v['ease'] * 100:+.0f}%)" for k, v in sz.items()))
    fr = res["fit"]["regions"]
    if fr:
        lim = res["fabric"]["limit"]
        L.append(f"  on the body (settled girth, ease, strain p95 across front/back; limit {lim * 100:.0f}% + "
                 f"{SIM_NOISE * 100:.0f}% sim noise): " + ", ".join(
                     f"{k} {v['ease_mm']:+.0f} mm {100 * (v['strain_p95'] or 0):.1f}%" for k, v in fr.items()))
    f = res["fit"]
    L.append(f"  strain p95 {f['strain_p95'] * 100:.1f}% (seams and buttons left out), placement p95 "
             f"{f['placement_p95'] * 100:.1f}%, off the body > 5 cm: {f['float_share'] * 100:.0f}% of the cloth")
    ig = res["integrity"]
    cr = {p: v["crumpled"] for p, v in ig["pieces"].items() if v["crumpled"] > 0.01}
    L.append(f"  integrity: {ig['self_intersections']} crossings" + (
        f" ({', '.join(f'{k} {v}' for k, v in ig['crossing_pairs'].items())}; first at "
        f"{ig['crossing_at'][:3]})" if ig["self_intersections"] else "")
        + (f"; crumpled > 1%: {', '.join(f'{p} {v * 100:.0f}%' for p, v in cr.items())}" if cr else "; nothing crumpled")
        + (f"; twisted seams {ig['twisted_seams']}" if ig["twisted_seams"] else "")
        + f" (the sim before the clean-up: {ig['sim']['self_intersections']} crossings)")
    sh = res["shape"]
    L.append(f"  surface (sim -> final): crinkle {sh['sim']['crinkle_deg']} -> {sh['final']['crinkle_deg']} deg median "
             f"between neighbouring triangles (smooth cloth reads ~3-5), {sh['sim']['crinkle_mm']} -> "
             f"{sh['final']['crinkle_mm']} mm fine waviness; folds {sh['sim']['folds_mm']} -> {sh['final']['folds_mm']} mm "
             "(under ~3 reads shrink-wrapped, 8+ clear folds)")
    cu = res.get("cleanup") or {}
    L.append(f"  clean-up: {cu.get('passes', 0)} smoothing passes, moved p95 {cu.get('moved_p95_mm')} mm"
             + (f"; hand sculpt applied ({res['sculpted']} vertices moved)" if res.get("sculpted") else "")
             + ("; a hand sculpt from an earlier sim is NOT applied (the sim changed)" if res.get("sculpt_stale") else ""))
    M = res["mesh"]
    L.append(f"  mesh: {len(M['uv'])} verts, {len(M['F'])} triangles, {'coarse sim + refined' if res.get('refined') else 'one sim'}"
             + "; sim log: " + "; ".join(ln.replace("cloth: ", "") for ln in res.get("log", "").splitlines()[-3:]))
    if res["pieces"].get("push"):
        L.append(f"  start pushed off the body (mm, becomes rest stretch): {res['pieces']['push']}")
        bad = [p for p, v in res["pieces"]["push"].items() if v > 8 and p in res["pieces"]["pieces"]
               and res["pieces"]["pieces"][p]["wrap"].get("to") == "neck"]
        if bad:
            L.append(f"  HINT: {', '.join(bad)} started inside the neck/jaw (> 8 mm): the band is taller than this neck "
                     "allows and crumples; lower it (simon: pattern options collarStandWidth 0.045, default 0.08)")
    return "\n".join(L)


# ---------------------------------------------------------------- detail: seams, topstitching, hems, buttons

DETAIL = {"thread": None, "button": None, "seam": 0.0012, "seam_width": 0.0025, "allowance": 0.0006, "topstitch": 0.006, "stitch": 0.003,
          "stitch_gap": 0.0015, "stitch_depth": 0.0003, "hem": 0.02, "hem_height": 0.0007, "buttons": True,
          "texture": 2048}


def detail_maps(M: dict, uv: np.ndarray, side: float, g: dict, texture: int | None = None) -> dict:
    """The sewing details a garment artist sculpts or stamps after the sim, drawn from the pattern itself into maps on
    the flat-pattern atlas: a groove along every sewn edge with the seam allowance's ridge beside it, a dashed
    topstitch line `topstitch` in from every edge (seams and hems), a turned-up hem `hem` deep along free edges (the
    doubled cloth a little proud), and buttons (raised discs with four holes) on marks named button*, buttonholes as
    stitched slots. Returns {"height" (m, float), "normal" (uint8 RGB, tangent space +Y up the image), "cavity"
    (0..1, darkening in grooves), "thread" (0..1 where stitches show), "texels_per_m"}."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    o = dict(DETAIL, **(g.get("detail") or {}))
    T = int(texture or o["texture"])
    mpt = side / T  # metres per texel
    px = lambda q: (q[0] * T, (1 - q[1]) * T)
    sewn = np.zeros(len(M["uv"]), bool)
    if len(M["sew"]):
        sewn[M["sew"].ravel()] = True
    inside = Image.new("L", (T, T), 0)
    di = ImageDraw.Draw(inside)
    L = np.zeros((T, T), np.uint8)  # 1 seam edge, 2 free edge
    A = np.zeros((T, T), np.float32)  # arc length along the piece's outline (m): stitches are dashes along it
    for k in range(len(M["names"])):
        ring = np.where((M["piece"] == k) & M["border"])[0]
        if len(ring) < 3:
            continue
        di.polygon([px(uv[i]) for i in ring], fill=255)
        arc = 0.0
        for a, b in zip(ring, np.roll(ring, -1)):
            kind = 1 if (sewn[a] and sewn[b]) else 2
            pa, pb = np.array(px(uv[a])), np.array(px(uv[b]))
            n = int(np.ceil(np.linalg.norm(pb - pa) * 2)) + 1
            f = np.linspace(0, 1, n)
            q = pa[None] + f[:, None] * (pb - pa)[None]
            xi = np.clip(np.round(q[:, 0]).astype(int), 0, T - 1)
            yi = np.clip(np.round(q[:, 1]).astype(int), 0, T - 1)
            L[yi, xi] = kind
            seg = float(np.linalg.norm(uv[b] - uv[a])) * side
            A[yi, xi] = arc + f * seg
            arc += seg
    inside = np.asarray(inside) > 0
    dist, (iy, ix) = ndimage.distance_transform_edt(L == 0, return_indices=True)
    d = dist * mpt  # metres to the nearest edge
    kind = L[iy, ix]
    H = np.zeros((T, T), np.float32)
    seam = kind == 1
    free = kind == 2
    # a sewn edge: the groove where the two pieces meet, the allowance folded under beside it
    H -= np.where(seam, o["seam"] * np.exp(-(d / o["seam_width"]) ** 2), 0)
    H += np.where(seam, o["allowance"] * np.exp(-((d - 2.2 * o["seam_width"]) / (1.2 * o["seam_width"])) ** 2), 0)
    # a free edge: a turned hem, the doubled cloth proud up to `hem` in, its fold rounded at the edge
    if o["hem"]:
        hem = np.clip((o["hem"] - d) / (0.15 * o["hem"]), 0, 1) * np.clip(d / 0.0015, 0, 1)
        H += np.where(free, o["hem_height"] * hem, 0)
    # topstitching: a dashed line `topstitch` in from each edge, each stitch a small dent
    thread = np.zeros((T, T), np.float32)
    if o["topstitch"]:
        per = o["stitch"] + o["stitch_gap"]
        s = A[iy, ix] % per  # along the outline at the nearest edge point
        dash = np.clip((o["stitch"] - np.abs(2 * s - o["stitch"])) / (1.5 * mpt + 1e-9), 0, 1)
        dash = np.minimum(dash, 1.0).astype(np.float32)
        band = np.exp(-((d - o["topstitch"]) / max(0.0004, 1.2 * mpt)) ** 2)
        thread = band * dash
        H -= o["stitch_depth"] * thread
    # buttons and buttonholes on the pieces' marks
    btn = np.zeros((T, T), np.float32)
    if o["buttons"]:
        for nm, v in M["marks"].items():
            mk = nm.split(":", 1)[1]
            cx, cy = px(uv[v])
            if mk.startswith("button") and not mk.startswith("buttonhole"):
                r = 0.0055 / mpt
                yy, xx = np.ogrid[:T, :T]
                x0, x1, y0, y1 = int(cx - r - 2), int(cx + r + 3), int(cy - r - 2), int(cy + r + 3)
                sub = (slice(max(y0, 0), min(y1, T)), slice(max(x0, 0), min(x1, T)))
                rr = np.hypot(xx[:, sub[1]] - cx, yy[sub[0], :] - cy) / r
                bump = 0.0018 * np.sqrt(np.clip(1 - rr ** 2, 0, 1))
                for hx, hy in ((-0.28, -0.28), (0.28, -0.28), (-0.28, 0.28), (0.28, 0.28)):
                    hr = np.hypot(xx[:, sub[1]] - (cx + hx * r), yy[sub[0], :] - (cy + hy * r)) / (0.13 * r)
                    bump -= 0.0012 * np.clip(1 - hr ** 2, 0, 1)
                H[sub] = np.maximum(H[sub], bump)
                btn[sub] = np.maximum(btn[sub], (rr < 1).astype(np.float32))
            elif mk.startswith("buttonhole"):
                w, hh = 0.0075 / mpt, 0.0012 / mpt  # a slot along the placket (pattern y)
                yy, xx = np.ogrid[:T, :T]
                sub = (slice(max(int(cy - w - 3), 0), min(int(cy + w + 3), T)),
                       slice(max(int(cx - 3 * hh - 3), 0), min(int(cx + 3 * hh + 3), T)))
                ex = np.abs(xx[:, sub[1]] - cx)
                ey = np.abs(yy[sub[0], :] - cy)
                rim = (ey < w) & (ex < 2.5 * hh)
                slot = (ey < w * 0.9) & (ex < 0.6 * hh)
                H[sub] += np.where(rim, 0.0004, 0) - np.where(slot, 0.0012, 0)
                thread[sub] = np.maximum(thread[sub], np.where(rim & ~slot, 1.0, 0))
    H *= inside
    thread *= inside
    # normal from the height's slope (tangent space: +x along the image's u, +y up the image)
    gy, gx = np.gradient(H.astype(np.float64), mpt)
    n = np.dstack([-gx, gy, np.ones_like(gx)])  # image rows run down: up the image is -row
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    N = ((n * 0.5 + 0.5) * 255).round().astype(np.uint8)
    cav = np.clip(1 + H / 0.0015, 0.55, 1.0).astype(np.float32)
    btn *= inside
    return {"height": H, "normal": N, "cavity": cav, "thread": thread.astype(np.float32), "button": btn, "inside": inside,
            "texels_per_m": T / side}


def write_maps(path_stem: Path, M: dict, uv: np.ndarray, side: float, g: dict, texture: int | None = None) -> dict:
    """The garment's base colour (its colour, grooves darker, stitches in thread colour), normal and height PNGs
    from detail_maps. Returns {channel: path}."""
    from PIL import Image
    dm = detail_maps(M, uv, side, g, texture)
    rgb = np.array([int(g.get("color", "#8fb3d9").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], float)
    thread = np.array([int(((g.get("detail") or {}).get("thread") or g.get("color", "#8fb3d9")).lstrip("#")[i:i + 2], 16)
                       for i in (0, 2, 4)], float)
    if not (g.get("detail") or {}).get("thread"):
        thread = np.clip(rgb * 1.18 + 12, 0, 255)  # a shade lighter than the cloth (matched thread catches light)
    C = rgb[None, None] * dm["cavity"][..., None]
    t = dm["thread"][..., None] * 0.8
    C = C * (1 - t) + thread[None, None] * t
    button = np.array([int(((g.get("detail") or {}).get("button") or "#ebe6dc").lstrip("#")[i:i + 2], 16)
                       for i in (0, 2, 4)], float)
    b = dm["button"][..., None]
    C = C * (1 - b) + button[None, None] * dm["cavity"][..., None] * b
    out = {}
    out["basecolor"] = Path(f"{path_stem}_basecolor.png")
    Image.fromarray(np.clip(C, 0, 255).astype(np.uint8)).save(out["basecolor"])
    out["shade"] = Path(f"{path_stem}_shade.png")  # the detail's shading alone (the scene multiplies the colour by it)
    sh = dm["cavity"] * (1 - dm["thread"] * 0.8) + dm["thread"] * 0.8
    sh = sh * (1 - dm["button"]) + dm["button"] * dm["cavity"]
    Image.fromarray((np.clip(sh, 0, 1) * 255).astype(np.uint8)).save(out["shade"])
    out["normal"] = Path(f"{path_stem}_normal.png")
    Image.fromarray(dm["normal"]).save(out["normal"])
    out["height"] = Path(f"{path_stem}_height.png")
    hn = np.clip(0.5 + dm["height"] / 0.004, 0, 1)
    Image.fromarray((hn * 65535).astype(np.uint16)).save(out["height"])
    out["texels_per_m"] = dm["texels_per_m"]
    return out


# ---------------------------------------------------------------- the model: scene, sync, pull, export


def garments(name: str, spec: dict, log=print, simulate: bool = False) -> list:
    """Every garment of a model (spec["cloth"]: {name: garment}) settled on the model's body: (name, garment,
    result) for those whose sim is cached (dress runs them); simulate=True runs the missing ones here (export)."""
    out = []
    for gname, g in (spec.get("cloth") or {}).items():
        src = model_body(name, spec, g)
        res = build(_garment_for_sim(g), src, f"{name}:{gname}", log=log, cached_only=not simulate)
        if res is None:
            log(f"cloth {gname}: not simulated yet (dress the model first): left out")
            continue
        log(f"cloth {gname}: {res['fit']['verdict']}")
        out.append((gname, g, res))
    return out


def scene_job(name: str, spec: dict, log: list | None = None) -> list:
    """What blender_cloth.show needs per garment: its settled mesh + pattern uv (+ detail maps) in files beside the
    model. Only garments already simulated (dress) go in: a sync never starts a sim."""
    from . import store
    say = (log.append if isinstance(log, list) else print)
    entries = []
    for gname, g, res in garments(name, spec, say):
        uv, side = atlas_uv(res["mesh"])
        path = store._dir(name) / f"cloth_{gname}.npz"
        np.savez(path, verts=res["V"].astype(np.float32), faces=res["mesh"]["F"].astype(np.int32),
                 uv=uv.astype(np.float32), base=(res["V"] - _sculpt_offset(res)).astype(np.float32))
        e = {"name": f"cloth:{gname}", "garment": gname, "key": res["key"] + _detail_key(g, res), "npz": str(path),
             "color": g.get("color", "#8fb3d9"), "thickness": fabric(g).get("thickness", 0.0008),
             "roughness": float(g.get("roughness", 0.85))}
        if g.get("detail", {}) is not False:
            maps = write_maps(store._dir(name) / f"cloth_{gname}", res["mesh"], uv, side, g)
            e["maps"] = {k: str(v) for k, v in maps.items() if k != "texels_per_m"}
        entries.append(e)
    return entries


def _detail_key(g: dict, res: dict) -> str:
    """What the scene object is made from beyond the sim: clean-up, sculpt, detail, colour."""
    return ":" + hashlib.sha1(json.dumps([g.get(k) for k in ("cleanup", "sculpt", "detail", "color", "roughness")],
                                         sort_keys=True, default=str).encode()).hexdigest()[:8]


def _sculpt_offset(res: dict) -> np.ndarray:
    sc = res.get("sculpt_offset")
    return sc if sc is not None else np.zeros_like(res["V"])


def sync(name: str, log: list | None = None) -> dict:
    """Push the simulated garments into scene.blend (the person's live Blender when it has the scene open)."""
    from .scene import _blender, _blender_live, blend_path, live_session
    from . import store
    log = [] if log is None else log
    spec = store.load(name)
    t = time.time()
    entries = scene_job(name, spec, log)
    j = {"mode": "cloth_sync", "blend": str(blend_path(name)), "cloth": entries}
    out = _blender_live(j) if live_session(name) else _blender(j)
    made = next((json.loads(line[7:]) for line in out.splitlines() if line.startswith("@@made")), [])
    return {"made": made, "garments": [e["garment"] for e in entries], "seconds": round(time.time() - t, 1), "log": log}


def pull_garments(spec: dict, name: str, got: dict, log: list) -> dict:
    """What a person changed on the garments in the scene: their material colour/roughness, and their shape (a
    sculpt or clean-up pass in Blender: the moved vertices kept as offsets on top of this sim, `cloth.<g>.sculpt`;
    they're dropped when the sim changes, since they belong to its surface)."""
    from . import store
    changes = {}
    gs = spec.get("cloth") or {}
    for obj, st in (got or {}).items():
        gname = obj.split(":", 1)[1] if obj.startswith("cloth:") else obj
        g = gs.get(gname)
        if g is None:
            continue
        ch = {}
        if st.get("color"):
            g["color"] = st["color"]
            ch["color"] = st["color"]
        if st.get("roughness") is not None:
            g["roughness"] = round(float(st["roughness"]), 3)
            ch["roughness"] = g["roughness"]
        if st.get("verts"):
            z = np.load(store._dir(name) / f"cloth_{gname}.npz")
            Vnew = np.load(st["verts"])["verts"].astype(np.float64)
            base = z["base"].astype(np.float64)
            if Vnew.shape == base.shape:
                off = Vnew - base
                f = store._dir(name) / f"cloth_{gname}_sculpt.npz"
                np.savez_compressed(f, offset=off.astype(np.float32))
                key = st.get("key", "").split(":")[0]
                g["sculpt"] = {"file": str(f), "key": key,
                               "moved": int(np.sum(np.linalg.norm(off, axis=1) > 2e-4))}
                ch["sculpt"] = g["sculpt"]["moved"]
                log.append(f"cloth {gname}: {g['sculpt']['moved']} vertices sculpted in Blender kept as offsets")
            else:
                log.append(f"cloth {gname}: the scene's mesh has another vertex count (remeshed?): its shape isn't pulled")
        if ch:
            changes[f"cloth.{gname}"] = ch
    return changes


def export_part(name: str, spec: dict, out_dir, texture: int = 1024, log=print) -> list:
    """The garments as export parts (as asset.lowpoly makes them: verts, corner_vert, uv, normal, tangent, sign) and
    their maps. Two-sided: the outer face and an inner one a cloth's thickness in (a coat open at the front shows
    its inside). The uv is the flat pattern (`atlas_uv`); the maps carry the sewing detail drawn from the pattern
    (`detail_maps`: seam grooves, topstitching, hems, buttons) in the base colour and the normal map."""
    from PIL import Image
    from . import hair as hairmod
    out_dir = Path(out_dir)
    parts = []
    for gname, g, res in garments(name, spec, log, simulate=True):
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
        body = res["body"]
        _, ni = cKDTree(body.V).query(V)
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
        files = {"orm": out_dir / f"cloth_{gname}_orm.png", "specular": out_dir / f"cloth_{gname}_specular_gltf.png"}
        if g.get("detail", {}) is not False:
            maps = write_maps(out_dir / f"cloth_{gname}", M, uv, side, dict(g, detail=dict(g.get("detail") or {},
                                                                                        texture=texture)), texture)
            files["basecolor"], files["normal"] = maps["basecolor"], maps["normal"]
        else:
            rgb = tuple(int(g.get("color", "#8fb3d9").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            files["basecolor"] = out_dir / f"cloth_{gname}_basecolor.png"
            Image.new("RGB", (16, 16), rgb).save(files["basecolor"])
            files["normal"] = out_dir / f"cloth_{gname}_normal.png"
            Image.new("RGB", (16, 16), (128, 128, 255)).save(files["normal"])
        rough = int(255 * float(g.get("roughness", 0.85)))
        Image.new("RGB", (16, 16), (255, rough, 0)).save(files["orm"])
        Image.new("RGBA", (16, 16), (255, 255, 255, 128)).save(files["specular"])
        log(f"cloth {gname}: {len(Fall)} triangles (two-sided), pattern uv at {texture / side:.0f} texels/m")
        parts.append((f"cloth_{gname}", part, files))
    return parts


# ---------------------------------------------------------------- looks


def _cylinder(a, b, r, n=20):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    u = np.cross(d, [1, 0, 0] if abs(d[0]) < 0.9 else [0, 1, 0])
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.outer(np.cos(ang), u) + np.outer(np.sin(ang), v)
    V = np.r_[a + r * ring, b + r * ring]
    F = [[i, (i + 1) % n, n + (i + 1) % n] for i in range(n)] + [[i, n + (i + 1) % n, n + i] for i in range(n)]
    return V, np.array(F)


def look(name: str, which: list | None = None, views=("front", "side", "back", "three"), strain: bool = True,
         size: int = 640, focus=None, zoom: float = 0.4, body: bool = True, textured: bool = False):
    """Renders of the model's simulated garments on their body (clay, each garment its colour) + the strain map, and
    the text report per garment. focus: [x, y, z] or "garment:piece" (that piece's middle) with zoom m across: a
    close-up. textured: EEVEE with the detail maps (seams, topstitching, hems, buttons) instead of clay.
    Returns (sheet PIL image, text)."""
    from PIL import Image, ImageDraw
    from . import store
    spec = store.load(name)
    gs = spec.get("cloth") or {}
    which = list(which or gs)
    texts, objs, results = [], [], []
    src = None
    for gn in which:
        if gn not in gs:
            raise ClothError(f"no garment {gn!r} (have {', '.join(gs) or 'none'})")
        res = cached(name, spec, gn)
        if res is None:
            st = status(name, gn, gs[gn])
            texts.append(f"{gn}: not simulated ({st['state']}" + (f": {st['lines'][-1]}" if st["lines"] else "")
                         + ") - dress it first")
            continue
        results.append((gn, gs[gn], res))
        texts.append(report(gn, res))
        src = res["body"]
    if not results:
        return None, "\n".join(texts)
    bod = results[0][2]["body"]
    hung = [g for _, g, _ in results if isinstance(_state(g), dict) and "hang" in _state(g)]
    if hung and len(hung) == len(results):  # hung garments: the body is gone, the rack shows
        body = False
        for k, (a, b, r) in enumerate([c for g in hung for c in (_state(g)["hang"].get("rack") or [])]):
            V, F = _cylinder(a, b, r)
            objs.append({"name": f"rack{k}", "V": V, "F": F, "color": "#8a6b45"})
    if body and len(bod.V):
        objs.append({"name": "body", "V": bod.V, "F": bod.T, "color": "#d9c3b0"})
    tmp = store._dir(name) / "_cloth_look"
    tmp.mkdir(exist_ok=True)
    for gn, g, res in results:
        o = {"name": f"g_{gn}", "V": res["V"], "F": res["mesh"]["F"], "color": g.get("color", "#8fb3d9"),
             "thickness": max(0.0006, fabric(g).get("thickness", 0.0008))}
        if textured and g.get("detail", {}) is not False:
            uv, side = atlas_uv(res["mesh"])
            maps = write_maps(tmp / f"look_{gn}", res["mesh"], uv, side, g)
            o.update(uv=uv, maps={k: str(v) for k, v in maps.items() if k != "texels_per_m"})
        objs.append(o)
    allV = np.concatenate([o["V"] for o in objs])
    box = (allV.min(0) - 0.05, allV.max(0) + 0.05)
    if focus is not None:
        if isinstance(focus, str):
            gn, pc = focus.split(":", 1) if ":" in focus else (results[0][0], focus)
            r = next((r for n_, _, r in results if n_ == gn), None)
            if r is None or pc not in r["mesh"]["names"]:
                raise ClothError(f"focus {focus!r}: give [x, y, z] or 'garment:piece' (pieces: "
                                 f"{', '.join(results[0][2]['mesh']['names'])})")
            c = r["V"][r["mesh"]["piece"] == r["mesh"]["names"].index(pc)].mean(0)
        else:
            c = np.asarray(focus, float)
        box = (c - zoom / 2, c + zoom / 2)
    vs = [v if v != "three" else {"name": "three", "dir": [-0.65, -0.72, 0.25]} for v in views]
    vs = [v if v != "three_back" else {"name": "three_back", "dir": [0.65, 0.72, 0.25]} for v in vs]
    aspect = 1.0 if focus is not None else 0.62
    paths = render(objs, tmp / "look", views=vs, resolution=size, box=box, aspect=aspect, textured=textured)
    ims = [Image.open(p).convert("RGB") for p in paths]
    rows = [ims]
    if strain:
        so = []
        for o in objs:
            if o["name"].startswith("g_"):
                gn = o["name"][2:]
                res = next(r for n_, _, r in results if n_ == gn)
                o = dict(o, C=strain_colors(res["fit"]["vertex_strain"], res["fabric"]["limit"]))
                o.pop("maps", None)
            so.append(o)
        sv = [v for v in vs if (v if isinstance(v, str) else v["name"]) in ("front", "back")] or vs[:1]
        sp = render(so, tmp / "strain", views=sv, resolution=size, box=box, aspect=aspect)
        rows.append([Image.open(p).convert("RGB") for p in sp])
    W = max(sum(i.width for i in r) for r in rows)
    Hh = sum(r[0].height for r in rows) + 26 * len(rows)
    sheet = Image.new("RGB", (W, Hh), (60, 60, 60))
    d = ImageDraw.Draw(sheet)
    y = 0
    labels = ["garment" + (" (textured)" if textured else " (clay)"),
              "strain against the rest shape: blue slack, green fine, yellow at the fabric's limit, red 2x"]
    for k, r in enumerate(rows):
        d.text((8, y + 6), labels[k] if k < len(labels) else "", fill=(255, 255, 255))
        y += 26
        x = 0
        for im in r:
            sheet.paste(im, (x, y))
            x += im.width
        y += r[0].height
    for p in paths:
        Path(p).unlink(missing_ok=True)
    return sheet, "\n".join(texts)


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
           aspect: float = 0.62, textured: bool = False) -> list:
    """objects: [{"name", "V", "F", "color" | "C" (linear RGB per vertex), "thickness", "uv"?, "maps"?}] -> PNG paths.
    textured: EEVEE with each object's maps (basecolor, normal) on its uv; else workbench clay."""
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
        if o.get("uv") is not None:
            data[o["name"] + "_UV"] = np.asarray(o["uv"], np.float32)
        objs.append({k: v for k, v in o.items() if k in ("name", "color", "thickness", "maps")})
    tag = Path(prefix).name
    np.savez(d / f"_{tag}_render.npz", **data)
    job = {"mode": "render", "data": f"_{tag}_render.npz", "objects": objs, "out_prefix": prefix,
           "views": list(views), "resolution": resolution, "aspect": aspect, "textured": bool(textured),
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
