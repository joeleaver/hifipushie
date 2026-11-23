"""Texture repaint: the steps (the MCP tools in tools_texrepaint.py call these). A model lives in
`<HIFIPUSHIE_HOME>/texrepaint/<name>/` (or any folder given as `name` with a "/"):
  model.glb, surface.npz/json, maps/<image>.png      the model, its triangles, the generated maps        (start)
  turnaround.*, concept.*, register.json, sheet_register.jpg, palette.json                               (start)
  materials.json, fields.npz, regions.json, sheet_regions.jpg                                            (regions)
  <image>_4k.png, <image>_normal_4k.png, <image>_rough_4k.png, <image>_labels.png, sheet_paint.jpg       (paint)
  render_<before|after>_<view>.png, sheet_render.jpg                                                     (render)
  decals.json, decal_<name>.png, sheet_decal_<name>.jpg                                                   (decal)
Order: start -> regions (name the materials from the palette, read the regions, judge the contradictions) -> paint
-> decal (graphics: signs, numbers, labels) -> render (before / after beside the turnaround)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from . import texrepaint_concept as C, texrepaint_regions as Rg
from .texrepaint_surface import Grid, Surface, View, dump, folder

ANALYSIS_RES = 2048


def _need(d: Path, *files):
    for f in files:
        if not (d / f).exists():
            raise ValueError(f"{d.name}: {f} is missing; run the step that makes it first (guide(topic=\"texrepaint\"))")


def _rgb(p) -> np.ndarray:
    return np.array(Image.open(p).convert("RGB"))


def _keep(surf: Surface):
    """triangles that occlude in views: everything but LOD copies"""
    return np.array(["lod" not in surf.meta["objects"][o].lower() or "lod0" in surf.meta["objects"][o].lower()
                     for o in surf.obj])


def _state(d):
    return json.loads((d / "state.json").read_text())


def start(name, glb, turnaround, concept=None, image=None, cover=None, invented=None, views=("front", "side", "back"),
          k=8):
    d = folder(name); d.mkdir(parents=True, exist_ok=True)
    shutil.copy(glb, d / "model.glb")
    t = Path(turnaround); shutil.copy(t, d / ("turnaround" + t.suffix.lower()))
    if concept:
        c = Path(concept); shutil.copy(c, d / ("concept" + c.suffix.lower()))
    meta = dump(d / "model.glb", d); surf = Surface.load(d)
    img = meta["images"][surf.image_index(image)]
    st = {"image": img, "turnaround": str(d / ("turnaround" + t.suffix.lower())), "views": list(views),
          "normal": meta["normal_of"].get(img)}
    for key, p in (("cover", cover), ("invented", invented)):
        if p:
            shutil.copy(p, d / f"mask_{key}.png"); st[key] = str(d / f"mask_{key}.png")
    lo, hi = surf.bounds(); st["height"] = float(hi[2] - lo[2])
    tx = surf.texels(img, 1024)
    tex = _rgb(d / "maps" / f"{img}.png")
    col, w, per, regs = C.project(C.panels_from(st["turnaround"], views), surf, tx, _ppm(st), keep=_keep(surf),
                                  image_index=surf.image_index(img), tex=tex)
    st["register"] = {p.view: {"k": p.k, "t": p.t, "colour_error": round(-p.iou, 1)} for p in regs}
    st["seen_by_art"] = round(float((w > 0.05).mean()), 3)
    (d / "state.json").write_text(json.dumps(st, indent=1))
    Image.fromarray(C.overlay(regs)).save(d / "sheet_register.jpg", quality=88)
    pal = C.palette(col[w > 0.3], k)
    (d / "palette.json").write_text(json.dumps(pal, indent=1))
    sw = np.zeros((60, 60 * len(pal), 3), np.uint8)
    for i, e in enumerate(pal):
        sw[:, i * 60:(i + 1) * 60] = e["colour"]
    Image.fromarray(sw).save(d / "palette.png")
    return st, pal


def _ppm(st):
    return 700.0 / max(st["height"], 1e-3)


def _panels(d, st, surf):
    ps = C.panels_from(st["turnaround"], st["views"])
    for p in ps:
        r = st["register"][p.view]; p.k, p.t = r["k"], tuple(r["t"])
    return ps


def _project_fixed(panels, surf, tx, ppm, keep, edge_px=6):
    """projection with the registration start found (no search)"""
    from scipy import ndimage
    n = len(tx.idx); acc = np.zeros((n, 3), np.float32); wsum = np.zeros(n, np.float32)
    occ = C._sub(surf, keep)
    for p in panels:
        v = View(p.view, occ, ppm, *surf.bounds())
        vis, cos, xy = v.visible(tx.pos, tx.nrm)
        inner = ndimage.distance_transform_edt(v.silhouette()) > edge_px
        xi = np.clip(xy[:, 0].astype(int), 0, v.W - 1); yi = np.clip(xy[:, 1].astype(int), 0, v.H - 1)
        cx = p.k * xy[:, 0] + p.t[0]; cy = p.k * xy[:, 1] + p.t[1]; H, W = p.img.shape[:2]
        ok = vis & inner[yi, xi] & (cx >= 0) & (cy >= 0) & (cx < W - 1) & (cy < H - 1)
        col = np.stack([ndimage.map_coordinates(p.img[..., c].astype(np.float32), [cy[ok], cx[ok]], order=1)
                        for c in range(3)], 1)
        w = np.zeros(n, np.float32); w[ok] = np.clip(cos[ok], 0, 1) ** 2
        acc[ok] += col * w[ok, None]; wsum += w
    return acc / np.maximum(wsum, 1e-6)[:, None], wsum


def _trust(st, tx):
    t = np.ones(len(tx.idx), np.float32)
    if st.get("cover"):
        t *= tx.sample(np.array(Image.open(st["cover"]).convert("L"), np.float32) / 255)
    if st.get("invented"):
        t *= 1 - tx.sample(np.array(Image.open(st["invented"]).convert("L"), np.float32) / 255)
    return np.clip(t, 0, 1)


def regions(name, materials, sigma=None, authority=3.0, min_area_cm2=2.0, fix_area_cm2=20.0):
    d = folder(name); _need(d, "state.json"); st = _state(d); surf = Surface.load(d)
    for m in materials:
        if "name" not in m or "colour" not in m:
            raise ValueError("materials: each needs a name and a colour [r, g, b] (0-255), sampled from the concept")
    (d / "materials.json").write_text(json.dumps(materials, indent=1))
    tx = surf.texels(st["image"], ANALYSIS_RES)
    tex = tx.sample(_rgb(d / "maps" / f"{st['image']}.png"))
    con, w = _project_fixed(_panels(d, st, surf), surf, tx, _ppm(st), _keep(surf))
    sigma = sigma or 0.005 * st["height"]
    area = Rg.texel_area(surf, tx)
    R = Rg.fuse(tx, tex, con, w, materials, sigma, sigma * 0.7, trust=_trust(st, tx), authority=authority,
                min_area=min_area_cm2 * 1e-4, area=area, fix_area=fix_area_cm2 * 1e-4, surf=surf)
    g: Grid = R["grid"]
    fields = []
    for k in range(len(materials)):   # the final reading as smooth 3D fields: paint evaluates them at any res
        a, nn = g.splat(R["P"][:, k])
        fields.append(a)
    _, n = g.splat(np.ones(len(tx.idx), np.float32))
    np.savez_compressed(d / "fields.npz", F=np.array(fields, np.float16), N=n.astype(np.float16), lo=g.lo, h=g.h,
                        sigma=sigma)
    summ = Rg.summary(tx, R, materials, area)
    rep = {"summary": summ, "contradictions": R["contradictions"], "sigma_m": sigma}
    (d / "regions.json").write_text(json.dumps(rep, indent=1))
    _np_save_labels(d, tx, R, materials, con, w)
    sheet = views_sheet(d, surf, st, [("texture", d / "maps" / f"{st['image']}.png"),
                                      ("texture read", d / "labels_texture.png"),
                                      ("concept read", d / "labels_concept.png"), ("regions", d / "labels_final.png")],
                        mark=R["disagree"], tx=tx)
    Image.fromarray(sheet).save(d / "sheet_regions.jpg", quality=85)
    return rep


def _np_save_labels(d, tx, R, materials, con, w):
    pal = np.array([m["colour"] for m in materials] + [[0, 0, 0]], np.uint8)
    tl = R["Pt"].argmax(1); cl = np.where(w > 0.05, R["Pc"].argmax(1), len(materials)); fl = R["P"].argmax(1)
    for tag, lab_ in (("texture", tl), ("concept", cl), ("final", fl)):
        Image.fromarray(tx.image(pal[lab_], 0)).save(d / f"labels_{tag}.png")


def views_sheet(d, surf, st, images, mark=None, tx=None, size=300):
    """front / side / back of the model coloured by each UV image (numpy, no Blender), with the turnaround panel
    first: rows = views, columns = concept, then each image. mark: texels to outline in red (contradictions)."""
    keep = _keep(surf); occ = C._sub(surf, keep); idx = surf.image_index(st["image"])
    panels = _panels(d, st, surf); rows = []
    marked = None
    if mark is not None and tx is not None:
        marked = tx.image(mark.astype(np.uint8), 0)
    for p in panels:
        v = View(p.view, occ, size / max(st["height"], 1e-3) * 0.9, *surf.bounds())
        x0, y0 = p.t; x1 = x0 + p.k * v.W * (_ppm(st) / v.ppm); y1 = y0 + p.k * v.H * (_ppm(st) / v.ppm)
        crop = Image.fromarray(p.img).crop((int(x0), int(y0), int(x1), int(y1))).resize((v.W, v.H))
        cells = [np.array(crop)]
        for _, path in images:
            im = _rgb(path) if not isinstance(path, np.ndarray) else path
            r, c, rgb = v.textured(idx, im, step=1)
            out = np.full((v.H, v.W, 3), 105, np.uint8); out[r, c] = rgb
            if marked is not None:
                r2, c2, mk = v.textured(idx, np.repeat(marked[..., None] * 255, 3, -1), step=1)
                edge = np.zeros((v.H, v.W), bool); edge[r2, c2] = mk[:, 0] > 0
                from scipy import ndimage
                ring = ndimage.binary_dilation(edge, iterations=2) & ~edge
                out[ring] = (255, 0, 0)
            cells.append(out)
        rows.append(np.concatenate(cells, 1))
    W = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, W - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    return np.concatenate(rows, 0)


SHEET_PX = 300   # views_sheet / look scale: px per model height / 0.9


def view_at(surf, st, view):
    occ = C._sub(surf, _keep(surf))
    return View(view, occ, SHEET_PX / max(st["height"], 1e-3) * 0.9, *surf.bounds())


def point_from_px(surf, st, view, px):
    """a pixel of a look / sheet cell (that view, SHEET_PX scale) -> the 3D surface point under it (depth buffer)"""
    v = view_at(surf, st, view); x, y = int(px[0]), int(px[1])
    win = v.depth[max(y - 2, 0):y + 3, max(x - 2, 0):x + 3]
    if not np.isfinite(win).any():
        raise ValueError(f"keep: pixel {px} in the {view} view is off the model")
    dep = float(np.nanmin(np.where(np.isfinite(win), win, np.nan)))
    pt = v.right * ((x + 0.5) / v.ppm + v.r0) - v.toward * dep
    pt[2] = v.z1 - (y + 0.5) / v.ppm
    return pt, v.toward


def look(name, view="front", crop=None, image=None):
    """a gridded view of the model with a map (default the generated one; "after" = the 4K repaint): grid every 10 px
    (red every 50) in the SAME pixels keep / decal points use. crop [x0, y0, x1, y1] zooms (x3)."""
    from PIL import ImageDraw
    d = folder(name); st = _state(d); surf = Surface.load(d); v = view_at(surf, st, view)
    src = st["painted"]["colour"] if image == "after" else (image or d / "maps" / f"{st['image']}.png")
    im_ = _rgb(src)
    r, c, rgb = v.textured(surf.image_index(st["image"]), im_, step=1)
    out = np.full((v.H, v.W, 3), 105, np.uint8); out[r, c] = rgb
    x0, y0, x1, y1 = crop or (0, 0, v.W, v.H); z = 3 if crop else 2
    im = Image.fromarray(out).resize((v.W * z, v.H * z), Image.LANCZOS); dr = ImageDraw.Draw(im)
    for x in range(0, v.W, 10):
        dr.line([(x * z, 0), (x * z, v.H * z)], fill=(255, 0, 0) if x % 50 == 0 else (0, 200, 255))
    for y in range(0, v.H, 10):
        dr.line([(0, y * z), (v.W * z, y * z)], fill=(255, 0, 0) if y % 50 == 0 else (0, 200, 255))
    im = im.crop((x0 * z, y0 * z, x1 * z, y1 * z)); p = d / f"look_{view}_{'after' if image == 'after' else 'before'}.jpg"
    im.save(p, quality=86)
    return p, {"view": view, "size_px": [v.W, v.H], "px_per_m": round(v.ppm, 1), "crop": [x0, y0, x1, y1]}


def _keep_weight(tx, surf, st, keep):
    """per texel: how much of the generated texture to keep (painted details: eyes, nostrils, a mouth line)"""
    w = np.zeros(len(tx.idx), np.float32); made = []
    for k in keep or []:
        if "at" in k:
            c = np.array(k["at"], np.float32); toward = None
        else:
            c, toward = point_from_px(surf, st, k.get("view", "front"), k["px"])
        r = float(k.get("r", 0.02)); dist = np.linalg.norm(tx.pos - c, axis=1)
        wk = np.clip((r - dist) / (0.35 * r), 0, 1)
        if toward is not None:
            wk *= np.clip(tx.nrm @ toward / 0.2, 0, 1)      # only the side facing that view
        w = np.maximum(w, wk); made.append({"why": k.get("why", ""), "at": [round(float(x), 3) for x in c], "r": r})
    return w, made


def paint(name, res=4096, detail=1.0, sharp=10.0, drift=0.035, bump=1.6, keep=None, brush=None):
    from . import texrepaint_paint as Pn
    from scipy import ndimage
    d = folder(name); _need(d, "fields.npz", "materials.json"); st = _state(d); surf = Surface.load(d)
    materials = json.loads((d / "materials.json").read_text())
    z = np.load(d / "fields.npz"); lo, h = z["lo"], float(z["h"]); s = float(z["sigma"]) / h
    tx = surf.texels(st["image"], res)
    ijk = ((tx.pos - lo) / h).T
    nn = ndimage.gaussian_filter(z["N"].astype(np.float32), s, truncate=2.5)
    nv = np.maximum(ndimage.map_coordinates(nn, ijk, order=1), 1e-6); del nn
    P = np.zeros((len(tx.idx), len(materials)), np.float32)
    for k in range(len(materials)):
        f = ndimage.gaussian_filter(z["F"][k].astype(np.float32), s, truncate=2.5)
        P[:, k] = ndimage.map_coordinates(f, ijk, order=1) / nv
    P /= np.maximum(P.sum(1, keepdims=True), 1e-6)
    names = [m["name"] for m in materials]; brushed = []
    for b in brush or []:   # the painter's brush: this material here (a crevice that kept the sculpt's dark colour)
        if b.get("material") not in names:
            raise ValueError(f"brush: material {b.get('material')!r} is not one of {names}")
        w, made = _keep_weight(tx, surf, st, [b]); k = names.index(b["material"])
        P *= (1 - w)[:, None]; P[:, k] += w; brushed += [dict(made[0], material=b["material"])]
    st["brushed"] = brushed
    tex_full = _rgb(d / "maps" / f"{st['image']}.png"); tex = tx.sample(tex_full)
    # base colours: measured at analysis res (concept on squarely seen texels)
    ta = surf.texels(st["image"], 1024); panels = _panels(d, st, surf)
    con, w = _project_fixed(panels, surf, ta, _ppm(st), _keep(surf))
    per_view = [_project_fixed([p], surf, ta, _ppm(st), _keep(surf)) for p in panels]
    Pa = np.stack([ndimage.map_coordinates(ndimage.gaussian_filter(z["F"][k].astype(np.float32), s, truncate=2.5),
                                           ((ta.pos - lo) / h).T, order=1) for k in range(len(materials))], 1)
    cols, src = Pn.base_colours(materials, {"P": Pa / np.maximum(Pa.sum(1, keepdims=True), 1e-6)},
                                ta.sample(tex_full), con, w, ta, per_view=per_view)
    nmap = _rgb(d / "maps" / f"{st['normal']}.png") if st.get("normal") else np.full((8, 8, 3), (128, 128, 255), np.uint8)
    kw, kept = _keep_weight(tx, surf, st, keep)
    colour, normal, rough, label = Pn.paint(tx, {"P": P}, materials, cols, nmap, tex, st["height"], sharp=sharp,
                                            drift=drift, detail_strength=detail, bump=bump, keep_w=kw)
    st["kept"] = kept
    img = st["image"]
    out = {"colour": d / f"{img}_4k.png", "normal": d / f"{img}_normal_4k.png", "rough": d / f"{img}_rough_4k.png"}
    Image.fromarray(colour).save(out["colour"]); Image.fromarray(normal).save(out["normal"])
    Image.fromarray(rough).save(out["rough"]); Image.fromarray(label).save(d / f"{img}_labels.png")
    st["painted"] = {k: str(v) for k, v in out.items()}
    st["base_colours"] = {m["name"]: {"rgb": [int(x) for x in c], "from": s_} for m, c, s_ in zip(materials, cols, src)}
    (d / "state.json").write_text(json.dumps(st, indent=1))
    small = np.array(Image.fromarray(colour).resize((1024, 1024), Image.LANCZOS))
    sheet = views_sheet(d, surf, st, [("before", d / "maps" / f"{img}.png"), ("after", small)])
    Image.fromarray(sheet).save(d / "sheet_paint.jpg", quality=88)
    return {"maps": {k: str(v) for k, v in out.items()}, "base_colours": st["base_colours"], "res": res}


def render(name, views=("front", "side", "back", "3q"), res=800, hide=(), centre=None, scale=None, tag=""):
    from .texrepaint_surface import blender
    d = folder(name); st = _state(d); _need(d, "state.json")
    if "painted" not in st:
        raise ValueError("render: run texrepaint_paint first")
    img = st["image"]; nrm = st.get("normal")
    P = st["painted"]
    swap = {img: P["colour"], **({nrm: P["normal"]} if nrm and P.get("normal") else {})}
    jobs = [("before", {}, {}), ("after", swap, {img: P["rough"]} if P.get("rough") else {})]
    for t, swap, rough in jobs:
        blender({"mode": "render", "glb": str(d / "model.glb"), "swap": swap, "rough": rough, "views": list(views),
                 "out_dir": str(d), "tag": f"render{tag}_{t}", "res": res, "hide": list(hide), "centre": centre,
                 "scale": scale}, gb=3, gpu=True)
    cells = []
    for v in views:
        col = [np.array(Image.open(d / f"render{tag}_{t}_{v}.png").convert("RGB").resize((res // 2, res // 2)))
               for t in ("before", "after")]
        cells.append(np.concatenate(col, 0))
    sheet = np.concatenate(cells, 1)
    Image.fromarray(sheet).save(d / f"sheet_render{tag}.jpg", quality=88)
    return d / f"sheet_render{tag}.jpg"


# ---- graphics: decals redrawn from the concept
def _base_map(d, st, res):
    """the map decals go onto: the 4K repaint if painted, else the generated map upscaled (Lanczos)"""
    if st.get("painted"):
        return _rgb(st["painted"]["colour"])
    return np.array(Image.open(d / "maps" / f"{st['image']}.png").convert("RGB").resize((res, res), Image.LANCZOS))


def decal_face(name, part, res=4096):
    """the part's face front-on as the generated texture shows it, with its outline corners numbered"""
    from PIL import ImageDraw
    from . import texrepaint_decal as Dc
    d = folder(name); st = _state(d); surf = Surface.load(d); tx = surf.texels(st["image"], 2048)
    F = Dc.face(tx, surf, part); tex = tx.sample(_rgb(d / "maps" / f"{st['image']}.png"))
    img, ppm, box, mask = Dc.rectify(F, tx, tex, 768)
    cs = Dc.corners(mask, 3)
    im = Image.fromarray(img); dr = ImageDraw.Draw(im)
    for i, (x, y) in enumerate(cs):
        dr.ellipse([x - 6, y - 6, x + 6, y + 6], outline=(0, 255, 255), width=3); dr.text((x + 8, y), str(i), fill=(0, 255, 255))
    p = d / f"face_{part}.png"; im.save(p)
    return p, {"part": part, "corners_px": [[round(float(a), 1) for a in c] for c in cs], "size_px": list(img.shape[:2]),
               "normal": [round(float(x), 3) for x in F["n"]], "texels": int(F["front"].sum())}


