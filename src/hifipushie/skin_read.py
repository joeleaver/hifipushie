"""The reference pictures as a MEASUREMENT of the skin (the `skin_from_reference` tool): what the procedural skin has
a parameter for is read off the fitted references and the parameters are set from the read. The picture is never the
albedo (likeness_texture is that test: it bakes the picture's light, brushwork and hair, and seams where no camera
looked); the result is the ordinary procedural skin, clean under any light and from any angle.

The instrument is DIFFERENTIAL. Per fitted reference view:
  P  the picture, cropped to the block-in's box
  R  OUR dressed head (the stage: bare skin + eyes) through the same camera under the picture's own fitted light
  A  our albedo at each pixel's surface point (the paint layers evaluated in Python: `albedo`)
  the picture's albedo  T = A x P / R  (the ratio image: the light, the shading, the scattering and the camera's tone
  curve cancel as far as our head and light stand in for theirs; what is left is where the skins differ).
Reads are region means of T against A, and for everything but the base tone DOUBLE differences: a region against the
face's plain skin in the same picture, so exposure and white balance cancel too. The base tone itself needs an
anchor in the picture (`anchor`): the sclera (ours through the same camera: exposure and white balance), else a
plain neutral backdrop (white balance only: the tone's lightness is kept), else nothing (tone not read).

Trust: a pixel counts where the model shows skin facing its camera (`FACE`), the picture's own parser says skin
(faceparse: no hair, cloth, backdrop), and neither picture nor render is clipped.

  capture(name)            -> the views' frames (P, R, surface points, trust), cached on disk by content
  read(name)               -> the measurements (dict + text)
  fit(name, read)          -> new spec["skin"] + the side-effect report
  apply(name, out=None)    -> read + fit + save (to `out`, or onto `name`)
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np

VERSION = 1
N = 512                 # px across a view's crop (the block-in's box)
FACE = (0.35, 0.7)      # cos between the skin's normal and the way to the camera: no trust .. full
CLIP = (0.02, 0.97)     # picture / render values (0..1, any channel) outside this are clipped: not read
STAGE = "_sr_"          # this reader's own dressed stages (never the look_skin / judging-sheet ones)
# the dressed render's light before it is re-aimed to the picture's own (blockin.photo_lighting): a big soft source
# above and in front, a weak frontal fill, a pale room (the judging sheets' stage light)
LIGHT = {"lights": [{"dir": [0.08, -0.74, 0.67], "energy": 3.3, "color": [1.0, 0.975, 0.95], "angle": 38,
                     "window": {"size": [1.4, 1.0], "distance": 2.2, "gain": 0.2}},
                    {"dir": [0.0, -1.0, 0.05], "energy": 0.7, "color": [1.0, 0.98, 0.97], "angle": 40, "shadow": False,
                     "specular": 0.0}],
         "world": {"color": [0.8, 0.8, 0.8], "strength": 0.45}, "view": "Standard", "exposure": 0.0}
EEVEE = {"fast_gi_resolution": "1", "fast_gi_quality": 1.0, "fast_gi_step_count": 16, "fast_gi_ray_count": 4}


def _lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(lin):
    lin = np.clip(np.asarray(lin, float), 0, None)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def lab(lin):
    """CIE Lab (D65) of LINEAR rgb."""
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = np.clip(np.asarray(lin, float), 0, None) @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


# ---------------------------------------------------------------- the dressed stage

def stage_spec(spec: dict) -> dict:
    """The model's head as bare skin + eyes (skin_look's head crop), mouth closed, no hair: what R is rendered from
    and what the albedo is evaluated on."""
    from . import skin_look
    st = skin_look.stage_spec(spec, "head")
    hd = st["base"]["head"]
    hd.pop("interior", None)
    if float(hd.get("mouth_gap") or 1.0) > 0.0005:
        hd.pop("mouth_gap", None)
    st["paint"] = {k: v for k, v in (st.get("paint") or {}).items() if "face_mouth_bag" not in json.dumps(v)}
    from . import likeness_texture as lt
    st["paint"] = {k: v for k, v in st["paint"].items() if not k.startswith(lt.LAYER)}
    return st


def _code() -> str:
    src = Path(__file__).parent
    return hashlib.sha1(b"".join((src / f).read_bytes() for f in
                                 ("skin.py", "skin_features.py", "skin_makeup.py", "skin_marks.py", "skin_swatch.py", "paint.py",
                                  "paintnodes.py", "blender_scene.py", "base.py", "skin_look.py", "scene.py"))).hexdigest()[:12]


def stage(name: str, spec: dict | None = None, log=print) -> str:
    """The stage model of `name` (or of `spec`, a variant of it), synced when its spec or the skin code changed."""
    from . import scene, store, stylesheet
    st = stage_spec(spec or store.load(name))
    sn = STAGE + name
    key = hashlib.sha1(json.dumps(st, sort_keys=True, default=str).encode()).hexdigest()[:16] + _code()
    d = store._dir(sn)
    d.mkdir(parents=True, exist_ok=True)
    mark = d / "sr_stage.key"
    (d / "spec.json").write_text(json.dumps(stylesheet.strip(st) if hasattr(stylesheet, "strip") else st))
    if mark.exists() and mark.read_text() == key and scene.blend_path(sn).exists():
        mark.touch()
        return sn
    t = time.time()
    scene.sync(sn, resolution=256)
    mark.write_text(key)
    log(f"skin_read: stage {sn} synced in {time.time() - t:.0f} s")
    return sn


def fitted_frame(cam: dict, crop, name: str) -> dict:
    """A fitted camera + a SQUARE pixel crop [x0, y0, x1, y1] of its picture -> a render frame (lens shift)."""
    from . import humanfit
    R = humanfit._cam_rot(cam)
    eye = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
    fwd = R.T @ np.array([0.0, 0.0, 1.0])
    up = R.T @ np.array([0.0, -1.0, 0.0])
    w, h = cam["size"]
    x0, y0, x1, y1 = crop
    side = max(x1 - x0, y1 - y0)
    return {"name": name, "eye": eye.tolist(), "dir": (-fwd).tolist(), "up": up.tolist(),
            "fov": float(np.degrees(2 * np.arctan(side / 2 / cam["f"]))),
            "shift": [float(((x0 + x1) / 2 - w / 2) / side), float(-((y0 + y1) / 2 - h / 2) / side)],
            "center": (eye + fwd).tolist(), "near": 0.01, "scale": None, "axes": None}


def shoot(sn: str, frames: list, lighting: dict | None, size: int = 2 * N, flat: bool = False, samples: int = 24) -> dict:
    """Frames of a stage under one lighting: {frame name: RGBA uint8 array}. flat: the unlit albedo."""
    from PIL import Image
    from . import scene
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
        job = {"blend": str(scene.blend_path(sn)), "views": fr, "size": size, "samples": samples, "hide": [], "flat": flat,
               "transparent": True, "mode": "render", "eevee": EEVEE}
        if lighting and not flat:
            job["lighting"] = {**lighting, "target": fr[0]["center"]}
        scene._blender(job, 2400)
        for f in fr:
            out[f["name"]] = np.asarray(Image.open(f["out"]).convert("RGBA")).copy()
    return out


def boxes(name: str) -> list:
    """Each view's square crop (picture pixels): the block-in's own, else round the fitted landmarks."""
    from . import blockin, store
    rj = blockin._refs(name)
    b = (rj.get("blockin") or {}).get("boxes")
    return [[float(x) for x in q] for q in (b or blockin._boxes(store.load(name)["base"], rj))]


def lighting(name: str, vi: int) -> dict:
    """LIGHT re-aimed and re-balanced to view vi's own fitted light."""
    from . import blockin
    return blockin.photo_lighting(name, LIGHT, vi)


