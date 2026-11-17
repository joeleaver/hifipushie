"""The toile's style parts (toile.py builds the field): the neckline, the sleeve hem, the FRONT OPENING with its lap, and
the TURNED FLAPS (lapels) about their roll lines, all from step 2's traces mapped onto the body (structure_outline
placement) and the declaration; no garment's name.

OPENING (declared opening: {closure, edge, lap_mm, buttons}): the WEAR STATE the reference shows (R3f-5, C502) is
step 2's ties for the declared closure (t.inp.wear: none done up = "open", every one = "closed"; a closure with no wear
state is refused by name, never defaulted). The toile is CUT CLOSED whatever the wear (R3f-7, C504: a jacket worn open
is the same pattern as worn closed; the open toile cut at its traced edges lost each front's cloth to centre front and
the lap). Worn open, the OPEN state is built too for the look (cut(): t.worn): the fronts do not lap, each front's edge
runs where step 2's front-edge trace puts it (below the break the traced edge past its corner, from the break up the
roll trace as traced: nothing moved, the picture shows the open place), the lapel turned about it. The field (its ease
calibrated round the body, toile.py) is the same in both states.
CLOSED: the over front (the body's left, +X) runs past centre front by the lap; the under front is its mirror,
LAP_UNDER_M inside it. Below the
lowest button (step 2 row `buttons`) the edge follows the traced front edge below its corner (a cutaway); above the
break it is the roll line (with a lapel) or the lap line up to the neck; with a lapel, above the roll's top (the gorge
point) the FRONT NECKLINE (front_neck, R3f-4): straight in the front view up and in to the side neck point.
LAPEL (declared lapel: {roll, top, width_mm}): the roll trace up to its first corner (gorge -> break) moved with the
closure (the break goes from the open picture's place to CF + lap; nothing moves at the gorge); the lapel's outer edge
the edge trace up to its first corner (notch -> break), widened square from the roll line to width_mm when declared;
its top the roll's top + the top trace up to its first corner (gorge, notch). The lapel = the toile under that outline,
lifted LAPEL_LIFT_M (the facing out, lying on the chest): its own part, mirrored for the right side; with a collar part
the lapels and the collar are ONE flap about one roll line (toile_flap.py, R3f-9), the lapel's outline its lapel region."""
from __future__ import annotations

import numpy as np

from .toile_geom import clip, largest, weld

LAP_UNDER_M = 0.002   # the under front's lap lies this far inside the over front
LAPEL_LIFT_M = 0.004  # the turned lapel lies this far off the chest
BACK_NECK_DEPTH_M = 0.015  # a draft's back neck: centre back this far below the side neck point (block drafting)
MIR = np.array([-1.0, 1, 1])
WEARS = ("open", "closed")


class WearRefused(ValueError):
    """An opening whose wear state the record doesn't give (named)."""


def wear(t) -> str:
    """The opening's wear state ("open" | "closed") from t.inp.wear (step 2's ties, toile_tool.wear_of): refused by name."""
    c = t.d["opening"].get("closure")
    w = (getattr(t.inp, "wear", None) or {}).get(c)
    if w not in WEARS:
        raise WearRefused(f"opening.closure {c!r}: no wear state ({w!r}): step 2's ties must give it (fastened [] = open, "
                          "every fastening = closed); garment_plan step style")
    return w


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


def neckline(t) -> tuple:
    """(the neck tape's points with the back lowered, the side neck points' height). The tape runs round the neck's
    base, at the back where the neck turns vertical (the cervicale): cut there, the cloth climbs the back of the neck as
    a stand. A draft's back neck runs from the side neck point (HPS) DOWN to centre back by BACK_NECK_DEPTH_M; the
    back of the tape is lowered to that (cos^2 from the side to centre back); the front is the tape's."""
    neck = np.asarray(t.inp.tapes["neck"], float)
    cn = t.cn
    side = np.abs(neck[:, 0]) > np.abs(neck[:, 0]).max() - 0.005
    z_hps, y_hps = float(neck[side, 2].mean()), float(neck[side, 1].mean())
    back = np.clip((neck[:, 1] - y_hps) / max(neck[:, 1].max() - y_hps, 1e-6), 0, 1)
    cap = z_hps - BACK_NECK_DEPTH_M * back ** 2
    N = neck.copy()
    N[:, 2] = np.where(neck[:, 1] > y_hps, np.minimum(neck[:, 2], cap), neck[:, 2])
    t.info["neckline"] = {"hps_z": round(z_hps, 4), "hps_y": round(y_hps, 4), "cb_z_tape": round(float(neck[np.argmax(neck[:, 1]), 2]), 4),
                          "cb_z": round(float(N[np.argmax(neck[:, 1]), 2]), 4), "back_depth_mm": BACK_NECK_DEPTH_M * 1000}
    return N, z_hps, y_hps


