"""The model: layers, check, apply; the fitted light as a scene light; the residual against the
procedural skin; placed marks. Part of the skin projection (skin_project.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import skin_project
from .skin_project import _lin, lab
from .skin_project_atlas import _blur, atlas, image, interp
from .skin_project_detail import region_masks
from .skin_project_light import _dirs, ours_albedo
from .skin_project_make import make

# ---------------------------------------------------------------- the model
def layers(spec: dict, pj: dict, out: dict, part: str) -> None:
    """spec["skin"]["projection"] as paint layers (skin_features.build calls it after the skin's own colour and hair
    paint, before scars, tattoos and make-up): the albedo over everything painted so far, and the fine relief."""
    if not pj or not pj.get("albedo"):
        return
    box = [float(x) for x in pj["box"]]
    op = float(pj.get("opacity", 1.0))
    if op > 0:
        out["skin:projection"] = {"part": part, "color": "image", "opacity": round(op, 4),
                                  "image": {"id": pj["albedo"], "wrap": "uv", "box": box, "channel": "alpha"}}
    d = float(pj.get("detail_depth", skin_project.DETAIL_DEPTH))
    # the projected RELIEF goes with the projected colour: with the atlas as a measuring instrument (opacity 0), the photo's
    # fine relief is photo pixels too, and it carried their accidents as shaded grooves (a hair strand across a jaw: a
    # "scratch"; a strand at an outer eye corner: a "crack"). Our own microrelief stands in.
    if pj.get("detail") and d > 0 and op > 0:
        out["skin:projection_detail"] = {"part": part, "height": -round(d, 7),
                                         "mask": [{"image": {"id": pj["detail"], "wrap": "uv", "box": box, "channel": "luma"}}]}


def check(pj) -> dict | None:
    """Validate spec["skin"]["projection"]."""
    from .spec import SpecError
    if pj in (None, False, {}):
        return None
    if not isinstance(pj, dict) or set(pj) - {"albedo", "detail", "box", "opacity", "detail_depth", "head", "views", "delight", "version", "confidence", "light_colour", "tone_gain"}:
        raise SpecError("skin projection: {albedo: image id, detail: image id, box: [u0, v0, u1, v1], opacity, detail_depth} (made by skin_project)")
    if not (isinstance(pj.get("box"), list) and len(pj["box"]) == 4):
        raise SpecError("skin projection: box is [u0, v0, u1, v1] (made by skin_project)")
    return pj


def apply(name: str, out: str | None = None, remove: bool = False, opacity: float = 0.0, detail_depth: float = skin_project.DETAIL_DEPTH,
          note: str = "", save_dir: str | None = None, raw: bool = False, made: dict | None = None, eyes: bool = False, stubble: str = "picture", **kw) -> dict:
    """make() + the images into the content store + spec["skin"]["projection"] saved (on `out`, a copy with the
    references, or on `name`). remove=True takes it out. raw=True lays the UN-de-lit blend instead (the comparison).
    opacity: 0 (default) = the atlas is a MEASUREMENT only: the skin that ships is the procedural layers, which
    skin_from_reference fits to it; 1 = the de-lit picture itself as the colour (the ceiling: refused by the export, a judging
    overlay, an explicit opt-in).
    The files (albedo, raw, detail, confidence, report) are also written to <model>/skin_projection/ (or save_dir)."""
    import copy
    from PIL import Image
    from . import images, likeness_texture as lt, store
    from . import blockin_models
    spec = copy.deepcopy(store.load(name))
    dst = out or name
    if remove:
        (spec.get("skin") or {}).pop("projection", None)
        store.save(dst, spec, note or "skin projection removed")
        return {"text": f"{dst}: skin projection removed"}
    if not spec.get("skin"):
        raise ValueError(f"skin_project: {name} has no skin (the projection lies over the procedural skin: `skin` first)")
    r = dict(made) if made is not None else make(name, spec=spec, **kw)     # (made: a make() result to lay again, e.g. raw)
    d = Path(save_dir) if save_dir else store._dir(dst) / "skin_projection"
    d.mkdir(parents=True, exist_ok=True)
    Image.fromarray(r["albedo"], "RGBA").save(d / "albedo.png")
    Image.fromarray(r["raw"], "RGBA").save(d / "raw.png")
    det = np.zeros(r["detail"].shape + (4,), np.uint8)
    det[..., :3] = r["detail"][..., None]
    det[..., 3] = 255
    Image.fromarray(det, "RGBA").save(d / "detail.png")
    Image.fromarray(r["conf"]).save(d / "confidence.png")
    (d / "report.json").write_text(json.dumps(r["report"], indent=1, default=str))
    (d / "report.txt").write_text(r["text"])
    pj = {"albedo": images.ingest(d / ("raw.png" if raw else "albedo.png")), "detail": images.ingest(d / "detail.png"), "box": [round(float(x), 6) for x in r["box"]],
          "opacity": float(opacity), "detail_depth": float(detail_depth), "head": lt.head_key(spec["base"]), "delight": not raw, "version": skin_project.VERSION,
          # the MEASUREMENT skin_from_reference fits the procedural skin to (skin_read_frames.atlas_source): the de-lit albedo, where a
          # picture vouches for it, and each view's fitted light colour (against a backdrop it gives the tone's hue)
          "confidence": images.ingest(d / "confidence.png"),
          "light_colour": {str(k): v["light_colour"] for k, v in r["report"]["views"].items() if v.get("light_colour")},
          "tone_gain": r["report"]["tone"].get("gain")}
    spec["skin"] = {**spec["skin"], "projection": pj}
    notes = []
    ir = r["report"].get("eyes") or {}
    if not eyes and ir.get("iris"):
        notes.append("  skin.eyes left as they are (eyes=True sets iris / iris_inner / limbal from the read above)")
    if eyes and ir.get("iris") and spec["skin"].get("eyes") is not False:
        e0 = dict(spec["skin"].get("eyes") or {})
        e1 = {**e0, "iris": ir["iris"], "iris_inner": ir["iris_inner"], "limbal": ir["limbal"]}
        spec["skin"]["eyes"] = e1
        notes.append(f"  skin.eyes: iris {e0.get('iris')} -> {e1['iris']}, iris_inner {e0.get('iris_inner')} -> {e1['iris_inner']}, limbal {e0.get('limbal')} -> {e1['limbal']} "
                     "(GNM's own eyeball and pupil are kept: only its painted iris changes)")
    h = spec["skin"].get("hair") or {}
    if h.get("stubble"):
        if stubble == "picture":   # one or the other: the picture's own beard shadow, not ours on top of it
            spec["skin"]["hair"] = {k: v for k, v in h.items() if k != "stubble"}
            notes.append(f"  skin.hair.stubble {json.dumps(h['stubble'])} REMOVED: the picture carries its own beard shadow (stubble=\"keep\" keeps "
                         "ours: its strands / relief then stand on the picture's shadow)")
        else:
            notes.append("  NOTE: skin.hair.stubble kept AND the picture carries its own beard shadow: the projection covers our painted shadow; "
                         "our stubble's relief / strands stand on the picture's")
    if dst != name:
        rj = copy.deepcopy(blockin_models._refs(name))
        if rj.get("blockin"):
            rj["blockin"] = {**rj["blockin"], "root": dst}
        blockin_models._save(dst, spec, note or f"skin projection of {name}'s references", rj)
    else:
        store.save(dst, spec, note or "skin projection: the references projected, de-lit, filled")
    r["text"] += "\n" + "\n".join([f"  saved: {dst} skin.projection (files in {d})"] + notes)
    r["dir"] = str(d)
    return r


# ---------------------------------------------------------------- the fitted light as a scene light
def stage_light(light: dict, n: int = 24, angle: float = 55.0) -> dict:
    """A view's FITTED light ({"sh": (3, 9), "key": {"dir", "rgb"} | None}: make()'s report, views.<i>.light) as a
    scene lighting dict (suns + a uniform world; Standard view, 0 EV: the picture's own exposure): the order-2 light as
    the fewest non-negative soft suns of a fixed direction set + ambient whose order-2 projection it is (NNLS per
    channel), the key as its own sun. For renders set beside the picture: what the tool believes lit it."""
    from scipy.optimize import nnls
    from . import likeness_render
    sh = np.asarray(light["sh"], float)
    Dq = _dirs(4000)
    Yq = likeness_render.sh9(Dq)
    G = 4 * np.pi / len(Dq) * Yq.T @ Yq
    D = _dirs(n)
    A = np.linalg.solve(G, np.pi * likeness_render.sh9(D).T)              # (9, n): a unit sun's order-2 coefficients
    amb = np.zeros((9, 1))
    amb[0, 0] = 1.0
    M = np.c_[A, amb]
    # ONE set of suns from the light's LUMINANCE, all of the light's own mean colour (solving each channel by itself put
    # differently coloured suns in different directions: colour fringes under the chin and round the nose)
    x = nnls(M, skin_project.Y @ sh)[0]
    # the light's colour: skin_project's own measure (the fitted shading's median colour on the trusted skin) when the
    # report has it, else the order-0 coefficients' ratio; neutral when that is degenerate (a fit with a negative mean)
    dc = np.asarray(light.get("colour") or sh[:, 0], float)
    dc = dc / max(float(dc @ skin_project.Y), 1e-9) if (dc > 0.05 * abs(dc).max()).all() and dc.min() > 0 else np.ones(3)
    cm = float(dc.max())
    lights = []
    for i in range(n):
        if x[i] > 0.01 * float(x[:n].max() + 1e-9):
            lights.append({"dir": [round(float(v), 4) for v in D[i]], "energy": round(float(np.pi * x[i] * cm), 4),
                           "color": [round(float(v), 4) for v in dc / cm], "angle": angle, "specular": 0.0})   # (no highlight from the soft fills: their broad discs lay in the cornea as grey polygonal patches over every iris, EEVEE and Cycles; the key keeps its catchlight)
    X = np.zeros((n + 1, 3))
    X[n] = x[n] * dc
    k = light.get("key")
    if k:
        m = float(max(k["rgb"]))
        if m > 0:
            lights.insert(0, {"dir": list(k["dir"]), "energy": round(float(np.pi * m), 4), "color": [round(float(v) / m, 4) for v in k["rgb"]],
                              "angle": 2 * skin_project.KEY_DISC})
    a = X[n]
    am = float(max(a.max(), 1e-4))
    return {"lights": lights or [{"dir": [0, -1, 0.3], "energy": 0.0, "angle": angle}],
            "world": {"color": [round(float(v) / am, 4) for v in a], "strength": round(am, 4)}, "view": "Standard", "exposure": 0.0}


def residual(name: str, spec: dict | None = None, stride: int = 2, save: str | None = None, log=print) -> dict:
    """The model's PROCEDURAL skin (its own layers, no projection) against its de-lit atlas, where a picture vouches
    for the atlas: {"regions": {region: {"dE" (Lab, broad colour), "dL", "da", "db" (ours - atlas), "mid" (rms of the
    1.2-6 mm band's log-luminance difference), "fine" (ours' fine-band strength / the atlas': texture statistics, not
    a pointwise match), "texels"}}, "all": {...}, "map" (H, W, 3) uint8 (the broad + mid residual: red = ours darker,
    blue = ours lighter, grey = no picture), "text"}. The quality measure of a fitted skin, and its to-do list."""
    from PIL import Image
    from . import images, store
    spec = spec or store.load(name)
    pj = (spec.get("skin") or {}).get("projection") or {}
    if not pj.get("albedo") or not pj.get("confidence"):
        raise ValueError(f"residual: {name} has no skin projection with its confidence (skin_project first)")
    at = atlas(spec["base"])
    A = _lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)[at["ii"], at["jj"]]
    cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0][at["ii"], at["jj"]] / 255.0
    O = ours_albedo(at, spec, stride=stride, log=log)
    ok = cf > 0.6
    w = ok.astype(float)
    la, lo = np.log(np.maximum(A, 1e-4)), np.log(np.maximum(O, 1e-4))
    A_low, O_low = np.exp(_blur(at, la, w, skin_project.BANDS_MM[0])), np.exp(_blur(at, lo, w, skin_project.BANDS_MM[0]))
    a_mid = _blur(at, la @ skin_project.Y, w, skin_project.BANDS_MM[1]) - _blur(at, la @ skin_project.Y, w, skin_project.BANDS_MM[0])
    o_mid = _blur(at, lo @ skin_project.Y, w, skin_project.BANDS_MM[1]) - _blur(at, lo @ skin_project.Y, w, skin_project.BANDS_MM[0])
    a_fine = la @ skin_project.Y - _blur(at, la @ skin_project.Y, w, skin_project.BANDS_MM[1])
    o_fine = lo @ skin_project.Y - _blur(at, lo @ skin_project.Y, w, skin_project.BANDS_MM[1])
    dlab = lab(O_low) - lab(A_low)
    regs = {"ALL": np.ones(len(ok), bool), **region_masks(at)}
    out = {"regions": {}}
    for k, m in regs.items():
        q = m & ok
        if q.sum() < 300:
            continue
        d = dlab[q]
        out["regions"][k] = {"dE": round(float(np.linalg.norm(d, axis=1).mean()), 2), "dL": round(float(d[:, 0].mean()), 2),
                             "da": round(float(d[:, 1].mean()), 2), "db": round(float(d[:, 2].mean()), 2),
                             "mid": round(float(np.sqrt(np.mean((o_mid[q] - a_mid[q]) ** 2))), 4),
                             "mid_atlas": round(float(a_mid[q].std()), 4), "mid_ours": round(float(o_mid[q].std()), 4),
                             "fine": round(float(o_fine[q].std() / max(a_fine[q].std(), 1e-6)), 2), "texels": int(q.sum())}
    out["all"] = out["regions"].get("ALL")
    dl = (lo @ skin_project.Y - la @ skin_project.Y) - (o_fine - a_fine)                # broad + mid, signed
    img = np.full(at["shape"] + (3,), 90, np.uint8)
    v = np.clip(dl / 0.3, -1, 1)
    col = np.stack([np.where(v < 0, 255, 255 * (1 - v)), 255 * (1 - np.abs(v)), np.where(v > 0, 255, 255 * (1 + v))], 1)
    col = np.where(ok[:, None], col, 120)
    img[at["ii"], at["jj"]] = col.astype(np.uint8)
    out["map"] = img
    if save:
        Image.fromarray(img).save(save)
    L = [f"residual {name}: procedural skin against the de-lit atlas ({int(ok.sum())} texels a picture vouches for); broad colour Lab (ours - atlas), "
         "mid band (1.2-6 mm) rms of the log-luminance difference [the atlas' own / ours' strength there], fine band strength ours / atlas:"]
    for k, r in out["regions"].items():
        L.append(f"  {k:16s} dE {r['dE']:5.2f}  dL {r['dL']:+5.1f} da {r['da']:+5.1f} db {r['db']:+5.1f}   mid {r['mid']:.3f} [{r['mid_atlas']:.3f} / {r['mid_ours']:.3f}]   fine x {r['fine']:.2f}")
    out["text"] = "\n".join(L)
    return out


def marks(name: str, spec: dict | None = None) -> dict:
    """Prominent dark MARKS (moles, large freckles) of the de-lit atlas, each placed where it is: {"marks": [{"at"
    [x, y, z] (the head at rest, world), "radius" m, "dark" (log luminance under its surroundings), "lab" (its
    colour against the skin round it), "region"}], "text"}. Only where a picture vouches for the texel directly; never
    on brows, lips, the lids, at the picture's own edges or where the model has a cavity. A mole is a placed mark, not
    noise: skin.features.moles.at takes the list."""
    from PIL import Image
    from scipy import ndimage
    from . import images, store
    from . import likeness_render
    spec = spec or store.load(name)
    pj = (spec.get("skin") or {}).get("projection") or {}
    if not pj.get("albedo") or not pj.get("confidence"):
        raise ValueError(f"marks: {name} has no skin projection (skin_project first)")
    at = atlas(spec["base"])
    img = _lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)
    cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0] / 255.0
    lum = np.log(np.maximum(img @ skin_project.Y, 1e-4)).astype(np.float32)
    valid = image(at, np.ones(len(at["ii"]), bool), False)
    lum = np.where(valid, lum, float(np.median(lum[valid])))
    regs = region_masks(at)
    allow = np.zeros(len(at["ii"]), bool)
    for k, m in regs.items():
        if k not in ("lips", "brow"):
            allow |= m
    X = interp(at, at["V"])
    for Ve, _, _ in likeness_render.model_mesh(spec["base"])["eyes"]:
        c_ = Ve.mean(0)
        allow &= np.linalg.norm(X - c_, axis=1) - float(np.linalg.norm(Ve - c_, axis=1).max()) > skin_project.DETAIL_LID
    A = image(at, allow, False) & (ndimage.gaussian_filter((cf > 0.6).astype(np.float32), 2.0 / at["mm"]) > 0.9)
    best, scale = np.zeros(lum.shape, np.float32), np.zeros(lum.shape, np.float32)
    for mm in skin_project.MARK_MM:
        s = mm / at["mm"]
        hxx = ndimage.gaussian_filter(lum, s, order=(0, 2)) * s * s
        hyy = ndimage.gaussian_filter(lum, s, order=(2, 0)) * s * s
        hxy = ndimage.gaussian_filter(lum, s, order=(1, 1)) * s * s
        tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
        l1, l2 = 0.5 * (tr + df), 0.5 * (tr - df)                 # both positive at a dark blob
        blob = np.where((l2 > 0) & (l2 > skin_project.MARK_ROUND * l1), 0.5 * tr, 0.0)   # ~ the centre's depth under its surroundings
        take = blob > best
        best, scale = np.where(take, blob, best), np.where(take, mm, scale)
    peak = (best == ndimage.maximum_filter(best, int(2 * 2.0 / at["mm"]) | 1)) & (best > skin_project.MARK_DARK) & A
    ys, xs = np.nonzero(peak)
    order = np.argsort(-best[ys, xs])[:skin_project.MARK_MAX]
    idx = np.full(at["shape"], -1)
    idx[at["ii"], at["jj"]] = np.arange(len(at["ii"]))
    out = []
    for y, x in zip(ys[order], xs[order]):
        t = idx[y, x]
        if t < 0:
            continue
        r_px = 1.4 * scale[y, x] / at["mm"]
        yy, xx = np.mgrid[max(y - int(4 * r_px), 0):y + int(4 * r_px) + 1, max(x - int(4 * r_px), 0):x + int(4 * r_px) + 1]
        d = np.hypot(yy - y, xx - x)
        inn, ring = img[yy[d < 0.7 * r_px], xx[d < 0.7 * r_px]], img[yy[(d > 2 * r_px) & (d < 3.5 * r_px)], xx[(d > 2 * r_px) & (d < 3.5 * r_px)]]
        dl = lab(np.median(inn, 0)) - lab(np.median(ring, 0)) if len(inn) and len(ring) else np.zeros(3)
        out.append({"at": [round(float(v), 5) for v in X[t]], "radius": round(float(1.4 * scale[y, x] / 1000.0), 5), "dark": round(float(best[y, x]), 3),
                    "lab": [round(float(v), 1) for v in dl], "region": next((k for k, m in regs.items() if m[t]), "?")})
    L = [f"marks {name}: {len(out)} placed dark mark(s) read in the de-lit atlas (darkest first; radius mm, darkness, Lab against the skin round it):"]
    L += [f"  {m_['region']:14s} at {m_['at']}  r {1000 * m_['radius']:.1f}  dark {m_['dark']:.2f}  dLab {m_['lab']}" for m_ in out]
    return {"marks": out, "text": "\n".join(L)}
