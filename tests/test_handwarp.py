"""The base body's skeleton warp moves a hand as one piece (retopo._hand_rotations / HAND_BLEND).

Regression for the lumpy MakeHuman knuckles (s0urc3's Garrett): the A-pose straightened MakeHuman's bent forearm, so
the whole hand rotated, but every finger bone got its own minimal-arc rotation (different rolls) and the warp's blend
averaged those frames across each joint: bulging knuckles, grooves, a ring round the thumb, nail edges cut in.
Uses the CC0 template in the package (no asset packs). Run: uv run python tests/test_handwarp.py"""
import numpy as np

from hifipushie import retopo

SIDE = "L"


def _rot(axis, deg):
    k = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    a = np.radians(deg)
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


def _hand_names(J):
    return [n for n in J if n.endswith(f".{SIDE}") and n.startswith(("wrist", "finger", "thumb"))]


def _warp(J):
    tpl = retopo.load_template()
    spec = {"joints": {n: {"pos": list(map(float, p))} for n, p in J.items()}}
    W, segs, dom, _, _ = retopo._skeleton_warp(tpl["P"], tpl["J"], spec, [], girth={})
    return tpl, np.asarray(W), segs, dom


def _bent_at_elbow(Jt, deg=55.0):
    """The forearm and hand turned about the elbow (as MakeHuman's bent forearm is straightened by an A-pose)."""
    e = Jt[f"elbow.{SIDE}"]
    R = _rot([0.3, 1.0, 0.2], deg)
    J = dict(Jt)
    for n in _hand_names(Jt):
        J[n] = e + (Jt[n] - e) @ R.T
    return J, R, e - e @ R.T


def _hand_verts(P, Jt):
    """Template vertices of the hand past the blend (template space)."""
    w, e = Jt[f"wrist.{SIDE}"], Jt[f"elbow.{SIDE}"]
    ax = (w - e) / np.linalg.norm(w - e)
    return ((P - w) @ ax > retopo.HAND_BLEND + 0.005) & (np.linalg.norm(P - w, axis=1) < 0.25) & (P[:, 0] > 0.15)


def _bumpiness(V, faces, sel):
    """Mean umbrella-Laplacian length over the selected vertices (a curvature proxy: bulges and grooves raise it)."""
    nb = [set() for _ in range(len(V))]
    for f in faces:
        f = list(f)
        for i in range(len(f)):
            nb[f[i]].add(f[i - 1])
            nb[f[i - 1]].add(f[i])
    idx = np.where(sel)[0]
    return float(np.mean([np.linalg.norm(V[list(nb[i])].mean(0) - V[i]) for i in idx]))


def test_rigid_hand():
    """Joints that are a rigid motion of the template's: the hand is the template's hand moved rigidly (< 0.5 mm),
    no bumpier than it, and nothing away from the hand changes compared with the general warp."""
    tpl = retopo.load_template()
    Jt = tpl["J"]
    J, R, t = _bent_at_elbow(Jt)
    _, W, segs, dom = _warp(J)
    P = tpl["P"]
    sel = _hand_verts(P, Jt)
    assert sel.sum() > 500, sel.sum()
    err = np.linalg.norm(W[sel] - (P[sel] @ R.T + t), axis=1)
    assert err.max() < 5e-4, f"hand off the rigid move by {err.max() * 1000:.2f} mm"
    faces, _, _ = retopo.topology(tpl["L"], tpl["S"])
    b0, b1 = _bumpiness(P, faces, sel), _bumpiness(W, faces, sel)
    assert b1 < 1.02 * b0, (b0, b1)
    # the general warp (no FK hand) elsewhere: identical outside the hand
    keep = retopo._hand_rotations
    retopo._hand_rotations = lambda *a: {}
    try:
        _, W0, _, _ = _warp(J)
    finally:
        retopo._hand_rotations = keep
    w, e = Jt[f"wrist.{SIDE}"], Jt[f"elbow.{SIDE}"]
    before = (P - w) @ ((w - e) / np.linalg.norm(w - e)) < 0
    assert np.abs(W[before] - W0[before]).max() < 1e-9
    assert np.abs(W[P[:, 0] < -0.05] - W0[P[:, 0] < -0.05]).max() < 1e-9  # the other side untouched (not re-posed)
    # per-bone minimal arcs (the old general rule) are what made the lumps: well off the rigid hand
    keep_b = retopo._body_rotations
    retopo._hand_rotations = lambda *a: {}
    retopo._body_rotations = lambda Jt, Jm, segs: ({(a, b): retopo._rot_between(retopo._unit(Jt[b] - Jt[a]),
                                                                                   retopo._unit(Jm[b] - Jm[a]))
                                                    for a, b in segs}, {})
    try:
        _, W1, _, _ = _warp(J)
    finally:
        retopo._hand_rotations, retopo._body_rotations = keep, keep_b
    assert np.linalg.norm(W1[sel] - (P[sel] @ R.T + t), axis=1).max() > 2e-3