def _axis_dense(t, n=400):
    tt = np.linspace(t.tax[0], t.tax[-1], n)
    return np.c_[[np.interp(tt, t.tax, t.CAX[:, i]) for i in range(3)]].T


def arm_dir(t) -> np.ndarray:
    """The sleeve's down-the-arm direction in the front view (x out, z), unit: from the axis's end."""
    A = t.CAX[-1] - t.CAX[-3]
    return np.array([abs(A[0]), A[2]]) / np.hypot(A[0], A[2])


def along_from_wrist(t, xz, wrist) -> float:
    """A traced edge's place along the arm (front view, m) past a wrist mark (+ toward the hand), folded to +x."""
    xz = np.asarray(xz, float)
    Q = np.c_[np.abs(xz[:, 0]) - abs(wrist[0]), xz[:, 1] - wrist[1]]
    return float(np.median(Q @ arm_dir(t)))


def sleeve_hem_point(t) -> tuple:
    """(the hem's point on the sleeve axis, how). `sleeves.hem` a step-2 trace: its place past the PICTURE's wrist
    carried onto the MODEL's wrist along the arm (the length read like with like: the pose and the body differ); a
    step-0 height: the axis point at that height."""
    h = t.d["sleeves"]["hem"]
    C = _axis_dense(t)
    w = getattr(t.inp, "wrists", None) or {}
    if h in t.inp.traces and "photo" in w and "model" in w:
        s = along_from_wrist(t, t.inp.traces[h]["xz"], w["photo"])
        m = np.asarray(w["model"], float)
        al = np.c_[C[:, 0] - m[0], C[:, 2] - m[1]] @ arm_dir(t)
        p = C[int(np.argmin(np.abs(al - s)))]
        return p, f"step 2's {h!r}: {s * 1000:+.1f} mm past the picture's wrist, carried onto the model's"
    z = float(t.inp.heights[h])
    return C[int(np.argmin(np.abs(C[:, 2] - z)))], f"step 0's height {h!r} (z {z:.3f})"


def neck_and_wrists(t, V, F):
    neck, _, _ = neckline(t)
    cn = t.cn
    an = np.arctan2(neck[:, 1] - cn[1], neck[:, 0] - cn[0])
    o = np.argsort(an)
    an_s, zn_s = an[o], neck[o, 2]
    phi_neck = lambda P: np.interp(np.arctan2(P[:, 1] - cn[1], P[:, 0] - cn[0]), an_s, zn_s, period=2 * np.pi) - P[:, 2]
    V, F = largest(*clip(V, F, phi_neck(V)))
    if "sleeves" in t.parts:
        p, how = sleeve_hem_point(t)
        A = (t.CAX[-1] - t.CAX[-3]) / np.linalg.norm(t.CAX[-1] - t.CAX[-3])
        phi = lambda P: np.maximum(-((_folded(P) - p) @ A), np.linalg.norm(np.cross(_folded(P) - p, A), axis=1) - 0.12)
        t.info["sleeve"].update(hem_z=round(float(p[2]), 3), hem_at=[round(float(p[0]), 4), round(float(p[2]), 4)], hem_from=how)
    else:  # (no sleeves: the armhole is cut on the cone)
        phi = lambda P: -t.cone.sdist(_folded(P))
    V, F = largest(*clip(V, F, phi(V)))
    t.phi_neck = phi_neck
    return V, F


