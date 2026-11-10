"""The flat gate's seam_ends row (F6): each seam's two edges run the same way, start to start, end to end.

Why: a seam's two sides are joined point for point from their starts. An edge declared "a>b" against its partner's
"y>x" sews the one's centre-front end to the other's side: the lengths agree, so the length rows PASS, and the build
fails much later (T13b: the cloak's hood.R:neck CF>CB against the cloak's CB>CF, held 1343 %; F5: t8's trousers'
front waist "cfWaist>sideWaist" sewn to the band's "sd>cf", held 3736 %). Twice a flat gate passed it.

What the pattern knows about where an edge end sits, read from the outline, never from a garment:
  - the point's own NAME on both sides (C403): a point both sides name (a design's parts drafted from one block share
    them: notch, collarCorner, neck) is one place; named at one side's start and the other's end is reversed;
  - the centre line: a point named cf* / cb* (or centre / center + front / back, "nape" = the back of the neck), and
    on a piece cut on the fold, a point on the fold line (x = 0) = "centre" (either);
  - the side: a point named side* / sd*;
  - up and down: an edge running mostly vertically in its piece (|dy| >= VERTICAL x |dx| end to end) has a top end
    (higher y; flip_y pieces are already turned) - a piece's top is its top.
A chain side (a list of edges) is read by its first edge's start and last edge's end.
A seam is REVERSED when its evidence says start meets end (a known place at one side's start sits at the other's end,
and nothing says start meets start); aligned or unknown pass. `rows(B)` -> the one row; `reversed_seams(B)` -> list.
"""
from __future__ import annotations

import re

import numpy as np

VERTICAL = 2.0  # an edge whose end-to-end run is >= 2x as tall as wide reads up / down
FOLD_TOL = 1e-3  # m: a point this near x = 0 on a piece cut on the fold lies on the fold (the centre line)


def _tokens(name: str) -> list:
    base = name.split(".")[0]
    return [t.lower() for t in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", base)]


def place_of(name: str) -> str | None:
    """cf / cb / side / None from a point's name."""
    t = _tokens(name)
    if not t:
        return None
    if t[0] == "cf" or ({"centre", "center"} & set(t) and "front" in t):
        return "cf"
    if t[0] == "cb" or ({"centre", "center"} & set(t) and "back" in t) or t[0] == "nape":
        return "cb"
    if t[0] in ("side", "sd"):
        return "side"
    return None


def _same(x, y) -> bool:
    if x is None or y is None:
        return False
    return x == y or ("centre" in (x, y) and {x, y} <= {"centre", "cf", "cb"})


def _end(pc: dict, name: str, folded: bool) -> str | None:
    p = place_of(name)
    if p is None and folded and name in pc["names"] and abs(pc["P"][pc["names"][name]][0]) < FOLD_TOL:
        return "centre"
    return p


def _side_ends(B: dict, side) -> dict:
    """{"start", "end": place or None, "up": +1 top->bottom / -1 bottom->top / 0}, "label"} of one seam side."""
    from . import pattern
    es = [side] if isinstance(side, str) else list(side)
    first, last = es[0].split(":", 1), es[-1].split(":", 1)
    pa, pb = B["pieces"][first[0]], B["pieces"][last[0]]
    fold = lambda p: bool(((B.get("decl") or {}).get("pieces") or {}).get(p, {}).get("fold"))
    sa, ea = first[1].split(">")[0], last[1].split(">")[-1]
    up = 0
    if len(es) == 1:
        ix = pattern.arc_indices(pa, first[1])
        d = pa["P"][ix[-1]] - pa["P"][ix[0]]
        if abs(d[1]) >= VERTICAL * abs(d[0]) and abs(d[1]) > 0:
            up = 1 if d[1] < 0 else -1
    return {"start": _end(pa, sa, fold(first[0])), "end": _end(pb, ea, fold(last[0])), "up": up,
            "sname": sa, "ename": ea, "pieces": {first[0], last[0]},
            "label": f"{first[0]}:{first[1]}" if len(es) == 1 else f"{first[0]}:{first[1]} .. {last[0]}:{last[1]}"}


def reversed_seams(B: dict) -> list:
    """[{"a", "b", "why", "fix"}] for each seam whose sides run opposite ways."""
    out = []
    for A, Bs in B.get("seams") or []:
        try:
            x, y = _side_ends(B, A), _side_ends(B, Bs)
        except (KeyError, ValueError, IndexError):
            continue
        cross = [f"{x['start']} at {x['label']}'s start meets {y['label']}'s end"
                 for _ in [0] if _same(x["start"], y["end"]) and not _same(x["start"], y["start"])]
        cross += [f"{x['end']} at {x['label']}'s end meets {y['label']}'s start"
                  for _ in [0] if _same(x["end"], y["start"]) and not _same(x["end"], y["end"])]
        if x["up"] and y["up"] and x["up"] != y["up"]:
            cross.append(f"{x['label']} runs {'down' if x['up'] > 0 else 'up'} its piece, "
                         f"{y['label']} runs {'down' if y['up'] > 0 else 'up'}")
        # (C403: a point both sides NAME sits at the same place: the jacket's undercollar "notch>collarCorner>shoulderL"
        # against the front's "neck>collarCorner>notch" passed, notch and shoulder being no cf / cb / side; sewn so, the
        # front's neck point and its notch, 106 mm apart, became one node; a piece sewn to itself is left to the build)
        if not (x["pieces"] & y["pieces"]):
            nm_cross = [f"point {x['sname']} at {x['label']}'s start is {y['label']}'s end"
                        for _ in [0] if x["sname"] == y["ename"] and x["sname"] != y["sname"]]
            nm_cross += [f"point {x['ename']} at {x['label']}'s end is {y['label']}'s start"
                         for _ in [0] if x["ename"] == y["sname"] and x["ename"] != y["ename"]]
            nm_along = x["sname"] == y["sname"] or x["ename"] == y["ename"]
            if nm_cross and not nm_along:
                cross += nm_cross
        along = _same(x["start"], y["start"]) or _same(x["end"], y["end"]) or (x["up"] and x["up"] == y["up"])
        along = along or x["sname"] == y["sname"] or x["ename"] == y["ename"]
        if cross and not along:
            e = y["label"] if isinstance(Bs, str) else x["label"]
            pts = e.split(":", 1)[1].split(">") if " .. " not in e else []
            fix = (f'swap the edge\'s direction: "{">".join(pts)}" -> "{">".join(pts[::-1])}" (edges.'
                   f'{e.split(":")[0].split(".")[0]})' if pts else "reverse one side's edges (each \"a>b\" -> \"b>a\", "
                   "the chain in the other order)")
            out.append({"a": x["label"], "b": y["label"], "why": "; ".join(cross), "fix": fix})
    return out


def rows(B: dict) -> list:
    rev = reversed_seams(B)
    return [{"id": "seam_ends", "status": "FAIL" if rev else "PASS",
             "value": f"{len(B.get('seams') or [])} seams, {len(rev)} reversed",
             "target": "each seam's two edges run the same way: start to start, end to end (the centre line, the "
                       "side, a piece's top)",
             "why": "; ".join(f"{r['a']} || {r['b']}: {r['why']}" for r in rev[:6]),
             "fix": "; ".join(r["fix"] for r in rev[:6]) or "", "back_to": "4", "detail": rev}]
