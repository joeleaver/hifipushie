"""eyesolve.py <dressed model> <out model> <fold json> [iters=3]: the EYE stage after the identity solve (the identity
fixed but for its eye-opening direction). Variables: the lid POSE (base.head.pose lid_upper / lid_lower, m: an
expression, both eyes), lidfold's crease_height and fold_overhang (mm, base.head.fold), and eye_opening as a coupled
attribute (faceatlas lid_aperture's within-sex direction, in sds). Measured on the dressed front close-up through
the photo's fitted camera, photo and render through the SAME detector (its bias on lids cancels), per eye averaged:
  opening   the aperture's height at the middle (lm 159-145 / 386-374, mm);
  lash      the upper lid's middle over the iris centre (mm; Tess: her lash line crosses our iris top);
  crease    lidfold.read_lid's TPS in the middle third (the visible crease over the lash line, mm).
Gauss-Newton by finite differences (one render per evaluation), an L2 pull toward the start per variable
(PRIOR), the eye_crease_* / eye_platform sliders dropped (lidfold owns the crease: two would render). The model's
part-ID aperture (aperture.from_mask) is printed alongside as a check. Writes <out model>, $F/out/eyes_<out>.png."""
import copy
import json
import os
import sys

import numpy as np
from PIL import Image

import stage
from hifipushie import aperture, faceatlas, humanfit, lidfold, likeness, store

F = "/mnt/data/hifipushie/facesliders"
src, out, fold0 = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
ITERS = int(sys.argv[4]) if len(sys.argv) > 4 else 3
SIZE = 900
UP = 2
VARS = ["lid_upper", "lid_lower", "crease_height", "fold_overhang", "eye_opening"]
STEP = np.array([0.0004, 0.0004, 0.4, 0.2, 0.3])
PRIOR = np.array([0.002, 0.002, 2.0, 1.0, 1.0])   # the pull toward the start: one unit costs as much as one tolerance
TOL = np.array([0.35, 0.35, 0.5])                   # opening, lash, crease (mm)
DROP = ("eye_crease_height", "eye_crease_depth", "eye_platform")
# eyedetail: the crease rides the opening's rim, so solve the lid (and the opening) FIRST against opening and lash,
# then the crease against TPS; fold_overhang barely moves TPS (shading above the line): held
STAGE = os.environ.get("STAGE", "A")
ACTIVE = [0, 1, 4] if STAGE == "A" else [2]
MEAS = np.array([True, True, False]) if STAGE == "A" else np.array([False, False, True])

sp0 = json.loads((store.HOME / src / "spec.json").read_text())
sp0 = sp0.get("spec", sp0)
refs = json.loads((store.HOME / src / "human_refs.json").read_text())
v, cam = refs["views"][0], refs["cameras"][0]
st0 = humanfit.state(sp0["base"])
L = st0["L"]
eyes_px = humanfit.project(cam, L[36:48])
lo, hi = eyes_px.min(0), eyes_px.max(0)
c = 0.5 * (lo + hi)
s = 1.7 * (hi - lo)[0]
box = [c[0] - s / 2, c[1] - s / 2 + 0.05 * s, c[0] + s / 2, c[1] + s / 2 + 0.05 * s]
fr = stage.fitted_frame(cam, box, "eyes")
dist = float(np.linalg.norm(0.5 * (L[68] + L[69]) - np.asarray(fr["eye"])))
MMPX = 2 * dist * np.tan(np.radians(fr["fov"]) / 2) * 1000 / SIZE
t_ = faceatlas.table()
SD_AP = float(t_["sd"][t_["index"]["lid_aperture"]])
DIR_AP = faceatlas.direction({"lid_aperture": SD_AP})
c_id0 = humanfit.identity(sp0["base"])


