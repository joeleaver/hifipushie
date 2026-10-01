"""Images as paint: a picture in a frame, a printed page, a poster, a label, a logo on a shirt.

The paint generator `image` lays an image on the surface as a projected decal (planar, along a facing direction):

  "image": {"file": path (a PNG/JPEG/...; copied into the content store at save and replaced by "id")
                | "id": 16 hex digits (an image in workspace/_images/)
                | "text": {...} (text set on a page, below),
            "at": joint | blob | [x, y, z] | {"bone", "t"}: the decal's centre. A blob (a canvas, a sign board, a
                label) puts the centre on that blob's face named by "dir",
            "dir": [x, y, z] (the way the printed surface faces: the decal is seen looking against it) | "front" |
                "back" | "left" | "right" | "top" | "bottom" (the "at" blob's own faces; front = its local -Y),
                default "front" for a blob, else [0, -1, 0],
            "up": [x, y, z] (default world Z, or the blob's local Z / +Y for top and bottom faces),
            "size": [w, h] m (null for one of them: from the image's aspect), "rotate": deg (about dir),
            "depth": m (how far in front of / behind the decal's plane it reaches: 0.25 x its larger side),
            "facing": 0..1 (0.3: skin facing away from dir by more than this doesn't take it, so a thin board's
                back stays clean),
            "channel": "alpha" (default: the image's coverage, PNG alpha) | "luma" | "r" | "g" | "b" | "coverage"
                (the whole rectangle),
            "flip": true (mirror the picture left-right), "mirror": true (also at the X-mirrored placement, the
                picture still reading the right way),
            "wrap": "planar" (default) | "cylinder" | "sphere" | "surface" (below),
            "style": true (the picture's colours through the paint style's saturation and value),
            "on": part(s) whose surface a wrap measures (default the layer's parts)}

Wraps, so a label isn't stretched round a curved thing:
  "cylinder": a label round a can, mug or bottle, a print round a sleeve. "axis": a bone | [joint, joint] |
      [x, y, z] (through "at") | {"at", "dir"}; default the "at" blob's own z axis. "at" sets the label's height
      (projected onto the axis), "dir" the way its centre faces (off the axis; default front). Width: "size"
      [w, h] in metres round the surface, or "span": degrees round (height from size [null, h] or the aspect).
      "seam": deg from the centre where the wrap is cut (180: behind). The surface's radius above and below the
      centre gives a local cone (r0 + m t); "unroll": "auto" fan-cuts the label on a taper (|m| > TAPER: rows
      round the axis, the ends along the cone's lines, even height, like a paper neck label) and is a plain
      cylinder otherwise; "cone" / "arc" force one ("arc": each row its true length at its own radius, v = height
      along the axis: the ends lean on a taper). Depth = distance off that cone; facing = against its normal.
  "sphere": a globe or a ball. "at" = the centre, "axis" = the poles (default the blob's z), "dir" = the
      decal's centre (latitude included). "span": [round, up] degrees ([360, 180]: equirectangular), or "size" in
      metres at the surface.
  "surface": a sticker lying on any curved surface: geodesic polar coordinates from its centre ("at", seated on
      the field; "up" orients it, "dir" only picks a blob's face). decalmap.py; measured per vertex in the scene.
Cylinder and sphere are computed per pixel in the look's shader nodes (and so in the export's Cycles bake).

As a layer's flat key with "color": "image" the layer paints the image's own colours (masked by the channel);
with a plain colour, or in a mask stack, it is a mask like any generator (a stencil). Height x mask gives relief:
{"height": 0.0008, "image": {..., "channel": "luma"}} raises the light parts (impasto, embossing).

Text: {"string": "...", ("\\n" breaks a line, a blank line between paragraphs), "font": "serif" | "sans" | "mono"
(+ "-bold", "-italic") | a .ttf path, "size": m (em height on the surface, 0.004), "color" ("#111111"),
"background": colour or null (transparent), "align": "left" | "center" | "right" | "justify", "margin": m
(0.012), "line": spacing x size (1.35), "px_per_m": render resolution (6000: 0.17 mm pixels)}. The page is the
decal's size (give "size": [w, null] to fit the page height to the text). Rendered once, cached by content.

Look shows decals per pixel (shader nodes read the image), the export bakes them through Cycles at the atlas'
texel density, raised automatically over each decal (asset.decal_focus) to keep about the image's resolution.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from .spec import SpecError

TEXT_VERSION = 2  # bump when text rendering changes
INK = 0.5  # coverage -> alpha exponent (ink spread)
MAX_PX = 4096  # a text page's longer side at most
FACES = {"front": (0, -1, 0), "back": (0, 1, 0), "left": (1, 0, 0), "right": (-1, 0, 0), "top": (0, 0, 1),
         "bottom": (0, 0, -1)}
KEYS = {"file", "id", "text", "name", "at", "dir", "up", "size", "rotate", "depth", "facing", "channel", "flip",
        "mirror", "wrap", "axis", "seam", "span", "style", "on", "unroll"}
WRAPS = ("planar", "cylinder", "sphere", "surface")
UNROLLS = ("auto", "cone", "arc")
TAPER = 0.02  # |d radius / d height| over a cylinder wrap's label above which "auto" unrolls it as a cone
TEXT_KEYS = {"string", "font", "size", "color", "background", "align", "margin", "line", "px_per_m"}
CHANNELS = ("alpha", "luma", "r", "g", "b", "coverage")
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF",
             "/Library/Fonts", "C:/Windows/Fonts"]
FONTS = {"sans": "DejaVuSans", "serif": "DejaVuSerif", "mono": "DejaVuSansMono"}


def store_dir() -> Path:
    from . import store
    return store.HOME / "_images"


def id_path(iid: str) -> Path:
    """Where a stored image lives. The id comes from the spec, so it must be a content id, never a path."""
    if not (isinstance(iid, str) and re.fullmatch(r"[0-9a-f]{16}", iid)):
        raise SpecError(f"image id {iid!r} isn't one (16 hex digits, as the image store names them)")
    return store_dir() / f"{iid}.png"


def _bleed(a: np.ndarray) -> np.ndarray:
    """RGBA uint8 with each transparent pixel's colour taken from the nearest visible one (alpha kept), so
    filtering at a decal's edge doesn't pull in the black of transparent pixels."""
    from scipy.ndimage import distance_transform_edt
    on = a[..., 3] > 8
    if on.all() or not on.any():
        return a
    _, (iy, ix) = distance_transform_edt(~on, return_indices=True)
    out = a.copy()
    out[..., :3] = a[iy, ix, :3]
    return out


def ingest(path) -> str:
    """Copy an image file into the content store (as an RGBA PNG) and return its id (a hash of the file's bytes)."""
    from PIL import Image
    p = Path(path).expanduser()
    if not p.is_file():
        from . import store
        alt = store.HOME / str(path)
        if not alt.is_file():
            raise SpecError(f"image file {str(path)!r} not found")
        p = alt
    raw = p.read_bytes()
    iid = hashlib.sha1(raw).hexdigest()[:16]
    out = id_path(iid)
    if not out.exists():
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            raise SpecError(f"image file {str(path)!r} isn't an image PIL can read ({e})") from e
        a = np.asarray(im.convert("RGBA"))
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.png")
        Image.fromarray(_bleed(a)).save(tmp)
        tmp.replace(out)
    return iid


def _entries(obj):
    """Every image dict in a paint layer or mask entry, nested stacks included."""
    if isinstance(obj, dict):
        if isinstance(obj.get("image"), dict):
            yield obj["image"]
        for e in obj.get("mask") or []:
            yield from _entries(e)


def layer_images(ly: dict) -> list:
    return list(_entries(ly))


def ingest_spec(spec: dict) -> dict:
    """The spec with every paint image given by "file" copied into the store and named by "id" (the file's name
    kept as "name"), so a model's spec stays portable and each version keeps its own picture."""
    paint = spec.get("paint")
    if not paint or not any(isinstance(img, dict) and "file" in img
                            for ly in paint.values() for img in _entries(ly)):
        return spec
    import copy
    spec = copy.deepcopy(spec)
    for ly in spec["paint"].values():
        for img in _entries(ly):
            if "file" in img:
                f = img.pop("file")
                img["id"] = ingest(f)
                img.setdefault("name", Path(str(f)).name)
    return spec


# ---- text ---------------------------------------------------------------------------------------------------------

def _font_file(name: str) -> str | None:
    if name.lower().endswith((".ttf", ".otf", ".ttc")):
        return name if Path(name).is_file() else None
    base, *style = name.split("-")
    stem = FONTS.get(base, base)
    sfx = {"bold": "-Bold", "italic": "-Oblique" if base != "serif" else "-Italic",
           "bolditalic": "-BoldOblique" if base != "serif" else "-BoldItalic"}.get("".join(style).lower(), "")
    for d in FONT_DIRS:
        f = Path(d) / f"{stem}{sfx}.ttf"
        if f.is_file():
            return str(f)
    return None


def _font(name: str, px: int):
    from PIL import ImageFont
    f = _font_file(name)
    return ImageFont.truetype(f, px) if f else ImageFont.load_default(px)


def _text_key(t: dict, w: float, h) -> str:
    f = _font_file(str(t.get("font", "serif")))
    fh = hashlib.sha1(Path(f).read_bytes()).hexdigest()[:12] if f else "default"
    return hashlib.sha1(json.dumps([t, w, h, fh, TEXT_VERSION], sort_keys=True, default=str).encode()).hexdigest()[:16]


def _wrap(text: str, font, width: float) -> list[tuple[list[str], bool]]:
    """Lines as (words, last line of its paragraph)."""
    out = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            out.append(([], True))
            continue
        line: list[str] = []
        for wd in words:
            if line and font.getlength(" ".join(line + [wd])) > width:
                out.append((line, False))
                line = [wd]
            else:
                line.append(wd)
        out.append((line, True))
    return out


def render_text(t: dict, w: float, h) -> "Image.Image":
    """A text page w x h metres (h None: as tall as the text) as an RGBA image."""
    from PIL import Image, ImageDraw
    from .paint import colour
    ppm = float(t.get("px_per_m", 6000.0))
    size, margin = float(t.get("size", 0.004)), float(t.get("margin", 0.012))
    lead = float(t.get("line", 1.35)) * size
    font = _font(str(t.get("font", "serif")), 64)  # measure at a fixed size, scale to the page
    probe = 64 / size  # px per m at the probe size
    lines = _wrap(str(t.get("string", "")), font, (w - 2 * margin) * probe)
    if h is None:
        h = 2 * margin + len(lines) * lead
    ppm = min(ppm, MAX_PX / max(w, h))
    W, H = max(int(round(w * ppm)), 1), max(int(round(h * ppm)), 1)
    font = _font(str(t.get("font", "serif")), max(int(round(size * ppm)), 4))
    ink = tuple(int(round(255 * c)) for c in colour(t.get("color", "#111111"), "image text color"))
    bg = t.get("background")
    im = Image.new("RGBA", (W, H), (*ink, 0))
    dr = ImageDraw.Draw(im)
    align = t.get("align", "left")
    x0, x1 = margin * ppm, (w - margin) * ppm
    y = margin * ppm
    for words, last in lines:
        if words:
            if align == "justify" and not last and len(words) > 1:
                gaps = len(words) - 1
                spare = (x1 - x0) - sum(font.getlength(wd) for wd in words)
                x = x0
                for wd in words:
                    dr.text((x, y + lead * ppm * 0.5), wd, font=font, fill=(*ink, 255), anchor="lm")
                    x += font.getlength(wd) + spare / gaps
            else:
                s = " ".join(words)
                lw = font.getlength(s)
                x = {"center": (x0 + x1 - lw) / 2, "right": x1 - lw}.get(align, x0)
                dr.text((x, y + lead * ppm * 0.5), s, font=font, fill=(*ink, 255), anchor="lm")
        y += lead * ppm
    a = np.asarray(im).copy()
    a[..., :3] = ink  # ink colour everywhere, coverage in alpha: no dark fringe when filtered
    # coverage is mixed in linear light, where half-covered pixels read paler than printed ink: spread it
    a[..., 3] = np.round(255 * (a[..., 3] / 255.0) ** INK).astype(np.uint8)
    out = Image.fromarray(a)
    if bg is not None:  # a printed sheet: the ink over the paper colour
        out = Image.alpha_composite(Image.new("RGBA", (W, H), (*(int(round(255 * c)) for c in colour(
            bg, "image text background")), 255)), out)
    return out


def text_path(t: dict, w: float, h) -> Path:
    out = store_dir() / f"t_{_text_key(t, w, h)}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.png")
        render_text(t, w, h).save(tmp)
        tmp.replace(out)
    return out


