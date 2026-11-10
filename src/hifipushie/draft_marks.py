"""Garment step 4's flat gate, row `marks_placed` (C380): every detail mark placed on the flat pattern NOW, as step 7
will place it, and said where it lands.

Why (t s4-10): marks declared at step 4 were only checked for their FORM; where rows of frogging or a braid's path landed
was first computed at step 7 (garment_details), so a mark past an edge's end or outside its piece surfaced three steps
late, and the agent "couldn't confirm where they land". Here each mark goes through garment_details.place on the flat
mesh with a stand-in geometry (a 10 mm point, or a 10 mm strip for follows / path), the declarations as step 7 reads
them (the pairs expanded: garment_details_tool.declarations). A mark that can't be placed FAILs naming why; placed ones are listed with
garment_details' own words (edge, rows, pitch, spacing, strip lengths) and drawn on the sheet (`sheet_marks`).
"""
from __future__ import annotations

import numpy as np

STAND_IN_MM = 10.0


def _kind(mark) -> str:
    specs = mark if isinstance(mark, list) else [mark]
    if any(isinstance(s, dict) and (s.get("lines") or s.get("knots")) for s in specs):
        return "motif"
    return "line" if any(isinstance(s, dict) and (s.get("follows") or s.get("path")) for s in specs) else "point"


def place(M: dict, decl: dict, step1: dict) -> tuple[dict, dict]:
    """(row, {piece: [(kind, uv | polyline)]}) for every mark the declarations give, plus a closure's own marks."""
    from . import garment_details as gd, garment_details_tool as gdt
    det = (step1.get("details") or {})
    inv = {n: x for n, x in det.items() if x.get("build") in gdt.BUILT}
    mk = gdt.marks({"steps": {"1": {"output": step1}}}, M, decl)
    fl = gd.Flat(M, decl.get("edges") or {})
    bad, said, drawn = [], [], {}
    for n, m in mk.items():
        k = _kind(m)
        geom = {"kind": k, "size_mm": STAND_IN_MM} if k == "point" else {"kind": k, "width_mm": STAND_IN_MM}
        try:
            r = gd.place(fl, n, m, geom, inv.get(n, {}))
        except (gd.DetailRefused, KeyError, ValueError, IndexError) as e:
            bad.append(f"{n}: {e}")
            continue
        said.append(f"{n} ({r['count']}): " + " | ".join(r["where"]))
        for i in r["instances"]:
            drawn.setdefault(i["piece"], []).append(("point", i["uv"]) if i["kind"] == "point" else ("strip", i["C"]))
    row = {"id": "marks_placed", "status": "FAIL" if bad else ("PASS" if mk else "INFO"),
           "value": f"{len(mk) - len(bad)} of {len(mk)} details placed on the flat pattern",
           "target": "every detail's mark lands on its piece as step 7 will place it",
           "why": "; ".join(bad), "info": "; ".join(said), "back_to": "4",
           "fix": "move the mark (its edge, rows' from / pitch, a path's points) onto its piece" if bad else ""}
    return row, drawn


def sheet_marks(B: dict, drawn: dict) -> None:
    """Put the placed marks on B's pieces for the sheet: points as marks named detail:*, strips as lines detail:*."""
    for p, items in drawn.items():
        pc = (B.get("pieces") or {}).get(p)
        if pc is None:
            continue
        for j, (k, v) in enumerate(items):
            if k == "point":
                pc.setdefault("marks", {})[f"detail:{j}"] = np.asarray(v, float)
            else:
                pc.setdefault("lines", {})[f"detail:{j}"] = np.asarray(v, float)
