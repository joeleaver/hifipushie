"""The upper lid as ONE structure: the eye step's SHAPE term (eyelid / orbit, 2026-10-11; Joe: "We are treating the
crease as if it's different from the eyelid but it's not"; from spikes/eyelid/lidsolve.py).

The upper lid is one sheet from the lashes to the brow: a margin with an edge, a platform lying ON the ball, a turn
where the levator tucks the skin in (the "crease" is only that line) and the drape coming forward to the brow. GNM's
skin round the eye is built for it (lidrings: closed rings round the opening, finest at its crease rings) and the fold
is an IDENTITY feature there (its expression basis shears the whole sheet and never forms a fold). So the lid's form is
solved in the identity alone, on GNM's own vertices, in one linear step:

  target   a DONOR head's lid (rings 1..rt, upper half: default GNM sample #376, a platform on the ball with one turn)
           re-proportioned to the person: each vertex keeps its stand-off from the ball and its place across the lid;
           its height over the margin is stretched below the donor's crease so the crease lands on the person's fold
           line (mm over the margin per column: the eye ruler's read of the picture) and shifted above it
  held     ring 0 of both lids (the margins the eye ruler set: 0.05 mm), gnm_mm's measures (0.3 mm: the orbit and
           everything else the block-in measured), every other skin vertex and the eyeballs (`hold` mm)
  min |W_t (V(c) - target)|^2 + |W_h (V(c) - V(c0))|^2 + |J_mm (c - c0) / 0.3|^2 + lam |c - c0|^2
a miss ALONG the surface counts a quarter (a vertex sliding in the skin is not a shape error); three rounds for the
normals. GNM frame, raw mm. What it cannot give (GNM has none in 2000 heads): a re-entrant tuck, skin over skin.

THE BALL. Our eyeball (base.gnm_head) is seated against the six lid landmarks, not the lid's surface, and is not GNM's
own ball, so a platform at the donor's stand-off can let it through the skin (el_f3: a brown patch on the lid).
`lid_step` measures the lid's stand-off from OUR ball on the shipped head after the solve and raises the designed
platform (`clear`) until every lid vertex clears it by GUARD."""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

DATA = Path(__file__).with_name("blockin_lid.npz")
NC = 170
RT = 8                # last designed ring
SIG_T = 0.1           # mm: a designed vertex
HOLD = 1.0            # mm: every other skin vertex, the eyeballs
HOLD_MARGIN = 0.05    # mm: ring 0
HOLD_MM = 0.3         # mm: gnm_mm's measures
TW = 0.25             # weight of a miss along the surface
LAM = 1.0
GUARD = 0.25          # mm: the least stand-off of the lid's skin (rings 1..7) from OUR eyeball on the shipped head
CLEAR_STEP = 0.2      # mm: the designed platform lifted this much per try
CLEAR_MAX = 1.2
DONOR = "s376"
FOLD_HEIGHT = 4.7     # mm: the crisp fold's height over the margin when the picture gives no line
FOLD_BROW = 0.3       # mm: the brow regions held in the crisp fold (free: the brows come down ~2 mm)
FOLD_MM = 0.02        # the crisp fold's weight on gnm_mm's measures (mm; a weight against ~1000 designed vertices at
                      # 0.1 mm, not a tolerance: 0.3 does nothing, 0.02 keeps them within ~0.3 mm for 4 deg of turn)
FOLD_STANDOFF = 1.3   # mm: the designed platform off GNM's ball (gnm_fold's default); raised FOLD_STEP by the guard
FOLD_STEP = 0.2
FOLD_STANDOFF_MAX = 2.1
_C: dict = {}


def donor(name: str = DONOR) -> np.ndarray:
    """A donor lid's GNM identity (170,): "s376" (a platform on the ball, one turn, the drape: Joe's "reads right"),
    "s540" (a wedge with a turn and a strong drape), or any block-in model's name."""
    if "d" not in _C:
        z = np.load(DATA)
        _C["d"] = {k: np.asarray(z[k], float) for k in z.files}
    if name in _C["d"]:
        return _C["d"][name]
    from . import blockin as bi, store
    try:
        return bi.identity(store.load(name))
    except Exception:  # noqa: BLE001
        raise ValueError(f"lid donor: {', '.join(_C['d'])} or a block-in model's name, not {name!r}") from None


