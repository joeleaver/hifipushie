"""Tailored-jacket drafting rules: the principles in docs/notes/tailoring_principles.md (R1..R26), as numbers drafted
from the body's tape for ANY body, and the operations that apply them. Learned by reading FreeSewing's Jaeger (MIT,
Joost De Cock and contributors; our pack 4.10.2) as a reference and written in our own terms; nothing is wrapped.

  rules(tape_mm, button_mm)  every derived value {"value", "source": "tailoring_principles.md R<n>"} (m unless _mm)
  jacket_ops(ops, tape_mm, button_mm, pockets)  a jacket design's op list rewritten with the rules (each op sourced):
                 the neckline from the neck girth, waist suppression shared CB / panel seams / front dart, overlap from
                 the button, the button spacing, a two-piece collar, flap + chest-welt pockets.
Operations (registered in pattern_draft.OPS):
  jacket_neck        back neck width and rise set from the neck girth (R3, R4)
  waist_suppression  the waist taken in to its target ease, shared CB / side-back / side-front / front dart (R8, R10)
  collar_two_piece   a straight stand + a sprung fall drafted from the neckline's length (R16-R18, R26)
Gate rows: `tailor_rows(Bp, ...)` (cloth_check.pattern_gate appends them for a jacket): T1..T7 with their rule numbers.
"""
from __future__ import annotations

import math

import numpy as np

from . import pattern, pattern_blocks as pb
from . import pattern_draft as pd
from .pattern_draft import DraftError, edge_length

DOC = "tailoring_principles.md"


def src(*n) -> str:
    return f"{DOC} " + ", ".join(f"R{k}" for k in n)


# ---------------------------------------------------------------- the rules as numbers
EASE = {"chest": 0.08, "waist": 0.14, "hips": 0.12}  # R1 (a jacket over a shirt; Jaeger / Bent defaults)
SHARE = {"cb": 0.16, "side_back": 0.32, "side_front": 0.32, "dart": 0.20}  # R8: of the half reduction
COLLAR = {"stand_frac": 0.0625, "stand_mm": (25.0, 30.0), "fall_over_mm": 10.0, "spread_deg": 13.0, "roll": 0.05,
          "rise": 0.035}  # R16-R18
# R16 (fit round 2): the collar at CB measured from the ROLL LINE: stand (neck seam -> roll line) = neck / 16 held to
# 25-30 mm, fall (roll line -> edge) = stand + 10 mm (practice: Mueller & Sohn stand 2.5-3 cm; the fall 6-15 mm deeper
# than the stand so it covers the seam; cloth_checklist collar_stand / collar_fall). Jaeger's 18 % of neck split 30 / 70
# (our first R16) gave stand 28.5 / fall 56: 27 mm too deep, and it grew with the neck (a 522 neck: stand 36).
FALL_FRONT = 0.5  # R15 (fit round 2): the fall's height at its end, x its CB height: the notch gap 20-40 mm (0.8: 53-61)
# R16 (fit round 2): the fall's fold (roll) line, `at` m above its seam on the stand: the fall rises that little with
# the stand, then turns down over it and hides the seam. Without the line the dress form left the fall standing up like a
# hood (fit round 1: fall top 71 mm above the neck point; the gate's flat_pattern row refused it)
FALL_FOLD = {"at": 0.004, "angle": 10.0, "radius": 0.004, "strength": 0.6}
# R18 (fit round 2, Joe via coordinator: "account for the turn of cloth from the fabric, not fixed fudges"): the fall's
# extra depth and outer-edge length come from what it wraps over. Layers: the collar = upper + under collar + canvas; at
# the roll line the fall wraps over the jacket's stand (same stack) and the shirt's collar (stand + its turned fall, each
# 2 layers + interfacing: 6 shirting thicknesses).
TURN = {"fabric": "wool_suiting", "canvas": "hair_canvas", "under": "cotton_shirting", "under_layers": 6}
# R28 (fit round 18, Joe's notch tab): the STAND RUNS OFF toward the collar's end. The collar's roll line is the lapel's
# roll line run on (R14: one line when worn), so the stand's height falls to (near) nothing where the lapel's roll line
# crosses the gorge (pattern_draft._roll_meets_neck); past it the whole collar is fall, lying flat on the turned lapel.
# Drafted with the one-piece collar's profile (op_collar: h = stand x (1 - (s / s_x)^p), p from the crossing angle),
# floored at `end` m (a band of cloth, not a zero-width strip). Off = the stand drafted to stand_front at the notch
# (fit rounds 2-17: the stand's end stood 7-30 mm off the lapel and carried the fall's end as a tab).
STAND_RUN_OFF = {"on": False, "end": 0.003, "over": 0.03}  # OPT-IN: on the form the fall still turns 172 deg past s_x (fit round 18)


def _thick_mm(name: str, default: float) -> float:
    """A KB fabric's thickness (mm, the middle of its thickness_mm), `default` for a name the KB doesn't have."""
    from . import garment_design
    e = ((garment_design.kb().get("fabrics") or {}).get(name)) if isinstance(name, str) else None
    t = (e or {}).get("thickness_mm")
    return 0.5 * (float(t[0]) + float(t[1])) if t else float(default)


def turn_stack(fabric: str | None = None, canvas: str | None = None, under: str | None = None,
               under_layers: int | None = None) -> dict:
    """The turn of cloth at the collar's roll line, from the fabrics (mm): t_fall (the fall's own stack: 2 cloth +
    canvas), t_under (what it wraps over: the stand's stack + the shirt collar's), depth (the fall's height spent in
    the turn: a hairpin of its own stack, pi/2 x t_fall, + the step out over the under-stack), ring (how far out the
    fall wraps at the roll line: t_under + t_fall; a record, it sets no length) and ring_outer (how far the outer edge's
    mid-surface stands off the jacket body's mid-surface where it lands: half the fall's stack + half the body cloth).
    length_mm = pi x ring_outer: the half outer edge's growth over the path measured on the flat body pieces (half a
    ring's). Fit round 3: the outer edge lies on the jacket body, not on the stand + shirt collar, so the under-stack
    never reaches it (round 2 used pi x ring = 17.3 mm, 13 mm too long: the spread solved to 43 deg)."""
    t = _thick_mm(fabric or TURN["fabric"], 0.75)
    tc = _thick_mm(canvas or TURN["canvas"], 0.5)
    tu = _thick_mm(under or TURN["under"], 0.25)
    n = TURN["under_layers"] if under_layers is None else int(under_layers)
    t_fall = 2 * t + tc
    t_under = (2 * t + tc) + n * tu
    ring = t_under + t_fall
    ring_o = 0.5 * (t_fall + t)
    return {"cloth_mm": t, "canvas_mm": tc, "under_mm": tu, "t_fall_mm": round(t_fall, 3), "t_under_mm": round(t_under, 3),
            "depth_mm": round(math.pi / 2 * t_fall + t_under, 2), "ring_mm": round(ring, 3),
            "ring_outer_mm": round(ring_o, 3), "length_mm": round(math.pi * ring_o, 2),
            "source": src(18) + " (fit round 2: turn of cloth from the fabrics' KB thickness; canvas inferred)"}


def fall_path(pcs: dict, chain: list, drop: float, step: float = 0.003) -> float:
    """The path the fall's outer edge lies on (m, one half: CB -> the collar's end): the neckline `chain` ("piece:a>b"
    arcs the collar is sewn to) offset `drop` into the body pieces (where the turned fall's edge lands, below the neck
    seam), each arc run on to its piece's outline."""
    tot = 0.0
    for e in chain:
        nm = e.split(":")[0]
        L = pattern.fold_line(pcs, {"piece": nm, "line": {"edge": e, "offset": float(drop)}}, step)
        tot += pattern.length(L)
    return tot


def fall_need(pcs: dict, chain: list, drop_cb: float, drop_end: float, ts: dict, step: float = 0.003) -> tuple:
    """R18: the length the half fall's outer edge needs (m) and its parts (mm). The edge lands `drop` below the neck
    seam, tapering like the collar's heights (both u^2 from CB to the end: drop(u) = drop_cb + (drop_end - drop_cb) u^2,
    u = the arc-length fraction along the neckline, clamped >= 0). Each neckline arc is offset by its mean drop
    (fall_path), + pi x the edge's stand-off on the body (turn_stack length_mm). Fit round 3: round 2 offset the whole
    neckline by the CB drop (10 mm) although the fall's end barely passes the seam."""
    Ls = []
    for e in chain:
        nm = e.split(":")[0]
        Ls.append(pattern.length(pcs[nm]["P"][pattern.arc_indices(pcs[nm], e.split(":", 1)[1])]))
    c = np.r_[0.0, np.cumsum(Ls)] / max(sum(Ls), 1e-9)
    tot, parts = 0.0, {}
    for i, e in enumerate(chain):
        u = np.linspace(c[i], c[i + 1], 21)
        dr = float(np.mean(np.maximum(drop_cb + (drop_end - drop_cb) * u * u, 0.0)))
        L = fall_path(pcs, [e], dr, step)
        tot += L
        parts[e] = {"arc_mm": round(Ls[i] * 1000, 1), "drop_mm": round(dr * 1000, 1), "path_mm": round(L * 1000, 1)}
    parts["ring_mm"] = ts["length_mm"]
    return tot + ts["length_mm"] / 1000, parts


