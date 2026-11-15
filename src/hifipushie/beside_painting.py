"""look_beside from the painting's own angle (beside.py does the flat views).

A concept painting is a three-quarter view: it is where a figure reads as itself, and where four blind blockouts in
a row could only set two pictures side by side and guess (p3 to p6: "the painting with the model's outline over it,
and the same add / remove map the flat views get"). With the painting's camera fitted (fit_concept_camera), this
puts the model in the painting's own frame, from the field in seconds:

    the painting, the model's outline and inside lines over it in blue
  | the model in clay, its parts tinted, the painting's outline and form lines over it in red
  | red = the painting has clay here and the model none, blue = the other way, the worst places numbered

A place is given by the painting's own pixel (the painting never changes, so a place kept on purpose stays put as
the model changes), the mass it is on, and which way the painting's outline lies from the model's in the figure's
own words (up, forward, toward its left). No call is suggested: what to change is the modeller's judgement.
`side` says which side of the figure the camera stands on: a near ear in the painting is the ".R" twin as often
as not, and a silhouette can't tell the sides apart (p6).
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

from . import matched, refread
from .featurerays import depth_image, rays

NEAR = 0.05  # a place is the one kept on purpose when it comes within this part of the painting's width of the record
FLAT = ("front", "side", "side_r", "back", "top")


def camera_label(name: str) -> str | None:
    """The fitted camera of the concept picture: "concept" (fit_concept_camera's own label), else the newest camera
    that is not a flat reference view's (agents label it as they like: p6 called it "painting")."""
    d = matched.cam_path(name, "concept").parent
    if not d.exists():
        return None
    cams = sorted((p for p in d.glob("*.json") if p.stem not in FLAT), key=lambda p: p.stat().st_mtime)
    if not cams:
        return None
    return "concept" if any(p.stem == "concept" for p in cams) else cams[-1].stem


def has_camera(name: str) -> bool:
    return camera_label(name) is not None


def side(cam: dict) -> str:
    """Which side of the figure the camera stands on, and where that puts its left and right in the picture."""
    a = ((float(cam["az"]) + 180) % 360) - 180
    where = "front" if abs(a) < 90 else "back"
    if abs(a) < 8 or abs(a) > 172:
        return (f"The painting's camera looks at the figure square from the {where} (azimuth {a:+.0f}, {cam['el']:+.0f} "
                "above the horizon).")
    near, twin = ("left (+x)", ".L") if a > 0 else ("right (-x)", ".R")
    pic = ("right" if a > 0 else "left") if where == "front" else ("left" if a > 0 else "right")
    extra = "" if twin == ".L" else " (the mirrors of the \".L\" ones the spec stores)"
    return (f"The painting's camera stands at the figure's {where} {near.split()[0]} (azimuth {a:+.0f}, {cam['el']:+.0f} "
            f"above the horizon): the figure's {near} side is the nearer one and is on the picture's {pic}, so the "
            f"nearer ear, arm and leg are the \"{twin}\" ones{extra}. If the painting plainly shows the other side, the "
            "camera was fitted mirrored: fit_concept_camera again with az of the other sign.")


def _way(vec: np.ndarray) -> str:
    v = vec / max(float(np.linalg.norm(vec)), 1e-9)
    words = []
    if abs(v[2]) > 0.4:
        words.append("up" if v[2] > 0 else "down")
    if abs(v[1]) > 0.4:
        words.append("forward" if v[1] < 0 else "back")
    if abs(v[0]) > 0.4:
        words.append("toward the figure's left (+x)" if v[0] > 0 else "toward the figure's right (-x)")
    return " and ".join(words) or "toward the camera's side"


def view(name: str, prims, whole, ig: set, meant: list[dict], used: set, known: set, width: int = 448) -> dict:
    """The painting's view for beside.compare: {"iou", "places", "on_purpose", "lines": [], "picture", "side", "fit"}."""
    from skimage.morphology import skeletonize

    from . import beside
    cam0 = matched.load_camera(name, camera_label(name))
    W0, H0 = cam0["size"]
    W = int(min(width, W0))
    H = int(round(H0 * W / W0))
    cam = dict(cam0, size=[W, H], f_px=cam0["f_px"] * W / W0)
    rgb = np.asarray(Image.open(cam0["image"]).convert("RGB").resize((W, H), Image.LANCZOS))
    ref = np.asarray(Image.fromarray(matched.mask_of(cam0["image"], cam0.get("mask")).astype(np.uint8) * 255)
                     .resize((W, H), Image.BILINEAR)) > 127
    depth = depth_image(whole, cam)
    hit = np.isfinite(depth)
    ys, xs = np.nonzero(hit)
    C, d, _ = rays(cam, np.stack([xs + 0.5, ys + 0.5], 1))
    owner = np.full(hit.shape, "", dtype=object)
    owner[ys, xs] = beside._owners(prims, C + depth[ys, xs][:, None] * d)
    if ig:
        hit = hit & ~np.isin(owner, sorted(ig))
        depth = np.where(hit, depth, np.inf)
    k = float(cam["dist"] / cam["f_px"])  # metres a pixel, at the camera's aim
    _, _, R, U = matched.axes(cam["az"], cam["el"], cam["roll"])
    mine = [(i, e) for i, e in enumerate(meant) if e["plane"] == "painting"]
    s0 = W0 / W

    def meant_by(mask):
        yy, xx = np.nonzero(mask)
        for i, e in mine:
            if np.hypot(xx * s0 - e["at"][0], yy * s0 - e["at"][1]).min() <= NEAR * W0:
                return i
        return None

    places, kept_on = [], {}
    accepted = np.zeros(hit.shape, bool)
    for kind, only, other in (("short", ref & ~hit, hit), ("out", hit & ~ref, ref)):
        for r in beside._places(only, other, k):
            i = meant_by(r["mask"])
            if i is not None:
                used.add(i)
                accepted |= r["mask"]
                o = kept_on.setdefault(i, {"why": meant[i]["why"], "at": meant[i]["at"], "area": 0.0, "off": 0.0})
                o["area"] += r["area"]
                o["off"] = max(o["off"], r["off"])
                continue
            a, b = (r["near"], r["far"]) if kind == "short" else (r["far"], r["near"])  # the model's outline, the painting's
            mass, twin = beside._stored(str(owner[a]) if owner[a] else "", known)
            if mass is None and kind == "short" and hit.any():
                yy, xx = np.nonzero(hit)
                j = np.argmin((yy - a[0]) ** 2 + (xx - a[1]) ** 2)
                mass, twin = beside._stored(str(owner[yy[j], xx[j]]), known)
            vec = (b[1] - a[1]) * R - (b[0] - a[0]) * U
            places.append({"kind": kind, "off": r["off"], "area": r["area"], "mass": mass, "twin": twin,
                           "at": [int(round(r["far"][1] * s0)), int(round(r["far"][0] * s0))], "px": r["far"],
                           "way": _way(vec), "vec": [round(float(x), 2) for x in vec / max(np.linalg.norm(vec), 1e-9)]})
    places = sorted(places, key=lambda r: -r["area"])[:beside.MOST]
    iou = float((ref & hit & ~accepted).sum() / max(((ref | hit) & ~accepted).sum(), 1))
    sk = skeletonize(refread.form_lines(rgb, ref) > 0.5)
    edge = hit & ~ndimage.binary_erosion(hit, iterations=1)
    inner = beside._model_lines(np.where(hit, depth, 0.0), hit, k)
    rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
    pic = beside._picture("painting", rgba, ref, hit, depth, sk, [], places, k, bool(ig), accepted,
                          tint=beside.part_tint(prims, owner, hit), model_edge=(edge, inner))
    return {"iou": iou, "places": places, "on_purpose": list(kept_on.values()), "lines": [], "picture": pic,
            "side": side(cam0), "fit": float(cam0.get("iou", 0.0))}


def text(r: dict) -> list[str]:
    lines = [f"painting (the concept's own angle): outline overlap {r['iou']:.0%}"
             + ("" if r["places"] else "; no outline difference worth listing"), "  " + r["side"],
             "  LOOK at this picture before the list: the left panel is the painting with the model's outline and inside "
             "lines in blue, the middle the model with the painting's outline and inside lines (snout, eyes, mouth, "
             "folds) in red. Where a blue shape sits beside the painted thing it stands for, or a red line crosses bare "
             "clay, a mass is in the wrong place, the wrong size or not made: that is what the outline's list can't say. (If "
             "EVERY feature sits off to the same side of its painted one, the camera's turn is off, not the model: "
             "fit_concept_camera again with an az guess.)"]
    for i, p in enumerate(r["places"], 1):
        what = "SHORT (add clay)" if p["kind"] == "short" else "STICKS OUT (take away)"
        on = ""
        if p["mass"]:
            twin = p["mass"][:-2] + ".R" if p["twin"] and p["mass"].endswith(".L") else None
            on = f", on {twin} (the mirror of {p['mass']})" if twin else f", on {p['mass']}"
        lines.append(f"  {i}. the model {what} by up to {p['off'] * 100:.1f} cm round pixel {p['at']} of the painting, "
                     f"{p['area'] * 1e4:.0f} cm2{on}: to meet the painting's outline the model's would move {p['way']}, "
                     "as the camera sees it")
    for o in r.get("on_purpose", []):
        lines.append(f"  on purpose (kept on record with the model: no need to give it again), not listed and not "
                     f"counted: {o['why']} (round pixel {o['at']}, {o['area'] * 1e4:.0f} cm2, up to {o['off'] * 100:.1f} cm)")
    return lines
