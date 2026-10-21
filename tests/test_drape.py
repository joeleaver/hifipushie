"""KATs for drape.py (drape band round 1): a stand + fall draped on a cylinder neck over a shoulder cone, a cuff on a
cylinder wrist, and one collar's closed vs open sweep."""
import math

import numpy as np

from hifipushie import drape

R_NECK, Z_TOP, Z_SH, R_SH = 0.060, 0.14, -0.05, 0.20
ALPHA = math.atan2(-Z_SH, R_SH - R_NECK)  # the shoulder cone's slope (down from horizontal)
STAND_OFF = 0.002


def _rev(profile, n_t=96):
    """A surface of revolution round Z: profile (k, 2) of (r, z) -> (V, F)."""
    t = np.linspace(0, 2 * np.pi, n_t, endpoint=False)
    V = np.array([[r * np.cos(a), r * np.sin(a), z] for r, z in profile for a in t])
    F = []
    for i in range(len(profile) - 1):
        for j in range(n_t):
            a, b = i * n_t + j, i * n_t + (j + 1) % n_t
            c, d = a + n_t, b + n_t
            F += [[a, b, d], [a, d, c]]
    return V, np.array(F)


def _axis_out(cen):
    o = cen.copy()
    o[:, 2] = 0.0
    return o


def _neck_body():
    prof = [(R_SH, Z_SH)] + [(R_NECK + (R_SH - R_NECK) * (1 - f), Z_SH * (1 - f)) for f in np.linspace(0.1, 1, 12)] + \
           [(R_NECK, z) for z in np.linspace(0.005, Z_TOP, 30)]
    V, F = _rev(prof)
    body = drape.Surf(V, F, out=_axis_out)
    cone = [(R_SH, Z_SH)] + [(R_NECK + (R_SH - R_NECK) * (1 - f), Z_SH * (1 - f)) for f in np.linspace(0.05, 1, 30)]
    Vc, Fc = _rev(cone, 160)
    under = drape.Surf(Vc, Fc, out=_axis_out)
    return body, under


def _neckline(r=R_NECK + STAND_OFF, n=121, straighten=0.0, drop=0.0):
    """Half neckline CB (+Y) -> CF (-Y) through +X; `straighten`: the front half's plan curvature reduced by this share
    (an open neck: the fronts' neck edges swing out, the length kept), `drop`: the CF end lowered (m)."""
    s = np.linspace(0, math.pi * r, n)
    k = np.full(n, 1 / r)
    u = s / s[-1]
    k *= 1 - straighten * np.clip((u - 0.5) / 0.5, 0, 1) ** 1.5
    th = np.r_[0, np.cumsum(0.5 * (k[1:] + k[:-1]) * np.diff(s))]
    d = np.c_[np.cos(-th), np.sin(-th)]  # heading: CB at (0, r) heading +X
    xy = np.r_[[[0.0, r]], np.cumsum(0.5 * (d[1:] + d[:-1]) * np.diff(s)[:, None], 0) + [0.0, r]]
    z = -drop * np.clip((u - 0.5) / 0.5, 0, 1) ** 2
    return np.c_[xy, z]


def _entry(H=0.032, land=0.010, rise=0.006):
    return {"name": "kat collar", "state": "closed",
            "layers": [{"piece": "stand", "kind": "stand", "height": H, "ext": 0.0},
                       {"piece": "collar", "kind": "fall", "rise": rise, "land": land, "end_in": 0.0, "point": 0.0}]}


TURN = {"w": 0.0015, "lay": 0.0015}


