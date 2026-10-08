"""Blocks (slopers): the basic patterns a pattern maker drafts from body measurements by stated rules, before any
design. Every design is then derived from a block by operations (pattern_draft.py): nothing here is a garment.

A block is a draft: {"pieces": {name: piece}, "seams": [[side, side]], "meta": {...}, "log": [what was computed]}.
Pieces are HALF pieces (centre at x = 0, the body's left at +x; y up, y = 0 at the high point of the shoulder for
upper blocks, at the waist for lower ones) with every construction point NAMED so operations can address them, and
`sym` saying how the half becomes the garment ("pair": a left and a mirrored right piece; "fold": cut on the fold at
x = 0, one whole piece; "copy": the same piece on both sides, a sleeve). `pattern_draft.unfold` makes the garment's
pieces and mirrors the seams.

Blocks (measurements in mm, FreeSewing's names from tailor.measure; options in fractions or metres):
  bodice    front + back to the waist or the hips, dartless or darted. Rules (Aldrich / Kershaw as FreeSewing's Brian
            states them): neck width = neck (1 + ease) / 4.8; shoulder point at half the shoulder width, dropped by the
            shoulder slope; armhole depth from waist-to-armpit less ease; chest quarter = chest (1 + ease) / 4; across
            back 98% and across front 93% of the half shoulder width at the pitch; waist suppression = chest quarter -
            waist quarter, taken at the side seam (40%, at most 25 mm) and in a waist dart (the rest, at most 35 mm);
            a bust dart from the side seam to the apex when the bust is fuller than the high bust.
  sleeve    one piece, drafted INTO the armhole it will be sewn to: width = biceps (1 + ease); the cap's height is
            solved so the cap's length = the armhole's length (1 + cap ease), and the cap's top is shifted until its
            front and back parts match the front and back armholes. A wide sleeve gets a low cap, a narrow one a high
            cap: the three can't be chosen independently.
  skirt     garment_blocks.skirt_block (front, back, darts, waistband).
  trouser   front + back leg (Aldrich): seat quarters -1 / +1 cm, body rise (crotch depth) from the waist, fork
            extensions seat / 16 + 5 mm (front) and about twice that (back), the back centre seam slanted and raised
            for the seat, a crease line midway, knee and hem widths about it.
  knit      the bodice with little or negative ease, no darts, a lower armhole and a flat cap without ease.
"""
from __future__ import annotations

import math

import numpy as np

from . import pattern

BLOCKS = ("bodice", "knit", "sleeve", "trouser", "skirt")


def bez(p0, c1, c2, p1, n=14):
    """Cubic Bezier points without p0."""
    t = np.linspace(0, 1, n + 1)[1:, None]
    p0, c1, c2, p1 = (np.asarray(v, float) for v in (p0, c1, c2, p1))
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * p1


def make_piece(name: str, pts: list, role: str, wrap: dict, sym: str, marks: dict | None = None,
               lines: dict | None = None, grain: float = 90.0) -> dict:
    """pts: [(name | None, [x, y]) ...] round the outline."""
    P, names = [], {}
    for nm, q in pts:
        q = np.asarray(q, float)
        if P and np.linalg.norm(q - P[-1]) < 1e-6:
            if nm:
                names.setdefault(nm, len(P) - 1)
            continue
        if nm:
            names[nm] = len(P)
        P.append(q)
    if np.linalg.norm(P[0] - P[-1]) < 1e-6:
        last = len(P) - 1
        P.pop()
        names = {k: (0 if i == last else i) for k, i in names.items()}
    return {"name": name, "P": np.asarray(P), "names": names,
            "marks": {k: np.asarray(v, float) for k, v in (marks or {}).items()},
            "lines": {k: np.asarray(v, float) for k, v in (lines or {}).items()}, "grain": grain, "role": role,
            "wrap": dict(wrap), "sym": sym, "darts": {}}


def _curve_pts(C):
    return [(None, p) for p in C[:-1]]


def edge_length(pc: dict, arc: str) -> float:
    return pattern.length(pc["P"][pattern.arc_indices(pc, arc)])


# ---------------------------------------------------------------- bodice


BODICE_DEFAULTS = {"chest_ease": 0.10, "waist_ease": 0.10, "hips_ease": 0.08, "collar_ease": 0.05,
                   "shoulder_ease": 0.0, "biceps_ease": 0.15, "armhole_depth": 0.02, "length": "hips",
                   "length_bonus": 0.0, "fitted": False, "darts": False, "bust_dart": None, "across_back": 0.98,
                   "across_front": 0.93, "back_neck": 0.05, "cb": "fold", "cf": "open", "front_balance": 0.0}
KNIT_DEFAULTS = dict(BODICE_DEFAULTS, chest_ease=0.0, waist_ease=0.02, hips_ease=0.0, biceps_ease=0.05,
                     armhole_depth=0.0, collar_ease=0.12, cf="fold")


