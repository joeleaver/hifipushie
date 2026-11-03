"""F4 (piece_start.py, tape_geom.py): every piece starts where its OWN measurements were taken. On a synthetic
two-legged body: a tube (front + back of one side sewn on two edges, naming girths taken on that side) starts round the
loops it was measured at, the .R pair round the mirrored ones; an open panel starts between its tapes (its top at the
top of the length path that spans it); a piece naming nothing starts on the old fallback, said by name. Step 4's
per-piece list comes from step 1's seams + the draft parts' own measurements."""
import numpy as np

from hifipushie import chain_garment as cg, piece_start as ps
from test_chain_loops import _pattern


def _cyl(cx, r, z0, z1, nz=12, na=24):
    th = np.linspace(0, 2 * np.pi, na, endpoint=False)
    zs = np.linspace(z0, z1, nz)
    V = np.concatenate([np.c_[cx + r * np.sin(th), -r * np.cos(th), np.full(na, z)] for z in zs])
    F = [[i * na + j, i * na + (j + 1) % na, (i + 1) * na + (j + 1) % na] for i in range(nz - 1) for j in range(na)]
    F += [[i * na + j, (i + 1) * na + (j + 1) % na, (i + 1) * na + j] for i in range(nz - 1) for j in range(na)]
    return V, np.array(F)


def _two_legs():
    """Torso r 0.15 (z 0.85-1.45) and two legs r 0.07 at x = +-0.10 (z 0.02-0.85)."""
    Vs, Fs, k = [], [], 0
    for cx, r, z0, z1 in ((0.0, 0.15, 0.85, 1.45), (0.10, 0.07, 0.02, 0.86), (-0.10, 0.07, 0.02, 0.86)):
        V, F = _cyl(cx, r, z0, z1)
        Vs.append(V), Fs.append(F + k)
        k += len(V)
    at = {"hps.L": [0.06, 0.0, 1.45], "cf_neck": [0.0, -0.06, 1.44], "cb_neck": [0.0, 0.06, 1.46],
          "shoulder.L": [0.18, 0.0, 1.43], "elbow.L": [0.25, 0.0, 1.15], "wrist.L": [0.30, 0.0, 0.90],
          "armpit_z": 1.30, "chest_z": 1.28, "waist_z": 1.10, "hips_z": 0.95, "crotch_z": 0.86}
    return cg.Body(np.concatenate(Vs), np.concatenate(Fs), at)


def _loop(cx, r, z, n=32):
    th = np.linspace(0, 2 * np.pi, n + 1)
    return np.c_[cx + r * np.sin(th), -r * np.cos(th), np.full(n + 1, z)].tolist()


TAPES = {"thigh": {"kind": "loop", "pts": _loop(0.10, 0.075, 0.75)},
         "knee": {"kind": "loop", "pts": _loop(0.10, 0.07, 0.45)},
         "outseam": {"kind": "path", "pts": [[0.17, 0.0, 1.10], [0.17, 0.0, 0.50], [0.17, 0.0, 0.02]]},
         "waist": {"kind": "loop", "pts": _loop(0.0, 0.15, 1.10)},
         "waistToKnee": {"kind": "path", "pts": [[0.15, 0.0, 1.10], [0.15, 0.0, 0.45]]}}


def _build(pieces, names, sew_cols=()):
    pat, vid = _pattern(pieces)
    sew = [[vid(a, ca, r), vid(b, cb, r)] for a, ca, b, cb in sew_cols for r in range(pieces[a][5])]
    pat.M["sew"] = np.array(sew, np.int64).reshape(-1, 2)
    pat.M["starts"] = {"pieces": names, "tapes": TAPES}
    return cg.GarmentBuild(pat, _two_legs(), {"state": "closed"}, log=lambda *_: None)


LEG = (0.0, 0.25, -1.08, 0.0, 6, 12)  # (a leg piece's flat: 0.25 wide, waist to floor; front + back: 0.50 round)


def test_a_tube_starts_round_the_loops_it_was_measured_at():
    pieces = {"front.L": LEG, "back.L": LEG, "front.R": LEG, "back.R": LEG}
    leg = ["thigh", "knee", "outseam"]
    b = _build(pieces, {p: leg for p in pieces},
               [("front.L", 0, "back.L", 0), ("front.L", 5, "back.L", 5), ("front.R", 0, "back.R", 0),
                ("front.R", 5, "back.R", 5)])
    R = b.roles
    assert set(R.tubes) == set(pieces) and not R.panels
    assert sorted(R.tube_groups["front.L"]) == ["back.L", "front.L"]
    for p, sx in (("front.L", 1), ("front.R", -1)):
        v = b.net.verts(p)
        X = b._tube_points(p, v)
        knee = np.abs(X[:, 2] - 0.45) < 0.06
        assert knee.any()
        c = X[knee][:, :2]
        d = np.hypot(c[:, 0] - sx * 0.10, c[:, 1])  # round ITS leg at the knee loop, at the pattern's radius
        assert np.allclose(d, 0.5 / (2 * np.pi), atol=0.012), (p, d.min(), d.max())
        assert X[:, 2].max() <= 1.10 + 0.02 and X[:, 2].min() >= 0.0  # (along the outseam's path: waist to floor)
    assert "tube round its own measurements: loops thigh, knee, along outseam" in str(b.reads["starts"])


