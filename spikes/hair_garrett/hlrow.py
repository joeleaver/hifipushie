"""hlrow.py <model> [patch.json ...]: WHICH locks make the hairline crop's lay (successor 16).

laycal.strands' hairline__front crop (view 0, az 0 / el 38, 95 mm; 120k strands, the same z-buffer), its visible
segments binned by their STRAND ROOT's distance behind the hairline (hair_loose.inside, mm): per band the share of
visible length, the mean |image angle| (0 = lying across, 90 = vertical) and the band's axial resultant (signed: +
= rising to the image's right), so a fix can target the band that carries the error. Then the crop's raster lay
(texmeas, as the screen row) for the same strands."""
import copy
import json
import sys

import numpy as np

BANDS = (0, 5, 10, 15, 20, 30, 45, 1000)


def run(m, patch=None, count=120000):
    from hifipushie import hair, hair_read as hr, hair_strands as hs, humanfit, store
    from laygeo import merge
    import laycal
    spec = store.load(m)
    tag = m
    if patch:
        spec = copy.deepcopy(spec)
        merge(spec["hair"], json.load(open(patch)))
        tag = m + ":" + patch.rsplit("/", 1)[-1].replace(".json", "")
    sc = hair.scalp(m, spec)
    g = hair.fit_to_head(copy.deepcopy(hair.groom_params(spec)), sc)
    line = hair.hairline(sc, g)
    sd = hair.job(m, spec, count=count)["strands"]
    D = hs.strands_of_model(sd)
    pts, cnt = D["pts"].astype(float), D["counts"]
    first = np.r_[0, np.cumsum(cnt)[:-1]]
    ra, re_, _ = sc.coords(pts[first])
    din = np.asarray(hair.inside(sc, line, ra, re_), float) * 1000  # mm behind the line per strand
    sid = np.repeat(np.arange(len(cnt)), cnt)
    ok = np.ones(len(pts), bool); ok[first + cnt - 1] = False
    ia = np.where(ok)[0]; ib = ia + 1
    A, B, S_ = pts[ia], pts[ib], sid[ia]
    refs = json.loads((store.HOME / m / "human_refs.json").read_text())
    v, az, el, mm = laycal.CROPS["hairline__front"]
    cam = refs["cameras"][int(v[1:])]
    uv = humanfit.project(cam, sc.point(np.array([az]), np.array([el]), 0.01))[0]
    eye, R = hr.cam_eye(cam)
    s = mm / 1000.0 * cam["f"] / np.linalg.norm(sc.C - eye)
    x0, y0 = uv - s / 2
    qa = (humanfit.project(cam, A) - [x0, y0]) / s * 520
    qb = (humanfit.project(cam, B) - [x0, y0]) / s * 520
    q = (qa + qb) / 2
    depth = ((A + B) / 2 - eye) @ R[2]
    inb = (q[:, 0] >= 0) & (q[:, 0] < 520) & (q[:, 1] >= 0) & (q[:, 1] < 520)
    nrm = (A + B) / 2 - sc.C; nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    inb &= ((eye - (A + B) / 2) * nrm).sum(1) > 0
    cell = (q[inb] // 2).astype(int); key = cell[:, 0] * 300 + cell[:, 1]
    zb = np.full(300 * 300, np.inf); np.minimum.at(zb, key, depth[inb])
    vis = np.zeros(len(A), bool); vis[np.where(inb)[0]] = depth[inb] < zb[key] + 0.0015
    d = (qb - qa)[vis]; lpx = np.hypot(d[:, 0], d[:, 1])
    ang = np.degrees(np.arctan2(np.abs(d[:, 1]), np.abs(d[:, 0])))
    z = lpx * np.exp(2j * np.arctan2(-d[:, 1], d[:, 0]))  # image y down: - for "rising"
    dv = din[S_[vis]]
    tot = lpx.sum()
    print(f"{tag}: hairline crop, visible segs {vis.sum()}, mean|ang| {(ang * lpx).sum() / tot:.1f}")
    rows = {}
    for lo, hi in zip(BANDS[:-1], BANDS[1:]):
        k = (dv >= lo) & (dv < hi)
        if lpx[k].sum() <= 0:
            continue
        sh = lpx[k].sum() / tot
        a = (ang[k] * lpx[k]).sum() / lpx[k].sum()
        zr = z[k].sum() / lpx[k].sum()
        res_ang = np.degrees(np.angle(zr) / 2)
        rows[f"{lo}-{hi}"] = (round(float(sh), 3), round(float(a), 1), round(float(res_ang), 1), round(float(abs(zr)), 2))
        print(f"  roots {lo:3d}-{hi:4d} mm behind: share {sh:.3f}  mean|ang| {a:5.1f}  resultant {res_ang:+6.1f} deg (R {abs(zr):.2f})")
    k = dv < 0
    if k.any():
        print(f"  roots OUTSIDE the line: share {lpx[k].sum() / tot:.3f}")
    r = laycal.strands(m, count, None, patch)["hairline__front"]["raster"]["lay"]
    print(f"{tag}: hairline raster lay {r:.1f} (target 17.8 +- 5)")
    return rows, r


if __name__ == "__main__":
    pats = sys.argv[2:] or [None]
    for p in pats:
        run(sys.argv[1], p)
