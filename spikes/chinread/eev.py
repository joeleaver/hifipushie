"""eev.py <tag> [light=top|soft] [engine=cycles|eevee] [moves=1]: the jaw's shading ramp read with the MODEL's picture a
DRESSED render (skin_read's instrument) instead of our clay, validated ACROSS renderers and dressings:
  the "photo"   cz_<tag>_T (stubbled) shot with CYCLES under a light that is NOT the stage's (top / soft), front + 3/4
  the model     cz_<tag>_M = the same head WITHOUT stubble, shot with EEVEE under the light FITTED to that "photo"
                (blockin.photo_lighting, as a real reference would be treated)
  null          face_ruler._ramp_obs(photo vs the model's shot): truth 0 everywhere (bias, rms, reads)
  moves=1       the model = the truth + a known change (chin_length -4, under_chin +4, jaw_square -1.5 sd, chin_width -5):
                slope and correlation of the reads on J (c_true - c_model)   (a new stage per change: ~3 min each)
Pictures in /mnt/data/hifipushie/chinread/synth/cz_<tag>_cy<light>_<vi>.png, the model's shots beside them."""
import copy, json, os, sys
import numpy as np
from PIL import Image
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
import stage
from hifipushie import blockin as bi, face_ruler as fr, gnm_mm, resources, solve_report as sr, store

S = "/mnt/data/hifipushie/chinread/synth"
tag = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
light, engine = kw.get("light", "top"), kw.get("engine", "cycles")
T = f"cz_{tag}_T"
spec, rj = store.load(T), bi._refs(T)
lt = copy.deepcopy(stage.FRONT_LIGHT)
if light == "soft":
    lt["lights"][0].update({"dir": [0.0, -0.97, 0.24], "energy": 2.2, "angle": 60}); lt["lights"][1]["energy"] = 1.2; lt["world"]["strength"] = 0.9
else:
    lt["lights"][0].update({"dir": [0.15, -0.5, 0.85], "energy": 3.8, "angle": 20}); lt["lights"][1]["energy"] = 0.4; lt["world"]["strength"] = 0.35


def shot(model, cam, f, lighting, eng):
    if not os.path.exists(f):
        w, h = cam["size"]
        with resources.heavy(f"chinread shot {model}", gb=6):
            im = stage.shoot(model, [stage.fitted_frame(cam, [w / 2 - h / 2, 0.0, w / 2 + h / 2, float(h)], "v")], lighting, size=int(h), hair_on=False, engine=eng)["v"]
        x0 = int(round((h - w) / 2))
        bg = Image.new("RGB", im.size, (222, 222, 222))
        bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        bg.crop((x0, 0, x0 + int(w), int(h))).save(f)
    return Image.open(f).convert("RGB")


def model(name, c, views):
    sp = copy.deepcopy(spec)
    bi.set_identity(sp, c)
    sp["skin"]["hair"]["stubble"] = 0
    d = store._dir(name); d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp))
    r2 = copy.deepcopy(rj)
    r2["views"] = views + r2["views"][len(views):]
    r2["blockin"] = {**r2["blockin"], "root": name}
    (d / "human_refs.json").write_text(json.dumps(r2))
    return sp


c0 = bi.identity(spec)
photos, views = [], []
for vi in (0, 1):
    f = f"{S}/cz_{tag}_cy{light}_{vi}.png"
    photos.append(shot(T, rj["cameras"][vi], f, lt, engine))
    views.append({**rj["views"][vi], "image": f})
    print("photo", f, flush=True)
rw = sr.rows()
MOVES = [("null", None, 0.0)] + ([("chin_length", "mm", -4.0), ("under_chin", "mm", 4.0), ("jaw_square", "sd", -1.5), ("chin_width", "mm", -5.0)] if kw.get("moves") == "1" else [])
for nm, unit, amt in MOVES:
    if unit is None:
        c = c0
    elif nm in gnm_mm.NAMES:
        c = c0 + gnm_mm.direction(nm) * amt
    else:
        r = rw["R"][rw["names"].index(nm)]
        c = c0 + r / (r @ r) * amt
    M = f"cz_{tag}_M" + ("" if unit is None else nm[:2] + nm[-2:])
    sp = model(M, c, views)
    head = fr.model_head(sp)
    for vi in (0, 1):
        cam = rj["cameras"][vi]
        fm = f"{S}/{M}_cy{light}_{vi}.png"
        ms = shot(M, cam, fm, stage.photo_light(M, vi), "eevee")
        a = np.asarray(ms, float) / 255.0
        v = {"img": photos[vi], "cam": cam, "kind": fr.kind_of(abs(fr.view_yaw(cam))), "style": "photo", "chin": {"ramp": True},
             "ramp_lum": a @ np.array([0.299, 0.587, 0.114])}
        ob = fr._ramp_obs(head, v)
        o = np.array([x["o"] for x in ob])
        line = f"{tag} {light} {v['kind']:5s} model {nm} {amt:+g}: n {len(o):2d}"
        if len(o):
            line += f" mean {o.mean():+.2f} rms {np.sqrt((o ** 2).mean()):.2f} median |o| {np.median(np.abs(o)):.2f}"
            if unit is not None and len(o) >= 3:
                J = np.array([x["J"][:170] for x in ob])
                pred = J @ (c0 - c)
                line += f"; predicted |o| {np.abs(pred).mean():.2f}; slope {float(pred @ o / max(pred @ pred, 1e-12)):+.2f} corr {float(np.corrcoef(pred, o)[0, 1]):+.2f}; residual rms {np.sqrt(((o - pred) ** 2).mean()):.2f}"
        print(line, flush=True)
