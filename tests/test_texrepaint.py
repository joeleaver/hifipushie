"""Texture repaint on a synthetic model (a UV sphere, no Blender): rasterising, the surface blur across UV seams,
the concept outvoting a wrong back, contradictions found and located, the 4K paint, and a decal redraw."""
import numpy as np

from hifipushie import texrepaint_concept as C, texrepaint_decal as Dc, texrepaint_paint as Pn
from hifipushie import texrepaint_regions as Rg
from hifipushie.texrepaint_surface import Grid, Surface, View, raster

CREAM, BLACK = [230, 215, 195], [40, 35, 30]


def sphere(n=24, m=48, r=0.5):
    P, N, UV = [], [], []
    for i in range(n):
        for j in range(m):
            q = []
            for a, b in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                th, ph = np.pi * a / n, 2 * np.pi * b / m
                p = np.array([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]) * r
                q.append((p, p / r, (b / m, 1 - a / n)))
            for t in ((0, 1, 2), (0, 2, 3)):
                P.append([q[k][0] for k in t]); N.append([q[k][1] for k in t]); UV.append([q[k][2] for k in t])
    T = len(P)
    meta = {"images": ["color"], "objects": ["ball", "ball_LOD1"], "normal_of": {}}
    return Surface(np.array(P, np.float32), np.array(N, np.float32), np.array(UV, np.float32),
                   np.zeros(T, np.int32), np.zeros(T, np.int32), meta)


def test_raster_covers_and_keeps_nearest():
    tri = np.array([[[0, 0], [10, 0], [0, 10]], [[0, 0], [10, 0], [0, 10]]], np.float32)
    tid, bc, zb = raster(tri, 12, 12, depth=np.array([[2, 2, 2], [1, 1, 1]], np.float32))
    assert (tid == 1).sum() > 40 and (tid == 0).sum() == 0 and np.isclose(zb[tid >= 0], 1).all()


def test_texels_lod_copy_does_not_claim_texels():
    s = sphere(); s.obj = np.r_[s.obj, np.ones(len(s.obj), np.int32)]
    for a in ("P", "N", "UV"):
        setattr(s, a, np.concatenate([getattr(s, a)] * 2))
    s.img = np.zeros(len(s.P), np.int32)
    tx = s.texels("color", 128)
    assert (tx.obj == 0).all() and len(tx.idx) > 0.9 * 128 * 128


def test_surface_blur_crosses_the_uv_seam():
    s = sphere(); tx = s.texels("color", 128); u = tx.idx % 128
    v = (u < 4).astype(np.float32)                 # marked just left of the seam (u = 0) in UV space
    g = Grid(tx.pos, 0.01); sm, _ = g.smooth(v, 0.02)
    across = (u == 127) & (np.abs(tx.pos[:, 2]) < 0.3)  # far away in UV, touching in 3D
    far = (u > 50) & (u < 70) & (np.abs(tx.pos[:, 2]) < 0.3)
    assert sm[across].mean() > 0.2 and sm[far].max() < 0.01


def test_concept_outvotes_a_wrong_back_and_reports_it():
    s = sphere(); tx = s.texels("color", 128)
    tex = np.tile(np.array(CREAM, np.float32), (len(tx.idx), 1))
    wrong = (tx.pos[:, 1] > 0.3) & (np.abs(tx.pos[:, 2]) < 0.2)       # a black patch on the BACK (+y)
    tex[wrong] = BLACK
    # the "concept": a back view showing it all cream; projected through View like a registered panel
    v = View("back", s, 200, *s.bounds()); vis, cos, _ = v.visible(tx.pos, tx.nrm)
    con = np.tile(np.array(CREAM, np.float32), (len(tx.idx), 1)); w = np.where(vis, np.clip(cos, 0, 1) ** 2, 0)
    mats = [{"name": "cream", "colour": CREAM}, {"name": "black", "colour": BLACK}]
    area = Rg.texel_area(s, tx)
    R = Rg.fuse(tx, tex, con, w.astype(np.float32), mats, 0.03, 0.02, area=area, min_area=1e-4)
    assert (R["P"].argmax(1)[wrong] == 0).mean() > 0.9                  # repainted cream
    big = R["contradictions"][0]
    assert big["texture_has"] == "black" and big["concept_shows"] == "cream" and "back" in big["where"]


