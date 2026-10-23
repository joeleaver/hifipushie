"""Layered garments, geometry only (no sim): the padded body, layer crossings, hidden faces, supports' errors.
uv run python tests/test_cloth_layers.py"""
import numpy as np
from scipy.spatial import ConvexHull

from hifipushie import cloth, cloth_layers


def _sphere(r=0.1, n=1500, seed=1):
    rng = np.random.default_rng(seed)
    P = rng.normal(size=(n, 3))
    P /= np.linalg.norm(P, axis=1, keepdims=True)
    F = ConvexHull(P).simplices
    c = P[F].mean(1)
    nrm = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    flip = (nrm * c).sum(1) < 0
    F[flip] = F[flip][:, [0, 2, 1]]
    return P * r, F


def _shell(V, F, r, zmax=None):
    V2 = V / np.linalg.norm(V, axis=1, keepdims=True) * r
    if zmax is not None:
        F = F[(V2[F][:, :, 2] < zmax).all(1)]
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    ue, cnt = np.unique(E, axis=0, return_counts=True)
    border = np.zeros(len(V2), bool)
    border[ue[cnt == 1].ravel()] = True
    return {"V": V2, "mesh": {"F": F, "sew": np.zeros((0, 2), np.int64), "border": border}}


def test_padded_body_covers_the_under_garment():
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    U = V[V[:, 2] > 0] * 1.08  # a cap worn 8 mm off the upper half
    pb = cloth.padded_body(body, {}, U, air=0.003)
    r = np.linalg.norm(pb.V, axis=1)
    top, bottom = V[:, 2] > 0.03, V[:, 2] < -0.085  # (the pad runs on ~6 cm past the garment's edge)
    assert r[top].min() > 0.108 + 0.002 and np.abs(r[bottom] - 0.1).max() < 1e-9, (r[top].min(), r[bottom].max())
    assert pb.clearance(U).max() < 0  # every point of the under garment is inside the padded body


def test_crossings_between_layers():
    A = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0.0]])
    B = np.array([[0.2, 0.2, -0.5], [0.3, 0.2, 0.5], [0.2, 0.3, 0.5]])
    F = np.array([[0, 1, 2]])
    assert cloth_layers.between_crossings(A, F, B, F) >= 1
    assert cloth_layers.between_crossings(A, F, B + [0, 0, 2.0], F) == 0


def test_hidden_faces_keep_a_margin_at_the_openings():
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    under = _shell(V, F, 0.103)
    outer = dict(_shell(V, F, 0.108, zmax=0.05), body=body)  # open above z = 0.05
    h = cloth_layers.hidden(under, outer, margin=0.02, rule="margin")
    z = under["V"][under["mesh"]["F"]].mean(1)[:, 2]
    assert h[z < 0.0].mean() > 0.97 and not h[z > 0.06].any(), (h[z < 0].mean(), h[z > 0.06].sum())
    assert not h[(z > 0.04)].any()  # the margin inside the opening stays


def test_cut_by_visibility_and_crossings():
    # merge-and-cut: an under shell inside an outer one open above z = 0.05. Cut: what the outer shell hides from every
    # direction, and a patch pushed out through it far from the opening; kept: the cloth seen through the opening, a
    # patch crossing beside the opening (it shows there), and the `keep` vertices (a collar) wherever they are
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    under = _shell(*_sphere(seed=2), 0.103)  # (its own triangulation: crossings never land on the outer's edges)
    Vu = under["V"].copy()
    far = (Vu[:, 2] < -0.07) & (Vu[:, 0] > 0.03)  # pokes out through the outer shell, 12+ cm from its opening
    near = (Vu[:, 2] > 0.035) & (Vu[:, 2] < 0.045) & (Vu[:, 0] > 0.05)  # crosses it just inside the opening
    Vu[far | near] *= 1.1
    under["V"] = Vu
    outer = dict(_shell(V, F, 0.108, zmax=0.05), body=body)
    keep = (Vu[:, 2] < -0.07) & (Vu[:, 0] < -0.05)  # (a "collar" deep under the outer shell: never cut)
    h, info = cloth_layers.cut(under, outer, keep=keep, n_ring=6, px=0.004)
    Fu = under["mesh"]["F"]
    z = Vu[Fu].mean(1)[:, 2]
    assert not h[z > 0.06].any(), info  # seen through the opening
    from scipy.spatial import cKDTree
    away_ = cKDTree(Vu[far | keep]).query(Vu[Fu].mean(1))[0] > 0.05  # (what pokes out shows, and a few rings round it)
    assert h[(z < -0.06) & away_].mean() > 0.95, info  # hidden from every direction (looking straight down the
    # 5 mm gap between body and outer shell sees the under one to the equator: grown 3 rings that is z -0.05)
    assert h[far[Fu].all(1)].all() and info["crossing_cut_vertices"] > 0, info  # crossing far from the opening: cut
    assert not h[near[Fu].all(1)].any(), info  # crossing where it shows: kept
    assert not h[keep[Fu].all(1)].any(), info  # never cut


