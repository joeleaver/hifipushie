"""hline.py <model> [views csv: 0,1]: the HAIRLINE and the hair's SILHOUETTE by proportion, like with like: the same
detector (MediaPipe) and the same pixel classifiers on her picture and on our dressed render through that picture's
fitted camera (tiles of shots.py). Frame from the detector: centre line + outer-eye-corner span, EYE line (four eye
corners), MOUTH line (corners), BROW line (upper brow 105 / 334), chin (152); U = eye line -> mouth line.
  hairline: per station s (x = centre + s x span) up from over the brows, where the forehead's skin ends; its height
            over the eye line / U; forehead (hairline - brow) / (brow - chin) at the centre.
  temples:  per level over the eye line (x U) from the centre outward, where skin ends: half-width / span.
  outline:  the head + hair against the backdrop: its top per station (over the eye line / U) and its half-width per
            level (/ span), her right | her left.
Prints hers | ours | miss in mm (+ = ours higher / wider); overlay $TOUT/hline_<model>_v<view>.png."""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import likeness, store

W, H = 1152, 1536
STN = [round(-0.7 + 0.1 * i, 2) for i in range(15)]
LEV = [0.5, 0.65, 0.8, 0.95, 1.1]
OLEV = [-0.6, -0.3, 0.0, 0.3, 0.6, 0.9, 1.2, 1.5]
OSTN = [round(-1.0 + 0.2 * i, 2) for i in range(11)]


