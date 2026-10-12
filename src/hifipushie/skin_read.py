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
             "mm_native": 1000.0 * float(np.median(z)) / cam["f"],
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
    ir = 0.5 * float(((spec.get("skin") or {}).get("eyes") or {}).get("iris_size", 0.0118))
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


def _anchor(frames: list, mesh: dict, spec: dict, mode: str = "auto") -> dict:
    """The picture's exposure and white balance against our render's: {"kind": "sclera" | "backdrop" | "none",
    "gain": per view [r, g, b] the ratio P / R is divided by, "note"}. sclera: ours through the same camera (both
    exposure and white balance); backdrop: a plain neutral backdrop gives the light's colour (lightness kept)."""
    from scipy import ndimage
    Y = np.array([0.2126, 0.7152, 0.0722])
    sc, bd = {}, {}
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
    if mode == "sclera" and sc:   # (not in "auto": on photographs the sclera reads 0.5-0.6 x ours against the skin and its
        # colour differs view to view; it failed as an anchor, see docs/notes/skin.md "## skinread")
        g = np.median([v[0] for v in sc.values()], 0)   # one camera set-up for a reference set: one gain
        return {"kind": "sclera", "gain": {f["view"]: (sc[f["view"]][0] if f["view"] in sc else g) for f in frames},
                "note": f"sclera through the same camera in view(s) {sorted(sc)} ({', '.join(str(v[1]) for v in sc.values())} px): "
                        "exposure and white balance; the tone's lightness rests on the sclera being lit as ours is (INFERRED)"}
    if mode in ("auto", "backdrop") and bd:
        return {"kind": "backdrop", "gain": {f["view"]: bd.get(f["view"]) for f in frames}, "level": True,
                "note": f"plain neutral backdrop in view(s) {sorted(bd)}: white balance only (the exposure stays free)" +
                        ("" if len(bd) == len(frames) else "; the other view(s) have their own light and no anchor: their plain skin "
                         "is set to the anchored views' (they give zones, lips and folds, not the tone)")}
    return {"kind": "none", "gain": {f["view"]: None for f in frames},
            "note": "no anchor (no readable sclera, no plain neutral backdrop): the base tone is NOT READ; zones, lips and "
                    "marks are read against the face's own plain skin"}


class Context:
    """The pooled trusted pixels of every view with the picture's albedo there, and the forward model to fit to."""


def context(name: str, spec: dict | None = None, frames: list | None = None, anchor: str = "auto", log=print) -> Context:
    from scipy import ndimage
    from . import likeness as lk, store
    spec = spec or store.load(name)
    frames = frames or capture(name, spec, log=log)
    mesh = lk.model_mesh(spec["base"])
    an = _anchor(frames, mesh, spec, anchor)
    X, n, w, vw, rho, pix = [], [], [], [], [], []
    views = []
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
        if g is None:
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
    c.views = views
    c.T = c.A0 * c.rho
    c.dlab = lab(c.T) - lab(c.A0)
    c.J = None
    return c


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


# ---------------------------------------------------------------- the read

def read(name: str, spec: dict | None = None, frames: list | None = None, anchor: str = "auto", log=print, ctx: Context | None = None) -> dict:
    """The measurements: {"anchor", "views", "regions": {region: {"px", "ours" Lab, "picture" Lab, "d", "by_view"}},
    "freckles", "brows", "eyes", "text", "ctx" (the Context, for `fit`)}."""
    c = ctx or context(name, spec, frames, anchor, log)
    R = regions(c)
    out = {"anchor": {k: v for k, v in c.anchor.items() if k != "gain"}, "views": c.views,
           "regions": {k: _region(c, wz) for k, wz in R.items()}}
    out["freckles"] = _freckle_read(c)
    out["brows"] = _brow_read(c)
    out["eyes"] = _eye_read(c)
    out["folds"] = fold_read(c)
    out["ctx"] = c
    out["text"] = read_text(out)
    return out


def read_text(r: dict) -> str:
    L = [f"SKIN READ (the picture's albedo against ours, CIE Lab; d = picture - ours; anchor: {r['anchor']['kind']})",
         "  " + r["anchor"]["note"]]
    for v in r["views"]:
        L.append(f"  view {v['view']}: {v['mm_per_px']} mm a pixel, {v['trusted_px']} trusted px, weight {v['weight']}"
                 + (f" (the light changes colour across the face: {v['light_spread']})" if v["weight"] < 0.6 else ""))
    L.append(f"  (mm a pixel: the PICTURE's own, at the face) {'region':16s} {'px':>7s}  {'ours L a b':20s} {'picture L a b':20s} d L a b")
    for k, x in r["regions"].items():
        L.append(f"  {k:16s} {x['px']:7.0f}  " + (f"{str(x['ours']):20s} {str(x['picture']):20s} {x['d']}" if x["read"] else "NOT READ"))
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
          "lips.blood": (0.15, 3.0), "lips.melanin": (0.2, 9.0), "lips.lower.blood": (0.4, 2.5), "lips.lower.melanin": (0.4, 2.5),
          }
