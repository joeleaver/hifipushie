"""skincheck.py <render dir> <checklist.json> [--pairs <pairs dir>]: the SKIN checklist (docs/notes/gates.md: MEASURE)
on a cu.py render set at the photo cameras: face_v0(_ref), face_v1(_ref) [face_v2], eyes_v0, eyesR_v0 (+ _pose), mouth_v0.
Every item measured on the reference and on ours in the same box (MediaPipe landmarks of the reference crop; our own
landmarks where an item is ours' shape, e.g. brow length), printed as item | reference | ours | tol | pass, written to
<render dir>/skincheck.json and .md. With --pairs: reference | result crops per review region into <pairs dir> and the
`review` arguments (pairs.txt). LIGHT.

The checklist file holds per item {tol, seen: true | false (inferred: the photo can't show it), note}; values come from
the pictures each run (the reference is the photo crop at the photo camera, so lighting is the photo's own: tone items
are compared as Lab under that light, ours rendered under the fitted light made white)."""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import likeness, skin_project as sp

d = sys.argv[1]
ck = json.load(open(sys.argv[2]))
pairs = sys.argv[sys.argv.index("--pairs") + 1] if "--pairs" in sys.argv else None


def img(f):
    p = f"{d}/{f}.png"
    return Image.open(p).convert("RGB") if os.path.exists(p) else None


def lab_box(im, box):
    a = np.asarray(im.crop(tuple(int(round(x)) for x in box)), float) / 255.0
    return sp.lab(np.median(sp._lin(a.reshape(-1, 3)), 0)[None])[0]


def hp_rms(im, box):   # fine texture: rms of log luminance minus its 3-px blur, in the box
    from scipy import ndimage
    a = np.asarray(im.convert("L").crop(tuple(int(round(x)) for x in box)), float) + 1
    L = np.log(a)
    return float(np.sqrt(np.mean((L - ndimage.gaussian_filter(L, 3)) ** 2)))


def bbox(P, ids, pad=0.0, dx=0.0, dy=0.0, w=None, h=None):
    q = P[list(ids)]
    lo, hi = q.min(0), q.max(0)
    c = (lo + hi) / 2 + [dx, dy]
    half = np.array([(w or (hi - lo)[0]) / 2, (h or (hi - lo)[1]) / 2]) * (1 + pad)
    return [c[0] - half[0], c[1] - half[1], c[0] + half[0], c[1] + half[1]]


R, O = img("face_v0_ref"), img("face_v0")
PR = np.asarray(likeness.detect([R])[0], float)[:, :2]
PO_ = likeness.detect([O])[0]
PO = np.asarray(PO_, float)[:, :2] if PO_ is not None else PR
iod = float(np.linalg.norm(PR[33] - PR[263]))       # outer canthi: the face's own unit
u = iod / 60.0                                        # ~1 mm (an outer-canthus distance ~ 60 mm... a scale, not a ruler)
B = {"forehead": bbox(PR, (9, 107, 336), w=24 * u, h=10 * u, dy=-8 * u),
     "cheek_R": bbox(PR, (116, 123, 147, 50), w=14 * u, h=14 * u), "cheek_L": bbox(PR, (345, 352, 376, 280), w=14 * u, h=14 * u),
     "nose": bbox(PR, (4, 5, 195), w=8 * u, h=8 * u), "chin": bbox(PR, (152, 175, 199), w=14 * u, h=8 * u, dy=-4 * u),
     "under_eye_R": bbox(PR, (230, 229, 228), w=12 * u, h=4 * u, dy=4 * u), "under_eye_L": bbox(PR, (450, 449, 448), w=12 * u, h=4 * u, dy=4 * u),
     "lip_upper": bbox(PR, (0, 37, 267), w=12 * u, h=3 * u, dy=1.5 * u), "lip_lower": bbox(PR, (17, 84, 314), w=12 * u, h=3 * u, dy=-2 * u),
     "brow_R": bbox(PR, (105, 66, 107, 52, 65), pad=0.1), "brow_L": bbox(PR, (334, 296, 336, 282, 295), pad=0.1)}
rows = []


