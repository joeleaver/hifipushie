"""sheet2.py <out.png> <tag>:<model off>:<model on> [..] [features=1]: the PIPELINE sheet. Per scan a block, a row per
view (front / three-quarter / profile): SCAN | GNM direct fit (the ceiling) | solved from pictures, dense OFF | its gap |
solved, dense ON | its gap. Each GNM head is laid on the scan by its own best pose and scale (gscore.py), so the gap is
shape, not placement. features=1: per scan <out>_<tag>_features.png, one feature a row."""
import json
import sys
import numpy as np
import gt, rast, draw, fit3d, gscore

out = sys.argv[1]
items = [a for a in sys.argv[2:] if "=" not in a]
kw = dict(a.split("=") for a in sys.argv[2:] if "=" in a)
blocks = []
for it in items:
    tag, m_off, m_on = it.split(":")
    scan = gt.load_scan(tag)
    fb = json.loads((gt.WORK / tag / "fit_p1b3.json").read_text())
    Sb = (fb["S"]["s"], np.asarray(fb["S"]["R"]), np.asarray(fb["S"]["t"]))
    skin_v = np.load(gt.WORK / tag / "skin_v.npy")
    G = gt.gnm()
    F = G["F"]
    cb = np.asarray(fb["c"])
    Vb = gt.verts(cb)
    L = G["WL"] @ Vb
    Vs, Fs, idx = draw.scan_in_gnm(scan, Sb, L)
    sc_col = np.where(skin_v[idx][:, None], draw.CLAY, np.array([150.0, 150.0, 158.0]))
    cols = [("SCAN", Vs, Fs, sc_col, None), ("CEILING (direct fit)", Vb, F, None, fb["table"]["face"])]
    for name, m in (("SOLVED dense OFF", m_off), ("SOLVED dense ON", m_on)):
        f = gt.OUT / "scores" / f"{tag}__{m}.json"
        sj = json.loads(f.read_text()) if f.exists() else gscore.score(tag, m, scan)
        Sm = (sj["S"]["s"], np.asarray(sj["S"]["R"]), np.asarray(sj["S"]["t"]))
        c = np.asarray(sj["c"])
        g = fit3d.evaluate(scan, c, None, Sm, skin_v)
        X = gt.compose(Sb, gt.inverse(Sm))               # this head's GNM world -> the scan -> the sheet's frame
        Vm = gt.apply(X, gt.verts(c))
        cols.append((name, Vm, F, None, sj["table"]["face"]))
        cols.append(("gap", Vm, F, rast.gap_colours(g["signed"] * 1000), None))
    rows = []
    for vn, yaw, pitch in draw.VIEWS:
        cam = draw.head_cam(L, yaw, pitch)
        tiles = []
        for name, V, Fx, col, t in cols:
            lab = f"{name}" + (f": {t['mean']:.2f} mm" if t else "")
            tiles.append(draw.label(draw.clay(V, Fx, cam, col), lab if name != "SCAN" else f"SCAN {vn}", sz=30))
        rows.append(draw.hstack(tiles, pad=3))
    blk = draw.vstack(rows, pad=4)
    blocks.append(draw.label(draw.vstack([draw.Image.new("RGB", (blk.width, 60), (255, 255, 255)), blk], pad=0), f"{tag}   (dense off: {m_off}; dense on: {m_on})", sz=42))
    if kw.get("features") == "1":
        ft = []
        for fn, (yaw, pitch, ids, mg) in draw.FEATURES.items():
            cam = draw.box_cam(L, ids, yaw, pitch, mg, size=(420, 420))
            ft.append(draw.label(draw.hstack([draw.clay(V, Fx, cam, col) for name, V, Fx, col, t in cols], pad=2), f"{fn}: scan | ceiling | dense off | gap | dense on | gap", sz=30))
        body = draw.vstack([draw.hstack(ft[i:i + 2], pad=14) for i in range(0, len(ft), 2)], pad=10)
        sheet = draw.vstack([body, draw.legend(body.width)], pad=10)
        p = out.replace(".png", f"_{tag}_features.png")
        draw.label(draw.vstack([draw.Image.new("RGB", (sheet.width, 54), (255, 255, 255)), sheet], pad=0), f"{tag}: features, scan beside the solved heads ({m_off} / {m_on})", sz=38).save(p)
        print(p)
sheet = draw.vstack(blocks + [draw.legend(3370)], pad=18)
sheet.save(out)
print(out, sheet.size)
