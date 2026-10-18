"""eyealb.py <glb> [out.png]: the export's baked albedo round the eyes. Sclera = eye-mesh faces facing front (n.y < -0.3),
6.5-11 mm off each eyeball's front axis: mean sRGB, CIELAB L a* b*, luminance CoV (blotchiness) and CoV after a 1 mm
blur (the coarse blotches). Socket = head faces 6-14 mm above the eye centre within 14 mm across (the lid / brow hollow),
lower lid = 3-9 mm below; each against the cheek (22-30 mm below): Lab differences (orange-brown = b* up, L down)."""
import sys, numpy as np
from PIL import Image
import mouthhits as mh
g, _, _ = mh.load(sys.argv[1]); uv_of = mh.uv_of


def seen_front(P, tris):
    """Points not covered from the front (a ray toward -y from each hits none of tris): the lids hide part of the
    eye mesh's front-facing faces; the sclera measure keeps only what a front view shows."""
    d = np.array([0.0, -1.0, 0.0]); e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    q_ = np.cross(d, e2); det = (e1 * q_).sum(1); ok = np.abs(det) > 1e-14
    out = np.ones(len(P), bool)
    for i, o in enumerate(P):
        s_ = o - tris[:, 0]; u = (s_ * q_).sum(1) / det; qq = np.cross(s_, e1); v = (qq @ d) / det; t = (qq * e2).sum(1) / det
        out[i] = not ((u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-5) & ok).any()
    return out
def lab(c):
    c = np.asarray(c, float) / 255; l = np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)
    M = np.array([[.4124, .3576, .1805], [.2126, .7152, .0722], [.0193, .1192, .9505]]); xyz = l @ M.T / [.9505, 1, 1.089]
    f = np.where(xyz > .008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)
def samples(part, faces, k=6):
    uv, tex = uv_of(part); m = g["meshes"][part]
    import os
    if os.environ.get("TEX"): tex = np.asarray(Image.open(os.environ["TEX"]).convert("RGB"))
    th, tw = tex.shape[:2]
    a, b = np.meshgrid(np.linspace(0, 1, k), np.linspace(0, 1, k)); ok = a + b <= 1; a, b = a[ok], b[ok]
    q = uv[m["F"][faces]]; P = m["V"][m["F"][faces]]
    c = q[:, None, 0] * (1 - a - b)[None, :, None] + q[:, None, 1] * a[None, :, None] + q[:, None, 2] * b[None, :, None]
    p = P[:, None, 0] * (1 - a - b)[None, :, None] + P[:, None, 1] * a[None, :, None] + P[:, None, 2] * b[None, :, None]
    return tex[np.clip((c[..., 1] * th).astype(int), 0, th - 1), np.clip((c[..., 0] * tw).astype(int), 0, tw - 1)].reshape(-1, 3).astype(float), p.reshape(-1, 3)
E = g["meshes"]["eyes"]; Hh = g["meshes"]["head"]
for side, sg in (("left(+x)", 1), ("right(-x)", -1)):
    ev = E["V"][E["V"][:, 0] * sg > 0]; c0 = np.array([np.median(ev[:, 0]), ev[:, 1].min() + 0.012, np.median(ev[:, 2])])
    T = E["V"][E["F"]]; n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    C = T.mean(1); lat = np.hypot(C[:, 0] - c0[0], C[:, 2] - c0[2])
    f = np.where((C[:, 0] * sg > 0) & (n[:, 1] < -0.3) & (lat > .0065) & (lat < .011))[0]
    s, P = samples("eyes", f)
    TH0 = Hh["V"][Hh["F"]]; near = (np.abs(TH0.mean(1)[:, 0] - c0[0]) < .02) & (np.abs(TH0.mean(1)[:, 2] - c0[2]) < .02)
    vis = seen_front(P, TH0[near]); n_all = len(s); s = s[vis]; L = s @ [.2126, .7152, .0722]
    print(f"{side} sclera seen from the front: {vis.sum()} of {n_all} samples")
    from scipy.ndimage import uniform_filter1d
    print(f"{side} sclera: {len(f)} faces, sRGB {s.mean(0).round()}, Lab {lab(s.mean(0)).round(1)}, lum CoV {L.std()/L.mean():.3f}, "
          f"lum p5/p95 {np.percentile(L,5):.0f}/{np.percentile(L,95):.0f}")
    TH = Hh["V"][Hh["F"]]; CH = TH.mean(1); nh = np.cross(TH[:, 1] - TH[:, 0], TH[:, 2] - TH[:, 0])
    fr = nh[:, 1] < 0; dx = np.abs(CH[:, 0] - c0[0]); dz = CH[:, 2] - c0[2]
    reg = {"socket (6-14 mm above)": fr & (dx < .014) & (dz > .006) & (dz < .014),
           "lower lid (3-9 mm below)": fr & (dx < .012) & (dz < -.003) & (dz > -.009),
           "cheek (22-30 mm below)": fr & (dx < .014) & (dz < -.022) & (dz > -.030)}
    ref = None
    for nm, m_ in list(reg.items())[::-1]:
        s, _ = samples("head", np.where(m_)[0]); lb = lab(s).mean(0)
        if ref is None: ref = lb
        print(f"   {nm}: sRGB {s.mean(0).round()} Lab {lb.round(1)}  vs cheek dL {lb[0]-ref[0]:+.1f} da {lb[1]-ref[1]:+.1f} db {lb[2]-ref[2]:+.1f}")