def add(name, ref, ours, tol, kind, fmt="{:.2f}"):
    if ref is None or ours is None:
        rows.append({"item": name, "ref": None, "ours": None, "pass": None, "tol": tol, "seen": ck.get(name, {}).get("seen", True)})
        return
    if kind == "dE":
        diff = float(np.linalg.norm(np.asarray(ref) - np.asarray(ours)))
    elif kind == "ratio":
        diff = abs(np.log(max(ours, 1e-6) / max(ref, 1e-6)))
    else:
        diff = abs(float(ours) - float(ref))
    t = float(ck.get(name, {}).get("tol", tol))
    show = (lambda v: "[" + ", ".join(f"{x:.1f}" for x in v) + "]") if kind == "dE" else (lambda v: fmt.format(v))
    rows.append({"item": name, "ref": show(ref), "ours": show(ours), "diff": round(diff, 3), "tol": t, "pass": bool(diff <= t),
                 "seen": ck.get(name, {}).get("seen", True)})


for k in ("forehead", "cheek_R", "cheek_L", "nose", "chin"):
    add(f"tone {k} (Lab)", lab_box(R, B[k]), lab_box(O, B[k]), 6.0, "dE")
# redness distribution: cheek a* over forehead a*, and the cheek box's a* spread (a broad warmth vs round patches)
for k in ("cheek_R", "cheek_L"):
    add(f"redness {k} - forehead (a*)", lab_box(R, B[k])[1] - lab_box(R, B["forehead"])[1], lab_box(O, B[k])[1] - lab_box(O, B["forehead"])[1], 3.0, "abs")
for k in ("under_eye_R", "under_eye_L"):
    side = "R" if k.endswith("R") else "L"
    add(f"under-eye / cheek {side} (L ratio)", lab_box(R, B[k])[0] / lab_box(R, B["cheek_" + side])[0], lab_box(O, B[k])[0] / lab_box(O, B["cheek_" + side])[0], 0.05, "abs")
add("lips upper (Lab)", lab_box(R, B["lip_upper"]), lab_box(O, B["lip_upper"]), 7.0, "dE")
add("lips lower (Lab)", lab_box(R, B["lip_lower"]), lab_box(O, B["lip_lower"]), 7.0, "dE")
add("texture cheek R (fine rms)", hp_rms(R, B["cheek_R"]), hp_rms(O, B["cheek_R"]), 0.5, "ratio", "{:.4f}")
add("texture forehead (fine rms)", hp_rms(R, B["forehead"]), hp_rms(O, B["forehead"]), 0.5, "ratio", "{:.4f}")
for k, ids in (("brow_R", (70, 46)), ("brow_L", (300, 276))):
    add(f"{k} darkness (L)", lab_box(R, B[k])[0], lab_box(O, B[k])[0], 8.0, "abs", "{:.1f}")
    lr = float(np.linalg.norm(PR[ids[0]] - PR[107 if k == 'brow_R' else 336])) / iod
    lo = float(np.linalg.norm(PO[ids[0]] - PO[107 if k == 'brow_R' else 336])) / iod
    add(f"{k} length (/ outer-canthus width)", lr, lo, 0.05, "abs", "{:.3f}")
# eyes: from the eye close-ups (eyecmp's reader: crease height / darkness), iris colour, sclera, catchlight
ec = json.load(open(f"{d}/eyecmp.json")) if os.path.exists(f"{d}/eyecmp.json") else None
if ec:
    r_ = list(ec.values())[0]
    for e, nm in ((0, "R"), (1, "L")):
        ph, ou = r_["photo"][e], r_["ours"][e]
        mid = lambda col: col[1]["tps"]  # noqa: E731
        add(f"crease height mid {nm} (mm)", mid(ph), mid(ou), 0.8, "abs")
        add(f"crease darkness mid {nm}", ph[1]["dark"], ou[1]["dark"], 0.12, "abs", "{:.3f}")
