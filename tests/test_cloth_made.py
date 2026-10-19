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
    # every column keeps its pattern length (the fall boarded at its CUT length: laid, it lost up to half at the side
    # neck and stood as a wall there, cloth12), within the roll's turn
    l3 = np.linalg.norm(np.diff(G, axis=1), axis=-1).sum(1)
    lu = np.linalg.norm(np.diff(uv, axis=1), axis=-1).sum(1)
    assert np.all(np.abs(l3 / lu - 1) < 0.15), np.round(l3 / lu, 2)


def test_patch_transition_never_folds_where_two_lays_meet():
    # a seam along x; stations 0-5 one lay (columns running +y, the collar's end on the lapel), 10-15 the other
    # (columns running down, the fall); 6-9 the meeting, where each station's own columns of the two lays (built at
    # a corner of the seam: they lean along it, every way) blended point by point cross; the patch between the
    # boundary columns keeps every quad the same way round
    n, m = 16, 8
    s = np.arange(n) * 0.01
    r = np.arange(m) * 0.006
    end = np.stack([np.zeros(m), 0.02 + 2 * r, np.zeros(m)], 1)  # (also offset along +y: the end lies further back)
    fall = np.stack([np.zeros(m), np.zeros(m), -r], 1)  # (90 deg from the end's columns)
    w = np.clip((np.arange(n) - 5) / 5.0, 0, 1)
    G = np.stack([np.array([s[i], 0, 0]) + (1 - w[i]) * end + w[i] * fall for i in range(n)])
    lean = np.where((w > 0) & (w < 1), np.where(np.arange(n) % 2, 1.5, -1.5), 0.0)
    G[:, :, 0] += lean[:, None] * (r ** 2 / r[-1])[None]  # (the outer rows most)
    G[:, 0] = np.c_[s, np.zeros(n), np.zeros(n)]
    rowf = np.clip(np.arange(m) / 3.0, 0, 1)

    def flips(X):
        N = np.cross(X[1:, 1:] - X[:-1, :-1], X[:-1, 1:] - X[1:, :-1])
        return int(((N[1:] * N[:-1]).sum(-1) < 0).sum())
    zone = (w > 0) & (w < 1)
    assert flips(G) > 0  # the point-by-point blend folds
    P = cm.patch_transition(G, s, zone, rowf, 1)
    assert flips(P) == 0, flips(P)
    assert np.allclose(P[:, 0], G[:, 0]) and np.allclose(P[~zone], G[~zone])  # the seam row and the pure lays stay


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
    Vn, made = cm.construct(V, M, bV, bT, {"construct": {"lapel": "pressed"}})  # (press_flap; "made": below)
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
    # the CONSTRUCTED lapel (the default): on a flat front it is the same mirror image, its edges straight
    Vm, mm_ = cm.construct(V, M, bV, bT, {"construct": {"lapel_options": {"roll_top": 0.0}}})  # (pressed flat)
    assert mm_["info"]["made_lapel"]["front"]["made"] == len(flap)
    assert np.allclose(Vm[flap, 0], 0.16 - uv[flap, 0], atol=1e-6) and np.allclose(Vm[flap, 1], uv[flap, 1], atol=1e-6)
    assert (Vm[flap, 2] > 0).all() and Vm[flap, 2].max() <= 0.0061
    far = np.setdiff1d(np.where(uv[:, 0] > 0.18)[0], flap)
    assert np.allclose(Vm[far], V[far])  # the forepart beyond the lapel's reach untouched
    # the default ROLL (canvassed): the roll line stands off the front, most at its top (the gorge), and the lapel
    # comes down to lie flat toward its outer edge (cloth12)
    Vr, _ = cm.construct(V, M, bV, bT, {})
    roll_v = flap[np.abs(uv[flap, 0] - 0.07) < 1e-6]  # (the flap's column next to the roll line)
    outer_v = flap[uv[flap, 0] < 0.02]
    hr = Vr[roll_v, 2]
    assert hr.max() > hr.min() + 0.002, (hr.min(), hr.max())  # graded along the line (break -> gorge)
    hi_ = roll_v[hr > np.percentile(hr, 75)]
    assert Vr[hi_, 2].mean() > Vr[outer_v[np.isin(uv[outer_v, 1], uv[hi_, 1])], 2].mean() + 0.002  # flat at its edge


