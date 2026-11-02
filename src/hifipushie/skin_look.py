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
# a low light from the side: what shows RELIEF (folds, bags, a lid's crease: skin.folds are geometry; skinfolds)
RAKE = {"lights": [{"dir": [0.96, -0.25, 0.12], "energy": 4.0, "color": [1.0, 0.98, 0.96], "angle": 6}],
        "world": {"color": [0.5, 0.5, 0.52], "strength": 0.12}, "view": "Khronos PBR Neutral", "exposure": -0.3}
LIGHTS = {"studio": STUDIO, "soft": SOFT, "back": BACK, "rake": RAKE}
# what 13 photographs of faces measured (skin_measure, medians; workspace/skin_refs): contrast per feature size
PHOTO = {"octaves_mm": [0.35, 0.7, 1.4, 2.8, 5.6, 11.2], "L": [1.2, 1.26, 0.83, 0.78, 1.2, 2.15],
         "a": [0.25, 0.29, 0.41, 0.47, 0.51, 0.6], "b": [0.24, 0.26, 0.4, 0.51, 0.62, 0.72], "micro": 0.051,
         "highlight_share": [0.05, 0.13], "highlight_breakup": [1.6, 2.4], "cheek_a": 1.2, "nose_a": 0.9}
VIEWS = {"bust": "head", "face": "head", "three_quarter": "head", "side": "head", "cheek": "head", "eye": "head",
         "mouth": "head", "forehead": "head", "brows": "head", "ear": "head", "hand": "arm", "palm": "arm", "forearm": "arm"}
