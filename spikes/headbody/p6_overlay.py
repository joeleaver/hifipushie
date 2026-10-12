"""p6_overlay.py: side profile (midline front / back) and front silhouette (half width by height) of the neck region,
old attach | native | MakeHuman's own, aligned at the suprasternale; ANSUR's heights marked. PIL only."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import headfit, makehuman, onemesh, store

F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
SUPRA, ACRO = 1522, 8275
a = onemesh.asset()
row = {int(v): i for i, v in enumerate(np.flatnonzero(a["m2f"] >= 0))}
ANS = {"F": {"top": 298.8, "acro": 5.4, "chin": 81.0, "neck": 329.8, "trag": 172.3}, "M": {"top": 317.6, "acro": -2.1, "chin": 86.0, "neck": 397.6, "trag": 186.5}}


def dense(P, L, S, lo):
    """The cage round the neck and head, Catmull-Clark'd twice (a smooth, dense point set)."""
    from hifipushie import base as B
    faces, i = [], 0
    for n in S:
        faces.append(list(L[i:i + n])); i += n
    keep = P[:, 2] > lo
    faces = [f for f in faces if keep[f].all()]
    used = np.unique(np.concatenate(faces))
    rm = np.full(len(P), -1); rm[used] = np.arange(len(used))
    V, Fq = P[used], [list(rm[f]) for f in faces]
    for _ in range(2):
        V, Fq = B._catmull_clark(V, Fq)
    return np.asarray(V, float)


def curves(P, supra, step=0.003):
    Q = P - [0, supra[1], supra[2]]
    out = {}
    m = np.abs(Q[:, 0]) < 0.004
    b = np.floor(Q[:, 2] / step).astype(int)
    zs = np.unique(b[m])
    out["front"] = np.array([[Q[m & (b == k)][:, 1].min(), (k + .5) * step] for k in zs])
    out["back"] = np.array([[Q[m & (b == k)][:, 1].max(), (k + .5) * step] for k in zs])
    m2 = (np.abs(Q[:, 1] - 0.05) < 0.20)
    zs = np.unique(b[(Q[:, 2] > -0.12)])
    out["width"] = np.array([[np.abs(Q[(b == k) & m2][:, 0]).max(), (k + .5) * step] for k in zs if ((b == k) & m2).any()])
    return out


def panel(sets, sex, title, mode):
    W, H, sc = 900, 1150, 2600.0
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    ox, oy = (520 if mode == "side" else 450), 800
    X = lambda y, z: (ox + sc * y, oy - sc * z)  # noqa: E731
    A = ANS[sex]
    for nm, mm, col in (("ANSUR top of head", A["top"], (0, 0, 0)), ("ANSUR chin (head height from memory)", A["chin"], (120, 120, 120)),
                        ("suprasternale", 0.0, (0, 0, 0)), ("ANSUR acromion", -A["acro"], (120, 120, 120))):
        y = oy - sc * mm / 1000
        d.line([(20, y), (W - 20, y)], fill=col, width=1)
        d.text((24, y - 22), f"{nm} {mm:+.0f} mm", font=F(17), fill=col)
    for (nm, col, C, extra) in sets:
        if mode == "side":
            for k in ("front", "back"):
                d.line([X(y, z) for y, z in C[k] if z > -0.12], fill=col, width=3)
        else:
            pts = [(ox + sc * x, oy - sc * z) for x, z in C["width"]]
            d.line(pts, fill=col, width=3)
            d.line([(2 * ox - x, y) for x, y in pts], fill=col, width=3)
        for z, lab in extra:
            y = oy - sc * z
            d.line([(W - 150, y), (W - 20, y)], fill=col, width=3)
    d.text((20, 10), title, font=F(30), fill=(0, 0, 0))
    yy = 52
    for (nm, col, C, extra) in sets:
        d.text((20, yy), nm, font=F(22), fill=col)
        yy += 28
    return im


def main():
    out = []
    for who, sex, old, new in (("TESS", "F", "nt_N06", "hb_tess"), ("GARRETT", "M", "ng_N05", "hb_garrett")):
        sets = []
        for name, col in ((old, (200, 40, 40)), (new, (20, 130, 50))):
            base = store.load(name)["base"]
            tpl = onemesh.template(base)
            ht = onemesh.head_rest(base)
            P = np.asarray(tpl["P"], float)
            s = P[row[SUPRA]]
            top, chin, ac = P[:, 2].max() - s[2], ht["lm68"][8][2] - s[2], P[row[ACRO]][2] - s[2]
            sets.append((f"{name}: top {1e3*top:+.0f}, chin {1e3*chin:+.0f}, acromion {1e3*ac:+.0f}", col, curves(dense(P, tpl["L"], tpl["S"], s[2] - 0.2), s), [(top, "top"), (chin, "chin")]))
            if name == old:
                mb = makehuman.body(onemesh.body_params(base))
                Pm = np.asarray(mb["P"], float)
                s = Pm[SUPRA]
                top, chin, ac = Pm[:, 2].max() - s[2], Pm[headfit.table()["lm68"][8]][2] - s[2], Pm[ACRO][2] - s[2]
                sets.append((f"MakeHuman's own: top {1e3*top:+.0f}, chin {1e3*chin:+.0f}, acromion {1e3*ac:+.0f}", (60, 90, 220), curves(dense(Pm, mb["L"], mb["S"], s[2] - 0.2), s), [(top, "top"), (chin, "chin")]))
        out += [panel(sets, sex, f"{who} side profile (midline), mm above the pit of the throat", "side"), panel(sets, sex, f"{who} front silhouette", "front")]
    W = Image.new("RGB", (4 * 900, 1150), (255, 255, 255))
    for i, im in enumerate(out):
        W.paste(im, (i * 900, 0))
    W.save("/mnt/data/hifipushie/headbody/out/neck_overlay.png")
    print("saved")


if __name__ == "__main__":
    main()
