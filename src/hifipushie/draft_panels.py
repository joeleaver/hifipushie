"""Where the seams round the body fall: step 2's `panels` (the style's shares of a girth) and step 4's row `panels`.

Why (trial s4-27, the suit jacket, 2026-11-15): its side body came out "a narrow sliver, about 46 mm at the chest", the
proportion of the FreeSewing block it extended (jaeger), and every row passed: the girths row sums the pieces, so a
round of the right length with its seams in the wrong places is invisible to it. A pattern maker places the side-body
seams where the style wants them (a three-piece lounge jacket: the front seam under the front of the armhole, the back
seam at the blade) and only then shapes the pieces. So the style states it and the flat is checked against it.

STEP 2 `panels` (panel_shares.py, F4): each piece's share of a girth, read off the reference or filled from the one
  named convention, never typed (t s4-28: shares typed as the block's own proportions passed this row against itself).
STEP 4 row `panels` (`rows`): each stated girth placed on the flat as the girths row places it (draft_girths: the level
  on each piece, the ring round the body); each base's width along its level (a closure's lap off the over / under
  pieces, a vent's overlap off its under piece) as a share of the round. FAIL: a piece more than TOL_MM off its share
  (per piece: a pair's each side), naming the piece, how many mm, which way, and its neighbours in the ring to take it
  from. FAIL (back to step 2): a ring of THREE OR MORE pieces a side round a girth some piece's tapes name, with no
  shares stated for any girth: a panel between two others is where a block's proportion goes wrong unseen (a two-piece
  body's one side seam is the block's and the girths row's business). Nothing here knows a garment."""
from __future__ import annotations

import numpy as np

TOL_MM = 15.0  # mm a piece, at its level: the level is placed to ~1 cm (draft_girths.TOL_MM's reasoning)


def base(p: str) -> str:
    return p[:-2] if p.endswith((".L", ".R")) else p


def _widths(B: dict, decl: dict, T: dict, g: str) -> list:
    """[(ring, {piece: width m}, {base: lap m off}, {piece: level line (q, u)})] of girth g on the flat, placed as the
    girths row places it."""
    from . import draft_girths as dg, draft_tapes, draft_vents
    loop = np.asarray(T[g]["loop"], float)
    lines, _, _ = dg.place(B, loop, T, decl)
    comps, _ = dg.rings(B, lines)
    named = {p for p in B["pieces"] if g in draft_tapes.names_of(decl, p)}
    comps = [c for c in comps if c & named]  # (a sleeve's girth plane crossing the torso isn't the torso's)
    out = []
    for ring in comps:
        w = {p: dg.width(np.asarray(B["pieces"][p]["P"], float), *lines[p])[0] for p in sorted(ring)}
        off = {}
        lap = dg.laps(B, ring, lines)[0]
        cl = [c for c in B.get("closures") or [] if c.get("over") in ring and c.get("under") in ring]
        for c in cl:
            for k in ("over", "under"):
                off[base(c[k])] = off.get(base(c[k]), 0.0) + lap / (2 * len(cl))
        vl = draft_vents.laps(B, ring, lines)
        vs = [v for v in decl.get("vents") or [] if isinstance(v, dict) and str(v.get("under", "")).split(":")[0] in ring]
        for v in vs:
            off[base(v["under"].split(":")[0])] = off.get(base(v["under"].split(":")[0]), 0.0) + vl / len(vs)
        out.append((ring, w, off, lines))
    return out


