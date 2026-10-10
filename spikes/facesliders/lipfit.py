"""lipfit.py <model> <out model>: faces5, the first EVIDENCE-DRIVEN fit in GNM alone (Joe: "GNM might have everything we
need built in"; test case = Tess's under-lip shadow, which faces3's coupled + MakeHuman levers could not darken in the
middle alone: hers 0.654 middle / 0.924 sides).

Unknowns z = [c (all 170 identity comps), h (habitual lower-face expression, GNM's lower_face_region_000..NH-1)], the
whole face free. The model's local lip sliders (LIP_SLIDERS) are DROPPED: GNM alone has to make the lips.
Prior: c ~ N(0, Sigma_c) (M3, out/m3_em_tau1.npz; mean 0: the within-sex mean is not applied in this spike), h ~
N(0, EXPR_SD^2) (designed).
Evidence:
  1. every view's calibrated detector points + clicks (humanfit_map / joint.evidence; the lip contours among them:
     the border's shape along its length), through each view's fitted camera (refitted), analytic Jacobians in c and h;
  2. the under-lip shadow (lipshade.read on the DRESSED render through the front camera vs the photo: shadow middle,
     shadow_side), by finite differences on renders ALONG A FEW DIRECTIONS ONLY: the posterior-cheapest moves (under
     evidence 1 + the prior) that change a geometric proxy of the shadow (the lower lip's step over the mentolabial
     sulcus at the middle and at the sides, on GNM's raw mesh). Each direction keeps the points fitted to first order.
Steps: (a) the points alone (Gauss-Newton, cameras refitted) with the sliders dropped; (b) ROUNDS of the shadow along
the directions (renders: 1 + NDIR each round), the points' quadratic cost and the prior carried in the same objective.
Writes <out model> (spec + refs + lipfit.json) and $F/out/lipfit_<out>.png (photo | start | after, front lip crops)."""
import copy
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

from hifipushie import headfit

headfit.N = 170   # all of GNM's head components (headfit._gnm() reads N when first built)

import joint as J0  # noqa: E402
import lipsolve as LV  # noqa: E402
import lipshade as LS  # noqa: E402
from hifipushie import base as basemod, humanfit, humanfit_map as hm, store  # noqa: E402

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
WS = store.HOME
PRIOR = os.environ.get("PRIOR", str(F / "out" / "m3_em_tau1.npz"))
NH = int(os.environ.get("NH", "20"))
EXPR_SD = float(os.environ.get("EXPR_SD", "0.3"))
ROUNDS = int(os.environ.get("ROUNDS", "3"))
NDIR = int(os.environ.get("NDIR", "3"))
LIP_SLIDERS = ("lip_tubercle", "mouth_corner", "lip_lower_width", "mh_lowerlip_width", "mh_lowerlip_middle",
               "mh_lowerlip_volume", "mh_lowerlip_ext", "mh_mouth_angles", "lip_upper_height", "lip_lower_height",
               "lip_upper_roll", "lip_lower_roll", "lip_bow")
KEEP = os.environ.get("KEEP_SLIDERS", "0") == "1"
TOL = {"shadow": 0.04, "shadow_side": 0.03}
FEATS = ("shadow", "shadow_side")
LV.FEATS = FEATS

g = basemod._gnm_data()
EN = [str(x) for x in g["expression_names"]]
HREG = os.environ.get("HREG", "lower_face")   # lower_face | eyes (both eyes' comp k as one habitual variable)
HN = ([(f"lower_face_region_{k:03d}",) for k in range(NH)] if HREG == "lower_face" else
      [(f"left_eye_region_{k:03d}", f"right_eye_region_{k:03d}") for k in range(NH)])
_EBall = np.asarray(g["expression_basis"], float)
EB = np.stack([sum(_EBall[EN.index(x)] for x in t) for t in HN])
IDN = [str(x) for x in g["identity_names"]]
HC = [i for i, x in enumerate(IDN) if x.startswith("head")]
IB = np.asarray(g["vertex_identity_basis"], float)[HC]
TPL = np.asarray(g["template_vertex_positions"], float)
NC = len(HC)


