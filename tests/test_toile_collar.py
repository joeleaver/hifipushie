"""R3f (C497): the collar DRAPED on the toile (toile_collar.py, step 4) on a synthetic neck + sloping shoulders: its
fall lies on the shoulders; cut and unfolded at step 6 (cut_collar.py) the flat collar is curved (outer edge longer than
its neck edge by what the toile gives), its fall across the roll from its neck edge, its edges named, the roll a
fold; its neck seams read against the garment's (not yet equal: R3f's NEXT)."""
import json
import types

import numpy as np

from hifipushie import cut_collar, toile_collar
from hifipushie.toile import Toile
from test_cut_made import neck_toile

Z_NECK, R_NECK, R_BODY, Z_SH = 1.50, 0.065, 0.17, 1.44


def _r(z):
    return np.where(z >= Z_NECK, R_NECK, np.where(z >= Z_SH, R_NECK + (Z_NECK - z) / (Z_NECK - Z_SH) * (R_BODY - R_NECK),
                                                  R_BODY))


def fake_toile(toile):
    """A Toile on neck_toile's surface of revolution (its field analytic), with a collar declared."""
    t = Toile.__new__(Toile)
    cone = np.cos(np.arctan((R_BODY - R_NECK) / (Z_NECK - Z_SH)))  # (the distance off the cone: radial x its cos)
    t.FD = lambda P: (np.hypot(P[:, 0], P[:, 1]) - _r(P[:, 2])) * np.where((P[:, 2] < Z_NECK) & (P[:, 2] > Z_SH), cone, 1.0)
    t.ys, t.yc, t.cn = np.arange(-0.3, 0.3, 0.004), 0.0, np.array([0.0, 0.0])
    t.phi_neck = lambda P: Z_NECK - P[:, 2]
    t.lapel_geom = {"shift": lambda z: 0.0 * np.asarray(z)}
    t.inp = types.SimpleNamespace(traces={"notch": {"xz": [[0.075, 1.445], [0.11, 1.43]], "corners": [1]}})
    zz = np.linspace(1.25, 1.46, 30)  # (the lapel's roll line, break -> its top on the chest below the neck)
    xx = np.interp(zz, [1.25, 1.46], [0.0, 0.04])
    t.roll_line = t.front_hit(xx, zz)
    t.d = {"collar": {"stand_mm": 20, "fall_mm": 35, "notch": "notch"}}
    t.info = {}
    return t


def test_collar_draped_lies_on_the_shoulders_cut_and_unfolded_curved(tmp_path):
    pcs, edges, s1, toile = neck_toile()
    t = fake_toile(toile)
    Vt, Ft = toile
    c3 = Vt[Ft].mean(1)  # (the front opening: the neck seam ends near the side neck point, as a jacket's does)
    toile_open = (Vt, Ft[~((c3[:, 1] < 0) & (np.abs(c3[:, 0]) < 0.05) & (c3[:, 2] > 1.40))])
    V, F = toile_collar.drape(t, toile_open)
    c = t.info["collar"]
    # ONE roll line: the collar's roll leaves the lapel's roll line at its top without a kink, round the back to CB
    assert c["roll_join_deg"] < 20, c  # (measured on the grid: 5 mm columns)
    assert c["outer_out_side_mm"] > 15, c  # (the fall lies out over the shoulders at the side, not down the neck)
    assert c["outer_off_toile_mm"][1] < 1.5, c  # (the fall's outer edge lies on the toile)
    assert c["lands_below_seam_cb_mm"] > 5 and 15 < c["roll_above_seam_cb_mm"] <= 20.5, c  # (turned down over the seam)
    nr, nc, ks = t.collar_grid
    G = V.reshape(nr, nc, 3)
    assert (G[-1, :, 2] < Z_NECK).all() and (np.hypot(G[-1, :, 0], G[-1, :, 1]) > R_NECK + 0.004).all()  # (on the slope)
    np.savez(tmp_path / "toile.npz", **{"collar:V": V, "collar:F": F, "collar_grid": np.array(t.collar_grid)})
    (tmp_path / "toile.json").write_text(json.dumps(t.info))
    d = {"pieces": ["collar"], "neck": ["front.L:neck", "back.L:neck"], "outer": "fall", "end": "end.L",
         "fold": "collar_roll", "fold_on": "collar"}
    out4 = {"toile": str(tmp_path / "toile.npz"), "numbers": str(tmp_path / "toile.json")}
    c_pcs, c_edges, folds, rep, bad = cut_collar.build(pcs, edges, d, s1, {}, out4)
    assert not bad, bad
    assert sorted(c_edges["collar"]) == ["end.L", "end.R", "fall", "neck_back.L", "neck_back.R", "neck_front.L",
                                         "neck_front.R"], c_edges
    # curved: the outer edge longer than the neck edge by what the toile gives (where it lies), the neck edge bowed
    assert rep["outer_over_neck"] > 1.15 and abs(rep["outer_flat_mm"] / rep["outer_3d_mm"] - 1) < 0.06, rep
    assert rep["neck_bow_mm"] > 10, rep
    # unfolded: the fall lies across the roll row from the neck row in the flat
    U = c_pcs["collar"]["U"].reshape(nr, nc, 2)
    m = nc // 2
    assert np.dot(U[-1, m] - U[ks, m], U[0, m] - U[ks, m]) < 0, (U[0, m], U[ks, m], U[-1, m])
    # the neck seams: the stand on the neck and the fall on the cone don't develop together (the roll is straight on the
    # stand's side, curved on the fall's): the flat's neck edge comes out ~11 % short of the garment's (R3f, NEXT)
    # (R3f-3: the synthetic's garment pieces have no opening, the toile it drapes on has: only the back seams compare)
    for g, v in rep["seams"].items():
        if g.startswith("back"):
            assert abs(v["collar_mm"] - v["garment_mm"]) < 20, (g, v)
    assert folds and folds[0]["name"] == "collar_roll" and rep["strain_mean_pct"] < 12, rep


def test_toile_collar_refused_by_name_without_its_part(tmp_path):
    np.savez(tmp_path / "toile.npz", **{"toile:V": np.zeros((3, 3)), "toile:F": np.zeros((1, 3), int)})
    try:
        cut_collar.toile_collar({"toile": str(tmp_path / "toile.npz")})
    except cut_collar.CollarRefused as e:
        assert "garment_toile parts \"collar\"" in str(e)
    else:
        raise AssertionError("a toile without a collar part must be refused")
