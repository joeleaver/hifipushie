"""The model beside its reference, view by view: the comparison a modeller makes all the time, as a picture an
agent can read and a list it can act on.

For each flat reference view (read_reference: front, side, side_r, back) the model is seen from that view's own
camera, at the picture's own pixels, straight from the field (no render: seconds). One picture per view, three
panels:
    the reference | the model, with the reference's outline and the lines inside it drawn in red | the difference
    (red = only the reference has clay there: add; blue = only the model has: take away), the worst places numbered.
The text gives, per view, the numbered places (how far the outline is off, where, on which mass) each with the
`grab` call that would move that outline to the reference's, and the reference's inside lines that the model has
no line near. An outline can match round the wrong figure (a bean for a head on a body): the lines inside it are
what say so.

`ignore`: masses left out of the model (a limb held away from the body for the rig, which the picture shows
hanging): the reference's own limb still shows where the picture has it.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from . import matched, refread, sdf, store
from .featurerays import depth_image, rays, relief
from .spec import compile_prims, mirror_name

FLAT = ("front", "side", "side_r", "back")
GRAB_VIEW = {"front": ("front", 0, 2), "back": ("front", 0, 2), "side": ("side", 1, 2), "side_r": ("side", 1, 2)}
OFF_M = 0.006  # an outline less than this far off is not listed
AREA_M2 = 1.5e-4  # nor a difference smaller than this
LINE_M = 0.05  # a reference line shorter than this is not listed
NEAR_M = 0.012  # a model line this near a reference line answers it
MOST = 5


def flat_views(name: str) -> list[str]:
    from . import featuremap
    fm = featuremap.load(name)
    return [v for v in FLAT if v in fm["views"] and matched.cam_path(name, v).exists()]


def _model(name: str, resolution: int):
    from . import featuresee
    prims = compile_prims(featuresee.expanded(store.load(name), name))
    frame = sdf.frame(prims, resolution)
    field = np.min([sdf.evaluate(ps, at=frame).field for ps in sdf.streams(prims)], 0)
    return prims, sdf.Grid(field, np.asarray(frame[0], float), float(frame[1]))


def _owners(prims, P: np.ndarray) -> np.ndarray:
    """For each point on the model's surface, the name of the mass it belongs to."""
    adds = [p for p in prims if p.op == "add"]
    vals = np.stack([sdf.SDF[p.kind](P, p.params) for p in adds])
    return np.array([p.name for p in adds])[vals.argmin(0)]


def _model_lines(depth: np.ndarray, hit: np.ndarray, k: float) -> np.ndarray:
    """Where the model itself has a line inside its outline: one mass standing in front of another, or a crease."""
    d = np.where(hit, depth, 0.0)
    step = np.zeros_like(hit)
    crease = np.zeros_like(hit)
    for ax in (0, 1):
        g = np.abs(np.diff(d, axis=ax))
        both = np.minimum(np.take(hit, range(hit.shape[ax] - 1), ax), np.take(hit, range(1, hit.shape[ax]), ax))
        s = (g > 6 * k) & both
        c = np.abs(np.diff(d, n=2, axis=ax)) > 1.2 * k
        pad = [(0, 0), (0, 0)]
        pad[ax] = (0, 1)
        step |= np.pad(s, pad)
        pad[ax] = (1, 1)
        crease |= np.pad(c, pad)
    inner = ndimage.binary_erosion(hit, iterations=3)
    return (step | crease) & inner


def _places(only: np.ndarray, other: np.ndarray, k: float) -> list[dict]:
    """The separate places where `only` has clay and `other` has none, biggest first."""
    lab, n = ndimage.label(ndimage.binary_opening(only, iterations=1))
    if not n:
        return []
    dist, idx = ndimage.distance_transform_edt(~other, return_indices=True)
    out = []
    for i in range(1, n + 1):
        m = lab == i
        area = float(m.sum()) * k * k
        far = np.unravel_index(np.argmax(np.where(m, dist, -1)), m.shape)
        off = float(dist[far]) * k
        if off < OFF_M or area < AREA_M2:
            continue
        near = (int(idx[0][far]), int(idx[1][far]))
        out.append({"area": area, "off": off, "far": (int(far[0]), int(far[1])), "near": near})
    return sorted(out, key=lambda r: -r["area"])[:MOST]