def spec_with(spec, c, h):
    sp = copy.deepcopy(spec)
    b = humanfit._with_identity(sp["base"], c)
    hd = b["head"]
    ex = dict(hd.get("habitual") or {})
    for t, v in zip(HN, h):
        for k in t:
            ex[k] = round(float(v), 5)
    hd["habitual"] = ex   # (base.gnm_head: part of the resting face, sealed with it)
    if not KEEP:
        hd["sliders"] = {k: v for k, v in (hd.get("sliders") or {}).items() if k not in LIP_SLIDERS}
    sp["base"] = b
    return sp


def h_of(spec):
    ex = (spec["base"]["head"].get("habitual") or {})
    return np.array([float(ex.get(t[0], 0.0)) for t in HN])


def expr_basis(st, rows):
    """(NH, n, 3) world move per expression unit of each evidence row."""
    c = st["head"]["carry"]
    R, s = np.asarray(c["R"], float), float(c["s"])
    out = np.zeros((NH, len(rows), 3))
    for i, row in enumerate(rows):
        if row[0] == "v":
            out[:, i] = s * (EB[:, row[1]] * row[2][None, :, None]).sum(1) @ R.T
        elif row[0] == "L":
            r = g["lm68"][row[1]]
            out[:, i] = s * sum(float(w) * EB[:, int(v)] for v, w in zip(r[0::2], r[1::2])) @ R.T
    return out


