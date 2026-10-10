"""macrostudy.py <out png> [base model]: faces6 MACRO STAGE study (Joe: "learn how to better approach the macros before
we do fine detail work in GNM"). For humanmacro's 37 macros (free mode: humanmacro.direction, the population's
conditional mean per +1 sd, 120 comps):
  - each direction against GNM's OWN sex difference (the semantic sampler's female / male class means, the audit's
    cvae_stats): cosine, and the macro's value on the female / male class means (humanmacro.read, in population sd);
  - the macros' share of the sampler's sex difference (least squares of d on the 37 directions);
  - a sheet: the mean face (identity 0 on <base model>'s body and head keys, local layers stripped) at -2 / +2 sd
    along each macro, whole-face clay (AO + soft key, hair cap, thin brows) through the base model's front and 3/4
    cameras.
Writes the sheet and $F/out/macrostudy.json."""
import copy
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import gates
import wholeclay as WC
from hifipushie import humanfit, humanmacro as hm_, likeness, store

F = os.environ.get("F", "/mnt/data/hifipushie/faces6")
TS = int(os.environ.get("TS", "150"))
Z = float(os.environ.get("Z", "2.0"))


def base_of(m):
    sp = store.load(m)
    b = copy.deepcopy(sp["base"])
    for k in ("sliders", "warp", "fold", "pose"):
        b["head"].pop(k, None)
    return b


def mesh_for(b, c120):
    c = np.zeros(170)
    c[:len(c120)] = c120
    bb = copy.deepcopy(b)
    bb["head"]["identity"] = {f"head_{i:03d}": round(float(v), 5) for i, v in enumerate(c)}
    st = humanfit.state(bb)
    mesh = likeness.model_mesh_from_state(st)
    mesh["C"] = WC.haircap(mesh, st)
    return mesh, st


def tile(mesh, st, cam, box, T):
    im, k = likeness.render(mesh, cam, box, px=2 * T, brows=False, ao=True, shadow=8.0)[:2]
    return WC.draw_brows(im, mesh, cam, box, k).resize((T, T), Image.LANCZOS)


if __name__ == "__main__":
    out = sys.argv[1]
    bm = sys.argv[2] if len(sys.argv) > 2 else "f3_t1"
    os.environ.setdefault("BROW_MM", "2")
    WC.BROW_MM = float(os.environ["BROW_MM"])
    refs = json.loads((store.HOME / bm / "human_refs.json").read_text())
    b = base_of(bm)
    t = hm_.table()
    K = hm_.K
    d = (gates.CV["m_m"] - gates.CV["m_f"])[:K]
    rf, rm = hm_.read(gates.CV["m_f"][:K]), hm_.read(gates.CV["m_m"][:K])
    D = np.stack([hm_.direction(n) for n in hm_.NAMES], 1)   # (K, 37)
    coef = np.linalg.lstsq(D, d, rcond=None)[0]
    share = 1 - np.linalg.norm(d - D @ coef) ** 2 / np.linalg.norm(d) ** 2
    rows = []
    for i, n in enumerate(hm_.NAMES):
        u = D[:, i]
        rows.append({"macro": n, "cos_sex": round(float(u @ d / np.linalg.norm(u) / np.linalg.norm(d)), 3),
                     "female_mean": round(rf[n], 2), "male_mean": round(rm[n], 2),
                     "m_minus_f": round(rm[n] - rf[n], 2), "r2": round(float(t["r2"][i]), 2),
                     "weak": n in t["weak"]})
    rows.sort(key=lambda r: -abs(r["m_minus_f"]))
    for r in rows:
        print(json.dumps(r))
    print(f"the 37 macro directions span {share:.2f} of the sampler's sex difference (|d| {np.linalg.norm(d):.2f}, first {K} comps)")
    json.dump({"rows": rows, "sex_share": share}, open(f"{F}/out/macrostudy.json", "w"), indent=1)
    # sheet
    ref_mesh, ref_st = mesh_for(b, np.zeros(K))
    boxes = []
    for vi in (0, 1):
        cam = refs["cameras"][vi]
        P = humanfit.project(cam, ref_st["L"])
        c = 0.5 * (P.min(0) + P.max(0))
        side = 1.45 * float(np.max(P.max(0) - P.min(0)))
        boxes.append((cam, (c[0] - side / 2, c[1] - side * 0.56, c[0] + side / 2, c[1] + side * 0.44)))
    names = ["(mean)"] + hm_.NAMES
    cols = 6
    bw, bh = 2 * TS + 8, 2 * TS + 22
    rws = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * bw, rws * bh + 20), "white")
    dr = ImageDraw.Draw(sheet)
    dr.text((4, 4), f"mean face (identity 0 on {bm}'s body, local layers off) at -{Z:g} sd (left) / +{Z:g} sd (right) along "
            f"each humanmacro direction; top front, bottom 3/4; fast clay, hair cap, thin brows", fill=(0, 0, 0))
    for j, n in enumerate(names):
        x0, y0 = (j % cols) * bw, 20 + (j // cols) * bh
        mm = {k: m for k, m in (r.values() for r in [])}
        lab = n if n == "(mean)" else f"{n} (m-f {rm[n] - rf[n]:+.2f} sd)"
        dr.text((x0 + 2, y0 + 2), lab, fill=(0, 0, 0))
        for si, s in enumerate((-Z, Z) if n != "(mean)" else (0.0, 0.0)):
            c = np.zeros(K) if n == "(mean)" else s * hm_.direction(n)
            mesh, st = (ref_mesh, ref_st) if n == "(mean)" else mesh_for(b, c)
            for vi, (cam, box) in enumerate(boxes):
                sheet.paste(tile(mesh, st, cam, box, TS), (x0 + si * TS, y0 + 16 + vi * TS))
        print("tile", n, flush=True)
    sheet.save(out)
    print("wrote", out)
