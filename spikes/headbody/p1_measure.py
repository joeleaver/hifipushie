"""p1_measure.py: where the head's size comes from (headbody, Part 1).

The same anthropometric measures, in mm, on GNM's topology wherever it is:
  - GNM's OWN evaluation (template, female / male class mean, each model's identity): GNM's units, no body
  - MakeHuman's head as onemesh.bound carries GNM's vertices on it (the body's own head)
  - the head as BUILT on each model (onemesh.head_rest: gnm_world)
plus each body's stature and heads-per-stature, and the carry scale (built head / GNM's own evaluation).

Measures (GNM frame: Y up, +Z forward; or world: Z up, -Y forward; `axes` says which):
  head_h   vertex - menton (top of the skin to the chin landmark, lm 8)        ANSUR "menton to top of head"
  breadth  the skull's greatest width above the eye line, ears left out         ANSUR "head breadth"
  length   glabella - opisthocranion (brow's front to the back of the skull)   ANSUR "head length"
  bizyg    greatest width of the face between the eye line and the nose base, ears left out
  face_h   sellion (lm 27) - menton (lm 8)                                      ANSUR "menton-sellion length"
  ipd      eye centres apart
  ball     scleral radius
"""
import json
import sys

import numpy as np

from hifipushie import base as B
from hifipushie import blockin as bi
from hifipushie import humans, onemesh, store

g = B._gnm_data()
SKIN = np.asarray(g["skin"], bool)
EXT = np.asarray(g["groups"]["skin_exterior"]) > 0.5
EARS = np.asarray(g["groups"]["ears"]) > 0.5
LM = g["lm68"]
Vt = g["template_vertex_positions"].astype(float)
Jt = g["template_joint_positions"].astype(float)
IDN = [str(n) for n in g["identity_names"]]


def lm(V, i):
    return sum(float(w) * V[int(v)] for v, w in zip(LM[i][0::2], LM[i][1::2]))


def measures(V, eyes, up, fwd):
    """V: every GNM vertex (17821, 3) in any frame; up / fwd unit vectors of that frame; eyes (2, 3)."""
    up, fwd = np.asarray(up, float), np.asarray(fwd, float)
    side = np.cross(up, fwd)
    m = SKIN & EXT & ~EARS
    X = V[m]
    u, f, s = X @ up, X @ fwd, X @ side
    eye_u = float(np.mean(eyes @ up))
    men, sel, sn = lm(V, 8), lm(V, 27), lm(V, 33)
    top = float(u.max())
    skull = u > eye_u + 0.01 * 0  # above the eye line
    out = {"head_h": top - float(men @ up),
           "breadth": float(np.ptp(s[skull])),
           "face_h": float(np.linalg.norm(sel - men)),
           "ipd": float(np.linalg.norm(eyes[0] - eyes[1]))}
    brow = (u > float(sel @ up)) & (u < float(sel @ up) + 0.03) & (np.abs(s - float(np.mean(eyes @ side))) < 0.01)
    out["length"] = float(f[brow].max() - f[skull].min())
    band = (u < eye_u) & (u > float(sn @ up)) & (f > float(np.mean(eyes @ fwd)) - 0.06)
    out["bizyg"] = float(np.ptp(s[band]))
    out["top"] = top
    out["chin"] = float(men @ up)
    return out


def gnm_eval(ident: dict | None):
    ci = B._gnm_coeffs(g["identity_names"], ident or {})
    V = Vt + np.tensordot(ci, g["vertex_identity_basis"], 1)
    J = Jt + np.tensordot(ci, g["joint_identity_basis"], 1)
    return V.astype(float), J.astype(float)


def ball(V, J):
    return float(np.mean([np.median(np.linalg.norm(V[m_] - J[2 + i], axis=1)) for i, m_ in enumerate(g["eye"])]))


def row(name, M, extra=""):
    mm = lambda k: f"{1000 * M[k]:6.1f}"  # noqa: E731
    print(f"{name:34s} head_h {mm('head_h')} breadth {mm('breadth')} length {mm('length')} bizyg {mm('bizyg')} "
          f"face_h {mm('face_h')} ipd {mm('ipd')} {extra}")


def similarity(A, Bp):
    a, b = A - A.mean(0), Bp - Bp.mean(0)
    return float(np.sqrt((b ** 2).sum() / (a ** 2).sum()))


UPG, FWG = [0, 1, 0], [0, 0, 1]
UPW, FWW = [0, 0, 1], [0, -1, 0]


