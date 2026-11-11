"""INVENTORY DARTS ARE DRAFTED (C410): a dart step 1 builds is an opened dart on the pattern, never only a mark.

Trial s4-21 (2026-11-10, the suit jacket): step 1 inventoried `front_dart.L/.R`, "front (fish) dart ... the forepart's
waist suppression", build full. The draft declared it as a MARK only (a line drawn on the front), so the forepart had no
shaping of its own, and every row passed: marks_placed counted it placed, and the darts row only checks darts that ARE
declared. A dart is shaping: cloth taken out between two legs that meet at a tip. A mark can't take cloth out.

The row: every step-1 detail that is a dart (its `kind` is "dart", or its name or `what` names one) and is built (full or
simplified) needs a drafted dart (declarations `darts [{piece, legs}]`) on each piece it is `on`. A dart that ends in
another detail (a pocket mouth) is still opened on the outline: the slit runs through that detail to a seam, its legs
declared toward the tip (draft_own's darts form, C361).
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
            "why": ("; ".join(miss[:6]) + ": a mark takes no cloth out, so the piece has no shaping there. change: open "
                    "the dart on the outline (its two legs from the outline to one tip, declared 'outline point>tip'; a "
                    "dart ending in a pocket mouth is slit through the pocket line to a seam) and declare it in darts "
                    "[{piece, legs}]; or, if the reference shows no dart, back to step 1") if miss else "",
            "back_to": "4", "source": "step 1's details vs the draft's darts (draft_darts_inv.py, C410)"}
