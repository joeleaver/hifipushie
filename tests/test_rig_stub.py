"""Stub limbs (rig.ARC_GIRTH / ARC_ROOTS / ARC_BODY, limb_girth, _arc_bend): a leg blended into a round body that is
shorter than it is thick (Puddles: thigh 5.5 cm long, 6.3 cm round). Its weights come from the limb's girth, not its
length; body skin round it is the hips'; a person's limb is untouched. Light: numpy only.
uv run python tests/test_rig_stub.py"""
import sys

import numpy as np

from hifipushie import rig

P = rig.PREFIX
HIPS, HIP, KNEE, ANKLE = (np.array(p) for p in ([0, 0, 0.24], [0.1, 0, 0.17], [0.1, 0, 0.115], [0.1, 0, 0.05]))


def stub():
    bones = [{"name": P + "Hips", "head": HIPS, "parent": -1},
             {"name": P + "LeftUpLeg", "head": HIP, "parent": 0},
             {"name": P + "LeftLeg", "head": KNEE, "parent": 1},
             {"name": P + "LeftFoot", "head": ANKLE, "parent": 2},
             {"name": P + "LeftUpLegBend", "head": HIP.copy(), "parent": 0,
              "bend": {"driver": P + "LeftUpLeg", "share": 0.5, "of": P + "Hips"}},
             {"name": P + "LeftLegBend", "head": KNEE.copy(), "parent": 1,
              "bend": {"driver": P + "LeftLeg", "share": 0.5, "of": P + "LeftUpLeg"}}]
    rng = np.random.default_rng(0)
    u = rng.normal(size=(6000, 3))
    u /= np.linalg.norm(u, axis=1, keepdims=True)
    body = np.array([0.0, 0.0, 0.26]) + u * [0.17, 0.15, 0.16]
    a = rng.uniform(0, 2 * np.pi, 3000)
    zz = rng.uniform(0.05, 0.2, 3000)
    leg = np.c_[0.1 + 0.06 * np.cos(a), 0.06 * np.sin(a), zz]
    body = body[(body[:, 2] > 0.14) & (body[:, 0] > 0.0)]  # this side; the body's underside over the leg
    V = np.r_[body, leg]
    # the distance blend's leak: thigh weight by distance to the thigh's segment, falling over 3 cm (a person's limb
    # radius x FALLOFF), so it reaches far up a body this much fatter than the limb
    d_leg = rig._seg_dist(V, HIP, KNEE) - 0.06
    d_body = np.where(np.arange(len(V)) < len(body), 0.0, 0.03)
    w = np.exp(-np.maximum(d_leg, 0) / 0.03) / (np.exp(-np.maximum(d_leg, 0) / 0.03) + np.exp(-d_body / 0.03))
    shin = np.clip((KNEE[2] - V[:, 2]) / 0.02 + 0.5, 0, 1) * w
    J = np.zeros((len(V), 4), int)
    W = np.zeros((len(V), 4))
    J[:, 0], J[:, 1], J[:, 2] = 0, 1, 2
    W[:, 0], W[:, 1], W[:, 2] = 1 - w, w - shin, shin
    return bones, V, J, W, len(body)


def limb(J, W, cols):
    return np.where(np.isin(J, cols), W, 0).sum(1)


def test_girth_and_stub_frames():
    bones, V, J, W, nb = stub()
    g = rig.limb_girth(bones, V, J, W)
    assert abs(g[1] - 0.06) < 0.01, g  # the thigh's own skin, not the belly the leak reached
    fr = {f["joint"]: f for f in rig.arc_frames(bones, g)}
    assert fr["UpLeg"]["stub"] and not fr["Leg"]["stub"]  # a stub's knee stays an ordinary hinge
    plain = {f["joint"]: f for f in rig.arc_frames(bones)}
    assert fr["UpLeg"]["outer"] > 5 * plain["UpLeg"]["outer"]  # sized by its girth, not its 7 cm length


