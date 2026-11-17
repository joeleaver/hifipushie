"""The collar's synthetic toile (a neck + sloping shoulders, used by test_toile_flap.py: R3f-9, C508, the collar and the
lapels draped as ONE flap) and toile_collar's own pieces; the cut refuses a toile with no collar by name."""
import types

import numpy as np
import pytest

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


def test_toile_collar_refused_by_name_without_its_part(tmp_path):
    np.savez(tmp_path / "toile.npz", **{"toile:V": np.zeros((3, 3)), "toile:F": np.zeros((1, 3), int)})
    try:
        cut_collar.toile_collar({"toile": str(tmp_path / "toile.npz")})
    except cut_collar.CollarRefused as e:
        assert "garment_toile parts \"collar\"" in str(e)
    else:
        raise AssertionError("a toile without a collar part must be refused")


def test_corner_row_puts_a_point_on_every_join():
    """R3f-8 (C507): the neck row has a column ON each corner (the side neck point, the gorge point)."""
    runs = (np.array([[0, 0, 0], [1.0, 0, 0]]), np.array([[1.0, 0, 0], [1.0, 1.0, 0]]))
    P, S = toile_collar.corner_row(runs, 9)
    assert np.min(np.linalg.norm(P - [1.0, 0, 0], axis=1)) < 1e-9 and S[-1] == pytest.approx(2.0)
