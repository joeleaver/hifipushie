"""creasepath.py <model with lid_fold and references> <out dir> [views=0,1]: the upper-lid crease's PATH in the pictures
against OURS, per view, as overlay tiles <out>/crease_v<i>.png (the picture's eye region; RED = the picture's crease traced,
GREEN = our fold's crease ring (base.head.lid_fold's slit ring on GNM's lid rings) projected through the same camera) and
numbers (the traced path's length past the outer canthus, its drop below the canthus height, mean gap to ours in mm). LIGHT.
Tracing: a dark-line (ridge) filter at ~0.8 mm on the picture's luminance; seeds = the strongest line points 3-10 mm over
the upper lash line at the lid's middle; followed both ways along the line's own direction (a step of 0.5 mm, the next
point the strongest line response within +-35 deg of the heading), stopping when the response falls under a third of the
seed's or the path runs 25 mm from the eye's centre."""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from hifipushie import blockin as bi, gnm_fold as gf, humanfit, likeness as lk, store, base as basemod

m, out = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
VI = [int(x) for x in kw.get("views", "0,1").split(",")]
os.makedirs(out, exist_ok=True)
spec, rj = store.load(m), bi._refs(m)
UP = ((33, 246, 161, 160, 159, 158, 157, 173, 133), (263, 466, 388, 387, 386, 385, 384, 398, 362))
res = {}
for vi in VI:
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    P = np.asarray(bi.detect_view(img, v), float)
    if P.ndim != 2:      # (no face found in this view: a profile)
        continue
    P = P[:, :2]
    st = humanfit.state(bi.view_base(spec["base"], rj, vi))
    L = st["L"]
    M = humanfit.project(cam, L[:70])
    mmpx = 1000.0 * float(np.linalg.norm(L[36] - L[39])) / float(np.linalg.norm(M[36] - M[39]))
    lum = np.log(np.maximum(np.asarray(img, float) @ [0.2126, 0.7152, 0.0722] / 255.0, 1e-3))
    s = max(0.8 / mmpx, 1.0)
    hxx = ndimage.gaussian_filter(lum, s, order=(0, 2)) * s * s
    hyy = ndimage.gaussian_filter(lum, s, order=(2, 0)) * s * s
    hxy = ndimage.gaussian_filter(lum, s, order=(1, 1)) * s * s
    tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
    l1 = 0.5 * (tr + df)
    resp = np.clip(l1, 0, None)
    th = 0.5 * np.arctan2(2 * hxy, hxx - hyy)            # the direction ACROSS the line (largest curvature)
    tiles = []
    wid = [float(np.linalg.norm(P[ids[0]] - P[ids[-1]])) for ids in UP]
    for se, ids in enumerate(UP):
        if wid[se] < 0.65 * max(wid):       # the far eye of a turned view (behind the nose): not traced
            continue
        lid = P[list(ids)]
        cen = 0.5 * (lid[0] + lid[-1])
        outer = lid[0] if se == 0 else lid[0]           # 33 / 263 = the outer canthus
        inner = lid[-1]
        ex = (outer - inner) / np.linalg.norm(outer - inner)
        upv = np.array([ex[1], -ex[0]])
        if upv[1] > 0:
            upv = -upv
        # OURS first: the fold's slit ring on the built head, projected (the wrap chains: round the outer corner too)
        cfg = spec["base"]["head"].get("lid_fold") or {}
        ka = int(cfg.get("ring", 5)) + 1
        ch, _ang = gf.chains_wrap(float(cfg.get("reach", 15.5)), wrap_deg=float(cfg.get("wrap", gf.WRAP_DEG)))
        ch = ch[_ang <= 90.0 + float(cfg.get("wrap", gf.WRAP_DEG)) - 0.5 * 30.0]   # only the chains the fold MOVES (weight > 0.5): the
        # rest of the ring sits unmoved on its own circle round the eye (drawn, it looked as if our crease turned down)
        tpl = st["tpl"]
        from hifipushie import onemesh
        fid = np.asarray(tpl["fid"])
        gidall = np.asarray(onemesh.asset()["gnm_id"])
        gid = np.where(fid < len(gidall), gidall[np.clip(fid, 0, len(gidall) - 1)], -1)
        rows = {int(gg): i for i, gg in enumerate(gid) if gg >= 0}
        both = []
        for ring_ids in (ch[:, ka], gf.topo()["mir"][ch[:, ka]]):
            pts = np.array([np.asarray(tpl["P"])[rows[int(x)]] for x in ring_ids if int(x) in rows])
            both.append(humanfit.project(cam, pts))
        ours = min(both, key=lambda q: np.linalg.norm(q.mean(0) - cen))
        # + the crease's TAIL past the outer canthus (lid_fold.<side>.tail), when the fold has one
        tails = [np.asarray((cfg.get(k_) or {}).get("tail", {}).get("path", []), int) for k_ in ("L", "R")]
        tails = [humanfit.project(cam, np.array([np.asarray(tpl["P"])[rows[int(x)]] for x in t_ if int(x) in rows])) for t_ in tails if len(t_) >= 3]
        if tails:
            tq = min(tails, key=lambda q: np.linalg.norm(q.mean(0) - cen))
            if np.linalg.norm(tq.mean(0) - cen) * mmpx < 25:
                ours = np.r_[ours, tq]
        # the seed: the strongest line within 3 mm of OUR path's middle (a prior on where the crease is; the lashes and
        # the hair were taken when the search started at the lash line)
        mid = ours[len(ours) // 3]
        best, bp = -1, None
        for h in np.arange(-3.0, 3.01, 0.2):
            for a in np.linspace(-1.5, 1.5, 7):
                q = mid + upv * h / mmpx + ex * a / mmpx
                r = resp[int(round(q[1])), int(round(q[0]))]
                if r > best:
                    best, bp = r, q
        path = {1: [bp], -1: [bp]}
        for sg in (1, -1):
            hd = ex * sg
            p = bp.copy()
            for _ in range(int(40 / 0.5)):
                cands = []
                for da in np.radians(np.arange(-35, 36, 5)):
                    c, s_ = np.cos(da), np.sin(da)
                    d = np.array([c * hd[0] - s_ * hd[1], s_ * hd[0] + c * hd[1]])
                    q = p + d * 0.5 / mmpx
                    yi, xi = int(round(q[1])), int(round(q[0]))
                    if not (0 <= yi < resp.shape[0] and 0 <= xi < resp.shape[1]):
                        continue
                    cands.append((resp[yi, xi] - 0.002 * abs(np.degrees(da)) * best / 35, q, d))
                if not cands:
                    break
                r, q, d = max(cands, key=lambda t: t[0])
                if resp[int(round(q[1])), int(round(q[0]))] < best / 3 or np.linalg.norm(q - cen) * mmpx > 25:
                    break
                path[sg].append(q)
                p, hd = q, d
        trace = np.array(path[-1][::-1] + path[1][1:])
        # numbers: how far the picture's path runs past the outer canthus, and drops below it
        along = (trace - outer) @ ex * mmpx
        past = float(max(along.max(), 0.0))
        drop = float(max(((outer - trace) @ upv * mmpx)[along > 0].max() if (along > 0).any() else 0.0, 0.0))
        ours_past = float(max(((ours - outer) @ ex * mmpx).max(), 0.0))
        from scipy.spatial import cKDTree
        gap = float(np.median(cKDTree(ours).query(trace)[0]) * mmpx)
        res[f"v{vi}_eye{se}"] = {"picture_past_outer_canthus_mm": round(past, 1), "picture_drop_below_canthus_mm": round(drop, 1),
                                 "ours_past_outer_canthus_mm": round(ours_past, 1), "median_gap_mm": round(gap, 1)}
        lo, hi = np.r_[trace, ours, lid].min(0) - 12 / mmpx, np.r_[trace, ours, lid].max(0) + 12 / mmpx
        side = float(max(hi - lo))
        box = (lo[0], lo[1], lo[0] + side, lo[1] + side)
        k = 600 / side
        tile = img.crop(tuple(int(round(x)) for x in box)).resize((600, 600), Image.LANCZOS)
        dr = ImageDraw.Draw(tile)
        f = lambda Q: [((x - box[0]) * k, (y - box[1]) * k) for x, y in Q]  # noqa: E731
        dr.line(f(trace), fill=(255, 40, 40), width=4)
        dr.line(f(ours), fill=(40, 230, 60), width=4)
        tiles.append((se, tile))
    for se, t in tiles:
        t.save(f"{out}/crease_v{vi}_eye{se}.png")
print(json.dumps(res, indent=1))
json.dump(res, open(f"{out}/crease.json", "w"), indent=1)