def test_body_skin_is_the_hips():
    bones, V, J, W, nb = stub()
    J2, W2 = rig._arc_bend(bones, V, J, W)
    legs = [1, 2, 4, 5]
    before, after = limb(J, W, legs), limb(J2, W2, legs)
    rho = np.linalg.norm((V - HIP)[:, :2], axis=1)
    g = rig.limb_girth(bones, V, J, W)[1]
    far = (np.arange(len(V)) < nb) & (rho > rig.ARC_BODY[1] * g + 0.01) & (V[:, 2] < 0.3)
    assert before[far].max() > 0.02  # the leak was there
    assert after[far].max() < 1e-6, after[far].max()
    own = (np.arange(len(V)) >= nb) & (V[:, 2] < KNEE[2])
    assert after[own].min() > 0.99  # the shin is still all leg
    assert np.allclose(W2.sum(1), 1.0)


def test_a_persons_leg_is_untouched():
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_rig_bend import leg
    bones, V, F, J, W = leg()
    J1, W1 = rig._arc_bend(bones, V, J, W)
    fr = rig.arc_frames(bones, rig.limb_girth(bones, V, J, W))
    assert not any(f["stub"] for f in fr)
    saved = rig.limb_girth
    rig.limb_girth = lambda *a: {}
    try:
        J0, W0 = rig._arc_bend(bones, V, J, W)
    finally:
        rig.limb_girth = saved
    assert np.array_equal(J0, J1) and np.array_equal(W0, W1)


def test_stub_seat_corrective():
    """A stub hip gets a seated corrective (correctives.UpLeg_flex, `_stub_target`); its target keeps the body skin
    off the thigh: the belly in front stays put, the seat behind isn't carried below the turned thigh's underside."""
    from hifipushie import correctives as cm
    bones, V, J, W, nb = stub()
    J2, W2 = rig._arc_bend(bones, V, J, W)
    g = rig.limb_girth(bones, V, J, W)
    ks = cm.keys(bones, girth=g)
    up = [k for k in ks if k["motion"] == "UpLeg_flex"]
    assert [k["name"] for k in up] == ["corr_LeftUpLeg_flex90"] and up[0]["frame"]["stub"]
    assert not [k for k in cm.keys(bones) if k["motion"] == "UpLeg_flex"]  # no girth, no stub: no seat
    tri = np.arange(len(V) // 3 * 3).reshape(-1, 3)  # (a soup: the target needs faces only for its smoothing)
    D = cm.solve(bones, V, tri, J2, W2, up)["corr_LeftUpLeg_flex90"]
    assert np.isfinite(D).all() and np.abs(D).max() > 1e-3
    f = up[0]["frame"]
    turns = rig.drive_twist(bones, {k["joint"]: (k["axis"], k["deg"]) for k in up})
    P0, P1 = rig.pose(bones, V, J2, W2, turns), rig.pose(bones, V + D, J2, W2, turns)
    d = V - f["pivot"]
    front = (np.arange(len(V)) < nb) & (d @ f["o"] < -1.5 * f["stub"])
    assert np.linalg.norm(P1 - V, axis=1)[front].max() <= np.linalg.norm(P0 - V, axis=1)[front].max() + 1e-9
    Ro = cm._rot(up[0]["axis"], 90) @ f["o"]
    back = (np.arange(len(V)) < nb) & (d @ f["o"] > f["stub"])
    cap = np.maximum(cm.STUB_FLOOR * f["stub"], d @ Ro)
    assert ((P1 - f["pivot"]) @ Ro - cap)[back].max() < ((P0 - f["pivot"]) @ Ro - cap)[back].max()


def test_a_persons_keys_are_unchanged():
    """A person's hip gets no corrective, girth or not, and every other key is the same (rig_r5: none for a hip)."""
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_rig_bend import leg
    from hifipushie import correctives as cm
    bones, V, F, J, W = leg()
    a, b = cm.keys(bones), cm.keys(bones, girth=rig.limb_girth(bones, V, J, W))
    assert [k["name"] for k in a] == [k["name"] for k in b]
    assert not any(k["motion"] == "UpLeg_flex" for k in b)
    for x, y in zip(a, b):
        assert np.array_equal(x["axis"], y["axis"]) and x["frame"]["outer"] == y["frame"]["outer"]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
