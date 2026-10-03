"""The base body's skeleton warp outside the hands (retopo._body_rotations, the twist along a bone, no radius offset
for girth): symmetric specs give symmetric bodies, a re-posed limb bends at its joints without bulges, and a spec in
the template's own pose (or that pose moved rigidly) gives the template back.

Regression for s0urc3's Garrett (MakeHuman, A-pose): per-bone minimal-arc rotations gave neighbouring bones different
rolls, the warp blended those frames across each joint, and the template's radii were read at the target frame's
angle; `_frame` isn't mirror-symmetric, so base bodies came out up to 13 mm asymmetric (right shoulder, chest).
Uses the CC0 template in the package; the MakeHuman checks run when its asset pack is present.
Run: uv run python tests/test_bodywarp.py"""
import numpy as np
from scipy.spatial import cKDTree

from hifipushie import retopo
from hifipushie.spec import expand_mirror


def _rot(axis, deg):
    k = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    a = np.radians(deg)
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


def _templates():
    out = [retopo.load_template()]
    try:
        from hifipushie import makehuman
        out.append(makehuman.body({"age": 52, "weight": 0.4, "muscle": 0.45, "height": 1.8}))
    except Exception as e:  # the MakeHuman pack isn't installed here
        print("(MakeHuman checks skipped:", str(e).splitlines()[0], ")")
    return out


def _turn(J, names, pivot, R):
    p = J[pivot].copy()
    for n in names:
        J[n] = p + (J[n] - p) @ R.T


def _posed(Jt):
    """A symmetric re-pose of the template's left side (mirrored by the spec): arm turned at the shoulder, elbow
    straightened (as an A-pose does to MakeHuman), hand pronated, thigh spread, knee bent. Joints: .L and centre."""
    J = {n: np.asarray(p, float).copy() for n, p in Jt.items() if not n.endswith(".R")}
    arm = [n for n in J if n.endswith(".L") and n.startswith(("elbow", "wrist", "finger", "thumb", "hand"))]
    _turn(J, arm, "shoulder.L", _rot([0, 1, 0.2], -18))
    fore = [n for n in arm if not n.startswith("elbow")]
    _turn(J, fore, "elbow.L", _rot(np.cross(J["wrist.L"] - J["elbow.L"], [0, 0, 1]), -25))
    hand = [n for n in fore if not n.startswith("wrist")]
    _turn(J, hand, "wrist.L", _rot(J["wrist.L"] - J["elbow.L"], 50))
    _turn(J, ["knee.L", "ankle.L", "toe.L"], "hip.L", _rot([0, 1, 0], 8))
    _turn(J, ["ankle.L", "toe.L"], "knee.L", _rot([1, 0, 0], 30))
    return J


def _warp(tpl, J):
    spec = expand_mirror({"symmetry": True, "joints": {n: {"pos": [float(x) for x in p]} for n, p in J.items()}})
    W, segs, dom, _, _ = retopo._skeleton_warp(tpl["P"], tpl["J"], spec, [], girth={})
    return np.asarray(W)


def _lap(V, faces):
    nb = [set() for _ in range(len(V))]
    for f in faces:
        f = list(f)
        for i in range(len(f)):
            nb[f[i]].add(f[i - 1])
            nb[f[i - 1]].add(f[i])
    return np.array([np.linalg.norm(V[list(n)].mean(0) - V[i]) if n else 0.0 for i, n in enumerate(nb)])


def test_symmetric():
    """A symmetric spec gives a mirror-symmetric body: the warped mesh mirrored lies on itself (nearest point,
    within the template's own asymmetry + 1 mm). Was up to 13 mm on Garrett."""
    for tpl in _templates():
        P = tpl["P"]
        W = _warp(tpl, _posed(tpl["J"]))
        own = cKDTree(P).query(P * [-1, 1, 1])[0]
        dev = cKDTree(W).query(W * [-1, 1, 1])[0]
        print(f"  {tpl['name']}: mirror deviation max {dev.max() * 1000:.2f} mm (template's own "
              f"{own.max() * 1000:.2f} mm)")
        assert dev.max() < own.max() + 1e-3, (tpl["name"], dev.max())


def test_rest_and_rigid():
    """Joints in the template's pose give the template back; the whole skeleton moved rigidly moves the body
    rigidly (FK from the pelvis/chest fits: per-bone minimal arcs rolled each bone differently)."""
    for tpl in _templates():
        P, Jt = tpl["P"], tpl["J"]
        J = {n: np.asarray(p, float) for n, p in Jt.items() if not n.endswith(".R")}
        W = _warp(tpl, J)
        assert np.abs(W - P).max() < 1e-6, (tpl["name"], np.abs(W - P).max())
        R, t = _rot([0.2, 0.1, 1.0], 35), np.array([0.3, -0.2, 0.05])
        Jr = {n: p @ R.T + t for n, p in Jt.items()}  # not mirror-symmetric any more: both sides given
        spec = {"joints": {n: {"pos": [float(x) for x in p]} for n, p in Jr.items()}}
        W = np.asarray(retopo._skeleton_warp(P, Jt, spec, [], girth={})[0])
        err = np.linalg.norm(W - (P @ R.T + t), axis=1)
        print(f"  {tpl['name']}: rigid skeleton -> body off by max {err.max() * 1000:.3f} mm")
        assert err.max() < 5e-4, (tpl["name"], err.max())


