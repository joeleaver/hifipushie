"""Age as soft-tissue ops on the head (headage.py; base.head.shape nasolabial / prejowl / lid_fold / cheek_flat /
lips_thin). uv run python tests/test_headage.py"""
import copy
import sys

import numpy as np

from hifipushie import assets, headage, humanfit as hf


def _have():
    try:
        assets.pack("gnm")
        assets.pack("makehuman")
        return True
    except Exception as err:
        print("skipped:", str(err)[:80])
        return False


def base(seed=3):
    return {"body": {"source": "human", "age": 50, "sex": 1.0}, "head": {"seed": seed, "spread": 0.5}}


_S0 = {}


def state0():
    if "st" not in _S0:
        _S0["st"] = hf.state(base())
    return _S0["st"]


def moved(shape):
    b = base()
    b["head"]["shape"] = shape
    st0, st1 = state0(), hf.state(b)
    P0, P1 = np.asarray(st0["tpl"]["P"]), np.asarray(st1["tpl"]["P"])
    return b, st0, st1, P0, P1, P1 - P0


def _sides(P0, d, mx):
    return [float(np.linalg.norm(d[np.sign(P0[:, 0] - mx) == sg], axis=1).max()) for sg in (-1, 1)]


def test_unset_is_identical():
    """No age key: headage is never applied (the head is the same array to the bit); a key at 0 as well."""
    b = base()
    b["head"]["shape"] = {"nasolabial": 0, "prejowl": 0.0, "lips_thin": 0}
    P0, P1 = np.asarray(state0()["tpl"]["P"]), np.asarray(hf.state(b)["tpl"]["P"])
    assert np.array_equal(P0, P1)
    assert not headage.wanted({"planes": 2.3, "lean": 0.004})


