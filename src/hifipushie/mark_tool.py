"""garment_mark's record and look (mark.py has the step and its declaration): reads step 4's toile and steps 0-2
(garment_record.READS["5"]), marks, gates, draws, writes step 5."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .mark import MarkRefused, gate, mirrored, run_marks, seam_map, validate

PAL = [(70, 120, 200), (220, 140, 60), (90, 170, 90), (200, 80, 90), (150, 110, 190), (120, 190, 200), (200, 190, 80),
       (160, 120, 90), (100, 100, 160), (210, 150, 180), (110, 160, 140), (180, 180, 180)]


def load_toile(out4: dict):
    Z = np.load(out4["toile"])
    return Z, Z["toile:V"].astype(float), Z["toile:F"].astype(int)


def look(V, F, lab, names, pairs, free, ref, path):
    from .toile_geom import render, sheet
    cols = np.array([PAL[i % len(PAL)] for i in range(len(names))])[lab]
    lines = [(V[ch], (20, 20, 20), 2) for runs in pairs.values() for ch in runs]
    lines += [(V[ch], (120, 120, 120), 1) for runs in free.values() for ch in runs]
    lo, hi = V.min(0), V.max(0)
    box = ((lo[0] - 0.03, hi[0] + 0.03), (lo[2] - 0.04, hi[2] + 0.04))
    sbox = ((lo[1] - 0.12, hi[1] + 0.12), box[1])
    tiles = [render([(V, F, cols)], lines=lines, view=v, box=box if v in ("front", "back") else sbox)
             for v in ("front", "left", "back", "right")]
    sheet(tiles, ref, labels=["reference", "front (marks black)", "left", "back", "right"]).save(path)
    return path


def answer_text(name, garment, v, rows, look_path, msg) -> str:
    lines = [f"{name}:{garment} step 5 MARK: {v}"]
    for r in rows:
        lines.append(f"  {r['status']:4s} {r['id']}: {r.get('value')} ({r.get('target')}) {r.get('why') or ''}")
    lines.append(f"  look: {look_path}")
    if msg:
        lines.append(f"  record: {msg}")
    lines.append("next: " + ("judge the marks on the toile beside the reference (do the seams fall where the reference's "
                             "do); then garment_cut (step 6) cuts and flattens" if v == "PASS" else
                             "each FAIL row names the mark or the piece: move a line (its kind's parameters) or declare a "
                             "piece absent with why; garment_mark again"))
    return "\n".join(lines)


def run(name: str, garment: str, declarations: dict, log=lambda *_: None):
    """(look sheet or None, text)."""
    from . import garment_record as gr
    from .mark_lines import Lines
    if isinstance(declarations, str):
        declarations = json.loads(declarations)
    try:
        rd = gr.reads(name, garment, "5")
    except gr.OrderRefused as e:
        return None, f"{name}:{garment} step 5 (mark): {e}\nnext: finish the step named"
    s0, s1, s2, s4 = rd["0"], rd["1"], rd["2"], rd["4"]
    bad = validate(declarations, s1)
    if not s4.get("toile") or not Path(s4["toile"]).exists():
        bad.append("step 4 has no toile.npz: garment_toile first")
    if bad:
        return None, f"{name}:{garment} step 5 (mark) refused: " + "; ".join(bad) + "\nnext: fix what is named, garment_mark again"
    Z, V, F = load_toile(s4)
    lines = Lines(Z, s0.get("fit") or {}, s0.get("heights") or {}, s2.get("panels") or [])
    d = gr.look_dir(name, garment) / "mark"
    d.mkdir(parents=True, exist_ok=True)
    try:
        V, F, lab, names, rep = run_marks(V, F, mirrored(declarations["marks"]), lines, log=log)
    except MarkRefused as e:
        rows = [{"id": "separate", "status": "FAIL", "value": "refused", "target": "every mark cuts its region in two",
                 "why": str(e), "back_to": "5"}]
        msg = gr._try(gr.write, name, garment, "5", "failed", output={"refused": str(e), "declarations": declarations},
                      gate={"verdict": "FAIL", "rows": rows}, back_to="5", by="garment_mark")
        return None, answer_text(name, garment, "FAIL", rows, None, msg)
    got, miss, skipped, extra, pairs, free = seam_map(V, F, lab, names, s1, declarations)
    rows = gate(rep, names, lab, V, F, s1, declarations, got, miss, skipped, extra)
    from .mark_flap import gorge_row
    g = gorge_row(dict(Z))  # (the turned flap's gorge mark: the collar from the lapels, R3f-9)
    rows += [g] if g else []
    v = "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
    np.savez(d / "mark.npz", V=V, F=F, lab=lab, names=np.array(names))
    info = {"marks": rep, "pieces": names, "seams": got, "absent": declarations.get("absent") or {},
            "not_in_step1": extra, "declarations": declarations}
    (d / "mark.json").write_text(json.dumps(info, indent=1, default=float))
    ref = ((s0.get("views") or [{}])[0]).get("image")
    lp = look(V, F, lab, names, pairs, free, ref if ref and Path(ref).exists() else None, d / "mark_sheet.png")
    out = {"mark": str(d / "mark.npz"), "numbers": str(d / "mark.json"), "pieces": names, "seams": len(got),
           "absent": declarations.get("absent") or {}, "declarations": declarations}
    msg = gr._try(gr.write, name, garment, "5", "done" if v == "PASS" else "failed", output=out,
                  gate={"verdict": v, "rows": rows}, look=[str(lp)], back_to="5", by="garment_mark")
    return lp, answer_text(name, garment, v, rows, lp, msg)