def test_tuck_lays_under_the_made_parts_not_the_pieces_they_replace():
    # the outer garment's band z 0..0.05 is "collar", simulated at r 0.108 but drawn as a made part at r 0.115; under
    # cloth at r 0.110 there lies 5 mm under what is drawn: it stays (laid under the hidden simulated piece it moved in)
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    Vi, Fi = _sphere(seed=2)
    under = _shell(Vi, Fi, 0.110)
    outer = dict(_shell(V, F, 0.108, zmax=0.05), body=body)
    Vo = outer["V"]
    outer["mesh"]["piece"] = np.where(Vo[:, 2] >= 0.0, 1, 0)
    outer["mesh"]["names"] = ["front", "collar"]
    band = F[((Vo[F][:, :, 2] >= -0.004) & (Vo[F][:, :, 2] < 0.05)).all(1)]
    made = {"parts": [{"name": "collar", "V": Vo / 0.108 * 0.115, "F": band, "thickness": 0.002, "replaces": ["collar"]}]}
    zu = under["V"][:, 2]
    mid = (zu > 0.012) & (zu < 0.035)  # (under the band, clear of its edges)
    Vn, _ = cloth_layers.tucked(under, outer)
    Vm, _ = cloth_layers.tucked(under, dict(outer, made=made))
    mv_n = np.linalg.norm(Vn - under["V"], axis=1)[mid]
    mv_m = np.linalg.norm(Vm - under["V"], axis=1)[mid]
    assert np.median(mv_n) > 0.004 and np.median(mv_m) < 0.001, (np.median(mv_n), np.median(mv_m))


def test_support_kinds_are_checked():
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    assert cloth.supports(body, None) is None and cloth.supports(body, ["shoulder_pad"]) is None  # no shoulders: none


def test_layer_crossing_verts():
    # an outer shell over an inner one: nothing crosses; one outer vertex pushed inside the inner shell crosses
    V, F = _sphere()
    Vi, Fi = _sphere(seed=2)  # its own triangulation (crossings never land on shared edges)
    outer = V * 1.05
    assert not cloth._layer_crossing_verts(outer, F, Vi, Fi).any()
    outer2 = outer.copy()
    k = int(np.argmax(V[:, 2]))
    outer2[k] *= 0.9
    got = cloth._layer_crossing_verts(outer2, F, Vi, Fi)
    assert got[k] and got.sum() < 12, got.sum()


def test_under_neckline_is_the_neck_pieces_sewn_edge():
    # a stand (wrap "neck") 400 mm along its neck edge, sewn to a torso piece; a garment over it is drafted to go round
    # that collar, not the bare neck (over_measures)
    n = 21
    x = np.linspace(-0.2, 0.2, n)
    uv = np.r_[np.c_[x, np.zeros(n)], np.c_[x, np.full(n, 0.03)], np.c_[x, np.zeros(n)]]
    piece = np.r_[np.zeros(2 * n, int), np.ones(n, int)]  # 0 the stand (two rows), 1 the shirt's body
    sew = np.c_[np.arange(n), 2 * n + np.arange(n)]
    res = {"mesh": {"names": ["stand", "front"], "piece": piece, "uv": uv, "sew": sew},
           "pieces": {"pieces": {"stand": {"wrap": {"to": "neck"}}, "front": {"wrap": {}}}}}
    assert abs(cloth.under_neckline(res) - 400.0) < 1e-6
    res["pieces"]["pieces"]["stand"]["wrap"] = {}  # no neck piece: nothing to go round
    assert cloth.under_neckline(res) == 0.0