def _ref_lines(lines: np.ndarray, ref: np.ndarray, model_lines: np.ndarray, k: float) -> tuple[list[dict], np.ndarray]:
    """The reference's lines inside its outline with no line of the model near them, longest first, and all the
    reference's lines as a mask."""
    from skimage.morphology import skeletonize
    inner = ndimage.binary_erosion(ref, iterations=max(3, int(0.006 / k)))
    sk = skeletonize((lines > 0.45) & inner)
    near = ndimage.binary_dilation(model_lines, iterations=max(2, int(round(NEAR_M / k))))
    lab, n = ndimage.label(sk, structure=np.ones((3, 3)))
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        length = len(ys) * k
        if length < LINE_M:
            continue
        if near[ys, xs].mean() < 0.35:
            run = "across" if np.ptp(xs) > 1.5 * np.ptp(ys) else "up and down" if np.ptp(ys) > 1.5 * np.ptp(xs) else "slanting"
            out.append({"length": length, "at": (float(ys.mean()), float(xs.mean())), "run": run, "mask": lab == i})
    return sorted(out, key=lambda r: -r["length"])[:MOST], sk


def _font(px: int):
    try:
        return ImageFont.truetype(refread.FONT, px)
    except OSError:
        return ImageFont.load_default()


def _stored(name: str, known: set) -> tuple[str | None, bool]:
    """A mass's name as the spec stores it (the ".L" one of a pair) and whether it was the mirrored twin."""
    if name in known:
        return name, False
    tw = name[:-2] + ".L" if name.endswith(".R") else mirror_name(name)
    return (tw, True) if tw in known else (None, False)