def test_zones_keep_a_dark_feature_off_the_body():
    pos = np.array([[0, 0, 0.0], [0, 0, 0.95]], np.float32)
    mats = [{"name": "cream", "colour": CREAM}, {"name": "pupil", "colour": BLACK, "zones": [[0.8, 1]]}]
    lab_, _ = Rg.classify(np.array([BLACK, BLACK], np.float32), mats, ok=Rg.allowed(pos, mats, 0, 1))
    assert list(lab_) == [0, 1]


def test_paint_gives_clean_regions_and_valid_maps():
    s = sphere(); tx = s.texels("color", 128)
    P = np.zeros((len(tx.idx), 2), np.float32); P[:, 0] = (tx.pos[:, 2] > 0); P[:, 1] = 1 - P[:, 0]
    mats = [{"name": "cream", "colour": CREAM, "kind": "clay"}, {"name": "black", "colour": BLACK, "kind": "gloss"}]
    col, nrm, rough, lab_ = Pn.paint(tx, {"P": P}, mats, np.array([CREAM, BLACK], np.float32),
                                     np.full((8, 8, 3), (128, 128, 255), np.uint8), np.zeros((len(tx.idx), 3)), 1.0)
    top = col.reshape(-1, 3)[tx.idx[tx.pos[:, 2] > 0.2]].mean(0); bot = col.reshape(-1, 3)[tx.idx[tx.pos[:, 2] < -0.2]].mean(0)
    assert np.abs(top - CREAM).max() < 25 and np.abs(bot - BLACK).max() < 15
    n = nrm.reshape(-1, 3)[tx.idx].astype(float) / 127.5 - 1
    assert (n[:, 2] > 0.7).all() and rough.reshape(-1)[tx.idx[tx.pos[:, 2] < -0.2]].mean() < rough.reshape(-1)[tx.idx[tx.pos[:, 2] > 0.2]].mean()


def test_redraw_is_flat_colours_without_specks():
    rng = np.random.default_rng(0)
    img = np.full((60, 60, 3), 200, np.float32); img[20:40, 20:40] = 30
    img += rng.normal(0, 12, img.shape)                                  # a smeared, noisy graphic
    src = [[0, 0], [59, 0], [0, 59]]; dst = [[0, 0], [239, 0], [0, 239]]
    rgb, lab_, pal = Dc.redraw(img.clip(0, 255), src, dst, (240, 240), k=2)
    assert len(np.unique(lab_)) == 2
    inner = lab_[100:140, 100:140]; outer = lab_[10:50, 10:50]
    assert (inner == inner[0, 0]).all() and (outer == outer[0, 0]).all() and inner[0, 0] != outer[0, 0]


def test_turnaround_panels_and_colour_registration():
    s = sphere(); tex = np.zeros((64, 64, 3), np.uint8); tex[:32] = CREAM; tex[32:] = BLACK
    v = View("front", s, 100, *s.bounds())
    r, c, rgb = v.textured(0, tex, step=1)
    sheet = np.full((200, 600, 3), 128, np.uint8)
    for x0 in (50, 250, 450):                                             # three figures: the model at k = 1.5
        sheet[(r * 1.5 + 20).astype(int), (c * 1.5 + x0).astype(int)] = rgb
    p = C.Panel("front", sheet, (40, 0, 220, 200))
    p = C.register(p, v, (r, c, rgb))
    assert abs(p.k - 1.5) < 0.08 and abs(p.t[0] - 50) < 6 and abs(p.t[1] - 20) < 6
