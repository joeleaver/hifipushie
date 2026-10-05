"""Our own drafts and generated pieces, for what FreeSewing doesn't draft (or our design tables don't use).

Blocks (`pattern.from` a block name instead of a FreeSewing design): drafted from the tailor's tape (`tailor.measure`,
mm) like a pattern maker drafts a block, as ordinary pattern pieces (pattern.from_spec dicts) + a seam table:
  "skirt_block"  a straight / A-line skirt (Aldrich's block): front cut whole, two backs with a centre-back seam (zip),
                 waist darts, a straight waistband lapped and buttoned at CB. Options (opts, m or fractions):
                 length (m below the waist, default to the knee), ease {"waist", "seat"} (fractions), flare (m added to
                 each side seam at the hem: 0 straight, 0.05-0.10 A-line), darts (true), waistband (height m, 0 = none),
                 overlap (m), closure ("cb_zip" | "side_zip": back cut on the fold, no CB seam).
  Pieces hang from the body's waist line (wrap "level": "waist": pattern y = 0 there).

Generated pieces (garment key "generate", applied after the draft, so they follow its real edge lengths):
  {"band": name, "role", "along": [edge chain of drafted pieces], "ratio" (band length / chain length: a rib band
   0.85, a woven band 1.0), "height" (m, finished), "overlap" (m: the ends lap and button: a waistband, a cuff), "ring"
   (true: the band's ends are sewn together into a ring, e.g. a neckband), "fold" (true: a fold line along its middle:
   a folded rib), "interfaced", "wrap"} -> a rectangle along x (sewn edge at y = 0, points sw s se ne n nw, lapStart),
   the seam to the chain, its closure stitch (button / buttonhole marks) or ring seam.
"""
from __future__ import annotations

import numpy as np

from . import pattern

BLOCKS = ("skirt_block",)
# the pattern keys each block takes (its options; also accepted inside "options")
WORDS = {"skirt_block": ("length", "ease", "flare", "darts", "waistband", "overlap", "closure", "front_dart_length",
                         "back_dart_length")}


def _curve(p0, p1, p2, n=12):
    """Quadratic Bezier p0 -> p2 (control p1), n points without p0."""
    t = np.linspace(0, 1, n + 1)[1:, None]
    p0, p1, p2 = (np.asarray(v, float) for v in (p0, p1, p2))
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def _outline(pts):
    """[[x, y] | ("name", [x, y])...] -> from_spec outline entries."""
    out = []
    for p in pts:
        if isinstance(p, tuple):
            out.append({"at": [float(p[1][0]), float(p[1][1])], "name": p[0]})
        else:
            out.append([float(p[0]), float(p[1])])
    return out


def _quarter(W: float, S: float, seat_y: float, L: float, flare: float, dart: float, dart_len: float,
             dart_at: float, centre: str):
    """One quarter of a skirt (centre at x = 0, side at +x), clockwise from the centre's waist: centre waist, waist
    to the dart, dart, waist to the side (raised 10 mm), hip curve to the seat line, side seam to the hem, hem back to
    the centre. W: the quarter's waist (sewn length), S: its seat width."""
    xd = dart_at * W
    xs = W + dart
    pts = [(f"{centre}Waist", [0.0, 0.0])]
    if dart > 0.003:
        pts += [("dartA", [xd - dart / 2, 0.0]), ("dartTip", [xd, -dart_len]), ("dartB", [xd + dart / 2, 0.0])]
    else:
        xs = W
    pts += [("sideWaist", [xs, 0.01])]
    hip = _curve([xs, 0.01], [S, 0.4 * seat_y], [S, seat_y])
    pts += [list(p) for p in hip[:-1]] + [("sideSeat", list(hip[-1]))]
    pts += [("sideHem", [S + flare, -L]), (f"{centre}Hem", [0.0, -L])]
    return pts


def _mirror_pts(pts):
    """The quarter's mirror (x -> -x), named .m, in reverse order without the centre points (x = 0)."""
    out = []
    for p in reversed(pts):
        name, xy = (p if isinstance(p, tuple) else (None, p))
        if abs(xy[0]) < 1e-9:
            continue
        q = [-xy[0], xy[1]]
        out.append((name + ".m", q) if name else q)
    return out


