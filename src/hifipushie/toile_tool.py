"""garment_toile: STEP 4 of drape first, the TOILE (toile.py builds it, toile_style.py its opening and flaps,
toile_gate.py its rows and look). Reads the ready steps 0-3 of the garment record (garment_record.READS) and the agent's
DECLARATION; writes the toile's parts (toile.npz), its numbers (toile.json) and the look into the garment's look folder,
and step 4 (output, gate rows, look) into the record. Joe approves it as any step.

THE DECLARATION (what the garment has, said by the agent, never inferred from a garment's name; refused by name):
  parts      a list from PARTS: "sleeves", "opening", "lapel" (needs "opening"), "pad". The body is always built.
  hang_from  a step-0 fit level the garment hangs straight down from (a jacket from its hips), or "none"
  armhole    {"length_mm"}: the garment's armhole round the body (the arm-root loop is scaled about the shoulder point)
  sleeves    {"ease_mm": [top, wrist], "crown_mm", "hem": a step-0 height}
  opening    {"lap_mm", "edge": a step-2 trace (the over front's edge), "buttons": a step-2 row id (optional)}
  lapel      {"roll": a step-2 trace, "top": a step-2 trace, "width_mm" (optional: else as traced)}
  pad        {"thickness_mm"}
TODAY'S DRAFT ROUTE: draft_pattern (an agent-written FreeSewing design) no longer writes step 4; its flat gate is what
step 6 (cut and flatten, R3b) runs on the flattened pieces."""
from __future__ import annotations

import json
import time

import numpy as np

PARTS = ("sleeves", "opening", "lapel", "pad")
NEEDS = {"sleeves": ("ease_mm", "crown_mm", "hem"), "opening": ("lap_mm", "edge"), "lapel": ("roll", "top"),
         "pad": ("thickness_mm",)}
TAPES = ("neck", "chest", "armhole_front", "armhole_back", "shoulderToWrist", "wrist")
HEAVY_GB = 3.0  # the field (~2 M grid points x a few float64 copies) + the body's contact tree


class ToileRefused(ValueError):
    """A declaration or an earlier step the toile can't be built from (named)."""


def validate(decl: dict, s0: dict, s2: dict) -> list:
    """Every fault in the declaration, by name (empty: buildable)."""
    bad = []
    if not isinstance(decl, dict):
        return ["declarations: a dict (module doc)"]
    parts = decl.get("parts")
    if not isinstance(parts, list):
        bad.append(f"parts: a list from {', '.join(PARTS)} (the body is always built)")
        parts = []
    bad += [f"parts: {p!r} is not one of {', '.join(PARTS)}" for p in parts if p not in PARTS]
    fit = {k for k, v in (s0.get("fit") or {}).items() if isinstance(v, dict) and "level_z_m" in v}
    heights = set(s0.get("heights") or {})
    traces = {t["id"] for t in s2.get("traces") or []}
    rows = {r["id"] for r in s2.get("rows") or []}
    hf = decl.get("hang_from")
    if hf is None:
        bad.append(f"hang_from: missing: a step-0 fit level ({', '.join(sorted(fit))}) or \"none\"")
    elif hf != "none" and hf not in fit:
        bad.append(f"hang_from: {hf!r} is not a step-0 fit level ({', '.join(sorted(fit))}) or \"none\"")
    if not (decl.get("armhole") or {}).get("length_mm"):
        bad.append("armhole: missing {\"length_mm\"}: the garment's armhole round the body")
    if "hem" not in heights:
        bad.append("step 0 has no height \"hem\": the toile's length (garment_plan step read)")
    for p in parts:
        if p not in NEEDS:
            continue
        blk = decl.get(p)
        if not isinstance(blk, dict):
            bad.append(f"{p}: listed in parts but not declared: {{{', '.join(NEEDS[p])}}}")
            continue
        bad += [f"{p}.{k}: missing" for k in NEEDS[p] if blk.get(k) in (None, "")]
    if "lapel" in parts and "opening" not in parts:
        bad.append("lapel: needs \"opening\" in parts (a lapel turns back from the front's opening)")
    for p, k in (("opening", "edge"), ("lapel", "roll"), ("lapel", "top")):
        v = (decl.get(p) or {}).get(k) if p in parts else None
        if v and v not in traces:
            bad.append(f"{p}.{k}: {v!r} is not a step-2 trace ({', '.join(sorted(traces))})")
    b = (decl.get("opening") or {}).get("buttons") if "opening" in parts else None
    if b and b not in rows:
        bad.append(f"opening.buttons: {b!r} is not a step-2 row")
    h = (decl.get("sleeves") or {}).get("hem") if "sleeves" in parts else None
    if h and h not in heights:
        bad.append(f"sleeves.hem: {h!r} is not a step-0 height ({', '.join(sorted(heights))})")
    if "sleeves" in parts and len((decl.get("sleeves") or {}).get("ease_mm") or []) != 2:
        bad.append("sleeves.ease_mm: [top, wrist] in mm")
    return bad