def test_under_garment_shown_finished_and_tucked_only_where_covered():
    """cloth_layers.tucked: what the outer garment covers is laid under its inner face; what shows in its opening
    stays exactly the finished surface (the user: "where the placket?": drawn pressed, the shirt's visible front had
    no band and no buttons)."""
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    under = _shell(V, F, 0.103)
    # the under garment blouses THROUGH the outer one on one side (a shirt sleeve through a jacket's)
    bulge = under["V"][:, 0] > 0.06
    under["V"] = np.where(bulge[:, None], under["V"] * (0.112 / 0.103), under["V"])
    outer = dict(_shell(V, F, 0.108, zmax=0.05), body=body)  # open above z = 0.05
    Vt, cov = cloth_layers.tucked(under, outer)
    r = np.linalg.norm(Vt, axis=1)
    z = under["V"][:, 2]
    low = z < 0.02
    assert (r[low] < 0.108 - 0.002).all(), r[low].max()  # under the outer cloth everywhere it covers
    assert cov[low].mean() > 0.97
    top = (z > 0.092) & ~bulge  # (past the feather: TUCK_FEATHER rings of ~9 mm beside the outer cloth's edge follow it)
    # the opening: as finished (to 1 um: the 5-ring feather's geometric fall leaves ~0.1 um this far out)
    assert np.abs(Vt[top] - under["V"][top]).max() < 1e-6 and not cov[top].any()
    assert (bulge & low).sum() > 20 and (np.linalg.norm(under['V'], axis=1)[bulge & low] > 0.108).all()  # (it did poke through)
    # a rigid group (a made piece) moves by one vector: its shape is kept
    rigid = np.where((z < -0.06), 0, -1)
    Vr, _ = cloth_layers.tucked(under, outer, rigid=rigid)
    d = (Vr - under["V"])[rigid == 0]
    assert np.abs(d - d.mean(0)).max() < 1e-9


def test_button_colour_by_kind():
    g = {"color": "#404040", "design": {"kind": "jacket"}}
    kd = cloth._kb()["kinds"]["jacket"]["closure"]
    assert kd["size"] >= 0.018 and kd["button"]["tone"] < 1 and kd["button"]["roughness"] > 0.5
    assert cloth.button_color(g, {"color": None, "tone": kd["button"]["tone"]}) == "#232323"
    assert cloth.button_color(g, {"color": "#112233", "tone": 0.5}) == "#112233"  # the closure's own colour wins
    assert cloth.button_color({"color": "#ffffff"}, {"color": None, "tone": None}) == "#ebe6dc"  # a shirt's pearl


def test_tuck_leaves_what_shows_bit_identical():
    """cloth_layers.tucked (keep_shown, the default): every vertex not covered by the outer garment is EXACTLY the
    finished under garment's (no feather onto visible cloth); covered ones are laid under; keep_shown=False feathers."""
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    under = _shell(V, F, 0.103)
    outer = dict(_shell(V, F, 0.102, zmax=0.05), body=body)  # (the outer cloth INSIDE the under one: everything moves)
    Vt, cov = cloth_layers.tucked(under, outer)
    assert cov.any() and (~cov).any()
    assert np.array_equal(Vt[~cov], under["V"][~cov])  # bit-identical where it shows
    assert (np.linalg.norm(Vt[cov] - under["V"][cov], axis=1) > 1e-4).all()
    Vf, cov_f = cloth_layers.tucked(under, outer, keep_shown=False)
    assert np.abs(Vf[~cov_f] - under["V"][~cov_f]).max() > 1e-4  # (the old feather moves uncovered cloth)