def compare(name: str, views: list[str] | None = None, ignore: list[str] | None = None, resolution: int = 176) -> dict:
    """{"views": {view: {"iou", "places": [...], "lines": [...], "picture": PIL image}}, "skipped": [...]}."""
    have = flat_views(name)
    if not have:
        raise ValueError(f"{name} has no flat reference view yet: read_reference(name, image, views=[\"front\", "
                         "\"side\", \"back\"], height=...) cuts the sheet and gives each view its camera")
    todo = views or have
    gone = [v for v in todo if v not in have]
    if gone:
        raise ValueError(f"no flat reference view {gone} (this model has: {have})")
    spec = store.load(name)
    known = set(spec.get("bones") or {}) | set(spec.get("blobs") or {})
    ig = set(ignore or [])
    bad = sorted(n for n in ig if n not in known)
    if bad:
        raise ValueError(f"ignore: no mass called {bad} (the model's masses: {sorted(known)})")
    ig |= {mirror_name(n) for n in ig if mirror_name(n)}
    prims, whole = _model(name, resolution)
    out = {"views": {}, "ignored": sorted(ig)}
    for v in todo:
        rec, cam = refread.view_record(name, v), matched.load_camera(name, v)
        k = float(rec["m_per_px"])
        rgba = np.asarray(Image.open(rec["image"]).convert("RGBA"))
        ref = rgba[..., 3] > 127
        lines = np.asarray(Image.open(refread.folder(name) / f"{v}_lines.png").convert("L"), float) / 255
        depth = depth_image(whole, cam)
        hit = np.isfinite(depth)
        H, W = hit.shape
        ys, xs = np.nonzero(hit)
        C, d, _ = rays(cam, np.stack([xs + 0.5, ys + 0.5], 1))
        P = C + depth[ys, xs][:, None] * d
        owner = np.full(hit.shape, "", dtype=object)
        owner[ys, xs] = _owners(prims, P)
        if ig:
            drop = np.isin(owner, sorted(ig))
            hit = hit & ~drop
            depth = np.where(hit, depth, np.inf)
        gv, iu, iv = GRAB_VIEW[v]

        def world(py, px):  # the pixel's place on the plane through the view's aim (a far camera: no perspective)
            c, dd, _ = rays(cam, np.array([[px + 0.5, py + 0.5]]))
            p = np.asarray(c, float) + cam["dist"] * dd[0]
            return [round(float(p[iu]), 3), round(float(p[iv]), 3)]

        places = []
        for kind, only, other in (("short", ref & ~hit, hit), ("out", hit & ~ref, ref)):
            for r in _places(only, other, k):
                # short: the model's outline (near) should go out to the reference's (far); out: the model's (far) back in
                a, b = (r["near"], r["far"]) if kind == "short" else (r["far"], r["near"])
                at, to = world(*a), world(*b)
                mass, twin = _stored(str(owner[a]) if owner[a] else "", known)
                if mass is None and kind == "short":  # the nearest model pixel may be just off the surface
                    yy, xx = np.nonzero(hit)
                    j = np.argmin((yy - a[0]) ** 2 + (xx - a[1]) ** 2)
                    mass, twin = _stored(str(owner[yy[j], xx[j]]), known)
                if twin and gv == "front":
                    at, to = [-at[0], at[1]], [-to[0], to[1]]
                rad = float(np.clip(max(2.2 * r["off"], 0.6 * np.sqrt(r["area"])), 0.02, 0.3))
                call = (f'grab("{name}", of=["{mass}"], view="{gv}", at={at}, to={to}, radius={rad:.3f})'
                        if mass else "(on a kit's own piece: no grab)")
                places.append({"kind": kind, "off": r["off"], "area": r["area"], "at": at, "to": to, "mass": mass,
                               "radius": rad, "grab": call, "px": r["far"], "twin": twin})
        places.sort(key=lambda r: (r["twin"], -r["area"]))
        kept = []  # a mirrored model is off the same way on both sides: say it once, on the side the spec stores
        for p in places:
            def same(q):
                if not p["mass"] or q["mass"] != p["mass"] or q["kind"] != p["kind"]:
                    return False
                if q["twin"] != p["twin"]:  # the other one of a mirrored pair
                    return True
                return (gv == "front" and abs(p["at"][0]) > 0.02  # the other side of a centre mass
                        and np.hypot(q["at"][0] + p["at"][0], q["at"][1] - p["at"][1]) < 0.04)
            if not any(same(q) for q in kept):
                kept.append(p)
        places = sorted(kept, key=lambda r: -r["area"])[:MOST]
        mlines = _model_lines(np.where(hit, depth, 0.0), hit, k)
        missing, sk = _ref_lines(lines, ref, mlines, k)
        for m in missing:
            m["where"] = world(int(m["at"][0]), int(m["at"][1]))
        iou = float((ref & hit).sum() / max((ref | hit).sum(), 1))
        out["views"][v] = {"iou": iou, "places": places, "lines": [{k2: m[k2] for k2 in ("length", "where", "run")} for m in missing],
                           "picture": _picture(v, rgba, ref, hit, depth, sk, missing, places, k, bool(ig))}
    return out


