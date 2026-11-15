"""The seams row's hint for a seam far off its ease: which named point a side should end at so the two sides agree.

Why (trial s4-27, the suit jacket, 2026-11-15): its sleeve cap chain came out 711 mm against a 475 mm armhole (+49.8 %).
In the FreeSewing two-piece sleeve it extended, the hind seam runs on ABOVE the obvious cap corners (to backPitchPoint on
the top sleeve, to the under sleeve's tall tip); counted as cap, that stretch made the cap half as long again, and "no
tool text says this". A pattern maker walks the cap against the armhole it is set into and marks where it ends. This
does the walk: for a seam outside its ease band, every way of ending its longer side's edges at one of their own named
outline points instead (cutting off the stretch past it at either end of one edge, or of two edges) whose new length
puts the seam inside its band; the fewest cuts first, then nearest the band's middle. The answer names the edges and the
points (`hint`); nothing is changed. Nothing here knows a garment."""
from __future__ import annotations

from itertools import combinations

import numpy as np

MAX_SHOWN = 2


def _cuts(B: dict, e: str, fixed: set = frozenset()) -> list:
    """[(label, metres removed, e)] of edge e ("piece:a>b>...") ended at one of its interior named points, at either
    end not in fixed (an end the side's next edge on the same piece starts from: the chain stays joined there)."""
    from . import pattern
    p, arc = e.split(":", 1)
    pc = B["pieces"].get(p)
    if pc is None:
        return []
    try:
        idx = list(pattern.arc_indices(pc, arc))
    except (KeyError, ValueError):
        return []
    P = np.asarray(pc["P"], float)
    pos = {i: k for k, i in enumerate(idx)}
    inner = sorted(((pos[i], n) for n, i in (pc.get("names") or {}).items() if i in pos and 0 < pos[i] < len(idx) - 1))
    ends = arc.split(">")
    out = []
    for k, n in inner:
        head, tail = pattern.length(P[idx[:k + 1]]), pattern.length(P[idx[k:]])
        if ends[-1] not in fixed:
            out.append((f"{p}:{ends[0]}...{n} (ended at {n}, dropping {n}...{ends[-1]})", tail, e))
        if ends[0] not in fixed:
            out.append((f"{p}:{n}...{ends[-1]} (started at {n}, dropping {ends[0]}...{n})", head, e))
    return out


def hint(B: dict, r: dict) -> str:
    """'' or a sentence: the ends that bring seam row r (cloth_check.seams + band) inside its band."""
    lo, hi = r["band"]
    la, lb = r["len_a_mm"] / 1000, r["len_b_mm"] / 1000
    long_a = la > lb * (1 + hi)
    side = r["a"] if long_a else r["b"]
    edges = [side] if isinstance(side, str) else list(side)
    other = lb if long_a else la
    want = (other * (1 + lo), other * (1 + hi)) if long_a else (other / (1 + hi), other / (1 + lo))
    mid = sum(want) / 2
    L = la if long_a else lb
    if L <= want[1]:
        return ""
    def tips(x: str) -> tuple[str, set]:
        p, arc = x.split(":", 1)
        n = arc.split(">")
        return p, {n[0], n[-1]}
    cuts = []
    for e in edges:
        p, mine = tips(e)
        fixed = {n for f in edges if f != e and tips(f)[0] == p for n in tips(f)[1]} & mine
        cuts += _cuts(B, e, fixed)
    found = []
    for n in (1, 2):
        for combo in combinations(cuts, n):
            if len({c[2] for c in combo}) < n:
                continue
            new = L - sum(c[1] for c in combo)
            if want[0] <= new <= want[1]:
                found.append((abs(new - mid), combo, new))
        if found:
            break
    if not found:
        return ""
    found.sort(key=lambda f: f[0])
    say = []
    for _, combo, new in found[:MAX_SHOWN]:
        e = new / other - 1 if long_a else other / new - 1
        say.append(" and ".join(c[0] for c in combo) + f" gives {1000 * new:.0f} mm, ease {100 * e:+.1f} %")
    return (f" (its {'a' if long_a else 'b'} side may run past where it should end: " + "; or ".join(say)
            + ": end the side's edges at the points where the seam it is sewn to ends, e.g. a seam that runs on above "
              "a cap's corners)")