# ---------------------------------------------------------------- the frames

def _picture_masks(img, cam, head) -> dict:
    """The picture's own parse (MediaPipe multiclass, faceparse): probability maps in picture pixels, or {} when the
    parser isn't installed (then only the model's own masks gate the read)."""
    from . import faceparse
    try:
        if not faceparse.available():
            return {}
        return faceparse.masks(img, cam, head, model="mediapipe")[2]
    except Exception:  # noqa: BLE001
        return {}


def capture(name: str, spec: dict | None = None, views: list | None = None, log=print, render: bool = True) -> list:
    """The frames of each fitted reference view: [{"view", "P" (N, N, 3) linear picture, "R" linear dressed render,
    "alpha", "X" world points, "n" world normals, "skin" (the model's skin part there), "eye" (its eyeballs),
    "facing", "parse" {skin, hair, figure..: picture-parser probabilities}, "mm" per pixel, "box", "cam"}].
    spec: a variant of the model's spec to dress the stage with (default: the saved one). render=False: no R."""
    from PIL import Image
    from . import blockin, humanfit, likeness as lk, resources, store
    spec = spec or store.load(name)
    rj = blockin._refs(name)
    bx = boxes(name)
    idx = [i for i in (range(len(rj["views"])) if views is None else views)
           if rj["views"][i].get("image") and rj["cameras"][i] is not None]
    mesh = lk.model_mesh(spec["base"])
    out = []
    shots = {}
    if render:
        with resources.heavy(f"skin_read {name}", gb=6, log=log):
            sn = stage(name, spec, log=log)
            for i in idx:
                shots[i] = shoot(sn, [fitted_frame(rj["cameras"][i], bx[i], "v")], lighting(name, i))["v"]
    for i in idx:
        v, cam, box = rj["views"][i], rj["cameras"][i], bx[i]
        img = Image.open(v["image"]).convert("RGB")
        w, h = cam["size"]
        ib = tuple(int(round(x)) for x in box)
        P = _lin(np.asarray(img.crop(ib).resize((N, N), Image.LANCZOS), float) / 255.0)
        _, k, ps = lk.render(mesh, cam, box, px=N, passes=True)
        zb, nrm, part = ps["zb"], ps["nrm"], ps["part"]
        part = part[..., 0] if part.ndim == 3 else part
        on = np.isfinite(zb)
        ii, jj = np.nonzero(on)
        z = zb[ii, jj]
        u, vv = box[0] + (jj + 0.5) / k, box[1] + (ii + 0.5) / k
        Rc = humanfit._cam_rot(cam)
        Xc = np.c_[(u - w / 2) / cam["f"] * z, (vv - h / 2) / cam["f"] * z, z]
        X = np.zeros((N, N, 3))
        X[ii, jj] = (Xc - np.asarray(cam["t"], float)) @ Rc + np.asarray(cam["centre"], float)
        nw = np.zeros((N, N, 3))
        nw[ii, jj] = nrm[ii, jj] @ Rc
        fac = np.zeros((N, N))
        fac[ii, jj] = -(nrm[ii, jj] * (Xc / np.linalg.norm(Xc, axis=1, keepdims=True))).sum(1)
        pm = _picture_masks(img, cam, mesh)
        parse = {}
        for kname, m in pm.items():
            parse[kname] = np.asarray(Image.fromarray(np.round(m * 255).astype(np.uint8)).crop(ib).resize((N, N), Image.BILINEAR), float) / 255.0
        f = {"view": i, "P": P, "X": X, "n": nw, "skin": on & (np.round(part) == 0), "eye": on & (np.round(part) == 1),
             "facing": fac, "parse": parse, "mm": 1000.0 * float(np.median(z)) / cam["f"] / k, "box": list(box), "cam": cam,
             "image": v["image"], "yaw": float(v.get("yaw", 0.0))}
        if render:
            r = np.asarray(Image.fromarray(shots[i]).resize((N, N), Image.LANCZOS), float) / 255.0
            f["R"], f["alpha"] = _lin(r[..., :3]), r[..., 3]
        out.append(f)
    return out