def _tapes(s3: dict) -> dict:
    out = {}
    for m in s3.get("measurements") or []:
        P = m.get("path") or m.get("loop")
        if P:
            out[m["name"]] = np.asarray(P, float)
    return out


def _mapped(s0: dict, s2: dict, at: dict, centre=None) -> tuple:
    """Step 2's traces and row marks in model metres (x, z), placed on the body by step 2's body marks: by its HEIGHT
    marks only when step 1 gives the picture's centre column (a wrist's place across depends on the arm's pose, which
    the picture and the model needn't share: the wrists put the jacket's traces 5 cm wide), else by every mark."""
    from . import structure_outline as so
    views = s0.get("views") or []
    pl = {}
    for bm in s2.get("body_marks") or []:
        vi = int(bm.get("view", 0))
        if vi < len(views) and views[vi].get("view") in ("front", "back"):
            mk = {k: v for k, v in bm["at"].items() if k.endswith("_z")} if centre is not None else bm["at"]
            p = so.placement(views[vi], mk if len(mk) >= 2 else bm["at"], at)
            if centre is not None and len(mk) >= 2:
                p = dict(p, u0=float(centre), how=p["how"] + f"; centre column {centre} px (step 1)")
            pl[vi] = (p, views[vi]["view"])

    def xz(px, vi):
        p, view = pl[vi]
        ab = so.to_mm(px, p)
        return np.c_[(1 if view == "front" else -1) * ab[:, 0] / 1000, -ab[:, 1] / 1000]
    traces = {t["id"]: {"xz": xz(t["points"], int(t.get("view", 0))), "corners": t.get("corners") or [],
                        "what": t.get("what")} for t in s2.get("traces") or [] if int(t.get("view", 0)) in pl}
    marks = {r["id"]: xz(r["at"], int(r.get("view", 0))) for r in s2.get("rows") or []
             if r.get("at") and int(r.get("view", 0)) in pl and all(len(a) == 2 for a in r["at"])}
    view = pl[min(pl)][1] if pl else "front"
    return traces, marks, view, {k: v[0] for k, v in pl.items()}


def inputs(name: str, garment: str, decl: dict):
    """(toile.Inputs, body (V, T), reference picture, view, placements) from the record and the model."""
    from . import body_tape, cloth, garment_record as gr, store, tailor
    from .toile import Inputs
    rd = gr.reads(name, garment, "4")
    s0, s2, s3 = rd["0"], rd["2"], rd["3"]
    bad = validate(decl, s0, s2)
    tp = _tapes(s3)
    bad += [f"step 3 has no tape {n!r}: body_tape(name, garment=..., measurements=[{n!r}])" for n in TAPES if n not in tp]
    if bad:
        raise ToileRefused("refused: " + "; ".join(bad))
    b = cloth.body_mesh(store.load(name))
    V = np.asarray(b["V"], float)
    T = tailor.triangles(b["F"])
    at = body_tape.Tape(V, b["F"], b["J"]).R["at"]
    traces, marks, view, pl = _mapped(s0, s2, at, rd["1"].get("centre"))
    levels = {k: (float(v["level_z_m"]), float(v["garment_girth_mm"]) / 1000) for k, v in (s0.get("fit") or {}).items()
              if isinstance(v, dict) and "level_z_m" in v and "garment_girth_mm" in v}
    heights = {k: float(v["z_mm"]) / 1000 for k, v in (s0.get("heights") or {}).items() if isinstance(v, dict) and "z_mm" in v}
    ref = ((s0.get("views") or [{}])[0]).get("image")
    return Inputs(V=V, T=T, tapes=tp, levels=levels, heights=heights, decl=decl, traces=traces, marks=marks), ref, view, pl


