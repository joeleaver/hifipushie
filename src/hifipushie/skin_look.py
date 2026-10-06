"""Fast, close looks at a character's skin (the `look_skin` tool): a cropped copy of the model per body region (the
head and shoulders, a forearm and hand: bare skin at ~1 mm, without clothes or hair), kept in
workspace/_skin_<model>_<region> and re-synced only when the spec changes (a paint-only change re-measures and
rebuilds the material: ~10-30 s; a geometry change re-meshes: ~2 min), rendered in EEVEE under fixed lights, with the
numbers `skin_measure` reads off the render next to what photographs of real skin measure."""
from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from . import skin_measure, store

STUDIO = {"lights": [{"dir": [-0.55, -0.7, 0.45], "energy": 3.6, "color": [1.0, 0.96, 0.9], "angle": 12,
                      "window": {"size": [0.45, 0.65], "distance": 2.4, "gain": 0.4}},  # one soft window-shaped highlight
                     {"dir": [0.7, -0.5, 0.1], "energy": 0.5, "color": [0.85, 0.9, 1.0], "angle": 40, "shadow": False,
                      "specular": 0.0}],
          "world": {"color": [0.55, 0.58, 0.62], "strength": 0.5}, "view": "Khronos PBR Neutral", "exposure": -0.6}
SOFT = {"lights": [{"dir": [-0.2, -0.9, 0.35], "energy": 2.4, "color": [1.0, 0.98, 0.95], "angle": 25,
                    "window": {"size": [0.8, 0.8], "distance": 2.2, "gain": 0.4}},
                   {"dir": [0.6, -0.6, 0.2], "energy": 1.0, "color": [0.95, 0.97, 1.0], "angle": 25, "shadow": False,
                    "specular": 0.0}],
        "world": {"color": [0.7, 0.72, 0.75], "strength": 0.8}, "view": "Khronos PBR Neutral", "exposure": -0.6}
BACK = {"lights": [{"dir": [-0.35, 0.9, 0.2], "energy": 7.0, "color": [1.0, 0.97, 0.92], "angle": 6},
                   {"dir": [-0.6, -0.7, 0.2], "energy": 0.3, "angle": 40, "shadow": False}],
        "world": {"color": [0.3, 0.32, 0.35], "strength": 0.3}, "view": "Khronos PBR Neutral", "exposure": -0.3}
LIGHTS = {"studio": STUDIO, "soft": SOFT, "back": BACK}
# what 13 photographs of faces measured (skin_measure, medians; workspace/skin_refs): contrast per feature size
PHOTO = {"octaves_mm": [0.35, 0.7, 1.4, 2.8, 5.6, 11.2], "L": [1.2, 1.26, 0.83, 0.78, 1.2, 2.15],
         "a": [0.25, 0.29, 0.41, 0.47, 0.51, 0.6], "b": [0.24, 0.26, 0.4, 0.51, 0.62, 0.72], "micro": 0.051,
         "highlight_share": [0.05, 0.13], "highlight_breakup": [1.6, 2.4], "cheek_a": 1.2, "nose_a": 0.9}
VIEWS = {"bust": "head", "face": "head", "three_quarter": "head", "side": "head", "cheek": "head", "eye": "head",
         "mouth": "head", "forehead": "head", "brows": "head", "ear": "head", "hand": "arm", "palm": "arm", "forearm": "arm"}
DEFAULT = ("face", "three_quarter", "cheek", "eye", "mouth", "ear")


def _J(spec: dict) -> dict:
    from .spec import expand_mirror
    return {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}


def stage_name(name: str, region: str) -> str:
    return f"_skin_{name}_{region}"