def test_pressed_flaps_by_fold_prefix():
    """construct's `press`: which folds' flaps are pressed (default lapels only; others experimental)."""
    uv, F = _strip_piece(0, 0.2, -0.3, 0, 21, 31)
    row = np.where(np.abs(uv[:, 0] - 0.08) < 1e-9)[0]
    M = {"names": ["front"], "piece": np.zeros(len(uv), int), "uv": uv, "F": F,
         "folds": [{"name": "open neck.L", "piece": "front", "rows": [row.tolist()]}]}
    assert cm.lapel_flaps(M) == []  # (default: lapels only)
    fl = cm.lapel_flaps(M, ("open neck",))
    assert len(fl) == 1 and len(fl[0]["flap"]) == int((uv[:, 0] < 0.08 - 1e-9).sum())
    assert cm.CONSTRUCT["press"] == ["lapel"]


def test_hug_neckline_draws_the_seam_to_what_is_under_it():
    """cloth10: a collar's ease holds the neckline `gap` off the under collar; the gorge (weight 0) stays; the cloth
    near the seam follows, far cloth doesn't; nothing ends inside the under layer."""
    V, F = _neck()
    under = {"V": V * np.array([1.08, 1.08, 1.0]), "F": F}  # an under collar ~5 mm out from the neck
    th = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    seam = np.c_[0.085 * np.cos(th), 0.085 * np.sin(th), np.full(48, 0.03)]  # 20 mm off the under layer
    below = seam + np.array([0, 0, -0.05])  # garment cloth 5 cm below the seam
    far = seam * np.array([1.0, 1.0, 0.0]) + np.array([0, 0, -0.10])
    Vg = np.concatenate([seam, below, far])
    w = np.ones(48)
    w[:6] = 0.0  # (a gorge)
    Vn, info = cm.hug_neckline(Vg, np.arange(48), w, [under], V, cm.outward(V, F), gap=0.003, reach=0.07, smooth=0)
    r = np.linalg.norm(Vn[:48, :2], axis=1)
    r_under = 0.060 * 1.08
    assert np.allclose(r[10:40], r_under + 0.003, atol=0.0015), r[10:40]
    assert np.allclose(Vn[:6], Vg[:6])  # the gorge stays
    assert (np.linalg.norm(Vn[58:88] - Vg[58:88], axis=1) > 0.001).all()  # near cloth follows (beside the gorge: less)
    assert np.allclose(Vn[96:], Vg[96:])  # far cloth stays
    assert info["seam_pull_mm"]["max"] <= 30.0 + 1e-6


def _cyl(r=0.150, z0=-0.3, z1=0.3, na=96, nz=40):
    th = np.linspace(0, 2 * np.pi, na, endpoint=False); zs = np.linspace(z0, z1, nz)
    V = np.stack([np.outer(np.ones(nz), r * np.cos(th)), np.outer(np.ones(nz), r * np.sin(th)), np.repeat(zs[:, None], na, 1)], -1).reshape(-1, 3)
    F = []
    for i in range(nz - 1):
        for j in range(na):
            a, b = i * na + j, i * na + (j + 1) % na
            F += [[a, b, b + na], [a, b + na, a + na]]
    return V, np.array(F)


