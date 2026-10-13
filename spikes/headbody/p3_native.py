"""p3_native.py <model> ...: the native attach on a model's base (not saved): exactness of the head, stature, the
neck field's size, mesh quality round the seam."""
import copy, sys, time
import numpy as np
from hifipushie import base as B, onemesh, store
from p1_measure import measures, gnm_eval, UPW, FWW, g, SKIN

a = onemesh.asset()
lev = a["g_lev"].astype(int)
for mname in sys.argv[1:]:
    base = copy.deepcopy(store.load(mname)["base"])
    base["head"]["attach"] = "native"
    import os
    if os.environ.get("NOLIP"):
        base["head"].pop("lip_close", None)
    if os.environ.get("NOSTYLE"):
        base.pop("style", None)
    t0 = time.time()
    hd = onemesh.head_desc(base)
    tpl = onemesh.template(base)
    ht = onemesh.head_rest(base)
    print(f"== {mname} native ({time.time()-t0:.1f} s): bound {hd['bound']}")
    W = ht["gnm_world"]
    ident = base["head"].get("identity") or {}
    Vg, Jg = gnm_eval(ident)
    # similarity fit GNM's own identity evaluation -> built (rotation fixed = _RG)
    X = Vg @ onemesh._RG.T
    keep = SKIN & (lev >= 13)
    far = keep & (np.asarray(g["groups"]["lower_face_region"] if "lower_face_region" in g["groups"] else np.zeros(len(lev))) < 0.5)
    c0, c1 = X[keep].mean(0), W[keep].mean(0)
    k = float(((W[keep] - c1) * (X[keep] - c0)).sum() / ((X[keep] - c0) ** 2).sum())
    res = np.linalg.norm(W[keep] - (c1 + k * (X[keep] - c0)), axis=1)
    print(f" head vs GNM(identity) similarity: scale {k:.6f}; residual max {1e3*res.max():.4f} mm rms {1e3*np.sqrt((res**2).mean()):.4f} (incl. lip_close's expression: {base['head'].get('lip_close')}); moved > 0.01 mm: {(res>1e-5).sum()} of {keep.sum()}")
    P = tpl["P"]
    M = measures(W, np.array(ht["eyes"]), UPW, FWW)
    stat = float(P[:, 2].max() - P[:, 2].min())
    print(f" stature {1000*stat:.1f} mm (stated {hd['bound']['native']['stature']}), head_h {1000*M['head_h']:.1f}, heads tall {stat/M['head_h']:.2f}, ipd {1000*M['ipd']:.1f}, ball r {1000*ht['eye_r']:.2f}, body height param {hd['bound']['body']['height']}")
    # template rows of head == ht verts?
    nb = tpl["n_body"]; hr = tpl["head_rows"]
    d = np.abs(tpl["P"][nb:nb + len(hr)] - ht["verts"][hr]).max()
    print(f" template head rows vs head verts: max {1e3*d:.5f} mm")
    # neck field: body displacement
    base0 = copy.deepcopy(base); 
    bd = onemesh.bound(hd["bound"]["body"], 1.0)
    mh_rows = np.flatnonzero(a["m2f"] >= 0)
    disp = np.linalg.norm(P[:tpl["n_mh"]] - bd["P"][mh_rows], axis=1)
    print(f" body vertices moved by the neck field: {(disp>1e-4).sum()} (> 0.1 mm), max {1e3*disp.max():.1f} mm, lowest moved z {1e3*bd['P'][mh_rows][disp>1e-4][:,2].min():.0f} (shoulder joint z {1e3*tpl['J']['shoulder.L'][2] if 'shoulder.L' in tpl['J'] else -1:.0f})")
    # quality round the seam: quad aspect / flipped normals for faces touching body rows that moved or bridge
    faces = []; i = 0
    for n_ in tpl["S"]:
        faces.append(tpl["L"][i:i + n_]); i += n_
    moved = np.zeros(len(P), bool); moved[:tpl["n_mh"]] = disp > 1e-4; moved[tpl["n_mh"]:nb] = True
    asp, flip = [], 0
    cen = np.array([0, P[nb:][:, 1].mean() * 0 + P[:nb][moved[:nb]][:, 1].mean(), 0])
    for f in faces:
        if moved[f].any():
            X_ = P[f]
            e_ = np.linalg.norm(X_ - np.roll(X_, -1, 0), axis=1)
            asp.append(e_.max() / max(e_.min(), 1e-9))
            n1 = np.cross(X_[1] - X_[0], X_[2] - X_[0]); n2 = np.cross(X_[2] - X_[0], X_[-1] - X_[0])
            if len(f) == 4 and (n1 @ n2) < 0: flip += 1
    asp = np.array(asp)
    print(f" faces in the moved zone {len(asp)}: edge aspect median {np.median(asp):.2f} p90 {np.percentile(asp,90):.2f} max {asp.max():.1f}; folded quads {flip}")
    np.savez(f"/mnt/data/hifipushie/headbody/out/{mname}_native_tpl.npz", P=P, L=tpl["L"], S=tpl["S"], n_body=nb, n_mh=tpl["n_mh"])