def test_stand_and_fall_on_a_cylinder_neck_over_a_shoulder_cone():
    body, under = _neck_body()
    C = _neckline()
    base = {"curve": C, "body": body, "under": under, "s_cf": drape._arc(C)[-1]}
    e = dict(_entry(), turn=TURN)
    d = drape.draft(e, base)
    rep = d["report"]["layers"]
    # flattening: a stand on a cylinder and a fall on a cone are developable
    assert rep["stand"]["strain_p99_pct"] < 0.5, rep
    assert rep["collar"]["strain_p99_pct"] < 1.5, rep
    # the stand: a straight band as long as the neckline, as high as asked
    st = d["pieces"]["stand"]
    P, nm = np.asarray(st["P"]), st["names"]
    assert abs(P[nm["topMid"]][1] - P[nm["bottomMid"]][1] - 0.032) < 0.0005
    assert abs(rep["stand"]["flat_bottom_mm"] - 2 * math.pi * (R_NECK + STAND_OFF) * 1000) < 2.0, rep
    # the fall's outer edge = the analytic landing path: the half circle where its edge lies on the cone
    k0 = np.array([R_NECK + STAND_OFF, 0.0])  # (the march starts at the seam)
    p0 = np.array([R_NECK + TURN["lay"] * math.sin(ALPHA), TURN["lay"] * math.cos(ALPHA)])
    dv = np.array([math.cos(ALPHA), -math.sin(ALPHA)])
    t = float((k0 - p0) @ dv)
    proj = p0 + t * dv
    delta = float(np.linalg.norm(k0 - proj))
    r_edge = proj[0] + (0.010 - delta) * math.cos(ALPHA)
    path_full = 2 * math.pi * r_edge * 1000  # (the whole collar: both halves round the neck)
    assert abs(rep["collar"]["flat_top_mm"] - path_full) / path_full < 0.01, (rep["collar"], path_full)
    # the sewn edge trues to the stand's top
    tr = d["report"]["truing"]
    assert abs(tr["stand_top_flat_mm"] - tr["fall_sewn_flat_mm"]) < 1.5, tr
    # the fit reproduces the sweep: the flat lengths relaxed from the drape stay on it (within 2 mm)
    for nm_ in ("stand", "collar"):
        m = d["mesh"][nm_]
        X = m["X"] + np.random.default_rng(0).normal(0, 0.0003, m["X"].shape)
        X = _relax(X, m["uv"], m["F"])
        dist = np.linalg.norm(X - m["X"], axis=1)
        assert dist.max() < 0.002, (nm_, dist.max())
    # placement from the drape: a vertex at a grid node lands on its worn point
    m = d["mesh"]["collar"]
    Xp = drape.place_on_drape(m["uv"][:50], m)
    assert np.abs(Xp - m["X"][:50]).max() < 1e-6


def _relax(X, U, F, iters=200):
    E = drape._edges(F)
    L0 = np.linalg.norm(U[E[:, 0]] - U[E[:, 1]], axis=1)
    X = X.copy()
    for _ in range(iters):
        d = X[E[:, 1]] - X[E[:, 0]]
        L = np.linalg.norm(d, axis=1) + 1e-15
        corr = (0.5 * (L - L0) / L)[:, None] * d
        acc = np.zeros_like(X)
        cnt = np.zeros(len(X))
        np.add.at(acc, E[:, 0], corr)
        np.add.at(acc, E[:, 1], -corr)
        np.add.at(cnt, E[:, 0], 1)
        np.add.at(cnt, E[:, 1], 1)
        X += 0.8 * acc / np.maximum(cnt, 1)[:, None]
    return X


def test_cuff_on_a_cylinder_wrist():
    Rw = 0.030
    V, F = _rev([(Rw, z) for z in np.linspace(-0.02, 0.12, 40)])
    wrist = drape.Surf(V, F, out=_axis_out)
    Vs, Fs = _rev([(Rw + 0.004, z) for z in np.linspace(-0.08, 0.02, 30)], 128)
    sleeve = drape.Surf(Vs, Fs, out=_axis_out)
    C = _neckline(r=Rw + STAND_OFF)
    base = {"curve": C, "body": wrist, "under": sleeve, "s_cf": drape._arc(C)[-1]}
    # a band cuff: a rectangle as long as the wrist round
    e = {"name": "cuff", "turn": TURN, "layers": [{"piece": "cuff", "kind": "stand", "height": 0.06, "ext": 0.0}]}
    d = drape.draft(e, base)
    r = d["report"]["layers"]["cuff"]
    assert r["strain_p99_pct"] < 0.3, r
    assert abs(r["flat_bottom_mm"] - r["flat_top_mm"]) < 1.0, r
    assert abs(r["flat_bottom_mm"] - 2 * math.pi * (Rw + STAND_OFF) * 1000) < 2.0, r
    # a turn-back cuff: a band 50 mm up the wrist, turned back down over itself and onto the sleeve, 15 mm past the seam
    e2 = {"name": "turnback", "turn": TURN, "layers": [{"piece": "band", "kind": "stand", "height": 0.05},
                                                     {"piece": "turn", "kind": "fall", "rise": 0.0, "land": 0.015}]}
    d2 = drape.draft(e2, base)
    r2 = d2["report"]["layers"]["turn"]
    assert r2["strain_p99_pct"] < 1.0, r2
    # its outer edge lies round the sleeve (one lay out of it)
    want = 2 * math.pi * (Rw + 0.004 + TURN["lay"]) * 1000
    assert abs(r2["flat_top_mm"] - want) / want < 0.02, (r2, want)
    assert r2["depth_cb_mm"] > 60, r2  # (the run from the roll to where it lands: 50 down the band + 15 on the sleeve, as a chord)


