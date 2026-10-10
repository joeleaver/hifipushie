"""itemcover.py <model> [what=id,expr,ict] [step=2]: is the likeness checklist COMPLETE? (faces5; Joe: "I'm not even sure
those checklist items are comprehensive or complete.") Every candidate face direction (GNM's 170 identity comps, the
eye-region and lower-face expression comps, ICT's 100 carried modes) is put on the model's head at -step / +step (its own
sd) as a LINEAR move of the one mesh's head vertices (GNM basis carried through the head's placement: s R (B - joint
mean), faded as the head is), and every checklist item is read on the model side (likeness.compare's model readings:
the clay renders through the reference's fixed cameras, the detector on them, contours, shading) at both. A direction
whose largest item change is under the item's tolerance is a GAP: no item sees it. Ranked by the direction's perceptual
effect (perc.py: 1 - cos of the face-ID embedding between -1 and +1 sd, from faces4's out/perc/*.json; ICT modes measured
here). Writes out/coverage_<what>.json and prints the table (direction, effect, best item and its change / tol, gap?).
Also: the noise floor (the camera turned 0.5 deg: what each item moves when nothing about the face does)."""
import copy
import json
import os
import sys
from pathlib import Path

import numpy as np

from hifipushie import headfit

headfit.N = 170
from hifipushie import base as basemod, humanfit, likeness, onemesh, store  # noqa: E402

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
model = sys.argv[1]
WHAT = (sys.argv[2] if len(sys.argv) > 2 else "id,expr,ict").split(",")
STEP = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
LIMIT = int(os.environ.get("LIMIT", "0"))
g = basemod._gnm_data()
spec = store.load(model)
base = spec["base"]
st = humanfit.state(base)
mesh0 = likeness.model_mesh_from_state(st)
refs = json.loads((store.HOME / model / "human_refs.json").read_text())
photos = likeness.photo_sides(likeness._refs(model))
cams = refs["cameras"]
tpl, c = st["tpl"], st["head"]["carry"]
R, s = np.asarray(c["R"], float), float(c["s"])
gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
fade = np.asarray(onemesh.asset()["g_fade"], float)
hv = np.flatnonzero(gid >= 0)
hg = gid[hv]
fw = fade[hg][:, None]
hg_ = headfit._gnm()
jm_all = None


def moved_mesh(D, eye_d=None):
    """mesh0 with a GNM-frame vertex field D (N_gnm, 3) applied to the head (carried, faded), landmarks too."""
    m = dict(mesh0)
    V = np.asarray(mesh0["V"], float).copy()
    jm = eye_d.mean(0) if eye_d is not None else np.zeros(3)
    V[hv] += fw * (s * (D[hg] - jm) @ R.T)
    m["V"] = V
    L = np.asarray(mesh0["L"], float).copy()
    for i, r in enumerate(g["lm68"]):
        L[i] += s * (sum(float(w) * D[int(v)] for v, w in zip(r[0::2], r[1::2])) - jm) @ R.T
    if eye_d is not None:
        L[68:70] += s * (eye_d - jm) @ R.T
    m["L"] = L
    if eye_d is not None:
        fwd = np.asarray(st["head"].get("forward", [0, -1, 0]), float)
        r_ = float(st["head"].get("eye_r", 0.012))
        m["eyes"] = [likeness._sphere(np.asarray(cc) + s * (e - jm) @ R.T, r_ * 0.985, fwd)
                     for cc, e in zip(st["head"]["eyes"], eye_d)]
    return m


def items(mesh):
    cmp = likeness.compare(model, base, photos=photos, cameras=cams, mesh=mesh)
    out = {}
    for r in cmp["rows"]:
        b = r.get("model")
        if isinstance(b, float) and np.isfinite(b):
            out[f"{r['id']}@{r['view']}"] = (b, float(r["tol"]) if r.get("tol") else float("nan"))
    return out


