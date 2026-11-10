"""PLANNED STATE (garment_steps T7, C287): the chain build is built straight into the style plan's ONE worn state.

Why (Joe 2026-11-02): "why build the shirt closed and then style it open, if we only need it open?" Run 3 found the band
always closed on its own button though the pattern's and the plan's band closure was open: the likely cause of the
collar points held together at CF and of the cloth forced under the fall's ends (front.R's edge +2.7 % off its cut).

The garment record's step 2 (garment_plan "style") names each closure's state. planned_wear() turns it into the build's
wear: the BAND closure's state is the wear (open / partly -> "open": the band's ends apart; closed -> "closed"); the FRONT
closure's pairs are tied as step 2's `ties` say (closure_ties.py, C391: which fastenings are done up, by number from the
top or by share along it); open / closed / partly are only their summary. Bends with targets the build chooses come from the plan: the collar points' spread (the FALL stage's
target; ratio of the neck width, mm, or px over the plan's neck_width row). With a record the plan wins: a `wear` or an
`opening` that contradicts it is refused by name. No record (or no step-2 state): the arguments, as before.

build_open(): the open build, straight. The band is solved once as its pressed ring (its rest shape: the band as cut and
pressed, never a state anything is built on), then opened (band_open) against the first fastened button's start on the
torso; the fall, rings and soft cloth are built under the open band, fastened only where the plan fastens; the plackets
fold on that cloth. No closed garment is built first (it was: stiff + soft closed, then restyled open)."""
from __future__ import annotations

import time

import numpy as np

class PlanContradiction(ValueError):
    """The arguments and the style plan disagree, or the plan asks for a state no stage builds."""


def _spread(style: dict) -> dict:
    """The collar points' planned spread: {"spread": neck widths} or {"spread_mm": mm}, with its source; {} if none."""
    rows = [r for r in (style.get("bends") or []) + (style.get("rows") or []) if isinstance(r, dict)]
    base = next((r["target"] for r in rows if r.get("what") == "neck_width" and isinstance(r.get("target"), dict)
                 and "value" in r["target"]), None)
    for r in rows:
        t = r.get("target")
        if r.get("what") != "collar_points_apart" or not isinstance(t, dict) or "value" not in t:
            continue
        u, v, src = t.get("unit"), float(t["value"]), f"style plan {r.get('id', 'collar_points_apart')}: {r.get('source', '')}"
        if u == "ratio" and t.get("of", "neck_width") == "neck_width":
            return {"spread": v, "spread_from": src}
        if u in ("mm", "cm"):
            return {"spread_mm": v * (10.0 if u == "cm" else 1.0), "spread_from": src}
        if u == "px" and base and base.get("unit") == "px" and float(base["value"]) > 0:
            return {"spread": round(v / float(base["value"]), 3), "spread_from": src + " (px over the neck_width row)"}
    return {}


def planned_wear(plan: dict | None, wear: str | None = None, opening: float | None = None) -> dict:
    """The build's wear dict from the record's step 2 (see the module doc). Raises PlanContradiction."""
    from . import structure_rows as sr
    style = (plan or {}).get("style") or {}
    from . import closure_ties as ct
    states = ct.states(style)  # (R1 C391: which fastenings are done up; open / closed / partly only as their summary)
    if not states:  # no record / no style plan: the arguments, as before
        if opening is not None and wear != "open":
            raise PlanContradiction("opening is how far an open collar opens: only with wear=\"open\"")
        w = {"state": wear or "closed"}
        if opening is not None:
            w["spread"] = float(opening)
        return w
    band = front = None
    bad = []
    for c, x in sr.closure_reads((plan or {}).get("parts"), states).items():
        s = x.get("state")
        if x.get("read") == "band_state":
            band = (c, x)
        elif x.get("read") == "front_state":
            front = (c, x)
        elif s != "closed":
            bad.append(f"ties.{c}: a fastening left undone; no chain stage builds that on this closure yet (a ring closes on "
                       "its own button; R3, docs/proposals/step5_one_build.md)")
    derived = "closed" if not band or band[1]["state"] == "closed" else "open"  # (the band pipeline's own switch, until R3)
    w = {"state": derived, "plan": {c: x.get("state") for c, x in states.items()},
         "ties": {c: x["tie"] for c, x in states.items()}}
    if band:
        w["band_tie"] = band[1]["tie"]
    if front:
        c, x = front
        w["front_tie"] = x["tie"]
        if x["state"] == "open":
            bad.append(f"ties.{c}: none of its fastenings done up; no chain stage lays a front with nothing tied yet (R3, "
                       "docs/proposals/step5_one_build.md); never plan a tie the reference doesn't show to get past this")
        elif x["state"] == "partly":
            t = x["tie"]
            if t.get("legacy") == "partly" and not (isinstance(t.get("fastened_from"), int) and t["fastened_from"] >= 1):
                bad.append(f"state.{c} partly (an old record): name the first fastened button, fastened_from=<1 = the top "
                           "button>, or write ties (C391)")
            elif derived == "closed":
                bad.append(f"ties.{c}: a front fastening undone under a band done up; no stage builds that yet (R3)")
    if bad:
        raise PlanContradiction("the style plan asks for what no chain stage builds: " + "; ".join(bad) +
                                ". next: change step 2 (garment_plan)")
    why = (f"ties.{band[0]} {band[1]['state']} ({band[1].get('source', '')})" if band else
           "no band closure in the plan: closed")
    if wear is not None and wear != derived:
        raise PlanContradiction(f"wear {wear!r} contradicts the style plan: {why}. With a garment record the plan decides "
                                f"the ONE worn state. next: call again without wear (builds {derived!r}), or change "
                                "step 2 (garment_plan)")
    w["state_from"] = why
    if derived == "open":
        sp = _spread(style)
        if sp and opening is not None and abs(float(opening) - float(sp.get("spread", -1))) > 1e-6:
            raise PlanContradiction(f"opening {opening} contradicts the style plan's collar spread ({sp['spread_from']}: "
                                    f"{sp.get('spread', sp.get('spread_mm'))}). next: call again without opening, or "
                                    "change the bend in step 2 (garment_plan)")
        w.update(sp or ({"spread": float(opening)} if opening is not None else {}))
    elif opening is not None:
        raise PlanContradiction(f"opening: the style plan builds the band closed ({why}); an opening only with an open band")
    return w


