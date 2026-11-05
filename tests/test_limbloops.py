"""Limb loops (limbloops.py, parts.<p>.topology = "limbs"): a round body on two stub legs (Puddles' proportions:
the thigh sunk in the belly) gets quad rings down each leg, a root ring where the leg leaves the body, junction
rings out over the belly, one hole per leg zipped (the crotch strip kept), every ring on the surface.
uv run python tests/test_limbloops.py"""
import sys

import numpy as np

from hifipushie import limbloops as LL, retopo, sdf
from hifipushie.spec import compile_prims


def creature():
    return {"symmetry": True, "blend": 0.03,
            "joints": {"pelvis": {"pos": [0, 0, 0.24], "r": 0.15}, "chest": {"pos": [0, 0, 0.33], "r": 0.14},
                       "hip.L": {"pos": [0.1, 0, 0.17], "r": 0.055}, "knee.L": {"pos": [0.1, 0, 0.115], "r": 0.05},
                       "ankle.L": {"pos": [0.1, 0, 0.05], "r": 0.048}},
            "bones": {"spine": {"a": "pelvis", "b": "chest", "r_a": 0.15, "r_b": 0.14},
                      "thigh.L": {"a": "hip.L", "b": "knee.L", "r_a": 0.055, "r_b": 0.05},
                      "shin.L": {"a": "knee.L", "b": "ankle.L", "r_a": 0.05, "r_b": 0.048}}}


def mesh(spec):
    prims = [p for p in compile_prims(spec) if p.part == "body"]
    V, F = sdf.mesh(sdf.evaluate(prims, 110))[:2]
    return prims, np.asarray(V, float), np.asarray(F, int)


def test_limbs_and_loops():
    spec = creature()
    ls = LL.limbs(spec)
    assert [l["label"] for l in ls] == ["hip.L", "hip.R"]
    assert ls[1]["C"][0, 0] < 0  # the mirror side


def test_build_rings_zipped():
    spec = creature()
    prims, V, F = mesh(spec)
    voxel = float(np.ptp(V, 0).max()) / 200
    log = []
    r = LL.build(spec, prims, V, F, voxel, 4000, log=log)
    Vo, L, S = r["verts"], r["loops"], r["sizes"]
    q = LL.quality(Vo, L, S, spec, prims, planes=r["planes"])
    roots = [k for k in q["rings"] if "slid" in k]
    assert len(roots) == 2 and all(q["rings"][k]["ring"] for k in roots), q["rings"]
    assert q["field_mm"][1] < 2.0, q  # on the exact surface
    # closed: every edge in two faces (one hole per leg zipped, nothing torn at the crotch)
    E = {}
    for f in retopo.topology(L, S)[0]:
        for k in range(len(f)):
            e = (min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)]))
            E[e] = E.get(e, 0) + 1
    assert set(E.values()) == {2}, {c: list(E.values()).count(c) for c in set(E.values())}
    # each leg's rings are quads; the root ring sits where the leg leaves the belly, below the sunk hip
    assert (S == 4).sum() >= 2 * 4 * LL.RING, (S == 4).sum()  # two legs, at least four quad rows each
    root_z = Vo[r["rings"]["hip.L"]][:, 2].mean()
    assert root_z < 0.17, root_z


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    sys.exit(0)
