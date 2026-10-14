"""stack1.py: STAGE 1b, the layer stack.
  stack1.py apply <src with a de-lit projection> <dst>      skin_layers.apply; prints the report; writes out/<dst>/maps.png (each
                                                            layer alone over the base, the recomposition, the atlas, provenance)
  stack1.py truth <truth model> <dst>                       the TRUE albedo of a synthetic set (its truth_v*.png, unlit) as dst's
                                                            projection (no de-lighting to do), for the map-recovery test
  stack1.py compare <fitted-from-photos> <truth>            the maps recovered from the photographs against the maps of the true albedo
  stack1.py edit <src with a stack> <dst> <edit> ...        skin_layers.edit saved as dst"""
import copy, json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import blockin as bi, skin_layers as sl, skin_project as sp, store

OUT = "/mnt/data/hifipushie/projskin/out"
cmd = sys.argv[1]


def font(px):
    f = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    return ImageFont.truetype(f, px) if os.path.exists(f) else ImageFont.load_default()


def maps_sheet(r, path, crop=(500, 330, 1700, 1530), T=560):
    at = r["at"]
    tiles = [("the de-lit ATLAS (measured + filled)", r["atlas"]), ("RECOMPOSED stack", r["recomposed"]), ("base (the lightest skin)", np.tile(r["base"], (len(r["atlas"]), 1)))]
    for nm, l in r["layers"].items():
        tiles.append((f"{nm} alone  (support {l['support']}, {l['mm']} mm)", r["base"] * np.exp(-2.0 * l["od"]) if nm in ("pigment", "redness", "shade") else r["base"] * np.exp(-l["od"])))
    tiles.append(("freckle DENSITY (drives the generator)", np.repeat(r["freckles"][:, None], 3, 1) ** 2.2))
    pv = r["provenance"].astype(float)[:, None] / 255.0 * np.ones(3)
    tiles.append(("provenance: white measured, grey mirrored, dark inferred", pv ** 2.2))
    n = len(tiles)
    cols = 4
    rows = (n + cols - 1) // cols
    S = Image.new("RGB", (cols * T, rows * (T + 46)), (20, 20, 20))
    d = ImageDraw.Draw(S)
    for i, (lab, col) in enumerate(tiles):
        im = Image.fromarray(sp.image(at, (np.clip(sp._srgb(col), 0, 1) * 255).astype(np.uint8))).crop(crop).resize((T, T), Image.LANCZOS)
        x, y = (i % cols) * T, (i // cols) * (T + 46)
        S.paste(im, (x, y + 46))
        d.text((x + 8, y + 8), lab + ("  (x 2 for the eye)" if lab.split()[0] in ("pigment", "redness", "shade") else ""), fill=(255, 255, 255), font=font(22))
    S.save(path)


if cmd == "apply":
    src, dst = sys.argv[2:4]
    os.makedirs(f"{OUT}/{dst}", exist_ok=True)
    r = sl.apply(src, out=dst)
    print(r["text"])
    maps_sheet(r, f"{OUT}/{dst}/maps.png")
    np.savez_compressed(f"{OUT}/{dst}/amounts.npz", **{f"{k}_{a}": v.astype(np.float32) for k, l in r["layers"].items() for a, v in l["amount"].items()},
                        meas=r["meas"], freckles=r["freckles"].astype(np.float32))
elif cmd == "truth":
    truth, dst = sys.argv[2:4]
    spec, rj = copy.deepcopy(store.load(truth)), bi._refs(truth)
    d = store._dir(truth)
    photos = {vi: np.asarray(Image.open(d / "refs" / f"truth_v{vi}.png").convert("RGB")) for vi in range(len(rj["views"]))}
    r = sp.make(truth, spec=spec, photos=photos, delight=False, parse=None, mirror=False, log=lambda s: None)
    a = sp.apply(truth, out=dst, made={**r, "raw": r["raw"], "albedo": r["raw"]}, opacity=0.0)
    s2 = store.load(dst)
    s2["skin"]["projection"]["delight"] = True       # (the true albedo has no light in it)
    store.save(dst, s2, "the TRUE albedo as the atlas (map-recovery truth)", checked=False)
    print(dst, "= the true albedo as an atlas")
elif cmd == "compare":
    a, b = (np.load(f"{OUT}/{m}/amounts.npz") for m in sys.argv[2:4])
    ok = a["meas"] & b["meas"]
    print(f"maps recovered from the photographs ({sys.argv[2]}) against the maps of the TRUE albedo ({sys.argv[3]}), {int(ok.sum())} texels both measure:")
    print(f"  {'layer / axis':22s} {'corr':>6s} {'rms':>7s} {'truth mean':>11s} {'ours mean':>10s}")
    for k in a.files:
        if k in ("meas",) or k not in b.files:
            continue
        x, y = a[k][ok].astype(float), b[k][ok].astype(float)
        if y.std() < 1e-5 and x.std() < 1e-5:
            continue
        c = float(np.corrcoef(x, y)[0, 1]) if x.std() > 1e-6 and y.std() > 1e-6 else float("nan")
        print(f"  {k:22s} {c:6.2f} {np.sqrt(np.mean((x - y) ** 2)):7.3f} {y.mean():11.3f} {x.mean():10.3f}")
elif cmd == "edit":
    src, dst = sys.argv[2:4]
    spec = sl.edit(store.load(src), *sys.argv[4:])
    rj = copy.deepcopy(bi._refs(src))
    if rj.get("blockin"):
        rj["blockin"] = {**rj["blockin"], "root": dst}
    bi._save(dst, spec, f"{src} edited: {' '.join(sys.argv[4:])}", rj)
    print(dst, [(l["name"], l["opacity"]) for l in spec["skin"]["stack"]["layers"]])