def _garment(n=60, rs=0.175, rflare=0.200, cut=0.10, fold=0.05, ratio=0.8):
    """body tube: rows z 0.10 .. 0 (r rs); band: (n+1) columns (its ends sewn shut) x rows over the cut; the outer half
    flares down to rflare at the fold, the inner half back up inside it."""
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    Vb = np.concatenate([np.c_[rs * np.cos(th), rs * np.sin(th), np.full(n, z)] for z in (0.10, 0.05, 0.0)])
    Fb = cm.grid_faces(3, n)  # (unused shape check only)
    C = 2 * np.pi * rs
    L0 = ratio * C
    rows = np.linspace(0, cut, 11)
    thb = np.linspace(0, 2 * np.pi, n + 1)
    Vband, uvb = [], []
    for t in rows:
        tf = t if t <= fold else 2 * fold - t
        r = rs + (rflare - rs) * tf / fold - (0.003 if t > fold else 0)
        z = -tf
        Vband.append(np.c_[r * np.cos(thb), r * np.sin(thb), np.full(n + 1, z)])
        uvb.append(np.c_[np.linspace(0, L0, n + 1), np.full(n + 1, t)])
    Vband, uvb = np.concatenate(Vband), np.concatenate(uvb)
    nb = len(Vb)
    V = np.r_[Vb, Vband]
    uv = np.r_[np.c_[np.tile(np.linspace(0, C, n, endpoint=False), 3), np.repeat([0.1, 0.05, 0.0], n)], uvb]
    piece = np.r_[np.zeros(nb, int), np.ones(len(Vband), int)]
    m = n + 1
    sew = [[2 * n + (j % n), nb + j] for j in range(n + 1)]  # band row 0 to the body's last ring (both ends: station 0)
    sew += [[nb + r * m, nb + r * m + n] for r in range(1, len(rows))]  # the band's own closing seam
    F = np.r_[cm.grid_faces(len(rows), m).reshape(-1, 3) * 0]  # (faces aren't used by made_band)
    return V, {"names": ["front", "hem_band"], "piece": piece, "uv": uv, "sew": np.array(sew), "F": F}, nb, n, m, len(rows)


def test_made_band_folded_welt():
    bV, bF = _cyl()
    V, M, nb, n, m, nr = _garment()
    V2, info = cm.made_band(V, M, "hem_band", [{"V": bV, "F": cm.outward(bV, bF)}], gap=0.004, fold=0.05, layer=0.0025)
    band = V2[nb:].reshape(nr, m, 3)
    # the sewn row sits on the garment's side of the seam: the seam stays shut
    assert np.allclose(band[0, :n], V2[2 * n:3 * n], atol=1e-9), "seam opened"
    # the band drew in from the seam (r 175) towards its pattern girth (0.8: r 140) and stopped on the body
    r = np.linalg.norm(band[..., :2], axis=-1)
    assert r[5].max() < 0.165, f"fold ring not drawn in: {r[5].max():.4f}"
    assert r.min() > 0.150 + 0.004 - 0.0006, f"band inside the body's clearance: {r.min():.4f}"
    # the outside half lies over the turned-under half
    assert (r[1:5].mean(1) > r[9:5:-1].mean(1)).all(), "turned-under half not inside"
    # its own closing seam is shut and its depth is the finished (folded) depth
    assert np.allclose(band[:, 0], band[:, n], atol=1e-9)
    assert abs(band[5, :, 2].mean() + 0.05) < 0.006, band[5, :, 2].mean()
    assert info["folded"] and info["girth_mm"]["built_free_edge"] >= info["girth_mm"]["target_free_edge"] - 1
    print("ok", info)




def test_made_band_fold_read_from_drape():
    """dress-tess w1 (2026-10-15): construct.bands on the real sweater found no 360 deg fold record, so fold "auto"
    built the welt UNFOLDED at its whole cut (114.8 mm, "folded": false, 62% crumpled, 286 crossings). Without a record
    the fold is read from the drape (`drape_fold`): the folded band's rows turn back at the fold."""
    bV, bF = _cyl()
    V, M, nb, n, m, nr = _garment()
    assert not M.get("folds")
    V2, info = cm.made_band(V, M, "hem_band", [{"V": bV, "F": cm.outward(bV, bF)}], gap=0.004, fold="drape", layer=0.0025)
    assert info["folded"] and abs(info["depth_mm"] - 50) < 6, info
    # "auto" without a fold record = single layer (generate "fold": true always records its fold)
    _, info = cm.made_band(V, M, "hem_band", [{"V": bV, "F": cm.outward(bV, bF)}], gap=0.004, fold="auto", layer=0.0025)
    assert not info["folded"] and abs(info["depth_mm"] - 100) < 1, info
    # a single-layer band (rows run straight down, no turn) stays unfolded
    Vs = V.copy()
    k = np.arange(nb, len(V))
    tt = M["uv"][k, 1]
    Vs[k, 2] = -tt
    Vs[k, :2] *= (0.175 + 0.025 * tt / 0.10)[:, None] / np.linalg.norm(V[k, :2], axis=1)[:, None]
    assert cm.drape_fold(Vs, k, tt, Vs[np.asarray(M["sew"])[:n, 0]]) is None
    # the real w1 drape (the welt stood off, crumpled) shows no turn either: fold "half" = the cut's middle
    _, info = cm.made_band(Vs, M, "hem_band", [{"V": bV, "F": cm.outward(bV, bF)}], gap=0.004, fold="half", layer=0.0025)
    assert info["folded"] and abs(info["depth_mm"] - 50) < 6, info


