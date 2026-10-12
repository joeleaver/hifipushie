"""rval.py <read: ramp|cloth> <truth model> ... [views=0,1] [key=value: RAMP_* overrides]: VALIDATION of a chin / jaw read on
dressed pictures of KNOWN heads through their true cameras (mkhead.py's cz_<tag>_T, solvereads' sx_<tag>_T).
  null     the model in the reader IS the head in the picture: every read's truth is 0 (bias, rms mm, reads per view)
  change   the model = the truth + a known gnm_mm move (chin_width +-5, jaw_width +-6, chin_length +-4, under_chin +-4):
           each read should say o = J (c_true - c_model): slope and correlation of o on that prediction over the reads,
           and the move the reads ALONE give that measure (least squares on the one direction: recovered / true)."""
import os, sys
import numpy as np
from PIL import Image
from hifipushie import face_ruler as fr, blockin as bi, gnm_mm, store

kind = sys.argv[1]
truths = [a for a in sys.argv[2:] if "=" not in a]
kw = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
vsel = [int(x) for x in kw.pop("views", "0,1").split(",")]
for k, v in kw.items():
    setattr(fr, k, float(v))
MOVES = [("chin_width", 5.0), ("chin_width", -5.0), ("jaw_width", 6.0), ("jaw_width", -6.0), ("chin_length", 4.0), ("chin_length", -4.0),
         ("under_chin", 4.0), ("under_chin", -4.0)]
fn = {"ramp": fr._ramp_obs, "cloth": None}[kind]


def views_of(T):
    rj = bi._refs(T)
    out = []
    for vi in vsel:
        v, cam = rj["views"][vi], rj["cameras"][vi]
        f = v["image"]
        if not os.path.basename(f).startswith(("cz_", "sx_")):        # solvereads' truths keep the real pictures as refs
            f = f"/mnt/data/hifipushie/solvereads/synth/{T[:-2]}_{vi}.png"
        out.append({"img": Image.open(f).convert("RGB"), "cam": cam, "kind": fr.kind_of(abs(fr.view_yaw(cam))), "style": "photo", "chin": {kind: True}, "name": os.path.basename(f)})
    return out


tot = {}
for T in truths:
    spec = store.load(T)
    h0 = fr.model_head(spec)
    c0 = bi.identity(spec)
    vs = views_of(T)
    for v in vs:
        ob = fn(h0, v)
        o = np.array([x["o"] for x in ob])
        tot.setdefault(("null", v["kind"]), []).append(o)
        print(f"{T} {v['kind']:5s} NULL: n {len(o):2d}" + (f" bias {o.mean():+.2f} rms {np.sqrt((o ** 2).mean()):.2f} mm (median |o| {np.median(np.abs(o)):.2f})" if len(o) else ""), flush=True)
    for nm, mmv in MOVES:
        d = gnm_mm.direction(nm) * mmv
        h = h0["rebuild"](c0 + d)
        for v in vs:
            v.pop("_light", None)
            ob = fn(h, v)
            if len(ob) < 3:
                print(f"{T} {v['kind']:5s} model {nm} {mmv:+.0f}: n {len(ob)}")
                continue
            o = np.array([x["o"] for x in ob])
            J = np.array([x["J"][:170] for x in ob])
            pred = J @ (-d)
            sl = float(pred @ o / max(pred @ pred, 1e-12))
            cr = float(np.corrcoef(pred, o)[0, 1]) if pred.std() > 1e-6 else float("nan")
            tot.setdefault(("chg", v["kind"], nm), []).append((sl, cr, len(o), float(np.abs(pred).mean())))
            print(f"{T} {v['kind']:5s} model {nm} {mmv:+.0f}: n {len(o):2d} predicted |o| {np.abs(pred).mean():.2f} mm; slope {sl:+.2f} corr {cr:+.2f}; residual rms {np.sqrt(((o - pred) ** 2).mean()):.2f}", flush=True)
print("\nSUMMARY")
for k, v in tot.items():
    if k[0] == "null":
        o = np.concatenate(v)
        if len(o):
            print(f"  null {k[1]:5s}: {len(o)} reads over {len(v)} pictures ({len(o) / len(v):.1f} a picture); bias {o.mean():+.2f} rms {np.sqrt((o ** 2).mean()):.2f} mm; per-picture bias sd {np.std([x.mean() for x in v if len(x)]):.2f}")
        else:
            print(f"  null {k[1]:5s}: no reads in {len(v)} pictures")
    else:
        a = np.array(v)
        print(f"  change {k[1]:5s} {k[2]:12s}: slope {np.average(a[:, 0], weights=a[:, 2] * a[:, 3]):+.2f} (per run {a[:, 0].min():+.2f} .. {a[:, 0].max():+.2f}); corr {np.nanmean(a[:, 1]):+.2f}; reads {a[:, 2].mean():.0f}; predicted |o| {a[:, 3].mean():.2f} mm")