def test_a_panel_starts_between_its_tapes_and_the_fallback_is_named():
    pieces = {"skirt": (-0.25, 0.25, -0.62, 0.0, 6, 8), "apron": (-0.2, 0.2, -0.3, 0.0, 5, 4)}
    b = _build(pieces, {"skirt": ["waist", "waistToKnee"], "apron": []})
    assert b.roles.panels == ["skirt", "apron"]  # (a waist loop holds the centre line: not a tube)
    dz = ps.panel_dz(b, "skirt")
    assert abs((1.45 + 0.0 + dz) - 1.10) < 1e-6  # (its top at the waist: the top of waistToKnee, which spans it)
    assert ps.panel_dz(b, "apron") == 0.0
    assert b.reads["starts"]["apron"].startswith("FALLBACK")
    assert "top of waistToKnee" in b.reads["starts"]["skirt"]


def test_a_tube_naming_no_sided_girth_falls_back_by_name():
    pieces = {"sleeve.L": (0.0, 0.3, -0.6, 0.0, 6, 8)}
    b = _build(pieces, {"sleeve.L": ["waist"]}, [("sleeve.L", 0, "sleeve.L", 5)])
    assert b.roles.tubes == ["sleeve.L"]  # (sewn to itself: a tube, by the old rule)
    X = b._tube_points("sleeve.L", b.net.verts("sleeve.L"))
    assert np.isfinite(X).all()
    assert any(v.startswith("FALLBACK") for v in b.reads["starts"].values())


def test_step4_lists_each_pieces_measurements():
    step1 = {"seams": [{"a": "front:side", "b": "back:side", "length": {"body": ["waistToFloor"]}},
                       {"a": "front:inseam", "b": "back:inseam", "length": {"body": ["inseam"]}},
                       {"a": "band:bottom", "b": "front:waist", "length": {"body": ["waist"]}}]}
    decl = {"pieces": {"front": {"part": "tr.front", "pair": True}, "back": {"part": "tr.back", "pair": True},
                       "band": {"part": "tr.band"}}}
    cfg = {"tr.front": {"measurements": ["upperLeg", "knee"]}, "tr.back": {"measurements": ["seat"]}}
    out = ps.piece_measurements(step1, decl, cfg, ["front.L", "front.R", "back.L", "back.R", "band"])
    assert out["front.L"] == out["front.R"] == ["inseam", "knee", "upperLeg", "waist", "waistToFloor"]
    assert out["back.R"] == ["inseam", "seat", "waistToFloor"] and out["band"] == ["waist"]


def test_a_panel_naming_an_armhole_girth_is_no_tube():
    """Front + back halves of one side joined by two seams (shoulder, side), naming a girth on that side (the armhole's)
    whose loop their own length (down the torso's side) doesn't run along: panels, not a tube round the arm."""
    tapes = dict(TAPES, arm={"kind": "loop", "pts": [[0.22 + 0.05 * np.cos(a) * 0.7, -0.05 * np.sin(a), 1.38 - 0.05 * np.cos(a) * 0.7]
                                                     for a in np.linspace(0, 2 * np.pi, 33)]},
                 side={"kind": "path", "pts": [[0.15, 0.0, 1.30], [0.15, 0.0, 1.10]]})
    pieces = {"front.L": (0.0, 0.25, -0.6, 0.0, 6, 8), "back.L": (0.0, 0.25, -0.6, 0.0, 6, 8)}
    pat, vid = _pattern(pieces)
    pat.M["sew"] = np.array([[vid("front.L", c, 7), vid("back.L", c, 7)] for c in range(2)] +
                            [[vid("front.L", 5, r), vid("back.L", 5, r)] for r in range(4)], np.int64)
    pat.M["starts"] = {"pieces": {p: ["arm", "side"] for p in pieces}, "tapes": tapes}
    b = cg.GarmentBuild(pat, _two_legs(), {"state": "closed"}, log=lambda *_: None)
    assert sorted(b.roles.panels) == ["back.L", "front.L"] and not b.roles.tubes
