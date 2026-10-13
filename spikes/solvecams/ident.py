"""ident.py <model> [dense=1] [truth=<model>] [tag=<out tag>]: the joint solve's linear system AT a model (its pictures,
its cameras, today's defaults as solve_step passes them), taken apart. Nothing is saved to the model.
 READ BALANCE: per read type and view: count, total weight (sum 1 / sigma^2), residual rms in mm and in sigmas AT the
   model (before any step), the per-group sigma scale `adapt` gives it, its share of the Fisher information on the
   identity (trace of J' W J in the prior's units) and on each camera's yaw / pitch.
 INFLATION: the "nothing forced" factor (cmax 3 sd) with every type in, and with each type left out in turn.
 IDENTIFIABILITY: per camera freedom: its posterior sd under today's prior ("free" and "trust"), from the READS ALONE
   (camera priors off, identity prior kept), the reads-alone sd with each read type left out, and what 1 unit of that
   freedom costs in SHAPE when everything else re-settles (mm of jaw / chin / cheekbone width .. per degree): the
   valley's direction. -> out/ident_<tag>.json"""
import json, sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, gnm_mm, solve_report as sr, store
import common as C

name = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
dense = kw.get("dense", "0") == "1"
tag = kw.get("tag", name + ("_d" if dense else ""))
fr.DENSE = dense
rj = C.refs(name)
c0 = bi.identity(store.load(name))
root = (rj.get("blockin") or {}).get("root")
truth = kw.get("truth")
# the prior's centre = the class mean the block-in started from (a truth model: its set's start)
start = kw.get("start") or (root if root and root != name else None)
off = c0 - bi.identity(store.load(start)) if start else None
cap = {}
solve0 = fr.solve


def spy(obs, head, **k):
    if k.get("cmax"):
        cap["a"] = (obs, head, dict(k))
    return solve0(obs, head, **k)


fr.solve = spy
b0 = rj.get("blockin") or {}
res = fr.compare(name, rounds=1, prior_off=off, cam_sd=fr.PHOTO_CAM_SD6, lids=True, lips=True, anchors="differential", parse="auto",
                 adapt=True, cmax=3.0, cam_done0=np.zeros((len(rj["views"]), 6)), kinds=b0.get("kinds"), readers=b0.get("readers"))
fr.solve = solve0
obs, head, k = cap["a"]
views = k["views"]
kinds = [v["kind"] for v in views]
vname = {v["kind"]: v.get("name", "") for v in views}
types = sorted({ob["type"] for ob in obs})
out = {"model": name, "dense": dense, "n": len(obs), "kinds": kinds, "pictures": vname}
print(f"== {name} dense {dense}: {len(obs)} reads; views {vname}")

# ---- read balance
k0 = {**k, "cmax": None}
base = solve0(obs, head, **k0)
post = base["post"]
Jx, w, pri, n1 = post["Jx"], post["w"], post["pri"], post["n1"]
o = np.array([ob["o"] for ob in obs])
sig = np.array([ob["sig"] for ob in obs])
nc = 6 * len(views)
Fid = (Jx[:, :n1] ** 2) * w[:, None]             # each read's information on each identity component (prior sd 1)
info = Fid.sum(1)
rows = []
print("READ BALANCE (at the model, before a step)")
print(f"{'type':9s} {'view':8s} {'n':>5s} {'sum w':>9s} {'rms mm':>7s} {'rms sig':>7s} {'adapt x':>7s} {'id info %':>9s} {'yaw info %':>10s} {'pitch info %':>12s}")
for t in types:
    for kd in kinds + ["-"]:
        ii = [i for i, ob in enumerate(obs) if ob["type"] == t and ob["view"] == kd] if kd != "-" else [i for i, ob in enumerate(obs) if ob["type"] == t and ob["view"] not in kinds]
        if not ii:
            continue
        ii = np.array(ii)
        r = {"type": t, "view": kd, "n": len(ii), "sum_w": float((1 / sig[ii] ** 2).sum()), "rms_mm": float(np.sqrt((o[ii] ** 2).mean())) if t not in ("hold",) else float("nan"),
             "rms_sig": float(np.sqrt(((o[ii] / sig[ii]) ** 2).mean())), "adapt": float(base["sig_scale"].get((t, kd), 1.0)),
             "id_info": float(100 * info[ii].sum() / info.sum())}
        if kd in kinds:
            vi = kinds.index(kd)
            for nm, j in (("yaw", 4), ("pitch", 5)):
                col = n1 + 6 * vi + j
                tot = ((Jx[:, col] ** 2) * w).sum()
                r[nm + "_info"] = float(100 * ((Jx[ii, col] ** 2) * w[ii]).sum() / max(tot, 1e-12))
        rows.append(r)
        print(f"{t:9s} {kd:8s} {r['n']:5d} {r['sum_w']:9.0f} {r['rms_mm']:7.2f} {r['rms_sig']:7.2f} {r['adapt']:7.2f} {r['id_info']:9.1f} {r.get('yaw_info', float('nan')):10.1f} {r.get('pitch_info', float('nan')):12.1f}")