def rules(tape: dict, button_mm: float = 20.0) -> dict:
    """The jacket's drafted values from the body's tape (mm in, m out unless the key says _mm)."""
    neck, chest, waist = float(tape["neck"]), float(tape["chest"]), float(tape["waist"])
    w2a, w2h = float(tape.get("waistToArmpit", 0.46 * tape["hpsToWaistBack"])), float(tape.get("waistToHips", 150.0))
    r = {}

    def put(k, v, *n):
        r[k] = {"value": float(v), "source": src(*n)}
    put("back_neck_width", (neck * 1.035 / 4.8 - 0.005 * chest) / 1000, 3)
    put("back_neck_rise", 0.05 * neck / 1000, 4)
    put("armhole_below_armpit", 0.15 * w2a / 1000, 6)
    put("chest_ease", EASE["chest"], 1)
    put("waist_ease", EASE["waist"], 1, 8)
    put("hips_ease", EASE["hips"], 1)
    red = chest * (1 + EASE["chest"]) - waist * (1 + EASE["waist"])
    put("waist_reduction", max(red, 0) / 1000, 8)
    put("dart_up", 0.0, 10)  # (set from the draft's armhole -> waist: 2/3 of it)
    put("dart_down", w2h / 1.5 / 1000, 10)
    put("overlap", button_mm / 1000, 12)
    roll_st = min(max(COLLAR["stand_frac"] * neck, COLLAR["stand_mm"][0]), COLLAR["stand_mm"][1])  # seam -> roll line
    fat = FALL_FOLD["at"] * 1000  # (the fall rises this far with the stand before it turns)
    put("collar_stand_cb", (roll_st - fat) / 1000, 16)  # the stand PIECE
    put("collar_fall_cb", (roll_st + COLLAR["fall_over_mm"] + fat) / 1000, 16)  # the fall PIECE (before the roll's 5 %)
    put("collar_spread_deg", COLLAR["spread_deg"], 18)
    put("collar_rise", COLLAR["rise"] * neck / 1000, 17)
    put("roll_height", 0.06 * neck / 1000, 14)
    put("button_spacing_frac", 0.30, 13)
    put("pocket_width_frac", 0.68, 21)
    put("pocket_below_waist", w2h / 1.5 / 3 / 1000, 21)
    put("flap_depth_frac", 0.33, 21)
    put("chest_pocket_width_frac", 0.37, 22)
    put("chest_welt_frac", 0.175, 22)
    put("chest_pocket_deg", 2.5, 22)
    return r


# ---------------------------------------------------------------- helpers
def _span_at(P: np.ndarray, y: float) -> float:
    """Total width of a closed outline inside the line y = const (darts cut out of the outline are not counted).
    Half-open crossings ((a > y) != (b > y)): a vertex ON the line (a contour op puts one at the waist / hips level)
    counts once. The strict product test missed it: Tess's coat read chest / waist / hips 0 mm (dress-tess s19)."""
    xs = []
    n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        if (a[1] > y) != (b[1] > y):
            xs.append(a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]))
    xs.sort()
    return float(sum(xs[k + 1] - xs[k] for k in range(0, len(xs) - 1, 2)))


def torso_span(D_or_Bp: dict, y: float, half: bool = True) -> float:
    """Garment girth at level y: spans of every torso piece (front / back roles), x2 for a half draft."""
    s = 0.0
    for nm, pc in D_or_Bp["pieces"].items():
        if pc.get("role") in ("front", "back"):
            s += _span_at(np.asarray(pc["P"], float), y)
    return s * (2 if half else 1)


def _pt(pc, n):
    return np.asarray(pc["P"][pc["names"][n]], float)


# ---------------------------------------------------------------- operations
def op_jacket_neck(D: dict, width: float | None = None, rise: float | None = None, **o) -> None:
    """R3 / R4: the back neck point `width` from the centre back neck and `rise` above it (default: from the neck
    girth). The front neck point moves with it (op_neckline: shoulder seams stay equal); the front is not lowered."""
    m = D["meta"]["measurements"]
    R = rules(m)
    width = R["back_neck_width"]["value"] if width is None else float(width)
    rise = R["back_neck_rise"]["value"] if rise is None else float(rise)
    pc = D["pieces"]["back"]
    hps, cb = _pt(pc, "hps"), _pt(pc, "cbNeck")
    sh = _pt(pc, "shoulder")
    sdir = (sh - hps) / np.linalg.norm(sh - hps)
    widen = (width - abs(hps[0] - cb[0])) / max(abs(sdir[0]), 0.5)
    new_hps_y = hps[1] + widen * sdir[1]
    back = cb[1] - (new_hps_y - rise)  # > 0 lowers the centre back
    from .pattern_styles import op_neckline
    op_neckline(D, widen=widen, back=back, signed=True)
    pc = D["pieces"]["back"]
    D["log"].append(f"jacket neck ({src(3, 4)}): back neck {abs(_pt(pc, 'hps')[0] - _pt(pc, 'cbNeck')[0]) * 1000:.1f} wide, "
                    f"rise {(_pt(pc, 'hps')[1] - _pt(pc, 'cbNeck')[1]) * 1000:.1f} mm (targets {width * 1000:.1f} / {rise * 1000:.1f})")


SILHOUETTES = ("suit", "straight", "plumb")  # R8's style: how much waist shaping beyond the body's own


# R8 "straight" (fit round 12, read from Garrett's concept): the sides hang straight in the front view. The concept's
# torso width over the BARE body is near uniform, 115 / 122 / 124 mm at 350 / 425 / 500 mm below HPS (the body itself is
# straight in width, 281 / 278 / 305: its 18.5 % chest -> waist girth drop is in depth), where the suit default left 92 /
# 79 / 91 (fit round 12 bodyrows.py): the hourglass is the draft's side take-ins, not the body. Straight keeps the CB and
# dart take-ins of the suit (the same mm: they shape the back and the front over the body's depth) and takes nothing at
# the side-back / side-front seams: the American sack's straight sides (Flusser, Dressing the Man: the sack "hangs
# straight from the shoulders"; Cabrera & Flaherty: suppression is a style choice of the side seams).
STRAIGHT_SIDES = ("side_back", "side_front")
# R8 "plumb" (fit round 24, Joe 2026-10-20 for Garrett: the jacket "should basically just fall straight down"): NO waist
# take-in anywhere (CB, side-back, side-front, front dart), so the cloth hangs from the chest and the shoulder blades and
# bridges the waist. "straight" still pinched the hollow: its CB + dart take-ins and the block's own fitted side seam
# (pattern_blocks: fitted takes up to 25 mm a quarter) left the flat waist 45-85 mm under the chest, and on the form the
# waist followed the body's hollow (C88). A plumb draft also wants block_options fitted False and no CB contour; the
# gate row waist_plumb checks the outcome on the flat pattern: waist girth >= chest girth x (1 - PLUMB_TOL), and the
# hips no narrower than the waist. PLUMB_TOL 0.03 (~35 mm on Garrett's 1150 chest): the cloth's own drape over the
# 15 % chest ease; the sack coat's straight body (Flusser: "hangs straight from the shoulders").
PLUMB_TOL = 0.03
# The plumb GIRTH below the chest (fit round 26, C94): a straight-hanging body needs the tube round the torso from the
# chest to the seat (tape plumbGirth: the hull of the union of those sections; Garrett 995) + what goes under it and
# its own layer, not the chest's full ease carried down (Garrett r24c: +116 over the tube, ~+55 surplus standing off at
# the sides and back). PLUMB_ALLOW = the under garment's allowance (layered_fit outer_first LAYER_ALLOW 8 mm all round:
# 2 pi x 8 = 50) + one cloth layer (2 pi x 1.6 = 10). The cut takes the surplus in at the side-back / side-front seams
# and CB (PLUMB_SHARE, where it stood off) from PLUMB_RAMP under the chest line down to the hem, ramped in over the
# PLUMB_RAMP above that: the sides still hang plumb below it. The gate row waist_plumb holds the girth (less the lap)
# from there to the hips in [target - PLUMB_FLOOR_TOL, target + PLUMB_CEIL].
PLUMB_ALLOW = 2 * math.pi * (0.008 + 0.0016)
PLUMB_RAMP = 0.10
PLUMB_SHARE = {"cb": 0.70, "side_back": 0.30, "side_front": 0.0}
PLUMB_FLOOR_TOL, PLUMB_CEIL = 0.010, 0.025


def plumb_target(m: dict) -> float | None:
    """The plumb cut's girth under the chest (m: tape, mm), or None for a tape without plumbGirth (the chest's kept)."""
    pg = (m or {}).get("plumbGirth")
    return None if not pg else float(pg) / 1000 + PLUMB_ALLOW


def _lap(D_or_Bp: dict, y: float) -> float:
    """Girth the fronts add past CF at level y (the laps): each front piece's span on the far side of x = 0."""
    s = 0.0
    for pc in D_or_Bp["pieces"].values():
        if pc.get("role") != "front":
            continue
        P = np.asarray(pc["P"], float)
        sg = 1.0 if np.median(P[:, 0]) > 0 else -1.0
        Q = P.copy()
        Q[:, 0] = np.where(sg * Q[:, 0] < 0, Q[:, 0], 0.0)  # the outline clipped to the far side of CF
        s += _span_at(Q, y)
    half = not any("." in k for k in D_or_Bp["pieces"])
    return s * (2 if half else 1)


