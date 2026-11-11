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



def row_lines(r: dict) -> list:
    """A gate row as text: its value on the row's line, then EVERY reason on a line of its own, in full (C378, t s4-8:
    one line cut at 600 characters hid the collar row's `change:` from the agent, who had to guess the fix)."""
    out = [f"  {r['status']} {r['id']}: {r.get('value', '')}"]
    why = [w.strip() for w in str(r.get("why") or "").split("; ") if w.strip()]
    out += [f"      why: {w}" for w in why]
    out += [f"      info: {w.strip()}" for w in str(r.get("info") or "").split("; ") if w.strip()]  # (C380: was never shown)
    if r.get("status") == "FAIL" and r.get("fix") and r["fix"] not in str(r.get("why")):
        out.append(f"      fix: {r['fix']}")
    return out

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


def stand_ref(name: str, garment: str) -> dict | None:
    """draft_stand.reference from step 2's collar_top trace, placed on the model's body (its landmarks); None: no trace."""
    from . import chain_structure as cs, cloth, draft_stand, store
    plan = cs.load_plan(name, garment)
    if not any(t.get("what") == "collar_top" for t in ((plan or {}).get("style") or {}).get("traces") or []):
        return None
    try:
        at = cloth.Body(cloth.body_mesh(store.load(name))).at
    except (KeyError, ValueError, TypeError) as e:
        return {"why": f"the body's landmarks: {type(e).__name__}: {str(e)[:120]}"}
    ref = draft_stand.reference(plan, at)
    if ref and "why" not in ref and "hps.L" in at:
        try:
            from . import garment_record as gr
            ref["top_girth"] = draft_stand.girth_at(gr.reads(name, garment, "4")["3"], at, ref["h_side"])
        except (KeyError, ValueError, TypeError):
            pass
    return ref


def _body(name: str) -> dict | None:
    """{"V", "at"}: the model's body and its landmarks (draft_girths places the levels on it); None: no body."""
    from . import cloth, store
    try:
        b = cloth.Body(cloth.body_mesh(store.load(name)))
        return {"V": b.V, "T": b.T, "at": b.at}
    except (KeyError, ValueError, TypeError):
        return None


def _fit(name: str, garment: str) -> dict:
    """Step 0's fit ease {region: {ease_mm}} (the body_lengths row's ease; {} when step 0 has none)."""
    from . import garment_record as gr
    try:
        return ((gr.load(name, garment).get("steps") or {}).get("0") or {}).get("output", {}).get("fit") or {}
    except (KeyError, ValueError, OSError, AttributeError):
        return {}


def flat_check(name: str, garment: str) -> tuple[list, dict, dict]:
    """(rows, B, decl) of a garment drafted with draft_pattern: the general flat gate re-read from its saved draft."""
    from . import cloth, garment_record as gr, store
    g = store.load(name)["cloth"][garment]
    d = Path(g["pattern"]["dir"])
    decl = json.loads((d / "declarations.json").read_text())
    rd = gr.reads(name, garment, "4")
    B = cloth.pieces(json.loads(json.dumps(g)), measurements(rd["3"]))
    blk = do.block(g["pattern"])
    B["edge_arcs"], B["decl"] = blk["edge_arcs"], blk["decl"]
    B["darts"] = blk.get("darts") or []  # (C386: cloth.pieces drops them; the dart row and the length rows need them)
    rows = do.gate(B, blk["decl"], rd["1"], stand_ref(name, garment), rd["3"], _fit(name, garment),
                   _body(name), step2=rd.get("2"))
    from . import draft_marks
    rows.append(draft_marks.place(cloth.mesh(B), blk["decl"], rd["1"])[0])  # (C380: the pairs expanded, as step 7)
    from . import draft_links
    rows += draft_links.saved_rows(name, garment)  # (C395, C403: step 4 FAILs what step 5 refuses, the build's mesh)
    return rows, B, decl


def check_text(name: str, garment: str) -> str:
    """pattern_check on a garment drafted with draft_pattern: the general flat gate re-read; step 4 rewritten."""
    from . import garment_record as gr
    rows, B, _ = flat_check(name, garment)
    v = do.verdict(rows)
    rec = gr._try(gr.write, name, garment, "4", "done" if v == "PASS" else "failed", by="pattern_check",
                  output=dict(gr.load(name, garment)["steps"]["4"].get("output") or {}, pieces=list(B["pieces"])),
                  gate={"verdict": v, "rows": rows}, look=gr.load(name, garment)["steps"]["4"].get("look"), back_to="4")
    lines = [f"{name}:{garment} pattern_check (own draft, the flat gate): {v}"]
    lines += [ln for r in rows for ln in row_lines(r)]
    lines.append(f"  {rec}" if rec else f"  record: step 4 written ({gr.path(name, garment)})")
    return "\n".join(lines) + ("\nnext: chain_garment" if v == "PASS" else "\nnext: fix the rows with draft_pattern")