def test_nasolabial_fold():
    """A crease on skin's own nasolabial line, as deep as asked (within the smoothing), the cheek's side standing over
    it, both sides alike; the eyes, brows and the jaw's border stay; nothing folds. Half the length ends higher."""
    b, st0, st1, P0, P1, d = moved({"nasolabial": {"depth": 0.003}})
    L0, L1 = st0["L"], st1["L"]
    mx = float(L0[27][0])
    for side in (-1, 1):
        line = headage.nasolabial_line(L0, side)
        mid = line[len(line) // 2]
        near = np.linalg.norm(P0 - mid, axis=1) < 0.012
        dy = d[near][:, 1]                       # the face looks along -y: in = +y
        assert 0.0012 < dy.max() < 0.0036, dy.max()
        crease = P0[near][np.argmax(dy)]
        pad = P0[near][np.argmin(dy)]
        assert dy.min() < -0.0003, dy.min()      # the pad stands out
        assert abs(pad[0] - mx) > abs(crease[0] - mx)        # ... on the cheek's side
    s = _sides(P0, d, mx)
    assert abs(s[0] - s[1]) < 0.0006, s
    assert np.linalg.norm(L1[17:31] - L0[17:31], axis=1).max() < 0.0003 and np.linalg.norm(L1[36:48] - L0[36:48], axis=1).max() < 0.0003
    assert np.linalg.norm(L1[0:17] - L0[0:17], axis=1).max() < 0.0006
    it = hf.integrity(b, st1, st0)
    assert it["ok"] and it["numbers"]["folded_faces"] < hf.FOLD_LIMIT, it
    _, _, _, _, _, dh = moved({"nasolabial": {"depth": 0.003, "length": 0.5}})
    lo = P0[:, 2] < L0[48][2] - 0.004
    assert np.linalg.norm(dh[lo], axis=1).max() < 0.4 * np.linalg.norm(d[lo], axis=1).max()


def test_prejowl_and_jowl():
    """A dent on the jaw's border between chin and jowl, a fuller jowl behind it that comes down; the chin and the
    upper face stay."""
    b, st0, st1, P0, P1, d = moved({"prejowl": {"depth": 0.003, "jowl": 0.002}})
    L0, L1 = st0["L"], st1["L"]
    mx = float(L0[8][0])
    n = np.linalg.norm(d, axis=1)
    for i_s, i_j in ((6, 5), (10, 11)):
        ns = np.linalg.norm(P0 - L0[i_s], axis=1) < 0.012
        assert n[ns].max() > 0.0012
        nj = np.linalg.norm(P0 - (L0[i_j] + [0, 0, 0.007]), axis=1) < 0.014
        assert d[nj][:, 2].min() < -0.0004, d[nj][:, 2].min()   # the jowl comes down
    assert np.linalg.norm(L1[17:48] - L0[17:48], axis=1).max() < 0.0003
    assert np.linalg.norm(L1[8] - L0[8]) < 0.0008
    s = _sides(P0, d, mx)
    assert abs(s[0] - s[1]) < 0.0008, s
    it = hf.integrity(b, st1, st0)
    assert it["ok"], it


def test_lid_fold_is_lateral_and_leaves_the_margin():
    """The skin between lid and brow comes down, more over the outer half; the lid's margin (its landmarks) moves
    less than a third of that; the lower lid not at all."""
    b, st0, st1, P0, P1, d = moved({"lid_fold": 0.003})
    L0, L1 = st0["L"], st1["L"]
    mx = float(L0[27][0])
    for up, (c_in, c_out), brow, low in (((37, 38), (39, 36), (18, 19, 20), (40, 41)), ((43, 44), (42, 45), (23, 24, 25), (46, 47))):
        U, B = L0[list(up)].mean(0), L0[list(brow)].mean(0)
        zone = (np.linalg.norm(P0 - (U + 0.6 * (B - U)), axis=1) < 0.014)
        drop = -d[zone][:, 2]
        assert 0.0012 < drop.max() < 0.0034, drop.max()
        inner = zone & (np.abs(P0[:, 0] - L0[c_in][0]) < 0.006)
        outer = zone & (np.abs(P0[:, 0] - L0[c_out][0]) < 0.006)
        assert (-d[outer][:, 2]).max() > 1.5 * max((-d[inner][:, 2]).max(), 1e-6)
        assert np.linalg.norm(L1[list(up)] - L0[list(up)], axis=1).max() < 0.34 * drop.max()
        assert np.linalg.norm(L1[list(low)] - L0[list(low)], axis=1).max() < 0.0002
    it = hf.integrity(b, st1, st0)
    assert it["ok"], it


def test_cheek_flat():
    """The front of the cheek under the orbit moves in and a little down; the nose, lips, lids and jaw stay."""
    b, st0, st1, P0, P1, d = moved({"cheek_flat": 0.003})
    L0, L1 = st0["L"], st1["L"]
    for lid, corner in ((41, 48), (46, 54)):
        c = 0.6 * L0[lid] + 0.4 * L0[corner]
        near = np.linalg.norm(P0[:, [0, 2]] - c[[0, 2]], axis=1) < 0.012
        near &= P0[:, 1] < c[1] + 0.02
        assert d[near][:, 1].max() > 0.001, d[near][:, 1].max()   # in (+y)
        assert d[near][:, 2].min() < -0.0002
    for ids in (range(27, 36), range(36, 48), range(48, 68), range(0, 17)):
        assert np.linalg.norm(L1[list(ids)] - L0[list(ids)], axis=1).max() < 0.0007, list(ids)[:2]
    it = hf.integrity(b, st1, st0)
    assert it["ok"], it


def test_lips_thin():
    """The vermilion's height falls by about the share asked; the mouth's corners, its width and the nose stay."""
    b, st0, st1, P0, P1, d = moved({"lips_thin": 0.3})
    L0, L1 = st0["L"], st1["L"]
    h0 = (L0[51][2] - L0[62][2]) + (L0[66][2] - L0[57][2])
    h1 = (L1[51][2] - L1[62][2]) + (L1[66][2] - L1[57][2])
    assert 0.6 < h1 / h0 < 0.85, (h0, h1)
    assert np.linalg.norm(L1[[48, 54]] - L0[[48, 54]], axis=1).max() < 0.0006
    assert np.linalg.norm(L1[27:36] - L0[27:36], axis=1).max() < 0.0006
    far = np.linalg.norm(P0 - 0.5 * (L0[62] + L0[66]), axis=1) > 0.05
    assert np.linalg.norm(d[far], axis=1).max() < 1e-4
    it = hf.integrity(b, st1, st0)
    assert it["ok"], it


def test_eye_bag_under_the_lower_lid():
    """eye_bag: the skin under each lower lid stands out (toward the face's front), a crease under it goes in, the
    lid's margin landmarks barely move, the upper lid and brow not at all; both eyes alike."""
    b, st0, st1, P0, P1, d = moved({"eye_bag": {"amount": 0.0015, "crease": 0.6}})
    L0, L1 = st0["L"], st1["L"]
    out = []
    for low, corners, up in (((40, 41), (36, 39), (37, 38)), ((46, 47), (42, 45), (43, 44))):
        Lw = L0[list(low)].mean(0)
        wid = float(np.linalg.norm(L0[corners[0]] - L0[corners[1]]))
        bag = np.linalg.norm(P0 - (Lw - [0, 0, 0.1 * wid]), axis=1) < 0.003
        fwd = -d[bag][:, 1]
        assert fwd.max() > 0.0006, fwd.max()
        out.append(fwd.max())
        crease = np.linalg.norm(P0 - (Lw - [0, 0, 0.25 * wid]), axis=1) < 0.004
        assert d[crease][:, 1].max() > 0.0001                       # pushed back somewhere along the crease
        assert np.linalg.norm(L1[list(low)] - L0[list(low)], axis=1).max() < 0.4 * fwd.max()
        assert np.linalg.norm(L1[list(up)] - L0[list(up)], axis=1).max() < 1e-4
    assert abs(out[0] - out[1]) < 0.25 * max(out)
    it = hf.integrity(b, st1, st0)
    assert it["ok"], it


def test_hood_lateral_hangs_over_the_outer_corner():
    """shape.hood "lateral": the fold comes down more over the outer part of the lid than the inner; lateral 0 is the
    old hood to the bit."""
    b0, st0, sth, P0, Ph, dh = moved({"hood": 0.002})
    b1, _, st1, _, P1, d1 = moved({"hood": {"amount": 0.002, "lateral": 0.0}})
    assert np.array_equal(Ph, P1)
    b2, _, st2, _, P2, d2 = moved({"hood": {"amount": 0.002, "lateral": 1.0}})
    L0 = st0["L"]
    for up, (c_in, c_out), brow in (((37, 38), (39, 36), (18, 19, 20)), ((43, 44), (42, 45), (23, 24, 25))):
        U, B = L0[list(up)].mean(0), L0[list(brow)].mean(0)
        zone = np.linalg.norm(P0 - (U + 0.3 * (B - U)), axis=1) < 0.016
        inner = zone & (np.abs(P0[:, 0] - L0[c_in][0]) < 0.005)
        outer = zone & (np.abs(P0[:, 0] - L0[c_out][0]) < 0.005)
        assert (-d2[outer][:, 2]).max() > 2.0 * (-d2[inner][:, 2]).max()
        assert (-d2[outer][:, 2]).max() > 0.8 * (-dh[outer][:, 2]).max()
    it = hf.integrity(b2, st2, st0)
    assert it["ok"], it


def test_hood_crease_is_a_groove_over_the_lid():
    """shape.hood "crease": a groove pressed back (+y) along a line between the lid margin and the brow, deepest on
    that line, the lid margin and the brow barely moving; crease 0 is the hood without it to the bit."""
    _, st0, _, P0, Ph, _ = moved({"hood": {"amount": 0.0012, "lateral": 1.0}})
    _, _, _, _, P1, _ = moved({"hood": {"amount": 0.0012, "lateral": 1.0, "crease": 0.0}})
    assert np.array_equal(Ph, P1)
    b2, _, st2, _, P2, _ = moved({"hood": {"amount": 0.0012, "lateral": 1.0, "crease": 0.0012}})
    d = P2 - Ph
    L0 = st0["L"]
    for up, brow in (((37, 38), (18, 19, 20)), ((43, 44), (23, 24, 25))):
        U, B = L0[list(up)].mean(0), L0[list(brow)].mean(0)
        line = np.linalg.norm(P0 - (U + 0.3 * (B - U)), axis=1) < 0.003
        assert d[line][:, 1].max() > 0.0006, d[line][:, 1].max()
        brow_pts = np.linalg.norm(P0 - B, axis=1) < 0.003
        assert np.abs(d[brow_pts]).max() < 0.0002
    it = hf.integrity(b2, st2, st0)
    assert it["ok"], it


if __name__ == "__main__":
    if _have():
        names = sys.argv[1:] or [k for k in dict(globals()) if k.startswith("test_")]
        for k in names:
            globals()[k]()
            print("ok", k)
