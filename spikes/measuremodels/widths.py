"""Face and neck WIDTHS from a front picture: the head's mask (a segmentation model's, or the true one) cut at
heights given by the detector's own points, in units of the pupil distance.

  run.sh widths.py pop            -> MM/widths_pop.npz: 300 random GNM heads: ratios (true mask) and their macros
  run.sh widths.py score <mask source: true | moge2 | david | ...>
  run.sh widths.py garrett <mask source>

Levels (rows of the picture after levelling the eye line), u = distance between the iris centres:
  eye    : at the eyes (head width with ears; hair makes it meaningless)
  sn     : at the base of the nose (the face under the cheekbones, at the ear lobes)
  mouth  : at the mouth corners (the jaw)
  lowjaw : half way from the mouth to the chin's bottom (the lower jaw / chin block)
  neck   : the narrowest row between 0.3 u and 0.9 u under the chin
  + chin_h: mouth line to chin bottom / u; face_h: eye line to chin / u
"""
import json
import sys

import numpy as np
from scipy import ndimage

import mm
import rs

MP = {"irisL": 473, "irisR": 468, "sn": 2, "mouthL": 291, "mouthR": 61, "chin": 152}
LEVELS = ("eye", "sn", "mouth", "lowjaw", "neck")
NAMES = tuple(f"w_{k}" for k in LEVELS) + ("chin_h", "face_h", "taper")
MACROS = ("face_width", "cheekbone_width", "jaw_width", "jaw_square", "chin_width", "chin_height", "neck_width", "face_length", "cheek_fullness", "under_chin")


def measure(mask, P):
    """Ratios from a boolean mask (H, W) and MediaPipe's 478 points P (pixels)."""
    a, b = P[MP["irisR"], :2], P[MP["irisL"], :2]
    u = float(np.linalg.norm(b - a))
    ang = np.arctan2(b[1] - a[1], b[0] - a[0])
    c, s = np.cos(-ang), np.sin(-ang)
    ctr = (a + b) / 2
    rot = lambda p: (np.asarray(p, float) - ctr) @ np.array([[c, s], [-s, c]])  # noqa: E731  levelled, origin between the eyes
    R = np.array([[c, s], [-s, c]])
    y_sn = rot(P[MP["sn"], :2])[1]
    y_m = (rot(P[MP["mouthL"], :2])[1] + rot(P[MP["mouthR"], :2])[1]) / 2
    y_c = rot(P[MP["chin"], :2])[1]
    x_c = rot(P[MP["chin"], :2])[0] * 0.5

    def width(y, x0=0.0):
        xs = np.arange(-3.2 * u, 3.2 * u, 0.5)
        pts = np.stack([xs, np.full(len(xs), y)], 1) @ R.T + ctr       # back to the picture
        v = ndimage.map_coordinates(mask.astype(float), [pts[:, 1] - 0.5, pts[:, 0] - 0.5], order=1, mode="constant") > 0.5
        i0 = int(np.argmin(np.abs(xs - x0)))
        if not v[i0]:
            return np.nan
        lo = i0
        while lo > 0 and v[lo - 1]:
            lo -= 1
        hi = i0
        while hi < len(v) - 1 and v[hi + 1]:
            hi += 1
        return (xs[hi] - xs[lo] + 0.5) / u

    out = {"w_eye": width(0.0), "w_sn": width(y_sn), "w_mouth": width(y_m), "w_lowjaw": width((y_m + y_c) / 2, x_c)}
    ws = [width(y_c + t * u, x_c) for t in np.linspace(0.3, 0.9, 13)]
    out["w_neck"] = float(np.nanmin(ws)) if np.isfinite(ws).any() else np.nan
    out["chin_h"] = (y_c - y_m) / u
    out["face_h"] = y_c / u
    out["taper"] = out["w_lowjaw"] / out["w_sn"]
    return out


def mp_true(V, cam, tab):
    """Where the detector WOULD put its points on a head (the calibrated front table), for the population run."""
    g = rs.gnm()
    X = (V[tab["vid"][0]] * tab["w"][0][..., None]).sum(1)
    return rs.humanfit.project(cam, X)


