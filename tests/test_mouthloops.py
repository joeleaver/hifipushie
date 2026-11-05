"""Open mouths (mouthloops.py, through limbloops.build): a round head on stub legs with a wide subtracted mouth
that wraps round its front gets a rim ring on the lips' edge, rings down the walls and over the face, all closed
quad loops through their own vertices, the mesh closed and on the surface. uv run python tests/test_mouthloops.py"""
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import test_limbloops as T  # noqa: E402

from hifipushie import limbloops as LL, retopo  # noqa: E402


def creature():
    s = T.creature()
    s["joints"]["head"] = {"pos": [0, 0, 0.5], "r": 0.12}
    s["bones"]["neckb"] = {"a": "chest", "b": "head", "r_a": 0.12, "r_b": 0.12}
    s["blobs"] = {"mouth_cut": {"at": "head", "offset": [0, -0.12, -0.02], "shape": "super",
                                "size": [0.07, 0.05, 0.025], "squareness": 2.3, "op": "subtract", "part": "body",
                                "blend": 0.006}}
    return s


def test_mouth_rings():
    spec = creature()
    prims, V, F = T.mesh(spec)
    voxel = float(np.ptp(V, 0).max()) / 200
    log = []
    r = LL.build(spec, prims, V, F, voxel, 5000, log=log)
    assert any("mouth_cut: opening" in x for x in log), log
    Vo, L, S = r["verts"], r["loops"], r["sizes"]
    mouth = {k: v for k, v in r["rings"].items() if k.startswith("mouth_cut")}
    q = LL.quality(Vo, L, S, spec, prims, planes={}, loops=mouth)
    closed = [k for k, v in q["rings"].items() if v["ring"]]
    assert "mouth_cut rim" in closed and sum("wall" in k for k in closed) >= 2, q["rings"]
    assert q["field_mm"][1] < 2.0, q
    E = {}
    for f in retopo.topology(L, S)[0]:
        for k in range(len(f)):
            e = (min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)]))
            E[e] = E.get(e, 0) + 1
    assert set(E.values()) == {2}
    # the rim lies on the cut's edge: in front of the head, round the opening
    rim = Vo[mouth["mouth_cut rim"]]
    assert rim[:, 1].max() < -0.05 and np.ptp(rim[:, 0]) > 0.08, (rim[:, 1].max(), np.ptp(rim[:, 0]))


if __name__ == "__main__":
    test_mouth_rings()
    print("ok test_mouth_rings")