def test_made_band_depth_on_a_curved_cut():
    """dress-tess w1's welt "lost its fold record" (2026-10-15): it never had one. It is a single-layer knitted_rib
    ("fold": false) cut as an annular sector (top_ratio 0.92), and made_band read depth along ONE pattern axis, which
    took in the sewn arc's sagitta: 114.8 mm "cut" for a 50 mm welt, built at twice its depth. Depth is now the
    distance from the sewn edge in the flat, and each row's length its own arc."""
    bV, bF = _cyl()
    h, tr = 0.05, 0.92
    V, M, nb, n, m, nr = _garment(cut=h, fold=h)
    uv = np.array(M["uv"], float)
    k = np.arange(nb, len(V))
    L0 = uv[k, 0].max()
    R1 = h / (1 - tr)
    ph = (uv[k, 0] - L0 / 2) / R1
    R = R1 - uv[k, 1]
    uv[k] = np.c_[R * np.sin(ph), R * np.cos(ph)]
    M = dict(M, uv=uv)
    _, info = cm.made_band(V, M, "hem_band", [{"V": bV, "F": cm.outward(bV, bF)}], gap=0.004, fold="auto", layer=0.0025)
    assert not info["folded"] and abs(info["depth_mm"] - 50) < 1 and abs(info["cut_mm"] - 50) < 1, info
    assert abs(info["girth_mm"]["pattern_free_edge"] - tr * L0 * 1000) < 0.01 * L0 * 1000, (info, tr * L0 * 1000)

def test_seam_gaps_leave_out_pieces_a_made_part_replaces():
    """dg_j8 / j10: the simulated collar (replaced by the made one, never shipped) read as the collar seam open 59-137
    mm; the shipped collar met the neckline at 0.0 mm. seam_gaps(made=) measures the shipped part instead."""
    from hifipushie import cloth
    V = np.array([[0, 0, 0], [0, 0, 0], [1, 0, 0], [1, 0.1, 0], [2, 0, 0], [2, 0, 0]], float)
    M = {"sew": [[0, 1], [2, 3], [4, 5]], "names": ["front", "collar", "back"], "piece": [0, 0, 0, 1, 2, 2]}
    g0 = cloth.seam_gaps(V, V, M)
    assert g0["open"] == 1 and g0["worst"] == "collar / front"
    made = {"parts": [{"name": "collar", "V": np.array([[1, 0, 0.001]]), "F": [[0, 0, 0]], "replaces": ["collar"]}]}
    g1 = cloth.seam_gaps(V, V, M, made)
    assert g1["open"] == 0 and g1["pairs"] == 2 and g1["replaced_pairs"] == 1
    assert g1["made_seam"]["pairs"] == 1 and abs(g1["made_seam"]["max"] - 1.0) < 1e-6




def test_mirror_pairs_and_symmetrize_make_left_and_right_one_shape():
    # (dress-garrett 2026-10-15: j10's lapels rolled 51 / 142 deg from a symmetric start; construct mirror="mean"
    # presses both sides to one shape. R pieces are cut mirrored: their uv is the left's with u negated)
    import numpy as np
    from hifipushie import cloth_made as cm
    rng = np.random.default_rng(1)
    uvL = rng.uniform([0.0, -0.5], [0.25, 0.0], (40, 2))
    order = rng.permutation(40)
    uvR = uvL[order] * [-1, 1]
    M = {"names": ["front.L", "front.R"], "piece": np.r_[np.zeros(40, int), np.ones(40, int)], "uv": np.r_[uvL, uvR]}
    iL, iR = cm.mirror_pairs(M)
    assert len(iL) == 40 and np.allclose(M["uv"][iR] * [-1, 1], M["uv"][iL])
    VL = np.c_[0.05 + uvL[:, 0], np.full(40, -0.15), 1.2 + uvL[:, 1]]
    VR = (VL * [-1, 1, 1])[order] + rng.normal(0, 0.01, (40, 3))  # the right side off by ~1 cm
    V = cm.symmetrize(np.r_[VL, VR], iL, iR, 0.0)
    assert np.allclose(V[iL], V[iR] * [-1, 1, 1])
    w = np.zeros(40)
    V0 = np.r_[VL, VR]
    assert np.allclose(cm.symmetrize(V0, iL, iR, 0.0, w), V0)  # weight 0 leaves the drape as it was
    # a side-to-side grid (a collar): station i pairs with n-1-i
    n, m = 7, 3
    xs = np.linspace(-0.1, 0.1, n)
    P = np.array([[x, 0.05 + 0.2 * x * x, 1.5 + 0.01 * j] for x in xs for j in range(m)])
    P[: m, 2] += 0.004
    Q, mis = cm.mirror_part(P, (n, m), 0.0)
    assert mis < 0.03 and np.allclose(Q.reshape(n, m, 3)[:, :, 2], Q.reshape(n, m, 3)[::-1, :, 2])


