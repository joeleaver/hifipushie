"""The toile's style parts (toile.py builds the field): the neckline, the sleeve hem, the FRONT OPENING with its lap, and
the TURNED FLAPS (lapels) about their roll lines, all from step 2's traces mapped onto the body (structure_outline
placement) and the declaration; no garment's name.

OPENING (declared opening: {lap_mm, edge, buttons}): the garment is built in its CLOSED state: the over front (the
body's left, +X) runs past centre front by the lap; the under front is its mirror, LAP_UNDER_M inside it. Below the
lowest button (step 2 row `buttons`) the edge follows the traced front edge below its corner (a cutaway); above the
break it is the roll line (with a lapel) or the lap line up to the neck.
LAPEL (declared lapel: {roll, top, width_mm}): the roll trace up to its first corner (gorge -> break) moved with the
closure (the break goes from the open picture's place to CF + lap; nothing moves at the gorge); the lapel's outer edge
the edge trace up to its first corner (notch -> break), widened square from the roll line to width_mm when declared;
its top the roll's top + the top trace up to its first corner (gorge, notch). The lapel = the toile under that outline,
lifted LAPEL_LIFT_M (the facing out, lying on the chest): its own part, mirrored for the right side."""
from __future__ import annotations

import numpy as np

from .toile_geom import clip, largest, weld

LAP_UNDER_M = 0.002   # the under front's lap lies this far inside the over front
LAPEL_LIFT_M = 0.004  # the turned lapel lies this far off the chest
MIR = np.array([-1.0, 1, 1])


def to_corner(tr: dict) -> np.ndarray:
    """A trace's points up to its first corner, inclusive (all of it without a corner)."""
    xz = np.asarray(tr["xz"], float)
    c = sorted(tr.get("corners") or [])
    return xz[: c[0] + 1] if c else xz


def past_corner(tr: dict) -> np.ndarray:
    xz = np.asarray(tr["xz"], float)
    c = sorted(tr.get("corners") or [])
    return xz[c[0]:] if c else xz


def _folded(P):
    return P * np.where(P[:, :1] < 0, MIR, 1)


def neck_and_wrists(t, V, F):
    neck = np.asarray(t.inp.tapes["neck"], float)
    cn = t.cn
    an = np.arctan2(neck[:, 1] - cn[1], neck[:, 0] - cn[0])
    o = np.argsort(an)
    an_s, zn_s = an[o], neck[o, 2]
    phi_neck = lambda P: np.interp(np.arctan2(P[:, 1] - cn[1], P[:, 0] - cn[0]), an_s, zn_s, period=2 * np.pi) - P[:, 2]
    V, F = largest(*clip(V, F, phi_neck(V)))
    if "sleeves" in t.parts:
        z_sl = float(t.inp.heights[t.d["sleeves"]["hem"]])
        k = int(np.argmin(np.abs(t.CAX[:, 2] - z_sl)))
        p, A = t.CAX[k], (t.CAX[-1] - t.CAX[-3]) / np.linalg.norm(t.CAX[-1] - t.CAX[-3])
        phi = lambda P: np.maximum(-((_folded(P) - p) @ A), np.linalg.norm(np.cross(_folded(P) - p, A), axis=1) - 0.12)
        t.info["sleeve"]["hem_z"] = round(z_sl, 3)
    else:  # (no sleeves: the armhole is cut on the cone)
        phi = lambda P: -t.cone.sdist(_folded(P))
    V, F = largest(*clip(V, F, phi(V)))
    t.phi_neck = phi_neck
    return V, F


def closure(t):
    """x_edge(z) (the over front's edge, metres) and what it was made from; None without an opening."""
    if "opening" not in t.parts:
        return None
    op, tr = t.d["opening"], t.inp.traces
    lap = float(op["lap_mm"]) / 1000
    edge = tr[op["edge"]]
    bt = t.inp.marks.get(op.get("buttons")) if op.get("buttons") else None
    t.info["opening"] = {"lap_mm": lap * 1000, "edge": op["edge"]}
    if "lapel" in t.parts:
        lp = t.d["lapel"]
        ROLL = to_corner(tr[lp["roll"]])
        ROLL = ROLL[np.argsort(-ROLL[:, 1])]  # gorge (top) -> break
        z_top, z_brk, x_brk = ROLL[0, 1], ROLL[-1, 1], ROLL[-1, 0]
        shift = lambda z: (-lap - x_brk) * np.clip((z_top - z) / (z_top - z_brk), 0, 1)
        RS = ROLL[np.argsort(ROLL[:, 1])]
        x_roll = lambda z: np.interp(z, RS[:, 1], RS[:, 0]) + shift(z)
        LE = to_corner(edge)
        LE = LE[np.argsort(LE[:, 1])]
        t.lapel_geom = dict(ROLL=ROLL, LE=LE, shift=shift, x_roll=x_roll, z_top=z_top, z_brk=z_brk)
        LOW = past_corner(edge)
    else:
        z_brk = np.inf
        x_roll = None
        LOW = np.asarray(edge["xz"], float)
    LOW = LOW[np.argsort(LOW[:, 1])]
    z_btm = float(np.min(bt[:, 1])) if bt is not None and len(bt) else min(z_brk, float(LOW[:, 1].max()))
    x0 = np.interp(z_btm, LOW[:, 1], LOW[:, 0])
    dx_cut = lambda z: np.where(z < z_btm, np.interp(z, LOW[:, 1], LOW[:, 0]) - x0, 0.0)
    t.info["opening"].update(lowest_button_z=round(z_btm, 3), break_z=None if not np.isfinite(z_brk) else round(float(z_brk), 3))
    if x_roll is None:
        return lambda z: -lap + dx_cut(z)
    return lambda z: np.where(z >= z_brk, x_roll(z), -lap + dx_cut(z))