def _g():
    from . import gnm_controls as gc
    return gc.gnm()


def _reflect(V):
    from . import lidrings
    return (V * [-1, 1, 1])[lidrings.mirror()]


def lid_frame(V, ctr, r) -> dict:
    """Per ring k: (ids, u, v, s) of the upper half in the eye frame (u across, v up, s = stand-off from the ball)."""
    from . import lidrings
    out = {}
    for k in range(0, lidrings.NR + 1):
        ids = lidrings.upper_ids(k)
        P = V[ids] - ctr
        o = np.argsort(P[:, 0])
        ids, P = ids[o], P[o]
        out[k] = (ids, P[:, 0], P[:, 1], np.linalg.norm(P, axis=1) - r)
    return out


def _crease_of(F, U):
    """Per column u: the donor's crease height over its margin (the lowest stand-off among rings 3..8)."""
    hc = []
    for u in U:
        col = []
        for k in range(0, 10):
            _, uu, vv, ss = F[k]
            col.append((float(np.interp(u, uu, vv)), float(np.interp(u, uu, ss))) if uu[0] <= u <= uu[-1] else (np.nan, np.nan))
        col = np.array(col)
        k = 3 + int(np.nanargmin(col[3:9, 1]))
        hc.append(col[k, 0] - col[0, 0])
    return np.array(hc)


def design(Vd, cd, Vs, cs, r, hc_person, rt: int = RT, clear: float = 0.0) -> dict:
    """Targets for the LEFT eye: {vertex id: (xyz raw mm, weight)} for rings 1..rt, the donor's lid Vd (eye centre cd)
    carried onto the source's eye (Vs, cs). hc_person(f) = the person's fold height over the margin (raw mm) at the
    fraction f across the margin (0 inner .. 1 outer); None = the donor's own heights. clear: the platform this much
    further off the ball than the donor's."""
    Fd, Fs = lid_frame(Vd, cd, r), lid_frame(Vs, cs, r)
    ad, bd = Fd[0][1][0], Fd[0][1][-1]
    as_, bs = Fs[0][1][0], Fs[0][1][-1]
    Ud = np.linspace(ad + 0.3, bd - 0.3, 61)
    hcd = np.convolve(np.pad(_crease_of(Fd, Ud), 3, mode="edge"), np.ones(7) / 7, mode="valid")
    out = {}
    for k in range(1, rt + 1):
        ids, u, v, s = Fd[k]
        f = (u - ad) / (bd - ad)
        ok = (f > 0.02) & (f < 0.98)
        md = np.interp(u, Fd[0][1], Fd[0][2])               # the donor's margin under this vertex
        sd0 = np.interp(u, Fd[0][1], Fd[0][3])
        h = v - md
        hd = np.interp(u, Ud, hcd)
        us = as_ + f * (bs - as_)
        ms = np.interp(us, Fs[0][1], Fs[0][2])
        ss0 = np.interp(us, Fs[0][1], Fs[0][3])
        H = hd if hc_person is None else hc_person(f)
        h2 = np.where(h <= hd, h * H / np.maximum(hd, 0.3), H + (h - hd))
        s2 = s + (ss0 - sd0) * np.exp(-np.maximum(h2, 0) / 1.5)
        if clear:
            s2 = s2 + clear * np.clip(h2 / 1.0, 0, 1) * np.clip((H + 1.5 - h2) / 1.5, 0, 1)
        v2 = ms + h2
        w2 = np.sqrt(np.maximum((r + s2) ** 2 - us ** 2 - v2 ** 2, 0.0))
        wt = np.clip((f - 0.02) / 0.13, 0, 1) * np.clip((0.98 - f) / 0.13, 0, 1)   # the corners fade to the source's own lid
        for i, vid in enumerate(ids):
            if ok[i]:
                out[int(vid)] = (np.array([us[i], v2[i], w2[i]]) + cs, float(wt[i]))
    return out


