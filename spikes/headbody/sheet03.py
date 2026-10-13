"""sheet03.py: workspace/human_renders/hb_03_neck_diagnosis.png: REFERENCE | previous native attach | old attach, rest,
side / front / back, with the measured neck lengths and ANSUR's printed large. Tiles: out/N_<model>_<view>.png."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import headfit, makehuman, onemesh, store
from p1_measure import gnm_eval, lm, SKIN
from p6_overlay import dense, SUPRA, ACRO, row

F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
OUT, REF = "/mnt/data/hifipushie/headbody/out", "/home/joe/dev/hifipushie/workspace/neck_refs"
ANS = {"F": (298.8, 81, "0.184"), "M": (317.6, 86, "0.181")}


def column(Pd, chin_z, lo, hi, at=0.085):
    """How far under the chin's level the shoulder line is, `at` metres out from the centre line (the first height,
    going down, where the silhouette's half width passes it): short = the trapezius rises to the neck high up."""
    zs = np.arange(hi, lo, -0.003)
    for z in zs:
        m = np.abs(Pd[:, 2] - z) < 0.003
        if m.any() and np.abs(Pd[m][:, 0]).max() > at:
            return chin_z - z, at
    return np.nan, at


def numbers(name):
    base = store.load(name)["base"]
    tpl = onemesh.template(base)
    ht = onemesh.head_rest(base)
    P = np.asarray(tpl["P"], float)
    s = P[row[SUPRA]]
    chin = float(ht["lm68"][8][2])
    Pd = dense(P, tpl["L"], tpl["S"], s[2] - 0.05)
    keep = np.abs(Pd[:, 1] - s[1] - 0.05) < 0.2
    col, hw = column(Pd[keep], chin, s[2] - 0.05, chin - 0.03)
    out = {"top": P[:, 2].max() - s[2], "chin": chin - s[2], "col": col, "stature": P[:, 2].max()}
    # GNM's own evaluation of this identity, with its bib: its chin -> pit and its own side column
    V, J = gnm_eval(base["head"].get("identity") or {})
    W = V[SKIN] @ onemesh._RG.T
    ch = lm(V, 8) @ onemesh._RG.T
    mid = W[(np.abs(W[:, 0]) < 0.003) & (W[:, 1] < ch[1] + 0.09) & (W[:, 2] < ch[2] - 0.02)]
    pit = mid[np.argmax(mid[:, 1])]
    gcol, _ = column(W, ch[2], ch[2] - 0.12, ch[2] - 0.03)
    out["gnm_chin_pit"], out["gnm_col"] = ch[2] - pit[2], gcol
    if not onemesh.native(base):
        mb = makehuman.body(onemesh.body_params(base))
        Pm = np.asarray(mb["P"], float)
        sm, cm = Pm[SUPRA], Pm[headfit.table()["lm68"][8]]
        Pmd = dense(Pm, mb["L"], mb["S"], sm[2] - 0.05)
        out["mh"] = {"top": Pm[:, 2].max() - sm[2], "chin": cm[2] - sm[2], "col": column(Pmd[np.abs(Pmd[:, 1] - sm[1] - 0.05) < 0.2], cm[2], sm[2] - 0.05, cm[2] - 0.03)[0]}
    return out


def fit(path, T, box=None):
    im = Image.open(path).convert("RGB")
    if box:
        w, h = im.size
        im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    k = max(T / im.width, T / im.height)
    im = im.resize((int(im.width * k + 1), int(im.height * k + 1)))
    x, y = (im.width - T) // 2, (im.height - T) // 2
    return im.crop((x, y, x + T, y + T))


T = 620
blocks = [("TESS", "F", "nt_N06", "hb_tess", {"side": ("Young_woman_s_neck.jpg", None), "front": ("Female_neck.jpg", (0.05, 0.0, 0.8, 1.0)), "back": ("Sunburnt_neck_and_shoulders.jpg", None)}),
          ("GARRETT", "M", "ng_N05", "hb_garrett", {"side": ("Adam_s_apple_35.jpg", (0.0, 0.0, 0.75, 1.0)), "front": ("Gray1195.png", None), "back": ("Cou.jpg", (0.15, 0.0, 0.85, 1.0))})]
HEAD = 290
ov = Image.open(f"{OUT}/neck_overlay.png").convert("RGB")
WID = 2 * (3 * T + 40) + 20
ov = ov.resize((WID - 40, int((WID - 40) * ov.height / ov.width)))
sheet = Image.new("RGB", (WID, HEAD + 3 * (T + 8) + 110 + ov.height), (250, 250, 250))
d = ImageDraw.Draw(sheet)
for bi_, (who, sex, old, new, refs) in enumerate(blocks):
    x0 = 20 + bi_ * (3 * T + 40)
    no, nn = numbers(old), numbers(new)
    A = ANS[sex]
    d.text((x0, 8), f"{who}: REFERENCE  |  PREVIOUS NATIVE ({new})  |  OLD ATTACH ({old})", font=F(30), fill=(0, 0, 0))
    lines = [
        (f"top of head over the pit of the throat:  ANSUR {A[0]:.0f} mm ({A[2]} of stature)   native {1e3*nn['top']:.0f}   old {1e3*no['top']:.0f}   MakeHuman's own {1e3*no['mh']['top']:.0f}", (0, 0, 0)),
        (f"chin over the pit of the throat:  ANSUR ~{A[1]} (head height from memory)   native {1e3*nn['chin']:.0f}   old {1e3*no['chin']:.0f}   MakeHuman {1e3*no['mh']['chin']:.0f}   GNM's OWN neck {1e3*nn['gnm_chin_pit']:.0f}", (0, 0, 0)),
        (f"=> the head sits {1e3*(nn['chin']-nn['gnm_chin_pit']):.0f} mm above where its own neck base belongs, and GNM's own shoulder slope (its bib) was cut off:", (170, 20, 20)),
        ("   the body's trapezius was pulled DOWN to the ring instead: a column on a shelf.", (170, 20, 20))]
    for i, (t, c) in enumerate(lines):
        d.text((x0, 56 + i * 50), t, font=F(22 if i < 2 else 24), fill=c)
    for r, view in enumerate(("side", "front", "back")):
        y = HEAD + r * (T + 8)
        rf, box = refs[view]
        sheet.paste(fit(f"{REF}/{rf}", T, box), (x0, y))
        d.text((x0 + 6, y + 4), f"REFERENCE {view} ({rf[:28]})", font=F(18), fill=(255, 220, 0))
        for c, m in enumerate((new, old)):
            sheet.paste(fit(f"{OUT}/N_{m}_{view}.png", T, (0.05, 0.03, 1.0, 0.95)), (x0 + (c + 1) * T, y))
            d.text((x0 + (c + 1) * T + 6, y + 4), f"{'PREVIOUS NATIVE' if c == 0 else 'OLD ATTACH'} {view}", font=F(18), fill=(255, 220, 0))
    print(who, {k: (round(1e3 * v) if isinstance(v, float) else v) for k, v in nn.items()}, {k: (round(1e3 * v) if isinstance(v, float) else v) for k, v in no.items()})
d.text((20, HEAD + 3 * (T + 8) + 20), "OUTLINES aligned at the pit of the throat: red = old attach, blue = MakeHuman's own, green = previous native. Front silhouettes: green runs straight down, then a corner and a shelf.", font=F(26), fill=(0, 0, 0))
sheet.paste(ov, (20, HEAD + 3 * (T + 8) + 70))
sheet.save("/home/joe/dev/hifipushie/workspace/human_renders/hb_03_neck_diagnosis.png")
print("saved")
