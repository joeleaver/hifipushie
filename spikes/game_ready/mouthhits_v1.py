"""mouthhits.py <glb> <out prefix> [pose ...]: a flat front ID / albedo pass of the mouth (orthographic, numpy z-buffer,
no lighting, no Blender) per pose of shots_expr8.json, and the numbers the open MAJOR causes need:
  opening   = pixels whose first hit is a teeth / tongue triangle or a head triangle NOT seen from the front in the
              neutral (inner rolls, sock): area, aspect, width at 15 / 50 / 85 % of its height over its max width
              (ellipse 0.71 / 1 / 0.71; a squared box ~1), fill = area / bbox
  walls     = share of the opening that is head seen edge-on (|n.view| < 0.35): the grey slabs
  torn      = share of the opening that is head seen from BEHIND (back faces) or nothing, overall and within 6 mm of
              each corner
  tongue    = share of the opening, its top's depth below the opening's top (share of the opening height), albedo
  edges     = upper / lower opening edge per 0.25 mm column: the largest jump over 1 mm and jumps > 0.5 mm (notches)
  seal      = (neutral) the lips band's darkest albedo along the seam vs the band's median, and blue-grey pixels
Writes <out>_<pose>_id.png and _alb.png (0.25 mm / px)."""
import json, struct, sys
import numpy as np
from PIL import Image
from hifipushie import rig_audit as ra

A = "/mnt/data/hifipushie/assembly"
glb, out = sys.argv[1], sys.argv[2]
poses = sys.argv[3:] or ["neutral", "jaw", "smile", "smileteeth"]
SH = {s["name"]: s.get("shapes", {}) for s in json.load(open(f"{A}/shots_expr8.json"))}
g = ra.read_glb(glb)
raw = open(glb, "rb").read(); jl = struct.unpack_from("<I", raw, 12)[0]; doc = json.loads(raw[20:20 + jl]); b0 = 28 + jl


def uv_of(name):
    me = next(m for m in doc["meshes"] if m["name"] == name); p = me["primitives"][0]
    a = doc["accessors"][p["attributes"]["TEXCOORD_0"]]; bv = doc["bufferViews"][a["bufferView"]]
    uv = np.frombuffer(raw, np.float32, a["count"] * 2, b0 + bv.get("byteOffset", 0) + a.get("byteOffset", 0)).reshape(-1, 2)
    mat = doc["materials"][p["material"]]; ti = mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    im = doc["images"][doc["textures"][ti]["source"]]; v = doc["bufferViews"][im["bufferView"]]
    import io
    tex = np.asarray(Image.open(io.BytesIO(raw[b0 + v.get("byteOffset", 0): b0 + v.get("byteOffset", 0) + v["byteLength"]])).convert("RGB"))
    return uv.astype(float), tex


PARTS = ["head", "teeth", "teeth_lower", "tongue"]
UV = {p: uv_of(p) for p in PARTS}
up = g["meshes"]["teeth"]["V"]; cz = up[np.abs(up[:, 0]) < 0.004, 2].min()
S = 0.00025; X0, X1, Z0, Z1 = -0.034, 0.034, cz - 0.030, cz + 0.016
W, H = int((X1 - X0) / S), int((Z1 - Z0) / S)


def raster(shapes):
    dep = np.full((H, W), np.inf); pid = np.full((H, W), -1); fid = np.full((H, W), -1); ny = np.zeros((H, W))
    alb = np.zeros((H, W, 3))
    for k, part in enumerate(PARTS):
        m = g["meshes"][part]; V = m["V"].copy()
        for s, w in shapes.items():
            if s in m["targets"]:
                V += w * m["targets"][s]
        T = V[m["F"]]
        keep = np.where(((T[:, :, 0] > X0 - .002) & (T[:, :, 0] < X1 + .002) & (T[:, :, 2] > Z0 - .002) & (T[:, :, 2] < Z1 + .002)).any(1))[0]
        uv, tex = UV[part]; th, tw = tex.shape[:2]
        for f in keep:
            t = T[f]; px = (t[:, 0] - X0) / S; pz = (Z1 - t[:, 2]) / S
            n = np.cross(t[1] - t[0], t[2] - t[0]); nn = np.linalg.norm(n)
            if nn < 1e-14:
                continue
            i0, i1 = max(int(np.floor(px.min())), 0), min(int(np.ceil(px.max())), W - 1)
            j0, j1 = max(int(np.floor(pz.min())), 0), min(int(np.ceil(pz.max())), H - 1)
            if i1 < i0 or j1 < j0:
                continue
            ii, jj = np.meshgrid(np.arange(i0, i1 + 1) + .5, np.arange(j0, j1 + 1) + .5)
            d = (px[1] - px[0]) * (pz[2] - pz[0]) - (px[2] - px[0]) * (pz[1] - pz[0])
            if abs(d) < 1e-12:
                continue
            l1 = ((ii - px[0]) * (pz[2] - pz[0]) - (px[2] - px[0]) * (jj - pz[0])) / d
            l2 = ((px[1] - px[0]) * (jj - pz[0]) - (ii - px[0]) * (pz[1] - pz[0])) / d
            l0 = 1 - l1 - l2; ins = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
            if not ins.any():
                continue
            y = l0 * t[0, 1] + l1 * t[1, 1] + l2 * t[2, 1]
            J, I = np.where(ins); J += j0; I += i0; yy = y[ins]
            win = yy < dep[J, I]
            J, I, yy = J[win], I[win], yy[win]
            dep[J, I] = yy; pid[J, I] = k; fid[J, I] = f; ny[J, I] = n[1] / nn
            q = uv[m["F"][f]]; c = (l0[ins][win, None] * q[0] + l1[ins][win, None] * q[1] + l2[ins][win, None] * q[2])
            alb[J, I] = tex[np.clip((c[:, 1] * th).astype(int), 0, th - 1), np.clip((c[:, 0] * tw).astype(int), 0, tw - 1)]
    return pid, fid, ny, alb


