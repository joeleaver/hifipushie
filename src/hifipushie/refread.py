"""Read a reference picture: its views, each view's camera, and what the picture holds INSIDE its outline.

Why (Braynard Racing, Scraps and Puddles, 2026-11-12): two racers were sculpted from concept art and scored on
their outer outline only. Scraps' block-in overlapped his turnaround 88 %, with a box for a head: no muzzle, no
sockets, no brows, no mouth. Everything inside the outline was read by the sculptor's eye, turned into 3D numbers
in its head and typed. The picture itself holds that information; this module gets it out, in the picture's own
pixels, so the sculptor can point at it (featuremap.py) and a model can be measured against it (featuresee.py).

- `split(image)`: a sheet's views, as the runs of columns its foreground covers (a turnaround: front, side, back).
- `read(name, image, views, height)`: per view: the crop (saved with its foreground as alpha), a CAMERA, the
  picture's PATCHES and its FORM LINES. Saved under <model>/features/; cameras under <model>/cameras/<view>.json
  in matched.py's format, so look_matched, feature_tiles, fit_matched and look(camera={"fitted": view}) all work
  from a turnaround view exactly as from a fitted concept camera.
  View kinds: "front" (the figure faces us; ITS LEFT IS AT THE PICTURE'S RIGHT), "back", "side" (it faces the
  picture's left: we see its left side), "side_r" (it faces the picture's right). These are orthographic, drawn
  as a camera 100 m away. The sheet's scale is metres per pixel from `height` (the top of the FIRST such view;
  the feet are z = 0); x = 0 is a front / back view's own mirror line, y = 0 the middle of a side view's feet.
  Any other name is a picture in perspective: no camera until fit_concept_camera(name, <its crop>, label=<view>).
- PATCHES: the foreground cut along its steps in brightness and colour, pieces joined while they are one colour
  with no line between them, numbered top to bottom. A patch is bounded by form lines as well as by paint, so a
  plain-coloured subject still has patches. A patch is not a feature: it is something to point at. `detail`
  coarse / medium / fine.
- NOTCHES: where the outline turns sharply inward (an armpit, a crotch, a neck's corner, the tip of a gap): the
  places a part is divided from its neighbour, labelled n1 .. on the picture. A cut (featuremap "piece") names two.
- FORM LINES: where the picture's brightness steps (Sobel on a smoothed grey). A line is an edge of a form OR
  an edge of paint; which is the sculptor's call.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import matched, store

ORTHO = {"front": 0.0, "back": 180.0, "side": 90.0, "side_r": -90.0}  # view kind -> azimuth (render.VIEWS' sign)
FAR = 100.0  # an orthographic view is a camera this far away (m): 0.3 % of scale across a 0.6 m deep figure
DETAIL = {"coarse": (16.0, 90), "medium": (10.0, 40), "fine": (6.0, 14)}  # (colour step that splits two patches, smallest patch px)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def folder(name: str) -> Path:
    d = store._dir(name) / "features"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _font(px: int):
    try:
        return ImageFont.truetype(FONT, px)
    except OSError:
        return ImageFont.load_default()


# ---------------------------------------------------------------- views and cameras

def split(image: str, mask: str | None = None, gap: float = 0.015) -> list[tuple[int, int]]:
    """(x0, x1) of each run of columns the foreground covers, left to right; runs closer than `gap` of the width
    are one view."""
    m = matched.mask_of(image, mask)
    cols = np.where(m.any(0))[0]
    if not len(cols):
        raise ValueError(f"{image}: no foreground found (pass mask=)")
    need = max(2, int(gap * m.shape[1]))
    runs, a, p = [], cols[0], cols[0]
    for c in cols[1:]:
        if c - p > need:
            runs.append((int(a), int(p) + 1))
            a = c
        p = c
    runs.append((int(a), int(p) + 1))
    return [r for r in runs if r[1] - r[0] > 0.02 * m.shape[1]]


def mirror_line(m: np.ndarray) -> float:
    """The column a (roughly symmetric) silhouette mirrors best about."""
    xs = np.where(m.any(0))[0]
    mid = (xs[0] + xs[-1]) / 2
    best, at = -1.0, mid
    for c in np.arange(mid - 0.08 * len(xs), mid + 0.08 * len(xs) + 0.5, 0.5):
        k = int(round(2 * c))
        idx = k - np.arange(m.shape[1])
        ok = (idx >= 0) & (idx < m.shape[1])
        f = np.zeros_like(m)
        f[:, ok] = m[:, idx[ok]]
        s = (m & f).sum() / max((m | f).sum(), 1)
        if s > best:
            best, at = s, c
    return float(at)


def ortho_camera(kind: str, size, k: float, c0: float, bottom: float) -> dict:
    """The far camera of an orthographic view: the world's z = 0 on pixel row `bottom`, the view's own centre line
    (x = 0, or y = 0 for a side view) on column `c0`, `k` metres per pixel."""
    W, H = size
    az = ORTHO[kind]
    _, _, R, U = matched.axes(az, 0.0, 0.0)
    aim = ((W / 2 - c0) * k) * R + ((bottom - H / 2) * k) * U
    return {"az": az, "el": 0.0, "roll": 0.0, "f_px": FAR / k, "aim": [float(v) for v in aim], "dist": FAR,
            "size": [int(W), int(H)], "kind": "ortho", "m_per_px": k, "iou": 1.0}


def read(name: str, image: str, views: list[str], height: float | None = None, mask: str | None = None,
         boxes: dict | None = None, detail: str = "medium", pad: int = 12) -> dict:
    """Cut `image` into `views` (left to right, or `boxes` {view: [x0, y0, x1, y1]}), save each with its camera,
    patches and form lines. Returns {view: record}."""
    if detail not in DETAIL:
        raise ValueError(f"detail is one of {list(DETAIL)}")
    src = Path(image).expanduser()
    rgb = np.asarray(Image.open(src).convert("RGB"))
    m = matched.mask_of(src, mask)
    runs = None
    if not boxes:
        runs = split(str(src), mask)
        if len(runs) != len(views):
            raise ValueError(f"{src.name} holds {len(runs)} separate figures (columns {runs}) but {len(views)} views "
                             f"were named ({views}): name one per figure, left to right, or pass boxes=")
    d = folder(name)
    out, k = {}, None
    for i, v in enumerate(views):
        if boxes:
            x0, y0, x1, y1 = (int(t) for t in boxes[v])
        else:
            x0, x1 = runs[i]
            ys = np.where(m[:, x0:x1].any(1))[0]
            y0, y1 = int(ys[0]), int(ys[-1]) + 1
        x0, y0 = max(x0 - pad, 0), max(y0 - pad, 0)
        x1, y1 = min(x1 + pad, m.shape[1]), min(y1 + pad, m.shape[0])
        mv, cv = m[y0:y1, x0:x1], rgb[y0:y1, x0:x1]
        ys = np.where(mv.any(1))[0]
        top, bottom = int(ys[0]), int(ys[-1]) + 1
        crop = np.dstack([cv, np.where(mv, 255, 0).astype(np.uint8)])
        Image.fromarray(crop, "RGBA").save(d / f"{v}.png")
        rec = {"image": str(d / f"{v}.png"), "source": str(src), "box": [x0, y0, x1, y1],
               "size": [x1 - x0, y1 - y0], "kind": v if v in ORTHO else "free", "detail": detail}
        if v in ORTHO:
            if k is None:
                if not height:
                    raise ValueError("height= (metres, feet to the top of the first front / side / back view) "
                                     "sets the sheet's scale")
                k = float(height) / (bottom - top)
            if v in ("front", "back"):
                c0 = mirror_line(mv)
            else:
                xs = np.where(mv[max(bottom - max(3, (bottom - top) // 25), 0):bottom].any(0))[0]
                c0 = (xs[0] + xs[-1]) / 2
            cam = ortho_camera(v, rec["size"], k, c0, bottom)
            cam.update(image=rec["image"], label=v)
            p = matched.cam_path(name, v)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(cam))
            rec.update(m_per_px=k, centre_px=float(c0), ground_px=bottom, top_m=round((bottom - top) * k, 4))
        rec["notches"] = notches(mv)
        lab = segment(cv, mv, detail)
        np.save(d / f"{v}_patches.npy", lab.astype(np.uint16))
        Image.fromarray((np.clip(form_lines(cv, mv), 0, 1) * 255).astype(np.uint8)).save(d / f"{v}_lines.png")
        rec["patches"] = int(lab.max())
        out[v] = rec
    return out


# ---------------------------------------------------------------- patches and lines

LINE = 10.0  # a full-strength line between two pieces counts like this colour step (Lab) against joining them


def steps(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """0..1 strength of a step at each pixel: in brightness (a form line) or in colour (paint), whichever is more."""
    from scipy import ndimage
    from skimage import color, filters
    lab = color.rgb2lab(filters.gaussian(rgb.astype(float) / 255, 1.0, channel_axis=-1))
    col = np.sqrt(sum(filters.sobel(lab[..., c]) ** 2 for c in (1, 2))) / 6.0
    col[~ndimage.binary_erosion(mask, iterations=3)] = 0
    return np.clip(np.maximum(form_lines(rgb, mask), col), 0, 1)


def segment(rgb: np.ndarray, mask: np.ndarray, detail: str = "medium") -> np.ndarray:
    """Label image: 0 outside the figure, patches 1..n numbered top to bottom (then left to right). The figure is
    first cut along every step in brightness or colour (watershed basins of the step strength), then neighbours
    are joined, closest first, while their mean colours (Lab, lightness counted half) plus the strength of the line
    between them stay under the detail's step. So a patch is bounded by form lines as well as by colour: on a
    subject of one plain colour the patches are its forms."""
    from skimage import color, filters, segmentation
    step, small = DETAIL[detail]
    lab = color.rgb2lab(filters.gaussian(rgb.astype(float) / 255, 0.8, channel_axis=-1)) * (0.5, 1.0, 1.0)
    edge = steps(rgb, mask)
    seg = segmentation.watershed(np.round(filters.gaussian(edge, 0.7) * 50), mask=mask)
    seg = _join(seg, lab, step, edge)
    seg = np.where(mask, seg, 0)
    seg = _absorb(seg, lab, small)
    ids = [i for i in np.unique(seg) if i]
    cy = {i: np.argwhere(seg == i).mean(0) for i in ids}
    band = max(mask.shape[0] / 24, 1.0)
    order = sorted(ids, key=lambda i: (round(cy[i][0] / band), cy[i][1]))
    lut = np.zeros(int(seg.max()) + 1, int)
    for n, i in enumerate(order, 1):
        lut[i] = n
    return lut[seg]


def _join(seg: np.ndarray, lab: np.ndarray, step: float, edge: np.ndarray) -> np.ndarray:
    """Join neighbouring pieces, closest pair first, until no two neighbours are closer than `step`. Closeness is
    the difference of their mean colours plus LINE x the mean step strength along the border they share."""
    import heapq
    ids = np.unique(seg[seg > 0])
    lut = np.zeros(int(seg.max()) + 1, int)
    lut[ids] = np.arange(1, len(ids) + 1)
    s = lut[seg]
    n = len(ids) + 1
    count = np.bincount(s.ravel(), minlength=n).astype(float)
    total = np.stack([np.bincount(s.ravel(), lab[..., c].ravel(), minlength=n) for c in range(3)], 1)
    nb = [set() for _ in range(n)]
    border: dict[tuple[int, int], list[float]] = {}
    for a, b, ea, eb in ((s[:, :-1], s[:, 1:], edge[:, :-1], edge[:, 1:]), (s[:-1], s[1:], edge[:-1], edge[1:])):
        k = (a != b) & (a > 0) & (b > 0)
        lo, hi = np.minimum(a[k], b[k]), np.maximum(a[k], b[k])
        code, inv = np.unique(lo.astype(np.int64) * n + hi, return_inverse=True)
        tot = np.bincount(inv, np.maximum(ea[k], eb[k]))
        cnt = np.bincount(inv)
        for c, t, m in zip(code, tot, cnt):
            i, j = int(c // n), int(c % n)
            nb[i].add(j)
            nb[j].add(i)
            e = border.setdefault((i, j), [0.0, 0.0])
            e[0] += float(t)
            e[1] += float(m)
    parent, ver = list(range(n)), [0] * n

    def dist(i, j):
        e = border.get((min(i, j), max(i, j)), (0.0, 1.0))
        return float(np.linalg.norm(total[i] / count[i] - total[j] / count[j])) + LINE * e[0] / max(e[1], 1.0)
    heap = [(dist(i, j), i, j, 0, 0) for i in range(1, n) for j in nb[i] if i < j]
    heapq.heapify(heap)
    while heap:
        d, i, j, vi, vj = heapq.heappop(heap)
        if d >= step:
            break
        if ver[i] != vi or ver[j] != vj or parent[i] != i or parent[j] != j:
            continue
        parent[j] = i
        total[i] += total[j]
        count[i] += count[j]
        ver[i] += 1
        border.pop((min(i, j), max(i, j)), None)
        for m in nb[j]:
            if m != i:
                old = border.pop((min(j, m), max(j, m)), None)
                if old:
                    e = border.setdefault((min(i, m), max(i, m)), [0.0, 0.0])
                    e[0] += old[0]
                    e[1] += old[1]
                nb[m].discard(j)
                nb[m].add(i)
                nb[i].add(m)
        nb[i].discard(j)
        for m in nb[i]:
            heapq.heappush(heap, (dist(i, m), min(i, m), max(i, m), ver[min(i, m)], ver[max(i, m)]))
    root = np.arange(n)
    for i in range(1, n):
        r = i
        while parent[r] != r:
            r = parent[r]
        root[i] = r
    return root[s]


def _absorb(seg: np.ndarray, lab: np.ndarray, small: int) -> np.ndarray:
    """Each connected piece is its own patch; a piece smaller than `small` px joins the neighbour nearest in colour."""
    from scipy import ndimage
    out, n = np.zeros_like(seg), 0
    for i in np.unique(seg):
        if i:
            cc, k = ndimage.label(seg == i)
            out[cc > 0] = cc[cc > 0] + n
            n += k
    for _ in range(3):
        ids, counts = np.unique(out[out > 0], return_counts=True)
        tiny = ids[counts < small]
        if not len(tiny):
            break
        cols = {int(i): lab[out == i].mean(0) for i in ids}
        for i in tiny:
            ring = ndimage.binary_dilation(out == i, iterations=2) & (out != i) & (out > 0)
            near = [int(j) for j in np.unique(out[ring])]
            if near:
                out[out == i] = min(near, key=lambda j: float(np.linalg.norm(cols[j] - cols[int(i)])))
    return out


def form_lines(rgb: np.ndarray, mask: np.ndarray, sigma: float = 1.2, full: float = 0.10) -> np.ndarray:
    """0..1 strength of a brightness step at each pixel inside the figure (its own outline left out)."""
    from scipy import ndimage
    from skimage import color, filters
    g = filters.gaussian(color.rgb2gray(rgb.astype(float) / 255), sigma)
    e = filters.sobel(g)
    e[~ndimage.binary_erosion(mask, iterations=3)] = 0
    return np.clip(e / full, 0, 1)


def notches(mask: np.ndarray, span: float = 7.0, deep: float = 2.2, most: int = 48) -> list[list[float]]:
    """The points where the figure's outline turns INWARD sharply (an armpit, a crotch, where a neck meets a
    shoulder, the tip of a gap between two parts): the places parts are divided at. On every contour, holes
    included: a point counts when the chord between its neighbours `span` px either side runs outside the figure
    and the point stands at least `deep` px off that chord. Strongest first within a few px of each other;
    returned top to bottom as [x, y] in the view's pixels."""
    from skimage import measure
    found = []
    H, W = mask.shape
    for c in measure.find_contours(np.pad(mask.astype(float), 1), 0.5):
        c = c - 1.0
        seg = np.hypot(*np.diff(c, axis=0).T)
        length = float(seg.sum())
        if length < 6 * span:
            continue
        t = np.concatenate([[0.0], np.cumsum(seg)])
        n = int(length / 1.5)
        u = np.linspace(0, length, n, endpoint=False)
        pts = np.stack([np.interp(u, t, c[:, 0]), np.interp(u, t, c[:, 1])], 1)  # (row, col), evenly spaced, closed
        k = max(2, int(round(span / 1.5)))
        a, b = np.roll(pts, k, 0), np.roll(pts, -k, 0)
        mid = (a + b) / 2
        mi = np.clip(np.round(mid).astype(int), 0, [H - 1, W - 1])
        outside = ~mask[mi[:, 0], mi[:, 1]]
        chord = b - a
        off = np.abs(chord[:, 0] * (pts[:, 1] - a[:, 1]) - chord[:, 1] * (pts[:, 0] - a[:, 0])) / np.maximum(np.hypot(*chord.T), 1e-9)
        score = np.where(outside, off, 0.0)
        for i in np.argsort(-score):
            if score[i] < deep:
                break
            found.append((float(score[i]), float(pts[i, 1]), float(pts[i, 0])))
    found.sort(reverse=True)
    keep = []
    for sc, x, y in found:
        if all(np.hypot(x - kx, y - ky) > 2.2 * span for _, kx, ky in keep):
            keep.append((sc, x, y))
        if len(keep) >= most:
            break
    keep.sort(key=lambda q: (round(q[2] / 12), q[1]))
    return [[round(x, 1), round(y, 1)] for _, x, y in keep]