def test_curled_fingers():
    """A real re-pose (fingers curled at every joint on top of the elbow turn): each bone turns by its forward-
    kinematics rotation (a consistent roll), bone middles follow it (< 2 mm), and the hand stays about as smooth as
    the template's."""
    tpl = retopo.load_template()
    Jt = tpl["J"]
    J, R, t = _bent_at_elbow(Jt)
    side = f".{SIDE}"
    palm_n = np.cross(Jt["finger1_0" + side] - Jt["finger4_0" + side], Jt["finger2_0" + side] - Jt["wrist" + side])
    palm_n /= np.linalg.norm(palm_n)
    T = {}  # template-space FK transforms (R, t) of each finger bone
    for f in (1, 2, 3, 4):
        ch = [f"finger{f}_{k}{side}" for k in range(4)]
        Rk, tk = np.eye(3), np.zeros(3)
        pos = {n: Jt[n].copy() for n in ch}
        for k, deg in enumerate((15, 25, 12)):
            p = pos[ch[k]]
            d = pos[ch[k + 1]] - p
            Rj = _rot(np.cross(d, palm_n), deg)
            Rk, tk = Rj @ Rk, Rj @ tk + p - Rj @ p
            for n in ch[k + 1:]:
                pos[n] = p + (pos[n] - p) @ Rj.T
            T[(ch[k], ch[k + 1])] = (Rk, tk)
        for n in ch:
            J[n] = pos[n] @ R.T + t
    # each bone's rotation is the FK one: the curl composed onto the elbow turn (a consistent roll)
    Jm = {n: np.asarray(p, float) for n, p in J.items()}
    Jt2, Jm2 = dict(Jt), dict(Jm)
    for d in (Jt2, Jm2):
        d["hand_end" + side] = d["finger2_0" + side]
    rots = retopo._hand_rotations(Jt2, Jm2, retopo._segments(Jt2))
    for sg, (Rk, _) in T.items():
        Rw = R @ Rk
        assert np.degrees(np.arccos(np.clip((np.trace(rots[sg] @ Rw.T) - 1) / 2, -1, 1))) < 0.01, sg
    _, W, segs, dom = _warp(J)
    P = tpl["P"]
    faces, _, _ = retopo.topology(tpl["L"], tpl["S"])
    hand = [k for k, sg in enumerate(segs) if sg in rots and sg[0].endswith(side)]
    D = np.stack([retopo._seg_dist(P, Jt2[a], Jt2[b]) for a, b in (segs[k] for k in hand)], 1)
    Ds = np.sort(D, 1)
    clear = Ds[:, 1] > 1.6 * Ds[:, 0]  # the template's finger joints sit off-centre: only points plainly on one bone
    worst = 0.0
    for (a, b), (Rk, tk) in T.items():
        k = segs.index((a, b))
        # vertices of this bone away from its joints (a third of the bone in from each end)
        ab = Jt[b] - Jt[a]
        s = (P - Jt[a]) @ ab / (ab @ ab)
        m = (dom == k) & (s > 0.3) & (s < 0.7) & clear
        assert m.sum() >= 1, (a, b, m.sum())
        want = (P[m] @ Rk.T + tk) @ R.T + t
        worst = max(worst, np.linalg.norm(W[m] - want, axis=1).max())
    # (not exact: a re-posed hand blends its bones' transforms, and on this template the finger joints sit off-centre
    # and the fingers close together, so bone middles still see their neighbours a little)
    assert worst < 2e-3, f"bone middles off their FK transform by {worst * 1000:.2f} mm"
    sel = _hand_verts(P, Jt)
    b0, b1 = _bumpiness(P, faces, sel), _bumpiness(W, faces, sel)
    assert b1 < 1.15 * b0, (b0, b1)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