def halves(t, V, F, x_edge):
    """The over (left) half to its edge in front and to centre back behind; the under (right) half its mirror, its lap
    LAP_UNDER_M inside; welded at centre back: one surface whose front overlaps."""
    phi = lambda P: np.where(P[:, 1] < t.yc, P[:, 0] - x_edge(P[:, 2]), P[:, 0])
    Vh, Fh = largest(*clip(V, F, phi(V)))
    Vr, Fr = Vh * MIR, Fh[:, ::-1].copy()
    lap = (Vr[:, 0] > 1e-6) & (Vr[:, 1] < t.yc)
    Vr[lap] -= LAP_UNDER_M * t.grad(Vr[lap])
    Vw, Fw = weld(np.r_[Vh, Vr], np.r_[Fh, Fr + len(Vh)])
    return Vw, Fw


def lapel(t, V, F):
    g, lp = t.lapel_geom, t.d["lapel"]
    x_roll, shift, z_brk, z_top, LE = g["x_roll"], g["shift"], g["z_brk"], g["z_top"], g["LE"]
    top = to_corner(t.inp.traces[lp["top"]])
    TOP = np.r_[g["ROLL"][:1], top]
    TOP[:, 0] += shift(TOP[:, 1])
    TOP = TOP[np.argsort(TOP[:, 0])]
    z_line = lambda x: np.interp(x, TOP[:, 0], TOP[:, 1])
    zz = np.linspace(z_brk, z_top, 40)
    rl = t.front_hit(x_roll(np.linspace(z_brk, z_top, 60)), np.linspace(z_brk, z_top, 60))

    def width(k):
        x_l = lambda z: x_roll(z) + (np.interp(z, LE[:, 1], LE[:, 0]) + shift(z) - x_roll(z)) * k
        le = t.front_hit(x_l(zz), zz)
        return x_l, max(np.min(np.linalg.norm(rl - p, axis=1)) for p in le)

    x_l, w0 = width(1.0)
    k = float(lp["width_mm"]) / 1000 / w0 if lp.get("width_mm") else 1.0
    x_l, w = width(k)
    Vl, Fl = V, F
    for ph in (lambda P: P[:, 0] - x_roll(P[:, 2]), lambda P: x_l(P[:, 2]) - P[:, 0],
               lambda P: z_line(P[:, 0]) - P[:, 2], lambda P: P[:, 2] - z_brk, lambda P: (t.yc - 0.03) - P[:, 1]):
        Vl, Fl = clip(Vl, Fl, ph(Vl))
    Vl, Fl = largest(Vl, Fl)
    Vl = Vl + LAPEL_LIFT_M * t.grad(Vl)
    t.info["lapel"] = {"width_traced_mm": round(w0 * 1000, 1), "width_mm": round(w * 1000, 1),
                       "roll_mm": round(float(np.linalg.norm(np.diff(rl, axis=0), axis=1).sum() * 1000), 1),
                       "break_z": round(float(z_brk), 4), "gorge_z": round(float(z_top), 4)}
    t.roll_line = rl
    return Vl, Fl


def cut(t, V, F) -> dict:
    """{part: (V, F)}: the toile (neck, sleeve hems, the opening) and its turned flaps."""
    V, F = neck_and_wrists(t, V, F)
    full = (V, F)
    x_edge = closure(t)
    out = {"toile": halves(t, V, F, x_edge) if x_edge is not None else full}
    t.x_edge = x_edge
    if "lapel" in t.parts:
        Vl, Fl = lapel(t, *full)
        out["lapel.L"] = (Vl, Fl)
        out["lapel.R"] = (Vl * MIR, Fl[:, ::-1].copy())
    return out