def colour_word(rgb) -> str:
    """A plain word for a colour (for the patch table: something to check a number against)."""
    import colorsys
    r, g, b = (float(c) / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.16:
        return "white" if v > 0.85 else "light grey" if v > 0.6 else "grey" if v > 0.35 else "dark grey" if v > 0.16 else "black"
    deg = h * 360
    hue = next(w for top, w in ((15, "red"), (40, "orange"), (70, "yellow"), (165, "green"), (200, "cyan"),
                                (260, "blue"), (300, "purple"), (345, "pink"), (361, "red")) if deg < top)
    if hue in ("red", "orange", "yellow") and s < 0.45:
        hue = "cream" if v > 0.75 else "tan" if v > 0.5 else "brown"
    elif hue in ("red", "orange") and v < 0.6:
        hue = "brown"
    elif hue == "red" and v > 0.8 and s < 0.6:
        hue = "pink"
    return ("dark " if v < 0.3 else "") + hue


def view_record(name: str, view: str) -> dict:
    from . import featuremap
    fm = featuremap.load(name)
    if view not in fm["views"]:
        raise ValueError(f"{name} has no reference view {view!r} (have {sorted(fm['views'])}); read_reference first")
    return fm["views"][view]


def patches(name: str, view: str) -> np.ndarray:
    return np.load(folder(name) / f"{view}_patches.npy").astype(int)


def patch_table(name: str, view: str, rec: dict, box=None) -> list[dict]:
    """One row per patch: id, colour, where its middle is (px; metres too in an orthographic view), its size."""
    lab = patches(name, view)
    rgb = np.asarray(Image.open(rec["image"]).convert("RGB"))
    rows = []
    for i in range(1, int(lab.max()) + 1):
        ys, xs = np.where(lab == i)
        if not len(ys):
            continue
        cx, cy = float(xs.mean()), float(ys.mean())
        if box and not (box[0] <= cx <= box[2] and box[1] <= cy <= box[3]):
            continue
        row = {"id": i, "colour": colour_word(rgb[ys, xs].mean(0)), "px": [round(cx), round(cy)],
               "w_px": int(np.ptp(xs)) + 1, "h_px": int(np.ptp(ys)) + 1, "area_px": int(len(ys))}
        if rec.get("m_per_px"):
            k = rec["m_per_px"]
            row["at_m"] = [round((cx - rec["centre_px"]) * k, 3), round((rec["ground_px"] - cy) * k, 3)]
        rows.append(row)
    return rows


# ---------------------------------------------------------------- pictures for the sculptor

def nice_step(span: float) -> int:
    """A ruler step (1, 2 or 5 x a power of ten) giving about six ticks across `span` px."""
    raw = max(span / 6, 1.0)
    p = 10 ** math.floor(math.log10(raw))
    return int(max(1, p * (5 if raw >= 5 * p else 2 if raw >= 2 * p else 1)))


def _ruler(im: Image.Image, box, scale: float, step: int) -> Image.Image:
    """Pixel rulers along the top and left: the numbers a mark's box / polygon / line is written in."""
    M = 34
    out = Image.new("RGB", (im.width + M, im.height + M), (255, 255, 255))
    out.paste(im, (M, M))
    d, f = ImageDraw.Draw(out), _font(12)
    x0, y0, x1, y1 = box
    for x in range((x0 // step + 1) * step, x1, step):
        px = M + (x - x0) * scale
        d.line([(px, M - 6), (px, M)], fill=(0, 0, 0))
        d.text((px - 10, 4), str(x), fill=(0, 0, 0), font=f)
    for y in range((y0 // step + 1) * step, y1, step):
        py = M + (y - y0) * scale
        d.line([(M - 6, py), (M, py)], fill=(0, 0, 0))
        d.text((2, py - 7), str(y), fill=(0, 0, 0), font=f)
    return out


def draw(name: str, view: str, rec: dict, focus=None, width: int = 760) -> Image.Image:
    """picture | numbered patches | form lines, of the whole view or of `focus` [x0, y0, x1, y1] (view px), with
    pixel rulers. Patch numbers sit on each patch's widest spot."""
    from scipy import ndimage
    from skimage import segmentation
    rgba = np.asarray(Image.open(rec["image"]).convert("RGBA"))
    lab = patches(name, view)
    lines = np.asarray(Image.open(folder(name) / f"{view}_lines.png")).astype(float) / 255
    H, W = lab.shape
    x0, y0, x1, y1 = (int(v) for v in (focus or (0, 0, W, H)))
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 - x0 < 8 or y1 - y0 < 8:
        raise ValueError(f"focus {focus} is outside the view ({W} x {H} px)")
    s = width / (x1 - x0)
    size = (width, int(round((y1 - y0) * s)))
    fg = rgba[..., 3:4] / 255.0
    pic = (rgba[..., :3] * fg + 255 * (1 - fg)).astype(np.uint8)
    flat = pic.astype(float).copy()
    for i in range(1, int(lab.max()) + 1):
        mk = lab == i
        if mk.any():
            flat[mk] = 0.35 * pic[mk].mean(0) + 0.65 * pic[mk]
    flat[segmentation.find_boundaries(lab, mode="inner") & (lab > 0)] = (20, 20, 20)
    ln = (255 * (1 - 0.95 * lines) * (lab > 0) + 255 * (lab == 0)).astype(np.uint8)

    def panel(a, resample):
        return Image.fromarray(a.astype(np.uint8)).crop((x0, y0, x1, y1)).resize(size, resample)
    mid = panel(flat, Image.NEAREST if s > 2 else Image.LANCZOS)
    d = ImageDraw.Draw(mid)
    sub = lab[y0:y1, x0:x1]
    for i in np.unique(sub):
        if not i:
            continue
        mk = sub == i
        dist = ndimage.distance_transform_edt(np.pad(mk, 1))[1:-1, 1:-1]
        cy, cx = np.unravel_index(dist.argmax(), dist.shape)
        fpx = int(np.clip(dist.max() * s * 0.9, 11, 22))
        t = str(int(i))
        d.text(((cx + 0.5) * s, (cy + 0.5) * s), t, fill=(255, 255, 255), font=_font(fpx), anchor="mm",
               stroke_width=2, stroke_fill=(0, 0, 0))
    step = nice_step(x1 - x0)
    left = panel(pic, Image.LANCZOS)
    dl = ImageDraw.Draw(left)
    for i, (nx, ny) in enumerate(rec.get("notches") or [], 1):  # the outline's notches: the ends a cut can name
        if x0 <= nx < x1 and y0 <= ny < y1:
            px, py = (nx - x0) * s, (ny - y0) * s
            dl.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(0, 200, 255), outline=(0, 0, 0))
            dl.text((px + 6, py - 2), f"n{i}", fill=(0, 60, 160), font=_font(13), anchor="lm", stroke_width=2, stroke_fill=(255, 255, 255))
    tiles = [_ruler(p, (x0, y0, x1, y1), s, step) for p in (left, mid, panel(np.dstack([ln] * 3), Image.LANCZOS))]
    out = Image.new("RGB", (sum(t.width for t in tiles) + 8 * 2, tiles[0].height + 26), (255, 255, 255))
    dd, x = ImageDraw.Draw(out), 0
    for t, cap in zip(tiles, (f"{view}: the picture, and its outline's notches (n1 ..)", "its patches (numbers to point at)", "its form lines (form or paint: your call)")):
        dd.text((x + 36, 4), cap, fill=(0, 0, 0), font=_font(14))
        out.paste(t, (x, 26))
        x += t.width + 8
    return out
