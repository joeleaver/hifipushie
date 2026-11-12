"""N2e item 5: why a hinge at plan reads less on the faces. Per hinge: the hinge's own read (chain_panels.hinge_read),
the angle between its two panels' normals at the row's middle, its gap (mm), and the Delaunay faces' read
(chain_lay._fold_turns) on the panels' positions as they are (each point at its OWNER panel) and with every face's points
at ONE panel (the face's own: the panel holding all three, else its first point's owner).

  uv run python spikes/n2e_folds.py <run dir> <loaded.pkl>"""
import json
import pickle
import sys

import numpy as np

from hifipushie.chain_lay import _fold_turns
from hifipushie.chain_panels import Panels

run, src = sys.argv[1:3]
d = pickle.load(open(src, "rb"))
k = pickle.load(open(f"{run}/cnet.pkl", "rb"))
c, TH = k["cnet"], k["TH"]
other = {c.names[c.piece[a]] for a, b in c.sew if c.piece[a] != c.piece[b]}
other |= {c.names[c.piece[b]] for a, b in c.sew if c.piece[a] != c.piece[b]}
pan = Panels(c, d["wear"], [p for p in c.names if p not in other])
out = {}
for h in pan.hinges:
    a, b, mid = h["base"], h["turned"], h["mid"][None]
    na, nb = pan.normal(TH[a], a, mid)[0], pan.normal(TH[b], b, mid)[0]
    uv = c.uv[h["row"]]
    gap = np.linalg.norm(pan.place(TH[a], a, uv) - pan.place(TH[b], b, uv), axis=1).max() * 1e3
    out[h["name"]] = {"planned": h["turn_deg"], "hinge_read": round(pan.hinge_read(TH, h)[2], 1),
                      "normals_deg": round(float(np.degrees(np.arccos(np.clip(na @ nb, -1, 1)))), 1),
                      "gap_mm": round(float(gap), 1)}
X = pan.positions(TH)
faces_owner = _fold_turns(c, np.nan_to_num(X), d["wear"])
# (each face at one panel: the panel holding all three points)
member = [set(P["ids"].tolist()) for P in pan.panels]
Xf = np.nan_to_num(X).copy()
got = {}
for bid, f in sorted((d["wear"].get("folds") or {}).items()):
    from hifipushie.chain_lay import _draft_fold
    fd = _draft_fold(c, f, bid)
    vals = []
    for row in fd.get("rows") or []:
        for u, v in zip(row[:-1], row[1:]):
            fs = c.F[(c.F == u).any(1) & (c.F == v).any(1)]
            if len(fs) != 2:
                continue
            ns = []
            for F in fs:
                ks = [q for q, m in enumerate(member) if all(int(x) in m for x in F)]
                q = ks[0] if ks else pan.owner[F[0]]
                P = pan.place(TH[q], q, c.uv[F])
                n = np.cross(P[1] - P[0], P[2] - P[0])
                ns.append(n / max(np.linalg.norm(n), 1e-12))
            vals.append(np.degrees(np.arccos(np.clip(ns[0] @ ns[1], -1, 1))))
    if vals:
        got[bid] = round(float(np.median(vals)), 1)
print(json.dumps({"hinges": out, "faces_owner": faces_owner, "faces_one_panel": got}, indent=0))