def rows(B: dict, step2: dict | None, step3: dict | None, decl: dict | None = None) -> list:
    """Row `panels` (module docstring); [] when there is nothing to check."""
    from . import draft_moves, draft_tapes, tape_geom
    decl = decl or B.get("decl") or {}
    T = tape_geom.tapes(step3)
    plan = [e for e in ((step2 or {}).get("output") or step2 or {}).get("panels") or [] if isinstance(e, dict)]
    rid = {"id": "panels", "back_to": "4", "target": f"each piece's share of a girth as step 2's panels state it, within "
           f"{TOL_MM:.0f} mm a piece"}
    named = sorted({n for p in B["pieces"] for n in draft_tapes.names_of(decl, p) if (T.get(n) or {}).get("kind") == "loop"})
    if not plan:
        for g in named:
            for ring, w, _, _ in _widths(B, decl, T, g):
                bs = {base(p) for p in ring}
                if len(bs) >= 3:
                    return [dict(rid, status="FAIL", back_to="2", value=f"{g}: {len(bs)} pieces round it ("
                                 + ", ".join(f"{p} {1000 * v:.0f} mm" for p, v in w.items()) + "); no shares stated",
                                 why=f"step 2 states no panels: where the seams between {', '.join(sorted(bs))} fall "
                                     f"round the {g} is the style's choice, not the block's",
                                 fix=f"back to step 2: garment_plan style with {_form()}")]
        return []
    stale = [e.get("girth", "?") for e in plan if not all(isinstance(v, dict) and "share" in v
                                                           for v in (e.get("shares") or {}).values())]
    if stale:  # (F4: a record written before shares had sources: its step 2 no longer validates)
        return [dict(rid, status="FAIL", back_to="2", value=f"step 2's panels at {', '.join(stale)} have no sources",
                     why="each share is read off the reference or filled from the convention (panel_shares.py, F4)",
                     fix=f"back to step 2: garment_plan style with {_form()}")]
    vals, why, moves = [], [], {}  # (moves: {seam: {"seam", "at": {mm along: mm}}}, every level's crossing)
    for e in plan:
        g, sh = e["girth"], {base(k): float(v["share"]) for k, v in e["shares"].items()}
        if (T.get(g) or {}).get("kind") != "loop":
            why.append(f"{g}: step 3 has no girth {g!r} (back to step 3: body_tape)")
            continue
        for ring, w, off, lines in _widths(B, decl, T, g):
            _crossings(B, ring, lines, moves)
            bw = {}
            for p, v in w.items():
                bw.setdefault(base(p), []).append(p)
            if not set(sh) & set(bw):
                continue
            tot = sum(w.values()) - sum(off.values())
            got = {b: (sum(w[p] for p in ps) - off.get(b, 0.0)) for b, ps in bw.items()}
            vals.append(f"{g}: round {1000 * tot:.0f} mm: " + ", ".join(
                f"{b} {got[b] / tot:.2f} ({1000 * got[b] / len(bw[b]):.0f} mm a piece; plan "
                + (f"{sh[b]:.2f})" if b in sh else "none)") for b in sorted(bw)))
            diff = {b: (got[b] - sh.get(b, 0.0) * tot) / len(bw[b]) for b in bw}
            for b in sorted(bw):
                if b not in sh:
                    why.append(f"{g}: {b} lies in the ring but step 2's shares don't name it (back to step 2)")
                    continue
                d = 1000 * diff[b]
                if abs(d) > TOL_MM:
                    nb = sorted({base(q) for p in bw[b] for q in _neighbours(B, p, ring)} - {b})
                    give = [n for n in nb if n in diff and (diff[n] < 0) != (d < 0) and 1000 * abs(diff[n]) > TOL_MM]
                    why.append(f"{g}: {b} is {abs(d):.0f} mm a piece too {'wide' if d > 0 else 'narrow'} (its share "
                               f"{got[b] / tot:.2f} against step 2's {sh[b]:.2f} of {1000 * tot:.0f} mm): move its seams "
                               f"{'in' if d > 0 else 'out'} by {abs(d):.0f} mm in total at the {g} line"
                               + (f", {'to' if d > 0 else 'from'} " + ", ".join(
                                   f"{n} ({1000 * abs(diff[n]):.0f} mm a piece too {'narrow' if d > 0 else 'wide'})"
                                   for n in give) if give else ""))
                    opp = [n for n in nb if n in diff and (diff[n] < 0) != (d < 0)]  # (within tolerance too)
                    if d > 0 or not give:  # (a pair off both ways: the wide one names it, once)
                        _hints(B, bw, b, give or opp or nb, diff, lines, d, moves)
    return [dict(rid, status="FAIL" if why else "PASS", value="; ".join(vals) or "no stated girth placed",
                 why="; ".join(why), fix=_fix([draft_moves.entry(m["seam"], m["at"]) for m in moves.values()
                                       if any(abs(v) >= 1 for v in m["at"].values())]) if why else "")]


def _twin(p: str, ring) -> bool:
    """p is a pair's right side whose left side is there too (its moves follow the left's: draft_moves.expand)."""
    return p.endswith(".R") and p[:-2] + ".L" in ring


def _crossings(B: dict, ring: set, lines: dict, moves: dict) -> None:
    """Every seam of the ring crossed at this level, at a 0 mm move (so a move declared at one level keeps the others)."""
    from . import draft_moves
    for p in sorted(x for x in ring if not _twin(x, ring) and x in lines):
        for q in sorted(q for q in _neighbours(B, p, ring) if q > p):
            c = draft_moves.crossing(B, p, q, lines[p])
            if c:
                moves.setdefault(tuple(c[0]), {"seam": c[0], "at": {}})["at"].setdefault(round(c[1]), 0.0)


def _hints(B: dict, bw: dict, b: str, give: list, diff: dict, lines: dict, d: float, moves: dict) -> None:
    """Into moves: b's seams with the neighbours in give whose seam crosses the level (a shoulder seam doesn't) moved by
    b's d mm, shared among them as far as each is off the other way (a neighbour within tolerance: all of it)."""
    from . import draft_moves
    ring = {x for xs in bw.values() for x in xs}
    can = {}
    for n in give:
        for p in [p for p in bw[b] if not _twin(p, ring)]:
            for q in [q for q in _neighbours(B, p, ring) if base(q) == n]:
                f, s = sorted((p, q))
                c = draft_moves.crossing(B, f, s, lines[f]) if f in lines else None
                if c:  # (the narrow one grows: + toward the second piece when the first is the narrow one)
                    can.setdefault(n, []).append((c, 1.0 if (f == q) == (d > 0) else -1.0))
    w = {n: max(0.0, -np.sign(d) * diff[n]) for n in can}
    for n, hits in can.items():
        mm = abs(d) * (w[n] / sum(w.values()) if sum(w.values()) > 0 else 1.0 / len(can))
        for (seam, at), sg in hits:
            m = moves.setdefault(tuple(seam), {"seam": seam, "at": {}})["at"]
            m[round(at)] = m.get(round(at), 0.0) + sg * mm


def _fix(moves: list) -> str:
    from . import draft_moves
    if not moves:
        return ("move the seams between the named pieces by the named mm (the design's seam points at that level; back "
                "to step 4); step 2's shares if the reference says otherwise")
    return ("declare (the converter re-cuts both pieces, the seam still sews; one entry a seam, its levels in one "
            f"'at' list, every level it crosses): moves [{', '.join(moves)}]. Form: {draft_moves.FORM}. Step 2's shares if the reference says "
            "otherwise")


def _form() -> str:
    from .panel_shares import FORM
    return FORM


def _neighbours(B: dict, p: str, ring: set) -> set:
    from .draft_girths import _seam_pairs
    return {pb for pa, _, pb, _ in _seam_pairs(B) if pa == p and pb in ring}
