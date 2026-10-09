"""Made pieces constructed on a finished drape (cloth_made): a shirt collar on a synthetic neck, a pressed flap.
Run: uv run python tests/test_cloth_made.py  (or pytest)."""
import numpy as np

from hifipushie import cloth_made as cm
from hifipushie import cloth_layers


def _neck(n_ang=96, n_z=60):
    """A body of revolution about z: a neck (r 60 mm) on shoulders sloping away below z = 0; closed top and bottom."""
    zs = np.linspace(-0.12, 0.16, n_z)
    r = np.where(zs > 0, 0.060 + 0.0 * zs, 0.060 + 0.9 * np.abs(zs) ** 1.0)
    r = np.where(np.abs(zs) < 0.015, 0.060 + 0.9 * (0.015 - zs) ** 2 / 0.06, r)  # a rounded corner
    th = np.linspace(0, 2 * np.pi, n_ang, endpoint=False)
    V = np.stack([np.outer(r, np.cos(th)), np.outer(r, np.sin(th)), np.repeat(zs[:, None], n_ang, 1)], -1).reshape(-1, 3)
    F = []
    for i in range(n_z - 1):
        for j in range(n_ang):
            a, b = i * n_ang + j, i * n_ang + (j + 1) % n_ang
            F += [[a, b, b + n_ang], [a, b + n_ang, a + n_ang]]
    top, bot = len(V), len(V) + 1
    V = np.concatenate([V, [[0, 0, zs[-1]], [0, 0, zs[0]]]])
    for j in range(n_ang):
        F.append([(n_z - 1) * n_ang + j, (n_z - 1) * n_ang + (j + 1) % n_ang, top])
        F.append([(j + 1) % n_ang, j, bot])
    return V, np.array(F)


def _neckline(open_deg=40.0, n=41, z=-0.012, off=0.004):
    """A seam round the neck's base, open at the front (-y), from one front end round the back to the other."""
    a0 = np.radians(-90 + open_deg / 2)
    th = np.linspace(a0, a0 + np.radians(360 - open_deg), n)
    r = 0.060 + 0.9 * abs(z) + off
    return np.stack([r * np.cos(th), r * np.sin(th), np.full(n, z)], 1)


def _build(**kw):
    V, F = _neck()
    P = _neckline()
    out = cm.shirt_collar(P, {"V": V, "F": F}, [], (np.zeros(3), np.array([0, 0, 1.0])), **kw)
    return V, F, P, out


def test_shirt_collar_honours_its_parameters():
    V, F, P, out = _build(stand=0.028, fall_over=0.012, points=0.07, open=0.0)
    stand, fall = out["parts"]
    n, m = stand["grid"]
    S = stand["V"].reshape(n, m, 3)
    assert np.allclose(S[::2][:len(P)][:, 0][0], P[0], atol=1e-9)  # the seam row starts on the seam
    # every seam vertex is a vertex of the stand's first row (welded: no gap)
    d = np.linalg.norm(S[:, 0][None] - P[:, None], axis=2).min(1)
    assert d.max() < 1e-9
    cb = n // 2
    rise = np.linalg.norm(np.diff(S[cb], axis=0), axis=1).sum()
    assert abs(rise - 0.028) < 0.002, rise
    assert S[cb, -1, 2] - S[cb, 0, 2] > 0.022  # it stands
    nf, mf = fall["grid"]
    G = fall["V"].reshape(nf, mf, 3)
    cbf = nf // 2
    depth = np.linalg.norm(np.diff(G[cbf], axis=0), axis=1).sum()
    assert abs(depth - 0.040) < 0.004, depth
    assert G[cbf, -1, 2] < S[cb, 0, 2] + 0.004  # the fall covers the seam at centre back
    # the points: as long as asked, in the pattern and as laid
    uv = fall["uv"].reshape(nf, mf, 2)
    for k in (0, nf - 1):
        assert abs(np.linalg.norm(uv[k, -1] - uv[k, 0]) - 0.07) < 0.002
        laid = np.linalg.norm(np.diff(G[k], axis=0), axis=1).sum()
        assert abs(laid - 0.07) < 0.008, laid
    # near isometric
    assert 0.9 < out["info"]["fall_stretch"]["p50"] < 1.06
    assert out["info"]["fall_stretch"]["p95"] < 1.35


