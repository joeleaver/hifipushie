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


def _unlab(L):
    """LINEAR rgb of CIE Lab (D65): lab's inverse."""
    L = np.asarray(L, float)
    fy = (L[..., 0] + 16) / 116
    f = np.stack([fy + L[..., 1] / 500, fy, fy - L[..., 2] / 200], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    Mi = np.linalg.inv(np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]]))
    return xyz @ Mi.T


def _lab_scale(L, k: float):
    """Lab colours of the same surfaces k x as bright (linear)."""
    L = np.asarray(L, float)
    fy = (L[..., 0] + 16) / 116
    f = np.stack([fy + L[..., 1] / 500, fy, fy - L[..., 2] / 200], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * k
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
                                 ("skin.py", "skin_features.py", "skin_makeup.py", "skin_marks.py", "skin_swatch.py", "skin_folds.py", "paint.py",
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


def photo_light(name: str, vi: int | None = None) -> dict:
    """View vi's fitted light (default: the front view's) AT THE PICTURE'S EXPOSURE: `lighting` + "exposure" = the EV
    the last read measured between our render under that light and the picture on the plain skin (`context` stores
    it beside the stage; "measured": False and EV 0 when no read has run). For renders set beside the reference.
    WHY (skinfolds2): blockin.photo_lighting keeps the face's front as bright as its TEMPLATE lights it, which is not
    how bright the photographer exposed it. The judging sheets' template (-0.55 EV, a filmic view) put every dressed
    head ~10 L under its reference, and the same albedo 10 L down reads as a tan."""
    from . import blockin, store
    vi = blockin._front(blockin._refs(name)) if vi is None else vi
    lt = lighting(name, vi)
    ev = None
    try:
        ev = json.loads((store._dir(STAGE + name) / "sr_exposure.json").read_text()).get(str(vi))
    except Exception:  # noqa: BLE001
        pass
    lt["exposure"] = float(ev) if ev is not None else 0.0
    lt["measured"] = ev is not None
    return lt


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
        ys_ = np.nonzero((on & (np.round(part) == 0)).any(1))[0]
        chin_y = box[1] + (float(np.percentile(ys_, 80)) if len(ys_) else 0.8 * N) / k       # picture px: under this is not face
        f = {"view": i, "white_patch": white_patch(_lin(np.asarray(img, float) / 255.0), pm, chin_y),
             "P": P, "X": X, "n": nw, "skin": on & (np.round(part) == 0), "eye": on & (np.round(part) == 1),
             "facing": fac, "parse": parse, "mm": 1000.0 * float(np.median(z)) / cam["f"] / k, "box": list(box), "cam": cam,
             "mm_native": 1000.0 * float(np.median(z)) / cam["f"],
             "image": v["image"], "yaw": float(v.get("yaw", 0.0))}
        if render:
            r = np.asarray(Image.fromarray(shots[i]).resize((N, N), Image.LANCZOS), float) / 255.0
            f["R"], f["alpha"] = _lin(r[..., :3]), r[..., 3]
            f["R2"] = shots[i][..., :3].copy()          # (sRGB uint8, 2N: the lid's fold line is read on it)
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
    if "atlas_conf" in f:      # (the atlas as the source: where a picture vouches for the de-lit albedo)
        t = t * f["atlas_conf"]
    return t


# ---------------------------------------------------------------- the de-lit atlas as the source (projskin)

def atlas_source(spec: dict) -> dict | None:
    """The model's de-lit projection atlas (skin.projection, made by skin_project) as this reader's source: {"albedo"
    (H, W, 3) linear, "conf" (H, W) 0..1 (a picture vouches for the texel directly: not mirrored, not filled), "box",
    "light_colour" {view: rgb}} or None (no projection, a raw one, or one made on another head shape)."""
    from PIL import Image
    from . import images, skin_project
    pj = (spec.get("skin") or {}).get("projection")
    if not (isinstance(pj, dict) and pj.get("albedo") and pj.get("confidence") and pj.get("delight", True)) or skin_project.stale(spec):
        return None
    try:
        a = np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0
        cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0] / 255.0
    except Exception:  # noqa: BLE001
        return None
    return {"albedo": _lin(a), "conf": cf, "box": [float(x) for x in pj["box"]],
            "light_colour": {int(k): np.asarray(v, float) for k, v in (pj.get("light_colour") or {}).items()}}


def atlas_frames(spec: dict, frames: list, src: dict, log=print) -> list:
    """capture(render=False)'s frames with the ATLAS as the picture: on the model's skin P = the de-lit albedo at each
    pixel's surface point (one albedo for every view: light, shading and the views' disagreement already taken out by
    skin_project) and R = OUR albedo there (no render: the instrument stays differential, T = A x P / R = the atlas);
    off the model P stays the photograph (the backdrop anchor reads it). "atlas_conf" gates the trust."""
    from . import skin_project
    st = stage_spec(spec)
    H, W = src["conf"].shape
    u0, v0, u1, v1 = src["box"]
    out = []
    for f in frames:
        sk = f["skin"]
        X, n = f["X"][sk], f["n"][sk]
        u, v, w = skin_project.lookup(spec["base"], X)
        x = np.clip((u - u0) / (u1 - u0) * W - 0.5, 0, W - 1.001)
        y = np.clip((v1 - v) / (v1 - v0) * H - 0.5, 0, H - 1.001)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = x - x0, y - y0

        def bil(img):
            fx_, fy_ = (fx[:, None], fy[:, None]) if img.ndim == 3 else (fx, fy)
            return (img[y0, x0] * (1 - fx_) * (1 - fy_) + img[y0, x0 + 1] * fx_ * (1 - fy_) + img[y0 + 1, x0] * (1 - fx_) * fy_
                    + img[y0 + 1, x0 + 1] * fx_ * fy_)
        P = f["P"].copy()
        P[sk] = bil(src["albedo"])
        cf = np.zeros(sk.shape)
        cf[sk] = bil(src["conf"]) * (w > 0.5)
        R = f["P"].copy()
        R[sk] = Albedo(st, X, n, log=None)()
        g = {**f, "P": P, "R": R, "alpha": (f["skin"] | f["eye"]).astype(float), "atlas_conf": np.clip((cf - 0.4) / 0.3, 0, 1),
             "white_patch": None, "atlas": True, "P_photo": f["P"]}
        out.append(g)
    return out


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
        skip = ("color", "opacity", "roughness", "specular", "metallic", "height", "mix", "part", "_pre", "_detail", "_blink", "_of")
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

    def subset(self, idx: np.ndarray) -> "Albedo":
        """The same model at some of the points (masks already measured are kept)."""
        a = Albedo(self.st, self.pts.pos[idx], self.pts.normal[idx], self.log)
        a.masks = {k: v[idx] for k, v in self.masks.items()}
        return a

    def __call__(self, skin: dict | None = None, skip=(), masks: dict | None = None, scale: dict | None = None) -> np.ndarray:
        """(n, 3) linear albedo. skip: layer names ("skin:" left off) or prefixes ending "*" left out; masks: gets
        each layer's opacity x mask; scale: {layer name ("skin:" left off): per-point factor on its opacity}."""
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
                a = float(ly.get("opacity", 1.0)) * self._mask(spec, name, ly)
                if scale and short in scale:
                    a = a * scale[short]
                a = np.clip(a, 0, 1)
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

    def zone(self, name: str, grow: float = 1.0) -> np.ndarray:
        """A skin zone's mask (0..1) at the points."""
        from . import skin as skinmod
        ly = skinmod.expand_zones(self.st, {"mask": [{"zone": {"name": name, "grow": grow}}]}, "skin_read")
        return self._mask(self.st, f"zone:{name}", ly)


# ---------------------------------------------------------------- the read

ZONES = ("forehead", "temple", "glabella", "nose_bridge", "nose_tip", "nose_wing", "cheek", "cheekbone", "cheek_side",
         "under_eye", "eyelid", "upper_lip", "philtrum", "mouth_corner", "soul_patch", "chin", "jaw", "jowl")
PLAIN = ("forehead", "cheek", "cheekbone", "nose_bridge", "chin")   # the face's plain skin: the double differences' zero
RHO_BLUR = 1.0          # px: picture and render are blurred this much before their ratio (sub-pixel misregistration)
RHO_CLIP = 4.0          # a pixel whose ratio is this far (x) from the view's median is not skin as we model it
MIN_PX = 40             # a region with fewer trusted pixels (weight sum) is NOT READ
SCLERA_PX = 60          # the sclera anchor needs this many pixels in a view
LIGHT_WHITE = np.array([1.0, 0.976, 0.953])   # our stage light's colour (key and fill), for the backdrop anchor
NEUTRAL = 7.0           # a backdrop within this Lab chroma of grey counts as neutral
LIGHT_SPREAD = 0.06     # a view whose picture / render ratio changes colour across the face by this much (rms of log
                        # chroma along the normal) counts half: coloured or mixed light, a painter's palette


def _wmedian(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    if x.ndim == 2:
        return np.array([_wmedian(x[:, c], w) for c in range(x.shape[1])])
    o = np.argsort(x)
    c = np.cumsum(w[o])
    return float(x[o][min(np.searchsorted(c, 0.5 * c[-1]), len(x) - 1)])


def _eye_classes(f: dict, mesh: dict, spec: dict) -> tuple:
    """(sclera, iris) pixel masks of a frame, from the eyeballs' own geometry (the angle off the gaze)."""
    ht = mesh["state"]["head"]
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    fwd = fwd / np.linalg.norm(fwd)
    r = float(ht.get("eye_r", 0.012))
    from . import base as _basemod
    ir = _basemod.drawn_iris(spec, 0.012, legacy=0.0059 / 0.012)   # skin.eyes.iris_size, GNM's limbus, else 11.8 mm
    a_iris = np.arcsin(min(ir / r, 0.99))
    scl, iris = np.zeros(f["eye"].shape, bool), np.zeros(f["eye"].shape, bool)
    X = f["X"][f["eye"]]
    if not len(X):
        return scl, iris
    ang = np.full(len(X), np.pi)
    for c in ht["eyes"]:
        d = X - np.asarray(c, float)
        dn = np.linalg.norm(d, axis=1)
        a = np.arccos(np.clip((d @ fwd) / np.maximum(dn, 1e-9), -1, 1))
        ang = np.where(np.abs(dn - r) < 0.004, np.minimum(ang, a), ang)
    scl[f["eye"]] = ang > 1.3 * a_iris
    iris[f["eye"]] = (ang > 0.5 * a_iris) & (ang < 0.88 * a_iris)
    return scl, iris


WHITE_ALBEDO = 0.8      # a white shirt / collar / paper: what the lightness anchor takes its albedo to be
WHITE_PX = 250          # it needs this many pixels in a view's crop
WHITE_CHROMA = 9.0      # ... within this Lab chroma of grey (after the backdrop's white balance, when there is one)
TONE_BOUND = 3.0        # L*: how far the plain skin's albedo may move from the PRIOR tone's without an exposure anchor
TONE_BOUND_WHITE = 8.0  # ... and with a known white in the picture (its albedo and its light are INFERRED: 0.8, lit as the face)
TONE_CHROMA = 5.0       # Lab a*b*: how far the plain skin's COLOUR may move from the prior's on a backdrop's white balance (a
                        # backdrop "neutral within 7" may be 7 of real colour: Garrett's painted one read his skin +9 b*, and
                        # exposed like the picture the head came out 5 b* too yellow: "orange")
TONE_CHROMA_WHITE = 10.0
TONE_SIGMA = 1.0        # L*: the solve's hold on the prior's lightness (the bound is checked after it)
TONE_SIGMA_WHITE = 12.0   # (the white leads, the bound holds: at 4 the prior took two thirds of what the white said)
WHITE_SIGMA = 0.15      # log: what a white's exposure is worth


WHITE_BACKDROP = 0.8    # a "white" darker than this x a neutral backdrop in the same picture is a pale grey thing, not a white
WHITE_OVER_SKIN = 1.1   # ... and it is brighter than the lit skin by this (albedo 0.8 against at most ~0.65)


def white_patch(img: np.ndarray, parse: dict, chin_y: float, box=None) -> dict | None:
    """The candidate white of a WHOLE picture (linear rgb, (h, w, 3)): what the parser calls clothing (or the figure
    that is neither skin nor hair) under the face, bright and unclipped: {"Y" (the median of its lit 40 %), "rgb",
    "px", "where" [x0, y0, x1, y1]}; with `box` (picture px [x0, y0, x1, y1]): that patch, as DECLARED by the caller
    (no parser). None: nothing there. Whether it IS a white is `_white`'s call (neutral, brighter than skin and
    backdrop). (skinfolds: the search ran inside the head crop, where a collar never is; it never fired.)"""
    Yv = np.array([0.2126, 0.7152, 0.0722])
    h, w = img.shape[:2]
    if box is not None:
        x0, y0, x1, y1 = (int(round(v_)) for v_ in box)
        m = np.zeros((h, w), bool)
        m[max(y0, 0):y1, max(x0, 0):x1] = True
    else:
        if not parse:
            return None
        cloth = parse["cloth"] if "cloth" in parse else np.clip(parse["figure"] - parse["skin"] - parse["hair"], 0, 1)
        m = np.asarray(cloth) > 0.6
        m[: int(max(chin_y, 0))] = False               # under the chin only (no hat, no headband)
    srgb = _srgb(img)
    m &= (srgb.max(-1) < CLIP[1]) & (srgb.min(-1) > (0.2 if box is not None else 0.35))
    if m.sum() < WHITE_PX:
        return None
    c = img[m]
    y = c @ Yv
    lit = c[y >= np.percentile(y, 60)]
    med = np.median(lit, 0)
    ys, xs = np.nonzero(m)
    return {"Y": float(med @ Yv), "rgb": med, "px": int(m.sum()), "declared": box is not None,
            "where": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]}


def _white(f: dict, wb=None, backdrop_Y: float | None = None, declared: dict | None = None) -> tuple:
    """(white | None, why): a view's KNOWN WHITE (the lightness anchor: skin albedo = its albedo x skin / white, the
    white taken to be lit as the face is: INFERRED). Found (white_patch: clothing under the face) it must be NEUTRAL
    (Lab chroma < WHITE_CHROMA after the backdrop's white balance `wb`), bright (L* > 62), brighter than the lit skin
    and no darker than WHITE_BACKDROP x a neutral backdrop (a pale grey shirt is not a white: Garrett's lilac-grey one
    reads half his backdrop). declared: {"box": [x0, y0, x1, y1] picture px, "albedo": 0.8}: the caller says this
    patch is white (paper, a shirt, a wall): taken at its word."""
    Yv = np.array([0.2126, 0.7152, 0.0722])
    if declared is not None:
        from PIL import Image
        img = _lin(np.asarray(Image.open(f["image"]).convert("RGB"), float) / 255.0)
        q = white_patch(img, {}, 0.0, box=declared["box"])
        if q is None:
            return None, f"the declared white {declared['box']} is clipped or too small ({WHITE_PX} px needed)"
        q["albedo"] = float(declared.get("albedo", WHITE_ALBEDO))
        q["lab"] = [round(float(x), 1) for x in lab(q["rgb"])]
        return q, "declared"
    q = f.get("white_patch")
    if q is None:
        return None, "no clothing under the face that is bright and unclipped"
    q = dict(q)
    rgb = np.asarray(q["rgb"], float) / (np.asarray(wb, float) / max(float(np.asarray(wb, float) @ Yv), 1e-9) if wb is not None else 1.0)
    L = lab(rgb * (q["Y"] / max(float(rgb @ Yv), 1e-9)))
    q["lab"] = [round(float(x), 1) for x in L]
    q["albedo"] = WHITE_ALBEDO
    if np.hypot(L[1], L[2]) > WHITE_CHROMA:
        return None, f"the clothing under the face is coloured (Lab {q['lab']}): not a white"
    if L[0] < 62:
        return None, f"the clothing under the face is not bright (L* {L[0]:.0f}): not a white"
    if backdrop_Y is not None and q["Y"] < WHITE_BACKDROP * backdrop_Y:
        return None, (f"the pale clothing under the face (L* {L[0]:.0f}) reads {q['Y'] / backdrop_Y:.2f} x the neutral backdrop: a grey "
                      "thing, not a known white")
    sk = f["P"][trust(f) > 0.5] @ Yv if "P" in f else np.zeros(0)
    if len(sk) > 200 and q["Y"] < WHITE_OVER_SKIN * float(np.percentile(sk, 75)):
        return None, f"the pale clothing under the face (L* {L[0]:.0f}) is no brighter than the lit skin: not a known white"
    return q, "found"


def _anchor(frames: list, mesh: dict, spec: dict, mode: str = "auto") -> dict:
    """The picture's exposure and white balance against our render's: {"kind": "sclera" | "backdrop" | "none",
    "gain": per view [r, g, b] the ratio P / R is divided by, "note"}. sclera: ours through the same camera (both
    exposure and white balance); backdrop: a plain neutral backdrop gives the light's colour (lightness kept)."""
    from scipy import ndimage
    Y = np.array([0.2126, 0.7152, 0.0722])
    sc, bd, bdY = {}, {}, {}
    for f in frames:
        scl, _ = _eye_classes(f, mesh, spec)
        ok = scl & (f["alpha"] > 0.98) & (_srgb(f["P"]).max(-1) < CLIP[1]) & (_srgb(f["R"]).max(-1) < CLIP[1])
        if ok.sum() >= SCLERA_PX:
            p, r = f["P"][ok], f["R"][ok]
            pb, rb = p[p @ Y >= np.median(p @ Y)], r[r @ Y >= np.median(r @ Y)]   # the lit half of each: lashes and
            sc[f["view"]] = (np.median(pb, 0) / np.maximum(np.median(rb, 0), 1e-4), int(ok.sum()))  # lid shadows differ
        if f["parse"]:
            bg = ndimage.binary_erosion((f["parse"]["figure"] < 0.3) & (f["alpha"] < 0.02), iterations=4)
            if bg.sum() > 400:
                c = f["P"][bg]
                L = lab(c)
                med = np.median(L, 0)
                m = np.median(c, 0)
                # neutral in Lab AND in its channels' ratio (a dark blue wall has little Lab chroma), and lit
                if (np.hypot(med[1], med[2]) < NEUTRAL and np.percentile(np.abs(L[:, 0] - med[0]), 80) < 8 and med[0] > 40
                        and m.max() / max(m.min(), 1e-4) < 1.3):
                    bd[f["view"]] = (m / (m @ Y)) / (LIGHT_WHITE / (LIGHT_WHITE @ Y))
                    bdY[f["view"]] = float(m @ Y)
    if mode == "sclera" and sc:   # (not in "auto": on photographs the sclera reads 0.5-0.6 x ours against the skin and its
        # colour differs view to view; it failed as an anchor, see docs/notes/skin.md "## skinread")
        g = np.median([v[0] for v in sc.values()], 0)   # one camera set-up for a reference set: one gain
        return {"kind": "sclera", "gain": {f["view"]: (sc[f["view"]][0] if f["view"] in sc else g) for f in frames},
                "note": f"sclera through the same camera in view(s) {sorted(sc)} ({', '.join(str(v[1]) for v in sc.values())} px): "
                        "exposure and white balance; the tone's lightness rests on the sclera being lit as ours is (INFERRED)"}
    if mode in ("auto", "backdrop") and bd:
        return {"kind": "backdrop", "gain": {f["view"]: bd.get(f["view"]) for f in frames}, "level": True, "backdrop_Y": bdY,
                "note": f"plain neutral backdrop in view(s) {sorted(bd)}: white balance only (the exposure stays free)" +
                        ("" if len(bd) == len(frames) else "; the other view(s) have their own light and no anchor: their plain skin "
                         "is set to the anchored views' (they give zones, lips and folds, not the tone)")}
    return {"kind": "none", "gain": {f["view"]: None for f in frames},
            "note": "no anchor (no readable sclera, no plain neutral backdrop): the base tone is NOT READ; zones, lips and "
                    "marks are read against the face's own plain skin"}


class Context:
    """The pooled trusted pixels of every view with the picture's albedo there, and the forward model to fit to."""


def context(name: str, spec: dict | None = None, frames: list | None = None, anchor: str = "auto", log=print, white=None) -> Context:
    from scipy import ndimage
    from . import likeness as lk, store
    spec = spec or store.load(name)
    src = atlas_source(spec) if frames is None else None
    if src is not None:       # the de-lit atlas is the picture (no stage, no render): docs/notes/skin.md "## projskin"
        frames = atlas_frames(spec, capture(name, spec, log=log, render=False), src, log=log)
    frames = frames or capture(name, spec, log=log)
    mesh = lk.model_mesh(spec["base"])
    an = _anchor([{**f, "P": f.get("P_photo", f["P"])} for f in frames], mesh, spec, anchor if anchor not in ("prior", "white") else "auto")
    wh, wh_why = {}, {}
    decl = {int(d_["view"]): d_ for d_ in (white or [])}
    if anchor != "prior":
        for f in frames:
            q, why = _white(f, an["gain"].get(f["view"]) if an["kind"] == "backdrop" else None, (an.get("backdrop_Y") or {}).get(f["view"]),
                            decl.get(f["view"]))
            wh_why[f["view"]] = why
            if q is not None:
                wh[f["view"]] = q
    if an["kind"] == "none" and wh:      # no backdrop: the white gives the light's colour too
        Y_ = np.array([0.2126, 0.7152, 0.0722])
        an = {"kind": "white", "level": True,
              "gain": {f["view"]: ((wh[f["view"]]["rgb"] / (wh[f["view"]]["rgb"] @ Y_)) / (LIGHT_WHITE / (LIGHT_WHITE @ Y_)) if f["view"] in wh else None)
                       for f in frames},
              "note": f"a white (shirt / collar) in view(s) {sorted(wh)}: white balance from it"}
    X, n, w, vw, rho, pix = [], [], [], [], [], []
    views = []
    src_lc = {}
    if frames and frames[0].get("atlas"):
        src_lc = (atlas_source(spec) or {}).get("light_colour", {})
        an["note"] = ("SOURCE: the de-lit projection atlas (skin_project): one albedo for every view, light and shading already out; "
                      "ours = our albedo evaluated at the same surface points (no render). " + an["note"])
    for f in frames:
        t = trust(f)
        sel = t > 0.3
        pb = np.stack([ndimage.gaussian_filter(f["P"][..., c], RHO_BLUR) for c in range(3)], -1)
        rb = np.stack([ndimage.gaussian_filter(f["R"][..., c], RHO_BLUR) for c in range(3)], -1)
        r = pb[sel] / np.maximum(rb[sel], 1e-4)
        X.append(f["X"][sel]); n.append(f["n"][sel]); w.append(t[sel]); rho.append(r)
        vw.append(np.full(sel.sum(), f["view"])); pix.append(np.flatnonzero(sel.ravel()))
        views.append({"view": f["view"], "image": f["image"], "mm_per_px": round(f.get("mm_native", f["mm"]), 3), "trusted_px": int(sel.sum())})
    c = Context()
    c.name, c.spec, c.frames, c.anchor, c.mesh = name, spec, frames, an, mesh
    c.X, c.n, c.w, c.view, c.rho, c.pix = (np.concatenate(a) for a in (X, n, w, vw, rho, pix))
    c.st = stage_spec(spec)
    c.alb = Albedo(c.st, c.X, c.n, log=log)
    c.A0 = c.alb()
    plain = np.max([c.alb.zone(z) for z in PLAIN], 0)
    c.plain = plain
    Yv = np.array([0.2126, 0.7152, 0.0722])
    carried = []           # the anchored views' plain skin, picture over ours (per channel): what an unanchored view is set to
    for v in sorted(views, key=lambda v_: an["gain"][v_["view"]] is None):
        m = c.view == v["view"]
        g = an["gain"][v["view"]]
        pm = m & (plain > 0.5)
        if pm.sum() < MIN_PX:
            pm = m
        med = _wmedian(c.rho[pm], c.w[pm])
        f_ = next(q_ for q_ in frames if q_["view"] == v["view"])
        if f_.get("atlas"):
            # the atlas' plain skin has the tone skin_project fitted its lights with (the model's own): its HUE is free
            # only where something else says what colour the light was. A neutral backdrop does: the fitted light's
            # colour over the backdrop's = how far the skin's colour is from the model's tone. One correction for the
            # whole atlas (the median over the anchored views), then the lightness levelled as ever.
            cors = []
            for q_ in frames:
                bd_, lc_ = an["gain"].get(q_["view"]) if an["kind"] == "backdrop" else None, src_lc.get(q_["view"])
                if bd_ is not None and lc_ is not None:
                    true = np.asarray(bd_, float) * LIGHT_WHITE
                    cr = np.asarray(lc_, float) / (true / (true @ Yv))
                    cors.append(cr / (cr @ Yv))
            if cors:
                cor = np.median(cors, 0)
                c.rho[m] = c.rho[m] * cor
                med = med * cor
                g = np.full(3, float(med @ Yv))
                v["atlas_tone"] = [round(float(x), 3) for x in cor]
            else:
                g = med                                   # no anchor: the tone is not read (T == A on the plain skin)
        elif g is None:
            # no anchor of its own: its plain skin's mean is ours (T == A there), or the anchored views' when there are some
            g = med / (np.median(carried, 0) if carried else 1.0)
        elif an.get("level"):
            g = np.asarray(g) * float(med @ Yv) / float(np.asarray(g) @ Yv)   # white balance only
            carried.append(med / g)
        c.rho[m] = c.rho[m] / np.asarray(g)
        v["gain"] = [round(float(x), 3) for x in np.asarray(g)]
        # the light's colour across the face: log chroma of the ratio along the normal (white light on our light: none)
        lr = np.log(np.maximum(c.rho[pm], 1e-4))
        ch = lr - lr.mean(1, keepdims=True)
        Nn = np.c_[np.ones(pm.sum()), c.n[pm]]
        co, *_ = np.linalg.lstsq(Nn * c.w[pm][:, None], ch * c.w[pm][:, None], rcond=None)
        v["light_spread"] = round(float(np.sqrt((((Nn[:, 1:] - Nn[:, 1:].mean(0)) @ co[1:]) ** 2).mean())), 3)
        v["weight"] = round(1.0 / (1.0 + (v["light_spread"] / LIGHT_SPREAD) ** 2), 3)
        far = np.abs(np.log(np.maximum(c.rho[m] @ Yv, 1e-4)) - np.log(max(float(_wmedian(c.rho[pm] @ Yv, c.w[pm])), 1e-4))) > np.log(RHO_CLIP)
        ww = c.w[m]
        ww[far] = 0.0
        c.w[m] = ww * v["weight"]
        # the picture's exposure against our render under the fitted light, on the plain skin (photo_light uses it)
        v["ev"] = round(float(np.log2(max(float(_wmedian((c.rho[pm] * np.asarray(g)) @ Yv, c.w[pm] + 1e-9)), 1e-4))), 3)
    c.views = views
    try:
        from . import store as _store
        d_ = _store._dir(STAGE + name)
        if d_.exists():
            (d_ / "sr_exposure.json").write_text(json.dumps({str(v_["view"]): v_["ev"] for v_ in views}))
    except Exception:  # noqa: BLE001
        pass
    # THE LIGHTNESS ANCHOR (skinfolds). A picture does not say how light a skin is (exposure x albedo). In this order:
    #   1. the PRIOR: the model's stated tone (skin.tone: a Fitzpatrick type or its own numbers). The picture then
    #      corrects hue and saturation only; the plain skin's lightness stays within TONE_BOUND of the prior's.
    #   2. a KNOWN WHITE in the picture (shirt collar; `_white`): skin albedo = WHITE_ALBEDO x skin / white. It moves
    #      the lightness off the prior, at most TONE_BOUND_WHITE (the white's albedo and light are inferred).
    #   (the sclera stays out: lid and lash shadow, 0.45-0.9 x; a grey backdrop gives the white balance, no level)
    an["tone_prior"] = [round(float(x), 2) for x in lab(_wmedian(c.A0[plain > 0.5], c.w[plain > 0.5] + 1e-9))] if (plain > 0.5).any() else None
    an["exposure"], an["lightness"] = None, "prior"
    if wh:
        es, wts = [], []
        for v in views:
            q = wh.get(v["view"])
            m = (c.view == v["view"]) & (plain > 0.5) & (c.w > 0)
            if q is None or m.sum() < MIN_PX:
                continue
            f = next(f_ for f_ in frames if f_["view"] == v["view"])
            py = (f["P"].reshape(-1, 3)[c.pix[m]] @ Yv)
            # (the LIT skin against the white's lit part: the 75th percentile of the plain skin, as the white's own
            # upper 40 %: a face's median sits in more shade than a shirt front's bright half)
            want = q["albedo"] * float(np.percentile(py, 75)) / q["Y"]          # the plain skin's albedo luminance
            have = float(np.percentile((c.A0[m] * c.rho[m]) @ Yv, 75))
            es.append(np.log(max(want, 1e-4) / max(have, 1e-4)))
            wts.append(v["weight"] * q["px"])
            v["white"] = {"px": q["px"], "lab": q["lab"], "skin_albedo_Y": round(want, 3), "where": q["where"], "albedo": q["albedo"],
                          "declared": bool(q.get("declared"))}
        if es:
            an["exposure"] = float(np.average(es, weights=wts))
            an["lightness"] = "white"
            an["exposure_spread"] = round(float(np.std(es)), 3) if len(es) > 1 else None
    an["note"] += ("\n  LIGHTNESS: " + (
        f"a known white in view(s) {sorted(k for k in wh)} (" + "; ".join(f"view {k}: {'DECLARED' if q_.get('declared') else 'found: clothing under the face'} at "
                                                                         f"{q_['where']} px, Lab {q_['lab']}, taken as albedo {q_['albedo']}" for k, q_ in sorted(wh.items())) +
        f"; lit as the face: INFERRED) puts the plain skin "
        f"{100 * (np.exp(an['exposure']) - 1):+.0f} % from where the levelled read had it; the tone's lightness may move up to {TONE_BOUND_WHITE} L* "
        f"from the prior" if an["lightness"] == "white" else
        f"no exposure anchor in the pictures: the tone's lightness is held to the PRIOR (the model's stated skin.tone, plain skin "
        f"L* {an['tone_prior'][0] if an['tone_prior'] else '?'}) within {TONE_BOUND} L*; the pictures correct its hue and saturation only"
        + ("" if anchor == "prior" else " (a white was looked for: " + "; ".join(f"view {k}: {w_}" for k, w_ in sorted(wh_why.items())) +
           "; a backdrop is no exposure anchor: its albedo and its own light are unknown. Point at a known white with white=[{view, box, albedo}])")))
    c.T = c.A0 * c.rho
    c.dlab = lab(c.T) - lab(c.A0)
    c.J = None
    return c


SHADE_Q = (0.7, 1.35)    # the shade's colour exponents are kept within this (1 = neutral shade)
SHADE_SIGMA = 1.5        # log: how freely a region's lightness is given to SHADE the head does not cast (a deeper-set
                         # eye, the jaw's turn from the light, a light the fit got wrong) rather than to pigment (at 0.6
                         # a third of Tess's lid shade still pulled on the lid tints: 3.4 L of 15)
PRUNE = 0.25             # half chi2 units: a parameter's move worth less than this to the fit is taken back
PRIOR_TONE = 6.0         # x PRIOR for the tone's three numbers: melanin / blood / undertone trade against each other
                         # (the same colour from many triples); loose, blood ran to 0 on Tess and every layer that
                         # multiplies the tone's blood (lips, lids, flush) went inert, the lips brown from melanin alone
SHADE_SIGMA_PLAIN = 0.05  # ... on the plain zones (the lit skin the exposure is levelled on)
SHADE_SIGMA_BEARD = 0.05  # ... where a beard may be laid: its shadow IS a lightness (little colour of its own)
SHADE_MAX = 0.7          # log: no region is more than this in shade (about -20 L*)
EXPOSURE_SIGMA = 0.2     # log: the free exposure without a white (the read is already levelled on the plain skin, and the
                         # model's plain L* is held to the prior: what is left to it is small. At 0.6 it traded against shade:
                         # on the synthetic F2 head exposure went to x 0.40 with every other region "26-32 L in shade")
SHADE_LOCAL = 0.03       # log: the hold on the shaded regions' lower quartile (shade is local)
SHADE_SAY = 0.1          # log: shade from here on is named in the reply
FACE_BOUND = 3.0         # L*: the WHOLE face's mean albedo (stubble apart) may leave the prior's by this much
ATLAS_SHADE_SIGMA = 0.15  # ... when the source is the de-lit ATLAS: the light and the head's own occlusion are already out,
                          # so what a region reads darker is pigment or a form the head lacks, not a wrong light: the
                          # tints may take it (Stage 2's forms take back what is form)
ATLAS_ZONE_BOUND = (12.0, 8.0)   # ... and the zones may leave the prior further (the measurement is one albedo, all views agreed)
ZONE_BOUND = (4.0, 5.0)  # L*, a*b*: a zone's offset from the face's mean may leave the prior's by this much (pigment that
                         # no exposure anchor and no shade model vouches for); the zone layers are scaled back to it


def shade_colour(c: Context) -> np.ndarray:
    """The COLOUR OF SHADE in these pictures, measured: over the trusted skin (lips and brows apart) the slopes q of
    log(picture / ours) per channel on its luminance's. Neutral shade: 1, 1, 1. Photographs of skin: about 0.85, 1.03,
    1.18 (Tess: red falls least, blue most: bounce light off skin and scatter warm a face's shade; a painter does the
    same on purpose). A region darker than our render predicts ALONG this line is shade (or a tan: the picture cannot
    tell them apart, the prior tone does); what leaves the line (redder, yellower, greyer) is skin colour."""
    if getattr(c, "_shade_q", None) is None:
        Yv = np.array([0.2126, 0.7152, 0.0722])
        m = (c.w > 0)
        try:
            m &= (c.alb.zone("lips", 1.4) < 0.05) & (c.alb.zone("brow", 2.5) < 0.05)
        except Exception:  # noqa: BLE001
            pass
        q = np.ones(3)
        if m.sum() >= 5000:
            lr = np.log(np.maximum(c.rho[m], 1e-4))
            x = np.log(np.maximum(c.rho[m] @ Yv, 1e-4))
            x = x - _wmedian(x, c.w[m])
            ok = (x > -0.7) & (x < 0.3)
            if ok.sum() >= 5000 and float(x[ok].std()) > 0.04:
                W = np.sqrt(c.w[m][ok])
                A_ = np.c_[x[ok], np.ones(ok.sum())] * W[:, None]
                q = np.array([np.linalg.lstsq(A_, lr[ok][:, k] * W, rcond=None)[0][0] for k in range(3)])
                med = _wmedian(c.T[m], c.w[m])
                q = q / max(float((q * med * Yv).sum() / (med * Yv).sum()), 1e-3)      # (so that exp(s q) is s in luminance)
                q = np.clip(q, *SHADE_Q)
        c._shade_q = q
    return c._shade_q


def _region(c: Context, wz: np.ndarray, views: bool = True) -> dict:
    """A region's read: the picture's albedo against ours over the region's trusted pixels."""
    W = c.w * wz
    s = float(W.sum())
    if s < MIN_PX:
        return {"px": round(s, 1), "read": False}
    d = _wmedian(c.dlab, W)
    ours = lab((c.A0 * W[:, None]).sum(0) / s)
    out = {"px": round(s, 1), "read": True, "ours": [round(float(x), 1) for x in ours],
           "picture": [round(float(x), 1) for x in ours + d], "d": [round(float(x), 2) for x in d]}
    if views and len(c.views) > 1:
        out["by_view"] = {}
        for v in c.views:
            m = c.view == v["view"]
            if W[m].sum() >= MIN_PX:
                out["by_view"][v["view"]] = [round(float(x), 2) for x in _wmedian(c.dlab[m], W[m])]
    return out


def regions(c: Context) -> dict:
    """{region: weights over the pooled points}: the skin's zones, the two lips, the beard's zones."""
    if getattr(c, "_regions", None) is None:
        from . import skin as skinmod, skin_marks
        R = {z: c.alb.zone(z) for z in ZONES}
        lips, low = c.alb.zone("lips", 0.8), c.alb.zone("lip_lower", 0.8)
        for z in ZONES:
            R[z] = R[z] * (1 - lips)
        R["lip_upper"] = (lips * (1 - low)) ** 3
        R["lip_lower"] = low ** 3
        J = skinmod._joints(c.st)
        c.J = J
        if "lm_jaw_1.L" in J:
            bz = skin_marks.beard_zones(J)(c.X)
            dens = skin_marks.beard_density(J, {"trim": 0.0, "cheek_line": 0.0, "neckline": 0.0, "cheeks": 1.0, "patchy": 0.0,
                                                "density": 1.0, "seed": 0})(c.X, c.n)
            c.beard_zones = bz
            for k, u in bz.items():
                R[f"beard:{k}"] = u * dens * (1 - lips)
        c._regions = R
    return c._regions


# ---------------------------------------------------------------- lips: in image space, at the picture's own lips

LIP_YAW = 50.0          # deg: views turned further do not give the detector's lip outline


_MP_LIPS = {"outer_up": [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291], "outer_lo": [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291],
            "inner_up": [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308], "inner_lo": [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]}


def lip_polygons(P) -> dict:
    """{"lip_upper", "lip_lower": (n, 2) polygons} of a picture's own lips from its detector points: MediaPipe's face
    mesh (468+ points: its own lip contours) or the 68 landmarks (outer contour 48-59, inner 60-67)."""
    P = np.asarray(P, float)[:, :2]
    if len(P) >= 468:
        m = _MP_LIPS
        return {"lip_upper": np.r_[P[m["outer_up"]], P[m["inner_up"][::-1]]], "lip_lower": np.r_[P[m["outer_lo"]], P[m["inner_lo"][::-1]]]}
    return {"lip_upper": np.r_[P[48:55], P[64:59:-1]], "lip_lower": np.r_[P[54:60], P[48:49], P[60:61], P[67:63:-1]]}


def _lip_read(c: Context) -> dict:
    """The lips' colour IN IMAGE SPACE, like with like (skinfolds2): the picture's pixels inside ITS OWN lip outline
    (the detector's, a pixel in from the edge) against our render's pixels inside OUR lips, both under the fitted
    light, the picture levelled to our exposure on the plain skin: {region: {"d": Lab picture - ours, "picture",
    "ours", "px", "by_view"}}. Why not the albedo ratio at our lips' pixels: a mouth's shape is never the picture's
    to the millimetre, and where our (fuller) lip lies over the picture's skin the read mixed her upper lip with the
    skin over it: lighter and yellower than her lip (Tess: "orange-brown" for a brown-mauve lip). The rendered lip is
    in the loop by construction: a second round reads what the first one's parameters render as."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    from . import blockin
    out = {}
    try:
        rj = blockin._refs(c.name)
    except Exception:  # noqa: BLE001
        return out
    R = regions(c)
    acc = {"lip_upper": [], "lip_lower": []}
    for f, v in zip(c.frames, c.views):
        # (and only the views whose light is as white as the best one's: a lamp-lit painting's lips, levelled on its
        # skin, read 10 Lab from the front view's; their spread made the lips' sigma so wide that nothing moved)
        if abs(f.get("yaw", 0.0)) > LIP_YAW or "R" not in f or v["weight"] < 0.7 * max(v_["weight"] for v_ in c.views):
            continue
        try:
            P = blockin.detect_view(Image.open(f["image"]).convert("RGB"), rj["views"][f["view"]])
        except Exception:  # noqa: BLE001
            P = None
        if P is None:
            continue
        k = N / (f["box"][2] - f["box"][0])
        g = np.asarray(v["gain"], float)
        m = c.view == f["view"]
        for key, poly in lip_polygons(P).items():
            im = Image.new("L", (N, N), 0)
            ImageDraw.Draw(im).polygon([tuple((np.asarray(q_) - np.asarray(f["box"][:2])) * k) for q_ in poly], fill=255)
            pm = ndimage.binary_erosion(np.asarray(im) > 127, iterations=1)
            ps_ = _srgb(f["P"])
            pm &= (ps_.max(-1) < CLIP[1]) & (ps_.min(-1) > CLIP[0])
            ours = np.zeros(N * N)
            ours[c.pix[m]] = R[key][m]
            om = (ours.reshape(N, N) > 0.5) & (f["alpha"] > 0.98)
            if pm.sum() < MIN_PX or om.sum() < MIN_PX:
                continue
            lp, lo = lab(np.median(f["P"][pm], 0) / g), lab(np.median(f["R"][om], 0))
            acc[key].append((v["weight"] * min(pm.sum(), om.sum()), lp, lo, f["view"], int(pm.sum())))
    for key, rows in acc.items():
        if not rows:
            continue
        w = np.array([r_[0] for r_ in rows])
        lp, lo = np.average([r_[1] for r_ in rows], 0, w), np.average([r_[2] for r_ in rows], 0, w)
        out[key] = {"d": [round(float(x), 2) for x in lp - lo], "picture": [round(float(x), 1) for x in lp], "ours": [round(float(x), 1) for x in lo],
                    "px": int(sum(r_[4] for r_ in rows)), "by_view": {r_[3]: [round(float(x), 2) for x in r_[1] - r_[2]] for r_ in rows}}
    return out


# ---------------------------------------------------------------- fine marks: freckles (image space, per view)

SPECK = (0.35, 1.3)     # mm: the band (two Gaussian sigmas) a freckle lives in
SPECK_T = 0.035         # a speck is this much darker (log luminance) than its surround in that band
SPECK_MM = 0.5          # mm a pixel: coarser pictures cannot show freckles (NOT READ)
SPECK_SIZE = (0.4, 12.0)  # mm2: a speck's area


def _specks(lum: np.ndarray, where: np.ndarray, mm: float) -> float:
    """Dark specks per cm2 of `where` in a luminance image (mm a pixel): connected blobs of the band-passed log
    luminance under -SPECK_T with a freckle's area."""
    from scipy import ndimage
    lg = np.log(np.maximum(lum, 1e-3))
    wf = where.astype(float)
    def blur(s):
        return ndimage.gaussian_filter(lg * wf, s) / np.maximum(ndimage.gaussian_filter(wf, s), 1e-3)
    bp = blur(SPECK[0] / mm) - blur(SPECK[1] / mm)
    inner = ndimage.binary_erosion(where, iterations=max(int(round(1.5 / mm)), 1))
    lab_, n = ndimage.label((bp < -SPECK_T) & inner)
    if not n or inner.sum() < 200:
        return 0.0
    area = ndimage.sum(np.ones_like(lab_), lab_, np.arange(1, n + 1)) * mm * mm
    return float(((area >= SPECK_SIZE[0]) & (area <= SPECK_SIZE[1])).sum() / (inner.sum() * mm * mm / 100.0))


def _freckle_read(c: Context) -> dict:
    """Freckles: dark specks per cm2 on cheeks, nose and forehead, the picture against our render (same camera and
    light), and the same count on our albedo with and without the freckle layer (what one unit of amount gives)."""
    Yv = np.array([0.2126, 0.7152, 0.0722])
    zone = np.max([c.alb.zone(z) for z in ("cheek", "cheekbone", "nose_bridge", "nose_tip", "forehead")], 0) > 0.5
    sk = copy.deepcopy(c.st.get("skin") or {})
    fr = (sk.get("features") or {}).get("freckles")
    have = float(fr if isinstance(fr, (int, float)) else (fr or {}).get("amount", 1.0 if fr else 0.0)) if fr else 0.0
    proto = have if have > 0.02 else 0.3
    with_ = copy.deepcopy(sk)
    with_.setdefault("features", {})
    if have <= 0.02:
        with_["features"]["freckles"] = {"amount": proto}
    without = copy.deepcopy(sk)
    (without.get("features") or {}).pop("freckles", None)
    A1, A0 = c.alb(with_), c.alb(without)
    out = {"have": round(have, 3), "views": {}, "read": False}
    num = den = 0.0
    for f, v in zip(c.frames, c.views):
        if f.get("mm_native", f["mm"]) > SPECK_MM:
            out["views"][f["view"]] = f"NOT READ ({f.get('mm_native', f['mm']):.2f} mm a pixel: freckles need {SPECK_MM} or finer)"
            continue
        m = c.view == f["view"]
        w2 = np.zeros(N * N, bool)
        w2[c.pix[m]] = zone[m] & (c.w[m] > 0)
        w2 = w2.reshape(N, N)
        if w2.sum() < 2000:
            continue
        def img(a, m=m):
            q = np.zeros(N * N)
            q[c.pix[m]] = a[m] @ Yv
            return q.reshape(N, N)
        sp, sr_, s1, s0 = _specks(f["P"] @ Yv, w2, f["mm"]), _specks(f["R"] @ Yv, w2, f["mm"]), _specks(img(A1), w2, f["mm"]), _specks(img(A0), w2, f["mm"])
        out["views"][f["view"]] = {"picture": round(sp, 2), "ours": round(sr_, 2), "albedo_with": round(s1, 2), "albedo_without": round(s0, 2)}
        if s1 - s0 > 0.3:
            ours_fr = sr_ if have > 0.02 else sr_ + (s1 - s0)   # the render's count had it the prototype's freckles
            num += v["weight"] * (proto * (sp - (ours_fr - (s1 - s0))) / (s1 - s0))
            den += v["weight"]
    if den > 0:
        out.update(read=True, amount=round(float(np.clip(num / den, 0, 2)), 3), proto=proto)
    return out


# ---------------------------------------------------------------- brows, irises

def _brow_read(c: Context) -> dict:
    """Brow hair from the picture's albedo: its colour (the darkest third of the band) and how much of it there is
    (the band's mean darkness under the skin above it), each against ours."""
    Yv = np.array([0.2126, 0.7152, 0.0722])
    band = c.alb.zone("brow", 1.7)
    wide = c.alb.zone("brow", 3.2)
    W = c.w * (band > 0.5)
    ring = c.w * ((wide > 0.05) & (band < 0.2)) * (c.X[:, 2] > np.median(c.X[band > 0.5][:, 2]) if (band > 0.5).any() else 0)
    if W.sum() < MIN_PX or ring.sum() < MIN_PX:
        return {"read": False, "why": "the brows are not in trusted skin (hair over them, turned away)"}
    out = {"read": True, "px": round(float(W.sum()), 0)}
    res = {}
    for key, col in (("picture", c.T), ("ours", c.A0)):
        lum = col @ Yv
        skin_c = _wmedian(col[ring > 0], ring[ring > 0])
        sel = W > 0
        thr = np.quantile(lum[sel], 0.33)
        dk = sel & (lum <= thr)
        dark_c = _wmedian(col[dk], W[dk])
        dness = float(((np.clip(1 - lum[sel] / max(skin_c @ Yv, 1e-4), 0, 1)) * W[sel]).sum() / W[sel].sum())
        res[key] = {"skin": skin_c, "dark": dark_c, "darkness": dness}
        out[key] = {"dark_Lab": [round(float(x), 1) for x in lab(dark_c)], "darkness": round(dness, 3)}
    out["colour_ratio"] = [round(float(x), 3) for x in np.clip(res["picture"]["dark"] / np.maximum(res["ours"]["dark"], 1e-4), 0.3, 3.0)]
    ko = 1 - (res["ours"]["dark"] @ Yv) / max(res["ours"]["skin"] @ Yv, 1e-4)
    kp = 1 - (res["picture"]["dark"] @ Yv) / max(res["picture"]["skin"] @ Yv, 1e-4)
    out["coverage_ratio"] = round(float(np.clip((res["picture"]["darkness"] / max(res["ours"]["darkness"], 1e-3)) / max(kp / max(ko, 1e-3), 0.2), 0.3, 3.0)), 3)
    return out


def _eye_read(c: Context) -> dict:
    """Iris and sclera colour: the picture against our render through the same camera, each relative to the plain
    skin beside it (so the exposure cancels; a lid's shadow on the picture's eye does not: INFERRED)."""
    out = {}
    for cls, i in (("sclera", 0), ("iris", 1)):
        rs, n = [], 0
        for f, v in zip(c.frames, c.views):
            m = _eye_classes(f, c.mesh, c.spec)[i] & (f["alpha"] > 0.98) & (_srgb(f["P"]).max(-1) < CLIP[1]) & (_srgb(f["R"]).max(-1) < CLIP[1])
            if m.sum() < (SCLERA_PX if cls == "sclera" else SCLERA_PX // 2):
                continue
            rs.append(np.median(f["P"][m], 0) / np.maximum(np.median(f["R"][m], 0), 1e-4) / np.asarray(v["gain"]))
            n += int(m.sum())
        out[cls] = {"read": bool(rs), "px": n, **({"ratio": [round(float(x), 3) for x in np.median(rs, 0)]} if rs else {})}
    return out


def _iris_rel(name: str, c: Context) -> dict:
    """THE IRIS AGAINST THE SCLERA BESIDE IT, picture over ours (readmix, 2026-10-13): what sets skin.eyes.iris.
    PICTURE: at the picture's OWN iris (blockin_eyes.limbus: the limbus circle found on the picture; the ring's colour
    along rays in the two lateral sectors, where no lid covers it) and the sclera just outside the limbus on the same
    rays, its BRIGHT part (a picture's sclera lies half under lid and lash shadow: Tess's front reads luminance 0.08 /
    0.16 / 0.25 at its 20 / 50 / 80 %). OURS: the render's eyeball pixels by the model's own geometry. Both tried and
    wrong on Tess: the model's geometry on the PICTURE (its eye opening is not the picture's: lid skin in the ring, a warm
    cast: the iris came out orange-brown whatever the start), and the sclera's median (in shadow: the iris too light).
    Views turned past 50 deg or with an iris under IRIS_R_PX of radius are left out. -> {"read", "ratio" (linear, per
    channel), "views", "px"}."""
    from PIL import Image
    from . import blockin, blockin_eyes as be, lidfold
    from .likeness_eyes import frame
    rj = blockin._refs(name)
    rel, npx = [], 0
    for f in c.frames:
        vi = int(f["view"])
        v = rj["views"][vi]
        if abs(float(v.get("yaw", 0.0) or 0.0)) > 50.0:
            continue
        scl, iris = _eye_classes(f, c.mesh, c.spec)
        ok = (f["alpha"] > 0.98) & (_srgb(f["R"]).max(-1) < CLIP[1])
        scl, iris = scl & ok, iris & ok
        if iris.sum() < SCLERA_PX // 2 or scl.sum() < SCLERA_PX:
            continue
        ours = np.median(f["R"][iris], 0) / np.maximum(np.median(f["R"][scl], 0), 1e-4)
        try:
            img = Image.open(v["image"]).convert("RGB")
            P = blockin.detect_view(img, v)
            if P is None:
                continue
            lb = be.limbus(img, P)
        except Exception:  # noqa: BLE001
            continue
        A = _lin(np.asarray(img, float) / 255.0)
        H, W = A.shape[:2]
        ex, ey = (np.asarray(x_, float) for x_ in frame(np.asarray(P, float)[:, :2]))
        for e in lb:
            r, cen = float(e["r_px"]), np.asarray(e["centre"], float)
            if r < IRIS_R_PX:
                continue
            ring, white = [], []
            for sg in (-1, 1):
                for a in np.radians(np.arange(-30, 31, 5)):
                    d = sg * (np.cos(a) * ex + np.sin(a) * ey)
                    for q, dst in [(q_, ring) for q_ in np.linspace(0.5, 0.85, 8)] + [(q_, white) for q_ in np.linspace(1.15, 1.7, 10)]:
                        p_ = cen + q * r * d
                        dst.append(A[int(np.clip(round(p_[1]), 0, H - 1)), int(np.clip(round(p_[0]), 0, W - 1))])
            ring, white = np.array(ring), np.array(white)
            lr, lw = ring.mean(1), white.mean(1)
            ring = np.median(ring[(lr <= np.percentile(lr, 80)) & (lr >= np.percentile(lr, 10))], 0)
            white = np.median(white[lw >= np.percentile(lw, 80)], 0)
            if white.mean() < 1.6 * ring.mean():      # no sclera beside this iris (a turned eye's far side, lashes): not a reference
                continue
            rel.append((r * r, (ring / np.maximum(white, 1e-4)) / np.maximum(ours, 1e-4)))
            npx += int(r * r)
    if not rel:
        return {"read": False, "px": 0, "views": 0}
    w = np.array([n_ for n_, _ in rel], float)
    return {"read": True, "px": npx, "views": len(rel),
            "ratio": [round(float(x), 3) for x in np.exp((w[:, None] * np.log(np.maximum(np.array([r_ for _, r_ in rel]), 1e-4))).sum(0) / w.sum())]}


IRIS_R_PX = 10.0          # an iris under this radius (picture px) is not read for colour
IRIS_STEP = (0.2, 5.0)    # the most one read changes the iris' lightness (x); its hue is never clipped per channel
IRIS_Y = (0.012, 0.42)    # linear luminance an iris colour may have (near-black brown .. pale grey-blue)


def iris_colour(c0, ratio) -> str:
    """skin.eyes.iris from the read: the colour now (c0: sRGB 0..1) x the picture's (iris / bright sclera) over ours
    (ratio, linear, per channel). The CHANGE's size is limited as a whole (IRIS_STEP on its luminance) and the result's
    luminance kept in IRIS_Y; the channels keep their proportions. (The old rule clipped each channel to 0.5 .. 2: from
    the default brown a grey-green iris needs x1.5 / x4.5 / x11, which the clip turned into orange-brown.)"""
    lumw = np.array([0.2126, 0.7152, 0.0722])
    l0 = _lin(np.asarray(c0, float)[:3])
    want = l0 * np.asarray(ratio, float)
    y0, y1 = float(l0 @ lumw), float(want @ lumw)
    k = float(np.clip(y1 / max(y0, 1e-6), *IRIS_STEP)) * y0 / max(y1, 1e-6)
    want = want * k
    y = float(want @ lumw)
    want = want * (float(np.clip(y, *IRIS_Y)) / max(y, 1e-6))
    if want.max() > 1.0:
        want = want / want.max()
    return "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in np.clip(_srgb(np.clip(want, 0, 1)), 0, 1))


# ---------------------------------------------------------------- the read

def read(name: str, spec: dict | None = None, frames: list | None = None, anchor: str = "auto", log=print, ctx: Context | None = None,
         white=None) -> dict:
    """The measurements: {"anchor", "views", "regions": {region: {"px", "ours" Lab, "picture" Lab, "d", "by_view"}},
    "freckles", "brows", "eyes", "text", "ctx" (the Context, for `fit`)}."""
    c = ctx or context(name, spec, frames, anchor, log, white=white)
    R = regions(c)
    out = {"anchor": {k: v for k, v in c.anchor.items() if k != "gain"}, "views": c.views,
           "regions": {k: _region(c, wz) for k, wz in R.items()}}
    # the lips: in image space at the picture's own lips (the albedo-ratio read at OUR lips' pixels kept beside it)
    out["lips_image"] = _lip_read(c)
    for key, q in out["lips_image"].items():
        r0 = out["regions"].get(key)
        if r0 and r0.get("read"):
            r0["d_albedo"] = r0["d"]
            r0["d"] = q["d"]
            r0["by_view"] = q["by_view"]
            r0["image"] = {"picture": q["picture"], "ours": q["ours"]}
    out["freckles"] = _freckle_read(c)
    out["brows"] = _brow_read(c)
    atlas = bool(c.frames and c.frames[0].get("atlas"))
    # (from the atlas: no eyeball render and no lit render: the irises are skin_project's read, the folds Stage 2's forms)
    if atlas:
        out["eyes"] = {"sclera": {"read": False, "px": 0}, "iris": {"read": False, "px": 0}}
    else:
        out["eyes"] = _eye_read(c)
        try:
            out["eyes"]["iris_rel"] = _iris_rel(name, c)
        except Exception as e_:  # noqa: BLE001
            out["eyes"]["iris_rel"] = {"read": False, "px": 0, "views": 0, "why": str(e_)[:120]}
    out["folds"] = {} if atlas else fold_read(c)
    out["source"] = "atlas" if atlas else "pictures"
    out["ctx"] = c
    out["text"] = read_text(out)
    return out


def read_text(r: dict) -> str:
    L = [f"SKIN READ (the picture's albedo against ours, CIE Lab; d = picture - ours; anchor: {r['anchor']['kind']})",
         "  " + r["anchor"]["note"]]
    for v in r["views"]:
        L.append(f"  view {v['view']}: {v['mm_per_px']} mm a pixel, {v['trusted_px']} trusted px, weight {v['weight']}"
                 + (f", the picture is exposed {v['ev']:+.2f} EV from our render under its fitted light" if "ev" in v else "")
                 + (f" (the light changes colour across the face: {v['light_spread']})" if v["weight"] < 0.6 else ""))
    L.append(f"  (mm a pixel: the PICTURE's own, at the face) {'region':16s} {'px':>7s}  {'ours L a b':20s} {'picture L a b':20s} d L a b")
    for k, x in r["regions"].items():
        L.append(f"  {k:16s} {x['px']:7.0f}  " + (f"{str(x['ours']):20s} {str(x['picture']):20s} {x['d']}" if x["read"] else "NOT READ")
                 + (f"   <- d in IMAGE SPACE at the picture's own lips: rendered {x['image']['ours']} vs the picture's {x['image']['picture']} "
                    f"(the albedo ratio at our lips' pixels said {x['d_albedo']})" if x.get("image") else ""))
    fr = r["freckles"]
    L.append("  freckles: " + (f"picture asks amount {fr['amount']} (ours {fr['have']})" if fr["read"] else "NOT READ") + f"; specks / cm2 by view: {fr['views']}")
    b = r["brows"]
    L.append("  brows: " + (f"hair colour x {b['colour_ratio']} (picture {b['picture']['dark_Lab']}, ours {b['ours']['dark_Lab']}), coverage x {b['coverage_ratio']}"
                             if b["read"] else f"NOT READ ({b.get('why')})"))
    for k, e in r["eyes"].items():
        L.append(f"  {k}: " + (f"picture / ours {e['ratio']} against the skin ({e['px']} px)" if e["read"] else "NOT READ (too few pixels)"))
    e = r["regions"].get("eyelid") or {}
    if e.get("read") and e["d"][0] < -8:
        L.append(f"  NOTE the upper lids read {-e['d'][0]:.0f} L darker in the pictures than ours under the same light: mostly SHADE our head "
                 "does not cast (a deeper-set eye, brow overhang, lashes) or lid pigment / make-up; the fit gives it to the "
                 "eyelids / periorbital tints only up to their bounds. The rest is geometry (eye depth, hooding), not skin.")
    if r.get("folds"):
        L.append(fold_text(r["folds"]))
    return "\n".join(L)


# ---------------------------------------------------------------- the fit

BOUNDS = {"tone.melanin": (0.0, 1.0), "tone.blood": (0.0, 1.0), "tone.undertone": (-1.0, 1.0),
          "zones.forehead_yellow": (0.0, 3.0), "zones.midface_red": (0.0, 3.0), "zones.nose_red": (0.0, 3.0),
          "zones.perioral_red": (0.0, 3.0), "zones.lower_cool": (0.0, 2.0), "zones.under_eye": (0.0, 2.5),
          "zones.eyelids": (0.0, 2.5), "zones.periorbital": (0.0, 1.5), "features.flush": (0.0, 1.5),
          # (lips.melanin is x the TONE's melanin: on a very fair tone a dark lip needs 10-20. At 9, and lower.melanin no
          # lower than 0.4, Garrett's upper lip stayed 11 L lighter than the painting's: the "stuck" lips. skinfolds)
          "lips.blood": (0.15, 3.0), "lips.melanin": (0.2, 30.0), "lips.lower.blood": (0.3, 2.5), "lips.lower.melanin": (0.1, 2.5), "lips.strength": (0.4, 1.6),
          }
GROUPS = {"tone": ("tone.melanin", "tone.blood", "tone.undertone"),
          "zones": ("zones.forehead_yellow", "zones.midface_red", "zones.nose_red", "zones.perioral_red", "zones.lower_cool",
                    "features.flush"),
          "eyes": ("zones.under_eye", "zones.eyelids", "zones.periorbital"),
          "lips": ("lips.blood", "lips.melanin", "lips.strength", "lips.lower.blood", "lips.lower.melanin"),
          "stubble": (), "brows": (), "freckles": (), "eyeballs": (), "folds": ()}
# ("eyeballs", the iris colour, was not a default until 2026-10-13: on Tess's photographs it turned grey-green irises
# orange-brown: the picture's sclera sits in lid shadow, and the change was clipped per channel. Now read against the
# sclera's bright part with the hue kept (iris_colour): in the default set, so a head no longer keeps the default brown)
DEFAULT_GROUPS = ("tone", "zones", "eyes", "lips", "stubble", "brows", "freckles", "folds", "eyeballs")
SIGMA = (6.0, 0.8, 0.8)     # Lab: what a region's read is worth (lightness carries the shading we do not model)
EXPOSURE = 0.08           # log units: how closely the picture's unknown exposure is held to our skin's lightness. At 0.5
                          # (free) the tone ran DARK: the pigment model reaches a picture's chroma most cheaply by adding
                          # melanin (validation: melanin 0.48 for a truth of 0.30; Garrett came out a tanned
                          # orange-brown). Held, it still runs dark when the picture's skin is far more saturated than the
                          # start (validation: 0.54), stays within ~3 L on the two subjects. The tone's lightness is NOT
                          # a read: check it by eye.
# (also tried: holding the base tone's own L to 1.5. On the far synthetic truth the solve then bent the zones to find the
# chroma: perioral 2.8, flush 1.26, no beard. Taken out.)
BEARD_EVEN = 0.6          # the beard's zone scales are held to their mean this loosely (side zones read lightness, the least
                          # trusted number; free, a jaw at 1 beside cheeks at 0 drew a band with an edge)
LIP_SIGMA_L = 2.5         # the lips' lightness is theirs (a small region, read whole): trusted more than the skin's
IRIS_MM = 0.5             # mm a picture pixel: coarser, an iris is a handful of pixels of lid shadow (Garrett's read x 2)
BROW_COLOUR_MM = 0.8      # coarser, a brow's darkest third is half skin: its colour is not read (its density is)
FIT_POINTS = 50000         # the solve's points (region means do not need every pixel)
PRIOR = 0.04                # the pull back to the start, per share of a parameter's range (least change)
STUBBLE_PROTO = {"amount": 1.0, "style": "short"}
BEARD_MIN = 0.08            # a fitted beard weaker than this share of the prototype is no beard


def _get(sk: dict, path: str):
    from . import skin as skinmod
    a, _, b = path.partition(".")
    if a == "tone":
        return skinmod.tone_params(sk.get("tone"))[b]
    if a == "zones":
        return float((sk.get("zones") or {}).get(b, skinmod.ZONE_LAYERS[b]))
    if path == "features.flush":
        v = (sk.get("features") or {}).get("flush")
        return float(v if isinstance(v, (int, float)) else (v or {}).get("amount", 1.0 if v else 0.0)) if v else 0.0
    if path == "hair.lashes":
        v = (sk.get("hair") or {}).get("lashes", 0.7)
        return float(v if isinstance(v, (int, float)) else (v or {}).get("amount", 1.0)) if v else 0.0
    if a == "lips":
        lp = sk.get("lips") or {}
        return float((lp.get("lower") or {}).get(b[6:], 1.0)) if b.startswith("lower.") else float(lp.get(b, 1.0))
    raise KeyError(path)


def _set(sk: dict, path: str, x: float) -> None:
    from . import skin as skinmod
    a, _, b = path.partition(".")
    x = round(float(x), 4)
    if a == "tone":
        t = skinmod.tone_params(sk.get("tone"))
        t[b] = x
        sk["tone"] = {k: round(float(v), 4) for k, v in t.items()}
    elif a == "zones":
        sk.setdefault("zones", {})[b] = x
    elif path == "features.flush":
        f = sk.setdefault("features", {})
        if isinstance(f.get("flush"), dict):
            f["flush"] = {**f["flush"], "amount": x}
        else:
            f["flush"] = x
        if x <= 0.005:
            f.pop("flush", None)
    elif path == "hair.lashes":
        h = sk.setdefault("hair", {})
        h["lashes"] = {**h["lashes"], "amount": x} if isinstance(h.get("lashes"), dict) else x
    elif a == "lips":
        lp = sk.setdefault("lips", {})
        if b.startswith("lower."):
            lp.setdefault("lower", {})[b[6:]] = x
        else:
            lp[b] = x


def _stubble_opts(sk: dict):
    v = (sk.get("hair") or {}).get("stubble")
    if not v:
        return None
    return {"amount": float(v)} if isinstance(v, (int, float)) else dict(v)


def fit(r: dict, groups=DEFAULT_GROUPS, stubble: bool | None = None, log=print, prior_L: float | None = None, lid_prior: bool = True,
        prior_ab=None, prior_tone: dict | None = None, prior_face: dict | None = None, prior_x: dict | None = None,
        iris_prev=None) -> dict:
    """spec["skin"] set from a read: {"skin": the new description, "changes": [(parameter, old, new, why)], "text",
    "residual": the regions' read before / after as the forward model has it}. groups: what may change (GROUPS).
    stubble: whether a beard shadow may be ADDED to a face that has none (default: unless skin.sex says female)."""
    from scipy.optimize import least_squares
    from . import skin as skinmod, skin_marks
    c: Context = r["ctx"]
    sk0 = copy.deepcopy(c.spec.get("skin") or {})
    sk = copy.deepcopy(sk0)
    R = regions(c)
    anchored = c.anchor["kind"] != "none"
    names = [p for g in groups for p in GROUPS.get(g, ()) if (g != "tone" or anchored)]
    # the beard: the stubble layers' opacity scaled zone by zone (a prototype when the face has none)
    sx = sk.get("sex")
    may = (stubble if stubble is not None else (sx is None or float(sx) > 0.5)) and "stubble" in groups and getattr(c, "beard_zones", None) is not None
    st0 = _stubble_opts(sk)
    proto = False
    if "stubble" in groups and st0 is None and may:
        sk.setdefault("hair", {})["stubble"] = dict(STUBBLE_PROTO)
        proto = True
    st_on = "stubble" in groups and _stubble_opts(sk) is not None
    bz = skin_marks.BEARD_ZONES if st_on else ()
    # the points the fit runs on, and each region's target
    reg = [k for k, x in r["regions"].items() if x["read"]]
    any_w = np.max([R[k] for k in reg], 0) * (c.w > 0)
    idx = np.flatnonzero(any_w > 0.05)
    if len(idx) > FIT_POINTS:   # (small regions whole: lips, lids; the rest thinned)
        small = np.max([R[k] for k in reg if r["regions"][k]["px"] < 6000] or [np.zeros(len(c.w))], 0)[idx] > 0.05
        rest = np.flatnonzero(~small)
        take = np.random.default_rng(0).choice(rest, max(FIT_POINTS - int(small.sum()), 1000), replace=False) if len(rest) > FIT_POINTS else rest
        idx = np.sort(np.r_[idx[small], idx[take]])
    sub = c.alb.subset(idx)
    Wk = {k: (c.w[idx] * R[k][idx]) for k in reg}
    Wk = {k: w / max(w.sum(), 1e-9) for k, w in Wk.items()}
    U = {z: c.beard_zones[z][idx] for z in bz}

    def model(x, sk_=None):
        s = copy.deepcopy(sk) if sk_ is None else sk_
        for p, v in zip(names, x[:len(names)]):
            _set(s, p, v)
        scale = None
        if bz:
            M = sum(float(x[len(names) + i]) * U[z] for i, z in enumerate(bz))
            scale = {"stubble_shadow": M, "stubble": M, "stubble_grey": M}
        A = sub(s, scale=scale)
        return np.array([lab(Wk[k] @ A) for k in reg]), s

    x0 = np.array([_get(sk, p) for p in names] + [0.0 if proto else 1.0] * len(bz), float)
    lo = np.array([BOUNDS[p][0] for p in names] + [0.0] * len(bz))
    hi = np.array([BOUNDS[p][1] for p in names] + [2.5] * len(bz))
    x0 = np.clip(x0, lo + 1e-4, hi - 1e-4)
    m0, _ = model(x0)
    base0 = m0   # (a prototype beard starts at scale 0: the face the read was made against)
    target = base0 + np.array([r["regions"][k]["d"] for k in reg])
    sig = []
    for k in reg:
        bv = list((r["regions"][k].get("by_view") or {}).values())
        sp = np.std(bv, 0) if len(bv) > 1 else np.array([2.0, 0.6, 0.6])
        s0 = (LIP_SIGMA_L, SIGMA[1], SIGMA[2]) if k.startswith("lip_") else SIGMA
        sig.append(np.hypot(s0, sp) / np.sqrt(min(r["regions"][k]["px"], 2000.0) / 2000.0))
    sig = np.array(sig)

    # A white-balance-only anchor gives the picture's albedo up to ONE unknown factor (its exposure): that factor is a
    # free parameter of the solve (held to 1 only weakly), so the tone is found from the skin's chromaticity (in the
    # pigment model a darker skin is a more saturated one) and no layer is bent to explain a lightness nobody measured.
    free_e = "tone" in groups and anchored and bool(c.anchor.get("level"))
    np_ = len(names) + len(bz)
    # the lightness anchor (context): the plain skin's albedo L* is held to the prior tone's (the start's), loosely
    # when a known white gives the exposure; the exposure itself is then free (prior) or the white's.
    Wp = c.w[idx] * ((c.plain[idx] > 0.5) if getattr(c, "plain", None) is not None else np.max([R[z][idx] for z in PLAIN if z in R], 0))
    Wp = Wp / max(Wp.sum(), 1e-9)
    white = c.anchor.get("lightness") == "white" and c.anchor.get("exposure") is not None
    e_mid = float(c.anchor["exposure"]) if white else 0.0
    e_sig = WHITE_SIGMA if white else EXPOSURE_SIGMA
    L_sig, L_bound = (TONE_SIGMA_WHITE, TONE_BOUND_WHITE) if white else (TONE_SIGMA, TONE_BOUND)

    # THE WHOLE FACE (skinfolds2): every skin zone's trusted pixels, stubble apart. Holding the PLAIN zones alone let
    # the eye-zone and lower-face layers run to their limits (Tess: eyelids 2.5, under_eye 2.5, lower_cool 1.9: a mask
    # round the eyes and a darker, yellower lower face at an unchanged "plain" lightness)
    zreg = [k for k in reg if k in ZONES]
    Wf = c.w[idx] * (np.max([R[k][idx] for k in zreg], 0) if zreg else 0.0)
    Wf = Wf / max(Wf.sum(), 1e-9)

    def tone_stats(x):
        """(plain skin Lab, whole face Lab, {zone: its Lab - the face's}) of a candidate, the beard's shadow left out."""
        s_ = copy.deepcopy(sk)
        for p_, v_ in zip(names, x[:len(names)]):
            _set(s_, p_, v_)
        A_ = sub(s_, skip=("stubble*",))
        fl = lab(Wf @ A_)
        return lab(Wp @ A_), fl, {k: lab(Wk[k] @ A_) - fl for k in zreg}

    def plain_lab(x):
        return tone_stats(x)[0]

    def plain_L(x):
        return float(plain_lab(x)[0])

    st_start = tone_stats(np.array([_get(sk, p) for p in names], float))
    ab0 = st_start[0][1:] if prior_ab is None else np.asarray(prior_ab, float)
    C_bound = TONE_CHROMA_WHITE if white else TONE_CHROMA
    if prior_face is None:       # (a later round: still the FIRST round's face)
        prior_face = {"lab": [float(v_) for v_ in st_start[1]], "zones": {k: [float(v_) for v_ in o] for k, o in st_start[2].items()}}
    Lf0 = float(prior_face["lab"][0])

    # SHADE (skinfolds2): a region the picture shows darker than our render predicts is first of all in shade our
    # head does not cast (a deeper-set eye, the jaw turning from a light the fit only roughly knows), not darker
    # skin. Each region's target is the read with a shade s >= 0 taken OUT again, in the pictures' own shade colour
    # (shade_colour: darker AND warmer); s is solved for inside every residual (one number per region, closed form
    # steps), held to nothing but SHADE_SIGMA. Pigment is what remains: colour off the shade line, and lightness
    # where a beard may explain it. Before: Tess's lids (15 L darker than ours under the same light in all three
    # views), jaw and neck (7-10 L) were painted in as eyelid / under-eye / lower-face pigment up to the bounds.
    qs = shade_colour(c)
    Tlin = np.clip(_unlab(target), 1e-5, None)
    # (the PLAIN zones are the lit skin the exposure is levelled on: nearly no shade of their own, or a white's "this
    # skin is darker than you say" would be explained away as shade everywhere)
    s_sig = np.array([0.0 if k.startswith("lip_") else SHADE_SIGMA_BEARD if (k.startswith("beard:") and st_on) else
                      SHADE_SIGMA_PLAIN if k in PLAIN else (ATLAS_SHADE_SIGMA if r.get("source") == "atlas" else SHADE_SIGMA) for k in reg])
    ZB = ATLAS_ZONE_BOUND if r.get("source") == "atlas" else ZONE_BOUND

    def shaded(sv, e):
        return lab(Tlin * np.exp(e + sv[:, None] * qs[None, :]))

    def shade_opt(m, e):
        sv = np.zeros(len(reg))
        on = s_sig > 0
        for _ in range(7):
            t0, t1 = shaded(sv, e), shaded(sv + 1e-3, e)
            r_ = (m - t0) / sig
            Jc = -(t1 - t0) / 1e-3 / sig
            ds = -((Jc * r_).sum(1) + sv / np.maximum(s_sig, 1e-9) ** 2) / ((Jc * Jc).sum(1) + 1.0 / np.maximum(s_sig, 1e-9) ** 2)
            sv = np.where(on, np.clip(sv + ds, 0.0, SHADE_MAX), 0.0)
        return sv

    def resid(x):
        m, _ = model(x[:np_])
        e = float(x[np_]) if free_e else 0.0
        sv = shade_opt(m, e)
        tg = shaded(sv, e)
        bs = x[len(names):np_]
        hold = []
        if free_e:
            pl, fl, _ = tone_stats(x)
            hold = [[len(reg) ** 0.5 * (x[np_] - e_mid) / e_sig, len(reg) ** 0.5 * (float(pl[0]) - L0) / L_sig,
                     len(reg) ** 0.5 * (float(fl[0]) - Lf0) / L_sig]]
        # SHADE IS LOCAL: a face is never all in shade against its own plain skin. A quarter of the regions that may
        # carry shade must carry none (their lower quartile is held to 0). Without it exposure and shade traded on the
        # synthetic heads: exposure x 0.4-0.5 and every region "20-30 L in shade", which is a colour cast along the
        # shade colour by another name (toneval F2: plain zones 20 L off, 21 regions at the cap).
        fr_ = sv[s_sig > 0.1]
        local = [len(reg) ** 0.5 * (float(np.percentile(fr_, 25)) if len(fr_) >= 4 else 0.0) / SHADE_LOCAL]
        return np.concatenate([((m - tg) / sig).ravel(), sv / np.maximum(s_sig, 1e-9) * (s_sig > 0), local,
                               PRIOR * len(reg) ** 0.5 * pw * (x[:np_] - x0[:np_]) / (hi - lo)[:np_]] +
                              ([len(bz) ** 0.5 * (bs - bs.mean()) / BEARD_EVEN] if len(bz) else []) + hold)

    L0 = float(prior_L) if prior_L is not None else float(st_start[0][0])   # (a later round: still the FIRST tone's lightness)
    pw = np.array([PRIOR_TONE if p_.startswith("tone.") else 1.0 for p_ in names] + [1.0] * len(bz))
    if free_e:
        x0, lo, hi = np.r_[x0, e_mid], np.r_[lo, -1.2], np.r_[hi, 1.2]

    t = time.time()
    # (a start on a bound never leaves it in a trust-region reflective solve: begin a little inside)
    xi = np.clip(x0, lo + 0.06 * (hi - lo), hi - 0.06 * (hi - lo))
    if proto:
        xi[len(names):np_] = 0.5
    sol, cost = None, np.inf
    c_start = 0.5 * float((resid(xi) ** 2).sum())
    for _ in range(6):   # (the solve stops early on its step tolerance in this bounded, curved problem: restart it)
        s_ = least_squares(resid, xi, bounds=(lo, hi), diff_step=0.02, x_scale=(hi - lo), max_nfev=30, xtol=1e-5, ftol=1e-6)
        if sol is not None and s_.cost > cost - max(0.03 * (c_start - cost), 0.02):   # (the gain against what CAN change: with lips alone free the other regions hold 99 % of the cost, and 1.5 % of the total never came)
            sol = s_ if s_.cost < cost else sol
            break
        sol, cost = s_, s_.cost
        xi = np.clip(s_.x, lo + 0.01 * (hi - lo), hi - 0.01 * (hi - lo))
    # THE BOUND: the plain skin's lightness never leaves the prior's by more than L_bound; a solve that wants more gets
    # its tone back toward the prior (the other parameters as solved) and says so
    # A MOVE MUST EARN ITS PLACE: a zone / lip parameter whose return to the start costs the fit next to nothing goes
    # back (layers that multiply the tone's blood are nearly inert on a pale, bloodless tone: Tess's eyelids ran to
    # 2.5 and lower_cool to 1.97, their bounds, for 0.1 L of albedo: numbers that say "dark lids" and paint nothing,
    # until someone changes the tone)
    cost = lambda xs_: 0.5 * float((resid(xs_) ** 2).sum())  # noqa: E731
    c_now = cost(sol.x)
    for i_ in sorted((i for i, p_ in enumerate(names) if not p_.startswith("tone.")), key=lambda i: -abs(sol.x[i] - x0[i]) / (hi[i] - lo[i])):
        if abs(sol.x[i_] - x0[i_]) < 0.01 * (hi[i_] - lo[i_]):
            continue
        xt = sol.x.copy()
        xt[i_] = x0[i_]
        c_try = cost(xt)
        if c_try - c_now < PRUNE:
            sol.x[:] = xt
            c_now = c_try
    tone_note = zone_note = None
    # THE ZONES' BOUND: no zone's offset from the face's mean leaves the prior's by more than ZONE_BOUND; the zone
    # layers' whole move is scaled back until all are inside (bisection on its share), and said
    zi = [i for i, p_ in enumerate(names) if not p_.startswith(("tone.", "lips."))]

    def zones_out(xs_):
        off = tone_stats(xs_)[2]
        bad = {}
        for k, o in off.items():
            d_ = o - np.asarray(prior_face["zones"].get(k, o), float)
            if abs(d_[0]) > ZB[0] or float(np.hypot(d_[1], d_[2])) > ZB[1]:
                bad[k] = d_
        return bad

    if zi and zreg:
        bad = zones_out(sol.x)
        if bad:
            xs, xp = sol.x.copy(), x0.copy()
            for i_ in zi:
                if prior_x and names[i_] in prior_x:
                    xp[i_] = float(np.clip(prior_x[names[i_]], lo[i_], hi[i_]))
            a_lo, a_hi = 0.0, 1.0
            for _ in range(10):
                a_ = 0.5 * (a_lo + a_hi)
                xs[zi] = xp[zi] + a_ * (sol.x[zi] - xp[zi])
                if zones_out(xs):
                    a_hi = a_
                else:
                    a_lo = a_
            xs[zi] = xp[zi] + a_lo * (sol.x[zi] - xp[zi])
            zone_note = ("the solve put " + ", ".join(f"{k} {d_[0]:+.1f} L* / {float(np.hypot(d_[1], d_[2])):.1f} a*b*" for k, d_ in bad.items()) +
                         f" from where the prior has that zone against the face (bounds {ZB[0]} L*, {ZB[1]} a*b*): "
                         f"the zone layers' move is held to {100 * a_lo:.0f} % of it")
            sol.x[:] = xs
    if free_e:
        L1 = plain_L(sol.x)
        ti = [i for i, p_ in enumerate(names) if p_.startswith("tone.")]

        def inside(xs_):
            pl, fl, _ = tone_stats(xs_)
            return (abs(float(pl[0]) - L0) <= L_bound and float(np.hypot(*(pl[1:] - ab0))) <= C_bound
                    and abs(float(fl[0]) - Lf0) <= (L_bound if white else FACE_BOUND)
                    and float(np.hypot(*(fl[1:] - np.asarray(prior_face["lab"][1:], float)))) <= C_bound)
        if ti and not inside(sol.x):
            xs = sol.x.copy()
            # (back toward the PRIOR tone itself: in a later round the start is the last round's tone, which the new
            # read's own points may already put outside the bound: Garrett's round 2 began 5.8 from the prior)
            xp = x0.copy()
            if prior_tone:
                for i_ in ti:
                    xp[i_] = float(np.clip(prior_tone[names[i_]], lo[i_], hi[i_]))
            a_lo, a_hi = 0.0, 1.0
            for _ in range(12):                 # the largest share of the tone's move that stays inside the bound
                a_ = 0.5 * (a_lo + a_hi)
                xs[ti] = xp[ti] + a_ * (sol.x[ti] - xp[ti])
                if not inside(xs):
                    a_hi = a_
                else:
                    a_lo = a_
            xs[ti] = xp[ti] + a_lo * (sol.x[ti] - xp[ti])
            d1, d2 = plain_lab(sol.x) - np.r_[L0, ab0], plain_lab(xs) - np.r_[L0, ab0]
            f1, f2 = tone_stats(sol.x)[1] - np.asarray(prior_face["lab"], float), tone_stats(xs)[1] - np.asarray(prior_face["lab"], float)
            tone_note = (f"the solve wanted the plain skin {d1[0]:+.1f} L* / {d1[1]:+.1f} a* / {d1[2]:+.1f} b* and the whole face "
                         f"{f1[0]:+.1f} / {f1[1]:+.1f} / {f1[2]:+.1f} from the prior; held to "
                         f"{d2[0]:+.1f} / {d2[1]:+.1f} / {d2[2]:+.1f} and {f2[0]:+.1f} / {f2[1]:+.1f} / {f2[2]:+.1f} (bounds: {L_bound} L*, {C_bound} in a*b*: "
                         f"{'a known white' if white else 'a backdrop is a weak white balance, and no exposure anchor'})")
            sol.x[:] = xs
    m1, sk1 = model(sol.x[:np_])
    expo = float(np.exp(sol.x[np_])) if free_e else 1.0
    sv1 = shade_opt(m1, float(sol.x[np_]) if free_e else 0.0)
    sv0 = shade_opt(base0, 0.0)
    target0 = shaded(sv0, 0.0)             # (the start against the read with ITS shade taken out: chi2 like with like)
    target = shaded(sv1, float(sol.x[np_]) if free_e else 0.0)
    st_end = tone_stats(sol.x)
    log(f"skin_read fit: {len(names) + len(bz)} parameters over {len(reg)} regions, status {sol.status}, {time.time() - t:.0f} s; "
        f"chi2 {float((((base0 - target0) / sig) ** 2).sum()):.0f} -> {float((((m1 - target) / sig) ** 2).sum()):.0f}; shade colour q {np.round(qs, 3).tolist()}")
    changes = []
    for p, a, b in zip(names, x0, sol.x[:len(names)]):
        if abs(b - a) > 0.01 * (BOUNDS[p][1] - BOUNDS[p][0]):
            at = " (at its bound: the picture asks for more than this control gives)" if min(b - BOUNDS[p][0], BOUNDS[p][1] - b) < 2e-3 * (BOUNDS[p][1] - BOUNDS[p][0]) and b != a else ""
            changes.append((p, round(float(a), 3), round(float(b), 3), "region colours" + at))
        elif _path_set(sk0, p):
            _set(sk1, p, _get(sk0, p))
        else:
            _unset(sk1, sk0, p)
    if not any(ch[0].startswith("tone.") for ch in changes):   # the tone as it was written (fitzpatrick and all)
        if "tone" in sk0:
            sk1["tone"] = copy.deepcopy(sk0["tone"])
        else:
            sk1.pop("tone", None)
    # the beard's scales -> hair.stubble (zones, density)
    if bz:
        s = sol.x[len(names):np_]
        o = _stubble_opts(sk1)
        zw0 = {z: float((o.get("zones") or {}).get(z, 1.0)) for z in bz}
        v = {z: zw0[z] * float(s[i]) for i, z in enumerate(bz)}
        seen = {z: r["regions"].get(f"beard:{z}", {}).get("read", False) for z in bz}
        top = max([v[z] for z in bz if seen[z]] or [0.0])
        if top < BEARD_MIN:
            if not proto:
                changes.append(("hair.stubble", "on", "off", "no beard shadow in the pictures"))
            sk1.get("hair", {}).pop("stubble", None)
        else:
            S = min(top, 1.0)
            zones = {z: round(float(np.clip(v[z] / top, 0, 1.5)), 2) if seen[z] else round(zw0[z], 2) for z in bz}
            from .skin_features import stubble_options
            d0 = stubble_options({"amount": 1.0, **o})["density"]
            o2 = {**o, "zones": {z: w for z, w in zones.items() if abs(w - 1) > 0.03}, "density": round(float(np.clip(d0 * S, 0.02, 1.0)), 3)}
            if not o2["zones"]:
                o2.pop("zones")
            sk1.setdefault("hair", {})["stubble"] = o2
            changes.append(("hair.stubble" + (" (ADDED)" if proto else ""), {"zones": {z: round(zw0[z], 2) for z in bz}, "density": round(d0, 3)} if not proto else None,
                            {"zones": zones, "density": o2["density"]}, "the lower face's shadow by beard zone" +
                            ("; zones not seen kept: " + ", ".join(z for z in bz if not seen[z]) if not all(seen.values()) else "")))
    # freckles
    fr = r["freckles"]
    if "freckles" in groups and fr["read"]:
        new = fr["amount"] if fr["amount"] >= 0.03 else 0.0
        if abs(new - fr["have"]) > 0.02:
            f = sk1.setdefault("features", {})
            old = f.get("freckles")
            if new <= 0:
                f.pop("freckles", None)
            else:
                f["freckles"] = {**old, "amount": new} if isinstance(old, dict) else new
            changes.append(("features.freckles", fr["have"], new, f"dark specks per cm2, picture vs ours: {fr['views']}"))
    # brows: colour and density
    b = r["brows"]
    native = min((v.get("mm_per_px", 0.3) for v in c.views), default=1.0)
    if "brows" in groups and b["read"]:
        hb = (sk1.get("hair") or {}).get("brows", 1.0)
        hb = {"amount": float(hb)} if isinstance(hb, (int, float)) else dict(hb or {})
        from . import paint
        p = skinmod.params({**c.spec, "skin": sk1})
        from .skin_features import hair_default
        col0 = np.asarray(paint.colour(hb["color"]) if "color" in hb else hair_default(p["tone"], p["age"]), float)[:3]
        g = float(hb.get("grey", 0.0))
        shown = col0 + g * (0.55 - col0)
        want = _srgb(np.clip(_lin(shown) * np.asarray(b["colour_ratio"]), 0, 1))
        new = dict(hb)
        if native <= BROW_COLOUR_MM and np.abs(lab(_lin(want)) - lab(_lin(shown))).max() > 2.0:
            new["color"] = "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in np.clip(want, 0, 1))
            new["grey"] = 0.0
            changes.append(("hair.brows.color", hb.get("color", "(default)") + (f" grey {g}" if g else ""), new["color"], f"brow hair colour x {b['colour_ratio']}"))
        d0 = float(hb.get("density", 0.8 - 0.12 * p["fem"] + 0.1 * p["masc"]))
        d1 = round(float(np.clip(d0 * b["coverage_ratio"], 0.15, 1.6)), 3)
        if abs(d1 - d0) > 0.05:
            new["density"] = d1
            changes.append(("hair.brows.density", round(d0, 3), d1, f"brow band coverage x {b['coverage_ratio']}"))
        sk1.setdefault("hair", {})["brows"] = new
    # eyeballs
    if "eyeballs" in groups and sk1.get("eyes") is not False and native <= IRIS_MM:
        from . import paint
        ey = dict(sk1.get("eyes") or {})
        e = r["eyes"].get("iris_rel") or {}
        if e.get("read"):
            c0 = np.asarray(paint.colour(ey.get("iris", "#5a3a1e")), float)[:3]
            hx0 = "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in c0)
            rt = np.asarray(e["ratio"], float)
            if iris_prev is not None:
                # the SECOND read: our eye picture answers a colour change with less than the whole of it (catchlight, cornea,
                # limbal ring: Tess, blue x1.39 applied, x1.24 still missing). The share it made of the last step, per
                # channel (0.5 .. 1), is taken into this one (a secant step)
                l0, l1 = np.log(np.maximum(np.asarray(iris_prev, float), 1e-4)), np.log(np.maximum(rt, 1e-4))
                gam = np.clip(np.where(np.abs(l0) > 0.05, 1.0 - l1 / np.where(np.abs(l0) > 0.05, l0, 1.0), 1.0), 0.5, 1.0)
                rt = np.exp(l1 / gam)
            hx1 = iris_colour(c0, rt)
            if np.abs(lab(_lin(np.asarray(paint.colour(hx1), float)[:3])) - lab(_lin(c0))).max() > 2.0:
                ey["iris"] = hx1
                changes.append(("eyes.iris", hx0, hx1, f"the picture's iris ring against its sclera's bright part, over ours: x {[round(float(x), 2) for x in e['ratio']]} "
                                                       f"({e['views']} eye(s); INFERRED: the sclera taken as ours, the hue is the picture's)"))
        else:
            changes.append(("eyes.iris", ey.get("iris", "default"), ey.get("iris", "default"),
                            f"NOT READ: no view shows an iris of {IRIS_R_PX:g} px radius with sclera beside it: the iris colour is NOT the picture's (set skin.eyes.iris by hand)"))
        if ey:
            sk1["eyes"] = ey
    if "folds" in groups and r.get("folds"):
        changes += fold_fit(sk1, r["folds"], True, lid_prior=lid_prior)
    resid_rows = {k: {"before": [round(float(x), 2) for x in (base0[i] - target0[i])], "after": [round(float(x), 2) for x in (m1[i] - target[i])]}
                  for i, k in enumerate(reg)}
    shade = {k: round(float(sv1[i]), 3) for i, k in enumerate(reg) if sv1[i] >= SHADE_SAY}
    out = {"skin": sk1, "changes": changes, "residual": resid_rows, "exposure": round(expo, 3),
           "iris_ratio": (r["eyes"].get("iris_rel") or {}).get("ratio") if "eyeballs" in groups else None,
           "shade": {"q": [round(float(v_), 3) for v_ in qs], "regions": shade,
                     "L": {k: round(float(lab(Tlin[i])[0] - lab(Tlin[i] * np.exp(sv1[i] * qs))[0]), 1) for i, k in enumerate(reg) if sv1[i] >= SHADE_SAY}},
           "face": {"prior": [round(float(v_), 2) for v_ in prior_face["lab"]], "fitted": [round(float(v_), 2) for v_ in st_end[1]],
                    "bound": FACE_BOUND, "zones": {k: [round(float(v_), 2) for v_ in (o - np.asarray(prior_face["zones"].get(k, o), float))] for k, o in st_end[2].items()},
                    "note": zone_note, "prior_face": prior_face},
           "tone": {"anchor": c.anchor.get("lightness", "prior") if free_e else "not read", "prior_L": round(L0, 2),
                    "prior_ab": [round(float(x), 2) for x in ab0],
                    "fitted_L": round(float(st_end[0][0]), 2) if free_e else round(L0, 2), "bound": L_bound, "note": tone_note}}
    out["text"] = fit_text(out)
    return out


def _path_set(sk: dict, path: str) -> bool:
    a, _, b = path.partition(".")
    d = sk.get(a) or {}
    if a == "tone":
        return True
    if b.startswith("lower."):
        return b[6:] in (d.get("lower") or {})
    return b in d


def _unset(sk1: dict, sk0: dict, path: str) -> None:
    """A parameter the fit left where it was and the description never named: take it out again."""
    a, _, b = path.partition(".")
    d = sk1.get(a)
    if not isinstance(d, dict):
        return
    if b.startswith("lower."):
        (d.get("lower") or {}).pop(b[6:], None)
        if "lower" in d and not d["lower"]:
            d.pop("lower")
    else:
        d.pop(b, None)
    if not d and a not in sk0:
        sk1.pop(a, None)


def fit_text(f: dict) -> str:
    L = ["SKIN FIT (what changed, from -> to, and the read behind it):"]
    t = f.get("tone") or {}
    if t.get("anchor") == "not read":
        L.append("  TONE: not read (no white balance in the pictures: no neutral backdrop, no white): lightness and hue stay the model's")
    elif t:
        L.append(f"  TONE LIGHTNESS: anchor = {'a known white in the picture (INFERRED albedo ' + str(WHITE_ALBEDO) + ')' if t['anchor'] == 'white' else 'the PRIOR (the stated skin.tone)'}; "
                 f"plain skin L* {t['prior_L']} -> {t['fitted_L']} (bound +-{t['bound']}); the picture's exposure against our render x {f.get('exposure', 1.0)}"
                 + (f"; {t['note']}" if t.get("note") else ""))
    fc = f.get("face")
    if fc:
        worst = sorted(fc["zones"].items(), key=lambda kv: -max(abs(kv[1][0]) / ZONE_BOUND[0], float(np.hypot(kv[1][1], kv[1][2])) / ZONE_BOUND[1]))[:4]
        L.append(f"  WHOLE FACE (mean albedo of every skin zone, stubble apart): Lab {fc['prior']} -> {fc['fitted']} (bound +-{fc['bound']} L*); "
                 f"zones against the face, moved most from the prior (bounds {ZONE_BOUND[0]} L*, {ZONE_BOUND[1]} a*b*): " +
                 "; ".join(f"{k} {v}" for k, v in worst) + (f". HELD: {fc['note']}" if fc.get("note") else ""))
    sh = f.get("shade")
    if sh and sh["regions"]:
        L.append(f"  SHADE, NOT PIGMENT (the pictures' own shade colour: exponents {sh['q']} for r g b; these regions read darker than our "
                 "render under the fitted light predicts, along that line: taken as shade our head does not cast, and NOT painted in): " +
                 ", ".join(f"{k} {sh['L'][k]:+.1f} L*" for k in sorted(sh["regions"], key=lambda k_: -sh["regions"][k_])) +
                 ". If it is pigment (a real tan line, dark circles), set that zone's strength yourself; if it is form (deep-set eyes, "
                 "hooding, a bag), it is geometry: block-in / skin.folds")
    for p, a, b, why in f["changes"]:
        L.append(f"  {p}: {a} -> {b}   [{why}]")
    if not f["changes"]:
        L.append("  nothing: the description already matches the read within its tolerance")
    worst = sorted(f["residual"].items(), key=lambda kv: -max(abs(kv[1]["after"][1]), abs(kv[1]["after"][2]), abs(kv[1]["after"][0]) / 4))[:6]
    L.append("  what the fit leaves (ours - picture, Lab, as the forward model has it): " +
             "; ".join(f"{k} {v['after']}" for k, v in worst))
    return "\n".join(L)


def apply(name: str, out: str | None = None, groups=DEFAULT_GROUPS, rounds: int = 2, anchor: str = "auto", stubble: bool | None = None,
          brow_shape: bool = True, log=print, tone=None, white=None) -> dict:
    """Read the references, set spec["skin"] from the read, save (onto `out`: a block-in fork of `name`, or `name`
    itself). rounds: read -> fit -> re-render -> read again (the second round corrects what the first could only
    estimate: freckle and beard densities, brow coverage). Returns {"model", "reads": [text per round], "fits",
    "skin", "text"}."""
    from . import blockin, store
    dst = out or name
    if out and out != name:
        blockin.fork(name, out, replace=True)
    reads, fits = [], []
    if tone is not None:     # a STATED tone (a Fitzpatrick type 1..6, or skin.tone's own keys): the lightness prior
        spec = store.load(dst)
        spec.setdefault("skin", {})["tone"] = {"fitzpatrick": float(tone)} if isinstance(tone, (int, float)) else dict(tone)
        store.save(dst, spec, "skin_from_reference: the stated tone (the lightness prior)")
    prior_L = prior_ab = prior_face = None
    sk_p = store.load(dst).get("skin") or {}
    prior_tone = {p_: _get(sk_p, p_) for p_ in GROUPS["tone"]}
    prior_x = {p_: _get(sk_p, p_) for g_ in ("zones", "eyes") for p_ in GROUPS[g_]}
    for k in range(max(int(rounds), 1)):
        r = read(dst, anchor=anchor, log=log, white=white)
        f = fit(r, groups=groups, stubble=stubble, log=log, prior_L=prior_L, prior_ab=prior_ab, prior_tone=prior_tone,
                prior_face=prior_face, prior_x=prior_x, iris_prev=fits[-1].get("iris_ratio") if fits else None)
        prior_L, prior_ab, prior_face = f["tone"]["prior_L"], f["tone"]["prior_ab"], f["face"]["prior_face"]
        reads.append(r["text"]); fits.append(f)
        spec = store.load(dst)
        spec["skin"] = f["skin"]
        if brow_shape and k == 0 and "brows" in groups:
            try:
                from . import blockin_brows
                bf = blockin_brows.fit(dst, spec)
                keep = {kk: spec["skin"]["hair"]["brows"][kk] for kk in ("color", "density", "grey") if kk in (spec["skin"].get("hair") or {}).get("brows", {})}
                spec["skin"].setdefault("hair", {})["brows"] = {**bf["brows"], **keep}
                f["text"] += "\n  " + bf["text"]
            except Exception as e:  # noqa: BLE001
                f["text"] += f"\n  brow placement NOT READ ({str(e)[:160]})"
        store.save(dst, spec, f"skin_from_reference round {k + 1}")
        log(f["text"])
        if not f["changes"]:
            break
    final = read(dst, anchor=anchor, log=log, white=white)
    text = "\n\n".join([f"{dst}: skin from the reference pictures ({len(fits)} round(s))", reads[0]] + [f["text"] for f in fits] +
                       ["AFTER:\n" + final["text"]])
    return {"model": dst, "reads": reads + [final["text"]], "fits": [{k: v for k, v in f.items()} for f in fits],
            "skin": store.load(dst).get("skin"), "text": text}


# ---------------------------------------------------------------- folds: the checklist's detectors

FOLD_T = 0.02          # log luminance: a valley this deep, across a fold's path, is a fold there
FOLD_OWN = 0.7         # ... and this share of our own valley there deeper than ours (the head's own shading under another light)
FOLD_SHARE = 0.3       # ... along at least this share of the path's visible stations
FOLD_MAX = 0.42        # log luminance: deeper than this is not a crease of skin
FOLD_CONF = 0.5        # a fold is laid only from this confidence up
SYMMETRIC = ("tear_trough", "nasolabial", "marionette")   # folds of age that come in pairs: a side that shows a valley
# along too little of its path to count takes the read side's amount x its own valley's share of the other's (INFERRED)
BILATERAL = ("lid_fold",)   # folds every face has on both sides: one side's read stands in for the other
PLACE_MM = 0.7         # mm a picture pixel: coarser, a fold's PLACE across its path is not read (it is laid on its landmark
                       # path, whole): on Garrett's paintings (1.1-1.3 mm) the shifts came out +-5 mm from station to station and the
                       # second round's moves ran to -8 mm
FOLD_MOVE = 1.5        # mm: a fold of ours is moved only when the picture's lies this far from it (median)
FOLD_STEP = 0.25       # mm between a profile's samples
# what an amount-1 fold of ours reads as (median valley depth, log luminance, under the pictures' fitted lights):
# calibrated on synthetic heads (spikes/skinread/foldval.py); the second round corrects what this gets wrong
# (skinfolds, 2026-10-12: recalibrated on the folds as GEOMETRY, spikes/skinfolds/foldval.py case A: nasolabial 0.18 /
# 0.08 by side under a side light, marionette 0.07, mouth_corner 0.10 / 0.09, mentolabial 0.28, tear_trough 0.18 / 0.23,
# glabella 0.15 / 0.11)
# (skinfolds2, the new paths and reliefs, foldval case A on folds2.json: nasolabial 0.23 / 0.15, marionette 0.094,
# commissure 0.076, mouth_corner 0.15 / 0.10, mentolabial 0.27, glabella 0.13 / 0.105)
FOLD_REF = {"nasolabial": 0.19, "marionette": 0.09, "mouth_corner": 0.12, "mentolabial": 0.28, "tear_trough": 0.2,
            "lid_fold": 0.16, "glabella": 0.13, "commissure": 0.08, "chin_notch": 0.1}
# THE STEP (skinfolds): a fold lit from its side is not a valley but a lit / shaded STEP across its line (a painter's
# nasolabial fold under a lamp). Per station: the mean log luminance just past the line on the plus side minus the
# minus side's, the picture's over OURS (our head's own shading across the path cancels), signed by the fitted light:
# with the light from the plus side the wall under the roll is in shade (step < 0), from the minus side it is lit.
STEP_T = 0.045         # log luminance: a step this much over ours, with the light's sign, is a fold there
STEP_LINE = 1.0        # mm: the step's place along a fold may wander this much (rms about its median-filtered course)
STEP_RUN = 10.0        # mm: ... and it runs on at least this far
STEP_MIN = 0.3         # the step per unit of cross light below which it is our light's error, not a fold
STEP_MAX = 1.0         # a fold read by its step alone is laid at most this strong (the step follows the light's angle)
STEP_CROSS = 0.25      # the fitted light must lie this far across the path (|l . across|) for the step to mean a fold
# what an amount-1 fold of ours reads as a step per unit of cross light (|l . across|); calibrated like FOLD_REF
# (case A: nasolabial 0.46 / 0.32, mouth_corner 0.15 / 0.19, mentolabial 0.28, tear_trough 0.16 / 0.71, lid_fold 0.60 /
# 0.69, glabella 0.17 / 0.19)
STEP_REF = {"nasolabial": 0.39, "marionette": 0.2, "mouth_corner": 0.17, "mentolabial": 0.28, "tear_trough": 0.4,
            "lid_fold": 0.65, "glabella": 0.18, "commissure": 0.2, "chin_notch": 0.2}
# THE LID'S CREASE FROM THE LASH LINE (skinfolds): on a picture fine enough, the upper lid's fold line is searched up
# from the PICTURE's own lash line (lidfold.read_lid on the detector's lid: the strongest valley 1.2 mm+ over it, per
# column), not across the model's nominal path: that path sits a crease height over OUR lid and found, on Tess, a
# faint arc above her real fold. shift = the picture's height over the lash line - the nominal path's over the same
# line; amount from the line's darkness over ours.
LID_PRIOR = {"amount": 0.6, "show": (3.3, 2.0), "nominal": 3.45}   # a lid fold the pictures CANNOT resolve is laid from
# norms (INFERRED, said so): the platform show over the lashes, women / men (Price et al. 2009, lidfold.NORMS), against
# the nominal path's own height (0.062 x the pupils' distance); its roll (the hooding) grows with age
LID_COLS = (0.2, 0.35, 0.5, 0.65, 0.8)
LID_REACH = 8.5        # mm over the lashes the line is searched (further up is the brow's own shadow: 11-13 mm on a smooth head)
LID_DARK = 0.08        # read_lid's darkness (0..1): a line is there
LID_REF = 0.36         # what an amount-1 lid_fold of ours adds to that darkness (skinfolds2, lidcal.py: our crease at amount 1,
                       # read on the render at its full size, 0.35 / 0.37 by side; Tess's photographed fold: 0.32. Before
                       # the crease's occlusion was measured in 3D and vanished mid-lid: 0.06-0.10 at amount 1.2)
LEGACY = {"nasolabial": "nasolabial", "marionette": "marionette", "glabella": "glabella"}   # skin.wrinkles' own lines
LEGACY_SHARE = 0.5     # what one unit of the legacy wrinkle is taken to be worth in fold amount when it is replaced
# fields of fine lines (skin.wrinkles' swatch layers): zone, the picture resolution they need (mm a pixel), and what
# one unit of amount adds to the zone's fine-line energy over the cheek's
FIELDS = {"forehead": ("forehead", 0.45, 0.6), "crows_feet": ("crows_feet", 0.45, 0.5), "under_eye": ("under_eye", 0.45, 0.4),
          "lip_lines": ("upper_lip", 0.4, 0.4)}
FIELD_BAND = (0.25, 0.9)   # mm: the band fine lines live in
FIELD_FIT = False          # see fold_fit: the read failed its null
FIELD_T = 0.25             # a zone's fine-line energy this far over ours (x the cheek's) is a difference


def _valley(prof: np.ndarray, u: np.ndarray, search: float, flank: float) -> tuple:
    """(depth, position) of the darkest valley within |u| <= search against the lower of the two rims within
    `flank` of it; 0 when there is none."""
    inner = np.abs(u) <= search
    i = np.flatnonzero(inner)[np.argmin(prof[inner])]
    left = prof[(u < u[i]) & (u >= u[i] - flank)]
    right = prof[(u > u[i]) & (u <= u[i] + flank)]
    if len(left) < 2 or len(right) < 2 or abs(u[i]) > search - 1.5 * (u[1] - u[0]):
        return 0.0, float(u[i])       # (a minimum on the window's edge is the slope of something else beside the path)
    return max(float(min(left.max(), right.max()) - prof[i]), 0.0), float(u[i])


def _bil(img: np.ndarray, x, y):
    h, w = img.shape
    x = np.clip(np.asarray(x, float), 0, w - 1.001)
    y = np.clip(np.asarray(y, float), 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy


def _fold_view(f: dict, q: dict, fd: dict, ldir=None) -> dict | None:
    """One fold's path in one view: per station the valley across it in the picture, in ours, and in the picture
    over ours (the differential), or None when the view does not show the path."""
    from scipy import ndimage
    from . import humanfit
    Yv = np.array([0.2126, 0.7152, 0.0722])
    box = f["box"]
    k = N / (box[2] - box[0])
    P, ac = q["P"], q["across"]
    p0 = (humanfit.project(f["cam"], P) - np.asarray(box[:2])) * k
    v = (humanfit.project(f["cam"], P + 0.001 * ac) - np.asarray(box[:2])) * k - p0       # px per mm across
    sc = np.linalg.norm(v, axis=1)
    flank = float(fd.get("flank", max(1.5 * fd["width"], 3.0)))
    U = fd["search"] + flank
    u = np.arange(-U, U + 1e-6, FOLD_STEP)
    sx = p0[:, None, 0] + u[None, :] * v[:, None, 0]
    sy = p0[:, None, 1] + u[None, :] * v[:, None, 1]
    inb = (sx > 2) & (sx < N - 3) & (sy > 2) & (sy < N - 3)
    good = (f["skin"] & (f["alpha"] > 0.98)).astype(float)
    if f["parse"]:
        good = good * (f["parse"]["skin"] > 0.5) * (f["parse"]["hair"] < 0.4)
    gs = _bil(good, sx, sy) * inb
    # the station itself: on the skin the camera sees (not behind the nose), not foreshortened to nothing
    ix, iy = np.clip(np.round(p0[:, 0]).astype(int), 0, N - 1), np.clip(np.round(p0[:, 1]).astype(int), 0, N - 1)
    seen = (np.linalg.norm(f["X"][iy, ix] - P, axis=1) < 0.003) & (sc > 0.45 / f["mm"])
    valid = seen & (gs.mean(1) > 0.8) & (q["t"] >= float(fd.get("read_from", 0.0)))
    if valid.sum() < max(4, 0.25 * len(P)):
        return None
    sg = float(np.clip(0.3 * fd["width"] / f["mm"], 0.7, 4.0))
    lp = ndimage.gaussian_filter(np.log(np.maximum(f["P"] @ Yv, 2e-3)), sg)
    lr = ndimage.gaussian_filter(np.log(np.maximum(f["R"] @ Yv, 2e-3)), sg)
    pp, pr = _bil(lp, sx, sy), _bil(lr, sx, sy)
    # (a couple of mm along the path: a fold runs on, noise does not)
    ker = np.ones(5) / 5.0
    sm = lambda a: np.apply_along_axis(lambda c_: np.convolve(np.r_[c_[:2][::-1], c_, c_[-2:][::-1]], ker, "valid"), 0, a)  # noqa: E731
    pp, pr = sm(pp), sm(pr)
    out = {"u": u}
    for key, a in (("picture", pp), ("ours", pr)):
        dv = np.array([_valley(a[i], u, fd["search"], flank) for i in range(len(P))])
        out[key], out[key + "_u"] = dv[:, 0], dv[:, 1]
    # a "valley" deeper than any crease of skin is a feature's own edge (the mouth's corner, a nostril, lashes: the
    # model's lies a millimetre from the picture's): not a fold
    valid = valid & (out["picture"] < FOLD_MAX) & (out["ours"] < FOLD_MAX)
    # the step across the line (see STEP_T): windows `fw` wide starting `gap` from a centre c, plus side minus the
    # minus side, at every c within the search; the picture's over ours, signed by the light
    out["step"], out["step_u"], out["cross"] = np.zeros(len(P)), np.zeros(len(P)), np.zeros(len(P))
    if ldir is not None:
        cross = ac @ (np.asarray(ldir, float) / np.linalg.norm(ldir))
        nw = max(int(round(max(fd["width"], 2.0) / FOLD_STEP)), 2)
        ng = max(int(round(0.25 * fd["width"] / FOLD_STEP)), 1)
        ker = np.ones(nw) / nw
        box = lambda a: np.apply_along_axis(lambda c_: np.convolve(c_, ker, "same"), 1, a)  # noqa: E731
        off = ng + nw // 2
        D = box(pp) - box(pr)                      # the differential profile's window means
        S = np.full_like(D, np.nan)
        S[:, off:-off] = D[:, 2 * off:] - D[:, :-2 * off]
        inner = (np.abs(u) <= fd["search"]) & np.isfinite(S[0])
        sgn = -np.sign(cross)
        V = S[:, inner] * sgn[:, None]
        V = np.where(np.isfinite(V).any(1)[:, None], V, 0.0)       # (a row with no finite window: nanargmax raises)
        k = np.nanargmax(V, 1)
        # (the largest step of the light's sign within the search is positive for any noise: it counts only OVER the
        # largest step of the other sign. First version without this: on Garrett's two paintings every fold "stepped"
        # along 92-100 % of its path, the line jumping +-4 mm from station to station)
        best = np.nan_to_num(V[np.arange(len(P)), k] - np.nanmax(-V, 1), nan=0.0)   # (a station off the picture: no step)
        # ... and the picture itself must step that way there, not only its difference to ours
        Sp = np.full_like(D, np.nan)
        Bp = box(pp)
        Sp[:, off:-off] = Bp[:, 2 * off:] - Bp[:, :-2 * off]
        own = np.nan_to_num((Sp[:, inner] * sgn[:, None])[np.arange(len(P)), k], nan=0.0)
        out["step_u"] = u[inner][k]
        # (a step on the window's edge is the edge of something beside the path: on Tess both tear troughs "stepped" at
        # +5.0 mm, her lower lid's margin and lashes)
        edge = np.abs(out["step_u"]) > fd["search"] - 1.5
        out["step"] = np.where(valid & ~edge & (np.abs(cross) >= STEP_CROSS) & (own >= 0.5 * STEP_T), np.maximum(best, 0.0), 0.0)
        out["cross"] = np.abs(cross)
    out["valid"] = valid
    out["picture"], out["ours"] = out["picture"] * valid, out["ours"] * valid
    if valid.sum() < 2:       # (every station was a feature's edge: no read of this view, and no NaN weight)
        return None
    out["scale"] = float(np.median(sc[valid]))
    return out


def _run(mask: np.ndarray, gap: int = 3) -> tuple:
    """The longest run of True (gaps up to `gap` bridged): (i0, i1) inclusive, or None."""
    best, start, last = None, None, None
    for i, m in enumerate(mask):
        if m:
            if start is None or i - last > gap + 1:
                start = i
            last = i
            if best is None or last - start > best[1] - best[0]:
                best = (start, last)
    return best


def fold_read(c: Context) -> dict:
    """The checklist: {fold: {"readable", "why", "sides": {side: {"present", "picture", "ours", "diff" (the picture's
    valley over ours, log luminance), "excess" (ours over the picture's), "share", "extent" [t0, t1], "shift" [mm at
    N_SHIFT stations], "confidence", "views"}}}}; + "fields": the fine-line zones."""
    from . import skin as skinmod, skin_folds as sf
    J = skinmod._joints(c.st)
    part = (c.st.get("skin") or {}).get("part", "body")
    native = {f["view"]: f.get("mm_native", f["mm"]) for f in c.frames}
    out = {}
    if "lm_jaw_1.L" not in J:
        return {"folds": {}, "fields": {}, "why": "no GNM head landmarks"}
    nominal = sf.paths(c.st, part, J, None)
    ldirs = {}
    for f in c.frames:
        try:
            ldirs[f["view"]] = np.asarray(lighting(c.name, f["view"])["lights"][0]["dir"], float)
        except Exception:  # noqa: BLE001
            ldirs[f["view"]] = None
    lash = _lid_read(c, nominal)
    for name, fd in sf.FOLDS.items():
        ok_views = [f for f in c.frames if native[f["view"]] <= fd["res"]] if fd.get("read", True) else []
        row = {"readable": bool(ok_views), "sides": {}, "about": fd["about"]}
        if not fd.get("read", True):
            row["why"] = "NOT READ (" + fd["read_why"] + "): set skin.folds." + name + " by eye"
            out[name] = row
            continue
        if not ok_views:
            row["why"] = (f"cannot tell: the pictures have {min(native.values()):.2f} mm a pixel at the face, this needs "
                          f"{fd['res']} or finer (a {fd['width']} mm feature)")
            out[name] = row
            continue
        for sd in ((".L", ".R") if sf.sided(name) else ("",)):
            q = nominal[(name, sd)]
            best, acc = None, []
            for f in ok_views:
                r_ = _fold_view(f, q, fd, ldirs.get(f["view"]))
                if r_ is None:
                    continue
                vw = next(v for v in c.views if v["view"] == f["view"])["weight"]
                acc.append((f["view"], r_, vw * float(r_["valid"].sum()) * r_["scale"]))
            if not acc:
                row["sides"][sd] = {"present": None, "why": "not seen (turned away, hidden, or under hair) in any view"}
                continue
            res = {"views": [a[0] for a in acc]}
            wsum = sum(a[2] for a in acc)
            stat = {k: 0.0 for k in ("picture", "ours", "diff", "excess", "share", "step", "step_share", "cross")}
            sbest = None
            for vi, r_, w in acc:
                val = r_["valid"]
                hit = val & (r_["picture"] - r_["ours"] >= FOLD_T) & (r_["picture"] >= FOLD_T)
                run = _run(hit)
                # the step: where the light lies across the path
                can = val & (r_["cross"] >= STEP_CROSS)
                shit = can & (r_["step"] >= STEP_T)
                srun = _run(shit)
                if srun is not None:
                    # a fold's step is a LINE: its place moves smoothly from station to station (STEP_LINE mm rms about
                    # its own smoothed course), and it runs on for STEP_RUN mm
                    from scipy.ndimage import median_filter as _mf
                    seg = np.arange(srun[0], srun[1] + 1)
                    seg = seg[shit[seg]]
                    us = r_["step_u"][seg]
                    rough = float(np.sqrt(np.mean((us - _mf(us, 5, mode="nearest")) ** 2))) if len(us) >= 5 else 9.0
                    if rough > STEP_LINE or len(seg) * sf.STATION * 1000 < STEP_RUN:
                        srun, shit = None, np.zeros(len(val), bool)
                if can.sum() >= 4:
                    ssel = np.zeros(len(val), bool)
                    if srun:
                        ssel[srun[0]:srun[1] + 1] = True
                    suse = (ssel & can) if (ssel & can).sum() >= 4 else can
                    stat["step"] += w / wsum * float(np.nan_to_num(np.median(r_["step"][suse] / np.maximum(r_["cross"][suse], 1e-6))))
                    stat["step_share"] += w / wsum * float(shit.sum() / max(can.sum(), 1))
                    stat["cross"] += w / wsum * float(np.median(r_["cross"][can]))
                    if srun is not None and (sbest is None or w * shit.sum() > sbest[2]):
                        sbest = (vi, r_, w * shit.sum(), srun, shit)
                sel = np.zeros(len(val), bool)
                if run:
                    sel[run[0]:run[1] + 1] = True
                sel &= val
                use = sel if sel.sum() >= 4 else val
                if sel.sum() < 4:
                    # no stretch where the picture has MORE than ours: compare where the PICTURE shows its valley (the
                    # same stations round after round). Over all stations a fold the picture has along half its path
                    # read 0.03 against 0.10 of ours, laid whole: "ours has more", taken off, read PRESENT again, ...
                    prun = _run(val & (r_["picture"] >= FOLD_T))
                    if prun is not None and prun[1] - prun[0] + 1 >= max(4, 0.3 * val.sum()):
                        psel = np.zeros(len(val), bool)
                        psel[prun[0]:prun[1] + 1] = True
                        use = psel & val
                stat["share"] += w / wsum * float(hit.sum() / max(val.sum(), 1))
                # (each alone, at its own valley: the head's own shading there is in both and cancels in the difference;
                # the valley of the RATIO image is not used: beside a fold of ours its roll and shade make false ones)
                for k in ("picture", "ours"):
                    stat[k] += w / wsum * float(np.median(r_[k][use]))
                stat["diff"] += w / wsum * float(np.median((r_["picture"] - r_["ours"])[use]))
                stat["excess"] += w / wsum * float(np.median((r_["ours"] - r_["picture"])[val]))
                wb = w * (1.0 + float(hit.sum()))          # (the view that shows the fold best places it)
                if best is None or wb > best[2]:
                    best = (vi, r_, wb, run)
            res.update({k: round(v, 4) for k, v in stat.items()})
            vi, r_, w, run = best
            res["present"] = bool(stat["share"] >= FOLD_SHARE and stat["diff"] >= FOLD_T + FOLD_OWN * stat["ours"] and stat["picture"] >= FOLD_T and run is not None)
            res["by"] = "valley" if res["present"] else None
            # (only folds that ARE steps, the ones with a roll; and STEP_MIN per unit of cross light: on a smooth young
            # head under an unknown light the mentolabial groove and both tear troughs "stepped" at 0.10-0.14, our fitted
            # light standing in for theirs; real folds at amount 1 step at 0.3-0.7. foldval case B)
            res["step_present"] = bool(sbest is not None and sf.RELIEF[name].get("roll") and stat["step_share"] >= FOLD_SHARE
                                       and stat["step"] >= STEP_MIN and stat["step"] * max(stat["cross"], 1e-6) >= STEP_T)
            res["absent_in_picture"] = bool(stat["excess"] >= FOLD_T + FOLD_OWN * stat["picture"] and stat["ours"] >= FOLD_T)
            t = q["t"]
            if run is not None:
                res["extent"] = [round(float(t[max(run[0] - 1, 0)]), 2), round(float(t[min(run[1] + 1, len(t) - 1)]), 2)]
                from scipy.ndimage import median_filter
                uu = median_filter(r_["picture_u"], 7, mode="nearest")
                good = r_["valid"] & (r_["picture"] - r_["ours"] >= FOLD_T) & (r_["picture"] >= FOLD_T)
                if good.sum() >= 3:
                    ts = np.linspace(0, 1, sf.N_SHIFT)
                    res["shift"] = [round(float(x), 2) for x in np.interp(ts, t[good], uu[good])]
                # where OURS shows the fold too, the two valleys' distance is the placement error with the light's
                # bias gone (a valley's darkest line sits off the groove, toward the wall the light misses)
                both = r_["valid"] & (r_["picture"] >= FOLD_T) & (r_["ours"] >= FOLD_T)
                if both.sum() >= max(4, 0.3 * r_["valid"].sum()):
                    du = median_filter(r_["picture_u"] - r_["ours_u"], 7, mode="nearest")
                    if abs(float(np.median(du[both]))) >= FOLD_MOVE:   # (the null moves +-1 mm: less is not a difference)
                        res["move"] = [round(float(x), 2) for x in np.interp(np.linspace(0, 1, sf.N_SHIFT), t[both], du[both])]
            res["confidence"] = round(float(np.clip(stat["diff"] / (2.5 * FOLD_T), 0, 1) * np.clip(stat["share"] / 0.5, 0, 1)), 2)
            if "shift" in res:   # a fold's line is smooth: a parabola through the stations' reads, inside the search
                ts_ = np.linspace(0, 1, len(res["shift"]))
                co = np.polyfit(ts_, res["shift"], 2)
                res["shift"] = [round(float(x), 2) for x in np.clip(np.polyval(co, ts_), -(fd["search"] - 1.0), fd["search"] - 1.0)]
            if res["step_present"] and not res["present"]:
                # a side-lit fold: no valley, a step. Placed at the step's own line (the steep wall under the roll)
                vi, r_, _, srun, shit = sbest
                res["present"], res["by"] = True, "step"
                res["views"] = sorted(set(res["views"]))
                res["extent"] = [round(float(t[max(srun[0] - 1, 0)]), 2), round(float(t[min(srun[1] + 1, len(t) - 1)]), 2)]
                if shit.sum() >= 3:
                    from scipy.ndimage import median_filter
                    uu = median_filter(r_["step_u"], 7, mode="nearest")
                    res["shift"] = [round(float(x), 2) for x in np.interp(np.linspace(0, 1, sf.N_SHIFT), t[shit], uu[shit])]
                res["confidence"] = round(float(np.clip(stat["step"] * stat["cross"] / (2.0 * STEP_T), 0, 1) * np.clip(stat["step_share"] / 0.7, 0, 1)), 2)
            if min(native[v_] for v_ in res["views"]) > PLACE_MM:
                for k_ in ("shift", "move", "extent"):
                    res.pop(k_, None)
                res["placed"] = "on its landmark path (the pictures are too coarse to place it)"
            if name == "lid_fold" and lash.get(sd) is not None:
                # the lash-line read PLACES the fold (the picture's own line over its own lashes); it is there when
                # either read says so, as strong as the stronger says
                lq = lash[sd]
                res["lash"] = lq["lash"]
                path_gain = (stat["step"] / STEP_REF[name] if res.get("by") == "step" else stat["diff"] / FOLD_REF[name]) if res["present"] else 0.0
                if lq["present"] or (res["present"] and "shift" in lq):
                    res["amount"] = round(float(np.clip(max(path_gain, lq.get("amount", 0.0)), 0, 1.5)), 3)
                    res["by"] = "lash line" + ("" if lq["present"] else f" (placed), {res.get('by')} (strength)")
                    res["present"] = True
                    res["shift"], res["extent"] = lq["shift"], lq["extent"]
                    if float(res["amount"]) >= 1.49:
                        res["placed"] = "at its strongest (the picture's fold line is darker than this control makes it)"
                    res["confidence"] = max(res["confidence"], lq["confidence"])
                    res.pop("move", None)
                    if lq["present"]:
                        res.update({k_: lq[k_] for k_ in ("picture", "ours", "diff", "excess", "share")})
                elif lq.get("works"):
                    # the lash-line read WORKS here (the picture's line, or ours, is found in 3+ columns) and says "as
                    # ours" or "ours is darker": it is the lid's read, the valley across the path is not (round 2 on
                    # Tess: her line 0.32, ours 0.30: as ours; the path's valley, 1.5 mm off her line, said "ours has
                    # more" and took half the fold off again). skinfolds2
                    res.update({k_: lq[k_] for k_ in ("picture", "ours", "diff", "excess", "share")})
                    res["present"], res["by"], res["confidence"] = False, "lash line", 0.0
                    res["absent_in_picture"] = bool(lq["excess"] >= 0.06)
                    res.pop("move", None)
            row["sides"][sd] = res
        out[name] = row
    return {"folds": out, "fields": _field_read(c, native)}


def _lid_read(c: Context, nominal: dict) -> dict:
    """{".L" | ".R": {"present", "by": "lash line", "lash": {...}, "shift", "extent", "confidence", "dark", "dark_ours"}}
    for the upper lid's fold, searched up from the PICTURE's lash line in the most frontal view fine enough
    (lidfold.read_lid; see LID_COLS); {} when no view allows it (then the path's valley read stands)."""
    from PIL import Image
    from . import blockin, humanfit, lidfold, skin_folds as sf
    from .likeness_eyes import frame as eye_frame
    fd = sf.FOLDS["lid_fold"]
    rj = blockin._refs(c.name)
    best = None
    for f in c.frames:
        if f.get("mm_native", f["mm"]) <= fd["res"] and (best is None or abs(f["yaw"]) < abs(best["yaw"])):
            best = f
    if best is None or abs(best["yaw"]) > 25 or "R" not in best:
        return {}
    f = best
    try:
        img = Image.open(f["image"]).convert("RGB")
        P = blockin.detect_view(img, rj["views"][f["view"]])
        if P is None:
            return {}
        P = np.asarray(P, float)[:, :2]
        mm = float(f.get("mm_native", f["mm"]))
        cols_p = lidfold.read_lid(img, P, mmpx=mm, fractions=LID_COLS, reach_mm=LID_REACH)
        # ours: the render through the same camera, the same detector points carried into its crop
        k = N / (f["box"][2] - f["box"][0])
        # (ours at the render's full size: at the 512 crop, 0.5 mm a pixel, our own crease read 0.05-0.13 where the
        # picture's, at 0.25 mm, read 0.3: half of that was the resolution. skinfolds2)
        if "R2" in f:
            k2 = f["R2"].shape[0] / (f["box"][2] - f["box"][0])
            cols_o = lidfold.read_lid(Image.fromarray(f["R2"]), (P - np.asarray(f["box"][:2])) * k2, mmpx=f["mm"] * N / f["R2"].shape[0],
                                      fractions=LID_COLS, reach_mm=LID_REACH)
        else:
            ours = Image.fromarray(np.round(255 * np.clip(_srgb(f["R"]), 0, 1)).astype(np.uint8))
            cols_o = lidfold.read_lid(ours, (P - np.asarray(f["box"][:2])) * k, mmpx=f["mm"], fractions=LID_COLS, reach_mm=LID_REACH)
    except Exception:  # noqa: BLE001
        return {}
    ex, ey = eye_frame(P)
    ex, ey = np.asarray(ex, float), np.asarray(ey, float)
    out = {}
    for s_, sd in ((0, ".R"), (1, ".L")):
        q = nominal.get(("lid_fold", sd))
        if q is None:
            continue
        o = P[lidfold.INNER[s_]]
        span = float((P[lidfold.OUTER[s_]] - o) @ ex)
        X = humanfit.project(f["cam"], q["P"]) - o
        xt, xh = X @ ex, -(X @ ey)                      # along the eye, up the face (px)
        order = np.argsort(xt * np.sign(span))
        # the lid leans back from the picture plane: a millimetre ALONG THE SKIN across the fold is this many up the
        # picture (0.4-0.6 on Tess's lids). The shift is asked in skin millimetres: the picture's are divided by it
        # (skinfolds2: laid 1:1, a fold read 1.6 mm over our path came out 0.8 over it)
        Xa = humanfit.project(f["cam"], q["P"] + 0.001 * q["across"]) - o
        lean = np.clip((-(Xa @ ey) - xh) * mm, 0.35, 1.0)
        # OUR lid margin through the same camera (the upper lid's landmarks): the path's height over OUR lashes
        h_own = None
        try:
            from . import skin as skinmod
            Jl = skinmod._joints(c.st)
            Mg = humanfit.project(f["cam"], np.array([Jl[k_ + sd] for k_ in ("lm_eye_inner", "lm_lid_upper_in", "lm_lid_upper", "lm_lid_upper_out", "lm_eye_outer")])) - o
            mt, mh = (Mg @ ex) * np.sign(span), -(Mg @ ey)
            om = np.argsort(mt)
            co_m = np.polyfit(mt[om], mh[om], 2)                    # (a lid margin is an arc)
            h_own = (xh - np.polyval(co_m, xt * np.sign(span))) * mm
        except Exception:  # noqa: BLE001
            pass
        rows = []
        for fr_, cp, co in zip(LID_COLS, cols_p[s_], cols_o[s_]):
            tcol = fr_ * span
            lid = lidfold._interp_curve(P, lidfold.UPPER[s_], tcol, ex, ey, o)      # (down the face, px)
            h_nom = (float(np.interp(tcol * np.sign(span), (xt * np.sign(span))[order], xh[order])) + lid) * mm   # the path over the lash line
            t_path = float(np.interp(tcol * np.sign(span), (xt * np.sign(span))[order], q["t"][order]))
            rows.append({"col": fr_, "t": t_path, "tps": cp.get("tps", np.nan), "dark": cp.get("dark", 0.0), "dark_ours": co.get("dark", 0.0),
                         "tps_ours": co.get("tps", np.nan), "nominal": h_nom,
                         "lean": float(np.interp(tcol * np.sign(span), (xt * np.sign(span))[order], lean[order]))})
        good = [r_ for r_ in rows if np.isfinite(r_["tps"]) and r_["dark"] >= LID_DARK and 1.5 <= r_["nominal"] <= 6.0]
        dark = float(np.median([r_["dark"] for r_ in rows]))
        dark_o = float(np.median([r_["dark_ours"] for r_ in rows]))
        res = {"by": "lash line", "lash": {"view": f["view"], "columns": [{k_: (round(float(v_), 2) if np.isfinite(v_) else None) for k_, v_ in r_.items()} for r_ in rows]},
               "picture": round(dark, 3), "ours": round(dark_o, 3), "diff": round(dark - dark_o, 3), "share": round(len(good) / len(rows), 2),
               "excess": round(dark_o - dark, 3), "views": [f["view"]]}
        res["present"] = bool(len(good) >= 3 and dark - dark_o >= 0.04)
        res["works"] = bool(len(good) >= 3 or sum(r_["dark_ours"] >= LID_DARK for r_ in rows) >= 3)
        res["absent_in_picture"] = bool(dark_o - dark >= 0.08 and dark < LID_DARK)
        res["confidence"] = round(float(np.clip(len(good) / 4.0, 0, 1) * np.clip((dark - dark_o) / 0.1, 0, 1)), 2)
        if len(good) >= 3 and h_own is not None:
            # THE LINE (skinfolds2; Joe: "that crease is still wobbly"): her fold is one smooth arc at a near-constant
            # height over her lashes. So: the picture's height over ITS lashes as a straight line in the column (2
            # numbers from the 3-5 columns: never the columns' noise), laid over OUR lash line at every station of the
            # path, in skin millimetres (/ lean), and that shift as a quadratic in t. Before: per column (picture's
            # height - the nominal path's over the PICTURE's lashes), a parabola through 5 noisy points held flat past
            # the outer columns: Tess's right eye got 2.8, 1.1, 2.6 mm along one lid.
            fr_g = np.array([r_["col"] for r_ in good])
            co_p = np.polyfit(fr_g, [r_["tps"] for r_ in good], 1, w=[max(r_["dark"], 0.05) for r_ in good])
            frs = xt / span
            use = (frs >= 0.2) & (frs <= 0.8)
            ts = q["t"][use]
            sh = (np.polyval(co_p, frs[use]) - h_own[use]) / lean[use]
            kk = np.argsort(ts)
            co = np.polyfit(ts[kk], sh[kk], 2)
            res["offset_mm"] = [round(float(np.polyval(co_p, x_)), 2) for x_ in (0.2, 0.5, 0.8)]
            ends = (float(ts.min()), float(ts.max()))
        elif len(good) >= 3:
            ts = np.array([r_["t"] for r_ in good])
            sh = np.array([(r_["tps"] - r_["nominal"]) / r_["lean"] for r_ in good])
            kk = np.argsort(ts)
            co = np.polyfit(ts[kk], sh[kk], 1 if len(good) < 4 else 2)        # a fold's line is smooth
        if len(good) >= 3:
            tn = np.linspace(0, 1, sf.N_SHIFT)
            shv = np.clip(np.polyval(co, np.clip(tn, ts.min(), ts.max())), -3, 6)
            if h_own is not None:
                # past the outer columns the constant offset ends: a crease runs into the corners with the lid, as the
                # nominal path does (the quadratic carried on gave +6 mm at the inner end: a hook)
                ramp = np.clip(np.minimum(tn / max(ends[0], 1e-3), (1 - tn) / max(1 - ends[1], 1e-3)), 0, 1)
                shv = shv * (0.25 + 0.75 * ramp * ramp * (3 - 2 * ramp))
            res["shift"] = [round(float(x), 2) for x in shv]
            res["extent"] = [0.0, 1.0]
            res["amount"] = round(float(np.clip((dark - dark_o) / LID_REF, 0, 1.5)), 3)
            res.pop("move", None)
        out[sd] = res
    return out


def _field_read(c: Context, native: dict) -> dict:
    """Fields of fine lines (forehead, crow's feet, under the eye, round the lips): the zone's fine-line energy over
    the cheek's, in the picture and in ours."""
    from scipy import ndimage
    Yv = np.array([0.2126, 0.7152, 0.0722])
    out = {}
    cheek = c.alb.zone("cheek") > 0.5
    for name, (zone, res, _) in FIELDS.items():
        zm = c.alb.zone(zone) > 0.5
        rows, why = [], None
        for f, v in zip(c.frames, c.views):
            if native[f["view"]] > res:
                why = f"cannot tell: {native[f['view']]:.2f} mm a pixel, fine lines need {res} or finer"
                continue
            m = c.view == f["view"]
            e = {}
            for key in ("P", "R"):
                lg = np.log(np.maximum(f[key] @ Yv, 2e-3))
                bp = ndimage.gaussian_filter(lg, FIELD_BAND[0] / f["mm"]) - ndimage.gaussian_filter(lg, FIELD_BAND[1] / f["mm"])
                b = bp.ravel()[c.pix[m]]
                ok = c.w[m] > 0
                if (zm[m] & ok).sum() < 300 or (cheek[m] & ok).sum() < 300:
                    e = None
                    break
                e[key] = float(np.sqrt(np.mean(b[zm[m] & ok] ** 2)) / max(np.sqrt(np.mean(b[cheek[m] & ok] ** 2)), 1e-5))
            if e:
                rows.append((v["weight"], e["P"], e["R"]))
        if not rows:
            out[name] = {"readable": False, "why": why or "the zone is not in trusted skin in any view"}
            continue
        w = np.array([r_[0] for r_ in rows])
        p, o = float(np.average([r_[1] for r_ in rows], weights=w)), float(np.average([r_[2] for r_ in rows], weights=w))
        out[name] = {"readable": True, "picture": round(p, 3), "ours": round(o, 3), "diff": round(p - o, 3)}
    return out


def fold_text(fr: dict) -> str:
    L = ["  FOLDS and LINES the shape model does not make (a valley across each feature's landmark path; log luminance; "
         "diff = the picture's over ours):"]
    for name, row in fr["folds"].items():
        if not row["readable"]:
            L.append(f"    {name:13s} {row['why']}")
            continue
        for sd, s in row["sides"].items():
            tag = f"{name}{sd}"
            if s.get("present") is None:
                L.append(f"    {tag:13s} {s['why']}")
                continue
            verdict = (f"PRESENT ({s.get('by') or 'valley'}), ours lacks it") if s["present"] else ("ours has more than the picture" if s["absent_in_picture"] else
                                                                       ("as ours" if s["picture"] >= FOLD_T else "absent"))
            L.append(f"    {tag:13s} {verdict:36s} picture {s['picture']:.3f} ours {s['ours']:.3f} diff {s['diff']:.3f} excess {s['excess']:.3f}"
                     + (f" step {s['step']:.3f}/cross-light along {int(100 * s['step_share'])} %" if s.get("step") else "") +
                     f" along {int(100 * s['share'])} %" + (f", extent {s.get('extent')}, shift mm {s.get('shift')}" if s["present"] else "") +
                     f"; confidence {s['confidence']} (views {s['views']})" +
                     ("\n" + " " * 18 + "lash line (mm over the picture's lashes; nominal = our path): " + "; ".join(
                         f"col {q['col']}: line {q['tps']} dark {q['dark']} (ours {q['dark_ours']}), nominal {q['nominal']}" for q in s["lash"]["columns"])
                      if s.get("lash") else ""))
    for name, row in fr["fields"].items():
        L.append(f"    {name + ' lines':13s} " + (f"fine-line energy over the cheek's: picture {row['picture']}, ours {row['ours']} (diff {row['diff']:+.3f}; REPORTED ONLY: follows the light)"
                                                   if row["readable"] else row["why"]))
    return "\n".join(L)


def fold_fit(sk: dict, fr: dict, first: bool, lid_prior: bool = False) -> list:
    """skin["folds"] and the fine-line amounts of skin["wrinkles"] set from a fold read (in place). Returns changes."""
    from . import skin_folds as sf
    changes, stuck = [], []
    folds = dict(sk.get("folds") or {})
    cur = sf.options(folds)
    for name, row in fr["folds"].items():
        if not row["readable"]:
            if name == "lid_fold" and name not in cur and lid_prior:
                from . import skin as skinmod
                pp = skinmod.params({"skin": sk})
                masc = float(pp.get("masc", 0.0)) if sk.get("sex") is not None else 0.5
                show = LID_PRIOR["show"][0] + (LID_PRIOR["show"][1] - LID_PRIOR["show"][0]) * masc
                sh = round(show - LID_PRIOR["nominal"], 2)
                entry = {"amount": LID_PRIOR["amount"], "roll": round(1.0 + 1.2 * skinmod._age_curve(pp["age"], 35, 75), 2),
                         "L": {"shift": [sh] * 3}, "R": {"shift": [sh] * 3}}
                hood = round(0.9 * skinmod._age_curve(pp["age"], 40, 75), 2)
                if hood >= 0.05:
                    entry["hood"] = hood
                folds[name] = entry
                changes.append((f"folds.{name}", "none", entry, f"INFERRED, NOT READ ({row.get('why', 'cannot tell')}): every lid has a fold and the shape "
                                f"model's is soft; laid from norms (platform show {show:.1f} mm over the lashes, hooding by age {pp['age']:.0f}). "
                                "Check it against the person; set skin.folds.lid_fold yourself or to 0"))
            continue
        old = cur.get(name)
        new_sides, amounts = {}, {}
        for sd, s in row["sides"].items():
            os_ = (old["sides"][sd] if old else {"amount": 0.0, "shift": [], "extent": [0.0, 1.0]})
            a0 = (old["amount"] * os_["amount"]) if old else 0.0
            if s.get("present") is None:
                amounts[sd], new_sides[sd] = a0, os_
                continue
            leg = LEGACY.get(name)
            a_leg = LEGACY_SHARE * float((sk.get("wrinkles") or {}).get(leg, 0.0)) if (leg and old is None and s["present"]) else 0.0
            a1 = a0
            if s["present"] and s["confidence"] >= FOLD_CONF:
                gain = (s["amount"] if "amount" in s else min(s["step"] / STEP_REF[name], max(STEP_MAX - a0, 0.0)) if s.get("by") == "step"
                        else s["diff"] / FOLD_REF[name])
                a1 = float(np.clip(a0 + a_leg + gain, 0, 1.5))
                if a0 > 0.2 and s.get("by") == "valley" and s["ours"] < 0.5 * a0 * FOLD_REF[name]:
                    # ours is laid and does not read under this light: more paint will not make it a form (a flat
                    # frontal light hides painted relief; the picture's fold is geometry + occlusion)
                    a1 = a0
                    stuck.append(f"{name}{sd}")
            elif s["absent_in_picture"] and a0 > 0:
                if s["picture"] >= FOLD_T and s.get("by") != "lash line":
                    # the picture has it, ours has more: toward the picture's share of ours, at most halved a round
                    a1 = float(a0 * np.clip(s["picture"] / max(s["ours"], 1e-6), 0.5, 1.0))
                else:
                    a1 = float(np.clip(a0 - s["excess"] / (LID_REF if s.get("by") == "lash line" else FOLD_REF[name]), 0, 1.5))
            amounts[sd] = a1
            shift = os_["shift"]
            if s.get("move") and a0 > 0.2:        # ours has it: move it by the two valleys' distance
                base = np.interp(np.linspace(0, 1, len(s["move"])), np.linspace(0, 1, len(shift)), shift) if shift else np.zeros(len(s["move"]))
                shift = [round(float(x), 2) for x in base + np.asarray(s["move"])]
            elif s["present"] and "shift" in s:
                shift = s["shift"]
            ext = s["extent"] if (s["present"] and "extent" in s and s["extent"][1] - s["extent"][0] > 0.2) else os_["extent"]
            me = sf.FOLDS[name].get("min_extent")
            if me and ext[1] - ext[0] < me:    # (a soft fold laid along a third of its path is a nick: a scar, not a fold)
                mid = float(np.clip(0.5 * (ext[0] + ext[1]), me / 2, 1 - me / 2))
                ext = [round(mid - me / 2, 2), round(mid + me / 2, 2)]
            new_sides[sd] = {"shift": shift, "extent": ext}
        # a fold both sides of every face have (the lid's crease): read on one side only, the other takes it over
        # (hair, a shadow or the pose hid it there): INFERRED, and said so
        mirrored = None
        if name in BILATERAL and len(amounts) == 2:
            (sa, sb) = list(amounts)
            for one, other in ((sa, sb), (sb, sa)):
                so, sn = row["sides"][one], row["sides"][other]
                if so.get("present") and so["confidence"] >= FOLD_CONF and not sn.get("present") and amounts[other] < 0.5 * amounts[one]:
                    amounts[other] = amounts[one]
                    new_sides[other] = {"shift": list(new_sides[one]["shift"]), "extent": list(new_sides[one]["extent"])}
                    mirrored = (one, other)
        # SYMMETRY AS THE PRIOR (skinfolds2): one side read with confidence, the other NOT READABLE (not seen, or pictures
        # too coarse to place a fold: there "not found" is no evidence of absence): the unread side takes the read
        # side's amount whole, INFERRED and said. (On pictures fine enough to place a fold a side that reads absent
        # stays absent: foldval's one-sided marionette.) Before: Garrett's left bag came out at 0.16 beside 0.44.
        if name in SYMMETRIC and len(amounts) == 2 and mirrored is None:
            (sa, sb) = list(amounts)
            for one, other in ((sa, sb), (sb, sa)):
                so, sn = row["sides"][one], row["sides"][other]
                poor = sn.get("present") is None or "placed" in sn
                if (so.get("present") and so["confidence"] >= FOLD_CONF and not sn.get("present") and poor and amounts[other] < 0.8 * amounts[one]) or \
                        (poor and "placed" in so and not so.get("present") and not sn.get("present") and amounts[one] > 0.2 and amounts[other] < 0.8 * amounts[one]
                         and (cur.get(name) or {}).get("sides", {}).get(one, {}).get("amount", 0) > 0):
                    amounts[other] = amounts[one]
                    new_sides[other] = {"shift": list(new_sides[other]["shift"]), "extent": list(new_sides[one]["extent"])}
                    mirrored = (one, other, "symmetry")
                    break
        if name in SYMMETRIC and len(amounts) == 2 and mirrored is None:
            (sa, sb) = list(amounts)
            for one, other in ((sa, sb), (sb, sa)):
                so, sn = row["sides"][one], row["sides"][other]
                if (so.get("present") and so["confidence"] >= FOLD_CONF and not sn.get("present") and sn.get("present") is not None
                        and sn["picture"] >= FOLD_T and sn["picture"] > sn["ours"] and amounts[other] < 0.4 * amounts[one]):
                    amounts[other] = amounts[one] * float(np.clip(sn["picture"] / max(so["picture"], 1e-6), 0.3, 1.0))
                    new_sides[other] = {"shift": list(new_sides[other]["shift"]), "extent": list(new_sides[other]["extent"])}
                    mirrored = (one, other)
        top = max(amounts.values()) if amounts else 0.0
        a_old = old["amount"] if old else 0.0
        if top < 0.08:
            if old:
                folds.pop(name, None)
                changes.append((f"folds.{name}", round(a_old, 2), "off", "the pictures do not show it"))
            continue
        moved = any(row["sides"][sd].get("move") for sd in row["sides"])
        if old is not None and abs(top - a_old) < 0.06 and not moved and all(not row["sides"][sd].get("present") for sd in row["sides"]):
            continue
        entry = {"amount": round(top, 3)}
        for sd, q in new_sides.items():
            e = {**({"amount": round(amounts[sd] / top, 3)} if abs(amounts[sd] / top - 1) > 0.05 else {}),
                 **({"shift": q["shift"]} if q["shift"] else {}), **({"extent": q["extent"]} if list(q["extent"]) != [0.0, 1.0] else {})}
            if sd:
                if e:
                    entry[sd[1:]] = e
            else:
                entry.update(e)
        if old:
            for kk in ("width", "roll", "depth", "hood"):
                if kk in (sk["folds"].get(name) if isinstance(sk["folds"].get(name), dict) else {}):
                    entry[kk] = sk["folds"][name][kk]
        folds[name] = entry
        why = "; ".join(f"{name}{sd}: valley {s['picture']:.3f} (ours {s['ours']:.3f}) along {int(100 * s['share'])} %, confidence {s['confidence']}"
                        for sd, s in row["sides"].items() if s.get("present") is not None)
        if mirrored:
            why += (f"; {name}{mirrored[1]} was not read: it takes {name}{mirrored[0]}'s (INFERRED: both sides have this fold)" if name in BILATERAL else
                    f"; {name}{mirrored[1]} CANNOT BE READ in these pictures (not seen, or too coarse to place a fold): it takes {name}{mirrored[0]}'s amount "
                    f"(INFERRED from the other side: these folds come in pairs; set skin.folds.{name}.{mirrored[1][1:]}.amount if the person is not symmetric)"
                    if len(mirrored) == 3 else
                    f"; {name}{mirrored[1]} shows a valley along too little of its path to count: it takes {name}{mirrored[0]}'s amount x its own "
                    f"valley's share (INFERRED: these folds come in pairs)")
        changes.append((f"folds.{name}", round(a_old, 2) if old else "none", entry, why))
        leg = LEGACY.get(name)
        if leg and old is None and float((sk.get("wrinkles") or {}).get(leg, 1.0)) != 0.0:
            sk.setdefault("wrinkles", {})[leg] = 0.0
            changes.append((f"wrinkles.{leg}", "by age / as set", 0.0, f"replaced by the measured folds.{name}"))
    if folds:
        sk["folds"] = folds
    else:
        sk.pop("folds", None)
    if stuck:
        changes.append(("folds (NOT raised)", "", "", ", ".join(stuck) + ": laid, yet our render shows less than a third of what that "
                        "amount should read under the picture's light. Painted relief does not carry it: the picture's fold is "
                        "geometry (sculpt / block-in), not more paint"))
    from . import skin as skinmod
    p = skinmod.params({"skin": sk})
    for name, row in fr["fields"].items():
        # FIELD_FIT is off: the validation's null (the same lines in picture and ours, another light) read +0.47 where
        # lines against none read +0.65: fine-line energy follows the light as much as the lines. Reported, not fitted.
        if not FIELD_FIT or not row["readable"] or abs(row["diff"]) < FIELD_T:
            continue
        age = p["age"]
        dflt = {"forehead": skinmod._age_curve(age, 26, 72), "crows_feet": skinmod._age_curve(age, 28, 70),
                "under_eye": skinmod._age_curve(age, 30, 75), "lip_lines": skinmod._age_curve(age, 48, 85)}[name]
        a0 = float((sk.get("wrinkles") or {}).get(name, dflt))
        a1 = round(float(np.clip(a0 + row["diff"] / FIELDS[name][2], 0, 2.0)), 3)
        if abs(a1 - a0) > 0.08:
            sk.setdefault("wrinkles", {})[name] = a1
            changes.append((f"wrinkles.{name}", round(a0, 3), a1, f"fine-line energy over the cheek's: picture {row['picture']}, ours {row['ours']}"))
    return changes