def change(Dp, Dm, ep=None, em=None):
    a, b = items(moved_mesh(Dp, ep)), items(moved_mesh(Dm, em))
    ch = {k: (abs(a[k][0] - b[k][0]) / 2, a[k][1]) for k in a if k in b}
    return ch


def directions():
    IB = np.asarray(g["vertex_identity_basis"], float)
    JB = np.asarray(g["joint_identity_basis"], float)
    names = [str(x) for x in g["identity_names"]]
    if "id" in WHAT:
        for i, n in enumerate(names):
            if n.startswith("head"):
                yield n, IB[i], JB[i][2:4]
    if "expr" in WHAT:
        EB = np.asarray(g["expression_basis"], float)
        en = [str(x) for x in g["expression_names"]]
        for k in range(20):
            a, b = en.index(f"left_eye_region_{k:03d}"), en.index(f"right_eye_region_{k:03d}")
            yield f"eyes_expr_{k:03d}", EB[a] + EB[b], None
        for k in range(30):
            yield f"lower_face_{k:03d}", EB[en.index(f"lower_face_region_{k:03d}")], None
    if "ict" in WHAT:
        M = np.load(F / "out" / "ict_modes.npz")["modes"].astype(float)
        for k in range(len(M)):
            yield f"ict_{k:02d}", M[k], None


def effects():
    eff = {}
    for f in ("perc_identity.json", "perc_expression.json"):
        p = F / "out" / "perc" / f
        if p.exists():
            for r in json.loads(p.read_text()):
                eff[r["name"]] = r["id"]["sface"]
    p = F / "out" / "perc" / "perc_ict.json"
    if p.exists():
        eff.update(json.loads(p.read_text()))
    return eff


if __name__ == "__main__":
    # noise floor: the same head, cameras turned 0.5 deg
    base_items = items(mesh0)
    cams_t = copy.deepcopy(cams)
    for cm in cams_t:
        cm["yaw"] = float(cm.get("yaw", 0.0)) + 0.5
    cmpn = likeness.compare(model, base, photos=photos, cameras=cams_t, mesh=mesh0)
    noise = {}
    for r in cmpn["rows"]:
        k = f"{r['id']}@{r['view']}"
        if k in base_items and isinstance(r.get("model"), float) and np.isfinite(r["model"]):
            noise[k] = abs(r["model"] - base_items[k][0])
    print(f"{len(base_items)} item readings on {model}; noise floor (0.5 deg turn) median "
          f"{np.median([noise[k] / base_items[k][1] for k in noise if base_items[k][1] > 0]):.3f} tol", flush=True)
    eff = effects()
    rows = []
    for n_, (nm, D, E) in enumerate(directions()):
        if LIMIT and n_ >= LIMIT:
            break
        ch = change(STEP * D, -STEP * D, None if E is None else STEP * E, None if E is None else -STEP * E)
        sc = {k: (v / t if t > 0 else 0.0) for k, (v, t) in ch.items()}
        sn = {k: (ch[k][0] / max(noise.get(k, 0.0), 1e-9)) for k in ch}
        top = sorted(sc, key=lambda k: -sc[k])[:3]
        rows.append({"dir": nm, "effect": eff.get(nm), "best": [(k, round(sc[k], 2), round(sn[k], 1)) for k in top],
                     "max_tol": float(sc[top[0]]) if top else 0.0, "n_items_over": int(sum(v > 1 for v in sc.values()))})
        r = rows[-1]
        print(f"{nm:18s} effect {r['effect'] if r['effect'] is not None else float('nan'):.4f} | best "
              + ", ".join(f"{k} {a:.2f} tol ({b:.0f}x noise)" for k, a, b in r["best"])
              + f" | items past tol {r['n_items_over']}{'  GAP' if r['max_tol'] < 1 else ''}", flush=True)
    (F / "out" / f"coverage_{'_'.join(WHAT)}.json").write_text(json.dumps({"noise": noise, "rows": rows}, default=float))
