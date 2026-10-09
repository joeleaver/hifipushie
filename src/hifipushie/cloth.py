"""Garments built like a tailor builds them: pattern pieces drafted from the body's measurements, sewn round the body
and settled by Blender's cloth simulation (sewing springs), then checked for fit.

Spec `spec["cloth"][name]`:
  {"pattern": {"from": FreeSewing design ("simon", "carlton"...),
               "ease": {"chest": 0.12, ...} (fraction of the body measurement), "length", "sleeve_length",
               "options": {raw FreeSewing options}, "measurements": {overrides, mm} (a fixed size instead of the body's)},
   "pieces": {name: piece spec (pattern.from_spec) + "wrap"}, "seams": [[a, b], ...], "stitches": [[a, b]...]
             (own pieces, or added to a design's), "drop": [pieces of the design left out],
   "alter": [pattern ops], "fabric": preset name or {...}, "interfaced": [pieces], "color": "#rrggbb",
   "state": "worn" | "hung" (on a hanger: hanger.py) | {"hang": {"hanger": {...}, "rail": {...}}} | "draped",
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
HANGER_SKIN = 0.25  # the hanger's collision skin in triangle sizes (5 mm at 2 cm; 1 cm held a coat 4 cm up, bouncing)
HOOK_GUARD = 0.4  # the hook's rod as the sim sees it: this many coarse triangle sizes thick (8 mm at 2 cm)
SIM_MIN_FREE_GB = 20.0  # a cloth sim isn't started with less free disk (run_zozo.py also stops a run under 10 GB)
PREV_APART = 6  # frames between the sim's last positions and Vprev (the "still moving" measure)
VERSION = 2  # bump with any change to the mesh, placement or sim job: results are cached by it

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


def expanded(g: dict) -> dict:
    """The garment with its design sheet (garment_design: the staged workflow's stage 1) compiled into the ordinary
    garment keys (pattern, fabric, folds, generate, detail...); keys written on the garment itself win."""
    if g.get("design"):
        from . import garment_design
        return garment_design.expand(g)
    return g


def fabric(g: dict) -> dict:
    g = expanded(g)
    f = g.get("fabric", "shirting")
    if isinstance(f, str):
        if f not in FABRICS:
            raise ValueError(f"no fabric {f!r} (have {', '.join(FABRICS)})")
        return dict(FABRICS[f], name=f)
    base = dict(FABRICS[f.get("preset", "shirting")])
    base.update({k: v for k, v in f.items() if k != "preset"})
    return dict(base, name=f.get("preset", "custom"))


# ---------------------------------------------------------------- pieces


def collar_options(tbl: dict, opts: dict, m: dict) -> dict:
    """A shirt collar's draft options from the wearer's neck (garment_kb.json kinds.<kind>.collar; the table's
    "collar_rule" names how its draft spells them: "simon" = FreeSewing Simon's options). The stand as tall as the
    neck allows less a finger's room under the jaw (`under_jaw`), within the shirtmakers' 25-35 mm, never under
    `stand[0]`; the fall at centre back `fall_over` deeper than the stand (it must cover the stand's seam); the points
    `points` long. (Simon's defaults gave a 20 mm stand, a 41 mm fall and 57 mm points: "tall, tight, small points".)
    Simon: stand = neck x collarStandWidth; fall at CB = stand x collarWidth x (1 + collarRoll); a point's edge
    ~ (fall + collar length x collarBend) / sin(collarAngle), collar length = neck x (1 + collarEase - collarGap)."""
    from . import garment_design
    rule = ((garment_design.kb().get("kinds") or {}).get(tbl.get("kind")) or {}).get("collar")
    neck, nh = m.get("neck"), m.get("neckHeight")
    if not rule or not neck or not nh or tbl.get("collar_rule") != "simon":
        return {}
    s = float(np.clip(nh - 1000 * rule["under_jaw"], 1000 * rule["stand"][0], 1000 * rule["stand"][1]))
    f = s + 1000 * rule["fall_over"]
    roll = float(opts.get("collarRoll", 0.03))
    L = neck * (1 + float(opts.get("collarEase", 0.02)) - float(opts.get("collarGap", 0.025)))
    ang = math.radians(float(opts.get("collarAngle", 85)))
    fl = math.radians(float(opts.get("collarFlare", 3.5)))

    def point(bend):  # Simon's collar.mjs: the end edge from the bottom corner up to the top edge's line
        bx, by = L / 2, f + L * bend  # (y down, angles up)
        hx = L / 4
        # hinge + t (cos fl, -sin fl) = bottom + u (cos ang, -sin ang)
        A = np.array([[math.cos(fl), -math.cos(ang)], [-math.sin(fl), math.sin(ang)]])
        t_, u_ = np.linalg.solve(A, [bx - hx, by])
        return abs(u_)
    lo, hi = 0.0, 0.10
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if point(mid) < 1000 * rule["points"] else (lo, mid)
    return {"collarStandWidth": round(s / neck, 4),
            "collarWidth": round(float(np.clip(f / (s * (1 + roll)), 0.9, 2.0)), 3),
            "collarBend": round(0.5 * (lo + hi), 4)}


def pieces(g: dict, meas_mm: dict) -> dict:
    """{"pieces": {name: piece (+ "wrap")}, "seams", "stitches", "interfaced", "draft"}."""
    out, seams, stitches, interfaced, draft_info = {}, [], [], [], None
    g = expanded(g)
    pat = g.get("pattern")
    gen, folds_tbl, seam_notes = [], [], {}
    closures_in = []
    from . import garment_blocks
    if pat and pat.get("from") in garment_blocks.BLOCKS:  # our own drafts (a skirt block): pieces + seams
        m = dict(meas_mm)
        m.update(pat.get("measurements") or {})
        bo = dict(pat.get("options") or {}, **{k: v for k, v in pat.items() if k not in ("from", "options", "measurements")})
        blk = garment_blocks.draft(pat["from"], m, bo)
        out, seams, stitches, interfaced = dict(blk["pieces"]), list(blk["seams"]), list(blk["stitches"]), list(blk["interfaced"])
        draft_info = blk["draft"]
        gen = list(blk.get("generate") or [])
        folds_tbl += blk.get("folds") or []
        closures_in += [dict(c) for c in blk.get("closures") or []]
        seam_notes = dict(blk.get("seam_notes") or {})
        pat = None
    if pat:
        from . import freesewing
        tbl = designs().get(pat["from"])
        if tbl is None:
            raise ValueError(f"no design table for {pat['from']!r} in cloth_designs.json (have "
                             f"{', '.join(k for k in designs() if not k.startswith('_'))})")
        m = dict(meas_mm)
        m.update(pat.get("measurements") or {})
        opts = dict(tbl.get("options") or {})  # the table's own draft defaults (a collar wide enough to cover its stand)
        if tbl.get("collar_rule"):  # the collar's proportions from the body's neck (garment_kb kinds.<kind>.collar)
            opts.update(collar_options(tbl, opts, m))
        opts.update(pat.get("options") or {})
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
            if pd.get("flip_y"):
                pc = pattern.mirror_y(pc)
            pc["wrap"] = dict(pd.get("wrap") or {})
            if pd.get("role"):
                pc["role"] = pd["role"]
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
        # a table seam's declared ease ("seam_notes": [{"seam": n (its index in the table), "ease": [lo, hi], "why"}]:
        # what a draft's own notes are for drafted garments)
        for n_ in tbl.get("seam_notes") or []:
            seam_notes[json.dumps(tbl["seams"][int(n_["seam"])])] = {"ease": list(n_["ease"]), "why": n_["why"]}
        stitches += tbl.get("stitches", [])
        interfaced += tbl.get("interfaced", [])
        folds_tbl += tbl.get("folds", [])
        closures_in += [dict(c) for c in tbl.get("closures", [])]
    for nm, pd in (g.get("pieces") or {}).items():
        pc = pattern.from_spec(nm, pd)
        pc["wrap"] = dict(pd.get("wrap") or {})
        if pd.get("role"):
            pc["role"] = pd["role"]
        out[nm] = pc
    for nm in g.get("drop", []):
        out.pop(nm, None)
    out = pattern.apply(out, g.get("alter"))
    seams += g.get("seams", [])
    stitches += g.get("stitches", [])
    # generated pieces (garment_blocks.generate: bands sized from the drafted edges they're sewn to)
    for e in gen + list(g.get("generate") or []):
        if any(x.split(":")[0] not in out for x in ([e.get("along")] if isinstance(e.get("along"), str) else e.get("along") or [])):
            continue  # what it is sewn to was dropped
        p_, s_, st_, i_ = garment_blocks.generate(out, e)
        out.update(p_)
        seams += s_
        stitches += st_
        interfaced += i_
    interfaced = interfaced + [e for e in g.get("interfaced", []) if e not in interfaced]
    # closures (closures.py): a lap held by fastenings; the garment's entry of a name is laid over the table's /
    # the draft's key by key (so {"name": "collar", "state": "open"} is how a garment is WORN: top button undone;
    # {"name": "front", "state": "open"}: a jacket hanging open), a new name is a new closure
    from . import closures as closuremod
    from . import garment_design as gdmod
    for c in gdmod.wear(g) + list(g.get("closures") or []):  # how the kind is worn (no tie: collar open), then the garment's own
        if not any(o.get("name") == c.get("name") for o in closures_in) and not c.get("over"):
            continue  # (a wear rule for a closure this pattern hasn't got)
        base = next((o for o in closures_in if o.get("name") == c.get("name")), {})
        closures_in = [o for o in closures_in if o.get("name") != c.get("name")] + [dict(base, **c)]
    # how the kind finishes a lapped closure (garment_kb kinds.<k>.closure: a shirt's box placket over a French
    # front, a jacket's faced fronts with horizontal holes), under the closure's own keys; self-closures (cuffs,
    # stands, waistbands) keep the defaults
    kd_ = _kb()["kinds"].get(garment_kind(g) or "", {}).get("closure") or {}
    if kd_:
        closures_in = [dict({k_: v_ for k_, v_ in kd_.items() if not k_.startswith("_")}, **c)
                       if c.get("over") and c.get("under", c["over"]) != c["over"] else c for c in closures_in]
    closuremod.validate(closures_in)
    st_c, folds_c, seams_c, closures_out = closuremod.expand(closures_in, out)
    stitches += [s_ for s_ in st_c if s_ not in stitches]
    seams += seams_c
    folds_tbl += folds_c
    keep = set(out)
    side_ok = lambda s: all(e.split(":")[0] in keep for e in ([s] if isinstance(s, str) else s))
    seams = [s for s in seams if side_ok(s[0]) and side_ok(s[1])]
    stitches = [s for s in stitches if side_ok(s[0]) and side_ok(s[1])]
    # fold lines (cloth_guide "Fold lines"): the design table's own, then the garment's
    folds = [dict(f) for f in folds_tbl]
    # how the kind is worn may roll pieces back (no tie: the fronts above the first closed button roll open in a V)
    for f in gdmod.wear(g, "folds"):
        pc_ = out.get(f.get("piece"))
        if pc_ is not None and all(isinstance(q, str) and (q.partition("+")[0] in pc_["names"]
                                                           or q.partition("+")[0] in (pc_.get("marks") or {}))
                                   for q in ([f["line"]] if isinstance(f["line"], str) else f["line"])):
            folds = [o for o in folds if o.get("name") != f.get("name")] + [dict(f)]
    for f in g.get("folds") or []:  # the garment's folds; one named like a table's replaces it ("off": drops it)
        folds = [o for o in folds if not (f.get("name") and o.get("name") == f["name"])] + [dict(f)]
    folds = [f for f in folds if f.get("piece") in keep and not f.get("off")]
    # made or draped per piece (made = constructed finished and kept so: garment_design.made_or_draped): the design
    # table's and the garment's "made" ({piece or role: "made" | "draped"}, or a list of made pieces) over the rule
    # (wholly interfaced = made). A coat's fronts are interfaced whole and still draped: frozen as placed, their
    # lapels couldn't roll
    made_own = {}
    for src in ((designs().get((g.get("pattern") or {}).get("from") or "", {}) or {}).get("made"), g.get("made")):
        if src:
            made_own.update(src if isinstance(src, dict) else {nm: "made" for nm in src})
    # pieces FUSED to another (a facing to its front: wrap "fused"): one cloth in the sim. Set aside with their seams
    # (Bp["fused"]: the pattern sheet and the cutting list still have them)
    fused = {nm: pc for nm, pc in out.items() if (pc.get("wrap") or {}).get("fused")}
    fused_seams = []
    if fused:
        out = {nm: pc for nm, pc in out.items() if nm not in fused}
        keep = set(out)
        fused_seams = [s for s in seams if not (side_ok(s[0]) and side_ok(s[1]))]
        seams = [s for s in seams if side_ok(s[0]) and side_ok(s[1])]
        stitches = [s for s in stitches if side_ok(s[0]) and side_ok(s[1])]
        folds = [f for f in folds if f.get("piece") in keep]
        seam_notes = {k: v for k, v in seam_notes.items() if not any(f'"{nm}:' in k for nm in fused)}
    return {"closures": closures_out, "trims": list(g.get("trims") or []), "fused": {"pieces": fused, "seams": fused_seams},
            "pieces": out, "seams": seams, "stitches": stitches, "interfaced": [p for p in interfaced
                                                                                    if (p if isinstance(p, str) else p["piece"]) in keep],
            "draft": draft_info, "folds": folds, "seam_notes": seam_notes, "made": made_own,
            "tacks": [t for t in list((designs().get((g.get("pattern") or {}).get("from") or "", {}) or {}).get("tacks") or [])
                      + list(g.get("tacks") or []) if t.get("piece") in keep]}


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


def mesh(B: dict, h: float = 0.02, fold_width: float = 0.0) -> dict:
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
    from . import folds as foldmod
    fold_entries = foldmod.entries(B)
    seam_sides = []
    for A, Bs in B["seams"]:
        sides = []
        for side in (A, Bs):
            chain = [side] if isinstance(side, str) else list(side)
            arcs = [_edge(pcs, e) for e in chain]
            lens = np.array([pattern.length(pcs[nm]["P"][ix]) for nm, ix in arcs])
            sides.append((arcs, np.r_[0, np.cumsum(lens)] / lens.sum(), float(lens.sum())))
        seam_sides.append(sides)

    def sample(extra):
        """Every seam's samples (extra: {seam: fractions that must be samples of both sides})."""
        for nm in names:
            fixed[nm].clear()
        keys = []
        for si, sides in enumerate(seam_sides):
            hs = min(ph[nm] for s in sides for nm, _ in s[0])
            Lmax = max(s[2] for s in sides)
            n = max(2, int(math.ceil(Lmax / hs)))
            U = list(np.unique(np.round(np.r_[sides[0][1], sides[1][1]], 9)))
            tol = SEAM_JOIN * hs / max(Lmax, 1e-9)
            for u in sorted(extra.get(si) or []):  # (closer to a sample than SEAM_JOIN h: that sample serves)
                if min(abs(u - v) for v in U) > tol:
                    U.append(float(u))
            U = np.sort(np.asarray(U))
            G = [0.0]
            for u0, u1 in zip(U[:-1], U[1:]):
                c = max(1, int(round(n * (u1 - u0))))
                G += list(np.linspace(u0, u1, c + 1)[1:])
            G = np.asarray(G)
            at = [[[] for _ in G] for _ in range(2)]  # per side, per global sample: its keys
            for k, (arcs, cum, _) in enumerate(sides):
                for j, (nm, ix) in enumerate(arcs):
                    s0, s1 = cum[j], cum[j + 1]
                    sel = np.where((G >= s0 - 1e-9) & (G <= s1 + 1e-9))[0]
                    f = np.clip((G[sel] - s0) / max(s1 - s0, 1e-12), 0, 1)
                    kk_ = put(nm, ix, _resample(pcs[nm]["P"][ix], f))
                    for g, kk in zip(sel, kk_):
                        at[k][g].append(kk)
            for g in range(len(G)):
                for ka in at[0][g]:
                    for kb in at[1][g]:
                        keys.append((si, ka, kb))
        return keys

    def on_seams(nm, q):
        """[(seam, fraction)] for a pattern point of piece nm that lies on sewn edges."""
        out = []
        for si, sides in enumerate(seam_sides):
            for arcs, cum, _ in sides:
                for j, (nm2, ix) in enumerate(arcs):
                    if nm2 != nm:
                        continue
                    L = pcs[nm]["P"][ix]
                    seg = np.linalg.norm(np.diff(L, axis=0), axis=1)
                    if len(L) < 2 or seg.sum() < 1e-9:
                        continue
                    ab = L[1:] - L[:-1]
                    tt = np.clip(np.sum((q - L[:-1]) * ab, 1) / np.maximum(seg ** 2, 1e-18), 0, 1)
                    d = np.linalg.norm(L[:-1] + tt[:, None] * ab - q, axis=1)
                    i = int(np.argmin(d))
                    if d[i] < 1e-3:
                        f = (seg[:i].sum() + tt[i] * seg[i]) / seg.sum()
                        out.append((si, float(cum[j] + f * (cum[j + 1] - cum[j]))))
        return out

    def at_fraction(si, u):
        """The pattern points (piece, point) of a seam's two sides at fraction u."""
        out = []
        for arcs, cum, _ in seam_sides[si]:
            for j, (nm, ix) in enumerate(arcs):
                if cum[j] - 1e-9 <= u <= cum[j + 1] + 1e-9 and cum[j + 1] > cum[j]:
                    f = float(np.clip((u - cum[j]) / (cum[j + 1] - cum[j]), 0, 1))
                    out.append((nm, _resample(pcs[nm]["P"][ix], np.array([f]))[0]))
        return out

    sew_keys = sample({})
    # A fold line that ends on a sewn edge: its end is a sample of the seam on BOTH sides (and of every other seam
    # the points it lands on belong to). The row's end used to take the outline's nearest vertex and move it onto the
    # line (up to 0.6 h along the seam, 1.3 h for a roll's further rows), on its own side only: the seam's two sides
    # were then paired up to 13 mm apart along it, and that pair never closed (a jacket's gorge beside the roll line)
    if fold_entries and seam_sides:
        extra, todo, seen = {}, [], []
        for f in fold_entries:
            nm = f["piece"]
            sewn = np.concatenate(list(fixed[nm].values())) if fixed[nm] else None
            for Lr in foldmod.rows(pcs, f, ph[nm], sewn, fold_width)["lines"]:
                todo += [(nm, Lr[0]), (nm, Lr[-1])]
        while todo:
            nm, q = todo.pop()
            if any(n_ == nm and np.linalg.norm(q - p_) < 1e-6 for n_, p_ in seen):
                continue
            seen.append((nm, q))
            for si, u in on_seams(nm, q):
                if 1e-6 < u < 1 - 1e-6 and all(abs(u - v) > 1e-7 for v in extra.get(si, [])):
                    extra.setdefault(si, []).append(u)
                    todo += at_fraction(si, u)
        if extra:
            sew_keys = sample(extra)
    uv, piece_of, F, border = [], [], [], []
    key_vid, points, marks = {}, {}, {}
    fold_recs = []
    folded = {f["piece"] for f in fold_entries}
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
        sewn_ring = {v - len(uv) for k_, v in key_vid.items() if k_[0] == nm}
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
        fl = _fold_line(B, nm, h) if nm not in folded else None
        if fl is not None and len(fl):
            fl = fl[_inside(ring, fl) & (_seg_dist(fl, ring) > 0.45 * h)]
            if len(fl) and len(Q):
                Q = Q[cKDTree(fl).query(Q)[0] > 0.5 * h]
            Q = np.r_[Q, fl] if len(fl) else Q
        # fold lines (folds.py): a row of vertices on each (rows over the arc for a roll), their ends on the outline
        FL, row_ids = np.zeros((0, 2)), []
        FL_of = []  # the fold entry each FL point belongs to
        for f in fold_entries:
            if f["piece"] != nm:
                continue
            sewn = np.concatenate(list(fixed[nm].values())) if fixed[nm] else None
            fr = foldmod.rows(pcs, f, h, sewn, fold_width)
            for d_end in (fr["lines"][0][0], fr["lines"][0][-1]):
                if _seg_dist(d_end[None], Pp)[0] > 1e-3:
                    raise ValueError(f"fold {f['name']}: its line must run from edge to edge of {nm} (an end is "
                                     f"{_seg_dist(d_end[None], Pp)[0] * 1000:.0f} mm inside; give \"reach\" or another line)")
            rec_rows = []
            taken = set()  # outline vertices that are already a row's end (a roll's rows end 3-4 mm apart: sharing
            # one vertex, every row's last segment bent to it and the flap turned about bent rows was stretched 150%)
            for S_ in foldmod.row_samples(fr["lines"], ring, h):
                ids = []
                ss_ = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(S_, axis=0), axis=1))]
                for j, q in enumerate(S_):
                    if j in (0, len(S_) - 1):  # an end: the outline's nearest vertex moves onto it
                        dq = np.linalg.norm(ring - q, axis=1)
                        i = int(np.argmin(dq))
                        ok = dq[i] < 0.6 * h
                        if ok and i in sewn_ring and dq[i] < 1.5 * SEAM_JOIN * h:
                            # a seam sample made for this end (or one within SEAM_JOIN h of it): the row ends on
                            # it where it is; moving it would unpair the seam's two sides
                            taken.add(i)
                            ids.append(("ring", i))
                            continue
                        if ok and i in taken and dq[i] > 1e-4:
                            # the next free vertex beside it, on the row end's side of it (else the rows share one)
                            for i2 in ((i + 1) % len(ring), (i - 1) % len(ring)):
                                if i2 not in taken and dq[i2] < 1.3 * h and (q - ring[i]) @ (ring[i2] - ring[i]) > 0:
                                    i = i2
                                    break
                        if ok:
                            if i not in taken:
                                ring[i] = q
                                taken.add(i)
                            ids.append(("ring", i))
                            continue
                    if 0 < j < len(S_) - 1 and min(ss_[j], ss_[-1] - ss_[j]) < ROW_END * h \
                            and _seg_dist(q[None], ring)[0] < ROW_KEEP * h:
                        # (a sample near a row's end a hair inside the outline: a 0.4 mm sliver edge at a shirt
                        # front's neck point, 11x stretched by the first mm the fine settle's start moved it. Only next
                        # to the ends: a collar's roll line runs 4 mm in from its edge all along, and dropping every
                        # sample left its row two vertices at 2 cm: the fall could not turn)
                        continue
                    if 0 < j < len(S_) - 1 and len(FL):
                        dk = np.linalg.norm(FL - q, axis=1)
                        dk[np.asarray(FL_of) == id(f)] = np.inf  # (another fold's row crossing this one: one vertex)
                        k_ = int(np.argmin(dk))
                        if dk[k_] < ROW_KEEP * h:
                            ids.append(("fold", k_))
                            continue
                    ids.append(("fold", len(FL)))
                    FL = np.r_[FL, q[None]]
                    FL_of.append(id(f))
                rec_rows.append(ids)
            row_ids.append((f, fr, rec_rows))
            if len(Q):
                for Lr in fr["lines"]:
                    Q = Q[_seg_dist(Q, Lr, closed=False) > 0.45 * h]
        nQ0 = len(Q)
        Q = np.r_[Q, FL] if len(FL) else Q
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
        # a mark on (or just inside) the outline (FreeSewing's notches) is the outline vertex nearest it, and marks
        # closer together than 0.4 h are one vertex: as vertices of their own they made sub-mm sliver edges (0.47 mm
        # at 1 cm), which a contact solver's gap can't resolve (ZOZO's CCD failed at frame 0)
        alias, own = {}, {}
        for k, v in mk.items():
            dr = np.linalg.norm(ring - v, axis=1)
            near = [o for o, p in own.items() if np.linalg.norm(p - v) < 0.4 * h]
            df_ = np.linalg.norm(FL - v, axis=1) if len(FL) else np.zeros(0)
            if dr.min() < 0.4 * h or _seg_dist(v[None], ring)[0] < 0.3 * h:
                alias[k] = ("ring", int(np.argmin(dr)))
            elif len(df_) and df_.min() < 0.4 * h:  # (a buttonhole a fold's row runs past: 0.54 mm from it)
                alias[k] = ("fold", int(np.argmin(df_)))
            elif near:
                alias[k] = ("mark", near[0])
            else:
                own[k] = v
        mk = own
        if mk and nQ0:
            M = np.array(list(mk.values()))
            d = cKDTree(M).query(Q[:nQ0])[0]
            Q = np.r_[Q[:nQ0][d > 0.5 * h], Q[nQ0:]]
            nQ0 = int((d > 0.5 * h).sum())
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
        for f, fr, rec_rows in row_ids:  # the rows' vertices joined by edges (the crease runs along mesh edges)
            loc = [[i if kind == "ring" else len(ring) + nQ0 + i for kind, i in ids] for ids in rec_rows]
            pairs = [(a_, b_) for ids in loc for a_, b_ in zip(ids[:-1], ids[1:]) if a_ != b_]
            tri, miss = foldmod.force_edges(X, tri, pairs)
            fold_recs.append({"piece": nm, "name": f["name"], "kind": f["kind"], "strength": f["strength"],
                              "angle": f["angle"], "turn": fr["turn"], "sign": fr["sign"], "missing_edges": miss,
                              "in_wrap": bool(f.get("in_wrap")),
                              "rows": [[len(uv) + i for i in ids] for ids in loc]})
        # orient counter-clockwise in the pattern (normals out of the pattern's face)
        a, b, c = X[tri[:, 0]], X[tri[:, 1]], X[tri[:, 2]]
        cw = ((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0]) < 0
        tri[cw] = tri[cw][:, [0, 2, 1]]
        base = len(uv)
        for k, i in pc["names"].items():  # named outline points -> nearest ring vertex
            points[f"{nm}:{k}"] = base + int(np.argmin(np.linalg.norm(ring - Pp[i], axis=1)))
        for j, k in enumerate(mk):
            marks[f"{nm}:{k}"] = base + len(ring) + len(Q) + j
        for k, (kind, i) in alias.items():
            marks[f"{nm}:{k}"] = (base + i if kind == "ring" else base + len(ring) + nQ0 + i if kind == "fold"
                                  else marks[f"{nm}:{i}"])
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
    for fd in fold_recs:
        fd["rows"] = [np.array([remap[i] for i in dict.fromkeys(row) if used[i]], np.int64) for row in fd["rows"]]
    from . import garment_design
    mod = garment_design.made_or_draped(dict(B, interfaced=B.get("interfaced", [])), None, {"made": B.get("made") or {}})
    from . import closures as closuremod
    marks_n = {k: int(remap[v]) for k, v in marks.items() if used[v]}
    return {"uv": uv_n, "piece": pid_n, "names": names, "F": remap[F], "folds": fold_recs,
            "made": [nm for nm in names if mod[nm][0] == "made"],
            "sew": sew, "sew_seam": sew_seam, "stitch": stitch,
            "marks": marks_n, "closures": closuremod.resolve(B.get("closures"), marks_n, pts_n, B.get("seams"), sew, sew_seam, pcs=pcs),
            "points": pts_n, "border": border_n,
            # lines drawn as stitching in the detail maps (pattern coordinates; a fly's J)
            "stitch_lines": {f"{nm}:{k_}": np.asarray(L_, float) for nm in names
                             for k_, L_ in (B["pieces"][nm].get("lines") or {}).items() if k_.endswith("_stitch")}}


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
        # things worn under / round the cloth that it rests on but that aren't the body (garment key "collide": the
        # model's shoes under a trouser hem): {"V", "F" (triangles), "key"}; colliders only, never measured
        self.worn = b.get("worn")

    @property
    def m(self) -> dict:
        """The tailor's tape (tailor.measure); a collider that isn't a body (a table under a tablecloth) measures
        nothing: {"mm": {}, "at": {}} (pieces wrapped on a torso, an arm or the neck need a body)."""
        if self._m is None:
            try:
                self._m = tailor.measure(self.V, self._faces, self.J)
            except Exception:  # no pelvis/neck/limb joints, sections that miss: not a body
                self._m = {"mm": {}, "at": {}, "body": False}
            if self.worn is not None and self._m.get("mm") and "ankle.L" in self.J:
                self._m["mm"].update(shoe_heights(np.asarray(self.worn["V"], float), np.asarray(self.J["ankle.L"], float)))
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

    def straight_arms(self, band: float = 0.04, frac: float = 1.0) -> tuple["Body", "callable"]:
        """(this body with both forearms (and hands) turned about the elbow into line with the upper arm, pose) where
        pose(P) carries points from the straight body back to this one. Garments are placed on the straight arms (a
        sleeve is a plain tube there: nothing overlaps or folds in the crook) and the body bends back while the
        sleeves are on (`placement` "smooth"), as a tailor's dummy is posed after dressing. The turn is blended over
        +-band across the elbow's mitre plane. frac < 1 turns them part way (the poses in between)."""
        V = self.V.copy()
        J = {k: v.copy() for k, v in self.J.items()}
        turns = []
        for side, sg in (("L", 1.0), ("R", -1.0)):
            try:
                sh, el, wr = (self.J[f"{j}.{side}"] for j in ("shoulder", "elbow", "wrist"))
            except KeyError:
                continue
            d1, d2 = (el - sh) / np.linalg.norm(el - sh), (wr - el) / np.linalg.norm(wr - el)
            ax = np.cross(d1, d2)
            if np.linalg.norm(ax) < 1e-4:
                continue
            ax /= np.linalg.norm(ax)
            theta = frac * math.acos(float(np.clip(d1 @ d2, -1, 1)))
            m = (d1 + d2) / np.linalg.norm(d1 + d2)
            lim = float(np.linalg.norm(wr - el)) + 0.3

            def weight(P, el=el, sh=sh, d1=d1, d2=d2, m=m, lim=lim, sg=sg):
                """0 on the upper arm, 1 past the elbow on the forearm and hand (this side's arm only)."""
                P = np.atleast_2d(P)
                s = (P - el) @ m
                w = np.clip((s + band) / (2 * band), 0, 1)
                w = w * w * (3 - 2 * w)
                t = (P - el) @ d2  # along the forearm, then distance to that line
                r = np.linalg.norm(P - el - np.outer(np.clip(t, 0, lim), d2), axis=1)
                ru = np.linalg.norm(P - sh - np.outer(np.clip((P - sh) @ d1, 0, None), d1), axis=1)
                arm = (sg * (P[:, 0] - sh[0] * 0.5) > 0) & (np.minimum(r, ru) < 0.14) & (t < lim)
                return np.where(arm, w, 0.0)

            turns.append((el, ax, theta, weight))

        def rot(P, el, ax, ang):
            P = np.atleast_2d(P) - el
            c, s = np.cos(ang)[:, None], np.sin(ang)[:, None]
            return el + P * c + np.cross(ax, P) * s + np.outer(P @ ax, ax) * (1 - c)

        for el, ax, theta, weight in turns:
            V = rot(V, el, ax, -theta * weight(V))
            for k in J:
                J[k] = rot(J[k], el, ax, -theta * weight(J[k]))[0]

        def pose(P, turns=turns):
            """Points on the straight body carried back onto this body's arms (the weights read on the straight body:
            the turn is about the elbow, which doesn't move)."""
            P = np.asarray(P, float)
            for el, ax, theta, weight in turns:
                ws = weight(rot(P, el, ax, theta * np.ones(len(P))))  # the bent-pose point's own weight
                P = rot(P, el, ax, theta * ws)
            return P

        b = Body({"V": V, "F": self._faces, "J": J, "worn": self.worn})
        b._m = self.m  # the tape is the body's own (drafting, landmarks on the torso)
        return b, pose

    def arms_down(self, gap: float = 0.07, band: float = 0.05, steps: int = 4, straighten: bool = False) -> list:
        """Poses lowering both arms about the shoulder joints toward the body's sides (the way a coat is taken off a
        dummy: arms down first, so the sleeves hang beside the body on the hanger instead of staying splayed in the
        A-pose). Each arm turns in its own plane (the upper arm and straight down) until its forearm and hand come
        within `gap` of the torso; blended over +-band across the plane through the shoulder joint square to the
        upper arm. straighten: the elbows straighten as the arms come down (the bent forearm met the torso after
        26 deg and left the sleeves ~20 deg out on the hanger). Returns [V (n, 3)] for `steps` poses evenly from here
        to fully down (the last fully down)."""
        base = self.straight_arms()[0] if straighten else self
        V0 = base.V
        turns = []
        for side, sg in (("L", 1.0), ("R", -1.0)):
            try:
                sh, el, wr = (base.J[f"{j}.{side}"] for j in ("shoulder", "elbow", "wrist"))
            except KeyError:
                continue
            d1 = (el - sh) / np.linalg.norm(el - sh)
            down = np.array([0.0, 0.0, -1.0])
            ax = np.cross(d1, down)
            if np.linalg.norm(ax) < 1e-3:
                continue
            ax /= np.linalg.norm(ax)
            lim = float(np.linalg.norm(el - sh) + np.linalg.norm(wr - el)) + 0.25
            d2 = (wr - el) / np.linalg.norm(wr - el)

            def weight(P, sh=sh, el=el, d1=d1, d2=d2, sg=sg, lim=lim):
                P = np.atleast_2d(P)
                s = (P - sh) @ d1
                w = np.clip((s + band) / (2 * band), 0, 1)
                w = w * w * (3 - 2 * w)
                ru = np.linalg.norm(P - sh - np.outer(np.clip(s, 0, None), d1), axis=1)
                t = (P - el) @ d2
                rf = np.linalg.norm(P - el - np.outer(np.clip(t, 0, lim), d2), axis=1)
                arm = (sg * (P[:, 0] - sh[0] * 0.5) > 0) & (np.minimum(ru, rf) < 0.14) & (s < lim)
                return np.where(arm, w, 0.0)

            turns.append((sh, ax, weight(V0), side))
        if not turns:
            return [V0.copy()]
        # the torso: what neither arm moves
        moving = np.zeros(len(V0), bool)
        for _, _, w, _ in turns:
            moving |= w > 0.01
        tree = cKDTree(V0[~moving])

        def rot(P, c, ax, ang):
            P = P - c
            ca, sa = np.cos(ang)[:, None], np.sin(ang)[:, None]
            return c + P * ca + np.cross(ax, P) * sa + np.outer(P @ ax, ax) * (1 - ca)

        full = []
        for sh, ax, w, side in turns:
            el, wr = base.J[f"elbow.{side}"], base.J[f"wrist.{side}"]
            # the forearm and hand: what meets the torso first (the upper arm's inside lies against the lat already)
            far = (w > 0.99) & ((V0 - el) @ ((wr - el) / np.linalg.norm(wr - el)) > 0.0)
            best = 0.0
            for ang in np.radians(np.arange(2.0, 80.0, 2.0)):
                P = rot(V0[far], sh, ax, np.full(far.sum(), ang))
                if tree.query(P)[0].min() < gap:
                    break
                best = ang
            full.append(best)
        poses = []
        for k in range(1, steps + 1):
            V = self.straight_arms(frac=k / steps)[0].V if straighten else V0.copy()
            for (sh, ax, w, _), ang in zip(turns, full):
                V = rot(V, sh, ax, ang * k / steps * w)
            poses.append(V)
        self._arms_down_deg = [float(np.degrees(a)) for a in full]
        return poses

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

    def clearance(self, P: np.ndarray) -> np.ndarray:
        """Signed distance-ish of points from the body (along its normal from the 4 nearest vertices; < 0 inside):
        push_out's own measure."""
        vn, tree = self.normals()
        _, i = tree.query(P, k=4)
        n = vn[i].mean(1)
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        return np.sum((P - self.V[i].mean(1)) * n, 1)

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
                # the loop that holds the body's middle line is the torso; a forearm hanging inside the shoulders'
                # width is not (a waistband alone started on a hull as wide as the arms: 28 cm from the middle,
                # its back half 16-25 cm from the trousers it is sewn to, and the sewing dragged them down)
                mid = [L[:, :2] for L in loops if L[:, 0].min() < -0.02 and L[:, 0].max() > 0.02]
                pts = mid or [L[:, :2] for L in loops if np.all(np.abs(L[:, 0]) < xs)]
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


WORN_DBG: list = []  # (columns' pattern x, their samples, start clearance, target) of the last worn tops laid
ENVELOPE_ROUNDS = 0  # smoothing rounds of the envelope a worn top is laid on (_envelope)
WORN_STEP = 0.003  # m between a worn top's samples up each column
WORN_COL = 0.004  # m between its columns (pattern x)
WORN_RAMP = 0.08  # m of column over which the start's clearance eases from the cylinder's to the worn one
WORN_NORMAL = 0.04  # m: the body's normal under a column is averaged over this radius (a crease's normals jump)


def _envelope(body: "Body", rounds: int = ENVELOPE_ROUNDS) -> "Body":
    """The body with its hollows and steps filled (never cut into), cached on it: a Laplacian-smoothed copy, each vertex
    taking the smoothed surface only where it stands further out along the normal. What a stiff forepart lies on: laid
    on the padded body itself, its columns followed every edge of an open shirt collar under it and neighbours 4 mm
    apart ended 2-6 cm apart (Garrett's gorge)."""
    if (getattr(body, "_env_by", None) or {}).get(rounds) is not None:
        return body._env_by[rounds]
    vn, _ = body.normals()
    T = body.T
    E = np.unique(np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1), axis=0)
    V = body.V.copy()
    for _ in range(rounds):
        acc, wt = np.zeros_like(V), np.zeros(len(V))
        np.add.at(acc, E[:, 0], V[E[:, 1]])
        np.add.at(wt, E[:, 0], 1.0)
        np.add.at(acc, E[:, 1], V[E[:, 0]])
        np.add.at(wt, E[:, 1], 1.0)
        Vs = acc / np.maximum(wt, 1)[:, None]
        # (only out along the body's own normal: its tangential place kept)
        V = body.V + vn * np.maximum(((Vs - body.V) * vn).sum(1), 0.0)[:, None]
    import copy as _copy
    env = _copy.copy(body)
    env.V = V
    for a_ in ("_vn", "_tree", "_env", "_env_by"):
        if hasattr(env, a_):
            delattr(env, a_)
    env._hull = {}
    env._env_by = {rounds: env}
    if not isinstance(getattr(body, "_env_by", None), dict):
        body._env_by = {}
    body._env_by[rounds] = env
    return env


def _worn_top(body: "Body", Cw: np.ndarray, start: np.ndarray, sgn: float, xs: np.ndarray, ys: np.ndarray,
              hz: float, y0: float, target: float, info: dict | None = None, neck_x: float = 0.0,
              envelope: int | None = None) -> np.ndarray:
    """A torso piece laid as it is WORN, hanging from the top of the shoulder, as a tailor builds a forepart on a
    form. Each column (fixed pattern x) is laid up the body from the torso cylinder at the armpit's level (pattern
    height y0), along the body's surface in a near-vertical plane facing the piece's side (a front column runs up
    the chest, over the ridge of the shoulder and down the back), arc length = pattern height. Where a column
    crosses the shoulder's ridge, the whole column is slid along that path so the piece's top lands ON the ridge
    (front and back meet there, as their shoulder seam does worn): the cloth below follows on the cylinder, raised or
    lowered by the same amount (a front long over the bust hangs lower: what the sim then sees is the pattern's
    balance, not the start's). Columns that don't cross (the neck, under the armhole) take their neighbours' slide.
    The clearance eases from the cylinder's to `target` over WORN_RAMP. Rows keep no lengths (the start relaxation
    trues them), columns do. On the cylinder alone a jacket's shoulder seams started 23-25 cm apart (front on the
    front of the cylinder, back on its back) and its notched collar, laid where it is worn, 13-25 cm from the
    neckline it is sewn to. Returns every point's position."""
    body = _envelope(body, ENVELOPE_ROUNDS if envelope is None else int(envelope))  # (laid over what it bridges: an under garment's collar points, the hollows above the collarbone)
    vn, tree = body.normals()
    gx = np.arange(xs.min() - WORN_COL, xs.max() + 2 * WORN_COL, WORN_COL)
    smax = max(float(ys.max() - y0) + 0.10, 0.36)
    ns = int(np.ceil(smax / WORN_STEP)) + 1
    q = _arc_point(Cw, start, gx, sgn)
    tg = _arc_point(Cw, start, gx + 0.003, sgn) - _arc_point(Cw, start, gx - 0.003, sgn)
    h = np.c_[tg[:, 1], -tg[:, 0]]
    h /= np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-12)
    h *= np.sign(np.sum(h * (q - Cw.mean(0)), 1))[:, None]
    # the column's plane: up and straight out to the front / back, at the column's own x (tilted with the cylinder,
    # the columns ran in toward the neck and front and back met different ridges: the front's 25 mm higher)
    h3 = np.c_[np.zeros(len(h)), np.where(h[:, 1] < 0, -1.0, 1.0), np.zeros(len(h))]
    h3 /= np.maximum(np.linalg.norm(h3, axis=1, keepdims=True), 1e-12)
    ez = np.array([0.0, 0.0, 1.0])
    t3 = np.cross(np.broadcast_to(ez, h3.shape), h3)  # the plane's normal
    P = np.c_[q, np.full(len(q), hz + y0)]
    c0 = body.clearance(P)
    S = np.zeros((len(gx), ns, 3))
    S[:, 0] = P
    D = np.broadcast_to(ez, P.shape).copy()

    def nrm(Pq):
        dd, i = tree.query(Pq, k=12, distance_upper_bound=WORN_NORMAL + 0.03)
        ok = np.isfinite(dd)
        i = np.where(ok, i, 0)
        n = (vn[i] * ok[..., None]).sum(1)
        n0 = vn[tree.query(Pq)[1]]
        n = np.where(ok.any(1)[:, None], n, n0)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    def march(free_neck):
        P_, D_ = P.copy(), D.copy()
        S_ = S.copy()
        Dr = D.copy()  # the direction a column runs on in (free_neck): its chord over the last WORN_RUN before it starts
        kr = max(1, int(round(WORN_RUN / WORN_STEP)))
        for j in range(1, ns):
            n = nrm(P_)
            n = n - t3 * np.sum(n * t3, 1, keepdims=True)
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            d = np.cross(t3, n)  # in the plane, along the surface
            d *= np.where(np.sum(d * D_, 1) < 0, -1.0, 1.0)[:, None]
            d = 0.5 * d + 0.5 * D_  # (a little momentum: a crease's normals still turn sharply)
            d -= t3 * np.sum(d * t3, 1, keepdims=True)
            d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
            Pn = P_ + WORN_STEP * d
            f = min(1.0, j * WORN_STEP / WORN_RAMP)
            want = c0 + (target - c0) * (f * f * (3 - 2 * f))
            for _ in range(2):
                n2 = nrm(Pn)
                Pn = Pn + n2 * (want - body.clearance(Pn))[:, None]
                Pn -= t3 * np.sum((Pn - S_[:, 0]) * t3, 1, keepdims=True)
            st = Pn - P_
            if free_neck:
                # in front of / behind the neck the cloth doesn't follow the body up the throat or the nape: past the
                # neck's base it runs on as it was going (a lapel's flap following the neck was turned out in the air)
                wz = np.clip((P_[:, 2] - (hz - WORN_NECK)) / 0.02 + 0.5, 0.0, 1.0)
                # (on in the direction the column had over its last few cm, frozen once it starts: the step's own
                # direction at that moment, over the edge of an open shirt collar's point, sent neighbours 4 mm apart
                # one up the throat and one back over the shoulder, 7 cm apart: Garrett's right gorge 3.6x)
                ch = P_ - S_[:, max(j - 1 - kr, 0)]
                ch -= t3 * np.sum(ch * t3, 1, keepdims=True)
                ch /= np.maximum(np.linalg.norm(ch, axis=1, keepdims=True), 1e-12)
                Dr = np.where((wz <= 0)[:, None], ch, Dr)
                st = (1 - wz)[:, None] * st + wz[:, None] * WORN_STEP * Dr
            st *= (WORN_STEP / np.maximum(np.linalg.norm(st, axis=1), 1e-12))[:, None]  # (arc length kept)
            D_ = st / WORN_STEP
            P_ = P_ + st
            S_[:, j] = P_
        return S_
    S = march(False)
    if neck_x:
        # the two lays (following the body, running on past the neck's base) mixed by POSITION across WORN_NECK_BAND
        # (mixed by direction step by step, two columns 4 mm apart ended 65 mm apart: Garrett's gorge strip 3.5-4.5x)
        wf = np.clip((neck_x + WORN_NECK_BAND - np.abs(S[:, 0, 0])) / WORN_NECK_BAND, 0.0, 1.0)
        wf = wf * wf * (3 - 2 * wf)
        if wf.any():
            S = (1 - wf)[:, None, None] * S + wf[:, None, None] * march(True)
    # the ridge: where a column's height peaks and falls again (over the shoulder)
    jr = np.argmax(S[:, :, 2], axis=1)
    zr = S[np.arange(len(gx)), jr, 2]
    crossed = (jr < ns - 4) & (zr - S[:, -1, 2] > 0.006)
    ci = np.clip(np.round((xs - gx[0]) / WORN_COL).astype(int), 0, len(gx) - 1)
    ytop = np.full(len(gx), -np.inf)
    np.maximum.at(ytop, ci, ys)
    ln = ytop - y0
    Lr = jr * WORN_STEP
    ok = crossed & (ln > 0.05) & (Lr > 0.5 * ln) & (Lr < 1.6 * ln + 0.02)
    if neck_x:  # (the shoulder's own ridge: by the neck the ridge climbs the neck, or an under garment's collar, and
        # slid onto it the jacket rode 27 mm high: its collar stood 33 mm over the shirt's, its cuffs showed 21-29 mm)
        ok &= np.abs(S[:, 0, 0]) > neck_x + WORN_NECK_CLEAR
    # ONE slide for the piece (the median over the columns that cross the ridge): a draft's shoulder slope puts every
    # column's top on the ridge when the piece hangs level; a slide per column sheared the piece (26-100 mm across
    # the front) and its neck columns, which never cross, climbed the neck
    slide = np.zeros(len(gx))
    if ok.any():
        slide[:] = float(np.clip(np.median((Lr - ln)[ok]), -WORN_SLIDE, WORN_SLIDE))
    WORN_DBG.append((gx, S.copy(), c0, target, slide, ok))
    del WORN_DBG[:-16]
    if info is not None:
        info.update(ridge_columns=int(ok.sum()), slide_mean=float(np.mean(np.interp(xs, gx, slide))), slide_mm=[round(float(slide.min()) * 1000, 1), round(float(slide.max()) * 1000, 1)])
    for _ in range(4):  # neighbouring columns agree (each was laid alone)
        S[1:-1, 1:] = 0.25 * S[:-2, 1:] + 0.5 * S[1:-1, 1:] + 0.25 * S[2:, 1:]
    fx = np.clip((xs - gx[0]) / WORN_COL, 0, len(gx) - 1.001)
    ix = fx.astype(int)
    ax = fx - ix
    sl = (1 - ax) * slide[ix] + ax * slide[ix + 1]
    s_ = ys - y0 + sl  # arc up the column's path (< 0: on the cylinder, under the armpit's level)
    # no point goes further than WORN_OVER past its OWN column's ridge (the piece's one slide is the shoulder's; by the
    # neck the ridge is nearer, and Garrett's front neckline was carried over it onto his back: 6x stretch, "ccd
    # failed"); what's left is compressed there, which a strain-limited solver starts from
    crossed_x = (jr < ns - 4) & (zr - S[:, -1, 2] > 0.006)
    if neck_x:  # (by the neck an under garment's collar makes ridges of its own: lie over them)
        crossed_x &= np.abs(S[:, 0, 0]) > neck_x
    # (the column's run above the armpit level shortened evenly, not piled at the ridge: a cap piled the neck point's
    # cloth into a 1 cm band and sheared the roll line's top end 4-5x)
    top_s = np.maximum(ln + slide, 1e-6)
    sc = np.where(crossed_x, np.minimum(1.0, (Lr + WORN_OVER) / top_s), 1.0)
    ut = getattr(body, "under_top", None)
    if neck_x and ut is not None and len(ut):
        # behind the neck a worn top's back ends where the garment under it ends (its neckline, where its collar is
        # sewn): run on up the nape with the piece's one slide, Garrett's jacket back started 42 mm over his shirt's
        # neckline at CB (ga_suit's 14 under it), its carried collar held over the shirt collar's top and the jacket
        # hung from it 15-50 mm high (collar_show -45, cuffs 44)
        back_ = (h3[:, 1] > 0) & (np.abs(S[:, 0, 0]) < neck_x)
        fin_ = np.isfinite(ytop)
        tops_ = np.maximum(np.interp(gx, gx[fin_], ytop[fin_]) - y0 + slide, 1e-6) if fin_.any() else top_s
        for i in np.where(back_)[0]:
            near_ = np.abs(ut[:, 0] - S[i, 0, 0]) < 0.008
            if not near_.any():
                continue
            zc = float(ut[near_, 2].max()) + WORN_NAPE
            over_ = np.where(S[i, :, 2] > zc)[0]
            if len(over_) and tops_[i] > over_[0] * WORN_STEP:
                sc[i] = min(sc[i], over_[0] * WORN_STEP / tops_[i])
    for _ in range(int(0.03 / WORN_COL)):  # (neighbouring columns alike)
        sc[1:-1] = np.minimum(sc[1:-1], 0.25 * sc[:-2] + 0.5 * sc[1:-1] + 0.25 * sc[2:])
    scv = (1 - ax) * sc[ix] + ax * sc[np.minimum(ix + 1, len(sc) - 1)]
    s_ = np.where(s_ > 0, s_ * scv, s_)
    fs = np.clip(s_ / WORN_STEP, 0, ns - 1.001)
    js = fs.astype(int)
    a2, aj = ax[:, None], (fs - js)[:, None]
    out = ((1 - a2) * (1 - aj) * S[ix, js] + a2 * (1 - aj) * S[ix + 1, js] + (1 - a2) * aj * S[ix, js + 1]
           + a2 * aj * S[ix + 1, js + 1])
    low = s_ < 0
    if low.any():
        out[low] = np.c_[_arc_point(Cw, start, xs[low], sgn), hz + y0 + s_[low]]
    return out


PIN_GAP = 0.002  # m a pinned seam's two sides start apart
WORN_STAND = 0.02  # m out from the neck point's radius: an under garment's neck pieces there are its stand (worn_body)
WORN_PIN = 0.06  # m (pattern, sigma) over which a pinned seam's move fades into its pieces


def _pressed(B: dict, M: dict, fd: dict) -> bool:
    """A fold whose flap is pressed onto its base (place: a forepart laid where it is worn, turned >= 150 deg)."""
    return fd["piece"] in (B.get("worn_top_pieces") or {}) and fd["turn"] > 0 and not fd.get("in_wrap") \
        and math.degrees(abs(fd["turn"]) * len(fd["rows"])) >= 150


def _repress(X: np.ndarray, B: dict, M: dict, smooth: bool) -> np.ndarray:
    """The pressed flaps laid again on their bases as they are now."""
    from . import folds as foldmod
    F = M["F"]
    hm = float(np.median(np.linalg.norm(M["uv"][F[:, 0]] - M["uv"][F[:, 1]], axis=1)))
    for fd in M.get("folds") or []:
        if _pressed(B, M, fd):
            X = foldmod.pressed_flap(X, M, fd, (B.get("faces") or {}).get(fd["piece"], 1.0), float(B.get("press_lay") or PRESS_LAY),
                                     wedge=float(np.clip(0.0012 / hm, 0.04, 0.15)) if smooth else 0.08)
    return X


WORN_LEVELS = True  # place(): a worn top's torso pieces below the armpit laid level by level (_worn_levels)
WORN_LEVEL_RAMP = 0.03  # m under the armpit over which the level lay takes over from the one cylinder
WORN_LEVEL_CLEAR = 0.004  # m: the level curves stand at least this far off the body's hull
OPEN_GAP = 0.16  # m between the front edges at the hem of a worn top whose front closure is worn OPEN (garment key open_gap)


def open_gap(B: dict, torso: list) -> float:
    """How far apart a worn top's fronts start at the hem: its front closure (two different torso pieces) worn open ->
    garment key `open_gap` or OPEN_GAP; closed, or no such closure -> 0."""
    for c in B.get("closures") or []:
        if c.get("state") == "open" and c.get("over") != c.get("under") and c.get("over") in torso and c.get("under") in torso:
            v = B.get("open_gap")
            return float(OPEN_GAP if v is None else v)
    return 0.0


def _worn_levels(X: np.ndarray, B: dict, M: dict, body: "Body", torso: list, pcs: dict, pid: np.ndarray,
                 dxs: dict, hps: np.ndarray, z_pit: float, lx) -> np.ndarray:
    """A worn top's torso pieces under the armpit laid round the body LEVEL BY LEVEL: at each 1 cm level the body's
    own hull pushed out until its perimeter is what the pieces span there (each side's span from its centre line,
    each piece at its own pattern height after its slide), the front from CF and the back from CB on that curve.
    On the garment's one cylinder (as big as its widest level) the arc a suppressed waist left over between the front
    and the back all fell into the side panel's back seam: Garrett's jacket's side-back seams started 135-160 mm open
    and the sim left them 67-110 mm open. Eased in over WORN_LEVEL_RAMP under the armpit; above it nothing moves.
    Shear a level lay brings (the taper spread round, not in the side seams) is the start relaxation's.
    A front closure worn OPEN (open_gap): the fronts start APART, the gap growing evenly from the armpit's level to
    the hem, and every level's curve is that much longer: the jacket starts as the loose tube an open jacket is,
    standing off the body all round. Started lapped at the centre like a buttoned one, Garrett's fronts stayed lapped
    15 mm, the sides hugged the hips at 2-8 mm and all the ease stood in front, 5-12 cm off the body (the tent)."""
    names = M["names"]
    slides = B.get("_worn_slides") or {}
    mean_sl = float(np.mean(list(slides.values()))) if slides else 0.0
    use = [nm for nm in torso if not pcs[nm]["wrap"].get("lies_on") and not _closed_girth(M, nm)
           and not pcs[nm]["wrap"].get("pleats") and pcs[nm]["wrap"].get("to", "torso") == "torso"]
    if not use:
        return X
    sl = {nm: slides.get(nm, mean_sl) for nm in use}
    ks = [names.index(nm) for nm in use]
    sel_all = np.isin(pid, ks)
    zlo = float(X[sel_all, 2].min()) - 0.01
    levels = np.arange(np.floor(zlo / 0.01) * 0.01, z_pit + 0.011, 0.01)
    curves = {}
    G_open = open_gap(B, use)
    for z in levels:
        h = body.hull(float(z))
        if h is None or len(h) < 3:
            continue
        H = h[ConvexHull(h).vertices]
        P0 = pattern.length(H, closed=True)
        sp = {}
        for nm in use:
            iv = lx(nm, float(z) - float(hps[2]) - sl[nm])
            if iv:
                sd = pcs[nm]["wrap"].get("side", "front")
                sp[sd] = (min(iv[0], sp[sd][0]), max(iv[1], sp[sd][1])) if sd in sp else iv
        if len(sp) != 2:
            continue
        span = sum(hi - lo for lo, hi in sp.values())
        gz = G_open * float(np.clip((z_pit - z) / max(z_pit - zlo, 1e-6), 0.0, 1.0))
        m = float(np.clip((span + gz - P0) / (2 * np.pi), WORN_LEVEL_CLEAR, 0.15))
        curves[round(float(z), 3)] = (H, m, gz)
    if not curves:
        return X
    zk = np.array(sorted(curves))
    X = X.copy()
    for nm in use:
        k = names.index(nm)
        w = pcs[nm]["wrap"]
        idx = np.where(pid == k)[0]
        z = X[idx, 2]
        wt = np.clip((z_pit - z) / WORN_LEVEL_RAMP, 0.0, 1.0)
        wt = wt * wt * (3 - 2 * wt)
        go = wt > 0
        if not go.any():
            continue
        lev = zk[np.clip(np.searchsorted(zk, z - 0.005), 0, len(zk) - 1)]
        out_ = float(w.get("out", 0.0))
        side = w.get("side", "front")
        hs = float(np.sign(np.median(M["uv"][idx, 0] + dxs.get(nm, 0.0))) or 1.0)  # which side of the centre it is on
        for L in np.unique(lev[go]):
            H, m, gz = curves[round(float(L), 3)]
            Cz = _densify(_offset_hull(H, m + out_), 0.002)
            cy = 0.5 * (Cz[:, 1].max() + Cz[:, 1].min())
            if side == "front":
                st = Cz[np.argmin(np.abs(Cz[:, 0]) + 10 * np.maximum(Cz[:, 1] - cy, 0))]
            else:
                st = Cz[np.argmin(np.abs(Cz[:, 0]) + 10 * np.maximum(cy - Cz[:, 1], 0))]
            j = np.where(go & (lev == L))[0]
            q = _arc_point(Cz, st, M["uv"][idx[j], 0] + dxs.get(nm, 0.0) + (0.5 * gz * hs if side == "front" else 0.0),
                           float(w.get("dir", 1.0)))
            X[idx[j], :2] = (1 - wt[j])[:, None] * X[idx[j], :2] + wt[j][:, None] * q
    return X


def _pin_seams(X: np.ndarray, M: dict, ks: list, sigma: float = WORN_PIN, fixed: list | None = None, pull: float = 1.0) -> np.ndarray:
    """Seams between pieces laid where they are worn (a jacket's shoulder seams, its centre back) pinned shut as a
    tailor pins them on the form: each sewn pair goes to its middle, and each piece follows its seam's moves, faded
    by pattern distance from the seam (Gaussian `sigma`, Shepard-weighted). Laid separately the front and back met
    over the shoulder 3-6 cm apart (the left front stands a lap further out than the back). `fixed` pieces (made ones
    laid on these, a notched collar) don't move: their seams' worn sides go all the way to them."""
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    pid, uv = M["piece"], M["uv"]
    fixed = list(fixed or [])
    both = np.isin(pid[sw[:, 0]], ks + fixed) & np.isin(pid[sw[:, 1]], ks + fixed) & \
        ~(np.isin(pid[sw[:, 0]], fixed) & np.isin(pid[sw[:, 1]], fixed))
    if not both.any():
        return X
    a, b = sw[both, 0], sw[both, 1]
    mid = 0.5 * (X[a] + X[b])
    fa, fb = np.isin(pid[a], fixed), np.isin(pid[b], fixed)
    mid[fa], mid[fb] = X[a[fa]], X[b[fb]]
    # each side stops PIN_GAP short of the other, the way it came (pinned onto one point, the cloth either side of the
    # seam crossed: centre back, shoulders, the collar's neck seam)
    # (toward each side's own cloth: the direction they came from crossed where they had passed each other)
    A_, B_ = _graph(M)
    same = pid[A_] == pid[B_]
    acc, wt = np.zeros_like(X), np.zeros(len(X))
    np.add.at(acc, A_[same], X[B_[same]])
    np.add.at(wt, A_[same], 1.0)
    np.add.at(acc, B_[same], X[A_[same]])
    np.add.at(wt, B_[same], 1.0)
    inward = acc / np.maximum(wt, 1)[:, None] - X
    inward /= np.maximum(np.linalg.norm(inward, axis=1, keepdims=True), 1e-9)
    ga, gb = np.where(fb, 1.0, 0.5) * PIN_GAP, np.where(fa, 1.0, 0.5) * PIN_GAP
    ta, tb = mid + inward[a] * ga[:, None], mid + inward[b] * gb[:, None]
    ta[fa], tb[fb] = X[a[fa]], X[b[fb]]
    # (`pull` < 1: a side sewn to a fixed piece goes that share of the way: the sewing closes the rest, and a back
    # held to a made collar while it relaxed started 9.8% of its triangles past 5%)
    ta[fb] = X[a[fb]] + pull * (ta[fb] - X[a[fb]])
    tb[fa] = X[b[fa]] + pull * (tb[fa] - X[b[fa]])
    Y = X.copy()
    for k in ks:
        ends = np.r_[a[pid[a] == k], b[pid[b] == k]]
        if not len(ends):
            continue
        D = np.r_[ta[pid[a] == k], tb[pid[b] == k]] - X[ends]
        sel = np.where(pid == k)[0]
        d2 = ((uv[sel, None, :] - uv[None, ends, :]) ** 2).sum(-1)
        w = np.exp(-d2 / (2 * sigma * sigma))
        fade = w.max(1)
        Y[sel] = X[sel] + (w @ D) / np.maximum(w.sum(1), 1e-12)[:, None] * fade[:, None]
    return Y


WORN_SLIDE = 0.10
WORN_PULL = 0.2  # share of the way a worn seam to a made piece (the collar) is pinned in the start relaxation
WORN_OVER = 0.01  # m a worn top may run on past its own column's ridge
WORN_CLEAR = 0.005  # m a worn top starts off the body under it: it RESTS on the shoulders (at the draped 12 mm the jacket
# started 19 mm over the shirt at the shoulder, and its made collar, carried where it started, held it 27 mm high)
WORN_NECK_BAND = 0.04  # m out past the neck point (world x) over which a column hands over from running on to following
WORN_NECK_CLEAR = 0.02  # m out from the neck point (world x) from which a column's ridge is the shoulder's
NOTCH_HOLD_CB = 0.04  # m of a notched collar's neck edge either side of CB held to the worn back neck while it is laid
NOTCH_HOLD_RATIO = 1.2  # ... when the worn neckline is this much longer than the collar's neck edge (ga_suit 1.15, Garrett 1.30)
WORN_NAPE = 0.0  # m a worn top's back may run on past the under garment's neckline behind the neck
WORN_RUN = 0.04  # m: a column running on past the neck's base goes the way its last WORN_RUN went
WORN_NECK = 0.05  # m under the neck point from which a column in front of / behind the neck stops following the body  # m a worn column may slide along its path to put the piece's top on the shoulder's ridge


SLEEVE_TAPER = True  # smooth placement: sleeves laid on a cone that follows their own girth (place(): taper)
LEG_BLEND = 0.15  # m under the crotch over which a trouser leg hands over from the seat's cylinder to the leg's tube
LEG_TOP = 0.01  # m under the crotch line where the hand-over starts
LEG_APART = 0.004  # m a trouser leg's side seam and inseam start apart at least
LEG_CLEAR = 0.005  # m a trouser leg starts off the leg at least (the 12 mm of draped cloth is more than a slim leg's ease)
LEG_SMOOTH = 0.04  # m (sigma) a leg tube's sections are smoothed over up and down the leg
LEG_DRIFT = 0.05  # the most a leg tube's crease line drifts round the leg per m down it (a drift is a shear)
LEG_TAPER = 5.0  # m of girth a leg tube may lose per m down the leg (5: as fast as the cloth; slower starts the seams apart)
LEG_EASE = 0.35  # m over the ankle's level from which a leg is compressed to start its hem clear of the foot


def _leg_section(body, sgn: float, z: float):
    """The leg's own section (its convex hull in plan) at height z, the side sgn: the loop under the crotch nearest the
    knee's plan position (a hanging hand is further off it), or None."""
    J = body.J
    kn = np.asarray(J["knee.L"], float) if "knee.L" in J else None
    if kn is None:
        return None
    kx, ky = sgn * kn[0], kn[1]
    best, bd = None, 0.2
    for L_ in tailor.slice_loops(body.V, body.T, [0, 0, float(z)], [0, 0, 1.0]):
        if len(L_) < 3:
            continue
        c_ = L_[:, :2].mean(0)
        if sgn * c_[0] < 0.01:
            continue
        d_ = float(np.hypot(c_[0] - kx, c_[1] - ky))
        if d_ < bd:
            best, bd = L_[:, :2], d_
    if best is None:
        return None
    return best[ConvexHull(best).vertices]


def _leg_tube(body, pcs: dict, names: list, to: str, nm: str, U: np.ndarray, z_w: float, gap: float,
              cache: dict) -> tuple | None:
    """Start positions of a trouser leg's piece on a tube round the LEG (as a sleeve lies on the arm), and the share
    of them to use (0 at the crotch, 1 from LEG_BLEND under it; above, the seat's cylinder). None when the leg isn't
    one front and one back piece; wrap "follow": false keeps the seat's cylinder all the way down.

    The tube: a smooth axis through the leg's sections' plan middles (quadratic in height); round it, in the plane
    SQUARE to the axis, the leg's section (its radius per direction, smoothed LEG_SMOOTH up and down the leg) pushed
    out to the cloth's girth at that row (+ LEG_APART for each seam, at least LEG_CLEAR off the leg). Pattern y runs
    down the axis (length along the leg, not plumb). The front piece's crease line on the section's front, the back
    piece's half the girth round, each row by arc length to either side (the crease line drifts at most LEG_DRIFT
    per m: the rows' middles run out toward the fork). Below LEG_EASE over the ankle the leg is compressed along its
    length until the hem clears the foot.
    A narrowing tube still SHEARS the cloth (a column a quarter girth from the crease leans by about a quarter of the
    narrowing rate; a slim leg narrows ~0.8 m per m down the thigh), as does the hand-over from the seat: place()'s
    start relaxation (_relax_strain: every triangle's singular values clamped) takes that out, the crease rows free.
    Start on su_garrett: seams 15 / 8 mm apart (p50, side / inseam), every triangle within 5% of the pattern.
    What it took: on the seat's one cylinder a slim leg's front and back started as slabs (side seams 174 / inseams
    213 mm apart); rows following each section's own hull put the leg's taper and every slice's jitter into the
    columns; horizontal rows on a leg that splays 11 deg in an A-pose are a shear of that slope; the back laid on
    from the front's side seam drifted with the side seam's slope; an edge-length relaxation can't see shear (every
    edge within 5%, the triangles 9-12% along the diagonal); fixed crease rows held a leaning column's shear."""
    at = body.at
    if "crotch_z" not in at or "knee.L" not in body.J:
        return None
    sgn = 1.0 if to.endswith("L") else -1.0
    mine = [o for o in names if pcs[o]["wrap"].get("to") == to and not pcs[o]["wrap"].get("lies_on")]
    fr = [o for o in mine if pcs[o]["wrap"].get("side", "front") == "front"]
    bk = [o for o in mine if pcs[o]["wrap"].get("side", "front") == "back"]
    if len(fr) != 1 or len(bk) != 1 or nm not in (fr[0], bk[0]):
        return None
    zc = float(at["crotch_z"])
    z_foot = float(body.J["ankle.L"][2]) + 0.04 if "ankle.L" in body.J else 0.05
    Pf, Pb = pcs[fr[0]]["P"] * [sgn, 1.0], pcs[bk[0]]["P"] * [sgn, 1.0]
    zt = zc - LEG_TOP  # the tube's top level (above it, both legs are one loop)
    if (to, "axis") not in cache:
        zs_ = np.arange(z_foot, zt - 0.004, 0.01)
        Hs = [(z_, H_) for z_ in zs_ if (H_ := _leg_section(body, sgn, float(z_))) is not None]
        if len(Hs) < 8:
            return None
        zh = np.array([z_ for z_, _ in Hs])
        mx = np.array([0.5 * (H_[:, 0].min() + H_[:, 0].max()) for _, H_ in Hs])
        my = np.array([0.5 * (H_[:, 1].min() + H_[:, 1].max()) for _, H_ in Hs])
        px, py = np.polyfit(zh, mx, 2), np.polyfit(zh, my, 2)
        # each section round the axis as a radius per direction, smoothed up and down the leg (a section's hull
        # changes by the slice: the front point stepped 5 mm a cm at the knee, a shear past the strain limit)
        th = np.linspace(0, 2 * np.pi, 180, endpoint=False)
        dirs = np.c_[np.cos(th), np.sin(th)]
        R = np.zeros((len(Hs), len(th)))
        for j, (z_, H_) in enumerate(Hs):
            Q = H_ - [np.polyval(px, z_), np.polyval(py, z_)]
            Q2 = np.roll(Q, -1, axis=0)
            # ray from the axis along each direction against each hull edge
            e_ = Q2 - Q
            for i_, d_ in enumerate(dirs):
                den = d_[0] * e_[:, 1] - d_[1] * e_[:, 0]
                with np.errstate(divide="ignore", invalid="ignore"):
                    tt = (Q[:, 0] * e_[:, 1] - Q[:, 1] * e_[:, 0]) / den
                    uu = (Q[:, 0] * d_[1] - Q[:, 1] * d_[0]) / den
                hit = (uu >= -1e-9) & (uu <= 1 + 1e-9) & (tt > 0)
                R[j, i_] = tt[hit].max() if hit.any() else np.linalg.norm(Q, axis=1).max()
        wz = np.exp(-0.5 * ((zh[:, None] - zh[None, :]) / LEG_SMOOTH) ** 2)
        R = (wz @ R) / wz.sum(1, keepdims=True)
        ab = [R[j][:, None] * dirs for j in range(len(Hs))]  # each section round the axis, smoothed
        # height <-> length down the axis from the tube's top
        zg = np.linspace(zt, min(z_foot, z_w - 1.3), 600)
        sl = np.sqrt(1 + np.polyval(np.polyder(px), zg) ** 2 + np.polyval(np.polyder(py), zg) ** 2)
        along = np.r_[0, np.cumsum(0.5 * (sl[1:] + sl[:-1]) * -np.diff(zg))]
        cache[(to, "axis")] = (px, py, zh, ab, zg, along)
    px, py, zh, ab, zg, along = cache[(to, "axis")]

    Lk = float(np.interp(z_foot + LEG_EASE, zg[::-1], along[::-1]))

    def eased(L):
        """Length down the axis of the pattern's row L down (the leg under Lk compressed by the leg's ease)."""
        f_ = cache.get((to, "ease"), 1.0)
        return np.where(L > Lk, Lk + (L - Lk) * f_, L)

    def frame(z):
        """The axis point at height z and the plan-x / plan-y directions square to the axis there."""
        T = np.array([np.polyval(np.polyder(px), z), np.polyval(np.polyder(py), z), 1.0])
        T /= np.linalg.norm(T)
        ux = np.array([1.0, 0, 0]) - T[0] * T
        ux /= np.linalg.norm(ux)
        uy = np.array([0, 1.0, 0]) - T[1] * T
        uy -= (uy @ ux) * ux
        uy /= np.linalg.norm(uy)
        return np.array([np.polyval(px, z), np.polyval(py, z), z]), ux, uy

    ymin = min(Pf[:, 1].min(), Pb[:, 1].min()) + 0.001

    if (to, "girth") not in cache:
        # the tube's girth down the leg: the cloth's (+ the seams' LEG_APART) and enough to clear the leg, but never
        # shrinking faster than LEG_TAPER per m. On a tube that narrows, a column a quarter girth from the crease
        # leans by a quarter of the narrowing rate (a shear: about an eighth of it in stretch), and a slim leg's
        # pattern narrows ~0.8 m per m between the crotch and the knee: there the seams start apart instead
        Lg = np.arange(0.0, zt - z_w - ymin + 0.01, 0.005)
        Wg = np.full(len(Lg), np.nan)
        for j, L_ in enumerate(Lg):
            y_ = max(zt - L_ - z_w, ymin)
            xf_, xb_ = _piece_xs_at(Pf, y_), _piece_xs_at(Pb, y_)
            if len(xf_) >= 2 and len(xb_) >= 2:
                Wg[j] = (max(xf_) - min(xf_)) + (max(xb_) - min(xb_))
        okg = np.isfinite(Wg)
        Lg, Wg = Lg[okg], Wg[okg]
        need_ = np.array([pattern.length(ab[int(np.argmin(np.abs(zh - min(max(float(np.interp(L_, along, zg)), z_foot),
                                                                                 zt - 0.005))))], closed=True)
                          for L_ in Lg]) + 2 * np.pi * LEG_CLEAR
        G = np.maximum(Wg + 2 * LEG_APART, need_)
        for j in range(1, len(G)):
            G[j] = max(G[j], G[j - 1] - LEG_TAPER * (Lg[j] - Lg[j - 1]))
        cache[(to, "girth")] = (Lg, G)
    Lg, G = cache[(to, "girth")]

    def level(L):
        """(ellipse polygon round 0 in its own plane, its front point, the girth past the cloth) for the row L down
        the pattern from the tube's top (by the cm), laid at its eased length down the axis."""
        key = (to, int(round(L * 100)))
        if key in cache:
            return cache[key]
        Lq = key[1] / 100.0
        zz = float(np.interp(eased(Lq), along, zg))
        zs = min(max(zz, z_foot), zt - 0.005)
        y = max(zt - Lq - z_w, ymin)
        # (each piece read no lower than its own hem: cut to a break the back is 12 mm longer, and the front's last
        # rows, rounded to a cm level under its own hem, had no width: they fell back to the seat's cylinder, the
        # front hem's vertices at centre front between the feet, 27 cm triangles in the start: tr_22 .. tr_24)
        xf, xb = _piece_xs_at(Pf, max(y, float(Pf[:, 1].min()) + 0.001)), _piece_xs_at(Pb, max(y, float(Pb[:, 1].min()) + 0.001))
        if len(xf) < 2 or len(xb) < 2:
            cache[key] = None
            return None
        W = (max(xf) - min(xf)) + (max(xb) - min(xb))
        H = ab[int(np.argmin(np.abs(zh - zs)))]
        # the section pushed out to the cloth's girth (at least LEG_CLEAR off the leg; the seams start at least
        # LEG_APART apart: edge on edge they read as crossings)
        Gq = float(np.interp(Lq, Lg, G))
        m_ = float(np.clip((Gq - pattern.length(H, closed=True)) / (2 * np.pi), LEG_CLEAR, 0.15))
        E = _densify(_offset_hull(H, m_), 0.002)
        E = E * max(1.0, Gq / pattern.length(E, closed=True))
        fr_ = E[E[:, 1] < 0]
        cache[key] = (E, fr_[np.argmin(np.abs(fr_[:, 0]))], pattern.length(E, closed=True) - W)
        return cache[key]

    z0 = z_w + U[:, 1]
    t = np.clip((zt - z0) / LEG_BLEND, 0.0, 1.0)
    ok = t > 0
    front = nm == fr[0]
    s = np.zeros(len(U))
    Lr = np.maximum(zt - z0, 0.0)  # the pattern's length under the tube's top
    if (to, nm, "anchor") not in cache:
        # each row's arc is measured from the piece's crease line: its row's middle, but drifting at most
        # LEG_DRIFT per m of length (from the hem up): a column's sideways drift is shear, and the rows' middles run
        # out toward the fork near the crotch (8% at the top of the thigh)
        P_ = Pf if front else Pb
        yg = np.arange(P_[:, 1].min() + 0.002, zt - z_w - 0.004, 0.005)
        mg = np.array([0.5 * (max(x_) + min(x_)) if len(x_ := _piece_xs_at(P_, float(y_))) >= 2 else np.nan for y_ in yg])
        ok_ = np.isfinite(mg)
        yg, mg = yg[ok_], mg[ok_]
        an = mg.copy()
        for j in range(1, len(an)):
            an[j] = an[j - 1] + np.clip(mg[j] - an[j - 1], -LEG_DRIFT * (yg[j] - yg[j - 1]), LEG_DRIFT * (yg[j] - yg[j - 1]))
        cache[(to, nm, "anchor")] = (yg, an)
    yg, an = cache[(to, nm, "anchor")]
    for i in np.where(ok)[0]:
        y = float(zt - z_w - max(Lr[i], 0.005))
        if not len(yg) or y < yg[0] - 0.01:
            ok[i] = False
            continue
        # arc from the piece's crease toward the outside; the back's from half the girth round
        s[i] = sgn * U[i, 0] - float(np.interp(y, yg, an))
    # a hem cut for a shoe ends under the ankle, where the foot runs forward: the leg from LEG_EASE over the ankle
    # down is compressed along its length (evenly, so the rows stay apart and square) until the hem clears the
    # foot's top (the instep) by the clearance. Compression a strain-limited solver can start from; squeezed into the
    # room over the instep alone the hem's rows lay mm apart and crossed, turned out over it they stretched 1.8x
    if (to, "ease") not in cache and LEG_BREAK > 0:  # the hem stops on the shoe instead (below): no ease up the leg
        cache[(to, "ease")] = 1.0
    if (to, "ease") not in cache:  # one compression for the leg (both pieces: their seams stay level)
        f = 1.0
        L_hem = zt - (z_w + min(Pf[:, 1].min(), Pb[:, 1].min()))
        z_hem = float(np.interp(L_hem, along, zg))
        Vall = body.V if not getattr(body, "worn", None) else np.r_[body.V, np.asarray(body.worn["V"], float)]
        Vb = Vall[(Vall[:, 2] < z_foot + 0.02) & (sgn * Vall[:, 0] > 0)]  # (the shoes too: garment key "collide")
        lv = level(L_hem)
        if lv is not None and len(Vb) and L_hem > Lk:
            from scipy.spatial import cKDTree
            A_, ux_, uy_ = frame(z_hem)
            ring = A_[:2] + lv[0][:, :1] * ux_[:2] + lv[0][:, 1:] * uy_[:2]
            d_, _ = cKDTree(ring).query(Vb[:, :2])
            under = Vb[d_ < gap + 0.012]  # the foot under the hem's line, and just round it
            if len(under):
                L_ok = float(np.interp(under[:, 2].max() + gap, zg[::-1], along[::-1]))
                f = float(np.clip((L_ok - Lk) / (L_hem - Lk), 0.5, 1.0))
        for k_ in [k_ for k_ in cache if k_[0] == to and isinstance(k_[1], int)]:
            del cache[k_]  # (levels made before the ease was known)
        cache[(to, "ease")] = f
    L = eased(Lr)
    out = np.zeros((len(U), 3))
    Lq = np.floor(Lr * 100)
    for lq in np.unique(Lq[ok]):
        sel_ = ok & (Lq == lq)
        lv0, lv1 = level(lq / 100.0), level((lq + 1) / 100.0)
        if lv0 is None or lv1 is None:
            ok &= ~sel_
            continue
        # the back's crease half the girth round, its outside back the way the front's came
        arc = (lambda lv: s[sel_]) if front else (lambda lv: 0.5 * pattern.length(lv[0], closed=True) - s[sel_])
        q0 = _arc_point(lv0[0], lv0[1], arc(lv0), sgn)
        q1 = _arc_point(lv1[0], lv1[1], arc(lv1), sgn)
        f_ = np.clip(Lr[sel_] * 100 - lq, 0.0, 1.0)[:, None]
        q = (1 - f_) * q0 + f_ * q1
        for j, i in enumerate(np.where(sel_)[0]):
            A_, ux_, uy_ = frame(float(np.interp(L[i], along, zg)))
            out[i] = A_ + q[j, 0] * ux_ + q[j, 1] * uy_
    if LEG_BREAK > 0 and ok.any():
        out = _hem_on_shoe(body, out, U, ok, sgn, z_foot, gap)
    t[~ok] = 0.0
    return out, t


SHOE_PROBE = 0.055  # m from the ankle joint (in plan) where a trouser hem's front / side / back stands over the shoe


def shoe_heights(W: np.ndarray, ankle: np.ndarray, r: float = SHOE_PROBE) -> dict:
    """The tailor's tape on the shoes (what a trouser's hem is cut to, measured with the shoes on): the height of the
    worn parts' top (mm) under the hem's front, outside and back, SHOE_PROBE in plan from the ankle (left side)."""
    out = {}
    W = W[W[:, 0] > 0]  # (the left shoe)
    if not len(W):
        return out
    for key, d in (("shoeFront", (0.0, -1.0)), ("shoeSide", (1.0, 0.0)), ("shoeBack", (0.0, 1.0))):
        p = ankle[:2] + r * np.asarray(d)
        near = np.linalg.norm(W[:, :2] - p, axis=1) < 0.015
        if near.any():
            out[key] = round(float(W[near, 2].max()) * 1000, 1)
    return out if len(out) == 3 else {}


def _hem_on_shoe(body, out: np.ndarray, U: np.ndarray, ok: np.ndarray, sgn: float, z_foot: float,
                 gap: float) -> np.ndarray:
    """A trouser leg cut to end on the shoe, laid as worn: each column of the leg (pattern x) hangs straight down to
    the floor less the hem's height, and where the foot or the shoe (garment key "collide") stands under it the
    column stops `gap` over that, the length it can't use gathered into the bottom LEG_BREAK of the column (pattern
    distance from its hem, linearly). That gathered length is the BREAK: a fold over the shoe's front, the back
    hanging lower, as a tailor cuts it. (Compressed evenly from 35 cm over the ankle the leg stored its length as
    4-5% crinkle all down the shin, the hem's back 4 cm over the floor and no break.)"""
    # what a hem can rest ON: the body's and the worn parts' surfaces that face up (a shoe's vamp, its counter's top
    # edge, the instep), not the walls round the ankle (su_garrett's shoe part stands round the ankle to 10 cm: taken
    # as support, the hems stopped on its collar 3 cm over the shoe's visible top)
    srcs = [(body.V, body.T)] + ([(np.asarray(body.worn["V"], float), np.asarray(body.worn["F"], np.int64))]
                                 if getattr(body, "worn", None) else [])
    Vb = []
    for V_, T_ in srcs:
        if not len(V_):
            continue
        sel_ = (V_[:, 2] < z_foot + 0.02) & (sgn * V_[:, 0] > 0)
        if len(T_):
            fn_ = np.cross(V_[T_[:, 1]] - V_[T_[:, 0]], V_[T_[:, 2]] - V_[T_[:, 0]])
            vn_ = np.zeros_like(V_)
            for c_ in range(3):
                np.add.at(vn_, T_[:, c_], fn_)
            vn_ /= np.maximum(np.linalg.norm(vn_, axis=1, keepdims=True), 1e-12)
            sel_ &= np.abs(vn_[:, 2]) > HEM_REST_NZ  # (either winding: a worn shell may face in)
        Vb.append(V_[sel_])
    Vb = np.concatenate(Vb) if Vb else np.zeros((0, 3))
    if not len(Vb):
        return out
    from scipy.spatial import cKDTree
    tree = cKDTree(Vb[:, :2])
    idx = np.where(ok)[0]
    floor = np.full(len(out), -np.inf)
    for j, nb in zip(idx, tree.query_ball_point(out[idx, :2], LEG_FOOT_R)):
        if nb:
            floor[j] = float(Vb[nb, 2].max()) + gap
    deficit = np.where(ok, floor - out[:, 2], -np.inf)
    col = np.round(U[:, 0] / 0.01).astype(int)
    cols = np.unique(col[ok])
    dc = {c: max(0.0, float(deficit[ok & (col == c)].max())) if (ok & (col == c)).any() else 0.0 for c in cols}
    # (smoothed across neighbouring columns: a step between columns is shear)
    ds = {c: float(np.mean([dc.get(c + k, dc[c]) for k in range(-2, 3)])) for c in cols}
    ds = {c: max(ds[c], dc[c]) for c in cols}
    out = out.copy()
    for c in cols:
        if ds[c] <= 0:
            continue
        sel = np.where(ok & (col == c))[0]
        d_hem = U[sel, 1] - U[sel, 1].min()
        w = np.clip(1.0 - d_hem / LEG_BREAK, 0.0, 1.0)
        out[sel, 2] += ds[c] * w
    # and nothing inside the worn parts: what hangs beside a shoe (its sides, the counter at the back) is pushed out
    # of it along its surface (resting only on what faces up, the sides of the hem went through the shoe's walls)
    return _clear_of_worn(out, ok & (out[:, 2] < z_foot + 0.12), body, max(gap, WORN_CLEAR))


def _clear_of_worn(X: np.ndarray, free: np.ndarray, body, gap: float, rounds: int = 4) -> np.ndarray:
    """X with its `free` vertices at least `gap` outside the body's worn parts (garment key "collide": shoes under a
    hem), pushed along the worn surface's normal. Body.push_out / clearance see the body alone."""
    wn = getattr(body, "worn", None)
    idx = np.where(free)[0]
    if wn is None or not len(wn.get("F", [])) or not len(idx):
        return X
    from .closures import _closest_on
    W_ = np.asarray(wn["V"], float)
    F_ = np.asarray(wn["F"], np.int64)
    fn_ = np.cross(W_[F_[:, 1]] - W_[F_[:, 0]], W_[F_[:, 2]] - W_[F_[:, 0]])
    orient = 1.0 if float(np.sum(fn_ * (W_[F_].mean(1) - W_.mean(0)))) >= 0 else -1.0  # (a shell may face in)
    lo, hi = W_.min(0) - 0.03, W_.max(0) + 0.03
    idx = idx[np.all((X[idx] > lo) & (X[idx] < hi), 1)]
    if not len(idx):
        return X
    X = X.copy()
    X0 = X[idx].copy()
    for _ in range(rounds):
        q_, n_, _i = _closest_on(X[idx], W_, F_)
        sd_ = np.sum((X[idx] - q_) * n_, 1) * orient
        bad_ = sd_ < gap
        if not bad_.any():
            break
        # (a step no longer than WORN_STEP, the whole move no longer than WORN_REACH: a vertex deep inside a shell
        # (a shoe is a hollow shell round the foot: its inner wall's normal points into the cavity) was sent on
        # through the far wall round after round: a trouser hem's centre-front vertices ended 11 cm away between the
        # toes, 27 cm triangles, and the crossing search over them took 17 GB)
        X[idx[bad_]] += (np.minimum(gap - sd_[bad_], WORN_STEP) * orient)[:, None] * n_[bad_]
        mv_ = X[idx] - X0
        ln_ = np.linalg.norm(mv_, axis=1)
        far_ = ln_ > WORN_REACH
        X[idx[far_]] = X0[far_] + mv_[far_] * (WORN_REACH / ln_[far_])[:, None]
    return X


WORN_STEP = 0.012  # m: the most one round of _clear_of_worn moves a vertex
WORN_REACH = 0.03  # m: the most _clear_of_worn moves a vertex in all


LEG_BREAK = 0.09  # m above a trouser hem over which the length the shoe stops is gathered (the break; 0 = the old ease)
WORN_CLEAR = 0.005  # m a start is kept off the worn parts (vertices: a 2 cm triangle's chord dips ~3 mm between them;
# the solver's contact offset is 1-2 mm)
HEM_REST_NZ = 0.5  # a surface a hem rests on faces up at least this much (|normal z|)
LEG_FOOT_R = 0.012  # m: the foot or shoe within this of a leg column (in plan) stands under it


def _piece_xs_at(P: np.ndarray, y: float) -> list:
    """Where the outline P crosses the level y (x values)."""
    xs = []
    for a, b in zip(P, np.roll(P, -1, axis=0)):
        if (a[1] - y) * (b[1] - y) <= 0 and a[1] != b[1]:
            xs.append(float(a[0] + (y - a[1]) / (b[1] - a[1]) * (b[0] - a[0])))
    return xs


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
SMOOTH_CLEAR = 0.004  # ZOZO bands (cuffs, neck pieces): its contact offset 2 mm + gap 1 mm + 1 mm
HUG_CLEAR = 0.0012  # a made band buttoned round the neck (a collar stand): it is HELD in the sim, not contact-solved, so
# it needs no solver standoff: constructed closed this far off the skin and pinned free of body contact (B["hug"])
BAND_CLEAR = 0.0025  # a made band closed on itself round the torso (a waistband): it grips. The sim then runs with
# the body's contact offset 1 mm + gap 0.5 mm (build(): B["band_clear"]). At 4 mm a band needs 25 mm more girth than
# the body: a waistband with 2-3% ease could never start closed
SMOOTH_FACE_CLEAR = 0.0035  # ... and the least clearance of their faces (centres, edge midpoints)


def _sewn_arc(B: dict, M: dict, nm: str, R: float):
    """(centre, radius) of the circle through a neck piece's sewn edge in the flat (the edge sewn to a piece not on
    the neck, else to any other piece), or None if it is near straight (radius > 3 m) or tighter than a cone allows."""
    k = M["names"].index(nm)
    sew = np.asarray(M["sew"])
    pid = M["piece"]
    mine = np.r_[sew[pid[sew[:, 0]] == k, 0], sew[pid[sew[:, 1]] == k, 1]]
    other = np.r_[sew[pid[sew[:, 0]] == k, 1], sew[pid[sew[:, 1]] == k, 0]]
    keep = pid[other] != k
    ss = None
    if "sew_seam" in M and B.get("seam_notes"):  # not the joins of one cloth cut for placement (pattern_draft hinges)
        virt = {i for i, s_ in enumerate(B["seams"]) if (B["seam_notes"].get(json.dumps(s_)) or {}).get("virtual")}
        ss = np.r_[np.asarray(M["sew_seam"])[pid[sew[:, 0]] == k], np.asarray(M["sew_seam"])[pid[sew[:, 1]] == k]]
        keep &= ~np.isin(ss, list(virt))
    far = keep & np.array([B["pieces"][M["names"][pid[o]]]["wrap"].get("to") != "neck" for o in other], bool)
    use = far if far.any() else keep
    if ss is not None and use.any():  # ONE seam: the longest (a facing's end sewn at a corner isn't on the arc)
        ids, cnt = np.unique(ss[use], return_counts=True)
        use = use & (ss == ids[np.argmax(cnt)])
    pts = M["uv"][np.unique(mine[use])]
    if len(pts) < 5:
        return None
    A = np.c_[2 * pts, np.ones(len(pts))]
    sol, *_ = np.linalg.lstsq(A, (pts ** 2).sum(1), rcond=None)
    c = sol[:2]
    rho = float(np.sqrt(sol[2] + c @ c))
    if rho > 3.0 or rho <= R * 1.02:
        return None
    return c, rho


def _neck_frame(body: "Body", nb: np.ndarray, d: np.ndarray, R: float, band: float | None = None) -> tuple[float, np.ndarray]:
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
    if band is not None:
        # a band `band` tall laid round the neck's own shape (place(): the hull spiral): where its girth fits (the
        # neckline was drafted for that girth: seated lower, at the neck's base, the yoke had a centimetre of cloth
        # too much and bunched up behind the collar), but no higher than keeps its top on the neck (a 3 cm stand on a
        # short neck reached the jaw)
        hs_ = [r["h"] for r in rows if r["neck"]]
        base = float(np.clip(base, min(hs_), max(min(hs_), max(hs_) - band)))
    return float(base), origin


def _at_pattern(X: np.ndarray, M: dict, k: int, q: np.ndarray) -> np.ndarray:
    """Where piece k's pattern point q lies in X: the affine map of the piece's triangle that holds q (the nearest
    one past its outline)."""
    F = M["F"][M["piece"][M["F"][:, 0]] == k]
    A = M["uv"][F]
    cen = A.mean(1)
    q = np.asarray(q, float)
    best, bd = 0, np.inf
    for t in np.argsort(((cen - q) ** 2).sum(1))[:12]:
        e1, e2 = A[t, 1] - A[t, 0], A[t, 2] - A[t, 0]
        det = e1[0] * e2[1] - e1[1] * e2[0]
        if abs(det) < 1e-14:
            continue
        w_ = q - A[t, 0]
        b1, b2 = (w_[0] * e2[1] - w_[1] * e2[0]) / det, (e1[0] * w_[1] - e1[1] * w_[0]) / det
        out = max(0.0, -b1) + max(0.0, -b2) + max(0.0, b1 + b2 - 1)
        if out < bd:
            best, bd, bb = t, out, (b1, b2)
    P = X[F[best]]
    return P[0] + bb[0] * (P[1] - P[0]) + bb[1] * (P[2] - P[0])


def _on_seam(M: dict, X: np.ndarray, uv: np.ndarray, pid: np.ndarray, k: int, nm: str, w: dict,
             body: "Body", pcs: dict | None = None, placed: set | None = None, chain_body: "Body | None" = None) -> np.ndarray:
    """Wrap "seam": a piece laid from the edge it is sewn to (a tailored collar's stand on the jacket's neckline, a
    collar on its stand, a band on an edge): its sewn edge lies ON the edge of the pieces already placed that it is
    sewn to (the seam's own vertex pairs), and the piece runs on from there in one direction: `dir` "up" (default;
    world z), or the body's outward normal there with `lean` deg (+ out, - in toward the body), square to the edge.
    Pattern distances from the sewn edge and along it are kept (past the edge's ends it runs on straight); `out` m
    lifts it off the body's normal. Where the placed edge curves otherwise than the pattern's the piece starts
    stretched there: for draped pieces. A neck band as a circle (wrap "neck") can't follow a neckline that lies on
    the shoulders and runs down onto the chest: placed so, a jacket's stand stood round the top of the neck."""
    sw = M["sew"]
    mine = np.where(pid == k)[0]
    a = np.r_[sw[(pid[sw[:, 0]] == k) & (pid[sw[:, 1]] < k), 0], sw[(pid[sw[:, 1]] == k) & (pid[sw[:, 0]] < k), 1]]
    b = np.r_[sw[(pid[sw[:, 0]] == k) & (pid[sw[:, 1]] < k), 1], sw[(pid[sw[:, 1]] == k) & (pid[sw[:, 0]] < k), 0]]
    if len(np.unique(a)) < 3:
        raise ClothError(f'piece {nm}: wrap "seam" needs a seam to a piece placed before it (pieces are placed in '
                         "the order they are listed)")
    ua, inv = np.unique(a, return_inverse=True)
    Cp = np.zeros((len(ua), 3))
    np.add.at(Cp, inv, X[b])
    Cp /= np.bincount(inv)[:, None]
    # the sewn edge in order: along its main direction in the pattern
    Q = uv[ua]
    ax = np.linalg.svd(Q - Q.mean(0))[2][0]
    o = np.argsort((Q - Q.mean(0)) @ ax)
    ax_s = ax if (Q[o[-1]] - Q[o[0]]) @ ax > 0 else -ax
    q_mid = Q.mean(0)
    Q, Cp = Q[o], Cp[o]
    vn, tree = body.normals()
    lay = float(w.get("out", 0.0)) + 0.003
    # the edge it lies on, at the PATTERN's lengths: the placed edge is not one curve yet (a neckline's pieces start
    # apart: fronts on the front of the body, backs on the back, the shoulder seams open: 778 mm of placed edge for a
    # 291 mm stand). From the middle of the sewn edge outward, each step goes the way the placed edge goes, as long
    # as the pattern's segment, along the body's surface (`out` off it)
    lq = np.linalg.norm(np.diff(Q, axis=0), axis=1)

    def snap(P):
        n = vn[tree.query(P)[1]]
        return P - n * (float(body.clearance(P[None])[0]) - lay)
    mid = int(np.argmin(np.abs(np.cumsum(np.r_[0, lq]) - 0.5 * lq.sum())))
    Cs = np.zeros_like(Cp)
    Cs[mid] = snap(Cp[mid])
    whole = float(np.linalg.norm(np.diff(Cp, axis=0), axis=1).sum()) <= 1.15 * float(lq.sum())
    if whole:  # one piece's edge, as long as the pattern's (a collar on its stand): that edge itself
        Cs = Cp.copy()
    worn = None
    if w.get("worn") and pcs is not None and "hps.L" in body.at:
        # "worn": the edge it is sewn to as it will lie WORN, not where its pieces start (torso pieces start apart
        # on a cylinder and the sewing brings them in; a made piece is held where it is placed): each torso piece's
        # point at its own pattern x and height (pattern y = 0 at the neck point) on the front or the back of the
        # body. Marched along the body toward where the fronts START, a jacket's neckline hugged the neck like a
        # shirt's band and ended at the throat, climbing the neck's side.
        hz = float(body.at["hps.L"][2])
        # the worn edge lies on the body the worn tops were laid on (chain_body: under another garment, that garment's
        # body without its standing collar): snapped onto the collar of the shirt under it, a jacket's 473 mm neckline
        # chain rose up the shirt collar to where its girth fitted, and the collar started 15-20 mm over the jacket's
        # back neck and over the shirt collar's top (Garrett: collar_show -45, the jacket hung from it)
        cb_ = chain_body or body
        vnc_, treec_ = cb_.normals()

        def snap2(P):
            n = vnc_[treec_.query(P)[1]]
            return P - n * (float(cb_.clearance(P[None])[0]) - lay)

        vny_ = vn[:, 1]
        side_ix = {True: np.where(vny_ > -0.3)[0], False: np.where(vny_ < 0.3)[0]}

        def worn_pt(x0, z0, back, kk=None):
            if placed and kk is not None and int(kk) in placed:
                # a piece already laid where it is worn (place: _worn_top): its own point there
                return _at_pattern(X, M, int(kk), [x0, z0 - hz])
            # (only the body's own back / front: at the nape the nearest vertex in x, z was one of the throat's)
            ix_ = side_ix[bool(back)]
            dxz = np.hypot(body.V[ix_, 0] - x0, body.V[ix_, 2] - z0)
            if dxz.min() >= 0.008:
                # past the body's outline at that height (a jacket's neck point lies wider than the neck, on the
                # slope of the shoulder; the top of the shoulder itself): the cloth lies on the body's top under the
                # point: the highest vertex at that x below it
                col = np.where((np.abs(body.V[:, 0] - x0) < 0.006) & (body.V[:, 2] < z0) & (body.V[:, 2] > z0 - 0.12))[0]
                if len(col):
                    pv = body.V[col[np.argmax(body.V[col, 2])]]
                    return np.array([x0, pv[1], pv[2]])
            near_ = ix_[dxz <= max(dxz.min() + 0.006, 0.012)]
            yy = body.V[near_, 1]
            pv = body.V[near_[np.argmax(yy) if back else np.argmin(yy)]]
            # the point itself at the body's depth there, not the body's vertex (two points given one vertex made
            # triangles of no size in a made piece's rest: "1652% stretched", the layered start failed)
            f_ = 1.0 if dxz.min() < 0.008 else 0.3
            return np.array([pv[0] + f_ * (x0 - pv[0]), pv[1], pv[2] + f_ * (z0 - pv[2])])
        Wb = np.full((len(b), 3), np.nan)
        for i_, vb in enumerate(b):
            wb_ = pcs[M["names"][pid[vb]]]["wrap"]
            if wb_.get("to", "torso") != "torso":
                continue
            Wb[i_] = worn_pt(float(uv[vb, 0]), hz + float(uv[vb, 1]), wb_.get("side") == "back", pid[vb])
        if not np.isnan(Wb).any():
            Wp = np.zeros((len(ua), 3))
            np.add.at(Wp, inv, Wb)
            Wp = (Wp / np.bincount(inv)[:, None])[o]
            for _ in range(3):
                Wp[1:-1] = 0.25 * Wp[:-2] + 0.5 * Wp[1:-1] + 0.25 * Wp[2:]
            sw_ = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Wp, axis=0), axis=1))]
            sp_ = np.r_[0, np.cumsum(lq)]
            # at the pattern's own lengths from the edge's middle (a neckline's ease stays in the piece)
            at_ = np.clip(sw_[mid] + (sp_ - sp_[mid]), 0.0, sw_[-1])
            Cs = np.stack([snap2(np.array([np.interp(a_, sw_, Wp[:, c_]) for c_ in range(3)])) for a_ in at_])
            if w.get("lay") == "notched":
                # the worn neckline as a chain: the pattern's lengths between its samples (kept), on the body the
                # seam's clearance off it (kept), each sample drawn toward where its partners' pattern x and height
                # put it. The chart alone is not the pattern's lengths: a jacket's neck point lies wider than the
                # neck, over the ridge of the trapezius from the back neck (the chart's step there was 42 mm for 21),
                # and smoothing the charted curve and snapping it back out walked it 1-2 cm up the slope
                Wr = np.zeros((len(ua), 3))
                np.add.at(Wr, inv, Wb)
                Wr = np.stack([snap2(q_) for q_ in (Wr / np.bincount(inv)[:, None])[o]])
                wt_ = np.full(len(Cs), 0.25)
                ln_ = (w.get("turn") or {}).get("line")
                if ln_ is not None and len(ln_) >= 4:  # (past the point the roll line meets the edge the chart is of the unturned front)
                    ja, jb = sorted(int(np.argmin(((Q - np.asarray(q_, float)) ** 2).sum(1))) for q_ in (ln_[1], ln_[-2]))
                    wt_[:ja] = wt_[jb + 1:] = 0.02
                # (except at the middle (CB), held where the worn back's centre is: where the worn neckline is longer than
                # the pattern's (Garrett: 1.30x, his back neck curves round more than the draft's) the chain cut the
                # corner up the nape and the collar started 20 mm over the jacket's back neck and the shirt collar's top)
                sp_c = np.abs(sp_ - sp_[mid])
                hold_ = np.where(sp_c < NOTCH_HOLD_CB, 0.25 * (1.0 - sp_c / NOTCH_HOLD_CB), 0.0) \
                    * float(sw_[-1] > NOTCH_HOLD_RATIO * sp_[-1])
                for it_ in range(160):  # (the pull toward the chart fades out: the lengths and the body decide the end)
                    Cs += np.maximum(wt_ * max(0.0, 1.0 - it_ / 110.0), hold_)[:, None] * (Wr - Cs)
                    for _ in range(4):
                        d_ = Cs[1:] - Cs[:-1]
                        l_ = np.maximum(np.linalg.norm(d_, axis=1), 1e-9)
                        c_ = 0.5 * ((l_ - lq) / l_)[:, None] * d_
                        Cs[:-1] += c_
                        Cs[1:] -= c_
                    Cs = np.stack([snap2(q_) for q_ in Cs])
                for _ in range(6):
                    d_ = Cs[1:] - Cs[:-1]
                    l_ = np.maximum(np.linalg.norm(d_, axis=1), 1e-9)
                    c_ = 0.5 * ((l_ - lq) / l_)[:, None] * d_
                    Cs[:-1] += c_
                    Cs[1:] -= c_
            worn = round(float(sw_[-1] / max(sp_[-1], 1e-9)), 3)
            whole = True
            # each edge sample's partner: its piece and pattern point (the turned side past a roll line's end is
            # laid in that piece's own pattern: below)
            first_ = np.zeros(len(ua), np.int64)
            first_[inv[::-1]] = np.arange(len(b))[::-1]
            Bk, Bq = pid[b[first_]][o], uv[b[first_]][o]
    for rng, sg in (() if whole else ((range(mid, len(Cp) - 1), 1), (range(mid, 0, -1), -1))):
        jumped = False
        for i in rng:
            j = i + sg
            dv = Cp[j] - Cp[i]
            # past a gap between the placed pieces (back neck -> the front's neckline, the shoulder seam open) the
            # placed edge's own direction means nothing here: head for where the edge ends (the gorge), along the body
            jumped = jumped or np.linalg.norm(dv) > 1.5 * lq[min(i, j)] + 0.004
            if jumped:
                dv = Cp[-1 if sg > 0 else 0] - Cs[i]
            n = vn[tree.query(Cs[i])[1]]
            dv = dv - n * (dv @ n)
            ln = np.linalg.norm(dv)
            if ln < 1e-9:
                dv, ln = Cp[j] - Cp[i], max(np.linalg.norm(Cp[j] - Cp[i]), 1e-9)
            Cs[j] = snap(Cs[i] + dv / ln * lq[min(i, j)])
    for _ in range(0 if (worn is not None and w.get("lay") == "notched") else 2):
        Cs[1:-1] = 0.25 * Cs[:-2] + 0.5 * Cs[1:-1] + 0.25 * Cs[2:]
    inside = uv[mine].mean(0)
    hub = Cs.mean(0)
    up0 = np.array([0.0, 0.0, 1.0])
    lean = math.radians(float(w.get("lean", 0.0)))
    out = np.zeros((len(mine), 3))
    seg = Q[1:] - Q[:-1]
    L2 = np.maximum((seg * seg).sum(1), 1e-18)
    # the frame along the edge: the body's normal a little up from the seam (a neck seam lies in the crease between
    # neck and shoulder: the nearest vertex's normal there flips between up and sideways from one sample to the
    # next, and a stand laid by it leaned in and out by 60 deg along the neck's side), smoothed along the edge
    btree = cKDTree(body.V)
    Ns = np.zeros_like(Cs)
    for i_ in range(len(Cs)):
        nb_ = btree.query_ball_point(Cs[i_] + 0.012 * up0, 0.02)
        Ns[i_] = vn[nb_].mean(0) if len(nb_) else vn[tree.query(Cs[i_])[1]]
    Ns /= np.maximum(np.linalg.norm(Ns, axis=1, keepdims=True), 1e-12)
    Ts = np.gradient(Cs, axis=0)
    Ts /= np.maximum(np.linalg.norm(Ts, axis=1, keepdims=True), 1e-12)
    for _ in range(3):
        Ns[1:-1] = 0.25 * Ns[:-2] + 0.5 * Ns[1:-1] + 0.25 * Ns[2:]
    Us = np.zeros_like(Cs)
    for i_ in range(len(Cs)):
        n3 = Ns[i_] - Ts[i_] * (Ns[i_] @ Ts[i_])
        n3 /= max(np.linalg.norm(n3), 1e-12)
        if w.get("dir", "up") == "normal":
            U3 = n3
        else:
            # up, along the body's surface and square to the edge (a stand against the neck; on a shoulder's top,
            # where up leaves the surface, toward the middle of the edge's curve: the neck)
            U3 = up0 - Ts[i_] * (up0 @ Ts[i_])
            U3 = U3 - n3 * (U3 @ n3)
            alt = np.cross(n3, Ts[i_])
            if alt @ (hub - Cs[i_]) < 0:
                alt = -alt
            wq = min(1.0, float(np.linalg.norm(U3)) / 0.5)
            U3 = wq * U3 / max(np.linalg.norm(U3), 1e-12) + (1 - wq) * alt
            U3 = U3 / max(np.linalg.norm(U3), 1e-12)
            U3 = math.cos(lean) * U3 + math.sin(lean) * n3
        Ns[i_], Us[i_] = n3, U3
    for _ in range(2):
        Us[1:-1] = 0.25 * Us[:-2] + 0.5 * Us[1:-1] + 0.25 * Us[2:]

    # the piece's side of its sewn edge: one handedness along the whole edge, read at its middle (per point, by the
    # piece's centroid, it flipped along a collar's slanting front part: the centroid lies on that part's own line)
    jm = min(max(mid, 0), len(seg) - 1)
    tm = seg[jm] / math.sqrt(L2[jm])
    # (by the piece's own cloth NEXT TO that middle: the whole piece's centroid lay on the other side when a notched
    # collar's ends run far down past its neck edge: a collar drafted round a shirt collar, its stand laid downward)
    qm_ = 0.5 * (Q[jm] + Q[jm + 1])
    dq_ = np.linalg.norm(uv[mine] - qm_, axis=1)
    loc_ = uv[mine][(dq_ < 0.06) & (dq_ > 0.003)]
    inside_m = loc_.mean(0) if len(loc_) >= 3 else inside
    nu_sign = 1.0 if np.array([-tm[1], tm[0]]) @ (inside_m - qm_) >= 0 else -1.0

    def frame(pnt):  # a pattern point laid unturned: where, along the edge / off it, and the frame there
        f = np.clip(((pnt - Q[:-1]) * seg).sum(1) / L2, 0.0, 1.0)
        near = Q[:-1] + seg * f[:, None]
        j = int(np.argmin(((near - pnt) ** 2).sum(1)))
        tau = seg[j] / math.sqrt(L2[j])
        nu = nu_sign * np.array([-tau[1], tau[0]])
        rel = pnt - near[j]
        al, t = float(rel @ tau), float(rel @ nu)
        c3 = Cs[j] + (Cs[j + 1] - Cs[j]) * f[j]
        T3 = Cs[j + 1] - Cs[j]
        T3 = T3 / max(np.linalg.norm(T3), 1e-12)
        U3 = Us[j] + (Us[j + 1] - Us[j]) * f[j]
        U3 = U3 - T3 * (U3 @ T3)
        U3 = U3 / max(np.linalg.norm(U3), 1e-12)
        n3 = Ns[j] + (Ns[j + 1] - Ns[j]) * f[j]
        n3 = n3 - T3 * (n3 @ T3) - U3 * (n3 @ U3)
        n3 = n3 / max(np.linalg.norm(n3), 1e-12)
        return c3, al, t, T3, U3, n3, tau, nu

    tr = w.get("turn")
    Lr = np.asarray(tr["line"], float) if tr and tr.get("line") is not None else None
    if Lr is not None:
        # "turn": {"line": [[x, y], ...] in the piece's pattern, "deg", "gap"}: the piece is turned over about that
        # LINE (a notched collar's roll line: it stands a stand's height at centre back and comes down to the neck
        # edge where the lapel's roll line crosses the neckline, then runs on as the lapel's roll line: past that
        # point the whole collar is on the turned side, lying where the turned lapel will, sewn to the gorge).
        # Each point beyond the line is laid as its foot on the line + its distance from it in the turned direction
        sr = Lr[1:] - Lr[:-1]
        lr2 = np.maximum((sr * sr).sum(1), 1e-18)
        km = len(sr) // 2
        mid_r = 0.5 * (Lr[km] + Lr[km + 1])
        side = 1.0
        rt_m = sr[km] / math.sqrt(lr2[km])
        if np.array([-rt_m[1], rt_m[0]]) @ (Q[np.argmin(((Q - mid_r) ** 2).sum(1))] - mid_r) > 0:
            side = -1.0  # (the sewn edge is on the unturned side at the line's middle)
        th = math.radians(float(tr.get("deg", 160.0)))
        lr_len = np.sqrt(lr2)
        lr_cum = np.r_[0, np.cumsum(lr_len)]
        if worn is not None and w.get("lay") == "notched" and len(Lr) >= 5:
            return _notched_lay(uv[mine], Q, Lr, side, (Cs, Us, Ns, nu_sign), worn_pt, hz, Bk, Bq, uv, pid, M, pcs, body, w, lay,
                                info=LAY_INFO.setdefault(nm, {}))

    for i, v in enumerate(mine):
        pnt = uv[v]
        c3, al, t, T3, U3, n3, tau, nu = frame(pnt)
        if Lr is not None:
            fr = np.clip(((pnt - Lr[:-1]) * sr).sum(1) / lr2, 0.0, 1.0)
            ft = Lr[:-1] + sr * fr[:, None]
            jr = int(np.argmin(((ft - pnt) ** 2).sum(1)))
            rt = sr[jr] / math.sqrt(lr2[jr])
            m2 = side * np.array([-rt[1], rt[0]])
            a_, d_ = float((pnt - ft[jr]) @ rt), float((pnt - ft[jr]) @ m2)
            if d_ <= 0:
                out[i] = c3 + al * T3 + t * U3 + float(w.get("out", 0.0)) * n3
                continue
            # the foot's own frame carries the line's direction and the turned side's (no differences between
            # neighbouring frames)
            c3, al, t, T3, U3, n3, tau, nu = frame(ft[jr])
            base = c3 + al * T3 + t * U3
            r3 = float(rt @ tau) * T3 + float(rt @ nu) * U3
            r3 /= max(np.linalg.norm(r3), 1e-12)
            p3 = float(m2 @ tau) * T3 + float(m2 @ nu) * U3
            p3 = p3 - r3 * (p3 @ r3)
            p3 /= max(np.linalg.norm(p3), 1e-12)
            nn = np.cross(r3, p3)
            if nn @ n3 < 0:
                nn = -nn
            D3 = math.cos(th) * p3 + math.sin(th) * nn
            off_ = float(w.get("out", 0.0)) + float(tr.get("gap", 0.004))
            P_ = base + a_ * r3 + d_ * D3 + off_ * nn
            # Where the line has run off the piece (a notched collar past the point its roll line meets the neck
            # edge: the line runs on as the LAPEL's roll line, in the front) the turned side lies on the cloth it is
            # sewn to there, turned with it: the point is reflected about the line in the pattern, carried into that
            # piece's own pattern by the seam (a rigid 2D fit of the sewn edge's two sides) and laid where that
            # piece lies worn. Reflected flat about the line in space, it ran into the shoulder: the chest curves.
            if worn is not None:
                # (blended in over the line's last 5 cm before it leaves the piece)
                right_ = jr >= len(sr) // 2
                if jr in (0, len(sr) - 1):
                    wv = 1.0
                else:
                    to_end = (lr_cum[len(sr) - 1] - lr_cum[jr] - fr[jr] * lr_len[jr]) if right_ else \
                        (lr_cum[jr] + fr[jr] * lr_len[jr] - lr_cum[1])
                    wv = float(np.clip(1.0 - to_end / 0.05, 0.0, 1.0))
                    wv = wv * wv * (3 - 2 * wv)
            if worn is not None and wv > 0:
                q2 = ft[jr] + a_ * rt - d_ * m2  # reflected about the line, in this piece's pattern
                # the seam's two sides between the line's end and the edge's end are both straight there: the end
                # pair and the pair at the line's end carry one pattern into the other (the pairs between them are
                # not exact: fold rows on either side shift them by a centimetre along the seam)
                je = len(Q) - 1 if (pnt - q_mid) @ ax_s > 0 else 0
                jx = int(np.argmin(((Q - Lr[-2 if jr >= len(sr) // 2 else 1]) ** 2).sum(1)))
                js = np.array([jx, je])
                if jx != je and Bk[jx] == Bk[je]:
                    ec, ef = Q[je] - Q[jx], Bq[je] - Bq[jx]
                    ec, ef = ec / max(np.linalg.norm(ec), 1e-12), ef / max(np.linalg.norm(ef), 1e-12)
                    nc, nf_ = np.array([-ec[1], ec[0]]), np.array([-ef[1], ef[0]])
                    sc = nu_sign * (1.0 if je > jx else -1.0)  # (the piece's own side, by the edge's handedness)
                    sf = 1.0 if nf_ @ (uv[pid == Bk[je]].mean(0) - Bq[jx]) >= 0 else -1.0
                    rel2 = q2 - Q[jx]
                    # (the piece lies across the seam from the cloth it is sewn to)
                    qf = Bq[jx] + float(rel2 @ ec) * ef - sc * sf * float(rel2 @ nc) * nf_
                    Pw = worn_pt(float(qf[0]), hz + float(qf[1]), pcs[M["names"][Bk[js[0]]]]["wrap"].get("side") == "back", Bk[js[0]])
                    Pw = Pw + vn[tree.query(Pw)[1]] * (off_ + 0.006)  # (over the front and its turned lapel)
                    P_ = (1 - wv) * P_ + wv * Pw
            # turned flat about the line, the far side runs into a body that curves away under it: it lies on the
            # body there, a layer off
            for _ in range(3):
                short_ = off_ + 0.003 - float(body.clearance(P_[None])[0])
                if short_ <= 1e-4:
                    break
                P_ = P_ + vn[tree.query(P_)[1]] * short_
            out[i] = P_
            continue
        if tr and t > float(tr["at"]):
            # "turn": {"at": m from the sewn edge, "deg", "gap"}: past that line the piece is turned over (a
            # collar's fall down outside its stand), `gap` further out; a fold line there marked "in_wrap" gives
            # the crease its rest angle
            th = math.radians(float(tr.get("deg", 160.0)))
            D3 = math.cos(th) * U3 + math.sin(th) * n3
            D3 = D3 / max(np.linalg.norm(D3), 1e-12)
            out[i] = (c3 + al * T3 + float(tr["at"]) * U3 + (t - float(tr["at"])) * D3
                      + (float(w.get("out", 0.0)) + float(tr.get("gap", 0.004))) * n3)
        else:
            out[i] = c3 + al * T3 + t * U3 + float(w.get("out", 0.0)) * n3
    return out


LAY_INFO: dict = {}  # what the last notched lay of each piece did (numbers for diagnosis)
NOTCH_STEP = 0.004  # m between the stations along a notched collar's roll line
NOTCH_BLEND = 0.04  # m of neck edge before the roll line meets it over which the end's plane is eased in
NOTCH_BRIDGE = 0.012  # m the turned side may stand over the body under it beyond its own clearance
NOTCH_OPEN_DEG = 40.0  # deg the fall stands open (from the stand) while the collar is sewn on
NOTCH_OPEN_FADE = 0.08  # m of roll line from each end over which the opening eases in
NOTCH_OPEN_STEPS = (1.0, 0.75, 0.5, 0.25)  # how open the fall is at the start and at each carried pose but the last
NOTCH_FALL = 0.0  # the fall lies this far over what the stand's own clearance leaves under it


def _notched_lay(P2: np.ndarray, Q: np.ndarray, Lr: np.ndarray, side: float, edge3, worn_pt, hz: float, Bk, Bq,
                 uv: np.ndarray, pid: np.ndarray, M: dict, pcs: dict, body: "Body", w: dict, lay: float,
                 info: dict | None = None) -> np.ndarray:
    """A notched (tailored) collar as a tailor makes it, laid as two parts that meet where the collar's roll line
    comes down to the neck edge and runs on as the lapel's roll line (wrap "seam" + "worn" + "lay": "notched";
    `Lr` = the roll line in the collar's pattern, its first and last segments the run-on into the fronts):
    (1) between those two points a BAND on the worn neckline: the stand follows the neck up from the seam, its own
    clearance off it, to the roll line; the fall is turned over about the roll line, station by station as far as
    clears what is under it (flat down over the stand and the back neck seam at centre back; open over the top of
    the shoulder at the neck's side, where a fall can't lie folded flat: the crease curves round the neck there);
    (2) past them the collar's END lies FLAT in the plane of the turned lapel, as the lapel's continuation across
    the gorge seam: its pattern carried into the front's by the seam's own pairs (a rigid 2D fit), turned about the
    lapel's roll line, on ONE plane fitted to the body where it lies worn (isometric: the end of a made collar is
    a flat board).
    The two share the roll line's stations (position, the pattern's tangent map there, the body's normal, the turn),
    smoothed along it, so the surface is one. Returns the piece's vertices' positions.
    The stand is the neck's shape, not the pattern's lengths: a collar cut with spring is longer at its roll line
    than a neck is 3 cm up (a tailor shrinks the crease in with the iron); a made piece rests as it is laid."""
    vn, tree = body.normals()
    btree = cKDTree(body.V)
    tr = w.get("turn") or {}
    th_max = math.radians(float(tr.get("deg", 172.0)))
    gap = float(tr.get("gap", 0.004))
    c_fall = lay + gap + NOTCH_FALL

    # the sewn edge as ONE smooth curve, in the pattern and worn (splines through the seam's samples): laid segment
    # by segment of the samples' polyline, the stand jumped 12-15 mm at every sample (the pattern's edge and the
    # worn one turn by different angles there, and a point 3 cm up the stand sees the difference)
    from scipy.interpolate import CubicSpline
    Cs_, Us_, Ns_, nu_sign = edge3
    sq = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    nf_ = max(8, int(round(sq[-1] / 0.003)))
    sf = np.linspace(0, sq[-1], nf_ + 1)
    Qf, Cf = CubicSpline(sq, Q)(sf), CubicSpline(sq, Cs_)(sf)
    Uf, Nf = CubicSpline(sq, Us_)(sf), CubicSpline(sq, Ns_)(sf)
    Tf = np.gradient(Cf, axis=0)
    Tf /= np.maximum(np.linalg.norm(Tf, axis=1, keepdims=True), 1e-12)
    tq = np.gradient(Qf, axis=0)
    tq /= np.maximum(np.linalg.norm(tq, axis=1, keepdims=True), 1e-12)
    segq = Qf[1:] - Qf[:-1]
    lq2 = np.maximum((segq * segq).sum(1), 1e-18)

    def frame(pnt):
        f = np.clip(((pnt - Qf[:-1]) * segq).sum(1) / lq2, 0.0, 1.0)
        near = Qf[:-1] + segq * f[:, None]
        j = int(np.argmin(((near - pnt) ** 2).sum(1)))
        tau = tq[j] + (tq[j + 1] - tq[j]) * f[j]
        tau = tau / max(np.linalg.norm(tau), 1e-12)
        nu = nu_sign * np.array([-tau[1], tau[0]])
        rel = pnt - near[j]
        inner = 0 < j < len(segq) - 1 or 0.0 < f[j] < 1.0
        al, t = (0.0 if inner else float(rel @ tau)), (float(np.linalg.norm(rel)) * (1.0 if rel @ nu >= 0 else -1.0) if inner else float(rel @ nu))
        c3 = Cf[j] + (Cf[j + 1] - Cf[j]) * f[j]
        T3 = Tf[j] + (Tf[j + 1] - Tf[j]) * f[j]
        T3 = T3 / max(np.linalg.norm(T3), 1e-12)
        U3 = Uf[j] + (Uf[j + 1] - Uf[j]) * f[j]
        U3 = U3 - T3 * (U3 @ T3)
        U3 = U3 / max(np.linalg.norm(U3), 1e-12)
        n3 = Nf[j] + (Nf[j + 1] - Nf[j]) * f[j]
        n3 = n3 - T3 * (n3 @ T3) - U3 * (n3 @ U3)
        n3 = n3 / max(np.linalg.norm(n3), 1e-12)
        return c3, al, t, T3, U3, n3, tau, nu

    def bnormal(P):
        nb_ = btree.query_ball_point(P, 0.015)
        n = vn[nb_].mean(0) if len(nb_) else vn[tree.query(P)[1]]
        return n / max(np.linalg.norm(n), 1e-12)

    def hug(pnt):  # a point of the unturned side: up the body from the seam, the seam's own clearance off it
        c3, al, t, T3, U3, n3, tau, nu = frame(pnt)
        P = c3 + al * T3
        if t <= 1e-6:
            return P + t * U3, (c3, T3, U3, n3, tau, nu)
        ns = max(1, int(math.ceil(t / 0.006)))
        for _ in range(ns):
            nb = bnormal(P)
            u = U3 - nb * (U3 @ nb)
            u = u / np.linalg.norm(u) if np.linalg.norm(u) > 0.3 else U3
            P = P + u * (t / ns)
            P = P + bnormal(P) * (lay - float(body.clearance(P[None])[0]))
        return P, (c3, T3, U3, n3, tau, nu)

    # stations along the roll line (run-ons included)
    seg = np.linalg.norm(np.diff(Lr, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    ns_ = max(8, int(round(cum[-1] / NOTCH_STEP)))
    sd = np.unique(np.r_[np.linspace(0, cum[-1], ns_ + 1), cum[1], cum[-2]])
    Ld = np.stack([np.interp(sd, cum, Lr[:, c]) for c in range(2)], 1)
    run = np.where(sd < cum[1] - 1e-9, -1, np.where(sd > cum[-2] + 1e-9, 1, 0))  # -1 / +1: the two run-ons
    dseg = Ld[1:] - Ld[:-1]
    dlen = np.maximum(np.linalg.norm(dseg, axis=1), 1e-12)
    rts = dseg / dlen[:, None]
    rtv = np.gradient(Ld, axis=0)
    rtv /= np.maximum(np.linalg.norm(rtv, axis=1, keepdims=True), 1e-12)
    perp = lambda a: np.stack([-a[..., 1], a[..., 0]], -1)
    n_st = len(Ld)
    S, Bm, Nn = np.zeros((n_st, 3)), np.zeros((n_st, 3, 2)), np.zeros((n_st, 3))
    for k in np.where(run == 0)[0]:
        S[k], (c3, T3, U3, n3, tau, nu) = hug(Ld[k])
        nb = bnormal(S[k])
        Tt = T3 - nb * (T3 @ nb)
        Tt /= max(np.linalg.norm(Tt), 1e-12)
        Ut = np.cross(nb, Tt)
        if Ut @ U3 < 0:
            Ut = -Ut
        Bm[k] = np.outer(Tt, tau) + np.outer(Ut, nu)
        Nn[k] = nb
    ends = {}
    for sgn, kx in ((-1, int(np.where(run == 0)[0][0])), (1, int(np.where(run == 0)[0][-1]))):
        X2 = Ld[kx]  # where the roll line meets the neck edge
        jx = int(np.argmin(((Q - X2) ** 2).sum(1)))
        dir_ = Ld[kx] - Ld[kx - sgn]
        je = 0 if (Q[0] - X2) @ dir_ > (Q[-1] - X2) @ dir_ else len(Q) - 1
        J = np.arange(min(jx, je), max(jx, je) + 1)
        J = J[Bk[J] == Bk[je]]
        if len(J) < 2:
            raise ClothError("notched collar: its end is sewn to the front by fewer than two pairs past the point its "
                             "roll line meets the neck edge (no gorge to lie along)")
        A, Bf = Q[J], Bq[J]
        ca, cb_ = A.mean(0), Bf.mean(0)
        fk = uv[pid == Bk[je]]

        def fit2(reflect):
            A0 = (A - ca) * ([1.0, -1.0] if reflect else [1.0, 1.0])
            Hm = A0.T @ (Bf - cb_)
            Uu, _, Vt = np.linalg.svd(Hm)
            Rm = (Uu @ Vt).T
            if np.linalg.det(Rm) < 0:
                Rm = (Uu @ np.diag([1.0, -1.0]) @ Vt).T
            G_ = Rm @ np.diag([1.0, -1.0] if reflect else [1.0, 1.0])
            return G_, cb_ - G_ @ ca
        G, g0 = fit2(False)
        ed = Bf[-1] - Bf[0]
        nf = perp(ed / max(np.linalg.norm(ed), 1e-12))
        inside = frame(0.5 * (A[0] + A[-1]))[7] * 0.02 + 0.5 * (A[0] + A[-1])  # a point of the collar beside the seam
        if ((G @ inside + g0 - cb_) @ nf) * ((fk.mean(0) - cb_) @ nf) > 0:  # (the collar lies ACROSS the seam from the front)
            G, g0 = fit2(True)
        # the turned lapel's plane where the collar's end will lie: the piece's points past the meeting point, turned
        # about the run-on (the lapel's roll line), in the front's pattern, worn
        r2 = rts[kx if sgn > 0 else kx - 1] * sgn  # (pointing along the run-on, away from the band)
        m2 = side * perp(rts[kx if sgn > 0 else kx - 1])
        rel = P2 - X2
        sel = (rel @ r2 > -0.01)
        pts = P2[sel] - 2 * np.outer((P2[sel] - X2) @ m2, m2)
        pts = np.r_[pts, X2 + np.outer(np.linspace(0, 0.12, 7), r2)]
        qf = pts @ G.T + g0
        back_ = pcs[M["names"][Bk[je]]]["wrap"].get("side") == "back"
        Wp = np.stack([worn_pt(float(q_[0]), hz + float(q_[1]), back_, Bk[je]) for q_ in qf])
        Wp = Wp + np.stack([bnormal(q_) for q_ in Wp]) * lay
        O = S[kx].copy()
        # the plane: through the lapel's roll line as it lies worn (from the meeting point toward the break), turned
        # about that line until the end rests on the body (a board on a chest: it bridges the hollows)
        n_run = len(pts) - 7
        r3 = (Wp[-1] - O) / np.linalg.norm(Wp[-1] - O) + (Wp[-3] - O) / np.linalg.norm(Wp[-3] - O)
        r3 /= np.linalg.norm(r3)
        n0 = np.mean([bnormal(q_) for q_ in Wp], axis=0)
        n0 = n0 - r3 * (n0 @ r3)
        n0 /= max(np.linalg.norm(n0), 1e-12)
        q0 = np.cross(n0, r3)
        if n_run and q0 @ (Wp[:n_run].mean(0) - O) < 0:
            q0 = -q0
        rel_p = P2[sel] - X2
        a_p, d_p = rel_p @ r2, np.abs(rel_p @ m2)
        best = None
        for ang in np.radians(np.arange(-40.0, 41.0, 2.0)):
            q3 = math.cos(ang) * q0 + math.sin(ang) * n0
            n3 = math.cos(ang) * n0 - math.sin(ang) * q0
            Pp = O + np.outer(a_p, r3) + np.outer(d_p, q3) + gap * n3
            cl = body.clearance(Pp) if len(Pp) else np.array([c_fall])
            score = (max(0.0, c_fall - 0.001 - float(cl.min())) * 50.0 + abs(float(np.percentile(cl, 20)) - c_fall))
            if best is None or score < best[0]:
                best = (score, q3, n3, float(cl.min()), float(np.median(cl)))
        _, q3, nrm, clmin, clmed = best
        Bf3 = np.outer(r3, r2) + np.outer(-q3, m2)  # the collar's pattern -> the plane, unturned (turned flat: -q3 -> q3)
        ends[sgn] = {"X2": X2, "kx": kx, "fit_mm": [round(clmin * 1000, 1), round(clmed * 1000, 1)], "O": O, "r2": r2, "m2": m2,
                     "r3": r3, "q3": q3, "n": nrm, "tx": frame(X2)[6] * (1.0 if frame(X2)[6] @ r2 > 0 else -1.0)}
        for k in np.where(run == sgn)[0]:
            S[k] = S[kx] + Bf3 @ (Ld[k] - X2)
            Bm[k], Nn[k] = Bf3, nrm
    for _ in range(4):  # one surface: the tangent maps and normals eased along the line (the run-ons stay planes)
        Bm[1:-1] = 0.25 * Bm[:-2] + 0.5 * Bm[1:-1] + 0.25 * Bm[2:]
        Nn[1:-1] = 0.25 * Nn[:-2] + 0.5 * Nn[1:-1] + 0.25 * Nn[2:]
    for k in range(n_st):
        Uu, _, Vt = np.linalg.svd(Bm[k], full_matrices=False)
        Bm[k] = Uu @ Vt
        nn = np.cross(Bm[k][:, 0], Bm[k][:, 1])
        Nn[k] = nn / max(np.linalg.norm(nn), 1e-12) * (1.0 if nn @ Nn[k] >= 0 else -1.0)

    # each point's foot on the line
    out = np.zeros((len(P2), 3))
    foot = np.zeros((len(P2), 4))  # station segment, fraction, along, across
    turned = np.zeros(len(P2), bool)
    for i, pnt in enumerate(P2):
        fr = np.clip(((pnt - Ld[:-1]) * dseg).sum(1) / dlen ** 2, 0.0, 1.0)
        ft = Ld[:-1] + dseg * fr[:, None]
        j = int(np.argmin(((ft - pnt) ** 2).sum(1)))
        a_, d_ = float((pnt - ft[j]) @ rts[j]), float((pnt - ft[j]) @ (side * perp(rts[j])))
        foot[i] = j, fr[j], a_, d_
        turned[i] = d_ > 0 or run[j] != 0 or run[j + 1] != 0
        if not turned[i]:
            out[i] = hug(pnt)[0]
    # how far the fall turns at each station: as far as asked, or as clears what is under it
    dmax = np.full(n_st, 0.0)
    for i in np.where(turned)[0]:
        j = int(foot[i, 0])
        dmax[j] = max(dmax[j], foot[i, 3])
        dmax[j + 1] = max(dmax[j + 1], foot[i, 3])
    for _ in range(3):
        dmax[1:-1] = np.maximum(dmax[1:-1], np.maximum(dmax[:-2], dmax[2:]))
    th = np.full(n_st, th_max)
    m2v = side * perp(rtv)
    for k in range(n_st):
        if dmax[k] <= 0.004:
            continue
        p3 = Bm[k] @ m2v[k]
        ds = np.linspace(0.008, dmax[k], max(2, int(dmax[k] / 0.01)))
        for t_ in np.arange(th_max if run[k] == 0 else math.pi, math.radians(40.0), -math.radians(4.0)):
            pts = S[k] + np.outer(ds, math.cos(t_) * p3 + math.sin(t_) * Nn[k]) + gap * Nn[k]
            th[k] = t_
            if float(body.clearance(pts).min()) >= c_fall - 0.0015:
                break
    thr = th.copy()
    for _ in range(2):
        th[1:-1] = np.minimum(th[1:-1], np.minimum(th[:-2], th[2:]))
    for _ in range(4):
        th[1:-1] = 0.25 * th[:-2] + 0.5 * th[1:-1] + 0.25 * th[2:]
    th = np.minimum(th, thr)
    out0, turned0 = out.copy(), turned.copy()

    def lay_turned(th, open_=0.0):
        out, turned = out0.copy(), turned0.copy()
        for i in np.where(turned)[0]:
            j, f, a_, d_ = int(foot[i, 0]), foot[i, 1], foot[i, 2], foot[i, 3]
            S_, B_ = S[j] + (S[j + 1] - S[j]) * f, Bm[j] + (Bm[j + 1] - Bm[j]) * f
            n_ = Nn[j] + (Nn[j + 1] - Nn[j]) * f
            t_ = th[j] + (th[j + 1] - th[j]) * f
            r3 = B_ @ rts[j]
            r3 /= max(np.linalg.norm(r3), 1e-12)
            p3 = B_ @ (side * perp(rts[j]))
            p3 = p3 - r3 * (p3 @ r3)
            p3 /= max(np.linalg.norm(p3), 1e-12)
            n_ = n_ - r3 * (n_ @ r3) - p3 * (n_ @ p3)
            n_ /= max(np.linalg.norm(n_), 1e-12)
            if d_ <= 0:
                out[i] = S_ + a_ * r3 + d_ * p3
                continue
            out[i] = S_ + a_ * r3 + d_ * (math.cos(t_) * p3 + math.sin(t_) * n_) + gap * min(1.0, d_ / 0.008) * n_
        # the end: every point past the meeting point ALONG THE NECK EDGE lies in the plane (its foot on the roll line is
        # back on the band's curved part for the outer half of the end: laid from there it fanned, 2-3x), eased in over
        # NOTCH_BLEND of neck edge before it
        flat_ = np.zeros(len(P2), bool)
        for sgn, e_ in ends.items():
            tx = e_["tx"] / np.linalg.norm(e_["tx"])
            for i, pnt in enumerate(P2):
                u_ = float((pnt - e_["X2"]) @ tx)
                wv = float(np.clip(1.0 + u_ / NOTCH_BLEND, 0.0, 1.0))
                if wv <= 0 or (pnt - Q.mean(0)) @ tx < 0:
                    continue
                wv = wv * wv * (3 - 2 * wv)
                rel = pnt - e_["X2"]
                a_, d_ = float(rel @ e_["r2"]), float(rel @ e_["m2"])
                Pl = e_["O"] + a_ * e_["r3"] + d_ * e_["q3"] + gap * min(1.0, max(d_, 0.0) / 0.008) * e_["n"]
                out[i] = (1 - wv) * out[i] + wv * Pl
                turned[i] = True
                flat_[i] = wv >= 1.0
        # the turned side goes over the ridge of the shoulder between the band and the end: the end's plane run on past
        # the ridge stands up behind it as a wing, and a fall turned only as far as clears the shoulder's top stands off
        # the back beyond it. A collar is pressed to lie: nothing of the turned side stays further than NOTCH_BRIDGE over
        # what is under it (it bridges the hollows of a chest, not the fall of a shoulder)
        for _ in range(3):
            for i in np.where(turned)[0]:
                far = float(body.clearance(out[i][None])[0]) - (c_fall + NOTCH_BRIDGE + open_ * 0.2)
                if far > 1e-4:
                    out[i] = out[i] - bnormal(out[i]) * far
                    flat_[i] = False
        tn = np.where(turned)[0]
        for _ in range(4):  # what still comes too near the body lies on it, a layer off
            short = c_fall - 0.0015 - body.clearance(out[tn])
            lo = short > 1e-4
            if not lo.any():
                break
            for i in tn[lo]:
                out[i] = out[i] + bnormal(out[i]) * (c_fall - 0.0015 - float(body.clearance(out[i][None])[0]))
        return out, flat_

    out, flat_ = lay_turned(th)
    # the fall OPEN (sewing order: the collar is sewn on with its fall standing up, then turned down over the seam):
    # in the sim the draped back and fronts sew onto the neck edge while the fall is up, and the carried poses turn it
    # down over them (laid down from the start it was a lid over the seam: the draped back came to rest ON the fall,
    # 14 mm off the neck, and the neck seam stayed open 9-18 mm at all 13 pairs, su_30). Opened along the band only,
    # easing back to the turned lapel's plane over NOTCH_OPEN_FADE of roll line from the points it meets the neck edge
    kb_ = np.where(run == 0)[0]
    to_end = np.minimum(sd - sd[kb_[0]], sd[kb_[-1]] - sd)
    w_open = np.where(run == 0, np.clip(to_end / NOTCH_OPEN_FADE, 0.0, 1.0), 0.0)
    w_open = w_open * w_open * (3 - 2 * w_open)
    th_open = math.radians(NOTCH_OPEN_DEG)
    opens = {}
    for fr_ in NOTCH_OPEN_STEPS:
        th_f = th - fr_ * w_open * np.maximum(th - th_open, 0.0)
        opens[fr_] = lay_turned(th_f, fr_)[0]
    if info is not None:
        info["flat"] = flat_
        info["open"] = opens
        info["closed"] = out.copy()
        kb = np.where(run == 0)[0]
        info["dbg"] = {"P2": P2, "foot": foot, "turned": turned, "run": run, "th": th, "sd": sd, "S": S, "out": out.copy()}
        info.update({"turn_deg": [round(math.degrees(float(th[kb].min())), 0), round(math.degrees(float(th[kb[len(kb) // 2]])), 0)],
                     "plane_fit_mm": [ends[-1]["fit_mm"], ends[1]["fit_mm"]], "stations": int(n_st)})
    return out


def _true_lengths(X: np.ndarray, M: dict, sel: np.ndarray, held: np.ndarray, body: "Body", clear: float,
                  iters: int = 400) -> np.ndarray:
    """X with the edges of the vertices `sel` at their pattern lengths (position based, both ways: long edges drawn
    in, short ones out; Jacobi), the vertices `held` nearly fixed and nothing under `clear` off the body. A start
    near the answer is assumed (it keeps the lay's folds: nothing here knows about bending)."""
    F, uv = M["F"], M["uv"]
    Fs = F[sel[F].all(1)]
    E = np.unique(np.sort(np.r_[Fs[:, [0, 1]], Fs[:, [1, 2]], Fs[:, [2, 0]]], 1), axis=0)
    if not len(E):
        return X
    L0 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    V = X.copy()
    w = np.where(held, 0.05, 1.0)
    wa, wb = w[E[:, 0]], w[E[:, 1]]
    ws = wa + wb
    vn, tree = body.normals()
    idx = np.where(sel)[0]
    for it in range(iters):
        d = V[E[:, 1]] - V[E[:, 0]]
        L = np.maximum(np.linalg.norm(d, axis=1), 1e-12)
        if np.abs(L / L0 - 1).max() < 0.01:
            break
        c = ((L - L0) / L)[:, None] * d
        acc, cnt = np.zeros_like(V), np.zeros(len(V))
        np.add.at(acc, E[:, 0], c * (wa / ws)[:, None])
        np.add.at(acc, E[:, 1], -c * (wb / ws)[:, None])
        np.add.at(cnt, E[:, 0], 1.0)
        np.add.at(cnt, E[:, 1], 1.0)
        V[idx] += 1.4 * (acc / np.maximum(cnt, 1.0)[:, None])[idx]
        if it % 10 == 9:
            short = clear - body.clearance(V[idx])
            lo = short > 0
            if lo.any():
                V[idx[lo]] += vn[tree.query(V[idx[lo]])[1]] * short[lo, None]
    return V


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


NECK_OPEN = 0.035  # m an UNBUTTONED stand's two ends start apart at the throat (a collar worn open)


def _open_closure(M: dict, nm: str) -> tuple[float, float, float]:
    """(girth it would close at, x of the fastening's point nearer the low x, how far its ends stand apart: the
    closure's `gap`, else NECK_OPEN) of a piece fastened to itself whose closure is worn OPEN (a shirt's stand
    without a tie: the button and buttonhole exist, nothing stitches them); (0, 0, 0) otherwise."""
    k = M["names"].index(nm)
    best, xlo, gap = 0.0, 0.0, 0.0
    for c in M.get("closures") or []:
        if c.get("over") != nm or c.get("under", nm) != nm or any(c.get("closed") or []):
            continue
        for a, b in np.asarray(c.get("v") or [], np.int64).reshape(-1, 2):
            if M["piece"][a] == k and M["piece"][b] == k:
                d = float(abs(M["uv"][a, 0] - M["uv"][b, 0]))
                if d > best:
                    best, xlo, gap = d, float(min(M["uv"][a, 0], M["uv"][b, 0])), float(c.get("gap", NECK_OPEN))
    return best, xlo, gap


def _cuff_spiral(body: "Body", t: np.ndarray, x: np.ndarray, closed: float, x_lo: float, lay: float, cx: float,
                 sgn: float, turn: float, frame_t, m_min: float | None = None, recentre: bool = False) -> tuple | None:
    """A piece closed on itself round an arm (a cuff) laid on a spiral that follows the arm's sections: the radial
    function of their convex hull (over the piece's length, in the cuff's frame) + m(phi), m growing by `lay` a turn,
    m's start solved so the stitched points (x_lo and x_lo + closed along the pattern) land exactly one turn apart, arc
    length along the spiral = pattern x (from the piece's middle cx, at angle `turn`). Returns (angle per vertex
    before sgn/turn, radius per vertex) for the placement's own angle convention, or None without sections."""
    pts, drift = [], []
    for ti in np.arange(float(t.min()), float(t.max()) + 1e-9, 0.005 if recentre else 0.01):
        c, up, fw, d = frame_t(ti)
        L = tailor.section(body.V, body.T, c, d, c)
        if L is None or not tailor._encloses(L, c, d):
            continue
        Q = L - c
        q2 = np.c_[Q @ up, Q @ fw]
        if recentre:
            # each section round its own centre (recentre: a neck leans, its sections' centres drift 8 mm over 3 cm:
            # the hull of them all in one frame was 2 cm of girth bigger than any of them). The caller shifts each
            # vertex by the drift at its height (fn.drift)
            h2 = q2[ConvexHull(q2).vertices]
            c2 = 0.5 * (h2.min(0) + h2.max(0))
            drift.append((float(ti), c2[0], c2[1]))
            q2 = q2 - c2
        pts.append(q2)
    if not pts:
        return None
    P = np.concatenate(pts)
    H = _densify(P[ConvexHull(P).vertices], 0.001)
    a = np.arctan2(H[:, 1], H[:, 0])
    o = np.argsort(a)
    a, rh = a[o], np.linalg.norm(H, axis=1)[o]

    def r_hull(psi):
        return np.interp(np.mod(psi + np.pi, 2 * np.pi) - np.pi, a, rh, period=2 * np.pi)
    phi = np.linspace(-3 * np.pi, 3 * np.pi, 6001)
    psi = sgn * phi + turn
    rH = r_hull(psi)

    def spiral(m0):
        r = rH + m0 + lay * phi / (2 * np.pi)
        xy = np.c_[r * np.cos(psi), r * np.sin(psi)]
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
        return s - np.interp(0.0, phi, s), r

    def turn_err(m0):
        s, _ = spiral(m0)
        return float(np.interp(x_lo + closed - cx, s, phi) - np.interp(x_lo - cx, s, phi)) - 2 * np.pi
    lo, hi = -0.5 * float(rH.min()), 0.2
    if turn_err(lo) < 0:  # the cuff can't close even right on the arm: as small as it goes, pushed out later
        hi = lo
    for _ in range(50 if closed else 0):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if turn_err(mid) > 0 else (lo, mid)
    m0 = 0.5 * (lo + hi) if closed else float(m_min or 0.0)
    if m_min is not None:  # never nearer the body than this (a band too short to close there stays open)
        m0 = max(m0, float(m_min))
    s, r = spiral(m0)
    if x is None:  # the spiral itself: arc position from cx -> (angle, radius)
        fn = lambda xs: (np.interp(xs, s, phi), np.interp(np.interp(xs, s, phi), phi, r))
        fn.drift = np.asarray(drift, float) if drift else None
        return fn
    th = np.interp(x - cx, s, phi)
    return th, np.interp(th, phi, r)


def place(B: dict, M: dict, body: Body, gap: float = 0.012, _blouse: dict | None = None, smooth: bool = False,
          _out: dict | None = None, _down: dict | None = None) -> np.ndarray:
    """Start positions: each piece wrapped round the body part its `wrap` names (torso front/back, arm.L/R, neck),
    lengths along the pattern kept along the wrap (the sim's rest shape is the flat pattern anyway).
    _blouse {piece: (t of its hem, excess)}: a sleeve whose cuff had to sit further up the arm than its hem is
    placed with the excess folded in under itself (a fold is isometric), so the hem meets the cuff; set by a first
    pass. (Left as a gap, sewing dragged the sleeve, and with it the shirt, 28 mm up the body.)
    smooth: for solvers whose rest shape is the flat pattern, not the placement (ZOZO): the body is expected to have
    straight arms (Body.straight_arms: the sim bends them back), so sleeves are plain tubes with no fin, and a blousing
    sleeve is compressed along the arm instead of turned under (a fold across a 4 cm triangle is a 2.6x stretch, and a
    strain-limited solver can't start past its limit; compression it can)."""
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
    dzs, dxs = {}, {}
    for nm in torso:
        w = pcs[nm]["wrap"]
        if "align" in w:  # [my point, other piece, its point]: hang this piece so the two are level (a coat's
            mine, other, op = w["align"]  # skirt from the bodice's waist)
            dzs[nm] = float(uv[M["points"][f"{other}:{op}"]][1] - uv[M["points"][f"{nm}:{mine}"]][1]) + dzs.get(other, 0.0)
        if "align_x" in w:  # the same round the body: my point at the other piece's point's place (a belt's end at the
            mine, other, op = w["align_x"]  # side seam, a tail's centre back line on the back's)
            dxs[nm] = float(uv[M["points"][f"{other}:{op}"]][0] - uv[M["points"][f"{nm}:{mine}"]][0]) + dxs.get(other, 0.0)
        if w.get("shift"):  # a panel cut from its neighbour starts a little off it (pattern_draft style_line)
            dxs[nm] = dxs.get(nm, 0.0) + float(w["shift"][0])
            dzs[nm] = dzs.get(nm, 0.0) + float(w["shift"][1])
        if w.get("level"):  # pattern y = 0 at the body's <level> line (a skirt or waistband hangs from the waist)
            dzs[nm] = dzs.get(nm, 0.0) + float(at[f"{w['level']}_z"]) - float(w.get("drop", 0.0)) - float(hps[2])
    if torso:
        ylo = min(pcs[nm]["P"][:, 1].min() + dzs.get(nm, 0) for nm in torso)
        ytop = max(pcs[nm]["P"][:, 1].max() + dzs.get(nm, 0) for nm in torso)
        # the hull from the hem up to the pieces' own top (a skirt's plan curve isn't the chest's)
        z_hi = min(hps[2] - 0.01, hps[2] + ytop + 0.02)  # (was max(ytop, -0.03): every hull ran up to the shoulders, and a
        # waistband alone started on a curve as wide as the chest, its back 16-25 cm from the trousers it is sewn to)
        zs = np.arange(max(hps[2] + ylo, 0.05), max(z_hi, max(hps[2] + ylo, 0.05) + 0.021), 0.02)
        pts = [h for z in zs if (h := body.hull(z)) is not None]
        Hu = np.concatenate(pts)
        Hu = Hu[ConvexHull(Hu).vertices]
        P0 = pattern.length(Hu, closed=True)
        # the girth where the pieces must meet round the chest (a coat's flared skirt would make it a tent)
        ys = np.arange(max(ylo, -0.45), -0.25, 0.01) if ytop > -0.1 else np.arange(max(ylo, ytop - 0.3), ytop - 0.04, 0.01)
        if not len(ys):  # only a band on the torso (a waistband over trouser legs)
            ys = np.array([0.5 * (ylo + ytop)])
        Wmax = max(sum(_piece_width_at(pcs[nm]["P"], y - dzs.get(nm, 0)) for nm in torso) for y in ys)
        if smooth:
            # the width the pieces take ROUND THE BODY at a level: pleats laid closed, a band at its closed girth,
            # nothing for a piece laid on another
            def _lw(nm, y):
                w_ = pcs[nm]["wrap"]
                if w_.get("lies_on"):
                    return 0.0
                P_ = pcs[nm]["P"]
                yy = y - dzs.get(nm, 0)
                if not (P_[:, 1].min() < yy < P_[:, 1].max()):
                    return 0.0
                cg = _closed_girth(M, nm)
                if cg:
                    return float(cg)
                wd = _piece_width_at(P_, yy)
                for pl in w_.get("pleats") or []:
                    if min(pl["a"][1], pl["b"][1]) <= yy <= max(pl["a"][1], pl["b"][1]):
                        wd -= 2 * float(pl["depth"])
                return max(wd, 0.0)
            Wmax = max(sum(_lw(nm, y) for nm in torso) for y in ys)
            def _lx(nm, y):
                """(lo, hi) of a piece round the body at a level, from its centre line (pleats laid closed)."""
                w_ = pcs[nm]["wrap"]
                yy = y - dzs.get(nm, 0)
                xs = _piece_xs_at(pcs[nm]["P"], yy)
                if len(xs) < 2:
                    return None
                lo, hi = min(xs), max(xs)
                for pl in w_.get("pleats") or []:
                    if min(pl["a"][1], pl["b"][1]) <= yy <= max(pl["a"][1], pl["b"][1]):
                        if float(pl["sign"]) > 0:
                            hi -= 2 * float(pl["depth"])
                        else:
                            lo += 2 * float(pl["depth"])
                return lo + dxs.get(nm, 0.0), hi + dxs.get(nm, 0.0)

            def _span(y):
                """What the pieces take round the body at a level. The pieces of a side lie side by side from its
                centre line (or over each other: lapped fronts, a yoke's curved seam): the SPAN of each side, not
                their sum (the sum read 1.15 m where yoke and skirt share levels: a 4 cm bulge in the start). nan
                where a side has no cloth."""
                sp = {}
                for nm in torso:
                    cg = _closed_girth(M, nm)
                    if cg or pcs[nm]["wrap"].get("lies_on"):
                        continue
                    iv = _lx(nm, y)
                    if iv:
                        sd = pcs[nm]["wrap"].get("side", "front")
                        sp[sd] = (min(iv[0], sp[sd][0]), max(iv[1], sp[sd][1])) if sd in sp else iv
                bnd = max([_lw(nm, y) for nm in torso if _closed_girth(M, nm)], default=0.0)
                if len(sp) == 2:
                    return max(sum(hi - lo for lo, hi in sp.values()), bnd)
                return bnd if bnd else np.nan
        # the fronts overlap at the closure: the girth is the total width less the overlap past centre front
        over = sum(min(abs(pcs[nm]["P"][:, 0].min()), abs(pcs[nm]["P"][:, 0].max())) for nm in torso
                   if pcs[nm]["wrap"].get("side", "front") == "front"
                   and abs(pcs[nm]["P"][:, 0].min() + pcs[nm]["P"][:, 0].max()) > 0.05)  # one-sided pieces
        if smooth:
            Wsp = np.array([_span(y) for y in ys])
            if np.isfinite(Wsp).any():
                Wmax = float(np.nanmax(Wsp))
                over = 0.0  # (lapped fronts are one span)
        m = float(np.clip((Wmax - over - P0) / (2 * np.pi), gap, 0.15))
        band_closed = [_closed_girth(M, nm) for nm in torso]
        if all(band_closed):
            # only bands buttoned to themselves on the torso (a waistband over trouser legs): the curve's girth is
            # the band's CLOSED girth, as near the body as a band may start. A waistband grips: laid a start gap
            # off the waist it was 8 cm too short to close, and the sewing left it gathered and low on the hips
            m = float(np.clip((max(band_closed) - P0) / (2 * np.pi), SMOOTH_CLEAR, 0.15))
        # densified: each piece starts at the hull's point nearest its centre line, and a convex hull's front is
        # one long edge between the pecs (its nearest vertex was 69 mm off centre: the bodice started turned round
        # the body and sewing dragged it back ~10 cm, lifting the armholes and the sleeves with them)
        C = _densify(_offset_hull(Hu, m), 0.002)
    placed = {}
    neck_base = None  # height up the neck axis where the neck pieces' sewn edges start (shared: a collar on a stand)
    neck_tilt = None  # the neck pieces' axis (shared; wrap "tilt")
    neck_R, neck_lay, neck_sp = None, 0.0, None  # a buttoned stand's radius, its spiral's growth a turn, the spiral
    neck_R0 = None  # the first neck piece's radius
    neck_hug, neck_drift = False, None  # a buttoned stand held closed inside the contact standoff; its sections' drift
    arm_ang = {}  # vertex -> its angle round its arm (pieces placed so far)
    leg_curve = {}  # "leg.L" -> (its plan curve, the flat's x, the waist's z)
    leg_levels = {}  # the leg tubes' sections by (leg, cm)
    leg_t = {}  # piece index -> each vertex's share on its leg's tube
    head_curve = None  # the plan curve round the head (hoods)
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
            cg_b = _closed_girth(M, nm)
            if cg_b and smooth:
                # a band closed on itself among other torso pieces (a skirt's waistband on its yokes): on its OWN
                # curve, the body's hull at its own level out to its closed girth. On the garment's one cylinder
                # (hip girth) it stood open by 30 cm at the back, and it is a made piece, carried as placed: it could
                # never close, and the yokes stitched to its ends were held apart in a V ("the skirt is unzipped")
                # (the narrowest of the band's own levels; a band shorter than that + the solver's clearance can't
                # start closed: B["band_short"], a stage 4 failure)
                z0b, z1b = hps[2] + U[:, 1].min() + dzs.get(nm, 0.0), hps[2] + U[:, 1].max() + dzs.get(nm, 0.0)
                hb_ = [h for zz in np.arange(z0b, z1b + 0.005, 0.01) if 0.05 < zz < hps[2] - 0.01 and (h := body.hull(zz)) is not None]
                if hb_:
                    Hb = min((h[ConvexHull(h).vertices] for h in hb_), key=lambda h: pattern.length(h, closed=True))
                    m_b = float(np.clip((cg_b - pattern.length(Hb, closed=True)) / (2 * np.pi), BAND_CLEAR, 0.15))
                    short_b = pattern.length(Hb, closed=True) + 2 * np.pi * BAND_CLEAR - cg_b
                    B["band_clear"] = BAND_CLEAR
                    B.setdefault("torso_bands", []).append(nm)
                    if short_b > 0.003:  # stage 4 says it: the band is smaller than the body where it sits
                        B.setdefault("band_short", {})[nm] = round(float(short_b) * 1000, 1)
                    Cw = _densify(_offset_hull(Hb, m_b), 0.002)  # (no wrap "out" on top: 4 mm out is 25 mm of girth, and the band stood that far open)
                    cy = 0.5 * (Cw[:, 1].max() + Cw[:, 1].min())
                    start = Cw[np.argmin(np.abs(Cw[:, 0]) + 10 * np.maximum((Cw[:, 1] - cy) * (1 if w.get("side", "front") == "front" else -1), 0))]
            xs_, ys_, lay_ = U[:, 0].copy(), U[:, 1].copy(), np.zeros(len(U))
            # wrap "pleats" [{a, b, depth, sign}]: the cloth past the line a-b (on side `sign` of it) runs BACK a
            # depth over the cloth before it (mirrored in the line), then on again over that (moved back two depths):
            # a Z in plan, three layers a LAYER apart, the pattern's lengths kept (a pleat laid closed; turned as two
            # flaps, the whole side of the piece swung round twice and started 100% stretched)
            for pl in sorted(w.get("pleats") or [], key=lambda p_: abs(p_["a"][0])):
                a_, b_, d_ = np.asarray(pl["a"], float), np.asarray(pl["b"], float), float(pl["depth"])
                dl_ = (b_ - a_) / np.linalg.norm(b_ - a_)
                n_ = np.array([-dl_[1], dl_[0]])
                n_ = n_ if n_[0] * float(pl["sign"]) > 0 else -n_
                t_ = (xs_ - a_[0]) * n_[0] + (ys_ - a_[1]) * n_[1]
                back_ = np.where(t_ <= 0, 0.0, np.where(t_ <= d_, 2 * t_, 2 * d_))
                xs_, ys_ = xs_ - back_ * n_[0], ys_ - back_ * n_[1]
                # (each layer leaves the one under it as a wedge over 2 cm (4 mm over 6 was a 20% stretch), and the top one eases back down over 8 cm)
                lay_ = np.maximum(lay_, np.clip(t_ / min(0.02, 0.7 * d_), 0, 1) + np.clip((t_ - d_) / min(0.02, 0.7 * d_), 0, 1)
                                  - 2.0 * np.clip((t_ - 2 * d_) / 0.08, 0, 1))
            q = _arc_point(Cw, start, xs_ + dxs.get(nm, 0.0), float(w.get("dir", 1.0)))  # wrap "dir" -1: pattern +x runs round toward -x from the start (a band whose chain starts on the left front, laid from the back)
            if w.get("out") and w.get("out_reach") and Cw is not C:
                # wrap "out_reach" [full, none] m from the centre line: a lap's layer out only where it laps; past it
                # the piece lies where the pieces it is sewn to lie (the whole left front a layer out started its
                # side seam and armhole 4 mm off the back's and the sleeve's: tr_12's underarm crossed and its
                # seams stayed open on the left only)
                r0, r1 = (float(v_) for v_ in w["out_reach"])
                st0 = C[np.argmin(np.linalg.norm(C - start, axis=1))]
                q0 = _arc_point(C, st0, xs_ + dxs.get(nm, 0.0), float(w.get("dir", 1.0)))
                wo = np.clip((r1 - np.abs(xs_)) / max(r1 - r0, 1e-6), 0.0, 1.0)[:, None]
                q = wo * q + (1 - wo) * q0
            if lay_.any():
                # out along the curve's own normal (out from its middle sheared the layers 11% on the flat front)
                tg_ = _arc_point(Cw, start, xs_ + dxs.get(nm, 0.0) + 0.003, float(w.get("dir", 1.0))) - _arc_point(Cw, start, xs_ + dxs.get(nm, 0.0) - 0.003, float(w.get("dir", 1.0)))
                nr_ = np.c_[tg_[:, 1], -tg_[:, 0]]
                nr_ /= np.maximum(np.linalg.norm(nr_, axis=1, keepdims=True), 1e-9)
                nr_ *= np.sign(np.sum(nr_ * (q - Cw.mean(0)), 1))[:, None]
                q = q + nr_ * (LAYER * lay_)[:, None]
            cg_ = _closed_girth(M, nm)
            if cg_:  # a band closed on itself: its overlapping end a layer outside the end under it
                lap_ = max(float(np.ptp(U[:, 0])) - cg_, 1e-6)
                ramp_ = np.clip((U[:, 0] - (U[:, 0].max() - 2.0 * lap_)) / lap_, 0, 1)
                if w.get("over") == "low":  # the low-x end laps over (a trouser band opening at the front, left over right)
                    ramp_ = np.clip(((U[:, 0].min() + 2.0 * lap_) - U[:, 0]) / lap_, 0, 1)
                rd_ = q - Cw.mean(0)
                q = q + rd_ / np.maximum(np.linalg.norm(rd_, axis=1, keepdims=True), 1e-9) * (LAYER * ramp_)[:, None]
            X[sel] = np.c_[q, hps[2] + ys_ + dzs.get(nm, 0.0)]
            if B.get("worn_top") and not cg_ and not lay_.any() and "armpit_z" in at \
                    and float(U[:, 1].max()) + dzs.get(nm, 0.0) > -0.03:
                # a jacket's / coat's forepart and back are built on the form: their tops start where they are worn
                # (shoulders, chest, shoulder blades), so collar, lapel and shoulder seams start together
                y0_ = float(at["armpit_z"]) - float(hps[2])
                wi_ = {}
                X[sel] = _worn_top(B.get("_worn_body") or body, Cw, start, float(w.get("dir", 1.0)), xs_ + dxs.get(nm, 0.0),
                                   ys_ + dzs.get(nm, 0.0), float(hps[2]), y0_, WORN_CLEAR + 0.25 * float(w.get("out", 0.0)), wi_,
                                   neck_x=abs(float(hps[0])), envelope=B.get("worn_envelope"))
                B.setdefault("worn_top_pieces", {})[nm] = wi_
                if wi_.get("ridge_columns"):
                    B.setdefault("_worn_slides", {})[nm] = wi_["slide_mean"]
            elif B.get("worn_top") and not cg_ and B.get("_worn_slides"):
                # a torso piece under the armhole (a side panel) rides with the worn pieces it is sewn between
                X[np.where(sel)[0], 2] += float(np.mean(list(B["_worn_slides"].values())))
        elif to.startswith("arm."):
            side = to[4:]
            sh, el, wr = (body.J[f"{j}.{side}"] for j in ("shoulder", "elbow", "wrist"))
            axis = [sh, el, wr]
            seg = [np.linalg.norm(el - sh), np.linalg.norm(wr - el)]
            out_dir = np.array([1.0 if side == "L" else -1.0, 0, 0])
            P = pcs[nm]["P"]
            if w.get("bend"):  # a sleeve cut bent at the elbow is laid as the straight sleeve it was bent from
                P, U = pattern.unbend(P, **w["bend"]), pattern.unbend(U, **w["bend"])
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
            if (_down or {}).get(nm):  # smooth: moved down the arm to start clear of the bodice (and its followers)
                t_of = lambda Q, f=t_of, dn=_down[nm]: f(Q) + dn
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
            R = max(girth / (2 * np.pi), 0.5 * body.m["mm"]["wrist"] / 1000 / np.pi + gap) + float(w.get("out", 0)) \
                + (_out or {}).get(nm, 0.0)
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
            if smooth:
                # one straight axis (the sections' centres fitted by a line): the centres' wander bent the axis and a
                # tube round a bent axis is stretched on its outside (7% at the sleeve cap); the radius clears the
                # centres' distance from the line too
                fit_ = np.polyfit(ts, offs, 1)
                dev = np.linalg.norm(offs - (np.outer(ts, fit_[0]) + fit_[1]), axis=1)
                offs = np.outer(ts, fit_[0]) + fit_[1]
                rmax = rmax + dev
            Rp = max(R, float(rmax[on].max()) + gap if on.any() else R)
            cx = 0.5 * (P[:, 0].max() + P[:, 0].min())
            if "cx" in w:  # the pattern x that lies along the top of the arm (a kimono sleeve's overarm seam: its
                cx = float(w["cx"])  # front and back halves each start there)
            # a piece buttoned to itself (a cuff) starts closed: round its closed girth (the stitched marks' distance
            # along it) on a slight spiral, the overlap one layer outside, arc length kept along it. (Laid open round
            # the hand, 108 mm apart, the stitch snapped a stiff cuff shut and crumpled it.)
            closed = _closed_girth(M, nm)
            if closed:
                # r grows by LAYER over the closed girth (dr/dx = kk) and the stitched points, `closed` apart along
                # the piece, land one turn apart: ln(r_hi / r_lo) / kk = 2 pi
                # smooth: the overlap a layer apart at the triangles' scale (4 mm under 2 cm triangles: the chords of
                # the two layers cut through each other, which a contact solver refuses to start from)
                lay = max(LAYER, 0.3 * float(np.median(np.linalg.norm(uv[M["F"][:, 0]] - uv[M["F"][:, 1]], axis=1)))) \
                    if smooth else LAYER
                kk = lay / closed
                x_lo = _closure(M, nm)[1]
                r_lo = lay / math.expm1(2 * np.pi * kk)
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
            taper = smooth and not closed and SLEEVE_TAPER and bool(B.get("worn_top"))  # (jackets, coats: shirts unchanged)
            if taper:
                # smooth: a cone, not one cylinder: each row on the radius its own girth needs (this piece's width
                # there / its share of the sleeve's widest girth) or what clears the arm there, whichever is more,
                # smoothed along the arm. On the deltoid's cylinder a jacket sleeve's hem (298 mm round) started on
                # a 610 mm circle, its two seams 150 mm open at the wrist, and the under sleeve sometimes rode up
                # and left the hindarm seam 40-66 mm open (ga_suit su_54, su_61)
                share = widest(P) / max(girth, 1e-9)
                yfit = np.polyfit(t, U[:, 1], 1)
                tg = np.arange(t.min() - 0.01, t.max() + 0.011, 0.005)
                wg = np.array([_piece_width_at(P, float(np.polyval(yfit, tt))) for tt in tg])
                cg = np.interp(tg, ts, rmax) + gap + float(w.get("out", 0)) + (_out or {}).get(nm, 0.0)
                Rg = np.maximum(wg / max(share, 1e-6) / (2 * np.pi), cg)
                Rg = np.minimum(Rg, Rp)
                ker = np.exp(-0.5 * (np.arange(-8, 9) * 0.005 / 0.015) ** 2)
                Rg = np.convolve(np.pad(Rg, 8, mode="edge"), ker / ker.sum(), mode="valid")
                rad = np.interp(t, tg, Rg)
            if _blouse and nm in _blouse and smooth:  # the excess taken up along the arm over the sleeve's last part
                t_h, ex = _blouse[nm]
                z0 = t_h - max(3 * ex, 0.08)
                t = np.where(t > z0, z0 + (t - z0) * (1 - ex / (t_h - z0)), t)
            elif _blouse and nm in _blouse:  # the excess turned in under the sleeve round a U of radius LAYER / 2
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
            vi_ = np.where(sel)[0]
            turn_w = math.radians(float(w.get("turn", 0)))
            if closed and "turn" not in w:
                # a piece closed on itself is turned round the arm to where the edge it is sewn to lies (a cuff's
                # opening at the sleeve's placket slit, not always under the arm): the mean angle between its seam
                # vertices and their partners on the pieces already placed
                loc = {int(v): i for i, v in enumerate(vi_)}
                dif = []
                for a_, b_ in M["sew"]:
                    for me, ot in ((int(a_), int(b_)), (int(b_), int(a_))):
                        if me in loc and ot in arm_ang:
                            dif.append(arm_ang[ot] - float(w.get("front", 1)) * (U[loc[me], 0] - cx) / (closed / (2 * np.pi)))
                if dif:
                    turn_w = float(np.arctan2(np.mean(np.sin(dif)), np.mean(np.cos(dif))))

            def frame_t(ti):
                """The axis point at arc position t along the bent axis, the directions angle 0 and 90 deg point
                round it (up, forward) and the axis direction there."""
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
                return c, up, fw, d

            def at_t(ti, ang, r):
                """The point at arc position t along the bent axis, angle ang round it, radius r; and its radial."""
                c, up, fw, _ = frame_t(ti)
                u = np.cos(ang) * up + np.sin(ang) * fw
                return c + r * u, u
            if closed and smooth:
                # a cuff closes round a wrist that is an ellipse (wider across than front to back), not a circle: the
                # spiral follows the arm's own sections over the cuff (their hull) grown to the closed girth. On a
                # circle of that girth it was pushed 18-21 mm out across the wrist and rested (made piece: rest =
                # placed) as a cuff that much too big, which ruffled
                sp = _cuff_spiral(body, t, U[:, 0], closed, x_lo, lay, cx, float(w.get("front", 1)),
                                  turn_w, frame_t)
                if sp is not None:
                    th, rr = sp
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
                    ang = float(w.get("front", 1)) * th[i] + turn_w
                    out[i] = at_t(ti, ang, rr[i])[0]
                    continue
                ang = float(w.get("front", 1)) * (x - cx) / (rad[i] if taper else Rp) + turn_w
                arm_ang[vi_[i]] = ang
                p, u = at_t(ti, ang, rad[i])
                _, u1 = at_t(seg[0] - 1e-6, ang, rad[i])
                dl = rad[i] * max(0.0, float(u1 @ nin)) * tan_h
                mg = 0.6 * dl  # the fin's feet stand back from the mitre plane on each side (its legs never touch)
                if dl > 1e-4 and seg[0] - dl - mg < ti < seg[0] + dl + mg and not w.get("no_fin") and not smooth:
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
            # a band buttoned to itself (a stand: its button and buttonhole stitched) closes at that girth, its ends
            # overlapping a layer apart on a slight spiral; the pieces sewn onto it (a collar) share its radius and
            # spiral, so a fall turned down over a stand lies on it (each at its own length / 2 pi, a stand that only
            # met at its ends stood 4 mm outside its collar: the folded fall landed inside it)
            closed_n = _closed_girth(M, nm) if neck_R is None else 0.0
            # a stand whose button is UNDONE (worn without a tie): seated and laid like a buttoned one, round the
            # neck at its own girth, but its ends parted NECK_OPEN at the throat (by its pattern length round a hull
            # of its pattern heights it started as a ring 114 mm open, its collar 2.2x stretched)
            open_n, open_x, open_gap = _open_closure(M, nm) if (neck_R is None and not closed_n and smooth) else (0.0, 0.0, 0.0)
            first_neck = neck_R0 is None
            # (wrap "girth": the whole circle a piece is part of, when it is only part of a band: a cut-on collar's
            # half round the back of the neck)
            # (wrap "span": deg of the circle the band covers, instead of a girth: a tailored collar runs round the
            # back and sides of the neck and down onto the chest, never closing: with "tilt" the circle tips forward)
            if "span" in w and "girth" not in w:
                w = dict(w, girth=width * 360.0 / float(w["span"]))
            # (a band buttoned to itself is as big as its CLOSED girth, not its length with the button extensions:
            # by its length a stand was seated 3 cm of girth too low on the neck's flare and started 7 cm open)
            R = float(w.get("girth", closed_n or open_n or width)) / (2 * np.pi)
            d0_ = d.copy()
            flip = -1.0 if w.get("flip") else 1.0  # pattern +x toward the body's right (a piece whose outside is
            # its pattern face: the neck's own bands are laid face in at the back, like back pieces)
            # "apart": the two halves of a pair start this far from the centre line each (edge on edge they read as
            # through each other)
            xoff = flip * float(w.get("half", 0)) * float(w.get("apart", 0.0))
            if first_neck:
                hm_ = float(np.median(np.linalg.norm(uv[M["F"][:, 0]] - uv[M["F"][:, 1]], axis=1)))
                neck_lay = (0.0025 + hm_ ** 2 / (4 * R)) if smooth else LAYER
            above = float(w.get("above", 0.0))
            if neck_base is None:
                neck_base, nb = _neck_frame(body, nb, d, R,
                                            band=None if (w.get("circle") or not smooth)
                                            else abs(pattern.area(P)) / max(width, 1e-9))
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
                if rc is not None and neck_R is None:
                    R = max(R, rc + CLEAR / 2)
            if first_neck:
                neck_R0 = R
            else:  # a piece on a neck piece already placed (a collar on its stand) takes that piece's radius: its
                # fall turns down onto it (each cleared the neck over its own heights: the collar stood 5 mm inside)
                R = neck_R0
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
            if first_neck and w.get("pivot") == "back" and not np.allclose(d, d0_):
                # the tilt turns the circle about its back point (the nape), not about the neck's centre: the back
                # stays at its height and the front comes down onto the chest
                b0_ = np.array([0, 1.0, 0]) - d0_ * d0_[1]
                b0_ /= np.linalg.norm(b0_)
                hb_ = neck_base + above
                nb = nb + d0_ * hb_ + R * b0_ - d * hb_ - R * back
            # "fold": [rise, layer] a turned-down collar: up `rise` from its sewn edge, then folded down outside
            # itself `layer` further out (placed folded, so the rest shape holds the fold; arc length kept per row)
            fold = w.get("fold") if not any(fd["piece"] == nm for fd in M.get("folds") or []) else None
            # a curved band (a stand, a collar: its sewn edge an arc in the flat) lies isometrically on a cone, not a
            # cylinder: the sewn edge's circle (centre c, radius rho) rolls round the base at R, the band narrowing
            # toward the apex. On a cylinder its ends started high and sewing bent the band in its plane: ruffles.
            cone = None if w.get("straight") else _sewn_arc(B, M, nm, R)
            out = np.zeros((len(U), 3))
            if first_neck and smooth and not w.get("circle") and "girth" not in w:  # (Blender's start keeps the circle: its bands are
                # sewn shut by its springs from 8 mm off the neck, and on the hull they crumpled)
                # round the neck's own sections (their hull over the band's height) a clearance off the skin, not a
                # circle clear of its widest radius (a neck is deeper than wide: that circle was 20-30% longer than
                # the band, which stood open and far off the neck's sides). A band buttoned to itself (its stitched
                # points) closes exactly where it is long enough to; a shorter one stays open at the front
                hts = neck_base + above + (P[:, 1] - e[1])
                # (only over sections that are the neck: 8 mm above a 3 cm stand on a 4 cm neck the sections cut the
                # chin, 44-48 mm forward: the hull was 6 cm of girth too big and a buttoned stand started 7 cm open)
                top_n_ = max(r_["h"] for r_ in body.neck_rows() if r_["neck"])
                # a BUTTONED band is held closed in the sim (a made piece, carried): constructed closed at its
                # buttoned girth HUG_CLEAR off the skin at least, free of body contact (B["hug"]); what it has over
                # the neck's girth is collar ease
                # (and over the band's own HEIGHT from where it sits: a curved stand's ends lie 1-2 cm lower in the
                # pattern than its middle, and by its pattern heights the hull took in the trapezius under the neck)
                bh_ = abs(pattern.area(P)) / max(width, 1e-9)
                lo_n_ = min(max(neck_base + above, min(r_["h"] for r_ in body.neck_rows() if r_["neck"])), top_n_ - 0.01)
                # (only for a buttoned band: an open stand keeps the hull over its pattern heights, as it was tuned)
                rng_ = np.array([lo_n_, min(lo_n_ + bh_ + 0.008, top_n_)]) if (closed_n or open_n) else np.array([hts.min(), hts.max() + 0.008])
                if open_n:  # its fastening's points a turn less the gap apart: the gap at the front, no lap
                    neck_sp = _cuff_spiral(body, rng_, None, open_n + open_gap, open_x - e[0], 0.0, 0.0, 1.0, 0.0,
                                           lambda ti: (nb + d * ti, back, side, d),
                                           m_min=(SMOOTH_CLEAR if smooth else CLEAR) + 0.0005, recentre=True)
                    if neck_sp is not None:
                        neck_drift = neck_sp.drift
                else:
                    neck_sp = _cuff_spiral(body, rng_, None, closed_n,
                                           (_closure(M, nm)[1] - e[0]) if closed_n else 0.0, neck_lay, 0.0, 1.0, 0.0,
                                           lambda ti: (nb + d * ti, back, side, d),
                                           m_min=HUG_CLEAR if closed_n else (SMOOTH_CLEAR if smooth else CLEAR) + 0.0005,
                                           recentre=bool(closed_n))
                if neck_sp is not None and closed_n:
                    neck_hug = True
                    neck_drift = neck_sp.drift
                if neck_sp is not None:  # the spiral's mean radius stands for R in the cone's terms
                    a_, r_ = neck_sp(np.linspace(-0.15, 0.15, 61))
                    R = neck_R0 = float(np.mean(r_))
                    cone = None if w.get("straight") else _sewn_arc(B, M, nm, R)
            sp_ = None
            if neck_sp is not None:  # every vertex's angle and radius on the shared spiral, at its arc position
                pre = []
                for x, y in U:
                    if cone is not None:
                        c, rho = cone
                        up = 1.0 if c[1] > e[1] else -1.0
                        phi = math.atan2(x - c[0], up * (c[1] - y)) - math.atan2(e[0] - c[0], up * (c[1] - e[1]))
                        pre.append(flip * (phi * rho + xoff))
                    else:
                        pre.append(flip * (x - e[0] + xoff))
                sp_ = neck_sp(np.asarray(pre))
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
                    ang = flip * (phi * rho + xoff) / R
                else:
                    dy, rad, ang = y - e[1], R, flip * (x - e[0] + xoff) / R
                if sp_ is not None:
                    ang, rad = float(sp_[0][i]), float(sp_[1][i]) + (rad - R)
                r, hgt = rad + float(w.get("out", 0.0)), above + dy
                if fold and dy > fold[0]:  # the fall turned down outside the stand round a U one layer across
                    sf, rho_f = dy - fold[0], fold[1] / 2
                    if sf < np.pi * rho_f:
                        r = rad + rho_f * (1 - math.cos(sf / rho_f))
                        hgt = above + fold[0] + rho_f * math.sin(sf / rho_f)
                    else:
                        r, hgt = rad + fold[1], above + fold[0] - (sf - np.pi * rho_f)
                radial = np.cos(ang) * back + np.sin(ang) * side
                out[i] = nb + d * (neck_base + hgt) + r * radial
                if neck_drift is not None:
                    out[i] += back * np.interp(neck_base + hgt, neck_drift[:, 0], neck_drift[:, 1]) + \
                        side * np.interp(neck_base + hgt, neck_drift[:, 0], neck_drift[:, 2])
            X[sel] = out
            if neck_hug and nm not in B.setdefault("hug", []):
                B["hug"].append(nm)
            neck_base = (neck_base, nb)
            placed_neck.append(nm)
        elif to.startswith("leg."):
            # A trouser leg's pieces (pattern x = 0 on the centre front / back seam at the seat, the side seam at +x,
            # the fork at -x; y = 0 at the waist): on ONE vertical generalized cylinder per leg, the hull of that
            # half of the body from the waist to the hem, cut flat on a plane just off the body's middle. The part
            # of each piece outside the centre seam's line goes round the outside (front pieces from the front
            # corner, back pieces from the back one), the fork's extension lies on the flat between the legs; arc
            # length x height, so the placed piece keeps its pattern's lengths. The inseam and the side seam start
            # open and the sewing closes the tube onto the leg, as with a sleeve.
            sgn = 1.0 if to.endswith("L") else -1.0
            if to not in leg_curve:
                mine_ = [o for o in names if pcs[o]["wrap"].get("to") == to]
                z_w = float(at["waist_z"]) - float(w.get("drop", 0.0))  # (a dropped waist: pattern y = 0 under the waist line)
                ylo_ = min(pcs[o]["P"][:, 1].min() for o in mine_)
                yhi_ = max(pcs[o]["P"][:, 1].max() for o in mine_)
                x0 = float(w.get("mid", 0.004))  # the flat's distance from the body's middle plane
                pts_ = []
                # (the foot is left out: a hem cut for a shoe ends below the ankle, and with the foot's sections in
                # the hull the leg's cylinder was as long as the foot: front and back started 20 cm apart as slabs)
                z_foot = float(body.J["ankle.L"][2]) + 0.04 if "ankle.L" in body.J else 0.05
                if w.get("follow", True) and "crotch_z" in at:  # the legs below go on their own tubes (_leg_tube):
                    # the seat's cylinder only reaches down the hand-over
                    z_foot = max(z_foot, float(at["crotch_z"]) - LEG_TOP - LEG_BLEND - 0.04)
                for z in np.arange(max(z_w + ylo_, z_foot, 0.05), z_w + yhi_ + 0.02, 0.02):
                    # every loop that isn't a hand (Body.hull drops loops wider than the shoulders as arms: an
                    # A-pose's calves stand out past them and the leg pieces started inside the legs)
                    lim_ = abs(float(at["shoulder.L"][0])) + 0.09
                    lp_ = [L_[:, :2] for L_ in tailor.slice_loops(body.V, body.T, [0, 0, float(z)], [0, 0, 1.0])
                           if abs(float(L_[:, 0].mean())) < lim_ and len(L_) >= 3]
                    if not lp_:
                        continue
                    h = np.concatenate(lp_)
                    h = h[ConvexHull(h).vertices]
                    Hc_ = np.r_[h, h[:1]]
                    keep_ = [q for q in h if q[0] >= x0]
                    for a_, b_ in zip(Hc_[:-1], Hc_[1:]):  # where the section crosses the flat's plane
                        if (a_[0] - x0) * (b_[0] - x0) < 0:
                            keep_.append(a_ + (b_ - a_) * (x0 - a_[0]) / (b_[0] - a_[0]))
                    if len(keep_) >= 3:
                        pts_.append(np.asarray(keep_))
                Hl = np.concatenate(pts_)
                Hl = Hl[ConvexHull(Hl).vertices]
                # the outer arc must hold the pieces' widths outside the centre line, side by side
                W_out = 0.0
                for y in np.arange(yhi_ - 0.25, yhi_ - 0.01, 0.01):
                    tot = 0.0
                    for o in mine_:
                        xs_ = _piece_xs_at(pcs[o]["P"] * [sgn, 1.0], y)
                        tot += max(max(xs_), 0.0) - max(min(xs_), 0.0) if xs_ else 0.0
                    W_out = max(W_out, tot)

                def cut(m_):
                    Ho = _offset_hull(Hl, m_)
                    Ho = np.c_[np.maximum(Ho[:, 0], x0), Ho[:, 1]]
                    Ho = Ho[ConvexHull(Ho).vertices]
                    D_ = _densify(Ho, 0.002)
                    on_flat = D_[:, 0] < x0 + 1e-6
                    return D_, pattern.length(D_, closed=True) - (D_[on_flat, 1].max() - D_[on_flat, 1].min())

                m_ = gap
                for _ in range(6):
                    Dl, arc_ = cut(m_)
                    if arc_ >= W_out - 1e-4:
                        break
                    m_ = min(m_ + (W_out - arc_) / np.pi + 0.001, 0.15)
                leg_curve[to] = (Dl, x0, z_w)
            Dl, x0, z_w = leg_curve[to]
            Dw = Dl
            if w.get("out"):
                Dw = _offset_hull(Dl, float(w["out"]))
                Dw = np.c_[np.maximum(Dw[:, 0], x0), Dw[:, 1]]
            flat_ = Dw[Dw[:, 0] < x0 + 1e-6]
            front = w.get("side", "front") == "front"
            start = flat_[np.argmin(flat_[:, 1])] if front else flat_[np.argmax(flat_[:, 1])]
            q = _arc_point(Dw, start + [1e-4, 0.0], sgn * U[:, 0], 1.0)
            zz = z_w + U[:, 1]
            if "crotch_z" in at:
                # the hollow of the crotch curve lies past the centre line ABOVE the crotch line: on the flat that
                # is inside the pelvis. That cloth passes under the body: it starts squeezed down under the crotch
                # (the one part of the start that isn't isometric: a few cm of the fork)
                zc = float(at["crotch_z"]) - 0.012
                ramp = np.clip(-sgn * U[:, 0] / 0.02, 0.0, 1.0)
                zz = zz - np.maximum(zz - zc, 0.0) * ramp
            X[sel] = np.c_[sgn * q[:, 0], q[:, 1], zz]
            tube = _leg_tube(body, pcs, names, to, nm, U, z_w, gap, leg_levels) if w.get("follow", True) else None
            if tube is not None:
                Xt, tt = tube
                X[sel] = (1 - tt[:, None]) * X[sel] + tt[:, None] * Xt
                leg_t[k] = tt
        elif to == "head":
            # A hood's sides (pattern x = 0 at centre back, the face edge at +-x, y = 0 at the neck point's height):
            # on ONE vertical generalized cylinder round the head, the hull of the head's and neck's sections from
            # the neck point up, from the back of the head round each side toward the face; arc length x height.
            # The crown stands open above the head: the centre seam closes it over the top.
            if head_curve is None:
                ztop = float(body.V[:, 2].max())
                lp_ = []
                for z in np.arange(float(hps[2]) + 0.01, ztop, 0.015):
                    lp_ += [L_[:, :2] for L_ in tailor.slice_loops(body.V, body.T, [0, 0, float(z)], [0, 0, 1.0])
                            if L_[:, 0].min() < -0.02 and L_[:, 0].max() > 0.02]
                Hh = np.concatenate(lp_)
                Hh = Hh[ConvexHull(Hh).vertices]
                Wh = sum(float(np.ptp(pcs[o]["P"][:, 0])) for o in names if pcs[o]["wrap"].get("to") == "head")
                m_h = float(np.clip((Wh - pattern.length(Hh, closed=True)) / (2 * np.pi), gap, 0.10))
                head_curve = _densify(_offset_hull(Hh, m_h), 0.002)
            cy_h = 0.5 * (head_curve[:, 1].max() + head_curve[:, 1].min())
            start_h = head_curve[np.argmin(np.abs(head_curve[:, 0]) + 10 * np.maximum(cy_h - head_curve[:, 1], 0))]
            xo = float(w.get("half", 0)) * float(w.get("apart", 0.0015))
            q = _arc_point(head_curve, start_h, U[:, 0] + xo, 1.0)
            X[sel] = np.c_[q, hps[2] + U[:, 1] + float(w.get("lift", 0.0))]
        elif to == "seam":
            X[sel] = _on_seam(M, X, uv, pid, k, nm, w, body, pcs,
                              placed={names.index(o) for o in (B.get("worn_top_pieces") or {})}, chain_body=B.get("_worn_body"))
            if w.get("lay") == "notched" and "flat" in LAY_INFO.get(nm, {}):
                # between the band and the flat end the fall goes over the ridge of the shoulder: laid from two
                # sides it is a little long there (the outer edge fans); its long edges are drawn in, the sewn edge
                # and the flat end held, clear of the body
                hold_ = np.zeros(len(X), bool)
                hold_[np.r_[M["sew"][(pid[M["sew"][:, 0]] == k), 0], M["sew"][(pid[M["sew"][:, 1]] == k), 1]]] = True
                hold_[np.where(sel)[0][LAY_INFO[nm]["flat"]]] = True
                X[sel] = _relax_stretch(X, M, sel & ~hold_, float(w.get("lay_limit", 0.03)), iters=200)[sel]
                off_ = float(w.get("out", 0.0)) + 0.003
                for _ in range(3):
                    X[sel] = body.push_out(X[sel], off_)
                    X[sel] = _relax_stretch(X, M, sel & ~hold_, float(w.get("lay_limit", 0.03)), iters=60)[sel]
            if w.get("lay") == "notched" and "open" in LAY_INFO.get(nm, {}):
                # (build: the fall stands open at the sim's start and is turned down through the carried poses)
                B.setdefault("open_lay", {})[nm] = {"closed": LAY_INFO[nm]["closed"], "open": LAY_INFO[nm]["open"],
                                                    "laid": X[sel].copy()}
            if w.get("worn") and w.get("true", False):
                # a piece laid by frames along a curved edge, turned about a line and carried across a seam is the
                # right SHAPE but not the pattern's lengths (a notched collar's front ends: 36 triangles up to 3.6x
                # at 2 cm, spikes at the throat); a made piece rests as placed, so its lay is trued: every edge
                # drawn to its pattern length, the sewn edge held where it lies
                sewn_ = np.zeros(len(X), bool)
                sewn_[np.r_[M["sew"][(pid[M["sew"][:, 0]] == k), 0], M["sew"][(pid[M["sew"][:, 1]] == k), 1]]] = True
                X[sel] = _true_lengths(X, M, sel, sewn_ & sel, body, SMOOTH_CLEAR if smooth else CLEAR)[sel]
        elif to == "flat":  # laid flat at a height (a tablecloth, a blanket): pattern x, y -> world x, y
            o = np.asarray(w.get("at", [0, 0, 1.0]), float)
            X[sel] = np.c_[U[:, 0] + o[0], U[:, 1] + o[1], np.full(len(U), o[2])]
        else:
            raise ValueError(f"piece {nm}: unknown wrap {to!r} (torso, arm.L, arm.R, leg.L, leg.R, neck, head, seam, flat)")
    if smooth and torso and B.get("worn_top_pieces") and WORN_LEVELS and "armpit_z" in at:
        X = _worn_levels(X, B, M, body, torso, pcs, pid, dxs, hps, float(at["armpit_z"]), _lx)
    if B.get("worn_top_pieces"):
        X = _pin_seams(X, M, [names.index(nm) for nm in B["worn_top_pieces"]])
    gaps = np.full(len(X), gap)
    for k, nm in enumerate(names):
        wto = B["pieces"][nm]["wrap"].get("to", "")
        # (a piece laid from its seam too, a jacket's collar: pushed the draped cloth's 12 mm off the body, its neck
        # edge was held 8 mm outside the back neck it is sewn to and the seam stayed open all round, 11-14 mm)
        if (wto.startswith("arm.") and _closed_girth(M, nm)) or wto in ("neck", "seam"):  # bands hugging the body
            # outside the collision zone (cloth + body distance): inside it, Blender's impulses launched the torso
            # 15 cm up. ZOZO's zone is its contact offset + gap (3 mm): Blender's 8 mm (+ h/4) pushed a 183 mm cuff
            # 14 mm off a 149 mm wrist and a collar 8 mm off the neck, and these made pieces rest as placed: a cuff
            # too big that ruffled. Their faces are checked below instead (coarse triangles reach in between the
            # vertices)
            gaps[pid == k] = SMOOTH_CLEAR if smooth else CLEAR
        if nm in (B.get("hug") or []):
            gaps[pid == k] = HUG_CLEAR
        if nm in (B.get("torso_bands") or []):  # a waistband grips (BAND_CLEAR)
            gaps[pid == k] = BAND_CLEAR
        if wto.startswith("leg."):
            # the fork's extension lies on the plane between the legs, where the thighs are closer together than
            # two clearances: pushed a full gap off one thigh it lands in the other (37-52 mm of rest stretch)
            inner = (pid == k) & ((1.0 if wto.endswith("L") else -1.0) * uv[:, 0] < 0)
            gaps[inner] = 0.002
            if k in leg_t:  # on the leg's tube: as far off the leg as the tube was laid
                ix = np.where(pid == k)[0]
                g_ = gaps[ix]
                gaps[ix] = np.where(leg_t[k] > 0.5, np.minimum(g_, LEG_CLEAR), g_)
    if shifts and _blouse is None:
        return place(B, M, body, gap, _blouse=shifts, smooth=smooth, _out=_out, _down=_down)
    # the made pieces' (cuff, collar) shape before the push: their rest (the push only clears the start)
    faces_ = piece_faces(M, X, body, pcs) if any(pcs[nm]["wrap"].get("lies_on") for nm in names) else {}
    B["start_unpushed"] = _lay_on(B, M, _place_folds(B, M, body, X, smooth), faces_)
    for k, nm in enumerate(names):  # a piece with another laid inside it starts that layer further off the body
        if any(pcs[o]["wrap"].get("lies_on") == nm for o in names):
            gaps[pid == k] += LIES
    fl_ = np.zeros(len(X), bool)  # the folds' flaps: turned at the end, about rows already pushed clear
    for fd in M.get("folds") or []:
        from . import folds as foldmod
        if not fd.get("in_wrap"):
            fl_[foldmod._geom(M, fd)["rows"][0]["v"]] = True
    Xp = body.push_out(X, gaps)
    if smooth:  # every face of a band clear of the body (centres and edge midpoints): its vertices go further out
        F = M["F"]
        bands = np.unique(pid[gaps == SMOOTH_CLEAR])
        for _ in range(6):
            Pf = np.concatenate([Xp[F].mean(1), 0.5 * (Xp[F[:, 0]] + Xp[F[:, 1]]), 0.5 * (Xp[F[:, 1]] + Xp[F[:, 2]]),
                                 0.5 * (Xp[F[:, 2]] + Xp[F[:, 0]])])
            fk = np.tile(pid[F[:, 0]], 4)
            on = np.isin(fk, bands)
            cl = np.full(len(Pf), np.inf)
            cl[on] = body.clearance(Pf[on])
            short = SMOOTH_FACE_CLEAR - cl
            if short.max() <= 2e-4:
                break
            fi = np.tile(np.arange(len(F)), 4)
            need = np.zeros(len(Xp))
            for c in range(3):  # each vertex out by the largest shortfall of the faces round it
                np.maximum.at(need, F[fi, c], np.maximum(short, 0))
            gaps = gaps + need + 2e-4 * (need > 0)
            Xp = body.push_out(X, gaps)
    if smooth:  # a piece closed on itself: its outer layer moves out with the inner one under it (pushed alone, the
        # inner layer was squeezed onto the outer: 1.7 mm apart, which a contact solver refuses to start from)
        for k, nm in enumerate(names):
            closed_, _ = _closure(M, nm)
            if not closed_ or not pcs[nm]["wrap"].get("to", "").startswith("arm."):
                continue
            sel = np.where(pid == k)[0]
            U = uv[sel]
            D = Xp[sel] - X[sel]
            outer = np.where(U[:, 0] - closed_ >= U[:, 0].min() - 1e-9)[0]
            if len(outer):
                _, j = cKDTree(U).query(U[outer] - [closed_, 0.0])
                big = np.linalg.norm(D[j], axis=1) > np.linalg.norm(D[outer], axis=1)
                D[outer[big]] = D[j[big]]
                Xp[sel] = X[sel] + D
    if fl_.any():
        # fold lines: the flaps are turned about their rows after the rest of the piece is pushed clear of the body
        # (pushed after, a stand moved out through the fall lying on it)
        Xp = _place_folds(B, M, body, np.where(fl_[:, None], X, Xp), smooth)
    Xp = _lay_on(B, M, Xp, faces_)
    laid_ = np.isin(pid, [k for k, nm in enumerate(names) if pcs[nm]["wrap"].get("lies_on") in names])
    mv = np.where(fl_ | laid_, 0.0, np.linalg.norm(Xp - X, axis=1))
    # what pushing the start out of the body moved: it becomes stretch in the rest shape (rest = placed)
    B["push"] = {nm: round(float(mv[pid == k].max() * 1000), 1) for k, nm in enumerate(names) if mv[pid == k].max() > 0.002}
    if smooth and (_out or {}).get("_n", 0) < 3:
        # resting on the flat pattern, a vertex pushed out of the body is stretch the solver starts with (a sleeve cap
        # pushed 6 mm off the deltoid: 7.5%, past a 5% strain limit): a sleeve (not closed on itself) stands that much
        # further out as a whole instead, still a cylinder
        more = {nm: float(mv[pid == k].max()) + 0.001 for k, nm in enumerate(names)
                if pcs[nm]["wrap"].get("to", "").startswith("arm.") and not _closed_girth(M, nm)
                and mv[pid == k].max() > 0.0015}
        if more:  # (again until clear: a further-out cylinder can meet the hand further down)
            out_ = dict(_out or {})
            for nm, v in more.items():
                out_[nm] = out_.get(nm, 0.0) + v
            out_["_n"] = out_.get("_n", 0) + 1
            return place(B, M, body, gap, _blouse=_blouse, smooth=True, _out=out_, _down=_down)
    if smooth:
        # nothing may start through anything else (a solver that keeps its contacts can't undo it): a sleeve whose cap
        # starts through the bodice round the armhole goes 1 cm further down the arm at a time (the sewing pulls it up)
        _xp = sorted(_piece_crossings(Xp, M))
        B.setdefault("sleeve_hits", []).append([p_ for p_ in _xp if any(pcs[q_]["wrap"].get("to", "").startswith("arm.") for q_ in p_)])
        hit = {a for a, b in _xp for a in (a, b)
               if pcs[a]["wrap"].get("to", "").startswith("arm.") and "follow" not in pcs[a]["wrap"]}
        # a sleeve still pushed off the body where it stands out further already (a coat's under sleeve's corner at
        # the armpit: 12% stretch) goes down the arm too
        hit |= {nm for k, nm in enumerate(names) if pcs[nm]["wrap"].get("to", "").startswith("arm.")
                and not _closed_girth(M, nm) and "follow" not in pcs[nm]["wrap"] and "align" not in pcs[nm]["wrap"] and mv[pid == k].max() > 0.0015}
        # (not a piece aligned to another on its arm, a two-piece sleeve's under sleeve: moved down alone it started 11 cm
        # below its top sleeve, the seams 130 mm apart, and the hindarm seam stayed 40-66 mm open: su_54, su_61)
        down = dict(_down or {})
        # (the pieces sharing an arm go down together: the sleeve is one tube)
        hit |= {o for o in names for h in list(hit) if pcs[o]["wrap"].get("to") == pcs[h]["wrap"].get("to")
                and "follow" not in pcs[o]["wrap"]}
        if hit and max([down.get(nm, 0.0) for nm in hit]) < 0.10:
            for nm in hit:
                down[nm] = max(down.get(o, 0.0) for o in hit if pcs[o]["wrap"].get("to") == pcs[nm]["wrap"].get("to")) + 0.01
            return place(B, M, body, gap, _blouse=None, smooth=True, _out=_out, _down=down)
        # draped cloth pushed clear of the body starts stretched where the body stands proud of the piece's wrap (an
        # under sleeve at the armpit 37-125%, a back's neck over a shirt collar): a strain-limited solver can't start
        # there. Its long edges are drawn back and the clearance restored, a few rounds
        if len(body.V):
            made_v = np.isin(pid, [names.index(nm) for nm in made_pieces(M, interfacing(B, M))])
            for fd in M.get("folds") or []:  # (a fold's rows and flap are constructed: left as laid)
                from . import folds as foldmod
                if fd.get("in_wrap") and fd.get("kind", "press") == "press" and \
                        pcs.get(fd.get("piece"), {}).get("wrap", {}).get("to", "").startswith("leg."):
                    continue  # (a trouser crease lies flat in the wrap: fixed, it held a leaning column's shear)
                made_v[foldmod._geom(M, fd)["rows"][0]["v"]] = True
                if _pressed(B, M, fd):  # (a pressed flap's line relaxes with its base; the flap is pressed again)
                    continue
                for row in fd["rows"]:
                    made_v[row] = True
            worn_k = [names.index(nm) for nm in (B.get("worn_top_pieces") or {})]
            for _ in range(12 if worn_k else 6):
                _, hi_, _, _ = __import__("hifipushie.cloth_detail", fromlist=["x"]).strain_field(M, Xp)
                if hi_[~made_v[M["F"]].any(1)].max() <= 1.04:
                    break
                if worn_k:
                    # pieces laid where they are worn keep their pinned seams shut while they relax (relaxed
                    # alone, a jacket's shoulder seams opened again to 5-10 cm)
                    for _ in range(10):
                        Xp = _relax_stretch(Xp, M, ~made_v, 0.02, iters=4)
                        Xp = _relax_strain(Xp, M, ~made_v, 0.03, iters=30)
                        Xp = _pin_seams(Xp, M, worn_k, sigma=WORN_PIN / 4,
                                        fixed=[j for j in range(len(names)) if made_v[pid == j].all() and j not in worn_k], pull=WORN_PULL)
                        Xp = _repress(Xp, B, M, smooth)  # (pressed lapels follow their foreparts)
                else:
                    Xp = _relax_stretch(Xp, M, ~made_v, 0.02, iters=40)
                    Xp = _relax_strain(Xp, M, ~made_v, 0.03, iters=300)
                Xp = _clear_of_body(Xp, M["F"], ~made_v, body, float(gaps.min()) * 0.5, 0.0034)
                Xp = _clear_of_worn(Xp, ~made_v, body, WORN_CLEAR)
                if worn_k:  # (the base moved: its pressed flaps with it)
                    Xp = _repress(Xp, B, M, smooth)
            if worn_k:
                # a worn top lies ON the body: when the loop ends (or never runs: nothing stretched) its faces must
                # still be clear of it (a shirt's worn back started 1.5 mm off a shoulder blade inside ZOZO's 2 mm
                # offset: "contact starts overlapping" at frame 0)
                Xp = _clear_of_body(Xp, M["F"], ~made_v, body, float(gaps.min()) * 0.5, 0.0034)
                Xp, _n = _clear_exact(Xp, M["F"], ~made_v, body.V, body.T)
            Xp = _clear_of_worn(Xp, ~made_v, body, WORN_CLEAR)
            _, hi_, _, _ = __import__("hifipushie.cloth_detail", fromlist=["x"]).strain_field(M, Xp)
            B["start_stretch"] = round(float(hi_[~made_v[M["F"]].any(1)].max()) - 1, 3)
        B["start_crossings"] = sorted(_piece_crossings(Xp, M))
        B["sleeve_down"] = {k_: round(v_, 3) for k_, v_ in (_down or {}).items()}
    # every band fastened to itself (a cuff, a stand, a waistband) must START closed, whatever path placed it: a
    # made band is held as placed, so one that starts with its button far from its buttonhole never closes, and what
    # is sewn to its ends is held apart (the trousers' band ended 77 mm open: only the torso path said band_short)
    st_ = np.asarray(M["stitch"]).reshape(-1, 2)
    if len(st_) and smooth:  # (Blender sews a band shut with its springs from wherever it starts)
        own = M["piece"][st_[:, 0]] == M["piece"][st_[:, 1]]
        for a_, b_ in st_[own]:
            nm_ = M["names"][M["piece"][a_]]
            g_ = float(np.linalg.norm(Xp[a_] - Xp[b_]))
            if g_ > 3 * LAYER and nm_ not in (B.get("band_short") or {}):
                B.setdefault("band_short", {})[nm_] = round(g_ * 1000, 1)
    return Xp


LIES = 0.003  # a piece laid on another (a facing on its front): this far inside it


def _lay_on(B: dict, M: dict, X: np.ndarray, faces: dict) -> np.ndarray:
    """Pieces whose wrap says "lies_on": <piece> (a facing traced from its front: the same pattern coordinates) are
    placed as that piece's own placed surface, LIES off its inside face (the face toward the body where the piece
    lies on its wrap; on a flap turned back, a lapel, that is the side that shows). A facing wrapped and folded by
    itself can't follow its front round a roll line: it would have to pass through it."""
    pcs, names, pid, F, uv = B["pieces"], M["names"], M["piece"], M["F"], M["uv"]
    todo = [(k, nm, pcs[nm]["wrap"]["lies_on"]) for k, nm in enumerate(names)
            if pcs[nm]["wrap"].get("lies_on") in names]
    if not todo:
        return X
    X = X.copy()
    N = np.zeros_like(X)
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    for c in range(3):
        np.add.at(N, F[:, c], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    base, dirs, more = X.copy(), np.zeros_like(X), np.zeros(len(X))
    for k, nm, on in todo:
        j = names.index(on)
        Fo = F[pid[F[:, 0]] == j]
        A, Bv, C = uv[Fo[:, 0]], uv[Fo[:, 1]], uv[Fo[:, 2]]
        tree = cKDTree((A + Bv + C) / 3)
        sel = np.where(pid == k)[0]
        # the triangle of the piece under it that holds each point: EVERY triangle is tried (the k nearest centroids
        # missed the big triangle a point lay in whenever a roll's rows of small ones were nearer: a third of a
        # facing was snapped onto the wrong triangles and started 50-300% stretched)
        d0, d1 = Bv - A, C - A
        den = d0[:, 0] * d1[:, 1] - d0[:, 1] * d1[:, 0]
        den = np.where(np.abs(den) < 1e-14, np.nan, den)
        for i, v in enumerate(sel):
            q = uv[v]
            d2 = q - A
            b1 = (d2[:, 0] * d1[:, 1] - d2[:, 1] * d1[:, 0]) / den
            b2 = (d0[:, 0] * d2[:, 1] - d0[:, 1] * d2[:, 0]) / den
            worst = np.nan_to_num(np.minimum(np.minimum(1 - b1 - b2, b1), b2), nan=-np.inf)
            t = int(np.argmax(worst))
            wts = np.array([1 - b1[t] - b2[t], b1[t], b2[t]])
            wts = np.clip(wts, 0, None)  # (past the outline's chords: the nearest triangle's edge)
            wts /= wts.sum()
            p = wts @ X[Fo[t]]
            nn = wts @ N[Fo[t]]
            nn /= max(np.linalg.norm(nn), 1e-12)
            sg = -1.0 if pcs[nm]["wrap"].get("face") == "out" else 1.0  # (a pocket lies on the OUTSIDE)
            sg *= float(pcs[nm]["wrap"].get("lies_depth", 1))  # (the second bag of a pocket: two layers in)
            X[v] = p - sg * faces.get(on, 1.0) * LIES * nn
            base[v], dirs[v] = p, -np.sign(sg) * faces.get(on, 1.0) * nn
            more[v] = (abs(sg) - 1.0) * LIES
        # round a tight roll the laid piece's chords can still cut the piece under it (their triangles differ):
        # the vertices of what crosses stand a little further off, until nothing does
        for _ in range(10):
            bad = _pair_crossing_verts(X, F, pid, k, j)
            if not len(bad):
                break
            more[bad] += 0.0015
            X[bad] = base[bad] + dirs[bad] * (LIES + more[bad])[:, None]
    return X


def _pair_crossing_verts(X: np.ndarray, F: np.ndarray, pid: np.ndarray, ka: int, kb: int) -> np.ndarray:
    """The vertices of piece ka on an edge or triangle that crosses piece kb (edges of each against the other's
    triangles)."""
    out = set()
    Fa, Fb = F[pid[F[:, 0]] == ka], F[pid[F[:, 0]] == kb]
    for Fe, Ft, mine_is_edge in ((Fa, Fb, True), (Fb, Fa, False)):
        if not len(Fe) or not len(Ft):
            continue
        E = np.unique(np.sort(np.r_[Fe[:, [0, 1]], Fe[:, [1, 2]], Fe[:, [2, 0]]], 1), axis=0)
        cen = X[Ft].mean(1)
        rad = np.max(np.linalg.norm(X[Ft] - cen[:, None], axis=2), axis=1)
        mid = 0.5 * (X[E[:, 0]] + X[E[:, 1]])
        half = 0.5 * np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
        if not np.isfinite(X[Ft]).all() or not np.isfinite(X[Fe]).all() or float(rad.max()) > 8.0 * float(np.median(rad)) + 0.05:
            raise ClothError(f"the start is broken: pieces {ka} / {kb} have a triangle {float(np.nanmax(rad)) * 2:.2f} m "
                             "across or not finite (a placement that failed; searched as it is, every edge pairs with it)")
        cand = cKDTree(cen).query_ball_point(mid, r=half + float(rad.max()), return_sorted=False)
        ei = np.repeat(np.arange(len(E)), [len(c) for c in cand])
        ti = np.fromiter((t for c in cand for t in c), dtype=np.int64, count=len(ei))
        if not len(ei):
            continue
        T = Ft[ti]
        hit = _seg_tri(X[E[ei, 0]], X[E[ei, 1]], X[T[:, 0]], X[T[:, 1]], X[T[:, 2]])
        out |= set(E[ei[hit]].ravel().tolist()) if mine_is_edge else set(T[hit].ravel().tolist())
    return np.asarray(sorted(out), dtype=np.int64)


def piece_faces(M: dict, X: np.ndarray, body: "Body", pcs: dict) -> dict:
    """{piece: +1 | -1}: whether a piece's pattern face (its triangles' normals, counter-clockwise in the pattern) is
    placed away from the body (+1) or toward it. Pieces laid flat: +1."""
    out = {}
    F = M["F"]
    for k, nm in enumerate(M["names"]):
        if pcs[nm]["wrap"].get("to", "torso") == "flat" or not len(body.V):
            out[nm] = 1.0
            continue
        Fk = F[M["piece"][F[:, 0]] == k]
        n = np.cross(X[Fk[:, 1]] - X[Fk[:, 0]], X[Fk[:, 2]] - X[Fk[:, 0]])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        c = X[Fk].mean(1)
        out[nm] = 1.0 if float(np.mean(body.clearance(c + 0.004 * n) - body.clearance(c - 0.004 * n))) >= 0 else -1.0
    return out


FOLD_WIDTH_FITTED = 0.008  # a fold's U in a "fitted" placement (Blender: its cloth's collision distances apart)
FOLD_WIDTH_MADE = 0.0016  # a fold's U on a constructed (never simulated) mesh: two layers of cloth nearly touching
RELAY_OPEN = 40.0  # deg a made flap opens to clear the cloth under it; past that the cloth is tucked under (_tuck)
PRESS_LAY = 0.003  # how far a pressed lapel lies off its forepart (it bridges a curving chest with 2 cm triangles)
FOLD_LAY = 0.0015  # how far a placed flap starts off what it lies on (a contact solver's gap, with room for chords)


def _place_folds(B: dict, M: dict, body: "Body", X: np.ndarray, smooth: bool) -> np.ndarray:
    """The garment's fold lines made in the placement (folds.apply): each piece was laid on its wrap unfolded; its
    flaps are turned about their rows as far as the fold asks or as they clear what they lie on (the piece's own base
    side, the pieces placed before it on the same part of the body, the body)."""
    fds = M.get("folds") or []
    if not fds:
        return X
    from . import folds as foldmod
    pcs, names, pid, F = B["pieces"], M["names"], M["piece"], M["F"]
    faces = piece_faces(M, X, body, pcs)
    B["faces"] = faces
    lay = FOLD_LAY if smooth else LAYER
    clear = SMOOTH_CLEAR if smooth else CLEAR
    info = {}
    bn, _ = body.normals() if len(body.V) else (np.zeros((0, 3)), None)
    # the neck pieces' folds first (a collar's fall), then the body pieces' (a front rolled back under it)
    fds = sorted(fds, key=lambda f_: pcs[f_["piece"]]["wrap"].get("to", "torso") not in ("neck", "seam"))
    spread_done = False
    for fd in fds:
        if not spread_done and pcs[fd["piece"]]["wrap"].get("to", "torso") not in ("neck", "seam"):
            # the neck pieces' folds are made: an open collar spreads before the fronts roll back under it
            X = _spread_open_collar(B, M, body, X, smooth)
            spread_done = True
        if fd.get("in_wrap"):  # a pleat's folds are laid by the wrap itself (place: wrap "pleats")
            continue
        nm = fd["piece"]
        k = names.index(nm)
        to = pcs[nm]["wrap"].get("to", "torso")
        obs = []
        if len(body.V):
            # (a flap of a band that hugs the body, a buttoned collar's fall, may lie as near the skin as its band
            # + a layer: at the solver's 4 mm it had no room over a stand 1.2 mm off the neck and stood up, 15 deg)
            cl_ = HUG_CLEAR + 0.002 if nm in (B.get("hug") or []) else clear
            obs.append((body.V + bn * (cl_ - lay), bn, 0.008))
        if fd["turn"] > 0 and to in ("neck", "seam"):  # a fold over a band: it lies on the pieces under it too (a collar's fall
            # on its stand). Torso pieces lap each other either way (a coat's left front over its right): their flaps
            # lie on their own base
            for j, o in enumerate(names[:k]):
                # (not its own mirror half: they stand side by side, neither lies on the other)
                if pcs[o]["wrap"].get("to", "torso") == to and \
                        pcs[o]["wrap"].get("half", 0) * pcs[nm]["wrap"].get("half", 0) >= 0:
                    obs.append(foldmod.samples(X, F[pid[F[:, 0]] == j], faces[o]))
        if fd["turn"] > 0 and to == "torso":
            # a torso piece rolled back at the neck (a shirt worn open) rolls UNDER the collar's fall, laid first (the
            # fall turned over the fronts and the fronts rolled out through it: 11 crossings at the start). Normals
            # turned in: the flap stays on the inner side of the neck pieces
            for j, o in enumerate(names):
                if pcs[o]["wrap"].get("to", "torso") in ("neck", "seam"):
                    p_, n_ = foldmod.samples(X, F[pid[F[:, 0]] == j], faces[o])
                    obs.append((p_, -n_, 0.008))
        hm = float(np.median(np.linalg.norm(M["uv"][F[:, 0]] - M["uv"][F[:, 1]], axis=1)))
        if _pressed(B, M, fd):
            # a forepart laid where it is worn: its lapel is PRESSED onto it (the flap's mirror image across the roll
            # line, on the base): turned rigidly about the roll line over a base that follows the chest and shoulder,
            # the flap stretched past 30% by 50 deg and stood up round the neck
            X = foldmod.pressed_flap(X, M, fd, faces[nm], float(B.get("press_lay") or PRESS_LAY), wedge=float(np.clip(0.0012 / hm, 0.04, 0.15)) if smooth else 0.08)
            info[fd["name"]] = {"pressed": True}
            continue
        X, info[fd["name"]] = foldmod.apply(X, M, fd, faces[nm], obs, lay,
                                            wedge=float(np.clip(0.0012 / hm, 0.04, 0.15)) if smooth else 0.08,
                                            max_stretch=0.30)  # (made pieces start up to that far past their flat lengths: the solver lifts their limit)
        info[fd["name"]].pop("_tv", None)
    if not spread_done:
        X = _spread_open_collar(B, M, body, X, smooth)
    B["fold_info"] = info
    return X


COLLAR_SPREAD = (18.0, 14.0, 65.0)  # deg: an open collar's front swung out from the neck, tipped down onto the
# collarbones, from this far round from the nape (0) toward the front (180)


def _spread_open_collar(B: dict, M: dict, body: "Body", X: np.ndarray, smooth: bool) -> np.ndarray:
    """A collar worn OPEN (its stand's own closure undone) lies spread, as worn without a tie: the stand still hugs
    the back and sides of the neck, but in front of the neck's sides it swings OUT (about a hinge up the neck's side)
    and tips DOWN, so its ends and the collar's points lie on the collarbones with the fronts rolled back under them
    (the user on su_77: our collar stood up round the neck like a ring; the concept's lies spread inside the
    lapels). Laid ring-like and carried as made, it ended as it started. Every neck piece turns with its stand,
    smoothly by its angle round the neck; garment key `collar_spread` [out deg, down deg, from deg] (or false)."""
    spread = B.get("collar_spread", COLLAR_SPREAD)
    if not spread:
        return X
    out_deg, down_deg, from_deg = (float(v) for v in spread)
    pcs, names, pid = B["pieces"], M["names"], M["piece"]
    neck = [n for n in names if pcs[n]["wrap"].get("to") == "neck"]
    opened = [c for c in M.get("closures") or [] if c.get("over") in neck and c["over"] == c.get("under")
              and len(c.get("closed") or []) and not any(c["closed"])]
    if not opened or not len(body.V):
        return X
    st = names.index(opened[0]["over"])
    ids = np.where(np.isin(pid, [names.index(n) for n in neck]))[0]
    S = X[pid == st]
    cen = S.mean(0)
    _, _, vt = np.linalg.svd(S - cen)
    d = vt[2] if vt[2][2] > 0 else -vt[2]  # the ring's axis, up
    back = np.array([0, 1.0, 0]) - d * d[1]
    back /= np.linalg.norm(back)
    side = np.cross(d, back)
    Q = X[ids] - cen
    phi = np.arctan2(Q @ side, Q @ back)
    R = float(np.median(np.linalg.norm(S - cen - np.outer((S - cen) @ d, d), axis=1)))
    f0 = math.radians(from_deg)
    # which side of the neck a vertex belongs to: by its piece's own pattern half, not by where it lies (ends that
    # lap past the centre front, a stand laid nearly closed, lay on the OTHER side and swung with it: the ends crossed
    # further instead of parting, button to buttonhole 10 mm after an 18 deg spread)
    sgn = np.sign(phi)
    sgn[sgn == 0] = 1.0
    aphi = np.abs(phi)
    for nm in neck:
        mp = pid[ids] == names.index(nm)
        if not mp.any():
            continue
        ux = M["uv"][ids[mp], 0]
        ux = ux - 0.5 * (ux.min() + ux.max())
        ref = aphi[mp] < 2.0
        cor = np.sign(float((ux[ref] * phi[mp][ref]).sum())) or 1.0
        s_ = np.sign(ux) * cor
        s_[s_ == 0] = 1.0
        over_ = (s_ != sgn[mp]) & (aphi[mp] > 0.5 * np.pi)  # past the centre front
        ap = aphi[mp]
        ap[over_] = 2 * np.pi - ap[over_]
        aphi[mp] = ap
        sg_ = sgn[mp]
        sg_[over_] = s_[over_]
        sgn[mp] = sg_
    t = np.clip((aphi - f0) / (np.pi - f0), 0, 1)
    t = t * t * (3 - 2 * t)
    out = np.zeros_like(Q)
    for sg in (-1.0, 1.0):
        m = sgn == sg
        if not m.any():
            continue
        H = R * (math.cos(f0) * back + sg * math.sin(f0) * side)  # the hinge up the neck's side
        tang = -math.sin(f0) * back + sg * math.cos(f0) * side  # round the ring toward the front
        tang /= np.linalg.norm(tang)
        radial = H / np.linalg.norm(H)
        for i in np.where(m)[0]:
            q = Q[i] - H
            a = math.radians(out_deg) * t[i]
            # out: about the hinge's vertical, the side that takes the front away from the neck
            r1 = _rot(d, a * (1 if np.dot(np.cross(d, tang), radial) > 0 else -1))
            q = r1 @ q
            # down: about the ring's radial direction at the hinge, front end toward the chest
            b = math.radians(down_deg) * t[i]
            r2 = _rot(radial, b)
            q2 = r2 @ q
            r3 = _rot(radial, -b)
            q3 = r3 @ q
            q = q2 if (q2 @ d) < (q3 @ d) else q3
            out[i] = H + q
    Xn = X.copy()
    Xn[ids] = cen + out
    Xn[ids] = body.push_out(Xn[ids], HUG_CLEAR if smooth else CLEAR)
    B["collar_spread_info"] = {"pieces": neck, "moved_max_mm": round(float(np.linalg.norm(Xn[ids] - X[ids], axis=1).max()) * 1000, 1)}
    return Xn


def _rot(axis: np.ndarray, ang: float) -> np.ndarray:
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K


def _piece_crossings(X: np.ndarray, M: dict) -> set:
    """Pairs of pieces (names) where an edge of one passes through a triangle of the other in X (seams not excused)."""
    F, pid, names = M["F"], M["piece"], M["names"]
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    cen = X[F].mean(1)
    rad = np.max(np.linalg.norm(X[F] - cen[:, None], axis=2), axis=1)
    mid = 0.5 * (X[E[:, 0]] + X[E[:, 1]])
    half = 0.5 * np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
    # (one search radius for all: a placement that flung vertices away, or left them NaN, made every edge a candidate
    # for every triangle: 17 GB of pairs, the machine's OOM of 2026-10-08. Such a start is not a start.)
    r_ok = 8.0 * max(float(np.median(rad)), 1e-4) + 0.05
    if not np.isfinite(X).all() or float(rad.max()) > r_ok:
        bad = int(np.argmax(np.where(np.isfinite(rad), rad, np.inf)))
        raise ClothError(f"the start is broken: a triangle of {names[pid[F[bad, 0]]]} is {float(rad[bad]) * 2:.2f} m across "
                         f"(the mesh's are ~{float(np.median(rad)) * 2000:.0f} mm) or not finite: its placement failed")
    # one search radius for all (the largest triangle's) made every edge a candidate of every triangle when ONE
    # triangle was large (su_garrett's trousers start: 12+ GB of pairs, a process killed for memory, 2026-10-08): the
    # ordinary triangles through the tree at their own size, the few large ones against the edges near each, in chunks
    rcap = float(min(rad.max(), max(np.percentile(rad, 99), 2 * np.median(rad))))
    small = np.where(rad <= rcap)[0]
    out = set()

    def test(ei, ti):
        keep = ~((F[ti] == E[ei, 0][:, None]).any(1) | (F[ti] == E[ei, 1][:, None]).any(1))
        ei, ti = ei[keep], ti[keep]
        T = F[ti]
        hit = _seg_tri(X[E[ei, 0]], X[E[ei, 1]], X[T[:, 0]], X[T[:, 1]], X[T[:, 2]])
        out.update(tuple(sorted((names[pid[E[e, 0]]], names[pid[F[t, 0]]]))) for e, t in zip(ei[hit], ti[hit]))
    if len(small):
        tree = cKDTree(cen[small])
        for s in range(0, len(E), 20000):
            cand = tree.query_ball_point(mid[s:s + 20000], r=half[s:s + 20000] + rcap, return_sorted=False)
            ei = np.repeat(np.arange(s, s + len(cand)), [len(c) for c in cand])
            ti = small[np.fromiter((t for c in cand for t in c), dtype=np.int64, count=len(ei))]
            if len(ei):
                test(ei, ti)
    big = np.where(rad > rcap)[0]
    if len(big):
        etree = cKDTree(mid)
        for t in big:
            ei = np.asarray(etree.query_ball_point(cen[t], r=float(rad[t] + half.max())), np.int64)
            if len(ei):
                test(ei, np.full(len(ei), t))
    return out


def _snap(X: np.ndarray, B: dict, M: dict, sigma: float = 0.08) -> np.ndarray:
    """Each piece that isn't wrapped on the torso is moved toward the pieces it's sewn to (in order: sleeves onto the
    armholes, cuffs onto the sleeves, a stand onto the neckline, a collar onto the stand): the seam's gaps as a smooth
    displacement over the piece (Gaussian weights in pattern coordinates), full at the seam, fading away from it."""
    X = X.copy()
    names = M["names"]
    done = {k for k, nm in enumerate(names) if B["pieces"][nm]["wrap"].get("to", "torso") in ("torso", "flat", "leg.L", "leg.R")}
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
    torso = np.isin(M["piece"], [k for k, nm in enumerate(M["names"]) if wraps[nm] in ("torso", "leg.L", "leg.R")])
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


NOT_SIM = ("color", "roughness", "cleanup", "detail", "sculpt", "note", "design", "_design", "trims")  # never change the sim
# (a design sheet changes the sim only through the keys it compiles into)


def _fabric_at(g: dict, h: float) -> dict:
    fab = fabric(g)
    # Blender's cloth mass is per vertex: the presets are per vertex at 2 cm triangles, so a finer mesh keeps the
    # garment's weight (and so its stretch and drape under gravity) by scaling it with the area a vertex carries
    fab["mass"] = float(fab["mass"]) * (h / H_REF) ** 2
    # lighter vertices on the same springs ring twice as fast per halving of h: more substeps (quality 6 at 1 cm
    # crumpled one interfaced cuff of a symmetric pair into a ball, the other not: an instability)
    fab.setdefault("quality", int(round(6 * max(1.0, H_REF / h))))
    return fab


def _blender_job(job_dir: Path, cfg: dict, arrays: dict, name: str, log, progress, timeout: float = 3600,
                 backend: str = "blender", names: list | None = None) -> tuple:
    """Run blender_cloth.py on a job (under resources.heavy), streaming its "cloth:" lines to `progress`; or hand the
    same solver-neutral job folder (cloth_job) to another backend ("file", "remote").
    Returns (out.npz contents, the log lines without progress)."""
    from . import cloth_job, resources, render as rmod
    import shutil
    job_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(job_dir).free / 2**30
    if free < SIM_MIN_FREE_GB:  # a full disk has stopped the machine before (solver sessions write every frame)
        raise RuntimeError(f"cloth sim {name}: only {free:.1f} GB free on the disk (need {SIM_MIN_FREE_GB}): not started")
    if backend != "blender":
        jd = cloth_job.write(job_dir / cfg.get("mode", "sim"), cfg, arrays, names)
        if backend == "zozo":
            return cloth_job.run_zozo(jd, progress, log)
        return cloth_job.run_external(jd, backend, progress)
    cloth_job.write(job_dir, cfg, arrays, names)
    progress(f"waiting for the heavy-job slot ({cfg.get('mode', 'sim')})")
    both = lambda m: (log(m), progress(m))  # noqa: E731
    with resources.heavy(f"cloth {name}", log=both, kind="cloth_blender", model=name):
        progress(f"started {cfg.get('mode', 'sim')}")
        t = time.time()
        p = subprocess.Popen([rmod.BLENDER, "-b", "--factory-startup", "--python", str(SCRIPT), "--",
                              str(job_dir / "job.json")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        resources.track(p)
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
        # (a vertex just outside the coarse outline runs on in its nearest triangle's plane: clamped onto the triangle,
        # two fine vertices beyond one coarse corner landed on the same point, a zero-area triangle)
        w = np.clip(W[np.arange(len(Q)), best], -0.6, None)
        w /= w.sum(1, keepdims=True)
        T = Fc[cand[np.arange(len(Q)), best]]
        out[sel] = np.einsum("nk,nkd->nd", w, Vs[T])
    return out


def made_pieces(M: dict, stiff: np.ndarray) -> list:
    """Pieces wholly interfaced (a collar, a stand, cuffs): their placed shape is the made shape. A solver resting on
    the flat pattern (placement "smooth") rests these as placed, in stretch and bending: a turned collar's U and a
    cuff's curl are how they were made, and a fold over coarse triangles isn't isometric to the flat."""
    if M.get("made") is not None:  # (mesh(): the design's and the garment's say over the interfacing rule)
        return list(M["made"])
    return [nm for k, nm in enumerate(M["names"]) if stiff[M["piece"] == k].mean() > 0.9]


def rest_shape(M: dict, X0: np.ndarray, stiff: np.ndarray, smooth: bool, made: np.ndarray | None = None) -> np.ndarray:
    """What the sim's cloth rests on, as positions with its edge lengths: the start (placement "fitted"), or the flat
    pattern with the made pieces as placed ("smooth"; `made`: their placement before it was pushed clear of the
    body, the shape they were made to: a cuff pushed off the wrist rested 17-30% too big and ruffled)."""
    if not smooth:
        return X0
    R = np.c_[M["uv"], np.zeros(len(M["uv"]))]
    for nm in made_pieces(M, stiff):
        sel = M["piece"] == M["names"].index(nm)
        R[sel] = (made if made is not None else X0)[sel]
    return R


def sleeve_angles(V: np.ndarray, M: dict, Bp: dict) -> dict:
    """Each arm's sleeve axis angle from vertical (deg): the centre of its cap's top (top 8% of each sleeve piece's
    pattern height) to the centre of its hem (bottom 4%). A garment on a hanger hangs its sleeves under ~5 deg."""
    out = {}
    for side in ("L", "R"):
        ks = [k for k, nm in enumerate(M["names"]) if Bp["pieces"][nm]["wrap"].get("to") == f"arm.{side}"
              and not _closed_girth(M, nm) and "follow" not in Bp["pieces"][nm]["wrap"]]
        top, hem = [], []
        for k in ks:
            sel = np.where(M["piece"] == k)[0]
            y = M["uv"][sel, 1]
            lo, hi = y.min(), y.max()
            top.append(sel[y > hi - 0.08 * (hi - lo)])
            hem.append(sel[y < lo + 0.04 * (hi - lo)])
        if not ks:
            continue
        v = V[np.concatenate(hem)].mean(0) - V[np.concatenate(top)].mean(0)
        out[side] = float(np.degrees(np.arccos(np.clip(-v[2] / np.linalg.norm(v), -1, 1))))
    return out


def _made_rest(Bp: dict, M: dict, X: np.ndarray) -> np.ndarray | None:
    """Where made pieces rest (placement smooth): pieces closed round an arm (cuffs) as placed before the push clear of
    the body (pushed, a cuff rested 17-30% too big and ruffled); everything else as it starts (a collar resting
    unpushed, its fall shorter than the layer it lies at, stood up and flared at the front; as placed it rolls
    round the neck cleanly)."""
    U = Bp.get("start_unpushed")
    if U is None:
        return None
    R = X.copy()
    for k, nm in enumerate(M["names"]):
        if Bp["pieces"][nm]["wrap"].get("to", "").startswith("arm.") and _closed_girth(M, nm):
            R[M["piece"] == k] = U[M["piece"] == k]
    return R


def _hang_pins(state: dict, Mx: dict, Xx: np.ndarray) -> np.ndarray:
    """The old pinned hang's vertices (state {"hang": {"pins": [...], "hook", "rack"}}): a hanger loop holds a patch,
    not a vertex: every vertex within `radius` of a named pin point (start positions)."""
    pins = [Mx["points"].get(p, Mx["marks"].get(p)) for p in state["hang"].get("pins", [])]
    if None in pins:
        raise KeyError(f"hang pins: no such point/mark in {state['hang'].get('pins')}")
    rad = float(state["hang"].get("radius", 0.03))
    return np.unique(np.concatenate([np.where(np.linalg.norm(Xx - Xx[p], axis=1) < rad)[0] for p in pins]))


def _rack_hanger(state: dict) -> dict:
    """The old pinned hang's rack capsules as a hanger dict (for the support measure: no arms, no hook)."""
    segs = [(np.asarray(a, float), np.asarray(b, float), (r, r), (r, r), "rack")
            for a, b, r in (state["hang"].get("rack") or [])]
    return {"segments": segs, "rail": []}


def _kabsch(A: np.ndarray, B: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(R, t): the rigid move taking points A onto B (least squares): B ~ A @ R.T + t."""
    ca, cb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    return R, cb - ca @ R.T


def made_flaps(g: dict, M: dict) -> list:
    """[(fold name, flap vertices)] of the folds whose flaps are made (garment key "made_folds": fold names or name
    prefixes, e.g. ["lapel"]): the cloth past a pressed roll line, held with the construction it is sewn to."""
    want = g.get("made_folds") or []
    if not want or not M.get("folds"):
        return []
    from . import folds as foldmod
    out = []
    for k, fd in enumerate(M["folds"]):
        nm = fd.get("name") or ""
        if any(nm == w or nm.startswith(w) for w in want):
            out.append((f"{nm}:{fd['piece']}", foldmod._geom(M, fd)["rows"][0]["v"]))
    return out


def _carry(Bp: dict, M: dict, X: np.ndarray, body0: "Body", poses: list, made: list | None = None,
           flaps: list | None = None) -> dict:
    """Method "settle": the made pieces (made_pieces, or the garment's "made" list) are held as constructed and ride
    the part of the body they were made on while it moves from `body0` through `poses` (vertex arrays of the same
    body): each piece's rigid move is fitted (Kabsch) to the body vertices near it. Returns {"idx" vertices,
    "poses" (k, m, 3) their positions per pose, "moves" {piece: (R, t) of the last pose}, "pieces"}."""
    names = made_pieces(M, interfacing(Bp, M)) if not made else [nm for nm in made if nm in M["names"]]
    tree = cKDTree(body0.V)
    idx, P, moves = [], [], {}
    # Made pieces sewn to each other are ONE construction (a collar on its stand) and ride the body as one: each
    # fitted to the body under itself, the stand took the neck's move and the collar, whose fall lies over the
    # shoulders, the shoulders': after the arms' poses they stood 16-25 mm apart all round, the collar's seam to
    # its stand open at every pair (su_02, the shirt with the collar built closed). The group takes the move of
    # its root: the piece with the most seam to draped cloth (the stand on the neckline)
    pid, sw = M["piece"], np.asarray(M["sew"]).reshape(-1, 2)
    ks = {nm: M["names"].index(nm) for nm in names}
    root = {nm: nm for nm in names}

    def find(a):
        while root[a] != a:
            a = root[a]
        return a
    madek = np.isin(pid, list(ks.values()))
    to_draped = {nm: int(((pid[sw[:, 0]] == k) & ~madek[sw[:, 1]]).sum() + ((pid[sw[:, 1]] == k) & ~madek[sw[:, 0]]).sum())
                 for nm, k in ks.items()}
    for a in names:
        for b in names:
            if a < b and (((pid[sw[:, 0]] == ks[a]) & (pid[sw[:, 1]] == ks[b])) | ((pid[sw[:, 0]] == ks[b]) & (pid[sw[:, 1]] == ks[a]))).any():
                ra, rb = find(a), find(b)
                if ra != rb:
                    hi, lo = (ra, rb) if to_draped[ra] >= to_draped[rb] else (rb, ra)
                    root[lo] = hi
    nbs = {}
    for nm in names:
        sel = np.where(M["piece"] == M["names"].index(nm))[0]
        rt = find(nm)
        if rt not in nbs:
            rs = np.where(M["piece"] == M["names"].index(rt))[0]
            c = X[rs].mean(0)
            r = float(np.linalg.norm(X[rs] - c, axis=1).max())
            nb = np.asarray(tree.query_ball_point(c, r + 0.01))
            if len(nb) < 6:
                nb = tree.query(c, k=30)[1]
            nbs[rt] = nb
        nb = nbs[rt]
        per = []
        for Vp in poses:
            R, t = _kabsch(body0.V[nb], np.asarray(Vp)[nb])
            per.append(X[sel] @ R.T + t)
        moves[nm] = (R, t)
        idx.append(sel)
        P.append(np.stack(per))
    # made REGIONS of draped pieces (garment key "made_folds": a lapel's flap past its roll line, pressed with the
    # chest canvas): held as laid and carried with the made piece they are sewn to (the collar along the gorge), so
    # collar + lapel + gorge are one pressed unit; the rest of the piece stays draped, joined along the roll line
    flap_info = {}
    taken = np.zeros(len(X), bool)
    for s_ in idx:
        taken[s_] = True
    for label, fv in flaps or []:
        fv = np.asarray(fv, np.int64)
        fv = fv[~taken[fv]]
        if not len(fv):
            continue
        taken[fv] = True
        fm = np.zeros(len(X), bool)
        fm[fv] = True
        part = [nm for nm in names if (((pid[sw[:, 0]] == ks[nm]) & fm[sw[:, 1]]) | ((pid[sw[:, 1]] == ks[nm]) & fm[sw[:, 0]])).any()]
        if part:
            nb = nbs[find(part[0])]
        else:
            c = X[fv].mean(0)
            nb = np.asarray(tree.query_ball_point(c, float(np.linalg.norm(X[fv] - c, axis=1).max()) + 0.01))
            if len(nb) < 6:
                nb = tree.query(c, k=30)[1]
        per = []
        for Vp in poses:
            R, t = _kabsch(body0.V[nb], np.asarray(Vp)[nb])
            per.append(X[fv] @ R.T + t)
        idx.append(fv)
        P.append(np.stack(per))
        flap_info[label] = {"vertices": int(len(fv)), "with": find(part[0]) if part else None}
    if not idx:
        return {"idx": np.zeros(0, np.int64), "poses": np.zeros((len(poses), 0, 3)), "moves": {}, "pieces": []}
    fi_ = np.where(taken & ~np.isin(pid, list(ks.values())))[0] if flap_info else np.zeros(0, np.int64)
    return {"idx": np.concatenate(idx), "poses": np.concatenate(P, axis=1), "moves": moves, "pieces": names,
            "roots": {nm: find(nm) for nm in names}, "flaps": flap_info, "flap_idx": fi_}


def _open_start(Bp: dict, M: dict, Xs: np.ndarray, body0: "Body", poses: list, carry: dict) -> tuple:
    """Method "settle" with a notched collar (place: B["open_lay"]): the sim starts with the collar's fall standing
    OPEN and the carried poses turn it down, as a tailor sews the collar on and then rolls it over: laid down from
    the start, the fall was a lid over the neck seam and the draped back came to rest on top of it. Each open lay
    takes what place did to the closed one afterwards (the relax, the push clear of the body) and is cleared of the
    body; pose k gets the lay NOTCH_OPEN_STEPS[k + 1] open (the last pose closed), moved with the body as the closed
    one is. Returns (start positions, carry with its poses replaced for those pieces)."""
    Xstart = Xs.copy()
    P = np.array(carry["poses"], copy=True)
    at = {int(v): i for i, v in enumerate(carry["idx"])}
    for nm, ol in Bp["open_lay"].items():
        if nm not in carry["pieces"]:
            continue
        sel = np.where(M["piece"] == M["names"].index(nm))[0]
        delta = Xs[sel] - np.asarray(ol["closed"])
        lays = {fr: body0.push_out(np.asarray(o) + delta, SMOOTH_CLEAR) for fr, o in ol["open"].items()}
        Xstart[sel] = lays[NOTCH_OPEN_STEPS[0]]
        cols = np.array([at[int(v)] for v in sel])
        for k, Vp in enumerate(poses[:-1]):
            fr = NOTCH_OPEN_STEPS[k + 1] if k + 1 < len(NOTCH_OPEN_STEPS) else 0.0
            if fr <= 0:
                continue
            Xk = Xs.copy()
            Xk[sel] = lays[fr]
            ck = _carry(Bp, M, Xk, body0, [Vp], made=list(carry["pieces"]))
            atk = {int(v): i for i, v in enumerate(ck["idx"])}
            P[k][cols] = ck["poses"][0][[atk[int(v)] for v in sel]]
    return Xstart, dict(carry, poses=P)


FINE_REACH = 0.10  # m from a made piece within which the fine settle moves the draped cloth
FINE_FREE = 40.0  # deg a made flap starts open when it is free in the fine settle (it closes by its own stiff fold)
FINE_OPEN = 55.0  # deg a made flap starts open in the fine settle (clear of the cloth it then presses down)
MADE_SHAPE = 0.008  # m (p90): a made piece laid this differently at the fine size keeps the coarse sim's shape
HELD_STEP = 0.003  # m the most _clear_of_held moves a vertex
HELD_GAP = 0.0015  # m the draped cloth is kept off a made piece's surface at the fine settle's start (_clear_of_held)


def _clear_of_held(V: np.ndarray, Vd: np.ndarray, M: dict, held: np.ndarray, reach: float = 0.008,
                   gap: float = HELD_GAP, rounds: int = 3, movable: np.ndarray | None = None) -> np.ndarray:
    """The draped cloth near a made piece put back on the side of it it lies on in the coarse drape Vd (the coarse
    sim carried onto the fine mesh, where both lie as the sim left them), at least `gap` off it. The made pieces are
    fitted rigidly from their own fine placement onto the coarse ones, the drape is interpolated: layers a few mm apart
    come out through each other (ga_suit's shirt: its collar's fall through both fronts, 80 crossings), and smoothing
    that out moved the fronts 20 mm and stretched their fold rows 3x."""
    from .closures import _closest_on
    if not held.any() or held.all():
        return V
    V = V.copy()
    F = M["F"]
    Fh = F[held[F].all(1)]
    if not len(Fh):
        return V
    free = np.where(~held if movable is None else movable & ~held)[0]
    tree = cKDTree(V[Fh].mean(1))
    near = free[tree.query(V[free], distance_upper_bound=reach + 0.02)[0] < reach + 0.02]
    if not len(near):
        return V
    qd, nd, ind = _closest_on(Vd[near], Vd, Fh)
    sd = np.sum((Vd[near] - qd) * nd, 1)
    side = np.sign(sd)
    keep = (np.abs(sd) < reach) & ind & (side != 0)  # (projecting inside a triangle: not round an edge)
    near, side = near[keep], side[keep]
    for _ in range(rounds):
        if not len(near):
            break
        q, n, _ = _closest_on(V[near], V, Fh)
        s_ = np.sum((V[near] - q) * n, 1) * side
        bad = s_ < gap
        if not bad.any():
            break
        # (at most HELD_STEP a vertex: a front rolled open under a collar, pushed by the full shortfall vertex by
        # vertex, came out 5x stretched)
        V[near[bad]] += (np.minimum(gap - s_[bad], HELD_STEP) * side[bad])[:, None] * n[bad]
    return V


START_GAP = 0.0012  # m: the fine settle's start is kept this far off the collider (body + worn parts + under garment)
FAR_CLEAR = 0.0012  # m the carried far cloth is kept off the body at the fine settle's start
FINE_ROOM = 0.0055  # the room a pressed flap leaves over the body for the cloth under it (m)


FINE_START_MAX = 0.6  # the fine settle's start may stretch its draped cloth this far at most (the solver's top limit)


def fine_start_check(M: dict, plan: dict, limit: float = FINE_START_MAX) -> str:
    """'' when the fine settle's start can be solved, else where it can't: draped triangles (no made vertex) that the
    solver moves (not every vertex carried) stretched past 1 + limit from the flat pattern. (tr_13's trousers started
    10.9x at the back forks and ran to a CORRUPT result; tr_14's shirt 11.4x on a sliver at the neck point: ccd failed.)"""
    from .cloth_zozo import _start_stretch
    F = M["F"]
    carried = np.zeros(len(M["uv"]), bool)
    carried[plan["idx"]] = True
    made = np.zeros(len(M["uv"]), bool)
    made[plan["rest_idx"]] = True
    t = ~made[F].any(1) & ~carried[F].all(1)
    if not t.any():
        return ""
    s = _start_stretch(np.c_[M["uv"], np.zeros(len(M["uv"]))], plan["start"], F[t])
    over = s > 1.0 + limit
    if not over.any():
        return ""
    Ft = F[t][over]
    by = {}
    for f, v in zip(Ft, s[over]):
        nm = M["names"][M["piece"][f[0]]]
        by[nm] = max(by.get(nm, 0.0), float(v))
    worst = Ft[int(np.argmax(s[over]))]
    return (f"{int(over.sum())} triangles over {1 + limit:.2f}x, worst {float(s.max()):.2f}x; by piece "
            + ", ".join(f"{k} {v:.1f}x" for k, v in sorted(by.items(), key=lambda kv: -kv[1]))
            + f"; worst at pattern {np.round(M['uv'][worst].mean(0), 3).tolist()}")


def _press_plan(Bp: dict, Ms: dict, Xs: np.ndarray, Vc: np.ndarray, M: dict, Xf: np.ndarray, carry: dict,
                body: "Body", press: bool = False) -> dict:
    """Method "settle"'s fine settle, set up: the coarse drape carried onto the fine mesh M (kept clear of the body),
    the made pieces from the fine placement set where the coarse ones were held, their turned-over flaps OPENED
    (FINE_OPEN) so nothing starts through them, and the positions they close through (`poses`): down to the made
    fold, or as far as leaves FINE_ROOM over the body for the cloth under them. In the sim the made pieces are
    prescribed: the flap presses the cloth down as an iron does, and the cloth settles round them by contact.
    Returns {"start", "drape" (the plain carried drape), "idx" (the made pieces' vertices), "poses" (k, m, 3),
    "info"}."""
    from . import folds as foldmod
    Vd = transfer(Ms, Vc, M)
    V = Vd.copy()
    Xc_on_f = transfer(Ms, Xs, M)
    held = np.zeros(len(V), bool)
    for nm in carry["pieces"]:
        sel = M["piece"] == M["names"].index(nm)
        # (fitted on the group's root, as in _constructed: a collar goes with its stand)
        rsel = M["piece"] == M["names"].index((carry.get("roots") or {}).get(nm, nm))
        R0, t0 = _kabsch(Xf[rsel], Xc_on_f[rsel])
        R1, t1 = carry["moves"][nm]
        V[sel] = (Xf[sel] @ R0.T + t0) @ R1.T + t1
        held[sel] = True
        Rs, ts = _kabsch(V[sel], Vd[sel])
        dev = float(np.percentile(np.linalg.norm(V[sel] @ Rs.T + ts - Vd[sel], axis=1), 90))
        if dev > MADE_SHAPE:
            Bp.setdefault("made_reshaped", {})[nm] = round(dev * 1000, 1)
    # a made piece laid in another SHAPE at the fine size than the coarse sim solved round (su_garrett's collar fall:
    # 174 deg placed at 1 cm, 160 at 2 cm; its points 15-20 mm lower, into the fronts rolled open under it: a 2.8x start
    # after the untangle) keeps the coarse sim's shape, carried onto the fine mesh, with the whole group it is made with
    # (a collar with its stand: one of them alone crossed the other along their seam). Rest stays the fine placement.
    if Bp.get("made_reshaped"):
        roots = carry.get("roots") or {}
        grp = {roots.get(n_, n_) for n_ in Bp["made_reshaped"]}
        Vp = V.copy()  # (the fine placement: its pieces lie on the right sides of each other)
        members = [nm for nm in carry["pieces"] if roots.get(nm, nm) in grp]
        for nm in members:
            V[M["piece"] == M["names"].index(nm)] = Vd[M["piece"] == M["names"].index(nm)]
        # the coarse group's own layers through each other (the transfer cuts a 2 cm fall's roll; the coarse sim
        # already had its collar a few mm into its stand: 147 crossings at the fine size) put back on the sides the
        # fine placement has them: each piece's vertices off its sewn edges moved off the others
        sewn_ = np.zeros(len(V), bool)
        sewn_[np.asarray(M["sew"]).ravel()] = True
        for nm in members:
            mine = M["piece"] == M["names"].index(nm)
            others = np.isin(M["piece"], [M["names"].index(o) for o in members if o != nm])
            if others.any():
                V = _clear_of_held(V, Vp, M, others, reach=0.012, gap=0.0008, rounds=4, movable=mine & ~sewn_)
    # the carried drape's overstretched edges taken back (at piece outlines the transfer runs on past the coarse
    # outline, and seams drawn together: a few dozen triangles 5-70% long, which a strain-limited solver can't start
    # from)
    V = _relax_stretch(V, M, ~held, 0.02)
    # the cloth the settle won't move (further than FINE_REACH from every made piece: carried as the coarse sim left it)
    # is only taken out of the body, not out to the solver's standoff (the settle's contact offset follows what the start
    # leaves): pushed to the standoff, the trousers' fork tips in the crotch's hollow went 35-106 mm across the body and
    # the start was 10x stretched there
    far0 = np.zeros(len(V), bool)
    if not press and held.any():
        far0 = ~held & (cKDTree(V[held]).query(V)[0] > FINE_REACH + 0.01)
    near0 = ~held & ~far0
    if len(body.V):  # (a fine vertex on a coarse facet's chord can lie inside the solver's standoff from the body)
        def clear(V):
            V = _clear_of_body(V, M["F"], near0, body, 0.0042, 0.0034, CLEAR_GROW)
            return _clear_of_body(V, M["F"], far0, body, FAR_CLEAR, FAR_CLEAR, CLEAR_GROW) if far0.any() else V
        V = clear(V)
        V = _relax_stretch(V, M, ~held, 0.03, iters=15)
        V = clear(V)
        V = _clear_of_held(V, Vd, M, held)
        V, untangled = _untangle(V, M, ~held, reshape=True)
        if len(untangled) > 1:
            V = clear(V)
        Bp["untangled"] = untangled + [int(_crossing_verts(V, M).sum())]
        # (the made pieces too, by the little their rigid fit onto the coarse ones left them inside the standoff: a
        # held vertex within it is fatal as well)
        V = _clear_of_body(V, M["F"], held, body, 0.0032, 0.0027, CLEAR_GROW)
    faces = Bp.get("faces") or {}
    bn, _ = body.normals() if len(body.V) else (np.zeros((0, 3)), None)
    turns, info = [], {}
    Vt = V.copy()
    for fd in M.get("folds") or []:
        if fd["piece"] not in carry["pieces"] or fd["turn"] <= 0:
            continue
        face = faces.get(fd["piece"], 1.0)
        full = abs(math.degrees(fd["turn"])) * len(fd["rows"])
        cur = foldmod.measure(Vt, M, fd, face).get("turn_deg", 170.0)
        obs = [(body.V + bn * (FINE_ROOM - FOLD_LAY), bn, 0.008)] if len(body.V) else []
        Vt, inf = foldmod.apply(Vt, M, fd, face, obs, FOLD_LAY, t_max=max(0.0, (179.0 - cur) / full),
                                t_min=-RELAY_OPEN / full, steps=30, own_base=True, wedge=0.03)
        turns.append((fd, face, inf.pop("_tv"), -(FINE_OPEN if press else FINE_FREE) / full))
        info[fd["name"]] = dict(inf, was_deg=cur)

    def at(a):  # the made pieces with every flap a (0 open .. 1 pressed) of the way closed
        W = V.copy()
        for fd, face, tv, t_open in turns:
            W = foldmod.turn_flap(W, M, fd, t_open + (tv - t_open) * a, face)
        return W
    flaps = np.zeros(len(V), bool)
    for fd, *_r in turns:
        flaps[foldmod._geom(M, fd)["rows"][0]["v"]] = True
    start = at(0.0)
    if not press and turns:
        # free flaps start opened only as far as clears the cloth under them, station by station (a curved crease has
        # one isometric angle: opened 40-55 deg the fall started 100%+ stretched at its roll)
        start = V.copy()
        loose_t = M["F"][~held[M["F"]].any(1)]
        for fd, face, tv, t_open in turns:
            full = abs(math.degrees(fd["turn"])) * len(fd["rows"])
            obs = [(foldmod.samples(start, loose_t, 1.0)[0], _out_normals(start, loose_t, body), 0.012)]
            start, inf = foldmod.apply(start, M, fd, face, obs, 0.004, t_max=0.0, t_min=-70.0 / full, steps=36,
                                       own_base=True, wedge=0.03)
            info[fd["name"]]["start_open_deg"] = inf["turn_deg"]
        # what still passes through an opened flap (the stations are eased along the line) is smoothed out from under it
        start, ut = _untangle(start, M, ~held, reshape=True)
        if len(ut) > 1 and len(body.V):
            start = _clear_of_body(start, M["F"], ~held, body, 0.0042, 0.0034, CLEAR_GROW)
        Bp["untangled"] = (Bp.get("untangled") or []) + ["flaps"] + ut + [int(_crossing_verts(start, M).sum())]
    # press: the flaps prescribed closed, then released (two prescribed things squeezing cloth between them stopped
    # the solver on intersections). Default: the flaps are free cloth from the first frame, resting folded as made:
    # their stiff fold closes them onto whatever lies under them, and they bend over it
    # only the cloth near the made pieces is settled (within FINE_REACH of them): the rest keeps the carried drape,
    # held. (Settled everywhere, the sleeves took on 1 cm sim crumple again under the strain limit the start needs.)
    far = np.zeros(len(V), bool)
    if not press and held.any():
        dn, _ = cKDTree(start[held]).query(start)
        far = ~held & (dn > FINE_REACH)
    # tacks: a point of a made flap stitched to the cloth under it (a collar's points held down: stays, buttons)
    tacks = []
    for tk in Bp.get("tacks") or []:
        v = M["points"].get(f"{tk['piece']}:{tk['point']}", M["marks"].get(f"{tk['piece']}:{tk['point']}"))
        if v is None or tk["piece"] not in carry["pieces"]:
            continue
        cand = np.where(~held & ~far)[0]
        if len(cand):
            tacks.append((int(v), int(cand[np.argmin(np.linalg.norm(start[cand] - start[v], axis=1))])))
    idx = np.where(held if press else (held & ~flaps) | far)[0]
    poses = np.stack([at(a)[idx] for a in (0.25, 0.5, 0.75, 1.0)]) if press else start[idx][None]
    return {"start": start, "drape": Vd, "idx": idx, "poses": poses, "info": info, "pieces": list(carry["pieces"]),
            "release": np.where(flaps)[0], "made": V, "rest_idx": np.where(held)[0],
            "tacks": np.asarray(tacks, np.int64).reshape(-1, 2)}


def _crossing_verts(X: np.ndarray, M: dict) -> np.ndarray:
    """Vertices of the edges and triangles that pass through each other in X (pairs joined by a seam or stitch
    vertex left out). Bool per vertex."""
    Eh, Th = _crossing_hits(X, M)
    out = np.zeros(len(X), bool)
    out[Eh.ravel()] = True
    out[Th.ravel()] = True
    return out


def _weld_clear(V: np.ndarray, V_sim: np.ndarray, M: dict, stiff: np.ndarray | None, rounds: int = 4) -> tuple[np.ndarray, int]:
    """The clean-up's surface with the crossings its weld made taken out WITHOUT undoing the weld. A solver leaves
    layers a contact gap apart (a made collar's fall on the back neck, a turned lapel on its front: 0.5-1.6 mm), and a
    seam vertex welded 1-5 mm to its partner went through the layer lying on it by a fraction of a mm; sending those
    places back to the sim's surface (the old answer, two rings wide) reopened every seam beside a collar: its neck
    and gorge seam, the shoulder seams' ends, the top of the centre back seam ("stitches super visible"). Here each
    vertex whose move made a crossing loses the part of its move ALONG THE NORMAL of the layer it went through (its
    height over that layer is the sim's again; the closing in the cloth's plane stays), together with the draped
    vertices welded to it. Returns (V, crossing vertices it could not clear: for the caller's revert)."""
    V = V.copy()
    moved = np.linalg.norm(V - V_sim, axis=1) > 1e-7
    if not moved.any():
        return V, 0
    soft = np.ones(len(V), bool) if stiff is None else np.asarray(stiff) < 0.5
    grp = np.arange(len(V))  # weld groups (closed seam pairs)
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    sw = sw[np.linalg.norm(V[sw[:, 0]] - V[sw[:, 1]], axis=1) < 1e-6] if len(sw) else sw
    for _ in range(6):
        if not len(sw):
            break
        m_ = np.minimum(grp[sw[:, 0]], grp[sw[:, 1]])
        np.minimum.at(grp, sw[:, 0], m_)
        np.minimum.at(grp, sw[:, 1], m_)
    Es, Ts = _crossing_hits(V_sim, M)
    was = set(map(tuple, np.c_[Es, Ts].tolist()))
    left = 0
    for _ in range(rounds):
        Eh, Th = _crossing_hits(V, M)
        new = np.array([tuple(r) not in was for r in np.c_[Eh, Th].tolist()], bool) if len(Eh) else np.zeros(0, bool)
        Eh, Th = Eh[new], Th[new]
        left = len(Eh)
        if not left:
            break
        corr, cnt = np.zeros_like(V), np.zeros(len(V))
        for e, tr in zip(Eh, Th):
            n = np.cross(V_sim[tr[1]] - V_sim[tr[0]], V_sim[tr[2]] - V_sim[tr[0]])
            n /= np.linalg.norm(n) + 1e-12
            for v in list(e) + list(tr):
                if moved[v] and soft[v]:
                    corr[v] -= ((V[v] - V_sim[v]) @ n) * n
                    cnt[v] += 1
        hit = cnt > 0
        if not hit.any():
            break
        corr[hit] /= cnt[hit][:, None]
        # one correction per weld group (its draped members stay together)
        g_ = grp[hit]
        acc = {}
        for v, g in zip(np.where(hit)[0], g_):
            acc.setdefault(int(g), []).append(corr[v])
        for g, cs in acc.items():
            mem = np.where((grp == g) & soft & moved)[0]
            V[mem] += np.mean(cs, axis=0)
    if left:
        Eh, Th = _crossing_hits(V, M)
        left = int(sum(tuple(r) not in was for r in np.c_[Eh, Th].tolist()))
    return V, left


def _crossing_hits(X: np.ndarray, M: dict) -> tuple[np.ndarray, np.ndarray]:
    """(edges (k, 2), triangles (k, 3)) of X that pass through each other (pairs joined by a seam or stitch vertex
    left out)."""
    F = M["F"]
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    cen = X[F].mean(1)
    rad = np.max(np.linalg.norm(X[F] - cen[:, None], axis=2), axis=1)
    mid = 0.5 * (X[E[:, 0]] + X[E[:, 1]])
    half = 0.5 * np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
    cand = cKDTree(cen).query_ball_point(mid, r=half + float(np.percentile(rad, 99)), return_sorted=False)
    ei = np.repeat(np.arange(len(E)), [len(c) for c in cand])
    ti = np.fromiter((t for c in cand for t in c), dtype=np.int64, count=len(ei))
    grp = np.arange(len(X))  # seam partners count as one vertex
    links = np.r_[M["sew"], M["stitch"]] if len(M["stitch"]) else M["sew"]
    for _ in range(4):
        if not len(links):
            break
        m = np.minimum(grp[links[:, 0]], grp[links[:, 1]])
        np.minimum.at(grp, links[:, 0], m)
        np.minimum.at(grp, links[:, 1], m)
    gT = grp[F[ti]]
    keep = ~((gT == grp[E[ei, 0]][:, None]).any(1) | (gT == grp[E[ei, 1]][:, None]).any(1))
    ei, ti = ei[keep], ti[keep]
    T = F[ti]
    hit = _seg_tri(X[E[ei, 0]], X[E[ei, 1]], X[T[:, 0]], X[T[:, 1]], X[T[:, 2]])
    return E[ei[hit]], T[hit]


def _layer_crossing_verts(X: np.ndarray, F: np.ndarray, U: np.ndarray, FU: np.ndarray) -> np.ndarray:
    """Vertices of X (faces F) in a crossing with another mesh U (faces FU): ends of X's edges through U's triangles
    and corners of X's triangles that U's edges pass through (a garment against the one worn under it)."""
    out = np.zeros(len(X), bool)
    if not len(FU):
        return out
    for (V1, F1), (V2, F2), mine in (((X, F), (U, FU), "edge"), ((U, FU), (X, F), "tri")):
        E = np.unique(np.sort(np.r_[F1[:, [0, 1]], F1[:, [1, 2]], F1[:, [2, 0]]], 1), axis=0)
        cen = V2[F2].mean(1)
        rad = np.max(np.linalg.norm(V2[F2] - cen[:, None], axis=2), axis=1)
        mid = 0.5 * (V1[E[:, 0]] + V1[E[:, 1]])
        half = 0.5 * np.linalg.norm(V1[E[:, 0]] - V1[E[:, 1]], axis=1)
        cand = cKDTree(cen).query_ball_point(mid, r=half + float(np.percentile(rad, 99)), return_sorted=False)
        ei = np.repeat(np.arange(len(E)), [len(c) for c in cand])
        ti = np.fromiter((t for c in cand for t in c), dtype=np.int64, count=len(ei))
        if not len(ei):
            continue
        T = F2[ti]
        hit = _seg_tri(V1[E[ei, 0]], V1[E[ei, 1]], V2[T[:, 0]], V2[T[:, 1]], V2[T[:, 2]])
        if mine == "edge":
            out[E[ei[hit]].ravel()] = True
        else:
            out[T[hit].ravel()] = True
    return out


def _untangle(V: np.ndarray, M: dict, free: np.ndarray, rounds: int = 10, reshape: bool = False) -> tuple[np.ndarray, list]:
    """V with the places where its cloth passes through itself smoothed out: the crossing edges' and triangles' free
    vertices and a ring round them relaxed toward their neighbours, until nothing crosses (or `rounds`). A carried
    coarse drape crosses itself in a few places beside folded seams, and a contact solver keeps what it starts with.
    reshape: the smoothed patch is then drawn back toward its pattern shape (_relax_strain, UNTANGLE_STRAIN) as far as
    that makes no new crossing: uniform smoothing evens edge lengths, and where fold rows run 2.5 mm apart beside 8 mm
    edges (a shirt's front band and its open-neck roll) it stretched those triangles 2.7x (the fine settle's start).
    Returns (V, crossing vertices per round)."""
    V = V.copy()
    V_in = V.copy()
    A_, B_ = _graph(M)
    hist = []
    def crossing(X):
        # (only crossings the free cloth takes part in: two held pieces through each other (a made collar's ends in
        # its stand) can't be untangled by moving the cloth round them, and smoothing toward them over the seam
        # pulled the shirt's front neckline 20 mm and stretched its fold rows 3x: ga_suit's fine-settle start)
        Eh, Th = _crossing_hits(X, M)
        out = np.zeros(len(X), bool)
        if len(Eh):
            mine = free[Eh].any(1) | free[Th].any(1)
            out[Eh[mine].ravel()] = True
            out[Th[mine].ravel()] = True
        return out

    for r in range(rounds):
        bad = crossing(V)
        hist.append(int(bad.sum()))
        if not bad.any():
            break
        for _ in range(1 + r // 3):  # a ring round them (more as rounds go by)
            g = bad.copy()
            g[A_[bad[B_]]] = True
            g[B_[bad[A_]]] = True
            bad = g
        mv = bad & free
        for _ in range(4):
            acc, wt = np.zeros_like(V), np.zeros(len(V))
            np.add.at(acc, A_, V[B_])
            np.add.at(wt, A_, 1.0)
            np.add.at(acc, B_, V[A_])
            np.add.at(wt, B_, 1.0)
            V[mv] = 0.5 * V[mv] + 0.5 * (acc[mv] / np.maximum(wt[mv], 1)[:, None])
    if reshape and len(hist) > 1:
        touched = (np.linalg.norm(V - V_in, axis=1) > 1e-7) & free
        g = touched.copy()
        g[A_[touched[B_]]] = True
        g[B_[touched[A_]]] = True
        before = crossing(V)
        mv_ = g & free
        W = V
        for _k in range(5):  # (kept away from the crossings it would make: those vertices held, the rest reshaped again)
            W = _relax_strain(V, M, mv_, UNTANGLE_STRAIN, iters=200)
            new_ = crossing(W) & ~before
            if not new_.any():
                break
            for _ in range(1 + _k):
                gg = new_.copy()
                gg[A_[new_[B_]]] = True
                gg[B_[new_[A_]]] = True
                new_ = gg
            mv_ = mv_ & ~new_
        else:
            W = V
        V = W
        hist.append(int(crossing(V).sum()))
    return V, hist


UNTANGLE_STRAIN = 0.05  # the stretch an untangled patch is drawn back under (_untangle reshape)


def _relax_stretch(V: np.ndarray, M: dict, free: np.ndarray, limit: float = 0.02, iters: int = 60) -> np.ndarray:
    """V with the edges of its `free` vertices no longer than (1 + limit) x their pattern length: position-based
    (each long edge's ends drawn together, Jacobi-averaged), other vertices fixed. Compression is left alone (it is
    where folds belong)."""
    F, uv = M["F"], M["uv"]
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    E = E[free[E].any(1)]
    L0 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1) * (1 + limit)
    V = V.copy()
    wa, wb = free[E[:, 0]].astype(float), free[E[:, 1]].astype(float)
    ws = np.maximum(wa + wb, 1e-9)
    for _ in range(iters):
        d = V[E[:, 1]] - V[E[:, 0]]
        L = np.maximum(np.linalg.norm(d, axis=1), 1e-12)
        ex = np.maximum(L - L0, 0.0)
        if ex.max() < 1e-5:
            break
        c = (ex / L)[:, None] * d
        acc = np.zeros_like(V)
        cnt = np.zeros(len(V))
        on = ex > 0
        np.add.at(acc, E[on, 0], c[on] * (wa / ws)[on, None])
        np.add.at(acc, E[on, 1], -c[on] * (wb / ws)[on, None])
        np.add.at(cnt, E[on, 0], 1.0)
        np.add.at(cnt, E[on, 1], 1.0)
        V += acc / np.maximum(cnt, 1.0)[:, None]
    return V


def _relax_strain(V: np.ndarray, M: dict, free: np.ndarray, limit: float = 0.03, iters: int = 80) -> np.ndarray:
    """V with every triangle of its `free` vertices stretched at most (1 + limit) in ANY direction from the pattern:
    each over-stretched triangle's deformation has its singular values clamped (compression left alone) and its
    vertices are drawn toward that shape about their centroid (Jacobi-averaged, other vertices fixed). An edge-length
    limit can't see shear: a tube that narrows down a leg leaned its columns 0.1-0.2 against its rows, every edge
    within 5% and the triangles 9-12% stretched along the diagonal (a strain-limited solver starts under 5%)."""
    F, uv = M["F"], M["uv"]
    F = F[free[F].any(1)]
    if not len(F):
        return V
    V = V.copy()
    a, b, c = uv[F[:, 0]], uv[F[:, 1]], uv[F[:, 2]]
    Dm = np.stack([b - a, c - a], -1)
    det = Dm[:, 0, 0] * Dm[:, 1, 1] - Dm[:, 0, 1] * Dm[:, 1, 0]
    ok = np.abs(det) > 1e-14
    F, Dm, det = F[ok], Dm[ok], det[ok]
    inv = np.empty_like(Dm)
    inv[:, 0, 0], inv[:, 0, 1] = Dm[:, 1, 1] / det, -Dm[:, 0, 1] / det
    inv[:, 1, 0], inv[:, 1, 1] = -Dm[:, 1, 0] / det, Dm[:, 0, 0] / det
    U3 = np.stack([uv[F[:, 0]], uv[F[:, 1]], uv[F[:, 2]]], 1)
    U3 = U3 - U3.mean(1, keepdims=True)  # (f, 3, 2) the pattern triangle about its centroid
    wv = free.astype(float)
    for _ in range(iters):
        Ds = np.stack([V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]], -1)
        G = Ds @ inv  # (f, 3, 2)
        Uq, S, Vt = np.linalg.svd(G, full_matrices=False)
        hot = S[:, 0] > 1 + limit
        if not hot.any():
            break
        S2 = np.minimum(S[hot], 1 + limit)
        G2 = Uq[hot] @ (S2[:, :, None] * Vt[hot])
        X3 = V[F[hot]]
        tgt = X3.mean(1, keepdims=True) + np.einsum("fij,fkj->fki", G2, U3[hot])
        acc = np.zeros_like(V)
        cnt = np.zeros(len(V))
        for k in range(3):
            np.add.at(acc, F[hot, k], tgt[:, k] - X3[:, k])
            np.add.at(cnt, F[hot, k], 1.0)
        V += wv[:, None] * acc / np.maximum(cnt, 1.0)[:, None]
    return V


CLEAR_GROW = 0.004  # m a vertex's gap may grow past the asked one to clear its faces (_clear_of_body in _press_plan)


def _clear_of_body(V: np.ndarray, F: np.ndarray, free: np.ndarray, body: "Body", gap: float, face_gap: float,
                   grow: float | None = None) -> np.ndarray:
    """V with its `free` vertices at least `gap` off the body and every face they are in at least `face_gap` off it
    (centres and edge midpoints: a triangle's chord reaches in between its vertices; a contact solver refuses a start
    inside its standoff)."""
    V = V.copy()
    gaps = np.where(free, gap, 0.0)
    X0 = V.copy()
    Ff = F[free[F].any(1)]
    for _ in range(6):
        V[free] = body.push_out(X0[free], gaps[free])
        Pf = np.concatenate([V[Ff].mean(1), 0.5 * (V[Ff[:, 0]] + V[Ff[:, 1]]), 0.5 * (V[Ff[:, 1]] + V[Ff[:, 2]]),
                             0.5 * (V[Ff[:, 2]] + V[Ff[:, 0]])])
        short = face_gap - body.clearance(Pf)
        if short.max() <= 2e-4:
            break
        fi = np.tile(np.arange(len(Ff)), 4)
        need = np.zeros(len(V))
        for c in range(3):
            np.maximum.at(need, Ff[fi, c], np.maximum(short, 0))
        # (`grow` caps the extra a vertex takes for its faces (the fine settle's start: CLEAR_GROW): in a hollow (the crotch, between the thighs) pushing a vertex
        # along the body's normal doesn't clear its faces, and a gap grown round after round sent fork tips 35-80 mm
        # across the body: a 10x stretched start; what is left is the exact pass's below)
        gaps = np.minimum(gaps + np.where(free, need + 2e-4 * (need > 0), 0.0), np.where(free, gap + (np.inf if grow is None else grow), 0.0))
    # exactly, the other way round: no body vertex within face_gap of a cloth face (the sampled clearance reads the
    # body by its nearest vertices' planes; a body vertex 1.6-1.9 mm under the middle of a sleeve's triangle stopped
    # the solver at its first step)
    vn, _ = body.normals()
    # (with the body's edge midpoints: an edge of the body 1.9 mm from an edge of the cloth, both ends of each
    # further off, stopped the solver the same way: "edge-edge pair's separation has collapsed")
    bT = body.T
    bE = np.unique(np.sort(np.r_[bT[:, [0, 1]], bT[:, [1, 2]], bT[:, [2, 0]]], 1), axis=0)
    BP = np.r_[body.V, 0.5 * (body.V[bE[:, 0]] + body.V[bE[:, 1]])]
    BN = np.r_[vn, vn[bE[:, 0]] + vn[bE[:, 1]]]
    BN /= np.maximum(np.linalg.norm(BN, axis=1, keepdims=True), 1e-12)
    near_ = cKDTree(V[free]).query(BP, distance_upper_bound=0.05)[0] < 0.05 if free.any() else np.zeros(len(BP), bool)
    BP, vn = BP[near_], BN[near_]
    for _ in range(4):
        if not len(BP):
            break
        tc = cKDTree(V[Ff].mean(1))
        _, nb = tc.query(BP, k=min(12, len(Ff)))
        nb = nb.reshape(len(BP), -1)
        push = np.zeros(len(V))
        dirs = np.zeros_like(V)
        for k in range(nb.shape[1]):
            T = Ff[nb[:, k]]
            dd = _pt_tri(BP, V[T[:, 0]], V[T[:, 1]], V[T[:, 2]])
            bad = np.where(dd < face_gap)[0]
            for c in range(3):
                np.maximum.at(push, T[bad, c], face_gap - dd[bad] + 3e-4)
                np.add.at(dirs, T[bad, c], vn[bad])
        mv = (push > 0) & free
        if not mv.any():
            break
        dirs[mv] /= np.maximum(np.linalg.norm(dirs[mv], axis=1, keepdims=True), 1e-12)
        V[mv] += dirs[mv] * push[mv, None]
    return V


def _start_separation(V: np.ndarray, F: np.ndarray, bV: np.ndarray, bT: np.ndarray) -> float:
    """The least distance between the cloth and its collider at the start (m), both ways: the collider's vertices
    and three points along each of its edges against the cloth's triangles, and the cloth's against the
    collider's (an edge-edge approach lies between the vertices of both)."""
    def pts(Vx, Fx):
        E = np.unique(np.sort(np.r_[Fx[:, [0, 1]], Fx[:, [1, 2]], Fx[:, [2, 0]]], 1), axis=0)
        return np.concatenate([Vx] + [Vx[E[:, 0]] + t * (Vx[E[:, 1]] - Vx[E[:, 0]]) for t in (0.25, 0.5, 0.75)])
    best = np.inf
    for (Va, Fa), (Vb, Fb) in (((bV, bT), (V, F)), ((V, F), (bV, bT))):
        P = pts(np.asarray(Va, float), np.asarray(Fa, np.int64))
        Vb, Fb = np.asarray(Vb, float), np.asarray(Fb, np.int64)
        cen = Vb[Fb].mean(1)
        tree = cKDTree(cen)
        d0, _ = tree.query(P)
        P = P[d0 < 0.03]  # (only what is near: the rest can't be the minimum)
        if not len(P):
            continue
        _, nb = tree.query(P, k=min(10, len(Fb)))
        nb = nb.reshape(len(P), -1)
        for k in range(nb.shape[1]):
            T = Fb[nb[:, k]]
            best = min(best, float(_pt_tri(P, Vb[T[:, 0]], Vb[T[:, 1]], Vb[T[:, 2]]).min()))
    return float(best)


EXACT_GAP = 0.003  # m: a smooth (contact-solver) start's cloth stands at least this far off the collider's triangles
MADE_LIFT = 0.015  # m: the most a made piece's vertex is lifted over the garment under it at the start (_lift_made)


def _lift_made(X: np.ndarray, M: dict, made: np.ndarray, body: "Body", padded: "Body", gap: float = EXACT_GAP) -> tuple[np.ndarray, int]:
    """A layered garment's MADE pieces (a jacket's collar: laid by construction, held and carried, never cleared)
    lifted over the garment under them where they start under or in it: along the body's normal to the padded body's
    height there (`padded.pad`: how far out the under garment lies over each body vertex) + `gap`, at most MADE_LIFT,
    the lift evened over the piece's own mesh so it stays a smooth surface. Laid on the body without the under
    garment's neck pieces, a jacket collar's side passed through an open shirt collar's wing at the neck's side (10
    edges; a held piece in contact that cannot yield: "newton stalled" at frame 0, om_05)."""
    pad = getattr(padded, "pad", None)
    idx = np.where(made)[0]
    if pad is None or not len(idx):
        return X, 0
    vn, tree = body.normals()
    d, j = tree.query(X[idx])
    h = ((X[idx] - body.V[j]) * vn[j]).sum(1)
    lift = np.clip(pad[j] + gap - h, 0.0, MADE_LIFT)
    lift[d > 0.06] = 0.0
    if not (lift > 1e-5).any():
        return X, 0
    # evened over the made pieces' own edges (a vertex is lifted at least by what it needs)
    L = np.zeros(len(X))
    L[idx] = lift
    F = M["F"]
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    E = E[made[E].all(1)]
    for _ in range(4):
        acc, wt = L.copy(), np.ones(len(X))
        np.add.at(acc, E[:, 0], L[E[:, 1]])
        np.add.at(wt, E[:, 0], 1.0)
        np.add.at(acc, E[:, 1], L[E[:, 0]])
        np.add.at(wt, E[:, 1], 1.0)
        Ls = acc / wt
        L[idx] = np.maximum(Ls[idx], lift)
    X = X.copy()
    X[idx] += L[idx][:, None] * vn[j]
    return X, int((L[idx] > 1e-5).sum())


def _clear_exact(X: np.ndarray, F: np.ndarray, free: np.ndarray, bV: np.ndarray, bT: np.ndarray, gap: float = EXACT_GAP,
                 rounds: int = 6, signed: int | None = None) -> tuple[np.ndarray, int]:
    """A start's free cloth moved off the collider EXACTLY: the cloth's vertices and three points along each of its
    edges against the collider's triangles (nearest centres), each one closer than `gap` moved out along the
    triangle's outward normal (its vertices sharing the move), a few rounds. Body.clearance (nearest vertices'
    planes) over-reads by up to 5 mm where the collider is coarse or turns (an elbow under a pressed shirt sleeve): a
    top sleeve's seam edge there started 1.8 mm from a collider edge and ZOZO stopped at frame 0, "contact starts
    overlapping" (ga_suit su_80). The first `signed` triangles (default all) are a closed body's, wound outward: a
    point under one is moved out through it; the rest (an under garment's cloth, wound as its pattern lies) push a
    point away on the side it is on. (X, how many vertices moved)."""
    bV, bT = np.asarray(bV, float), np.asarray(bT, np.int64)
    if not len(bT) or not free.any():
        return X, 0
    from .rig_template import _closest_on_triangles
    X = X.copy()
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    E = E[free[E].any(1)]
    fn = np.cross(bV[bT[:, 1]] - bV[bT[:, 0]], bV[bT[:, 2]] - bV[bT[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1), 1e-12)[:, None]
    cen = bV[bT].mean(1)
    tree = cKDTree(cen)
    r_t = float(np.percentile(np.linalg.norm(bV[bT[:, 0]] - cen, axis=1), 95))
    vi = np.where(free)[0]
    ia = np.r_[vi, E[:, 0], E[:, 0], E[:, 0]]
    ib = np.r_[vi, E[:, 1], E[:, 1], E[:, 1]]
    tt = np.r_[np.zeros(len(vi)), np.full(len(E), 0.25), np.full(len(E), 0.5), np.full(len(E), 0.75)]
    moved = np.zeros(len(X), bool)
    # the other way round too: the collider's vertices and edge middles against the CLOTH's triangles (a 2 cm cloth
    # triangle's middle dips under a finer collider's ridge with all its own vertices and edge points clear: a shirt
    # placket under a jacket front, least separation 0.013 mm, "newton stalled" at frame 0: om_05)
    lo_, hi_ = X[free].min(0) - 0.03, X[free].max(0) + 0.03
    bE = np.unique(np.sort(np.r_[bT[:, [0, 1]], bT[:, [1, 2]], bT[:, [2, 0]]], 1), axis=0)
    Cs = np.r_[bV, 0.5 * (bV[bE[:, 0]] + bV[bE[:, 1]])]
    Cs = Cs[np.all((Cs > lo_) & (Cs < hi_), 1)]
    Ff = F[free[F].any(1)]
    for _ in range(rounds):
        any_ = False
        if len(Cs) and len(Ff):
            cc = X[Ff].mean(1)
            rr = float(np.percentile(np.linalg.norm(X[Ff[:, 0]] - cc, axis=1), 95))
            tc = cKDTree(cc)
            d0c, _ = tc.query(Cs)
            nc = np.where(d0c < gap + rr)[0]
            if len(nc):
                _, nbc = tc.query(Cs[nc], k=min(8, len(Ff)))
                nbc = nbc.reshape(len(nc), -1)
                mvc = np.zeros_like(X)
                lnc = np.zeros(len(X))
                for k in range(nbc.shape[1]):
                    T = Ff[nbc[:, k]]
                    bary, d = _closest_on_triangles(Cs[nc], X[T[:, 0]], X[T[:, 1]], X[T[:, 2]])
                    hitc = d < gap
                    if not hitc.any():
                        continue
                    Q = bary[:, :1] * X[T[:, 0]] + bary[:, 1:2] * X[T[:, 1]] + bary[:, 2:] * X[T[:, 2]]
                    away = Q - Cs[nc]
                    nrm = np.cross(X[T[:, 1]] - X[T[:, 0]], X[T[:, 2]] - X[T[:, 0]])
                    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
                    # (the side the collider point is on: away from it; on the surface itself, along the cloth's
                    # normal, whichever way the triangle's own middle lies from the collider's nearest centre)
                    dirn = np.where((d > 3e-4)[:, None], away / np.maximum(d, 1e-9)[:, None], nrm)
                    amt = (gap - d)[hitc]
                    for c_ in range(3):
                        vi_ = T[hitc, c_]
                        better = amt > lnc[vi_]
                        mvc[vi_[better]] = dirn[hitc][better] * amt[better][:, None]
                        lnc[vi_[better]] = amt[better]
                mvc[~free] = 0.0
                if np.linalg.norm(mvc, axis=1).max() > 1e-6:
                    any_ = True
                    moved |= np.linalg.norm(mvc, axis=1) > 1e-6
                    X += mvc * 1.05
        P = X[ia] * (1 - tt)[:, None] + X[ib] * tt[:, None]
        d0, _ = tree.query(P)
        near = np.where(d0 < gap + r_t)[0]
        if not len(near):
            if any_:
                continue
            break
        _, nb = tree.query(P[near], k=min(12, len(bT)))
        nb = nb.reshape(len(near), -1)
        best = np.full(len(near), np.inf)
        push = np.zeros((len(near), 3))
        for k in range(nb.shape[1]):
            T = bT[nb[:, k]]
            bary, d = _closest_on_triangles(P[near], bV[T[:, 0]], bV[T[:, 1]], bV[T[:, 2]])
            Q = bary[:, :1] * bV[T[:, 0]] + bary[:, 1:2] * bV[T[:, 1]] + bary[:, 2:] * bV[T[:, 2]]
            n = fn[nb[:, k]]
            sd = ((P[near] - Q) * n).sum(1)
            if signed is not None:  # (cloth triangles: away on the point's own side)
                two = nb[:, k] >= signed
                away = (P[near] - Q) / np.maximum(d, 1e-9)[:, None]
                n = np.where((two & (d > 3e-4))[:, None], away, np.where((two & (sd < 0))[:, None], -n, n))
                sd = np.where(two, np.abs(sd), sd)
            # (under the triangle's plane = inside the collider: out through it and the gap beyond)
            need = np.where(sd >= 0, gap - d, gap + d)
            better = d < best
            best = np.where(better, d, best)
            push = np.where(better[:, None], n * np.maximum(need, 0.0)[:, None], push)
        hit = best < gap
        if not hit.any():
            if any_:
                continue
            break
        mv = np.zeros_like(X)
        # (each vertex takes the largest move any of its samples asks for)
        idx = np.r_[ia[near][hit], ib[near][hit]]
        cand = np.r_[push[hit], push[hit]]
        order = np.argsort(np.linalg.norm(cand, axis=1))
        mv[idx[order]] = cand[order]
        mv[~free] = 0.0
        if not np.linalg.norm(mv, axis=1).max() > 1e-6:
            if any_:
                continue
            break
        moved |= np.linalg.norm(mv, axis=1) > 1e-6
        X += mv * 1.05
    return X, int(moved.sum())


def _pt_tri(P: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray) -> np.ndarray:
    """Distances from points P to triangles (A, B, C), row by row (clamped barycentric: exact inside, close at the
    edges)."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    d00, d01, d11 = (ab * ab).sum(1), (ab * ac).sum(1), (ac * ac).sum(1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) > 1e-18, d00 * d11 - d01 * d01, 1e-18)
    v = np.clip((d11 * d1 - d01 * d2) / den, 0, 1)
    w = np.clip((d00 * d2 - d01 * d1) / den, 0, 1)
    sm = v + w
    over = sm > 1
    v[over] /= sm[over]
    w[over] /= sm[over]
    return np.linalg.norm(P - (A + v[:, None] * ab + w[:, None] * ac), axis=1)


def _constructed(Bp: dict, Ms: dict, Xs: np.ndarray, Vc: np.ndarray, M: dict, Xf: np.ndarray, carry: dict,
                 body: "Body") -> tuple:
    """Method "settle"'s result on the fine mesh M without a fine sim: the loose cloth is the coarse drape Vc carried
    over (transfer); each made piece is its own fine placement Xf (crisp folds, layers nearly touching) set where the
    coarse one was held (the fine placement fitted rigidly to the coarse one's, then the body's move), and the loose
    cloth's seam vertices are drawn onto the made edges they are sewn to. Returns (V, the plain carried drape (the
    fine folds are read from it), {"pieces", "seam_mm": how far the loose seams were drawn, median / max})."""
    Vd = transfer(Ms, Vc, M)
    V = Vd.copy()
    Xc_on_f = transfer(Ms, Xs, M)
    dbg = (lambda tag, W: print(f"construct {tag}: {integrity(W, M, Bp, Xf)['self_intersections']} crossings", flush=True)) \
        if os.environ.get("HIFIPUSHIE_CLOTH_DEBUG") else (lambda tag, W: None)
    dbg("carried", V)
    held = np.zeros(len(V), bool)
    for nm in carry["pieces"]:
        sel = M["piece"] == M["names"].index(nm)
        # the fine placement onto the coarse one (they agree to a mm or two), fitted on the group's root (made pieces
        # sewn to each other are one construction: a collar fitted by itself, its fall turned a little differently
        # at the two mesh sizes, landed 16-25 mm off its stand all round, the seam between them open at every pair)
        rsel = M["piece"] == M["names"].index((carry.get("roots") or {}).get(nm, nm))
        R0, t0 = _kabsch(Xf[rsel], Xc_on_f[rsel])
        R1, t1 = carry["moves"][nm]
        V[sel] = (Xf[sel] @ R0.T + t0) @ R1.T + t1
        held[sel] = True
    dbg("made pieces set", V)
    # a fold's flap lies on the cloth that has arrived under it (the shirt under a collar's fall)
    from . import folds as foldmod
    faces = Bp.get("faces") or {}
    info = {}
    F, pid = M["F"], M["piece"]
    loose_t = F[~held[F].any(1)]
    for fd in M.get("folds") or []:
        if fd["piece"] not in carry["pieces"] or fd["turn"] <= 0:
            continue
        obs = [foldmod.samples(V, loose_t, 1.0)[:1] + (_out_normals(V, loose_t, body),)]
        k = len(fd["rows"])
        # from where it was made: a little further down if nothing is under it, back up where the cloth is in the way
        V, info[fd["name"]] = _relay(V, M, fd, faces.get(fd["piece"], 1.0), obs)
    dbg("flaps laid", V)
    V = _tuck(V, M, held, body)
    dbg("tucked", V)
    sew = M["sew"]
    a, b = sew[:, 0], sew[:, 1]
    d_all = []
    for src, dst in ((a, b), (b, a)):
        m = held[src] & ~held[dst]
        d_all.append(np.linalg.norm(V[src[m]] - V[dst[m]], axis=1))
        V[dst[m]] = V[src[m]]
    d_all = np.concatenate(d_all) if d_all else np.zeros(0)
    # the pull spread into the loose cloth beside the seam (smoothed displacement over a few rings)
    moved = V - Vd
    A_, B_ = _graph(M)
    fixed = held | (np.linalg.norm(moved, axis=1) > 0)
    D = moved.copy()
    reach = np.zeros(len(V))
    reach[fixed] = 1.0
    for _ in range(8):
        acc, wt = np.zeros_like(D), np.zeros(len(V))
        np.add.at(acc, A_, D[B_])
        np.add.at(wt, A_, 1.0)
        np.add.at(acc, B_, D[A_])
        np.add.at(wt, B_, 1.0)
        D2 = acc / np.maximum(wt, 1)[:, None]
        D = np.where(fixed[:, None], D, 0.85 * D2)
    V = np.where(fixed[:, None], V, Vd + D)
    dbg("seams drawn", V)
    V = _tuck(V, M, held, body)
    dbg("tucked again", V)
    return V, Vd, {"pieces": list(carry["pieces"]), "folds": info,
                   "seam_mm": [round(float(np.median(d_all)) * 1000, 1), round(float(d_all.max()) * 1000, 1)] if len(d_all) else None}


def _tuck(V: np.ndarray, M: dict, held: np.ndarray, body: "Body", lay: float | None = None) -> np.ndarray:
    """Loose cloth that pokes out through a made piece's turned-over flap (a shirt's shoulder through its collar's
    fall) is tucked back under it: moved in along the flap's normal to `lay` under. The made pieces don't move."""
    from . import folds as foldmod
    lay = FOLD_LAY if lay is None else lay
    V = V.copy()
    names = M["names"]
    for fd in M.get("folds") or []:
        k = names.index(fd["piece"])
        if fd["turn"] <= 0 or not held[M["piece"] == k].all():
            continue
        g = foldmod._geom(M, fd)
        Tf = g["tris"][g["flap0"][g["tris"]].all(1)]
        if not len(Tf):
            continue
        hm = float(np.median(np.linalg.norm(V[Tf[:, 0]] - V[Tf[:, 1]], axis=1)))
        loose = np.where(~held)[0]
        for _ in range(3):
            P = foldmod.samples(V, Tf, 1.0)[0]
            N = _out_normals(V, Tf, body)
            d, i = cKDTree(P).query(V[loose])
            sd = ((V[loose] - P[i]) * N[i]).sum(1)
            tang = np.sqrt(np.maximum(d * d - sd * sd, 0.0))
            bad = (tang < 0.45 * hm) & (sd > -lay) & (sd < 0.015)
            if not bad.any():
                break
            V[loose[bad]] -= (sd[bad] + lay)[:, None] * N[i[bad]]
    return V


def _out_normals(V: np.ndarray, T: np.ndarray, body: "Body") -> np.ndarray:
    """Normals of folds.samples(V, T) turned away from the body."""
    from . import folds as foldmod
    P, N = foldmod.samples(V, T, 1.0)
    if not len(P) or not len(body.V):
        return N
    s = np.sign(body.clearance(P + 0.004 * N) - body.clearance(P - 0.004 * N))
    return N * np.where(s == 0, 1.0, s)[:, None]


def _relay(V: np.ndarray, M: dict, fd: dict, face: float, obs: list) -> tuple:
    """A made fold's flap laid again on what is under it now: turned back to open by up to 40 deg where cloth is in the
    way, on down toward the full turn where nothing is."""
    from . import folds as foldmod
    cur = foldmod.measure(V, M, fd, face).get("turn_deg", 170.0)
    k = len(fd["rows"])
    full = abs(math.degrees(fd["turn"])) * k
    # folds.apply turns by t x the fold's turn from the state it is given: here from the made fold
    t_hi = max(0.0, (178.0 - cur) / full)
    Vn, info = foldmod.apply(V, M, fd, face, obs, FOLD_LAY, t_max=t_hi, t_min=-RELAY_OPEN / full, steps=30, own_base=True,
                             wedge=0.03)  # (nothing simulates this: the layers as near as cloth lies)
    info["was_deg"] = cur
    info.pop("_tv", None)
    return Vn, info


SUPPORTS = {
    # a shoulder pad: thickest at the shoulder's edge, thinning to nothing toward the neck over `reach` m of the
    # shoulder line, `width` m front to back, running `past` m beyond the shoulder point (the sleeve head it holds out)
    "shoulder_pad": {"thickness": 0.008, "reach": 0.11, "width": 0.07, "past": 0.012},
    # a sleeve-head roll: a soft ridge just past the shoulder point that holds the top of the sleeve cap out
    "sleeve_head": {"thickness": 0.005, "reach": 0.02, "width": 0.06, "past": 0.03},
}


def supports(body: "Body", spec: list | None) -> "Body | None":
    """The body with a garment's support pieces on it (garment key `support`: [{"kind": "shoulder_pad" |
    "sleeve_head", ...its numbers}] or just the kind names): each a pad grown along the body's normals over the
    shoulder line (hps -> shoulder point and a little past it), both sides. None without supports."""
    if not spec or not body.m.get("at"):
        return None
    at = body.at
    vn, _ = body.normals()
    pad = np.zeros(len(body.V))
    for e in spec:
        e = {"kind": e} if isinstance(e, str) else dict(e)
        if e["kind"] not in SUPPORTS:
            raise ClothError(f"support kind {e['kind']!r} unknown (have {', '.join(SUPPORTS)})")
        o = dict(SUPPORTS[e["kind"]], **{k: v for k, v in e.items() if k != "kind"})
        for sx in (1.0, -1.0):
            h = np.asarray(at["hps.L"], float) * [sx, 1, 1]
            sp = np.asarray(at["shoulder.L"], float) * [sx, 1, 1]
            L = float(np.linalg.norm(sp - h))
            d = (sp - h) / L
            rel = body.V - sp
            u = rel @ d  # along the shoulder line from the shoulder point (+ = past it, down the arm's top)
            off = rel - np.outer(u, d)
            across = np.abs(off[:, 1])  # front to back
            ramp = np.clip((u + o["reach"]) / o["reach"], 0, 1) * np.clip((o["past"] - u) / max(o["past"], 1e-6) + 1, 0, 1)
            ramp = np.where(u > 0, np.clip(1 - u / max(o["past"], 1e-6), 0, 1), ramp)
            w = ramp * np.clip(1 - (across / o["width"]) ** 2, 0, 1)
            up = (vn[:, 2] > 0.25) & (np.abs(off[:, 2]) < 0.05) & (np.sign(body.V[:, 0]) == sx)
            pad = np.maximum(pad, np.where(up, o["thickness"] * w * w * (3 - 2 * w), 0.0))
    if pad.max() <= 0:
        return None
    b = Body({"V": body.V + vn * pad[:, None], "F": body._faces, "J": body.J})
    b.support_pad = pad
    return b


PAD_LATERAL = 0.008  # m: a garment point pads a body vertex when it lies this close to the vertex's normal line
PAD_SLOPE = 1.0  # the padded surface's steepest fall-off (m of pad per m along the body): no overhangs


def worn_body(body: "Body", src: dict, under: dict, air: float = 0.003) -> "Body | None":
    """The body padded by an under garment WITHOUT its neck pieces (pieces wrapped round the neck or laid from a seam:
    a shirt's collar and stand): what a worn top (_worn_top) is laid on. None when the under garment has no such
    pieces."""
    res = under.get("res") or {}
    Mu, Bu = res.get("mesh"), (res.get("pieces") or {}).get("pieces")
    if Mu is None or not Bu:
        return None
    neck = [k for k, nm in enumerate(Mu["names"]) if (Bu.get(nm) or {}).get("wrap", {}).get("to") in ("neck", "seam")]
    if not neck:
        return None
    U = np.asarray(under["V"], float)
    if len(U) != len(Mu["piece"]):
        return None
    # (only what stands round the neck: an open collar's points lie on the chest, under the lapels, and a forepart
    # laid without them landed inside them and was pushed out 11x)
    at = body.at
    if "cf_neck" in at and "cb_neck" in at and "hps.L" in at:
        c = 0.5 * (np.asarray(at["cf_neck"], float) + np.asarray(at["cb_neck"], float))
        rn = abs(float(at["hps.L"][0] - c[0]))
        near = np.hypot(U[:, 0] - c[0], U[:, 1] - c[1]) < rn + WORN_STAND
    else:
        near = np.ones(len(U), bool)
    keep = ~(np.isin(np.asarray(Mu["piece"]), neck) & near)
    b = padded_body(body, src, U[keep], air)
    b._m = body.m
    # the under garment's own body cloth round the neck (its neckline's edge is the top of it): a worn top's back
    # columns behind the neck stop there (_worn_top)
    ring = ~np.isin(np.asarray(Mu["piece"]), neck) & (np.hypot(U[:, 0] - c[0], U[:, 1] - c[1]) < rn + WORN_STAND + 0.02) \
        if "cf_neck" in at and "cb_neck" in at and "hps.L" in at else np.zeros(len(U), bool)
    b.under_top = U[ring] if ring.any() else None
    return b


def padded_body(body: "Body", src: dict, U: np.ndarray, air: float = 0.003) -> "Body":
    """The body grown along its normals to cover the points U (a garment worn on it) plus `air`: what the next
    garment's pieces are placed on and kept clear of. A closed body again, so the tape, the sections and the arm axes
    work on it as on the bare one."""
    vn, tree = body.normals()
    # each body vertex is padded by how far out along ITS OWN normal the garment lies: the garment's points within
    # PAD_LATERAL of the normal's line (by the nearest vertex instead, a shirt collar's fall standing 25 mm off the
    # neck padded the vertices below its edge, a 3 cm shelf at the back neck under the collar the jacket's collar was
    # laid on: su_32, its stand 27 mm off the shirt), then the vertices between those even out
    pad = np.zeros(len(body.V))
    T = body.T
    E = np.unique(np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1), axis=0)
    U = np.asarray(U, float)
    if len(U):
        d, i = tree.query(U, k=48, distance_upper_bound=0.08)
        ok = np.isfinite(d)
        iu = np.broadcast_to(np.arange(len(U))[:, None], i.shape)[ok]
        iv = i[ok]
        rel = U[iu] - body.V[iv]
        h = (rel * vn[iv]).sum(1)
        lat = np.linalg.norm(rel - h[:, None] * vn[iv], axis=1)
        # (and only what lies over that part of the body: the torso's side under a hanging arm is not padded by the
        # sleeve 6 cm off it along its normal: no farther than 1.5x the point's own distance to the body)
        dn = np.broadcast_to(d[:, :1], d.shape)[ok]
        s = (h > 0) & (lat < PAD_LATERAL) & (h < 1.5 * dn + 0.005)
        np.maximum.at(pad, iv[s], np.clip(h[s], 0.0, 0.08))
    # no overhangs: the pad falls off no steeper than PAD_SLOPE from any vertex (under a shirt collar's fall, whose edge
    # stands 25 mm off the neck, the padded surface turned under the lip: the normals there point down, and a jacket
    # stand laid "up the body" from below the lip went down and out, 24 mm off it). What goes over a step bridges it
    Ev = np.linalg.norm(body.V[E[:, 0]] - body.V[E[:, 1]], axis=1) * PAD_SLOPE
    for _ in range(60):
        m_ = pad.copy()
        np.maximum.at(m_, E[:, 0], pad[E[:, 1]] - Ev)
        np.maximum.at(m_, E[:, 1], pad[E[:, 0]] - Ev)
        if np.allclose(m_, pad):
            break
        pad = m_
    covered = pad > 0
    for _ in range(3):
        acc, wt = np.zeros(len(pad)), np.zeros(len(pad))
        np.add.at(acc, E[:, 0], pad[E[:, 1]])
        np.add.at(wt, E[:, 0], 1.0)
        np.add.at(acc, E[:, 1], pad[E[:, 0]])
        np.add.at(wt, E[:, 1], 1.0)
        pad = np.maximum(pad * covered, 0.5 * pad + 0.5 * acc / np.maximum(wt, 1))
    pad = np.where(pad > 1e-4, pad + air, 0.0)
    P = _unfold_offset(body.V, T, E, vn, pad)
    # (with the parts the garment also rests on, garment key "collide": padded for a layer, the trousers lost their
    # shoes and the hem started inside them: "contact starts overlapping", tr_20)
    b = Body({"V": P, "F": body._faces, "J": body.J, "worn": getattr(body, "worn", None)})
    b.pad = pad
    return b


PAD_UNFOLD = 40  # rounds of untangling a padded body's folds (_unfold_offset)


def _unfold_offset(V: np.ndarray, T: np.ndarray, E: np.ndarray, vn: np.ndarray, pad: np.ndarray) -> np.ndarray:
    """V grown by `pad` along its normals vn, with the folds such an offset makes in hollows taken out: where the pad
    is deeper than the hollow is wide (the neck's side under an open shirt collar's point, the armpit) neighbouring
    normals cross, and the padded surface turned over on itself (Garrett: 116 turned faces round the neck, 24 in the
    pits). Faces turned more than ~70 deg from the body's own are smoothed out (their vertices to their neighbours'
    mean, never further in along the normal than their pad): what lies over a hollow bridges it, as cloth does. The
    clearance and push-out read a folded surface's normals backwards (a jacket's gorge vertex 21 mm clear was pushed
    56 mm out across the shirt collar)."""
    P = V + vn * pad[:, None]
    if not (pad > 0).any():
        return P

    def fnorm(Q):
        n = np.cross(Q[T[:, 1]] - Q[T[:, 0]], Q[T[:, 2]] - Q[T[:, 0]])
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    n0 = fnorm(V)
    for _ in range(PAD_UNFOLD):
        bad = (fnorm(P) * n0).sum(1) < 0.35
        if not bad.any():
            break
        mv = np.zeros(len(P), bool)
        mv[T[bad].ravel()] = True
        # (and their neighbours: the fold is a few rings wide)
        nb = np.zeros(len(P), bool)
        nb[E[mv[E[:, 0]], 1]] = True
        nb[E[mv[E[:, 1]], 0]] = True
        mv |= nb
        acc, wt = np.zeros_like(P), np.zeros(len(P))
        np.add.at(acc, E[:, 0], P[E[:, 1]])
        np.add.at(wt, E[:, 0], 1.0)
        np.add.at(acc, E[:, 1], P[E[:, 0]])
        np.add.at(wt, E[:, 1], 1.0)
        Q = acc / np.maximum(wt, 1)[:, None]
        h = ((Q - V) * vn).sum(1)
        Q = Q + vn * np.maximum(pad - h, 0.0)[:, None]  # never in past the pad
        P[mv] = Q[mv]
    return P


UNDER_COLLAR_T = 0.003  # m: a shirt collar as it lies under a jacket's (stand, interfacing, fall over it: pressed)


def under_neckline(res: dict) -> float:
    """The neckline of a finished garment as the next garment goes round it (mm): its neck pieces' (wrap "neck":
    a collar stand, a neckband) edge sewn to its torso pieces, in the pattern; 0 if it has none."""
    M, pcs = res["mesh"], res["pieces"]["pieces"]
    names = M["names"]
    neck = [k for k, nm in enumerate(names) if (pcs.get(nm, {}).get("wrap") or {}).get("to") == "neck"]
    torso = [k for k, nm in enumerate(names) if (pcs.get(nm, {}).get("wrap") or {}).get("to", "torso") == "torso"]
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    best = 0.0
    for k in neck:
        a = np.r_[sw[np.isin(M["piece"][sw[:, 0]], [k]) & np.isin(M["piece"][sw[:, 1]], torso), 0],
                  sw[np.isin(M["piece"][sw[:, 1]], [k]) & np.isin(M["piece"][sw[:, 0]], torso), 1]]
        a = np.unique(a)
        if len(a) < 3:
            continue
        q = M["uv"][a]
        q = q[np.argsort(q[:, 0])]
        best = max(best, float(np.linalg.norm(np.diff(q, axis=0), axis=1).sum()) * 1000.0)
    return best


def waist_hung(g: dict) -> bool:
    """A garment that hangs from the waist by a band (trousers, a skirt): its waist is taped over what is tucked
    into it."""
    pt = (g.get("pattern") or {}) if isinstance(g.get("pattern"), dict) else {}
    return pt.get("block") in ("trouser", "skirt") or pt.get("from") == "skirt_block"


def over_measures(body: "Body", U: np.ndarray, res: dict | None = None, waist: float | None = None) -> tuple[dict, dict]:
    """The tailor's measures for a garment worn OVER another (garment key "over"), U = the under garment as it lies
    under it (pressed), res its result: a jacket is drafted to go round the shirt. `neck` = the under garment's own
    neckline (its collar size: under_neckline) + its collar's thickness (UNDER_COLLAR_T) round, when more than the
    bare neck (drafted from the bare neck, a jacket's collar was shorter than the shirt collar it must go round, and the
    made jacket collar climbed the shirt collar to where it was narrow enough: su_32, 23 mm high, the shirt collar
    hidden. The tape taken round the pressed shirt collar read +123 mm: its fall stands off the stand, and a 108 mm
    neck width followed, against a tailor's ~87 for this collar size); the armhole is lowered by the under garment's
    thickness in the armpit (`waistToArmpit`; drafted for the bare pit the jacket's armhole sat 12 mm under the shirt's
    own and its underarm seams stood 20-60 mm open over the shirt in the pit). The body's girths (chest, waist, hips,
    seat) stay the bare body's: the design's ease bands (and the fit report) are against the body. (mm, info)."""
    mm = dict(body.m["mm"])
    pb = padded_body(body, {}, U, 0.0)
    info = {}
    nl = under_neckline(res) if res is not None else 0.0
    if nl > 0:
        nk = nl + 2 * np.pi * UNDER_COLLAR_T * 1000.0
        if nk > mm.get("neck", 0.0):
            info["neck"] = [round(mm["neck"], 1), round(nk, 1)]
            mm["neck"] = nk
    at = body.at
    if "armpit_z" in at and "shoulder.L" in body.J and "waistToArmpit" in mm:
        sh = np.asarray(body.J["shoulder.L"], float)
        pits = []
        for sx in (1.0, -1.0):
            p = np.array([sx * sh[0], sh[1], float(at["armpit_z"])])
            near = np.linalg.norm(body.V - p, axis=1) < 0.04
            if near.any():
                pits.append(float(np.median(pb.pad[near])))
        if pits:
            t = 1000.0 * float(np.mean(pits))
            info["armpit_mm"] = round(t, 1)
            mm["waistToArmpit"] = mm["waistToArmpit"] - t
    if waist is not None and "waist_z" in at and "waist" in mm:
        # a garment hung from the waist over a tucked-in shirt: its band goes round the shirt. Drafted from the bare
        # waist the made band (laid at its closed girth) lay UNDER the pressed shirt tail and the draped back's top
        # was cleared over it: 103 triangles 1.6-4.4x at the fine settle's start (tr_22). `waist` = the air the
        # garment is placed off the under one (layer_gap): without it the band started 13.6 mm short of closing
        zw = float(at["waist_z"])
        near = np.abs(body.V[:, 2] - zw) < 0.02
        if near.any():
            t = 1000.0 * (float(np.median(pb.pad[near])) + float(waist))
            if t > 0.2:
                info["waist"] = [round(mm["waist"], 1), round(mm["waist"] + 2 * np.pi * t, 1)]
                mm["waist"] = mm["waist"] + 2 * np.pi * t
    return mm, info


def draft_measures(body_src: dict, g: dict, body: "Body | None" = None) -> tuple[dict, dict]:
    """The measures a garment's pattern is drafted from: the body's tape, or over the garment under it (`over`,
    over_measures) when that garment is finished. (mm, info); info["over"] names the under garment, or
    info["over_missing"] when it isn't dressed yet (the bare body's then)."""
    body = body or Body(body_src)
    under = body_src.get("under")
    if under is None or under.get("res") is None:
        return dict(body.m["mm"]), ({"over_missing": body_src["under_missing"]} if body_src.get("under_missing") else {})
    U = pressed(under, body, float(g.get("under_cap", UNDER_CAP)))
    mm, info = over_measures(body, U, under["res"], waist=float(g.get("layer_gap", 0.003)) if waist_hung(g) else None)
    return mm, dict(info, over=under.get("name"))


UNDER_CAP = 0.008  # m off the body: how far a garment's loose cloth stands under another worn over it


def pressed(under: dict, body: "Body", cap: float = UNDER_CAP) -> np.ndarray:
    """A finished garment as it lies UNDER another: its loose cloth pressed toward the body to at most `cap` off it
    (a shirt blouses 2-5 cm at the sleeves and the back; a jacket's sleeve and body flatten that, and frozen as
    simulated the shirt held the jacket out like a puffer), its made pieces (collar, stand, cuffs: what shows) as
    they are, the cloth next to them eased over a few cm. Vertices move along the body's normal; nothing is solved."""
    res = under["res"]
    M, V = res["mesh"], np.array(under["V"], float)
    vn, tree = body.normals()
    n = vn[tree.query(V)[1]]
    cl = body.clearance(V)
    made = np.isin(M["piece"], [M["names"].index(nm) for nm in made_pieces(M, interfacing(res["pieces"], M)) if nm in M["names"]])
    # (and what was rolled or folded back stays as it lies: an open shirt neck's fronts, rolled back from the neck
    # to the first closed button, pressed flat along the body's normals drew as a ragged, torn-looking edge under a
    # jacket: om_13)
    from . import folds as foldmod
    for fd in M.get("folds") or []:
        if fd.get("kind") == "roll" or fd.get("name", "").startswith("open neck"):
            try:
                g_ = foldmod._geom(M, fd)
                made[np.asarray(g_["rows"][0]["v"], np.int64)] = True
                for row in fd["rows"]:
                    made[np.asarray(row, np.int64)] = True
            except Exception:
                pass
    keep = np.where(made, 1.0, 0.0)  # 1 = stays as simulated
    F = M["F"]
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]], np.asarray(M["sew"]).reshape(-1, 2)], 1), axis=0)
    hm = float(np.median(np.linalg.norm(V[F[:, 0]] - V[F[:, 1]], axis=1)))
    for _ in range(max(2, int(round(0.03 / max(hm, 1e-4))))):  # ease over ~3 cm from the made pieces
        acc, wt = np.zeros(len(V)), np.zeros(len(V))
        np.add.at(acc, E[:, 0], keep[E[:, 1]])
        np.add.at(wt, E[:, 0], 1.0)
        np.add.at(acc, E[:, 1], keep[E[:, 0]])
        np.add.at(wt, E[:, 1], 1.0)
        keep = np.where(made, 1.0, np.maximum(keep * 0.0, acc / np.maximum(wt, 1)))
    move = np.maximum(cl - cap, 0.0) * (1.0 - keep)
    for _ in range(2):  # (even: neighbours pressed alike)
        acc, wt = np.zeros(len(V)), np.zeros(len(V))
        np.add.at(acc, E[:, 0], move[E[:, 1]])
        np.add.at(wt, E[:, 0], 1.0)
        np.add.at(acc, E[:, 1], move[E[:, 0]])
        np.add.at(wt, E[:, 1], 1.0)
        move = np.where(made, 0.0, 0.5 * move + 0.5 * acc / np.maximum(wt, 1))
    move = np.minimum(move, np.maximum(cl - 0.002, 0.0))
    return V - n * move[:, None]


UNDER_SLIVER = 0.01  # a collider face thinner than this share of its longest edge squared (x2 area) is left out


def _collider(body: "Body", under: dict | None, smooth: bool) -> dict:
    """The sim's collider arrays (cloth_job: bodyV / bodyT, and for a smooth placement bodyV0 + bodyPoses: straight
    arms bending back): the body, and with it the garment worn under this one, one mesh. The under garment rides the
    body through the poses by its nearest body vertices' moves (a collider only: at the last pose it is exactly its
    own finished shape)."""
    poses = [body.straight_arms(frac=f)[0].V for f in (1.0, 0.75, 0.5, 0.25)] if smooth else []
    V, T = body.V, body.T
    if getattr(body, "worn", None):  # (garment key "collide": the model's own parts, as an under garment is)
        wv = dict(body.worn)
        # (their sliver faces and the vertices those leave without a face go first: rows are joined to the poses
        # below, and ZOZO's builder stops on a collider vertex with no face area: 12 at a shoe's toe, om_06 .. om_10)
        Vw_, Fw_ = np.asarray(wv["V"], float), np.asarray(wv["F"], np.int64)
        e1_, e2_ = Vw_[Fw_[:, 1]] - Vw_[Fw_[:, 0]], Vw_[Fw_[:, 2]] - Vw_[Fw_[:, 0]]
        a2_ = np.linalg.norm(np.cross(e1_, e2_), axis=1)
        lm_ = np.max([np.linalg.norm(e1_, axis=1), np.linalg.norm(e2_, axis=1), np.linalg.norm(e2_ - e1_, axis=1)], axis=0)
        Fw_ = Fw_[(a2_ > 1e-9) & (a2_ > UNDER_SLIVER * lm_ ** 2)]
        us_ = np.unique(Fw_)
        if len(us_) < len(Vw_):
            rm_ = np.full(len(Vw_), -1, np.int64)
            rm_[us_] = np.arange(len(us_))
            Vw_, Fw_ = Vw_[us_], rm_[Fw_]
        wv["V"], wv["F"] = Vw_, Fw_
        body = Body({"V": V, "F": body._faces, "J": body.J})
        body._m = {"mm": {}, "at": {}}
        out_ = _collider(body, {"V": wv["V"], "F": wv["F"]}, False)
        if under is None:
            out = {"bodyV": out_["bodyV"], "bodyT": out_["bodyT"]}
            if smooth:
                U = np.asarray(wv["V"], float)
                d, i = cKDTree(V).query(U, k=4)
                w = 1.0 / np.maximum(d, 1e-4) ** 2
                w /= w.sum(1, keepdims=True)
                carry_ = lambda P: U + np.einsum("nk,nkd->nd", w, (P - V)[i])
                out.update(bodyV0=np.r_[poses[0], carry_(poses[0])],
                           bodyPoses=np.stack([np.r_[P, carry_(P)] for P in poses[1:]] + [out["bodyV"]]))
            return out
        # with an under garment too: the worn parts join the body first (they ride it)
        V, T = out_["bodyV"], out_["bodyT"]
        poses = [np.r_[P, np.asarray(wv["V"], float)] for P in poses]
        body = Body({"V": V, "F": T, "J": body.J})
    if under is None:
        out = {"bodyV": V, "bodyT": T}
        if smooth:
            out.update(bodyV0=poses[0], bodyPoses=np.stack(poses[1:] + [V]))
        return out
    U = np.asarray(under["V"], float)
    d, i = cKDTree(V).query(U, k=4)
    w = 1.0 / np.maximum(d, 1e-4) ** 2
    w /= w.sum(1, keepdims=True)
    carry = lambda P: U + np.einsum("nk,nkd->nd", w, (P - V)[i])
    # the under garment's degenerate faces left out: a welded seam's two vertices at one place make slivers, and a
    # contact solver building a shell from them stops ("degenerate shell face": su_32, the blazer over the shirt)
    FU = np.asarray(under["F"], np.int64)
    keep = np.ones(len(FU), bool)
    for P in [U] + ([carry(poses[0])] if smooth else []):
        e1, e2 = P[FU[:, 1]] - P[FU[:, 0]], P[FU[:, 2]] - P[FU[:, 0]]
        a2 = np.linalg.norm(np.cross(e1, e2), axis=1)
        lmax = np.max([np.linalg.norm(e1, axis=1), np.linalg.norm(e2, axis=1), np.linalg.norm(e2 - e1, axis=1)], axis=0)
        # (and no face under 0.0005 mm2: ZOZO's builder asserts on a zero-area collider face in single precision;
        # 10 faces of 5e-11 m2 in a shirt with its placket in the mesh stopped every trousers job over it: om_03, om_06)
        keep &= (a2 > 1e-9) & (a2 > UNDER_SLIVER * lmax ** 2)
    FU = FU[keep]
    # (and no vertex left without a face: ZOZO's builder averages each collider vertex's parameters over its faces'
    # areas and asserts the sum > 0: a seam-welded vertex whose only faces were slivers stopped the job, om_06 / om_08)
    used = np.unique(FU)
    if len(used) < len(U) and under.get("res") is not None:  # (a garment; worn parts joined above keep their rows)
        remap = np.full(len(U), -1, np.int64)
        remap[used] = np.arange(len(used))
        FU = remap[FU]
        U, w, i = U[used], w[used], i[used]
        carry = lambda P: U + np.einsum("nk,nkd->nd", w, (P - V)[i])
    out = {"bodyV": np.r_[V, U], "bodyT": np.r_[T, FU + len(V)]}
    if smooth:
        out.update(bodyV0=np.r_[poses[0], carry(poses[0])],
                   bodyPoses=np.stack([np.r_[P, carry(P)] for P in poses[1:]] + [out["bodyV"]]))
    return out


def cloth_job_backend(g: dict) -> str:
    from . import cloth_job
    return cloth_job.backend_of(g)


def method_of(g: dict) -> str:
    """"settle" (construct, settle, detail: the default for a worn garment on backend "zozo") or "simulate" (sew and
    simulate everything: Blender, and states where the whole shape is physics: hung, draped)."""
    if g.get("method"):
        return g["method"]
    tm = (designs().get((g.get("pattern") or {}).get("from") or "", {}) or {}).get("method")
    if tm:  # the design table's own (a design not yet proven on "settle")
        return tm
    return "settle" if cloth_job_backend(g) == "zozo" and g.get("state", "worn") == "worn" else "simulate"


def placement_of(g: dict) -> str:
    """"smooth" (ZOZO's default: rests on the flat pattern, dressed on straight arms) or "fitted" (Blender's)."""
    return g.get("placement") or ("smooth" if cloth_job_backend(g) == "zozo" else "fitted")


def build(g: dict, body_src: dict, name: str = "garment", log=print, frames: int | None = None,
          render: dict | None = None, out_dir: Path | None = None, cached_only: bool = False, progress=None,
          result: str | Path | None = None, place_only: bool = False) -> dict | None:
    """Draft, mesh, place and simulate one garment on one body, then clean it up. Returns {"V" final verts, "V_sim"
    the sim's own, "mesh", "fit", "integrity", "sizing", "shape", ...}; the sim is cached by content (keys that only
    change the look or the clean-up never re-simulate). cached_only: None when it hasn't been simulated.
    quality "final" (default): the whole sim at `coarse` (2 cm), then carried onto the `resolution` mesh (1 cm) and
    settled there (refine): the coarse-then-fine particle distance artists use. "draft": the coarse sim alone.
    Backend "zozo" sims once at `resolution` (its contact holds at 1 cm; "draft" = at `coarse`).
    result: an out.npz (a job folder's, from any solver) applied instead of the cached/simulated one, for judging a
    result whose key has moved; it isn't cached.
    place_only: stop before the sim and return the start as the sim would get it (on the padded body when layered):
    res + {"Xs" the sim mesh's start, "coarse" its mesh, "carry", "placed_on" the body it was placed on}."""
    progress = progress or (lambda s: None)
    if body_src.get("under_missing"):
        if cached_only:
            return None
        raise ClothError(f"the garment under this one ({body_src['under_missing']}) isn't dressed yet")
    body_real = Body(body_src)
    # layered (garment key "over"): the finished garment under this one is a frozen collider with the body. Pieces are
    # placed on, and kept clear of, the body padded out to cover it (+ "layer_gap" of air, default 3 mm); the sim
    # collides with the real body and the under garment's own mesh
    under = body_src.get("under")
    # support (garment key): structure that shapes the garment without being cloth of it (shoulder pads, a sleeve-head
    # roll): the body the garment is built on is padded there, in the placement and in the sim; never rendered or
    # exported
    sup = supports(body_real, g.get("support", (designs().get((g.get("pattern") or {}).get("from") or "", {}) or {})
                                    .get("support")))
    if sup is not None:
        body_meas, body_real = body_real, sup
        body_real._m = body_meas.m  # (the tape reads the body, not its pads)
    body = body_real
    if under is not None:
        if under.get("res") is not None:  # the garment under this one as it lies under it (pressed)
            under = dict(under, V=pressed(under, body_real, float(g.get("under_cap", UNDER_CAP))))
        body = padded_body(body_real, body_src, under["V"], float(g.get("layer_gap", 0.003)))
        body._m = body_real.m
    # drafted from the tape; over another garment, from the tape taken over it (neck, armhole: over_measures)
    meas_info = {}
    if g.get("pattern"):
        meas, meas_info = (over_measures(body_real, under["V"], under["res"], waist=float(g.get("layer_gap", 0.003)) if waist_hung(g) else None) if under is not None and under.get("res") is not None
                           else (body_real.m["mm"], {}))
    Bp = pieces(g, meas if g.get("pattern") else {})
    if meas_info:
        log(f"drafted over {under.get('name')}: {json.dumps(meas_info)}")
    h = float(g.get("resolution", 0.01))  # 2 cm made blobby, faceted folds
    quality = g.get("quality", "final")
    hc = float(g.get("coarse", 0.02))
    backend = cloth_job_backend(g)
    # ZOZO isn't refined: its contact keeps a 1 cm sim clean, and a refine would rest on the carried drape
    refine = quality == "final" and hc > 1.4 * h and backend != "zozo"
    if quality == "draft":
        h = max(h, hc)
    # method "settle" (construct, settle, detail): the made pieces (collar, stand, cuffs: constructed folded by the
    # placement) are held as made and carried with the body, never shaped by the solver; the loose cloth is sewn onto
    # them and settled at `coarse`; the result is carried onto the `resolution` mesh with the made pieces constructed
    # again there (no fine sim), and the fine folds are authored from the drape (cloth_detail)
    settle = method_of(g) == "settle"
    if settle and backend != "zozo":
        raise ClothError('method "settle" needs backend "zozo" (the made pieces are held and carried in its sim)')
    hs = hc if refine or (settle and hc > 1.4 * h) else h
    construct = settle and hs > 1.4 * h
    smooth = placement_of(g) == "smooth"
    # fold lines: a contact solver's layers lie nearly touching (one crease); Blender's cloth keeps its collision
    # distance between layers, so a fold there is a U that wide (as the old collar U was)
    fw_ = 0.0 if smooth else FOLD_WIDTH_FITTED
    Ms = mesh(Bp, hs, fw_)
    if smooth and backend == "blender":
        raise ClothError('placement "smooth" is for solvers resting on the flat pattern (backend "zozo"); '
                         "Blender rests on the placement")
    # smooth: dressed on straight arms (the body bends back in the sim's "pose" stage), nothing folded but what the
    # solver keeps as rest (interfaced pieces)
    body_p, pose = body.straight_arms() if smooth else (body, None)
    Bp["worn_top"] = worn_top(g)
    # garment keys "press_lay" (m a pressed lapel lies off its forepart, PRESS_LAY) and "worn_envelope" (smoothing
    # rounds of the body a worn top is laid on, ENVELOPE_ROUNDS): over a bumpy under garment (an open shirt collar's
    # points on the chest under the lapels) a 3 mm lay crossed the forepart at Garrett's left roll line
    for k_ in ("press_lay", "worn_envelope", "open_gap", "collar_spread"):
        if g.get(k_) is not None:
            Bp[k_] = g[k_]
    if Bp["worn_top"] and under is not None and under.get("res") is not None:
        # a forepart worn over a shirt lies on the shirt's BODY: the open shirt collar sits between the jacket's
        # collar and the neck and doesn't hold the jacket up. The worn tops are laid on the body padded by the under
        # garment without its neck pieces (collar, stand), then cleared against the whole collider as everything is
        # (laid on the collar stand too, Garrett's gorge climbed the open stand and folded back: 4x, "ccd failed")
        wb = worn_body(body_real, body_src, under, float(g.get("layer_gap", 0.003)))
        if wb is not None:
            Bp["_worn_body"] = wb.straight_arms()[0] if smooth else wb
            Bp["_worn_body"].under_top = wb.under_top
    Xs = place(Bp, Ms, body_p, smooth=smooth)
    if smooth and under is not None:
        # placed on the PADDED body; the sim's collider is the body + the under garment's own mesh, and where that
        # stands proud of the pad (a pressed sleeve's fold at the elbow) draped cloth started on it
        c0_ = _collider(body_real, under, smooth)
        free_ = ~np.isin(Ms["piece"], [Ms["names"].index(nm) for nm in made_pieces(Ms, interfacing(Bp, Ms)) if nm in Ms["names"]])
        Xs, n_ex = _clear_exact(Xs, Ms["F"], free_, c0_.get("bodyV0", c0_["bodyV"]), c0_["bodyT"],
                                signed=len(body_real.T))
        if n_ex:
            log(f"   start: {n_ex} vertices moved off the collider's own triangles (exact, {EXACT_GAP * 1000:.0f} mm)")
        if under.get("res") is not None and getattr(body, "pad", None) is not None:
            Xs, n_ml = _lift_made(Xs, Ms, ~free_, body_real, body)
            if n_ml:
                log(f"   start: {n_ml} vertices of made pieces lifted over the garment under them")
    push = dict(Bp.get("push") or {})
    poses_c = [body.straight_arms(frac=f)[0].V for f in (0.75, 0.5, 0.25)] + [body.V] if settle else []
    carry = _carry(Bp, Ms, Xs, body_p, poses_c, flaps=made_flaps(g, Ms)) if settle else None
    if carry is not None and under is not None and under.get("res") is not None and Bp.get("open_lay"):
        # a made collar sewn on open and turned down by its carried poses, over another garment's collar: its pins
        # pass through the collider (the runner's hugIdx pins). Prescribed onto an open shirt collar's wings, which
        # can't yield, the solver stalled in the first frames ("a prescribed pin driven into geometry that cannot
        # yield": om_05 .. om_11). The draped cloth still meets the collider and the collar.
        Bp["thru"] = sorted(carry.get("pieces") or [])
    Xstart = Xs
    if carry is not None and Bp.get("open_lay"):
        Xstart, carry = _open_start(Bp, Ms, Xs, body_p, poses_c, carry)
    if refine:
        M = mesh(Bp, h, fw_)
        # the fine mesh's rest shape is the coarse one's placement carried onto it (the same surface, sampled finer):
        # placed again at 1 cm, its cuff spiral and pushed-off rows differed from the coarse rest the sim had settled,
        # and easing between the two crumpled one interfaced cuff
        X0 = transfer(Ms, Xs, M)
    elif construct:
        # the fine mesh is never simulated: its folds are a U as wide as two layers of cloth lie apart (a sim's start
        # needs a contact gap at its first ring of vertices, so a simulated crease is a wedge 5-7 deg open)
        M = mesh(Bp, h, FOLD_WIDTH_MADE)
        Bf = dict(Bp)
        X0 = place(Bf, M, body_p, smooth=smooth)  # the fine mesh's own placement: its made pieces as constructed
        Bp["faces"] = Bf.get("faces", Bp.get("faces"))
    else:
        M, X0 = Ms, Xs
    fab_s, fab = _fabric_at(g, hs), _fabric_at(g, h)
    state = g.get("state", "worn")
    hang = isinstance(state, dict) and "hang" in state or state == "hung"
    from . import hanger as hangmod
    hspec = hangmod.spec_of(state)
    # hung on a hanger: the hanger is put inside the dressed garment where the body's shoulders were (its hook clear of
    # the collar the garment starts with), the body goes and the garment settles onto it; no pins
    hg = hangmod.fit(body, hspec, garment_X=Xs) if hspec is not None else None
    hmesh = hangmod.meshes(hg) if hg is not None else []
    harr = {}
    for o in hangmod.meshes(hg, guard=HOOK_GUARD * hc) if hg is not None else []:  # the sim's colliders
        harr[f"{o['name']}V"], harr[f"{o['name']}F"] = o["V"], o["F"]
    # before the body goes, its arms come down to its sides with the garment on (stage "lower"): taken off a dummy in
    # the A-pose, a coat's sleeves stayed splayed on the hanger
    la = g.get("lower_arms", True)
    # ZOZO's arms come down straightened to 3 cm off the body (the sleeves hang straight); Blender's as before
    la = dict({"gap": 0.03, "straighten": True} if backend == "zozo" else {}, **(la if isinstance(la, dict) else {}))
    lower = {"bodyLower": np.stack(body.arms_down(**la))} if hg is not None and g.get("lower_arms", True) else {}
    from . import cloth_job
    solver = cloth_job.solver_of(backend)
    # the code that makes the result: blender_cloth.py for Blender, the runner for any other solver (a ZOZO result
    # was lost on every edit of the Blender script)
    code = hashlib.sha1(SCRIPT.read_bytes()).hexdigest() if solver == "blender" else cloth_job.solver_code(solver)
    # keyed on the sim's inputs themselves (start positions, pattern, triangles, seams, stitches, interfacing, both
    # meshes) and the Blender side's code, not on cloth.py: a change there that moves nothing doesn't re-simulate
    # smooth: the rest the solver gets (flat pattern + the made pieces' unpushed placement) is an input too
    made_s = _made_rest(Bp, Ms, Xs) if smooth else None
    rest_s = rest_shape(Ms, Xs, interfacing(Bp, Ms), True, made_s) if smooth else None
    # fold lines: where the cloth rests on the flat pattern, the hinges along a fold rest at its angle (the flat
    # pattern folded: folds.bend_reference) and bend harder (fold weights); made pieces and Blender's cloth rest on the
    # placement, which holds the fold
    from . import folds as foldmod
    fold_s = {}
    if Ms.get("folds"):
        fold_s["fold"] = foldmod.weights(Ms)
        if smooth:
            fold_s["bend_rest"] = foldmod.bend_reference(Ms, np.c_[Ms["uv"], np.zeros(len(Ms["uv"]))], Bp.get("faces"))
    inputs = hashlib.sha1(b"".join(np.ascontiguousarray(a).tobytes() for a in (
        Xstart, Ms["uv"], Ms["F"], Ms["sew"], Ms["stitch"], interfacing(Bp, Ms),
        *((X0, M["uv"], M["F"], M["sew"], M["stitch"]) if refine else ()), *harr.values(), *lower.values(),
        *((rest_s,) if smooth else ()), *fold_s.values(),
        *((carry["idx"], carry["poses"]) if carry else ())))).hexdigest()
    gs = {k: v for k, v in g.items() if k not in NOT_SIM}
    gs.pop("backend", None)
    if construct:  # the sim is the coarse one whatever the fine mesh: its size isn't in the key
        gs.pop("resolution", None)
    keyed = [VERSION, gs, body_src.get("key"), frames, code, inputs, fab_s, fab_s if construct else fab]
    if body_src.get("worn"):
        keyed.append(["worn", body_src["worn"]["key"]])
    if under is not None:  # another under garment (or another drape of it) is another result
        keyed.append(["under", under["key"]])
    if solver != "blender":  # another solver's result is another result (Blender's keys stay as they were); the
        # solver, not the backend: ZOZO run here or on a pod is the same result
        keyed.append(["solver", solver])
    if result is not None:  # a hand-carried out.npz: its own key, never cached
        keyed.append(["result", hashlib.sha1(Path(result).read_bytes()).hexdigest()])
    key = hashlib.sha1(json.dumps(keyed, sort_keys=True, default=str).encode()).hexdigest()[:16]
    cache = _cache_dir() / f"{key}.npz"
    coll = _collider(body_real, under, smooth)
    Bp.pop("_worn_body", None)  # (a Body: not part of the result)
    res = {"pieces": Bp, "mesh": M, "X0": X0, "body": body_real, "collider": body, "under": under,
           "fabric": fab, "key": key, "refined": refine,
           "rest": rest_shape(M, X0, interfacing(Bp, M), smooth, made_s if not (refine or construct) else None),
           "coarse_mesh": Ms if refine else None, "hung": hang, "hanger": hg, "hanger_meshes": hmesh}
    if place_only:
        return dict(res, Xs=Xs, Xstart=Xstart, coarse=Ms, carry=carry, placed_on=body_p, rest_s=rest_s)
    if result is not None:
        from . import cloth_job as cj
        d, lines = cj.read_out(Path(result))
        if d["V"].shape != Xs.shape:
            raise ClothError(f"result {result}: {len(d['V'])} vertices, this garment's sim mesh has {len(Xs)} (another "
                             "garment, resolution or quality?)")
        res["V_sim"], res["V_coarse"], res["V_prev"] = d["V"], None, d.get("Vprev")
        res["log"] = "\n".join(lines)
        if construct:  # the coarse settle: the fine result is constructed from it below
            res["V_coarse"], res["V_sim"], res["V_prev"] = d["V"], None, None
        if refine:  # a coarse result: carried onto the fine mesh (no refine run)
            res["V_coarse"] = d["V"]
            res["V_sim"] = transfer(Ms, d["V"], M)
            res["V_prev"] = transfer(Ms, d["Vprev"], M) if d.get("Vprev") is not None else None
    elif cache.exists() and not render:
        d = np.load(cache)
        res["V_sim"] = d["V"]
        res["V_coarse"] = d["Vc"] if "Vc" in d else None
        res["V_prev"] = d["Vprev"] if "Vprev" in d else None
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
               "placement": placement_of(g), **({"zozo": dict(g["zozo"])} if g.get("zozo") else {}),
               "wraps": {nm: Bp["pieces"][nm]["wrap"].get("to", "torso") for nm in Ms["names"]},
               "made": made_pieces(Ms, stiff_s),
               **{k: g[k] for k in ("sew_force", "sew_frames", "worn_frames", "settle_frames", "self_collision_sew",
                                    "hang_frames", "hang_sew_force", "hang_air", "lower_frames") if k in g}}
        if settle:  # nothing assembled in stages: the made pieces are held, the loose cloth sews onto them
            cfg.update(carry=True, sew_frames=int(g.get("sew_frames", 60)), pose_frames=int(g.get("pose_frames", 30)),
                       frames=int(frames or g.get("frames", 48)), settle_frames=int(g.get("settle_frames", 12)))
        elif g.get("assemble", True):
            cfg["assemble"] = _assembly(Bp, Ms, body)
        pins_of = None
        if hg is not None:
            cfg["hanger"], cfg["hanger_thickness"] = hangmod.to_job(hg), HANGER_SKIN * hs
            cfg["lower"] = bool(lower)
        elif hang:
            def pins_of(Mx, Xx):
                return _hang_pins(state, Mx, Xx)
            cfg["pins"] = [int(i) for i in pins_of(Ms, Xs)]
            cfg["hook"] = state["hang"].get("hook")
            cfg["rack"] = state["hang"].get("rack")  # [[a, b, radius], ...] colliders (a coat rack's pole, arms)
            cfg["pin_spread"] = state["hang"].get("spread", 0.3)
        arrays = dict(X=Xstart, uv=Ms["uv"], F=Ms["F"], sew=Ms["sew"], stitch=Ms["stitch"], stiff=stiff_s,
                      piece=Ms["piece"], pins=np.zeros(0, np.int64), **harr, **lower,
                      **fold_s, **({"carryIdx": carry["idx"], "carryPoses": carry["poses"]} if carry else {}),
                      **({"hugIdx": np.where(np.isin(Ms["piece"], [Ms["names"].index(n_) for n_ in
                                                                    list(Bp.get("hug") or []) + list(Bp.get("thru") or [])]))[0]}
                         if Bp.get("hug") or Bp.get("thru") else {}),
                      **coll, **({"rest": rest_s} if smooth else {}))
        if carry and len(carry.get("flap_idx", ())) and smooth and "bend_rest" in fold_s:
            # made flaps of draped pieces (made_folds): held like the made pieces, but their rest is the flat pattern
            # FOLDED at their line (as the draped cloth beside them rests): resting as they start (world positions)
            # beside cloth resting on the flat pattern, the triangles across the roll line read 332% stretched and the
            # solver failed at frame 0 (su_44). The runner's restIdx path: carried vertices rest as given here
            rj_ = np.array(rest_s, float, copy=True)
            rj_[carry["idx"]] = Xstart[carry["idx"]]  # (the made pieces as before: as they start)
            fl_ = carry["flap_idx"]
            rj_[fl_] = np.asarray(fold_s["bend_rest"], float)[fl_]
            arrays.update(rest=rj_, restIdx=np.asarray(carry["idx"], np.int64))
        if (Bp.get("band_clear") or Bp.get("hug")) and backend == "zozo":
            # a gripping band starts BAND_CLEAR off the body: the body's contact offset + gap must be inside that
            zc_ = cfg.setdefault("zozo", {})
            zc_.setdefault("body_offset", 0.001)
            zc_.setdefault("contact_gap", 0.0005)
        progress(f"sim at {hs * 100:.1f} cm: {len(Xs)} verts")
        d, lines = _blender_job(job_dir, cfg, arrays, name, log, progress, backend=backend, names=Ms["names"])
        Vs = d["V"]
        Vc = None
        if construct:
            Vc = Vs
            Vs = None
        elif refine and hg is not None:
            # on a hanger the fine settle is skipped: the coarse hang carried onto the fine mesh is the result (a
            # 40-frame settle of it in Blender flailed, 62 mm/frame at the end, and crossed at centre back: interpolated
            # sleeves and fronts lying close cross at 1 cm; the clean-up smooths the carried surface)
            Vc = Vs
            Vs = transfer(Ms, Vs, M)
            if d.get("Vprev") is not None:
                d = dict(d, Vprev=transfer(Ms, d["Vprev"], M))
            lines = lines + ["cloth: refine on the hanger skipped: the coarse hang carried onto the fine mesh"]
        elif refine:
            Vc = Vs
            S = transfer(Ms, Vs, M)
            rcfg = {"mode": "refine", "fabric": fab, "self_collision": bool(g.get("self_collision", True)),
                    "refine_frames": int(g.get("refine_frames", 40)), "refine_ease": int(g.get("refine_ease", 15)),
                    "body": not hang}
            pins = np.zeros(0, np.int64)
            if hg is not None:
                rcfg["hanger"], rcfg["hanger_thickness"] = hangmod.to_job(hg), HANGER_SKIN * h
            elif hang:
                pins = pins_of(M, X0)
                rcfg["pins"] = [int(i) for i in pins]
                rcfg["rack"] = state["hang"].get("rack")
            progress(f"refine at {h * 100:.1f} cm: {len(X0)} verts")
            d2, lines2 = _blender_job(job_dir, rcfg, dict(X=X0, S=S, uv=M["uv"], F=M["F"], sew=M["sew"],
                                                          stitch=M["stitch"], stiff=interfacing(Bp, M),
                                                          bodyV=body.V, bodyT=body.T, piece=M["piece"], **harr),
                                            name, log,
                                            progress, backend=backend, names=M["names"])
            Vs = d2["V"]
            d = d2
            lines = lines + lines2
        res["V_sim"], res["V_coarse"] = Vs, Vc
        res["V_prev"] = d.get("Vprev") if not construct else None
        res["log"] = "\n".join(lines)
        log(f"cloth {name}: simulated in {time.time() - t:.0f} s")
        np.savez_compressed(cache, V=Vs if Vs is not None else Vc, log=res["log"], **({"Vc": Vc} if Vc is not None else {}),
                            **({"Vprev": res["V_prev"]} if res.get("V_prev") is not None else {}))
        if out_dir is None and not os.environ.get("HIFIPUSHIE_CLOTH_KEEP"):  # the job's files (MBs) go
            import shutil
            shutil.rmtree(job_dir, ignore_errors=True)
    Bp["push"] = push
    if construct and g.get("fine_settle", True):
        # ("fine_settle": false turns it off (the result is then put together by hand: _constructed, with crossings);
        # [press, settle] frames: press > 0 prescribes the flaps closed first, which stopped the solver on intersections)
        # the fine settle: the made pieces prescribed (their flaps pressing down from open), the carried drape settling
        # round them by contact for a few frames; no geometry is moved by hand
        fs = g.get("fine_settle")
        fr = [int(v) for v in (fs if isinstance(fs, (list, tuple)) else (0, 36))]
        press_ = fr[0] > 0
        plan = _press_plan(Bp, Ms, Xs, res["V_coarse"], M, X0, carry, body, press=fr[0] > 0)
        # the start cleared of the WHOLE collider too (the body alone was cleared in the plan: a trouser hem resting on
        # the shoes, garment key "collide", started 0.5 mm off them, under the settle's least contact offset: "contact
        # starts overlapping")
        if len(coll["bodyV"]) > len(body.V) and _start_separation(plan["start"], M["F"], coll["bodyV"], coll["bodyT"]) < START_GAP:
            cb_ = Body({"V": coll["bodyV"], "F": coll["bodyT"], "J": {}})
            cb_._m = {"mm": {}, "at": {}}
            mv_ = np.ones(len(plan["start"]), bool)
            st_ = plan["start"]
            if under is not None:
                # (over another garment the collider holds that garment's own cloth, wound as its pattern lies: read
                # as a closed body, its normals pushed the trousers' back INTO the tucked shirt's tail: 102 triangles
                # 1.6-3.9x at the back's waist corner, tr_22 / tr_24. Against its triangles, on the side each point is)
                st_, _n = _clear_exact(st_, M["F"], mv_, coll["bodyV"], coll["bodyT"], gap=START_GAP, rounds=8,
                                       signed=len(body_real.T))
            for _ in range(3 if under is None else 0):  # (the exact pass's few rounds leave the worst pairs short: again, from where they got)
                st_ = _clear_of_body(st_, M["F"], mv_, cb_, START_GAP, START_GAP, CLEAR_GROW)
                if _start_separation(st_, M["F"], coll["bodyV"], coll["bodyT"]) >= 0.9 * START_GAP:
                    break
            plan["start"] = st_
            if not press_ and len(plan["idx"]):
                plan["poses"] = st_[plan["idx"]][None]
        stiff_f = interfacing(Bp, M)
        fold_f = {}
        if M.get("folds"):
            fold_f = {"fold": foldmod.weights(M),
                      "bend_rest": foldmod.bend_reference(M, np.c_[M["uv"], np.zeros(len(M["uv"]))], Bp.get("faces"))}
        fkey = hashlib.sha1(b"".join(np.ascontiguousarray(a).tobytes() for a in (
            plan["start"], plan["poses"], plan["release"], plan["idx"], plan["tacks"], M["F"], M["sew"], body.V)) + json.dumps(
            [fr, fab, g.get("zozo"), code], sort_keys=True, default=str).encode()).hexdigest()[:16]
        fcache = _cache_dir() / f"{fkey}_fine.npz"
        if fcache.exists():
            df = dict(np.load(fcache))
        elif cached_only:
            return None
        else:
            t = time.time()
            fcfg = {"mode": "fine_settle", "fabric": fab, "state": "worn", "name": name, "placement": "smooth",
                    "self_collision": True, "press_frames": fr[0], "frames": fr[1], "carry": True,
                    "made": made_pieces(M, stiff_f), "wraps": {nm: Bp["pieces"][nm]["wrap"].get("to", "torso") for nm in M["names"]},
                    **({"zozo": dict(g["zozo"])} if g.get("zozo") else {})}
            farr = dict(X=plan["start"], uv=M["uv"], F=M["F"], sew=M["sew"],
                        stitch=np.r_[M["stitch"].reshape(-1, 2), plan["tacks"]], stiff=stiff_f,
                        piece=M["piece"], bodyV=coll["bodyV"], bodyT=coll["bodyT"], pins=np.zeros(0, np.int64),
                        carryIdx=plan["idx"], carryPoses=plan["poses"], releaseIdx=plan["release"],
                        **({"hugIdx": np.where(np.isin(M["piece"], [M["names"].index(n_) for n_ in Bp["hug"]]))[0]}
                           if Bp.get("hug") else {}),
                        restIdx=plan["rest_idx"], rest=plan["made"], **fold_f)
            # a strain-limited solver can't start past its limit: the carried drape, kept clear of the body vertex by
            # vertex, starts stretched a few % in places (1 mm on a 1 cm triangle is 10%); the limit over this short
            # settle is what the start needs, and the membrane takes the stretch back out
            bad_ = fine_start_check(M, plan)
            if bad_:
                raise RuntimeError(f"cloth {name}: the fine settle's start is stretched past what the solver can start "
                                   f"from ({bad_}); nothing was sent to the GPU")
            from . import cloth_detail
            _, hi_, _, _ = cloth_detail.strain_field(M, plan["start"])
            loose_t = ~np.isin(M["F"], plan["idx"]).any(1)
            need_ = float(hi_[loose_t].max()) - 1.0 if loose_t.any() else 0.0
            zz = dict(g.get("zozo") or {})
            zz.setdefault("strain_limit", float(np.clip(1.15 * need_ + 0.02, 0.05, 0.6)))
            # a contact solver can't start inside its standoff either, and the made pieces are held where the coarse
            # sim carried them (a cuff round a wrist can't be pushed clear on one side without closing on the other):
            # the body's contact offset for this settle is what the start leaves (it stopped on a pair 1.9 mm apart
            # under a 2 mm offset)
            sep_ = _start_separation(plan["start"], M["F"], coll["bodyV"], coll["bodyT"])
            if sep_ < 0.0022:
                # (never more than 0.7 of what the start leaves: a 0.6 mm floor over a 0.51 mm start was "contact
                # starts overlapping")
                zz.setdefault("body_offset", float(max(0.0003, 0.7 * sep_)))
                progress(f"fine settle: the start comes within {sep_ * 1000:.2f} mm of the body: its contact offset "
                         f"{zz['body_offset'] * 1000:.2f} mm for this settle")
            fcfg["zozo"] = zz
            progress(f"fine settle at {h * 100:.1f} cm: {len(plan['start'])} verts, {sum(fr)} frames, start stretch up to "
                     f"{need_ * 100:.0f}% (strain limit {zz['strain_limit'] * 100:.0f}%)")
            df, lines_f = _blender_job(out_dir or (_cache_dir() / f"job_{key}"), fcfg, farr, name, log, progress,
                                       backend=backend, names=M["names"])
            res["log"] = res.get("log", "") + "\n" + "\n".join(lines_f)
            log(f"cloth {name}: fine settle in {time.time() - t:.0f} s")
            np.savez_compressed(fcache, V=df["V"], **({"Vprev": df["Vprev"]} if df.get("Vprev") is not None else {}))
        res["V_sim"], res["V_drape"], res["V_prev"] = df["V"], plan["drape"], df.get("Vprev")
        res["constructed"] = {"pieces": plan["pieces"], "folds": plan["info"], "fine_settle": fr,
                              "untangled": Bp.get("untangled"), "made_reshaped": Bp.get("made_reshaped")}
    elif construct:
        res["V_sim"], res["V_drape"], res["constructed"] = _constructed(Bp, Ms, Xs, res["V_coarse"], M, X0, carry, body)
        res["V_prev"] = None
    # A piece the fine settle tangled or crumpled that the coarse drape had clean keeps the coarse drape carried onto
    # the fine mesh (the clean-up then welds its seams). Blender's self-collision at 1 cm let bunched cloth pass through
    # itself where the 2 cm sim held (a hung coat's top: 2 -> 1600 crossings whatever the rest shape or ease; a heavy
    # body's cuff)
    if refine and res.get("V_coarse") is not None:
        S = transfer(Ms, res["V_coarse"], M)
        ig_f, ig_s = integrity(res["V_sim"], M, Bp, X0), integrity(S, M, Bp, X0)
        back = [p for p in ig_f["corrupt_pieces"] if p not in ig_s["corrupt_pieces"]]
        if back:
            V = res["V_sim"].copy()
            for p in back:
                sel = M["piece"] == M["names"].index(p)
                V[sel] = S[sel]
            res["kept_coarse"] = back
            if integrity(V, M, Bp, X0)["self_intersections"] > 3 * ig_s["self_intersections"] + 20:
                V, res["kept_coarse"] = S, ["all pieces"]  # tangled across pieces (the hung coat): the whole drape
            res["V_sim"] = V
    # the clean-up pass (what artists do in ZBrush/Blender after the sim): crinkle smoothed, big folds kept, seams
    # welded, the cloth kept off the body
    # ZOZO's surface needs no smoothing (its sim crinkle is low): Taubin rounded its fold crests 20-40% (sleeve crest
    # radius p50 12 -> 17 mm at 1 cm) and wiped its smaller folds; welding and the push off the body stay
    cu = g.get("cleanup", {"smooth": 0} if backend == "zozo" else {})
    if construct and "cleanup" not in g:
        # the coarse drape carried onto the fine mesh is its facets: smoothed over about a coarse triangle (the made
        # pieces, constructed at the fine size, are left: cleanup doesn't smooth interfaced cloth)
        cu = {"smooth": int(round(1.5 * (hs / h) ** 2 * max(1.0, (h / 0.01) ** 2))), "keep": 0.3 * hs}
        if res["constructed"].get("fine_settle"):  # settled at the fine size: what is left of the coarse facets only
            cu = {"smooth": 3, "keep": 0.002}
    # (the REAL body: layered, `body` is padded out over the garment underneath, and pushing the finished jacket
    # off that pad moved it 7 mm at p95 and through its own collar: 88 crossings the sim didn't have)
    cu = dict(cu if isinstance(cu, dict) else {"smooth": 0} if cu is False else {})
    cu.setdefault("pressed", seam_press_mask(M, g))  # (seam kinds: a "welt" seam isn't pressed)
    res["V"], res["cleanup"] = cleanup(res["V_sim"], M, None if hang else body_real,  # hung: the body is gone
                                       cu, stiff=interfacing(Bp, M))
    if construct and not res["constructed"].get("fine_settle"):  # (the smoothing can bring cloth back out through a
        # made flap)
        held_ = np.isin(M["piece"], [M["names"].index(nm) for nm in res["constructed"]["pieces"]])
        res["V"] = _tuck(res["V"], M, held_, body)
    do = dict(DETAIL, **(g.get("detail") or {})) if g.get("detail", {}) is not False else {"folds": False}
    if do["folds"] if do["folds"] is not None else settle:
        # the folds the drape implies but the mesh couldn't make (cloth_detail): the big ones into the geometry here
        # (the silhouette has them), the fine ones into the normal map (fine_folds)
        from . import cloth_detail
        fabn = res["fabric"].get("name", "shirting")
        Vd_ = res["V_drape"] if res.get("V_drape") is not None else res["V_sim"]
        res["fold_dabs"], res["fold_info"] = cloth_detail.fold_dabs(M, Vd_, fabn, interfacing(Bp, M),
                                                                    float(do["fold_gain"]), opts=do["fold_opts"])
        if h <= 0.012 and not hang:
            res["V"], rms = cloth_detail.displace(M, res["V"], res["fold_dabs"], fabn, do["fold_opts"], interfacing(Bp, M),
                                                  body=body_real)
            res["folds_in_geometry"] = round(rms, 2)
    if any(fd.get("kind") == "press" and fd.get("in_wrap") and float(fd.get("angle", 180)) > 180.5
           for fd in M.get("folds") or []) and not hang:
        # pressed ridges (a trouser crease) sharpened in the geometry: the iron's work (folds.press_ridges)
        Fo = oriented_faces(M, res["V"], body=body_real)
        fn_ = np.cross(res["V"][Fo[:, 1]] - res["V"][Fo[:, 0]], res["V"][Fo[:, 2]] - res["V"][Fo[:, 0]])
        No = np.zeros_like(res["V"])
        for c_ in range(3):
            np.add.at(No, Fo[:, c_], fn_)
        No /= np.maximum(np.linalg.norm(No, axis=1, keepdims=True), 1e-12)
        made_v = np.isin(M["piece"], [M["names"].index(nm) for nm in (res.get("constructed") or {}).get("pieces", [])])
        res["V"], res["pressed_ridges"] = foldmod.press_ridges(res["V"], M, No, skip=made_v)
    if not hang:
        # the clean-up (welds, the push off the body) and the folds put into the geometry must not make the cloth
        # cross itself where the sim left it clean: those places go back to the sim's surface. For every garment:
        # it used to run only after a fine settle, and a jacket's clean-up crossed its collar ends
        A_, B_ = _graph(M)
        # (only crossings the clean-up MADE: where the sim itself is crossed, a made collar's ends, going back to the
        # sim's surface mends nothing, and each round grew the reverted patch by two rings: its welds were undone and
        # the seams round it stayed open, 66 of 502 sewn pairs on the shirt)
        if len(M["sew"]):
            res["V"], res["weld_left"] = _weld_clear(res["V"], res["V_sim"], M, interfacing(Bp, M))
        # layered: the clean-up knows the body only, so its push and welds took the jacket's sleeves and armholes 4-9 mm
        # into the shirt (su_41: 16 crossings between the layers in the sim, 247 after the clean-up: the white flecks of
        # shirt through the jacket); crossings with the garment under this one count as the clean-up's too
        uV_ = np.asarray(under["V"], float) if (under is not None and under.get("res") is not None) else None
        uF_ = np.asarray(under["res"]["mesh"]["F"]) if uV_ is not None else None

        def crossed(X_):
            c_ = _crossing_verts(X_, M)
            if uV_ is not None:
                c_ = c_ | _layer_crossing_verts(X_, M["F"], uV_, uF_)
            return c_
        sim_bad = crossed(res["V_sim"])
        for _r in range(2):
            gr = sim_bad.copy()
            gr[A_[sim_bad[B_]]] = True
            gr[B_[sim_bad[A_]]] = True
            sim_bad = gr
        # the welded seam groups as the clean-up left them (sewn pairs closed within 0.5 mm)
        wgrp_ = wsize_ = None
        sw_ = np.asarray(M["sew"]).reshape(-1, 2)
        if len(sw_):
            sw_ = sw_[np.linalg.norm(res["V"][sw_[:, 0]] - res["V"][sw_[:, 1]], axis=1) < 5e-4]
            wgrp_ = np.arange(len(res["V"]))
            for _ in range(8):
                m2_ = np.minimum(wgrp_[sw_[:, 0]], wgrp_[sw_[:, 1]])
                np.minimum.at(wgrp_, sw_[:, 0], m2_)
                np.minimum.at(wgrp_, sw_[:, 1], m2_)
                wgrp_ = wgrp_[wgrp_]
            wsize_ = np.bincount(wgrp_, minlength=len(wgrp_))[wgrp_]
        for it_ in range(8):
            bad = crossed(res["V"]) & ~sim_bad
            if not bad.any():
                break
            # (the crossing vertices alone first, then a ring, then two: two rings at once reopened every seam
            # within 4 cm of one stubborn crossing at a collar's end, the shoulder seams with it)
            for _r in range(min(it_, 2)):
                gr = bad.copy()
                gr[A_[bad[B_]]] = True
                gr[B_[bad[A_]]] = True
                bad = gr
            res["V"][bad] = res["V_sim"][bad]
            # a welded seam vertex that goes back takes its weld with it: the group moves to the mean of its sides'
            # sim positions (sent back alone, one side of a closed seam stood at the sim's 3-6 mm gap: pale slits on
            # both upper sleeves in su_43); the seam stays closed where nothing crosses
            if wgrp_ is not None and bad.any():
                gb_ = np.unique(wgrp_[bad & (wsize_ > 1)])
                if len(gb_):
                    m_ = np.isin(wgrp_, gb_)
                    acc_ = np.zeros((len(res["V"]), 3))
                    np.add.at(acc_, wgrp_[m_], res["V_sim"][m_])
                    res["V"][m_] = acc_[wgrp_[m_]] / wsize_[m_][:, None]
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
    # closures: the plackets' bands stand their extra layers proud, the buttons are small geometry on them, and each
    # chosen closure is measured in the result
    from . import closures as closuremod
    if M.get("closures"):
        res["closures_sim"] = closuremod.measure(res["V"], M)
        if not hang and (g.get("cleanup") is not False) and (g.get("cleanup") or {}).get("seat", True):
            # a closed lap lies closed (closures.seat): the over band laid on the under layer, the fastenings' two
            # sides brought together; what crosses for it goes back
            Vs_, res["closures_seat"] = closuremod.seat(res["V"], M, Bp["pieces"], body_real,
                                                        fixed=np.isin(M["piece"], [M["names"].index(n_) for n_ in made_pieces(M, interfacing(Bp, M))]))
            # where laying the lap made the cloth cross itself, those vertices (and two rings round them) stay as
            # they were; the rest of the lap is laid
            was_ = _crossing_verts(res["V"], M)
            # (first each crossing vertex loses the part of its move across the layer it went through, as for the
            # welds: reverted two rings wide, 230 vertices round su_garrett's 4th and 5th buttons went back and
            # those fastenings stayed 9 mm open)
            if (_crossing_verts(Vs_, M) & ~was_).any():
                Vs_, _ = _weld_clear(Vs_, res["V"], M, interfacing(Bp, M))
            bad_ = _crossing_verts(Vs_, M) & ~was_
            if bad_.any():
                # (the crossing vertices alone first, then a ring, then two: two rings at once put 229 vertices round
                # su_garrett's 4th and 5th buttons back and those fastenings stayed 9 mm open)
                A2_, B2_ = _graph(M)
                kept_ = np.zeros(len(Vs_), bool)
                for it_ in range(6):
                    bad_ = _crossing_verts(Vs_, M) & ~was_
                    if not bad_.any():
                        break
                    for _r in range(min(it_, 2)):
                        gr_ = bad_.copy()
                        gr_[A2_[bad_[B2_]]] = True
                        gr_[B2_[bad_[A2_]]] = True
                        bad_ = gr_
                    Vs_[bad_] = res["V"][bad_]
                    kept_ |= bad_
                res["closures_seat"] = [dict(r_, kept_back=int(kept_.sum())) for r_ in res["closures_seat"]]
            if int((_crossing_verts(Vs_, M) & ~was_).sum()) == 0:
                res["V"] = Vs_
            else:
                res["closures_seat"] = [dict(r_, reverted="it crossed the cloth") for r_ in res["closures_seat"]]
        res["closures"] = closuremod.measure(res["V"], M)
        # a box band's edge as a crisp step in the mesh: a row 1.5 mm outside its inner fold (new vertices appended to
        # every per-vertex array: the sim's own arrays too, so later steps see one mesh)
        if not hang and (g.get("cleanup") or {}).get("band_edges", True) is not False:
            nV_ = len(M["uv"])
            sp_ = closuremod.split_band_edges(M, Bp["pieces"])
            if sp_ is not None:
                for k_ in list(res):
                    a_ = res[k_]
                    if k_ != "mesh" and isinstance(a_, np.ndarray) and a_.ndim >= 1 and len(a_) == nV_:
                        res[k_] = closuremod.extend(a_, sp_)
                X0 = closuremod.extend(X0, sp_) if len(X0) == nV_ else X0
                res["band_edges"] = int(len(sp_["t"]))
        res["V_closed"] = res["V"]  # (before the bands' relief: what relief / buttons_mesh are applied to)
        res["V"] = closuremod.relief(res["V"], M, Bp["pieces"], None if hang else body_real)
        # pressing the band flat must not cross the cloth (the lap's under layer bulging between two buttons): those
        # vertices and a ring round them stay as they were (pk_27: 16 crossings at the lowest button)
        bad_ = _crossing_verts(res["V"], M) & ~_crossing_verts(res["V_closed"], M)
        if bad_.any():
            A3_, B3_ = _graph(M)
            for _r in range(2):
                gr_ = bad_.copy()
                gr_[A3_[bad_[B3_]]] = True
                gr_[B3_[bad_[A3_]]] = True
                bad_ = gr_
            res["V"] = np.where(bad_[:, None], res["V_closed"], res["V"])
            res["band_kept_back"] = int(bad_.sum())
        res["buttons"] = closuremod.buttons_mesh(res["V"], M, None if hang else body_real)
    res["seam_gaps"] = seam_gaps(res["V_sim"], res["V"], M)
    res["shape"] = {"sim": shape_numbers(res["V_sim"], M), "final": shape_numbers(res["V"], M)}
    res["fit"] = fit(res)
    res["integrity"] = integrity(res["V"], M, Bp, X0)
    ig_sim = integrity(res["V_sim"], M, Bp, X0)
    res["integrity"]["sim"] = {"self_intersections": ig_sim["self_intersections"],
                               "corrupt_pieces": ig_sim["corrupt_pieces"],
                               "crumpled": {p: v["crumpled"] for p, v in ig_sim["pieces"].items() if v["crumpled"] > 0.01}}
    res["sizing"] = sizing(res)
    if under is not None and under.get("res") is not None:  # layered: the tailoring tells against the garment under it
        from . import cloth_layers
        res["under_V"] = np.asarray(under["V"], float)  # the under garment as pressed under this one
        res["tells"] = cloth_layers.tells(res, dict(under["res"], V=res["under_V"]))
    if hang:  # what carries it: the hanger's arms by contact (pins: the old pinned hang), and is the hanger inside it
        if hg is not None:
            pins_h, hx = np.zeros(0, np.int64), hg
        else:
            pins_h, hx = _hang_pins(state, M, X0), _rack_hanger(state)
        res["support"] = hangmod.support(res["V_sim"], M, hx, pins_h, res.get("V_prev"), frames_apart=PREV_APART)
        res["on_hanger"] = hangmod.on_hanger(res["V"], M, hg) if hg is not None else None
        res["hanger_ok"], res["hanger_line"] = hangmod.verdict(res["support"], res["on_hanger"])
        res["sleeves"] = sleeve_angles(res["V"], M, Bp)
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
    if hang and not res["hanger_ok"]:  # hung: a garment not hanging on its hanger is said before anything else
        res["fit"]["verdict"] = res["hanger_line"].split(": supported by")[0] + " | " + res["fit"]["verdict"]
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
    the surface against a Taubin low-pass keeping forms over ~15 cm: folds narrower than that; a 20 mm-deep 10 cm fold
    reads ~9, a shirt hanging close 2-4)."""
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
    # a Taubin low-pass whose pass band ends at ~15 cm wavelengths (kpb = (2 pi h / 0.15)^2): folds narrower than that
    # are removed, the garment's form round the body (arms, shoulders) kept. A plain Laplacian shrank a sleeve's tube
    # and read 30 mm of "folds" on every shirt
    # (capped at 0.3: at 2 and 4 cm (0.7, 1) the 200 passes blew up to 1e4..5e10 mm of "folds")
    kpb = min(0.3, (2 * np.pi * max(h, 1e-3) / 0.15) ** 2)
    lo = taubin(V, M, 200, lam=0.5, mu=1.0 / (kpb - 1.0 / 0.5))
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


ROW_KEEP = 0.25  # x h: a fold row's inner sample this near the outline (within ROW_END h of the row's ends) is left out
ROW_END = 2.5  # x h: (ROW_KEEP) how far from a row's ends; a sample near another fold's row is shared
SEAM_JOIN = 0.15  # x h: a fold line ending this near a seam sample ends ON it (no sliver edge on the seam)
CLEANUP = {"smooth": 4, "weld": True, "clear": 0.003, "keep": 0.004, "seat": True, "seams": True, "press": True,
           "kinks": True}


SEAM_GAP_MM = 0.5  # a finished seam's two sides further apart than this at p95 shows as an open seam


def seam_gaps(V_sim: np.ndarray, V: np.ndarray, M: dict) -> dict:
    """How far apart the two sides of the seams are (mm), as the sim left them and after the clean-up's weld; `open` =
    sewn pairs still over SEAM_GAP_MM in the finished surface, `worst` = the seam (piece pair) with the widest."""
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    if not len(sw):
        return {}
    out = {}
    for tag, X in (("sim", V_sim), ("final", V)):
        d = np.linalg.norm(X[sw[:, 0]] - X[sw[:, 1]], axis=1) * 1000
        out[tag] = {"p50": round(float(np.median(d)), 2), "p95": round(float(np.percentile(d, 95)), 2),
                    "max": round(float(d.max()), 1)}
    i = int(np.argmax(d))
    out["open"] = int((d > SEAM_GAP_MM).sum())
    out["pairs"] = int(len(d))
    out["worst"] = " / ".join(sorted({M["names"][M["piece"][sw[i, 0]]], M["names"][M["piece"][sw[i, 1]]]}))
    out["ok"] = bool(out["final"]["p95"] <= SEAM_GAP_MM)
    return out


def _seam_relax(X: np.ndarray, M: dict, h: float, stiff: np.ndarray | None, keep: float, passes: int = 6) -> np.ndarray:
    """Welded seams pressed: a sewn seam is a smooth line. Each closed seam's vertices (its two sides as one) are
    smoothed ALONG the seam's own polyline (Laplacian over its neighbours on the seam only, ends kept), never more
    than 2 x `keep` from where the weld left them, and the first ring of cloth beside it follows by half. A solver's
    stitches leave a seam between two soft pieces puckered: a jacket's centre back seam at 2 cm had its vertices
    alternately 4 mm sunk and 5-9 mm proud of the cloth beside them (the pale zigzag down the back). The two sides
    share their samples, so it is not an offset along the seam. Easing each vertex toward its neighbours on all sides
    (the first version) took the median 2.0 -> 0.86 mm and still read as a zigzag. Seams with an interfaced side
    stay (a made edge is where it was made)."""
    sw_all = np.asarray(M["sew"]).reshape(-1, 2)
    ss = np.asarray(M["sew_seam"])
    closed = np.linalg.norm(X[sw_all[:, 0]] - X[sw_all[:, 1]], axis=1) < 1e-6
    if not closed.any():
        return X
    hard = np.zeros(len(X), bool) if stiff is None else np.asarray(stiff) > 0.5
    X0, X = X, X.copy()
    cap = 2.0 * keep
    A_, B_ = _graph(M)
    on_seam = np.zeros(len(X), bool)
    on_seam[sw_all.ravel()] = True
    for si in np.unique(ss):
        rows = np.where(ss == si)[0]
        p = sw_all[rows]  # (in sample order along the seam)
        ok = closed[rows] & ~hard[p].any(1)
        # runs of consecutive closed pairs
        i = 0
        while i < len(p):
            if not ok[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(p) and ok[j + 1]:
                j += 1
            if j - i >= 3:
                q = p[i:j + 1]
                keep_i = np.r_[0, np.where(np.any(q[1:] != q[:-1], axis=1))[0] + 1]  # (a chain's junction: one row)
                q = q[keep_i]
                C = X[q[:, 0]].copy()
                C0 = C.copy()
                for _ in range(passes):
                    C[1:-1] = 0.25 * C[:-2] + 0.5 * C[1:-1] + 0.25 * C[2:]
                    D = C - C0
                    L = np.linalg.norm(D, axis=1)
                    C = C0 + D * np.minimum(1.0, cap / np.maximum(L, 1e-12))[:, None]
                X[q[:, 0]] = C
                X[q[:, 1]] = C
            i = j + 1
    moved = X - X0
    mv = np.linalg.norm(moved, axis=1) > 1e-9
    if mv.any():  # the first ring beside the seam follows by half the mean move of the seam vertices it touches
        acc, cnt = np.zeros_like(X), np.zeros(len(X))
        for a_, b_ in ((A_, B_), (B_, A_)):
            k = mv[b_] & ~on_seam[a_] & ~hard[a_]
            np.add.at(acc, a_[k], moved[b_[k]])
            np.add.at(cnt, a_[k], 1.0)
        r1 = cnt > 0
        X[r1] += 0.5 * acc[r1] / cnt[r1][:, None]
    return X


def _welded_roots(M: dict, X: np.ndarray, tol: float = 1e-6) -> np.ndarray:
    """Per vertex the id of its welded group (the vertices of closed sewn pairs as one; others themselves)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    sw = sw[np.linalg.norm(X[sw[:, 0]] - X[sw[:, 1]], axis=1) <= tol] if len(sw) else sw
    n = len(X)
    A = coo_matrix((np.ones(len(sw)), (sw[:, 0], sw[:, 1])), shape=(n, n))
    _, lab = connected_components(A, directed=False)
    return lab


_KB = {}


def _kb() -> dict:
    if not _KB:
        _KB.update(json.loads((Path(__file__).with_name("garment_kb.json")).read_text()))
    return _KB


def seam_finishes() -> dict:
    """The seam finishes (garment_kb.json seam_finishes): name -> numbers."""
    return {k: v for k, v in _kb()["seam_finishes"].items() if not k.startswith("_")}


def worn_top(g: dict) -> bool:
    """Garment key `worn_top` (default: the kind's, garment_kb.json): torso pieces' tops start where they are worn
    (place(): _worn_top), as tailored garments are built on a form."""
    if "worn_top" in g:
        return bool(g["worn_top"])
    return bool(_kb()["kinds"].get(garment_kind(g) or "", {}).get("worn_top", False))


def garment_kind(g: dict) -> str | None:
    """The garment's kind (garment_kb.json kinds): its design sheet's, else its draft design's."""
    for d in (g.get("design"), g.get("_design")):  # (the compiled garment carries its sheet as "_design")
        if isinstance(d, dict) and d.get("kind"):
            return d["kind"]
    e = expanded(g)
    fr = (e.get("pattern") or {}).get("from") if isinstance(e.get("pattern"), dict) else None
    d = _kb()["designs"].get(fr) if isinstance(fr, str) else None
    if isinstance(d, dict):
        return d.get("kind") or (d.get("kinds") or [None])[0]
    return None


def seam_kinds(M: dict, g: dict) -> dict:
    """{seam index: seam finish name} (garment_kb.json seam_finishes). detail "seam_finish" = the
    garment's default (else its kind's `seam_finish`, else pressed_open); detail "seam_finishes" = {seam index,
    "pieceA/pieceB" or a piece name (".L"/".R" may be left off: both sides): finish} for single seams."""
    det = expanded(g).get("detail") or {}
    kd = _kb()["kinds"].get(garment_kind(g) or "", {})
    base = det.get("seam_finish") or kd.get("seam_finish") or "pressed_open"
    over = det.get("seam_finishes") or {}
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    ss = np.asarray(M["sew_seam"])
    strip = lambda n: n[:-2] if n[-2:] in (".L", ".R") else n
    out = {}
    for si in np.unique(ss):
        r = np.where(ss == si)[0][0]
        nm = {M["names"][M["piece"][sw[r, 0]]], M["names"][M["piece"][sw[r, 1]]]}
        k = base
        for key, v in over.items():
            ks = str(key)
            if ks == str(int(si)):
                k = v
            elif "/" in ks:
                a, b = ks.split("/", 1)
                names = list(nm) * (2 if len(nm) == 1 else 1)
                if ({a, b} == set(nm)) or ({a, b} == {strip(n) for n in nm} and len({strip(n) for n in nm}) == 2) \
                        or (a == b and {strip(n) for n in names} == {a}):
                    k = v
            elif ks in nm or ks in {strip(n) for n in nm}:
                k = v
        if k not in seam_finishes():
            raise ClothError(f"seam finish {k!r} unknown (have {', '.join(seam_finishes())})")
        out[int(si)] = k
    return out


PRESS = {"reach": 0.03, "passes": 40, "cap": 0.4}  # m out from the seam either side; Taubin passes; max move x h


def seam_press_mask(M: dict, g: dict | None) -> np.ndarray:
    """Per sewn pair: is its seam pressed (a pressed seam reads as a fine line, the cloth runs smooth across it)? From
    the garment's seam kinds (`seam_kinds`): every kind but "welt" (a seam made to stand: a corded or piped seam)."""
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    out = np.ones(len(sw), bool)
    if g is None or not len(sw):
        return out
    kinds = seam_kinds(M, g)
    ss = np.asarray(M["sew_seam"])
    for si, k in kinds.items():
        if not seam_finishes().get(k, {}).get("press", True):
            out[ss == si] = False
    return out


def _seam_press(X: np.ndarray, M: dict, h: float, stiff: np.ndarray | None, opts: dict | None = None,
                pressed: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """Seams PRESSED: the surface made smooth ACROSS each closed seam, as a tailor's iron leaves it (and as garment
    artists model it: nearly flat geometry, the line itself in the normal map). A solver's stitch is a free hinge (no
    bending is passed across it), so each side's last row of triangles tilts on its own and the welded seam stands as
    a crease, a ridge with a valley beside it read from across the room: on a 2 cm blazer the two sides' normals met
    at 20-45 deg (side seams 20, centre back 45; the cloth's own neighbouring normals 10). Here the welded mesh's
    vertices within `reach` of a seam (rings, fading out) are Taubin-smoothed (lambda/mu: no shrinking), each welded
    group moved as one, never more than `cap` x h; interfaced vertices (a made collar's edge) stay. `pressed` (per
    sewn pair): seams left out are kept as they are (kind "welt")."""
    o = dict(PRESS, **(opts or {}))
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    if not len(sw):
        return X, {}
    root = _welded_roots(M, X)
    closed = root[sw[:, 0]] == root[sw[:, 1]]
    use = closed if pressed is None else closed & np.asarray(pressed, bool)
    if not use.any():
        return X, {}
    hard = np.zeros(len(X), bool) if stiff is None else np.asarray(stiff) > 0.5
    ur, inv = np.unique(root, return_inverse=True)  # groups 0..G-1
    G = len(ur)
    P = np.zeros((G, 3))
    np.add.at(P, inv, X)
    P /= np.bincount(inv, minlength=G)[:, None]
    hardg = np.zeros(G, bool)
    hardg[inv[hard]] = True
    F = np.asarray(M["F"])
    E = inv[np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]]
    E = np.unique(np.sort(E[E[:, 0] != E[:, 1]], 1), axis=0)
    a, b = E[:, 0], E[:, 1]
    deg = np.bincount(a, minlength=G) + np.bincount(b, minlength=G)
    rings = int(np.clip(np.ceil(o["reach"] / max(h, 1e-4)), 1, 6))
    dist = np.full(G, 99)
    dist[inv[sw[use].ravel()]] = 0
    for r in range(1, rings + 1):
        cur = dist == r - 1
        nb = np.zeros(G, bool)
        nb[a[cur[b]]] = True
        nb[b[cur[a]]] = True
        dist[nb & (dist > r)] = r
    w = np.where(dist <= rings, 1.0 - dist / (rings + 1.0), 0.0)
    w[hardg] = 0.0
    # a vertex on a free edge (a hem's end at the seam) keeps its place across the edge: smoothing it pulls the edge in
    if "border" in M:
        bg = np.zeros(G, bool)
        bg[inv[np.asarray(M["border"], bool)]] = True
        bg[inv[sw.ravel()]] &= False  # (seam vertices are borders of their pieces: they're what moves)
        w[bg] *= 0.3
    if not (w > 0).any():
        return X, {}
    P0 = P.copy()
    cap = float(o["cap"]) * h

    def lap(Q):
        S = np.zeros_like(Q)
        np.add.at(S, a, Q[b])
        np.add.at(S, b, Q[a])
        return S / np.maximum(deg, 1)[:, None] - Q
    # moves along the surface's normal only: a uniform Laplacian on an irregular mesh also slides vertices along the
    # cloth (6 mm along a test seam: a zigzag in plan); a normal's sign doesn't matter in n n^T, but the pieces'
    # windings must agree for the normals not to cancel at the seam (oriented_faces)
    Fo = inv[oriented_faces(M, X)]
    fn = np.cross(P[Fo[:, 1]] - P[Fo[:, 0]], P[Fo[:, 2]] - P[Fo[:, 0]])
    nrm = np.zeros_like(P)
    for k in range(3):
        np.add.at(nrm, Fo[:, k], fn)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    along = lambda D: nrm * np.sum(D * nrm, 1, keepdims=True)
    for _ in range(int(o["passes"])):
        P = P + along((0.5 * w)[:, None] * lap(P))
        P = P - along((0.53 * w)[:, None] * lap(P))
        D = P - P0
        L = np.linalg.norm(D, axis=1)
        P = P0 + D * np.minimum(1.0, cap / np.maximum(L, 1e-12))[:, None]
    mv = np.linalg.norm(P - P0, axis=1)
    Xn = X + (P - P0)[inv]
    return Xn, {"moved_p95_mm": round(float(np.percentile(mv[w > 0], 95) * 1000), 2), "rings": rings,
                "seams": int(len(np.unique(np.asarray(M["sew_seam"])[use])))}


KINK = 0.0015  # m: a draped vertex standing this far out of its neighbours' plane, with its faces turned against them
KINK_MAX = 0.006  # m: the most _unkink moves a vertex in all
KINK_TURN = 25.0  # deg: (KINK) a face this far turned from its neighbours' mean normal is a kink, not a fold's slope


def _unkink(X: np.ndarray, M: dict, stiff: np.ndarray | None = None, rounds: int = 6) -> tuple[np.ndarray, dict]:
    """X with the single-vertex kinks of the sim smoothed out: a draped vertex standing out of its neighbours' plane
    by more than KINK whose triangles are turned more than KINK_TURN from the mean of the triangles round it (a buckle
    a triangle or two across, frozen by the contact solver's strain limit) moved along its normal onto its neighbours'
    mean; fold rows, seam vertices and interfaced cloth stay. A broad fold turns its faces a little each: not a kink.
    The textured look showed them as pale angular shards round a shirt's collar ends (6 mm deep in the sim, 4-5 mm
    after the clean-up's smoothing, which caps every move at `keep`). Returns (X, {"kinks": [per round]})."""
    X = X.copy()
    F = M["F"]
    fixed = np.zeros(len(X), bool)
    fixed[np.asarray(M["sew"]).ravel()] = True
    for fd in M.get("folds") or []:
        for r in fd["rows"]:
            fixed[np.asarray(r)] = True
    if stiff is not None:
        fixed |= np.asarray(stiff) > 0.5
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    a, b = E[:, 0], E[:, 1]
    deg = np.bincount(np.r_[a, b], minlength=len(X)).astype(float)
    hist = []
    X0 = X.copy()
    for _ in range(rounds):
        fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        vn = np.zeros_like(X)
        for c in range(3):
            np.add.at(vn, F[:, c], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        # a face against the normal of its corners' area (the mean over their faces)
        ang = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", fn, vn[F].mean(1) / np.maximum(
            np.linalg.norm(vn[F].mean(1), axis=1, keepdims=True), 1e-12)), -1, 1)))
        turned = np.zeros(len(X), bool)
        turned[F[ang > KINK_TURN].ravel()] = True
        acc = np.zeros_like(X)
        np.add.at(acc, a, X[b])
        np.add.at(acc, b, X[a])
        mean = acc / np.maximum(deg, 1)[:, None]
        off = np.einsum("ij,ij->i", mean - X, vn)
        k = turned & ~fixed & (np.abs(off) > KINK) & (deg > 0)
        hist.append(int(k.sum()))
        if not k.any():
            break
        X[k] += off[k, None] * vn[k]
        # (no vertex goes further than KINK_MAX in all: round after round a sleeve's hem, bunched at the wrist in
        # real folds a triangle across, was walked 15-20 mm flat and squashed: ga_suit su_74 under.R 0.6% crumpled in
        # the sim -> 3.7% after the clean-up, CORRUPT)
        D_ = X - X0
        L_ = np.linalg.norm(D_, axis=1)
        X = X0 + D_ * np.minimum(1.0, KINK_MAX / np.maximum(L_, 1e-12))[:, None]
    return X, {"kinks": hist}


def cleanup(V: np.ndarray, M: dict, body: "Body", opts: dict, stiff: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """The pass artists make after the sim: the fine crinkle (frozen buckles a triangle or two across) smoothed away by
    Taubin passes (a band-limited smoothing that doesn't shrink the cloth: the folds, many triangles across, stay),
    seams welded (both sides at their midpoint), and anything the smoothing pulled toward the body pushed back out to
    `clear`. opts: {"smooth": passes (0 = off), "weld": bool, "clear": m, "keep": m, "seams": bool (welded seams
    smoothed along their line, _seam_relax; default on), "press": bool | {"reach", "passes", "cap"} (the surface made
    smooth ACROSS each seam, _seam_press; default on), "pressed": per sewn pair, which seams are pressed (build
    passes seam_press_mask: kind "welt" isn't)}. stiff (per vertex 0..1, the
    interfacing): interfaced pieces (collars, cuffs, plackets) aren't smoothed: they don't crinkle, and smoothing
    their tight folds and overlaps crumpled them (a cuff 2 -> 6%)."""
    o = dict(CLEANUP, **(opts or {}))
    X = np.asarray(V, float).copy()
    press_info = {}
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
    kink_info = {}
    if o.get("kinks", True):
        X, kink_info = _unkink(X, M, stiff)
    def weld():
        # only seams the sim closed (a gap over 1.5 triangles is a seam it couldn't close: welding it drags cloth).
        # Sewn vertices are welded as GROUPS (a vertex in two seams, three pieces meeting at a point: pair by pair
        # the last pair won and the others stayed open by the solver's few mm: "stitches super visible"), each group
        # at its mean, weighted toward interfaced vertices (a made collar's edge stays, the cloth comes to it)
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        s_ = np.asarray(M["sew"]).reshape(-1, 2)
        s_ = s_[np.linalg.norm(X[s_[:, 0]] - X[s_[:, 1]], axis=1) < 1.5 * h]
        if not len(s_):
            return
        A = coo_matrix((np.ones(len(s_)), (s_[:, 0], s_[:, 1])), shape=(len(X), len(X)))
        _, lab = connected_components(A, directed=False)
        vs = np.unique(s_)
        wv = 1.0 + 20.0 * (np.zeros(len(vs)) if stiff is None else np.clip(np.asarray(stiff, float)[vs], 0, 1))
        _, gi = np.unique(lab[vs], return_inverse=True)
        acc = np.zeros((gi.max() + 1, 3))
        np.add.at(acc, gi, X[vs] * wv[:, None])
        X[vs] = (acc / np.bincount(gi, weights=wv)[:, None])[gi]
    if o["weld"] and len(M["sew"]):
        weld()
        if o.get("seams", True):
            X = _seam_relax(X, M, h, stiff, float(o["keep"]))
        if o.get("press", True):
            X, press_info = _seam_press(X, M, h, stiff, o["press"] if isinstance(o.get("press"), dict) else None,
                                        pressed=o.get("pressed"))
    if o["clear"] and body is not None and len(body.V):
        vn, tree = body.normals()
        _, i = tree.query(X)
        s_ = np.sum((X - body.V[i]) * vn[i], 1)
        bad = s_ < o["clear"]
        bad &= np.linalg.norm(X - body.V[i], axis=1) < 0.05  # only near the body (far vertices: a hang, a drape)
        if bad.any():
            X[bad] = body.push_out(X[bad], o["clear"])
            if o["weld"] and len(M["sew"]):  # (the push moved one side of a seam and not the other)
                weld()
        # the FACES clear too, at their centres and edge midpoints: a 2 cm triangle over a buttock's curve dips
        # between its vertices, and the body showed through as pale specks on tr_11's seat (0.27 mm off at an edge
        # midpoint, the vertices 2-3 mm off)
        # (measured EXACTLY against the body's triangles: Body.clearance, the mean of the 4 nearest vertices along
        # their normal, reads 2.5-3 mm too much on a convex body: tr_11 read 1.5 mm where the cloth was 0.5 mm inside
        # the body at the knee's side and on the seat, the specks)
        from .closures import _closest_on
        F_ = np.asarray(M["F"])
        vnb, treeb = body.normals()
        for _ in range(4):
            Pf = np.concatenate([X[F_].mean(1), 0.5 * (X[F_[:, 0]] + X[F_[:, 1]]), 0.5 * (X[F_[:, 1]] + X[F_[:, 2]]),
                                 0.5 * (X[F_[:, 2]] + X[F_[:, 0]])])
            nearb = treeb.query(Pf)[0] < 0.05
            cl_ = np.full(len(Pf), np.inf)
            if nearb.any():
                Qb, _, _ = _closest_on(Pf[nearb], body.V, body.T, k=16)
                sg = np.sign(np.sum((Pf[nearb] - Qb) * vnb[treeb.query(Qb)[1]], 1))
                cl_[nearb] = np.linalg.norm(Pf[nearb] - Qb, axis=1) * np.where(sg == 0, 1.0, sg)
            short = 0.5 * o["clear"] - cl_
            if short.max() <= 1e-4:
                break
            fi = np.tile(np.arange(len(F_)), 4)
            add = np.zeros(len(X))
            for c in range(3):
                np.maximum.at(add, F_[fi, c], np.maximum(short, 0.0))
            mv = add > 0  # out along the body's normal by the shortfall (push_out reads the biased measure)
            X[mv] += vnb[treeb.query(X[mv])[1]] * add[mv, None]
            if o["weld"] and len(M["sew"]):
                weld()
    moved = np.linalg.norm(X - V, axis=1)
    return X, {"passes": n, **({"press": press_info} if press_info else {}), **kink_info, "moved_p95_mm": round(float(np.percentile(moved, 95) * 1000), 2),
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
    R0 = res.get("rest", X0)  # placement "smooth": the flat pattern (made pieces as placed)
    eds = [(0, 1), (1, 2), (2, 0)]
    tri = np.max([np.linalg.norm(V[F_[:, a]] - V[F_[:, b]], axis=1) /
                  np.maximum(np.linalg.norm(R0[F_[:, a]] - R0[F_[:, b]], axis=1), 1e-9) for a, b in eds], axis=0) - 1
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
    # fold rows too (a folded placket's, a closure band's): a 1-3 mm wedge of layers crushed across the row and
    # stretched along it (row 0.3x, along 1.5-2.3x) is construction, not fit; on Simon's fronts they are the
    # worst triangles of su_05 ("STRAINED at waist 17.8%" at +23% waist ease; the pieces' interiors p95 1.5-2%)
    for fd in M.get("folds") or []:
        for row in fd.get("rows") or []:
            seamv[np.asarray(row, np.int64)] = True
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
    # girths round the body pieces (not the sleeves; trouser legs are: their seat and hips are the body's)
    tors = [k for k, nm in enumerate(M["names"])
            if str(res["pieces"]["pieces"][nm]["wrap"].get("to", "torso")).split(".")[0] in ("torso", "leg")]
    garment_T = M["F"][np.isin(M["piece"][M["F"][:, 0]], tors)]
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
        if gg < 0.6 * bb:  # (the slice caught only a band standing above that girth: the trousers read "waist -555 mm")
            continue
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
    # a band closed on itself (a waistband buttoned round the waist) measures its own girth, not the body pieces'
    own = {a.split(":")[0] for a, b in B.get("stitches", []) if a.split(":")[0] == b.split(":")[0]}
    from . import garment_design
    under = ("facing", "lining", "pocket", "interfacing")  # layers inside the shell add no girth
    torso = [nm for nm in pcs if pcs[nm]["wrap"].get("to") == "torso" and nm not in own
             and garment_design.role_of(nm, pcs[nm]) not in under]
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
        # a panel that starts under the arm (a jacket's side panel: its top IS the armhole's base) lies below the
        # body's chest line: measured there, the girth misses the whole panel and what is under the arm is armhole,
        # not garment (Jaeger read -116 mm "TOO SMALL" and settled at +208). The chest is then taken just under
        # that panel's top
        y_cap = None
        if reg == "chest":
            yb = body.at[zk] - hps_z
            tops = [float(pcs[nm]["P"][:, 1].max()) for nm in torso
                    if not pcs[nm]["wrap"].get("align") and not pcs[nm]["wrap"].get("level")]
            low = [t for t in tops if yb - 0.15 < t < yb]
            if low:  # (3 cm under its top: the top is the armhole's U, whose horns alone are a few mm wide)
                y_cap = min(low) - 0.03
        for nm in torso:
            P = pcs[nm]["P"]
            dz = 0.0
            al = pcs[nm]["wrap"].get("align")
            if al:  # a piece hung from another's point (a coat's skirt): its own pattern y is shifted
                mine, other, op = al
                dz = float(pcs[other]["P"][pcs[other]["names"][op], 1] - P[pcs[nm]["names"][mine], 1])
            if pcs[nm]["wrap"].get("level"):  # pattern y = 0 at that body line
                dz += float(body.at[f"{pcs[nm]['wrap']['level']}_z"]) - float(pcs[nm]["wrap"].get("drop", 0.0)) - hps_z
            L = pcs[nm]["lines"].get(reg)
            y = float(np.mean(L[:, 1])) if L is not None else body.at[zk] - hps_z - dz  # the draft's line, or the
            # body's height (pattern y, hps at 0); the chest at the armhole's bottom (where a chest line ends: the
            # outline is still curving in at the line's own height)
            if reg == "chest" and "armhole" in pcs[nm]["names"]:
                y = float(P[pcs[nm]["names"]["armhole"], 1]) - 0.002
            if y_cap is not None:
                y = min(y, y_cap)
            wi = _piece_width_at(P, y)
            half = pcs[nm]["wrap"].get("half")
            if wi > 0 and (half or abs(P[:, 0].min() + P[:, 0].max()) > 0.05):
                # a piece drawn from its centre line out (x = 0 the centre front/back): what lies past the centre
                # is an overlap (a closure, a lapel, a pleat's underlay), not girth
                xs = []
                for a_, b_ in zip(P, np.roll(P, -1, axis=0)):
                    if (a_[1] - y) * (b_[1] - y) <= 0 and a_[1] != b_[1]:
                        xs.append(a_[0] + (y - a_[1]) / (b_[1] - a_[1]) * (b_[0] - a_[0]))
                if xs:
                    sgn = float(half) if half else 1.0 if P[:, 0].max() > -P[:, 0].min() else -1.0
                    # (a side panel that starts off the centre measures from its own inner edge)
                    wi = max(0.0, max(sgn * x for x in xs) - max(min(sgn * x for x in xs), 0.0))
            # cloth folded away in a pleat is not girth (pattern_styles pleat: "underlays" [{y: [lo, hi], width}])
            for ul in pcs[nm].get("underlays") or []:
                if ul["y"][0] - 1e-9 <= y <= ul["y"][1] + 1e-9:
                    wi = max(0.0, wi - float(ul["width"]) * (2.0 if (not half and abs(P[:, 0].min() + P[:, 0].max()) <= 0.05) else 1.0))
            per[nm] = round(wi * 1000, 1)
            w += wi
        if w <= 0:  # the garment doesn't reach that girth (a skirt has no chest)
            continue
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
                "sew_force", "sew_frames", "worn_frames", "settle_frames", "hang_frames", "hang_sew_force", "hang_air", "refine_frames",
                "refine_ease", "cleanup", "detail", "sculpt", "note", "backend", "placement", "lower_arms", "lower_frames", "zozo", "_trace",
                "design", "folds", "generate", "method", "made", "fine_settle", "tacks", "over", "layer_gap", "support", "export_hidden", "hidden_margin", "under_cap", "closures", "trims", "tie", "collide", "made_folds", "worn_top", "press_lay", "worn_envelope", "collar_spread", "open_gap"}
WRAPS = ("torso", "arm.L", "arm.R", "leg.L", "leg.R", "neck", "head", "seam", "flat")


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
        if g.get("design") is not None:  # the staged workflow's design sheet: checked, then what it compiles into
            from . import garment_design
            garment_design.validate(g["design"], where)
            g = expanded(g)
        from . import garment_blocks
        pat = g.get("pattern")
        if pat is None and not g.get("pieces"):
            raise ClothError(f'{where}: needs "pattern": {{"from": design}} ({", ".join(names + list(garment_blocks.BLOCKS))}) '
                             'or own "pieces" + "seams", or a "design" sheet (design_garment)')
        if pat is not None and isinstance(pat, dict) and pat.get("from") in garment_blocks.BLOCKS:
            okp = {"from", "options", "measurements"} | set(garment_blocks.WORDS[pat["from"]])
            bad = set(pat) - okp
            if bad:
                raise ClothError(f"{where}: pattern keys {sorted(bad)} unknown for {pat['from']} (have {sorted(okp)})")
        elif pat is not None:
            if not isinstance(pat, dict) or pat.get("from") not in names:
                raise ClothError(f'{where}: pattern is {{"from": one of {names + list(garment_blocks.BLOCKS)}, "ease": {{...}}, "length"...}}')
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
            bad = set(f) - set(FABRICS["shirting"]) - {"preset", "quality", "sewing", "stiff_tension", "rest", "physical"}
            if bad:
                raise ClothError(f"{where}: fabric keys {sorted(bad)} unknown (have {sorted(FABRICS['shirting'])})")
        else:
            raise ClothError(f"{where}: fabric is a preset name or {{\"preset\", overrides}}")
        st = g.get("state", "worn")
        if isinstance(st, dict):
            if len(st) != 1 or next(iter(st)) not in ("hang", "drape"):
                raise ClothError(f'{where}: state is "worn", "hung", "draped", {{"hang": {{...}}}} or {{"drape": {{...}}}}')
            if "hang" in st:
                hg = st["hang"] or {}
                if not hg.get("pins"):  # on a hanger (the way a person hangs it)
                    from . import hanger as hangmod
                    bad = set(hg) - {"hanger", "rail"}
                    if bad:
                        raise ClothError(f'{where}: hang is {{"hanger": {{...}}, "rail": {{...}} | false}} (or the old '
                                         f'pinned {{"pins", "hook", "rack"}}); unknown {sorted(bad)}')
                    hangmod.validate(hg, where)
                elif not (isinstance(hg.get("hook"), list) and len(hg["hook"]) == 3):
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
        if g.get("method", "simulate") not in ("simulate", "settle"):
            raise ClothError(f'{where}: method is "simulate" (sew and simulate everything) or "settle" (made pieces '
                             "constructed finished, the loose cloth settled lightly)")
        if g.get("over") is not None:  # layered: worn over another garment of this model
            seen, cur = [gn], g.get("over")
            while cur is not None:
                if not isinstance(cur, str) or cur not in gs:
                    raise ClothError(f"{where}: over {cur!r} isn't a garment of this model (have {', '.join(gs)})")
                if cur in seen:
                    raise ClothError(f"{where}: over runs in a circle ({' -> '.join(seen + [cur])})")
                seen.append(cur)
                cg = gs[cur]
                cur = expanded(cg).get("over") if isinstance(cg, dict) else None
            if isinstance(_state(g), dict) or isinstance(_state(gs[g["over"]]), dict):
                raise ClothError(f'{where}: over needs both garments worn (state "worn"): a hung or draped garment '
                                 "has no body under it to share")
        for e in g.get("support") or []:
            kd = e if isinstance(e, str) else (e or {}).get("kind") if isinstance(e, dict) else None
            if kd not in SUPPORTS:
                raise ClothError(f"{where}: support {e!r}: a kind name or {{\"kind\", ...}} of {', '.join(SUPPORTS)}")
            if isinstance(e, dict) and set(e) - {"kind"} - set(SUPPORTS[kd]):
                raise ClothError(f"{where}: support {kd} takes {', '.join(SUPPORTS[kd])}")
        if g.get("closures") is not None:
            from . import closures as closuremod
            try:
                closuremod.validate(g["closures"], f"{where} closures")
            except closuremod.ClosureError as e:
                raise ClothError(str(e))
        if g.get("trims") is not None:
            from . import cloth_trims
            try:
                cloth_trims.validate(g["trims"], f"{where} trims")
            except cloth_trims.TrimError as e:
                raise ClothError(str(e))
        if "layer_gap" in g and not (isinstance(g["layer_gap"], (int, float)) and 0 <= g["layer_gap"] <= 0.03):
            raise ClothError(f"{where}: layer_gap is the air between the layers at the start in m (0..0.03)")
        if g.get("quality", "final") not in ("draft", "final"):
            raise ClothError(f'{where}: quality is "draft" (one coarse sim, ~1 min) or "final" (coarse then refined)')
        for k, lo, hi in (("resolution", 0.004, 0.05), ("coarse", 0.008, 0.05)):
            if k in g and not (isinstance(g[k], (int, float)) and lo <= g[k] <= hi):
                raise ClothError(f"{where}: {k} is a triangle size in m ({lo}..{hi})")
        if g.get("placement", "fitted") not in ("fitted", "smooth"):
            raise ClothError(f'{where}: placement is "fitted" (Blender\'s default: the start is the rest shape, folds '
                             'and fins laid isometrically) or "smooth" (ZOZO\'s default: rests on the flat pattern)')
        if g.get("backend", "blender") not in ("blender", "zozo", "file", "remote"):
            raise ClothError(f'{where}: backend is "blender" (default), "zozo" (ZOZO\'s contact solver, here or on a GPU '
                             'box), "file" (write the job, wait for its result) or "remote" ($HIFIPUSHIE_CLOTH_REMOTE '
                             'runs it): see cloth_job.py')
        if g.get("placement") == "smooth" and cloth_job_backend(g) == "blender":
            raise ClothError(f'{where}: placement "smooth" needs backend "zozo" (Blender rests on the placement)')
        if "zozo" in g and not isinstance(g["zozo"], dict):
            raise ClothError(f'{where}: zozo is a dict of solver options (contact_gap, strain_limit, dt, ...: '
                             'cloth_zozo.py)')
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
    if st == "hung":  # on the default hanger, on a rail
        return {"hang": {"hanger": {}}}
    return st


def model_body(name: str, spec: dict, g: dict, simulate: bool = True) -> dict:
    """The collider a garment settles on: the model's base body (worn, hung: dressed on it first), or for a drape
    over the "model" the model's whole built surface (a table under a tablecloth, a bed under a blanket)."""
    st = _state(g)
    over = st["drape"].get("over", "model") if isinstance(st, dict) and "drape" in st else "body"
    if over == "body" and spec.get("base"):
        src = body_mesh(spec=spec)
        ug = expanded(g).get("over")
        if ug:  # layered: the garment under this one, finished, joins the body as a frozen collider
            if ug not in (spec.get("cloth") or {}):
                raise ClothError(f"over: no garment {ug!r} in this model's cloth (have {', '.join(spec.get('cloth') or {})})")
            u = spec["cloth"][ug]
            ures = build(_garment_for_sim(u), model_body(name, spec, u, simulate), f"{name}:{ug}",
                         log=lambda *_: None, cached_only=not simulate)
            src = dict(src, under=None if ures is None else {"V": ures["V"], "F": ures["mesh"]["F"], "key": ures["key"],
                                                              "name": ug, "res": ures})
            if ures is None:
                src["under_missing"] = ug
        if expanded(g).get("collide"):
            src = dict(src, worn=worn_parts(name, spec, list(expanded(g)["collide"])))
        return src
    from . import spec as specmod, store
    meta = store.build(name, int((st.get("drape") or {}).get("resolution", 192)) if isinstance(st, dict) else 192)
    z = np.load(store._dir(name) / "build" / "mesh.npz")
    se = specmod.expand_mirror(spec)
    J = {k: np.asarray(v["pos"], float) for k, v in se.get("joints", {}).items() if isinstance(v.get("pos"), list)}
    return {"V": np.asarray(z["verts"], float), "F": np.asarray(z["faces"]), "J": J, "key": f"model:{meta.get('key')}"}


WORN_VOXEL = 0.005  # m: the voxel worn parts (garment key "collide") are meshed at for the collider


def worn_parts(name: str, spec: dict, parts: list) -> dict:
    """The model's own parts a garment rests on (garment key "collide": ["shoes", "soles"] under a trouser hem), meshed
    in a box round their elements (store.build's close-up at WORN_VOXEL), as one triangle mesh {"V", "F", "key"}.
    A hem that ends on the foot without them stood off the bare foot as a ring: no vamp to break over."""
    from . import spec as specmod, store
    se = specmod.expand_mirror(spec)
    have = set((spec.get("parts") or {}).keys())
    bad = [p_ for p_ in parts if p_ not in have]
    if bad:
        raise ClothError(f"collide: no part {', '.join(bad)} in this model (have {', '.join(sorted(have))})")
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    J = {k: np.asarray(v["pos"], float) for k, v in se.get("joints", {}).items() if isinstance(v.get("pos"), list)}
    for kind in ("blobs", "bones"):
        for e in (se.get(kind) or {}).values():
            if e.get("part") not in parts:
                continue
            if kind == "blobs":
                at = e.get("at")
                c = np.asarray(at, float) if isinstance(at, list) else J.get(at) if isinstance(at, str) else None
                if c is None:
                    continue
                r = float(np.max(e.get("size", [0.05]))) * 1.8 + float(e.get("blend", 0.0)) + 0.01
                pts = [c - r, c + r]
            else:
                pts = [J[e[j]] + sg * (float(max(e.get("r_a", 0.05), e.get("r_b", 0.05))) + 0.01)
                       for j in ("a", "b") if e.get(j) in J for sg in (-1, 1)]
            for q in pts:
                lo, hi = np.minimum(lo, q), np.maximum(hi, q)
    if not np.isfinite(lo).all():
        raise ClothError(f"collide: no elements of {', '.join(parts)} with a position to box them")
    lo, hi = lo - 0.02, hi + 0.02
    res = int(np.ceil(float((hi - lo).max()) / WORN_VOXEL))
    info = store.build(name, res, box=(lo, hi))
    z = np.load(info["mesh"])
    names_ = [str(n) for n in z["part_names"]]
    on = np.isin(z["part"], [names_.index(p_) for p_ in parts if p_ in names_])
    Fz = np.asarray(z["faces"], np.int64)
    Fz = Fz[on[Fz].all(1)]
    keep = np.unique(Fz)
    remap = np.full(len(on), -1)
    remap[keep] = np.arange(len(keep))
    return {"V": np.asarray(z["verts"], float)[keep], "F": remap[Fz], "key": f"{info['key']}:{','.join(parts)}"}


def _garment_for_sim(g: dict) -> dict:
    """The garment as build() takes it: its design sheet compiled, the named states turned into their objects."""
    g = expanded(g)
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
    src = model_body(name, spec, g, simulate=False)
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
    if res.get("hanger_line"):
        L.append("  hanger: " + res["hanger_line"])
    if res.get("sleeves"):
        L.append("  sleeves from vertical (cap top -> hem centre; hanging straight is under ~5 deg): " + ", ".join(
            f"{k} {v:.1f} deg" for k, v in res["sleeves"].items()))
    sh = res["shape"]
    L.append(f"  surface (sim -> final): crinkle {sh['sim']['crinkle_deg']} -> {sh['final']['crinkle_deg']} deg median "
             f"between neighbouring triangles (smooth cloth reads ~3-5), {sh['sim']['crinkle_mm']} -> "
             f"{sh['final']['crinkle_mm']} mm fine waviness; folds {sh['sim']['folds_mm']} -> {sh['final']['folds_mm']} mm "
             "(rms height of folds narrower than ~15 cm; a 20 mm-deep 10 cm fold reads ~9; 2-4 hangs close to the body)")
    s = sh["sim"]
    # what reads first in a render: the sim's own surface (crinkle the clean-up has to smooth away), then fold depth.
    # The user picked a smooth 1 cm Newton shirt (sim crinkle 2.9 deg, strain p95 18%) over Blender's (7.7 deg, 1%):
    # strain is a fit number, not the look
    rd = "smooth" if s["crinkle_deg"] < 4 else "some crinkle" if s["crinkle_deg"] < 7 else "crinkly"
    fd = "flat (few folds)" if s["folds_mm"] < 2.5 else "soft folds" if s["folds_mm"] < 6 else "deep folds"
    L.append(f"  reads (judge renders first): sim surface {rd} ({s['crinkle_deg']} deg), {fd} ({s['folds_mm']} mm); "
             "rank looks by these before strain")
    cu = res.get("cleanup") or {}
    L.append(f"  clean-up: {cu.get('passes', 0)} smoothing passes, moved p95 {cu.get('moved_p95_mm')} mm"
             + (f"; the fine settle tangled {res['kept_coarse']}: kept the coarse drape there" if res.get("kept_coarse") else "")
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
                     "allows and crumples; lower it (the design's stand/collar width option, e.g. simon \"options\": "
                     "{\"collarStandWidth\": 0.045}, default 0.08)")
    sg = res.get("seam_gaps")
    if sg:
        L.append(f"  {'ok ' if sg['ok'] else '!! '}seams: sides apart p50 {sg['final']['p50']} / p95 {sg['final']['p95']} / max "
                 f"{sg['final']['max']} mm after the clean-up (the sim left {sg['sim']['p50']} / {sg['sim']['p95']} / "
                 f"{sg['sim']['max']}; closed <= {SEAM_GAP_MM} at p95)"
                 + ("" if not sg["open"] else f"; {sg['open']} of {sg['pairs']} sewn pairs still OPEN, widest at {sg['worst']}"))
    if res.get("closures"):
        from . import closures as closuremod
        L.append(closuremod.text(res["closures"]))
        for r_ in res.get("closures_seat") or []:
            sim_ = next((x for x in res.get("closures_sim") or [] if x["name"] == r_["name"]), {})
            L.append(f"     lap {r_['name']} laid closed after the sim: {r_['laid']} vertices of the over band moved "
                     f"{r_['moved_p50_mm']} mm (median; most {r_['moved_max_mm']}) onto the under layer; the sim had left "
                     f"its fastenings up to {sim_.get('gap_max_mm')} mm apart"
                     + (f"; {r_['kept_back']} vertices kept back (laid, they crossed the cloth)" if r_.get("kept_back") else "")
                     + (f" ({r_['reverted']}: not applied)" if r_.get("reverted") else ""))
    if res.get("tells"):
        from . import cloth_layers
        L.append("  layered over " + str((res.get("under") or {}).get("name")) + ":")
        L.append(cloth_layers.tells_text(res["tells"]).replace("\n", "\n  "))
    return "\n".join(L)


# ---------------------------------------------------------------- detail: seams, topstitching, hems, buttons

DETAIL = {"thread": None, "button": None, "seam_finish": None, "seam_finishes": None,
          "seam": None, "seam_width": None, "allowance": None, "topstitch": None, "stitch": 0.003,
          "stitch_gap": 0.0015, "stitch_depth": 0.0003, "hem": 0.02, "hem_height": 0.0007, "buttons": True,
          "texture": 2048, "folds": None, "fold_gain": 1.0, "fold_opts": None}
# seam_finish / seam_finishes: how seams are finished (garment_kb.json seam_finishes; seam_kinds); seam, seam_width,
# allowance: override every finish's groove depth, groove half width, allowance rise (m; None = the finish's own);
# topstitch: the row on free edges (hems), None = the garment kind's hem default (hem_topstitch)


def hem_topstitch(g: dict) -> float:
    """The topstitching row's distance in from a free edge (m) the garment's kind hems with: 0 for blind-stitched
    hems (tailored jackets, coats, suit trousers, skirts), else 6 mm."""
    kd = _kb()["kinds"].get(garment_kind(g) or "", {})
    ch = (kd.get("details") or {}).get("hem")
    det = ((_kb()["details"].get("hem") or {}).get(ch) or {}).get("detail") or {}
    return float(det.get("topstitch", 0.006))


def fine_folds(res: dict, g: dict, uv: np.ndarray, side: float, texture: int | None = None):
    """The fine folds authored from the drape (cloth_detail.wrinkle_height: where the sim's cloth is left compressed,
    real cloth has folds finer than the mesh), as a height map on the atlas for detail_maps(extra=...). On for method
    "settle", or detail {"folds": true}; detail "fold_gain" scales their depth, "fold_opts" overrides the fabric's
    fold sizes. None when off."""
    o = dict(DETAIL, **(expanded(g).get("detail") or {}))
    want = o["folds"] if o["folds"] is not None else method_of(expanded(g)) == "settle"
    if not want:
        return None
    from . import cloth_detail
    T = int(texture or o["texture"])
    Vd = res["V_drape"] if res.get("V_drape") is not None else res["V_sim"]
    fabn = res["fabric"].get("name", "shirting")
    if res.get("fold_dabs") is None:
        res["fold_dabs"], res["fold_info"] = cloth_detail.fold_dabs(
            res["mesh"], Vd, fabn, interfacing(res["pieces"], res["mesh"]), float(o["fold_gain"]), opts=o["fold_opts"])
    # (the big folds are in the geometry when the build put them there: the map takes the fine ones only)
    H, info = cloth_detail.wrinkle_height(res["mesh"], Vd, uv, side, T, fabn, opts=o["fold_opts"], dabs=res["fold_dabs"],
                                          big=False if res.get("folds_in_geometry") else None)
    res["fine_folds"] = dict(res.get("fold_info") or {}, **info)
    return H


def _closure_bands(M: dict, uv: np.ndarray, side: float, T: int, px, inside: np.ndarray):
    """The closures' bands and buttonholes on the atlas: (bands [(zone (T, T) bool: the band's texels, distance (m)
    from the closure edge, band width, finish, topstitch)], an empty band mask, holes [(x, y) px, axis (pattern),
    length (m), vertex])."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    from . import closures as closuremod
    mpt = side / T
    bands, holes = [], []
    for c in M.get("closures") or []:
        exy = c.get("edge_xy") or {}
        fin = c.get("finish") or {"over": "box", "under": "french"}
        ts = float(c.get("topstitch", 0.003))
        for sd in ("over", "under"):
            if sd == "under" and c["under"] == c["over"]:
                continue
            band = c.get("band")
            w = band.get(sd) if isinstance(band, dict) else band
            if not w or exy.get(sd) is None or c[sd] not in M["names"]:
                continue
            k_ = M["names"].index(c[sd])
            ring = np.where((M["piece"] == k_) & M["border"])[0]
            vs_ = np.where(M["piece"] == k_)[0]
            if len(ring) < 3 or not len(vs_):
                continue
            off_ = uv[vs_[0]] * side - M["uv"][vs_[0]]  # the piece's place in the atlas (one scale, no turn)
            Q = (np.asarray(exy[sd], float) + off_) / side
            pm = Image.new("L", (T, T), 0)
            ImageDraw.Draw(pm).polygon([px(uv[i]) for i in ring], fill=255)
            pm = np.asarray(pm) > 0
            em = Image.new("L", (T, T), 0)
            ImageDraw.Draw(em).line([px(q) for q in Q], fill=255, width=1)
            ys, xs = np.where(pm)
            if not len(ys):
                continue
            pad = int(float(w) / mpt) + 8
            sub = (slice(max(ys.min() - pad, 0), min(ys.max() + pad + 1, T)), slice(max(xs.min() - pad, 0), min(xs.max() + pad + 1, T)))
            db = np.full((T, T), 1.0, np.float32)
            db[sub] = ndimage.distance_transform_edt(np.asarray(em)[sub] == 0) * mpt
            zone = pm & inside & (db <= float(w) + 0.004)
            bands.append((zone, db, float(w), fin.get(sd, "plain"), ts))
        if c.get("kind") == "buttons":
            for va, vb in c.get("v") or []:
                hx, hy = px(uv[va])
                holes.append((hx, hy, closuremod.hole_axis(c, M, va, vb), float(c.get("size", 0.011)) + 0.003, int(va)))
    return bands, np.zeros((T, T), bool), holes


def detail_maps(M: dict, uv: np.ndarray, side: float, g: dict, texture: int | None = None, extra=None) -> dict:
    """The sewing details a garment artist sculpts or stamps after the sim, drawn from the pattern itself into maps on
    the flat-pattern atlas: a groove along every sewn edge with the seam allowance's ridge beside it, a dashed
    topstitch line `topstitch` in from every edge (seams and hems), a turned-up hem `hem` deep along free edges (the
    doubled cloth a little proud), and buttons (raised discs with four holes) on marks named button*, buttonholes as
    stitched slots. Returns {"height" (m, float), "normal" (uint8 RGB, tangent space +Y up the image), "cavity"
    (0..1, darkening in grooves), "thread" (0..1 where stitches show), "texels_per_m"}."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    o = dict(DETAIL, **(expanded(g).get("detail") or {}))
    T = int(texture or o["texture"])
    mpt = side / T  # metres per texel
    px = lambda q: (q[0] * T, (1 - q[1]) * T)
    sewn = np.zeros(len(M["uv"]), bool)
    if len(M["sew"]):
        sewn[M["sew"].ravel()] = True
    # per sewn vertex its seam and side (0: the seam's first piece, 1: its second, the side a seam pressed to one side
    # lies toward), and each seam's finish (seam_kinds: garment_kb.json seam_finishes)
    sw_ = np.asarray(M["sew"]).reshape(-1, 2)
    vseam = np.full(len(M["uv"]), -1)
    vside = np.zeros(len(M["uv"]), int)
    if len(sw_):
        ss_ = np.asarray(M["sew_seam"])
        vseam[sw_[:, 0]], vside[sw_[:, 0]] = ss_, 0
        vseam[sw_[:, 1]], vside[sw_[:, 1]] = ss_, 1
    kinds = seam_kinds(M, g) if len(sw_) else {}
    fin_all = seam_finishes()
    codes = [None, None]  # L code -> (finish numbers, side); 0 none, 1 free edge
    inside = Image.new("L", (T, T), 0)
    di = ImageDraw.Draw(inside)
    L = np.zeros((T, T), np.int32)  # 1 free edge, 2+ a seam edge (codes: its finish and side)
    code_of = {}
    A = np.zeros((T, T), np.float32)  # arc length along the piece's outline (m): stitches are dashes along it
    for k in range(len(M["names"])):
        ring = np.where((M["piece"] == k) & M["border"])[0]
        if len(ring) < 3:
            continue
        di.polygon([px(uv[i]) for i in ring], fill=255)
        arc = 0.0
        for a, b in zip(ring, np.roll(ring, -1)):
            if sewn[a] and sewn[b]:
                si_ = int(vseam[a] if vseam[a] >= 0 else vseam[b])
                ck = (kinds.get(si_, "pressed_open"), int(vside[a]))
                if ck not in code_of:
                    code_of[ck] = len(codes)
                    codes.append((fin_all[ck[0]], ck[1]))
                kind = code_of[ck]
            else:
                kind = 1
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
    free = kind == 1
    # dashes along the outline (topstitching): each stitch a small dent
    per = o["stitch"] + o["stitch_gap"]
    s_ = A[iy, ix] % per  # along the outline at the nearest edge point
    dash = np.clip((o["stitch"] - np.abs(2 * s_ - o["stitch"])) / (1.5 * mpt + 1e-9), 0, 1).astype(np.float32)
    row = lambda at: np.exp(-((d - at) / max(0.0004, 1.2 * mpt)) ** 2)
    thread = np.zeros((T, T), np.float32)
    # a sewn edge, by its finish (garment_kb.json seam_finishes): a fine groove where the two pieces meet, the
    # allowances under the cloth a faint broad rise (both sides when pressed open, the toward side when pressed to one
    # side), its rows of topstitching. A groove narrower than a texel can't be drawn: it is held to 0.8 texel (the
    # normal map would alias it into dashes). detail seam / seam_width / allowance set override every finish.
    for c in range(2, len(codes)):
        m = kind == c
        if not m.any():
            continue
        fin, sd = codes[c]
        gr = o["seam"] if o["seam"] is not None else fin["groove"]
        gw = max(o["seam_width"] if o["seam_width"] is not None else fin["groove_width"], 0.8 * mpt)
        al = o["allowance"] if o["allowance"] is not None else fin["allowance"]
        mine = fin["sides"] == "both" or sd == 1
        H -= np.where(m, gr * np.exp(-(d / gw) ** 2), 0)
        if mine and al:
            aw = max(fin["allowance_width"], 1.5 * mpt)
            H += np.where(m, al * np.exp(-((d - fin["allowance_at"]) / aw) ** 2), 0)
        if mine:
            for r_ in fin["rows"]:
                t_ = np.where(m, row(r_) * dash, 0).astype(np.float32)
                thread = np.maximum(thread, t_)
                H -= o["stitch_depth"] * t_
    # closures' bands (closures.py), each as its `finish` makes it, from the closure's edge (its piece's pattern
    # polyline carried into the atlas): what lies in a band is drawn by the band, not as a turned hem
    bands, bandzone, holes_done = _closure_bands(M, uv, side, T, px, inside)
    for z_, _db, _w, _f, _ts in bands:
        bandzone |= z_
    free = free & ~bandzone
    # a free edge: a turned hem, the doubled cloth proud up to `hem` in, its fold rounded at the edge
    if o["hem"]:
        hem = np.clip((o["hem"] - d) / (0.15 * o["hem"]), 0, 1) * np.clip(d / 0.0015, 0, 1)
        H += np.where(free, o["hem_height"] * hem, 0)
    # topstitching on free edges (hems, a collar's or a cuff's edge): a dashed line `topstitch` in (a blind-stitched
    # hem, a tailored jacket's or trousers', shows none: the kind's hem default says 0)
    ts = o["topstitch"] if o["topstitch"] is not None else hem_topstitch(g)
    if ts:
        t_ = np.where(free, row(ts) * dash, 0).astype(np.float32)
        thread = np.maximum(thread, t_)
        H -= o["stitch_depth"] * t_
    # the bands: a box placket stands its three layers proud (rounded at its folded outer edge, a crisp fold at the
    # inner edge where the tuck turns under, a faint shadow just past it) with a row of topstitching `topstitch` in
    # from each edge; a French front only rounds its folded edge (the facing is inside: no rows); a faced edge has one
    # row. (Real heights: shirting ~0.3 mm a layer; a sub-millimetre step reads only as the normal map's crisp line.)
    sstep = lambda x: (lambda t: t * t * (3 - 2 * t))(np.clip(x, 0, 1))
    rowb = lambda db, at: np.exp(-((db - at) / max(0.0004, 1.2 * mpt)) ** 2)
    shadow = np.ones((T, T), np.float32)  # darkening the relief alone can't give (stitch dimples, a slit, the tuck)
    s_b = A[iy, ix] % 0.0025  # band topstitching: a shirt's fine stitch (~10 per inch: 2 mm stitches, 0.5 mm apart)
    dash_b = np.clip((0.002 - np.abs(2 * s_b - 0.002)) / (1.5 * mpt + 1e-9), 0, 1).astype(np.float32)
    for z_, db, w, fin, ts in bands:
        if fin == "plain":
            continue
        rise = sstep(db / 0.0012)
        if fin == "box":
            h_ = 0.0006 * rise * (1 - sstep((db - w) / 0.0008 + 0.5))
            h_ -= 0.00025 * np.exp(-((db - w - 0.0007) / 0.0006) ** 2)  # the tuck's shadow past the inner fold
            rows_ = [ts, w - ts]
        elif fin == "french":
            h_ = 0.0004 * rise * (1 - sstep((db - w) / 0.004 + 0.5))
            rows_ = []
        else:  # facing
            h_ = 0.0004 * rise * (1 - sstep((db - w) / 0.004 + 0.5))
            rows_ = [ts]
        H += np.where(z_, h_, 0).astype(H.dtype)
        if fin == "box":  # the tuck under the inner fold throws a thin shadow on the front beside it
            # (wide enough to survive the mip levels at outfit distance: the concept reads the band by its two edges)
            shadow *= np.where(z_, 1 - 0.22 * np.exp(-((db - w - 0.0008) / 0.0011) ** 2), 1).astype(np.float32)
            shadow *= np.where(z_, 1 - 0.1 * np.exp(-((db - 0.0006) / 0.0008) ** 2), 1).astype(np.float32)  # the folded edge's shoulder
        for r_ in [r_ for r_ in rows_ if r_ > 0]:  # (topstitch 0: none, a tailored jacket's front)
            t_ = np.where(z_, rowb(db, r_) * dash_b, 0).astype(np.float32)
            thread = np.maximum(thread, t_)
            H -= o["stitch_depth"] * t_
            # the row pulls the layers together: a fine shadowed line either side of the stitches
            shadow *= np.where(z_, 1 - 0.12 * np.exp(-((db - r_) / max(0.0008, 2 * mpt)) ** 2), 1).astype(np.float32)
    # buttonholes, from the closures: a slit cut through, satin-stitched both sides (a bead ~1 mm wide) with a bar tack
    # at each end, `size` + 3 mm long, along the hole's axis (closures.hole_axis: down a placket, along a cuff)
    for hx_, hy_, ax_, ln_, _v in holes_done:
        ux, uy = ax_[0], -ax_[1]  # (image rows run down)
        half = 0.5 * ln_ / mpt
        bead = 0.0013 / mpt
        r0 = int(half + bead + 4)
        sub = (slice(max(int(hy_) - r0, 0), min(int(hy_) + r0 + 1, T)), slice(max(int(hx_) - r0, 0), min(int(hx_) + r0 + 1, T)))
        yy, xx = np.mgrid[sub]
        s_ = ((xx - hx_) * ux + (yy - hy_) * uy) * mpt  # along (m)
        t_ = np.abs(-(xx - hx_) * uy + (yy - hy_) * ux) * mpt  # across
        a_ = np.abs(s_)
        e_ = 0.5 * mpt
        outline = np.clip((0.5 * ln_ - a_) / e_ + 0.5, 0, 1) * np.clip((0.0013 - t_) / e_ + 0.5, 0, 1)
        slit = np.clip((0.5 * ln_ - 0.0012 - a_) / e_ + 0.5, 0, 1) * np.clip((max(0.00025, 0.4 * mpt) - t_) / e_ + 0.5, 0, 1)
        thr = np.clip(outline - slit, 0, 1).astype(np.float32)
        # the beads rounded (dense satin stitches stand ~0.4 mm), the slit a dark cut between them
        bead_h = np.clip(1 - ((t_ - 0.0007) / 0.0007) ** 2, 0, 1) * np.clip((0.5 * ln_ - a_) / 0.0006, 0, 1)
        H[sub] += (0.0004 * np.maximum(bead_h, 0.5 * thr) * (1 - slit) - 0.0012 * slit).astype(H.dtype)
        thread[sub] = np.maximum(thread[sub], 0.6 * thr)
        shadow[sub] *= (1 - 0.12 * thr) * (1 - 0.5 * slit)
    # stitch lines drawn on a piece (its pattern lines named *_stitch: a fly's J, a pocket's outline): dashes along them
    for key_, Ls in (M.get("stitch_lines") or {}).items():
        k_ = M["names"].index(key_.split(":", 1)[0]) if key_.split(":", 1)[0] in M["names"] else None
        vs_ = np.where(M["piece"] == k_)[0] if k_ is not None else []
        if not len(vs_):
            continue
        off_ = uv[vs_[0]] * side - M["uv"][vs_[0]]  # the piece's place in the atlas (one scale, no turn)
        Q = (np.asarray(Ls, float) + off_) / side
        seg_ = np.linalg.norm(np.diff(Q * side, axis=0), axis=1)
        cum_ = np.r_[0, np.cumsum(seg_)]
        per = o["stitch"] + o["stitch_gap"]
        im_ = Image.new("L", (T, T), 0)
        dr_ = ImageDraw.Draw(im_)
        for s0 in np.arange(0, cum_[-1], per):
            pa, pb = (np.array([np.interp(s_, cum_, Q[:, 0]), np.interp(s_, cum_, Q[:, 1])]) for s_ in (s0, min(s0 + o["stitch"], cum_[-1])))
            dr_.line([px(pa), px(pb)], fill=255, width=max(1, int(round(0.0009 / mpt))))
        st_ = np.asarray(im_, np.float32) / 255.0
        thread = np.maximum(thread, st_)
        H -= o["stitch_depth"] * st_
    # pressed creases (press folds standing OUT past 180 deg, a trouser's crease): the pressed edge itself, a sharp
    # ridge `crease_width` either side of the fold's row, as high as its angle asks (a mesh at 1-2 cm turns a crease
    # over a triangle's width: a soft rounded ridge, not the knife edge an iron leaves)
    cw_ = float((g.get("detail") or {}).get("crease_width", 0.0025))
    for fd in M.get("folds") or []:
        if fd.get("kind") != "press" or float(fd.get("angle", 180)) <= 182 or not fd.get("rows"):
            continue
        row_ = np.asarray(fd["rows"][0], np.int64)
        if len(row_) < 2:
            continue
        im_ = Image.new("L", (T, T), 0)
        ImageDraw.Draw(im_).line([px(uv[v]) for v in row_], fill=255, width=1)
        from scipy.ndimage import distance_transform_edt as _edt
        dc_ = _edt(np.asarray(im_) == 0) * mpt
        amp_ = 0.0006 * min(1.0, (float(fd["angle"]) - 180.0) / 25.0) * min(1.0, 0.5 + float(fd.get("strength", 0.6)))
        H += (amp_ * np.clip(1.0 - dc_ / cw_, 0.0, 1.0) ** 2).astype(H.dtype)
    # buttons and buttonholes on the pieces' marks
    btn = np.zeros((T, T), np.float32)
    # (a closure's HOLE marks are not buttons, whatever they are called: a jacket's fronts both carry "button<n>",
    # and the over front got a button drawn on its own buttonhole)
    hole_marks = {f"{c_['over']}:{a_}" for c_ in (M.get("closures") or []) if c_.get("under") != c_.get("over")
                  for a_, _b in (c_.get("pairs") or [])}
    from . import closures as closuremod_
    covered_ = closuremod_.covered_buttons(M)  # (under a closed lap: the 3D button sits on the hole over them)
    if o["buttons"]:
        for nm, v in M["marks"].items():
            mk = nm.split(":", 1)[1]
            cx, cy = px(uv[v])
            if mk.startswith("button") and not mk.startswith("buttonhole") and nm not in hole_marks and v not in covered_:
                r = 0.0055 / mpt
                yy, xx = np.ogrid[:T, :T]
                x0, x1, y0, y1 = int(cx - r - 2), int(cx + r + 3), int(cy - r - 2), int(cy + r + 3)
                sub = (slice(max(y0, 0), min(y1, T)), slice(max(x0, 0), min(x1, T)))
                rr = np.hypot(xx[:, sub[1]] - cx, yy[sub[0], :] - cy) / r
                # a flat sew-through button: a low rim round a dished middle (a dome read as a rivet)
                bump = (0.0014 + 0.0004 * np.exp(-((rr - 0.85) / 0.08) ** 2)) * np.clip((1 - rr) / 0.06, 0, 1)
                for hx, hy in ((-0.28, -0.28), (0.28, -0.28), (-0.28, 0.28), (0.28, 0.28)):
                    hr = np.hypot(xx[:, sub[1]] - (cx + hx * r), yy[sub[0], :] - (cy + hy * r)) / (0.13 * r)
                    bump -= 0.0012 * np.clip(1 - hr ** 2, 0, 1)
                H[sub] = np.maximum(H[sub], bump)
                btn[sub] = np.maximum(btn[sub], (rr < 1).astype(np.float32))
            elif mk.startswith("buttonhole") and v not in {h_[4] for h_ in holes_done}:
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
    if extra is not None:  # authored fine folds (fine_folds), under the sewing details
        H += np.asarray(extra, np.float32)
    H *= inside
    thread *= inside
    # normal from the height's slope (tangent space: +x along the image's u, +y up the image)
    gy, gx = np.gradient(H.astype(np.float64), mpt)
    n = np.dstack([-gx, gy, np.ones_like(gx)])  # image rows run down: up the image is -row
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    N = ((n * 0.5 + 0.5) * 255).round().astype(np.uint8)
    Hc = H - (np.asarray(extra, np.float32) * inside if extra is not None else 0)  # (folds don't darken like grooves)
    cav = (np.clip(1 + Hc / 0.004, 0.7, 1.0) * np.where(inside, shadow, 1)).astype(np.float32)
    btn *= inside
    return {"height": H, "normal": N, "cavity": cav, "thread": thread.astype(np.float32), "button": btn, "inside": inside,
            "texels_per_m": T / side}


def write_maps(path_stem: Path, M: dict, uv: np.ndarray, side: float, g: dict, texture: int | None = None,
               extra=None) -> dict:
    """The garment's base colour (its colour, grooves darker, stitches in thread colour), normal and height PNGs
    from detail_maps. Returns {channel: path}."""
    from PIL import Image
    dm = detail_maps(M, uv, side, g, texture, extra)
    rgb = np.array([int(g.get("color", "#8fb3d9").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], float)
    thread = np.array([int(((g.get("detail") or {}).get("thread") or g.get("color", "#8fb3d9")).lstrip("#")[i:i + 2], 16)
                       for i in (0, 2, 4)], float)
    if not (g.get("detail") or {}).get("thread"):
        thread = np.clip(rgb * 1.18 + 12, 0, 255)  # a shade lighter than the cloth (matched thread catches light)
    C = rgb[None, None] * dm["cavity"][..., None]
    t = dm["thread"][..., None] * 0.8
    C = C * (1 - t) + thread[None, None] * t
    button = np.array([int(button_color(g, next((c for c in M.get("closures") or [] if c.get("kind") == "buttons"), None)).lstrip("#")[i:i + 2], 16)
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


def button_color(g: dict, bt: dict | None = None) -> str:
    """A garment's button colour (sRGB hex), one path for looks, the scene, the maps and the export: the closure's
    own `button.color`, else the garment's detail.button, else the closure's `button.tone` x the cloth's colour (a
    kind's default: a jacket's buttons are its cloth darkened, garment_kb kinds.<k>.closure.button), else shirt
    pearl. `bt`: a buttons mesh (closures.buttons_mesh) or a resolved closure."""
    bt = bt or {}
    b = bt.get("button") if isinstance(bt.get("button"), dict) else bt
    if b.get("color"):
        return b["color"]
    if (g.get("detail") or {}).get("button"):
        return g["detail"]["button"]
    if b.get("tone") is not None:
        h = g.get("color", "#8fb3d9").lstrip("#")
        return "#" + "".join(f"{int(np.clip(int(h[i:i + 2], 16) * float(b['tone']), 0, 255)):02x}" for i in (0, 2, 4))
    return "#ebe6dc"


def worn_together(results: list) -> list:
    """[(name, garment, result)] with every garment that another in the list is worn `over` shown as it is worn
    UNDER it: its own finished surface (relief, bands, made pieces) with only the covered cloth laid under the outer
    garment (cloth_layers.tucked), its buttons made again on that surface, those under the outer garment left out.
    One rule for looks, the scene and the export (drawn as the pressed collider instead, a shirt's front in a jacket's
    V had no placket, no buttons and ragged edges)."""
    from . import cloth_layers
    from . import closures as closuremod
    out = list(results)
    by_ = {gn: k for k, (gn, _, _) in enumerate(out)}
    for gn, g, res in results:
        ov = expanded(g).get("over") if isinstance(g, dict) else None
        if ov not in by_:
            continue
        k = by_[ov]
        ogn, og, ores = out[k]
        M = ores["mesh"]
        # what keeps its shape: each made piece, each closure band (a group moves by one vector)
        rigid = np.full(len(ores["V"]), -1, np.int64)
        for j, nm in enumerate(made_pieces(M, interfacing(ores["pieces"], M))):
            if nm in M["names"]:
                rigid[np.asarray(M["piece"]) == M["names"].index(nm)] = j
        V, cov = cloth_layers.tucked(ores, res, rigid=rigid)
        new = dict(ores, V=V, covered=cov)
        if ores.get("buttons"):
            bt = closuremod.buttons_mesh(V, M, ores["body"])
            if bt is not None and len(bt.get("at", [])):
                # a button the outer garment covers is not drawn (2 mm of button under 4 mm of air pokes through)
                kv = ~cov[np.asarray(bt["at"], np.int64)]  # (per button vertex: the cloth vertex it sits on)
                if not kv.any():
                    bt = None
                elif not kv.all():
                    kf = kv[bt["F"]].all(1)
                    remap = np.cumsum(kv) - 1
                    bt = dict(bt, V=bt["V"][kv], F=remap[bt["F"][kf]], at=np.asarray(bt["at"])[kv],
                              mark=np.asarray(bt["mark"])[kv])
            new["buttons"] = bt
        out[k] = (ogn, og, new)
    return out


def garments(name: str, spec: dict, log=print, simulate: bool = False) -> list:
    """Every garment of a model (spec["cloth"]: {name: garment}) settled on the model's body: (name, garment,
    result) for those whose sim is cached (dress runs them); simulate=True runs the missing ones here (export)."""
    out = []
    for gname, g in (spec.get("cloth") or {}).items():
        src = model_body(name, spec, g, simulate=simulate)
        res = build(_garment_for_sim(g), src, f"{name}:{gname}", log=log, cached_only=not simulate)
        if res is None:
            log(f"cloth {gname}: not simulated yet (dress the model first): left out")
            continue
        log(f"cloth {gname}: {res['fit']['verdict']}")
        out.append((gname, g, res))
    return worn_together(out)


def scene_job(name: str, spec: dict, log: list | None = None) -> list:
    """What blender_cloth.show needs per garment: its settled mesh + pattern uv (+ detail maps) in files beside the
    model. Only garments already simulated (dress) go in: a sync never starts a sim."""
    from . import store
    say = (log.append if isinstance(log, list) else print)
    entries = []
    for gname, g, res in garments(name, spec, say):
        uv, side = atlas_uv(res["mesh"])
        path = store._dir(name) / f"cloth_{gname}.npz"
        # (the pieces wound alike, facing out: Solidify grows every piece the same way; vertex ids stay the mesh's, so a
        # sculpt pulls back per vertex)
        np.savez(path, verts=res["V"].astype(np.float32),
                 faces=oriented_faces(res["mesh"], res["V"], body=res["body"]).astype(np.int32),
                 uv=uv.astype(np.float32), base=(res["V"] - _sculpt_offset(res)).astype(np.float32))
        e = {"name": f"cloth:{gname}", "garment": gname, "key": res["key"] + _detail_key(g, res), "npz": str(path),
             "color": g.get("color", "#8fb3d9"), "thickness": fabric(g).get("thickness", 0.0008),
             "roughness": float(g.get("roughness", 0.85))}
        if g.get("detail", {}) is not False:
            maps = write_maps(store._dir(name) / f"cloth_{gname}", res["mesh"], uv, side, g,
                              extra=fine_folds(res, g, uv, side))
            e["maps"] = {k: str(v) for k, v in maps.items() if k != "texels_per_m"}
        if res.get("buttons") is not None:  # the closures' buttons: their own small object beside the garment
            bp_ = store._dir(name) / f"cloth_{gname}_buttons.npz"
            np.savez(bp_, verts=res["buttons"]["V"].astype(np.float32), faces=res["buttons"]["F"].astype(np.int32))
            e["buttons"] = {"npz": str(bp_), "color": button_color(g, res["buttons"]),
                            "roughness": float(res["buttons"].get("roughness", 0.42))}
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
        # (the scene keeps what the sync stamped until the next sync: a value already in the spec isn't news)
        if st.get("color") and st["color"].lower() != str(g.get("color", "")).lower():
            g["color"] = st["color"]
            ch["color"] = st["color"]
        if st.get("roughness") is not None and abs(float(st["roughness"]) - float(g.get("roughness", 0.85))) > 1e-3:
            g["roughness"] = round(float(st["roughness"]), 3)
            ch["roughness"] = g["roughness"]
        if st.get("verts"):
            z = np.load(store._dir(name) / f"cloth_{gname}.npz")
            Vnew = np.load(st["verts"])["verts"].astype(np.float64)
            base = z["base"].astype(np.float64)
            f = store._dir(name) / f"cloth_{gname}_sculpt.npz"
            same = (Vnew.shape == base.shape and f.exists() and (g.get("sculpt") or {}).get("file") == str(f)
                    and np.abs(np.load(f)["offset"] - (Vnew - base)).max() < 2e-4)
            if same:
                pass
            elif Vnew.shape == base.shape:
                off = Vnew - base
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
    from . import closures as closuremod
    out_dir = Path(out_dir)
    parts = []
    built = garments(name, spec, log, simulate=True)
    for gname, g, res in built:
        M, V = res["mesh"], res["V"].astype(np.float64)
        F = M["F"]
        uv, side = atlas_uv(M)
        # layered: the faces of this garment that the garments worn over it hide are left out (a shirt under a jacket
        # is exported as collar, front V and cuffs); garment key "export_hidden": true keeps them
        hide = np.zeros(len(F), bool)
        if not g.get("export_hidden"):
            from . import cloth_layers
            for on, og, ores in built:
                if expanded(og).get("over") == gname:
                    hide |= cloth_layers.hidden(res, ores, float(og.get("hidden_margin", 0.03)))
        if hide.any():
            log(f"cloth {gname}: {int(hide.sum())} of {len(F)} triangles hidden under another garment, left out")
            F = F[~hide]
        # every piece wound to face out (a garment's pieces come out of the pattern either way: one global flip left
        # half a jacket facing in), normals shared across closed seams (each side its own normal shaded every seam
        # as a line, and pushed the inner shell apart there)
        body = res["body"]
        fl = piece_flips(M, V, body)
        pf_ = np.asarray(M["piece"])[F[:, 0]]
        F = F.copy()
        F[fl[pf_]] = F[fl[pf_]][:, [0, 2, 1]]
        vn = shared_normals(M, V, F)
        th = float(fabric(g).get("thickness", 0.0008))
        Vin = V - vn * th
        Vall = np.r_[V, Vin]
        Fall = np.r_[F, F[:, [0, 2, 1]] + len(V)]
        UVall = np.r_[uv, uv]
        bt = res.get("buttons")
        if bt is not None:  # the closures' buttons: small geometry, coloured by the texel of the button drawn at
            # their mark (every vertex of a button takes its mark's uv)
            Fall = np.r_[Fall, np.asarray(bt["F"], np.int64) + len(Vall)]
            Vall = np.r_[Vall, bt["V"]]
            UVall = np.r_[UVall, uv[closuremod.button_texels(M, bt)]]  # (the button drawn at its own mark: at a closed
            # fastening the button sits on the hole, whose texel is thread)
        UVc = UVall[Fall.ravel()]  # per corner
        n, tt, sg = hairmod._tangents(Vall, Fall, UVc)
        # the shared normals (outer shell; the inner shell the opposite), tangents made orthogonal to them again
        nv = np.r_[vn, -vn, np.zeros((len(Vall) - 2 * len(V), 3))]
        cw = Fall.ravel()
        own = cw < 2 * len(V)  # (buttons keep their own)
        n[own] = nv[cw[own]]
        tt = tt - np.sum(tt * n, 1, keepdims=True) * n
        tt /= np.linalg.norm(tt, axis=1, keepdims=True) + 1e-12
        part = {"verts": Vall.astype(np.float32), "corner_vert": Fall.ravel().astype(np.int64),
                "uv": UVc.astype(np.float32),
                "normal": n.astype(np.float32), "tangent": tt.astype(np.float32), "sign": sg.astype(np.float32)}
        files = {"orm": out_dir / f"cloth_{gname}_orm.png", "specular": out_dir / f"cloth_{gname}_specular_gltf.png"}
        if g.get("detail", {}) is not False:
            maps = write_maps(out_dir / f"cloth_{gname}", M, uv, side, dict(g, detail=dict(g.get("detail") or {},
                                                                                        texture=texture)), texture,
                              extra=fine_folds(res, g, uv, side, texture))
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
         size: int = 640, focus=None, zoom: float = 0.4, body: bool = True, textured: bool = False,
         result: str | None = None):
    """Renders of the model's simulated garments on their body (clay, each garment its colour) + the strain map, and
    the text report per garment. focus: [x, y, z] or "garment:piece" (that piece's middle) with zoom m across: a
    close-up. textured: EEVEE with the detail maps (seams, topstitching, hems, buttons) instead of clay.
    result: an out.npz from a cloth job folder (any solver) shown for the one garment named, instead of its cached
    sim: a result whose cache key has moved can still be judged.
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
        if result:
            if len(which) != 1:
                raise ClothError("look with a result: name the one garment it is for")
            g = gs[gn]
            res = build(_garment_for_sim(g), model_body(name, spec, g), f"{name}:{gn}", log=lambda *_: None,
                        result=result)
        else:
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
    # a garment worn under another shown together is drawn as it is worn under it: its finished surface, the covered
    # cloth laid under the outer garment (worn_together; its free-standing sim blouses through the outer one)
    results = worn_together(results)
    # (the body from a garment that also rests on the model's worn parts, if any: shoes under trousers show then)
    bod = next((r_["body"] for _, _, r_ in results if getattr(r_["body"], "worn", None)), results[0][2]["body"])
    hung = [g for _, g, _ in results if isinstance(_state(g), dict) and "hang" in _state(g)]
    if hung and len(hung) == len(results):  # hung garments: the body is gone, the hanger and rail (or rack) show
        body = False
        for gn, _, res in results:
            for o in res.get("hanger_meshes") or []:
                objs.append(dict(o, name=f"{o['name']}_{gn}"))
        for k, (a, b, r) in enumerate([c for g in hung for c in (_state(g)["hang"].get("rack") or [])]):
            V, F = _cylinder(a, b, r)
            objs.append({"name": f"rack{k}", "V": V, "F": F, "color": "#8a6b45"})
    if body and len(bod.V):
        objs.append({"name": "body", "V": bod.V, "F": bod.T, "color": "#d9c3b0"})
        wn = getattr(bod, "worn", None)
        if wn is not None and len(wn.get("V", [])):  # what the cloth rests on besides the body (shoes under a hem)
            objs.append({"name": "worn", "V": np.asarray(wn["V"], float), "F": np.asarray(wn["F"], np.int64),
                         "color": "#3a3634"})
    tmp = store._dir(name) / "_cloth_look"
    tmp.mkdir(exist_ok=True)
    for gn, g, res in results:
        o = {"name": f"g_{gn}", "V": res["V"], "F": res["mesh"]["F"], "color": g.get("color", "#8fb3d9"), "roughness": float(g.get("roughness", 0.85)),
             "thickness": max(0.0006, fabric(g).get("thickness", 0.0008))}
        Fw, Fc = welded_faces(res["mesh"], res["V"], body=res["body"], corners=True)
        o["F"] = Fw  # (one surface: the seams' vertices shared, the pieces wound alike)
        if textured and g.get("detail", {}) is not False:
            uv, side = atlas_uv(res["mesh"])
            maps = write_maps(tmp / f"look_{gn}", res["mesh"], uv, side, g, extra=fine_folds(res, g, uv, side))
            o.update(uv_corner=uv[Fc.ravel()], maps={k: str(v) for k, v in maps.items() if k != "texels_per_m"})
        objs.append(o)
        if res.get("buttons"):
            objs.append({"name": f"buttons_{gn}", "V": res["buttons"]["V"], "F": res["buttons"]["F"],
                         "color": button_color(g, res["buttons"]),
                         "roughness": float(res["buttons"].get("roughness", 0.42))})
        from . import cloth_trims  # belts, loops: built on the finished surface (cloth_trims.py)
        for tm_ in cloth_trims.meshes(res, expanded(g)):
            objs.append({"name": f"{tm_['name']}_{gn}", "V": tm_["V"], "F": tm_["F"], "color": tm_["color"]})
    allV = np.concatenate([o["V"] for o in objs if not o["name"].startswith("rail_")])  # the rail runs out of frame
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
    ext = box[1] - box[0]  # the frame follows the subject (a table is wide, a person tall)
    aspect = 1.0 if focus is not None else float(np.clip(max(ext[0], ext[1]) / max(ext[2], 1e-3), 0.62, 1.8))
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


def piece_flips(M: dict, V: np.ndarray, body=None, tol: float = 0.0006) -> np.ndarray:
    """Per piece: must its faces be turned over so the garment is ONE consistently wound surface facing out? The
    pattern mesh winds each piece as its pattern lies (a mirrored piece, a piece flipped in placement, a turned
    collar all come out either way): on the suit's blazer the backs, the left sleeve's two pieces faced IN and the
    rest out. Welded (clay looks) the normals of a seam's two sides then cancel into a pale or dark line, Solidify
    grows one side out and the other in (a step at every such seam), and the export's inner shell is pushed out on
    those pieces. Consistency comes from the seams (closed sewn pairs: the two sides' vertex normals, as wound, agree
    or oppose; a maximum spanning tree over the pieces by that vote), then the whole is turned to face away from
    the body (or the garment's own vertical axis) by area."""
    F = np.asarray(M["F"])
    P = len(M["names"])
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
    pf = np.asarray(M["piece"])[F[:, 0]]
    W = np.zeros((P, P))
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    if len(sw):
        sw = sw[np.linalg.norm(V[sw[:, 0]] - V[sw[:, 1]], axis=1) <= tol]
        pa, pb = np.asarray(M["piece"])[sw[:, 0]], np.asarray(M["piece"])[sw[:, 1]]
        d = np.sum(vn[sw[:, 0]] * vn[sw[:, 1]], 1)
        k = pa != pb
        np.add.at(W, (pa[k], pb[k]), d[k])
        np.add.at(W, (pb[k], pa[k]), d[k])
    area = np.bincount(pf, weights=0.5 * np.linalg.norm(fn, axis=1), minlength=P)
    sgn = np.zeros(P)
    for start in np.argsort(-area):  # (each connected group of pieces from its largest)
        if sgn[start] or area[start] == 0:
            continue
        sgn[start] = 1
        while True:  # Prim: the strongest vote from a placed piece to an unplaced one
            placed = sgn != 0
            S = np.abs(W) * placed[:, None] * (~placed)[None, :]
            i, j = np.unravel_index(int(np.argmax(S)), S.shape)
            if S[i, j] <= 1e-9:
                break
            sgn[j] = sgn[i] * (1 if W[i, j] > 0 else -1)
    sgn[sgn == 0] = 1
    # which way is out
    c = V.mean(0)
    if body is not None and len(getattr(body, "V", [])):
        _, ni = cKDTree(body.V).query(V[F].mean(1))
        outv = V[F].mean(1) - body.V[ni]
    else:
        outv = V[F].mean(1) - c
        outv[:, 2] = 0
    face_out = np.sum(fn * outv, 1) * sgn[pf]
    if np.sum(np.sign(face_out) * 0.5 * np.linalg.norm(fn, axis=1)) < 0:
        sgn = -sgn
    return sgn < 0


def oriented_faces(M: dict, V: np.ndarray, F: np.ndarray | None = None, body=None) -> np.ndarray:
    """F (default the mesh's) with each piece's faces wound so the garment is one surface facing out (piece_flips).
    F may be welded (vertex ids of M's vertices, as welded_faces returns)."""
    F = np.asarray(M["F"] if F is None else F)
    fl = piece_flips(M, V, body)
    pf = np.asarray(M["piece"])[F[:, 0]]
    out = F.copy()
    out[fl[pf]] = out[fl[pf]][:, [0, 2, 1]]
    return out


def shared_normals(M: dict, V: np.ndarray, F: np.ndarray, tol: float = 0.0006) -> np.ndarray:
    """Vertex normals of the (oriented) faces with every closed seam's vertices sharing one normal: a sewn seam is
    one surface, so it shades as one (each side's own normal drew every seam as a shading line)."""
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    root = _welded_roots(M, V, tol)
    acc = np.zeros((root.max() + 1, 3))
    np.add.at(acc, root, vn)
    vn = acc[root]
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)


def welded_faces(M: dict, V: np.ndarray, tol: float = 0.0006, body=None, orient: bool = True,
                 corners: bool = False):
    """The mesh's faces with the two vertices of every CLOSED seam pair made one (the clay look: a sewn seam is one
    surface. As two rows of vertices at the same place, each with its own normal, every seam rendered as a pale
    line, read as visible stitching or a gap), each piece wound so the whole faces out (oriented_faces; `orient`).
    corners: also the same faces in M's own vertex ids (per-corner uv for a textured look)."""
    F = oriented_faces(M, V, body=body) if orient else np.asarray(M["F"])
    sew = np.asarray(M["sew"]).reshape(-1, 2)
    if not len(sew):
        return (F, F) if corners else F
    root = np.arange(len(V))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    for a_, b_ in sew[np.linalg.norm(V[sew[:, 0]] - V[sew[:, 1]], axis=1) <= tol]:
        ra, rb = find(int(a_)), find(int(b_))
        if ra != rb:
            root[max(ra, rb)] = min(ra, rb)
    rm = np.array([find(i) for i in range(len(V))])
    Fw = rm[F]
    ok = (Fw[:, 0] != Fw[:, 1]) & (Fw[:, 1] != Fw[:, 2]) & (Fw[:, 0] != Fw[:, 2])
    _, first = np.unique(np.sort(Fw, 1), axis=0, return_index=True)  # (two faces made one by the weld: Blender's
    dup = np.ones(len(Fw), bool)  # validate would drop one and a per-corner uv would no longer line up)
    dup[first] = False
    ok &= ~dup
    return (Fw[ok], F[ok]) if corners else Fw[ok]


def strain_colors(strain: np.ndarray, limit: float) -> np.ndarray:
    """Linear RGB per vertex: slack blue -> fine green -> at the limit yellow -> 2x the limit red."""
    t = np.clip(strain / max(limit, 1e-6), -1, 2)
    stops = np.array([[-1, 0.05, 0.15, 0.6], [0, 0.1, 0.5, 0.12], [1, 0.9, 0.75, 0.02], [2, 0.8, 0.02, 0.02]])
    out = np.zeros((len(t), 3))
    for ch in range(3):
        out[:, ch] = np.interp(t, stops[:, 0], stops[:, ch + 1])
    return out


def render(objects: list, prefix: str, views=("front", "side", "back"), resolution: int = 700, box=None,
           aspect: float = 0.62, textured: bool = False, suns=None) -> list:
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
        if o.get("uv_corner") is not None:  # (per corner: welded faces whose seam vertices are shared keep each
            # side's own uv)
            data[o["name"] + "_UVC"] = np.asarray(o["uv_corner"], np.float32)
        objs.append({k: v for k, v in o.items() if k in ("name", "color", "thickness", "maps", "roughness")})
    tag = Path(prefix).name
    np.savez(d / f"_{tag}_render.npz", **data)
    job = {"mode": "render", "data": f"_{tag}_render.npz", "objects": objs, "out_prefix": prefix,
           "views": list(views), "resolution": resolution, "aspect": aspect, "textured": bool(textured), "suns": suns,
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