# ---- sources ------------------------------------------------------------------------------------------------------

def source_path(img: dict) -> Path:
    """The PNG an image dict shows (a stored image, or its text rendered)."""
    if "text" in img:
        sz = img.get("size")
        if not (isinstance(sz, list) and len(sz) == 2 and sz[0]):
            raise SpecError("image text needs \"size\": [width, height or null] (m): the page")
        return text_path(img["text"], float(sz[0]), None if sz[1] is None else float(sz[1]))
    if "id" in img:
        p = id_path(img["id"])
        if not p.exists():
            raise SpecError(f"image {img['id']!r} is missing from the store ({p})")
        return p
    if "file" in img:  # not saved yet (a spec handed straight to the code): store it now
        return id_path(ingest(img["file"]))
    raise SpecError("image needs \"file\", \"id\" or \"text\"")


_PIX: dict = {}


def pixels(path: Path) -> np.ndarray:
    """(H, W, 4) float32 0..1, sRGB as stored, rows top first."""
    key = str(path)
    if key not in _PIX:
        from PIL import Image
        if len(_PIX) > 16:
            _PIX.pop(next(iter(_PIX)))
        _PIX[key] = np.asarray(Image.open(path).convert("RGBA"), np.float32) / 255.0
    return _PIX[key]


def image_size(path: Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


# ---- style --------------------------------------------------------------------------------------------------------

def styled_path(path: Path, st: dict) -> Path:
    """The image with the paint style's saturation and value applied per pixel (paint.style_rgb's HSV scaling, in
    sRGB as every colour here), cached by content: "style": true on an image."""
    from PIL import Image
    sat, val = float(st.get("saturation", 1.0)), float(st.get("value", 1.0))
    if sat == 1.0 and val == 1.0:
        return path
    key = hashlib.sha1(Path(path).read_bytes() + json.dumps([sat, val]).encode()).hexdigest()[:16]
    out = store_dir() / f"s_{key}.png"
    if not out.exists():
        with Image.open(path) as im:
            rgba = np.asarray(im.convert("RGBA"))
        hsv = np.asarray(Image.fromarray(np.ascontiguousarray(rgba[..., :3])).convert("HSV")).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * sat, 0, 255)
        hsv[..., 2] = np.clip(hsv[..., 2] * val, 0, 255)
        rgb = np.asarray(Image.fromarray(np.round(hsv).astype(np.uint8), "HSV").convert("RGB"))
        tmp = out.with_suffix(".tmp.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.dstack([rgb, rgba[..., 3]])).save(tmp)
        tmp.replace(out)
    return out


# ---- placement ----------------------------------------------------------------------------------------------------

def _unit(v, what):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    if v.shape != (3,) or n < 1e-9:
        raise SpecError(f"{what}: {v.tolist()} isn't a direction [x, y, z]")
    return v / n


_PRIMS: dict = {}  # a frame's "geo" -> the primitives its surface is measured on (surface maps)


def prims_on(spec: dict, parts) -> list:
    """The primitives of these parts (their cuts too): what a wrap measures its surface on. None / "*": every part."""
    from .spec import compile_prims
    prims = compile_prims(spec)
    if parts is None or parts == "*" or (not isinstance(parts, str) and "*" in parts):
        return list(prims)
    parts = [parts] if isinstance(parts, str) else list(parts)
    return [p for p in prims if p.part in parts]


def _geo(prims) -> str:
    from . import sdf
    g = hashlib.sha1(json.dumps(sorted(sdf.fingerprint(p) for p in prims)).encode()).hexdigest()[:16]
    _PRIMS[g] = prims
    if len(_PRIMS) > 32:
        _PRIMS.pop(next(iter(_PRIMS)))
    return g


def _hit(prims, o, d, what) -> float:
    """Distance along d from o to the outermost surface crossing (marched in from outside the model)."""
    from . import sdf
    adds = [p for p in prims if p.op == "add"]
    if not adds:
        raise SpecError(f"{what}: no surface to wrap onto (the parts have no primitives)")
    lo, hi = np.min([p.lo for p in adds], 0), np.max([p.hi for p in adds], 0)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    tmax = float(np.linalg.norm(corners - o, axis=1).max()) + 0.01
    t = np.linspace(tmax, 0.0, 400)
    f = sdf.field_at(prims, o + t[:, None] * d)
    idx = np.flatnonzero((f[:-1] > 0) & (f[1:] <= 0))
    if not len(idx):
        raise SpecError(f"{what}: the wrap's centre ray (from {np.round(o, 3).tolist()} along "
                        f"{np.round(d, 2).tolist()}) hits nothing on the decal's parts")
    a, b = t[idx[0]], t[idx[0] + 1]
    for _ in range(40):
        m = 0.5 * (a + b)
        if sdf.field_at(prims, (o + m * d)[None])[0] > 0:
            a = m
        else:
            b = m
    return 0.5 * (a + b)


def _axis(s: dict, img: dict, blob, R, what):
    """(a point on the axis, unit direction) of a cylinder/sphere wrap: "axis" = a bone | [joint or xyz, joint or
    xyz] | [x, y, z] (a direction through "at") | {"at", "dir"}; default the "at" blob's own z axis (a cylinder
    blob: a can, a bottle), or world Z through "at"."""
    from .spec import resolve_point
    ax = img.get("axis")
    at = img.get("at")
    if ax is None:
        if at is None:
            raise SpecError(f"{what}: a {img.get('wrap')} wrap needs \"axis\" (a bone, [joint, joint] or "
                            f"{{\"at\", \"dir\"}}) or \"at\" (a cylinder blob, or a point the axis runs up through)")
        return resolve_point(s, at), R @ np.array([0, 0, 1.0])
    if isinstance(ax, str):
        b = (s.get("bones") or {}).get(ax)
        if b is None:
            raise SpecError(f"{what}: axis bone {ax!r} doesn't exist")
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        return 0.5 * (a + bb), _unit(bb - a, f"{what} axis")
    if isinstance(ax, dict):
        if "dir" not in ax:
            raise SpecError(f"{what}: axis {{\"at\", \"dir\"}} needs dir")
        o = resolve_point(s, ax["at"]) if "at" in ax else (resolve_point(s, at) if at is not None else None)
        if o is None:
            raise SpecError(f"{what}: axis needs \"at\" (a point on it)")
        return o, _unit(ax["dir"], f"{what} axis dir")
    if isinstance(ax, list) and len(ax) == 3 and all(isinstance(x, (int, float)) for x in ax):
        if at is None:
            raise SpecError(f"{what}: axis [x, y, z] is a direction: give \"at\" (a point on the axis) too")
        return resolve_point(s, at), _unit(ax, f"{what} axis")
    if isinstance(ax, list) and len(ax) == 2:
        a, bb = resolve_point(s, ax[0]), resolve_point(s, ax[1])
        return 0.5 * (a + bb), _unit(bb - a, f"{what} axis")
    raise SpecError(f"{what}: axis is a bone, [joint, joint], [x, y, z] (with at) or {{\"at\", \"dir\"}}")


def frame(spec: dict, img: dict, expanded: dict | None = None, what: str = "image", parts=None) -> dict:
    """The decal's placement in world space: centre c, unit right/up/dir, size w x h (m), depth, facing, and the
    image file. Computed from the spec (joints and blobs follow edits). parts: the layer's parts (the surface a
    wrap is measured on; an image's own "on" wins)."""
    from .spec import euler_matrix, expand_mirror, resolve_point
    bad = set(img) - KEYS
    if bad:
        raise SpecError(f"{what}: unknown keys {sorted(bad)} (have {', '.join(sorted(KEYS))})")
    wrap = img.get("wrap", "planar")
    if wrap not in WRAPS:
        raise SpecError(f"{what}: wrap is one of {', '.join(WRAPS)}")
    if "at" not in img and not (wrap == "cylinder" and "axis" in img):
        raise SpecError(f"{what}: needs \"at\" (the decal's centre: a joint, a blob, [x, y, z])")
    for k in ("axis", "seam", "span"):
        if k in img and wrap not in ("cylinder", "sphere"):
            raise SpecError(f"{what}: {k} is for wrap cylinder or sphere")
    if "rotate" in img and wrap in ("cylinder", "sphere"):
        raise SpecError(f"{what}: rotate is for planar and surface decals (a wrap's picture runs round its axis)")
    s = expanded if expanded is not None else expand_mirror(spec)
    at = img.get("at")
    blob = (s.get("blobs") or {}).get(at) if isinstance(at, str) else None
    if isinstance(at, str) and at not in (s.get("joints") or {}) and blob is None:
        raise SpecError(f"{what}: at {at!r} is no joint or blob")
    R = euler_matrix(blob.get("rot", [0, 0, 0])) if blob is not None else np.eye(3)
    path = source_path(img)
    if img.get("style"):
        path = styled_path(path, (spec.get("style") or {}).get("paint") or {})
    pw, ph = image_size(path)
    ch = img.get("channel", "alpha")
    if ch not in CHANNELS:
        raise SpecError(f"{what}: channel is one of {', '.join(CHANNELS)}")
    base = {"path": str(path), "wrap": wrap, "facing": float(img.get("facing", 0.3)), "channel": ch,
            "flip": bool(img.get("flip", False)), "mirror": bool(img.get("mirror", False)), "px": [pw, ph]}
    if wrap in ("cylinder", "sphere"):
        return {**base, **_wrap_frame(spec, s, img, blob, R, wrap, pw, ph, parts, what)}
    d = img.get("dir", "front" if blob is not None else [0, -1, 0])
    named = isinstance(d, str)
    if named:
        if d not in FACES:
            raise SpecError(f"{what}: dir {d!r} is a vector or one of {', '.join(FACES)}")
        d = R @ np.array(FACES[d], float)
    d = _unit(d, f"{what} dir")
    c = resolve_point(s, at)
    if blob is not None:  # onto the blob's face along dir
        size = np.asarray(blob.get("size", [0.05] * 3), float)
        loc = R.T @ d
        if blob.get("shape") == "box":
            ext = float(np.abs(loc) @ size)
        elif blob.get("shape") == "cylinder":
            ext = float(np.hypot(loc[0] * size[0], loc[1] * size[1]) + abs(loc[2]) * size[2])
        else:
            ext = float(np.linalg.norm(loc * size))
        c = c + d * ext
    sz = img.get("size")
    if not (isinstance(sz, list) and len(sz) == 2 and (sz[0] or sz[1])):
        raise SpecError(f"{what}: size is [width, height] in m (one may be null: from the image's aspect)")
    w = float(sz[0]) if sz[0] else float(sz[1]) * pw / ph
    h = float(sz[1]) if sz[1] else w * ph / pw
    if w <= 0 or h <= 0:
        raise SpecError(f"{what}: size must be > 0")
    geo = None
    if wrap == "surface":  # seated on the field: the centre and its normal are the surface's own
        from . import sdf
        prims = prims_on(spec, img.get("on", parts))
        if not prims:
            raise SpecError(f"{what}: no surface to lay the decal on (parts {img.get('on', parts)!r})")
        geo = _geo(prims)
        def fg(x, h=1e-5):  # unclipped: the centre may start well off the surface
            st = np.vstack([x, x + np.eye(3) * h])
            f = sdf.field_at(prims, st, clip=False)
            return f[0], (f[1:] - f[0]) / h
        for _ in range(12):
            f, g = fg(c)
            c = c - (f / max(float(g @ g), 1e-12)) * g
        f, g = fg(c)
        if abs(f) > 1e-3 * max(w, h):
            raise SpecError(f"{what}: couldn't seat the decal's centre on the surface (left {f:.4f} m off)")
        n0 = _unit(g, f"{what} surface normal")
        if n0 @ d < -0.2 and "dir" in img:
            raise SpecError(f"{what}: the surface at the centre faces away from dir")
        d = n0
    if "up" in img:
        up = _unit(img["up"], f"{what} up")
    elif named:
        up = R @ (np.array([0, 1.0, 0]) if img.get("dir") in ("top", "bottom") else np.array([0, 0, 1.0]))
    else:
        up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.95 else np.array([0, 1.0, 0])
    up = up - (up @ d) * d
    if np.linalg.norm(up) < 1e-6:
        raise SpecError(f"{what}: up is along dir")
    up /= np.linalg.norm(up)
    right = np.cross(up, d)
    rot = np.radians(float(img.get("rotate", 0.0)))
    if rot:
        right, up = np.cos(rot) * right + np.sin(rot) * up, -np.sin(rot) * right + np.cos(rot) * up
    out = {**base, "c": c.tolist(), "right": right.tolist(), "up": up.tolist(), "dir": d.tolist(), "w": w, "h": h}
    if wrap == "surface":
        from . import decalmap
        reach = 0.5 * float(np.hypot(w, h)) * decalmap.REACH
        vox = max(2 * reach / decalmap.RES, min(w, h) / 60, decalmap.MIN_VOXEL)
        out.update(geo=geo, reach=reach, voxel=vox, depth=float(img.get("depth", max(0.04 * max(w, h), 3 * vox))))
    else:
        out["depth"] = float(img.get("depth", 0.25 * max(w, h)))
    if out["depth"] <= 0:
        raise SpecError(f"{what}: depth must be > 0")
    return out


def _wrap_frame(spec, s, img, blob, R, wrap, pw, ph, parts, what) -> dict:
    """A cylinder or sphere wrap: the axis (o, k), the centre's direction e1 (dir projected off the axis), e2 = k x
    e1 (the picture's right, seen from outside), the surface's radius at the centre r0 (measured), the seam."""
    from .spec import resolve_point
    if wrap == "cylinder":
        o, k = _axis(s, img, blob, R, what)
        if img.get("at") is not None:  # the centre's height: "at" projected onto the axis
            o = o + ((resolve_point(s, img["at"]) - o) @ k) * k
    else:
        if img.get("at") is None:
            raise SpecError(f"{what}: a sphere wrap needs \"at\" (the sphere's centre)")
        o = resolve_point(s, img["at"])
        if img.get("axis") is None:
            k = R @ np.array([0, 0, 1.0])
        else:
            k = _axis(s, img, blob, R, what)[1]
    d = img.get("dir", "front" if blob is not None else [0, -1, 0])
    if isinstance(d, str):
        if d not in FACES:
            raise SpecError(f"{what}: dir {d!r} is a vector or one of {', '.join(FACES)}")
        d = R @ np.array(FACES[d], float)
    d = _unit(d, f"{what} dir")
    e1 = d - (d @ k) * k
    if np.linalg.norm(e1) < 1e-3:
        if wrap == "cylinder":
            raise SpecError(f"{what}: dir runs along the axis (dir is the way the decal's centre faces, off the axis)")
        e1 = np.cross(k, [1.0, 0, 0] if abs(k[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(k, e1)
    phic = float(np.arcsin(np.clip(d @ k, -1, 1))) if wrap == "sphere" else 0.0
    cdir = np.cos(phic) * e1 + np.sin(phic) * k  # from o to the decal's centre
    prims = prims_on(spec, img.get("on", parts))
    r0 = _hit(prims, o, cdir, what)
    seam = np.radians(float(img.get("seam", 180.0)))
    span = img.get("span")
    su = sv = None
    if span is not None:
        sp = span if isinstance(span, list) else [span, None]
        if not (len(sp) == 2 and sp[0] and float(sp[0]) > 0 and (sp[1] is None or float(sp[1]) > 0)):
            raise SpecError(f"{what}: span is degrees round the axis (> 0), or [round, up] for a sphere")
        if sp[1] is not None and wrap == "cylinder":
            raise SpecError(f"{what}: a cylinder's span is one angle (round the axis); its height is size[1] or "
                            f"from the image's aspect")
        su = float(np.radians(float(sp[0])))
        sv = float(np.radians(float(sp[1]))) if sp[1] is not None else None
    sz = img.get("size")
    rho0 = r0 * np.cos(phic)  # the centre's distance from the axis
    if su is not None:
        w = su * rho0
        if sz is not None and (not isinstance(sz, list) or len(sz) != 2 or sz[0]):
            raise SpecError(f"{what}: with span, size is [null, height] (or left out: from the image's aspect)")
        if sv is not None:
            h = sv * r0
        elif sz is not None and sz[1]:
            h = float(sz[1])
        else:
            h = w * ph / pw
            if wrap == "sphere":
                sv = su * ph / pw  # equirectangular: square pixels at the equator
                h = sv * r0
    else:
        if not (isinstance(sz, list) and len(sz) == 2 and (sz[0] or sz[1])):
            raise SpecError(f"{what}: size is [width, height] in m (width measured round the surface), or give "
                            f"span (degrees)")
        w = float(sz[0]) if sz[0] else float(sz[1]) * pw / ph
        h = float(sz[1]) if sz[1] else w * ph / pw
    if w <= 0 or h <= 0:
        raise SpecError(f"{what}: size must be > 0")
    if su is None and w > 2 * np.pi * rho0 * 1.0001:
        raise SpecError(f"{what}: {w:.3f} m is more than once round ({2 * np.pi * rho0:.3f} m at the centre's radius)")
    depth = float(img.get("depth", 0.25 * max(w, h)))
    if depth <= 0:
        raise SpecError(f"{what}: depth must be > 0")
    out = {"o": o.tolist(), "k": k.tolist(), "c": (o + r0 * cdir).tolist(), "dir": e1.tolist(), "up": k.tolist(),
           "right": e2.tolist(), "r0": float(r0), "phic": phic, "seam": float(seam),
           "dc": float(np.mod(-seam, 2 * np.pi)), "su": su, "sv": sv, "w": float(w), "h": float(h), "depth": depth,
           "m": 0.0, "unroll": "arc"}
    if wrap == "cylinder":
        unroll = img.get("unroll", "auto")
        if unroll not in UNROLLS:
            raise SpecError(f"{what}: unroll is one of {', '.join(UNROLLS)}")
        # the surface's taper over the label: its radius a little above and below the centre (a local cone)
        dt = 0.5 * h
        r_hi, r_lo = (_hit(prims, o + sgn * dt * k, e1, what) for sgn in (1, -1))
        m = float((r_hi - r_lo) / (2 * dt))
        if unroll == "auto":
            unroll = "cone" if abs(m) > TAPER else "arc"
        out.update(m=m, unroll=unroll)
        if unroll == "cone":  # fan-cut: rows on circles round the axis, columns on the cone's generators
            if abs(m) < 1e-6:
                raise SpecError(f"{what}: unroll cone on a surface with no taper here (use arc)")
            out.update(ta=float(-r0 / m), Rc=float(r0 * np.sqrt(1 + m * m) / abs(m)), sg=1.0 if m < 0 else -1.0)
    elif "unroll" in img:
        raise SpecError(f"{what}: unroll is for cylinder wraps")
    return out


def mirrored(fr: dict) -> dict:
    """The placement reflected across X with the picture still reading the right way."""
    M = np.array([-1.0, 1.0, 1.0])
    c, d, up = np.array(fr["c"]) * M, np.array(fr["dir"]) * M, np.array(fr["up"]) * M
    out = {**fr, "c": c.tolist(), "dir": d.tolist(), "up": up.tolist(), "right": np.cross(up, d).tolist(),
           "mirror": False}
    if fr.get("wrap") in ("cylinder", "sphere"):  # the seam's place mirrored too (angles run the other way)
        out.update(o=(np.array(fr["o"]) * M).tolist(), k=up.tolist(), seam=-fr["seam"],
                   dc=float(np.mod(fr["seam"], 2 * np.pi)))
    return out


def _ramp(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def surface_map(fr: dict) -> dict:
    """A surface decal's exponential map (decalmap.build), on the primitives its frame was made from."""
    from . import decalmap
    prims = _PRIMS.get(fr["geo"])
    if prims is None:
        raise RuntimeError("a surface decal's frame must be made in this process (images.frame) before it's used")
    return decalmap.build(prims, fr)


def wrap_coords(fr: dict, pos: np.ndarray):
    """A cylinder/sphere wrap's (u, v, distance off its surface, outward unit) at points (before flip). The
    cylinder's surface is the local cone fitted at the centre (radius r0 + m t), "arc": u = arc length at the point's
    own radius, v = height along the axis; "cone": the label fan-cut onto that cone (u = angle x the centre's radius,
    v = slant distance: columns run along the cone's generators, rows round it, even height)."""
    q = np.asarray(pos, float) - fr["o"]
    k, e1, e2 = (np.asarray(fr[x], float) for x in ("k", "dir", "right"))
    t, x, y = q @ k, q @ e1, q @ e2
    D = np.mod(np.arctan2(y, x) - fr["seam"], 2 * np.pi) - fr["dc"]
    rho = np.hypot(x, y)
    if fr["wrap"] == "cylinder":
        m = fr.get("m", 0.0)
        s = np.sqrt(1 + m * m)
        radial = (x[:, None] * e1 + y[:, None] * e2) / np.maximum(rho, 1e-12)[:, None]
        out = (radial - m * k) / s
        err = (rho - (fr["r0"] + m * t)) / s
        if fr.get("unroll") == "cone":
            u = (D / fr["su"] if fr["su"] else fr["r0"] * D / fr["w"]) + 0.5
            v = fr["sg"] * (fr["Rc"] - np.hypot(rho, t - fr["ta"])) / fr["h"] + 0.5
        else:
            u = (D / fr["su"] if fr["su"] else rho * D / fr["w"]) + 0.5
            v = t / fr["h"] + 0.5
    else:
        u = (D / fr["su"] if fr["su"] else rho * D / fr["w"]) + 0.5
        R = np.linalg.norm(q, axis=1)
        phi = np.arcsin(np.clip(t / np.maximum(R, 1e-12), -1, 1)) - fr["phic"]
        v = (phi / fr["sv"] if fr["sv"] else R * phi / fr["h"]) + 0.5
        err = R - fr["r0"]
        out = q / np.maximum(R, 1e-12)[:, None]
    return u, v, err, out


def project(fr: dict, pos: np.ndarray, nrm: np.ndarray):
    """(u, v, weight) per point: u, v in 0..1 across the decal (v up), weight = inside its depth x facing."""
    nn = np.asarray(nrm, float)
    nn = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
    wrap = fr.get("wrap", "planar")
    if wrap in ("cylinder", "sphere"):
        u, v, err, out = wrap_coords(fr, pos)
        wgt = _ramp(np.abs(err), fr["depth"], 0.8 * fr["depth"])
        wgt = wgt * _ramp((nn * out).sum(1), fr["facing"] - 0.15, fr["facing"])
    elif wrap == "surface":
        from . import decalmap
        U, dist, N = decalmap.lookup(surface_map(fr), pos)
        off = ~np.isfinite(U).all(1)
        U[off] = -1e3
        u = U[:, 0] / fr["w"] + 0.5
        v = U[:, 1] / fr["h"] + 0.5
        wgt = _ramp(dist, fr["depth"], 0.8 * fr["depth"]) * _ramp((nn * N).sum(1), fr["facing"] - 0.15, fr["facing"])
        wgt = wgt * _ramp(np.linalg.norm(U, axis=1), fr["reach"], 0.9 * fr["reach"])
        wgt[off] = 0
    else:
        p = np.asarray(pos, float) - fr["c"]
        u = p @ fr["right"] / fr["w"] + 0.5
        v = p @ fr["up"] / fr["h"] + 0.5
        s = np.abs(p @ fr["dir"])
        wgt = _ramp(s, fr["depth"], 0.8 * fr["depth"])
        wgt = wgt * _ramp(nn @ fr["dir"], fr["facing"] - 0.15, fr["facing"])
    if fr["flip"]:
        u = 1 - u
    return u, v, wgt


def sample(pix: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear lookup at (u, v) (v up), 0 outside the image (as Blender's CLIP extension)."""
    H, W = pix.shape[:2]
    x, y = u * W - 0.5, (1 - v) * H - 0.5
    inside = (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    x0c, x1c = np.clip(x0, 0, W - 1), np.clip(x0 + 1, 0, W - 1)
    y0c, y1c = np.clip(y0, 0, H - 1), np.clip(y0 + 1, 0, H - 1)
    out = (pix[y0c, x0c] * (1 - fx) * (1 - fy) + pix[y0c, x1c] * fx * (1 - fy)
           + pix[y1c, x0c] * (1 - fx) * fy + pix[y1c, x1c] * fx * fy)
    out[~inside] = 0
    return out


def _one(fr: dict, pos, nrm):
    u, v, wgt = project(fr, pos, nrm)
    rgba = sample(pixels(Path(fr["path"])), u, v)
    ch = fr["channel"]
    if ch == "coverage":
        val = ((u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)).astype(float)
    elif ch == "alpha":
        val = rgba[:, 3]
    elif ch == "luma":
        val = rgba[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
    else:
        val = rgba[:, "rgb".index(ch)]
    return val * wgt, rgba[:, :3]


def evaluate(fr: dict, pos: np.ndarray, nrm: np.ndarray):
    """(mask (n,), sRGB colour (n, 3)) of a decal at surface points; with "mirror", the stronger placement wins."""
    m, col = _one(fr, pos, nrm)
    if fr["mirror"]:
        m2, col2 = _one(mirrored(fr), pos, nrm)
        col = np.where((m2 > m)[:, None], col2, col)
        m = np.maximum(m, m2)
    return m, col


def frames_of(spec: dict, ly: dict, expanded: dict | None = None) -> list[dict]:
    from .spec import expand_mirror
    imgs = layer_images(ly)
    if not imgs:
        return []
    s = expanded if expanded is not None else expand_mirror(spec)
    return [frame(spec, img, s, parts=ly.get("part", "body")) for img in imgs]


def footprint(fr: dict, n: int = 24) -> np.ndarray:
    """World points over the decal's rectangle as it lies on the surface (texel focus, coverage): a grid on the
    plane, on the wrap's cylinder/sphere at the centre's radius, or the surface map's own vertices inside it."""
    a = (np.arange(n) + 0.5) / n
    gu, gv = (x.ravel() for x in np.meshgrid(a, a))
    if fr["wrap"] == "planar":
        return (np.asarray(fr["c"]) + ((gu - 0.5) * fr["w"])[:, None] * np.asarray(fr["right"])
                + ((gv - 0.5) * fr["h"])[:, None] * np.asarray(fr["up"]))
    if fr["wrap"] == "surface":
        m = surface_map(fr)
        U = m["U"].astype(float)
        ok = np.isfinite(U).all(1)
        ok[ok] = (np.abs(U[ok, 0]) <= 0.5 * fr["w"]) & (np.abs(U[ok, 1]) <= 0.5 * fr["h"])
        return m["V"][ok].astype(float)
    o, k, e1, e2 = (np.asarray(fr[x], float) for x in ("o", "k", "dir", "right"))
    r0, phic = fr["r0"], fr["phic"]
    rho0 = r0 * np.cos(phic)
    D = (gu - 0.5) * (fr["su"] if fr["su"] else fr["w"] / rho0)
    if fr["flip"]:
        D = -D
    if fr["wrap"] == "cylinder":
        m = fr.get("m", 0.0)
        if fr.get("unroll") == "cone":  # back from the fan: slant distance -> height and radius on the cone
            R = fr["Rc"] - fr["sg"] * (gv - 0.5) * fr["h"]
            s = np.sqrt(1 + m * m)
            t = fr["ta"] - fr["sg"] * R / s
            rho = R * abs(m) / s
        else:
            t = (gv - 0.5) * fr["h"]
            rho = rho0 + m * t
            if not fr["su"]:
                D = D * rho0 / rho  # arc length at the point's own radius
        return o + rho[:, None] * (np.cos(D)[:, None] * e1 + np.sin(D)[:, None] * e2) + t[:, None] * k
    phi = phic + (gv - 0.5) * (fr["sv"] if fr["sv"] else fr["h"] / r0)
    return o + r0 * (np.cos(phi)[:, None] * (np.cos(D)[:, None] * e1 + np.sin(D)[:, None] * e2)
                     + np.sin(phi)[:, None] * k)


def coverage(fr: dict, prims: list, n: int = 7, steps: int = 48) -> float:
    """The share of an n x n grid over the decal whose ray (from depth in front of its surface to depth behind)
    crosses the surface of these primitives: 0 = the placement hits nothing."""
    from . import sdf
    if not prims:
        return 0.0
    if fr["wrap"] == "surface":
        return 1.0 if len(footprint(fr)) else 0.0  # seated on the surface already
    a = (np.arange(n) + 0.5) / n - 0.5
    if fr["wrap"] == "planar":
        c, r, u, d = (np.asarray(fr[k], float) for k in ("c", "right", "up", "dir"))
        gu, gv = np.meshgrid(a * fr["w"], a * fr["h"])
        base = c + gu.reshape(-1, 1) * r + gv.reshape(-1, 1) * u
        dirs = np.broadcast_to(d, base.shape)
    else:
        base = footprint(fr, n)
        rel = base - np.asarray(fr["o"], float)
        if fr["wrap"] == "cylinder":
            k = np.asarray(fr["k"], float)
            rel = rel - (rel @ k)[:, None] * k
        dirs = rel / np.maximum(np.linalg.norm(rel, axis=1, keepdims=True), 1e-12)
    t = np.linspace(fr["depth"], -fr["depth"], steps)
    pts = base[:, None, :] + t[None, :, None] * dirs[:, None, :]
    f = sdf.field_at(prims, pts.reshape(-1, 3)).reshape(len(base), steps)
    hit = ((f[:, :-1] > 0) & (f[:, 1:] <= 0)).any(1)
    return float(hit.mean())
