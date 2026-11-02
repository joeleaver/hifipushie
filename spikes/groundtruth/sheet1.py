"""sheet1.py <out.png> <tag>:<fit> [<tag>:<fit> ..] [features=1]: the CEILING sheet. Per scan a row: front /
three-quarter / profile, each as scan (clay) | GNM direct fit (clay) | the signed gap on GNM. features=1: per scan a
second sheet <out>_<tag>_features.png: one feature at a time, scan beside fit beside gap."""
import json
import sys
import numpy as np
import gt, rast, draw, fit3d

out = sys.argv[1]
items = [a for a in sys.argv[2:] if "=" not in a]
kw = dict(a.split("=") for a in sys.argv[2:] if "=" in a)
rows = []
for it in items:
    tag, name = it.split(":")
    scan = gt.load_scan(tag)
    fj = json.loads((gt.WORK / tag / f"fit_{name}.json").read_text())
    S = (fj["S"]["s"], np.asarray(fj["S"]["R"]), np.asarray(fj["S"]["t"]))
    c, e = np.asarray(fj["c"]), (None if fj["e"] is None else np.asarray(fj["e"]))
    Vg, F, L = draw.gnm_mesh(c, e)
    skin_v = np.load(gt.WORK / tag / "skin_v.npy")
    g = fit3d.evaluate(scan, c, e, S, skin_v)
    Vs, Fs, idx = draw.scan_in_gnm(scan, S, L)
    sc_col = np.where(skin_v[idx][:, None], draw.CLAY, np.array([150.0, 150.0, 158.0]))      # hair / cloth (not compared) darker
    gcol = rast.gap_colours(g["signed"] * 1000)
    tiles = []
    for vn, yaw, pitch in draw.VIEWS:
        cam = draw.head_cam(L, yaw, pitch)
        a = draw.label(draw.clay(Vs, Fs, cam, sc_col), f"SCAN {vn}")
        b = draw.label(draw.clay(Vg, F, cam), "GNM direct fit")
        d = draw.label(draw.clay(Vg, F, cam, gcol), "gap")
        tiles.append(draw.hstack([a, b, d], pad=2))
    row = draw.hstack(tiles, pad=14)
    t = fj["table"]["face"]
    rows.append(draw.label(draw.vstack([draw.Image.new("RGB", (row.width, 56), (255, 255, 255)), row], pad=0),
                           f"{tag}  |  fit {name}: prior x{fj['prior']:g}{', + expression' if fj['expr'] else ''}  |  face mean {t['mean']:.2f} mm, p90 {t['p90']:.2f} mm  |  |c - class mean| {fj['c_off']:.1f} (max {fj['c_max']:.1f} sd)", sz=40))
    if kw.get("features") == "1":
        ft = []
        for fn, (yaw, pitch, ids, mg) in draw.FEATURES.items():
            cam = draw.box_cam(L, ids, yaw, pitch, mg)
            ft.append(draw.label(draw.hstack([draw.clay(Vs, Fs, cam, sc_col), draw.clay(Vg, F, cam), draw.clay(Vg, F, cam, gcol)], pad=2), f"{fn}: scan | GNM fit | gap", sz=30))
        n = 3
        sheet = draw.vstack([draw.hstack(ft[i:i + n], pad=12) for i in range(0, len(ft), n)] + [draw.legend(1400)], pad=10)
        p = out.replace(".png", f"_{tag}_{name}_features.png")
        draw.label(draw.vstack([draw.Image.new("RGB", (sheet.width, 50), (255, 255, 255)), sheet], pad=0), f"{tag} fit {name}: features", sz=36).save(p)
        print(p)
sheet = draw.vstack(rows + [draw.legend(2400)], pad=16)
sheet.save(out)
print(out, sheet.size)