def closure(t, state: str):
    """x_edge(z) (the over front's edge, metres) of the toile in `state` ("closed": the CUT state; "open": the worn
    look) and what it was made from (t.info["opening"]); None without an opening."""
    if "opening" not in t.parts:
        return None
    op, tr = t.d["opening"], t.inp.traces
    lap = float(op.get("lap_mm") or 0) / 1000 if state == "closed" else 0.0
    edge = tr[op["edge"]]
    bt = t.inp.marks.get(op.get("buttons")) if op.get("buttons") else None
    t.info["opening"] = {"wear": wear(t), "cut": "closed", "state": state, "closure": op.get("closure"),
                         "lap_mm": lap * 1000, "edge": op["edge"]}
    if "lapel" in t.parts:
        lp = t.d["lapel"]
        ROLL = to_corner(tr[lp["roll"]])
        ROLL = ROLL[np.argsort(-ROLL[:, 1])]  # gorge (top) -> break
        z_top, z_brk, x_brk = ROLL[0, 1], ROLL[-1, 1], ROLL[-1, 0]
        if state == "open":  # (the picture's place: nothing moved)
            shift = lambda z: 0.0 * np.asarray(z, float)
        else:
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
    if state == "open":  # (each front's edge where the trace puts it, from the hem up to the break)
        top = min(z_brk, float(LOW[-1, 1]))
        t.info["opening"].update(break_z=None if not np.isfinite(z_brk) else round(float(z_brk), 3),
                                 edge_x_mm={f"{z:.3f}": round(float(np.interp(z, LOW[:, 1], LOW[:, 0])) * 1000, 1)
                                            for z in np.linspace(float(LOW[0, 1]), top, 4)})
        x_lo = lambda z: np.interp(z, LOW[:, 1], LOW[:, 0])
        if x_roll is None:
            return x_lo
        x_hi = front_neck(t, x_roll)
        return lambda z: np.where(z >= z_brk, x_hi(z), x_lo(z))
    z_btm = float(np.min(bt[:, 1])) if bt is not None and len(bt) else min(z_brk, float(LOW[:, 1].max()))
    x0 = np.interp(z_btm, LOW[:, 1], LOW[:, 0])
    dx_cut = lambda z: np.where(z < z_btm, np.interp(z, LOW[:, 1], LOW[:, 0]) - x0, 0.0)
    t.info["opening"].update(buttons_z=sorted(round(float(z), 4) for z in bt[:, 1]) if bt is not None else [],
                             lowest_button_z=round(z_btm, 3), break_z=None if not np.isfinite(z_brk) else round(float(z_brk), 3))
    if x_roll is None:
        return lambda z: -lap + dx_cut(z)
    x_hi = front_neck(t, x_roll)
    return lambda z: np.where(z >= z_brk, x_hi(z), -lap + dx_cut(z))


def front_neck(t, x_roll):
    """The over front's edge above the break: the roll line up to its top (the gorge point, step 2's roll trace's
    first point), then the FRONT NECKLINE from the gorge point up and in to the side neck point (HPS: the neck tape's
    outermost points), straight in the front view (a draft's front neck from the HPS down to the gorge): one edge
    running round the neck seam at the HPS, so the collar sews to a real neckline (R3f-4; R3f-3 left the roll top's x
    standing up over the shoulder to centre's plane: a 45 mm vertical edge with a jog at the HPS)."""
    g = t.lapel_geom
    z_top = float(g["z_top"])
    x_top = float(x_roll(z_top))
    neck, z_h, _ = neckline(t)
    x_h = float(np.abs(neck[:, 0]).max())
    t.info["front_neck"] = {"gorge_point": [round(x_top, 4), round(z_top, 4)], "hps": [round(x_h, 4), round(z_h, 4)],
                            "drop_mm": round((z_h - z_top) * 1000, 1), "out_mm": round((x_top - x_h) * 1000, 1),
                            "from": "gorge point: step 2's roll trace's top; HPS: step 3's neck tape's side points"}
    w = lambda z: np.clip((z - z_top) / max(z_h - z_top, 1e-6), 0, 1)
    return lambda z: np.where(z > z_top, x_top + (x_h - x_top) * w(z), x_roll(z))


def halves(t, V, F, x_edge):
    """The over (left) half to its edge in front and to centre back behind; the under (right) half its mirror, its lap
    LAP_UNDER_M inside; welded at centre back: one surface whose front overlaps (closed) or parts (open: no lap)."""
    phi = lambda P: np.where(P[:, 1] < t.yc, P[:, 0] - x_edge(P[:, 2]), P[:, 0])
    Vh, Fh = largest(*clip(V, F, phi(V)))
    Vr, Fr = Vh * MIR, Fh[:, ::-1].copy()
    lap = (Vr[:, 0] > 1e-6) & (Vr[:, 1] < t.yc)
    Vr[lap] -= LAP_UNDER_M * t.grad(Vr[lap])
    Vw, Fw = weld(np.r_[Vh, Vr], np.r_[Fh, Fr + len(Vh)])
    return Vw, Fw


