"""Sea stacks as jointed rock columns (terrain_stack.Column): one piece down to the plinth, continuous, near-vertical
planar walls, deterministic, styles' overrides checked."""
import numpy as np
import pytest
from scipy import ndimage

from hifipushie.terrain_stack import Column, FORM, form

CASES = [((0.0, 0.0), 42.0, 7.6, 3000), ((0.0, 0.0), 32.0, 6.1, 3001), ((0.0, 0.0), 25.0, 6.0, 3002),
         ((0.0, 0.0), 12.0, 9.0, 3003)] + [((0.0, 0.0), 30.0, 6.0, s) for s in range(4000, 4012)]


def _grid(c, vox=0.5):
    lo = np.r_[c.xy - c.reach - 1, c.base - 1.5]
    hi = np.r_[c.xy + c.reach + 1, c.top + 2]
    ax = [np.arange(lo[i], hi[i] + vox, vox) for i in range(3)]
    G = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    return ax, G, c.sd(G).reshape([len(a) for a in ax])


@pytest.mark.parametrize("xy,h,r,seed", CASES)
def test_one_piece_down_to_the_plinth(xy, h, r, seed):
    """Every horizontal section of the column (and its fallen blocks) is connected down to the plinth: a piece cut
    loose near the top floated over the island's stack (tiles2's floating check)."""
    c = Column(xy, -2.0, h, r, seed, sea=0.0, stage="auto")
    ax, G, V = _grid(c)
    solid = V < 0
    s18 = ndimage.generate_binary_structure(3, 2)  # (face + edge neighbours: a voxel touching by an edge is one piece in marching cubes)
    lab, n = ndimage.label(solid, s18)
    assert n == 1, f"{n} pieces (stage {c.stage})"
    # each slice's solid cells reach the bottom through solid cells at or below that slice
    k0 = int(np.flatnonzero(solid.any((0, 1)))[0])  # (the plinth's first layer)
    for k in range(solid.shape[2] - 1, k0, -3):
        sub, nn = ndimage.label(solid[:, :, k0:k + 1], s18)
        top_ids = set(np.unique(sub[:, :, -1][solid[:, :, k]]))
        bot_ids = set(np.unique(sub[:, :, 0][solid[:, :, k0]]))
        assert top_ids <= bot_ids, f"slice {ax[2][k]:.1f} m hangs (stage {c.stage})"


def test_continuous():
    """No jumps in the field (a jump meshes as shards): neighbouring samples differ by at most ~their distance."""
    for _, h, r, seed in CASES[:6]:
        c = Column((0.0, 0.0), -2.0, h, r, seed, sea=0.0)
        rng = np.random.default_rng(seed)
        p = np.c_[rng.uniform(-c.reach, c.reach, (20000, 2)), rng.uniform(-3, h + 2, 20000)]
        e = 0.02
        for ax in range(3):
            d = np.zeros(3)
            d[ax] = e
            g = np.abs(c.sd(p + d) - c.sd(p)) / e
            assert g.max() < 3.0, (seed, ax, g.max())  # (notch + a cut + the warps stack up near 2.7)


