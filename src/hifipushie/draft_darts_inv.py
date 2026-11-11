"""INVENTORY DARTS ARE DRAFTED (C410): a dart step 1 builds is an opened dart on the pattern, never only a mark.

Trial s4-21 (2026-11-10, the suit jacket): step 1 inventoried `front_dart.L/.R`, "front (fish) dart ... the forepart's
waist suppression", build full. The draft declared it as a MARK only (a line drawn on the front), so the forepart had no
shaping of its own, and every row passed: marks_placed counted it placed, and the darts row only checks darts that ARE
declared. A dart is shaping: cloth taken out between two legs that meet at a tip. A mark can't take cloth out.

The row: every step-1 detail that is a dart (its `kind` is "dart", or its name or `what` names one) and is built (full or
simplified) needs a drafted dart (declarations `darts`) on each piece it is `on`: open on the outline ({piece, legs},
C361), or drawn inside the piece ({piece, inside, release}, C416: a fish dart, a dart ending in a pocket mouth; the tool
cuts it through along release and sews it). The s4-21 text said "slit it to a seam"; s4-22 and s4-23 then cut 1 mm
slits to the hem by hand, a seam down the front no tailor cuts (C416).
"""
from __future__ import annotations

import re

WORD = re.compile(r"\bdarts?\b", re.I)


def base(p: str) -> str:
    return p[:-2] if p.endswith((".L", ".R")) else p


def is_dart(name: str, d: dict) -> bool:
    if (d or {}).get("kind") is not None:
        return d.get("kind") == "dart"
    return bool(WORD.search(name.replace("_", " ")) or WORD.search(str((d or {}).get("what") or "")))


def row(step1: dict, decl: dict) -> dict | None:
    dets = (step1 or {}).get("details") or {}
    want = [(n, d) for n, d in dets.items() if isinstance(d, dict) and is_dart(n, d)
            and (d.get("build") or "full") != "omit"]
    if not want:
        return None
    have = {base(str(x.get("piece", ""))) for x in decl.get("darts") or [] if isinstance(x, dict)}
    miss = [f"{n} on {p}" for n, d in want for p in d.get("on") or [] if base(str(p)) not in have]
    return {"id": "darts_drafted", "status": "FAIL" if miss else "PASS",
            "value": f"{len(want)} inventory darts, {len(miss)} not drafted",
            "target": "every dart step 1 builds is an opened dart on its piece (declarations darts), not a mark",
            "why": ("; ".join(miss[:6]) + ": a mark takes no cloth out, so the piece has no shaping there. change: draft "
                    "the dart as the reference shows it and declare it: a dart open on the outline as darts [{piece, "
                    "legs: [edge, edge]}] (each leg 'outline point>tip'); a dart inside the piece (a fish dart, a dart "
                    "ending in a pocket mouth) as darts [{piece, inside: <its closed path>, release: [points..., outline "
                    "point]}]: never cut it open by hand, the tool cuts it through along release (through the pocket "
                    "mouth to the nearest seam, or straight to it) and sews it; or, if the reference shows no dart, back "
                    "to step 1") if miss else "",
            "back_to": "4", "source": "step 1's details vs the draft's darts (draft_darts_inv.py, C410)"}
