"""Measure the solid rock relief on a face: rock_relief's offset on a vertical plane through a point of the face
(along the strike x up the face), split into scale bands (rms per band, m), the blocks' size distribution and the
share of recesses / proud blocks. uv run python examples/rock_measure.py [alps|pebble] [x,y] [size m]"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

from hifipushie import terrain, terrain_mesh as tm

ROOT = Path("/home/joe/dev/hifipushie")
SPECS = {"alps": ("workspace/terrain/t3_alps/spec.json", [2215, 3690]),
         "pebble": ("workspace/terrain/pebble_disc/spec.json", [176, 224])}


def measure(T, at, size=40.0, h=0.1):
    field = tm.build_field(T)[0]
    r = field.rock
    fd0 = field.face_dir(np.array([at[0]]), np.array([at[1]]))[0]
    n = fd0 / max(np.linalg.norm(fd0), 1e-9)
    t = np.array([-n[1], n[0]])
    z0 = float(T.sample(np.array(at, float)[None])[0])
    s = np.arange(0, size, h)
    U, V = np.meshgrid(s, s)
    P = np.c_[at[0] + (U.ravel() - size / 2) * t[0], at[1] + (U.ravel() - size / 2) * t[1], z0 - size / 2 + V.ravel()]
    fd = np.tile(fd0, (len(P), 1))
    g = field.grain_at(P[:, 0], P[:, 1]) if field.grain is not None else None
    O = tm.rock_relief(P, r, g, None, fd, None).reshape(len(s), len(s))
    out = {"rms_total": round(float(O.std()), 3), "bands_rms_m": {}}
    for a, b in ((0.2, 1.0), (1.0, 3.0), (3.0, 10.0), (10.0, 30.0)):
        band = ndimage.gaussian_filter(O, a / h / 2) - ndimage.gaussian_filter(O, b / h / 2)
        out["bands_rms_m"][f"{a:g}-{b:g} m"] = round(float(band.std()), 3)
    gy, gx = np.gradient(O, h)
    out["slope_p50_p99"] = [round(float(x), 2) for x in np.percentile(np.hypot(gx, gy), [50, 99])]
    loc = O - ndimage.median_filter(O, size=int(8 / h))
    out["recess_share(>0.4 m back)"] = round(float((loc > 0.4).mean()), 3)
    out["proud_share(>0.3 m out)"] = round(float((loc < -0.3).mean()), 3)
    if r.get("blocks"):
        out["blocks"] = structure(P, r, fd, len(s), h)
    return out


def structure(P, r, fd, n, h):
    """The rock structure on the sampled face: blocks (connected cells of one bed and one block per family shown),
    their area and aspect; the joint traces' angle to the beds (share within 10 deg of a right angle: masonry);
    drawn crack length per m2 (open joints, open bed planes, master joints: the colour's dark lines)."""
    from skimage.measure import label, regionprops
    from skimage.morphology import skeletonize
    from hifipushie import terrain_blocks as tb
    B = r["blocks"]
    zoff = r["bed_offset"](P[:, :2]) if r.get("bed_offset") else 0.0
    I = tb.ids(P, B, fd, zoff)
    key = (I["K"] * 16 + I["j"]).astype(np.int64)
    for m, w in enumerate(I["weights"]):
        key = key * 1000003 + np.where(w > 0.3, I["blocks"][m], 0)
    _, inv = np.unique(key, return_inverse=True)
    lab = label(inv.reshape(n, n) + 1, connectivity=1, background=0)
    props = [q for q in regionprops(lab) if q.area * h * h >= 0.05]
    area = np.array([q.area * h * h for q in props])
    asp = np.array([q.major_axis_length / max(q.minor_axis_length, 1.0) for q in props])
    # joint traces on this face: the direction of (face normal x joint normal), its angle from the vertical
    fn = np.r_[fd[0], 1.0]
    fn = fn / np.linalg.norm(fn)
    ang = []
    beds = np.unique(np.c_[I["K"], I["j"]], axis=0)
    for K, j in beds:
        for m in range(len(tb.AZ)):
            nrm, n2 = tb._joint_frame(np.array([K]), np.array([j]), m, B)
            wgt = float(tb.face_weight(n2, fd[:1])[0] * B["family"][m])
            if wgt < 0.3:
                continue
            t = np.cross(fn, nrm[0])
            ang.append(np.degrees(np.arccos(min(1.0, abs(t[2]) / max(np.linalg.norm(t), 1e-9)))))
    ang = np.array(ang)
    dark = np.zeros(len(P))
    for m in range(len(tb.AZ)):
        dark = np.maximum(dark, I["weights"][m] * (I["open"][m] < 0.08))
    dark = np.maximum(dark, I["bed_crack"] * (I["bed_edge"] < 0.08))
    dark = np.maximum(dark, I["master"] > 0.3)
    sk = skeletonize(dark.reshape(n, n) > 0.5)
    face = (n * h) ** 2
    # every boundary (open or closed): bed planes + shown families' block edges, for the drawn share
    edge = (I["bed_edge"] < 0.08)
    for m, w in enumerate(I["weights"]):
        edge |= (w > 0.3) & (I["edges"][m] < 0.08)
    allsk = skeletonize(edge.reshape(n, n))
    return {"count": int(len(area)), "per_100m2": round(100 * len(area) / face, 1),
            "area_m2_p10_50_90": [round(float(x), 2) for x in np.percentile(area, [10, 50, 90])],
            "small_share(<2 m2)": round(float((area < 2).mean()), 2),
            "aspect_p50_p90": [round(float(x), 2) for x in np.percentile(asp, [50, 90])],
            "bed_thick_m_p10_50_90": [round(float(x), 2) for x in np.percentile(I["thick"], [10, 50, 90])],
            "thin_bed_share": round(float(I["thin"].mean()), 3),
            "joint_trace_deg_from_vertical_p10_50_90": [round(float(x), 1) for x in np.percentile(ang, [10, 50, 90])]
            if len(ang) else None,
            "right_angle_share(<10 deg)": round(float((ang < 10).mean()), 2) if len(ang) else None,
            "drawn_crack_m_per_m2": round(float(sk.sum() * h / face), 3),
            "all_edges_m_per_m2": round(float(allsk.sum() * h / face), 3),
            "drawn_share_of_edges": round(float(sk.sum() / max(allsk.sum(), 1)), 2)}


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "alps"
    spec, at = SPECS[name]
    if len(sys.argv) > 2 and "," in sys.argv[2]:
        at = [float(v) for v in sys.argv[2].split(",")]
    size = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3][0].isdigit() else 40.0
    T = terrain.load(ROOT / spec)
    if "--noblocks" in sys.argv:  # (the rock before jointed blocks: joints back on)
        T.spec["rock"] = {**(T.spec.get("rock") or {}), "blocks": 0}
    print(json.dumps({name: measure(T, at, size)}, indent=1))
