"""R3f-9 (C508): the lapels and the collar draped as ONE flap turned back about ONE roll line (toile_flap.py) on a
synthetic torso + neck: the roll runs from the break up the chest, through the gorge point and round the back of the
neck without a kink at the old lapel / collar join; the stand mostly hidden from the front; step 5's gorge mark splits
the flap into the collar and the lapels (mark_flap.py: both sides one line); cut, the gorge seam's sides are equal."""
import json

import numpy as np

from hifipushie import cut_collar, mark_flap, toile_flap, toile_style
from test_cut_made import neck_toile
from test_toile_collar import R_NECK, Z_NECK, fake_toile


def flap_toile():
    pcs, edges, s1, toile = neck_toile()
    t = fake_toile(toile)
    an = np.linspace(-np.pi, np.pi, 72, endpoint=False)
    t.inp.tapes = {"neck": np.c_[R_NECK * np.sin(an), R_NECK * np.cos(an), np.full(len(an), Z_NECK)]}
    t.inp.traces["notch"] = {"xz": [[0.075, 1.445], [0.11, 1.43], [0.10, 1.46], [0.085, 1.49], [0.07, 1.52]],
                             "corners": [1]}  # (its top above the neck seam: the fall seen edge-on beside the neck)
    z_top, z_brk = 1.46, 1.25
    x_roll = lambda z: np.interp(z, [z_brk, z_top], [0.0, 0.04])
    TOP = np.array([[0.04, z_top], [0.075, 1.445], [0.11, 1.43]])
    t.lapel_geom.update(z_top=z_top, z_brk=z_brk, x_roll=x_roll, z_line=lambda x: np.interp(x, TOP[:, 0], TOP[:, 1]),
                        x_l=lambda z: x_roll(z) + 0.075 * np.clip((z - z_brk) / 0.15, 0, 1))
    t.x_edge = xe = toile_style.front_neck(t, x_roll)
    Vt, Ft = toile
    c3 = Vt[Ft].mean(1)
    toile_open = (Vt, Ft[~((c3[:, 1] < 0) & (np.abs(c3[:, 0]) < xe(c3[:, 2])) & (c3[:, 2] > z_brk))])
    return t, toile_open, pcs, edges, s1


def test_one_flap_one_roll_line_gorge_mark_splits_it_equal_at_the_cut(tmp_path):
    t, toile_open, pcs, edges, s1 = flap_toile()
    V, F = toile_flap.drape(t, toile_open)
    f, c = t.info["flap"], t.info["collar"]
    # ONE roll line: no kink where the collar's region meets the lapel's (R3f-8: 40 deg on the jacket)
    assert f["roll_join_deg"] < 12, f
    # R3f-10 (C509): the roll drawn ON the toile passes the side neck point at the traced collar top (no shortcut past
    # it: R3f-9's Hermite through the air lay low), smooth at the gorge and everywhere; the stand a thin edge in front
    assert abs(f["roll_side_z_mm"] - f["trace_top_z_mm"]) < 3, f
    assert f["roll_turn_max_deg"] < 45, f
    assert c["stand_front_area_pct"] < 25, c
    assert c["stand_seen_front_pct"] < 50, c  # (the fall covers the stand)
    assert c["lands_below_seam_cb_mm"] > 5, c  # (turned down over the neck seam)
    # ONE piece: every vertex used, the mesh one connected surface (the lapels and the collar)
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]]]
    n, _ = connected_components(coo_matrix((np.ones(len(E)), E.T), shape=(len(V),) * 2))
    assert n == 1 and len(np.unique(F)) == len(V)
    Z = {"flap:V": V, "flap:F": F, "flap_layout": np.array(t.flap_layout)}
    P = mark_flap.parts(Z)
    nr, ncf, ks = P["collar_grid"]
    X = P["collar:V"].reshape(nr, ncf, 3)
    YL = P["lapel.L:V"].reshape(nr - ks, -1, 3)
    assert np.array_equal(X[ks:, -1], YL[:, 0])  # (the gorge: one line, the collar's end = the lapel's top)
    assert (YL[0, :, 2] < X[ks, -1, 2] + 1e-9).all()  # (the lapel's roll runs down from the gorge to the break)
    assert mark_flap.gorge_row(Z)["status"] == "PASS"
    np.savez(tmp_path / "toile.npz", **Z)
    (tmp_path / "toile.json").write_text(json.dumps(t.info))
    d = {"pieces": ["collar"], "neck": ["front.L:neck", "back.L:neck"], "outer": "fall", "end": "end.L",
         "fold": "collar_roll", "fold_on": "collar"}
    out4 = {"toile": str(tmp_path / "toile.npz"), "numbers": str(tmp_path / "toile.json")}
    c_pcs, c_edges, folds, rep, bad = cut_collar.build(pcs, edges, d, s1, {}, out4)
    g = rep["gorge"]
    assert g["collar_3d_mm"] == g["lapel_3d_mm"], g
    assert abs(g["collar_flat_mm"] - g["lapel_flat_mm"]) < 0.04 * g["lapel_3d_mm"], g  # (each side's flatten only)
    assert rep["outer_over_neck"] > 1.1, rep  # (a turned collar's crescent, not a band)