def test_construct_bands_clear_the_finished_under_garment_with_a_scoop():
    """dress-tess ds37 (2026-10-16): the sweater's welt crossed the jeans at 17-25 vertices. construct_bands was handed
    the jeans PRESSED (the collider the sweater was simulated over: loose cloth capped 8 mm off the body), which lies up
    to ~38 mm inside the jeans as drawn and checked; and over the front pocket's scoop (a cut edge, the pocket bag
    behind it) a closed-surface layer let the band settle into the opening. The band is now built clear of the FINISHED
    under garment, as a sheet with its render thickness."""
    bV, bF = _cyl()
    V, M, nb, n, m, nr = _garment()
    na, nz = 96, 40
    th = np.linspace(0, 2 * np.pi, na, endpoint=False)
    zs = np.linspace(-0.3, 0.3, nz)

    def tube(r, keep=lambda t, z: True):
        P = np.stack([np.outer(np.ones(nz), r * np.cos(th)), np.outer(np.ones(nz), r * np.sin(th)),
                      np.repeat(zs[:, None], na, 1)], -1).reshape(-1, 3)
        F = []
        for i in range(nz - 1):
            for j in range(na):
                a, b = i * na + j, i * na + (j + 1) % na
                tc, zc = th[j] + np.pi / na, 0.5 * (zs[i] + zs[i + 1])
                if keep(tc, zc):
                    F += [[a, b, b + na], [a, b + na, a + na]]
        return P, np.array(F)
    scoop = lambda t, z: 0.3 < t < 1.2 and -0.08 < z < 0.03  # the pocket mouth: no front panel there
    pV, pF = tube(0.155)  # pressed
    fV, fF = tube(0.165, keep=lambda t, z: not scoop(t, z))  # finished front panel, scoop cut out
    gV, gF = tube(0.158, keep=lambda t, z: 0.2 < t < 1.3 and -0.12 < z < 0.05)  # the pocket bag behind it
    # one under mesh: panel + bag (same topology for pressed / finished: the pressed bag lies on the pressed panel)
    uF = np.r_[fF, gF + len(fV)]
    under_fin = np.r_[fV, gV]
    under_pr = np.r_[pV, pV]
    opt = {"bands": ["hem_band"], "band_options": {"fold": 0.05}}
    Fo = cm.outward(bV, bF)

    def worst(Vb):
        """mm by which band vertices lie inside the finished under cloth (panel outside the scoop, the bag in it)."""
        P = Vb[nb:]
        r = np.linalg.norm(P[:, :2], axis=1)
        t = np.mod(np.arctan2(P[:, 1], P[:, 0]), 2 * np.pi)
        z = P[:, 2]
        core = (t > 0.3) & (t < 1.2) & (z > -0.08) & (z < 0.03)
        wall = np.where(core, 0.158, 0.165)
        # (at the cut edge either may hold: within a cell of it)
        edge = (((np.abs(t - 0.3) < 0.08) | (np.abs(t - 1.2) < 0.08)) & (z > -0.1) & (z < 0.05)) | \
            ((np.abs(z + 0.08) < 0.016) & (t > 0.2) & (t < 1.3))
        bad = ~edge & (r < wall)
        return float(((wall - r) * bad).max() * 1000), int(bad.sum())
    # as before: only the pressed jeans -> the band sits inside the finished jeans
    V_old, _ = cm.construct_bands(np.array(V), M, bV, Fo, {}, {"V": under_pr, "F": uF}, opt)
    mm_old, n_old = worst(V_old)
    assert n_old > 0 and mm_old > 3, (mm_old, n_old)
    # now: clear of the finished jeans, panel and bag
    V_new, info = cm.construct_bands(np.array(V), M, bV, Fo, {}, {"V": under_pr, "F": uF, "finished": under_fin,
                                                                 "thickness": 0.0006,
                                                                 "piece": np.r_[np.zeros(len(fV), int), np.ones(len(gV), int)]}, opt)
    mm_new, n_new = worst(V_new)
    assert n_new == 0, (mm_new, n_new)
    # and the band still drew in where nothing holds it out more (the scoop: down to the bag)
    P = V_new[nb:]
    t = np.mod(np.arctan2(P[:, 1], P[:, 0]), 2 * np.pi)
    rin = np.linalg.norm(P[:, :2], axis=1)[(t > 0.5) & (t < 1.0) & (P[:, 2] < -0.01) & (P[:, 2] > -0.06)]
    assert len(rin) and rin.min() < 0.165, rin.min()
    print("ok", mm_old, n_old, "->", mm_new, n_new, info["hem_band"]["depth_mm"])


