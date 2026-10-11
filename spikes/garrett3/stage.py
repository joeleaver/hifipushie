"""stage.py: the DRESSED head stage of a model: skin_look's head crop (bare skin + eyes at ~1 mm) WITH the model's
groom, as its own model `_g3_<name>` (synced when the spec or the skin code changed), and renders of it through any
camera: the references' fitted cameras (humanfit cameras + a pixel crop -> a Blender frame with lens shift) or eye /
target views. Hair is shown by the hair_look job (the spec's locks on the stage's own scalp; nothing saved).
  run.sh stage.py <model> [HAIR=0]   -> syncs the stage, prints timings"""
import copy
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from hifipushie import hair, humanfit, render, scene, skin_look, store, stylesheet

# the photo's light: a big soft source above and in front (shade under the brow, nose, lower lip and chin, the
# cheeks falling off a little to the sides), a weak frontal fill, a pale room
FRONT_LIGHT = {"lights": [{"dir": [0.08, -0.74, 0.67], "energy": 3.3, "color": [1.0, 0.975, 0.95], "angle": 38,
                           "window": {"size": [1.4, 1.0], "distance": 2.2, "gain": 0.2}},
                          {"dir": [0.0, -1.0, 0.05], "energy": 0.7, "color": [1.0, 0.98, 0.97], "angle": 40, "shadow": False,
                           "specular": 0.0}],
               "world": {"color": [0.8, 0.8, 0.8], "strength": 0.45}, "view": "Khronos PBR Neutral", "exposure": -0.55}

# EEVEE's fast GI at FULL resolution (default half): a 1.6 mm lid crease read dark 0.14 at half (Cycles 0.21, the photo
# 0.32), 0.25 at full; ~same time on a head (gnmdetail2). A 1 mm crease reads in neither (0.02-0.07)
STAGE_EEVEE = (json.loads(os.environ["STAGE_EEVEE"]) if os.environ.get("STAGE_EEVEE") else
               {"fast_gi_resolution": "1", "fast_gi_quality": 1.0, "fast_gi_step_count": 16, "fast_gi_ray_count": 4})


def photo_light(name, vi=None):
    """FRONT_LIGHT re-aimed and re-balanced to the front picture's own fitted light (blockin.photo_lighting: the clay
    sheets' light): use it for dressed vs photo comparisons (jw2: the fixed 42-deg key read narrower / harder)."""
    from hifipushie import blockin
    return blockin.photo_lighting(name, FRONT_LIGHT, vi)


POSE = {"lid_upper": 0.0013, "brow_inner": -0.0015, "brow_outer": -0.0012, "smile": -0.0015}  # the photo's (garrett3.POSE)


def desk_light(cam_frame):
    """The painting's light: a warm lamp from picture right / in front of the face, a dim blue room."""
    d = -np.asarray(cam_frame["dir"], float)          # the camera looks along -dir
    up = np.asarray(cam_frame["up"], float)
    right = np.cross(d, up)
    key = 0.85 * right - 0.45 * d + 0.12 * up        # toward the light, from the subject
    fill = -0.6 * right - 0.7 * d + 0.3 * up
    return {"lights": [{"dir": (key / np.linalg.norm(key)).tolist(), "energy": 3.4, "color": [1.0, 0.74, 0.46], "angle": 14},
                       {"dir": (fill / np.linalg.norm(fill)).tolist(), "energy": 0.55, "color": [0.55, 0.68, 1.0], "angle": 50,
                        "shadow": False, "specular": 0.0}],
            "world": {"color": [0.16, 0.2, 0.3], "strength": 0.6}, "view": "Khronos PBR Neutral", "exposure": -0.3}


def stage_name(name, posed=False, tex=None):
    return f"_g3_{name}" + ("_posed" if posed else "") + ("_tex" + "".join(str(i) for i in tex) if tex is not None else "")


def ensure(name, with_hair=True, log=print, posed=False, tex=None):
    """posed: True (the photo's hand-set pose) | a head.pose dict | False. tex: None | [reference views]: the
    reference pictures projected as albedo (likeness_texture) on THIS stage's own head shape."""
    spec = store.load(name)
    st = skin_look.stage_spec(spec, "head")
    hd = st["base"]["head"]
    hd.pop("interior", None)     # a look of the closed mouth: no slit / bag (its ends showed as holes at the corners:
    if float(hd.get("mouth_gap") or 1.0) > 0.0005:  # the stage has no teeth or tongue parts), GNM's own lips (a
        hd.pop("mouth_gap", None)                    # closed mouth_gap stays: GNM's expression is what closes them)
    st["paint"] = {k: v for k, v in (st.get("paint") or {}).items() if "face_mouth_bag" not in json.dumps(v)}
    if posed:
        pf = store.HOME / name / "pose.json"      # the pose its fit was made with (refit.py), else the hand-set one
        own = json.loads(pf.read_text()) if pf.exists() else POSE
        hd["pose"] = {**(hd.get("pose") or {}), **(posed if isinstance(posed, dict) else own)}
    if with_hair and spec.get("hair"):
        st["hair"] = copy.deepcopy(spec["hair"])
        st["parts"]["hair"] = copy.deepcopy((spec.get("parts") or {}).get("hair") or {})
    sn = stage_name(name, bool(posed), tex)
    if tex is not None:
        from hifipushie import likeness_texture as lt
        store._dir(sn).mkdir(parents=True, exist_ok=True)
        plain = ensure(name, with_hair=False, log=log, posed=posed) if os.environ.get("HARMONISE", "1") == "1" else None
        r = lt.make(name, base=st["base"], views=tex, out_dir=str(store._dir(sn)), spec=spec, opacity=1.0,
                    ours=lt.scene_albedo(plain) if plain else None)
        st["paint"].update(r["layers"])
        log(r["text"])
    geo = {k: v for k, v in st.items() if k != "hair"}
    src = Path(skin_look.__file__).parent
    code = hashlib.sha1(b"".join((src / f).read_bytes() for f in
                                 ("skin.py", "skin_features.py", "skin_swatch.py", "paint.py", "paintnodes.py", "blender_scene.py",
                                  "base.py", "headfit.py", "onemesh.py", "images.py", "lashes.py", "blender_lashes.py",
                                  "scene.py", "skin_look.py", "lidfold.py", "sdf.py", "spec.py"))).hexdigest()[:12]
    key = hashlib.sha1(json.dumps(geo, sort_keys=True, default=str).encode()).hexdigest()[:16] + code
    d = store._dir(sn)
    d.mkdir(parents=True, exist_ok=True)
    mark = d / "g3_stage.key"
    (d / "spec.json").write_text(json.dumps(stylesheet.strip(st) if hasattr(stylesheet, "strip") else st))
    if mark.exists() and mark.read_text() == key and scene.blend_path(sn).exists():
        mark.touch()  # last use, for store.prune_stages
        return sn
    t = time.time()
    r = scene.sync(sn, resolution=256)
    mark.write_text(key)
    store.prune_stages("_g3_", "g3_stage.key", keep=sn)
    log(f"stage {sn}: synced in {time.time() - t:.0f} s ({', '.join(f'{k} {v}' for k, v in r['seconds'].items())})")
    return sn


