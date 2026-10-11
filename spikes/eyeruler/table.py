"""table.py <model> ...: the eye ruler's MESH read of models (through gd_T12's fitted front camera) beside the photo's
image read; + the detector's own corner width on the photo and the models' landmark corner width. out/table.json"""
import json
import os
import sys

import numpy as np

from hifipushie import blockin_brows as bb, eye_ruler as er, humanfit, store

G = os.environ["G"] + "/out"
q = bb._inputs("gd_T12")
mm, cam, P = q["mm"], q["cam"], q["P"]
ph = er.read(q["img"], P, mm)
pm = er.mean(ph)
pd = float(np.linalg.norm(np.array(ph[0]["c"]) - np.array(ph[1]["c"])) * mm)


def line(tag, m, pd_, extra=""):
    print(f"{tag:14s} fiss {m['fissure']:5.1f} tilt {m['tilt']:5.1f} in ({m['inner'][0]:6.1f},{m['inner'][1]:5.1f}) out ({m['outer'][0]:5.1f},{m['outer'][1]:5.1f}) "
          f"car {m['caruncle']:4.1f} iris {m['iris']:5.1f} pd {pd_:5.1f} intercanth {pd_ + 2 * m['inner'][0]:5.1f} biocular {pd_ + 2 * m['outer'][0]:5.1f} peak {m['peak_u']:4.1f} {extra}\n"
          f"{'':14s} up {np.round(m['up'], 1)}  lo {np.round(m['lo'], 1)}  open {np.round(m['open'], 1)}\n"
          f"{'':14s} crease {np.round(m['crease'], 1)} brow {np.round(m['brow'], 1)}")


det = [np.linalg.norm(P[a] - P[b]) * mm for a, b in ((33, 133), (362, 263))]
line("PHOTO (read)", pm, pd, f"| detector corner width {np.mean(det):.1f}")
out = {"photo": {"mean": pm, "pd": pd, "detector_width": float(np.mean(det))}}
for name in sys.argv[1:]:
    spec = store.load(name)
    t = er.model(spec, cam)
    m = er.mean(t)
    m["platform"] = np.nanmean([x["platform"] for x in t], 0).tolist()
    m["gap_up"] = np.nanmean([x["gap"]["up"] for x in t], 0).tolist()
    m["gap_lo"] = np.nanmean([x["gap"]["lo"] for x in t], 0).tolist()
    pdm = float(np.linalg.norm(np.array(t[0]["c"]) - np.array(t[1]["c"])) * mm)
    L = humanfit.state(spec["base"])["L"]
    lw = 0.5 * (np.linalg.norm(L[36] - L[39]) + np.linalg.norm(L[42] - L[45])) * 1000
    hd = spec["base"]["head"]
    e = np.linalg.norm(list((hd.get("expression") or {}).values())) if hd.get("expression") else 0.0
    line(name, m, pdm, f"| lm corner width {lw:.1f} |expr| {e:.2f}")
    print(f"{'':14s} platform {np.round(m['platform'], 1)} lining gap up {np.round(m['gap_up'], 2)} lo {np.round(m['gap_lo'], 2)}")
    out[name] = {"mean": m, "pd": pdm, "lm_width": float(lw)}
json.dump(out, open(G + "/table.json", "w"), indent=1)