def test_closed_vs_open_sweep_of_one_collar():
    body, under = _neck_body()
    C = _neckline()
    base = {"curve": C, "body": body, "under": under, "s_cf": drape._arc(C)[-1]}
    e = dict(_entry(), turn=TURN)
    d = drape.draft(e, base)
    Co = _neckline(straighten=0.05)
    mild = drape.reach(d, e, {"curve": Co, "body": body, "under": under, "s_cf": drape._arc(Co)[-1]})
    assert mild["ok"], {k: v for k, v in mild.items() if k != "target"}
    Cd = _neckline(straighten=1.0, drop=0.05)
    deep = drape.reach(d, e, {"curve": Cd, "body": body, "under": under, "s_cf": drape._arc(Cd)[-1]})
    assert not deep["ok"], {k: v for k, v in deep.items() if k != "target"}
    assert deep["layers"]["collar"]["strain_p99_pct"] > mild["layers"]["collar"]["strain_p99_pct"]


def test_gate_refuses_a_piece_whose_worn_spec_changed(tmp_path, monkeypatch):
    from hifipushie import store
    monkeypatch.setattr(store, "HOME", tmp_path)
    body, under = _neck_body()
    C = _neckline()
    base = {"curve": C, "body": body, "under": under, "s_cf": drape._arc(C)[-1]}
    e = dict(_entry(), turn=TURN)
    rec = drape.record(e, drape.draft(e, base), "kat")
    g = {"drape": [rec]}
    assert all(r["status"] == "PASS" for r in drape.gate_rows(g))
    rec2 = dict(rec, layers=[dict(rec["layers"][0], height=0.036), rec["layers"][1]])
    rows = drape.gate_rows({"drape": [rec2]})
    assert rows[0]["status"] == "FAIL"
    pcs, folds = drape.replace_pieces({"stand": {"wrap": {"to": "neck"}}}, g)
    assert pcs["stand"]["wrap"] == {"to": "neck"} and "drape" in pcs["stand"] and folds[0]["piece"] == "collar"