def fitted_frame(cam, crop, name):
    """A humanfit camera {"r", "t", "f", "size", "centre", "yaw"} + a SQUARE pixel crop [x0, y0, x1, y1] of its
    picture -> a render frame (perspective, lens shift)."""
    R = humanfit._cam_rot(cam)
    eye = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
    fwd = R.T @ np.array([0.0, 0.0, 1.0])
    up = R.T @ np.array([0.0, -1.0, 0.0])
    w, h = cam["size"]
    x0, y0, x1, y1 = crop
    side = max(x1 - x0, y1 - y0)
    fov = float(np.degrees(2 * np.arctan(side / 2 / cam["f"])))
    shift = [float(((x0 + x1) / 2 - w / 2) / side), float(-((y0 + y1) / 2 - h / 2) / side)]
    return {"name": name, "eye": eye.tolist(), "dir": (-fwd).tolist(), "up": up.tolist(), "fov": fov, "shift": shift,
            "center": (eye + fwd).tolist(), "near": 0.01, "scale": None, "axes": None}


def view_frames(spec, names=("front", "three_quarter", "profile_right", "profile_left", "three_quarter_other", "low_angle")):
    """Perspective frames round the head (the six views of the judging sheets), from the face landmarks."""
    J = skin_look._J(spec)
    nt = J["lm_nose_tip"]
    c = np.array([0.0, nt[1] + 0.085, nt[2] + 0.03])
    D = {"front": [0, -1, 0.0], "three_quarter": [-0.66, -0.75, 0.05], "profile_right": [-1, 0.0, 0.0],
         "profile_left": [1, 0.0, 0.0], "three_quarter_other": [0.66, -0.75, 0.05], "low_angle": [-0.2, -0.86, -0.47],
         "back": [0.2, 1, 0.1], "top": [0, -0.3, 1]}
    out = []
    for i, n in enumerate(names):
        d = np.asarray(D[n], float)
        d /= np.linalg.norm(d)
        f = render.camera_frame({"eye": (c + d * 1.25).tolist(), "target": (c - [0, 0, 0.02]).tolist(), "fov": 19.0, "name": n}, i)
        out.append(f)
    return out


def shoot(name, frames, lighting, size=768, hair_on=True, engine="eevee", flat=False, samples=24, layer=None, posed=False,
          tex=None, eevee=None):
    """Render frames of the stage (one lighting). Returns {frame name: RGB image}. eevee: scene.eevee overrides by name
    (blender_scene; default STAGE_EEVEE)."""
    sn = ensure(name, posed=posed, tex=tex)
    st = json.loads((store._dir(sn) / "spec.json").read_text())
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
        lt = {**lighting, "target": fr[0]["center"]} if lighting else None
        job = {"blend": str(scene.blend_path(sn)), "views": fr, "size": size, "samples": samples, "hide": [], "flat": flat,
               "transparent": True}
        if lt:
            job["lighting"] = lt
        ee = STAGE_EEVEE if eevee is None else eevee
        if ee:
            job["eevee"] = ee
        if hair_on and st.get("hair"):
            job.update(mode="hair_look", hair=hair.job(sn, st), clay_views=[], id_views=[], look_engine=engine)
        else:
            job.update(mode="render")
            if engine == "cycles":
                job.update(engine="cycles", samples=64)
        if layer:
            from hifipushie import paint, paintnodes
            names = list(paint.layers(st))
            full = layer if layer in names else f"skin:{layer}"
            job.update(mode="render", show_layer=full, program=paintnodes.compile(st),
                       bases={p: {"color": [0.5] * 3, "roughness": 0.6, "metallic": 0.0, "specular": 0.5}
                              for p in list(st.get("parts") or {}) + ["body"]})
        scene._blender(job, 2400)
        for f in fr:
            im = Image.open(f["out"])
            if im.mode == "RGBA":
                bg = Image.new("RGBA", im.size, tuple(int(255 * min(1.0, c * 1.0)) for c in (lighting or {}).get("backdrop", [0.86, 0.86, 0.86])) + (255,))
                im = Image.alpha_composite(bg, im)
            out[f["name"]] = im.convert("RGB").copy()
    return out


if __name__ == "__main__":
    t = time.time()
    print(ensure(sys.argv[1]), f"{time.time() - t:.0f} s")
