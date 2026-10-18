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


from eyetone import EYE, eye_tone  # noqa: E402  (the lid / sclera / iris / reference-skin bands: spikes/projskin/eyetone.py)


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
# skin sheen (r4: every head's review "matte, no specular on the nose / forehead"; no row measured it): the highlight's
# lift over the box's own median, L p99 - L p50, on the front face (a matte surface stays within a few L)
def sheen(im, box):
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    a = (np.asarray(im, float) / 255.0)[max(y0, 0):y1, max(x0, 0):x1].reshape(-1, 3)
    l = sp.lab(sp._lin(a))[:, 0] if len(a) else np.zeros(0)
    return float(np.percentile(l, 99) - np.percentile(l, 50)) if len(l) > 20 else None
# + the lower lip's gloss (r9: lips read matte painted on every review; the lips.roughness lever had no row)
for k in ("nose", "forehead", "lip_lower"):
    add(f"sheen {k} (L p99 - p50)", sheen(R, B[k]), sheen(O, B[k]), 0.3, "ratio", "{:.1f}")
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
        ph, ou = (r_.get("photo") or [None, None])[e], (r_.get("ours") or [None, None])[e]
        if ph is None or ou is None:   # eyecmp's reader found no lid on one side (garrett_g10): the row is n/a, not a crash
            add(f"crease height mid {nm} (mm)", None, None, 0.8, "abs"); continue
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
    # sclera TONE as the reader sees it (garrett-eyes' ID-pass measure, contrast.py): each image in its OWN eye frame (its own
    # landmarks), the sclera = the visible opening minus the iris, as a RATIO to the upper-lid skin (and the iris to the
    # sclera), not an absolute L in a box placed by the photo's landmarks (on ours that box missed the visible white)
    tr, to = eye_tone(ri, Pr, nm), eye_tone(oi, PO, nm)
    if tr and to:
        add(f"sclera / lid skin {nm}", tr["scl"] / tr["lid"], to["scl"] / to["lid"], 0.08, "ratio")
        add(f"sclera / iris {nm}", tr["scl"] / tr["iris"], to["scl"] / to["iris"], 0.12, "ratio")
        # the white's own level (r10, 2026-10-18: the tile reviews read every sclera as too bright; the ratios hide it when
        # the lid is off too): eye_tone's value in its own eye frame, both images under the same fitted light
        add(f"sclera level {nm} (eye_tone)", tr["scl"], to["scl"], 0.1, "ratio", "{:.3f}")
        # lid SKIN (the band above the lash line, eyetone.lash_line) against the upper cheek: renamed twice on 2026-10-16 ("upper lid / cheek"
        # read the under-eye zone; "upper lid / upper cheek" read the photo's lashes on hooded lids): compare only same-named rows
        add(f"upper lid skin / upper cheek {nm}", tr["lid_skin"] / tr["cheek"], to["lid_skin"] / to["cheek"], 0.06, "ratio")
        add(f"lid band lash share {nm}", tr["lash"], to["lash"], 0.15, "abs")
        add(f"visible white {nm} (frac of the opening, > lid)", tr["wfrac"], to["wfrac"], 0.12, "abs")


# --- crop statistics for the rows that had no measure (2026-10-15, coordinator: every change needs a MEASURED target) ---
def lab_px(im, mask=None, box=None):
    """per-pixel Lab of an image (or of a box / under a mask), N x 3"""
    a = np.asarray(im, float) / 255.0
    if box is not None:
        x0, y0, x1, y1 = (int(round(v)) for v in box)
        a = a[max(y0, 0):y1, max(x0, 0):x1]
    q = a.reshape(-1, 3) if mask is None else a[mask]
    return sp.lab(sp._lin(q)) if len(q) else np.zeros((0, 3))


def brow_stats(im, box, skin_L):
    """brow hair against the forehead skin: coverage = fraction of the brow box more than 12 L below the skin; hair / skin =
    median L of those pixels over the skin's L; strand rms = fine texture (hp_rms) of the box (a solid painted block is flat)"""
    L = lab_px(im, box=box)[:, 0]
    hair = L < skin_L - 12.0
    return float(hair.mean()), (float(np.median(L[hair])) / skin_L if hair.sum() > 4 else 1.0), hp_rms(im, box)


