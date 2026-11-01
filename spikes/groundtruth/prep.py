"""prep.py lps | hsrd <pose id>: a WORKING COPY of a scan's head under $HIFIPUSHIE_GROUNDTRUTH/work/<tag>/ (the
downloads stay as they are).
  lps: the Lee Perry-Smith head (McGuire's archive copy: head.OBJ, 8,842 quads = the release's ZBrush level; its fine
       detail is a displacement map we do not apply), Catmull-Clark x2 (141k quads) with the UVs carried.
  hsrd <pose>: the LOD0 scan (1M triangles, metres, Z up) cut to the head and shoulders (the top `top` m), the largest
       piece, vertex colours kept.
-> head.npz {V, F, (C), (FUV per-corner uv)}, info.json. tag = lps | the pose id."""
import json
import sys
import numpy as np
import gt

what = sys.argv[1]
if what == "lps":
    from hifipushie import base as basemod
    m = gt.read_obj(gt.ROOT / "lps/mcguire/x/head.OBJ")
    V, polys, puv = m["V"], m["poly"], [m["UV"][q] for q in m["polyuv"]]
    for _ in range(2):
        V, quads = basemod._catmull_clark(V, polys)
        nuv = []
        for uv in puv:
            c = uv.mean(0)
            for k in range(len(uv)):
                nuv.append(np.array([uv[k], 0.5 * (uv[k] + uv[(k + 1) % len(uv)]), c, 0.5 * (uv[k - 1] + uv[k])]))
        polys, puv = quads, nuv
    Q = np.asarray(polys, np.int64)
    U = np.asarray(puv)
    F = np.r_[Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]]
    FUV = np.r_[U[:, [0, 1, 2]], U[:, [0, 2, 3]]]
    d = gt.WORK / "lps"
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "head.npz", V=V, F=F, FUV=FUV)
    (d / "info.json").write_text(json.dumps({"unit_m": None, "sex": "male", "age": 35, "source": "lps/mcguire/x/head.OBJ", "texture": "lps/mcguire/x/lambertian.jpg",
                                              "note": "ZBrush units, no real scale; Catmull-Clark x2 of the 8,842-quad release mesh, displacement map not applied"}))
    print("lps", V.shape, F.shape, V.min(0), V.max(0))
else:
    pose = sys.argv[2]
    top = float(sys.argv[3]) if len(sys.argv) > 3 else 0.42
    src = gt.ROOT / f"hsrd100/x/{pose}/scan/{pose}_LOD0.obj"
    m = gt.read_obj(src)
    V, F = m["V"], m["F"]
    keep = V[:, 2] > V[:, 2].max() - top
    V1, F1, idx = gt.submesh(V, F, keep)
    big = gt.largest_component(V1, F1)
    V2, F2, idx2 = gt.submesh(V1, F1, big)
    C = m["C"][idx][idx2] if m["C"] is not None else None
    # per-corner uv of the kept faces (the texture cut of hsrd_export.py) and the WHOLE scan as an occluder (float32)
    fkeep = np.flatnonzero(keep[F].all(1))[big[F1].all(1)]
    FUV = m["UV"][m["FUV"][fkeep]].astype(np.float32) if m["FUV"] is not None else None
    assert FUV is None or len(FUV) == len(F2)
    meta = json.loads((gt.ROOT / f"hsrd100/dl/{pose}/person_meta.json").read_text())
    d = gt.WORK / pose
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "body.npz", V=V.astype(np.float32), F=F.astype(np.int32))
    np.savez_compressed(d / "head.npz", V=V2, F=F2, C=C, **({} if FUV is None else {"FUV": FUV}))
    (d / "info.json").write_text(json.dumps({"unit_m": 1.0, "sex": meta["sex"].lower(), "age": float(meta["age"]), "source": str(src.relative_to(gt.ROOT)),
                                              "stature_scan_m": float(V[:, 2].max() - V[:, 2].min()), "height_meta_cm": float(meta["height"]),
                                              "note": f"LOD0 (1M triangles), the top {top} m, largest piece"}))
    print(pose, "whole", V.shape, "bbox", V.min(0).round(3), V.max(0).round(3), "head", V2.shape, F2.shape)
