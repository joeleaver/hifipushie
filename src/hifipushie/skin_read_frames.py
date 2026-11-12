"""The dressed stage and the frames: our head through each reference's camera under its light, the trust mask, the
de-lit atlas as a source, and our albedo in Python. Part of the skin read (skin_read.py has the overview)."""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from . import skin_read
from .skin_read import _lin, _srgb

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
    from . import base as basemod
    src = Path(__file__).parent
    return hashlib.sha1(b"".join((src / f).read_bytes() for f in
                                 ("skin.py", "skin_features.py", "skin_makeup.py", "skin_marks.py", "skin_swatch.py", "skin_folds.py", "paint.py",
                                  "paintnodes.py", "blender_scene.py", "base.py", *(f"{m}.py" for m in basemod.MODULES),  # (base.py was split, C417)
                                  "skin_look.py", "scene.py"))).hexdigest()[:12]


def stage(name: str, spec: dict | None = None, log=print) -> str:
    """The stage model of `name` (or of `spec`, a variant of it), synced when its spec or the skin code changed."""
    from . import scene, store, stylesheet
    st = stage_spec(spec or store.load(name))
    sn = skin_read.STAGE + name
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


def shoot(sn: str, frames: list, lighting: dict | None, size: int = 2 * skin_read.N, flat: bool = False, samples: int = 24) -> dict:
    """Frames of a stage under one lighting: {frame name: RGBA uint8 array}. flat: the unlit albedo."""
    from PIL import Image
    from . import scene
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
        job = {"blend": str(scene.blend_path(sn)), "views": fr, "size": size, "samples": samples, "hide": [], "flat": flat,
               "transparent": True, "mode": "render", "eevee": skin_read.EEVEE}
        if lighting and not flat:
            job["lighting"] = {**lighting, "target": fr[0]["center"]}
        scene._blender(job, 2400)
        for f in fr:
            out[f["name"]] = np.asarray(Image.open(f["out"]).convert("RGBA")).copy()
    return out


def boxes(name: str) -> list:
    """Each view's square crop (picture pixels): the block-in's own, else round the fitted landmarks."""
    from . import store
    from . import blockin_models
    rj = blockin_models._refs(name)
    b = (rj.get("blockin") or {}).get("boxes")
    return [[float(x) for x in q] for q in (b or blockin_models._boxes(store.load(name)["base"], rj))]


def lighting(name: str, vi: int) -> dict:
    """LIGHT re-aimed and re-balanced to view vi's own fitted light."""
    from . import blockin_look
    return blockin_look.photo_lighting(name, skin_read.LIGHT, vi)