def bodice(m: dict, opts: dict | None = None, knit: bool = False) -> dict:
    o = dict(KNIT_DEFAULTS if knit else BODICE_DEFAULTS, **(opts or {}))
    mm = lambda k: float(m[k]) / 1000.0
    log = []
    neck, chest, waist = mm("neck"), mm("chest"), mm("waist")
    hips = mm("hips") if "hips" in m else chest
    nw = neck * (1 + o["collar_ease"]) / 4.8
    bn = o["back_neck"] * neck
    # the front neck's depth is SOLVED: back + front neckline = half the neck girth with its ease (a collar or band
    # of that length then fits). It starts at the neck width (a quarter circle) and comes up or down
    back_len = pattern.length(np.r_[[[0, -bn]], bez([0, -bn], [nw * 0.6, -bn], [nw * 0.92, -bn * 0.25], [nw, 0])])
    target = neck * (1 + o["collar_ease"]) / 2 - back_len
    lo_, hi_ = 0.3 * nw, 2.5 * nw
    for _ in range(40):
        fn = 0.5 * (lo_ + hi_)
        ln_ = pattern.length(np.r_[[[0, -fn]], bez([0, -fn], [nw * 0.75, -fn], [nw, -fn * 0.45], [nw, 0])])
        lo_, hi_ = (fn, hi_) if ln_ < target else (lo_, fn)
    if o.get("front_neck") is not None:
        fn = float(o["front_neck"])
    sx = mm("shoulderToShoulder") / 2 * (1 + o["shoulder_ease"])
    slope = math.radians(float(m.get("shoulderSlope", 13.0)))
    sy = (sx - nw) * math.tan(slope)
    wy = mm("hpsToWaistBack")
    ay = wy - mm("waistToArmpit") * (1 - o["armhole_depth"] - o["biceps_ease"] / 2)
    cx = chest * (1 + o["chest_ease"]) / 4
    wq = waist * (1 + o["waist_ease"]) / 4
    hq = max(hips * (1 + o["hips_ease"]) / 4, wq)
    hy = wy + mm("waistToHips") if "waistToHips" in m else wy + 0.15
    to_hips = o["length"] != "waist"
    ly = (hy if to_hips else wy) * 1.0
    if isinstance(o["length"], (int, float)):  # metres below the hps at centre back
        ly, to_hips = float(o["length"]), float(o["length"]) > wy + 0.03
    ly += float(o["length_bonus"])
    supp = max(cx - wq, 0.0)  # per quarter
    side = min(0.4 * supp, 0.025) if o["fitted"] else 0.0
    dart = min(supp - side, 0.035) if (o["fitted"] and o["darts"]) else 0.0
    left = supp - side - dart  # what stays as ease at the waist, or is there for panel seams to take in
    log.append(f"neck width {nw * 1000:.0f} mm (neck x {1 + o['collar_ease']:.2f} / 4.8), shoulder point at "
               f"{sx * 1000:.0f}, {sy * 1000:.0f} down (slope {math.degrees(slope):.0f} deg), armhole depth {ay * 1000:.0f}, "
               f"chest quarter {cx * 1000:.0f} (ease {o['chest_ease'] * 100:.0f}%), waist quarter {wq * 1000:.0f}; front neck "
               f"depth {fn * 1000:.0f} mm (solved: the neckline is half the neck girth + {o['collar_ease'] * 100:.0f}%)")
    log.append(f"waist suppression {supp * 1000:.0f} mm per quarter: side seam {side * 1000:.0f}, dart {dart * 1000:.0f}, "
               f"left as ease / for panel seams {left * 1000:.0f}")
    bust = None
    if "hpsToBust" in m:
        bust = np.array([min(0.5 * cx, float(m.get("bustSpan", 0)) / 2000.0 or 0.47 * cx), mm("hpsToBust")])
    bd = o["bust_dart"]
    if bd is None:  # the front needs length over a bust fuller than the high bust
        bd = max(0.0, (float(m.get("chest", 0)) - float(m.get("highBust", m.get("chest", 0)))) / 1000.0 * 0.5)
        bd = bd if bd > 0.008 else 0.0
    out = {}
    for which in ("back", "front"):
        front = which == "front"
        af = o["across_front"] if front else o["across_back"]
        px, py = sx * af, sy + (ay - sy) * (0.62 if front else 0.55)
        nd = fn if front else bn
        Y = lambda y: -y  # y down in the draft, up in the piece
        pts = [("cfNeck" if front else "cbNeck", [0, Y(nd)])]
        # neckline: square to the centre line at the centre, square to the shoulder seam at the hps
        if front:
            pts += _curve_pts(bez([0, Y(nd)], [nw * 0.75, Y(nd)], [nw, Y(nd * 0.45)], [nw, 0]))
        else:
            pts += _curve_pts(bez([0, Y(nd)], [nw * 0.6, Y(nd)], [nw * 0.92, Y(nd * 0.25)], [nw, 0]))
        pts += [("hps", [nw, 0]), ("shoulder", [sx, Y(sy)])]
        # armhole: leaves the shoulder square to the seam, runs down to the pitch, round into the underarm
        sh_dir = np.array([sx - nw, -(sy)]) / math.hypot(sx - nw, sy)
        dn = np.array([sh_dir[1], -sh_dir[0]])  # square to the seam, pointing down
        k1 = 0.35 * (py - sy)
        pts += _curve_pts(bez([sx, Y(sy)], np.array([sx, Y(sy)]) + dn * k1, [px, Y(py - 0.45 * (py - sy))], [px, Y(py)]))
        pts += [("armholePitch", [px, Y(py)])]
        scoop = 0.56 if front else 0.52  # the front armhole is hollowed a little more than the back
        pts += _curve_pts(bez([px, Y(py)], [px, Y(py + scoop * (ay - py))], [px + (1 - scoop * 1.05) * (cx - px), Y(ay)],
                              [cx, Y(ay)]))
        pts += [("armhole", [cx, Y(ay)])]
        shift = bd if front else 0.0  # the front below the bust line is longer by the bust dart
        if front and bd > 0 and bust is not None:
            by = float(np.clip(bust[1], ay + 0.02, wy - 0.05))
            # level with the apex, its legs the same length; the tip stops 2 cm short of the apex
            pts += [("bustDartA", [cx, Y(by - bd / 2)]), ("bustDartTip", [bust[0] + 0.02, Y(by)]),
                    ("bustDartB", [cx, Y(by + bd / 2)])]
        swx = cx - side
        # the side seam as one line from the underarm to the hips, cut (or run on straight) at the block's length
        S = [np.array([cx, ay + shift])]
        if side > 0:
            S += list(bez([cx, ay + shift], [cx, ay + shift + 0.4 * (wy - ay)], [swx, wy + shift - 0.3 * (wy - ay)],
                          [swx, wy + shift]))
            S += list(bez([swx, wy + shift], [swx, wy + shift + 0.4 * (hy - wy)], [hq, hy + shift - 0.3 * (hy - wy)],
                          [hq, hy + shift]))
        else:
            S += [np.array([cx, wy + shift]), np.array([max(hq, cx), hy + shift])]
        S = np.asarray(S)
        end = ly + shift
        if end > S[-1, 1] + 1e-6:
            S = np.r_[S, [[S[-1, 0], end]]]
        else:
            keep = S[:, 1] < end - 1e-6
            x_end = float(np.interp(end, S[:, 1], S[:, 0]))
            S = np.r_[S[keep], [[x_end, end]]]
        wi = int(np.argmin(np.abs(S[:, 1] - (wy + shift))))
        named_waist = to_hips and abs(S[wi, 1] - (wy + shift)) < 1e-6 and 0 < wi < len(S) - 1
        dart_end = max((-q[1] for nm_, q in pts if nm_ == "bustDartB"), default=-1e9)  # y (down) of the dart's low leg
        for i, q in enumerate(S[1:-1], start=1):
            if q[1] < dart_end + 0.004:
                continue  # the side seam above the bust dart's lower leg is already drawn
            pts.append(("waist" if (named_waist and i == wi) else None, [q[0], Y(q[1])]))
        pts.append(("hem" if to_hips else "waist", [S[-1, 0], Y(end)]))
        if dart > 0 and not to_hips:
            dxm = bust[0] if (front and bust is not None) else 0.5 * wq
            tip_y = (bust[1] + 0.02 + shift) if (front and bust is not None) else ay + 0.03
            pts += [("waistDartB", [dxm + dart / 2, Y(end)]), ("waistDartTip", [dxm, Y(tip_y)]),
                    ("waistDartA", [dxm - dart / 2, Y(end)])]
        pts.append((("cfHem" if front else "cbHem") if to_hips else ("cfWaist" if front else "cbWaist"), [0, Y(end)]))
        sym = ("fold" if o["cf"] == "fold" else "pair") if front else ("fold" if o["cb"] == "fold" else "pair")
        lines = {"chest": [[0, Y(ay)], [cx, Y(ay)]], "waist": [[0, Y(wy + shift)], [cx, Y(wy + shift)]]}
        marks = {}
        if front and bust is not None:
            marks["bust"] = [bust[0], Y(bust[1])]
        fb = float(o.get("front_balance", 0.0)) if front else 0.0
        if fb:
            # front balance: the front longer between the neck point and the chest line than the back (a man's
            # chest stands forward of his neck point: cut as long as the back there, an open front is pulled up
            # over the chest and kicks forward at the hem). The front above the chest line is spread upward: the
            # neck point and shoulder by the whole amount, easing to nothing at the chest line
            def _raise(q, fb=fb):
                q = np.asarray(q, float)
                return [float(q[0]), float(q[1]) + fb * float(np.clip((ay + q[1]) / max(ay - sy, 1e-6), 0.0, 1.0))]
            pts = [(n_, _raise(q)) for n_, q in pts]
            if "bust" in marks:
                marks["bust"] = _raise(marks["bust"])
            log.append(f"front balance {fb * 1000:.0f} mm: the front's neck point and shoulder raised over the back's")
        pc = make_piece(which, pts, which, {"to": "torso", "side": which}, sym, marks, lines)
        if "bustDartA" in pc["names"]:
            pc["darts"]["bustDart"] = ("bustDartA", "bustDartTip", "bustDartB")
        if "waistDartA" in pc["names"]:
            pc["darts"]["waistDart"] = ("waistDartA", "waistDartTip", "waistDartB")
        out[which] = pc
    f, b = out["front"], out["back"]
    low = "hem" if to_hips else "waist"
    seams = [["front:shoulder>hps", "back:shoulder>hps"]]
    if "bustDartA" in f["names"]:
        seams += [[["front:armhole>bustDartA", f"front:bustDartB>{low}"], f"back:armhole>{low}"],
                  ["front:bustDartA>bustDartTip", "front:bustDartB>bustDartTip"]]
    else:
        seams += [[f"front:armhole>{low}", f"back:armhole>{low}"]]
    for nm, pc in out.items():
        if "waistDartA" in pc["names"]:
            seams.append([f"{nm}:waistDartA>waistDartTip", f"{nm}:waistDartB>waistDartTip"])
    meta = {"kind": "knit" if knit else "bodice", "armhole_front": edge_length(f, "armhole>armholePitch>shoulder"),
            "armhole_back": edge_length(b, "armhole>armholePitch>shoulder"), "armhole_depth": ay - sy,
            "neck_front": edge_length(f, "cfNeck>hps"), "neck_back": edge_length(b, "cbNeck>hps"),
            "waist_left": left, "waist_dart": dart, "waist_y": -wy, "hips_y": -hy, "chest_y": -ay, "chest_quarter": cx, "waist_quarter": wq,
            "bust": None if bust is None else [float(bust[0]), float(-bust[1])], "options": o, "low": low,
            "biceps_ease": o["biceps_ease"], "knit": knit}
    log.append(f"armhole front {meta['armhole_front'] * 1000:.0f} + back {meta['armhole_back'] * 1000:.0f} mm; neckline "
               f"front {meta['neck_front'] * 1000:.0f} + back {meta['neck_back'] * 1000:.0f} mm (per half)")
    return {"pieces": out, "seams": seams, "meta": meta, "log": log, "centre": {"front": o["cf"], "back": o["cb"]}}


