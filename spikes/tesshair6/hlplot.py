"""hlplot.py <out.png> <model> ...: WITHOUT Blender (1 s a head): each head's left side drawn from its scalp rays
(shaded by the rays' normals, 0.5 degree), the ear hair.ear() found (cyan dots, dotted lines at its top and lobe), and
the hairline OLD (the ear guessed at brow_outer + 4 mm: red) against NEW (the ear found: green). old=0: only the
current line. cols=4, px=520 (a panel), span=0.26 (m across a panel)."""
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hifipushie import hair, store


def font(sz):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", sz)
    except Exception:
        return ImageFont.load_default()


def panel(m, px=520, span=0.26, old=True):
    spec = store.load(m)
    sc = hair.scalp(m, spec)
    g = hair.groom_params(spec)
    a = np.arange(0.0, 181.0, 0.5)
    e = np.arange(-68.0, 90.0, 0.5)
    AA, EE = np.meshgrid(a, e, indexing="ij")
    P = sc.point(AA, EE, 0.0) - sc.C
    N = sc.normal(AA, EE, 1.0)
    L = np.array([0.55, -0.45, 0.7])
    sh = np.clip(N @ (L / np.linalg.norm(L)), 0, 1) * 0.7 + 0.3
    cy = 0.01

    def uv(Q):
        return (px / 2 + (Q[..., 1] - cy) / span * px), (px / 2 - (Q[..., 2] + 0.02) / span * px)

    img = np.full((px, px, 3), 235, np.uint8)
    zb = np.full((px, px), -np.inf)
    u, v = uv(P)
    vis = (N[..., 0] > 0.0)
    for du in range(-2, 3):
        for dv in range(-2, 3):
            ui, vi = np.round(u[vis] + du).astype(int), np.round(v[vis] + dv).astype(int)
            ok = (ui >= 0) & (ui < px) & (vi >= 0) & (vi < px)
            x = P[..., 0][vis][ok]
            c = (sh[vis][ok] * 215).astype(np.uint8)
            o = np.argsort(x)
            ui, vi, x, c = ui[ok][o], vi[ok][o], x[o], c[o]
            upd = x > zb[vi, ui]
            img[vi[upd], ui[upd]] = np.stack([c[upd], (c[upd] * 0.93).astype(np.uint8), (c[upd] * 0.86).astype(np.uint8)], 1)
            zb[vi[upd], ui[upd]] = x[upd]
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    er = hair.ear(sc)
    lines = []
    if old and er is not None:
        sc._ear = None
        lines.append((hair.hairline(sc, g), (220, 30, 30)))
        sc._ear = er
    lines.append((hair.hairline(sc, g), (20, 170, 40)))
    txt = [m]
    if er is not None:
        C = np.asarray(er["cells"], float)
        Q = sc.point(C[:, 0], C[:, 1], 0.0) - sc.C
        qu, qv = uv(Q)
        for x_, y_ in zip(qu, qv):
            dr.ellipse([x_ - 1.5, y_ - 1.5, x_ + 1.5, y_ + 1.5], fill=(0, 200, 230))
        for z, c in ((er["top"], (0, 150, 200)), (er["lobe"], (0, 150, 200))):
            y_ = px / 2 - (z - sc.C[2] + 0.02) / span * px
            for x_ in range(0, px, 8):
                dr.line([x_, y_, x_ + 3, y_], fill=c)
        o = sc.lm.get("lm_brow_outer.L")
        if o is not None:
            y_ = px / 2 - (o[2] + 0.004 - sc.C[2] + 0.02) / span * px
            for x_ in range(0, px, 8):
                dr.line([x_, y_, x_ + 3, y_], fill=(220, 30, 30))
            txt.append(f"ear top FOUND {100 * (er['top'] - sc.C[2]):+.1f} cm, old guess {100 * (o[2] + 0.004 - sc.C[2]):+.1f} cm")
            txt.append(f"old line {1000 * (o[2] + 0.004 + (0.01 if g['hairline'].get('ear') is None else g['hairline']['ear']) - er['top']):.0f} mm over the ear")
    else:
        txt.append("NO EAR FOUND: old rule")
    for line, c in lines:
        az = np.arange(0.0, 181.0, 0.5)
        Q = sc.point(az, hair._line_at(line, az), 0.0) - sc.C
        qu, qv = uv(Q)
        dr.line(list(zip(qu.tolist(), qv.tolist())), fill=c, width=3)
    f = font(17)
    for i, t in enumerate(txt):
        dr.text((6, 4 + 20 * i), t, fill=(0, 0, 0), font=f)
    if old:
        dr.text((6, px - 44), "OLD hairline", fill=(220, 30, 30), font=f)
        dr.text((6, px - 24), "NEW hairline (ear found)", fill=(20, 150, 40), font=f)
    return im


if __name__ == "__main__":
    kw = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    args = [a for a in sys.argv[1:] if "=" not in a]
    out, names = args[0], args[1:]
    px = int(kw.get("px", 520))
    cols = min(len(names), int(kw.get("cols", 4)))
    rows = -(-len(names) // cols)
    sheet = Image.new("RGB", (cols * px, rows * px), (255, 255, 255))
    for i, m in enumerate(names):
        sheet.paste(panel(m, px, float(kw.get("span", 0.26)), bool(int(kw.get("old", 1)))), ((i % cols) * px, (i // cols) * px))
        print("done", m)
    sheet.save(out)
    print("saved", out)