def test_tuck_never_lays_the_under_garment_into_the_body():
    """cloth_layers.tucked: where the outer cloth lies ON the skin (a jacket's forepart pressed onto the chest under a
    rolled lapel), the under garment is laid on the skin, never through it (Garrett's right chest, cloth12: shirt moved
    38 mm into the body, the skin drew over it in the production cut); `hold` vertices never move."""
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    under = _shell(V, F, 0.104)
    outer = dict(_shell(V, F, 0.1005, zmax=0.05), body=body)  # (on the skin: `gap` under it is inside the body)
    Vt, cov = cloth_layers.tucked(under, outer)
    assert cov.sum() > 100
    moved = np.linalg.norm(Vt - under["V"], axis=1) > 1e-6
    assert moved.sum() > 100
    assert body.clearance(Vt[moved]).min() >= cloth_layers.TUCK_BODY - 1e-4, body.clearance(Vt[moved]).min()
    hold = under["V"][:, 2] < -0.05
    Vh, cov_h = cloth_layers.tucked(under, outer, hold=hold)
    assert np.array_equal(Vh[hold], under["V"][hold]) and not cov_h[hold].any()
    assert np.linalg.norm(Vh[~hold] - under["V"][~hold], axis=1).max() > 1e-3


def test_occluded_by_a_shell_from_every_side():
    """cloth_layers.occluded / view_dirs: a point inside a closed shell is hidden from every direction; one outside
    it is not; gaps + front_only see only the shell's outer side."""
    V, F = _sphere()
    sh = _shell(V, F, 0.108)
    Fo = np.asarray(sh["mesh"]["F"])
    a = (sh["V"][Fo[:, 1]] - sh["V"][Fo[:, 0]])
    if (np.cross(a, sh["V"][Fo[:, 2]] - sh["V"][Fo[:, 0]]) * sh["V"][Fo].mean(1)).sum() < 0:
        Fo = Fo[:, ::-1]
    P = np.array([[0.0, 0.0, 0.05], [0.0, -0.13, 0.0], [0.0, -0.110, 0.0]])
    dirs = cloth_layers.view_dirs(8)
    oc = cloth_layers.occluded(P, sh["V"], Fo, dirs, px=0.002)
    assert oc[:, 0].all()  # inside: hidden from all
    assert not oc[:, 1].all() and not oc[:, 2].all()  # outside: seen from somewhere
    gp = cloth_layers.occluded(P, sh["V"], Fo, np.array([[0.0, 1.0, 0.0]]), px=0.002, gaps=True, front_only=True)
    assert 0.0005 < gp[0, 2] < 0.004  # 2 mm in front of the shell's near (outer) side, looking +y


def test_worn_together_lays_under_every_garment_above():
    """cloth.worn_together is transitive: a garment is laid under EVERY garment over it in the `over` chain, not just
    the next one. A garment is simulated over the one directly under it only (model_body), so cloth further down is
    not in its collider (dt_tess b01: the coat, over the sweater, hung over the thighs where only the jeans are; the
    drawn jeans came out through its lower fronts at 437-450 vertices, up to +23 mm). Drawn: 0 crossings with
    every garment above."""
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})

    def res(sh):
        n_ = len(sh["V"])
        return dict(sh, body=body, pieces={"interfaced": []}, mesh=dict(sh["mesh"], names=["p"], piece=np.zeros(n_, np.int64),
                                                        uv=np.zeros((n_, 2))))
    Vj, Fj_ = _sphere(seed=2)  # (its own triangulation: on the same one every crossing lies on a shared edge)
    jeans = res(_shell(Vj, Fj_, 0.104))
    # the jeans stand out at the bottom, where only the coat is over them (its collider never had them)
    lowj = jeans["V"][:, 2] < -0.04
    jeans["V"] = np.where(lowj[:, None], jeans["V"] * (0.111 / 0.104), jeans["V"])
    sweater = res(_shell(V, F, 0.106))
    sweater["mesh"]["F"] = sweater["mesh"]["F"][(sweater["V"][sweater["mesh"]["F"]][:, :, 2] > 0.0).all(1)]
    coat = res(_shell(V, F, 0.109, zmax=0.06))
    items = [("jeans", {}, jeans), ("sweater", {"over": "jeans"}, sweater), ("coat", {"over": "sweater"}, coat)]
    J0, Fj = jeans["V"], np.asarray(jeans["mesh"]["F"])
    Vc, Fc = coat["V"], np.asarray(coat["mesh"]["F"])
    assert cloth._layer_crossing_verts(J0, Fj, Vc, Fc).sum() > 5  # (it did come through the coat)
    assert (np.linalg.norm(J0, axis=1) > 0.109).sum() > 50
    out = {gn: r for gn, _, r in cloth.worn_together(items)}
    Jd = np.asarray(out["jeans"]["V"])
    assert cloth._layer_crossing_verts(Jd, Fj, Vc, Fc).sum() == 0
    Sd = np.asarray(out["sweater"]["V"])
    assert cloth._layer_crossing_verts(Jd, Fj, Sd, np.asarray(sweater["mesh"]["F"])).sum() == 0
    assert out["jeans"]["covered"][lowj].mean() > 0.9
    assert (np.linalg.norm(Jd[lowj & (J0[:, 2] < -0.05)], axis=1) < 0.109).all()  # under the coat's cloth


