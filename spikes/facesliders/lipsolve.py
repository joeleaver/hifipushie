"""lipsolve.py <dressed model> <out model>: the LIP stage (after the identity and the eyes, like eyesolve.py): the
lower lip's form in depth solved against its SHADING in the photo (lipshade.read: the under-lip shadow at the middle
and toward the corners, the lit pad's roll), photo vs the DRESSED render through the fitted camera and light (the
clay has no cast shadows: the shadow under a pouting lip is mostly cast, and Lambert clay read it 0.78 vs the
photo's 0.41).

Variables (LEVERS, comma list): c:<attribute> = the identity's coupled direction (faceatlas.direction within sex), in
the attribute's sds, prior = its within-sex Mahalanobis cost; s:<slider> = a residual local morph, L2 cost SLIDER_W
per unit. Evidence: FEATS, (photo - render) / TOL. Gauss-Newton, finite differences on renders (front view only, no
hair: ~2.5 min each), ROUNDS rounds. Writes <out model> (the dressed spec with the result), prints features photo /
before / after and the prior. No hand values: the result is the solve's.

Env: VIEW (0), LEVERS, ROUNDS (1), LIGHT (the fitted light json)."""
import copy
import json
import os
import shutil
import sys

import numpy as np

import lipshade as LS
import sheet1
import stage
from hifipushie import faceatlas, store
from shot import light

# (the roll features read the lip's own colour too: the photo's natural lip darkens toward the stomion and the
# corners, the paint doesn't: the first Tess solve chased that with lip_lower_roll -1.9, the opposite of a pout.
# Default: the under-lip shadow alone, on skin)
FEATS = tuple(os.environ.get("FEATS", "shadow,shadow_side").split(","))
TOL = {"shadow": 0.04, "shadow_u0": 0.04, "shadow_u2": 0.04, "shadow_side": 0.03, "roll": 0.06, "roll_u0": 0.08,
       "roll_u4": 0.08}
STEP = {"c": 1.0, "s": 0.5}
SLIDER_W = 1.0
SIZE = 768
VIEW = int(os.environ.get("VIEW", "0"))
LEVERS = os.environ.get("LEVERS", "c:lower_lip_proj,s:lip_lower_roll").split(",")
ROUNDS = int(os.environ.get("ROUNDS", "1"))
SCR = "f2_lipv"


def feats(r):
    d = {"shadow": r["shadow"], "shadow_u0": r["shadow_u"][0], "shadow_u2": r["shadow_u"][2], "roll": r["roll"],
         "roll_u0": r["roll_u"][0], "roll_u4": r["roll_u"][4], "shadow_side": 0.5 * (r["shadow_u"][0] + r["shadow_u"][2])}
    return np.array([d[k] for k in FEATS])


def apply(spec, x):
    sp = copy.deepcopy(spec)
    h = sp["base"]["head"]
    t = faceatlas.table()
    change = {lv.split(":")[1]: v * float(t["sd"][t["index"][lv.split(":")[1]]]) for lv, v in zip(LEVERS, x)
              if lv.startswith("c:") and v != 0}
    if change:
        dc = faceatlas.direction(change)
        for i in range(faceatlas.K):
            k = f"head_{i:03d}"
            h["identity"][k] = float(h["identity"].get(k, 0.0)) + float(dc[i])
    sl = h.setdefault("sliders", {})
    for lv, v in zip(LEVERS, x):
        if lv.startswith("s:") and v != 0:
            nm = lv.split(":")[1]
            o = sl.get(nm, 0.0)
            sl[nm] = [a + v for a in o] if isinstance(o, list) else o + v
    return sp


def render(spec, src):
    d = store.HOME / SCR
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(spec, indent=1))
    shutil.copy(store.HOME / src / "human_refs.json", d / "human_refs.json")
    r = json.loads((d / "human_refs.json").read_text())
    fr = [stage.fitted_frame(r["cameras"][VIEW], sheet1.crop_of(r["views"][VIEW]), "v")]
    im = stage.shoot(SCR, fr, light(), size=SIZE, hair_on=False)["v"]
    return np.asarray(im.convert("RGB"))


def prior_costs():
    """Per lever: the prior's cost of one unit (coupled: within-sex Mahalanobis of the direction; residual: SLIDER_W)."""
    Sw = faceatlas.within_sex()
    Si = np.linalg.pinv(Sw)
    t = faceatlas.table()
    out = []
    for lv in LEVERS:
        k, nm = lv.split(":")
        if k == "c":
            dc = faceatlas.direction({nm: float(t["sd"][t["index"][nm]])})
            out.append(float(dc @ Si @ dc))
        else:
            out.append(SLIDER_W)
    return np.array(out)


def main(src, dst):
    spec = store.load(src)
    r = json.loads((store.HOME / src / "human_refs.json").read_text())
    from PIL import Image
    v = r["views"][VIEW]
    crop = [int(round(c)) for c in sheet1.crop_of(v)]
    ph = np.asarray(Image.open(v["image"]).convert("RGB").crop(tuple(crop)).resize((SIZE, SIZE), Image.LANCZOS))
    fp = feats(LS.read(ph))
    w = np.array([1.0 / TOL[k] for k in FEATS])
    pc = prior_costs()
    print("levers", LEVERS, "prior per unit", pc.round(3))
    x = np.zeros(len(LEVERS))
    f0 = feats(LS.read(render(apply(spec, x), src)))
    hist = [("start", x.copy(), f0)]
    for it in range(ROUNDS):
        J = np.zeros((len(FEATS), len(LEVERS)))
        for j, lv in enumerate(LEVERS):
            xs = x.copy()
            xs[j] += STEP[lv[0]]
            fj = feats(LS.read(render(apply(spec, xs), src)))
            J[:, j] = (fj - f0) / STEP[lv[0]]
            print(f"  d/d {lv}: " + " ".join(f"{k} {g:+.3f}" for k, g in zip(FEATS, J[:, j])))
        A = (J * w[:, None]).T @ (J * w[:, None]) + np.diag(pc)
        b = (J * w[:, None]).T @ (w * (fp - f0)) - pc * x
        x = x + np.linalg.solve(A, b)
        f0 = feats(LS.read(render(apply(spec, x), src)))
        hist.append((f"round {it}", x.copy(), f0))
    print(f"{'':10s}" + " ".join(f"{k:>10s}" for k in FEATS) + "   cost")
    print(f"{'photo':10s}" + " ".join(f"{v_:10.3f}" for v_ in fp))
    for nm, xx, ff in hist:
        cost = float(((w * (fp - ff)) ** 2).sum())
        print(f"{nm:10s}" + " ".join(f"{v_:10.3f}" for v_ in ff) + f"   {cost:.2f}  x {np.round(xx, 3).tolist()}  prior "
              f"{float((pc * xx ** 2).sum()):.2f}")
    out = apply(spec, x)
    d = store.HOME / dst
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(out, indent=1))
    shutil.copy(store.HOME / src / "human_refs.json", d / "human_refs.json")
    (d / "lip_report.json").write_text(json.dumps({"levers": LEVERS, "x": x.tolist(), "photo": fp.tolist(),
                                                   "hist": [[n, xx.tolist(), ff.tolist()] for n, xx, ff in hist],
                                                   "feats": FEATS}, indent=1))
    print("wrote", d)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
