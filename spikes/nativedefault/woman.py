"""woman.py: headbody's class-mean woman (hb_r_woman: GNM's female class mean, native attach, flagged NECK CONFLICT) BEFORE |
AFTER the neck's anthropometric hold (solve_report.neck_move to ANSUR's mean for her sex and stature: what block_in_solve's
neck row does when no picture is there to disagree). Model nd_w1; attach reports; clay tiles + a sheet
workspace/human_renders/nd_01_neck_prior_woman.png. Run through heavy.sh."""
import copy, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import blockin as bi, onemesh, server, solve_report as sr, store

OUT = "/mnt/data/hifipushie/nativedefault/out"
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
src = "hb_r_woman"
sp0 = store.load(src)
ns = onemesh.native_size(sp0["base"])
c = bi.identity(sp0)
L0 = sr.neck_girth(c)[0]
t, sig = ns["neck"] / ns["size"], ns["neck_sd"] / ns["size"]
# the PRIOR with no picture to disagree: min |dc|^2 + ((girth - t) / sig)^2 with the size held = a share of the way
G = abs(t - L0) / sr.neck_move(c, t, hold=0.0)["cost"]          # m of girth per unit |dc| (size held)
tp = L0 + (t - L0) * G ** 2 / (G ** 2 + sig ** 2)
MODELS = [(src, "BEFORE (GNM's class-mean neck)")]
for dst, tgt, hold, lab in (("nd_w2", tp, 0.0, "AFTER, the DEFAULT: ANSUR's prior (mean +- sd), no picture"), ("nd_w1", t, 5.0, "neck=\"held\": pinned at ANSUR's mean, face held")):
    sp = copy.deepcopy(sp0)
    m = sr.neck_move(c, tgt, hold=hold)
    bi.set_identity(sp, c + m["dc"])
    store.save(dst, sp, "nativedefault: the class-mean woman, " + lab, checked=False)
    print(f"{dst}: neck_move {1e3 * m['girth0']:.0f} -> {1e3 * m['girth']:.0f} GNM mm, |dc| {m['cost']:.2f}; moved most:", [(a, round(b, 2), u) for a, b, u in m["moved"]])
    MODELS.append((dst, lab))
reps = {}
for nm, _ in MODELS:
    reps[nm] = onemesh.attach_report(store.load(nm)["base"])
    print("==", nm, "\n" + reps[nm]["text"])
if "--norender" in sys.argv:
    sys.exit()
T = 620
tiles = {}
for nm, _ in MODELS:
    r = reps[nm]
    zc = r["stature"] - r["head_height"] - 0.03
    for v in ("front", "side", "three_quarter"):
        p = f"{OUT}/w_{nm}_{v}.png"
        server.look(nm, views=[v], size=T, resolution=220, shading="clay", paint=False, focus=[0, -0.03, zc], zoom=3.4 * r["stature"] / 1.7, save=p)
        tiles[(nm, v)] = Image.open(p).convert("RGB").resize((T, T))
W = Image.new("RGB", (3 * T + 40, len(MODELS) * (T + 85) + 70), (250, 250, 250))
d = ImageDraw.Draw(W)
d.text((20, 10), "CLASS-MEAN WOMAN (GNM female mean, native head, 1.59 m body): the neck's anthropometric prior", font=F(30), fill=(0, 0, 0))
for i, (nm, lab) in enumerate(MODELS):
    r = reps[nm]
    y = 60 + i * (T + 85)
    ng = next(c_ for c_ in r["checks"] if c_["name"] == "neck girth")
    d.text((20, y), f"{lab}: head's neck {1e3 * r['neck']['head']:.0f} mm, body's own {1e3 * r['neck']['body']:.0f} ({100 * r['neck_conflict']:+.0f} %); "
                    f"ANSUR {1e3 * ng['expected']:.0f} +- {1e3 * ng['sd']:.0f} ({ng['z']:+.1f} sd)", font=F(22), fill=(0, 90, 30))
    fl = [f for f in r["flags"] if f.startswith("NECK")]
    d.text((20, y + 34), ("FLAG: " + fl[0][:150]) if fl else "no neck flag", font=F(17), fill=(170, 30, 30) if fl else (0, 90, 30))
    for j, v in enumerate(("front", "three_quarter", "side")):
        W.paste(tiles[(nm, v)], (20 + j * T, y + 64))
W.save("/home/joe/dev/hifipushie/workspace/human_renders/nd_01_neck_prior_woman.png")
print("sheet: workspace/human_renders/nd_01_neck_prior_woman.png")