def dots(im, box, mm):
    """stubble / pore dots in a box: pixels darker than their 3-px blur by > 6 % (log L), connected components:
    density per cm^2, median size (mm^2), median elongation (major / minor axis: strokes read as dashes, stubble as dots)"""
    from scipy import ndimage
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    a = np.log(np.asarray(im.convert("L"), float)[max(y0, 0):y1, max(x0, 0):x1] + 1)
    dk = (a - ndimage.gaussian_filter(a, 3)) < -0.06
    lab, n = ndimage.label(dk)
    area_cm2 = dk.size / (mm * mm) / 100.0
    if n == 0:
        return 0.0, 0.0, 1.0
    sizes = ndimage.sum(dk, lab, range(1, n + 1)) / (mm * mm)
    el = []
    for sl, i in zip(ndimage.find_objects(lab), range(1, n + 1)):
        yy, xx = np.nonzero(lab[sl] == i)
        if len(yy) < 3:
            el.append(1.0); continue
        ev = np.linalg.eigvalsh(np.cov(np.stack([xx, yy])) + 1e-3 * np.eye(2))
        el.append(float(np.sqrt(ev[1] / ev[0])))
    return n / area_cm2, float(np.median(sizes)), float(np.median(el))


def dot_area(im, box, mm, sign=-1):
    """AREA-WEIGHTED mean dot size (mm^2; sum s^2 / sum s) and the density of dots (per cm^2) darker (sign -1) or lighter
    (+1) than their 3-px blur by > 6 %. The median size of dots() has a ONE-PIXEL FLOOR (1 / mm^2 = .029 mm^2 on the
    768 face tile: synthetic dots of .008 and .03 mm^2 both read .029 / .058, cut/r7/dotfloor.py); weighting by area lets
    clusters and strokes count, so a sub-pixel speckle and a dense hair texture no longer read the same."""
    from scipy import ndimage
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    a = np.log(np.asarray(im.convert("L"), float)[max(y0, 0):y1, max(x0, 0):x1] + 1)
    dk = sign * (a - ndimage.gaussian_filter(a, 3)) > 0.06
    lab, n = ndimage.label(dk)
    if n == 0:
        return 0.0, 0.0
    s = ndimage.sum(dk, lab, range(1, n + 1)) / (mm * mm)
    return n / (dk.size / (mm * mm) / 100.0), float((s * s).sum() / s.sum())


def beard(im, box, ref_box, mm):
    """stubble as COVERAGE (the review: "sparse dots vs dense grey coverage"): L and chroma of the box minus the forehead's
    (a shaved / bare reference, same light), and the hair-texture coverage = fraction of pixels whose log L departs from
    its 3-px blur by > 4 % (either sign): a dense short-hair texture covers most of the box, a few specks on bare skin don't"""
    from scipy import ndimage
    q, r = lab_box(im, box), lab_box(im, ref_box)
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    a = np.log(np.asarray(im.convert("L"), float)[max(y0, 0):y1, max(x0, 0):x1] + 1)
    cov = float((np.abs(a - ndimage.gaussian_filter(a, 3)) > 0.04).mean())
    return q[0] - r[0], float(np.hypot(q[1], q[2]) - np.hypot(r[1], r[2])), cov


