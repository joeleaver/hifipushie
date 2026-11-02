"""The draft_pattern tool body (garment step 4): the agent's FreeSewing design + declarations -> the flat pattern, the
flat gate, the record's step 4 and its look. draft_own.py holds the parts (Node run, declarations, converter, gate).

`run(name, garment, design, declarations, options, sa)` -> (sheet path | None, answer text). It reads steps 1 (pieces,
seams, closures) and 3 (measurements, by name) of the garment record (garment_record.READS), drafts in
<model>/garments/<garment>/draft/, validates, builds the pieces through cloth.pieces (pattern {"from": "own"}), meshes
them flat (cloth.mesh: the keys chain_garment reads), gates, draws the flat sheet with the seam pairs labelled, writes
the spec's garment entry (so pattern_check and chain_garment find it) and step 4.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import draft_own as do


def measurements(step3: dict) -> dict:
    """{name: number} from body_tape's rows (mm; an angle in degrees: FreeSewing's shoulderSlope)."""
    out = {}
    for r in step3.get("measurements") or []:
        v = r.get("mm", r.get("deg"))
        if v is not None:
            out[r["name"]] = float(v)
    return out


def _labels(B: dict, decl: dict) -> dict:
    """{piece: lines}: each seam's number at its edges, so the sheet shows which edge sews to which."""
    lab = {nm: [] for nm in B["pieces"]}
    for i, s in enumerate(decl.get("seams") or []):
        for side, other in (("a", "b"), ("b", "a")):
            for e in do._sides(s[side]):
                p, ed = e.split(":", 1)
                if p in lab:
                    lab[p].append(f"S{i + 1} {ed} > {', '.join(do._sides(s[other]))}"[:48])
    for nm, pd in (decl.get("pieces") or {}).items():
        if nm in lab:
            lab[nm].insert(0, f"cut {pd.get('cut', 1)}{' on fold' if pd.get('fold') else ''}"
                              f"{' stiff' if nm in (decl.get('stiff') or []) else ''}")
    return lab


def flat_check(name: str, garment: str) -> tuple[list, dict, dict]:
    """(rows, B, decl) of a garment drafted with draft_pattern: the general flat gate re-read from its saved draft."""
    from . import cloth, garment_record as gr, store
    g = store.load(name)["cloth"][garment]
    d = Path(g["pattern"]["dir"])
    decl = json.loads((d / "declarations.json").read_text())
    rd = gr.reads(name, garment, "4")
    B = cloth.pieces(json.loads(json.dumps(g)), measurements(rd["3"]))
    B["edge_arcs"] = do.block(g["pattern"])["edge_arcs"]
    return do.gate(B, decl, rd["1"]), B, decl


def check_text(name: str, garment: str) -> str:
    """pattern_check on a garment drafted with draft_pattern: the general flat gate re-read; step 4 rewritten."""
    from . import garment_record as gr
    rows, B, _ = flat_check(name, garment)
    v = do.verdict(rows)
    rec = gr._try(gr.write, name, garment, "4", "done" if v == "PASS" else "failed", by="pattern_check",
                  output=dict(gr.load(name, garment)["steps"]["4"].get("output") or {}, pieces=list(B["pieces"])),
                  gate={"verdict": v, "rows": rows}, look=gr.load(name, garment)["steps"]["4"].get("look"), back_to="4")
    lines = [f"{name}:{garment} pattern_check (own draft, the flat gate): {v}"]
    lines += [f"  {r['status']} {r['id']}: {r.get('value', '')}{' | ' + r['why'] if r.get('why') else ''}"[:600] for r in rows]
    lines.append(f"  {rec}" if rec else f"  record: step 4 written ({gr.path(name, garment)})")
    return "\n".join(lines) + ("\nnext: chain_garment" if v == "PASS" else "\nnext: fix the rows with draft_pattern")


