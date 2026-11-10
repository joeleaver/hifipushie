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

R3c (C396): there is no open build and no closed build, only chain_garment.GarmentBuild.run's one sequence, which ties
exactly the pairs these ties name (apply_tie). wear["state"] is a derived label (the job's directory, status texts):
nothing in the build branches on it. Refused only: an argument that contradicts the plan, a tie the pattern can't make
(apply_tie's count check), an old record's "partly" that names no first button (which pairs is unknown)."""
from __future__ import annotations

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
        # (C396: any other closure left undone is built as its tie says; it was refused, "no chain stage builds that")
    derived = "closed" if not band or band[1]["state"] == "closed" else "open"  # (a LABEL only: the job's dir, the texts)
    from . import fold_bends
    w = {"state": derived, "plan": {c: x.get("state") for c, x in states.items()},
         "ties": {c: x["tie"] for c, x in states.items()}}
    if fold_bends.planned(style):  # (R2 C392: each planned fold's turn, for R3's one crease turn)
        w["folds"] = fold_bends.wear(style)
    if band:
        w["band_tie"] = band[1]["tie"]
    if front:
        c, x = front
        w["front_tie"] = x["tie"]
        # (C396: a front with nothing tied, or partly tied under a band done up, is built: its untied edges are free)
        t = x["tie"]
        if t.get("legacy") == "partly" and not (isinstance(t.get("fastened_from"), int) and t["fastened_from"] >= 1):
            bad.append(f"state.{c} partly (an old record): name the first fastened button, fastened_from=<1 = the top "
                       "button>, or write ties (C391)")
    if bad:
        raise PlanContradiction("the style plan's ties can't be read: " + "; ".join(bad) +
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
    Every pair is kept, each marked tied or not (`closed`): the build ties only those, and none tied is a closure whose
    edges are free (C396; it was refused, and the pairs above the first tied one were dropped)."""
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
    return dict(closure, v=v, closed=ct.tied(tie, shares))


def first_tied(closure: dict | None, uv) -> tuple | None:
    """The topmost TIED pair of a closure (what used to be "the first fastened button"), None when none is tied: then
    whatever was held to it is free (C396)."""
    if not closure:
        return None
    v = [tuple(p) for p, c in zip(closure.get("v") or [], closure.get("closed") or []) if c]
    return max(v, key=lambda p: float(uv[p[0]][1])) if v else None


def top_tied(closure: dict | None, uv) -> bool:
    """Its topmost pair is tied (a stand's neck ends meet over a front done up at its top)."""
    v = [tuple(p) for p in (closure or {}).get("v") or []]
    if not v:
        return False
    k = max(range(len(v)), key=lambda i: float(uv[v[i][0]][1]))
    return bool((closure.get("closed") or [False] * len(v))[k])


def ties_of_wear(wear: dict) -> dict:
    """No record (no step-2 ties): the `wear` argument read as ties, as closure_ties.of_style reads an old record. "open"
    is the band's own closure left undone, the front's pairs as the pattern has them; "closed" is every pattern pair."""
    if wear.get("ties") or wear.get("state") != "open":
        return wear
    return dict(wear, band_tie={"fastened": [], "legacy": "open"})