def skirt_block(m: dict, opts: dict) -> dict:
    """A skirt drafted from the tape (mm): {"pieces", "seams", "stitches", "interfaced", "draft"}."""
    mm = lambda k, d=None: float(m.get(k, d)) / 1000.0
    ease = dict({"waist": 0.01, "seat": 0.05}, **(opts.get("ease") or {}))
    waist, seat = mm("waist"), mm("seat")
    seat_y = -mm("waistToSeat", 220)
    L = float(opts.get("length") or (mm("waistToKnee", 580) - 0.03))
    flare = float(opts.get("flare", 0.0))
    W = waist * (1 + ease["waist"]) / 4
    S = seat * (1 + ease["seat"]) / 4
    diff = max(S - W, 0.0)
    darts = bool(opts.get("darts", True))
    side_take = min(0.5 * diff, 0.03) if darts else diff  # the side seam takes half (at most 3 cm), darts the rest
    dart_f = (diff - side_take) * 0.4 if darts else 0.0  # front darts a little smaller than the back's
    dart_b = (diff - side_take) * 0.6 if darts else 0.0
    W_f, W_b = W, W  # sewn waist lengths (the darts' intake comes on top)
    front_q = _quarter(W_f, S, seat_y, L, flare, dart_f, float(opts.get("front_dart_length", 0.09)), 0.5, "cf")
    back_q = _quarter(W_b, S, seat_y, L, flare, dart_b, float(opts.get("back_dart_length", 0.13)), 0.5, "cb")
    # The front, whole: the right half (x < 0, the body's right) mirrored, then the left half
    # the front whole, round its outline: cfWaist, the left quarter (x > 0, the body's left) down to cfHem, then the
    # mirrored right quarter back up (sideHem.m ... dartA.m)
    front_pts = front_q + _mirror_pts(front_q)
    pieces = {"front": {"outline": _outline(front_pts), "grain": 90, "role": "skirt_front",
                        "wrap": {"to": "torso", "side": "front", "level": "waist"}}}
    seams, stitches = [], []
    side_zip = opts.get("closure", "cb_zip") == "side_zip"
    if side_zip:  # back cut on the fold: one piece
        pieces["back"] = {"outline": _outline(back_q + _mirror_pts(back_q)), "grain": 90, "role": "skirt_back",
                          "wrap": {"to": "torso", "side": "back", "level": "waist"}}
        backs = {"L": ("back", ""), "R": ("back", ".m")}
    else:
        bl = back_q
        pieces["back.L"] = {"outline": _outline(bl), "grain": 90, "role": "skirt_back",
                            "wrap": {"to": "torso", "side": "back", "level": "waist"},
                            "lines": {"zip": [[0.0, 0.0], [0.0, -0.2]]}}
        pieces["back.R"] = {"outline": _outline([(p[0], [-p[1][0], p[1][1]]) if isinstance(p, tuple) else [-p[0], p[1]]
                                                 for p in reversed(bl)]), "grain": 90, "role": "skirt_back",
                            "wrap": {"to": "torso", "side": "back", "level": "waist"},
                            "lines": {"zip": [[0.0, 0.0], [0.0, -0.2]]}}
        backs = {"L": ("back.L", ""), "R": ("back.R", "")}
        seams.append(["back.L:cbWaist>cbHem", "back.R:cbWaist>cbHem"])
    # side seams: the body's left (+x) is the front's plain names and back.L; its right the .m names and back.R
    seams.append(["front:sideWaist>sideHem", f"{backs['L'][0]}:sideWaist{backs['L'][1]}>sideHem{backs['L'][1]}"])
    seams.append(["front:sideWaist.m>sideHem.m", f"{backs['R'][0]}:sideWaist{backs['R'][1]}>sideHem{backs['R'][1]}"])
    if darts:
        for pc, sfx in (("front", ""), ("front", ".m"), (backs["L"][0], backs["L"][1]), (backs["R"][0], backs["R"][1])):
            if (pc.startswith("front") and dart_f > 0.003) or (not pc.startswith("front") and dart_b > 0.003):
                seams.append([f"{pc}:dartA{sfx}>dartTip{sfx}", f"{pc}:dartB{sfx}>dartTip{sfx}"])
    # the waist, as one chain round the body from the right CB (x < 0 at the back) to the left CB
    hasd = lambda f: darts and f > 0.003

    def edge(pc, a, b):
        return f"{pc}:{a}>{b}"
    chain = []
    bR, sR = backs["R"]
    bL, sL = backs["L"]
    if side_zip:
        chain += ([edge(bR, "cbWaist", "dartA.m"), edge(bR, "dartB.m", "sideWaist.m")] if hasd(dart_b)
                  else [edge(bR, "cbWaist", "sideWaist.m")])
    else:
        chain += ([edge(bR, "cbWaist", "dartA"), edge(bR, "dartB", "sideWaist")] if hasd(dart_b)
                  else [edge(bR, "cbWaist", "sideWaist")])
    chain += ([edge("front", "sideWaist.m", "dartB.m"), edge("front", "dartA.m", "cfWaist>dartA"),
               edge("front", "dartB", "sideWaist")] if hasd(dart_f) else [edge("front", "sideWaist.m", "cfWaist>sideWaist")])
    chain += ([edge(bL, "sideWaist", "dartB"), edge(bL, "dartA", "cbWaist")] if hasd(dart_b)
              else [edge(bL, "sideWaist", "cbWaist")])
    draft = {"design": "skirt_block", "options": dict(opts), "measurements": dict(m),
             "derived_mm": {"waist_quarter": round(W * 1000, 1), "seat_quarter": round(S * 1000, 1),
                            "front_dart": round(dart_f * 1000, 1), "back_dart": round(dart_b * 1000, 1),
                            "side_shaping": round(side_take * 1000, 1), "length": round(L * 1000, 1)}}
    out = {"pieces": {}, "seams": seams, "stitches": stitches, "interfaced": [], "draft": draft}
    for nm, d in pieces.items():
        pc = pattern.from_spec(nm, d)
        pc["wrap"] = dict(d["wrap"])
        pc["role"] = d["role"]
        out["pieces"][nm] = pc
    hb = float(opts.get("waistband", 0.035))
    if hb > 0:
        out["generate"] = [{"band": "waistband", "role": "waistband", "along": chain, "ratio": 1.0, "height": hb,
                            "overlap": float(opts.get("overlap", 0.035)), "interfaced": True,
                            "wrap": {"to": "torso", "side": "front", "level": "waist"}}]
    return out