def measures(img):
    big = img.resize((img.width * UP, img.height * UP), Image.LANCZOS)
    d = likeness.detect([big])[0]
    if d is None:
        return None
    P = np.asarray(d, float)[:, :2] / UP
    side = likeness.Side(P, None, "detector")
    ex, ey = side.frame()
    op = np.mean([abs((P[a] - P[b]) @ ey) for a, b in ((159, 145), (386, 374))]) * MMPX
    lash = np.mean([((P[c_] - P[a]) @ ey) for a, c_ in ((159, 468), (386, 473))]) * MMPX   # + = lid above the iris centre
    lid = lidfold.read_lid(img, P, MMPX)
    tps = [col["tps"] for eye in lid for col in eye[1:2] if np.isfinite(col["tps"])]
    return np.array([op, lash, float(np.mean(tps)) if tps else np.nan])


def spec_of(x):
    sp = copy.deepcopy(sp0)
    if x is None:   # the start model as it is (the sheet's "current")
        return sp
    h = sp["base"]["head"]
    h["pose"] = {**(h.get("pose") or {}), "lid_upper": round(float(x[0]), 6), "lid_lower": round(float(x[1]), 6)}
    h["fold"] = {**fold0, "crease_height": round(float(x[2]), 3), "fold_overhang": round(float(x[3]), 3)}
    h["sliders"] = {k: v_ for k, v_ in (h.get("sliders") or {}).items() if k not in DROP}
    sp["base"] = humanfit._with_identity(sp["base"], c_id0 + float(x[4]) * DIR_AP)
    return sp


N = [0, None]
PID = os.environ.get("PID", "1") == "1"   # the model's opening / lash by part ID (the photo's by the detector, its
# bias on our renders calibrated once at the start: detector on the dressed start render minus its part ID)


def pid(name, x):
    """The model's opening by PART ID (aperture.mask: the eyeball's visible pixels, lashes hidden, no paint): per
    eye at the column through its centre, the opening's height and its top over the eye's centre (mm), averaged.
    Deterministic, unlike the detector on a dressed render (its lid points moved 0.3-1 mm with every step)."""
    from hifipushie import scene as scenemod
    sp = spec_of(x)
    st = humanfit.state(sp["base"])
    blend = str(scenemod.blend_path(stage.ensure(name, with_hair=False)))
    m = aperture.mask(blend, fr, SIZE, "eyes", hide=("lashes", "hair"))
    U = []
    import numpy as _np
    # the frame's pixels: the same crop as the photo's (box), SIZE px
    k = SIZE / (box[2] - box[0])
    ops, tops = [], []
    for e in (68, 69):
        u, v_ = (humanfit.project(cam, st["L"][e][None])[0] - [box[0], box[1]]) * k
        col = m[:, int(round(u)) - 2:int(round(u)) + 3].any(1)
        rows = _np.flatnonzero(col)
        if not len(rows):
            return _np.array([_np.nan, _np.nan])
        ops.append((rows.max() - rows.min() + 1) * MMPX)
        tops.append((v_ - rows.min()) * MMPX)
    return _np.array([float(_np.mean(ops)), float(_np.mean(tops))])


def render(x, keep=None):
    N[0] += 1
    name = keep or f"fs_e_{out}_{N[0] % 3}"
    d = store.HOME / name
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(spec_of(x), indent=1))
    (d / "human_refs.json").write_text(json.dumps(refs, indent=1))
    for f in (store.HOME / src).glob("hair_scalp_*.npz"):
        (d / f.name).write_bytes(f.read_bytes())
    im = stage.shoot(name, [fr], json.load(open(os.environ["LIGHT"])), size=SIZE, hair_on=False)["eyes"]
    if PID:
        N[1] = pid(name, x)
    return im.convert("RGB"), name


photo = Image.open(v["image"]).convert("RGB").crop(tuple(int(round(q)) for q in box)).resize((SIZE, SIZE), Image.LANCZOS)
mp = measures(photo)
print("photo: opening %.2f, lash over iris %.2f, crease TPS %.2f mm" % tuple(mp))
h0 = sp0["base"]["head"]
x0 = np.array([float((h0.get("pose") or {}).get("lid_upper", 0.0)), float((h0.get("pose") or {}).get("lid_lower", 0.0)),
               float(fold0.get("crease_height", 4.0)), float(fold0.get("fold_overhang", 0.4)), 0.0])
