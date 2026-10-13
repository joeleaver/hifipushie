"""iris.py <model> <scratch name> [out.png]: the IRIS COLOUR read looked at. The model is forked (nothing accepted is
written), its reference views captured (skin_read.capture: the picture and our dressed render through the same camera),
and per view the iris ring's and the sclera's pixels (the model's own eyeball geometry) are measured in both, with the
candidate iris colours each rule would set: the old rule (picture / ours against the sclera's MEDIAN, each channel
clipped to 0.5 .. 2), the same unclipped, and against the sclera's BRIGHT part (skin_read.iris_colour: what ships).
-> a tile per view: the picture's eye | our render's eye | swatches, and the numbers on stdout. Heavy (one stage)."""
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import blockin as bi, likeness as lk, paint, skin_read as sr, store

src, name = sys.argv[1], sys.argv[2]
bi.fork(src, name, replace=True)
spec = store.load(name)
frames = sr.capture(name, spec, log=print)
ctx = sr.context(name, spec, frames=frames, log=print)
mesh = lk.model_mesh(spec["base"])
c0 = np.asarray(paint.colour(((spec.get("skin") or {}).get("eyes") or {}).get("iris", "#5a3a1e")), float)[:3]
print("the model's iris colour now:", "#" + "".join(f"{int(round(255 * x)):02x}" for x in c0))
hexs = lambda lin: "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in np.clip(sr._srgb(np.clip(lin, 0, 1)), 0, 1))  # noqa: E731
tiles = []
for f, v in zip(ctx.frames, ctx.views):
    scl, iris = sr._eye_classes(f, mesh, spec)
    ok = (f["alpha"] > 0.98)
    scl, iris = scl & ok, iris & ok
    if iris.sum() < 30 or scl.sum() < 60:
        print(f"view {f['view']}: iris {int(iris.sum())} px, sclera {int(scl.sum())} px: not read")
        continue
    P, R = f["P"], f["R"]
    lum = lambda A: A @ np.array([0.2126, 0.7152, 0.0722])  # noqa: E731
    out = {}
    for nm, m in (("sclera", scl), ("iris", iris)):
        lp = lum(P[m])
        q = np.percentile(lp, [20, 50, 80])
        out[nm] = {"P_med": np.median(P[m], 0), "R_med": np.median(R[m], 0), "P_bright": np.median(P[m][lp >= q[2]], 0), "P_mid": np.median(P[m][(lp >= q[0]) & (lp <= q[2])], 0), "q": q}
        print(f"view {f['view']} {nm}: {int(m.sum())} px; picture lum 20/50/80 % {q.round(3)}; picture median {hexs(out[nm]['P_med'])} bright {hexs(out[nm]['P_bright'])}; ours median {hexs(out[nm]['R_med'])}")
    r_old = np.clip((out["iris"]["P_med"] / out["iris"]["R_med"]) / (out["sclera"]["P_med"] / out["sclera"]["R_med"]), 0.5, 2.0)
    r_unc = (out["iris"]["P_med"] / out["iris"]["R_med"]) / (out["sclera"]["P_med"] / out["sclera"]["R_med"])
    r_bri = (out["iris"]["P_mid"] / out["iris"]["R_med"]) / (out["sclera"]["P_bright"] / out["sclera"]["R_med"])
    cands = {"old (clipped)": sr._lin(c0) * r_old, "unclipped": sr._lin(c0) * r_unc, "bright sclera": sr._lin(c0) * r_bri}
    if hasattr(sr, "iris_colour"):
        cands["ships"] = sr._lin(np.asarray(paint.colour(sr.iris_colour(c0, r_bri)), float)[:3])
    for k, c in cands.items():
        print(f"   {k}: ratio {np.round(c / np.maximum(sr._lin(c0), 1e-6), 2)} -> {hexs(c)}")
    ys, xs = np.where(iris | scl)
    y0, y1, x0, x1 = ys.min() - 12, ys.max() + 12, xs.min() - 12, xs.max() + 12
    crop = lambda A: Image.fromarray((255 * np.clip(sr._srgb(np.clip(A[max(y0, 0):y1, max(x0, 0):x1], 0, 1)), 0, 1)).astype(np.uint8)).resize((4 * (x1 - max(x0, 0)), 4 * (y1 - max(y0, 0))), Image.LANCZOS)  # noqa: E731
    a, b = crop(P), crop(R)
    sw = Image.new("RGB", (220, a.size[1]), "white")
    d = ImageDraw.Draw(sw)
    for i, (k, c) in enumerate(cands.items()):
        d.rectangle([4, 4 + i * 44, 60, 40 + i * 44], fill=hexs(c))
        d.text((66, 14 + i * 44), k, fill=(0, 0, 0))
    W = Image.new("RGB", (a.size[0] + b.size[0] + sw.size[0] + 12, a.size[1]), "white")
    W.paste(a, (0, 0)); W.paste(b, (a.size[0] + 6, 0)); W.paste(sw, (a.size[0] + b.size[0] + 12, 0))
    tiles.append(W)
if tiles and len(sys.argv) > 3:
    H = Image.new("RGB", (max(t.size[0] for t in tiles), sum(t.size[1] + 6 for t in tiles)), "white")
    y = 0
    for t in tiles:
        H.paste(t, (0, y)); y += t.size[1] + 6
    H.save(sys.argv[3])
    print("->", sys.argv[3])