def _plumb_cut(D: dict) -> None:
    """R8 plumb + C94: take the girth under the chest to plumb_target (see PLUMB_ALLOW)."""
    import copy as _copy
    target = plumb_target(D["meta"].get("measurements"))
    if target is None:
        D["log"].append("plumb girth: no plumbGirth on the tape; the chest's girth carried down")
        return
    yf = float(D["meta"]["chest_y"]) - PLUMB_RAMP
    now = torso_span(D, yf) - _lap(D, yf)
    red = (now - target) / 2  # per half
    if red <= 0.002:
        D["log"].append(f"plumb girth: {now * 1000:.0f} within the tube's {target * 1000:.0f} mm")
        return

    def cut(Dx, r):
        pcb = Dx["pieces"]["back"]
        arc = Dx["edges"]["centre_back"][0].split(":", 1)[1]
        pd.densify_edge(pcb, arc)
        ix = pattern.arc_indices(pcb, arc)
        L = pcb["P"][ix]
        sgn = 1.0 if pcb["P"][:, 0].mean() > L[:, 0].mean() else -1.0
        pcb["P"][ix, 0] = L[:, 0] + sgn * r * PLUMB_SHARE["cb"] * pd.take_in_weight(L[:, 1], yf, PLUMB_RAMP, below=True)
        for ln, k in (("sideB", "side_back"), ("sideF", "side_front")):
            if ln in Dx["lines"]:
                pd.op_take_in(Dx, ln, r * PLUMB_SHARE[k], y=yf, length=PLUMB_RAMP, below=True)

    trial = _copy.deepcopy(D)
    cut(trial, red)
    got = now - (torso_span(trial, yf) - _lap(trial, yf))
    gain = float(np.clip(2 * red / got, 0.8, 1.6)) if got > 1e-4 else 1.0
    cut(D, red * gain)
    D["log"].append(f"plumb girth (C94): under the chest {now * 1000:.0f} -> tube {target * 1000:.0f} mm (plumbGirth "
                    f"{(target - PLUMB_ALLOW) * 1000:.0f} + {PLUMB_ALLOW * 1000:.0f}), {red * gain * 1000:.1f} per half "
                    f"(gain {gain:.2f}) from {PLUMB_RAMP * 1000:.0f} mm under the chest to the hem; now "
                    f"{(torso_span(D, yf) - _lap(D, yf)) * 1000:.0f}")


def op_waist_suppression(D: dict, waist_ease: float | None = None, share: dict | None = None, dart_x: float = 0.55,
                         silhouette: str = "suit", **o) -> None:
    """R8 / R10 (see _suppress): the shares are scaled so the waist lands on its target (the seam take-ins fade above
    and below the waist, so a first pass on a copy measures what each mm of take-in really removes). silhouette (R8's
    style, a design choice read from the reference's row profile): "suit" = the waist at R1's waist ease (11-20 % of the
    chest taken in, shared CB / side-back / side-front / dart); "straight" = the suit's CB and dart take-ins only, the
    sides straight (STRAIGHT_SIDES)."""
    import copy as _copy
    if silhouette not in SILHOUETTES:
        raise ValueError(f"waist_suppression silhouette {silhouette!r}: one of {SILHOUETTES}")
    if silhouette == "plumb":
        D["log"].append("waist suppression R8 silhouette plumb: none (CB, side panels and dart untouched; Joe 2026-10-20)")
        _plumb_cut(D)
        return
    if silhouette == "straight":  # (the suit's CB / dart mm, no side take-ins: no gain, which would scale them up)
        share = dict(SHARE, **(share or {}), **{k: 0.0 for k in STRAIGHT_SIDES})
        _suppress(D, waist_ease, share, dart_x, gain=1.0)
        D["meta"].pop("_supp_want", None)
        D["log"].append("waist suppression R8 silhouette straight: no side-back / side-front take-ins")
        return
    if o.get("_gain") is None:
        trial = _copy.deepcopy(D)
        _suppress(trial, waist_ease, share, dart_x, gain=1.0)
        wy = float(D["meta"]["waist_y"])
        want, got = trial["meta"].get("_supp_want"), torso_span(D, wy) - torso_span(trial, wy)
        gain = float(np.clip(want / got, 1.0, 1.6)) if want and got > 1e-4 else 1.0
    else:
        gain = float(o["_gain"])
    _suppress(D, waist_ease, share, dart_x, gain=gain)
    D["meta"].pop("_supp_want", None)


def _suppress(D: dict, waist_ease, share, dart_x, gain: float = 1.0) -> None:
    """R8 / R10: measure the draft's waist now, take it to waist x (1 + waist_ease), the reduction shared as a tailor
    shares it: centre back, the side-back and side-front panel seams (shaved on both edges), and a front fish-eye dart
    `dart_x` of the way from CF to the front's side seam, 2/3 of armhole -> waist up and 2/3 of waist -> hips down."""
    m = D["meta"]["measurements"]
    we = EASE["waist"] if waist_ease is None else float(waist_ease)
    sh = dict(SHARE, **(share or {}))
    wy = float(D["meta"]["waist_y"])
    now = torso_span(D, wy)
    target = float(m["waist"]) * (1 + we) / 1000
    red = (now - target) / 2  # per half
    D["meta"]["_supp_want"] = 2 * red
    red *= gain
    if red <= 0.002:
        D["log"].append(f"waist suppression: waist {now * 1000:.0f} already within {target * 1000:.0f} mm")
        return
    # centre back: the back's CB edge in by its share at the waist, faded like a seam take-in
    pcb = D["pieces"]["back"]
    arc = D["edges"]["centre_back"][0].split(":", 1)[1]
    pd.densify_edge(pcb, arc)
    ix = pattern.arc_indices(pcb, arc)
    L = pcb["P"][ix]
    # the shaping fades out by the hip line (R8: the hips keep their own ease; a fade past it pulled the hips in to
    # -0.4 % on Garrett's first v2)
    fade = 0.9 * (wy - float(D["meta"].get("hips_y", wy - 0.16)))
    w = np.clip(1 - np.abs(L[:, 1] - wy) / fade, 0, 1)
    w = w * w * (3 - 2 * w)
    sgn = 1.0 if pcb["P"][:, 0].mean() > L[:, 0].mean() else -1.0
    top = L[:, 1] > float(D["meta"].get("chest_y", wy + 0.2))
    w[top] = 0.0
    pcb["P"][ix, 0] = L[:, 0] + sgn * red * sh["cb"] * w
    for ln, k in (("sideB", "side_back"), ("sideF", "side_front")):
        if ln in D["lines"]:
            pd.op_take_in(D, ln, red * sh[k], length=fade)
    # the front dart
    pf = D["pieces"]["front"]
    P = np.asarray(pf["P"], float)
    xs = []
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        if (a[1] - wy) * (b[1] - wy) < 0:
            xs.append(a[0] + (b[0] - a[0]) * (wy - a[1]) / (b[1] - a[1]))
    side = max(xs, key=abs) if xs else 0.15
    up = (float(D["meta"].get("chest_y", wy + 0.22)) - wy) / 1.5
    down = rules(m)["dart_down"]["value"]
    from .pattern_tailor import op_fisheye
    op_fisheye(D, "front", x=dart_x * side, width=red * sh["dart"], up=up, down=down, name="frontDart")
    D["log"].append(f"waist suppression ({src(8, 10)}): waist {now * 1000:.0f} -> target {target * 1000:.0f} mm "
                    f"(+{we * 100:.0f}%), {red * 1000:.1f} per half: CB {red * sh['cb'] * 1000:.1f}, side back "
                    f"{red * sh['side_back'] * 1000:.1f}, side front {red * sh['side_front'] * 1000:.1f}, dart "
                    f"{red * sh['dart'] * 1000:.1f}; now {torso_span(D, wy) * 1000:.0f}")


def _resample(E: np.ndarray, n: int) -> np.ndarray:
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
    t = np.linspace(0, s[-1], n)
    return np.c_[np.interp(t, s, E[:, 0]), np.interp(t, s, E[:, 1])]


