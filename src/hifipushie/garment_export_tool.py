"""The export_garment tool body (step 10; garment_export.py is the method, garment_glb.py the file).

run(name, garment, wear, role, look) -> (look paths, text). Reads the record: step 9 approved (the hung garment), or,
internally, an approved 7a (the build: exported, but step 10 isn't written until 9 is ready: the text says so).
Writes <job>/export/<garment>.glb (the asset: garment + details, skinned), <garment>_LOD1.glb .. (lods: the same
re-grid, coarser; what the character's export takes at each LOD), <garment>_look.glb (+ the body, for the look only),
<garment>_export.json (the numbers), step 10 of the record with the look.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import garment_bend as gb, garment_details as gd, garment_export as ge, garment_game as gg, garment_glb as glbw
from . import garment_loops as gl, garment_record as gr

SKIN = [0.85, 0.69, 0.55]


def source(rec: dict, d: Path) -> tuple[Path, str]:
    """(pickle, what) for the export, or ExportRefused naming the record's next call."""
    s = gr.states(rec)
    hung, built = d / "final.pkl", d / "built.pkl"
    if s["9"]["ready"]:
        if hung.exists():
            return hung, "hung garment (step 9 approved)"
        if built.exists():
            return built, "build (step 9 approved; no hung garment)"
    elif s["7a"]["status"] == "approved" and not s["7a"]["stale"] and built.exists():
        return (hung, "hung garment (7a approved; step 9 not yet)") if hung.exists() else (built, "build (7a approved)")
    nx = gr.next_step(rec)
    raise ge.ExportRefused(f"{rec['model']}:{rec['garment']}: export (step 10) refused: step 9 (look) is not approved "
                           f"({s['9']['status']}{'; ' + s['9']['why'] if s['9']['why'] else ''}), nor 7a. "
                           f"next: step {nx['step']}: {nx['why']}; {nx['call']}")