def run(name: str, garment: str, design: str, declarations: dict, options: dict | None = None,
        sa: float = 10.0) -> tuple[str | None, str]:
    from . import chain_garment as cg, cloth, garment_record as gr, pattern_sheet, store
    if not isinstance(design, str) or "Design" not in design:
        raise do.DraftRefused("design: the FreeSewing design source (an ES module ending `export default new Design({...})`)")
    if not isinstance(declarations, dict):
        raise do.DraftRefused("declarations: {pieces, edges, seams, stiff, folds, closures, omit}: guide(topic=\"draft_pattern\")")
    rd = gr.reads(name, garment, "4")
    meas = measurements(rd["3"])
    d = gr.look_dir(name, garment) / "draft"
    draft = do.node_draft(design, meas, options, sa, d)
    bad = do.validate(declarations, rd["1"], draft["parts"])
    if bad:
        return None, ("draft_pattern REFUSED (nothing written):\n  " + "\n  ".join(bad[:20]) +
                      f"\n  draft parts: {', '.join(draft['parts'])}\nnext: fix the declarations (step 1's names) and call again")
    (d / "draft.json").write_text(json.dumps(draft))
    (d / "declarations.json").write_text(json.dumps(declarations, indent=1))
    (d / "options.json").write_text(json.dumps({"options": options or {}, "sa": sa}))
    g = {"pattern": {"from": "own", "dir": str(d)}}
    try:
        B = cloth.pieces(json.loads(json.dumps(g)), meas)
        M = cloth.mesh(B)
    except (KeyError, ValueError, IndexError) as e:
        raise do.DraftRefused(f"the converter refused the draft: {e}") from None
    B["edge_arcs"] = do.block(g["pattern"])["edge_arcs"]
    rows = do.gate(B, declarations, rd["1"])
    v = do.verdict(rows)
    seam_rows = next(r for r in rows if r["id"] == "seams")["detail"]
    im = pattern_sheet.render(B, f"{name}:{garment} draft_pattern (own design)", seam_rows=seam_rows,
                              labels=_labels(B, declarations), grid=True)
    sheet = gr.look_dir(name, garment) / "step4_flat.png"
    im.save(sheet)
    spec = store.load(name)
    cl = dict(spec.get("cloth") or {})
    cl[garment] = {"pattern": g["pattern"]}  # (a garment drafted afresh: no older design's keys ride along)
    spec["cloth"] = cl
    ver = store.save(name, spec, f"draft_pattern {garment}")
    keys = [k for k in cg.PATTERN_KEYS if k in M]
    out = {"dir": str(d), "pieces": list(B["pieces"]), "seams": len(B["seams"]), "measurements": sorted(meas),
           "mesh": {"vertices": int(len(M["uv"])), "faces": int(len(M["F"])), "keys": keys}}
    rec = gr._try(gr.write, name, garment, "4", "done" if v == "PASS" else "failed", output=out, by="draft_pattern",
                  gate={"verdict": v, "rows": rows}, look=[str(sheet)], back_to="4")
    lines = [f"{name}:{garment} draft_pattern: {v} (spec v{ver}; draft {d})",
             f"  pieces {len(B['pieces'])}: {', '.join(B['pieces'])}",
             f"  flat mesh: {out['mesh']['vertices']} vertices, {out['mesh']['faces']} faces; keys {', '.join(keys)}"]
    lines += [f"  {r['status']} {r['id']}: {r.get('value', '')}{' | ' + r['why'] if r.get('why') else ''}"[:600] for r in rows]
    lines.append(f"  look: {sheet}")
    lines.append(f"  {rec}" if rec else f"  record: step 4 written ({gr.path(name, garment)})")
    nxt = ("judge the flat sheet beside the reference (every piece, every seam pair labelled); then chain_garment"
           if v == "PASS" else "fix the failing rows in the design or the declarations and call again")
    return str(sheet), "\n".join(lines) + f"\nnext: {nxt}"