def test_seal_under_closes_rims_not_seams():
    """seal_under (dress-tess s18): an open tube 12 mm off a body cylinder, cut by a seam down its side: its two rims
    are sealed to the body by strips that stay between the tube and the body; the seam's split edges are not."""
    import numpy as np
    from hifipushie import cloth
    na, nz, R, r = 48, 10, 0.112, 0.1
    th = np.linspace(0, 2 * np.pi, na + 1)  # (last column = the first, as a split seam: na + 1 columns)
    z = np.linspace(0.8, 0.95, nz)
    U = np.array([[R * np.cos(t), R * np.sin(t), zz] for zz in z for t in th])
    F = []
    for i in range(nz - 1):
        for j in range(na):
            a, b, c, d = i * (na + 1) + j, i * (na + 1) + j + 1, (i + 1) * (na + 1) + j, (i + 1) * (na + 1) + j + 1
            F += [[a, b, d], [a, d, c]]
    tb, zb = np.linspace(0, 2 * np.pi, 200, endpoint=False), np.linspace(0.6, 1.2, 120)
    BV = np.array([[r * np.cos(t), r * np.sin(t), zz] for zz in zb for t in tb])
    S, FS = cloth.seal_rims(U, np.array(F), BV, True)
    assert len(S) == 2 * (na + 1), len(S)  # (both rims whole, the seam's two ends included: no hole at the seam)
    rs = np.hypot(S[:, 0], S[:, 1])
    assert np.all(rs < R - 0.005) and np.all(rs > r), (rs.min(), rs.max())  # between the tube and the body
    assert np.all(S[:, 2] >= U[:, 2].min() - 1e-9) and np.all(S[:, 2] <= U[:, 2].max() + 0.01)
    assert len(FS) == 2 * 2 * na, len(FS)  # (the seam's split edges: none)
    S0, _ = cloth.seal_rims(U, np.array(F), BV, 0.005)  # a gap wider than the reach: nothing sealed
    assert len(S0) == 0


def test_under_fit_rows_judged_on_what_shows():
    """C85 visible scope (fit round 24): an under garment standing 20 mm off the body at the waist FAILs its own
    under_standoff_waist; under an outer garment that covers the waist band the band is culled and the re-judged row
    PASSes (nothing of it is drawn); with the outer garment open over the band it still FAILs, on the visible cloth."""
    from hifipushie import cloth_check as cc
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    under = _shell(V, F, 0.120)
    alone = cc.standoff_row(body, under["V"], 0.0)
    assert alone["status"] == "FAIL" and alone["ours"] > 15, alone
    covered = dict(_shell(V, F, 0.128, zmax=0.06))
    rows, hid = cc.visible_fit_rows(body, under, covered, z=0.0)
    assert rows[0]["status"] == "PASS" and rows[0]["n"] == 0 and hid.any(), rows
    low = dict(_shell(V, F, 0.128, zmax=-0.06))  # the outer garment ends below the waist band: the band shows
    rows, _ = cc.visible_fit_rows(body, under, low, z=0.0)
    assert rows[0]["status"] == "FAIL" and rows[0]["n"] > 20 and rows[0]["ours"] > 15, rows
    assert "under_standoff_waist" in cc.VISIBLE_SCOPED


