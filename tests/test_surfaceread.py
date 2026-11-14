"""A picture's read surface (surfaceread.py): the slope-adding solver on a shape whose answer is known. The reader
itself (a learned model in its own venv) is not run here."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from hifipushie import surfaceread

PX = 0.002


def test_the_slopes_add_up_to_the_dome_and_the_pins_find_its_true_depth():
    n = 81
    y, x = np.mgrid[0:n, 0:n]
    X, Y = (x - 40) * PX, (y - 40) * PX
    Rd = 0.07
    mask = X ** 2 + Y ** 2 < Rd ** 2 * 0.98
    true = np.sqrt(np.clip(Rd ** 2 - X ** 2 - Y ** 2, 0, None)) * 0.8
    gy, gx = np.gradient(true * 0.6, PX)             # a read that mutes depth to 60 %
    nrm = np.stack([-gx, gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    rim = mask & (ndimage.distance_transform_edt(mask) < 2)
    pin = np.full(mask.shape, np.nan)
    pin[rim] = true[rim]
    pin[38:43, 38:43] = true[38:43, 38:43]
    z, gain = surfaceread.height(nrm, mask, PX, pin=pin, gain=(0.5, 3.0))
    inner = mask & (ndimage.distance_transform_edt(mask) > 6)
    assert 1.45 < gain < 1.8                          # 1 / 0.6 = 1.67 undoes the muting
    assert np.abs((z - true)[inner]).max() < 0.0015
    # a part hidden by something standing in front is carried through smoothly
    hole = mask & (np.abs(X + 0.02) < 0.012) & (np.abs(Y) < 0.012)
    z2, _ = surfaceread.height(nrm, mask, PX, pin=pin, data=mask & ~hole, gain=(0.5, 3.0))
    assert np.abs((z2 - true)[hole]).max() < 0.004
    # without pins a piece floats: zero-mean, the slopes as read
    z3 = surfaceread.height(nrm, mask, PX)
    assert abs(float(z3[mask].mean())) < 1e-6
    assert np.ptp(z3[inner]) == pytest.approx(0.6 * np.ptp(true[inner]), rel=0.1)


def test_the_read_lit_as_grey_clay_is_a_picture_of_the_surface():
    n = np.zeros((20, 30, 3), np.float32)
    n[..., 2] = 1.0                                   # a flat wall facing the viewer
    mask = np.zeros((20, 30), bool)
    mask[5:15, 5:25] = True
    im = surfaceread.clay(n, mask)
    a = np.asarray(im)
    assert im.size == (30, 20) and tuple(a[0, 0]) == (236, 236, 232)       # the ground outside the figure
    assert a[10, 15].max() > 120 and len({tuple(p) for p in a[6:14, 6:24].reshape(-1, 3)}) == 1   # evenly lit