def stage_spec(spec: dict, region: str, voxel: float | None = None) -> dict:
    """The model cut down to one region's bare skin (and its eyes)."""
    from . import skin
    s = copy.deepcopy(spec)
    part = (s.get("skin") or {}).get("part", "body")
    keep = {part, (s.get("base") or {}).get("eyes") or "eyes"}
    J = _J(spec)
    for kind in ("bones", "blobs", "strokes"):
        s[kind] = {k: v for k, v in (s.get(kind) or {}).items() if v.get("part", "body") in keep}
    for k, j in list((s.get("joints") or {}).items()):  # a joint seated on a dropped part (a button on the shirt)
        if isinstance(j.get("on"), dict) and (j["on"].get("part") or "body") not in keep:
            s["joints"].pop(k)
    gone = lambda at: isinstance(at, str) and at not in s["joints"] and at.replace(".R", ".L") not in s["joints"]
    for kind in ("bones", "blobs"):
        s[kind] = {k: v for k, v in s[kind].items() if not (gone(v.get("at")) or gone(v.get("a")) or gone(v.get("b")))}
    for k in ("hair", "cloth", "kits", "story", "weather", "rig", "plan", "face_shapes"):
        if k == "kits":
            s[k] = {n: v for n, v in (s.get(k) or {}).items() if v.get("part", "body") in keep and v.get("type") not in ("neckline",)}
        else:
            s.pop(k, None)
    s["parts"] = {k: {kk: vv for kk, vv in v.items() if kk not in ("topology", "texel_focus", "atlas")}
                  for k, v in (s.get("parts") or {}).items() if k in keep}
    s["paint"] = {k: v for k, v in (s.get("paint") or {}).items()
                  if set([v.get("part", "body")] if isinstance(v.get("part", "body"), str) else v["part"]) <= keep}
    s.setdefault("blobs", {})
    if region == "head":
        if "head" not in J:
            raise ValueError("look_skin: the model has no head joint")
        top = max(J["head"][2] + 0.14, J.get("lm_nose_bridge", J["head"])[2] + 0.12)
        lo = J.get("neck", J["head"] - [0, 0, 0.16])[2] - 0.1
        if float(((spec.get("base") or {}).get("body") or {}).get("age", 99)) < 18:  # a child: the head and neck only
            # (this stage is bare skin, without the clothes; a child's chest and shoulders are never rendered bare)
            lo = J.get("neck", J["head"] - [0, 0, 0.1])[2] - 0.012
        front = min(J["head"][1] - 0.16, J.get("lm_nose_tip", J["head"])[1] - 0.03)  # clear of the nose tip (a box 2 cm
        back = J["head"][1] + 0.17  # short sliced one head's nose off flat)
        c = [0.0, float((front + back) / 2), float((top + lo) / 2)]
        size = [0.17, float((back - front) / 2), float((top - lo) / 2)]
        vx = 0.001
    elif region == "arm":
        need = ["elbow.L", "wrist.L"]
        if any(n not in J for n in need):
            raise ValueError("look_skin: the model has no arm joints (elbow.L, wrist.L)")
        P = np.array([J[k] for k in J if k.endswith(".L") and k.startswith(("elbow", "wrist", "finger", "thumb"))])
        lo, hi = P.min(0) - 0.05, P.max(0) + 0.05
        c, size = ((lo + hi) / 2).round(4).tolist(), ((hi - lo) / 2).round(4).tolist()
        vx = 0.0009
    else:
        raise ValueError(f"look_skin: no region {region!r} (head, arm)")
    s["blobs"]["skin_look_crop"] = {"at": c, "shape": "box", "size": size, "op": "intersect", "blend": 0.0, "part": part}
    s["parts"].setdefault(part, {})
    s["parts"][part]["voxel"] = float(voxel or min(vx, s["parts"][part].get("voxel", 1.0)))
    s.pop("symmetry", None) if False else None
    return s


def ensure(name: str, region: str, log: list, voxel: float | None = None) -> str:
    """The region's stage model, saved and synced when the model changed since. Returns its name."""
    from . import scene, stylesheet
    spec = store.load(name)
    st = stage_spec(spec, region, voxel)
    sn = stage_name(name, region)
    key = hashlib.sha1(json.dumps([st, Path(scene.SCRIPT).read_bytes().hex()[:0]], sort_keys=True, default=str).encode()).hexdigest()[:16]
    d = store._dir(sn)
    mark = d / "skin_look.key"
    code = hashlib.sha1(b"".join((Path(__file__).parent / f).read_bytes() for f in
                                 ("skin.py", "skin_features.py", "skin_makeup.py", "skin_swatch.py", "paint.py", "paintnodes.py",
                                  "blender_scene.py", "base.py", "headfit.py", "skin_look.py"))).hexdigest()[:12]
    if mark.exists() and mark.read_text() == key + code and scene.blend_path(sn).exists():
        return sn
    t = time.time()
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(stylesheet.strip(st) if hasattr(stylesheet, "strip") else st))
    r = scene.sync(sn, resolution=256)
    mark.write_text(key + code)
    log.append(f"{region}: synced in {time.time() - t:.0f} s ({', '.join(f'{k} {v}' for k, v in r['seconds'].items())})")
    return sn


