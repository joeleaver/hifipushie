"""geo.py <model> ...: where the model's brow LANDMARKS and its drawn brow HAIR (the skin's brow decal) sit over the
upper lid, seen through the front picture's fitted camera, against the picture's own brow (bm.read). No render.
Per column (inner third / pupil / outer third of the eye, both eyes' mean), mm AT THE MODEL (picture pixels x the
camera's mm/px at the face), over the upper lid margin:
  photo   lower edge / core / top of the hair band (bm.read on the picture)
  lm      the model's GNM brow landmarks (iBUG 17-26) line
  hair    the decal's spine and lower edge: skin_features' placement (centre from the landmarks, - 0.02 io, - drop,
          + lift ..., rotated) laid on the head's vertices along the decal's direction
  hair0   the same with drop / lift / tilt / apart cleared (the landmark placement alone)"""
import json
import sys

import numpy as np
from PIL import Image

import bm
from hifipushie import blockin as bi, humanfit, likeness, lidfold, skin_look, store
from hifipushie.skin import interocular


def col_interp(pts, x):
    o = np.argsort(pts[:, 0])
    return float(np.interp(x, pts[o, 0], pts[o, 1]))


def decal(J, o, side):
    """Decal frame of the brow on `side` (+1 the subject's left): centre, right, up, width, height (m) as skin_features."""
    a_, m_, b_ = (J[f"lm_brow_{k}.L"].copy() for k in ("inner", "mid", "outer"))
    io = interocular(J)
    span = float(np.linalg.norm(b_ - a_))
    width = 1.22 * span
    c = 0.5 * (a_ + b_)
    c[2] = (a_[2] + 2 * m_[2] + b_[2]) / 4 - 0.02 * io
    c[1] = m_[1]
    c[2] -= float(o.get("drop", 0.0))
    li, lo_ = (float(x) for x in (o.get("lift") or (0.0, 0.0)))
    c[2] += 0.5 * (li + lo_)
    c[0] += float(o.get("apart", 0.0))
    d = np.array([0.42, -1.0, 0.12])
    d /= np.linalg.norm(d)
    slope = float(np.degrees(np.arctan2(b_[2] - a_[2], np.linalg.norm((b_ - a_)[:2])))) * float(o.get("arch", 1.0))
    slope += float(o.get("tilt", 0.0)) + float(np.degrees(np.arctan2(lo_ - li, width)))
    up = np.array([0, 0, 1.0])
    up = up - (up @ d) * d
    up /= np.linalg.norm(up)
    right = np.cross(up, d)
    rot = np.radians(slope)
    right, up = np.cos(rot) * right + np.sin(rot) * up, -np.sin(rot) * right + np.cos(rot) * up
    if side < 0:
        M = np.array([-1.0, 1, 1])
        c, right, up = c * M, -(right * M), up * M      # mirrored picture: u runs toward the outer end on both sides
    return c, right, up, width, 0.42 * width


def spine(t, fall):
    return 0.56 - 0.2 * np.sin(np.clip(t / 0.62, 0, 1) * np.pi / 2) + 0.3 * fall * np.clip((t - 0.62) / 0.38, 0, 1) ** 1.6


def half(t, thickness, taper):
    return thickness * (0.03 + 0.14 * np.clip((t + 0.02) / 0.12, 0, 1) * (1 - taper * np.clip((t - 0.25) / 0.75, 0, 1) ** 0.9))


