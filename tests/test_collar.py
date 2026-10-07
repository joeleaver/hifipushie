"""The notched (tailored) collar: its roll line in the draft, and its made lay (cloth._notched_lay: a band on the worn
neckline + a flat end in the turned lapel's plane). The lay test needs a model with a body (workspace `ga_suit`: the
drafted blazer); without it only the draft is tested.
Run: uv run python tests/test_collar.py"""
import json

import numpy as np

from hifipushie import pattern, pattern_draft as pd

MM = {"neck": 370.5, "shoulderSlope": 29.0, "shoulderToShoulder": 463.9, "chest": 994.0, "waist": 776.3, "hips": 920.6,
      "seat": 972.2, "biceps": 340.2, "wrist": 148.6, "shoulderToElbow": 300.3, "shoulderToWrist": 570.0,
      "hpsToWaistBack": 545.0, "hpsToBust": 331.1, "highBust": 994.0, "waistToArmpit": 230.7, "waistToHips": 145.2,
      "waistToSeat": 245.2, "waistToFloor": 1109.3, "waistToKnee": 585.4, "head": 560.0, "waistToUpperLeg": 251.1,
      "inseam": 858.2}


def _notched():
    D = pd.start("bodice", MM, {"fitted": True})
    pd.apply(D, [{"op": "lapel", "break_y": 0.40, "stand": 0.02, "width": 0.085, "gorge": "straight", "gorge_drop": 0.085},
                 {"op": "collar", "type": "tailored", "stop": 0.0, "stand_height": 0.03, "fall": 0.045}])
    return D


def test_roll_line_meets_the_lapels():
    """The collar's roll line stands a stand's height at centre back and comes down to the neck edge where the lapel's
    roll line crosses the neckline, at that line's own angle; the wrap carries it run on into the front, and asks for
    the notched lay."""
    D = _notched()
    c = D["pieces"]["collar"]
    w = c["wrap"]
    assert w["to"] == "seam" and w["worn"] and w["lay"] == "notched", w
    lb = pd.edge_length(D, D["edges"]["neck_back"])
    neck = pd.edge_length(D, D["edges"]["collar_neck"])
    sx = D["meta"]["collar_roll_end"]
    assert lb < sx < neck - 0.02, (lb, sx, neck)  # past the neck point, before the collar's end: a gorge to lie along
    L = np.asarray(w["turn"]["line"])  # (half: the mirrored half is added when the piece is unfolded)
    E = pattern._resampled(c["P"][pattern.arc_indices(c, "cb>shoulderNotch>cf")], 0.002)
    d_end = np.linalg.norm(E - L[-2], axis=1).min()
    assert d_end < 1e-3, d_end  # the line's last point before the run-on lies on the neck edge
    assert np.linalg.norm(E - L[-1], axis=1).min() > 0.05  # ... and the run-on leaves the piece
    # one line: the run-on continues the roll line's last stretch (no kink over 15 deg)
    a, b = L[-2] - L[-4], L[-1] - L[-2]
    cosk = float(a @ b / np.linalg.norm(a) / np.linalg.norm(b))
    assert cosk > np.cos(np.radians(15)), np.degrees(np.arccos(cosk))
    f = next(f for f in D["folds"] if f["piece"] == "collar")
    assert f.get("in_wrap") and isinstance(f["line"], list)
    # "roll": "parallel" keeps the old constant stand (no notched lay)
    D2 = pd.start("bodice", MM, {"fitted": True})
    pd.apply(D2, [{"op": "lapel", "break_y": 0.40, "stand": 0.02, "width": 0.085},
                  {"op": "collar", "type": "tailored", "roll": "parallel"}])
    assert "lay" not in D2["pieces"]["collar"]["wrap"]


def _placed():
    from hifipushie import cloth, store
    try:
        spec = store.load("ga_suit")
    except Exception:
        return None
    g = json.loads(json.dumps(spec["cloth"]["jacket"]))
    g["over"] = None
    g["made"] = {}
    return cloth, cloth.build(cloth._garment_for_sim(g), cloth.model_body("ga_suit", spec, g), "ga_suit:jacket",
                              log=lambda *a: None, place_only=True)