def _grid_garment(nx=12, ny=8, h=0.01):
    """Two pieces side by side (a: x < 0, b: x > 0), each a grid, sewn along x = 0 (duplicate seam vertices)."""
    uvs, F, piece = [], [], []
    for k, x0 in enumerate((-nx * h, 0.0)):
        base = len(uvs)
        for j in range(ny + 1):
            for i in range(nx + 1):
                uvs.append((x0 + i * h, j * h))
                piece.append(k)
        for j in range(ny):
            for i in range(nx):
                a = base + j * (nx + 1) + i
                F += [(a, a + 1, a + nx + 2), (a, a + nx + 2, a + nx + 1)]
    uv = np.array(uvs)
    piece = np.array(piece)
    sa = [j * (nx + 1) + nx for j in range(ny + 1)]  # a's right edge
    sb = [(ny + 1) * (nx + 1) + j * (nx + 1) for j in range(ny + 1)]  # b's left edge
    M = {"uv": uv, "piece": piece, "names": ["a", "b"], "F": np.array(F), "sew": np.array(list(zip(sa, sb))),
         "sew_seam": np.zeros(len(sa), int), "stitch": np.zeros((0, 2), int), "border": np.zeros(len(uv), bool),
         "points": {"a:corner": 0, "b:far": int(len(uv) - 1)}, "marks": {}, "closures": [],
         "folds": [{"piece": "b", "name": "crease", "rows": [np.array(sb)], "_g": {}}], "made": ["b"]}
    return M


def test_seen_part_cuts_the_hidden_cloth_and_its_strain_out_of_the_start():
    """KAT (shirt round 5, C115): the seen part of an under garment (seen_part / subset_mesh) keeps only the cloth that
    shows, every index field remapped (seams, points, folds), its cut edge returned (to be pinned); a strain planted
    in the HIDDEN cloth leaves the start check, one planted in the SEEN cloth stays (the preflight isn't loosened)."""
    from hifipushie import cloth_job
    M = _grid_garment()
    X = np.c_[M["uv"], np.zeros(len(M["uv"]))]
    F = M["F"]
    fa = M["piece"][F[:, 0]] == 0
    hid = fa & (X[F, 0].mean(1) < -0.06)  # piece a's far half is hidden (under an outer garment)
    X2 = X.copy()
    far = X[:, 0] < -0.085
    X2[far, 0] = -0.085 + (X[far, 0] + 0.085) * 1.4  # hidden cloth stretched 40 % (a yoke strained by the fit)
    M2, V2, info = cloth_layers.seen_part({"V": X2, "mesh": M}, hid=hid, whole=())
    assert info["kept"] == int((~hid).sum()) and len(V2) == len(M2["uv"]) == len(info["old"])
    # seams, points, folds remapped onto the same positions
    assert len(M2["sew"]) == len(M["sew"]) and np.allclose(V2[M2["sew"][:, 0]], X2[M["sew"][:, 0]])
    assert "a:corner" not in M2["points"] and np.allclose(V2[M2["points"]["b:far"]], X2[M["points"]["b:far"]])
    assert len(M2["folds"]) == 1 and "_g" not in M2["folds"][0] and len(M2["folds"][0]["rows"][0]) == 9
    # the cut edge: the kept vertices on a dropped triangle, all at the cut line x = -0.06
    assert info["cut_vertices"] == 9 and np.allclose(V2[info["cut"], 0], -0.06)

    def start(Xs, Ms):
        arr = {"X": Xs, "F": Ms["F"], "piece": Ms["piece"], "uv": Ms["uv"]}
        return cloth_job.start_strain_check(arr, {"rest": "flat", "pieces": Ms["names"]})
    whole = start(X2, M)
    seen = start(V2, M2)
    assert whole["over"] > 0 and not whole["ok"], whole
    assert seen["over"] == 0 and seen["ok"], seen
    X3 = X2.copy()  # the same stretch planted in SEEN cloth (piece b) is still counted
    nb = X[:, 0] > 0.08
    X3[nb, 0] = 0.08 + (X[nb, 0] - 0.08) * 1.4
    M3, V3, _ = cloth_layers.seen_part({"V": X3, "mesh": M}, hid=hid, whole=())
    s3 = start(V3, M3)
    assert s3["over"] > 0 and not s3["ok"], s3
    # a made piece kept whole once any of it shows, and the cloth within the margin of it
    hid_b = ~fa & (X[F, 0].mean(1) > 0.02)
    _, _, ib = cloth_layers.seen_part({"V": X, "mesh": M}, hid=hid_b, whole=("b",), whole_margin=0.015)
    assert ib["kept_by_piece"]["b"] == int((~fa).sum()) and ib["kept"] == len(F), ib["kept_by_piece"]




