"""The garment_appearance tool body (step 9a; garment_appearance.py is the method).

run(name, garment, appearance, wear, role, look) -> (look paths, text). Reads the record: step 0's cloth readings
(colour, print, grain), step 1's pieces (each piece's cloth) and details, step 2's `appearance` block (the argument
overrides it: validated the same way), the build / hung garment export_garment would export (step 9 approved, or an
approved 7a internally). Writes <job>/appearance/<garment>_{base,mr,normal}.png (the role's texture size: budgets.json),
<garment>_appearance.json (the numbers) and step 9a of the record; export_garment then puts these maps on its GLB.
The look: the garment textured, rendered in EEVEE (asset.preview: the game's view) with the body, beside the
reference, plus a close-up and the texture sheet; every number in the text.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from . import garment_appearance as ga, garment_details as gd, garment_export as ge, garment_record as gr


def plan_of(rec: dict, appearance: dict | None) -> tuple[dict, dict, dict, list, str]:
    """(cloths, cloth_of piece, plan, detail names, where the plan came from); refused by name when it doesn't check."""
    st = rec["steps"]
    cloths = ((st.get("0") or {}).get("output") or {}).get("cloth") or {}
    parts = ((st.get("1") or {}).get("output") or {})
    pieces, details = parts.get("pieces") or {}, list((parts.get("details") or {}).keys())
    src = "argument" if appearance is not None else "step 2"
    plan = appearance if appearance is not None else (((st.get("2") or {}).get("output") or {}).get("appearance") or {})
    if not plan:
        src = "restrained defaults (no appearance block in step 2)"
    bad = ga.check_plan(plan, list(cloths), details)
    if bad:
        raise ga.AppearanceRefused(f"{rec['model']}:{rec['garment']}: appearance refused ({src}):\n  " + "\n  ".join(bad)
                                   + "\nnext: fix the block (garment_plan step 2's appearance, or the argument)")
    cloth_of = {p: v.get("cloth") for p, v in pieces.items() if v.get("cloth") in cloths}
    return cloths, cloth_of, plan, details, src


def save_maps(tex: dict, out: Path, garment: str) -> dict:
    from PIL import Image
    out.mkdir(parents=True, exist_ok=True)
    paths = {"base": out / f"{garment}_base.png", "mr": out / f"{garment}_mr.png", "normal": out / f"{garment}_normal.png"}
    Image.fromarray(tex["base"], "RGBA").save(paths["base"])
    mr = np.zeros(tex["base"].shape[:2] + (3,), np.uint8)
    mr[..., 1] = tex["rough"]  # (glTF: G = roughness, B = metallic: cloth 0)
    Image.fromarray(mr, "RGB").save(paths["mr"])
    Image.fromarray(tex["normal"], "RGB").save(paths["normal"])
    return {k: str(v) for k, v in paths.items()}