def structure(V, u: float = 0.0) -> dict:
    """The upper lid's structure at a column on GNM's raw vertices V (mm), by ring, against GNM's own ball:
    crease_h (the turn's height over the margin), platform_s (mean stand-off of rings 2..crease: ~0 = lying on the
    ball), roll (the margin's), tuck (deg: the surface's turn at the crease ring), wall (deg off the ball's surface,
    crease -> 2 rings up), drape (the skin 3 mm above the crease stands this much further off)."""
    from . import lidrings
    ctr, r = lidrings.ball(V)
    col = {k: (v, w) for k, v, w in lidrings.column(V, ctr, u)}
    ks = [k for k in range(0, 12) if k in col]
    v = np.array([col[k][0] for k in ks])
    w = np.array([col[k][1] for k in ks])
    s = np.sqrt(u * u + v * v + w * w) - r
    a = np.r_[0, np.cumsum(np.hypot(np.diff(v), np.diff(w)))]
    turn = np.diff(np.degrees(np.arctan2(np.diff(s), np.diff(a))))
    ic = max(range(3, 9), key=lambda i: turn[i - 1])
    return {"crease_h": float(v[ic] - v[0]), "platform_s": float(s[2:ic + 1].mean()), "roll": float(s[:3].max() - s[ic]),
            "tuck": float(turn[ic - 1]), "wall": float(np.degrees(np.arctan2(s[ic + 2] - s[ic], a[ic + 2] - a[ic]))),
            "drape": float(np.interp(a[ic] + 3.0, a, s) - s[ic])}


def mean_structure(c, e=None, us=(-4.0, 0.0, 4.0)) -> dict:
    from . import gnm_controls as gc
    V = gc.vertices(np.asarray(c, float), e) * 1000
    q = [structure(V, u) for u in us]
    return {k: float(np.mean([x[k] for x in q])) for k in q[0]}


def solve(c0, cdn, hc_person=None, *, e=None, clear: float = 0.0, hold: float = HOLD, rt: int = RT, sig: float = SIG_T,
          lam: float = LAM, tw: float = TW, hold_mm: float | None = HOLD_MM) -> dict:
    """The whole-lid solve: identity c0 (170,) -> {"c", "dc" (|c - c0|), "miss" (target miss along the normal, rms mm),
    "ring_miss" {ring: rms}, "held" / "held_max" (the held skin's move, mm), "margins" (ring 0's move, rms mm), "mm"
    (the largest gnm_mm measure drift, mm)}. e: the head's expression vector (GNM's order) when it carries one."""
    from . import gnm_controls as gc, gnm_mm, lidrings
    g, t, mir = _g(), lidrings.topo(), lidrings.mirror()
    c0, cdn = np.asarray(c0, float), np.asarray(cdn, float)
    Vs, Vd = gc.vertices(c0, e) * 1000, gc.vertices(cdn) * 1000
    cs, r = lidrings.ball(Vs)
    cd, _ = lidrings.ball(Vd)
    tgt = dict(design(Vd, cd, Vs, cs, r, hc_person, rt, clear))
    cs_r = lidrings.ball(Vs, "right")[0] * [-1, 1, 1]       # the right eye: the same design on the reflected heads
    cd_r = lidrings.ball(Vd, "right")[0] * [-1, 1, 1]
    for vid, (p, w) in design(_reflect(Vd), cd_r, _reflect(Vs), cs_r, r, hc_person, rt, clear).items():
        tgt[int(mir[vid])] = (p * [-1, 1, 1], w)
    ids = np.array(sorted(tgt))
    P = np.array([tgt[i][0] for i in ids])
    wt = np.array([tgt[i][1] for i in ids])
    if "IB" not in _C:
        _C["IB"] = g["IB"][:NC].astype(np.float64) * 1000.0     # (NC, V, 3) mm per unit
    IB = _C["IB"]
    hm = (g["groups"]["skin_exterior"] | g["groups"]["eyes"]).copy()
    hm[ids] = False
    hid = np.flatnonzero(hm)
    m0 = (np.abs(t["ring"][hid]) <= 0) | (np.abs(t["ring"][mir[hid]]) <= 0)     # the lid margins, both lids, both eyes
    hw = np.where(m0, 1.0 / HOLD_MARGIN, 1.0 / hold)
    key = ("AhA", tuple(ids.tolist()), hold)
    if key not in _C:
        for k in [k for k in _C if isinstance(k, tuple) and k[0] == "AhA"]:
            _C.pop(k)
        Ah = (IB[:, hid] * hw[None, :, None]).reshape(NC, -1)
        _C[key] = Ah @ Ah.T
    AhA = _C[key].copy()
    if hold_mm:
        Jm = gnm_mm.jacobian() / hold_mm
        AhA += Jm.T @ Jm
    D0 = P - Vs[ids]
    IBt = IB[:, ids]
    dc = np.zeros(NC)
    full = wt > 0.99
    for _ in range(3):
        Nn = gc.normals(gc.vertices(c0 + dc, e))[ids]
        M = tw * np.eye(3)[None] + (1 - tw) * Nn[:, :, None] * Nn[:, None, :]
        At = (np.einsum("vij,cvj->cvi", M, IBt) * (wt / sig)[None, :, None]).reshape(NC, -1).T
        bt = (np.einsum("vij,vj->vi", M, D0) * (wt / sig)[:, None]).ravel()
        dc = np.linalg.solve(At.T @ At + AhA + lam * np.eye(NC), At.T @ bt)
    rn = ((D0 - np.tensordot(dc, IBt, 1)) * Nn).sum(1)
    mv = np.tensordot(dc, IB[:, hid], 1)
    rk = np.minimum(np.abs(t["ring"][ids]), np.abs(t["ring"][mir[ids]]))
    return {"c": c0 + dc, "dc": float(np.linalg.norm(dc)), "miss": float(np.sqrt((rn[full] ** 2).mean())),
            "miss0": float(np.sqrt((((D0 * Nn).sum(1))[full] ** 2).mean())),
            "ring_miss": {int(k): float(np.sqrt((rn[(rk == k) & full] ** 2).mean())) for k in range(1, rt + 1) if ((rk == k) & full).any()},
            "held": float(np.sqrt((mv ** 2).sum(1).mean())), "held_max": float(np.linalg.norm(mv, axis=1).max()),
            "margins": float(np.sqrt((mv[m0] ** 2).sum(1).mean())),
            "mm": float(np.abs(gnm_mm.jacobian()[:len(gnm_mm.NAMES)] @ dc).max()), "clear": float(clear)}