def test_joints_smooth():
    """A re-posed limb bends at its joints: no bulges or grooves at the shoulder, elbow, wrist, hip or knee (the mean
    umbrella-Laplacian length within 7 cm of each joint stays within 10% of the template's), and the shin's middle
    follows its own rigid FK transform."""
    for tpl in _templates():
        P, Jt = tpl["P"], tpl["J"]
        J = _posed(Jt)
        W = _warp(tpl, J)
        faces, _, _ = retopo.topology(tpl["L"], tpl["S"])
        L0, L1 = _lap(P, faces), _lap(W, faces)
        for j in ("shoulder.L", "elbow.L", "wrist.L", "knee.L", "hip.L"):
            m = np.linalg.norm(P - Jt[j], axis=1) < 0.07
            r = L1[m].mean() / L0[m].mean()
            print(f"  {tpl['name']}: {j} bumpiness x{r:.3f}")
            assert r < 1.1, (tpl["name"], j, r)
        Jm = {**J, **{n[:-2] + ".R": p * [-1, 1, 1] for n, p in J.items() if n.endswith(".L")}}
        segs = [sg for sg in retopo._segments(Jt) if sg[0] in Jm and sg[1] in Jm]
        rots, _ = retopo._body_rotations(Jt, Jm, segs)
        a, b = "knee.L", "ankle.L"
        k = segs.index((a, b))
        D = np.stack([retopo._seg_dist(P, Jt[x], Jt[y]) for x, y in segs], 1)
        ab = Jt[b] - Jt[a]
        s = (P - Jt[a]) @ ab / (ab @ ab)
        m = (D.argmin(1) == k) & (s > 0.35) & (s < 0.65)
        m &= D[:, k] < 1.2 * np.median(D[m, k])  # the shin's skin (not the calf's far back: a joint's blend is
        # relative to the distance from the bone, so it reaches further there)
        sax = np.linalg.norm(Jm[b] - Jm[a]) / np.linalg.norm(ab)
        want = Jm[a] + (P[m] - Jt[a]) @ rots[(a, b)].T + np.outer(
            ((P[m] - Jt[a]) @ (ab / np.linalg.norm(ab))) * (sax - 1), (Jm[b] - Jm[a]) / np.linalg.norm(Jm[b] - Jm[a]))
        err = np.linalg.norm(W[m] - want, axis=1).max()
        print(f"  {tpl['name']}: shin middle off its FK transform by max {err * 1000:.2f} mm")
        assert err < 1e-3, (tpl["name"], err)


def test_unrelated_bones():
    """Bones that share no joint don't drag each other: one arm raised and one leg spread (the other side kept) leave
    the neck, the other arm and the other thigh where they were (< 2 mm; 0-1.4 mm). The old blend reached across:
    the neck moved 2-12 mm, the other thigh 14-15 mm (MakeHuman, the template)."""
    for tpl in _templates():
        P, Jt = tpl["P"], tpl["J"]
        J = {n: np.asarray(p, float).copy() for n, p in Jt.items()}
        arm = [n for n in J if n.endswith(".R") and n.startswith(("elbow", "wrist", "finger", "thumb"))]
        _turn(J, arm, "shoulder.R", _rot([0, 1, 0], 25))
        _turn(J, ["knee.R", "ankle.R", "toe.R"], "hip.R", _rot([0, 1, 0], 12))
        spec = {"joints": {n: {"pos": [float(x) for x in p]} for n, p in J.items()}}
        W = np.asarray(retopo._skeleton_warp(P, Jt, spec, [], girth={})[0])
        segs = retopo._segments(Jt)
        D = np.stack([retopo._seg_dist(P, Jt[x], Jt[y]) for x, y in segs], 1)
        dom, Ds = D.argmin(1), np.sort(D, 1)
        clear = Ds[:, 1] > 1.5 * Ds[:, 0]  # not on the border with another bone (the crotch's midline moves with
        # either leg: the weights stay continuous there)
        for sg in (("neck", "head"), ("hip.L", "knee.L"), ("shoulder.L", "elbow.L")):
            m = (dom == segs.index(sg)) & clear
            err = np.linalg.norm(W[m] - P[m], axis=1).max()
            print(f"  {tpl['name']}: {sg[0]}->{sg[1]} moved by max {err * 1000:.2f} mm")
            assert err < 2e-3, (tpl["name"], sg, err)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
