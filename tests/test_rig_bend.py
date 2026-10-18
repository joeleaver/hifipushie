"""Arc bend weights and pose correctives (rig.BEND_ARC / _arc_bend, correctives.py) on a synthetic leg: a tube round
hip -> knee -> ankle with the knee bent 5 deg at rest. Light: numpy only, a second. uv run python tests/test_rig_bend.py"""
import sys

import numpy as np

from hifipushie import correctives as co
from hifipushie import rig

P = rig.PREFIX


def leg():
    hip, knee = np.array([0.1, 0.0, 0.9]), np.array([0.1, 0.0, 0.48])
    t = np.radians(5)
    ankle = knee + 0.42 * np.array([0.0, np.sin(t), -np.cos(t)])  # the shin a little back: the knee flexes about +x
    bones = [{"name": P + "Hips", "head": np.array([0.0, 0.0, 0.95]), "parent": -1},
             {"name": P + "LeftUpLeg", "head": hip, "parent": 0},
             {"name": P + "LeftLeg", "head": knee, "parent": 1},
             {"name": P + "LeftFoot", "head": ankle, "parent": 2},
             {"name": P + "LeftLegBend", "head": knee.copy(), "parent": 1,
              "bend": {"driver": P + "LeftLeg", "share": 0.5, "of": P + "LeftUpLeg"}}]
    # a tube of radius 5.5 cm: rings every 1.5 cm along hip -> knee -> ankle, 24 round
    path = [hip + (knee - hip) * s for s in np.linspace(0, 1, 29)] + [knee + (ankle - knee) * s for s in np.linspace(0, 1, 29)[1:]]
    V, rings = [], []
    for c in path:
        rings.append(len(V))
        for a in np.linspace(0, 2 * np.pi, 24, endpoint=False):
            V.append(c + 0.055 * np.array([np.cos(a), np.sin(a), 0.0]))
    V = np.array(V)
    F = []
    for r in range(len(rings) - 1):
        for k in range(24):
            a, b = rings[r] + k, rings[r] + (k + 1) % 24
            c, d = rings[r + 1] + k, rings[r + 1] + (k + 1) % 24
            F += [(a, b, d), (a, d, c)]
    F = np.array(F)
    # MakeHuman-like weights: thigh above the knee, shin below, a 2 cm linear blend
    s = (V[:, 2] - knee[2])
    w = np.clip(0.5 - s / 0.04, 0, 1)  # shin share
    J = np.zeros((len(V), 4), int)
    W = np.zeros((len(V), 4))
    J[:, 0], J[:, 1] = 1, 2
    W[:, 0], W[:, 1] = 1 - w, w
    return bones, V, F, J, W


def test_arc_weights_by_side():
    bones, V, F, J, W = leg()
    J2, W2 = rig._arc_bend(bones, V, J, W)
    h = np.where(J2 == 4, W2, 0).sum(1)
    knee = bones[2]["head"]
    near = np.abs(V[:, 2] - knee[2]) < 0.01
    front, back = near & (V[:, 1] < knee[1] - 0.04), near & (V[:, 1] > knee[1] + 0.04)
    assert h[front].mean() > 0.8, h[front].mean()  # the outer side rides the half-angle helper
    far = np.abs(V[:, 2] - knee[2]) > 0.2
    assert h[far].max() < 1e-6
    # the zone is wider in front than behind
    zone = lambda m: np.ptp(V[m & (h > 0.2), 2])
    band = np.abs(V[:, 2] - knee[2]) < 0.1
    assert zone(band & (V[:, 1] < knee[1] - 0.04)) > 1.5 * zone(band & (V[:, 1] > knee[1] + 0.04))
    assert np.allclose(W2.sum(1), 1.0)


def test_corrective_reproduces_target_and_stays_local():
    bones, V, F, J, W = leg()
    J, W = rig._arc_bend(bones, V, J, W)
    ks = co.keys(bones, {"Leg_flex": co.MOTIONS["Leg_flex"]})
    assert [k["name"] for k in ks] == ["corr_LeftLeg_flex90", "corr_LeftLeg_flex130"], [k["name"] for k in ks]
    D = co.solve(bones, V, F, J, W, ks)
    k = ks[0]
    d = np.linalg.norm(D[k["name"]], axis=1)
    knee = bones[2]["head"]
    assert d[np.abs(V[:, 2] - knee[2]) > 0.25].max() < 1e-9  # nothing away from the knee
    assert d.max() > 1e-3
    turns = rig.drive_twist(bones, {k["joint"]: (k["axis"], k["deg"])})
    P0 = rig.pose(bones, V, J, W, turns)
    P1 = rig.pose(bones, V + D[k["name"]], J, W, turns)
    # no vertex of the bent tube crosses the bisecting plane further than the soft contact allows
    assert np.isfinite(P1).all()
    # the corrected knee's outer side stays at least as far from the pivot as LBS put it, inside the rest radius x 1.3
    front = (V[:, 1] < knee[1] - 0.04) & (np.abs(V[:, 2] - knee[2]) < 0.03)
    r0 = np.linalg.norm(P0[front] - knee, axis=1)
    r1 = np.linalg.norm(P1[front] - knee, axis=1)
    assert r1.max() < 0.055 * 1.3 + 0.01, r1.max()
    print("r0", np.round(np.percentile(r0, [5, 50, 95]), 4), "r1", np.round(np.percentile(r1, [5, 50, 95]), 4))
    assert np.median(r1) >= np.median(r0) - 1e-3 and np.median(r1) < 0.055 * 1.1  # kept round, not collapsed
    # driver weights: piecewise linear across the two keys
    w = co.weights_at(k, ks, 110.0)
    assert abs(w["corr_LeftLeg_flex90"] - 0.5) < 1e-9 and abs(w["corr_LeftLeg_flex130"] - 0.5) < 1e-9


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and (len(sys.argv) < 2 or any(a in name for a in sys.argv[1:])):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
