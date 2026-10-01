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
                picture still reading the right way)}

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
        "mirror"}
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


# ---- placement ----------------------------------------------------------------------------------------------------

def _unit(v, what):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    if v.shape != (3,) or n < 1e-9:
        raise SpecError(f"{what}: {v.tolist()} isn't a direction [x, y, z]")
    return v / n


def frame(spec: dict, img: dict, expanded: dict | None = None, what: str = "image") -> dict:
    """The decal's placement in world space: centre c, unit right/up/dir, size w x h (m), depth, facing, and the
    image file. Computed from the spec (joints and blobs follow edits)."""
    from .spec import euler_matrix, expand_mirror, resolve_point
    bad = set(img) - KEYS
    if bad:
        raise SpecError(f"{what}: unknown keys {sorted(bad)} (have {', '.join(sorted(KEYS))})")
    if "at" not in img:
        raise SpecError(f"{what}: needs \"at\" (the decal's centre: a joint, a blob, [x, y, z])")
    s = expanded if expanded is not None else expand_mirror(spec)
    at = img["at"]
    blob = (s.get("blobs") or {}).get(at) if isinstance(at, str) else None
    if isinstance(at, str) and at not in (s.get("joints") or {}) and blob is None:
        raise SpecError(f"{what}: at {at!r} is no joint or blob")
    c = resolve_point(s, at)
    R = euler_matrix(blob.get("rot", [0, 0, 0])) if blob is not None else np.eye(3)
    d = img.get("dir", "front" if blob is not None else [0, -1, 0])
    named = isinstance(d, str)
    if named:
        if d not in FACES:
            raise SpecError(f"{what}: dir {d!r} is a vector or one of {', '.join(FACES)}")
        d = R @ np.array(FACES[d], float)
    d = _unit(d, f"{what} dir")
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
    path = source_path(img)
    sz = img.get("size")
    if not (isinstance(sz, list) and len(sz) == 2 and (sz[0] or sz[1])):
        raise SpecError(f"{what}: size is [width, height] in m (one may be null: from the image's aspect)")
    pw, ph = image_size(path)
    w = float(sz[0]) if sz[0] else float(sz[1]) * pw / ph
    h = float(sz[1]) if sz[1] else w * ph / pw
    if w <= 0 or h <= 0:
        raise SpecError(f"{what}: size must be > 0")
    ch = img.get("channel", "alpha")
    if ch not in CHANNELS:
        raise SpecError(f"{what}: channel is one of {', '.join(CHANNELS)}")
    depth = float(img.get("depth", 0.25 * max(w, h)))
    if depth <= 0:
        raise SpecError(f"{what}: depth must be > 0")
    return {"path": str(path), "c": c.tolist(), "right": right.tolist(), "up": up.tolist(), "dir": d.tolist(),
            "w": w, "h": h, "depth": depth, "facing": float(img.get("facing", 0.3)), "channel": ch,
            "flip": bool(img.get("flip", False)), "mirror": bool(img.get("mirror", False)), "px": [pw, ph]}


def mirrored(fr: dict) -> dict:
    """The placement reflected across X with the picture still reading the right way."""
    M = np.array([-1.0, 1.0, 1.0])
    c, d, up = np.array(fr["c"]) * M, np.array(fr["dir"]) * M, np.array(fr["up"]) * M
    return {**fr, "c": c.tolist(), "dir": d.tolist(), "up": up.tolist(), "right": np.cross(up, d).tolist(),
            "mirror": False}


def _ramp(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def project(fr: dict, pos: np.ndarray, nrm: np.ndarray):
    """(u, v, weight) per point: u, v in 0..1 across the decal (v up), weight = inside its depth x facing."""
    p = np.asarray(pos, float) - fr["c"]
    u = p @ fr["right"] / fr["w"] + 0.5
    if fr["flip"]:
        u = 1 - u
    v = p @ fr["up"] / fr["h"] + 0.5
    s = np.abs(p @ fr["dir"])
    wgt = _ramp(s, fr["depth"], 0.8 * fr["depth"])
    nn = np.asarray(nrm, float)
    nn = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
    wgt = wgt * _ramp(nn @ fr["dir"], fr["facing"] - 0.15, fr["facing"])
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
    return [frame(spec, img, s) for img in imgs]


def coverage(fr: dict, prims: list, n: int = 7, steps: int = 48) -> float:
    """The share of an n x n grid over the decal whose ray (from depth in front of its plane to depth behind,
    against dir) crosses the surface of these primitives: 0 = the placement hits nothing."""
    from . import sdf
    if not prims:
        return 0.0
    c, r, u, d = (np.asarray(fr[k], float) for k in ("c", "right", "up", "dir"))
    a = (np.arange(n) + 0.5) / n - 0.5
    gu, gv = np.meshgrid(a * fr["w"], a * fr["h"])
    base = c + gu.reshape(-1, 1) * r + gv.reshape(-1, 1) * u
    t = np.linspace(fr["depth"], -fr["depth"], steps)
    pts = base[:, None, :] + t[None, :, None] * d
    f = sdf.field_at(prims, pts.reshape(-1, 3)).reshape(len(base), steps)
    hit = ((f[:, :-1] > 0) & (f[:, 1:] <= 0)).any(1)
    return float(hit.mean())
