"""Looking at hair and its gates: look, look_glb, check tiers, bare regions, the silhouette gate, pulling locks
back from Blender. Part of hair (hair.py has the overview)."""
from __future__ import annotations

import json
import re
import tempfile
import os
import time
from pathlib import Path

import numpy as np

from . import store
from . import hair, hair_card_fit, hair_head, hair_job
from .hair import _unit, dirs
from .hair_card_fit import cameras, human_ref_frames, make_stage, reference_image, stage_path
from .hair_groom import groom_params, hairline, inside
from .hair_head import Scalp
from .hair_job import job
from .hair_spec import fins, folds, hair_of, lock_address, lock_hash, root_ends

def look(name: str, views=("front", "three_quarter", "side", "back", "top"), size: int = 480, save: str | None = None,
         reference: str | None = None, spec: dict | None = None, caption: str = "", clay: bool = True,
         only=None, engine: str = "eevee", count: int | None = None, samples: int | None = None,
         budget: int | None = None, light=None, denoise: bool = True, debug: str | None = None,
         stage: str | None = None) -> tuple:
    """A fast hair look: the head-cropped stage file + the hair from the spec, EEVEE, a few perspective views, a
    thumbnail (how it reads small) and the reference beside. Returns (sheet image, seconds).
    Views "ref0", "ref1", ...: the FITTED cameras of the model's reference pictures (human_refs.json, the block-in /
    solve's cameras), the whole picture squared: the hair as the picture shows it (look.ids[view] = its hair mask,
    look.images[view] = the render; outline_measure / colour_bands compare them with the picture).
    `stage`: another model with the same head whose scene the hair is shown on (a riff's copy needs no scene of its
    own). The hair is always the spec's CURRENT hair (a stage file holds none)."""
    from . import hair_reference, hair_trace
    from PIL import Image, ImageDraw
    from . import render
    from .scene import _blender
    t = time.time()
    spec = store.load(name) if spec is None else spec
    sp = make_stage(stage or name, spec=spec)
    sc = hair_head.scalp(name, spec)
    ref_names = [v for v in views if re.fullmatch(r"ref\d+", str(v))]
    views = [v for v in views if v not in ref_names]
    cams = cameras(sc, views)
    frames = [render.camera_frame(c, i) for i, c in enumerate(cams)] + human_ref_frames(name, ref_names, stage)
    rvs = hair_reference.ref_views(name)
    mnames = ["matched" if v == "matched" else f"matched_{v}" for v, _, _ in rvs]
    for fname, (v, rc, _) in zip(mnames, rvs):  # the reference's own cameras (fit_camera): compared with the
        # reference pixel for pixel
        frames.append({"name": fname, "eye": rc["eye"], "dir": rc["dir"], "up": rc["up"], "fov": rc["fov"],
                       "shift": rc["shift"], "center": sc.C.tolist(), "near": 0.01, "scale": None, "axes": None})
    thumb = render.camera_frame({"name": "thumb", "eye": (sc.C + dirs(25.0, 8.0) * 1.6).tolist(),
                                 "target": (sc.C - [0, 0, 0.12]).tolist(), "fov": 30.0}, len(frames))
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames + [thumb]:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        thumb["size"] = 160
        dump = str(Path(tmp) / "hair_pts.npy")
        cf = [{**f, "out": str(Path(tmp) / f"clay_{f['name']}.png")} for f in frames] if clay else []
        idf = [{**f, "out": str(Path(tmp) / f"id_{f['name']}.png"),
                "size": 480 if f["name"].startswith(("matched", "ref")) else 240} for f in frames]  # (matched ones finer:
        # the hairline's edge is measured on them)
        j = {"mode": "hair_look", "blend": str(sp), "views": frames + [thumb], "size": size,
             "hair": job(name, spec, only=only, count=count, budget=budget),
             "samples": samples or (32 if engine == "cycles" else 16), "dump": dump, "clay_views": cf, "id_views": idf,
             "look_engine": engine}
        style = hair_of(spec).get("style", "locks")
        if debug and j["hair"].get("cards"):
            j["hair"]["cards"]["debug"] = debug
        light = light if light is not None else (hair_of(spec).get("look") or {}).get("light")
        if light is None and style in ("strands", "cards"):
            light = "salon"
        if light:
            j["lighting"] = hair_card_fit.LIGHTS[light] if isinstance(light, str) else light
        if engine == "cycles" and style == "strands":
            j.update(hair_bounces=10, denoise=bool(denoise), adaptive_threshold=0.01,
                     samples=samples or 96)
        if engine == "cycles":  # path-traced strands: minutes of every core, one such job at a time on the machine
            from . import resources
            with resources.heavy(f"hair look {name} (cycles)", kind="hair_cycles", model=name):
                out = _blender(j, timeout=3600)
        else:
            out = _blender(j)
        clays = [Image.open(f["out"]).convert("RGB") for f in cf]
        look.mass_share, look.lit_mass, masks = {}, {}, {}
        look.ids, look.images = {}, {}
        for f, fm in zip(idf, frames):  # red = the underlayer, green = locks (flat emission, nothing else drawn)
            a = np.asarray(Image.open(f["out"]).convert("RGB"), float)
            red, green = a[..., 0] > a[..., 1] + 60, a[..., 1] > a[..., 0] + 60
            if f["name"] in mnames:
                masks[f["name"]] = red | green
            if f["name"] in ref_names:
                look.ids[f["name"]] = red | green
                look.images[f["name"]] = Image.open(fm["out"]).convert("RGB")
            look.mass_share[f["name"]] = round(float(red.sum() / max(red.sum() + green.sum(), 1)), 3)
            # lit bare volume: where the volume shows AND is shaded like the locks around it (not a crevice or a
            # parting in shadow): the smooth patch the eye reads as a helmet
            lum = np.asarray(Image.open(fm["out"]).convert("L").resize(a.shape[1::-1]), float)
            lit_ref = np.percentile(lum[green], 35) if green.any() else 255.0
            lit = red & (lum >= lit_ref)
            look.lit_mass[f["name"]] = round(float(lit.sum() / max(red.sum() + green.sum(), 1)), 3)
            Image.open(f["out"]).save(store._dir(name) / f"hair_id_{f['name']}.png")  # the last look's id pass
        pts = np.load(dump)
        np.save(store._dir(name) / "hair_points.npy", pts)  # the last look's hair vertices (for measuring) and
        np.savez(store._dir(name) / "hair_point_owners.npz", ids=np.load(dump + ".ids.npy"),  # which object each is
                 names=np.array(json.load(open(dump + ".names.json"))))
        owners = (pts, np.load(dump + ".ids.npy"), json.load(open(dump + ".names.json")))
        look.bare_where = {}
        if j["hair"] and j["hair"].get("cap"):  # where the bare volume shows, by head region
            capV = np.load(j["hair"]["cap"])["verts"]
            g_ = groom_params(spec)
            for f, fm in zip(idf, frames):
                a = np.asarray(Image.open(f["out"]).convert("RGB"), float)
                red, green = a[..., 0] > a[..., 1] + 60, a[..., 1] > a[..., 0] + 60
                look.bare_where[f["name"]] = bare_regions(sc, g_, capV, fm, red, red.sum() + green.sum(),
                                                          cam=dict(zip(mnames, [rc for _, rc, _ in rvs])).get(f["name"]))
        look.gate = silhouette_gate(sc, pts)
        look.folds = folds(sc, j["hair"].get("locks") or []) if j["hair"] else {}
        # (tied hair's own locks are strand guides, never a sculpted surface: a tail "stands 16 cm over the layer",
        # every gather lock "rises out of it": 226 fins and 60 blunt ends on a good ponytail told the reader nothing)
        solid = [k_ for k_ in (j["hair"].get("locks") or [])
                 if not re.fullmatch(r"t\d*(g\d+_\d+|t\d+|e\d+_\d+|s\d+|f\d+|band)", str(k_.get("name", "")))] if j["hair"] else []
        look.root_ends = root_ends(sc, groom_params(spec), solid) if solid else {}
        look.fins = fins(sc, groom_params(spec), solid) if solid else {}
        imgs = [Image.open(f["out"]).convert("RGB") for f in frames]
        th = Image.open(thumb["out"]).convert("RGB")
    t_render = time.time() - t
    W = size
    nm = len(rvs)
    matched, mclay = [], []
    if nm:  # a row each: matched render, clay, reference, 50% blend, the traced lines
        matched = imgs[len(imgs) - nm:]
        imgs = imgs[:len(imgs) - nm]
        if clays:
            mclay = clays[len(clays) - nm:]
            clays = clays[:len(clays) - nm]
        frames = frames[:len(frames) - nm]
    cols = max(len(imgs) + 1, 5 if nm else 0)
    rows = (2 if clays else 1) + nm
    sheet = Image.new("RGB", (W * cols, rows * W + 22), (30, 31, 35))
    dr = ImageDraw.Draw(sheet)
    for i, (im, f) in enumerate(zip(imgs, frames)):
        sheet.paste(im.resize((W, W)), (i * W, 22))
        dr.text((i * W + 6, 5), f["name"], fill=(220, 220, 220))
    for i, im in enumerate(clays):
        sheet.paste(im.resize((W, W)), (i * W, 22 + W))
    if clays:
        dr.text((6, 22 + W + 6), "clay", fill=(220, 220, 220))
    x0 = len(imgs) * W
    ref, rcrop = reference_image(name, reference)
    if ref is not None:
        r = Image.open(ref).convert("RGB")
        r = r.crop(tuple(rcrop)) if rcrop else r
        r.thumbnail((W, W - 170))
        sheet.paste(r, (x0, 22))
        dr.text((x0 + 6, 5), "reference", fill=(220, 220, 220))
    sheet.paste(th, (x0 + 6, W + 22 - th.height - 4))
    dr.text((x0 + 170, W + 22 - 20), f"thumbnail {th.width}px", fill=(200, 200, 200))
    look.fits = {v: hair_reference.fit_metrics(name, sc, rc, spec, masks.get(fn), tr=t, owners=owners)
                 for fn, (v, rc, t) in zip(mnames, rvs)}
    look.fit = look.fits.get("matched")
    if look.fit:
        f = look.fit
        caption = (caption + "   " if caption else "") + "fit: " + ", ".join(
            f"{k} {v}" for k, v in f.items() if k not in ("clumps", "mm_per_px", "regions", "front_edge"))
    for j, (fn, (v, rc, t)) in enumerate(zip(mnames, rvs)):
        y = (rows - nm + j) * W + 22
        rimg = Path(t["image"]) if t.get("image") and Path(t["image"]).exists() else None
        mr = matched[j].resize((W, W))
        panels = [(f"matched camera ({v})", mr)]
        if rimg is not None:
            refc = Image.open(rimg).convert("RGB").crop(tuple(rc["crop"])).resize((W, W))
            fv = look.fits.get(v)
            if fv and masks.get(fn) is not None:
                fl = hair_trace.front_flow(rc, t, Image.open(rimg).convert("RGB").crop(tuple(rc["crop"])), matched[j],
                                masks[fn], fv["mm_per_px"])
                if fl:
                    fv["front_flow"] = fl
            panels += [("reference", refc), ("50% blend", Image.blend(mr, refc, 0.5))]
        if mclay:
            panels.insert(1, ("matched clay", mclay[j].resize((W, W))))
        tro = hair_trace.trace_overlay(name, sc, rc, mr, spec, tr=t, mask=masks.get(fn))
        if tro is not None:
            panels.append(("trace: ref yellow/orange, ours cyan/magenta", tro))
        for i, (lab, im) in enumerate(panels[:cols]):
            sheet.paste(im, (i * W, y))
            dr.text((i * W + 6, y + 4), lab, fill=(255, 255, 120))
    if caption:
        dr.text((6, rows * W + 6), caption, fill=(240, 220, 160))
    if save:
        sheet.save(save)
    frames_t = [line for line in out.splitlines() if line.startswith("@@")]
    return sheet, round(t_render, 1), frames_t