def run(name: str, garment: str, wear: str = "open", role: str = ge.ROLE, look: bool = True) -> tuple[list, str]:
    from . import chain_garment as cg, store
    from . import rig_report
    rec = gr.load(name, garment)
    d = cg.job_dir(name, garment, wear)
    pkl, what = source(rec, d)
    budget = ge.budget_for(role)
    r = gd.load_result(pkl)
    spec = store.load(name)
    colour = ge.hex_rgb(((spec.get("cloth") or {}).get(garment) or {}).get("color"))
    bV, bT = np.asarray(r["bV"], float), np.asarray(r["bT"], np.int64)
    details = ge.details_of(d, pkl.name == "final.pkl")
    n_det = sum(len(x["F"]) for x in details.values())
    drape = ge.drape_of(r)
    rb = rig_report.rig_bones(spec)
    g, tries = ge.fit_budget(drape, r["M"], budget, n_det, body=bV, joints=gl.joint_lines(drape, rb))
    total = len(g["T"]) + n_det
    if total > budget:
        big = max(details, key=lambda k: len(details[k]["F"])) if details else None
        raise ge.ExportRefused(
            f"{name}:{garment}: export refused: {total} triangles over the {role} {ge.PART} budget {budget} at the coarsest "
            f"grid ({ge.H_MAX * 1000:.0f} mm; coarser loses the drape): garment {len(g['T'])}, details {n_det}"
            + (f" (most: {big} {len(details[big]['F'])})" if big else "") +
            ". next: a bigger role (role=\"hero\": " + str(ge.budget_for("hero")) + "), fewer pieces built in full "
            "(step 1: an occluded piece simplified or left out), or simpler details (step 7: fewer segments)")
    st = ge.uv_stretch(g["outer"])
    sd = ge.stretch(drape["V"], drape["uv"], drape["F"])
    o = g["outer"]
    gJ, gW, winfo = gb.skin(spec, rb, o["V"], o["T"], g["h"])
    bJ, bW, _ = gb.skin(spec, rb, bV, bT, 0.0, smooth=False)
    made = [i for i, n in enumerate(g["pieces"]) if n in set(r["M"].get("made") or [])]
    bend = gb.deformation(rb, o["V"], o["T"], gJ, gW, bV, bT, bJ, bW,
                          soft_faces=~np.isin(np.asarray(o["piece"])[np.asarray(o["T"])[:, 0]], made))
    J2, W2 = np.vstack([gJ, gJ]), np.vstack([gW, gW])  # (the inner faces share the outer's vertices' weights)
    gk = cKD(o["V"])
    meshes = [{"name": garment, "V": g["V"], "T": g["T"], "uv": g["uv"], "N": g["N"], "colour": colour, "J": J2, "W": W2}]
    for dn, x in details.items():
        k = gk.query(x["V"])[1]
        meshes.append({"name": f"{garment}_{dn}", "V": x["V"], "T": x["F"], "colour": ge.hex_rgb(x["colour"]),
                       "J": gJ[k], "W": gW[k], "roughness": 0.5})
    mat = materials(rec, meshes, garment)
    out = d / "export"
    glb = glbw.write(out / f"{garment}.glb", garment, meshes, rb)
    counts = glbw.read_counts(glb)
    lod_list, lod_lines = lods(garment, rec, role, spec, rb, drape, r["M"], bV, details, colour, g, out)
    lines = ge.text(name, garment, what, g, n_det, budget, role, tries, st, bend, glb, sd, winfo)
    lines.append("  " + mat)
    lines += lod_lines
    rows = ge.gate_rows(g, n_det, budget, st, bend, sd, lod_list)
    verdict = "PASS" if all(x["status"] in ("PASS", "INFO") for x in rows) else "FAIL"
    looks = []
    if look:
        looks = render_looks(name, garment, rec, meshes, rb, bV, bT, bJ, bW, out, [x["glb"] for x in lod_list])
        lines.append("  look (shape only): " + ", ".join(map(str, looks)) + (
            f"; the last sheet is the LOD files, LOD1 at the top to LOD{len(lod_list)} (front, three-quarter), the garment "
            "ALONE: its shape, holes and kinks (skin through a LOD's cloth is the character export's check: it cuts "
            "the covered skin away)" if lod_list else ""))
    numbers = {"glb": str(glb), "source": str(pkl), "role": role, "budget": budget, "triangles": total, "counts": counts,
               "grid_mm": round(g["h"] * 1000, 1), "tries": tries, "stretch": st, "drape_stretch": sd,
               "quad_share": o.get("quad_share"), "weights": winfo, "bend": {"limits": bend["limits"], "poses": bend["poses"]},
               "bones": len(rb), "lods": lod_list}
    ge.write_json(out / f"{garment}_export.json", numbers)
    msg = gr._try(gr.write, name, garment, "10", "done" if verdict == "PASS" else "failed", output=numbers,
                  gate={"verdict": verdict, "rows": rows}, look=looks, back_to=None if verdict == "PASS" else "10",
                  by="export_garment")
    lines.insert(1, f"  gate {verdict}: " + "; ".join(f"{x['id']} {x['status']}" for x in rows))
    lines.append(f"  {msg}" if msg else "  record: step 10 written")
    lines.append(next_line(name, role, verdict, len(lod_list), gr.states(rec)["9"]["ready"]))
    return looks, "\n".join(lines)


def next_line(name: str, role: str, verdict: str, n_lods: int, look_approved: bool) -> str:
    """What follows step 10: the look, what a FAIL row sends back, and the way onto the character (export_asset)."""
    onto = (f'export_asset("{name}", "<out_dir>", role="{role}", rig=True) puts this garment on its character AS THIS '
            f"FILE (LOD0) and its {n_lods} LOD file(s): never rebuilt, never decimated")
    if not look_approved:
        onto += "; it leaves the garment out until step 9 (the look) is approved"
    elif verdict != "PASS":
        onto += "; with this gate FAILED it ships with a WARNING naming the rows"
    fix = ("" if verdict == "PASS" else "a FAIL row names what to change: the role / pieces (triangles), the hang "
           "(stretch), the weights / the build (a bend row: its pose's close-up; the body's own crease is the body's), "
           "a LOD's open pattern edge (the pattern's outline there: this tool again after the fix); ")
    return f"next: look at it beside the reference (shape) and at the LOD sheet; {fix}then {onto}"