GROUPS = {"tone": ("tone.melanin", "tone.blood", "tone.undertone"),
          "zones": ("zones.forehead_yellow", "zones.midface_red", "zones.nose_red", "zones.perioral_red", "zones.lower_cool",
                    "features.flush"),
          "eyes": ("zones.under_eye", "zones.eyelids", "zones.periorbital"),
          "lips": ("lips.blood", "lips.melanin", "lips.lower.blood", "lips.lower.melanin"),
          "stubble": (), "brows": (), "freckles": (), "eyeballs": (), "folds": ()}
DEFAULT_GROUPS = ("tone", "zones", "eyes", "lips", "stubble", "brows", "freckles", "eyeballs", "folds")
SIGMA = (6.0, 0.8, 0.8)     # Lab: what a region's read is worth (lightness carries the shading we do not model)
EXPOSURE = 0.5            # log units: how loosely the picture's unknown exposure is held to our skin's lightness
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


def fit(r: dict, groups=DEFAULT_GROUPS, stubble: bool | None = None, log=print) -> dict:
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
        sig.append(np.hypot(SIGMA, sp) / np.sqrt(min(r["regions"][k]["px"], 2000.0) / 2000.0))
    sig = np.array(sig)

    # A white-balance-only anchor gives the picture's albedo up to ONE unknown factor (its exposure): that factor is a
    # free parameter of the solve (held to 1 only weakly), so the tone is found from the skin's chromaticity (in the
    # pigment model a darker skin is a more saturated one) and no layer is bent to explain a lightness nobody measured.
    free_e = "tone" in groups and anchored and bool(c.anchor.get("level"))
    np_ = len(names) + len(bz)

    def resid(x):
        m, _ = model(x[:np_])
        tg = _lab_scale(target, float(np.exp(x[np_]))) if free_e else target
        return np.concatenate([((m - tg) / sig).ravel(), PRIOR * len(reg) ** 0.5 * (x[:np_] - x0[:np_]) / (hi - lo)[:np_]] +
                              ([[len(reg) ** 0.5 * x[np_] / EXPOSURE]] if free_e else []))

    if free_e:
        x0, lo, hi = np.r_[x0, 0.0], np.r_[lo, -1.2], np.r_[hi, 1.2]

    t = time.time()
    # (a start on a bound never leaves it in a trust-region reflective solve: begin a little inside)
    xi = np.clip(x0, lo + 0.06 * (hi - lo), hi - 0.06 * (hi - lo))
    if proto:
        xi[len(names):np_] = 0.5
    sol, cost = None, np.inf
    for _ in range(6):   # (the solve stops early on its step tolerance in this bounded, curved problem: restart it)
        s_ = least_squares(resid, xi, bounds=(lo, hi), diff_step=0.02, x_scale=(hi - lo), max_nfev=30, xtol=1e-5, ftol=1e-6)
        if sol is not None and s_.cost > cost * 0.985:
            sol = s_ if s_.cost < cost else sol
            break
        sol, cost = s_, s_.cost
        xi = np.clip(s_.x, lo + 0.01 * (hi - lo), hi - 0.01 * (hi - lo))
    m1, sk1 = model(sol.x[:np_])
    expo = float(np.exp(sol.x[np_])) if free_e else 1.0
    if free_e:
        target = _lab_scale(target, expo)
    log(f"skin_read fit: {len(names) + len(bz)} parameters over {len(reg)} regions, status {sol.status}, {time.time() - t:.0f} s; "
        f"chi2 {float((((base0 - target) / sig) ** 2).sum()):.0f} -> {float((((m1 - target) / sig) ** 2).sum()):.0f}")
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
        if np.abs(lab(_lin(want)) - lab(_lin(shown))).max() > 2.0:
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
    if "eyeballs" in groups and sk1.get("eyes") is not False:
        from . import paint
        ey = dict(sk1.get("eyes") or {})
        for key, dflt, lim in (("iris", "#5a3a1e", (0.5, 2.0)),):
            e = r["eyes"][key]
            if not e["read"] or not r["eyes"]["sclera"]["read"]:
                continue
            c0 = np.asarray(paint.colour(ey.get(key, dflt)), float)[:3]
            # against the sclera beside it (taken as ours): an eye's lid shadow and the exposure cancel
            ratio = np.clip(np.asarray(e["ratio"]) / np.asarray(r["eyes"]["sclera"]["ratio"]), *lim)
            want = _srgb(np.clip(_lin(c0) * ratio, 0, 1))
            if np.abs(lab(_lin(want)) - lab(_lin(c0))).max() > 2.0:
                ey[key] = "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in np.clip(want, 0, 1))
                changes.append((f"eyes.{key}", "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in c0), ey[key],
                                f"picture / ours {[round(float(x), 2) for x in ratio]} against the sclera beside it (INFERRED: the sclera taken as ours)"))
        if ey:
            sk1["eyes"] = ey
    if "folds" in groups and r.get("folds"):
        changes += fold_fit(sk1, r["folds"], True)
    resid_rows = {k: {"before": [round(float(x), 2) for x in (base0[i] - target[i])], "after": [round(float(x), 2) for x in (m1[i] - target[i])]}
                  for i, k in enumerate(reg)}
    out = {"skin": sk1, "changes": changes, "residual": resid_rows, "exposure": round(expo, 3)}
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
    if f.get("exposure", 1.0) != 1.0:
        L.append(f"  the picture's exposure against our render: x {f['exposure']} (a free factor: the tone's lightness comes from the "
                 "skin's chromaticity through the pigment model, INFERRED)")
    for p, a, b, why in f["changes"]:
        L.append(f"  {p}: {a} -> {b}   [{why}]")
    if not f["changes"]:
        L.append("  nothing: the description already matches the read within its tolerance")
    worst = sorted(f["residual"].items(), key=lambda kv: -max(abs(kv[1]["after"][1]), abs(kv[1]["after"][2]), abs(kv[1]["after"][0]) / 4))[:6]
    L.append("  what the fit leaves (ours - picture, Lab, as the forward model has it): " +
             "; ".join(f"{k} {v['after']}" for k, v in worst))
    return "\n".join(L)