def look_glb(name: str, glb, views=("wide_r", "back_quarter", "close_front", "three_quarter"), size: int = 480,
             alpha: str = "test", light="salon", spec: dict | None = None, dist: float | None = None,
             engine: str = "eevee") -> tuple:
    """An exported hair GLB re-imported onto the model's head stage and rendered as an engine draws it (Blender's
    glTF importer; alpha "test" = cut at the material's alphaCutoff, "dither" = hashed alpha, "off" = solid cards).
    Returns ([image per view], what the importer made, seconds). `dist`: the camera's distance (m) in place of the
    close look's 0.62: a tier is judged where it is meant to be seen."""
    from PIL import Image
    from . import render
    from .scene import _blender
    t = time.time()
    spec = store.load(name) if spec is None else spec
    sp = make_stage(name, spec=spec)
    sc = hair_head.scalp(name, spec)
    cams = cameras(sc, views) if dist is None else cameras(sc, views, dist=dist)
    frames = [render.camera_frame(c, i) for i, c in enumerate(cams)]
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        j = {"mode": "hair_glb_look", "blend": str(sp), "views": frames, "size": size, "glb": str(glb) if glb else None,
             "alpha": alpha, "samples": 16, "look_engine": engine}
        if light:
            j["lighting"] = hair_card_fit.LIGHTS[light] if isinstance(light, str) else light
        out = _blender(j)
        imgs = [Image.open(f["out"]).convert("RGB") for f in frames]
    info = next((json.loads(ln[6:]) for ln in out.splitlines() if ln.startswith("@@glb")), {})
    return imgs, info, round(time.time() - t, 1)


