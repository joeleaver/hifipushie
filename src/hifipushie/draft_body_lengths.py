"""The flat gate's body_lengths row (F6): the pattern checked against the body BEFORE anything is built.

Joe (2026-11-03): with right measurements, a right draft and its ease, nothing should stretch and seams should meet; so
a seam whose length step 1 says comes from a body measurement is checked here against that measurement as step 3 took
it, plus the plan's fit ease (step 0 `fit` {region: {ease_mm}}; a region named as the measurement, or by ALIAS):
  - a GIRTH (step 3 took it as a loop: waist, seat, upperLeg): every drafted edge on the step-1 seams that name it,
    summed round (both sides of a pair, a fold's mirrored half), against girth + ease. Shorter than that by more than
    TOL = cloth that must stretch round the body: FAIL. Longer than girth + ease by more than LONG: INFO (loose).
  - a LENGTH (a path: inseam, waistToUpperLeg): each drafted edge on those seams against it, SAID (INFO): step 1 names
        where a length comes from, not that the edge equals it (a sleeve underarm is shoulderToWrist less its cap); an edge
    sewn at both ends shorter than it is flagged so. A path is the straight / vertical distance, so a curved edge only
    has it as a lower bound (said in the row).
`rows(B, step1, step3, fit)` -> [the row]. Nothing here names a garment: the record's own names carry it.
"""
from __future__ import annotations

TOL = 0.01  # shorter than the body + ease by more than 1 % (the plain seam tolerance) must stretch
LONG = 0.10  # longer than the body + ease by more than 10 %: said, not refused (style ease the plan didn't name)
ALIAS = {"thigh": "upperLeg", "hip": "hips", "bust": "chest", "calf": "calf", "neck": "neck"}


def _base(e: str) -> tuple[str, str]:
    p, ed = e.split(":", 1)
    p = p[:-2] if p[-2:] in (".L", ".R") else p
    return p, ed[:-2] if ed.endswith(".m") else ed


def _ease(name: str, fit: dict) -> tuple[float, str]:
    for r, e in (fit or {}).items():
        if r == name or ALIAS.get(r) == name:
            try:
                return float(e.get("ease_mm", 0.0)), r
            except (AttributeError, TypeError, ValueError):
                pass
    return 0.0, ""


def _anchored(decl: dict, piece: str, arc: str) -> bool:
    """Both ends of piece's edge `arc` ("a>b") are ends of OTHER sewn edges of that piece."""
    ends = set()
    for s in decl.get("seams") or []:
        for side in (s.get("a"), s.get("b")):
            for e in [side] if isinstance(side, str) else list(side or []):
                p, ed = e.split(":", 1)
                if p != piece:
                    continue
                a = ((decl.get("edges") or {}).get(p) or {}).get(ed)
                if isinstance(a, str) and a != arc:
                    ends |= {a.split(">")[0], a.split(">")[-1]}
    pts = arc.split(">")
    return pts[0] in ends and pts[-1] in ends


def rows(B: dict, step1: dict, step3: dict | None, fit: dict | None) -> list:
    from . import cloth_check as cc
    meas = {m["name"]: m for m in (step3 or {}).get("measurements") or []}
    dx = B.get("decl") or {}
    exp = dx.get("seams") or []
    sm = cc.seams(B)
    if len(exp) != len(sm) or not meas:
        return [{"id": "body_lengths", "status": "INFO", "value": "n/a", "target": "every body-measured seam vs its "
                 "measurement + ease", "why": "no step-3 measurements" if not meas else "seams not one to one"}]
    fails, infos, n = [], [], 0
    rounds: dict = {}  # girth name -> [(step-1 seam, expanded seam indices)]: summed round over every seam naming it
    for r in step1.get("seams") or []:
        names = ((r.get("length") or {}).get("body")) or []
        want = {r.get("a"), r.get("b")}
        hit = [i for i, s in enumerate(exp) if isinstance(s.get("a"), str) and isinstance(s.get("b"), str)
               and {"{}:{}".format(*_base(s["a"])), "{}:{}".format(*_base(s["b"]))} == want]
        for nm in names:
            m = meas.get(nm)
            if not m or not hit:
                continue
            n += 1
            ease, reg = _ease(nm, fit)
            body = float(m["mm"])
            tgt = body + ease
            how = f"{nm} {body:.0f} mm" + (f" + {reg} ease {ease:.0f}" if reg else " + no fit ease")
            if m.get("loop") is not None:  # a girth: summed round, below
                n -= 1
                rounds.setdefault(nm, []).append((r, hit))
                continue
            for i in hit:  # a length: each drafted edge
                s = exp[i]
                for side, L in ((s["a"], sm[i]["len_a_mm"]), (s["b"], sm[i]["len_b_mm"])):
                    p, ed = side.split(":", 1)
                    arc = ((dx.get("edges") or {}).get(p) or {}).get(ed)
                    curved = isinstance(arc, str) and L > body * 1.02
                    if L < tgt * (1 - TOL):
                        line = f"{side}: {L:.0f} mm < {how} = {tgt:.0f} mm ({L - tgt:+.0f} mm)"
                        if isinstance(arc, str) and _anchored(dx, p, arc):  # (INFO: step 1 names where a length
                            # COMES FROM, not that it equals it: a sleeve's underarm is shoulderToWrist less its cap)
                            infos.append(line + ", sewn at both ends (stretches if it spans that measurement)")
                        else:
                            infos.append(line + ", a free end (shorter by design?)")
                    elif curved:
                        infos.append(f"{side}: {L:.0f} mm >= {nm} {body:.0f} mm (a straight distance: a lower bound only)")
                    break  # (a pair's sides agree within the seams row: read one)
    for nm, hs in rounds.items():
        n += 1
        ease, reg = _ease(nm, fit)
        body = float(meas[nm]["mm"])
        tgt = body + ease
        how = f"{nm} {body:.0f} mm" + (f" + {reg} ease {ease:.0f}" if reg else " + no fit ease")
        idx = sorted({i for _, h in hs for i in h})
        got = sum((sm[i]["len_a_mm"] + sm[i]["len_b_mm"]) / 2 for i in idx)
        edges = ", ".join(exp[i]["b"] for i in idx)
        if got < tgt * (1 - TOL):
            fails.append(f"{nm}: round {got:.0f} mm ({edges}) < {how} = {tgt:.0f} mm ({got - tgt:+.0f} mm: must "
                         f"stretch round the body). change: the design's edges on the {nm} seams, or step 0's ease")
        else:
            infos.append(f"{nm}: round {got:.0f} mm ({edges}) vs {how} = {tgt:.0f} mm ({got - tgt:+.0f} mm"
                         + (", loose" if got > tgt * (1 + LONG) else "") + ")")
    return [{"id": "body_lengths", "status": "FAIL" if fails else "PASS",
             "value": f"{n} body measurements, {len(fails)} short", "target": "each girth step 1 names on seams, summed "
             "round its drafted edges, >= that girth + the plan's fit ease (lengths: said, not refused)",
             "why": "; ".join(fails[:6]), "info": "; ".join(infos[:8]), "back_to": "4",
             "fix": "redraft the named edges (or step 1's measurement for the seam, step 0's ease)" if fails else ""}]