# ---------------------------------------------------------------- sleeve


def _cap(W: float, h: float, xt: float, n: int = 24):
    """The cap from the back underarm (-W/2, 0) over the top (xt, h) to the front underarm (+W/2, 0): two S curves.
    The front is hollowed more at the underarm and fuller over the cap, as the front armhole is."""
    back = bez([-W / 2, 0], [-W / 2 + 0.30 * (xt + W / 2), 0], [xt - 0.50 * (xt + W / 2), h], [xt, h], n)
    frontc = bez([xt, h], [xt + 0.42 * (W / 2 - xt), h], [W / 2 - 0.36 * (W / 2 - xt), 0], [W / 2, 0], n)
    return np.r_[[[-W / 2, 0.0]], back], frontc  # back part (with its start), front part (after the top)


def solve_cap(W: float, ah_front: float, ah_back: float, ease: float) -> dict:
    """Cap height h and top shift xt so the cap's back part = ah_back (1 + ease) and its front part = ah_front (1 +
    ease). Returns {"h", "xt", "front", "back", "ok", "why"}: not ok when the sleeve is so wide that even a flat cap is
    longer than the armhole (lower the biceps ease or deepen the armhole) or so narrow the cap would stand higher than
    the armhole is deep."""
    tf, tb = ah_front * (1 + ease), ah_back * (1 + ease)

    def lens(h, xt):
        b, f = _cap(W, h, xt)
        return pattern.length(b), pattern.length(np.r_[b[-1:], f])
    if W >= tf + tb - 1e-4:
        return {"h": 0.0, "xt": 0.0, "front": W / 2, "back": W / 2, "ok": False,
                "why": f"the sleeve ({W * 1000:.0f} mm wide) is wider than the armhole is long ({(tf + tb) * 1000:.0f} mm): "
                       "no cap fits. Less biceps ease, or a deeper armhole"}
    h, xt = 0.1, 0.0
    for _ in range(40):  # alternate: height for the total, shift for the split
        lo, hi = 0.0, 0.6
        for _ in range(40):
            h = 0.5 * (lo + hi)
            b, f = lens(h, xt)
            lo, hi = (h, hi) if b + f < tf + tb else (lo, h)
        lo, hi = -0.3 * W, 0.3 * W
        for _ in range(40):
            xt = 0.5 * (lo + hi)
            b, f = lens(h, xt)
            lo, hi = (xt, hi) if b - tb < f - tf else (lo, xt)  # the back too short: move the top forward
    b, f = lens(h, xt)
    return {"h": h, "xt": xt, "front": f, "back": b, "ok": True, "why": ""}


