"""Step 1's MIRRORING (garment_plan.check_parts): the project's own convention, ".L" mirrors to ".R", for any garment
(t s1-4: an agent that declared only the left side was refused every ".R" name, and wrote its centre-back seam as
back.L:cb = back.L:cb; s1-2 / s1-3 traced both sides by hand: agents split on it).

FORM: centre = the garment's centre line on the picture: u (one view) or {view index: u}. A piece or detail named
"X.L" brings "X.R" unless the plan traces "X.R" itself (a picture that isn't symmetric): its place mirrored about the
centre (u -> 2 c - u), every ".L" in it (pieces it sits on, edges it follows, edge names) swapped to ".R". A seam with
a ".L" in it brings its mirrored twin, unless that twin is already there (either way round). Each copy carries
mirrored_from. Names ending ".R" may then be used anywhere (a CB seam back.L:cb = back.R:cb, a zip between front.L
and front.R).
"""
from __future__ import annotations

import copy

_L, _R = ".L", ".R"


def swap(x):
    """Every '.L' ending (a name, a 'piece:edge' on either side) as '.R', in strings, lists and dict values."""
    if isinstance(x, str):
        if ":" in x:
            a, _, b = x.partition(":")
            return f"{swap(a)}:{swap(b)}"
        return x[:-2] + _R if x.endswith(_L) else x
    if isinstance(x, list):
        return [swap(v) for v in x]
    if isinstance(x, dict):
        return {k: swap(v) for k, v in x.items()}
    return x


def _centre(centre, view):
    if isinstance(centre, (int, float)) and not isinstance(centre, bool):
        return float(centre)
    if isinstance(centre, dict):
        c = centre.get(str(view), centre.get(view))
        return float(c) if isinstance(c, (int, float)) else None
    return None


def _flip(pts, c):
    if not isinstance(pts, list):
        return pts
    if pts and isinstance(pts[0], (int, float)):
        return [2 * c - pts[0], *pts[1:]]
    return [_flip(p, c) for p in pts]


def _mirror_where(w, centre, name: str, bad: list):
    if not isinstance(w, dict):
        return w
    c = _centre(centre, w.get("view", 0))
    if c is None:
        bad.append(f"centre: the garment's centre line u on view {w.get('view', 0)} (to mirror {name} to "
                   f"{name[:-2] + _R}): centre = u, or {{view: u}}; or trace {name[:-2] + _R} yourself")
        return None
    out = dict(w)
    for k in ("outline", "at", "outlines"):
        if k in out:
            out[k] = _flip(out[k], c)
    return out


def mirror(p: dict, bad: list) -> list:
    """Adds the ".R" side to p in place; returns the names it made (for the answer)."""
    made = []
    centre = p.get("centre")
    for grp in ("pieces", "details"):
        items = p.get(grp)
        if not isinstance(items, dict):
            continue
        for n in [k for k in items if isinstance(k, str) and k.endswith(_L)]:
            r = n[:-2] + _R
            if r in items or not isinstance(items[n], dict):
                continue  # (traced by hand: kept)
            x = swap(copy.deepcopy(items[n]))
            if isinstance(items[n].get("edges"), (dict, list)):  # (a piece's own edge names: .L -> .R too)
                x["edges"] = swap(items[n]["edges"]) if isinstance(items[n]["edges"], list) else \
                    {swap(k): v for k, v in items[n]["edges"].items()}
                if items[n].get("hidden"):
                    x["hidden"] = swap(items[n]["hidden"])
            if "where" in items[n]:
                x["where"] = _mirror_where(items[n]["where"], centre, n, bad)
            x["mirrored_from"] = n
            items[r] = x
            made.append(r)
    seams = p.get("seams")
    if isinstance(seams, list):
        have = {(s.get("a"), s.get("b")) for s in seams if isinstance(s, dict)}
        have |= {(b, a) for a, b in have}
        for s in list(seams):
            ends = [str(s.get(k, "")) for k in ("a", "b")] if isinstance(s, dict) else []
            if not any(e.endswith(_L) or _L + ":" in e for e in ends) or any(
                    e.endswith(_R) or _R + ":" in e for e in ends):
                continue  # (no left side in it, or it already crosses the centre: back.L:cb = back.R:cb)
            t = dict(s, a=swap(s.get("a")), b=swap(s.get("b")))
            if (t["a"], t["b"]) in have:
                continue
            t["mirrored_from"] = f"{s.get('a')} = {s.get('b')}"
            seams.append(t)
            have |= {(t["a"], t["b"]), (t["b"], t["a"])}
    return made