def apply_tie(closure: dict | None, tie: dict | None, uv) -> dict | None:
    """A closure's pairs tied as step 2's tie says (closure_ties.tied: by number from the top, or by share along it).
    A front keeps its pairs from the first tied one down (the build lays the cloth above it from the band, as a front
    fastened from that button); every pair after it is tied or left undone as the plan says. None tied: refused."""
    from . import closure_ties as ct
    from .chain_garment import ChainRefused
    if not closure or tie is None or tie.get("legacy") == "closed":  # (an old record's closed: the pattern's pairs as they were)
        return closure
    v = [tuple(p) for p in closure.get("v") or []]
    if not v:
        return closure
    y = [float(uv[a][1]) for a, _ in v]
    top, bot = max(y), min(y)
    shares = ct.shares_of(len(v)) if top - bot < 1e-9 else [(top - q) / (top - bot) for q in y]
    if "fastened" in tie and tie.get("of") not in (None, len(v)):
        raise ChainRefused(f"ties.{closure.get('name', 'closure')}: the plan counts {tie['of']} fastenings, the pattern has "
                           f"{len(v)} pairs. next: change step 2 (garment_plan) or step 4 (the closure's marks)")
    mask = ct.tied(tie, shares)
    if not any(mask):
        raise ChainRefused(f"ties.{closure.get('name', 'closure')}: none tied (R3). next: change step 2 (garment_plan)")
    k = mask.index(True)
    return dict(closure, v=v[k:], closed=mask[k:])


def button_start(b) -> np.ndarray:
    """Where the first fastened button starts, before any soft cloth: its cut distance below the front's neck point (sewn
    to the band, already built), down the body's centre front, a gap and a layer off it. (cf_shirt: the closed build's
    button sat 90 mm (cut) below the neck point; the torso-ring start put it 39 mm lower and 20 mm forward, and the
    band opened against it stretched its links 9x.)"""
    from .chain_garment import GAP, LAYER
    net, R = b.net, b.roles
    p, bv = R.front["over"], R.front["v"][0]
    bvp = bv[0] if net.piece[bv[0]] == net.pid(p) else bv[1]
    sew = list(b.sewn_with(p, R.band))
    L = np.linalg.norm(net.uv[sew] - net.uv[bvp], axis=1)
    top = b.X[net.root[sew[int(np.argmin(L))]]].copy()
    ys = np.arange(top[1] - 0.15, top[1] + 0.15, 0.001)
    for z in np.arange(top[2], top[2] - 3 * L.min(), -0.002):
        P = np.c_[np.zeros(len(ys)), ys, np.full(len(ys), z)]
        near = np.where(b.body.contact.query(P)[0] <= GAP + LAYER)[0]  # the front surface: the first point from the front
        if not len(near):
            continue
        q = P[near[0]]
        if np.linalg.norm(q - top) >= L.min():
            return q
    return np.array([0.0, top[1], top[2] - L.min()])


def build_open(b, t0: float) -> None:
    """The open build, straight (module doc). b: a chain_garment.GarmentBuild with wear state "open"."""
    net, R = b.net, b.roles
    b.wear["state"] = "open"
    b.band_closed()  # the band's pressed ring: its rest shape (band_open keeps its curve round the back)
    b.reads["band_ring_s"] = round(time.time() - t0, 1)
    bv = R.front["v"][0]
    b.X[net.root[bv[0]]] = b.X[net.root[bv[1]]] = button_start(b)  # (nothing soft is built yet)
    b.reads["button_start_mm"] = [round(float(c) * 1e3, 1) for c in b.X[net.root[bv[0]]]]
    b.band_open()  # the band in its planned state: ends apart, the sewn fronts tied to the first fastened button
    b.fall_build()
    b.fill_band()
    b.fall_surface()
    b.stiff_last()
    b.rings()
    b.reads["stiff_open_s"] = round(time.time() - t0, 1)
    # the first fastened button stays where the open band was tied to it: left free, the soft cloth carried it 10 mm down
    # and 14 mm out, the fronts' neck-to-button reach ran 12.6 mm past its cut and the plackets tore (T7)
    b.extra_held = np.zeros(net.n, bool)
    b.extra_held[list(bv)] = True
    b.soft_net()  # the soft cloth under the open band, fastened only where the plan fastens
    Xs = b.X.copy()
    b.X = b.plackets(Xs)
    bz = float(Xs[net.root[bv[0]], 2])
    b.reads["first_fastened_z_mm"] = round(bz * 1e3, 1)
    b.stay_v = np.isin(net.piece, [net.pid(p) for p in R.panels]) & (Xs[:, 2] < bz - 0.02)
    b.soft_net(start=b.X.copy(), far_z=bz - 0.03)
    b.under_cloth = b._cloth_contact()
    b.fall_build()
    b.fall_surface()
    b.stiff_last()
    b.soft_net(start=b.X.copy(), far_z=bz - 0.03)
    b.stay_v = None
    b.thread_read_all()
