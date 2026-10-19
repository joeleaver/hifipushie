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
COLLAR = {"total": 0.18, "stand": 0.30, "spread_deg": 13.0, "roll": 0.05, "rise": 0.035}  # R16-R18 (x neck girth)


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
    stand = COLLAR["total"] * COLLAR["stand"] * neck
    put("collar_stand_cb", stand / 1000, 16)
    put("collar_fall_cb", COLLAR["total"] * (1 - COLLAR["stand"]) * neck / 1000, 16)
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
    """Total width of a closed outline inside the line y = const (darts cut out of the outline are not counted)."""
    xs = []
    n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        if (a[1] - y) * (b[1] - y) < 0:
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


def op_waist_suppression(D: dict, waist_ease: float | None = None, share: dict | None = None, dart_x: float = 0.55,
                         **o) -> None:
    """R8 / R10 (see _suppress): the shares are scaled so the waist lands on its target (the seam take-ins fade above
    and below the waist, so a first pass on a copy measures what each mm of take-in really removes)."""
    import copy as _copy
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
                  rise: float, spread_deg: float, roll: float, point: float = 0.0, n: int = 41) -> dict:
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
                        ease: float = 0.0, stand: str = "stand", name: str = "collar", **o) -> None:
    """A tailored jacket's collar in two pieces (R16-R18, R26): a near-straight STAND (the neckline's length, back neck
    + the gorge up to the notch) and a sprung FALL sewn to the stand's top edge (the roll line). Defaults from the
    neck girth (rules). `ease` (fraction, R26): the stand's neck edge cut that much shorter than the neckline and
    eased on (0: sewn 1:1). Point names: stand cb, shoulderNotch, cf, cfTop, cbTop; fall cbLow, endLow, endOuter,
    cbOuter. Both cut on the fold at CB."""
    nb, nf = D["edges"].get("neck_back"), D["edges"].get("neck_front")
    if not nb or not nf:
        raise DraftError("collar_two_piece: no neckline edges (neck_back / neck_front)")
    m = D["meta"]["measurements"]
    R = rules(m)
    stand_cb = R["collar_stand_cb"]["value"] if stand_cb is None else float(stand_cb)
    fall_cb = R["collar_fall_cb"]["value"] if fall_cb is None else float(fall_cb)
    stand_front = 0.6 * stand_cb if stand_front is None else float(stand_front)
    fall_front = 0.8 * fall_cb if fall_front is None else float(fall_front)
    rise = R["collar_rise"]["value"] if rise is None else float(rise)
    spread_deg = COLLAR["spread_deg"] if spread_deg is None else float(spread_deg)
    roll = COLLAR["roll"] if roll is None else float(roll)
    lb, lf = edge_length(D, nb), edge_length(D, nf)
    c = collar_shapes(lb * (1 - ease), lf * (1 - ease), stand_cb, fall_cb, stand_front, fall_front, rise, spread_deg,
                      roll, point)
    E, T, F, O, ks = c["stand_neck"], c["stand_top"], c["fall_low"], c["fall_out"], c["k_shoulder"]
    n = len(E)
    pts = [("cb", E[0])] + [("shoulderNotch" if k == ks else None, E[k]) for k in range(1, n - 1)] + [("cf", E[-1])]
    pts += [("cfTop", T[-1])] + [(None, q) for q in T[-2:0:-1]] + [("cbTop", T[0])]
    wrap = {"to": "seam", "worn": True, "out": 0.004}
    ps = pb.make_piece(stand, pts, "collar_stand", dict(wrap), "fold")
    pts = [("cbLow", F[0])] + [(None, q) for q in F[1:-1]] + [("endLow", F[-1])]
    pts += [("endOuter", O[-1])] + [(None, q) for q in O[-2:0:-1]] + [("cbOuter", O[0])]
    pf = pb.make_piece(name, pts, "collar_fall", dict(wrap, turn={"at": 0.0, "deg": 172, "gap": 0.004}), "fold")
    for pc in (ps, pf):
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
    D["interfaced"] += [stand, name]
    D["edges"][f"{stand}_neck"] = [f"{stand}:cb>shoulderNotch>cf"]
    D["edges"][f"{name}_outer"] = [f"{name}:endOuter>cbOuter"]
    D["meta"]["collar_two_piece"] = {"stand_cb": stand_cb, "fall_cb": fall_cb, "rise": rise, "spread_deg": spread_deg}
    D["log"].append(f"collar two-piece ({src(16, 17, 18)}): stand {stand_cb * 1000:.0f} -> {stand_front * 1000:.0f} mm, "
                    f"neck edge {pattern.length(E) * 1000:.0f} (neckline {(lb + lf) * 1000:.0f}) rising "
                    f"{rise * 1000:.0f} at the front; fall {fall_cb * 1000:.0f} mm, spread {spread_deg:.0f} deg: outer "
                    f"{pattern.length(O) * 1000:.0f} for a roll line of {pattern.length(F) * 1000:.0f} (half)")


pd.OPS.update({"jacket_neck": op_jacket_neck, "waist_suppression": op_waist_suppression,
               "collar_two_piece": op_collar_two_piece})


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
        if k == "contour" and op.get("edge") == "centre_back":
            op["at"] = [[lv, (0.0 if lv == "waist" else v)] for lv, v in op["at"]]  # the waist share: R8
        if k == "lapel":
            op["stand"] = R["overlap"]["value"]
            op["source"] = (op.get("source", "") + f"; stand (overlap) = the button's diameter {button_mm:.0f} mm: "
                            + src(12)).strip("; ")
        if k == "collar":
            out.append({"op": "collar_two_piece", "point": op.get("point", 0.0), "source": src(16, 17, 18)})
            continue
        out.append(op)
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
        row("front_dart", src(10), 1.0 if has else 0.0, 1.0, 0, ok=has, units="present")
        if "break" in fr["names"]:
            ov = abs(_pt(fr, "break")[0]) * 1000
            row("front_overlap", src(12), ov, button_mm, 4.0, why="front edge past CF at the break vs the button diameter")
    st = next((p for n, p in Bp["pieces"].items() if p.get("role") == "collar_stand" and n.split(".")[0] != "shirt"), None)
    col = next((p for p in Bp["pieces"].values() if p.get("role") == "collar_fall"), None)
    neck = float(tape["neck"])
    if st is not None and "cb" in st["names"] and "cf" in st["names"]:
        sr = sagitta_ratio(_neck_edge(st))
        row("collar_neck_edge_straight", src(17), sr, "<= 0.08", 0, ok=sr <= 0.08, units="sagitta / chord",
            why="a band-shaped stand (a flat collar's neck edge follows the neckline: ~0.2-0.3)")
        hs = float(np.linalg.norm(_pt(st, "cbTop") - _pt(st, "cb"))) * 1000
        row("collar_stand_cb", src(16), hs, R["collar_stand_cb"]["value"] * 1000, 0.012 * neck)
        if col is not None and "cbOuter" in col["names"]:
            hf = float(np.linalg.norm(_pt(col, "cbOuter") - _pt(col, "cbLow"))) * 1000
            row("collar_fall_cb", src(16, 18), hf, R["collar_fall_cb"]["value"] * 1000 * (1 + COLLAR["roll"]), 0.02 * neck)
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