def population(n=300):
    from hifipushie import humanmacro as hm
    import fits
    tab = fits.table("skin")
    rng = np.random.default_rng(3)
    R, Z = [], []
    for i in range(n):
        c = np.random.default_rng(20000 + i).normal(0, 1.0, rs.K_TRUE)
        V = rs.head(c)
        cam = rs.make_cam(V, yaw=rng.normal(0, 3), pitch=rng.normal(0, 4), roll=rng.normal(0, 2), lens=float(rng.choice([35, 50, 70, 85, 105])),
                          fill=rng.uniform(0.5, 0.66), size=(512, 512))
        _, zb = rs.render(V, cam)
        m = measure(np.isfinite(zb), mp_true(V, cam, tab))
        z = hm.read(V=V)
        R.append([m[k] for k in NAMES])
        Z.append([z[k] for k in MACROS])
        if i % 50 == 0:
            print(i, flush=True)
    R, Z = np.array(R), np.array(Z)
    np.savez(mm.MM / "widths_pop.npz", R=R, Z=Z)
    report_pop(R, Z)


def model(R, Z):
    """Linear read of each macro (sigmas) from the ratios: (coef (macros, ratios+1), r2, resid sd), on the population."""
    ok = np.isfinite(R).all(1)
    X = np.c_[(R[ok] - R[ok].mean(0)) / R[ok].std(0), np.ones(ok.sum())]
    co, r2, sd = [], [], []
    for j in range(Z.shape[1]):
        b = np.linalg.lstsq(X, Z[ok, j], rcond=None)[0]
        res = Z[ok, j] - X @ b
        co.append(b)
        r2.append(1 - res.var() / Z[ok, j].var())
        sd.append(res.std())
    return {"mu": R[ok].mean(0), "sd": R[ok].std(0), "coef": np.array(co), "r2": np.array(r2), "resid": np.array(sd)}


def report_pop(R, Z):
    ok = np.isfinite(R).all(1)
    print(f"population: {ok.sum()} heads. ratio mean +- sd:")
    for i, k in enumerate(NAMES):
        print(f"  {k:9s} {R[ok, i].mean():6.3f} +- {R[ok, i].std():5.3f}  ({100 * R[ok, i].std() / R[ok, i].mean():4.1f}%)")
    m = model(R, Z)
    print("macro read from the ratios (true mask, any lens 35-105): r2, sd left (sigmas); single best ratio")
    for j, k in enumerate(MACROS):
        cc = [abs(np.corrcoef(R[ok, i], Z[ok, j])[0, 1]) for i in range(len(NAMES))]
        print(f"  {k:16s} r2 {m['r2'][j]:5.2f}  left {m['resid'][j]:4.2f}   best {NAMES[int(np.argmax(cc))]} r {max(cc):.2f}")


def mask_of(src, iid):
    if src == "true":
        it = mm.item(iid)
        return np.isfinite(it["zb"]) | it["hair"]
    p = mm.pred(src, iid)
    if p is None or "mask" not in p:
        return None
    return p["mask"].squeeze() > 0.5


def read_macros(m, mdl):
    r = np.array([m[k] for k in NAMES])
    x = np.r_[(r - mdl["mu"]) / mdl["sd"], 1.0]
    return {k: (float(mdl["coef"][j] @ x), float(mdl["resid"][j])) for j, k in enumerate(MACROS)}