out["balance"] = rows

# ---- inflation
def relax_of(sel):
    o_ = [ob for ob in obs if sel(ob)]
    t_ = solve0(o_, head, **k)
    return float(t_["relax"]), float(np.abs(np.asarray(head["c"], float) + t_["dc"]).max()), float(np.linalg.norm(t_["dc"]))


print("INFLATION (cmax 3 sd): sigma factor, largest component after, |dc|")
infl = {"all": relax_of(lambda ob: True)}
print(f"  all reads: x{infl['all'][0]:.2f}, {infl['all'][1]:.2f} sd, |dc| {infl['all'][2]:.2f}")
t1 = solve0(obs, head, **k0)
cc = np.asarray(head["c"], float) + t1["dc"]
print(f"  without the cap: largest component {np.abs(cc).max():.2f} sd (component {int(np.abs(cc).argmax())}), {int((np.abs(cc) > 3).sum())} past 3 sd, |dc| {np.linalg.norm(t1['dc']):.2f}")
infl["uncapped"] = (float(np.abs(cc).max()), int((np.abs(cc) > 3).sum()), float(np.linalg.norm(t1["dc"])))
for t in types:
    if t == "hold":
        continue
    infl["no " + t] = relax_of(lambda ob, t=t: ob["type"] != t)
    print(f"  without {t:9s}: x{infl['no ' + t][0]:.2f}, {infl['no ' + t][1]:.2f} sd, |dc| {infl['no ' + t][2]:.2f}")
for kd in kinds:
    infl["no view " + kd] = relax_of(lambda ob, kd=kd: ob["view"] != kd)
    print(f"  without view {kd:8s}: x{infl['no view ' + kd][0]:.2f}, {infl['no view ' + kd][1]:.2f} sd, |dc| {infl['no view ' + kd][2]:.2f}")
out["inflation"] = infl

# ---- identifiability
rw = sr.rows()
MEAS = ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "chin_length", "chin_forward", "eyes_forward", "skull_width")
Rm = np.array([rw["R"][rw["names"].index(m)] for m in MEAS])
P = Jx.shape[1]
CN = ("dx mm", "dy mm", "scale %", "roll deg", "yaw deg", "pitch deg")


def info_matrix(wsel, cam_prior=None):
    p = pri.copy()
    if cam_prior is not None:
        p[n1:n1 + nc] = cam_prior
    return (Jx * (w * wsel)[:, None]).T @ Jx + np.diag(1.0 / p ** 2)


ones = np.ones(len(obs))
WIDE = np.full(nc, 1e3)
A_free = info_matrix(ones)
A_trust = info_matrix(ones, pri[n1:n1 + nc] / 3.0)
A_data = info_matrix(ones, WIDE)
Ai_free, Ai_trust, Ai_data = (np.linalg.inv(A) for A in (A_free, A_trust, A_data))
ident = []
print("IDENTIFIABILITY: per camera freedom: sd today (free / trust) | reads alone | reads alone without each type | shape per unit (mm)")
for vi, kd in enumerate(kinds):
    for j in range(6):
        col = n1 + 6 * vi + j
        rest = np.array([q for q in range(P) if q != col])
        # everything else re-settled when this freedom is moved by 1 unit (reads alone on the cameras, prior on identity)
        d = -np.linalg.solve(A_data[np.ix_(rest, rest)], A_data[rest, col])
        full = np.zeros(P); full[rest] = d; full[col] = 1.0
        dm = Rm @ full[:n1]
        e = {"view": kd, "freedom": CN[j], "prior": float(pri[col]), "sd_free": float(np.sqrt(Ai_free[col, col])), "sd_trust": float(np.sqrt(Ai_trust[col, col])),
             "sd_reads": float(np.sqrt(Ai_data[col, col])), "shape": {m: float(x) for m, x in zip(MEAS, dm)}, "dc_per_unit": float(np.linalg.norm(full[:n1])), "without": {}}
        for t in types:
            if t == "hold":
                continue
            sel = np.array([ob["type"] != t for ob in obs], float)
            e["without"][t] = float(np.sqrt(np.linalg.inv(info_matrix(sel, WIDE))[col, col]))
        ident.append(e)
        print(f"  {kd:8s} {CN[j]:9s} prior {e['prior']:4.1f} | free {e['sd_free']:5.2f} trust {e['sd_trust']:5.2f} | reads {e['sd_reads']:6.2f} | "
              + " ".join(f"-{t[:4]} {v:.2f}" for t, v in e["without"].items()) + " | " + " ".join(f"{m[:8]} {x:+.2f}" for m, x in zip(MEAS, dm)) + f" |dc| {e['dc_per_unit']:.2f}")