def test_shirt_collar_clears_the_body():
    V, F, P, out = _build()
    Fo = cm.outward(V, F)
    for pt in out["parts"]:
        assert cloth_layers.between_crossings(pt["V"], pt["F"], V, Fo) == 0, pt["name"]
        Q, N, _ = cm.closest(pt["V"], V, Fo)
        sd = ((pt["V"] - Q) * N).sum(1)
        assert sd.min() > 0.0005, (pt["name"], sd.min())
    # a taller stand is taller; a longer point is longer
    a = _build(stand=0.022)[3]["parts"][0]
    b = _build(stand=0.032)[3]["parts"][0]
    assert b["V"][:, 2].max() - a["V"][:, 2].max() > 0.006


def test_solid_is_closed():
    V, F, P, out = _build()
    pt = out["parts"][1]
    Vs, Fs = cm.solid(pt["V"], pt["F"], 0.0016)
    E = np.sort(np.concatenate([Fs[:, [0, 1]], Fs[:, [1, 2]], Fs[:, [2, 0]]]), axis=1)
    _, cnt = np.unique(E, axis=0, return_counts=True)
    assert (cnt == 2).all()


def test_press_flap_lays_the_mirror_image():
    # a flat square piece, the strip x > 0.08 folded over the line x = 0.08
    xs = np.linspace(0, 0.12, 13)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    uv = np.stack([X.ravel(), Y.ravel()], 1)
    V = np.c_[uv, np.zeros(len(uv))]
    F = cm.grid_faces(13, 13)
    flap = np.where(uv[:, 0] > 0.08 + 1e-9)[0]
    Vn = cm.press_flap(V, F, uv, flap, ((0.08, 0.0), (0.0, 1.0)), lay=0.003, wedge=0.35,
                       out=np.tile([0, 0, 1.0], (len(V), 1)))
    assert np.allclose(Vn[flap, 0], 0.16 - uv[flap, 0], atol=1e-9)
    assert np.allclose(Vn[flap, 1], uv[flap, 1], atol=1e-9)
    assert (Vn[flap, 2] > 0).all() and Vn[flap, 2].max() <= 0.003 + 1e-12
    keep = np.setdiff1d(np.arange(len(V)), flap)
    assert np.allclose(Vn[keep], V[keep])


def _strip_piece(x0, x1, y0, y1, nx, ny):
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    return np.stack([X.ravel(), Y.ravel()], 1), cm.grid_faces(nx, ny)


def test_sewn_image_lays_two_pieces_edge_to_edge():
    # piece a: a strip above its sewn edge y = 0 (x 0..0.1); piece b: below ITS edge, which runs along x = 1 downward
    uv_a, _ = _strip_piece(0, 0.1, 0, 0.04, 11, 5)
    uv_b = np.stack([1 - np.linspace(0, 0.05, 6)[:, None].repeat(11, 1).ravel(),
                     -np.linspace(0, 0.1, 11)[None].repeat(6, 0).ravel()], 1)
    ea = np.stack([np.linspace(0, 0.1, 11), np.zeros(11)], 1)
    eb = np.stack([np.ones(11), -np.linspace(0, 0.1, 11)], 1)
    P = np.array([[0.03, 0.02], [0.1, 0.04], [0.12, 0.01]])  # (the last one past the seam's end: run on straight)
    Q = cm.sewn_image(P, ea, eb, uv_a, uv_b)
    assert np.allclose(Q, [[1.02, -0.03], [1.04, -0.1], [1.01, -0.12]], atol=1e-9), Q
    s, d = cm.edge_coords(np.array([[0.05, 0.01], [-0.02, -0.01]]), ea)
    assert np.allclose(s, [0.05, -0.02]) and np.allclose(d, [0.01, -0.01])


def test_on_pattern_is_the_piece_run_on_as_a_board():
    uv, F = _strip_piece(0, 0.2, 0, 0.2, 21, 21)
    V = np.c_[uv[:, 0], 0.8 * uv[:, 1], 0.6 * uv[:, 1]]  # a tilted plane, isometric
    img = np.array([[0.1, 0.1], [0.25, 0.1], [0.1, -0.03]])  # inside, and past two edges
    X, N = cm.on_pattern(V, F, uv, img, out=np.tile([0, -0.6, 0.8], (len(V), 1)))
    assert np.allclose(X, np.c_[img[:, 0], 0.8 * img[:, 1], 0.6 * img[:, 1]], atol=1e-9)
    assert np.allclose(N, [[0, -0.6, 0.8]] * 3, atol=1e-9)