def _skin_rings() -> np.ndarray:
    """Per row of onemesh.head_template's skin vertices: the lid ring of either eye (99 elsewhere)."""
    if "sr" not in _C:
        from . import base as basemod, lidrings
        t, mir = lidrings.topo(), lidrings.mirror()
        sk = np.flatnonzero(np.asarray(basemod._gnm_data()["skin"]))
        ring = np.where(t["ring"] != 99, t["ring"], t["ring"][mir])
        up = _g()["T"][:, 1] > _g()["J"][2][1] + 0.0005
        _C["sr"] = (ring[sk], up[sk])
    return _C["sr"]


def ball_clearance(ht: dict, rings=range(1, 8)) -> dict:
    """The lid skin's stand-off from OUR eyeball on a shipped head (onemesh.head_template / base.gnm_head): {"min" (mm,
    the least over rings 1..7 of both lids, both eyes: under 0 the ball is through the skin), "upper" (the upper lid's
    least), "rings": {ring: least}, "landmarks" (the six lid landmarks' least: what the seat itself clears)}."""
    ring, up = _skin_rings()
    V = np.asarray(ht["verts"], float)[:len(ring)]
    r = float(ht["eye_r"])
    d = np.min([np.linalg.norm(V - np.asarray(c, float), axis=1) for c in ht["eyes"]], 0) - r
    out = {"rings": {int(k): float(d[ring == k].min() * 1000) for k in rings}}
    sel = np.isin(ring, list(rings))
    out["min"] = float(d[sel].min() * 1000)
    out["upper"] = float(d[sel & up].min() * 1000)
    lm = np.asarray(ht["lm68"], float)[36:48]
    out["landmarks"] = float((np.min([np.linalg.norm(lm - np.asarray(c, float), axis=1) for c in ht["eyes"]], 0) - r).min() * 1000)
    return out