def test_untuck_crossings_reverts_only_what_the_tuck_pushed_through():
    """ds37: worn_together's tuck laid the jeans' pocket corners through the sweater's welt (10 -> 31 crossing vertices).
    untuck_crossings sends back only moved vertices in new crossings; other tuck moves stay."""
    from hifipushie import cloth
    n = 12
    g = np.linspace(-0.1, 0.1, n)
    P = np.array([[x, y, 0.0] for x in g for y in g])
    Fg = cm.grid_faces(n, n)
    V0 = P + [0.0061, 0.0047, -0.010]  # the under garment as finished: 10 mm under the outer one (off its vertices)
    V = V0.copy()
    V[:, 2] -= 0.002  # the tuck lays everything 2 mm further in ...
    k = (np.abs(P[:, 0]) < 0.03) & (np.abs(P[:, 1]) < 0.03)
    V[k, 2] = 0.006  # ... and pushes a patch out through the outer cloth
    outer = {"V": P, "mesh": {"F": Fg}}
    assert cloth._layer_crossing_verts(V, Fg, P, Fg).any()
    V2 = cloth.untuck_crossings(V0, V, {"F": Fg}, outer)
    assert not cloth._layer_crossing_verts(V2, Fg, P, Fg).any()
    far = (np.abs(P[:, 0]) > 0.06) | (np.abs(P[:, 1]) > 0.06)
    assert np.allclose(V2[far], V[far]), "a tuck move away from the crossing was undone"
    assert np.allclose(V2[k], V0[k])


def test_fair_edge_runs_redraws_a_crowded_hooked_end_and_keeps_ordinary_corners():
    """cloth_made.fair_edge_runs (dress-garrett ag): a made part's outline with a crowded run (short segments hooking
    out past the edge, the jacket collar's ends) is redrawn as one smooth curve; a grid with even spacing (its four
    corners ordinary) is left as it is."""
    import numpy as np
    from hifipushie import cloth_made
    nx, nz = 12, 5
    X, Z = np.meshgrid(np.linspace(0, 0.088, nx), np.linspace(0, 0.032, nz))
    V = np.c_[X.ravel(), np.zeros(nx * nz), Z.ravel()]
    F = []
    for j in range(nz - 1):
        for i in range(nx - 1):
            a = j * nx + i
            F += [[a, a + 1, a + nx + 1], [a, a + nx + 1, a + nx]]
    F = np.array(F)
    V2, info = cloth_made.fair_edge_runs(V, F)
    assert info["moved"] == 0 and np.allclose(V2, V)
    # crowd the bottom edge's last three vertices into a hook 6 mm below the edge
    H = V.copy()
    for k, i in enumerate((nx - 4, nx - 3, nx - 2)):
        H[i] = [V[nx - 4, 0] + 0.0012 * k, 0.0, -0.006 + 0.0012 * k]
    out = lambda W: float(-W[:nx, 2].min())
    V3, info = cloth_made.fair_edge_runs(H, F)
    assert info["moved"] > 0 and out(V3) < 0.5 * out(H), (out(H), out(V3), info)
    assert np.allclose(V3[nx * 3:], H[nx * 3:])  # past the relaxed rings: untouched