def test_collar_pattern_reads_the_drafted_outline():
    # a collar strip with slanted ends (a notch's collar side): sewn along y = 0
    nx = 21
    xs = np.linspace(-0.1, 0.1, nx)
    uv = np.concatenate([np.c_[xs, np.zeros(nx)], np.c_[xs * 1.2, np.full(nx, 0.02)], np.c_[xs * 1.4, np.full(nx, 0.04)]])
    F = np.concatenate([cm.grid_faces(3, nx)[:, ::1]])
    uv = uv.reshape(3, nx, 2).reshape(-1, 2)
    pat = cm.collar_pattern(uv, F, np.arange(nx), roll_row=np.arange(nx, 2 * nx))
    assert np.allclose(pat["edge"], uv[:nx])
    assert np.allclose(pat["outer"][0], [-0.14, 0.04]) and np.allclose(pat["outer"][-1], [0.14, 0.04])  # the end corners
    assert len(pat["roll"]) == nx


def test_notched_end_lies_in_the_turned_lapels_plane():
    """The end lay's steps on a flat synthetic front: a collar end sewn to the gorge edge, carried across the seam,
    mirrored across the roll line and laid on the forepart: one plane with the pressed lapel, isometric, and the
    notch between the collar's end edge and the lapel's top edge is the drafted one."""
    # the front: x 0..0.2, y -0.3..0; roll line x = 0.08 (flap: x < 0.08); gorge = the top edge y = 0, x 0.08 -> 0.02
    uv, F = _strip_piece(0, 0.2, -0.3, 0, 21, 31)
    V = np.c_[uv, np.zeros(len(uv))]
    up = np.tile([0, 0, 1.0], (len(V), 1))
    flap = np.where(uv[:, 0] < 0.08 - 1e-9)[0]
    Vp = cm.press_flap(V, F, uv, flap, ((0.08, 0.0), (0.0, 1.0)), lay=0.003, wedge=0.35, out=up)
    isf = np.zeros(len(V), bool); isf[flap] = True
    Fb = F[~isf[F].any(1)]
    # the collar's end in its own pattern: sewn edge along its y = 0 from x = 0 (the meeting point) to 0.06, 0.04 deep,
    # its end edge square to the seam
    cuv, _ = _strip_piece(0, 0.06, 0, 0.04, 7, 5)
    ea = np.stack([np.linspace(0, 0.06, 7), np.zeros(7)], 1)
    eb = np.stack([0.08 - np.linspace(0, 0.06, 7), np.zeros(7)], 1)
    img = cm.sewn_image(cuv, ea, eb, cuv, uv)
    assert np.allclose(img, np.c_[0.08 - cuv[:, 0], cuv[:, 1]], atol=1e-9)  # past the top edge, on the flap's side
    mir = np.c_[0.16 - img[:, 0], img[:, 1]]
    X, N = cm.on_pattern(Vp, Fb, uv, mir, out=up)
    X = X + 0.003 * N
    assert np.allclose(X[:, 2], 0.003, atol=1e-9)  # the lapel's own height: one surface with it
    assert np.allclose(X[:, :2], mir, atol=1e-9)  # isometric (a mirror image), running on past the piece's top edge
    seam = np.where(np.abs(cuv[:, 1]) < 1e-12)[0]
    fl_top = np.where((np.abs(uv[:, 1]) < 1e-12) & (uv[:, 0] < 0.08 + 1e-9))[0]
    d = np.linalg.norm(X[seam][:, None, :2] - Vp[fl_top][None, :, :2], axis=2).min(1)
    assert d.max() < 1e-9  # the collar's seam row lies on the pressed lapel's gorge edge
    # the notch: the collar's end edge (square to the gorge) against the lapel's top edge run on past the gorge's end
    end = X[np.abs(cuv[:, 0] - 0.06) < 1e-12]
    ce = end[np.argmax(end[:, 1])] - end[np.argmin(end[:, 1])]
    lapel_pt = Vp[flap[np.argmin(uv[flap, 0] + 10 * np.abs(uv[flap, 1]))]]  # the flap's top corner (x = 0, y = 0)
    le = lapel_pt - end[np.argmin(end[:, 1])]
    ang = np.degrees(np.arccos(ce[:2] @ le[:2] / np.linalg.norm(ce[:2]) / np.linalg.norm(le[:2])))
    assert abs(ang - 90) < 1e-6 and abs(np.linalg.norm(le[:2]) - 0.02) < 1e-9