def apply(name: str, out: str | None = None, groups=DEFAULT_GROUPS, rounds: int = 2, anchor: str = "auto", stubble: bool | None = None,
          brow_shape: bool = True, log=print) -> dict:
    """Read the references, set spec["skin"] from the read, save (onto `out`: a block-in fork of `name`, or `name`
    itself). rounds: read -> fit -> re-render -> read again (the second round corrects what the first could only
    estimate: freckle and beard densities, brow coverage). Returns {"model", "reads": [text per round], "fits",
    "skin", "text"}."""
    from . import blockin, store
    dst = out or name
    if out and out != name:
        blockin.fork(name, out, replace=True)
    reads, fits = [], []
    for k in range(max(int(rounds), 1)):
        r = read(dst, anchor=anchor, log=log)
        f = fit(r, groups=groups, stubble=stubble, log=log)
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
    final = read(dst, anchor=anchor, log=log)
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
FOLD_MOVE = 1.5        # mm: a fold of ours is moved only when the picture's lies this far from it (median)
FOLD_STEP = 0.25       # mm between a profile's samples
# what an amount-1 fold of ours reads as (median valley depth, log luminance, under the pictures' fitted lights):
# calibrated on synthetic heads (spikes/skinread/foldval.py); the second round corrects what this gets wrong
FOLD_REF = {"nasolabial": 0.15, "marionette": 0.11, "mouth_corner": 0.2, "mentolabial": 0.3, "tear_trough": 0.22,
            "lid_fold": 0.2, "glabella": 0.135}
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