def world_scale(ht: dict, c0, e=None) -> float:
    """World mm per raw GNM mm round the eye on a shipped head (the head's scale x the body's hook x eyes)."""
    from . import base as basemod, gnm_controls as gc, lidrings
    sk = np.flatnonzero(np.asarray(basemod._gnm_data()["skin"]))
    loc = -np.ones(len(_g()["T"]), int)
    loc[sk] = np.arange(len(sk))
    ids = np.concatenate([lidrings.upper_ids(k) for k in range(0, 9)])
    A, B = (gc.vertices(np.asarray(c0, float), e) * 1000)[ids], np.asarray(ht["verts"], float)[loc[ids]] * 1000
    return float(np.sqrt(((B - B.mean(0)) ** 2).sum() / ((A - A.mean(0)) ** 2).sum()))


def expression_vector(base: dict):
    """The base head's expression as GNM's vector (None when it has none)."""
    ex = (base.get("head") or {}).get("expression") or {}
    if not any(ex.values()):
        return None
    names = _g()["ex_names"]
    e = np.zeros(len(names))
    for k, v in ex.items():
        if k in names:
            e[names.index(k)] = float(v)
    return e


def lid_step(base: dict, heights=None, cols=None, corners=None, donor_name: str = DONOR, hold: float = HOLD,
             guard: float = GUARD, log=print) -> dict:
    """The eye step's shape term on a block-in base (the margins already on the eye ruler's rows): the whole-lid solve,
    then the BALL GUARD: the result's lid against OUR eyeball on the shipped head; while any lid vertex (rings 1..7)
    stands under `guard` mm off the ball the designed platform is lifted CLEAR_STEP and the solve repeated.
    heights: the picture's fold line over the margin (mm at the model) at cols (mm from the iris centre, + = outer),
    corners = (inner u, outer u); None = the donor's own fold heights. -> solve()'s dict + "structure0" / "structure" /
    "donor" (mean_structure), "ball0" / "ball" (ball_clearance), "clear", "tries", "scale"."""
    from . import blockin as bi, onemesh

    def head(c):
        b = copy.deepcopy(base)
        bi.set_identity({"base": b}, c)
        ht = onemesh.head_template(b)
        for kk in [k for k in onemesh._CACHE if isinstance(k, tuple) and k and k[0] == "head_t"]:
            onemesh._CACHE.pop(kk, None)
        return ht
    c0 = bi.identity({"base": base})
    e = expression_vector(base)
    cdn = donor(donor_name)
    ht0 = head(c0)
    sc = world_scale(ht0, c0, e)
    hc = None
    if heights is not None and np.isfinite(np.asarray(heights, float)).sum() >= 2:
        h, u = np.asarray(heights, float), np.asarray(cols, float)
        ok = np.isfinite(h)
        fcol = (u[ok] - corners[0]) / (corners[1] - corners[0])
        hc = lambda f: np.interp(f, fcol, h[ok]) / sc   # noqa: E731
    b0 = ball_clearance(ht0)
    clear, tries, best = 0.0, 0, None
    while True:
        s = solve(c0, cdn, hc, e=e, clear=clear, hold=hold)
        s["ball"] = ball_clearance(head(s["c"]))
        tries += 1
        log(f"  lid solve (donor {donor_name}, platform lifted {clear:.1f} mm): |dc| {s['dc']:.2f}, target miss along the normal "
            f"{s['miss0']:.2f} -> {s['miss']:.2f} mm, margins moved {s['margins']:.2f} mm, measures within {s['mm']:.2f} mm; "
            f"lid over OUR eyeball: least stand-off {s['ball']['min']:.2f} mm (upper lid {s['ball']['upper']:.2f})")
        if best is None or s["ball"]["min"] > best["ball"]["min"]:
            best = s
        if s["ball"]["min"] >= guard or clear >= CLEAR_MAX - 1e-9:
            break
        clear += CLEAR_STEP
    s = best
    s.update(structure0=mean_structure(c0, e), structure=mean_structure(s["c"], e), donor=mean_structure(cdn), ball0=b0,
             tries=tries, scale=sc, donor_name=donor_name, guard=guard, guarded=bool(s["ball"]["min"] >= guard),
             heights=None if hc is None else [float(x) for x in np.asarray(heights, float)])
    return s