def test_seat_fall_turns_a_raised_fall_down_and_keeps_kept_stations():
    """dress-garrett ai: seat_fall turns each station's rows past its roll top about the seam tangent until the outer
    edge lies `gap` over the cloth; a station already down, or in `keep`, is not moved; column lengths are kept."""
    import numpy as np
    from hifipushie import cloth_made as cm
    # the cloth: a floor at z=0 (a big two-triangle sheet, wound up)
    fV = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], float)
    fF = np.array([[0, 1, 2], [0, 2, 3]])
    u = cm.Under([{"V": fV, "F": fF, "sheet": True}])
    n, m = 9, 6
    G = np.zeros((n, m, 3))
    for i in range(n):  # seam along x at z=0.02, the roll top row 1 at z=0.03, the fall standing out level along -y
        G[i, 0] = [0.01 * i, 0.0, 0.02]
        G[i, 1] = [0.01 * i, -0.005, 0.03]
        for r in range(2, m):
            G[i, r] = [0.01 * i, -0.005 - 0.008 * (r - 1), 0.03 - 0.0005 * (r - 1)]
    keep = np.zeros(n, bool)
    keep[0] = True
    G2, info = cm.seat_fall(G, u, 0.004, smooth=0.0, keep=keep)
    assert np.allclose(G2[0], G[0])  # kept
    assert np.allclose(G2[:, :2], G[:, :2])  # the seam and the roll top stay
    assert (G2[1:, -1, 2] < 0.012).all(), G2[1:, -1, 2]  # the outer edge turned down toward the floor
    assert (G2[1:, -1, 2] > 0.0035).all()  # and kept clear of it
    L = lambda X: np.linalg.norm(np.diff(X, axis=1), axis=-1).sum(1)
    assert np.allclose(L(G2), L(G), atol=1e-6)  # turned as a board: its length as cut


def test_even_outer_evens_the_outer_edge_and_keeps_the_seam():
    # a flat 10 x 6 grid whose outer row is bunched (fanned columns): stations evened along the outer row, seam row kept
    n, m = 10, 6
    x = np.linspace(0, 0.09, n)
    G = np.zeros((n, m, 3))
    for j in range(m):
        t = j / (m - 1)
        xo = x + t * 0.004 * np.sin(np.linspace(0, np.pi, n)) ** 2 * np.r_[np.ones(5), -np.ones(5)]
        G[:, j, 0], G[:, j, 1] = xo, 0.03 * t
    sel = np.ones(n, bool)
    E = cm.even_outer(G, sel)
    st0 = np.linalg.norm(np.diff(G[:, -1], axis=0), axis=1)
    st1 = np.linalg.norm(np.diff(E[:, -1], axis=0), axis=1)
    assert st1.max() / st1.min() < 1.05 < st0.max() / st0.min()
    assert np.allclose(E[:, 0], G[:, 0])


def test_round_corner_rounds_the_end_column_corner():
    # a flat grid, end column 0 along +y, outer edge along +x: the corner point moves in onto a fillet of radius R
    n, m, R = 12, 16, 0.008
    G = np.zeros((n, m, 3))
    G[..., 0] = np.linspace(0, 0.06, n)[:, None]
    G[..., 1] = np.linspace(0, 0.03, m)[None]
    E = cm.round_corner(G, 0, R)
    c = E[0, -1]
    # the arc's mid point of a 90 deg fillet sits R (sqrt2 - 1) in from the square corner
    assert abs(np.linalg.norm(c - G[0, -1]) - R * (np.sqrt(2) - 1)) < 1e-3
    assert np.allclose(E[0, :m // 2], G[0, :m // 2]) and np.allclose(E[-1], G[-1])
    assert np.allclose(E[..., 2], 0)  # (stays in the sheet's plane)
    E2 = cm.round_corner(G, n - 1, R)
    assert np.linalg.norm(E2[-1, -1] - G[-1, -1]) > 1e-3


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