EYE_VOXEL = float(__import__("os").environ.get("HIFIPUSHIE_EYE_VOXEL", "0.0005"))  # m: the head stage's orbits (lids, folds,
# brows) are meshed this fine (an env value >= the stage voxel turns the refinement off)
SEAM_VOXEL = float(__import__("os").environ.get("HIFIPUSHIE_SEAM_VOXEL", "0.0002"))  # m: the closed lips' seam is meshed this fine
DEFAULT = ("face","three_quarter", "cheek", "eye", "mouth", "ear")


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
    if region == "head" and "eye.L" in J and "eye.R" in J and EYE_VOXEL < s["parts"][part]["voxel"]:
        # the orbits, lids to brows, finer (scene.refine_box): at 1 mm the lid margins came out ragged and the
        # lid's folds and rims (2-3 mm features) were a voxel or two wide
        e = np.array([J["eye.L"], J["eye.R"]])
        # (with a tear trough laid, skin.folds: down to the trough under the bag, ~2 cm under the eye)
        low = 0.024 if ((spec.get("skin") or {}).get("folds") or {}).get("tear_trough") else 0.016
        s["parts"][part]["refine"] = [{"lo": [round(float(e[:, 0].min()) - 0.024, 4), round(float(e[:, 1].min()) - 0.03, 4),
                                              round(float(e[:, 2].min()) - low, 4)],
                                       "hi": [round(float(e[:, 0].max()) + 0.024, 4), round(float(e[:, 1].max()) + 0.004, 4),
                                              round(float(e[:, 2].max()) + 0.026, 4)], "voxel": EYE_VOXEL}]
        if all(k in J for k in ("lm_mouth_corner.L", "lm_mouth_corner.R", "lm_lip_upper", "lm_lip_lower")):
            # the mouth too: the lips' colour is laid per vertex, and at 1 mm their border came out as a fringe ("fur")
            m = np.array([J["lm_mouth_corner.L"], J["lm_mouth_corner.R"], J["lm_lip_upper"], J["lm_lip_lower"]])
            s["parts"][part]["refine"].append({"lo": [round(float(m[:, 0].min()) - 0.006, 4), round(float(m[:, 1].min()) - 0.006, 4),
                                                      round(float(m[:, 2].min()) - 0.008, 4)],
                                               "hi": [round(float(m[:, 0].max()) + 0.006, 4), round(float(m[:, 1].max()) + 0.012, 4),
                                                      round(float(m[:, 2].max()) + 0.008, 4)], "voxel": EYE_VOXEL})
            if "lm_lip_seam" in J and SEAM_VOXEL < EYE_VOXEL:
                # the closed lips' SEAM: the two lip surfaces touch within a voxel, and at 0.5 mm marching cubes cut it into a
                # jagged line with hairline gaps (the lips' unshaded inner faces showed through: a pale zigzag at the
                # parting on every head). A thin box along the seam meshed finer
                zc = float(J["lm_lip_seam"][2])
                s["parts"][part]["refine"].append({"lo": [round(float(m[:, 0].min()) - 0.003, 4), round(float(m[:, 1].min()) - 0.004, 4), round(zc - 0.0022, 4)],
                                                   "hi": [round(float(m[:, 0].max()) + 0.003, 4), round(float(m[:, 1].max()) + 0.008, 4), round(zc + 0.0022, 4)],
                                                   "voxel": SEAM_VOXEL})
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
                                 ("skin.py", "skin_features.py", "skin_makeup.py", "skin_marks.py", "skin_swatch.py", "paint.py", "paintnodes.py",
                                  "blender_scene.py", "base.py", "headfit.py", "skin_look.py"))).hexdigest()[:12]
    if mark.exists() and mark.read_text() == key + code and scene.blend_path(sn).exists():
        mark.touch()  # last use, for store.prune_stages
        return sn
    t = time.time()
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(stylesheet.strip(st) if hasattr(stylesheet, "strip") else st))
    r = scene.sync(sn, resolution=256)
    mark.write_text(key + code)
    store.prune_stages("_skin_", "skin_look.key", keep=sn)
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
         layer: str | None = None, measure: bool = True, save: str | None = None):
    """Render the views (see VIEWS) and measure the face. Returns (sheet image, text, {view: image})."""
    from PIL import Image
    from . import paint, render, scene, skin
    views = list(views)
    bad = [v for v in views if v not in VIEWS]
    if bad:
        raise ValueError(f"look_skin: unknown views {bad} (have {', '.join(VIEWS)})")
    if light is not None and light not in LIGHTS and light != "photo":
        raise ValueError(f"look_skin: light is one of {', '.join(LIGHTS)}, photo")
    lights = dict(LIGHTS)
    if light == "photo":   # the front reference's fitted light at the picture's exposure (skin_read.photo_light)
        from . import skin_read
        lights["photo"] = {k: v for k, v in skin_read.photo_light(name).items() if k not in ("fitted", "measured")}
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
                       "lighting": {**lights[lt], "target": [round(float(x), 4) for x in cams[group[0]]["target"]]}}
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
    if sk and not skin.shaded(spec):
        text.append(f"skin only {skin.params(spec)['only']}: the skin part keeps its own paint and shading")
    elif sk:
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


def _crop_of(spec: dict, cam: dict, region: str) -> list:
    """The square picture crop [x0, y0, x1, y1] of a region through a fitted camera, on the side facing it."""
    from . import humanfit
    from .skin import interocular
    J = _J(spec)
    io = interocular(J)
    Rc = humanfit._cam_rot(cam)
    c0, t0 = np.asarray(cam["centre"], float), np.asarray(cam["t"], float)
    pos = c0 - Rc.T @ t0                                   # (the camera's own position: skin_read.fitted_frame)
    side = region[-2:] if region[-2:] in (".L", ".R") else (".R" if pos[0] < J["lm_nose_tip"][0] else ".L")
    region = region[:-2] if region[-2:] in (".L", ".R") else region
    sx = -1.0 if side == ".R" else 1.0
    br, tip = J["lm_nose_bridge"], J["lm_nose_tip"]
    at, half = {"forehead": (br + io * np.array([0, 0, 0.75]), 0.8), "brows": (br + io * np.array([0, 0, 0.1]), 1.05),
                "eye": (J.get("eye_front" + side, J["lm_lid_upper" + side]), 0.5),
                "cheek": (J["lm_lid_lower" + side] + io * np.array([0.1 * sx, 0, -0.6]), 0.5),
                "nose": (0.5 * (br + tip), 0.62), "mouth": (J["lm_lip_seam"], 0.62),
                "jaw": (J["lm_chin"] + io * np.array([0, 0, 0.25]), 0.7)}[region]
    Xc = Rc @ (np.asarray(at, float) - c0) + t0
    w, h = cam["size"]
    u, v = cam["f"] * Xc[0] / Xc[2] + w / 2, cam["f"] * Xc[1] / Xc[2] + h / 2
    r = min(half * io * cam["f"] / Xc[2], w / 2, h / 2)
    x0, y0 = float(np.clip(u - r, 0, w - 2 * r)), float(np.clip(v - r, 0, h - 2 * r))   # (kept whole: the frame stays square)
    return [x0, y0, x0 + 2 * r, y0 + 2 * r]