def test_walls_vertical_and_planar():
    """Side faces near vertical (median |nz| < 0.2) and mostly a few planes (>= 40% of the side area within 8 deg
    of six azimuths); the lobed, bedded prism before read 0.29 and 0.30."""
    from skimage import measure
    for _, h, r, seed in CASES[:3]:
        c = Column((0.0, 0.0), -2.0, h, r, seed, sea=0.0)
        ax, G, V = _grid(c)
        v, f, _, _ = measure.marching_cubes(V, 0.0, spacing=(0.5,) * 3)
        t = v[f]
        nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        A = np.linalg.norm(nrm, axis=1) / 2
        nz = nrm[:, 2] / np.maximum(2 * A, 1e-12)
        zc = t[:, :, 2].mean(1) + ax[2][0]
        side = (np.abs(nz) < 0.6) & (zc > 3) & (zc < h - 2)
        o = np.argsort(np.abs(nz[side]))
        cw = np.cumsum(A[side][o])
        assert np.abs(nz[side])[o][np.searchsorted(cw, cw[-1] / 2)] < 0.2
        az = np.degrees(np.arctan2(nrm[side, 1], nrm[side, 0])) % 360
        hist, _ = np.histogram(az, 360, (0, 360), weights=A[side])
        hs = np.convolve(np.r_[hist[-8:], hist, hist[:8]], np.ones(17), "valid")
        taken = np.zeros(360, bool)
        share = 0.0
        for _ in range(6):
            k = int(np.argmax(np.where(taken, -1, hs)))
            idx = np.arange(k - 8, k + 9) % 360
            share += hist[idx][~taken[idx]].sum()
            taken[idx] = True
        assert share / hist.sum() > 0.4


def test_deterministic_and_overrides():
    a = Column((5.0, 7.0), -2.0, 30.0, 6.0, 11, sea=0.0)
    b = Column((5.0, 7.0), -2.0, 30.0, 6.0, 11, sea=0.0)
    p = np.random.default_rng(0).uniform(-10, 30, (1000, 3))
    assert np.array_equal(a.sd(p), b.sd(p))
    c = Column((5.0, 7.0), -2.0, 30.0, 6.0, 11, sea=0.0, over={"bevel": 2.0})
    assert not np.array_equal(a.sd(p), c.sd(p))
    with pytest.raises(ValueError):
        form({"lobes": 1})
    assert set(form()) == set(FORM)


def test_style_sheets_stack_keys_are_known():
    """Every terrain style sheet's rock.stack keys are terrain_stack.FORM keys."""
    import json
    from pathlib import Path
    import hifipushie
    d = Path(hifipushie.__file__).parent / "terrain_styles"
    for f in d.glob("*.json"):
        st = (json.loads(f.read_text()).get("rock") or {}).get("stack")
        if st:
            form(st)


@pytest.mark.parametrize("seed", [3000, 3002, 4001, 4003, 4006])
def test_no_sealed_air(seed):
    """No air enclosed in a column (tiles2: a sealed sub-voxel pocket at the old stack's notch broke the decimator
    wherever the cliff shell followed it): sampled at 0.2 m, every air component reaches the box's boundary."""
    h, r = (42.0, 7.6) if seed < 4000 else (30.0, 6.0)
    c = Column((0.0, 0.0), -2.0, h, r, seed, sea=0.0)
    ax, G, V = _grid(c, vox=0.2)
    lab, n = ndimage.label(V > 0)
    edge = set(np.unique(np.concatenate([lab[0].ravel(), lab[-1].ravel(), lab[:, 0].ravel(), lab[:, -1].ravel(),
                                         lab[:, :, 0].ravel(), lab[:, :, -1].ravel()])))
    sealed = [i for i in range(1, n + 1) if i not in edge]
    assert not sealed, f"{len(sealed)} sealed pockets, the biggest {max(int((lab == i).sum()) for i in sealed)} cells"


@pytest.mark.parametrize("seed", [3000, 3002, 4001, 4003, 4006])
def test_no_thin_slots(seed):
    """Every recess a voxel pair wide at least: no air cell at 0.2 m that a 0.5 m ball can't reach from outside
    (an opening of the air by a 1 m wide structure removes nothing but sub-voxel slots and pockets)."""
    h, r = (42.0, 7.6) if seed < 4000 else (30.0, 6.0)
    c = Column((0.0, 0.0), -2.0, h, r, seed, sea=0.0)
    ax, G, V = _grid(c, vox=0.2)
    air = V > 0
    ball = ndimage.generate_binary_structure(3, 1)
    opened = ndimage.binary_opening(air, ball, iterations=2, border_value=1)  # (a ~1 m wide ball at 0.2 m cells)
    thin = air & ~opened
    # (a recess narrower than the ball shows as thin air; the arrises' bevel leaves a few cells in corners: allowed)
    frac = thin.sum() / max((V < 0).sum(), 1)
    assert frac < 0.004, f"thin air {frac:.4f} of the solid ({int(thin.sum())} cells)"