SLEEVE_DEFAULTS = {"biceps_ease": 0.15, "cap_ease": 0.015, "wrist_ease": 0.25, "length_bonus": 0.0, "length": None,
                   "hem_width": None}


def sleeve(m: dict, body: dict, opts: dict | None = None, armhole: tuple | None = None, mate: list | None = None) -> dict:
    """A one-piece sleeve for the bodice draft `body` (its armhole lengths as they are now, after any ops; or
    `armhole` = (front, back) lengths and `mate` = the armhole's edge chain, front underarm up, back down)."""
    o = dict(SLEEVE_DEFAULTS, **(opts or {}))
    mm = lambda k: float(m[k]) / 1000.0
    af, ab = armhole if armhole is not None else armhole_lengths(body)
    W = mm("biceps") * (1 + o["biceps_ease"])
    cap = solve_cap(W, af, ab, o["cap_ease"])
    L = float(o["length"]) if o["length"] else mm("shoulderToWrist") * (1 + o["length_bonus"])
    hw = float(o["hem_width"]) if o["hem_width"] else mm("wrist") * (1 + o["wrist_ease"])
    hem_y = -(L - cap["h"])
    elbow_y = -(mm("shoulderToElbow") - cap["h"]) if "shoulderToElbow" in m else hem_y * 0.45
    back, frontc = _cap(W, cap["h"], cap["xt"])
    pts = [("underarmB", back[0])] + [(None, p) for p in back[1:-1]] + [("capTop", back[-1])]
    pts += [(None, p) for p in frontc[:-1]] + [("underarmF", frontc[-1])]
    we = lambda y: hw / 2 + (W / 2 - hw / 2) * (1 - y / hem_y)  # the underarm seam's x at depth y
    pts += [("elbowF", [we(elbow_y), elbow_y]), ("wristF", [hw / 2, hem_y]), ("wristB", [-hw / 2, hem_y]),
            ("elbowB", [-we(elbow_y), elbow_y])]
    # pitch notches: where the armhole's pitch points land on the cap (by the same fraction of each part)
    marks = {}
    pc = make_piece("sleeve", pts, "sleeve", {"to": "arm.L", "front": 1}, "copy", marks,
                    {"biceps": [[-W / 2, 0], [W / 2, 0]], "elbow": [[-we(elbow_y), elbow_y], [we(elbow_y), elbow_y]],
                     "centre": [[cap["xt"], cap["h"]], [0, hem_y]]})
    log = [f"sleeve: biceps width {W * 1000:.0f} mm (ease {o['biceps_ease'] * 100:.0f}%), armhole front {af * 1000:.0f} + back "
           f"{ab * 1000:.0f} mm, cap ease {o['cap_ease'] * 100:.1f}% -> cap height {cap['h'] * 1000:.0f} mm "
           f"({cap['h'] / max(body['meta']['armhole_depth'], 1e-6) * 100:.0f}% of the armhole depth), top shifted "
           f"{cap['xt'] * 1000:+.0f} mm; cap front {cap['front'] * 1000:.0f}, back {cap['back'] * 1000:.0f} mm"]
    if not cap["ok"]:
        log.append("!! " + cap["why"])
    elif cap["h"] > 1.05 * body["meta"]["armhole_depth"]:
        log.append("!! the cap stands higher than the armhole is deep: the sleeve is too narrow for this armhole "
                   "(more biceps ease, or a shallower armhole)")
    seams = [["sleeve:underarmF>capTop>underarmB", mate if mate is not None else cap_mate(body)],
             ["sleeve:underarmF>wristF", "sleeve:underarmB>wristB"]]
    return {"pieces": {"sleeve": pc}, "seams": seams, "meta": {"cap": cap, "width": W, "length": L, "hem_width": hw, "cap_ease": o["cap_ease"]},
            "log": log}


