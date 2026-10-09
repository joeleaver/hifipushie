"""The REAL tools on ground truth: a one-mesh human whose head identity is a truth subject's, pictured front +
three-quarter through likeness's own clay render; a fresh mean-headed copy fitted with what exists:
  R1 humanfit.fit_views on the detector's 68 (jaw contour left out, as onemesh2 did)
  R2 + humanfit.fit_outline on the detector's face oval
  R3 the staged checklist fit (likeness.fit_likeness) from the fresh head       (flag "staged": ~10-20 min)
Scored like the fast lane (3D mm by region after similarity alignment on the face).
  run.sh real.py <subject> [staged]"""
import copy
import json
import sys
import time

import numpy as np
from PIL import Image

import rs
import subjects
from hifipushie import humanfit, likeness, onemesh, server, store

OUT = rs.D / "real"
OVAL_R = [127, 234, 93, 132, 58, 172, 136, 150, 149, 176, 148, 152]
OVAL_L = [356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152]


def gnm_verts(b):
    st = humanfit.state(b)
    tpl = st["tpl"]
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    V = np.full((len(rs.gnm()["V0"]), 3), np.nan)
    V[gid[gid >= 0]] = P[gid >= 0]
    return V, st


def score(Vb, Vt):
    g = rs.gnm()
    ok = np.isfinite(Vb[:, 0]) & np.isfinite(Vt[:, 0])
    f = g["regions"]["face"]
    f = f[ok[f]]
    s, R, t = rs.similarity(Vb[f], Vt[f])
    A = s * Vb @ R.T + t
    d = np.linalg.norm(A - Vt, axis=1) * 1000
    out = {}
    for k, i in g["regions"].items():
        i = i[ok[i]]
        out[k] = float(d[i].mean()) if len(i) else float("nan")
    p = g["regions"]["profile"]
    p = p[ok[p]]
    out["profile"] = float(np.sqrt(((A[p, 1] - Vt[p, 1]) ** 2).mean()) * 1000)
    return out


def cam_for(L, yaw, pitch, lens, size=(900, 900), fill=0.5):
    w, h = size
    f = lens / 36.0 * w
    dist = f * 0.25 / (fill * h)
    r = rs._rv(humanfit._rotvec([np.radians(pitch), 0, 0]))
    return {"r": r.tolist(), "t": [0.0, 0.0, dist], "f": float(f), "size": [w, h], "centre": L[:68].mean(0).tolist(), "yaw": float(yaw)}