def decal(name, part, concept, concept_pts, k=4, colours=None, graphic=None, inset=0.003, res=4096, why=""):
    """redraw the part's graphic from the concept (corners concept_pts, in the order decal_face numbers them) or lay
    a given RGBA graphic (canvas space of decal_face), onto the map at res"""
    from . import texrepaint_decal as Dc
    d = folder(name); st = _state(d); surf = Surface.load(d)
    t2 = surf.texels(st["image"], 2048); F = Dc.face(t2, surf, part)
    tex2 = t2.sample(_rgb(d / "maps" / f"{st['image']}.png"))
    before, ppm0, box, mask = Dc.rectify(F, t2, tex2, 768)
    S = 2048 / 768; ppm = ppm0 * S; H, W = int(mask.shape[0] * S), int(mask.shape[1] * S)
    cs = Dc.corners(mask, 3) * S
    if graphic:
        g = np.array(Image.open(graphic).convert("RGBA").resize((W, H), Image.LANCZOS)).astype(np.float32)
        rgb, alpha, pal = g[..., :3], g[..., 3] / 255, None
    else:
        from skimage.draw import polygon
        conc = _rgb(concept); inside = np.zeros((H, W), bool)
        rr, cc = polygon(cs[:, 1], cs[:, 0], (H, W)); inside[rr, cc] = True
        rgb, _, pal = Dc.redraw(conc, concept_pts, cs, (H, W), k=k, colours=colours, inside=inside)
        dist = ndimage_edt(inside)
        alpha = np.clip(dist / (inset * ppm), 0, 1)   # soft edge over `inset` m inside the outline
    tx = surf.texels(st["image"], res); F4 = Dc.face(tx, surf, part)
    F4.update({k_: F[k_] for k_ in ("centre", "n", "up", "right")})
    F4["front"] = np.isin(tx.obj, F["objects"]) & ((tx.pos - F["centre"]) @ F["n"] > 0) & (np.abs(tx.nrm @ F["n"]) > 0.5)
    base = _base_map(d, st, res)
    out, n = Dc.apply(base, F4, tx, rgb, alpha, ppm, box)
    pth = d / f"{st['image']}_4k.png"; Image.fromarray(out).save(pth)
    st.setdefault("painted", {}).setdefault("colour", str(pth))
    st["painted"]["colour"] = str(pth)
    st.setdefault("decals", []).append({"part": part, "why": why, "concept_pts": concept_pts, "palette": pal,
                                         "texels": n, "source": graphic or str(concept)})
    (d / "state.json").write_text(json.dumps(st, indent=1))
    Image.fromarray(np.asarray(rgb, np.uint8)).save(d / f"decal_{part}.png")
    after = np.asarray(Image.fromarray(np.asarray(rgb, np.uint8)).resize(before.shape[1::-1]))
    after = np.where(mask[..., None], after, 0).astype(np.uint8)
    Image.fromarray(np.concatenate([before, after], 1)).save(d / f"sheet_decal_{part}.jpg", quality=90)
    return d / f"sheet_decal_{part}.jpg", st["decals"][-1]


def ndimage_edt(m):
    from scipy import ndimage
    return ndimage.distance_transform_edt(m)
