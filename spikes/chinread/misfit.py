"""misfit.py <model> [move=<measure>:<amount>,..] [out=<png>]: HOW THE PICTURES TAKE a chin / jaw variant. The model's
identity moved (gnm_mm `mm:` direction for its measures, else the least-norm change of a solve_report row), the cameras
laid on it again (two cameras-first rounds, the head held), then every read's misfit o (picture - model) BEFORE any
identity step: per group n, mean, rms; for the outlines also by region of the head (the vertex that makes the outline:
chin / jaw body / jaw angle / cheek / above), signed (+ = the picture lies outside the model). Nothing is saved."""
import sys, copy
import numpy as np
from hifipushie import face_ruler as fr, blockin as bi, gnm_mm, solve_report as sr, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
moves = [(x.split(":")[0], float(x.split(":")[1])) for x in kw.get("move", "").split(",") if x]
spec = copy.deepcopy(store.load(m))
c = bi.identity(spec)
rw = sr.rows()
for nm, amt in moves:
    if nm in gnm_mm.NAMES:
        c = c + gnm_mm.direction(nm) * amt
    else:
        r = rw["R"][rw["names"].index(nm)]
        c = c + r / (r @ r) * amt
rj = bi._refs(m)
b0 = rj.get("blockin") or {}
head0, views, notes = fr.reference_views(m, lids=True, lips=True, parse="auto", kinds=b0.get("kinds"), readers=b0.get("readers"), chin={"chin_lm": "none"})
head = head0["rebuild"](c)
cam_sd = {kk: tuple(v) for kk, v in fr.PHOTO_CAM_SD6.items()}
res = fr.read(head, views, rounds=1, cam_sd=cam_sd, cam_first=2, adapt=True, tau=0.02)
obs = res["obs"]
o = np.array([ob["o"] for ob in obs])
sp = gnm_mm._space()
T = sp["T"] * 1000
Lt = sp["WL"] @ T
gid = np.asarray(head["gid"], int)


def region(v):
    g = gid[v]
    if g < 0:
        return "body"
    x, y, z = T[g]
    if y < Lt[57, 1]:
        if abs(x) < 22:
            return "chin"
        return "jaw body" if z > Lt[4, 2] + 15 else "jaw angle"
    if y < Lt[29, 1]:
        return "cheek"
    return "above"


print(f"== {m} {moves}: |c| {np.linalg.norm(c):.2f}; chin_width {rw['R'][rw['names'].index('chin_width')] @ c:+.1f} jaw_width {rw['R'][rw['names'].index('jaw_width')] @ c:+.1f} "
      f"gonial {rw['R'][rw['names'].index('gonial_width')] @ c:+.1f} jaw_square {rw['R'][rw['names'].index('jaw_square')] @ c:+.2f}")
G = {}
for i, ob in enumerate(obs):
    G.setdefault((ob["type"], ob["view"]), []).append(i)
for key, ii in sorted(G.items()):
    print(f"  {key[0]:9s} {key[1]:10s} n {len(ii):4d} mean {o[ii].mean():+.2f} rms {np.sqrt((o[ii] ** 2).mean()):.2f}")
    if key[0] == "outline":
        R = {}
        for i in ii:
            R.setdefault(region(obs[i]["v"]), []).append(i)
        print("      " + "; ".join(f"{k} n {len(v)} mean {o[v].mean():+.2f} rms {np.sqrt((o[v] ** 2).mean()):.2f}" for k, v in sorted(R.items())))
tot = np.array([ob["o"] / ob["sig"] for ob in obs])
print(f"  all reads: chi2 / n = {(tot ** 2).mean():.2f} (n {len(obs)})")
