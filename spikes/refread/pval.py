"""pval.py <model>...: the OUTLINE readers validated on dressed renders of known heads. The picture = the model's own
dressed shot through each of its fitted cameras (the judging sheets' cached d_<model>_<view>.png: EEVEE, the photo's
light, bald) laid over (a) its plain grey backdrop and (b) a DARK PAINTED background (a piece of Garrett's desk
painting, behind the true alpha). The model in the solve = the same head, so every outline read should be 0 mm: the
rms of the reads IS the reader's error. Readers: truth (the shot's own mask), photo (face_ruler.photo_masks),
bisenet / mediapipe (faceparse.masks), hybrid (the plain-background mask where the backdrop is plain, the parser's
skin as trust). Also saves an overlay per model (out/pval_<model>.png)."""
import os, sys
import numpy as np
from PIL import Image, ImageFilter
from hifipushie import blockin as bi, face_ruler as fr, faceparse as fp, store

MODEL_DRAW = ("painted", "mediapipe")
OUT = "/mnt/data/hifipushie/refread/out"
SHOTS = "/mnt/data/hifipushie/reruns/out"
PAINT = Image.open("/home/joe/dev/hifipushie/workspace/garrett_v20/concept_v6_portrait_at_desk.png").convert("RGB")


def backdrop(n, seed):
    rng = np.random.default_rng(seed)
    x0, y0 = int(rng.integers(620, 900)), int(rng.integers(0, 120))
    return PAINT.crop((x0, y0, x0 + 400, y0 + 400)).resize((n, n), Image.BICUBIC)


def reads(head, view, mask, trust):
    v = dict(view, mask=mask, trust=trust, limbus=False)
    ob = [o for o in fr.observe(head, [v], colour=False) if o["type"] == "outline"]
    o = np.array([x["o"] for x in ob])
    return ob, (len(o), float(o.mean()) if len(o) else np.nan, float(np.sqrt((o ** 2).mean())) if len(o) else np.nan,
                float(np.percentile(np.abs(o), 90)) if len(o) else np.nan)


tot = {}
for m in sys.argv[1:]:
    spec, rj = store.load(m), bi._refs(m)
    head = fr.model_head(spec)
    tiles = []
    for vi, (v, cam, box) in enumerate(zip(rj["views"], rj["cameras"], rj["blockin"]["boxes"])):
        f = f"{SHOTS}/d_{m}_{vi}.png"
        if not os.path.exists(f):
            continue
        shot = Image.open(f).convert("RGB")
        n = shot.size[0]
        ib = [int(round(x)) for x in box]
        sc = n / float(ib[2] - ib[0])
        kind = fr.kind_of(v.get("yaw", 0))
        base = {"cam": cam, "kind": kind, "style": "photo", "hair": False, "face_only": True, "scale": sc, "origin": (ib[0], ib[1])}
        fg = fr.foreground(shot)
        a = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
        dark = Image.composite(shot, backdrop(n, vi + len(m)), a)
        LO = 4
        lo = dark.resize((n // LO, n // LO), Image.LANCZOS)
        fg_hi, sc_hi = fg, sc
        for bn, img in (("grey", shot), ("painted", dark), ("paint_lo", lo)):
            sc = sc_hi / LO if bn == "paint_lo" else sc_hi
            fg = np.asarray(Image.fromarray(fg_hi).resize(img.size, Image.NEAREST)) if bn == "paint_lo" else fg_hi
            view = dict(base, img=img, scale=sc)
            res = {}
            res["truth"] = reads(head, view, fg, None)
            pm, ps = fr.photo_masks(img, cam, head, origin=(ib[0], ib[1]), scale=sc)
            res["photo"] = reads(head, view, pm, ps)
            for model in ("bisenet", "mediapipe"):
                g, s, full = fp.masks(img, cam, head, origin=(ib[0], ib[1]), scale=sc, model=model)
                res[model] = reads(head, view, g, s)
                if model == "bisenet":
                    res["hybrid"] = reads(head, view, pm, s)
            for k, (ob, st) in res.items():
                print(f"{m:8s} {kind:7s} {bn:7s} {k:9s} n {st[0]:4d}  mean {st[1]:+5.2f}  rms {st[2]:5.2f}  p90 {st[3]:5.2f} mm")
                tot.setdefault((bn, kind, k), []).append(np.array([x["o"] for x in ob]))
            if bn == MODEL_DRAW[0]:
                from PIL import ImageDraw
                t = img.copy()
                d = ImageDraw.Draw(t)
                for x in res[MODEL_DRAW[1]][0]:
                    d.line([tuple(x["p"]), tuple(x["q"])], fill=(255, 235, 0), width=2)
                    d.point(tuple(x["q"]), fill=(255, 0, 0))
                tiles.append(t.resize((520, 520)))
    if tiles:
        W = Image.new("RGB", (520 * len(tiles), 520))
        for i, t in enumerate(tiles):
            W.paste(t, (520 * i, 0))
        W.save(f"{OUT}/pval_{m}.png")
print("\nALL MODELS (mm; each read's truth is 0):")
for (bn, kind, k), L in sorted(tot.items()):
    o = np.concatenate(L) if L else np.zeros(0)
    if len(o):
        print(f"  {bn:7s} {kind:7s} {k:9s} n/view {len(o) / len(L):6.1f}  bias {o.mean():+5.2f}  rms {np.sqrt((o ** 2).mean()):5.2f}  p90 {np.percentile(np.abs(o), 90):5.2f}")
    else:
        print(f"  {bn:7s} {kind:7s} {k:9s} NOTHING READ")