def run(name, photo=None):
    spec = store.load(name)
    rj = bi._refs(name)
    vi = bi._front(rj)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    st = humanfit.state(spec["base"])
    L = st["L"]
    V = np.asarray(st["tpl"]["P"], float)
    mm = likeness._mm_per_px(cam, L[27:48])
    J = skin_look._J(spec)
    img = Image.open(v["image"]).convert("RGB")
    Pm = np.asarray(bi.detect_view(img, v), float)[:, :2]
    ph = bm.read(img, Pm) if photo is None else photo
    kph = lidfold.IRIS_MM / ph["iris_px"]              # the reader's mm (11.7 iris) per picture px
    L2 = humanfit.project(cam, L)
    ob = ((spec.get("skin") or {}).get("hair") or {}).get("brows") or {}
    if not isinstance(ob, dict):
        ob = {}
    fem = 1.0 - float((spec.get("skin") or {}).get("sex", 0.5))
    thick = float(ob.get("thickness", 1.0 - 0.32 * fem))
    out = {"mm_per_px": mm, "iris_model_mm": 2 * 0.51 * 0.985 * float(st["head"].get("eye_r", 0.012)) * 1000,
           "iris_photo_mm_at_model": ph["iris_px"] * mm, "brows": ob, "cols": {}}
    rows = {k: [] for k in ("photo_edge", "photo_core", "photo_top", "lm", "hair_spine", "hair_edge", "hair0_spine", "hair0_edge",
                            "lid_model_vs_photo")}
    # eyes: (inner, outer, upper lid pts, brow pts) in iBUG; subject's right first (as the reader)
    for s, (ci, co, lid, brow, sd) in enumerate(((39, 36, (37, 38), range(17, 22), -1), (42, 45, (43, 44), range(22, 27), +1))):
        pi, po = L2[ci], L2[co]
        lidp = np.array([L2[ci], *[L2[i] for i in lid], L2[co]])
        browp = np.array([L2[i] for i in brow])
        fr = {}
        for key, o in (("hair", ob), ("hair0", {k: x for k, x in ob.items() if k not in ("drop", "lift", "tilt", "apart")})):
            c, right, up, w, h = decal(J, o, sd)
            near = np.linalg.norm(V - c, axis=1) < 0.05
            Q = V[near]
            u, vv = (Q - c) @ right / w + 0.5, 0.5 - (Q - c) @ up / h       # image coords 0..1 (v down)
            t = np.clip((u - 0.04) / 0.92, 0, 1)
            dv = (spine(t, float(o.get("fall", 1.0))) - vv) * h * 1000         # mm the vertex is BELOW the spine (+)... v down: spine - v > 0 = above
            hf = half(t, thick, float(o.get("taper", 0.82))) * h * 1000
            ok = (u > 0.02) & (u < 0.98) & (np.abs(dv) < 12) & (Q[:, 1] < c[1] + 0.012)
            fr[key] = (humanfit.project(cam, Q[ok]), dv[ok], hf[ok])
        for k, f in enumerate(bm.FR):
            x = pi[0] + f * (po[0] - pi[0])
            ylid = col_interp(lidp, x)
            rows["lm"].append((ylid - col_interp(browp, x)) * mm)
            c = ph["eyes"][s]["cols"][k]
            rows["photo_edge"].append(c["edge_mm"] / kph * mm)
            rows["photo_core"].append(c["core_mm"] / kph * mm)
            rows["photo_top"].append(c["top_mm"] / kph * mm)
            # the photo's lid margin vs the model's, along the picture's y at the photo's column
            pim, pom = Pm[lidfold.INNER[s]], Pm[lidfold.OUTER[s]]
            xm = pim[0] + f * (pom[0] - pim[0])
            ym = col_interp(Pm[list(lidfold.UPPER[s])], xm)
            rows["lid_model_vs_photo"].append((ym - ylid) * mm)     # + = the model's lid margin is HIGHER in the picture
            for key in ("hair", "hair0"):
                p2, dv, hf = fr[key]
                sel = np.abs(p2[:, 0] - x) < 2.5 / mm
                if sel.sum() < 4:
                    rows[key + "_spine"].append(np.nan)
                    rows[key + "_edge"].append(np.nan)
                    continue
                # picture y as a function of the offset from the spine (linear fit over the column's vertices)
                A = np.c_[dv[sel], np.ones(sel.sum())]
                co_ = np.linalg.lstsq(A, p2[sel, 1], rcond=None)[0]
                hfm = float(np.median(hf[sel]))
                rows[key + "_spine"].append((ylid - co_[1]) * mm)
                rows[key + "_edge"].append((ylid - (co_[1] + co_[0] * (-hfm))) * mm)
    for k_, vals in rows.items():
        a = np.array(vals, float).reshape(2, 3)
        out["cols"][k_] = np.nanmean(a, 0).round(2).tolist()
    # the brow landmarks' height in the world, over the upper lid landmark (m -> mm), left side
    out["lm_world_mm"] = {k: round(float(J[f"lm_brow_{k}.L"][2] - J["lm_lid_upper.L"][2]) * 1000, 2) for k in ("inner", "mid", "outer")}
    return out, ph


if __name__ == "__main__":
    ph = None
    res = {}
    for name in sys.argv[1:]:
        r, ph = run(name, ph)
        res[name] = r
        print(name, f"mm/px {r['mm_per_px']:.4f} iris model {r['iris_model_mm']:.2f} mm, photo iris at the model {r['iris_photo_mm_at_model']:.2f} mm",
              "brows", json.dumps(r["brows"]))
        for k, vv in r["cols"].items():
            print(f"   {k:20s}", vv)
        print("   lm over lid lm (world)", r["lm_world_mm"], flush=True)
    json.dump(res, open(bm.G + "/geo.json", "w"), indent=1)