def _picture(view: str, rgba, ref, hit, depth, sk, missing, places, k: float, ignoring: bool, height: int = 560) -> Image.Image:
    H, W = ref.shape
    s = height / H
    size = (max(int(round(W * s)), 1), height)
    bg = np.full((H, W, 3), 232, np.uint8)
    a = (rgba[..., 3:4].astype(float) / 255)
    left = Image.fromarray((rgba[..., :3] * a + bg * (1 - a)).astype(np.uint8)).resize(size, Image.LANCZOS)
    clay = np.repeat(relief(np.where(hit, depth, np.inf), k)[..., None], 3, -1)
    clay[~hit] = 232
    edge = ref & ~ndimage.binary_erosion(ref, iterations=1)
    mid = Image.fromarray(clay).resize(size, Image.LANCZOS)
    over = np.zeros((H, W, 4), np.uint8)
    over[sk] = (225, 40, 40, 150)
    for m in missing:
        over[ndimage.binary_dilation(m["mask"], iterations=1)] = (225, 30, 30, 255)
    over[ndimage.binary_dilation(edge, iterations=1)] = (225, 30, 30, 255)
    mid = Image.alpha_composite(mid.convert("RGBA"), Image.fromarray(over, "RGBA").resize(size, Image.NEAREST)).convert("RGB")
    diff = np.full((H, W, 3), 255, np.uint8)
    diff[ref & hit] = 205
    diff[ref & ~hit] = (225, 40, 40)
    diff[hit & ~ref] = (45, 90, 225)
    right = Image.fromarray(diff).resize(size, Image.NEAREST)
    dr = ImageDraw.Draw(right)
    f = _font(26)
    for i, p in enumerate(places, 1):
        x, y = p["px"][1] * s, p["px"][0] * s
        x = min(max(x + 10, 4), size[0] - 22)
        y = min(max(y - 14, 4), size[1] - 30)
        dr.text((x, y), str(i), font=f, fill=(0, 0, 0), stroke_width=3, stroke_fill=(255, 255, 255))
    gap, top = 10, 30
    sheet = Image.new("RGB", (size[0] * 3 + gap * 2, height + top), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    small = _font(15)
    for i, (im, title) in enumerate(((left, f"reference ({view})"),
                                     (mid, "model" + (" (without the ignored masses)" if ignoring else "") + ": red = the reference's outline and lines"),
                                     (right, "red = add clay, blue = take away"))):
        x = i * (size[0] + gap)
        sheet.paste(im, (x, top))
        d.text((x + 4, 6), title[: max(int(size[0] / 8.2), 12)], font=small, fill=(0, 0, 0))
    return sheet


def text(name: str, res: dict) -> str:
    lines = []
    for v, r in res["views"].items():
        lines.append(f"{v}: outline overlap {r['iou']:.0%}" + ("" if r["places"] else "; no outline difference worth listing"))
        for i, p in enumerate(r["places"], 1):
            what = "SHORT (add clay)" if p["kind"] == "short" else "STICKS OUT (take away)"
            ax = "x, z" if GRAB_VIEW[v][0] == "front" else "y, z"
            lines.append(f"  {i}. the model {what} by up to {p['off'] * 100:.1f} cm round ({ax}) {p['at']}, {p['area'] * 1e4:.0f} cm2"
                         + (f", on {p['mass']}" if p["mass"] else "") + f": {p['grab']}")
        if r["lines"]:
            lines.append("  lines inside the reference's outline with no line of the model near them (form the outline can't "
                         "show: a mass in front of another, a crease; some are paint):")
            ax = "x, z" if GRAB_VIEW[v][0] == "front" else "y, z"
            lines += [f"    a line {m['length'] * 100:.0f} cm long running {m['run']}, round ({ax}) {m['where']}" for m in r["lines"]]
    if res["ignored"]:
        lines.append(f"left out of the model: {', '.join(res['ignored'])}. The reference's own still shows where the picture has it.")
    lines.append("next: one picture per view: look at each. Fix the BIGGEST difference on the whole figure first: a mass in "
                 "the wrong place or of the wrong size is its own joint or size; an outline that is off on a mass that is "
                 "otherwise right is the grab given; two masses that should be one are a fuse. A red line with no line of "
                 "the model under it is form still to make (one mass standing in front of another, a crease), unless it is "
                 "paint. Then look_beside again. A limb held away from the body for the rig is not a fault: ignore=[its masses].")
    return "\n".join(lines)