def build(inp, log=print):
    from . import resources
    from .toile import Toile
    with resources.heavy("garment_toile", log=log, gb=HEAVY_GB):
        return Toile(inp, log=log).build()


def save(t, d) -> tuple:
    d.mkdir(parents=True, exist_ok=True)
    arrs = {}
    for k, (V, F) in t.meshes.items():
        arrs[f"{k}:V"], arrs[f"{k}:F"] = V, F
    arrs.update(cone_O=t.cone.O, cone_A=t.cone.A, cone_PS=t.cone.PS, cone_AL=t.cone.AL, armhole=t.armhole,
                shoulder_line=t.shoulder_line, sleeve_axis=t.CAX, sleeve_r=t.RAX, yc=t.yc)
    if getattr(t, "roll_line", None) is not None:
        arrs["roll_line"] = t.roll_line
    np.savez(d / "toile.npz", **arrs)
    (d / "toile.json").write_text(json.dumps(t.info, indent=1, default=float))
    return d / "toile.npz", d / "toile.json"


def answer_text(name, garment, v, rows, info, look, msg) -> str:
    lines = [f"{name}:{garment} step 4 TOILE: {v}"]
    for r in rows:
        lines.append(f"  {r['status']:4s} {r['id']}: {r.get('value')} ({r.get('target')}) {r.get('why') or ''}")
    for k in ("armhole", "sleeve", "hang", "pad", "opening", "lapel", "ease_k_mm"):
        if k in info:
            lines.append(f"  {k}: {json.dumps(info[k], default=float)}")
    lines.append(f"  look: {look}")
    if msg:
        lines.append(f"  record: {msg}")
    lines.append("next: " + ("judge the look beside the reference (shape only); Joe approves step 4 (garment_record shows the "
                             "approve command); then step 5 marks the seam lines" if v == "PASS" else
                             "each FAIL row says what to change: a declaration (armhole, ease, hang_from, a part) or an "
                             "earlier step (step 0's girth plan, step 2's traces); garment_toile again"))
    return "\n".join(lines)


def run(name: str, garment: str, declarations: dict, log=lambda *_: None):
    """(look sheet or None, text)."""
    from . import garment_record as gr, toile_gate
    if isinstance(declarations, str):
        declarations = json.loads(declarations)
    try:
        inp, ref, view, pl = inputs(name, garment, declarations)
    except (ToileRefused, gr.OrderRefused) as e:
        return None, f"{name}:{garment} step 4 (toile): {e}\nnext: fix what is named, garment_toile again"
    t0 = time.time()
    t = build(inp, log=log)
    rows = toile_gate.rows(t, view)
    v = toile_gate.verdict(rows)
    d = gr.look_dir(name, garment) / "toile"
    npz, js = save(t, d)
    traces3d = [np.c_[tr["xz"][:, 0], np.full(len(tr["xz"]), t.ys[0]), tr["xz"][:, 1]] for tr in inp.traces.values()]
    look = toile_gate.look(t, inp.V, inp.T, ref, d / "toile_sheet.png", traces3d)
    out = {"toile": str(npz), "numbers": str(js), "parts": sorted(t.meshes), "declarations": declarations,
           "girths_mm": {r["id"].split(":")[1]: r["value"] for r in rows if r["id"].startswith("girth:")},
           "placement": {str(k): {"mm_per_px": round(p["s"], 4), "how": p["how"], "residual_mm": p["residual_mm"]}
                         for k, p in pl.items()}, "seconds": round(time.time() - t0, 1)}
    msg = gr._try(gr.write, name, garment, "4", "done" if v == "PASS" else "failed", output=out,
                  gate={"verdict": v, "rows": rows}, look=[str(look)], back_to="4", by="garment_toile")
    return look, answer_text(name, garment, v, rows, t.info, look, msg)