def trust(f: dict) -> np.ndarray:
    """0..1 per pixel: the model's skin facing the camera, the picture's parser agreeing it is skin, nothing clipped."""
    t = f["skin"] * np.clip((f["facing"] - FACE[0]) / (FACE[1] - FACE[0]), 0, 1)
    if f["parse"]:
        t = t * np.clip((f["parse"]["skin"] - 0.5) / 0.3, 0, 1) * np.clip((0.4 - f["parse"]["hair"]) / 0.3, 0, 1)
    ps = _srgb(f["P"])
    t = t * ((ps.min(-1) > CLIP[0]) & (ps.max(-1) < CLIP[1]))
    if "R" in f:
        rs = _srgb(f["R"])
        t = t * (f["alpha"] > 0.98) * ((rs.min(-1) > CLIP[0]) & (rs.max(-1) < CLIP[1]))
    return t


# ---------------------------------------------------------------- our albedo, in Python

class Albedo:
    """Our skin's albedo at surface points, as the scene composites it (the "_pre" layers first, then the rest; linear
    colour), for any variant of spec["skin"]: masks are evaluated once per distinct mask definition and reused, so a
    change of colours and strengths costs milliseconds (what the fit iterates on)."""

    def __init__(self, st: dict, X: np.ndarray, n: np.ndarray, log=None):
        from .surface import Points
        self.st = st
        self.part = (st.get("skin") or {}).get("part", "body")
        self.pts = Points(st, X, n, np.zeros(len(X), int), [self.part], 0.001)
        self.pts.footprint = 0.0005
        self.masks: dict = {}
        self.log = log

    def _mask(self, spec: dict, name: str, ly: dict) -> np.ndarray:
        from . import paint
        skip = ("color", "opacity", "roughness", "specular", "metallic", "height", "mix", "part", "_pre", "_detail", "_of")
        gens = {k: v for k, v in ly.items() if k not in skip}
        key = hashlib.sha1(json.dumps([name.endswith(".L"), gens], sort_keys=True, default=str).encode()).hexdigest()
        if key not in self.masks:
            t = time.time()
            self.masks[key] = paint.layer_mask(spec, name, ly, paint._View(self.pts, np.arange(len(self.pts))))
            if self.log and time.time() - t > 2:
                self.log(f"  mask {name}: {time.time() - t:.1f} s")
        return self.masks[key]

    def layers(self, skin: dict | None = None) -> tuple:
        """(spec, [(name, layer)]) of the skin part for this variant of spec["skin"]."""
        from . import paint
        spec = self.st if skin is None else {**self.st, "skin": skin}
        out = []
        for name, ly in paint.layers(spec).items():
            parts = ly.get("part", "body")
            if parts != "*" and self.part not in ([parts] if isinstance(parts, str) else parts):
                continue
            out.append((name, ly))
        return spec, out

    def __call__(self, skin: dict | None = None, skip=(), masks: dict | None = None) -> np.ndarray:
        """(n, 3) linear albedo. skip: layer names ("skin:" left off) or prefixes ending "*" left out; masks: gets
        each layer's opacity x mask."""
        from . import paint, skin as skinmod
        spec, lys = self.layers(skin)
        base = skinmod.part_base(spec)
        col = np.tile(_lin(np.asarray(base[1]["color"], float)[:3]) if base else np.array([0.5, 0.5, 0.5]), (len(self.pts), 1))
        for pre in (True, False):
            for name, ly in lys:
                if bool(ly.get("_pre")) != pre or "color" not in ly or ly["color"] == "image":
                    continue
                short = name[5:] if name.startswith("skin:") else name
                if any(short == s or (s.endswith("*") and short.startswith(s[:-1])) for s in skip):
                    continue
                a = np.clip(float(ly.get("opacity", 1.0)) * self._mask(spec, name, ly), 0, 1)
                if masks is not None:
                    masks[name] = a
                c = _lin(paint.colour(ly["color"]))
                mode = ly.get("mix", "mix")
                if mode == "multiply":
                    col = col * (1 - a[:, None] + a[:, None] * c)
                elif mode == "screen":
                    col = col + a[:, None] * ((1 - (1 - col) * (1 - c)) - col)
                else:
                    col = col + a[:, None] * (c - col)
        return col