def lods(garment, rec, role, spec, rb, drape, M, bV, details, colour, lod0, out: Path) -> tuple[list, list]:
    """<garment>_LOD<k>.glb for every LOD of the role (garment_export.lod_plan) -> (entries for the record, text
    lines). The LOD0 method again on a coarser grid: fit_budget at the LOD's share of the
    budget, weights by garment_bend.skin on the LOD's own mesh, the pattern UVs and step 9a's maps; the details by
    garment_export.lod_details (small ones left out, the rest simplified and seated on the LOD's cloth)."""
    for old in list(out.glob(f"{garment}_LOD[0-9].glb")) + list(out.glob(f"{garment}_LOD[0-9].json")):
        old.unlink()  # (this tool's own files from a run before: a role with fewer LODs leaves none behind)
    joints = gl.joint_lines(drape, rb)
    size = float(np.linalg.norm(bV.max(0) - bV.min(0)))  # (the character's bounding sphere, about: its body's box diagonal)
    o0 = lod0["outer"]
    entries, lines = [], []
    for p in ge.lod_plan(role):
        k = p["lod"]
        px = p["screen"] * ge.SCREEN_PX / size
        det, dinfo = ge.lod_details(details, p["share"], px)
        n_det = sum(len(x["F"]) for x in det.values())
        g, tries = ge.fit_budget(drape, M, p["budget"], n_det, body=bV, h0=min(2 * lod0["h"], p["h_max"]), joints=joints,
                                 rows=p["rows"], h_max=p["h_max"])
        o = g["outer"]
        ge.seat_details(det, o0["V"], o0["T"], o["V"], o["T"])
        gJ, gW, _ = gb.skin(spec, rb, o["V"], o["T"], g["h"])
        meshes = [{"name": garment, "V": g["V"], "T": g["T"], "uv": g["uv"], "N": g["N"], "colour": colour,
                   "J": np.vstack([gJ, gJ]), "W": np.vstack([gW, gW])}]
        gk = cKD(o["V"])
        for dn, x in det.items():
            i = gk.query(x["V"])[1]
            meshes.append({"name": f"{garment}_{dn}", "V": x["V"], "T": x["F"], "colour": ge.hex_rgb(x["colour"]),
                           "J": gJ[i], "W": gW[i], "roughness": 0.5})
        materials(rec, meshes, garment)
        glb = glbw.write(out / f"{garment}_LOD{k}.glb", garment, meshes, rb)
        total = len(g["T"]) + n_det
        entries.append({"lod": k, "glb": str(glb), "share": p["share"], "budget": p["budget"], "triangles": total,
                        "counts": glbw.read_counts(glb), "grid_mm": round(g["h"] * 1000, 1), "rows": p["rows"],
                        "open_edges": int(g["missing_boundary_edges"]), "tries": tries, "details": dinfo})
        over = (f" OVER its share at the coarsest grid kept ({p['h_max'] * 1000:.0f} mm; information, not refused)"
                if total > p["budget"] else "")
        lines.append(f"  LOD{k}: {glb.name} {total} triangles / {p['budget']} ({p['share']:g} of the budget){over}: garment "
                     f"{len(g['T'])} at {g['h'] * 1000:.0f} mm, stiff pieces {p['rows']} row(s), open pattern edges "
                     f"{g['missing_boundary_edges']}; details at {p['screen']:g} of a {ge.SCREEN_PX} px screen: "
                     f"{ge.details_text(dinfo)}")
    if entries:
        lines.insert(0, f"  LODs: the same pattern re-grid, coarser (never a decimation of LOD0); a detail piece under "
                        f"{ge.DETAIL_MIN_PX:g} px at its LOD's switch size is left out, the others are simplified")
    return entries, lines


