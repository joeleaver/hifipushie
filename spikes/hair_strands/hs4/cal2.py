"""cal2.py <model> <engine> [fit=A,p] [gain=g] [colours=a,b]: how a lit mass of strands renders against the look colour
(after spikes/hair_strands/hs4/cal.py, without its own heavy lock: hair.look takes it). One view on the key's side,
the hair pixels' brighter half in linear RGB vs the colour asked; prints the fit rendered = A x asked^p."""
import json, os, sys
import numpy as np
from PIL import Image
from hifipushie import hair, store

COLOURS = {"black": "#17120f", "dark_brown": "#3a271c", "mid_brown": "#5c3b28", "garrett": "#55504b",
           "light_brown": "#8a6644", "blond": "#b08a55", "grey": "#8f8c88"}
name, engine = sys.argv[1], sys.argv[2]
opt = dict(a.split("=", 1) for a in sys.argv[3:])
fit = [float(v) for v in opt["fit"].split(",")] if "fit" in opt else [1.0, 1.0]
cols = opt["colours"].split(",") if "colours" in opt else list(COLOURS)
VIEW = opt.get("view", "three_quarter_r")
lin = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
hexlin = lambda h: lin(np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0)
rows = {}
for cn in cols:
    c = COLOURS[cn]
    spec = store.load(name)
    spec["hair"]["style"] = "strands"
    lk = {**spec["hair"].get("look", {}), "gap": c, "lit": c, "tip": c, "sheen": c, "vary": 0.0, "tip_amount": 0.0,
          "root": 0.02, "cycles_fit": fit, "grey_amount": 0.0, "grey_locks": 0.0}
    if "gain" in opt:
        lk["eevee_gain"] = float(opt["gain"])
    spec["hair"]["look"] = lk
    kw = dict(engine=engine, views=(VIEW,), size=256, clay=False, spec=spec)
    if engine == "cycles":
        kw.update(samples=48, denoise=False, count=40000)
    sheet, sec, _ = hair.look(name, **kw)
    im = np.asarray(sheet.crop((0, 22, 256, 278)).convert("RGB"), float) / 255
    idp = np.asarray(Image.open(store._dir(name) / f"hair_id_{VIEW}.png").convert("RGB").resize((256, 256), Image.NEAREST), float)
    m = (idp[..., 1] > idp[..., 0] + 60)
    px = lin(im[m])
    lum = px @ [0.2126, 0.7152, 0.0722]
    top = px[lum >= np.percentile(lum, 50)].mean(0)
    rows[cn] = (hexlin(c), top)
    sheet.save(f"{os.environ['D']}/cal_{engine}_{cn}.png")
    print(engine, cn, "asked", np.round(hexlin(c), 4), "got", np.round(top, 4), "ratio", np.round(top / hexlin(c), 2),
          sec, "s", flush=True)
X = np.log(np.concatenate([r[0] for r in rows.values()]))
Y = np.log(np.concatenate([np.maximum(r[1], 1e-5) for r in rows.values()]))
p, a = np.polyfit(X, Y, 1)
print(engine, f"fit: rendered = {np.exp(a):.3f} x asked^{p:.3f}   rms log error {np.sqrt(np.mean((a + p * X - Y) ** 2)):.3f}")
json.dump({k: [v[0].tolist(), v[1].tolist()] for k, v in rows.items()}, open(f"{os.environ['D']}/cal_{engine}.json", "w"))
