"""Looks at a plant: Blender renders (clay skeleton, leafed colour) and the reference sheet (photo, outlines over
each other, renders, numbers)."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from . import render as _render
from . import veg_mesh, vegetation

SCRIPT = Path(__file__).with_name("blender_vegetation.py")


def _euler(frames: np.ndarray) -> np.ndarray:
    from scipy.spatial.transform import Rotation
    return Rotation.from_matrix(frames).as_euler("xyz") if len(frames) else np.zeros((0, 3))


def render(tree: dict, views: list[dict], save: str | None = None, timeout: float = 900) -> dict:
    """Render views of a grown tree in Blender (see blender_vegetation's job). Returns timings and counts."""
    from . import veg_leaf
    s = tree["spec"]
    t0 = time.perf_counter()
    M = veg_mesh.tubes(tree)
    tw = veg_leaf.place(tree)
    arrays = {"V": M["V"], "F": M["F"], "tan": M["tan"], "radius": M["radius"]}
    tris = 0
    if len(tw["pos"]):
        nv = int(tw["variant"].max()) + 1
        per = []
        for i in range(nv):
            tm = veg_leaf.twig_mesh(s["leaves"], i)
            arrays.update({f"twig{i}_V": tm["V"], f"twig{i}_F": tm["F"], f"twig{i}_mat": tm["mat"], f"twig{i}_col": tm["col"]})
            per.append(len(tm["F"]))
        tris = int(sum(per[v] for v in tw["variant"]))
        arrays.update(tw_pos=tw["pos"], tw_rot=_euler(tw["frame"]), tw_scale=tw["scale"], tw_var=tw["variant"],
                      tw_tint=vegetation._u(tw["key"], 77))
    with tempfile.TemporaryDirectory(prefix="hifipushie-veg-") as tmp:
        npz = Path(tmp) / "plant.npz"
        np.savez(npz, **arrays)
        lf = s["leaves"]
        job = {"npz": str(npz), "views": views, "save": save, "bark": s.get("bark") or {},
               "leaf": {k: lf[k] for k in ("color", "through", "translucency", "roughness") if k in lf},
               **(s.get("look") or {})}
        jp = Path(tmp) / "job.json"
        jp.write_text(json.dumps(job))
        t1 = time.perf_counter()
        r = subprocess.run([_render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
                            str(SCRIPT), "--", str(jp)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return {"mesh_s": round(t1 - t0, 2), "blender_s": round(time.perf_counter() - t1, 2),
            "triangles": int(len(M["F"])), "twigs": int(len(tw["pos"])), "leaf_triangles": tris}


def closeup_focus(tree: dict, azimuth: float = 0.0):
    """A point on the crown's near side at about half height, with twigs: where a close-up shows the foliage."""
    from . import veg_leaf
    import math
    tw = veg_leaf.place(tree)
    P = tw["pos"] if len(tw["pos"]) else tree["pos"][tree["ends"]]
    c, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    depth = -P[:, 0] * s_ + P[:, 1] * c  # toward +y is away from the camera at azimuth 0
    H = tree["height"]
    ok = (P[:, 2] > 0.4 * H) & (P[:, 2] < 0.65 * H)
    if not ok.any():
        ok = np.ones(len(P), bool)
    i = np.flatnonzero(ok)[np.argsort(depth[ok])[: max(1, ok.sum() // 20)]]
    return P[i].mean(0).tolist()


def overlay(ref_mask: np.ndarray, ours: np.ndarray, size: int = 420):
    """The two row-filled outlines at equal height, feet together: reference red, ours blue, both dark."""
    from PIL import Image
    A, B = vegetation._outline(ref_mask, size), vegetation._outline(ours, size)
    if (A & B[:, ::-1]).sum() > (A & B).sum():
        B = B[:, ::-1]
    im = np.full(A.shape + (3,), 255, np.uint8)
    im[A & ~B] = (225, 90, 80)
    im[B & ~A] = (80, 120, 225)
    im[A & B] = (70, 70, 70)
    cols = np.flatnonzero((A | B).any(0))
    return Image.fromarray(im[:, max(cols[0] - 8, 0): cols[-1] + 8])


def reference_sheet(spec: dict, ref: dict | None, out: str, bare: bool = False, title: str = "", height: int = 520) -> dict:
    """One row: the photo | outlines over each other | clay skeleton | leafed, with the numbers under it.
    ref = {"image", "mask": reference_mask kwargs, "credit"} or None."""
    from PIL import Image, ImageDraw
    T = vegetation.grow(spec)
    panels, text = [], [f"{title or spec.get('species', 'plant')}: age {T['spec']['age']}, {T['stats']['nodes']} nodes, "
                        f"{T['stats']['height_m']} m, trunk {T['stats']['trunk_diameter_m']} m, grown in {T['stats']['grow_s']} s"]
    az = 0
    info = {"stats": T["stats"]}
    if ref:
        R = vegetation.reference_mask(ref["image"], **ref["mask"])
        m = vegetation.match(T, R, bare=bare, azimuths=(0, 45, 90, 135))
        az = m["azimuth"]
        photo = Image.open(ref["image"]).convert("RGB")
        c = ref["mask"].get("crop")
        if c is None and ref["mask"].get("polygon"):
            P = np.asarray(ref["mask"]["polygon"])
            c = [max(int(P[:, 0].min()) - 20, 0), max(int(P[:, 1].min()) - 20, 0), int(P[:, 0].max()) + 20, int(P[:, 1].max()) + 20]
        photo = photo.crop(c) if c else photo
        photo = photo.resize((max(1, int(photo.width * height / photo.height)), height))
        panels += [photo, overlay(R, m["mask"], height)]
        f = lambda M: "  ".join(f"{k} {M[k]:.2f}" for k in ("width_over_height", "bole", "widest_at", "lopsided"))
        text += [f"outline IoU {m['iou']:.2f} (reference red, ours blue, view azimuth {az})",
                 f"reference: {f(m['ref'])}", f"ours:      {f(m['ours'])}"]
        info["match"] = {k: m[k] for k in ("iou", "azimuth", "ours", "ref")}
    ang = vegetation.branch_angles(T, 1)
    text.append(f"first-order branches: {ang['n']}, insertion p10/50/90 {ang['insertion_p10_50_90']} deg, "
                f"far-half elevation {ang['elevation_p10_50_90']} deg")
    info["angles"] = ang
    tmp = Path(tempfile.mkdtemp(prefix="hifipushie-vegsheet-"))
    asp = 0.95
    views = [{"name": "clay", "azimuth": az, "out": str(tmp / "clay.png"), "size": [int(height * asp), height],
              "leaves": False, "clay": True},
             {"name": "bare", "azimuth": az, "elevation": 4, "out": str(tmp / "bare.png"),
              "size": [int(height * asp), height], "leaves": False}]
    has_leaves = T["spec"].get("season") not in ("winter", "bare", "dead") and not T["spec"].get("decay")
    if has_leaves:
        views.append({"name": "leaf", "azimuth": az, "elevation": 4, "out": str(tmp / "leaf.png"),
                      "size": [int(height * asp), height]})
        views.append({"name": "close", "azimuth": az, "elevation": 8, "out": str(tmp / "close.png"),
                      "size": [int(height * asp), height], "focus": closeup_focus(T, az), "span": 2.4})
    info["render"] = render(T, views)
    text.append(f"look: mesh {info['render']['mesh_s']} s + Blender {info['render']['blender_s']} s, "
                f"{info['render']['triangles']} branch triangles, {info['render']['twigs']} twigs "
                f"({info['render']['leaf_triangles']} instanced triangles)")
    panels += [Image.open(v["out"]).convert("RGB") for v in views]
    W = sum(p.width for p in panels) + 6 * (len(panels) - 1)
    S = Image.new("RGB", (max(W, 900), height + 16 * len(text) + 12), "white")
    x = 0
    for p in panels:
        S.paste(p, (x, 0))
        x += p.width + 6
    d = ImageDraw.Draw(S)
    for i, t in enumerate(text):
        d.text((6, height + 6 + 16 * i), t, fill=(0, 0, 0))
    if ref and ref.get("credit"):
        d.text((6, 4), ref["credit"], fill=(255, 255, 255))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    S.save(out)
    info["out"] = out
    return info