def vertex_normals(V, F):
    n = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(n, F[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def run(name: str, garment: str, appearance: dict | None = None, wear: str = "open", role: str = ge.ROLE,
        look: bool = True) -> tuple[list, str]:
    from . import chain_garment as cg, garment_export_tool as get, rig, store
    rec = gr.load(name, garment)
    d = cg.job_dir(name, garment, wear)
    pkl, what = get.source(rec, d)
    cloths, cloth_of, plan, details, src = plan_of(rec, appearance)
    r = gd.load_result(pkl)
    drape = ge.drape_of(r)
    fallback = Counter(cloth_of.values()).most_common(1)[0][0] if cloth_of else next(iter(cloths), None)
    unnamed = [n for n in drape["names"] if n not in cloth_of]
    cmap = {n: cloth_of.get(n, fallback) for n in drape["names"]}
    spec = store.load(name)
    rb = rig.rig_bones(spec)
    wear_v = {c: ga.high_point_wear(drape, r.get("bV"), rb, a.get("where") or [])
              for c, a in plan.items() if c != "details" and isinstance(a, dict) and a.get("wear", 0) > 0}
    size = ga.texture_size(role)
    tex = ga.bake(drape, cmap, cloths, plan, dict((r["M"].get("grain") or {})), size, wear_v)
    out = d / "appearance"
    maps = save_maps(tex, out, garment)
    det = {dn: ga.detail_material(dn, plan, x["colour"]) for dn, x in ge.details_of(d, pkl.name == "final.pkl").items()}
    numbers = {"source": str(pkl), "plan_from": src, "role": role, "size": size, "texel_mm": round(tex["texel_mm"], 3),
               "atlas_side_m": round(tex["side_m"], 3), "maps": maps, "alpha_cut": tex["alpha_cut"], "layers": tex["layers"],
               "pieces_cloth": cmap, "cloth_by_default": unnamed, "details": det, "plan": plan}
    (out / f"{garment}_appearance.json").write_text(json.dumps(numbers, indent=1, default=str))
    looks = render_look(name, garment, rec, drape, r, rb, maps, tex, det, d, out) if look else []
    msg = gr._try(gr.write, name, garment, "9a", "done", output=numbers, look=looks, by="garment_appearance")
    return looks, "\n".join(text(name, garment, what, numbers, looks, msg))


def text(name, garment, what, n, looks, msg) -> list[str]:
    L = [f"{name}:{garment}: appearance (step 9a) on the {what}: {n['size']} px maps ({n['role']} clothing set), "
         f"{n['texel_mm']:.2f} mm/texel over a {n['atlas_side_m']:.2f} m pattern square; plan: {n['plan_from']}"]
    for x in n["layers"]:
        p = x.get("print")
        s = x.get("stitch") or {}
        w = x.get("wear") or {}
        sf = x["surface"]
        L.append(f"  {x['cloth']} ({x['fabric'] or 'plain'}; colour {x['colour']}; pieces {', '.join(x['pieces'])}):")
        L.append(f"    variation {x['variation']['amount']} at {x['variation']['scale_mm']:.0f} mm; "
                 + (f"print {p['kind']} {p['repeat_mm']:.0f} mm repeat ({p['repeat_px']} px), lines {p['line_mm']} mm, on the grain"
                    if p else "no print"))
        L.append(f"    surface {sf['kind']} {sf['period_mm']} mm: " + (f"DROPPED ({sf['dropped']})" if sf.get("dropped")
                                                                       else f"{sf['period_px']} px (normal map)"))
        if s:
            L.append(f"    stitch on {s['edges']}: {s['length_mm']} mm stitches, {s['offset_mm']} mm in, thread {s['colour']}")
        L.append(f"    wear {w.get('amount')} (edges {w.get('edges')}; at {w.get('where') or 'none'}; why: {w.get('why') or '-'}): "
                 f"{w.get('worn_texels_pct')} % of texels touched" + (f"; fray {x['fray']}" if x.get("fray") else ""))
    if n["cloth_by_default"]:
        L.append(f"  pieces not in step 1 (given the main cloth): {', '.join(n['cloth_by_default'])}")
    L.append("  details: " + ("; ".join(f"{k} {v['material']} (metallic {v['metallic']}, rough {v['roughness']})"
                                       for k, v in n["details"].items()) or "none"))
    L.append("  maps: " + ", ".join(n["maps"].values()))
    if looks:
        L.append("  look (EEVEE, beside the reference): " + ", ".join(map(str, looks)))
    L.append(f"  {msg}" if msg else "  record: step 9a written")
    L.append("next: judge it beside the reference at full size (the print on each piece's grain, meeting at the seams; "
             "the wear restrained); a wrong colour / print goes back to step 0, an amount to step 2's appearance; then "
             "export_garment (it puts these maps on the GLB)")
    return L


def render_look(name, garment, rec, drape, r, rb, maps, tex, det, d, out) -> list:
    """The garment textured + the body (EEVEE), beside the reference: four views, a chest close-up, the sheet."""
    from PIL import Image
    from . import asset, garment_glb as glbw, resources
    from .garment_details_tool import _ref, beside
    from .garment_export_tool import SKIN
    lay = ga.layout(drape)
    A = np.zeros_like(drape["uv"])
    for i, n in enumerate(drape["names"]):
        m = drape["piece"] == i
        if m.any():
            A[m] = ga.atlas_uv(lay, n, drape["uv"][m])
    V = drape["V"]
    meshes = [{"name": garment, "V": V, "T": drape["F"], "uv": A, "N": vertex_normals(V, drape["F"]), "textures": maps,
               "double_sided": True, "alpha_cut": tex["alpha_cut"]}]
    for dn, x in ge.details_of(d, False).items():
        mt = det.get(dn) or {}
        meshes.append({"name": f"{garment}_{dn}", "V": x["V"], "T": x["F"], "colour": ge.hex_rgb(mt.get("colour")),
                       "metallic": mt.get("metallic", 0.0), "roughness": mt.get("roughness", 0.5)})
    bV, bT = np.asarray(r["bV"], float), np.asarray(r["bT"], np.int64)
    fr = [(V.min(0) - 0.03).tolist(), (V.max(0) + 0.03).tolist()]
    glb = glbw.write(out / f"{garment}_appearance_look.glb", garment, [{"name": "body", "V": bV, "T": bT, "colour": SKIN}] + meshes,
                     None, frame=fr)
    c = (V.min(0) + V.max(0)) / 2
    top = V[:, 2].max()
    chest = [float(c[0]), float(V[:, 1].min()), float(top - 0.22 * (top - V[:, 2].min()))]
    cam = [{"eye": [chest[0] - 0.05, chest[1] - 0.45, chest[2] + 0.02], "target": chest, "fov": 40}]
    with resources.heavy(f"garment_appearance look {name}:{garment}", gb=4, gpu=True):
        im = asset.preview(glb, ["front", "side", "back", "three_quarter"], size=768)
        cu = asset.preview(glb, [], size=1024, cameras=cam)
    p1, p2 = out / f"{garment}_appearance_views.png", out / f"{garment}_appearance_close.png"
    im.save(p1); cu.save(p2)
    sheet = Image.fromarray(tex["base"][..., :3]).resize((1024, 1024))
    p3 = out / f"{garment}_appearance_sheet.png"
    sheet.save(p3)
    ld = gr.look_dir(name, garment)
    ref = _ref(rec)
    return [beside(ref, [p1], ld / "step9a_views.png"), beside(ref, [p2], ld / "step9a_close.png"),
            beside(ref, [p3], ld / "step9a_sheet.png")]
