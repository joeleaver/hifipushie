"""relabel.py <data root> [dressing dirs..]: bring dressings labelled with an older landmark set up to denselm.current()
WITHOUT rendering: a sample's picture is fixed by its stored identity, teeth, expression and camera (meta.npz), so a
new landmark's pixel is its vertex posed as the generator posed it (gen2.make_poser on the dressing's own base spec)
through the stored camera. The check: the landmarks the dressing already has are recomputed the same way and must
land on their stored pixels (max error printed; a dressing over 0.3 px is left alone and reported). Visibility of a
new landmark = its nearest old skin landmark's (the ray casts need the Blender scene; visibility is only used to
split the evaluation)."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import gen2  # noqa: E402

from hifipushie import base as basemod, denselm, humanfit, onemesh  # noqa: E402

root = Path(sys.argv[1])
dirs = [root / a for a in sys.argv[2:]] or sorted(d for d in root.iterdir() if (d / "labels.npz").exists())
LMS = denselm.current()
T, _gr, _pr, _g = denselm._groups()
for d in dirs:
    lab = dict(np.load(d / "labels.npz"))
    n_old = lab["xy"].shape[1]
    if n_old == LMS["n"]:
        continue
    meta = dict(np.load(d / "meta.npz"))
    dr = json.loads((d / "dressing.json").read_text())
    tm = json.loads((d / "timing.json").read_text())
    sp = gen2.base_spec(dr, float(tm.get("voxel", 0.002)))
    st0 = humanfit.state(sp["base"])
    pose = gen2.make_poser(sp, st0, fv_set=LMS)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st0["tpl"]["fid"])]
    at = np.full(int(gid.max()) + 1, -1)
    at[gid[gid >= 0]] = np.where(gid >= 0)[0]
    ids = LMS["gnm_all"]
    skin_old = np.arange(LMS["n_skin"])
    new = np.arange(n_old, LMS["n"])
    assert (at[ids[new]] >= 0).all(), "a new landmark is not on the one mesh"
    size = int(lab["size"])
    S = len(lab["xy"])
    XY = np.zeros((S, LMS["n"], 2), np.float32)
    VIS = np.zeros((S, LMS["n"]), np.uint8)
    DEP = np.zeros((S, LMS["n"]), np.float32)
    XY[:, :n_old], VIS[:, :n_old], DEP[:, :n_old] = lab["xy"], lab["vis"], lab["depth"]
    LMw = np.zeros((S, LMS["n"], 3), np.float32)
    LMw[:, :n_old] = meta["LM"]
    near = np.argmin(np.linalg.norm(T[ids[new]][:, None] - T[ids[skin_old]][None], axis=2), 1)
    worst = 0.0
    for i in range(S):
        P, Wn, L68, eye = pose(meta["identity"][i], meta["teeth"][i], meta["expression"][i])
        X = P[at[ids[np.r_[skin_old, new]]]]
        Xc = (X - meta["cam_eye"][i]) @ meta["cam_R"][i]            # camera frame: looks along -Z, +Y up
        k = 1.0 / (2 * np.tan(np.radians(meta["fov"][i]) / 2))
        u = (0.5 + Xc[:, 0] / -Xc[:, 2] * k - meta["shift"][i][0]) * size          # (Blender: the frame is shifted BY the lens shift)
        v = (1.0 - (0.5 + Xc[:, 1] / -Xc[:, 2] * k - meta["shift"][i][1])) * size
        uv = np.stack([u, v], 1)
        worst = max(worst, float(np.abs(uv[:len(skin_old)] - lab["xy"][i, skin_old]).max()))
        XY[i, new] = uv[len(skin_old):]
        DEP[i, new] = -Xc[len(skin_old):, 2]
        VIS[i, new] = lab["vis"][i, near]
        LMw[i, new] = X[len(skin_old):]
    if worst > 0.3:
        print(f"{d.name}: NOT relabelled: the old landmarks recomputed are up to {worst:.2f} px off their stored pixels", flush=True)
        continue
    (d / "labels_v2.npz").write_bytes((d / "labels.npz").read_bytes())
    np.savez_compressed(d / "labels.npz", xy=XY, vis=VIS, depth=DEP, sec=lab["sec"], landmark_version=LMS["version"], size=size)
    meta["LM"] = LMw
    np.savez_compressed(d / "meta.npz", **meta)
    print(f"{d.name}: {n_old} -> {LMS['n']} landmarks ({S} samples); the old ones recomputed: max {worst:.3f} px off", flush=True)