def test_notched_collar_follows_its_draft():
    V, F = _neck()
    P = _neckline(open_deg=60.0, n=41, z=-0.02, off=0.006)
    L = np.linalg.norm(np.diff(P, axis=0), axis=1).sum()
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    edge = np.c_[s - L / 2, np.zeros(len(P))]
    xo = np.linspace(-L / 2 - 0.02, L / 2 + 0.02, 30)
    outer = np.c_[xo, np.full(30, 0.06)]
    xr = np.linspace(-0.6 * L / 2, 0.6 * L / 2, 25)
    roll = np.c_[xr, 0.022 * (1 - (xr / xr[-1]) ** 2)]
    into = np.tile([0, 0, -1.0], (len(P), 1))
    out = cm.notched_collar(P, into, np.zeros(len(P), bool), {"V": V, "F": F}, [], [], (np.zeros(3), np.array([0, 0, 1.0])),
                            pattern={"edge": edge, "outer": outer, "roll": roll})
    pt = out["parts"][0]
    n, m = pt["grid"]
    uv, G = pt["uv"].reshape(n, m, 2), pt["V"].reshape(n, m, 3)
    assert np.allclose(uv[0, 0], edge[0]) and np.allclose(uv[0, -1], outer[0], atol=1e-6)  # the end edge is the draft's
    assert np.allclose(uv[-1, -1], outer[-1], atol=1e-6)
    cb = n // 2
    assert abs(np.linalg.norm(uv[cb, -1] - uv[cb, 0]) - 0.06) < 1e-3
    assert 0.019 < G[cb, :, 2].max() - G[cb, 0, 2] < 0.028  # it stands to the draft's roll line (22 mm + the roll)
    assert G[0, :, 2].max() - G[0, 0, 2] < 0.012  # and not at its ends
    assert np.linalg.norm(G[:, 0] - np.array([cm._stations(P, 0.010)[0]])[0], axis=1).max() < 1e-9  # on the seam


def _box(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    V = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    F = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return V, F


def test_construct_presses_lapels_and_is_not_in_the_sims_key():
    from hifipushie import cloth
    assert "construct" in cloth.NOT_SIM and "construct" in cloth.GARMENT_KEYS  # post-sim: the sim's key never moves
    uv, F = _strip_piece(0, 0.2, -0.3, 0, 21, 31)
    V = np.c_[uv, np.zeros(len(uv))]
    flap = np.where(uv[:, 0] < 0.08 - 1e-9)[0]
    V[flap, 2] = 0.02 + 0.3 * (0.08 - uv[flap, 0])  # the lapel as a sim leaves it: standing off its forepart
    row = np.where(np.abs(uv[:, 0] - 0.08) < 1e-9)[0]
    M = {"names": ["front"], "piece": np.zeros(len(V), int), "uv": uv, "F": F, "sew": None,
         "folds": [{"name": "lapel roll", "piece": "front", "rows": [row.tolist()]}]}
    bV, bT = _box([-0.1, -0.4, -0.06], [0.3, 0.1, -0.004])
    Vn, made = cm.construct(V, M, bV, bT, {})
    assert made and made["lapels"][0]["vertices"] == len(flap) and not made["parts"]
    assert np.allclose(Vn[flap, 0], 0.16 - uv[flap, 0], atol=1e-9) and Vn[flap, 2].max() <= 0.003 + 1e-9
    assert (Vn[flap, 2] > 0).all()  # on the side away from the body
    keep = np.setdiff1d(np.arange(len(V)), flap)
    assert np.allclose(Vn[keep], V[keep])
    for off in (False, {"lapels": False}):
        V2, m2 = cm.construct(V, M, bV, bT, {"construct": off})
        assert m2 is None and np.allclose(V2, V)
    V3, m3 = cm.construct(V, dict(M, folds=[]), bV, bT, {})  # nothing to construct: the result is the sim's
    assert m3 is None and V3 is V
    hide, parts = cm.drawn({"mesh": M, "made": made})
    assert not hide.any() and parts == []


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