def materials(rec: dict, meshes: list, garment: str) -> str:
    """Step 9a's maps on the garment mesh and its detail materials (T14); without them, flat colours (said)."""
    ap = (rec["steps"].get("9a") or {}).get("output") or {}
    maps = ap.get("maps") or {}
    if not maps or not all(Path(p).exists() for p in maps.values()):
        return ("materials: FLAT colours (no appearance, step 9a); next: garment_appearance (it bakes the maps this "
                "export puts on the GLB; the record writes step 10 only after 9a)")
    meshes[0].update({"textures": maps, "alpha_cut": bool(ap.get("alpha_cut"))})
    for m in meshes[1:]:
        x = (ap.get("details") or {}).get(m["name"][len(garment) + 1:])
        if x:
            m.update({"colour": ge.hex_rgb(x.get("colour")), "metallic": x["metallic"], "roughness": x["roughness"]})
    return (f"materials: step 9a's maps ({ap.get('size')} px: base, metallic-roughness, normal; "
            f"{ap.get('texel_mm')} mm/texel) on the pattern UVs; details " +
            (", ".join(f"{k} {v['material']}" for k, v in (ap.get("details") or {}).items()) or "flat"))


def cKD(V):
    from scipy.spatial import cKDTree
    return cKDTree(V)


def render_looks(name, garment, rec, meshes, rb, bV, bT, bJ, bW, out: Path, lod_glbs=()) -> list:
    """The GLB with the body at rest (EEVEE: asset_export.preview, the game's view) beside the reference, then one close-up
    sheet per bend pose (garment_bend_look: shoulder + armpit, the elbow when bent; the bare body beside it), then the
    LOD files as one sheet (LOD1 at the top; front and three-quarter; the garment alone: under a coarse LOD the whole
    body shows through everywhere, which says nothing: the character's export cuts the covered skin away)."""
    from PIL import Image
    from . import resources
    from . import asset_export
    from . import garment_bend_look as gbl
    from .garment_details_tool import _ref, beside
    body = {"name": "body", "V": bV, "T": bT, "colour": SKIN, "J": bJ, "W": bW}
    G = np.vstack([m["V"] for m in meshes])
    fr = [(G.min(0) - 0.03).tolist(), (G.max(0) + 0.03).tolist()]  # the cameras frame the garment, not the body
    rest = glbw.write(out / f"{garment}_look.glb", garment, [body] + meshes, rb, frame=fr)
    lod_ims = []
    with resources.heavy(f"export_garment look {name}:{garment}", gb=4, gpu=True):
        im = asset_export.preview(rest, ["front", "side", "back", "three_quarter"], size=512)
        for f in lod_glbs:
            lod_ims.append(asset_export.preview(Path(f), ["front", "three_quarter"], size=384))
    p = out / f"{garment}_rest.png"
    im.save(p)
    ld = gr.look_dir(name, garment)
    shots = [beside(_ref(rec), [p], ld / "step10_rest.png")]
    for b in gbl.looks(rb, meshes, body, {}, out, f"{garment}_"):
        shots.append(beside(None, [b], ld / f"step10_{b.stem.split(garment + '_', 1)[-1]}.png"))
    if lod_ims:
        sheet = Image.new("RGB", (max(i.width for i in lod_ims), sum(i.height for i in lod_ims)), (255, 255, 255))
        y = 0
        for i in lod_ims:
            sheet.paste(i.convert("RGB"), (0, y))
            y += i.height
        sheet.save(ld / "step10_lods.png")
        shots.append(ld / "step10_lods.png")
    return shots