def cameras(spec: dict) -> dict:
    """Every view's camera {"eye", "target", "fov"} + its light preset and region, from the model's joints."""
    J = _J(spec)
    out = {}
    if "lm_nose_tip" in J:
        nt = J["lm_nose_tip"]
        from .skin import interocular
        io = interocular(J)
        k = io / 0.0863
        ear = J["lm_jaw_0.R"] + np.array([-0.01, 0.025, 0.02]) * k
        eye = J.get("eye_front.R", J["lm_lid_upper.R"])
        mouth = J["lm_lip_seam"]
        fh = J["lm_nose_bridge"] + np.array([0, 0.0, 0.75 * io])
        out.update({
            "bust": (nt + [0, -1.0 * k, 0.0], nt + [0, 0, -0.03], 24, "studio"),
            "face": (nt + [0, -0.62 * k, 0.0], nt + [0, 0, 0.012], 22, "studio"),
            "three_quarter": (nt + np.array([-0.36, -0.5, 0.03]) * k, nt + [0, 0.05, 0.012], 22, "studio"),
            "side": (nt + np.array([-0.62, 0.08, 0.0]) * k, nt + [0, 0.08, 0.012], 22, "studio"),
            "cheek": (nt + np.array([-0.17, -0.25, 0.0]) * k, nt + np.array([-0.04, 0.03, 0.0]) * k, 14, "studio"),
            "eye": (eye + np.array([-0.03, -0.22, 0.01]) * k, eye + [0, 0, 0.004], 13, "soft"),
            "mouth": (mouth + np.array([-0.04, -0.24, 0.0]) * k, mouth, 14, "studio"),
            "forehead": (fh + np.array([-0.06, -0.24, 0.05]) * k, fh, 16, "studio"),
            "brows": (J["lm_nose_bridge"] + np.array([0.0, -0.3, 0.03]) * k, J["lm_nose_bridge"] + [0, 0, 0.012 * k], 17, "soft"),
            "ear": (ear + np.array([-0.3, -0.12, 0.0]) * k, ear, 20, "back")})
    if "wrist.L" in J and "finger2_0.L" in J:
        from .skin import _palm_normal
        pn = _palm_normal(J, ".L")
        w = J["wrist.L"]
        c = 0.5 * (w + J["finger2_3.L"])  # the whole hand, fingertips and nails in frame
        up = J["finger2_1.L"] - w
        up = (up / np.linalg.norm(up)).tolist()
        out["hand"] = (c - 0.46 * pn, c, 26, "studio", up)
        out["palm"] = (c + 0.46 * pn, c, 26, "soft", up)
        if "elbow.L" in J:
            m = 0.45 * J["elbow.L"] + 0.55 * w
            ax = w - J["elbow.L"]
            ax /= np.linalg.norm(ax)
            side = -pn - ax * float(-pn @ ax)
            side /= max(np.linalg.norm(side), 1e-9)
            out["forearm"] = (m + 0.34 * side, m, 22, "studio", ax.tolist())
    return {n: {"eye": np.asarray(c[0], float).tolist(), "target": np.asarray(c[1], float).tolist(), "fov": c[2], "light": c[3],
                **({"up": c[4]} if len(c) > 4 else {})} for n, c in out.items()}