def check_tiers(name: str, export: dict | str | Path, tiers=None, save: str | None = None, size: int = 400,
                views=("wide_r", "back_quarter", "close_front", "three_quarter"), solid: bool = True,
                spec: dict | None = None) -> dict:
    """An export's card tiers judged as an engine draws them, against the strand groom: each tier's GLB re-imported
    on the head (alpha TEST at its cutoff, and dithered), the strands and the bald head in the same views and light.
    Per tier and view (hair_checks.compare): iou / missing (strand silhouette left bare), value and saturation x the
    strands', detached rectangular blobs (cards showing as stamps), straight outline share (plank ends); per tier
    the card mesh's own numbers (cards, widths, triangles by layer, what the budget dropped) and WARNING lines.
    `save`: a sheet: strands | per tier alpha test, dithered, and (solid=True) the cards as solid quads coloured by
    layer | the atlas. `export`: export_hair's report or its folder. Returns {"tiers": {...}, "warnings": [...],
    "sheet": path}."""
    from PIL import Image, ImageDraw
    from . import hair_checks as hk
    if not isinstance(export, dict):
        export = json.loads((Path(export) / f"{name}_hair.json").read_text())
    spec = store.load(name) if spec is None else spec
    tiers = list(tiers or export["tiers"])
    bald, _, _ = look_glb(name, None, views=views, size=size, spec=spec)
    sp = {**spec, "hair": {**hair_of(spec), "style": "strands"}}
    sheet, _, _ = look(name, views=views, size=size, spec=sp, clay=False)
    strands = [sheet.crop((i * size, 22, (i + 1) * size, 22 + size)) for i in range(len(views))]
    rows = [("strands (the groom)", strands)]
    out = {"tiers": {}, "warnings": []}
    for tier in tiers:
        e = export["tiers"][tier]
        r = {"triangles": e["triangles"], "budget": e.get("budget"), "layers": e.get("layers")}
        for alpha in ("test", "dither"):
            imgs, info, _ = look_glb(name, e["glb"], views=views, size=size, alpha=alpha, spec=spec)
            r[alpha] = {v: hk.compare(s_, im, b) for v, s_, im, b in zip(views, strands, imgs, bald)}
            rows.append((f"{tier}: the GLB re-imported, alpha {alpha}   {e['triangles']} triangles", imgs))
        r["clearance"] = e.get("clearance")
        r["warnings"] = sorted(set(hk.verdict(r["test"], far=tier == "far") + hk.verdict(r["dither"], far=tier == "far")
                                   + hk.mesh_verdict(e.get("clearance"))))
        out["warnings"] += [f"{tier}: {w}" for w in r["warnings"]]
        if solid and tier in hair_job.CARD_TIERS:
            sc_ = {**spec, "hair": {**hair_of(spec), "style": "cards"}}
            sh, _, _ = look(name, views=views, size=size, spec=sc_, clay=False, budget=tier, debug="layers")
            rows.append((f"{tier}: cards as solid quads by layer (cap + core grey, 0 red, 1 green, 2 blue, 3 yellow, "
                         f"above magenta; back faces dark)",
                         [sh.crop((i * size, 22, (i + 1) * size, 22 + size)) for i in range(len(views))]))
        out["tiers"][tier] = r
    if save:
        W_ = size * len(views)
        maps = export.get("maps") or {}
        atl = Image.open(maps["basecolor"]).convert("RGBA") if maps.get("basecolor") else None
        extra = 2 * (W_ // 2 + 18) if atl is not None else 0
        img = Image.new("RGB", (W_, len(rows) * (size + 18) + extra), (30, 31, 35))
        d = ImageDraw.Draw(img)
        y = 0
        for lab, ims in rows:
            d.text((6, y + 3), lab, fill=(240, 220, 160))
            for i, im in enumerate(ims):
                img.paste(im.resize((size, size)), (i * size, y + 18))
            y += size + 18
        if atl is not None:
            bg = Image.new("RGBA", atl.size, (140, 140, 140, 255))
            for lab, im in (("atlas: base colour over grey (left: clump tiles, right: the scalp chart)",
                             Image.alpha_composite(bg, atl).convert("RGB")), ("atlas: alpha", atl.split()[3].convert("RGB"))):
                d.text((6, y + 3), lab, fill=(240, 220, 160))
                img.paste(im.resize((W_, W_ // 2)), (0, y + 18))
                y += W_ // 2 + 18
        img.save(save)
        out["sheet"] = str(save)
        stem = str(save)[:-4]
        for lab, ims in rows:  # each row alone too (the whole sheet is tall)
            rr = Image.new("RGB", (W_, size))
            for i, im in enumerate(ims):
                rr.paste(im.resize((size, size)), (i * size, 0))
            tag = lab.split(":")[0].split(" ")[0] + ("_solid" if "solid" in lab else "_dither" if "dither" in lab
                                                     else "_test" if "test" in lab else "")
            rr.save(f"{stem}_{tag}.png")
    return out


def tiers_text(chk: dict) -> str:
    """check_tiers' numbers as a table."""
    lines = ["tier     tris   view            iou   bare  value   sat  stamps straight   (alpha test | dithered)"]
    for tier, r in chk["tiers"].items():
        for v in r["test"]:
            a, b = r["test"][v], r["dither"][v]
            lines.append(f"{tier:<6} {r['triangles']:>6}   {v:<14} {a['iou']:.2f}  {a['missing']:.2f}   {a['value']:.2f}  {a['sat']:.2f}"
                         f"   {a['stamps']}    {a['straight']:.2f}   |  {b['iou']:.2f}  {b['missing']:.2f}   {b['value']:.2f}  {b['sat']:.2f}"
                         f"   {b['stamps']}    {b['straight']:.2f}")
    lines += chk["warnings"] or ["no warnings"]
    return "\n".join(lines)


def _project_frame(fm: dict, P, W: int):
    """World points -> pixels (u right, v down) of a square look frame (render.camera_frame: perspective, fov across)
    and their depth along the view."""
    eye = np.asarray(fm["eye"], float)
    fwd = -_unit(np.asarray(fm["dir"], float))
    right = _unit(np.cross(fwd, np.asarray(fm["up"], float)))
    up = np.cross(right, fwd)
    Q = np.asarray(P, float) - eye
    z = Q @ fwd
    k = 1.0 / np.tan(np.radians(float(fm["fov"])) / 2)
    x, y = (Q @ right) / z * k, (Q @ up) / z * k
    return np.stack([(x + 1) / 2 * W, (1 - (y + 1) / 2) * W], -1), z


BARE_BAND = 0.015  # m inside the hairline: bare volume there is reported as "<region> hairline"


def bare_regions(sc: Scalp, g: dict, capV, fm: dict, red, total: int, cam: dict | None = None) -> dict:
    """Where the bare volume shows in a view: each underlayer pixel of the id pass labelled by the head region of the
    underlayer point it shows (the nearest projected vertex), "<region> hairline" within BARE_BAND of the hairline.
    {label: share of the view's visible hair}, largest first (above 0.005)."""
    from . import hair_reference, hair_trace
    if total == 0 or not red.any():
        return {}
    W = red.shape[0]
    if cam is not None:  # a matched view: the reference camera (lens shift)
        uv = hair_reference._to_crop(cam, hair_reference.project_ref(cam, capV), W)
        R_, t_, ctr = np.array(cam["R"]), np.array(cam["t"]), np.array(cam["ctr"])
        z = ((capV - ctr) @ R_.T + t_)[:, 2]
    else:
        uv, z = _project_frame(fm, capV, W)
    iu, iv = np.round(uv[:, 0]).astype(int), np.round(uv[:, 1]).astype(int)
    ok = (z > 0) & (iu >= 0) & (iu < W) & (iv >= 0) & (iv < W)
    zb = np.full((W, W), np.inf)
    owner = -np.ones((W, W), int)
    idx = np.nonzero(ok)[0]
    order = idx[np.argsort(-z[idx])]  # far first: nearer vertices overwrite
    zb[iv[order], iu[order]] = z[order]
    owner[iv[order], iu[order]] = order
    from scipy.ndimage import distance_transform_edt
    has = owner >= 0
    _, (ri, ci) = distance_transform_edt(~has, return_indices=True)  # pixels between projected vertices
    ys, xs = np.nonzero(red)
    v = owner[ri[ys, xs], ci[ys, xs]]
    a, e, _ = sc.coords(capV[v])
    d_in = inside(sc, hairline(sc, g), a, e)
    lab = np.char.add(hair_trace.region_of(a, e).astype(str), np.where(d_in < BARE_BAND, " hairline", ""))
    out = {}
    for L in np.unique(lab):
        s = float((lab == L).sum() / total)
        if s >= 0.005:
            out[str(L)] = round(s, 3)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


GATE_MM = 1.5  # the deepest dent allowed in the hair's outline (front and 3/4), mm, from the brows up to...


GATE_SCALE = 0.012  # m: the outline is gated on shapes at least one lock row tall (smoothed over it): a waist or


# divot is tens of mm; a clump's step where one lock ends over the next is a notch, the relief we want
NOTCH_SCALE = 0.006  # m: notches (clump steps at the outline) are measured on this and reported, target 2-5 mm


CROWN_BAND = 0.02  # ...this far under the top (the top's outline is the lock crowns: reported, not gated)


def silhouette_gate(sc: Scalp, V, views=(("front", 0.0, ("left", "right")), ("three_quarter", 40.0, ("left",)),
                                          ("three_quarter_r", -40.0, ("right",)))) -> dict:
    """How far the hair's outline dips inside its own convex hull, per view and side, over the band from a little
    above the brows to near the top (a waist at the temples reads as a divot). Orthographic along the view's azimuth.
    {view: {"left": mm, "right": mm, "at": z of the worst}, "pass": bool}."""
    from scipy.spatial import ConvexHull
    z0 = (sc.lm["lm_brow_mid.L"][2] if "lm_brow_mid.L" in sc.lm else float(sc.C[2])) + 0.02
    out, ok = {}, True
    for name, az, sides in views:  # 3/4: the near side's outline (the far one is the forehead's profile)
        a = np.radians(az)
        right = np.array([np.cos(a), np.sin(a), 0.0])  # the view's lateral axis (his left positive)
        Q = V - sc.C
        x, z = Q @ right, V[:, 2]
        keep = z > z0
        x, z = x[keep], z[keep]
        ztop = z.max() - 0.01
        res, worst = {}, (0.0, None)
        edges = np.arange(z0, ztop, 0.002)
        for side, sgn in (("left", 1.0), ("right", -1.0)):
            if side not in sides:
                continue
            raw = np.array([np.max(sgn * x[(z >= e) & (z < e + 0.002)]) if np.any((z >= e) & (z < e + 0.002))
                            else np.nan for e in edges])

            def smoothed(scale):
                k = max(1, int(round(scale / 0.002)))
                if k > 1 and np.isfinite(raw).all():
                    return np.convolve(np.pad(raw, k // 2, mode="edge"), np.ones(k) / k, mode="valid")[:len(edges)]
                return raw
            prof = smoothed(NOTCH_SCALE)
            good = ~np.isnan(prof)
            if good.sum() >= 4:  # the notches: clump steps (6 mm smoothing), reported
                Pn = np.stack([prof[good], edges[good]], 1)
                Pn = Pn[Pn[:, 1] <= ztop - CROWN_BAND]
                if len(Pn) >= 4:
                    b = Pn[:, 0].min() - 1.0
                    P2 = np.vstack([Pn, [[b, Pn[0, 1]], [b, Pn[-1, 1]]]])
                    hv = P2[ConvexHull(P2).vertices]
                    hv = hv[hv[:, 0] > b + 0.5]
                    hv = hv[np.argsort(hv[:, 1])]
                    res[side + "_notch"] = round(float(((np.interp(Pn[:, 1], hv[:, 1], hv[:, 0]) - Pn[:, 0])
                                                        * 1000).max()), 1)
            prof = smoothed(GATE_SCALE)
            good = ~np.isnan(prof)
            if good.sum() < 4:
                continue
            P = np.stack([prof[good], edges[good]], 1)

            def dents(P):
                base = P[:, 0].min() - 1.0  # close the outline on the inside: the hull's outer chain is the envelope
                P2 = np.vstack([P, [[base, P[0, 1]], [base, P[-1, 1]]]])
                hv = P2[ConvexHull(P2).vertices]
                hv = hv[hv[:, 0] > base + 0.5]
                hv = hv[np.argsort(hv[:, 1])]
                return (np.interp(P[:, 1], hv[:, 1], hv[:, 0]) - P[:, 0]) * 1000
            # the gated band: brows + 2 cm up to CROWN_BAND under the top, its own envelope (the lock crowns on top
            # are the clumps; a chord from them down onto the sides is reported as "full", not gated)
            crown = P[:, 1] > ztop - CROWN_BAND
            full = dents(P)
            res[side + "_crown"] = round(float(full[crown].max()), 1) if crown.any() else 0.0
            res[side + "_full"] = round(float(full.max()), 1)
            gap = np.zeros(len(P))
            if (~crown).sum() >= 4:
                gap[~crown] = dents(P[~crown])
            i = int(np.argmax(gap))
            res[side] = round(float(gap[i]), 1)
            if gap[i] > worst[0]:
                worst = (float(gap[i]), round(float(P[i, 1]), 3))
        res["at"] = worst[1]
        out[name] = res
        ok &= worst[0] <= GATE_MM
    out["pass"] = bool(ok)
    return out


def sync(name: str) -> dict:
    """Push the spec's hair into scene.blend (the person's live Blender when it has the scene open)."""
    from .scene import _blender, _blender_live, blend_path, live_session
    j = {"mode": "hair_sync", "blend": str(blend_path(name)), "hair": job(name)}
    t = time.time()
    bp, sp = blend_path(name), stage_path(name)
    fresh = sp.exists() and bp.exists() and sp.stat().st_mtime > bp.stat().st_mtime
    out = _blender_live(j) if live_session(name) else _blender(j)
    if fresh:  # the stage holds no hair (looks show the spec's): a hair-only save of scene.blend doesn't stale it
        os.utime(sp)
    made = next((json.loads(line[7:]) for line in out.splitlines() if line.startswith("@@made")), [])
    return {"made": len(made), "seconds": round(time.time() - t, 1)}


def pull_locks(spec: dict, name: str, got: dict, log: list) -> dict:
    """Locks a person changed in the scene, written into the spec as (az, el, h) addresses and lock numbers."""
    if not got:
        return {}
    h = hair_of(spec)
    locks = h.get("locks") or {}
    sc = hair_head.scalp(name, spec)
    changes = {}
    inv = {v: k for k, v in hair.MOD.items()}
    for n, st in got.items():
        if n in ("__deleted__", "__new__"):
            continue
        lk = locks.get(n)
        if lk is None:
            continue
        stale = bool(st.get("hash")) and st["hash"] != lock_hash(lk, sc)
        # stale: the scene's lock was built from another version of the spec (regrown or synced from another model
        # since): an edit to it isn't an edit to this lock. The next sync replaces it. (A lock pulled from a saved
        # file reads back as itself until the next sync: not news.)
        P = np.asarray(st["pts"], float)
        new = dict(lk)
        new["pts"] = lock_address(sc, lk, P)
        if st.get("handles"):
            H = []
            for hd in st["handles"]:
                if hd:
                    if lk.get("space") == "xyz":
                        q = lock_address(sc, lk, [hd[:3], hd[3:]])
                        H.append(q[0] + q[1])
                    else:
                        a1, e1, h1 = sc.coords(np.asarray(hd[:3]))
                        a2, e2, h2 = sc.coords(np.asarray(hd[3:]))
                        H.append([round(float(v), 4) for v in (a1, e1, h1, a2, e2, h2)])
                else:
                    H.append(None)
            new["handles"] = H
        else:
            new.pop("handles", None)
        for k, key in (("radius", 1.0), ("tilt", 0.0)):
            vals = st.get(k) or []
            if vals and any(abs(v - key) > 1e-4 for v in vals):
                new[k] = vals
            else:
                new.pop(k, None)
        for mk, v in (st.get("inputs") or {}).items():
            if mk in inv:
                if abs(float(v) - float(lk.get(inv[mk], hair.LOCK_DEFAULTS.get(inv[mk], 0.0)))) > 1e-5:
                    new[inv[mk]] = round(float(v), 5)
        if stale:
            if {k: v for k, v in new.items() if k != "hand"} != {k: v for k, v in lk.items() if k != "hand"}:
                log.append(f"hair lock {n}: the scene's copy was built from another version of the spec (regrown or "
                           f"edited since the last sync): not pulled; sync replaces it")
            continue
        if new != lk:
            new["hand"] = True  # shaped by hand: a regrow (hair.groom) leaves it alone
            locks[n] = new
            changes[f"hair.{n}"] = "edited in the scene"
            log.append(f"hair lock {n}: edited in the scene")
    for n, st in (got.get("__new__") or {}).items():  # curves added in Blender (Shift+D on a lock, or drawn new)
        if n in locks:
            log.append(f"hair lock {n}: added in the scene, but the spec has a lock of that name: not pulled")
            continue
        P = np.asarray(st["pts"], float)
        a, e, hh = sc.coords(P)
        new = {"tier": "hand", "hand": True,
               "pts": [[round(float(a[i]), 2), round(float(e[i]), 2), round(float(hh[i]), 4)] for i in range(len(P))]}
        if st.get("handles"):
            H = []
            for hd in st["handles"]:
                if hd:
                    a1, e1, h1 = sc.coords(np.asarray(hd[:3]))
                    a2, e2, h2 = sc.coords(np.asarray(hd[3:]))
                    H.append([round(float(v), 4) for v in (a1, e1, h1, a2, e2, h2)])
                else:
                    H.append(None)
            new["handles"] = H
        for k in ("radius", "tilt"):
            vals = st.get(k) or []
            if vals and any(abs(v - (1.0 if k == "radius" else 0.0)) > 1e-4 for v in vals):
                new[k] = vals
        for mk, v in (st.get("inputs") or {}).items():
            if mk in inv:
                new[inv[mk]] = round(float(v), 5)
        new.setdefault("width", 0.03)
        new.setdefault("thickness", 0.006)
        locks[n] = new
        changes[f"hair.{n}"] = "added in the scene"
        log.append(f"hair lock {n}: added in the scene")
    removed = h.setdefault("removed", [])
    for n in got.get("__deleted__", []):
        if n in locks:
            locks.pop(n)
            if n not in removed:  # a regrow mustn't bring it back
                removed.append(n)
            changes[f"hair.{n}"] = "deleted in the scene"
            log.append(f"hair lock {n}: deleted in the scene")
    if not removed:
        h.pop("removed", None)
    return changes
