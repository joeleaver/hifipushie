"""hang_prep.py <tag> [job]: the chain-built shirt <tag>U.pkl -> ZOZO job (local). Held solid (carry): stand, collar, the
plackets above the button, seam rows sewn to them. Free: the soft cloth. Gravity only. Run with the path-A worktree's code."""
import sys, json, pickle, types
from pathlib import Path
import numpy as np
from hifipushie import cloth, cloth_job as cj, zozo_hang as zh, cloth_zozo as cz, folds as foldmod
D = "/mnt/data/hifipushie/folds_ab/D/"; t = sys.argv[1]; job = sys.argv[2] if len(sys.argv) > 2 else t
d = pickle.load(open(f"{D}{t}U.pkl", "rb")); X = np.asarray(d["A"], float).copy(); M = d["mesh"]; F = np.asarray(M["F"], np.int64)
uv = np.asarray(M["uv"], float); pc = np.asarray(M["piece"]); nm = list(M["names"]); bV = np.asarray(d["bodyV"], float); bT = np.asarray(d["bodyF"], np.int64)
# torso only: sleeves + cuffs leave the job (the fit's crushed sleeves are not this hang's business); armhole rows stay held
keep = np.isin(pc, [nm.index(k) for k in ("back", "yoke", "front.L", "front.R", "stand", "collar")])
sew0 = np.asarray(M["sew"], np.int64).reshape(-1, 2); arm = sew0[keep[sew0[:, 0]] ^ keep[sew0[:, 1]]]; armv = arm[keep[arm]]
sew = sew0[keep[sew0].all(1)]; F = F[keep[F].all(1)]
sew_all = sew; cl = [c for c in M["closures"] if c["name"] == "front"][0]
hold = np.isin(pc, [nm.index("stand"), nm.index("collar")])
stiff = hold.astype(float).copy()
for n_ in ("cuff.L", "cuff.R"): stiff[pc == nm.index(n_)] = 1.0
for fname, bv, in (("front.L", cl["v"][0][0]), ("front.R", cl["v"][0][1])):
    pv = np.where(pc == nm.index(fname))[0]; fx = np.median(uv[[f for f in M["folds"] if f["piece"] == fname][0]["rows"][0], 0])
    ex = uv[pv, 0].min() if fx > 0 else uv[pv, 0].max(); lo, hi = sorted((ex, fx)); s_ = pv[(uv[pv, 0] >= lo - 1e-5) & (uv[pv, 0] <= hi + 1e-5)]
    stiff[s_] = 1.0; hold[s_[uv[s_, 1] > uv[bv, 1] - 0.02]] = True      # above the hold line the strip is held; below it follows the buttons
part = sew[hold[sew[:, 0]] ^ hold[sew[:, 1]]]; hold[part.ravel()] = True; hold[armv] = True
# the held band needs no collider: body triangles right under it go, the soft cloth still has the rest of the body
from scipy.spatial import cKDTree as _K
bandv = X[np.isin(pc, [nm.index("stand"), nm.index("collar")])]; near_ = _K(bandv).query(bV)[0] < 0.035
bT = bT[~near_[bT].any(1)]; u_ = np.unique(bT); ix_ = -np.ones(len(bV), np.int64); ix_[u_] = np.arange(len(u_)); bV = bV[u_]; bT = ix_[bT]; print("body triangles left:", len(bT))
free_f = ~hold[F].all(1)
lg = zh.legality(X, F, bV, bT); print("legality of torso cloth:", {k: lg[k] for k in ("ok", "illegal", "min_mm", "in_reach")}, lg.get("by_kind"))
g = {"fabric": "shirting"}
lim = zh.woven_limit(); print("strain limit", round(lim * 100, 1), "%")
flat = np.c_[uv, np.zeros(len(uv))]; sig = cz._start_stretch(flat, X, F); over = (sig > 1 + lim) & free_f
print("free faces past the limit at the start:", over.sum(), "of", free_f.sum(), " by piece", {nm[p]: int((pc[F[over, 0]] == p).sum()) for p in np.unique(pc[F[over, 0]])} if over.any() else {})
pickle.dump({"X": X, "hold": hold, "stiff": stiff}, open(f"/mnt/data/hifipushie/folds_ab/H/{job}_prep.pkl", "wb"))
print("held", hold.sum(), "of", len(X))
# ---- legal start (the hang work's own contact pass), then the job
hid = list(np.where(np.isin(pc, [nm.index("stand"), nm.index("collar")]))[0]); fx0 = np.zeros(len(X), bool); fx0[hid] = True
P = zh.legality(X, F[fx0[F].all(1)], bV, bT); print("band + collar vs body:", {k: P[k] for k in ("ok", "illegal", "min_mm")})
Ff = F[~fx0[F].all(1)]
for it in range(60):
    Pr = zh.contact_pairs(X, Ff, bV, bT, zh.REACH)
    if not len(Pr["d"]): break
    Y, _ = zh.push_out(X, Pr, zh.REACH); Y[fx0] = X[fx0]; X = Y
    # smooth what was pushed along the cloth so no dents remain: one light pass on the pushed verts' neighbours is left to the settle
print("contact pass rounds", it + 1, "left", len(Pr["d"]))
lg = zh.legality(X, F, bV, bT); print("legality, all cloth:", {k: lg[k] for k in ("ok", "illegal", "min_mm")}, lg["by_kind"])
sig = cz._start_stretch(flat, X, F); bad = (sig > 1 + lim) & free_f
if bad.any():
    hold[np.unique(F[bad])] = True; free_f = ~hold[F].all(1); bad2 = (sig > 1 + lim) & free_f; print("past-limit faces held:", bad.sum(), "left", bad2.sum())