def fold_step(base: dict, heights=None, cols=None, corners=None, brow: float | None = FOLD_BROW,
              hold_mm: float | None = FOLD_MM, guard: float = GUARD, log=print) -> dict:
    """The eye step's shape term, RECIPE A (overhang, 2026-10-11; Joe: "recipe A is as good as it has to get"):
    gnm_fold.fold's crisp fold, a designed lid (platform on the ball up to the fold line, the turn, the drape; no donor
    head) fitted in the identity alone with the brows held `brow` mm, gnm_mm's measures held (`hold_mm`: a weight, not
    a tolerance; the hollow under the brow is left free: the fold IS that) and every other skin vertex at 1 mm. heights
    / cols as lid_step (the picture's fold line over the margin, mm at the model; None = 4.7 mm). Then the BALL GUARD:
    while the upper lid on the shipped head stands under `guard` mm off OUR eyeball the platform's stand-off is raised
    FOLD_STEP. -> gnm_fold.fold()'s dict + "kind": "crisp", "structure0" / "structure", "ball0" / "ball", "standoff",
    "tries", "scale", "guarded", "heights", "crease" (raw mm at the pupil), "mm" (largest held measure's drift)."""
    from . import blockin as bi, gnm_fold as gf, gnm_mm, onemesh

    def head(c):
        b = copy.deepcopy(base)
        bi.set_identity({"base": b}, c)
        ht = onemesh.head_template(b)
        for kk in [k for k in onemesh._CACHE if isinstance(k, tuple) and k and k[0] == "head_t"]:
            onemesh._CACHE.pop(kk, None)
        return ht
    if expression_vector(base) is not None:
        raise ValueError("fold_step: identity only (the head carries an expression: use lid_step)")
    c0 = bi.identity({"base": base})
    ht0 = head(c0)
    sc = world_scale(ht0, c0)
    crease, hs = FOLD_HEIGHT, None
    if heights is not None and np.isfinite(np.asarray(heights, float)).sum() >= 2:
        h, u = np.asarray(heights, float), np.asarray(cols, float)
        ok = np.isfinite(h)
        hs = [float(x) for x in h]
        crease = lambda uu: np.interp(np.asarray(uu, float) * sc, u[ok], h[ok]) / sc   # noqa: E731
    b0 = ball_clearance(ht0)
    standoff, tries, best = FOLD_STANDOFF, 0, None
    while True:
        s = gf.fold(c0, crease=crease, brow=brow, hold_mm=hold_mm, standoff=standoff)
        s["ball"], s["standoff"] = ball_clearance(head(s["c"])), standoff
        tries += 1
        a = s["after"]
        log(f"  crisp fold (platform {standoff:.1f} mm off GNM's ball): |dc| {s['dc']:.2f}, turn {s['before']['turn_mean']:.0f} -> "
            f"{a['turn_mean']:.0f} deg at {a['h_mean']:.1f} mm, brow ring {s['brow_drop']:+.1f} mm down; lid over OUR eyeball: "
            f"least stand-off {s['ball']['upper']:.2f} mm (both lids {s['ball']['min']:.2f})")
        if best is None or s["ball"]["upper"] > best["ball"]["upper"]:
            best = s
        if s["ball"]["upper"] >= guard or standoff >= FOLD_STANDOFF_MAX - 1e-9:
            break
        standoff += FOLD_STEP
    s = best
    d = gnm_mm.jacobian() @ (s["c"] - c0)
    held = [(n, float(x)) for n, x in zip(gnm_mm.HELD, d) if n not in gf.MM_FREE]
    s.update(kind="crisp", structure0=mean_structure(c0), structure=mean_structure(s["c"]), ball0=b0, tries=tries, scale=sc,
             guard=guard, guarded=bool(s["ball"]["upper"] >= guard), heights=hs, brow=brow,
             crease=float(crease(0.0)) if callable(crease) else float(crease),
             mm=max(abs(x) for _, x in held), mm_worst=sorted(held, key=lambda t: -abs(t[1]))[:4],
             hollow=float(d[gnm_mm.HELD.index("brow_hollow")]))
    return s