def test_made_lay():
    """The blazer's collar, made, as the sim gets it: no triangle past 1.3 x its pattern, the neck edge the seam's
    clearance off the body all along the band, the stand up the neck, the fall turned down over the neck seam at
    centre back, the end flat (isometric) and resting on the chest, nothing crossing the collar; it is one made
    construction, carried."""
    got = _placed()
    if got is None:
        print("   (no model ga_suit in the workspace: the lay is not tested)")
        return
    cloth, res = got
    M, X, Bp, body = res["coarse"], res["Xs"], res["pieces"], res["placed_on"]
    names, F, pid, uv = M["names"], M["F"], M["piece"], M["uv"]
    assert M["made"] == ["collar"] and res["carry"]["pieces"] == ["collar"], (M["made"], res["carry"]["pieces"])
    assert res["carry"]["roots"] == {"collar": "collar"}
    kc = names.index("collar")
    Fc = F[pid[F[:, 0]] == kc]
    E = np.unique(np.sort(np.r_[Fc[:, [0, 1]], Fc[:, [1, 2]], Fc[:, [2, 0]]], 1), axis=0)
    rt = np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    assert rt.max() < 1.3, rt.max()
    far = np.abs(uv[E].mean(1)[:, 0]) > 0.16  # the end: a flat board
    assert far.any() and abs(np.median(rt[far]) - 1) < 0.03 and rt[far].max() < 1.1, (np.median(rt[far]), rt[far].max())
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    mine = np.r_[sw[pid[sw[:, 0]] == kc, 0], sw[pid[sw[:, 1]] == kc, 1]]
    band = mine[np.abs(uv[mine, 0]) < 0.07]
    cl = body.clearance(X[band])
    assert cl.min() > 0.003 and cl.max() < 0.012, (cl.min(), cl.max())  # on the neck, not in it and not off it
    cb = np.where((pid == kc) & (np.abs(uv[:, 0]) < 0.012))[0]
    cb = cb[np.argsort(uv[cb, 1])]
    z = X[cb, 2] - X[cb[0], 2]
    top = int(np.argmax(z))
    assert 0.02 < z[top] < 0.035 and abs(uv[cb[top], 1] - 0.03) < 0.006, (z[top], uv[cb[top]])  # the stand stands
    assert z[-1] < -0.005, z[-1]  # the fall's edge hangs below the neck seam: it covers it
    assert float(body.clearance(X[cb]).max()) < 0.02  # ... and lies on the neck and the back, not off them
    assert not [p for p in cloth._piece_crossings(X, M) if "collar" in p]
    assert float(body.clearance(X[pid == kc]).min()) > 0.002
    # the sim starts with the fall OPEN (sewn on before it is turned down): standing up off the neck at centre
    # back, nothing crossing, and the carried poses end on the closed lay
    Xo = res["Xstart"]
    top = cb[np.argmax(uv[cb, 1])]
    assert Xo[top, 2] - Xo[cb[0], 2] > 0.04, Xo[top, 2] - Xo[cb[0], 2]
    assert not [p for p in cloth._piece_crossings(Xo, M) if "collar" in p]
    car = res["carry"]
    ci = {int(v): i for i, v in enumerate(car["idx"])}
    assert np.allclose(car["poses"][-1][ci[int(top)]], X[top], atol=0.03)
    # mirror symmetric (one construction, both sides)
    vc = np.where(pid == kc)[0]
    from scipy.spatial import cKDTree
    dm, jm = cKDTree(uv[vc]).query(uv[vc] * [-1, 1])
    ok = dm < 1e-4  # vertices whose mirror in the pattern is a vertex too
    asym = np.linalg.norm(X[vc[ok]] - X[vc[jm[ok]]] * [-1, 1, 1], axis=1)
    assert ok.sum() > 20 and np.percentile(asym, 95) < 0.003, (ok.sum(), np.percentile(asym, 95))


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