def armhole_lengths(body: dict) -> tuple[float, float]:
    """(front, back) armhole lengths of a bodice draft as it is now: every piece's edges on the armhole (pieces cut
    by style lines carry "armhole_edges": a list of arcs)."""
    out = {"front": 0.0, "back": 0.0}
    for nm, pc in body["pieces"].items():
        for arc in pc.get("armhole_edges", ["armhole>armholePitch>shoulder"] if "armholePitch" in pc["names"] and
                          "armhole" in pc["names"] and "shoulder" in pc["names"] else []):
            out["front" if pc.get("role") == "front" else "back"] += edge_length(pc, arc)
    return out["front"], out["back"]


def cap_mate(body: dict) -> list:
    """The armhole as the sleeve cap's mate: the front from the underarm up to the shoulder, then the back down."""
    fr, bk = [], []
    for nm, pc in body["pieces"].items():
        arcs = pc.get("armhole_edges", ["armhole>armholePitch>shoulder"] if "armholePitch" in pc["names"] and
                      "armhole" in pc["names"] and "shoulder" in pc["names"] else [])
        for arc in arcs:
            (fr if pc.get("role") == "front" else bk).append((nm, arc))
    rev = lambda arc: ">".join(reversed(arc.split(">")))
    # front pieces in order from the underarm up; back pieces from the shoulder down
    fr.sort(key=lambda e: -body["pieces"][e[0]]["P"][pattern.arc_indices(body["pieces"][e[0]], e[1])][:, 1].mean() * -1)
    bk.sort(key=lambda e: -body["pieces"][e[0]]["P"][pattern.arc_indices(body["pieces"][e[0]], e[1])][:, 1].mean())
    return [f"{n}:{a}" for n, a in fr] + [f"{n}:{rev(a)}" for n, a in bk]


# ---------------------------------------------------------------- skirt


SKIRT_DEFAULTS = {"waist_ease": 0.02, "seat_ease": 0.05, "length": 0.55, "darts": True, "cb": "seam", "cf": "fold",
                  "flare": 0.0}