def point_system(st, views, cams, z, z_lin):
    """Gauss-Newton normal equations of the points' evidence at z (linearised at z_lin's state): (H, b, cost, rms per
    view), cams refitted in place."""
    evs = J0.evidence(st, views)
    n = NC + NH
    H, b = np.zeros((n, n)), np.zeros(n)
    cost, rms = 0.0, []
    for vi, (v, e) in enumerate(zip(views, evs)):
        XB = np.concatenate([e["XB"], expr_basis(st, e["rows"])])        # (n, m, 3)
        X = e["X"] + np.tensordot(z - z_lin, XB, 1)
        cam = cams[vi]
        mm0 = cam["t"][2] / cam["f"] * 1000
        cam = cams[vi] = hm._fit_cam(cam, X, e["uv"], mm0 / e["sig"])
        Rc = humanfit._cam_rot(cam)
        Xc = (X - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
        zz = Xc[:, 2]
        J = np.zeros((len(X), 2, 3))
        J[:, 0, 0] = J[:, 1, 1] = cam["f"] / zz
        J[:, 0, 2] = -cam["f"] * Xc[:, 0] / zz ** 2
        J[:, 1, 2] = -cam["f"] * Xc[:, 1] / zz ** 2
        J = J @ Rc
        wt = (zz / cam["f"] * 1000) / e["sig"]
        r = (e["uv"] - humanfit.project(cam, X)) * wt[:, None]
        a = np.linalg.norm(r, axis=1)
        hw = np.where(a > 2.5, np.sqrt(2.5 / np.maximum(a, 1e-9)), 1.0)
        A = (np.einsum("nij,knj->nik", J, XB) * (wt * hw)[:, None, None]).reshape(-1, n)
        y = A @ z + (r * hw[:, None]).ravel()
        H += A.T @ A
        b += A.T @ y
        cost += float(np.sum((r * hw[:, None]) ** 2))
        rms.append(float(np.sqrt(np.mean(a ** 2))))
    return H, b, cost, rms


def prior_inv():
    Sc = np.load(PRIOR)["cov"][:NC, :NC]
    P = np.zeros((NC + NH, NC + NH))
    P[:NC, :NC] = np.linalg.inv(Sc)
    P[NC:, NC:] = np.eye(NH) / EXPR_SD ** 2
    return P


# --- the shadow's geometric proxy on GNM's raw mesh ------------------------------------------------------------
grp = lambda k: np.asarray(g["groups"][k], float) > 0.5  # noqa: E731
EXT = grp("skin_exterior")
LL = grp("lower_lip_region") & EXT
CH = grp("chin_region") & EXT


def _proxy_sets():
    """Per column (x = 0, +-12 mm; GNM frame: z forward, y up) two FIXED vertex sets chosen on the template: the lower
    lip's 5 front-most vertices, and the 5 deepest of the skin in the 12 mm under the lip's lowest vertex there (the
    mentolabial sulcus). (Re-selecting them per head made the proxy jump: an 8.8 mm 'move' per unit.)"""
    V = TPL
    sets = []
    for x0 in (0.0, 0.012, -0.012):
        lip = np.flatnonzero(LL & (np.abs(V[:, 0] - x0) < 0.002))
        top = lip[np.argsort(V[lip, 2])[-5:]]
        ybot = V[lip, 1].min()
        band = np.flatnonzero((LL | CH) & (np.abs(V[:, 0] - x0) < 0.002) & (V[:, 1] < ybot) & (V[:, 1] > ybot - 0.012))
        deep = band[np.argsort(V[band, 2])[:5]]
        sets.append((top, deep))
    return sets


SETS = _proxy_sets()


def proxy_jac(z):
    """(mid, side) the lower lip's step over the sulcus (front z of the lip set minus the sulcus set's), linear in z:
    exact Jacobian from the bases."""
    Bz = np.concatenate([IB, EB])[:, :, 2]          # (n, N) z-moves
    V0 = TPL + np.tensordot(z[:NC], IB, 1) + np.tensordot(z[NC:], EB, 1)
    p, J = [], []
    for top, deep in SETS:
        p.append(V0[top, 2].mean() - V0[deep, 2].mean())
        J.append(Bz[:, top].mean(1) - Bz[:, deep].mean(1))
    p0 = np.array([p[0], 0.5 * (p[1] + p[2])])
    Jp = np.array([J[0], 0.5 * (J[1] + J[2])])
    return p0, Jp


def main(src, dst):
    spec = store.load(src)
    refs = json.loads((WS / src / "human_refs.json").read_text())
    views = [dict(v) for v in refs["views"]]
    cams = [dict(cm) for cm in refs["cameras"]]
    Pinv = prior_inv()
    c_in = humanfit.identity(spec["base"])
    z0 = np.r_[c_in, h_of(spec)]
    rep = {"src": src, "prior": PRIOR, "nh": NH, "expr_sd": EXPR_SD, "keep_sliders": KEEP}
    # the photo's shadow
    from PIL import Image
    import sheet1
    v0 = refs["views"][LV.VIEW]
    crop = [int(round(c)) for c in sheet1.crop_of(v0)]
    ph = np.asarray(Image.open(v0["image"]).convert("RGB").crop(tuple(crop)).resize((LV.SIZE, LV.SIZE), Image.LANCZOS))
    fp = LV.feats(LS.read(ph))
    W = np.array([1.0 / TOL[k] for k in FEATS])
    imgs = {}

    def shadow(z, tag):
        im = LV.render(spec_with(spec, z[:NC], z[NC:]), src)
        imgs[tag] = im
        return LV.feats(LS.read(im))

    f_in = shadow(np.r_[c_in, h_of(spec)], "start") if KEEP else None
    # (a) the points alone, sliders dropped
    z = z0.copy()
    rviews = None
    for it in range(3):
        sp = spec_with(spec, z[:NC], z[NC:])
        st = humanfit.state(sp["base"])
        if rviews is None:
            rviews = hm._resolve(st, views)
        for _ in range(3):
            H, b, cost, rms = point_system(st, rviews, cams, z, z)
            zn = np.linalg.solve(H + Pinv, b)
            z = zn
        print(f"(a) round {it}: points rms per view {np.round(rms, 2).tolist()} | prior {float(z @ Pinv @ z):.1f}", flush=True)
    st = humanfit.state(spec_with(spec, z[:NC], z[NC:])["base"])
    H, b, cost_a, rms_a = point_system(st, rviews, cams, z, z)
    st0 = humanfit.state(spec["base"])
    _, _, cost_0, rms_0 = point_system(st0, rviews, [dict(cm) for cm in refs["cameras"]], z0, z0)
    rep["points_rms_start"], rep["points_rms_a"] = rms_0, rms_a
    f_a = shadow(z, "points")
    print(f"start (with its sliders) points rms {np.round(rms_0, 2).tolist()}; after (a) {np.round(rms_a, 2).tolist()}; "
          f"shadow photo {fp.round(3)} after (a) {f_a.round(3)}", flush=True)
    # (b) the shadow along the posterior-cheapest proxy directions
    za = z.copy()
    Hp = H + Pinv                                    # the quadratic model of points + prior around za
    hist = [("a", f_a.tolist(), float(za @ Pinv @ za))]
    f_cur = f_a
    for rnd in range(ROUNDS):
        p0, Jp = proxy_jac(z)
        Post = np.linalg.inv(Hp)
        D = Post @ Jp.T                               # (n, 2): mid, side
        D = np.c_[D, D[:, 0] - D[:, 1]][:, :NDIR]
        D /= np.sqrt(np.einsum("ij,jk,ki->i", D.T, Hp, D))[None, :]   # one unit = one unit of the quadratic cost
        Jf = np.zeros((len(FEATS), D.shape[1]))
        step = 1.5
        for j in range(D.shape[1]):
            Jf[:, j] = (shadow(z + step * D[:, j], f"r{rnd}d{j}") - f_cur) / step
            print(f"   d shadow / d dir{j}: {Jf[:, j].round(4)} (proxy move per unit {(Jp @ D[:, j] * 1e3).round(3)} mm)",
                  flush=True)
        # objective in a: |W (f_cur + Jf a - fp)|^2 + (z + D a)^T Hp (z + D a) - 2 b^T (z + D a)  (points + prior)
        gq = D.T @ (Hp @ z - b)
        A = (Jf * W[:, None]).T @ (Jf * W[:, None]) + D.T @ Hp @ D
        rhs = (Jf * W[:, None]).T @ (W * (fp - f_cur)) - gq
        a = np.linalg.solve(A, rhs)
        z = z + D @ a
        f_cur = shadow(z, f"round{rnd}")
        pc = float(z @ Pinv @ z)
        hist.append((f"round {rnd}", f_cur.tolist(), pc))
        print(f"(b) round {rnd}: a {a.round(2)} | shadow {f_cur.round(3)} (photo {fp.round(3)}) | prior {pc:.1f}", flush=True)
    st = humanfit.state(spec_with(spec, z[:NC], z[NC:])["base"])
    _, _, cost_b, rms_b = point_system(st, rviews, cams, z, z)
    rep.update({"photo": fp.tolist(), "start_with_sliders": None if f_in is None else f_in.tolist(), "hist": hist,
                "points_rms_b": rms_b, "maha_c": float(np.sqrt(z[:NC] @ Pinv[:NC, :NC] @ z[:NC])),
                "maha_c_start": float(np.sqrt(c_in @ Pinv[:NC, :NC] @ c_in)), "h": z[NC:].round(3).tolist(),
                "max_c": float(np.abs(z[:NC]).max())})
    print(json.dumps({k: rep[k] for k in ("photo", "points_rms_start", "points_rms_a", "points_rms_b", "maha_c_start",
                                          "maha_c", "max_c")}, default=float))
    d = WS / dst
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(spec_with(spec, z[:NC], z[NC:]), indent=1))
    r2 = dict(refs)
    r2["cameras"] = cams
    (d / "human_refs.json").write_text(json.dumps(r2, indent=1, default=float))
    (d / "lipfit.json").write_text(json.dumps(rep, indent=1, default=float))
    # crops: photo | start (the model's own render, read by lipsolve) | after (a) | final
    from PIL import ImageDraw
    start_im = LV.render(spec, src)
    tiles = [("photo", ph), (f"{src} as is", start_im), ("(a) points, GNM only", imgs["points"]),
             (f"(b) final", imgs[f"round{ROUNDS - 1}"])]
    rows = []
    for lab, im in tiles:
        r = LS.read(im)
        P = LS.rs.detect([im.astype(np.uint8)])[0]["P"]
        box = LS.crop_img(None, P, pad=1.6)
        crp = Image.fromarray(im.astype(np.uint8)).crop(box)
        crp = crp.resize((420, int(420 * crp.height / crp.width)))
        dr = ImageDraw.Draw(crp)
        dr.rectangle([0, 0, 420, 16], fill=(255, 255, 255))
        dr.text((4, 2), f"{lab}: shadow mid {r['shadow']:.3f} sides {0.5 * (r['shadow_u'][0] + r['shadow_u'][2]):.3f}", fill=(0, 0, 0))
        rows.append(crp)
    Wd = sum(t.width for t in rows)
    Hd = max(t.height for t in rows)
    sheet = Image.new("RGB", (Wd, Hd), "white")
    x = 0
    for t in rows:
        sheet.paste(t, (x, 0))
        x += t.width
    p = F / "out" / f"lipfit_{dst}.png"
    sheet.save(p)
    print("wrote", d, p)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