def score(src):
    import fits
    from hifipushie import humanmacro as hm
    import subjects
    z = np.load(mm.MM / "widths_pop.npz")
    mdl = model(z["R"], z["Z"])
    rows = []
    for iid in mm.ids(view="front"):
        d = fits.det(iid)
        mk = mask_of(src, iid)
        if d is None or mk is None:
            continue
        it = mm.item(iid)
        mt = measure(np.isfinite(it["zb"]), d["P"])      # the true head's own mask (no hair), same levels
        me = measure(mk, d["P"])
        sub = it["subject"]
        Vn = subjects.load(sub)["V"] if not sub.startswith("C") else it["V"]
        zt = hm.read(V=Vn)
        rows.append((iid, mt, me, zt, read_macros(me, mdl), bool(it["look"]["hair"])))
    print(f"\nwidths from the '{src}' mask on {len(rows)} skinned front pictures (truth + calibration heads), units of pupil distance")
    print(f"{'ratio':9s} | {'err % rms':>9s} {'bias %':>7s} | {'corr with the true mask':>24s}   (hair pictures left out of w_eye)")
    for k in NAMES:
        a = np.array([[r[1][k], r[2][k]] for r in rows if not (k == "w_eye" and r[5])])
        a = a[np.isfinite(a).all(1)]
        e = (a[:, 1] - a[:, 0]) / a[:, 0] * 100
        print(f"{k:9s} | {np.sqrt((e ** 2).mean()):9.2f} {e.mean():7.2f} | {np.corrcoef(a[:, 0], a[:, 1])[0, 1]:24.2f}")
    print(f"\nmacros read from those ratios vs the head's true macros (sigmas), {len(rows)} heads")
    print(f"{'macro':16s} | {'err rms':>7s} {'(saying 0: rms)':>15s} | {'corr':>5s} | {'pop r2':>6s}")
    out = {}
    for j, k in enumerate(MACROS):
        a = np.array([[r[3][k], r[4][k][0]] for r in rows])
        a = a[np.isfinite(a).all(1)]
        cc = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
        er = float(np.sqrt(((a[:, 1] - a[:, 0]) ** 2).mean()))
        print(f"{k:16s} | {er:7.2f} {np.sqrt((a[:, 0] ** 2).mean()):15.2f} | {cc:5.2f} | {mdl['r2'][j]:6.2f}")
        out[k] = {"err": er, "corr": cc, "zero": float(np.sqrt((a[:, 0] ** 2).mean()))}
    (mm.MM / "out" / f"widths_{src}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "pop":
        population()
    elif sys.argv[1] == "score":
        score(sys.argv[2])


def garrett(src="moge2"):
    """Garrett's front reference: ratios, their place in GNM's population, the macros they read."""
    from PIL import Image, ImageDraw
    z = np.load(mm.MM / "widths_pop.npz")
    mdl = model(z["R"], z["Z"])
    im = np.asarray(Image.open(mm.MM / "img" / "garrett_front.png").convert("RGB"))
    d = rs.detect([im])[0]
    mk = np.load(mm.PRED / src / "garrett_front.npz")["mask"].squeeze() > 0.5
    m = measure(mk, d["P"])
    print("Garrett front (mask: %s): ratio, population mean +- sd, z" % src)
    for i, k in enumerate(NAMES):
        print(f"  {k:9s} {m[k]:6.3f}   {mdl['mu'][i]:6.3f} +- {mdl['sd'][i]:5.3f}   z {(m[k] - mdl['mu'][i]) / mdl['sd'][i]:+5.2f}")
    use = [i for i, k in enumerate(NAMES) if k not in ("w_eye", "w_neck")]   # hair and a collar hide those two on him
    m2 = model(z["R"][:, use], z["Z"])
    x = np.r_[(np.array([m[NAMES[i]] for i in use]) - m2["mu"]) / m2["sd"], 1.0]
    print("macros read WITHOUT w_eye (hair) and w_neck (collar) (sigmas, +- what the ratios leave open; r2 in the population):")
    for j, k in enumerate(MACROS):
        print(f"  {k:16s} {m2['coef'][j] @ x:+5.2f} +- {m2['resid'][j]:4.2f}   r2 {m2['r2'][j]:.2f}")
    o = Image.fromarray(np.where(mk[..., None], im, (im * 0.35).astype(np.uint8)))
    dr = ImageDraw.Draw(o)
    for k in MP.values():
        x, y = d["P"][k, :2]
        dr.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(255, 255, 0))
    o.save(mm.MM / "out" / f"garrett_widths_{src}.png")


if __name__ == "__main__" and sys.argv[1] == "garrett":
    garrett(*sys.argv[2:])