def _sphere(c, r, n=40):
    th = np.linspace(0, np.pi, n // 2)
    prof = [(r * math.sin(t), -r * math.cos(t)) for t in th]
    V, F = _rev(prof, n)
    return V + np.asarray(c), F


def test_stand_on_the_neck_leans_in_past_a_chest_bulge_and_a_chin():
    """Round 2 (C131): the case that broke Garrett d1. The neckline stands 2 mm off the neck at CB, 12 mm at CF; a
    chest bulge in front below the seam and a chin overhanging the front of the stand's top. The stand is built ON THE
    NECK: it leans in so its inner face is `gap` off the neck all round, its top edge comes out shorter than its neck
    edge, it never enters the chin. The r1 build (nearest skin) snaps the front top onto the chin and flares."""
    body0, under = _neck_body()
    spheres = (((0, -0.115, -0.07), 0.07), ((0, -0.09, 0.062), 0.032))
    Vs, Fs = _sphere(*spheres[0])
    Vc, Fc = _sphere(*spheres[1])
    V = np.r_[body0.V, Vs, Vc]
    F = np.r_[body0.F, Fs + len(body0.V), Fc + len(body0.V) + len(Vs)]

    def out(P):
        o = _axis_out(P)
        for c, r in spheres:
            m = np.abs(np.linalg.norm(P - np.asarray(c), axis=1) - r) < 0.004
            o[m] = (P - np.asarray(c))[m]
        return o
    body = drape.Surf(V, F, out=out)
    th = np.linspace(0, math.pi, 121)
    u = th / math.pi
    r = R_NECK + 0.002 + 0.010 * u * u * (3 - 2 * u)
    C = np.c_[r * np.sin(th), r * np.cos(th), np.zeros_like(th)]
    base = {"curve": C, "body": body, "under": under, "s_cf": drape._arc(C)[-1]}
    gap = 0.002
    e = {"name": "kat neck", "turn": TURN, "layers": [
        {"piece": "stand", "kind": "stand", "height": {"cb": 0.032, "end": 0.029}, "ext": 0.0, "gap": gap},
        {"piece": "collar", "kind": "fall", "rise": 0.006, "land": 0.010, "end_in": 0.0, "point": 0.0}]}
    d = drape.draft(e, base)
    rep = d["report"]
    st = rep["layers"]["stand"]
    nk = rep["stand_neck"]
    # the top sits gap (+ half the band) off the neck all round, never in the chin
    want = (gap + 0.5 * TURN["w"]) * 1000
    assert all(abs(v - want) < 0.8 for v in nk["top_clear_mm"].values()), nk
    assert nk["top_body_min_mm"] > 0.5, nk
    # it leans in, most at the front where the seam stands furthest off
    assert nk["lean_deg"]["100%"] > nk["lean_deg"]["0%"] + 5 and nk["lean_deg"]["100%"] > 10, nk
    # the top edge shorter than the neck edge: no flare
    assert st["worn_top_mm"] < st["worn_bottom_mm"] - 15, st
    assert st["flat_top_mm"] < st["flat_bottom_mm"] - 15, st
    assert st["strain_p99_pct"] < 2.0, rep["layers"]
    # (the fall over a stand leaning 18 deg in at CF, 1 deg at CB: 2.4 % p99 here, over the 2 % gate; Garrett d2c's
    # milder lean flattens at 1.98 %. Open: the fall's band above a varying lean; this bound only catches a regression)
    assert rep["layers"]["collar"]["strain_p99_pct"] < 3.0, rep["layers"]
    # the r1 build on the same body: the front top snaps onto the chin and flares
    d_old = drape.draft(dict(e, stand_mode="skin"), base)
    so = d_old["report"]["layers"]["stand"]
    assert so["worn_top_mm"] > st["worn_top_mm"] + 15, (so, st)


def test_pieces_place_on_their_own_drape():
    """Round 3 (the placement bug): the emitted pattern piece's coords ARE the drape mesh's flat coords. Garrett v12's
    stand had its v mirrored (to_piece and draft normalised the flat half by different corners: a neck edge that
    rises toward CF flipped one and not the other), so cloth.place put the stand ~60 mm up the neck, flat, and the
    fronts' neck seams were pinned up into the jaw (a 0.29 m triangle at the CF neck corner). A neckline dropping
    40 mm to CF, the stand's flat neck edge curved: every named point of every piece lands on its own worn point."""
    body, under = _neck_body()
    C = _neckline(drop=0.040)
    base = {"curve": C, "body": body, "under": under, "s_cf": drape._arc(C)[-1]}
    e = dict(_entry(), turn=TURN)
    d = drape.draft(e, base)
    for nm, pc in d["pieces"].items():
        m = d["mesh"][nm]
        Xg = d["build"]["layers"][nm]["X"]
        P = np.asarray(pc["P"], float)
        want = {"bottomMid": Xg[0, 0], "topMid": Xg[-1, 0], "rightBottomEdge": Xg[0, -1]}
        want["rightTopCf" if "rightTopCf" in pc["names"] else "rightTopEdge"] = Xg[-1, -1]
        for k, w in want.items():
            got = drape.place_on_drape(P[[pc["names"][k]]], m)[0]
            assert np.linalg.norm(got - w) < 1e-3, (nm, k, got, w)