def _fold_view(f: dict, q: dict, fd: dict) -> dict | None:
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
    valid = seen & (gs.mean(1) > 0.8)
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
    out["valid"] = valid
    out["picture"], out["ours"] = out["picture"] * valid, out["ours"] * valid
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
    for name, fd in sf.FOLDS.items():
        ok_views = [f for f in c.frames if native[f["view"]] <= fd["res"]]
        row = {"readable": bool(ok_views), "sides": {}, "about": fd["about"]}
        if not ok_views:
            row["why"] = (f"cannot tell: the pictures have {min(native.values()):.2f} mm a pixel at the face, this needs "
                          f"{fd['res']} or finer (a {fd['width']} mm feature)")
            out[name] = row
            continue
        for sd in ((".L", ".R") if sf.sided(name) else ("",)):
            q = nominal[(name, sd)]
            best, acc = None, []
            for f in ok_views:
                r_ = _fold_view(f, q, fd)
                if r_ is None:
                    continue
                vw = next(v for v in c.views if v["view"] == f["view"])["weight"]
                acc.append((f["view"], r_, vw * float(r_["valid"].sum()) * r_["scale"]))
            if not acc:
                row["sides"][sd] = {"present": None, "why": "not seen (turned away, hidden, or under hair) in any view"}
                continue
            res = {"views": [a[0] for a in acc]}
            wsum = sum(a[2] for a in acc)
            stat = {k: 0.0 for k in ("picture", "ours", "diff", "excess", "share")}
            for vi, r_, w in acc:
                val = r_["valid"]
                hit = val & (r_["picture"] - r_["ours"] >= FOLD_T) & (r_["picture"] >= FOLD_T)
                run = _run(hit)
                sel = np.zeros(len(val), bool)
                if run:
                    sel[run[0]:run[1] + 1] = True
                sel &= val
                use = sel if sel.sum() >= 4 else val
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
            res["confidence"] = round(float(np.clip(stat["diff"] / (2.5 * FOLD_T), 0, 1) * np.clip(stat["share"] / 0.7, 0, 1)), 2)
            row["sides"][sd] = res
        out[name] = row
    return {"folds": out, "fields": _field_read(c, native)}


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
            verdict = "PRESENT, ours lacks it" if s["present"] else ("ours has more than the picture" if s["absent_in_picture"] else
                                                                       ("as ours" if s["picture"] >= FOLD_T else "absent"))
            L.append(f"    {tag:13s} {verdict:28s} picture {s['picture']:.3f} ours {s['ours']:.3f} diff {s['diff']:.3f} excess {s['excess']:.3f}"
                     f" along {int(100 * s['share'])} %" + (f", extent {s['extent']}, shift mm {s.get('shift')}" if s["present"] else "") +
                     f"; confidence {s['confidence']} (views {s['views']})")
    for name, row in fr["fields"].items():
        L.append(f"    {name + ' lines':13s} " + (f"fine-line energy over the cheek's: picture {row['picture']}, ours {row['ours']} (diff {row['diff']:+.3f}; REPORTED ONLY: follows the light)"
                                                   if row["readable"] else row["why"]))
    return "\n".join(L)


def fold_fit(sk: dict, fr: dict, first: bool) -> list:
    """skin["folds"] and the fine-line amounts of skin["wrinkles"] set from a fold read (in place). Returns changes."""
    from . import skin_folds as sf
    changes = []
    folds = dict(sk.get("folds") or {})
    cur = sf.options(folds)
    for name, row in fr["folds"].items():
        if not row["readable"]:
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
                a1 = float(np.clip(a0 + a_leg + s["diff"] / FOLD_REF[name], 0, 1.5))
            elif s["absent_in_picture"] and a0 > 0:
                a1 = float(np.clip(a0 - s["excess"] / FOLD_REF[name], 0, 1.5))
            amounts[sd] = a1
            shift = os_["shift"]
            if s.get("move") and a0 > 0.2:        # ours has it: move it by the two valleys' distance
                base = np.interp(np.linspace(0, 1, len(s["move"])), np.linspace(0, 1, len(shift)), shift) if shift else np.zeros(len(s["move"]))
                shift = [round(float(x), 2) for x in base + np.asarray(s["move"])]
            elif s["present"] and "shift" in s:
                shift = s["shift"]
            new_sides[sd] = {"shift": shift,
                             "extent": s["extent"] if (s["present"] and "extent" in s and s["extent"][1] - s["extent"][0] > 0.2) else os_["extent"]}
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
            for kk in ("width", "roll"):
                if kk in (sk["folds"].get(name) if isinstance(sk["folds"].get(name), dict) else {}):
                    entry[kk] = sk["folds"][name][kk]
        folds[name] = entry
        why = "; ".join(f"{name}{sd}: valley {s['picture']:.3f} (ours {s['ours']:.3f}) along {int(100 * s['share'])} %, confidence {s['confidence']}"
                        for sd, s in row["sides"].items() if s.get("present") is not None)
        changes.append((f"folds.{name}", round(a_old, 2) if old else "none", entry, why))
        leg = LEGACY.get(name)
        if leg and old is None and float((sk.get("wrinkles") or {}).get(leg, 1.0)) != 0.0:
            sk.setdefault("wrinkles", {})[leg] = 0.0
            changes.append((f"wrinkles.{leg}", "by age / as set", 0.0, f"replaced by the measured folds.{name}"))
    if folds:
        sk["folds"] = folds
    else:
        sk.pop("folds", None)
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