def option_errors(options: dict, cfg: dict) -> list:
    """Each given option against the design's own config (pattern_parts): a known name, inside its range. A pct option
    is a FRACTION here (FreeSewing's own unit: 4 % = 0.04) though its config reads in %: t s4-2 gave 4 and drafted a cap
    three times the size; a value outside [min, max] is refused with the fraction it would be."""
    bad = []
    for k, v in options.items():
        o = cfg.get(k)
        if o is None:
            bad.append(f"options.{k}: not an option of this design (pattern_parts(design) lists them)")
            continue
        if "constant" in o or not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        for unit, scale in (("pct", 100.0), ("deg", 1.0), ("mm", 1.0), ("count", 1.0)):
            if o.get(unit) is None:
                continue
            lo, hi = o.get("min"), o.get("max")
            if lo is not None and hi is not None and not lo / scale - 1e-9 <= v <= hi / scale + 1e-9:
                hint = (f" (a pct option is a fraction: {lo}..{hi} % = {lo / 100:g}..{hi / 100:g}; did you mean "
                        f"{v / 100:g}?)" if unit == "pct" else "")
                bad.append(f"options.{k} = {v}: outside its range {lo}..{hi} {unit}{hint}")
            break
    return bad


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
    from . import pattern_parts as pp  # (the design's FULL list, before drafting: a block without one crashes inside it)
    try:
        cfg_ = pp.inspect(design, meas, None, draft=False, d=d / "inspect")
        miss = list(cfg_.get("missing") or [])
    except pp.InspectRefused as e:
        raise do.DraftRefused(str(e)) from None
    if miss:
        raise do.DraftRefused(f"design.mjs needs measurements step 3 hasn't taken: {', '.join(miss)} (the design's own list, "
                              f"every part it drafts; have {', '.join(sorted(meas))}): measure them by name with body_tape "
                              "(step 3), then draft again. pattern_parts(design) lists what each part needs")
    obad = option_errors(options or {}, cfg_["config"].get("options") or {})  # (C362: a pct given in %: 3x the cap)
    if obad:
        raise do.DraftRefused("options refused (nothing drafted):\n  " + "\n  ".join(obad))
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
        nan = " (a NaN: a point with no value, or a curve between two points that coincide; pattern_parts(design, " \
              "part=...) names a part's points with no value)" if "nan" in str(e).lower() else ""
        raise do.DraftRefused(f"the converter refused the draft: {e}{nan}") from None
    blk = do.block(g["pattern"])
    B["edge_arcs"], B["decl"] = blk["edge_arcs"], blk["decl"]
    B["darts"] = blk.get("darts") or []  # (C386: cloth.pieces drops them; the dart row and the length rows need them)
    rows = do.gate(B, blk["decl"], rd["1"], stand_ref(name, garment), rd["3"], _fit(name, garment),
                   _body(name), step2=rd.get("2"))  # (expanded: C366)
    from . import draft_marks
    mrow, drawn = draft_marks.place(M, B["decl"], rd["1"])  # (C380: where every mark lands, as step 7 places it)
    rows.append(mrow)
    draft_marks.sheet_marks(B, drawn)
    v = do.verdict(rows)
    seam_rows = next(r for r in rows if r["id"] == "seams")["detail"]
    dx = B.get("decl") or declarations
    names = seam_names(dx) if len(dx.get("seams") or []) == len(B["seams"]) else None
    im = pattern_sheet.render(B, f"{name}:{garment} draft_pattern (own design)", grid=True, names=names)
    sheet = gr.look_dir(name, garment) / "step4_flat.png"
    im.save(sheet)
    spec = store.load(name)
    cl = dict(spec.get("cloth") or {})
    cl[garment] = {"pattern": g["pattern"]}  # (a garment drafted afresh: no older design's keys ride along)
    spec["cloth"] = cl
    ver = store.save(name, spec, f"draft_pattern {garment}")
    from . import draft_links  # (C395: step 4 FAILs what step 5 refuses, read on the build's own mesh of this draft)
    rows += draft_links.saved_rows(name, garment)
    v = do.verdict(rows)
    keys = [k for k in cg.PATTERN_KEYS if k in M]
    out = {"dir": str(d), "pieces": list(B["pieces"]), "seams": len(B["seams"]), "measurements": sorted(meas),
           "mesh": {"vertices": int(len(M["uv"])), "faces": int(len(M["F"])), "keys": keys}}
    from . import piece_start  # (F4: which step-3 measurements each piece's lengths come from: where it starts)
    out["piece_measurements"] = piece_start.piece_measurements(rd["1"], declarations, (cfg_.get("config") or {}).get("parts"),
                                                              list(B["pieces"]))
    rec = gr._try(gr.write, name, garment, "4", "done" if v == "PASS" else "failed", output=out, by="draft_pattern",
                  gate={"verdict": v, "rows": rows}, look=[str(sheet)], back_to="4")
    lines = [f"{name}:{garment} draft_pattern: {v} (spec v{ver}; draft {d})",
             f"  pieces {len(B['pieces'])}: {', '.join(B['pieces'])}",
             f"  flat mesh: {out['mesh']['vertices']} vertices, {out['mesh']['faces']} faces; keys {', '.join(keys)}"]
    lines += [ln for r in rows for ln in row_lines(r)]
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