def _collar_scene():
    """A body (sphere), an outer shell open above z = 0.05 (a jacket at its neck), an under shell (a shirt) open above
    z = 0.09 whose top band is a made piece "collar" standing in view above the outer's opening and lying 2-4 mm OVER
    the outer's rim (as a shirt collar lies on a jacket collar)."""
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    Vu, Fu = _sphere(seed=2)
    u = Vu / np.linalg.norm(Vu, axis=1, keepdims=True)
    r = np.full(len(u), 0.103)
    zc = u[:, 2] * 0.103
    ramp = np.clip((zc - 0.035) / 0.012, 0, 1)
    r = r + ramp * 0.0085  # 0.103 -> 0.1115: 3.5 mm outside the outer shell (0.108) from z ~0.047 up
    Vu = u * r[:, None]
    Fu = Fu[(Vu[Fu][:, :, 2] < 0.09).all(1)]
    collar = Vu[Fu].mean(1)[:, 2] > 0.035
    piece = np.zeros(len(Vu), np.int64)
    piece[np.unique(Fu[collar])] = 1
    collar = (piece[Fu] == 1).all(1)
    under = {"V": Vu, "mesh": {"F": Fu, "sew": np.zeros((0, 2), np.int64), "border": np.zeros(len(Vu), bool),
                               "piece": piece, "names": ["body", "collar"], "made": ["collar"]}}
    outer = dict(_shell(V, F, 0.108, zmax=0.05), body=body)
    return under, outer, collar


def test_cull_keeps_a_seen_collar_whole_and_culls_a_covered_back():
    """Fit round 28 (Joe on r27sc: the cull "thrashed the shirt"): a shirt collar standing in view above a jacket collar
    stays WHOLE; a back panel under the jacket is culled; the old distance + pierce rule removed seen collar."""
    under, outer, collar = _collar_scene()
    info = {}
    h = cloth_layers.hidden(under, outer, info=info)
    c = under["V"][under["mesh"]["F"]].mean(1)
    back = (c[:, 1] > 0.05) & (c[:, 2] < 0.0)
    assert not h[collar].any(), int(h[collar].sum())
    assert h[back].mean() > 0.9, h[back].mean()
    # the old rule, with the outer's rim a TURNED edge (a jacket collar's fall: no free border, so no opening margin):
    # it cut seen collar cloth lying over the rim (the 15 mm pierce allowance) and left the rest as fragments
    turned = dict(outer, mesh=dict(outer["mesh"], border=np.zeros(len(outer["V"]), bool)))
    old = cloth_layers.hidden(under, turned, margin=0.03, pierce=cloth_layers.PIERCE_CULL, rule="margin")
    assert old[collar].any() and not old[collar].all()
    assert not cloth_layers.hidden(under, turned)[collar].any()
    # no stranded islands: every seen region is big (no fragment of < ISLAND_FACES triangles in hidden cloth)
    lab = cloth_layers._face_components(np.asarray(under["mesh"]["F"]), ~h)
    assert np.bincount(lab[lab >= 0]).min() >= cloth_layers.ISLAND_FACES or len(np.unique(lab[lab >= 0])) == 1
    assert info["hidden_faces"] == int(h.sum()) and info["directions"] >= 7 * 9 - 9


def test_cull_never_hides_cloth_a_judged_view_sees():
    """Every under triangle with a corner seen in a judged view (the outer and body not in front of it) is kept."""
    under, outer, _ = _collar_scene()
    h = cloth_layers.hidden(under, outer)
    Vo, Fo = outer["V"], np.asarray(outer["mesh"]["F"])
    b = outer["body"]
    occ = cloth_layers.occluded(under["V"], np.r_[Vo, b.V], np.r_[Fo, np.asarray(b.T) + len(Vo)],
                                cloth_layers.judged_dirs(), tol=cloth_layers.HIDE_TOL)
    seen_v = ~occ.all(0)
    assert not h[seen_v[np.asarray(under["mesh"]["F"])].any(1)].any()