def skirt(m: dict, opts: dict | None = None) -> dict:
    """The straight skirt block as HALF pieces for the operations (y = 0 at the waist at the centre, x = 0 on the
    centre line): seat quarter = seat (1 + ease) / 4 at the seat line, waist quarter = waist (1 + ease) / 4; the
    difference is taken at the side seam (half, at most 30 mm) and in a waist dart (the rest; with "darts": false
    all of it at the side seam, for a yoke or panel seams to take over); the side waist is raised 12 mm (the waist
    curves up over the hip); "flare" m added at the hem's side."""
    o = dict(SKIRT_DEFAULTS, **(opts or {}))
    mm = lambda k: float(m[k]) / 1000.0
    waist, seat = mm("waist"), mm("seat")
    wts = mm("waistToSeat") if "waistToSeat" in m else 0.22
    sq, wq = seat * (1 + o["seat_ease"]) / 4, waist * (1 + o["waist_ease"]) / 4
    supp = max(sq - wq, 0.0)
    side = min(0.5 * supp, 0.03) if o["darts"] else supp
    dart = supp - side
    L = float(o["length"])
    Y = lambda y: -y
    out = {}
    for which in ("front", "back"):
        fr = which == "front"
        dl = 0.09 if fr else 0.13
        pts = [("cWaist", [0.0, 0.0])]
        if dart > 0:
            dx = 0.5 * wq
            pts += [("dartA", [dx, 0.004]), ("dartTip", [dx + dart / 2, Y(dl)]), ("dartB", [dx + dart, 0.006])]
        sw = wq + dart
        pts += [("sideWaist", [sw, 0.012])]
        pts += _curve_pts(bez([sw, 0.012], [sw + 0.35 * (sq - sw), Y(0.3 * wts)], [sq, Y(0.6 * wts)], [sq, Y(wts)]))
        pts += [("sideSeat", [sq, Y(wts)]), ("hem", [sq + float(o["flare"]), Y(L)]), ("cHem", [0.0, Y(L)])]
        sym = ("fold" if o["cf"] == "fold" else "pair") if fr else ("fold" if o["cb"] == "fold" else "pair")
        pc = make_piece(which, pts, "skirt_front" if fr else "skirt_back", {"to": "torso", "side": which, "level": "waist"},
                        sym, {}, {"seat": [[0, Y(wts)], [sq, Y(wts)]]})
        if dart > 0:
            pc["darts"]["dart"] = ("dartA", "dartTip", "dartB")
        out[which] = pc
    seams = [["front:sideWaist>sideSeat>hem", "back:sideWaist>sideSeat>hem"]]
    if dart > 0:
        seams += [[f"{k}:dartA>dartTip", f"{k}:dartB>dartTip"] for k in ("front", "back")]
    log = [f"skirt: seat quarter {sq * 1000:.0f} mm (ease {o['seat_ease'] * 100:.0f}%), waist quarter {wq * 1000:.0f}; "
           f"{supp * 1000:.0f} mm a quarter to take out: side seam {side * 1000:.0f}, dart {dart * 1000:.0f}; length {L * 1000:.0f} mm"]
    return {"pieces": out, "seams": seams, "log": log, "centre": {"front": o["cf"], "back": o["cb"]},
            "meta": {"kind": "skirt", "options": o, "low": "hem", "waist_y": 0.0, "hips_y": -wts, "waist_quarter": wq,
                     "waist_dart": 0.0}}


# ---------------------------------------------------------------- trouser


# where a trouser hem ends, as metres above the floor: "floor" (a wide leg's hem over a heel), "shoe" (a break on
# the shoe: for a body that wears shoes), "ankle" (the default: these bodies are barefoot, and a hem cut for a shoe
# pools on the foot), "cropped", "calf"; "knee" and "shorts" are set from the knee and the rise
TROUSER_LENGTHS = {"floor": 0.015, "shoe": 0.03, "break": None, "ankle": 0.085, "cropped": 0.16, "calf": 0.30, "knee": None,
                   "shorts": None}
# "break": a suit trouser cut for one slight break: the sides and front to "shoe" (30 mm over the floor), the back
# BREAK_BACK longer (a sloped hem: the back reaches the heel counter), and the front's extra length over the shoe's
# vamp is the break: the start lays it on the shoe (cloth._hem_on_shoe gathers what the shoe stops into the bottom of
# the leg). Cut from the shoes' own heights it was wrong both ways: su_garrett's shoe part stands ~10 cm high all round
# its collar, which cut the leg 5 cm SHORT (the ankle showed between hem and shoe)
BREAK_BACK = 0.012
TROUSER_DEFAULTS = {"seat_ease": 0.05, "waist_ease": 0.02, "rise": None, "rise_ease": 0.01, "knee": None, "hem": None,
                    "length": None, "back_dart": 0.02, "leg": None, "dart_length": None, "dart_taper": 0.0}
# the cut of the leg, from the leg itself (tailor.measure: knee, calf, heel girths). Knee and hem are finished
# circumferences: knee = the knee girth x (1 + knee ease), never under the calf x (1 + calf ease) (the leg must hang
# clear of the calf or it catches there); hem = the knee's x `hem` share, never under heel + `heel` (the heel-and-
# instep girth is what the hem must pass over; + 20 mm is as slim as a hem without a zip goes).
# Men's ready-to-wear on a 38 cm knee / 34 cm heel: slim suit trousers knee 42-44, hem 36-38 cm; classic 48 / 42-44
# (Aldrich's men's trouser block: bottom width 25 cm flat classic, 20-22 slim; Cabrera: knee 19-20", bottom 17-18").
LEG_CUTS = {"skinny": {"knee": 0.10, "calf": 0.03, "hem": 0.84, "heel": 0.015},
            "slim": {"knee": 0.20, "calf": 0.08, "hem": 0.88, "heel": 0.02},
            "tapered": {"knee": 0.30, "calf": 0.14, "hem": 0.80, "heel": 0.02},
            "straight": {"knee": 0.32, "calf": 0.16, "hem": 0.92, "heel": 0.04},
            "wide": {"knee": 0.60, "calf": 0.40, "hem": 1.0, "heel": 0.10}}


