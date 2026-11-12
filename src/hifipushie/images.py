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
                picture still reading the right way: text, a logo),
            "mirror_image": true (with "mirror", or on a ".L" layer: the mirrored placement shows the picture
                MIRRORED too, as symmetric anatomy is: a brow's hairs run from the nose outward on both sides;
                planar decals),
            "wrap": "planar" (default) | "cylinder" | "sphere" | "surface" (below),
            "style": true (the picture's colours through the paint style's saturation and value),
            "on": part(s) whose surface a wrap measures (default the layer's parts),
            "offset": [x, y, z] m (world axes) added to the centre "at" gives (after a blob's face): how a decal
                moved in the Blender scene comes back while it stays near its joint or blob (`from_gizmo`)}

In the Blender scene every decal is a wire gizmo (collection "decals", never rendered or baked): its rectangle
(a wrap's outline round its axis, plus the axis). Move, turn or scale it there and `scene.pull` writes the
placement back (`from_gizmo`): at/offset, dir/up/rotate, size; a wrap's height, axis, dir, span.

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
texel density, raised automatically over each decal (asset_parts.decal_focus) to keep about the image's resolution.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at images.NAME: C422). images_frame: placement: the frame an image sits in (on a prim, at a point, along an
axis), the wrap frame, the UV frame. images_project: placement: mirrored copies, the surface map, wrap coordinates,
projection, sampling, `evaluate`, the frames of a spec, footprint and coverage. images_gizmo: decals as gizmos in the
Blender scene (scene.sync / scene.pull): entries, the gizmo, and back from it.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from .spec import SpecError
from . import moved

TEXT_VERSION = 2  # bump when text rendering changes
INK = 0.5  # coverage -> alpha exponent (ink spread)
MAX_PX = 4096  # a text page's longer side at most
FACES = {"front": (0, -1, 0), "back": (0, 1, 0), "left": (1, 0, 0), "right": (-1, 0, 0), "top": (0, 0, 1),
         "bottom": (0, 0, -1)}
KEYS = {"file", "id", "text", "name", "at", "dir", "up", "size", "rotate", "depth", "facing", "channel", "flip",
        "mirror", "mirror_image", "wrap", "axis", "seam", "span", "style", "on", "unroll", "offset", "box"}
WRAPS = ("planar", "cylinder", "sphere", "surface", "uv")
PLACE_KEYS = {"id", "file", "text", "at", "dir", "up", "size", "rotate", "offset", "wrap", "axis", "seam", "span",
              "unroll", "on"}  # entries alike in these share one gizmo in the scene (scene.decal_gizmos)
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


_PRIMS: dict = {}  # a frame's "geo" -> the primitives its surface is measured on (surface maps)

_UVBASE: dict = {}  # a uv frame's "geo" -> the base whose atlas it is laid in


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("images_frame", "images_project", "images_gizmo")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