def main():
    name = sys.argv[1]
    staged = "staged" in sys.argv[2:]
    OUT.mkdir(exist_ok=True)
    sub = subjects.load(name)
    g = rs.gnm()
    sp0 = json.load(open(store.HOME / "lk_garrett" / "history" / "0001.json"))
    sp0 = copy.deepcopy(sp0.get("spec", sp0))
    b0 = sp0["base"]
    bt = copy.deepcopy(b0)
    bt["head"]["identity"] = {g["names"][g["comps"][i]]: round(float(v), 4) for i, v in enumerate(sub["c"])}
    t0 = time.time()
    Vt, stt = gnm_verts(bt)
    V0, st0 = gnm_verts(b0)
    print(f"state() {(time.time() - t0) / 2:.1f} s each")
    res = {"R0 the fresh (mean) head": score(V0, Vt)}
    print("integrity of the TRUTH head itself, judged as an edit of the fresh head:", humanfit.verdict(humanfit.integrity(bt, stt, st0))[:200])
    mesh = likeness.model_mesh(bt)
    views = []
    for vn, yaw, pitch, lens in (("front", 3.0, 4.0, 70.0), ("tq", -41.0, -3.0, 50.0)):
        cam = cam_for(stt["L"], yaw, pitch, lens)
        im, _ = likeness.render(mesh, cam, (0, 0, *cam["size"]), px=max(cam["size"]))
        path = OUT / f"{name}_{vn}.png"
        im.save(path)
        d = likeness.detect_info([im])[0]
        if d is None:
            print("no detection in", vn)
            continue
        P = d["P"]
        Lp = humanfit.project(cam, stt["L"])
        mmpx = cam["t"][2] / cam["f"] * 1000
        e = (P[rs.LM_FROM_MP] - Lp) * mmpx
        print(f"{vn}: detector vs the truth's own landmarks, mm in the picture: jaw {np.linalg.norm(e[:17], axis=1).mean():.1f} brows "
              f"{np.linalg.norm(e[17:27], axis=1).mean():.1f} nose {np.linalg.norm(e[27:36], axis=1).mean():.1f} eyes "
              f"{np.linalg.norm(e[36:48], axis=1).mean():.1f} mouth {np.linalg.norm(e[48:68], axis=1).mean():.1f}")
        pts = {f"lm{i}": [float(x) for x in P[likeness.MP68[i]]] for i in range(17, 68)}
        if vn == "front":
            pts["eye.L"] = [float(x) for x in P[likeness.MP_EYES[1]]]
            pts["eye.R"] = [float(x) for x in P[likeness.MP_EYES[0]]]
            ol = OVAL_R + OVAL_L[::-1][1:]
        else:
            ol = OVAL_R if yaw < 0 else OVAL_L
        views.append({"image": str(path), "size": cam["size"], "yaw": float(round(yaw / 5) * 5), "points": pts,
                      "outline": [[float(x) for x in P[i]] for i in ol], "_true_cam": cam})
    vp = [{k: v for k, v in vw.items() if k not in ("outline", "_true_cam")} for vw in views]
    t0 = time.time()
    b1, rep1 = humanfit.fit_views(b0, vp, force=True)
    print(f"fit_views {time.time() - t0:.0f} s; refused: {bool(rep1.get('refused'))}; plausibility {rep1['plausibility']}; "
          f"integrity {humanfit.verdict(rep1['integrity'])[:120]}")
    print("  views:", [(v["rms_mm"], v["worst"]) for v in rep1["views"]])
    V1, _ = gnm_verts(b1)
    res["R1 fit_views (detector 68, no jaw)"] = score(V1, Vt)
    vo = [{k: v for k, v in vw.items() if k != "_true_cam"} for vw in views]
    t0 = time.time()
    try:
        b2, rep2 = humanfit.fit_outline(b1, vo, rep1["cameras"], force=True)
        V2, _ = gnm_verts(b2)
        res["R2 + fit_outline (detector oval)"] = score(V2, Vt)
        print(f"fit_outline {time.time() - t0:.0f} s; integrity {humanfit.verdict(rep2['integrity'])[:120]}")
    except Exception as ex:  # noqa: BLE001
        print("fit_outline FAILED", repr(ex)[:300])
    from hifipushie import humanfit_map, humanmacro as hm
    import exp2
    vm = [{k: v for k, v in vw.items() if k not in ("outline", "_true_cam")} for vw in views]
    for tag, kw in (("R4 humanfit_map.fit (calibrated 478, MAP)", {}),
                    ("R5 R4 + character read (noisy reader)", {"read": {k: v[0] for k, v in exp2.reader({"name": name, "V": rs.head(sub["c"])}).items()}}),
                    ("R6 front picture only + read", {"read": {k: v[0] for k, v in exp2.reader({"name": name, "V": rs.head(sub["c"])}).items()}, "front": True})):
        t0 = time.time()
        front = kw.pop("front", False)
        bm, repm = humanfit_map.fit(b0, vm[:1] if front else vm, force=True, **kw)
        Vm, _ = gnm_verts(bm)
        res[tag] = score(Vm, Vt)
        print(f"{tag}: {time.time() - t0:.0f} s; refused {bool(repm.get('refused'))}; {repm['plausibility']}; {humanfit.verdict(repm['integrity'])[:90]}")
        print("   ", [(v["evidence"], v["rms_mm"], v["lens_mm"]) for v in repm["views"]])
    if staged:
        mname = f"rs_real_{name.split('_')[0]}"
        sp = copy.deepcopy(sp0)
        store.save(mname, sp, "refstudy: fresh head for the staged fit on a ground-truth subject")
        server.human_reference(mname, vo, fit=False, save=False, figure=False)
        t0 = time.time()
        try:
            likeness.measure_reference(mname)
            for s in [x["name"] for x in likeness.stage_names()]:
                try:
                    rep = likeness.fit_stage(mname, s, save=True, panels=str(OUT / f"{mname}_{s}.png"))
                    print(rep["text"][:600], flush=True)
                except Exception as ex:  # noqa: BLE001
                    print("stage", s, "FAILED", repr(ex)[:300], flush=True)
                V3, _ = gnm_verts(store.load(mname)["base"])
                res[f"R3 staged fit after {s}"] = score(V3, Vt)
            print(f"staged fit {time.time() - t0:.0f} s")
        except Exception as ex:  # noqa: BLE001
            import traceback
            traceback.print_exc()
    print(f"\n{name}  {'method':40s} " + rs.HEADER)
    for k, sc in res.items():
        print(f"{'':{len(name)}s}  {k[:40]:40s} " + " ".join(f"{sc.get(r, float('nan')):5.2f}" for r in rs.REGIONS))
    (OUT / f"{name}_res.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
