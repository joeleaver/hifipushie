"""diag.py <model> <export dir> <out prefix> [tiers=hero,main,npc,far] [size=400] [export=1]: the card tiers as an
engine gets them, with evidence. One sheet: strands | per tier: the GLB re-imported (alpha test) / dithered / the
cards as solid quads by layer | the atlas. Numbers per tier to <prefix>.json and stdout."""
import json, os, sys, tempfile, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import hair, store, hair_cards as hc

name, out_dir, prefix = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
kw = dict(a.split("=", 1) for a in sys.argv[4:])
tiers = kw.get("tiers", "hero,main,npc,far").split(",")
size = int(kw.get("size", 400))
views = tuple(kw.get("views", "wide_r,back_quarter,close_front,three_quarter").split(","))
HR = Path(os.environ["HR"])
t0 = time.time()
if int(kw.get("export", 1)):
    rep = hair.export_hair(name, out_dir, tiers=tuple(tiers), groom=False)
else:
    rep = json.loads((out_dir / f"{name}_hair.json").read_text())
print("export", round(time.time() - t0, 1), "s")


def hsv(rgb):
    import colorsys
    return np.array([colorsys.rgb_to_hsv(*c) for c in rgb])


def stats(img, bald, ref_mask=None):
    a, b = np.asarray(img, float) / 255, np.asarray(bald, float) / 255
    m = np.abs(a - b).max(-1) > 0.06
    px = a[m]
    h = hsv(px[:: max(1, len(px) // 4000)]) if len(px) else np.zeros((1, 3))
    o = {"hair_px": int(m.sum()), "value": round(float(h[:, 2].mean()), 3), "sat": round(float(h[:, 1].mean()), 3),
         "hue": round(float(np.median(h[:, 0]) * 360), 1), "black": round(float((h[:, 2] < 0.06).mean()), 3)}
    if ref_mask is not None:
        o["iou"] = round(float((m & ref_mask).sum() / max((m | ref_mask).sum(), 1)), 3)
        o["missing"] = round(float((ref_mask & ~m).sum() / max(ref_mask.sum(), 1)), 3)
    return o, m


spec = store.load(name)
bald, _, _ = hair.look_glb(name, None, views=views, size=size)
sp = store.load(name)
sp["hair"]["style"] = "strands"
sheet, sec, fr = hair.look(name, views=views, size=size, spec=sp, clay=False)
strands = [sheet.crop((i * size, 22, (i + 1) * size, 22 + size)) for i in range(len(views))]
rows = [("strands (EEVEE)", strands)]
num = {"strands": {}}
ref = {}
for v, im, b in zip(views, strands, bald):
    num["strands"][v], ref[v] = stats(im, b)
for tier in tiers:
    glb = rep["tiers"][tier]["glb"]
    num[tier] = {"triangles": rep["tiers"][tier]["triangles"], "layers": rep["tiers"][tier]["layers"],
                 "budget": rep["tiers"][tier]["budget"]}
    for alpha in ("test", "dither"):
        imgs, info, s_ = hair.look_glb(name, glb, views=views, size=size, alpha=alpha)
        rows.append((f"{tier}: GLB re-imported, alpha {alpha}   {rep['tiers'][tier]['triangles']} triangles   {s_}s", imgs))
        num[tier][alpha] = {v: stats(im, b, ref[v])[0] for v, im, b in zip(views, imgs, bald)}
        num[tier]["import"] = info
    sc_ = store.load(name)
    sc_["hair"]["style"] = "cards"
    sh, s_, _ = hair.look(name, views=views, size=size, spec=sc_, clay=False, budget=tier, debug="layers")
    rows.append((f"{tier}: cards as solid quads by layer (cap grey, 0 red, 1 green, 2 blue, 3 yellow, fly/top magenta; back faces dark)",
                 [sh.crop((i * size, 22, (i + 1) * size, 22 + size)) for i in range(len(views))]))
    # the card mesh's own numbers
    j = hair.job(name, sc_, budget=tier)
    cd = j["cards"]
    M = dict(np.load(cd["mesh"]))
    sc = hair.scalp(name, spec)
    T = M["tris"]
    lay = M["layer"][T[:, 0]]
    out_dir_ = M["verts"] - sc.C
    facing = (M["normal"] * out_dir_).sum(1) / np.maximum(np.linalg.norm(out_dir_, axis=1), 1e-9)
    # card widths: verts come in left / right pairs
    wd = np.linalg.norm(M["verts"][0::2] - M["verts"][1::2], axis=1)
    cid = M["card"][0::2]
    wcard = np.array([wd[cid == c].max() for c in np.unique(cid)])
    lcard = np.array([M["layer"][0::2][cid == c][0] for c in np.unique(cid)])
    num[tier]["mesh"] = {"cards": int(len(wcard)), "card_width_mm_p10_50_90": [round(float(x) * 1000, 1) for x in np.percentile(wcard, [10, 50, 90])],
                         "triangles_by_layer": {str(int(k)): int((lay == k).sum()) for k in np.unique(lay)},
                         "cards_by_layer": {str(int(k)): int((lcard == k).sum()) for k in np.unique(lcard)},
                         "normals_facing_inward": round(float((facing < 0).mean()), 3),
                         "uv_range": [round(float(M["uv"][:, 0].min()), 3), round(float(M["uv"][:, 0].max()), 3),
                                      round(float(M["uv"][:, 1].min()), 3), round(float(M["uv"][:, 1].max()), 3)],
                         "vcolor_mean": round(float(M["col"].mean()), 3), "coverage": cd["coverage"]}
# the atlas: alpha kept at the cutoff through the mips, per tile
bc = np.asarray(Image.open(out_dir / "hair_basecolor.png").convert("RGBA"), np.float32) / 255
at = {}
j = hair.job(name, {**spec, "hair": {**spec["hair"], "style": "cards"}}, budget="main")
import inspect
W = bc.shape[1]
x = 0
tiles = []
for kind, w0 in hc.TILES:
    w = int(round(w0 * (W // 2) / 1024))
    tiles.append((kind, x, x + w))
    x += w
tiles.append(("cap", W // 2, W))
for kind, a, b in tiles:
    al = bc[:, a:b, 3]
    r = {}
    for mip in (0, 1, 2, 3, 4):
        f = 2 ** mip
        hh, ww = (al.shape[0] // f) * f, max((al.shape[1] // f) * f, f)
        q = al[:hh, :ww].reshape(hh // f, f, ww // f, f).mean((1, 3)) if ww <= al.shape[1] else al
        r[f"mip{mip}"] = round(float((q > 0.33).mean()), 3)
    rgb = bc[:, a:b, :3][al > 0.5]
    r["srgb_mean"] = [round(float(c), 3) for c in rgb.mean(0)] if len(rgb) else None
    at.setdefault(kind, r)
num["atlas_alpha_over_cutoff_by_mip"] = at
lk = {**hair.LOOK, **(spec["hair"].get("look") or {})}
num["look"] = {k: lk[k] for k in ("gap", "lit", "tip", "vary", "root", "tip_amount")}
(HR / f"{prefix}.json").write_text(json.dumps(num, indent=1, default=float))
W_ = size * len(views)
atl = Image.open(out_dir / "hair_basecolor.png").convert("RGBA")
bg = Image.new("RGBA", atl.size, (140, 140, 140, 255))
atl_c = Image.alpha_composite(bg, atl).convert("RGB").resize((W_, W_ // 2))
atl_a = atl.split()[3].convert("RGB").resize((W_, W_ // 2))
img = Image.new("RGB", (W_, len(rows) * (size + 18) + 2 * (W_ // 2 + 18)), (30, 31, 35))
d = ImageDraw.Draw(img)
y = 0
for lab, ims in rows:
    d.text((6, y + 3), lab, fill=(240, 220, 160))
    for i, im in enumerate(ims):
        img.paste(im.resize((size, size)), (i * size, y + 18))
    y += size + 18
for lab, im in (("atlas: base colour over grey (left half the clump tiles, right half the scalp chart)", atl_c), ("atlas: alpha", atl_a)):
    d.text((6, y + 3), lab, fill=(240, 220, 160))
    img.paste(im, (0, y + 18))
    y += W_ // 2 + 18
img.save(HR / f"{prefix}.png")
for lab, ims in rows:  # each row on its own too (readable at full size)
    r = Image.new("RGB", (W_, size))
    for i, im in enumerate(ims):
        r.paste(im.resize((size, size)), (i * size, 0))
    r.save(HR / f"{prefix}_{lab.split(':')[0].split(' ')[0]}_{'solid' if 'solid' in lab else 'dither' if 'dither' in lab else 'test' if 'test' in lab else 'look'}.png")
print(json.dumps({k: v for k, v in num.items() if k != "strands"}, default=float)[:6000])
print("total", round(time.time() - t0, 1), "s")
