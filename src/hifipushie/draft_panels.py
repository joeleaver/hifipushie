"""Where the seams round the body fall: step 2's `panels` (the style's shares of a girth) and step 4's row `panels`.

Why (trial s4-27, the suit jacket, 2026-11-15): its side body came out "a narrow sliver, about 46 mm at the chest", the
proportion of the FreeSewing block it extended (jaeger), and every row passed: the girths row sums the pieces, so a
round of the right length with its seams in the wrong places is invisible to it. A pattern maker places the side-body
seams where the style wants them (a three-piece lounge jacket: the front seam under the front of the armhole, the back
seam at the blade) and only then shapes the pieces. So the style states it and the flat is checked against it.

STEP 2 `panels` [{girth: a body girth by name (chest, waist, hips...: what step 3 measures), shares: {piece: share of
  the round, ...} (step 1's pieces by base name, without .L / .R: a left and right pair share it between them; the
  shares sum to 1), source}] (`check`, called by garment_plan's step-2 check). Read off the reference where its seams
  show; else the convention for the garment, said in source (a three-piece lounge jacket at the chest: front ~0.40,
  side ~0.22, back ~0.38 of the round, the front's to the centre line).
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
SUM_TOL = 0.02  # the shares' sum may miss 1 by this (read off a picture to two figures)
FORM = ("panels: [{girth: a body girth by name (chest, waist, hips...), shares: {piece base name (no .L/.R): share of "
        "the round}, summing to 1, source}] where the seams round the body fall (draft_panels.py)")


def base(p: str) -> str:
    return p[:-2] if p.endswith((".L", ".R")) else p


def check(panels, pieces: dict, bad: list):
    """Step 2's `panels` refused by name (FORM)."""
    if panels is None:
        return
    if not isinstance(panels, list):
        bad.append(FORM)
        return
    have = {base(p) for p in pieces}
    for i, e in enumerate(panels):
        w = f"panels[{i}]"
        if not isinstance(e, dict) or not isinstance(e.get("girth"), str) or not isinstance(e.get("shares"), dict):
            bad.append(f"{w}: {FORM}")
            continue
        sh = e["shares"]
        for k, v in sh.items():
            if base(k) not in have:
                bad.append(f"{w}.shares.{k}: not a step-1 piece (have {', '.join(sorted(have))})")
            if not isinstance(v, (int, float)) or not 0 < v < 1:
                bad.append(f"{w}.shares.{k}: a share of the round between 0 and 1")
        tot = sum(v for v in sh.values() if isinstance(v, (int, float)))
        if abs(tot - 1) > SUM_TOL:
            bad.append(f"{w}.shares sum to {tot:.2f}: the pieces round the {e['girth']} share all of it (1)")
        if not str(e.get("source") or "").strip():
            bad.append(f"{w}.source: where the seams show on the reference, or the convention for the garment")


def _widths(B: dict, decl: dict, T: dict, g: str) -> list:
    """[(ring, {piece: width m}, {base: lap m off})] of girth g on the flat, placed as the girths row places it."""
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
        out.append((ring, w, off))
    return out


def rows(B: dict, step2: dict | None, step3: dict | None, decl: dict | None = None) -> list:
    """Row `panels` (module docstring); [] when there is nothing to check."""
    from . import draft_tapes, tape_geom
    decl = decl or B.get("decl") or {}
    T = tape_geom.tapes(step3)
    plan = [e for e in ((step2 or {}).get("output") or step2 or {}).get("panels") or [] if isinstance(e, dict)]
    rid = {"id": "panels", "back_to": "4", "target": f"each piece's share of a girth as step 2's panels state it, within "
           f"{TOL_MM:.0f} mm a piece"}
    named = sorted({n for p in B["pieces"] for n in draft_tapes.names_of(decl, p) if (T.get(n) or {}).get("kind") == "loop"})
    if not plan:
        for g in named:
            for ring, w, _ in _widths(B, decl, T, g):
                bs = {base(p) for p in ring}
                if len(bs) >= 3:
                    return [dict(rid, status="FAIL", back_to="2", value=f"{g}: {len(bs)} pieces round it ("
                                 + ", ".join(f"{p} {1000 * v:.0f} mm" for p, v in w.items()) + "); no shares stated",
                                 why=f"step 2 states no panels: where the seams between {', '.join(sorted(bs))} fall "
                                     f"round the {g} is the style's choice, not the block's",
                                 fix=f"back to step 2: garment_plan style with {FORM}")]
        return []
    vals, why = [], []
    for e in plan:
        g, sh = e["girth"], {base(k): float(v) for k, v in e["shares"].items()}
        if (T.get(g) or {}).get("kind") != "loop":
            why.append(f"{g}: step 3 has no girth {g!r} (back to step 3: body_tape)")
            continue
        for ring, w, off in _widths(B, decl, T, g):
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
    return [dict(rid, status="FAIL" if why else "PASS", value="; ".join(vals) or "no stated girth placed",
                 why="; ".join(why), fix="move the seams between the named pieces by the named mm (the design's seam "
                 "points at that level; back to step 4); step 2's shares if the reference says otherwise" if why else "")]


def _neighbours(B: dict, p: str, ring: set) -> set:
    from .draft_girths import _seam_pairs
    return {pb for pa, _, pb, _ in _seam_pairs(B) if pa == p and pb in ring}