base = raster({})
seen0 = set(base[1][base[0] == 0].tolist())  # head faces seen from the front in the neutral
xs = X0 + (np.arange(W) + .5) * S; zs = Z1 - (np.arange(H) + .5) * S
COL = np.array([[30, 30, 30], [220, 190, 170], [90, 90, 200], [230, 40, 40], [255, 255, 255], [200, 200, 120], [240, 120, 160], [60, 160, 60]])
for pose in poses:
    pid, fid, ny, alb = base if pose == "neutral" else raster(SH[pose])
    head = pid == 0; interior = head & ~np.isin(fid, list(seen0))
    cls = np.zeros(pid.shape, int)
    cls[head & (ny < -0.35)] = 1; cls[head & (np.abs(ny) <= 0.35)] = 2; cls[head & (ny > 0.35)] = 3
    cls[pid == 1] = 4; cls[pid == 2] = 5; cls[pid == 3] = 6
    img = COL[cls].copy(); img[interior & (cls == 1)] = [170, 60, 90]  # interior seen face-on: dark pink
    Image.fromarray(img.astype(np.uint8)).save(f"{out}_{pose}_id.png"); Image.fromarray(alb.astype(np.uint8)).save(f"{out}_{pose}_alb.png")
    op = interior | (pid >= 1) | (pid < 0) & (np.abs(xs)[None, :] < 0.03)
    # keep the connected opening through the centre column
    from scipy.ndimage import label
    lab, _ = label(op); mid = lab[:, W // 2]; ids = [v for v in np.unique(mid) if v > 0]
    if pose == "neutral" or not ids:
        print(f"{pose}: no opening")
    else:
        sizes = [(lab == v).sum() for v in ids]; o = lab == ids[int(np.argmax(sizes))]
        r = np.where(o.any(1))[0]; c = np.where(o.any(0))[0]; h = len(r); w_ = len(c)
        wid = o.sum(1)
        prof = [wid[r[0] + int(f * (h - 1))] / wid.max() for f in (.15, .5, .85)]
        n = o.sum()
        def sh(m): return (m & o).sum() / n
        print(f"{pose}: opening {n*S*S*1e6:.0f} mm^2, {w_*S*1e3:.1f} x {h*S*1e3:.1f} mm (aspect {w_/h:.2f}), width at 15/50/85% "
              f"{prof[0]:.2f}/{prof[1]:.2f}/{prof[2]:.2f}, fill {n/(h*w_):.2f}")
        print(f"   walls (head edge-on) {sh(cls == 2):.3f}, torn (back faces) {sh(cls == 3):.3f}, holes {sh(pid < 0):.3f}, "
              f"interior face-on {sh(interior & (cls == 1)):.3f}, teeth {sh(pid == 1):.3f}, lower {sh(pid == 2):.3f}, tongue {sh(pid == 3):.3f}")
        for side, sx in (("right(-x)", c[0]), ("left(+x)", c[-1])):
            zc = np.where(o[:, sx])[0].mean(); cz_ = int(zc); R = int(0.006 / S)
            yy, xx = np.ogrid[:H, :W]; disk = ((yy - cz_) ** 2 + (xx - sx) ** 2 < R * R) & o
            print(f"   corner {side}: back {((cls == 3) & disk).sum()/max(disk.sum(),1):.3f}, edge-on {((cls == 2) & disk).sum()/max(disk.sum(),1):.3f}, "
                  f"holes {((pid < 0) & disk).sum()/max(disk.sum(),1):.3f} of {disk.sum()} px")
        tg = (pid == 3) & o
        if tg.any():
            tt = np.where(tg.any(1))[0][0]
            a = alb[tg].mean(0)
            print(f"   tongue top {(tt - r[0]) / h:.2f} of the opening height below its top; albedo sRGB {a.round(0)}")
        else:
            print("   tongue not seen")
        top = np.array([np.where(o[:, i])[0].min() if o[:, i].any() else -1 for i in range(W)]) * S * 1e3
        bot = np.array([np.where(o[:, i])[0].max() if o[:, i].any() else -1 for i in range(W)]) * S * 1e3
        cc = np.arange(c[int(.1 * w_)], c[int(.9 * w_)])
        for nm, e in (("upper", top), ("lower", bot)):
            j = np.abs(e[cc[4:]] - e[cc[:-4]])
            print(f"   {nm} edge: largest jump over 1 mm {j.max():.2f} mm at x {xs[cc[np.argmax(j)]]*1e3:.1f}; 1-mm jumps > 0.5 mm: {(j[::4] > .5).sum()}")
    # seal: the lips band (interior or lips: |x| < 20 mm, within 7 mm of the teeth's tip height)
    band = head & (np.abs(xs)[None, :] < 0.02) & (np.abs(zs - cz)[:, None] < 0.007)
    lum = alb @ [0.2126, 0.7152, 0.0722]
    cols = [lum[band[:, i], i] for i in range(W) if band[:, i].sum() > 10]
    dark = np.array([cc_.min() / np.median(cc_) for cc_ in cols])
    blue = band & (alb[..., 2] > alb[..., 0])
    print(f"   seal band: darkest / median lum per column p10 {np.percentile(dark, 10):.2f} median {np.median(dark):.2f}; "
          f"blue-grey px {blue.sum()} ({blue.sum()*S*S*1e6:.1f} mm^2)")