def main():
    D = bi.data()
    res = {}
    print("== GNM's own evaluation (its units; no body)")
    print("template extent (m): x %s y %s z %s; joints (neck, head, eye L, eye R):\n%s" % (
        np.round([Vt[:, 0].min(), Vt[:, 0].max()], 4), np.round([Vt[:, 1].min(), Vt[:, 1].max()], 4),
        np.round([Vt[:, 2].min(), Vt[:, 2].max()], 4), np.round(Jt, 4)))
    for nm, c in (("GNM template", None), ("GNM female class mean", D["m_f"]), ("GNM male class mean", D["m_m"])):
        ident = {} if c is None else {f"head_{i:03d}": float(x) for i, x in enumerate(np.asarray(c)[:170])}
        V, J = gnm_eval(ident)
        M = measures(V, J[2:4], UPG, FWG)
        M["ball"] = ball(V, J)
        res[nm] = M
        row(nm, M, f"ball {1000 * M['ball']:.2f}")

    print("\n== MakeHuman's own head (GNM's vertices bound on the body's surface), stature, heads per stature")
    bodies = {"MH male 25 (default height)": {"age": 25, "sex": 1.0}, "MH female 25 (default height)": {"age": 25, "sex": 0.0},
              "MH neutral 25": {"age": 25, "sex": 0.5}}
    models = [a for a in sys.argv[1:]]
    for mname in models:
        bodies[f"{mname} body"] = onemesh.body_params(store.load(mname)["base"])
    io_scale = onemesh._reference()["io_scale"]
    print(f"asset io (MakeHuman reference eyes apart, GNM template eyes apart): {onemesh.asset()['io']}  io_scale {io_scale:.4f}")
    print("reference body:", json.loads(str(onemesh.asset()["reference"])))
    for nm, params in bodies.items():
        bd = onemesh.bound(params)
        P = bd["P"]
        stat = float(P[:, 2].max() - P[:, 2].min())
        M = measures(bd["B"], bd["eyes"], UPW, FWW)
        res[nm] = {**M, "stature": stat, "k": bd["k"]}
        row(nm, M, f"stature {1000 * stat:.0f} heads {stat / M['head_h']:.2f}  bound k {bd['k']:.4f} -> head scale s = k x io_scale = {bd['k'] * io_scale:.4f}")

    print("\n== the head as BUILT on each model, against GNM's own evaluation of the same identity")
    for mname in models:
        sp = store.load(mname)
        base = sp["base"]
        hd = onemesh.head_desc(base)
        ht = onemesh.head_rest(base)
        tpl = onemesh.template(base)
        P = tpl["P"]
        stat = float(P[:, 2].max() - P[:, 2].min())
        W = ht["gnm_world"]
        eyes = np.array(ht["eyes"])
        M = measures(W, eyes, UPW, FWW)
        ident = {k: v for k, v in (base["head"].get("identity") or {}).items()}
        Vg, Jg = gnm_eval(ident)
        Mg = measures(Vg, Jg[2:4], UPG, FWG)
        fade = onemesh.neck_fade()
        hm = np.asarray(g["groups"]["hockey_mask"]) > 0.5
        k_face = similarity(Vg[hm], W[hm])
        full = SKIN & EXT & (fade > 0.999)
        k_head = similarity(Vg[full], W[full])
        hs = float(hd["bound"].get("head_size", 1.0))
        res[mname] = {**M, "stature": stat, "k_face": k_face, "k_head": k_head, "s": hd["scale"], "head_size": hs,
                      "eye_r": float(ht["eye_r"]), "gnm": Mg}
        row(mname + " (built)", M, f"stature {1000 * stat:.0f} heads {stat / M['head_h']:.2f}")
        row(mname + " (GNM's own, same identity)", Mg)
        print(f"    carry: face (hockey mask) {k_face:.4f}, whole head above the neck fade {k_head:.4f}; hd.scale s {hd['scale']:.4f}, "
              f"style head_size {hs}, gnm_base {base['head'].get('gnm_base')}, user head.scale {base['head'].get('scale')}, "
              f"ball r {1000 * ht['eye_r']:.2f} mm; a body with GNM's head at 1.0 and the same heads-per-stature would stand "
              f"{1000 * stat / k_head:.0f} mm; at ANSUR's 7.5 heads: {7.5 * Mg['head_h'] * 1000:.0f} mm")
    json.dump(res, open("/mnt/data/hifipushie/headbody/out/p1.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
