"""decomp.py <src model> <fitted model>: faces6, WHAT MOVED THE FACE. Re-linearises fit5's system at the fitted model's
solution x (identity from its spec, per-picture expression from its fit5.json; run with the SAME env as that fit) and
splits the identity change from the source, dc = x - x0, exactly into one part per evidence term plus the prior's:
  x_new - x0 = (H + P)^-1 [ sum_t (b_t - H_t x0) - P x0 ],    term t's part = (H + P)^-1 (b_t - H_t x0)
(fit5.TERMS: per view, MediaPipe face-oval points / feature points / clicks, the profile contour, contact, border).
Prints per term: |part| (identity), its share of dc (part . dc / |dc|^2), its push on GNM's sex direction (gates.sex_read
units) and the top comps; then dc's biggest comps."""
import json
import os
import sys

import numpy as np
from PIL import Image

import fit5
import gates
import lipborder as LB
from hifipushie import humanfit, humanfit_map as hm, likeness, store

NC, NE = fit5.NC, fit5.NE

if __name__ == "__main__":
    src, fm = sys.argv[1], sys.argv[2]
    c0 = gates.ident(store.load(src))
    c1 = gates.ident(store.load(fm))
    fj = json.loads((store.HOME / fm / "fit5.json").read_text())
    refs = json.loads((store.HOME / fm / "human_refs.json").read_text())
    views = [dict(v) for v in refs["views"]]
    cams = [dict(c) for c in refs["cameras"]]
    nv = len(views)
    names = ["+".join(t) for t in fit5.EXPR]
    ex = [np.array([fj["expr"][f"view{i}"][n] for n in names]) for i in range(nv)]
    x = np.r_[c1, *ex]
    x0 = np.r_[c0, np.zeros(NE * nv)]
    border = None
    if fit5.USE_BORDER:
        img = Image.open([v for v in views if abs(float(v.get("yaw", 0))) < 20][0]["image"]).convert("RGB")
        border = LB.read(img, likeness.detect([img])[0])
    st = humanfit.state(fit5.spec_with(store.load(src), x[:NC])["base"])
    rviews = hm._resolve(st, views)
    fit5.TERMS = {}
    H, b, rep = fit5.system(st, rviews, cams, x, x, border, nv)
    P = np.diag(np.r_[np.ones(NC), np.full(NE * nv, 1.0 / fit5.EXPR_SD ** 2)])
    Hi = np.linalg.inv(H + P)
    xn = Hi @ b
    dc = c1 - c0
    print(f"|c0| {np.linalg.norm(c0):.2f} -> |c1| {np.linalg.norm(c1):.2f}, |dc| {np.linalg.norm(dc):.2f}; re-solve at x: "
          f"|x_new - x| identity {np.linalg.norm(xn[:NC] - x[:NC]):.2f} (0 = x is the fixed point)")
    d = gates.CV["m_m"] - gates.CV["m_f"]
    sexu = lambda v: float(v[:170] @ d / (d @ d) * 2)  # noqa: E731
    print(f"sex_gnm: {gates.sex_read(c0):.2f} -> {gates.sex_read(c1):.2f} (dc's push {sexu(dc):+.2f})")
    parts = {t: Hi @ (v[1] - v[0] @ x0) for t, v in fit5.TERMS.items()}
    parts["PRIOR"] = -Hi @ (P @ x0)
    tot = sum(parts.values())
    print(f"sum of parts vs x_new - x0 (identity): {np.linalg.norm(tot[:NC] - (xn - x0)[:NC]):.3f}")
    rows = []
    for t, v in parts.items():
        ci = v[:NC]
        top = np.argsort(-np.abs(ci))[:5]
        rows.append((float(ci @ dc / (dc @ dc)), t, float(np.linalg.norm(ci)), sexu(ci), [(int(k), round(float(ci[k]), 2)) for k in top]))
    for sh, t, nrm, sx, top in sorted(rows, key=lambda r: -abs(r[0])):
        print(f"{t:26s} share {sh:+.2f}  |part| {nrm:5.2f}  sex {sx:+.2f}  top {top}")
    top = np.argsort(-np.abs(dc))[:12]
    print("dc top comps:", [(int(k), round(float(dc[k]), 2)) for k in top])
    print("dc norm by band 0-9 / 10-39 / 40-119 / 120-169:",
          [round(float(np.linalg.norm(dc[a:b_])), 2) for a, b_ in ((0, 10), (10, 40), (40, 120), (120, 170))])
    np.savez(os.environ.get("F", "/mnt/data/hifipushie/faces6") + f"/out/decomp_{fm}.npz",
             **{t.replace(":", "_"): v for t, v in parts.items()}, dc=dc)