def lapel_outline(t):
    """The lapel's outline (module doc) in the front view: g["x_l"] (its outer edge x at z), g["z_line"] (its top z at
    x); t.roll_line (the roll on the toile, break -> the gorge point) and t.info["lapel"]."""
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
    g.update(x_l=x_l, z_line=z_line, TOP=TOP)
    t.info["lapel"] = {"width_traced_mm": round(w0 * 1000, 1), "width_mm": round(w * 1000, 1),
                       "roll_mm": round(float(np.linalg.norm(np.diff(rl, axis=0), axis=1).sum() * 1000), 1),
                       "break_z": round(float(z_brk), 4), "gorge_z": round(float(z_top), 4)}
    t.roll_line = rl


def lapel(t, V, F):
    """A lapel alone (no collar part): the toile under its outline, lifted LAPEL_LIFT_M (with a collar the lapel and the
    collar are ONE turned flap: toile_flap.py)."""
    lapel_outline(t)
    g = t.lapel_geom
    x_roll, x_l, z_line, z_brk = g["x_roll"], g["x_l"], g["z_line"], g["z_brk"]
    Vl, Fl = V, F
    for ph in (lambda P: P[:, 0] - x_roll(P[:, 2]), lambda P: x_l(P[:, 2]) - P[:, 0],
               lambda P: z_line(P[:, 0]) - P[:, 2], lambda P: P[:, 2] - z_brk, lambda P: (t.yc - 0.03) - P[:, 1]):
        Vl, Fl = clip(Vl, Fl, ph(Vl))
    Vl, Fl = largest(Vl, Fl)
    return Vl + LAPEL_LIFT_M * t.grad(Vl), Fl


STATE_ATTRS = ("x_edge", "lapel_geom", "roll_line", "flap_layout")
STATE_INFO = ("opening", "front_neck", "lapel", "collar", "flap")


def _state(t, full, state) -> dict:
    """{part: (V, F)} of the toile in `state` (closure): the halves, the turned flaps, the collar."""
    t.x_edge = closure(t, state)
    out = {"toile": halves(t, *full, t.x_edge) if t.x_edge is not None else full}
    if "collar" in t.parts:  # (the lapels and the collar: ONE flap turned back about ONE roll line, R3f-9)
        from .toile_flap import drape
        lapel_outline(t)
        out["flap"] = drape(t, out["toile"])
    elif "lapel" in t.parts:
        Vl, Fl = lapel(t, *full)
        out["lapel.L"] = (Vl, Fl)
        out["lapel.R"] = (Vl * MIR, Fl[:, ::-1].copy())
    return out


def cut(t, V, F) -> dict:
    """{part: (V, F)}: the toile CUT (neck, sleeve hems, the opening), its turned flap (the lapels and the collar as ONE piece, toile_flap.py),
    always in the CLOSED state (R3f-7, C504): a garment worn open is the same pattern as worn closed (the fronts lap at
    centre front, the buttons on it); the wear state is how it is worn, looked at and hung. Worn open, the OPEN state
    (each front's edge where traced, the roll as traced) is built too: t.worn (the look, the outline rows, the hang's
    start), its numbers in t.info["worn"], its roll line / collar grid in t.worn_arrays; t's other attributes and
    numbers are the closed (cut) state's."""
    V, F = neck_and_wrists(t, V, F)
    full = (V, F)
    t.closed_mesh = full  # (the girth rows read the closed surface before it is split at the fronts)
    worn = wear(t) if "opening" in t.parts else "closed"
    t.worn, t.worn_arrays = None, {}
    if worn == "open":
        t.worn = _state(t, full, "open")
        t.info["worn"] = {k: t.info.pop(k) for k in STATE_INFO if k in t.info}
        t.worn_arrays = {k: getattr(t, k) for k in ("roll_line", "flap_layout") if getattr(t, k, None) is not None}
        for a in STATE_ATTRS:
            setattr(t, a, None)
    out = _state(t, full, "closed")
    if t.worn is None:
        t.worn = out
    return out
