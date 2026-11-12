"""Lay a reference's flat views on a model before it is measured (featuresee.py), and say what had to move.

A picture can't say how tall a model was built, where its ground is, or where its origin lies along its length.
Those are fitted to the model's outline, reported as findings about the model, and features are then placed
relative to the whole figure, as an eye compares them.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from . import featuremap, matched, sdf
from .featurerays import first_hit


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / max((a | b).sum(), 1))


def align_flat(name: str, fm: dict, cams: dict, whole: sdf.Grid) -> list[str]:
    """Lay each flat view on the model before measuring, and say what had to move. A picture can't say how tall the
    model was built, where its ground is, or where its origin lies along its length, so those are fitted: one scale
    for the whole sheet (from its first flat view), each view's ground row, and a side view's centre line (a front
    or back view keeps its mirror line). What moved is a finding about the model, reported, not hidden: features
    are then placed relative to the whole figure, as an eye compares them."""
    import json as _json
    from . import refread
    flat = [v for v in cams if fm["views"].get(v, {}).get("kind") in refread.ORTHO]
    notes, scale = [], None
    for v in flat:
        cam, rec = cams[v], fm["views"][v]
        fig = np.asarray(Image.open(rec["image"]).convert("RGBA"))[..., 3] > 127
        W, H = cam["size"]

        def outline(c):
            ys, xs = np.mgrid[0:H:2, 0:W:2]
            return np.isfinite(first_hit(whole, c, np.stack([xs.ravel() + 1.0, ys.ravel() + 1.0], 1)).reshape(ys.shape))
        ref = fig[::2, ::2]
        mod = outline(cam)[:ref.shape[0], :ref.shape[1]]
        if not mod.any():
            continue
        # the model's own height and lowest point, in metres (an outline drawn in the view can be cut by its edge)
        zi = np.where((whole.field < 0).any((0, 1)))[0]
        z_lo, z_hi = whole.origin[2] + zi[0] * whole.voxel, whole.origin[2] + zi[-1] * whole.voxel
        rows = np.where(fig.any(1))[0]
        k0 = cam["m_per_px"]
        if scale is None:  # the sheet's scale: the model's height over the figure's drawn height
            scale = float((z_hi - z_lo) / ((rows[-1] - rows[0] + 1) * k0))
        k = k0 * scale if abs(scale - 1) > 0.015 else k0
        side = rec["kind"] in ("side", "side_r")
        ground = int(round(rows[-1] + 1 + z_lo / k))  # the model's lowest point on the figure's lowest row
        dy = ground - rec["ground_px"]
        trial = refread.ortho_camera(rec["kind"], (W, H), k, rec["centre_px"], ground)
        mod = outline(trial)[:ref.shape[0], :ref.shape[1]]
        best, at = _iou(mod, ref), 0
        for sx in (range(-mod.shape[1] // 4, mod.shape[1] // 4 + 1) if side else ()):
            i = _iou(np.roll(mod, sx, 1), ref)
            if i > best:
                best, at = i, sx
        dx = 2 * at
        if k != k0 or abs(dx) >= 3 or abs(dy) >= 3:
            new = refread.ortho_camera(rec["kind"], (W, H), k, rec["centre_px"] + dx, rec["ground_px"] + dy)
            cam.update({q: new[q] for q in ("f_px", "aim", "m_per_px")})
            rec.update(m_per_px=k, centre_px=float(rec["centre_px"] + dx), ground_px=int(rec["ground_px"] + dy))
            matched.cam_path(name, v).write_text(_json.dumps(cam))
            why = []
            if k != k0:
                why.append(f"the model is {scale:.2f} x the height the sheet was read at")
            if abs(dy) >= 3:
                why.append(f"its lowest point is {abs(z_lo) * 1000:.0f} mm {'below' if z_lo < 0 else 'above'} its own zero")
            if abs(dx) >= 3:
                why.append(f"its centre line is {abs(dx) * k * 1000:.0f} mm from where the drawn feet put it")
            notes.append(f"{v}: {'; '.join(why)}. The view now sits on the model (outlines overlap {best:.0%})")
            for c in fm["features"].values():  # a mark's place in metres follows its view
                if v in c["marks"]:
                    g = c["marks"][v]
                    x0, y0, x1, y1 = g["box"]
                    sign = -1.0 if rec["kind"] in ("back", "side_r") else 1.0
                    axis = "x" if rec["kind"] in ("front", "back") else "y"
                    g["world"] = {axis: round(sign * (g["centre_px"][0] - rec["centre_px"]) * k, 4),
                                  "z": round((rec["ground_px"] - g["centre_px"][1]) * k, 4),
                                  "z_lo": round((rec["ground_px"] - y1) * k, 4), "z_hi": round((rec["ground_px"] - y0) * k, 4),
                                  "w": round((x1 - x0) * k, 4), "h": round((y1 - y0) * k, 4)}
    if notes:
        featuremap.save(name, fm)
    return notes
