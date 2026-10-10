"""m3look.py [n=8] [seed=0]: random faces from GNM's prior N(0, I) vs the M3 joint prior (out/m3_prior.npz): identity
only, and identity + habitual expression. Same normal draws pushed through each prior's square root (eigen), clay
(perc.render: GNM's head alone, eyes, drawn brows) front and 3/4. Also the face-ID spread: 1 - cos between every pair
of samples within a prior (do prior samples differ like different people do? calibration: random GNM heads 0.24-0.65,
median ~0.44; a 0.5 deg turn 0.014) and the fine-detail roughness (curvature p99 of the sample's skin minus the mean
head's). Writes human_renders/f5_01_prior_samples.png and out/m3_look.json."""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import perc
from hifipushie import faceid

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
R = Path("/home/joe/dev/hifipushie/workspace/human_renders")
n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
out_png = sys.argv[3] if len(sys.argv) > 3 else str(R / "f5_01_prior_samples.png")
P = np.load(os.environ.get("PRIOR", str(F / "out" / "m3_prior.npz")))
J = P["cov"]
NC = int(P["nc"])
hn = [str(x) for x in P["h_names"]]
hidx = [perc.EX_NAMES.index(x) for x in hn]
HC = [i for i, x in enumerate(perc.ID_NAMES) if x.startswith("head")]


def sqrtm(S):
    w, V = np.linalg.eigh(S)
    return V * np.sqrt(np.maximum(w, 0))


rng = np.random.default_rng(seed)
Zc = rng.standard_normal((n, NC))
Zj = np.c_[Zc, rng.standard_normal((n, len(hn)))]
A_c = sqrtm(J[:NC, :NC])
A_j = sqrtm(J)
# (eigen square roots: the same draw maps to different faces under different priors; the rows are populations, not
# the same people)
sets = {"GNM prior N(0, I)": [(z, None) for z in Zc],
        "M3 prior: identity": [(A_c @ z, None) for z in Zc],
        "M3 prior: identity + habitual expression": [((A_j @ z)[:NC], (A_j @ z)[NC:]) for z in Zj]}
if not hn:
    sets.pop("M3 prior: identity + habitual expression")
TAG = os.environ.get("TAG")
if TAG:
    sets[f"{TAG}: identity"] = sets.pop("M3 prior: identity")


def V_of(c, h):
    cf = np.zeros(len(perc.ID_NAMES))
    cf[HC] = c
    e = None
    if h is not None:
        e = np.zeros(len(perc.EX_NAMES))
        e[hidx] = h
    return perc.verts(cf, e)


views = (0.0, 35.0)
tiles, stats = [], {}
for label, items in sets.items():
    row, embs = [], []
    for c, h in items:
        V = V_of(c, h)
        ims = [perc.render(V, y) for y in views]
        row.append(ims)
    E = faceid.embed([ims[0] for ims in row])
    d = [1 - faceid.cosine(E[i]["sface"], E[j]["sface"]) for i in range(n) for j in range(i + 1, n)
         if E[i] is not None and E[j] is not None]
    maha = [float(np.sqrt(c @ c)) for c, _ in items]
    stats[label] = {"id_spread_median": float(np.median(d)), "id_spread_q": [float(x) for x in np.quantile(d, [.1, .9])],
                    "gnm_maha_median": float(np.median(maha))}
    print(label, json.dumps(stats[label]), flush=True)
    tiles.append((label, row))
(F / "out" / "m3_look.json").write_text(json.dumps(stats))
S = 256
W_ = S * len(views) * n
H_ = (S + 20) * len(tiles)
sheet = Image.new("RGB", (W_, H_), (255, 255, 255))
dr = ImageDraw.Draw(sheet)
for r, (label, row) in enumerate(tiles):
    y = r * (S + 20)
    st = stats[label]
    dr.text((6, y + 4), f"{label}   face-ID spread between samples: median {st['id_spread_median']:.2f} "
                        f"(10-90%: {st['id_spread_q'][0]:.2f}-{st['id_spread_q'][1]:.2f}); |c| under GNM's prior median "
                        f"{st['gnm_maha_median']:.1f}", fill=(0, 0, 0))
    for k, ims in enumerate(row):
        for v, im in enumerate(ims):
            sheet.paste(im.convert("RGB").resize((S, S)), ((k * len(views) + v) * S, y + 20))
sheet.save(out_png)
print("wrote", out_png)