def leg_cut(m: dict, cut: str) -> tuple[float, float, str]:
    """(knee, hem) as the block takes them (the mean flat width = half the finished circumference, m) for a named
    cut of the leg, and the rule as text."""
    if cut not in LEG_CUTS:
        raise ValueError(f"trouser leg {cut!r}: one of {', '.join(LEG_CUTS)} (or give knee / hem in metres)")
    c = LEG_CUTS[cut]
    kg = float(m.get("knee", 0.47 * float(m["waist"]))) / 1000.0  # (no leg scan: a knee from the waist's proportion)
    cg = float(m.get("calf", 1.07 * kg * 1000)) / 1000.0
    hg = float(m.get("heel", 0.95 * kg * 1000)) / 1000.0
    knee = max(kg * (1 + c["knee"]), cg * (1 + c["calf"]))
    hem = min(max(knee * c["hem"], hg + c["heel"]), knee)
    return knee / 2, hem / 2, (f"leg {cut}: knee {knee * 1000:.0f} mm round (knee girth {kg * 1000:.0f} + {c['knee'] * 100:.0f}%, "
                               f"calf {cg * 1000:.0f} + {c['calf'] * 100:.0f}% at least), hem {hem * 1000:.0f} mm round "
                               f"({c['hem'] * 100:.0f}% of the knee, heel {hg * 1000:.0f} + {c['heel'] * 1000:.0f} mm at least)")


