"""field.gd's coverage pictures measured: the share of GROUND pixels hidden by grass, by distance along the ground
(each pixel's ray met with the ground plane; bands of +-15% round 2 / 6 / 12 / 30 m), per view, + triangles and GPU ms.

  python spikes/godot_veg/field_measure.py <prefix> [<prefix> ...]
"""
import json
import sys

import numpy as np
from PIL import Image

BANDS = (2.0, 6.0, 12.0, 30.0)


def coverage(prefix: str, view: str, J: dict) -> dict:
    a = np.asarray(Image.open(f"{prefix}_{view}_cov.png").convert("RGB"), float) / 255
    h, w = a.shape[:2]
    eye, look = np.array(J["views"][view]["eye"]), np.array(J["views"][view]["look"])
    f = look - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, [0, 1.0, 0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    t = np.tan(np.radians(J["fov"]) / 2)
    ys, xs = np.mgrid[0:h, 0:w]
    dx = ((xs + 0.5) / w * 2 - 1) * t * w / h
    dy = (1 - (ys + 0.5) / h * 2) * t
    d = f[None, None] + dx[..., None] * r[None, None] + dy[..., None] * u[None, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where(d[..., 1] < -1e-6, -eye[1] / d[..., 1], np.inf)
    dist = np.hypot(k * d[..., 0], k * d[..., 2])
    # MSAA mixes grass (0, 1, 0) and ground (1, 0, 1) inside a pixel: the green channel, linear, is the pixel's share of grass
    lin = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    g, r = lin(a[..., 1]), lin(a[..., 0])
    sky = (a[..., 2] > 0.5) & (a[..., 0] < 0.3) & (a[..., 1] < 0.3)
    share = g / np.maximum(g + r, 1e-6)
    out = {}
    for b in BANDS:
        m = (dist > 0.85 * b) & (dist < 1.15 * b) & ~sky
        out[b] = round(float(share[m].mean()), 3) if m.sum() > 200 else None
    return out


for prefix in sys.argv[1:]:
    J = json.load(open(prefix + ".json"))
    line = f"{prefix.split('/')[-1]:<28} tris {J['triangles'] / 1e6:6.2f} M  placed {J['placed']:6d}"
    for v in ("eye", "high"):
        c = coverage(prefix, v, J)
        line += f"  | {v}: gpu {J['views'][v]['gpu_ms']:.1f} ms, hidden " + " ".join(f"{int(b)}m {'-' if c[b] is None else format(c[b], '.2f')}" for b in BANDS)
        J["views"][v]["hidden"] = {str(b): c[b] for b in BANDS}
    json.dump(J, open(prefix + ".json", "w"), indent=1)
    print(line)