def _coast_field():
    import json
    import tempfile
    from pathlib import Path
    from hifipushie import terrain, terrain_mesh as tm
    spec = {"world": {"kind": "coast", "base": 10}, "extent": [[0, 0], [160, 160]], "cell": 1.0,
            "tilt": {"down": "south", "grade": 0.25},
            "sea": {"level": 0, "shore": "cliffs", "cliffs": {"height": [22, 30], "stacks": {"count": 3}}},
            "cover": [{"type": "meadow", "in": "everywhere"}, {"type": "rock", "in": "cliffs"}],
            "export": {"tiles": {"tile": 32}}}
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(spec))
    T = terrain.load(d / "spec.json")
    field, vols, _, _ = tm.build_field(T)
    return T, field


def _style_forms():
    import json
    from pathlib import Path
    import hifipushie
    out = {"realistic": None}
    for f in sorted((Path(hifipushie.__file__).parent / "terrain_styles").glob("*.json")):
        st = (json.loads(f.read_text()).get("rock") or {}).get("stack")
        if st:
            out[f.stem] = st
    return out


@pytest.mark.parametrize("style", list(_style_forms()))
def test_no_piece_detached(style):
    """In a terrain's field (stack + heightfield + rock relief + fallen blocks), every solid piece from under a stack's
    foot to over its top reaches the ground or the box's sides, with every style's stack form. Found: the island's
    stack2 had a lip of relief-built rock over its notch (30 triangles 0.75 m over the heightmap: stack relief now
    builds at most terrain_mesh.STACK_BUILD); a column's rim hung over a deeper sea floor and the relief cut pieces off
    (`foot`: it runs into the floor; fallen blocks seat BOULDER_SEAT deep); ts_slice_a's anime stack stood beside a
    sliver of the heightfield's lobed core cut loose 5-12 m up by the clip under it (124 triangles 9.6 m up: the core
    is round now)."""
    from hifipushie import terrain_mesh as tm
    T, field = _coast_field()
    over = _style_forms()[style]
    vols = []
    for v in field.vols:  # (each stack again with this style's form, as stacks(T) makes it in that style's zone)
        if isinstance(v, tm.Stack):
            v = tm.Stack(v.name, v.xy, v.base, v.top, v.r, v.seed, clip=v.clip[0] if v.clip else None, sea=v.col.sea,
                         over=over, foot=v.col.foot)
        vols.append(v)
    field.vols = vols
    st = [v for v in vols if isinstance(v, tm.Stack)]
    assert st, "the test coast has no stacks"
    s18 = ndimage.generate_binary_structure(3, 2)
    for v in st:
        vox = 0.3
        m = v.col.reach + 2
        lo = np.r_[v.xy - m, v.col.foot - 1.0]
        hi = np.r_[v.xy + m, v.top + 2.0]
        ax = [np.arange(lo[i], hi[i] + vox, vox) for i in range(3)]
        G = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
        V = np.concatenate([field.value(G[i:i + 200000]) for i in range(0, len(G), 200000)])
        lab, n = ndimage.label(V.reshape([len(a) for a in ax]) < 0, s18)
        edge = set(np.unique(lab[:, :, 0])) | set(np.unique(lab[0])) | set(np.unique(lab[-1])) | \
            set(np.unique(lab[:, 0])) | set(np.unique(lab[:, -1]))
        loose = [i for i in range(1, n + 1) if i not in edge]
        where = [np.argwhere(lab == i).mean(0).round(1).tolist() for i in loose]
        assert not loose, f"{style} {v.name} ({v.col.stage}): {len(loose)} loose solid pieces (cells {where})"