def _project(cam, p, size):
    eye, tg = np.array(cam["eye"]), np.array(cam["target"])
    f = (tg - eye) / np.linalg.norm(tg - eye)
    r = np.cross(f, [0, 0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    d = np.asarray(p) - eye
    z = d @ f
    k = (size / 2) / np.tan(np.radians(cam["fov"]) / 2)
    return np.array([size / 2 + k * (d @ r) / z, size / 2 - k * (d @ u) / z]), k / z


def face_boxes(spec: dict, cam: dict, size: int) -> tuple[dict, float]:
    """Skin-only boxes (forehead, cheek on the lit side, nose, chin) in a front view of the face, and mm per pixel."""
    from .skin import interocular
    J = _J(spec)
    io = interocular(J)

    def box(p, w, h):
        (x, y), k = _project(cam, p, size)
        return [x - w * io * k / 2, y - h * io * k / 2, x + w * io * k / 2, y + h * io * k / 2], 1000 / k
    b = {}
    b["forehead"], mm = box(J["lm_nose_bridge"] + io * np.array([0, 0.0, 0.75]), 1.3, 0.5)
    b["cheek_lit"], _ = box(J["lm_lid_lower.R"] + io * np.array([-0.1, 0, -0.6]), 0.5, 0.5)
    b["nose"], _ = box(0.5 * (J["lm_nose_bridge"] + J["lm_nose_tip"]) + [0, -0.01, -0.005], 0.24, 0.55)
    b["chin_jaw"], _ = box(J["lm_chin"] + io * np.array([0, 0, 0.22]), 0.6, 0.25)
    return b, mm


def look(name: str, views=DEFAULT, size: int = 768, light: str | None = None, flat: bool = False,
         layer: str | None = None, measure: bool = True, save: str | None = None, engine: str = "eevee"):
    """Render the views (see VIEWS) and measure the face. Returns (sheet image, text, {view: image})."""
    from PIL import Image
    from . import paint, render, scene, skin
    views = list(views)
    bad = [v for v in views if v not in VIEWS]
    if bad:
        raise ValueError(f"look_skin: unknown views {bad} (have {', '.join(VIEWS)})")
    if light is not None and light not in LIGHTS:
        raise ValueError(f"look_skin: light is one of {', '.join(LIGHTS)}")
    spec = store.load(name)
    cams = cameras(spec)
    miss = [v for v in views if v not in cams]
    if miss:
        raise ValueError(f"look_skin: this model has no joints for {miss} (a base body with a GNM head gives the face's lm_* "
                         f"landmarks and the hand joints)")
    log, imgs = [], {}
    t0 = time.time()
    need_face = measure and "face" not in views and "lm_nose_tip" in _J(spec) and any(VIEWS[v] == "head" for v in views)
    for region in dict.fromkeys(VIEWS[v] for v in views):
        sn = ensure(name, region, log)
        vs = [v for v in views if VIEWS[v] == region] + (["face"] if need_face and region == "head" else [])
        for lt in dict.fromkeys(light or cams[v]["light"] for v in vs):
            group = [v for v in vs if (light or cams[v]["light"]) == lt]
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                frames = []
                for i, v in enumerate(group):
                    f = render.camera_frame({k: cams[v][k] for k in ("eye", "target", "fov", "up") if k in cams[v]}, i)
                    f["out"] = str(Path(tmp) / f"{v}.png")
                    frames.append(f)
                job = {"mode": "render", "blend": str(scene.blend_path(sn)), "views": frames, "size": size, "hide": [],
                       "flat": flat, "samples": 16,
                       "lighting": {**LIGHTS[lt], "target": [round(float(x), 4) for x in cams[group[0]]["target"]]}}
                if engine == "cycles" and not flat and not layer:  # path traced: real subsurface scattering
                    job.update(engine="cycles", samples=64)
                if layer:
                    from . import paintnodes
                    st = store.load(sn)
                    names = list(paint.layers(st))
                    full = layer if layer in names or any(n.startswith(layer + ":") for n in names) else f"skin:{layer}"
                    if full not in names:
                        raise ValueError(f"look_skin: no layer {layer!r}; skin layers: {', '.join(n[5:] for n in names if n.startswith('skin:'))}")
                    job.update(show_layer=full, program=paintnodes.compile(st),
                               bases={p: {"color": [0.5] * 3, "roughness": 0.6, "metallic": 0.0, "specular": 0.5}
                                      for p in list(st.get("parts") or {}) + ["body"]})
                scene._blender(job, 1800)
                for v, f in zip(group, frames):
                    im = Image.open(f["out"])
                    if layer:
                        bg = Image.new("RGBA", im.size, (140, 150, 165, 255))
                        im = Image.alpha_composite(bg, im.convert("RGBA"))
                    imgs[v] = im.convert("RGB").copy()
    cols = min(len(views), 3)
    rows = (len(views) + cols - 1) // cols
    from PIL import ImageDraw
    sheet = Image.new("RGB", (cols * size, rows * size), (20, 22, 26))
    for i, v in enumerate(views):
        sheet.paste(imgs[v], ((i % cols) * size, (i // cols) * size))
        ImageDraw.Draw(sheet).text(((i % cols) * size + 6, (i // cols) * size + 4), v + (f" [{layer}]" if layer else ""), fill=(255, 255, 255))
    if save:
        sheet.save(save)
    text = [f"rendered {', '.join(views)} in {time.time() - t0:.0f} s" + ("; " + "; ".join(log) if log else "")]
    sk = spec.get("skin")
    if sk:
        p = skin.params(spec)
        base = skin.part_base(spec)[1]
        n = sum(1 for k in paint.layers(spec) if k.startswith("skin:"))
        text.append(f"skin: melanin {p['tone']['melanin']:.2f} blood {p['tone']['blood']:.2f} undertone {p['tone']['undertone']:+.1f}, "
                    f"age {p['age']:.0f}; base #{''.join(f'{int(round(c * 255)):02x}' for c in base['color'])} roughness "
                    f"{base['roughness']:.2f}, subsurface {base['subsurface']:.1f} x {base['subsurface_scale'] * 1000:.1f} mm; {n} layers")
    else:
        text.append("no spec.skin on this model: the `skin` tool sets one (tone, age, features, make-up)")
    rep = None
    if measure and "face" in imgs and not flat and not layer:
        boxes, mm = face_boxes(spec, cams["face"], size)
        rep = skin_measure.patch_report(imgs["face"], boxes, mm)
        text.append(report_text(rep))
    look.report, look.images = rep, imgs
    return sheet, "\n".join(text), imgs


def report_text(rep: dict) -> str:
    """The face view's measurements beside the photographs' (see PHOTO)."""
    oc = PHOTO["octaves_mm"]
    out = ["measured on the face view (skin-only boxes: forehead, lit cheek, nose, chin) vs photographs of real faces (median of 13):",
           "  feature size mm     " + "".join(f"{o:>7}" for o in oc)]
    for ch, what in (("L", "lightness "), ("a", "red-green "), ("b", "yel-blue  ")):
        v = rep["bands"].get(ch) or []
        out.append(f"  {what} ours   " + "".join(f"{x:>7.2f}" if x is not None else "      -" for x in v[:len(oc)]))
        out.append(f"  {what} photos " + "".join(f"{x:>7.2f}" for x in PHOTO[ch]))
    z = rep.get("zones") or {}
    zs = "; ".join(f"{n} a{v['d']['a']:+.1f} b{v['d']['b']:+.1f}" for n, v in z.items() if "d" in v)
    out.append(f"  colour zones vs forehead (a = redder, b = yellower): {zs}  (photos: cheek a +1.2, nose a +0.9; up to +7 on ruddy faces)")
    hs = [h for h in (rep.get("highlight") or {}).values() if h.get("breakup") is not None]
    h = max(hs, key=lambda x: x["share"]) if hs else None
    out.append("  highlight: " + (f"{h['share'] * 100:.0f}% of the patch, blobs {h['blob_mm']} mm, breakup {h['breakup']}" if h else "none in the boxes")
               + "  (photos: 5-13%, blobs 1-10 mm, breakup 1.6-2.4; breakup ~1 = a smooth plastic highlight)")
    out.append(f"  micro contrast (<= 0.7 mm): {rep.get('micro')}  (photos 0.05; under 0.01 reads airbrushed)")
    hints = []
    L, a = rep["bands"].get("L") or [], rep["bands"].get("a") or []
    if L and L[0] is not None and L[0] < 0.3:
        hints.append("fine relief is weak: raise skin.detail (or check the view is close enough to resolve it)")
    if a and len(a) > 4 and a[4] is not None and a[4] < 0.2:
        hints.append("colour is too even at 3-10 mm: raise skin.variation, add features (freckles, flush, blemishes)")
    if a and len(a) > 4 and a[4] is not None and a[4] > 1.2:
        hints.append("colour is blotchier than any photograph at 3-10 mm: lower skin.variation / the features' amounts")
    if h is None:
        hints.append("no highlight on the face: the skin is too rough or too evenly lit (skin.oil, shading.roughness)")
    if hints:
        out.append("  HINT: " + "; ".join(hints))
    return "\n".join(out)
