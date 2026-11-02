"""The export_garment tool body (step 10; garment_export.py is the method, garment_glb.py the file).

run(name, garment, wear, role, look) -> (look paths, text). Reads the record: step 9 approved (the hung garment), or,
internally, an approved 7a (the build: exported, but step 10 isn't written until 9 is ready: the text says so).
Writes <job>/export/<garment>.glb (the asset: garment + details, skinned), <garment>_look.glb (+ the body, for the
look only), <garment>_export.json (the numbers), step 10 of the record with the look.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import garment_details as gd, garment_export as ge, garment_game as gg, garment_glb as glbw, garment_record as gr

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
    from . import chain_garment as cg, rig, store
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
    g, tries = ge.fit_budget(drape, r["M"], budget, n_det, body=bV)
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
    rb = rig.rig_bones(spec)
    o = g["outer"]
    gJ, gW = ge.skin(spec, rb, o["V"], o["T"])
    bJ, bW = ge.skin(spec, rb, bV, bT)
    wc = ge.weight_check(rb, o["V"], gJ, gW, bV, bJ, bW)
    J2, W2 = np.vstack([gJ, gJ]), np.vstack([gW, gW])  # (the inner faces share the outer's vertices' weights)
    gk = cKD(o["V"])
    meshes = [{"name": garment, "V": g["V"], "T": g["T"], "uv": g["uv"], "N": g["N"], "colour": colour, "J": J2, "W": W2}]
    for dn, x in details.items():
        k = gk.query(x["V"])[1]
        meshes.append({"name": f"{garment}_{dn}", "V": x["V"], "T": x["F"], "colour": ge.hex_rgb(x["colour"]),
                       "J": gJ[k], "W": gW[k], "roughness": 0.5})
    out = d / "export"
    glb = glbw.write(out / f"{garment}.glb", garment, meshes, rb)
    counts = glbw.read_counts(glb)
    lines = ge.text(name, garment, what, g, n_det, budget, role, tries, st, wc, glb, sd)
    rows = ge.gate_rows(g, n_det, budget, st, wc, sd)
    verdict = "PASS" if all(x["status"] == "PASS" for x in rows) else "FAIL"
    looks = []
    if look:
        looks = render_looks(name, garment, rec, meshes, rb, bV, bT, bJ, bW, wc, out)
        lines.append("  look (shape only): " + ", ".join(map(str, looks)))
    numbers = {"glb": str(glb), "source": str(pkl), "role": role, "budget": budget, "triangles": total, "counts": counts,
               "grid_mm": round(g["h"] * 1000, 1), "tries": tries, "stretch": st, "drape_stretch": sd,
               "weights": {k: v for k, v in wc.items() if not k.startswith("posed")}, "bones": len(rb)}
    ge.write_json(out / f"{garment}_export.json", numbers)
    msg = gr._try(gr.write, name, garment, "10", "done" if verdict == "PASS" else "failed", output=numbers,
                  gate={"verdict": verdict, "rows": rows}, look=looks, back_to=None if verdict == "PASS" else "10",
                  by="export_garment")
    lines.insert(1, f"  gate {verdict}: " + "; ".join(f"{x['row']} {x['status']}" for x in rows))
    lines.append(f"  {msg}" if msg else "  record: step 10 written")
    lines.append("next: look at it beside the reference (shape); a FAIL row names what to change: the role / pieces "
                 "(triangles), the hang (stretch), the rig (weights)")
    return looks, "\n".join(lines)


def cKD(V):
    from scipy.spatial import cKDTree
    return cKDTree(V)


def render_looks(name, garment, rec, meshes, rb, bV, bT, bJ, bW, wc, out: Path) -> list:
    """The GLB with the body, rendered in EEVEE (asset.preview: the game's view), rest and the arm raised, beside the
    reference. One Blender run per GLB, under the heavy / GPU lock."""
    from . import asset, resources
    from .garment_details_tool import _ref, beside
    from . import rig
    body = {"name": "body", "V": bV, "T": bT, "colour": SKIN, "J": bJ, "W": bW}
    G = np.vstack([m["V"] for m in meshes])
    fr = [(G.min(0) - 0.03).tolist(), (G.max(0) + 0.03).tolist()]  # the cameras frame the garment, not the body
    rest = glbw.write(out / f"{garment}_look.glb", garment, [body] + meshes, rb, frame=fr)
    turn = {rb[ge.bone_index(rb, ge.ARM_BONE)]["name"]: ge.ARM_TURN}
    posed = [dict(m, V=rig.pose(rb, m["V"], m["J"], m["W"], turn)) for m in [body] + meshes]
    for m in posed:  # (smooth normals of the posed surface: the rest normals no longer apply)
        m["N"] = gg.normals(m["V"], np.asarray(m["T"]))
    P = np.vstack([m["V"] for m in posed[1:]])
    pose_glb = glbw.write(out / f"{garment}_look_arm.glb", garment, posed, None,
                          frame=[(P.min(0) - 0.03).tolist(), (P.max(0) + 0.03).tolist()])
    shots = []
    with resources.heavy(f"export_garment look {name}:{garment}", gb=4, gpu=True):
        for g_, tag, views in ((rest, "rest", ["front", "side", "back", "three_quarter"]), (pose_glb, "arm", ["front", "three_quarter"])):
            im = asset.preview(g_, views, size=512)
            p = out / f"{garment}_{tag}.png"
            im.save(p)
            shots.append(p)
    ld = gr.look_dir(name, garment)
    return [beside(_ref(rec), [shots[0]], ld / "step10_rest.png"), beside(None, [shots[1]], ld / "step10_arm.png")]