def photo_light(name: str, vi: int | None = None) -> dict:
    """View vi's fitted light (default: the front view's) AT THE PICTURE'S EXPOSURE: `lighting` + "exposure" = the EV
    the last read measured between our render under that light and the picture on the plain skin (`context` stores
    it beside the stage; "measured": False and EV 0 when no read has run). For renders set beside the reference.
    WHY (skinfolds2): blockin_look.photo_lighting keeps the face's front as bright as its TEMPLATE lights it, which is not
    how bright the photographer exposed it. The judging sheets' template (-0.55 EV, a filmic view) put every dressed
    head ~10 L under its reference, and the same albedo 10 L down reads as a tan."""
    from . import store
    from . import blockin_clay, blockin_models
    vi = blockin_clay._front(blockin_models._refs(name)) if vi is None else vi
    lt = lighting(name, vi)
    ev = None
    try:
        ev = json.loads((store._dir(skin_read.STAGE + name) / "sr_exposure.json").read_text()).get(str(vi))
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
    from . import humanfit, resources, store
    from . import likeness_render
    from . import blockin_models
    spec = spec or store.load(name)
    rj = blockin_models._refs(name)
    bx = boxes(name)
    idx = [i for i in (range(len(rj["views"])) if views is None else views)
           if rj["views"][i].get("image") and rj["cameras"][i] is not None]
    mesh = likeness_render.model_mesh(spec["base"])
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
        P = _lin(np.asarray(img.crop(ib).resize((skin_read.N, skin_read.N), Image.LANCZOS), float) / 255.0)
        _, k, ps = likeness_render.render(mesh, cam, box, px=skin_read.N, passes=True)
        zb, nrm, part = ps["zb"], ps["nrm"], ps["part"]
        part = part[..., 0] if part.ndim == 3 else part
        on = np.isfinite(zb)
        ii, jj = np.nonzero(on)
        z = zb[ii, jj]
        u, vv = box[0] + (jj + 0.5) / k, box[1] + (ii + 0.5) / k
        Rc = humanfit._cam_rot(cam)
        Xc = np.c_[(u - w / 2) / cam["f"] * z, (vv - h / 2) / cam["f"] * z, z]
        X = np.zeros((skin_read.N, skin_read.N, 3))
        X[ii, jj] = (Xc - np.asarray(cam["t"], float)) @ Rc + np.asarray(cam["centre"], float)
        nw = np.zeros((skin_read.N, skin_read.N, 3))
        nw[ii, jj] = nrm[ii, jj] @ Rc
        fac = np.zeros((skin_read.N, skin_read.N))
        fac[ii, jj] = -(nrm[ii, jj] * (Xc / np.linalg.norm(Xc, axis=1, keepdims=True))).sum(1)
        pm = _picture_masks(img, cam, mesh)
        parse = {}
        for kname, m in pm.items():
            parse[kname] = np.asarray(Image.fromarray(np.round(m * 255).astype(np.uint8)).crop(ib).resize((skin_read.N, skin_read.N), Image.BILINEAR), float) / 255.0
        ys_ = np.nonzero((on & (np.round(part) == 0)).any(1))[0]
        chin_y = box[1] + (float(np.percentile(ys_, 80)) if len(ys_) else 0.8 * skin_read.N) / k       # picture px: under this is not face
        f = {"view": i, "white_patch": white_patch(_lin(np.asarray(img, float) / 255.0), pm, chin_y),
             "P": P, "X": X, "n": nw, "skin": on & (np.round(part) == 0), "eye": on & (np.round(part) == 1),
             "facing": fac, "parse": parse, "mm": 1000.0 * float(np.median(z)) / cam["f"] / k, "box": list(box), "cam": cam,
             "mm_native": 1000.0 * float(np.median(z)) / cam["f"],
             "image": v["image"], "yaw": float(v.get("yaw", 0.0))}
        if render:
            r = np.asarray(Image.fromarray(shots[i]).resize((skin_read.N, skin_read.N), Image.LANCZOS), float) / 255.0
            f["R"], f["alpha"] = _lin(r[..., :3]), r[..., 3]
            f["R2"] = shots[i][..., :3].copy()          # (sRGB uint8, 2N: the lid's fold line is read on it)
        out.append(f)
    return out


def trust(f: dict) -> np.ndarray:
    """0..1 per pixel: the model's skin facing the camera, the picture's parser agreeing it is skin, nothing clipped."""
    t = f["skin"] * np.clip((f["facing"] - skin_read.FACE[0]) / (skin_read.FACE[1] - skin_read.FACE[0]), 0, 1)
    if f["parse"]:
        t = t * np.clip((f["parse"]["skin"] - 0.5) / 0.3, 0, 1) * np.clip((0.4 - f["parse"]["hair"]) / 0.3, 0, 1)
    ps = _srgb(f["P"])
    t = t * ((ps.min(-1) > skin_read.CLIP[0]) & (ps.max(-1) < skin_read.CLIP[1]))
    if "R" in f:
        rs = _srgb(f["R"])
        t = t * (f["alpha"] > 0.98) * ((rs.min(-1) > skin_read.CLIP[0]) & (rs.max(-1) < skin_read.CLIP[1]))
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
    from . import skin_project_lookup
    st = stage_spec(spec)
    H, W = src["conf"].shape
    u0, v0, u1, v1 = src["box"]
    out = []
    for f in frames:
        sk = f["skin"]
        X, n = f["X"][sk], f["n"][sk]
        u, v, w = skin_project_lookup.lookup(spec["base"], X)
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
    m &= (srgb.max(-1) < skin_read.CLIP[1]) & (srgb.min(-1) > (0.2 if box is not None else 0.35))
    if m.sum() < skin_read.WHITE_PX:
        return None
    c = img[m]
    y = c @ Yv
    lit = c[y >= np.percentile(y, 60)]
    med = np.median(lit, 0)
    ys, xs = np.nonzero(m)
    return {"Y": float(med @ Yv), "rgb": med, "px": int(m.sum()), "declared": box is not None,
            "where": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]}