def _offset(E: np.ndarray, h: np.ndarray) -> np.ndarray:
    t = np.gradient(E, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.c_[-t[:, 1], t[:, 0]]  # left of travel (+y at CB: the collar's body)
    return E + nrm * h[:, None]


def collar_shapes(lb: float, lf: float, stand_cb: float, fall_cb: float, stand_front: float, fall_front: float,
                  rise: float, spread_deg: float, roll: float, point: float = 0.0, n: int = 41,
                  run_off: tuple | None = None) -> dict:
    """The two collar pieces as halves, CB at x = 0 (pure geometry: the known-answer tests use it).
    STAND: its neck edge runs straight across the back neck (lb) and rises `rise` over the front part (lf), as a
    gentle quadratic: a band, not the neckline's curve (R17); its top edge is that line offset by the stand's height
    (stand_cb at CB to stand_front at the end), so it is a little shorter than the neck edge and leans in to the neck.
    FALL: its lower edge is the stand's top edge (the roll line, same length: sewn to it); it is turned progressively
    by `spread_deg` over its length (the spread a tailor slashes in at the front) so its outer edge is longer by
    ~ fall x spread: it lies over the stand and down onto the shoulders (R18); `roll` (fraction) adds height to the
    outer edge for the turn of the cloth."""
    L = lb + lf
    s = np.linspace(0, L, 4 * n)
    y = rise * np.clip((s - lb) / max(lf, 1e-6), 0, 1) ** 2
    E = _resample(np.c_[s, y], n)
    # (resampled to its true length L: the band's length is the neckline's)
    E *= 1.0
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
    E = np.c_[np.interp(np.linspace(0, seg[-1], n), seg, E[:, 0]), np.interp(np.linspace(0, seg[-1], n), seg, E[:, 1])]
    k = L / seg[-1]
    E = E * k
    u = np.linspace(0, 1, n)
    hs = stand_cb + (stand_front - stand_cb) * u * u  # (square to the fold at CB: no kink in the roll line)
    if run_off is not None:
        # R28: the stand runs off to `end` at s_x (where the lapel's roll line crosses the gorge), `end` beyond it
        sx, phi, h_end = float(run_off[0]), float(run_off[1]), float(run_off[2])
        se = np.r_[0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
        pw = float(np.clip(math.tan(phi) * sx / max(stand_cb, 1e-6), 1.5, 6.0))
        hs = np.maximum(hs * np.clip(1 - (se / max(sx, 1e-6)) ** pw, 0, None), h_end)
    T = _offset(E, hs)
    # fall: lower edge = T, turned by an angle growing along it (outer edge on the outside of the turn)
    th = math.radians(spread_deg)
    d = np.diff(T, axis=0)
    seglen = np.linalg.norm(d, axis=1)
    ang = np.arctan2(d[:, 1], d[:, 0]) - th * (np.cumsum(seglen) - 0.5 * seglen) / seglen.sum()
    F = np.vstack([[0.0, 0.0], np.cumsum(np.c_[np.cos(ang), np.sin(ang)] * seglen[:, None], axis=0)])
    hf = (fall_cb + (fall_front - fall_cb) * u * u) * (1 + roll)
    O = _offset(F, hf)
    # the fall's centre back square to the fold (x = 0): turned about its CB foot so cbLow -> cbOuter is vertical
    v = O[0] - F[0]
    a = math.pi / 2 - math.atan2(v[1], v[0])
    Rm = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    F, O = (F - F[0]) @ Rm.T, (O - F[0]) @ Rm.T
    O[0, 0] = 0.0
    if point:
        tt = O[-1] - O[-2]
        O[-1] = O[-1] + tt / np.linalg.norm(tt) * point
    return {"stand_neck": E, "stand_top": T, "fall_low": F, "fall_out": O, "k_shoulder": int(np.argmin(np.abs(
        np.r_[0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))] - lb)))}


def op_collar_two_piece(D: dict, stand_cb: float | None = None, fall_cb: float | None = None,
                        stand_front: float | None = None, fall_front: float | None = None, rise: float | None = None,
                        spread_deg: float | None = None, roll: float | None = None, point: float = 0.0,
                        ease: float = 0.0, stand: str = "stand", name: str = "collar", fold_at: float | None = None,
                        **o) -> None:
    """A tailored jacket's collar in two pieces (R16-R18, R26): a near-straight STAND (the neckline's length, back neck
    + the gorge up to the notch) and a sprung FALL sewn to the stand's top edge (the roll line). Defaults from the
    neck girth (rules). `ease` (fraction, R26): the stand's neck edge cut that much shorter than the neckline and
    eased on (0: sewn 1:1). `fold_at` (m, R16; default FALL_FOLD): the fall's fold line, parallel to its seam on the
    stand that far into the fall, about which it turns down over the stand (folds.py). Point names: stand cb, shoulderNotch, cf, cfTop, cbTop; fall cbLow, endLow, endOuter,
    cbOuter. Both cut on the fold at CB."""
    nb, nf = D["edges"].get("neck_back"), D["edges"].get("neck_front")
    if not nb or not nf:
        raise DraftError("collar_two_piece: no neckline edges (neck_back / neck_front)")
    m = D["meta"]["measurements"]
    R = rules(m)
    stand_cb = R["collar_stand_cb"]["value"] if stand_cb is None else float(stand_cb)
    fall_cb = R["collar_fall_cb"]["value"] if fall_cb is None else float(fall_cb)
    stand_front = 0.6 * stand_cb if stand_front is None else float(stand_front)
    fall_front = FALL_FRONT * fall_cb if fall_front is None else float(fall_front)
    rise = R["collar_rise"]["value"] if rise is None else float(rise)
    fat = FALL_FOLD["at"] if fold_at is None else float(fold_at)
    ts = turn_stack(o.get("fabric"), o.get("canvas"), o.get("under"), o.get("under_layers"))
    # R18 turn of cloth: the fall's height spent in the turn (ts depth) instead of a fixed 5 % roll
    roll = ts["depth_mm"] / 1000 / fall_cb if roll is None else float(roll)
    lb, lf = edge_length(D, nb), edge_length(D, nf)
    # R18: the outer edge as long as its path: the neckline offset by where the fall's edge lands (fall - stand from the
    # roll line, below the neck seam) + pi x the ring it stands out by (the under-stack and the fall's own cloth)
    run_off = None
    if o.get("run_off", STAND_RUN_OFF.get("on")):  # (op option "run_off": true turns it on for one design)
        met = pd._roll_meets_neck(D, list(nf), lb)
        if met is not None and met[0] < lb + lf - 0.005:
            # (the outer edge's path is unchanged: past s_x the collar lies in the lapel's plane beside a straight
            # gorge, so its end adds no drop over the body; the spread is solved to that path with the new roll line)
            run_off = (met[0] * (1 - ease), met[1], float(STAND_RUN_OFF["end"]))
    drop = (fall_cb - fat) - (stand_cb + fat)
    drop_end = (fall_front - fat) - (stand_front + fat)
    need, need_parts = fall_need(D["pieces"], list(nb) + list(nf), drop, drop_end, ts)

    def shapes(sp):
        return collar_shapes(lb * (1 - ease), lf * (1 - ease), stand_cb, fall_cb, stand_front, fall_front, rise, sp,
                             roll, point, run_off=run_off)
    if spread_deg is None:  # solved: the spread whose outer edge is the path's length (bisection; length grows with it)
        lo_, hi_ = -10.0, 45.0
        for _ in range(40):
            mid = 0.5 * (lo_ + hi_)
            if pattern.length(shapes(mid)["fall_out"]) < need:
                lo_ = mid
            else:
                hi_ = mid
        spread_deg = 0.5 * (lo_ + hi_)
    spread_deg = float(spread_deg)
    c = shapes(spread_deg)
    E, T, F, O, ks = c["stand_neck"], c["stand_top"], c["fall_low"], c["fall_out"], c["k_shoulder"]
    n = len(E)
    pts = [("cb", E[0])] + [("shoulderNotch" if k == ks else None, E[k]) for k in range(1, n - 1)] + [("cf", E[-1])]
    pts += [("cfTop", T[-1])] + [(None, q) for q in T[-2:0:-1]] + [("cbTop", T[0])]
    wrap = {"to": "seam", "worn": True, "out": 0.004}
    ps = pb.make_piece(stand, pts, "collar_stand", dict(wrap), "fold")
    pts = [("cbLow", F[0])] + [(None, q) for q in F[1:-1]] + [("endLow", F[-1])]
    pts += [("endOuter", O[-1])] + [(None, q) for q in O[-2:0:-1]] + [("cbOuter", O[0])]
    pf = pb.make_piece(name, pts, "collar_fall", dict(wrap, turn={"at": fat, "deg": 172, "gap": 0.004}), "fold")
    # R18 / R27 (fit round 3): the undercollar a turn of cloth smaller at its outer edge (pi/2 x the fall's stack, the
    # seam rolls under out of sight; books trim it ~3 mm), cut on the bias. FUSED to the fall: a cut piece of record,
    # one cloth with the fall in the sim / form (as facings are)
    tu_ = math.pi / 2 * ts["t_fall_mm"] / 1000
    dv = O - F
    Ou = F + dv * np.maximum(1 - tu_ / np.maximum(np.linalg.norm(dv, axis=1, keepdims=True), 1e-9), 0.0)
    pts_u = [("cbLow", F[0])] + [(None, q) for q in F[1:-1]] + [("endLow", F[-1])]
    pts_u += [("endOuter", Ou[-1])] + [(None, q) for q in Ou[-2:0:-1]] + [("cbOuter", Ou[0])]
    under = f"under{name}"
    pu = pb.make_piece(under, pts_u, "undercollar", {**wrap, "out": 0.002, "lies_on": name, "fused": name}, "fold")
    pu["grain"] = 45.0
    pu["traced"] = name
    for pc in (ps, pf, pu):
        if pc["P"][:, 0].mean() < 0:
            pc["P"][:, 0] *= -1
    D["pieces"][stand], D["pieces"][name] = ps, pf
    D["centre"][stand] = D["centre"][name] = "fold"
    D["seams"].append([f"{stand}:cb>shoulderNotch>cf", list(nb) + list(nf)])
    if ease:
        import json as _json
        D["notes"][_json.dumps(D["seams"][-1])] = {"ease": [ease - 0.006, ease + 0.006],
                                                   "why": f"the stand's neck edge eased onto the neckline ({src(26)})"}
    D["seams"].append([f"{name}:cbLow>endLow", f"{stand}:cbTop>cfTop"])
    D["pieces"][under] = pu
    D["centre"][under] = "fold"
    import json as _js
    sm = [f"{under}:endOuter>cbOuter", f"{name}:endOuter>cbOuter"]
    D["seams"].append(sm)
    D["notes"][_js.dumps(sm)] = {"ease": [-0.01, 0.01], "turned": "under",
                                 "why": f"the undercollar ({tu_ * 1000:.1f} mm a turn smaller) sewn to the fall's outer "
                                        f"edge, the seam rolled under ({src(18)})"}
    D["interfaced"] += [stand, name]
    D.setdefault("folds", []).append({"piece": name, "line": {"edge": f"{name}:cbLow>endLow", "offset": fat},
                                      "angle": FALL_FOLD["angle"], "kind": "roll", "radius": FALL_FOLD["radius"],
                                      "strength": FALL_FOLD["strength"], "flap": "cbOuter", "name": "collar roll",
                                      "source": src(16)})
    if run_off is not None:
        # R28 (fit round 19): the fall's crease runs off with the stand: no turn past s_x (the collar's end lies flat
        # on the lapel), fading over STAND_RUN_OFF["over"] before it (folds.fade). Measured along the fall's seam
        Ln = (lb + lf) * (1 - ease)
        D["folds"][-1]["run_off"] = {"ends": "both", "off": round((1 - run_off[0] / Ln) * pattern.length(F), 4),
                                     "over": float(STAND_RUN_OFF.get("over", 0.03))}
    D["edges"][f"{stand}_neck"] = [f"{stand}:cb>shoulderNotch>cf"]
    D["edges"][f"{name}_outer"] = [f"{name}:endOuter>cbOuter"]
    D["meta"]["collar_two_piece"] = {"stand_cb": stand_cb, "fall_cb": fall_cb, "rise": rise, "spread_deg": spread_deg,
                                     "fold_at": fat, "turn": ts, "outer_need_mm": round(need * 1000, 1), "drop_mm": round(drop * 1000, 1),
                                     "drop_end_mm": round(drop_end * 1000, 1), "need_parts": need_parts,
                                     "stand_run_off": None if run_off is None else {
                                         "s_x_mm": round(run_off[0] * 1000, 1),
                                         "before_end_mm": round(((lb + lf) * (1 - ease) - run_off[0]) * 1000, 1),
                                         "angle_deg": round(math.degrees(run_off[1]), 1),
                                         "end_mm": round(run_off[2] * 1000, 1), "source": src(14, 28)}}
    D["log"].append(f"collar two-piece ({src(16, 17, 18)}): stand {stand_cb * 1000:.0f} -> {stand_front * 1000:.0f} mm, "
                    f"neck edge {pattern.length(E) * 1000:.0f} (neckline {(lb + lf) * 1000:.0f}) rising "
                    f"{rise * 1000:.0f} at the front; fall {fall_cb * 1000:.0f} mm, spread {spread_deg:.0f} deg: outer "
                    f"{pattern.length(O) * 1000:.0f} for a roll line of {pattern.length(F) * 1000:.0f} (half)")


