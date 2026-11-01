"""gscore.py <tag> <model or fit:<name>> [..]: a solved GNM head against the SCAN's surface (what Part 2 is about):
the head's identity (a block-in model's, or a Part 1 fit's for reference), the scan's pose and scale fitted to it
(identity held: fit3d.fit(pose_only)), then the region table (two-sided, the scan's skin only) and, against the Part 1
fit's identity (truth=, default p1b3), errmap's rms and the acceptance measures. -> out/scores/<tag>__<model>.json."""
import json
import sys
import numpy as np
import gt, fit3d


def score(tag, what, scan=None, truth="p1b3", skin_v=None):
    scan = scan or gt.load_scan(tag)
    fj = json.loads((gt.WORK / tag / f"fit_{truth}.json").read_text())
    S = (fj["S"]["s"], np.asarray(fj["S"]["R"]), np.asarray(fj["S"]["t"]))
    if what.startswith("fit:"):
        c = np.asarray(json.loads((gt.WORK / tag / f"fit_{what[4:]}.json").read_text())["c"])
    elif what.startswith("mean"):
        c = gt.class_mean(scan["info"]["sex"])
    else:
        from hifipushie import blockin as bi, store
        c = bi.identity(store.load(what))
    skin_v = np.load(gt.WORK / tag / "skin_v.npy") if skin_v is None else skin_v
    r = fit3d.fit(scan, S, c_start=c, pose_only=True, scale_free=True, rounds=30, log=lambda *a: None, skin_v=skin_v)
    g = fit3d.evaluate(scan, c, None, r["S"], skin_v)
    import errmap
    ct = np.asarray(fj["c"])
    e = errmap.rms(c, ct)
    a, b = errmap.measures(c, e["scale"]), errmap.measures(ct)
    out = {"tag": tag, "what": what, "table": g["table"], "scan_scale": float(r["S"][0] / S[0]), "S": {"s": float(r["S"][0]), "R": np.asarray(r["S"][1]).tolist(), "t": np.asarray(r["S"][2]).tolist()},
           "c": c.tolist(), "vs_fit": {k: e[k] for k in ("face", "low", "chin", "jaw body", "jaw angle", "cheeks", "scale")},
           "meas": {k: a[k] - b[k] for k in ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "chin_length", "nose_width", "mouth_width", "pupils_apart")},
           "meas_abs": {k: a[k] for k in ("jaw_width", "gonial_width", "chin_width", "cheekbone_width")}, "c_off": float(np.linalg.norm(c - gt.class_mean(scan["info"]["sex"])))}
    d = gt.OUT / "scores"
    d.mkdir(exist_ok=True)
    (d / f"{tag}__{what.replace(':', '_')}.json").write_text(json.dumps(out))
    return out


if __name__ == "__main__":
    tag = sys.argv[1]
    scan = gt.load_scan(tag)
    for what in sys.argv[2:]:
        o = score(tag, what, scan)
        t = o["table"]
        print(f"{tag} {what}: scan x{o['scan_scale']:.3f} | " + " ".join(f"{k} {t[k]['mean']:.2f}/{t[k]['p90']:.2f}" for k in gt.REGIONS if t.get(k))
              + f" | vs fit: face {o['vs_fit']['face']:.2f} low {o['vs_fit']['low']:.2f} | " + " ".join(f"{k} {v:+.1f}" for k, v in o["meas"].items()), flush=True)
