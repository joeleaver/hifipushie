"""det.py: how far MediaPipe's own eye points are from the mesh truth on the dressed validation shots, and where GNM's
lm68 eye corners sit against the visible canthi (all in the eye frame, mm)."""
import json
import os

import numpy as np
from PIL import Image

from hifipushie import blockin_brows as bb, eye_ruler as er, humanfit, likeness, store

G = os.environ["G"] + "/out"
bx = json.load(open(G + "/box.json"))
K, box = bx["K"], bx["box"]
q = bb._inputs("gd_T12")
mm, cam = q["mm"], q["cam"]
R = json.load(open(G + "/rule.json"))
MODELS = dict(s376="gk_s376", s540="gk_s540", s115="gk_s115", s290="gk_s290", s319="gk_s319", s381="gk_s381", s487="gk_s487",
              s562="gk_s562", s650="gk_s650", s96="gk_s96", T12="gd_T12", T30="gd_T30", ev5="gk_ev5s376", fx="gb_fx")
IDX = (dict(c=468, inn=133, out=33, up=159, lo=145, rim=(469, 470, 471, 472)), dict(c=473, inn=362, out=263, up=386, lo=374, rim=(474, 475, 476, 477)))
rows = {}


def add(k, v):
    rows.setdefault(k, []).append(v)


def uv(p, e):
    d = (np.asarray(p, float) - np.asarray(e["c"])) * mm
    fr = e["frame"]
    return np.array([d @ np.asarray(fr["ex"]), -(d @ np.asarray(fr["ey"]))])


for tag in ["photo"] + list(MODELS):
    v = R[tag]
    if tag == "photo":
        P = q["P"]
    else:
        im = Image.open(f"{G}/s_{tag}.png").convert("RGB")
        P = np.asarray(likeness.detect([im])[0], float)[:, :2] / K + box[:2]
    L = None
    if tag != "photo":
        L = humanfit.project(cam, humanfit.state(store.load(MODELS[tag])["base"])["L"])
    for s in (0, 1):
        e = v["read"][s]
        e["frame"] = er.frames(v["read"][0]["c"], v["read"][1]["c"])[s]
        ix = IDX[s]
        dc, di, do, du, dl = (uv(P[ix[k]], e) for k in ("c", "inn", "out", "up", "lo"))
        rdet = float(np.mean([np.linalg.norm(P[i] - P[ix["c"]]) for i in ix["rim"]])) * mm
        if tag == "photo":
            print(f"photo eye {s}: detector iris centre vs circle (u, v) {np.round(dc, 2)}, iris {2 * rdet:.1f} (circle {e['iris']:.1f}); inner {np.round(di, 1)} (ruler {np.round(e['inner'], 1)}) "
                  f"outer {np.round(do, 1)} (ruler {np.round(e['outer'], 1)}) up {du[1]:.2f} (ruler {e['mrd1']:.2f}) lo {dl[1]:.2f} (ruler {-e['mrd2']:.2f})")
            continue
        m = v["model"][s]
        off = (np.array(e["c"]) - np.array(m["c"])) * mm          # reader frame origin - truth origin (picture px -> mm)
        fr = e["frame"]
        sh = np.array([off @ np.asarray(fr["ex"]), -(off @ np.asarray(fr["ey"]))])
        add("det iris centre v", dc[1] + sh[1])
        add("det iris centre u", dc[0] + sh[0])
        add("det iris diameter", 2 * rdet - m["iris"])
        add("det inner u", di[0] + sh[0] - m["inner"][0])
        add("det outer u", do[0] + sh[0] - m["outer"][0])
        add("det width", (do[0] - di[0]) - (m["outer"][0] - m["inner"][0]))
        add("det upper lid at pupil (own centre)", (du[1] - dc[1]) - m["mrd1"])
        add("det lower lid at pupil (own centre)", (dl[1] - dc[1]) + m["mrd2"])
        add("det opening", (du[1] - dl[1]) - (m["mrd1"] + m["mrd2"]))
        a, b = ((36, 39), (42, 45))[s]
        lo_, li_ = uv(L[a], {"c": m["c"], "frame": fr}), uv(L[b], {"c": m["c"], "frame": fr})
        if s == 1:
            lo_, li_ = li_, lo_
        add("lm68 inner corner u - visible", li_[0] - m["inner"][0])
        add("lm68 outer corner u - visible", lo_[0] - m["outer"][0])
        add("lm68 width - visible fissure", abs(lo_[0] - li_[0]) - m["fissure"])
        add("det width - lm68 width", (do[0] - di[0]) - abs(lo_[0] - li_[0]))
print(f"{'measure':40s} {'n':>3s} {'bias':>6s} {'sd':>6s} {'rms':>6s}")
for k, d in rows.items():
    d = np.array(d, float)
    print(f"{k:40s} {len(d):3d} {d.mean():6.2f} {d.std():6.2f} {np.sqrt((d ** 2).mean()):6.2f}")