def op_lapel_turn(D: dict, piece: str = "front", facing: str | None = None, **o) -> None:
    """R27 (fit round 3): the facing's turn allowance past the roll line. Above the break the lapel turns back over the
    roll line with the facing outermost, so the facing needs pi/2 x the lapel's stack (front cloth + canvas + facing
    cloth, turn_stack t_fall) more width across the fold, and the seam at the lapel edge rolls to the underside. Its
    sewn edge (break -> lapel point -> gorge) is let out by that, nothing at the break (no fold there) growing to
    full at the lapel point and along the gorge; the seam eased (Cabrera & Flaherty: the facing cut 3-6 mm wider at
    the lapel, eased across the roll line). A cut-piece record: the facing is fused (one cloth with the front)."""
    facing = facing or f"{piece}_facing"
    fp = D["pieces"].get(facing)
    if fp is None or "edge.a" not in fp["names"] or "edge.b" not in fp["names"]:
        raise DraftError(f"lapel_turn: no facing {facing} with a sewn edge (edge.a > edge.b)")
    ts = turn_stack(o.get("fabric"), o.get("canvas"))
    tu = math.pi / 2 * ts["t_fall_mm"] / 1000
    P = np.asarray(fp["P"], float).copy()
    ia, ib = fp["names"]["edge.a"], fp["names"]["edge.b"]
    idx = np.arange(ia, ib + 1) if ib >= ia else np.r_[np.arange(ia, len(P)), np.arange(0, ib + 1)]
    E = P[idx]
    lp = (fp.get("marks") or {}).get("lapelPoint")
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
    k_lp = int(np.argmin(np.linalg.norm(E - np.asarray(lp), axis=1))) if lp is not None else len(E) - 1
    w = np.clip(s / max(s[k_lp], 1e-9), 0, 1)
    t = np.gradient(E, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.c_[t[:, 1], -t[:, 0]]
    if np.mean(np.sum((P.mean(0) - E) * nrm, 1)) > 0:  # outward: away from the facing's body
        nrm = -nrm
    L0 = pattern.length(E)
    P[idx] = E + nrm * (tu * w)[:, None]
    fp["P"] = P
    if lp is not None:
        fp["marks"]["lapelPoint"] = P[idx][k_lp]
    grow = pattern.length(P[idx]) / L0 - 1
    for sm in D["seams"]:
        if isinstance(sm[0], str) and sm[0].startswith(f"{facing}:"):
            import json as _js
            key = _js.dumps(sm)
            nt = D["notes"].setdefault(key, {})
            nt["ease"] = [-0.004, max(0.004, grow + 0.004)]
            nt["why"] = (nt.get("why", "") + f"; turn allowance {tu * 1000:.1f} mm past the roll line ({src(27)})").strip("; ")
    D["log"].append(f"lapel turn ({src(27)}): {facing}'s lapel edge let out {tu * 1000:.1f} mm from the break to the lapel "
                    f"point and gorge (edge {L0 * 1000:.0f} -> {pattern.length(P[idx]) * 1000:.0f} mm, eased)")


# R25 (fit round 13): the front's cutaway hem, Jaeger's construction (frontCutawayAngle 2.5 deg, frontCutawayStart 30 %,
# frontCutawayEnd 40 %, hemRadius 100 %, buttonLength 30 %; @freesewing/jaeger front.mjs "Round the hem"): from the lower
# button the front edge is cut away 2.5 deg toward the side; it turns into the hem on a curve that starts 30 % of the way
# from that button to the hem and ends on the hem 40 % of the hem's width (CF -> the side panel's back seam) out from CF.
# A sack / square-cornered design leaves it out (op not in the list).
CUTAWAY = {"angle_deg": 2.5, "start": 0.30, "end": 0.40, "radius": 1.0, "button_frac": 0.30, "top_below_break": 0.015}


def _cubic(p0, c1, c2, p1, n):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * p1


def cutaway_geometry(K, up, side, y_button, hem_width, cf_x, **c):
    """R25's points for a front whose edge corner (the front edge meets the hem) is K, `up` the unit vector up the front
    edge, `side` the unit vector along the hem toward the side seam, the lower button at height y_button, the hem width
    hem_width (m, CF -> the side panel's back seam) and CF at x cf_x: {"C" lower button on the edge, "S" the curve's
    start (rotated `angle_deg` toward the side), "V" where the cut line meets the hem line, "E" the curve's end}."""
    c = {**CUTAWAY, **c}
    K, up, side = (np.asarray(v, float) for v in (K, up, side))
    C = K + up * ((y_button - K[1]) / up[1])
    a = math.radians(c["angle_deg"])
    d = (K - C) * c["start"]
    S = C + d * math.cos(a) + side * np.linalg.norm(d) * math.sin(a)
    u = (S - C) / np.linalg.norm(S - C)
    # V: the cut line C + u s meets the hem line K + side t
    A_ = np.c_[u, -side]
    s_, _t = np.linalg.solve(A_, K - C)
    V = C + u * s_
    E = K + side * (abs(cf_x - K[0]) / abs(side[0]) + c["end"] * hem_width)
    return {"C": C, "S": S, "V": V, "E": E}


def op_front_cutaway(D: dict, piece: str = "front", corner: str = "stand.b", button_frac: float | None = None,
                     **o) -> None:
    """R25: the front edge cut away from the lower button and rounded into the hem (CUTAWAY; Jaeger's construction).
    The lower button's height is R13's (the top one 15 mm under the break, the second `button_frac` of break -> the
    corner below it), recorded as meta "front_low" so op_buttons spaces them from the same corner. The curve's end is
    kept 10 mm short of the first dart / seam point on the hem."""
    from .pattern_tailor import op_round_corner
    c = {**CUTAWAY, **{k: o[k] for k in CUTAWAY if k in o}}
    if button_frac is not None:
        c["button_frac"] = float(button_frac)
    pc = D["pieces"][piece]
    if corner not in pc["names"]:
        raise DraftError(f"front_cutaway: {piece} has no point {corner!r}")
    P = np.asarray(pc["P"], float)
    n, i = len(P), pc["names"][corner]
    K = P[i].copy()
    nb = [P[(i - 1) % n], P[(i + 1) % n]]
    vert = [abs((q - K)[1]) / (np.linalg.norm(q - K) + 1e-12) for q in nb]
    ie = int(np.argmax(vert))  # the neighbour up the front edge (0: before the corner, 1: after)
    up = (nb[ie] - K) / np.linalg.norm(nb[ie] - K)
    side = (nb[1 - ie] - K) / np.linalg.norm(nb[1 - ie] - K)
    yb = float(D["meta"].get("break", [0, K[1] + 0.3])[1])
    y_btn = yb - c["top_below_break"] - c["button_frac"] * (yb - K[1])
    cf_x = 0.0
    # the hem's width CF -> the side panel's back seam (Jaeger's hemDropEnd): every torso piece's hem row but the back
    hem_x = []
    for nm_, q in D["pieces"].items():
        if nm_.split(".")[0] not in (piece.split(".")[0], "side", "side_front"):
            continue
        Q = np.asarray(q["P"], float)
        if abs(Q[:, 1].min() - K[1]) < 0.03:
            hem_x.append(Q[Q[:, 1] < Q[:, 1].min() + 0.015][:, 0])
    xs = np.concatenate(hem_x) if hem_x else np.array([K[0]])
    hem_w = float(np.max(np.abs(xs - cf_x)))
    g = cutaway_geometry(K, up, side, y_btn, hem_w, cf_x, **c)
    # the end kept 10 mm short of the next named point along the hem (a dart leg, a seam end)
    j, acc, lim = i, 0.0, None
    for _ in range(n):
        k = (j + (1 if ie == 0 else -1)) % n
        acc += float(np.linalg.norm(P[k] - P[j]))
        if any(v == k and not nm.startswith(("cf", corner)) for nm, v in pc["names"].items()):  # (not CF's own mark)
            lim = acc - 0.010
            break
        j = k
    along_hem = float(np.linalg.norm(g["E"] - K))
    if lim is not None and along_hem > lim:
        along_hem = lim
        g["E"] = K + side * lim
    along_edge = float(np.linalg.norm(g["C"] - K))
    C_, S_, V_, E_ = g["C"], g["S"], g["V"], g["E"]
    cpd = abs(C_[1] - S_[1]) / 3
    u = (S_ - V_) / np.linalg.norm(S_ - V_)

    def shape(A, Cc, B):  # A on the edge before the corner, B after: E -> S -> C or C -> S -> E
        lo = _cubic(E_, V_ + (E_ - V_) * (1 - c["radius"]), V_ + (S_ - V_) * (1 - c["radius"]), S_, 14)
        hi = _cubic(S_, S_ + u * cpd, C_ - up * cpd, C_, 10)  # (Jaeger: C's control straight down the edge)
        pts = np.r_[lo[1:], hi[1:-1]]
        return pts if np.linalg.norm(A - E_) < np.linalg.norm(A - C_) else pts[::-1]

    along = [along_hem, along_edge] if ie == 1 else [along_edge, along_hem]
    op_round_corner(D, piece, corner, along=along, shape=shape)
    # the cutaway's top on the front edge (where the edge leaves its line): a named point a worn-open hem pin can sit on
    # (fit round 14: the cfHem pin, sourced at the concept's corner top, sat on the cut curve near the hem, C62)
    pc["names"]["cutawayTop"] = pc["names"][f"{corner}.r1" if ie == 1 else f"{corner}.r0"]
    D["meta"]["front_low"] = float(K[1])
    D["meta"]["cutaway"] = {k: (v * 1000).round(1).tolist() for k, v in g.items()}
    D["log"].append(f"front cutaway ({src(25)}, Jaeger's construction): from the lower button {(yb - y_btn) * 1000:.0f} mm "
                    f"below the break, {c['angle_deg']} deg toward the side; the curve from {(K[1] - S_[1]) * -1000:.0f} mm "
                    f"above the corner to {along_hem * 1000:.0f} mm along the hem (hem width {hem_w * 1000:.0f} mm)")


pd.OPS.update({"jacket_neck": op_jacket_neck, "waist_suppression": op_waist_suppression,
               "collar_two_piece": op_collar_two_piece, "lapel_turn": op_lapel_turn, "front_cutaway": op_front_cutaway})


# ---------------------------------------------------------------- a design's op list, rewritten by the rules
def jacket_ops(ops: list, tape: dict, button_mm: float = 20.0, pockets: str = "flap", break_y: float | None = None) -> list:
    """The jacket design's ops with the tailor's rules applied (each changed op carries its "source")."""
    R = rules(tape, button_mm)
    out = []
    for op in ops:
        op = dict(op)
        k = op["op"]
        if k == "neckline":
            out.append({"op": "jacket_neck", "source": src(3, 4)})
            continue
        if k == "take_in":
            continue  # (replaced by waist_suppression)
        if k == "round_corner" and str(op.get("piece", "")).startswith("front") and op.get("corner") == "stand.b":
            # the rounded front hem drafted by R25 (cut away from the lower button), not a free corner radius
            out.append({"op": "front_cutaway", "piece": op["piece"], "corner": "stand.b", "source": src(25, 13)})
            continue
        if k == "contour" and op.get("edge") == "centre_back":
            op["at"] = [[lv, (0.0 if lv == "waist" else v)] for lv, v in op["at"]]  # the waist share: R8
        if k == "lapel":
            op["stand"] = R["overlap"]["value"]
            op["source"] = (op.get("source", "") + f"; stand (overlap) = the button's diameter {button_mm:.0f} mm: "
                            + src(12)).strip("; ")
        if k == "buttons" and op.get("spacing") is None and op.get("spacing_frac") is None:
            op["spacing_frac"] = 0.30  # R13 (fit round 9: the op's fixed 90 mm default had replaced the rule)
            op["source"] = (op.get("source", "") + "; second button 30 % of break -> hem below the first: "
                            + src(13)).strip("; ")
        if k == "collar":
            out.append({"op": "collar_two_piece", "point": op.get("point", 0.0), "source": src(16, 17, 18)})
            continue
        out.append(op)
        if k == "facing" and str(op.get("piece", "")).startswith("front"):
            out.append({"op": "lapel_turn", "piece": op["piece"], "facing": op.get("name"), "source": src(27)})
    # waist suppression after the panel seams exist (after the last style line / join / contour on them)
    last = max(i for i, o_ in enumerate(out) if o_["op"] in ("style_line", "join", "contour"))
    out.insert(last + 1, {"op": "waist_suppression", "source": src(8, 10)})
    if pockets in ("flap", "flap+chest"):
        i = next(i for i, o_ in enumerate(out) if o_["op"] == "buttons")
        out.insert(i + 1, {"op": "jacket_pockets", "chest": pockets == "flap+chest", "source": src(21, 22)})
    return out


def op_jacket_pockets(D: dict, chest: bool = False, **o) -> None:
    """R21 / R22: a flap pocket on each front just below the waist (width 0.68 of the front's hip width, flap ~1/3 of
    that deep, kept inside the front's side seam), and optionally a chest welt at the armhole-pitch level."""
    from .pattern_tailor import op_pocket
    m = D["meta"]["measurements"]
    R = rules(m)
    pf = D["pieces"]["front"]
    P = np.asarray(pf["P"], float)
    hy, wy = float(D["meta"]["hips_y"]), float(D["meta"]["waist_y"])
    xs = sorted(P[i][0] + (P[(i + 1) % len(P)][0] - P[i][0]) * (hy - P[i][1]) / (P[(i + 1) % len(P)][1] - P[i][1])
                for i in range(len(P)) if (P[i][1] - hy) * (P[(i + 1) % len(P)][1] - hy) < 0)
    side = max(xs, key=abs)
    sg = 1.0 if side > 0 else -1.0
    W = abs(side)
    w = R["pocket_width_frac"]["value"] * W
    xc = min(0.75 * W, W - w / 2 - 0.012)
    top = wy - R["pocket_below_waist"]["value"]
    op_pocket(D, "front", type="flap", at=[sg * xc, top], width=w, height=R["flap_depth_frac"]["value"] * w, name="flap")
    if chest:
        cy = float(D["meta"]["chest_y"]) + 0.02
        wc = R["chest_pocket_width_frac"]["value"] * W
        op_pocket(D, "front", type="welt", at=[sg * 0.55 * W, cy], width=wc,
                  height=min(R["chest_welt_frac"]["value"] * wc, 0.02), name="chest_welt")
    D["log"].append(f"jacket pockets ({src(21, 22)}): flap {w * 1000:.0f} mm wide, {R['flap_depth_frac']['value'] * w * 1000:.0f} "
                    f"deep, {(wy - top) * 1000:.0f} mm below the waist" + (", chest welt" if chest else ""))


pd.OPS["jacket_pockets"] = op_jacket_pockets


# ---------------------------------------------------------------- gate rows (T1..T7)
def _half(Bp: dict, base: str):
    pcs = Bp["pieces"]
    return pcs.get(base) or pcs.get(base + ".L")


def sagitta_ratio(E: np.ndarray) -> float:
    """How far a line bows off its chord, over the chord's length: a straight band ~0, the neckline ~0.2-0.3."""
    E = np.asarray(E, float)
    c = E[-1] - E[0]
    Lc = float(np.linalg.norm(c))
    nrm = np.array([-c[1], c[0]]) / max(Lc, 1e-12)
    return float(np.abs((E - E[0]) @ nrm).max() / max(Lc, 1e-12))


def _neck_edge(pc: dict):
    """A collar's whole neck edge, CF to CF across the CB fold when unfolded (a half shows little of a crescent)."""
    nm = pc["names"]
    if "cb" not in nm or "cf" not in nm:
        return None

    def half(a_, b_):
        via = ("shoulderNotch" + (".m" if a_.endswith(".m") else "")) if "shoulderNotch" in nm else None
        return np.asarray(pc["P"], float)[pattern.arc_indices(pc, f"{a_}>{via}>{b_}" if via else f"{a_}>{b_}")]
    E = half("cb", "cf")
    if "cf.m" in nm:
        E = np.r_[half("cf.m", "cb")[:-1], E]
    return E


def front_edge_profile(pc: dict, step: float = 0.002) -> np.ndarray:
    """The flat front's front edge from the break down to the hem: rows (y, x) in m, x the outline crossing furthest out
    past CF on each row (the edge's side is the break's)."""
    P = np.asarray(pc["P"], float)
    xb, yb = _pt(pc, "break")
    s = 1.0 if xb >= 0 else -1.0
    Q = np.r_[P, P[:1]]
    out = []
    for y in np.arange(yb - step, P[:, 1].min(), -step):
        a, b = Q[:-1], Q[1:]
        m = (a[:, 1] - y) * (b[:, 1] - y) < 0
        if not m.any():
            continue
        t = (y - a[m, 1]) / (b[m, 1] - a[m, 1])
        xs = a[m, 0] + t * (b[m, 0] - a[m, 0])
        out.append((y, xs[np.argmax(s * xs)]))
    return np.asarray(out)


def cutaway_rows(pc: dict) -> list:
    """R25 gate rows read on the FLAT front's outline (a cutaway front): where the edge leaves its straight line (the
    lower button, +-15 mm), the cut's angle over its first 30 % to the hem (2.5 +- 1 deg), and how far the hem corner
    curves back from the edge line at the hem (>= 25 % of the front's hem width CF -> its side seam: a rounded cutaway,
    not a square corner rounded by a few cm)."""
    rows = []
    E = front_edge_profile(pc)
    if len(E) < 10 or "button2" not in (pc.get("marks") or {}):
        return [{"id": "front_cutaway", "stage": 2, "status": "UNMEASURED", "rule": src(25),
                 "why": "no front edge / lower button mark to read"}]
    xb = float(_pt(pc, "break")[0])
    s = 1.0 if xb >= 0 else -1.0
    back = s * (xb - E[:, 1])  # how far the edge has moved back toward the side (m)
    k0 = int(np.argmax(back > 0.001)) if (back > 0.001).any() else len(E) - 1
    yb2 = float(np.asarray(pc["marks"]["button2"])[1])
    y_lo = float(np.asarray(pc["P"])[:, 1].min())
    y30 = yb2 - 0.3 * (yb2 - y_lo)
    b30 = float(np.interp(-y30, -E[:, 0], back))
    # the cut's start: its line (from where it is 1 mm back to its 30 % point) run up to the straight edge
    y1, b1 = float(E[k0, 0]), float(back[k0])
    y_st = y1 + b1 * (y1 - y30) / (b30 - b1) if b30 - b1 > 1e-4 and y1 > y30 else y1
    st = (y_st - yb2) * 1000
    rows.append({"id": "front_cutaway_start", "stage": 2, "rule": src(25, 13), "ours": round(st, 1), "ref": -15.0, "tol": 10.0,
                 "units": "mm above the lower button", "status": "PASS" if abs(st + 15.0) <= 10.0 else "FAIL",
                 "measure": "pattern_jacket.cutaway_rows",
                 "why": "the cut line (1 mm back -> its 30 % point) meets the straight front edge at the lower button; "
                        "Jaeger leaves the button tangent (its C control straight down): this measure reads -16 mm on "
                        "Jaeger's own front at three sizes (test_cutaway_reads_the_same_on_jaegers_front)"})
    ang = math.degrees(math.atan2(b30, yb2 - y30))
    rows.append({"id": "front_cutaway_angle", "stage": 2, "rule": src(25), "ours": round(ang, 2), "ref": 2.5, "tol": 1.0,
                 "units": "deg", "status": "PASS" if abs(ang - 2.5) <= 1.0 else "FAIL", "measure": "pattern_jacket.cutaway_rows",
                 "why": "the edge's lean toward the side from the lower button over 30 % of the way to the hem"})
    P = np.asarray(pc["P"], float)
    hem = P[P[:, 1] < y_lo + 0.0005]
    hem_w = float(np.max(s * (xb - hem[:, 0]))) if len(hem) else 0.0  # (edge line -> the hem's far end)
    reach = float(np.min(s * (xb - hem[:, 0]))) if len(hem) else 0.0  # where the straight hem starts
    rows.append({"id": "front_hem_round", "stage": 2, "rule": src(25), "ours": round(reach * 1000, 1),
                 "ref": f">= {0.25 * hem_w * 1000:.0f}", "tol": 0, "units": "mm back from the edge line at the hem",
                 "status": "PASS" if reach >= 0.25 * hem_w else "FAIL", "measure": "pattern_jacket.cutaway_rows",
                 "why": f"the hem corner's curve ends {reach * 1000:.0f} mm in from the front edge line (front hem "
                        f"{hem_w * 1000:.0f} mm): a cutaway, not a square corner"})
    return rows


def tailor_rows(Bp: dict, tape: dict, g: dict | None = None, button_mm: float = 20.0) -> list:
    """The tailor-rule rows for a jacket's flat pattern (each with its rule number and tolerance)."""
    g = g or {}
    R = rules(tape, button_mm)
    rows = []

    def row(id_, rule, ours, ref, tol, ok=None, units="mm", why=""):
        if ours is None:
            rows.append({"id": id_, "stage": 2, "status": "UNMEASURED", "rule": rule, "why": why})
            return
        good = (abs(ours - ref) <= tol) if ok is None else ok
        rows.append({"id": id_, "stage": 2, "status": "PASS" if good else "FAIL", "rule": rule, "ours": round(ours, 2),
                     "ref": round(ref, 2) if isinstance(ref, (int, float)) else ref, "tol": tol, "units": units,
                     "measure": "pattern_jacket.tailor_rows", **({"why": why} if why else {})})
    bk = _half(Bp, "back")
    if bk is not None and all(k in bk["names"] for k in ("hps", "cbNeck")):
        h, c = _pt(bk, "hps"), _pt(bk, "cbNeck")
        row("back_neck_width", src(3), abs(h[0] - c[0]) * 1000, R["back_neck_width"]["value"] * 1000, 6.0)
        row("back_neck_rise", src(4), (h[1] - c[1]) * 1000, R["back_neck_rise"]["value"] * 1000, 6.0)
    else:
        row("back_neck_width", src(3), None, None, 0, why="no back piece with hps / cbNeck")
    # waist suppression: the chest -> waist reduction over the chest, and a front dart
    meta = (Bp.get("draft") or {}).get("meta") or {}
    if "waist_y" in meta and "chest_y" in meta:
        ch, wa = torso_span(Bp, meta["chest_y"], half=False), torso_span(Bp, meta["waist_y"], half=False)
        sup = (ch - wa) / max(ch, 1e-9) * 100
        sil = next((op_.get("silhouette", "suit") for op_ in ((g.get("design") or {}).get("ops") or [])
                    if op_.get("op") == "waist_suppression"), "suit")
        if sil == "plumb":  # (fit round 24: nothing taken in; the waist >= the chest less the drape, hips >= waist)
            hy_ = float(meta.get("hips_y", meta["waist_y"]))
            # the narrowest row from the chest line to the hip line (the pinch is not always at the waist line)
            ys_ = np.linspace(float(meta["chest_y"]), hy_, 25)
            gs_ = [torso_span(Bp, y_, half=False) for y_ in ys_]
            wmin, hp_ = min(gs_), gs_[-1]
            tgt = plumb_target(tape)
            if tgt is not None:  # (C94: the tube's girth under the chest, floor AND ceiling; less the lap)
                ys2 = np.linspace(float(meta["chest_y"]) - PLUMB_RAMP, hy_, 20)
                es = [torso_span(Bp, y_, half=False) - _lap(Bp, y_) for y_ in ys2]
                lo, hi = min(es), max(es)
                row("waist_plumb", src(8), lo * 1000, f"{(tgt - PLUMB_FLOOR_TOL) * 1000:.0f} .. "
                    f"{(tgt + PLUMB_CEIL) * 1000:.0f}", 0,
                    ok=lo >= tgt - PLUMB_FLOOR_TOL and hi <= tgt + PLUMB_CEIL and hp_ >= wmin - 0.005,
                    why=f"silhouette plumb (Joe 2026-10-20 'fall straight down') sized to the tube (C94): girth less "
                        f"the lap from {PLUMB_RAMP * 1000:.0f} mm under the chest to the hips {lo * 1000:.0f} .. "
                        f"{hi * 1000:.0f} vs plumbGirth + allowances {tgt * 1000:.0f} (floor -{PLUMB_FLOOR_TOL * 1000:.0f}: "
                        f"a pinch; ceiling +{PLUMB_CEIL * 1000:.0f}: the chest's ease carried down stands off)")
            else:
                row("waist_plumb", src(8), wmin * 1000, f">= {ch * (1 - PLUMB_TOL) * 1000:.0f}", 0,
                    ok=wmin >= ch * (1 - PLUMB_TOL) and hp_ >= wmin - 0.005,
                    why=f"silhouette plumb (Joe 2026-10-20 'fall straight down'): the narrowest flat girth chest -> hips "
                        f"{wmin * 1000:.0f} ({(ys_[int(np.argmin(gs_))] - ys_[0]) * 1000:+.0f} mm from the chest line) >= chest "
                        f"{ch * 1000:.0f} x {1 - PLUMB_TOL:.2f}, hips {hp_ * 1000:.0f} >= waist; a pinch here is the block's "
                        f"fitted side seam or a CB contour")
        if sil == "straight":  # (CB + dart only, at their R8 shares of the reduction, no gain: ~1-3 % of the chest)
            row("waist_suppression", src(8), sup, "<= 9 % (straight)", 0, ok=sup <= 9.0, units="% of chest",
                why=f"chest {ch * 1000:.0f} / waist {wa * 1000:.0f} mm on the flat pattern; silhouette straight: CB "
                    f"and dart only (the sack's straight sides)")
        elif sil == "plumb":
            # (C94: a tube-sized plumb cut takes the chest's surplus over the tube in under the chest, then hangs
            # straight: the allowed reduction is that surplus + PLUMB_TOL)
            tgt_ = plumb_target(tape)
            cap = PLUMB_TOL if tgt_ is None else max(PLUMB_TOL, (ch - _lap(Bp, meta["chest_y"]) - tgt_) / ch + PLUMB_TOL)
            row("waist_suppression", src(8), sup, f"<= {cap * 100:.0f} % (plumb)", 0, ok=sup <= cap * 100,
                units="% of chest", why=f"chest {ch * 1000:.0f} / waist {wa * 1000:.0f} mm on the flat pattern; "
                                        f"silhouette plumb: only the chest's surplus over the tube taken in (C94)")
        else:
            row("waist_suppression", src(8), sup, "11-20 %", 0, ok=11.0 <= sup <= 20.0, units="% of chest",
                why=f"chest {ch * 1000:.0f} / waist {wa * 1000:.0f} mm on the flat pattern (Jaeger reads 13-17 %)")
    if "hips_y" in meta:
        hp = torso_span(Bp, meta["hips_y"], half=False) * 1000
        frh = _half(Bp, "front")
        ov = abs(_pt(frh, "break")[0]) * 2000 if frh is not None and "break" in frh["names"] else 0.0
        need = float(tape["hips"]) * 1.04
        row("hips_clearance", src(1, 8), hp - ov, f">= {need:.0f}", 0, ok=hp - ov >= need,
            why="flat hip girth CF to CF (overlaps out) >= hips + 4 %: the waist shaping must not pull the hips in")
    fr = _half(Bp, "front")
    if fr is not None:
        has = bool(fr.get("fisheyes")) or any(k.startswith("frontDart") or k.startswith("waistDart") for k in fr["names"])
        plumb = any(op_.get("op") == "waist_suppression" and op_.get("silhouette") == "plumb"
                    for op_ in ((g.get("design") or {}).get("ops") or []))
        if plumb:  # (a straight-cut front has no fish-eye: a dart there would pinch the waist)
            row("front_dart", src(10), 1.0 if has else 0.0, 0.0, 0, ok=not has, units="present",
                why="silhouette plumb: no waist dart (Joe 2026-10-20)")
        else:
            row("front_dart", src(10), 1.0 if has else 0.0, 1.0, 0, ok=has, units="present")
        if "break" in fr["names"]:
            ov = abs(_pt(fr, "break")[0]) * 1000
            row("front_overlap", src(12), ov, button_mm, 4.0, why="front edge past CF at the break vs the button diameter")
        cut = any(op_.get("op") == "front_cutaway" for op_ in ((g.get("design") or {}).get("ops") or []))
        if cut:
            rows.extend(cutaway_rows(fr))
    st = next((p for n, p in Bp["pieces"].items() if p.get("role") == "collar_stand" and n.split(".")[0] != "shirt"), None)
    col = next((p for p in Bp["pieces"].values() if p.get("role") == "collar_fall"), None)
    neck = float(tape["neck"])
    if st is not None and "cb" in st["names"] and "cf" in st["names"]:
        sr = sagitta_ratio(_neck_edge(st))
        row("collar_neck_edge_straight", src(17), sr, "<= 0.08", 0, ok=sr <= 0.08, units="sagitta / chord",
            why="a band-shaped stand (a flat collar's neck edge follows the neckline: ~0.2-0.3)")
        hs = float(np.linalg.norm(_pt(st, "cbTop") - _pt(st, "cb"))) * 1000
        row("collar_stand_cb", src(16), hs, R["collar_stand_cb"]["value"] * 1000, 0.012 * neck)
        if "cfTop" in st["names"] and any("lapelPoint" in p["names"] for p in Bp["pieces"].values()):
            he = float(np.linalg.norm(_pt(st, "cfTop") - _pt(st, "cf"))) * 1000
            row("collar_stand_end", src(14, 28), he, STAND_RUN_OFF["end"] * 1000, 3.0,
                why="the stand's height at the collar's end: it runs off where the lapel's roll line crosses the gorge, "
                    "so the collar's end lies flat on the lapel (a stand standing to the notch carries the end as a tab)")
        if col is not None and "cbOuter" in col["names"]:
            hf = float(np.linalg.norm(_pt(col, "cbOuter") - _pt(col, "cbLow"))) * 1000
            fab = g.get("fabric") if isinstance(g.get("fabric"), str) else None
            ts = turn_stack(fab)
            row("collar_fall_cb", src(16, 18), hf, R["collar_fall_cb"]["value"] * 1000 + ts["depth_mm"], 0.02 * neck,
                why=f"fall piece = the rule's + the turn of cloth {ts['depth_mm']} mm ({ts['source']})")
            # R18: the fall's outer edge (half) at least the path it lies on: the neckline it is sewn round, offset to
            # where its edge lands, + pi x the ring it stands out by (turn_stack); at most 15 mm over (a frilled edge)
            sn = next((s for s in Bp.get("seams") or [] if isinstance(s[0], str) and s[0].startswith("stand:")
                       and not s[0].endswith(".m") and isinstance(s[1], list)), None)
            if sn is not None and "endOuter" in col["names"]:
                hs_ = float(np.linalg.norm(_pt(st, "cbTop") - _pt(st, "cb")))
                fat = FALL_FOLD["at"]
                drop = (hf / 1000 - ts["depth_mm"] / 1000 - fat) - (hs_ + fat)
                # the end's drop from the pieces' end heights (the fall's end carries its CB's roll factor)
                he_s = float(np.linalg.norm(_pt(st, "cfTop") - _pt(st, "cf")))
                he_f = float(np.linalg.norm(_pt(col, "endOuter") - _pt(col, "endLow"))) * (1 - ts["depth_mm"] / hf)
                drop_e = (he_f - fat) - (he_s + fat)
                need_m, _np = fall_need(Bp["pieces"], sn[1], drop, drop_e, ts)
                need = need_m * 1000
                out = pattern.length(np.asarray(col["P"], float)[pattern.arc_indices(col, "endOuter>cbOuter")]) * 1000
                row("collar_fall_outer", src(18), out, need, 15.0, ok=need - 3.0 <= out <= need + 15.0,
                    why=f"half outer edge vs the neckline offset by the edge's drop ({drop * 1000:.1f} mm at CB -> "
                        f"{drop_e * 1000:.1f} at the end, u^2) into the body pieces + pi x {ts['ring_outer_mm']} mm (its "
                        f"stand-off on the body: fall {ts['t_fall_mm']} / 2 + cloth {ts['cloth_mm']} / 2); tol -3 / +15 mm")
            else:
                row("collar_fall_outer", src(18), None, None, 0, why="no stand neck seam / collar endOuter to read")
    elif col is not None:
        E = _neck_edge(col)
        sr = sagitta_ratio(E) if E is not None else None
        row("collar_neck_edge_straight", src(17), sr, "<= 0.08", 0, ok=sr is not None and sr <= 0.08,
            units="sagitta / chord", why="one-piece collar: its neck edge read as the stand's")
        row("collar_stand_cb", src(16), None, None, 0, why="no separate stand piece (a one-piece collar)")
    want = str(((g.get("design") or {}).get("details") or {}).get("pockets", "")).lower()
    asked = any(w in want for w in ("flap", "welt", "patch", "jetted")) or bool(g.get("pockets"))
    have = [n for n, p in Bp["pieces"].items() if p.get("role") == "pocket"]
    if asked:
        row("pockets", src(21), float(len(have)), ">= 2", 0, ok=len(have) >= 2, units="pocket pieces",
            why=f"design asks {want or g.get('pockets')}")
    return rows