def test_zbuffer_matches_the_per_face_loop():
    V, F = _sphere()
    P = np.random.default_rng(3).normal(size=(300, 3)) * 0.06
    dirs = cloth_layers.view_dirs(6, (0.0, 30.0))
    g = cloth_layers.occluded(P, V, F, dirs, gaps=True)
    # reference: the per-face loop it replaced, on one direction
    d = dirs[1] / np.linalg.norm(dirs[1])
    a = np.cross(d, [0.0, 0.0, 1.0]); a /= np.linalg.norm(a); b = np.cross(d, a)
    uv = np.c_[V @ a, V @ b] / 0.002
    lo = np.floor(uv.min(0)).astype(int) - 1
    W, H = (np.ceil(uv.max(0)).astype(int) - lo + 2)
    Z = np.full((W, H), np.inf)
    T, Dz = uv[F] - lo, (V @ d)[F]
    for f in range(len(F)):
        xs = np.arange(int(np.floor(T[f, :, 0].min())), int(np.ceil(T[f, :, 0].max())) + 1)
        ys = np.arange(int(np.floor(T[f, :, 1].min())), int(np.ceil(T[f, :, 1].max())) + 1)
        gx, gy = np.meshgrid(xs + 0.5, ys + 0.5, indexing="ij")
        (x0, y0), (x1, y1), (x2, y2) = T[f]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
        l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
        ins = (l0 >= -0.02) & (l1 >= -0.02) & (1 - l0 - l1 >= -0.02)
        z = l0 * Dz[f, 0] + l1 * Dz[f, 1] + (1 - l0 - l1) * Dz[f, 2]
        sub = Z[xs[0]:xs[-1] + 1, ys[0]:ys[-1] + 1]
        np.minimum(sub, np.where(ins, z, np.inf), out=sub)
    q = (np.c_[P @ a, P @ b] / 0.002 - lo).astype(int)
    ok = (q[:, 0] >= 0) & (q[:, 0] < W) & (q[:, 1] >= 0) & (q[:, 1] < H)
    ref = np.full(len(P), np.inf)
    ref[ok] = Z[q[ok, 0], q[ok, 1]] - (P @ d)[ok]
    fin = np.isfinite(ref)
    assert np.array_equal(fin, np.isfinite(g[1])) and np.allclose(ref[fin], g[1][fin])


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)


def test_form_fit_under_layer_needs_no_sim(monkeypatch):
    """The muslin fit's layered path (C168): model_body given the under garment's FORM fit (pattern_form.on_form's
    under_as_worn result) layers on it as given: no sim built or looked up, no pinned result, no "under_missing"
    (before: on_form refused gc_garrett's jacket until the shirt was simulated)."""
    def no_sim(*a, **k):
        raise AssertionError("an under garment's sim was built / looked up for a form fit")
    monkeypatch.setattr(cloth, "build", no_sim)
    monkeypatch.setattr(cloth, "under_pinned", no_sim)
    monkeypatch.setattr(cloth, "body_mesh", lambda spec=None: {"V": np.zeros((3, 3)), "F": [[0, 1, 2]], "J": {}, "key": "b"})
    spec = {"base": {"kind": "test"}, "cloth": {"shirt": {}, "jacket": {"over": "shirt", "under": {"pin": "pin:x"}}}}
    form = {"V": np.ones((3, 3)), "mesh": {"F": np.array([[0, 1, 2]])}, "key": "form:shirt:abc"}
    src = cloth.model_body("m", spec, spec["cloth"]["jacket"], simulate=False, under=form)
    assert "under_missing" not in src and src["under"]["res"] is form and src["under"]["key"] == "form:shirt:abc"
    assert np.allclose(src["under"]["V"], form["V"]) and src["under"]["name"] == "shirt"
    with __import__("pytest").raises(AssertionError, match="sim was built"):  # (without it, the sim path as before)
        cloth.model_body("m", spec, spec["cloth"]["jacket"], simulate=False)
