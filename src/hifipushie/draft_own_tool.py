"""The draft_pattern tool body (garment step 4): the agent's FreeSewing design + declarations -> the flat pattern, the
flat gate, the record's step 4 and its look. draft_own.py holds the parts (Node run, declarations, converter, gate).

`run(name, garment, design, declarations, options, sa)` -> (sheet path | None, answer text). It reads steps 1 (pieces,
seams, closures) and 3 (measurements, by name) of the garment record (garment_record.READS), drafts in
<model>/garments/<garment>/draft/, validates, builds the pieces through cloth.pieces (pattern {"from": "own"}), meshes
them flat (cloth.mesh: the keys chain_garment reads), gates, draws the flat sheet (shape only: C288) and lists its
numbers in the text, writes
the spec's garment entry (so pattern_check and chain_garment find it) and step 4.
"""
from __future__ import annotations

import hashlib
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


def seam_names(decl: dict) -> list:
    """Each declared seam's name, both sides' edges as the declarations name them (the legend's and the text's)."""
    side = lambda x: x if isinstance(x, str) else " + ".join(x)
    return [f"{side(s['a'])} = {side(s['b'])}" for s in decl.get("seams") or []]


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
    # the draft's content in the spec: a redraft into the same dir is a new pattern, so chain_garment's job key changes
    dig = hashlib.sha1(b"".join((d / f).read_bytes() for f in ("draft.json", "declarations.json", "options.json"))).hexdigest()[:12]
    g = {"pattern": {"from": "own", "dir": str(d), "digest": dig}}
    try:
        B = cloth.pieces(json.loads(json.dumps(g)), meas)
        M = cloth.mesh(B)
    except (KeyError, ValueError, IndexError) as e:
        raise do.DraftRefused(f"the converter refused the draft: {e}") from None
    B["edge_arcs"] = do.block(g["pattern"])["edge_arcs"]
    rows = do.gate(B, declarations, rd["1"])
    v = do.verdict(rows)
    seam_rows = next(r for r in rows if r["id"] == "seams")["detail"]
    names = seam_names(declarations) if len(declarations.get("seams") or []) == len(B["seams"]) else None
    im = pattern_sheet.render(B, f"{name}:{garment} draft_pattern (own design)", grid=True, names=names)
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
    lines += ["  " + ln for ln in pattern_sheet.text_lines(B, seam_rows, names, declarations)]
    if im.info.get("names_off"):
        lines.append(f"  on the sheet without a name (too small to hold one): {', '.join(im.info['names_off'])}")
    lines.append(f"  look: {sheet} (shape only: outlines, grain, one colour per seam pair; every number is above)")
    lines.append(f"  {rec}" if rec else f"  record: step 4 written ({gr.path(name, garment)})")
    nxt = ("compare the sheet's SHAPES with the reference (is the band curved and which way, does the hem run straight "
           "or curve, are the pieces the reference's pieces); take every number from this text, never off the image; "
           "then chain_garment"
           if v == "PASS" else "fix the failing rows in the design or the declarations (a shape row says what to change; "
           "for a role a FreeSewing design in the pack already drafts: collar stand, collar, cuff, two-piece sleeve, "
           "extend that part with `from:` and its options instead of drawing one) and call again")
    return str(sheet), "\n".join(lines) + f"\nnext: {nxt}"