def beside(name: str, region: str, view: int | None = None, size: int = 768, light: str | None = None,
           views=None, flat: bool = False, layer: str | None = None):
    """ONE region of the model and of the reference at the same framing: the picture's crop, and the model through that
    picture's fitted camera, under its fitted light at its exposure. The two files are what review_view takes. Returns
    (the two side by side, text). Photo pixels here are for judging: they are written to the workspace only."""
    from PIL import Image
    from . import blockin, resources, skin_read, skin_route
    if views or flat or layer:
        raise ValueError("look_skin: beside is one region, lit like its picture: it takes no views, flat or layer")
    if light not in (None, "photo"):
        raise ValueError("look_skin: beside renders under the picture's own light (light=\"photo\"); another light has no "
                         "reference to stand beside")
    base = region[:-2] if region[-2:] in (".L", ".R") else region
    if base not in skin_route.REGIONS:
        raise ValueError(f"look_skin: beside is one of {', '.join(skin_route.REGIONS)} (.L / .R picks a side)")
    if isinstance(view, int) and not isinstance(view, bool) and view < 0:
        raise ValueError("look_skin: view is a reference picture's index")
    rj, spec = blockin._refs(name), store.load(name)
    vi = blockin._front(rj) if view is None else view
    if vi >= len(rj["views"]) or not rj["views"][vi].get("image") or rj["cameras"][vi] is None:
        raise ValueError(f"look_skin: reference view {vi} has no picture or no fitted camera ({len(rj['views'])} views)")
    cam = rj["cameras"][vi]
    box = skin_read.boxes(name)[vi] if base == "face" else _crop_of(spec, cam, region)
    log: list = []
    lt = skin_read.photo_light(name, vi)
    with resources.heavy(f"look_skin beside {name}", gb=8, gpu=True, log=log.append):
        sn = ensure(name, "head", log)
        px = skin_read.shoot(sn, [skin_read.fitted_frame(cam, box, "v")],
                             {k: v for k, v in lt.items() if k not in ("fitted", "measured")}, size=size)["v"]
    res = Image.alpha_composite(Image.new("RGBA", (size, size), (128, 128, 128, 255)), Image.fromarray(px).convert("RGBA")).convert("RGB")
    ref = Image.open(rj["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((size, size), Image.LANCZOS)
    d = store.HOME / "_looks" / "skin_beside"
    d.mkdir(parents=True, exist_ok=True)
    f_ref, f_res = d / f"{name}_{region}_v{vi}_reference.png", d / f"{name}_{region}_v{vi}_result.png"
    ref.save(f_ref)
    res.save(f_res)
    pair = Image.new("RGB", (2 * size, size))
    pair.paste(ref, (0, 0))
    pair.paste(res, (size, 0))
    side_px = box[2] - box[0]
    text = [f"{region}: reference picture {vi} (left) | the model, its camera and fitted light (right); the crop is {side_px:.0f} picture px"]
    if side_px < 96:
        text.append(f"the picture shows this region at only {side_px:.0f} px: no fine texture can be judged in it")
    if not lt.get("measured"):
        text.append("exposure NOT measured yet (no read has run): lightness here means nothing until skin_from_reference has")
    text.append("bare-skin stage: no hair, no clothes, so the judgement is the skin's")
    text += log
    rest = [r for r in skin_route.REGIONS if r != base]
    args = {"region": base, "reference": str(f_ref), "result": str(f_res), "stage": "skin colour and surface", "not_stages": "hair, clothes, backdrop"}
    text.append(skin_route.next_look(args, rest))
    return pair, "\n".join(text)


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