fw = foldmod.weights(M)[keep] if M.get("folds") else None; br = foldmod.bend_reference(M, flat, None) if M.get("folds") else None
print("fold rest arrays:", None if br is None else {k: np.shape(v) for k, v in (br.items() if isinstance(br, dict) else [("bend_rest", br)])})
hold = hold.copy(); hold[~keep] = False
idx = -np.ones(len(X), np.int64); idx[keep] = np.arange(keep.sum()); F = idx[F]; sew = idx[sew]
X_all = X.copy(); X = X[keep]; uv = uv[keep]; stiff = stiff[keep]; pc = pc[keep]; hold = hold[keep]; flat = flat[keep]
ci = np.where(hold)[0].astype(np.int64); whole = np.isin(pc, [nm.index("stand"), nm.index("collar")]); Rr = flat.copy(); Rr[whole] = X[whole]
arrays = dict(X=X, uv=uv, F=F, sew=sew, stitch=np.asarray(M.get("stitch", np.zeros((0, 2))), np.int64).reshape(-1, 2), stiff=stiff, piece=pc.astype(np.int64),
              pins=np.zeros(0, np.int64), bodyV=bV, bodyT=bT, carryIdx=ci, carryPoses=X[ci][None], rest=Rr, restIdx=np.where(whole)[0].astype(np.int64))
cfg = {"fabric": cloth.fabric(g), "name": f"chain_hang:{job}", "placement": "smooth", "wraps": {}, "made": ["stand", "collar", "cuff.L", "cuff.R"], "strain_limit": lim}
jc = cj.job_config(cfg, nm); n = int(sys.argv[3]) if len(sys.argv) > 3 else 144
jc["stages"] = [{"name": "settle", "frames": n, "gravity": 1, "sew": True, "self_collision": True, "fixed": [], "body": True}]; jc["snap"] = 24
jd = Path(f"/mnt/data/hifipushie/folds_ab/H/{job}"); jd.mkdir(parents=True, exist_ok=True); np.savez(jd / "in.npz", **arrays); (jd / "job.json").write_text(json.dumps(jc, indent=1, default=cj._jsonable))
pickle.dump({"X": X, "Xall": X_all, "keep": keep, "hold": hold, "stiff": stiff, "M": M, "bodyV": bV, "bodyF": bT, "at": d["at"]}, open(f"/mnt/data/hifipushie/folds_ab/H/{job}_prep.pkl", "wb"))
ss = zh.start_strain(arrays, jc)
nbm = {}
for f_ in F:
    for a_ in f_: nbm.setdefault(int(a_), set()).update(int(b_) for b_ in f_ if b_ != a_)
for rnd in range(30):
    if ss["ok"]: break
    sg2 = cz._start_stretch(arrays["rest"], X, F); wh_ = whole[F].any(1); badv = np.unique(F[(sg2 > 1.0 + 0.85) & ~wh_])
    if not len(badv): print("no bad free verts found", ss["worst"]); break
    for v_ in badv: X[v_] = 0.5 * X[v_] + 0.5 * X[list(nbm[int(v_)])].mean(0)
    arrays["X"] = X; arrays["carryPoses"] = X[ci][None]; ss = zh.start_strain(arrays, jc)
for rn2 in range(12):
    Pr = zh.contact_pairs(X, F, bV, bT, zh.BODY_OFFSET + 0.0002)
    if not len(Pr["d"]): break
    Y, _ = zh.push_out(X, Pr, zh.BODY_OFFSET + 0.0012); Y[whole] = X[whole]; X = Y
Pr = zh.contact_pairs(X, F, bV, bT, zh.BODY_OFFSET + 1e-6)
if len(Pr["d"]):                                                       # what's left touches the held band: that bit of neck goes too
    bad_b = set()
    for k_, b_ in zip(Pr["kind"], Pr["body"]):
        if k_ == "vf": bad_b.update(int(q) for q in bT[int(b_)])
        elif k_ == "fv": bad_b.add(int(b_))
    for c_ in Pr["cloth"]:
        pts = X[c_[c_ >= 0]].mean(0); bad_b.update(int(q) for q in np.where(np.linalg.norm(bV - pts, axis=1) < 0.012)[0])
    print("left at the end:", list(zip(Pr["kind"], np.round(Pr["d"] * 1e3, 2), [bool(whole[c_[0]]) for c_ in Pr["cloth"]])))
    bT = bT[~np.isin(bT, list(bad_b)).any(1)]; u_ = np.unique(bT); ix_ = -np.ones(len(bV), np.int64); ix_[u_] = np.arange(len(u_)); bV = bV[u_]; bT = ix_[bT]; arrays["bodyV"] = bV; arrays["bodyT"] = bT
arrays["X"] = X; arrays["carryPoses"] = X[ci][None]; lgf = zh.legality(X, F, bV, bT)
print("smoothing rounds", rnd, "contact rounds", rn2, "legal", lgf["ok"], lgf["illegal"], lgf["min_mm"]); np.savez(jd / "in.npz", **arrays)
ss = zh.start_strain(arrays, jc); print("start strain ok:", ss["ok"], {k: ss.get(k) for k in ("over", "faces", "worst")}); print("job", jd, "held", hold.sum(), "frames", n)