if os.environ.get("X0"):
    x0 = np.array(json.loads(os.environ["X0"]), float)
x = x0.copy()
hist = []
BIAS = np.zeros(3)


def model_measures(im):
    m = measures(im)
    if PID and m is not None and N[1] is not None:
        m = m.copy()
        m[:2] = N[1]
    return m


for it in range(ITERS + 1):
    im, nm = render(x)
    m = model_measures(im)
    if it == 0 and PID:   # the detector's bias on our render, onto the photo's targets
        md = measures(im)
        BIAS[:2] = md[:2] - m[:2]
        mp = mp - BIAS
        print(f"detector - part ID on our start render: opening {BIAS[0]:+.2f}, lash {BIAS[1]:+.2f} mm; photo targets "
              f"now {mp[0]:.2f}, {mp[1]:.2f}")
    hist.append((x.copy(), m, im))
    print(f"iter {it}: x {dict(zip(VARS, np.round(x, 4)))} -> opening {m[0]:.2f}, lash {m[1]:.2f}, crease {m[2]:.2f} "
          f"(photo {mp[0]:.2f}, {mp[1]:.2f}, {mp[2]:.2f})", flush=True)
    if it == ITERS:
        break
    J = np.zeros((3, len(x)))
    for k in ACTIVE:
        xk = x.copy()
        xk[k] += STEP[k]
        mk = model_measures(render(xk)[0])
        J[:, k] = (mk - m) / STEP[k]
    ok = np.isfinite(mp) & np.isfinite(m) & np.isfinite(J[:, ACTIVE]).all(1) & MEAS
    W = 1.0 / TOL[ok]
    Ja = J[ok][:, ACTIVE]
    A = np.r_[Ja * W[:, None], np.diag(1.0 / PRIOR[ACTIVE])]
    r = np.r_[(mp[ok] - m[ok]) * W, -(x - x0)[ACTIVE] / PRIOR[ACTIVE]]
    dx = np.linalg.lstsq(A, r, rcond=None)[0]
    x[ACTIVE] = x[ACTIVE] + dx
    print("  J rows (per unit):", np.round(J, 2).tolist())
def cost(m):
    ok = np.isfinite(mp) & np.isfinite(m) & MEAS
    return float(np.sum(((mp[ok] - m[ok]) / TOL[ok]) ** 2))


best = min(hist, key=lambda h: cost(h[1]))   # (the measures are noisy: the best iterate, not the last)
cur_im = render(None)[0]
im, nm = render(best[0], keep=out)
# the model's own opening by part ID (lashes hidden), the check
try:
    blend = str(__import__("hifipushie").scene.blend_path(stage.ensure(out, with_hair=False)))
    ap = aperture.measure(blend, fr, [L[68].tolist(), L[69].tolist()], size=SIZE)
    print("part-ID aperture (model):", ap)
except Exception as e:  # noqa: BLE001
    print("part-ID aperture: not measured:", e)
S = Image.new("RGB", (3 * SIZE // 2, SIZE // 2))
S.paste(photo.resize((SIZE // 2, SIZE // 2)), (0, 0))
S.paste(cur_im.resize((SIZE // 2, SIZE // 2)), (SIZE // 2, 0))
S.paste(im.resize((SIZE // 2, SIZE // 2)), (SIZE, 0))
S.save(f"{F}/out/eyes_{out}.png")
json.dump({"vars": VARS, "x0": x0.tolist(), "x": best[0].tolist(), "photo": mp.tolist(), "start": hist[0][1].tolist(),
           "end": best[1].tolist()}, open(store.HOME / out / "eye_report.json", "w"), indent=1)
print("wrote", out, f"{F}/out/eyes_{out}.png")