out["ident"] = ident
# ---- the camera's DISTANCE (not a freedom of today's solve): one more column per view = each read's change per 10 %
# of distance with the lens to match (the picture scale at the head's centre kept), by finite differences
sc_mm = lambda v: float(v["cam"]["t"][2]) / v["cam"]["f"] * 1000.0 / float(v.get("scale", 1.0))
D = np.zeros((len(obs), len(views)))
for vi, v in enumerate(views):
    iv = [i for i, ob in enumerate(obs) if ob["view"] == v["kind"] and "X" in ob]
    if not iv:
        continue
    X = np.array([obs[i]["X"] for i in iv], float)
    far = {**v["cam"], "t": [x * 1.1 for x in v["cam"]["t"]], "f": v["cam"]["f"] * 1.1}
    d = (fr._cam_points(far, X)[1] - fr._cam_points(v["cam"], X)[1]) * float(v.get("scale", 1.0)) * sc_mm(v)
    for i, dd in zip(iv, d):
        ob = obs[i]
        D[i, vi] = dd @ np.asarray(ob["n"]) if "n" in ob else (dd[0] if ob["name"].endswith(".x") else dd[1])
J2 = np.c_[Jx, D]
p2 = np.r_[pri, np.full(len(views), 1e3)]
p2[n1:n1 + nc] = 1e3


def A2(wsel, cam_wide=True):
    q = p2.copy()
    if not cam_wide:
        q[n1:n1 + nc] = pri[n1:n1 + nc]
    return (J2 * (w * wsel)[:, None]).T @ J2 + np.diag(1.0 / q ** 2)


print("DISTANCE (per 10 % of camera distance at the same picture scale): sd from the reads alone (x10 %), without each type, shape per +10 % left uncorrected")
dist = []
Af = A2(ones)
Afi = np.linalg.inv(Af)
for vi, kd in enumerate(kinds):
    col = P + vi
    # what a +10 % distance error costs when the solve CANNOT move distance (today): the other freedoms' response
    g = -np.linalg.solve(A_free, (Jx * w[:, None]).T @ D[:, vi])
    dm = Rm @ g[:n1]
    e = {"view": kd, "sd_reads": float(np.sqrt(Afi[col, col])), "sd_cam_prior": float(np.sqrt(np.linalg.inv(A2(ones, False))[col, col])),
         "shape": {m: float(x) for m, x in zip(MEAS, dm)}, "dc": float(np.linalg.norm(g[:n1])), "without": {}}
    for t in types:
        if t != "hold":
            e["without"][t] = float(np.sqrt(np.linalg.inv(A2(np.array([ob["type"] != t for ob in obs], float)))[col, col]))
    dist.append(e)
    print(f"  {kd:8s} reads alone {10 * e['sd_reads']:6.1f} % (cameras at today's priors: {10 * e['sd_cam_prior']:.1f} %) | " + " ".join(f"-{t[:4]} {10 * v:.1f}" for t, v in e["without"].items())
          + " | +10 % too far, uncorrected: " + " ".join(f"{m[:8]} {x:+.2f}" for m, x in zip(MEAS, dm)) + f" |dc| {e['dc']:.2f}")
out["dist"] = dist
# the softest directions of the whole system (reads alone on the cameras), in the prior's units: what they are made of
S = np.r_[np.ones(n1), np.tile(np.array([1.5, 1.5, 2.5, 0.8, 6.0, 2.0]), len(views)), np.ones(P - n1 - nc)]   # one scale per freedom
ev, V = np.linalg.eigh((A_data * S[:, None]) * S[None, :])
print("SOFTEST DIRECTIONS (reads alone on the cameras; unit = identity sd / the profile's camera sd): eigenvalue, camera part, shape (mm)")
soft = []
for q in range(6):
    v = V[:, q] * S
    cam = v[n1:n1 + nc].reshape(len(views), 6)
    big = [(kinds[a], CN[b], float(cam[a, b])) for a in range(len(views)) for b in range(6) if abs(cam[a, b]) > 0.25 * np.abs(cam).max() and np.abs(cam).max() > 1e-3]
    dm = Rm @ v[:n1]
    soft.append({"eig": float(ev[q]), "cam": big, "shape": {m: float(x) for m, x in zip(MEAS, dm)}, "dc": float(np.linalg.norm(v[:n1]))})
    print(f"  {ev[q]:8.3f}: |dc| {np.linalg.norm(v[:n1]):.2f}; cam " + ", ".join(f"{a} {b} {x:+.2f}" for a, b, x in big[:6]) + " | " + " ".join(f"{m[:8]} {x:+.2f}" for m, x in zip(MEAS, dm)))
out["soft"] = soft
json.dump(out, open(f"{C.S}/out/ident_{tag}.json", "w"), default=float)