def brow_edge(im, box, skin_L, mm, mid_x):
    """the brow's EDGE and INSIDE (2026-10-16: r5's brows passed darkness / coverage / hair-skin but read as a "solid dark
    block, blunt front, sticker"): the hair mask (L < skin - 12 on a 1-px blur) in the box padded 2 mm; edge width = mm
    between the 20 % and 80 % points of the darkening profile across the mask's outline (signed distance bins of .25 mm:
    a sticker steps in < 0.5 mm, hair feathers out); inside spread = L p90 - p10 inside the mask eroded 0.5 mm (a block
    is flat inside, hair is strands and gaps); front / middle = darkening of the medial fifth (the end nearer the face's
    midline) over the middle two fifths (the front of a real brow fades)."""
    from scipy import ndimage
    p = 2 * mm
    bx = [box[0] - p, box[1] - p, box[2] + p, box[3] + p]
    x0, y0, x1, y1 = (int(round(v)) for v in bx)
    x0, y0 = max(x0, 0), max(y0, 0)
    a = np.asarray(im, float)[y0:y1, x0:x1] / 255.0
    L = sp.lab(sp._lin(a.reshape(-1, 3)))[:, 0].reshape(a.shape[:2])
    m = ndimage.gaussian_filter(L, 1) < skin_L - 12.0
    if m.sum() < 20:
        return None
    lab, n = ndimage.label(m)
    keep = np.argsort(ndimage.sum(m, lab, range(1, n + 1)))[::-1][:2] + 1   # the brow, not stray dark specks
    m = np.isin(lab, keep)
    sd = (ndimage.distance_transform_edt(~m) - ndimage.distance_transform_edt(m)) / mm
    dk = np.clip(skin_L - L, 0, None)
    core = np.median(dk[sd < -1.0]) if (sd < -1.0).sum() > 10 else np.median(dk[m])
    bins = np.arange(-2.0, 2.01, 0.25)
    prof = np.array([np.median(dk[(sd >= b) & (sd < b + 0.25)]) if ((sd >= b) & (sd < b + 0.25)).sum() > 3 else np.nan for b in bins])
    c = bins + 0.125
    ok = np.isfinite(prof)
    if ok.sum() < 6 or core <= 1:
        return None
    pr = np.clip(prof[ok] / core, 0, 1.5)
    cc = c[ok]
    # outward: profile falls from ~1 to ~0; the first crossings of .8 and .2 going outward from the inside
    def cross(t):
        for i in range(len(pr) - 1):
            if pr[i] >= t > pr[i + 1]:
                return cc[i] + (pr[i] - t) / (pr[i] - pr[i + 1]) * (cc[i + 1] - cc[i])
        return cc[0] if pr[0] < t else cc[-1]
    width = float(cross(0.2) - cross(0.8))
    inner = ndimage.binary_erosion(m, iterations=max(1, int(round(0.5 * mm))))
    spread = float(np.percentile(L[inner], 90) - np.percentile(L[inner], 10)) if inner.sum() > 10 else 0.0
    cols = np.nonzero(m.any(0))[0]
    if len(cols) < 10:
        return width, spread, None
    c0, c1 = cols.min(), cols.max()
    col = np.array([dk[:, j][m[:, j]].sum() for j in range(c0, c1 + 1)])   # darkening mass per column (thinning counts too)
    k = len(col)
    near_lo = abs(x0 + c0 - mid_x) < abs(x0 + c1 - mid_x)
    front = col[: k // 5] if near_lo else col[-(k // 5):]
    middle = col[3 * k // 10: 7 * k // 10]
    # the PROFILE along the brow, medial -> lateral (2026-10-18 r10, the brow head fade): darkening mass in 10 bins over
    # the middle's mean, and the head's RISE = mm from the medial end of the mask to where the column mass (smoothed
    # over .5 mm) first reaches 80 % of the middle's, minus where it first reaches 20 % (a blunt club rises in < 1 mm)
    cm = col if near_lo else col[::-1]
    mm_ = max(middle.mean(), 1e-3)
    prof10 = [float(np.mean(cm[int(i * k / 10): max(int((i + 1) * k / 10), int(i * k / 10) + 1)]) / mm_) for i in range(10)]
    sm = ndimage.uniform_filter1d(cm.astype(float), max(1, int(round(0.5 * mm)))) / mm_
    def first(t):
        i = np.nonzero(sm >= t)[0]
        return float(i[0]) / mm if len(i) else float(k) / mm
    rise = first(0.8) - first(0.2)
    return width, spread, float(front.mean() / max(middle.mean(), 1e-3)), rise, prof10


def band_rms(im, box):   # age lines: log L band-pass (1 .. 4 px), rms
    from scipy import ndimage
    a = np.log(np.asarray(im.convert("L").crop(tuple(int(round(x)) for x in box)), float) + 1)
    return float(np.sqrt(np.mean((ndimage.gaussian_filter(a, 1) - ndimage.gaussian_filter(a, 4)) ** 2)))


def eye_region(im, P, nm):
    """Lab of the rim round the opening (0 .. 1 mm outside it: waterline / inner lid colour), the socket (3 .. 7 mm above the
    upper margin) and the cheek; sclera blotchiness (L coefficient of variation, a* spread); opening height / width"""
    from scipy import ndimage
    e = EYE[nm]
    if P is None or len(P) <= max(e["iris"]):
        return None
    c = P[e["iris"][0]]; rad = float(np.mean(np.linalg.norm(P[list(e["iris"][1:])] - c, axis=1))); mm = rad / 5.9
    h, w = im.height, im.width
    poly = [tuple(P[i]) for i in e["up"]] + [tuple(P[i]) for i in e["lo"]]
    mk = Image.new("L", (w, h), 0); ImageDraw.Draw(mk).polygon(poly, fill=1); op = np.asarray(mk, bool)
    rim = ndimage.binary_dilation(op, iterations=max(1, int(round(1.0 * mm)))) & ~op
    yy, xx = np.mgrid[0:h, 0:w]; rr = np.hypot(xx - c[0], yy - c[1])
    sock = np.zeros((h, w), bool); lid = np.zeros((h, w), bool)
    for a, b in zip(e["up"][1:-2], e["up"][2:-1]):
        for t in np.linspace(0, 1, 6):
            q = P[a] * (1 - t) + P[b] * t
            sock[int(round(q[1] - 7 * mm)):int(round(q[1] - 3 * mm)), int(round(q[0])) - 1:int(round(q[0])) + 2] = True
            lid[int(round(q[1] - 3 * mm)):int(round(q[1] - 1 * mm)), int(round(q[0])) - 1:int(round(q[0])) + 2] = True
    cheek = (np.abs(xx - c[0]) < 6 * mm) & (yy > c[1] + 9 * mm) & (yy < c[1] + 12 * mm)
    scl = ndimage.binary_erosion(op, iterations=max(1, int(round(0.5 * mm)))) & (rr > rad + 0.6 * mm)
    if not (rim.any() and sock.any() and cheek.any() and scl.sum() > 8):
        return None
    md = lambda m: np.median(lab_px(im, m), 0)   # noqa: E731
    S_ = lab_px(im, scl)
    pts = np.asarray(poly)
    return {"rim": md(rim), "lid": md(lid), "sock": md(sock), "cheek": md(cheek), "scl_cv": float(S_[:, 0].std() / max(S_[:, 0].mean(), 1e-3)),
            "scl_a": float(np.percentile(S_[:, 1], 90) - np.percentile(S_[:, 1], 10)),
            "hw": float((pts[:, 1].max() - pts[:, 1].min()) / max(np.linalg.norm(P[e["up"][0]] - P[e["up"][-1]]), 1e-3))}


try:
    skinL_r, skinL_o = lab_box(R, B["forehead"])[0], lab_box(O, B["forehead"])[0]
    for k in ("brow_R", "brow_L"):
        br, bo = brow_stats(R, B[k], skinL_r), brow_stats(O, B[k], skinL_o)
        add(f"{k} coverage (frac > 12 L below forehead)", br[0], bo[0], 0.12, "abs")
        add(f"{k} hair / skin (L ratio)", br[1], bo[1], 0.08, "ratio")
        add(f"{k} strand texture (fine rms)", br[2], bo[2], 0.4, "ratio", "{:.4f}")
        mid_r, mid_o = PR[168][0], (PO[168][0] if PO is not None and len(PO) > 168 else PR[168][0])
        er_, eo_ = brow_edge(R, B[k], skinL_r, u, mid_r), brow_edge(O, B[k], skinL_o, u, mid_o)
        if er_ and eo_:
            add(f"{k} edge width (mm, 20-80 % darkening)", er_[0], eo_[0], 0.35, "ratio")
            add(f"{k} inside spread (L p90 - p10)", er_[1], eo_[1], 0.3, "ratio", "{:.1f}")
            if er_[2] is not None and eo_[2] is not None:
                add(f"{k} front / middle darkening", er_[2], eo_[2], 0.2, "abs")
            if len(er_) > 3 and len(eo_) > 3:
                add(f"{k} head rise (mm, 20-80 % of middle mass)", er_[3], eo_[3], 0.4, "ratio")
                print(f"PROFILE {k} ref  " + " ".join(f"{v:.2f}" for v in er_[4]))
                print(f"PROFILE {k} ours " + " ".join(f"{v:.2f}" for v in eo_[4]))
    jaw = {"jaw_R": bbox(PR, (172, 136, 150, 149)), "jaw_L": bbox(PR, (397, 365, 379, 378))}
    for k, box in (("chin", B["chin"]), ("jaw_R", jaw["jaw_R"]), ("cheek_R", B["cheek_R"])):
        dr, do = dots(R, box, u), dots(O, box, u)
        add(f"dots {k} (per cm^2)", dr[0], do[0], 0.5, "ratio", "{:.1f}")
        add(f"dots {k} size (mm^2)", dr[1], do[1], 0.5, "ratio", "{:.3f}")
        add(f"dots {k} elongation", dr[2], do[2], 0.25, "ratio")
        ar, ao_ = dot_area(R, box, u), dot_area(O, box, u)
        add(f"dots {k} size (mm^2, area-weighted)", ar[1], ao_[1], 0.5, "ratio", "{:.3f}")
        lr_, lo_ = dot_area(R, box, u, +1), dot_area(O, box, u, +1)
        add(f"light dots {k} (per cm^2)", lr_[0], lo_[0], 0.5, "ratio", "{:.1f}")
        if k != "cheek_R":
            gr, go = beard(R, box, B["forehead"], u), beard(O, box, B["forehead"], u)
            add(f"beard {k} - forehead (L)", gr[0], go[0], 4.0, "abs", "{:.1f}")
            add(f"beard {k} - forehead (chroma)", gr[1], go[1], 3.0, "abs", "{:.1f}")
            add(f"beard {k} hair coverage (frac)", gr[2], go[2], 0.12, "abs")
    cf = {"crows_feet_R": [PR[33][0] - 14 * u, PR[33][1] - 5 * u, PR[33][0] - 2 * u, PR[33][1] + 7 * u],
          "crows_feet_L": [PR[263][0] + 2 * u, PR[263][1] - 5 * u, PR[263][0] + 14 * u, PR[263][1] + 7 * u],
          "forehead": B["forehead"], "under_eye_R": B["under_eye_R"]}
    for k, box in cf.items():
        add(f"lines {k} (band rms)", band_rms(R, box), band_rms(O, box), 0.4, "ratio", "{:.4f}")
    for nm in ("R", "L"):
        er, eo = eye_region(R, PR, nm), eye_region(O, PO, nm)
        if er and eo:
            for part in ("rim", "lid", "sock"):
                for ch, ci in (("L", 0), ("a*", 1), ("b*", 2)):
                    add(f"eye {part} - cheek {nm} ({ch})", er[part][ci] - er["cheek"][ci], eo[part][ci] - eo["cheek"][ci], 4.0 if ci == 0 else 3.0, "abs", "{:.1f}")
            add(f"sclera blotch {nm} (L cv)", er["scl_cv"], eo["scl_cv"], 0.35, "ratio", "{:.3f}")
            add(f"sclera blotch {nm} (a* p90-p10)", er["scl_a"], eo["scl_a"], 3.0, "abs", "{:.1f}")
            add(f"eye opening {nm} (h / w, landmarks)", er["hw"], eo["hw"], 0.04, "abs", "{:.3f}")
except Exception as ex:   # the new rows must never cost the old ones
    print("WARNING: detail rows failed:", repr(ex))

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