def draft(design: str, meas_mm: dict, opts: dict) -> dict:
    if design == "skirt_block":
        return skirt_block(meas_mm, opts)
    raise ValueError(f"no block {design!r} (have {', '.join(BLOCKS)})")


def _chain_length(pcs: dict, chain) -> float:
    tot = 0.0
    for e in ([chain] if isinstance(chain, str) else chain):
        nm, arc = e.split(":", 1)
        if nm not in pcs:
            raise KeyError(f"generate: along names piece {nm!r} (have {', '.join(pcs)})")
        tot += pattern.length(pcs[nm]["P"][pattern.arc_indices(pcs[nm], arc)])
    return tot


def generate(pcs: dict, entry: dict) -> tuple[dict, list, list, list]:
    """One generated piece -> (pieces to add, seams, stitches, interfaced)."""
    if "band" not in entry:
        raise ValueError(f'generate: each entry is {{"band": name, "along": [...], ...}}, got {sorted(entry)}')
    nm = entry["band"]
    along = entry["along"]
    Lc = _chain_length(pcs, along)
    ratio = float(entry.get("ratio", 1.0))
    lap = float(entry.get("overlap", 0.0))
    h = float(entry.get("height", 0.035))
    L = Lc * ratio + lap
    x0, x1 = -L / 2, L / 2
    pts = [("sw", [x0, 0.0])]
    if lap > 0:
        pts.append(("lapStart", [x0 + lap, 0.0]))
    pts += [("s", [0.0, 0.0]), ("se", [x1, 0.0]), ("ne", [x1, h]), ("n", [0.0, h]), ("nw", [x0, h])]
    d = {"outline": _outline(pts), "grain": 0 if entry.get("grain") is None else entry["grain"]}
    marks, lines = {}, {}
    if lap > 0:  # the ends lap: a button on the underlap, its hole on the other end, `L - lap` apart (the chain)
        marks = {"button1": [x0 + lap / 2, h / 2], "buttonhole1": [x1 - lap / 2, h / 2]}
    if entry.get("fold"):
        lines["fold"] = [[x0, h / 2], [x1, h / 2]]
    d["marks"], d["lines"] = marks, lines
    pc = pattern.from_spec(nm, d)
    pc["wrap"] = dict(entry.get("wrap") or {"to": "torso"})
    pc["role"] = entry.get("role", nm)
    seams = [[f"{nm}:{'lapStart' if lap > 0 else 'sw'}>s>se", along]]
    if entry.get("ring"):
        seams.append([f"{nm}:sw>nw", f"{nm}:se>ne"])
    stitches = [[f"{nm}:button1", f"{nm}:buttonhole1"]] if lap > 0 else []
    inter = [nm] if entry.get("interfaced") else []
    return {nm: pc}, seams, stitches, inter