def _fold_text(s: dict) -> str:
    a, b = s["structure0"], s["structure"]
    q0, q1 = s["before"], s["after"]
    row = lambda q, r: (f"turn {r['turn_mean']:.0f} deg at {r['h_mean']:.1f} mm over the margin, platform {q['platform_s']:.1f} mm off "   # noqa: E731
                        f"the ball, drape {q['drape']:.1f} mm, brow ring {r['brow_h']:.1f} mm over the margin")
    out = (f"  LID as one structure, a CRISP FOLD (recipe A: identity only; a designed lid on GNM's rings, no donor head"
           + (", the turn on the picture's fold line" if s.get("heights") is not None else f", the fold at {FOLD_HEIGHT} mm (no line read)")
           + f": {s['crease']:.1f} mm at the pupil; raw GNM mm):\n    before {row(a, q0)}\n    after  {row(b, q1)}\n"
           f"    |dc| {s['dc']:.1f}; held skin moved {s['held_rms']:.2f} mm rms (max {s['held_max']:.1f}: "
           + ", ".join(f"{k} {v:.1f}" for k, v in list(s["worst"].items())[:3]) + f"); the brow ring came {s['brow_drop']:+.1f} mm DOWN "
           f"(brows held {s['brow']} mm); measures held within {s['mm']:.2f} mm ("
           + ", ".join(f"{k} {v:+.2f}" for k, v in s["mm_worst"][:3]) + f"); the hollow under the brow {s['hollow']:+.1f} mm (the fold itself)\n"
           "    No skin-over-skin overhang (in GNM that is HOODING: block_in_step {\"hooding\": x}, for hooded / deep-set eyes only).\n"
           f"    EYEBALL GUARD: upper lid over our eyeball, least stand-off {s['ball0']['upper']:.2f} -> {s['ball']['upper']:.2f} mm "
           f"(both lids {s['ball']['min']:.2f}; needs {s['guard']:.2f})")
    if s["standoff"] > FOLD_STANDOFF:
        out += f"; the platform's stand-off was raised to {s['standoff']:.1f} mm to clear it ({s['tries']} tries)"
    if not s["guarded"]:
        out += ("\n    WARNING: the eyeball still comes within the guard: look at the dressed lid for a patch of the "
                "ball's colour (the ball is seated on six lid landmarks, not the lid's surface)")
    if abs(s["brow_drop"]) > 1.5 or s["mm"] > 0.5:
        out += "\n    CHECK: the brow or a measure moved: read brow_read / face_ruler again before keeping it"
    return out


def text(s: dict) -> str:
    if s.get("kind") == "crisp":
        return _fold_text(s)
    a, b, d = s["structure0"], s["structure"], s["donor"]
    row = lambda q: (f"platform {q['platform_s']:.1f} mm off the ball, turn {q['tuck']:.0f} deg at {q['crease_h']:.1f} mm, wall "   # noqa: E731
                     f"{q['wall']:.0f} deg, drape {q['drape']:.1f} mm")
    out = (f"  LID as one structure (identity only; GNM's rings 1-{RT} of the upper lid toward donor {s['donor_name']!r} at the "
           f"person's proportions"
           + ("" if s.get("heights") is None else ", the turn on the picture's fold line")
           + f"; raw GNM mm):\n    before {row(a)}\n    after  {row(b)}\n    donor  {row(d)}\n"
           f"    |dc| {s['dc']:.2f}; target miss along the normal {s['miss0']:.2f} -> {s['miss']:.2f} mm (the first fold row "
           f"resists: GNM's ceiling is a ~25 deg turn on a tall platform and no skin-over-skin overhang: left as it is); "
           f"margins moved {s['margins']:.2f} mm, the mm measures {s['mm']:.2f} mm at most\n"
           f"    EYEBALL GUARD: lid over our eyeball, least stand-off {s['ball0']['min']:.2f} -> {s['ball']['min']:.2f} mm "
           f"(upper lid {s['ball']['upper']:.2f}; needs {s['guard']:.2f})")
    if s["clear"]:
        out += f"; the designed platform was lifted {s['clear']:.1f} mm to clear it ({s['tries']} tries)"
    if not s["guarded"]:
        out += ("\n    WARNING: the eyeball still comes within the guard: look at the dressed lid for a patch of the "
                "ball's colour (the ball is seated on six lid landmarks, not the lid's surface)")
    return out