for f, nm, ids in (("face_v0", "R", (468, 469, 470, 471, 472)), ("face_v0", "L", (473, 474, 475, 476, 477))):
    # (on the face at the photo camera: MediaPipe does not find a face in an eye close-up)
    ri, oi, Pr = R, O, PR
    c, rad = Pr[ids[0]], float(np.mean(np.linalg.norm(Pr[list(ids[1:])] - Pr[ids[0]], axis=1)))
    ib = [c[0] - 0.6 * rad, c[1] - 0.6 * rad, c[0] + 0.6 * rad, c[1] + 0.6 * rad]
    add(f"iris {nm} (Lab)", lab_box(ri, ib), lab_box(oi, ib), 10.0, "dE")
    def cl(im):
        a = np.asarray(im.convert("L").crop(tuple(int(x) for x in ib)), float)
        return float(a.max() - np.percentile(a, 50))
    add(f"catchlight {nm} (peak - median)", cl(ri), cl(oi), 60.0, "abs", "{:.0f}")
    corner = Pr[33] if nm == "R" else Pr[263]
    sb = [min(c[0], corner[0]) + 0.3 * abs(corner[0] - c[0]), c[1] - 0.25 * rad, max(c[0], corner[0]) - 0.3 * abs(corner[0] - c[0]), c[1] + 0.25 * rad]
    add(f"sclera {nm} (L)", lab_box(ri, sb)[0], lab_box(oi, sb)[0], 10.0, "abs", "{:.1f}")
ok = [r for r in rows if r["pass"] is not None]
md = ["| item | reference | ours | diff | tol | pass | seen |", "|---|---|---|---|---|---|---|"]
for r in rows:
    md.append(f"| {r['item']} | {r['ref']} | {r['ours']} | {r.get('diff', '')} | {r['tol']} | {'PASS' if r['pass'] else ('FAIL' if r['pass'] is False else 'n/a')} | {'seen' if r['seen'] else 'inferred'} |")
md.append(f"\n{sum(r['pass'] for r in ok)} / {len(ok)} measured items pass")
open(f"{d}/skincheck.md", "w").write("\n".join(md))
json.dump(rows, open(f"{d}/skincheck.json", "w"), indent=1)
print("\n".join(md))

if pairs:   # the review's crops: one pair a checklist region, same framing both sides
    os.makedirs(pairs, exist_ok=True)
    args = []

    def pair(name, ri, oi, box=None):
        if ri is None or oi is None:
            return
        if box is not None:
            box = tuple(int(round(x)) for x in box)
            ri, oi = ri.crop(box), oi.crop(box)
        a, b = f"{pairs}/{len(args):02d}_ref.png", f"{pairs}/{len(args):02d}_res.png"
        ri.save(a); oi.save(b)
        args.append(f"{name}={a}:{b}")
    pair("full face, front", R, O)
    pair("full face, second view", img("face_v1_ref"), img("face_v1"))
    if img("face_v2") is not None:
        pair("full face, third view", img("face_v2_ref"), img("face_v2"))
    pair("right eye (image left), open", img("eyesR_v0_ref"), img("eyesR_v0"))
    pair("left eye (image right), open", img("eyes_v0_ref"), img("eyes_v0"))
    pair("right eye, closed (reference shows it open)", img("eyesR_v0_ref"), img("eyesR_v0_pose"))
    pair("left eye, closed (reference shows it open)", img("eyes_v0_ref"), img("eyes_v0_pose"))
    pair("lips", img("mouth_v0_ref"), img("mouth_v0"))
    pair("nose and nostrils", R, O, bbox(PR, (6, 2, 98, 327, 64, 294), pad=0.35))
    if img("cheek_v0") is not None:   # the cheek close-up at the photo camera (surface texture needs the pixels)
        pair("cheek, close-up", img("cheek_v0_ref"), img("cheek_v0"))
    pair("right cheek (image left)", R, O, bbox(PR, (116, 123, 147, 50, 205, 187), pad=0.5))
    pair("left cheek (image right)", R, O, bbox(PR, (345, 352, 376, 280, 425, 411), pad=0.5))
    pair("forehead and brows", R, O, bbox(PR, (70, 300, 10, 151, 9), pad=0.2))
    pair("jaw and neck join", R, O, [PR[:, 0].min() - 10 * u, PR[152, 1] - 25 * u, PR[:, 0].max() + 10 * u, min(R.height, PR[152, 1] + 25 * u)])
    open(f"{pairs}/pairs.txt", "w").write("\n".join(args))
    print("pairs ->", pairs, len(args))
