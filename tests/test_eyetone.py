"""skincheck's eye_tone reference band ("upper lid / upper cheek") lies outside every eye-region paint zone: up to r7 it sat
inside the under_eye zone, so darkening the under-eye made the lid read LIGHTER against it (2026-10-16, projskin2)."""
import os, sys
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "spikes/projskin"))
import eyetone  # noqa: E402
from hifipushie import skin  # noqa: E402

EYE_ZONES = ("under_eye.L", "eyelid.L", "eye_corner.L")
GROW = 1.2     # the largest grow any skin layer applies to an eye-region zone (micro cells / lines; periorbital 1.15)
IO_MAX = 0.068  # a wide interocular (m)


def _zone_bottom_mm():
    """how far below the lower-lid margin landmark the under_eye zone reaches (mm, z down), at IO_MAX and GROW"""
    (anchor, off, rad), = skin.FACE["under_eye.L"]
    assert anchor == "lm_lid_lower.L"
    return 1000 * IO_MAX * (-off[2] + GROW * rad[2])


def test_band_clears_the_under_eye_zone():
    assert eyetone.CHEEK_MM[0] > _zone_bottom_mm() + 1.5, (eyetone.CHEEK_MM, _zone_bottom_mm())
    for z in EYE_ZONES:          # every eye-region zone is anchored at the lids / the inner corner, none reaches lower
        for anchor, off, rad in skin.FACE[z]:
            if anchor.startswith("lm_lid_lower"):
                assert 1000 * IO_MAX * (-off[2] + GROW * rad[2]) < eyetone.CHEEK_MM[0] - 1.5, z


def _face(mm=6.0, n=400):
    """a frontal eye's landmarks (iris centre at (200, 120), mm px per mm) on a flat grey image"""
    P = np.zeros((478, 2))
    c = np.array([200.0, 120.0])
    e = eyetone.EYE["R"]
    xs = np.linspace(-15, 15, 9) * mm
    for i, x in zip(e["up"], xs[::-1]):
        P[i] = c + [x, -5 * mm * (1 - (x / (15 * mm)) ** 2)]
    for i, x in zip(e["lo"], xs[::-1]):
        P[i] = c + [-x, 5 * mm * (1 - (x / (15 * mm)) ** 2)]
    P[e["up"][0]] = P[e["lo"][-1]] = c + [15 * mm, 0]
    P[e["up"][-1]] = P[e["lo"][0]] = c + [-15 * mm, 0]
    P[e["iris"][0]] = c
    for i, d in zip(e["iris"][1:], ((1, 0), (0, 1), (-1, 0), (0, -1))):
        P[i] = c + np.array(d) * eyetone.IRIS_MM * mm
    A = np.full((n, n, 3), 0.6)
    yy, xx = np.mgrid[0:n, 0:n]
    A[np.hypot(xx - c[0], yy - c[1]) < 13 * mm] = 0.9      # a pale eye so sclera / iris bands exist
    A[np.hypot(xx - c[0], yy - c[1]) < 5.9 * mm] = 0.3
    return A, P, c, mm, yy, xx


def test_under_eye_darkening_leaves_the_reference_alone():
    A, P, c, mm, yy, xx = _face()
    base = eyetone.eye_tone(Image.fromarray((A * 255).astype(np.uint8)), P, "R")
    lo = P[eyetone.EYE["R"]["lo"][4]]
    B = A.copy()   # darken the under_eye zone's whole frontal extent (lower lid .. zone bottom), as under_eye_shade does
    zone = (np.abs(xx - c[0]) < 21 * mm) & (yy > lo[1]) & (yy < lo[1] + _zone_bottom_mm() * mm)
    B[zone] *= 0.7
    t = eyetone.eye_tone(Image.fromarray((B * 255).astype(np.uint8)), P, "R")
    assert abs(t["cheek"] - base["cheek"]) < 1e-6 and abs(t["lid"] - base["lid"]) < 1e-6, (base, t)
    # ... while the old band (9-12 mm under the iris centre) would have moved
    old = (np.abs(xx - c[0]) < 6 * mm) & (yy > c[1] + 9 * mm) & (yy < c[1] + 12 * mm)
    assert old.any() and np.median(B[old][:, 1]) < np.median(A[old][:, 1]) - 0.1
    C = A.copy(); C[(yy > lo[1] + eyetone.CHEEK_MM[0] * mm) & (yy < lo[1] + eyetone.CHEEK_MM[1] * mm)] *= 0.7
    assert eyetone.eye_tone(Image.fromarray((C * 255).astype(np.uint8)), P, "R")["cheek"] < base["cheek"] - 0.1


def test_lid_skin_ignores_lashes():
    """lid_skin is read just above the lash line: a photo's lashes merged into a dark band 0-2 mm above the margin (hooded
    lids at face distance) no longer read as lid; a broad darkening of the lid (lid_shade) still does"""
    A, P, c, mm, yy, xx = _face()
    base = eyetone.eye_tone(Image.fromarray((A * 255).astype(np.uint8)), P, "R")
    up = P[list(eyetone.EYE["R"]["up"])]
    top = np.interp(xx, up[::-1, 0], up[::-1, 1])
    B = A.copy(); B[(yy < top) & (yy > top - 2.0 * mm) & (np.abs(xx - c[0]) < 14 * mm)] = 0.15
    t = eyetone.eye_tone(Image.fromarray((B * 255).astype(np.uint8)), P, "R")
    assert t["lash"] > 0.3, t                                                   # the lash line covers the old 1-3 mm band ...
    assert abs(t["lid_skin"] - base["lid_skin"]) < 0.01, (base, t)             # ... the skin band does not
    C = A.copy(); C[(yy < top) & (yy > top - 8 * mm) & (np.abs(xx - c[0]) < 14 * mm)] *= 0.75   # a broad shade is lid skin
    u = eyetone.eye_tone(Image.fromarray((C * 255).astype(np.uint8)), P, "R")
    assert u["lash"] < 0.05 and u["lid_skin"] < base["lid_skin"] - 0.1, u

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