def trouser(m: dict, opts: dict | None = None) -> dict:
    o = dict(TROUSER_DEFAULTS, **(opts or {}))
    mm = lambda k: float(m[k]) / 1000.0
    waist, seat = mm("waist"), mm("seat")
    wts = mm("waistToSeat")
    measured = "waistToUpperLeg" in m
    rise = float(o["rise"]) if o["rise"] else (mm("waistToUpperLeg") if measured else 0.175 * waist + 0.154)
    rise += o["rise_ease"]
    wts = min(wts, rise - 0.075)  # the hip line the crotch curve springs from: at least 75 mm above the crotch line
    # the length: metres from the waist, or where the hem ends (TROUSER_LENGTHS: above the floor)
    lw = o["length"] if isinstance(o["length"], str) else None
    if lw is not None and lw not in TROUSER_LENGTHS:
        raise ValueError(f"trouser length {lw!r}: metres from the waist, or one of {', '.join(TROUSER_LENGTHS)}")
    dh_crease = {"front": 0.0, "back": 0.0}
    if lw == "break":
        L = mm("waistToFloor") - TROUSER_LENGTHS["shoe"]
        dh_crease = {"front": 0.0, "back": BREAK_BACK}
    elif lw in ("knee", "shorts"):
        knee_ = mm("waistToKnee") if "waistToKnee" in m else rise + 0.33
        L = knee_ - (0.02 if lw == "knee" else 0.5 * (knee_ - rise))
    elif lw:
        L = mm("waistToFloor") - TROUSER_LENGTHS[lw]
    else:
        L = float(o["length"]) if o["length"] else mm("waistToFloor") - TROUSER_LENGTHS["ankle"]
    knee_y = mm("waistToKnee") if "waistToKnee" in m else rise + 0.45 * (L - rise)
    sq = seat * (1 + o["seat_ease"]) / 4
    wq = waist * (1 + o["waist_ease"]) / 4
    fork_f = seat / 16 + 0.005
    fork_b = 1.5 * fork_f + 0.005  # Aldrich: the front's + half of it + 5 mm
    cut_rule = None
    if o["leg"]:
        knee_c, hem_c, cut_rule = leg_cut(m, o["leg"])
    hem = float(o["hem"]) if o["hem"] else hem_c if o["leg"] else 0.22
    knee = float(o["knee"]) if o["knee"] else knee_c if o["leg"] else hem + 0.03
    log = ([cut_rule] if cut_rule else []) + [f"trouser length {L * 1000:.0f} mm from the waist ({lw or ('given' if o['length'] else 'ankle: the default')})",
           f"trouser: seat quarter {sq * 1000:.0f} (front -10, back +10 mm), body rise {rise * 1000:.0f} mm "
           f"({'given' if o['rise'] else 'measured: waist to the crotch + ease' if measured else 'estimated 0.175 x waist + 154 mm'}), forks front "
           f"{fork_f * 1000:.0f} / back {fork_b * 1000:.0f} mm, knee {knee * 1000:.0f}, hem {hem * 1000:.0f} mm"]
    out = {}
    Y = lambda y: -y
    drop = 0.0  # the back fork point is dropped until the back inseam is 5 mm SHORTER than the front's (it is
    # stretched onto the front between fork and knee: that hollows the back thigh under the seat)
    for which in ("front", "back", "back", "back", "back", "back", "back"):
        fr = which == "front"
        if not fr and "back" in out:
            diff = edge_length(out["back"], "fork>inKnee>inHem") - (edge_length(out["front"], "fork>inKnee>inHem") - 0.005)
            if abs(diff) < 2e-4:
                break
            drop += diff * 1.1
        w = sq - 0.01 if fr else sq + 0.01
        fork = fork_f if fr else fork_b
        fd = 0.0 if fr else drop
        # x = 0 at the centre (front / back) seam's line at the seat, the side seam at +x... drawn with the fork at -x
        crease = 0.5 * (w - fork)  # midway between the side seam and the fork point at the crotch line
        kn = (knee - 0.01 if fr else knee + 0.01) / 2
        hm = (hem - 0.01 if fr else hem + 0.01) / 2
        cin = 0.01 if fr else 0.035  # the centre seam leans in at the waist (much more at the back: the seat angle)
        up = 0.0 if fr else 0.02  # and the back's is raised
        dart = 0.0 if fr else float(o["back_dart"])
        side_w = cin + wq + dart
        pts = [("cWaist", [cin, Y(-up)])]
        if dart > 0:
            dx = cin + 0.5 * wq
            dl = float(o["dart_length"]) if o["dart_length"] else 0.11
            tp = float(o["dart_taper"])
            A_, T_, B_ = np.array([dx, Y(-up * 0.5)]), np.array([dx + dart / 2, Y(dl)]), np.array([dx + dart, Y(-up * 0.5)])
            pts += [("dartA", A_.tolist())]
            if tp > 0:
                # a shaped dart: its legs run in toward the fold over the last third, so the tip dies away to nothing
                # (straight legs meet at the full angle: a poke at the dart's point); both legs alike = equal lengths
                mid = lambda P_: (T_ + (P_ - T_) * 0.35 - np.array([(P_ - T_)[0] * 0.35 * tp, 0.0])).tolist()
                pts += [(None, mid(A_)), ("dartTip", T_.tolist()), (None, mid(B_))]
            else:
                pts += [("dartTip", T_.tolist())]
            pts += [("dartB", B_.tolist())]
        pts += [("sideWaist", [min(side_w, w + 0.01), Y(0.0)])]
        pts += _curve_pts(bez([min(side_w, w + 0.01), 0], [w, Y(0.4 * wts)], [w, Y(0.8 * wts)], [w, Y(wts)]))
        pts += [("sideSeat", [w, Y(wts)])]
        # one smooth line from the hip to the knee (a straight drop to the crotch line and then a curve kinked)
        pts += _curve_pts(bez([w, Y(wts)], [w, Y(wts + 0.45 * (knee_y - wts))], [crease + kn, Y(knee_y - 0.40 * (knee_y - wts))],
                              [crease + kn, Y(knee_y)]))
        dh = dh_crease["front" if fr else "back"]
        pts += [("sideKnee", [crease + kn, Y(knee_y)]), ("sideHem", [crease + hm, Y(L)])]
        if abs(dh) > 1e-4:  # a sloped hem: the crease's point higher at the front, lower at the back
            pts += [("creaseHem", [crease, Y(L + dh)])]
        pts += [("inHem", [crease - hm, Y(L)]),
                ("inKnee", [crease - kn, Y(knee_y)])]
        pts += _curve_pts(bez([crease - kn, Y(knee_y)], [crease - kn, Y(knee_y - 0.35 * (knee_y - rise))],
                              [-fork + 0.25 * fork, Y(rise + fd + 0.12 * (knee_y - rise))], [-fork, Y(rise + fd)]))
        pts += [("fork", [-fork, Y(rise + fd)])]
        # the crotch curve: from the fork round into the centre seam at the seat line
        pts += _curve_pts(bez([-fork, Y(rise + fd)], [-fork * 0.35, Y(rise + fd)], [0.0, Y(rise - 0.35 * (rise - wts))], [0.0, Y(wts)]))
        pts += [("cSeat", [0.0, Y(wts)])]
        pc = make_piece(which, pts, "leg_front" if fr else "leg_back", {"to": f"leg.L", "side": which}, "pair", {},
                        {"crease": [[crease, Y(-up)], [crease, Y(L + dh)]], "seat": [[0, Y(wts)], [w, Y(wts)]],
                         "knee": [[crease - kn, Y(knee_y)], [crease + kn, Y(knee_y)]]})
        if dart > 0:
            pc["darts"]["dart"] = ("dartA", "dartTip", "dartB")
        out[which] = pc
    # the side seams trued: the back's top is raised (or dropped) until both are the same length (its waist then
    # runs up from the side to the centre back a little less)
    for _ in range(3):
        diff = edge_length(out["front"], "sideWaist>sideSeat>sideHem") - edge_length(out["back"], "sideWaist>sideSeat>sideHem")
        out["back"]["P"][out["back"]["names"]["sideWaist"], 1] += diff
    seams = [["front:sideWaist>sideSeat>sideHem", "back:sideWaist>sideSeat>sideHem"],
             ["front:fork>inKnee>inHem", "back:fork>inKnee>inHem"]]
    notes = {'["front:fork>inKnee>inHem", "back:fork>inKnee>inHem"]': {
        "ease": [0.004, 0.009], "why": "the back inseam is stretched onto the front (5 mm)"}}
    if "dartA" in out["back"]["names"]:
        seams.append(["back:dartA>dartTip", "back:dartB>dartTip"])
    centre_seams = {"front": "cWaist>cSeat>fork", "back": "cWaist>cSeat>fork"}
    ins = [edge_length(out[k], "fork>inKnee>inHem") for k in ("front", "back")]
    log.append(f"inseams front {ins[0] * 1000:.0f} / back {ins[1] * 1000:.0f} mm: the back fork dropped {drop * 1000:.0f} mm "
               "so the back is 5 mm shorter (stretched onto the front above the knee)")
    return {"pieces": out, "seams": seams, "meta": {"kind": "trouser", "rise": rise, "options": o, "low": "sideHem",
                                                     "centre_seams": centre_seams},
            "log": log, "centre": {"front": "seam", "back": "seam"}, "notes": notes}
