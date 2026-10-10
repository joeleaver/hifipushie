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
    h = cloth_layers.hidden(under, outer, margin=0.02)
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


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