def lab(a):
    a = np.asarray(a, float) / 255.0
    lin = np.where(a > 0.04045, ((a + 0.055) / 1.055) ** 2.4, a / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / [0.9505, 1.0, 1.089]
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def photo_tile(path, N):
    ph = Image.open(path).convert("RGB")
    a = np.asarray(ph)
    edge = tuple(int(x) for x in np.median(np.r_[a[:300, :40].reshape(-1, 3), a[:300, -40:].reshape(-1, 3)], 0))
    sq = Image.new("RGB", (H, H), edge)
    sq.paste(ph, ((H - W) // 2, 0))
    return sq.resize((N, N), Image.LANCZOS)


def frame(P):
    cx = 0.5 * (P[33][0] + P[263][0])
    span = abs(P[263][0] - P[33][0])
    eye = float(np.mean([P[i][1] for i in (33, 133, 362, 263)]))
    mouth = 0.5 * (P[61][1] + P[291][1])
    return {"cx": float(cx), "span": float(span), "eye": eye, "mouth": float(mouth), "U": float(mouth - eye),
            "brow": float(0.5 * (P[105][1] + P[334][1])), "chin": float(P[152][1])}


def _walk(row, x, sg, need):
    run = 0
    while 2 < x < len(row) - 2:
        run = 0 if row[x] else run + 1
        if run >= need:
            break
        x += sg
    return x - sg * run


def measure(img):
    P = likeness.detect([img])[0]
    assert P is not None, "no face found"
    P = np.asarray(P, float)[:, :2]
    fr = frame(P)
    a = np.asarray(img, float)
    L = lab(a)
    cx, sp, U, eye = fr["cx"], fr["span"], fr["U"], fr["eye"]
    # skin: near the forehead's own colour (a patch just over the brows)
    y0, y1 = int(fr["brow"] - 0.30 * U), int(fr["brow"] - 0.10 * U)
    x0, x1 = int(cx - 0.25 * sp), int(cx + 0.25 * sp)
    ref = np.median(L[y0:y1, x0:x1].reshape(-1, 3), 0)
    d = L - ref
    sk = (np.sqrt((d[..., 0] / 3.0) ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2) < 15.0) & (d[..., 0] > -22)
    # backdrop: near the top corners' colour
    n = a.shape[0]
    bgc = np.median(np.r_[L[: n // 12, : n // 6].reshape(-1, 3), L[: n // 12, -n // 6:].reshape(-1, 3)], 0)
    db = L - bgc
    fg = np.sqrt((db[..., 0] / 2.0) ** 2 + db[..., 1] ** 2 + db[..., 2] ** 2) > 7.0
    k = max(1, int(round(0.03 * sp)))
    need = max(3, int(round(0.05 * U)))
    rows = []
    for s in STN:
        x = int(round(cx + s * sp))
        col = sk[:, x - k:x + k + 1].mean(1) > 0.5
        ys = y = int(fr["brow"] - 0.08 * U)
        run = 0
        while y > 2:
            run = 0 if col[y] else run + 1
            if run >= need:
                break
            y -= 1
        yh = y + run
        rows.append([s, x, yh, (eye - yh) / U if yh < ys - 2 else float("nan")])
    wid = []
    for lv in LEV:
        y = int(round(eye - lv * U))
        row = sk[y - k:y + k + 1].mean(0) > 0.5
        wid.append([lv, y] + [abs(_walk(row, int(cx), sg, need) - cx) / sp for sg in (-1, 1)])
    top = []
    for s in OSTN:
        x = int(round(cx + s * sp))
        col = fg[:, x - k:x + k + 1].mean(1) > 0.5
        run = np.convolve(col, np.ones(need), "valid") >= need
        yt = int(np.argmax(run)) if run.any() else n
        top.append([s, x, yt, (eye - yt) / U])
    out = []
    for lv in OLEV:
        y = int(round(eye - lv * U))
        row = fg[y - k:y + k + 1].mean(0) > 0.5
        out.append([lv, y] + [abs(_walk(row, int(cx), sg, need) - cx) / sp for sg in (-1, 1)])
    c = [r[3] for r in rows if abs(r[0]) <= 0.15 and r[3] == r[3]]
    tri = eye - float(np.mean(c)) * U if c else float("nan")
    fr["forehead_ratio"] = (fr["brow"] - tri) / (fr["chin"] - fr["brow"])
    return {"fr": fr, "rows": rows, "wid": wid, "top": top, "out": out, "sk": sk, "fg": fg}


def draw(img, m):
    a = np.asarray(img, float).copy()
    a[~m["fg"]] = a[~m["fg"]] * 0.75 + np.array([0, 50, 0])
    a[m["sk"]] = a[m["sk"]] * 0.75 + np.array([60, 0, 0])
    im = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    fr = m["fr"]
    for key, colr in (("eye", (0, 255, 0)), ("mouth", (0, 255, 0)), ("brow", (255, 255, 0)), ("chin", (255, 255, 0))):
        d.line([(fr["cx"] - fr["span"], fr[key]), (fr["cx"] + fr["span"], fr[key])], fill=colr)
    for s, x, y, v in m["rows"]:
        if v == v:
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 0, 0))
    for s, x, y, v in m["top"]:
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 0, 255))
    for key, colr in (("wid", (0, 255, 255)), ("out", (255, 128, 0))):
        for lv, y, l, r in m[key]:
            for xx in (fr["cx"] - l * fr["span"], fr["cx"] + r * fr["span"]):
                d.ellipse((xx - 3, y - 3, xx + 3, y + 3), fill=colr)
    return im


def run(model, v=0, N=768, log=print):
    refs = json.loads((store.HOME / model / "human_refs.json").read_text())
    OUT = os.environ["TOUT"]
    ph = photo_tile(refs["views"][v]["image"], N)
    ours = Image.open(f"{OUT}/s_{model}_v{v}.png").convert("RGB").resize((N, N), Image.LANCZOS)
    a, b = measure(ph), measure(ours)
    cam = refs["cameras"][v]
    mm = cam["t"][2] / cam["f"] * 1000 * H / N          # mm a tile pixel at the head
    Ua, Ub, Sa, Sb = a["fr"]["U"] * mm, b["fr"]["U"] * mm, a["fr"]["span"] * mm, b["fr"]["span"] * mm
    log(f"== {model} view {v}: U (eye line -> mouth line) hers {Ua:.1f} mm ours {Ub:.1f} mm; eye span hers {Sa:.1f} ours {Sb:.1f} mm")
    log(f"   forehead / lower face ((brow - hairline at centre) / (brow - chin)): hers {a['fr']['forehead_ratio']:.3f} ours {b['fr']['forehead_ratio']:.3f}")
    log("   HAIRLINE over the eye line / U   station: hers | ours | miss mm (+ = ours higher)")
    ms = []
    for ra, rb in zip(a["rows"], b["rows"]):
        mi = (rb[3] - ra[3]) * Ua
        ms.append((ra[0], mi))
        log(f"     s {ra[0]:+.1f}: {ra[3]:.3f} | {rb[3]:.3f} | {mi:+5.1f}")
    A = np.array(ms)
    cen, outr = A[np.abs(A[:, 0]) <= 0.25, 1], A[np.abs(A[:, 0]) >= 0.35, 1]
    log("   TEMPLES: forehead half-width / span, her right | her left   level: hers | ours | miss mm (+ = ours wider = more bare)")
    wm = []
    for wa, wb in zip(a["wid"], b["wid"]):
        wm.append(((wb[2] - wa[2]) * Sa, (wb[3] - wa[3]) * Sa))
        log(f"     level {wa[0]:.2f}: {wa[2]:.2f} {wa[3]:.2f} | {wb[2]:.2f} {wb[3]:.2f} | {wm[-1][0]:+5.1f} {wm[-1][1]:+5.1f}")
    log("   OUTLINE TOP over the eye line / U   station: hers | ours | miss mm (+ = ours taller)")
    tm = []
    for ta, tb in zip(a["top"], b["top"]):
        tm.append((tb[3] - ta[3]) * Ua)
        log(f"     s {ta[0]:+.1f}: {ta[3]:.3f} | {tb[3]:.3f} | {tm[-1]:+5.1f}")
    log("   OUTLINE half-width / span, her right | her left   level: hers | ours | miss mm (+ = ours wider)")
    om = []
    for oa, ob in zip(a["out"], b["out"]):
        om.append(((ob[2] - oa[2]) * Sa, (ob[3] - oa[3]) * Sa))
        log(f"     level {oa[0]:+.1f}: {oa[2]:.2f} {oa[3]:.2f} | {ob[2]:.2f} {ob[3]:.2f} | {om[-1][0]:+5.1f} {om[-1][1]:+5.1f}")
    tmc = np.array(tm)[np.abs(np.array(OSTN)) <= 0.45]
    omu = np.array(om)[np.array(OLEV) >= 0.3]
    log(f"   SUMMARY v{v}: hairline centre {np.nanmean(cen):+.1f} mm, outer {np.nanmean(outr):+.1f} mm; temples {np.nanmean(wm):+.1f} mm; "
        f"top (|s| <= 0.4) {np.nanmean(tmc):+.1f} mm; width above the eyes her right {np.nanmean(omu[:, 0]):+.1f} / her left {np.nanmean(omu[:, 1]):+.1f} mm")
    sh = Image.new("RGB", (2 * N, N))
    sh.paste(draw(ph, a), (0, 0))
    sh.paste(draw(ours, b), (N, 0))
    sh.save(f"{OUT}/hline_{model}_v{v}.png")


if __name__ == "__main__":
    for v in [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "0,1").split(",")]:
        run(sys.argv[1], v)
