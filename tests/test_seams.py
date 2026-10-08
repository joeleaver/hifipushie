"""Seams that read as on real clothes: a fine line, not a welt (the user on the suits, 2026-10-07: "ours look huge
and structural"). Three causes, each tested here: pieces wound opposite ways (piece_flips), a solver's stitch a free
hinge leaving a crease along every seam (_seam_press), and maps drawing a deep wide groove beside allowance ridges
(seam finishes)."""
import numpy as np

from hifipushie import cloth


def _two(h=0.01):
    g = {"pieces": {"a": {"rect": [0.4, 0.1], "wrap": {"to": "flat", "at": [0, 0, 1.0]}},
                    "b": {"rect": [0.4, 0.1], "wrap": {"to": "flat", "at": [0, 0, 1.0]}}},
         "seams": [["a:nw>n>ne", "b:sw>s>se"]]}
    Bp = cloth.pieces(g, {})
    M = cloth.mesh(Bp, h)
    uv, pid = M["uv"], M["piece"]
    V = np.c_[uv, np.zeros(len(uv))]
    ia, ib = (pid == M["names"].index(n) for n in "ab")
    # the seam on y = 0: a below, b above
    V[ia, 1] -= V[M["sew"][:, 0], 1].mean()
    V[ib, 1] -= V[M["sew"][:, 1], 1].mean()
    return g, M, V, ia, ib


class _Body:
    def __init__(self, V):
        self.V = V


def _side_angle(M, V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True)
    sw = M["sew"]
    return np.degrees(np.arccos(np.clip(np.sum(vn[sw[:, 0]] * vn[sw[:, 1]], 1), -1, 1)))


def test_pieces_wound_alike_facing_out():
    g, M, V, ia, ib = _two()
    M = dict(M, F=M["F"].copy())
    pf = M["piece"][M["F"][:, 0]]
    fb = pf == M["names"].index("b")
    M["F"][fb] = M["F"][fb][:, [0, 2, 1]]  # b wound the other way, as a mirrored or turned piece comes out
    body = _Body(np.c_[np.random.default_rng(0).uniform(-0.2, 0.6, (400, 2)), np.full(400, -0.05)])
    F = cloth.oriented_faces(M, V, body=body)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    assert (fn[:, 2] > 0).all()  # one surface, facing away from the body
    Fw = cloth.welded_faces(M, V, body=body)
    fw = np.cross(V[Fw[:, 1]] - V[Fw[:, 0]], V[Fw[:, 2]] - V[Fw[:, 0]])
    assert (fw[:, 2] > 0).all()
    n = cloth.shared_normals(M, V, F)
    sw = M["sew"]
    assert np.allclose(n[sw[:, 0]], n[sw[:, 1]]) and (n[:, 2] > 0.99).all()


def test_seam_pressed_smooth_across():
    # a solver's stitch passes no bending: each side's last rows tilt and the welded seam stands as a crease (20-45
    # deg across the blazer's seams). Pressed, the cloth runs across it.
    g, M, V, ia, ib = _two()
    V[:, 2] = -np.tan(np.radians(18)) * np.abs(V[:, 1]) * (np.abs(V[:, 1]) < 0.03)  # a ridge 3 cm either side
    V[:, 2] += np.where(np.abs(V[:, 1]) >= 0.03, -np.tan(np.radians(18)) * 0.03, 0)
    before = _side_angle(M, V, M["F"])
    assert np.median(before) > 25, np.median(before)
    W, info = cloth.cleanup(V, M, None, {"smooth": 0, "clear": 0})
    sw = M["sew"]
    assert np.linalg.norm(W[sw[:, 0]] - W[sw[:, 1]], axis=1).max() < 1e-9  # still welded
    after = _side_angle(M, W, M["F"])
    assert np.median(after) < 0.35 * np.median(before), (np.median(before), np.median(after))
    assert info["press"]["seams"] == 1
    assert np.abs(W - V).max() <= 0.4 * 0.01 + 1e-9  # capped
    # a seam not pressed (a welt) and interfaced cloth stay as they were
    K, _ = cloth.cleanup(V, M, None, {"smooth": 0, "clear": 0, "pressed": np.zeros(len(sw), bool)})
    Wp, _ = cloth.cleanup(V, M, None, {"smooth": 0, "clear": 0, "press": False})
    assert np.allclose(K, Wp)
    S, _ = cloth.cleanup(V, M, None, {"smooth": 0, "clear": 0}, stiff=ib.astype(float))
    assert np.allclose(S[ib], Wp[ib])


def test_seam_finish_in_the_maps_is_a_fine_line():
    g, M, V, ia, ib = _two()
    uv, side = cloth.atlas_uv(M)
    seam_len = 0.4

    def line(finish):
        gg = dict(g, detail={"seam_finish": finish, "hem": 0, "topstitch": 0, "texture": 1024})
        dm = cloth.detail_maps(M, uv, side, gg)
        H = dm["height"]
        mpt = side / 1024
        deep = -H.min()
        width = (H < -0.5 * deep).sum() * mpt ** 2 / seam_len  # the groove's full width at half depth
        return deep, width, dm
    d, w, dm = line("pressed_open")
    assert d <= 0.00035 and w < 0.003, (d, w)
    assert dm["thread"].max() == 0  # no stitching shows on a seam pressed open
    assert dm["cavity"].min() > 0.9  # hardly darkened
    dw, ww, _ = line("welt")
    assert dw > 3 * d and ww > w
    _, _, df = line("felled")
    assert df["thread"].max() > 0.5  # two rows on one side
    assert cloth.seam_kinds(M, dict(g, detail={"seam_finishes": {"a/b": "welt"}})) == {0: "welt"}
    assert cloth.seam_kinds(M, {"design": {"kind": "shirt"}, **g})[0] == "felled"


def test_export_shares_normals_across_seams(tmp_path=None):
    import tempfile
    from pathlib import Path
    g, M, V, ia, ib = _two()
    M = dict(M, F=M["F"].copy())
    pf = M["piece"][M["F"][:, 0]]
    fb = pf == M["names"].index("b")
    M["F"][fb] = M["F"][fb][:, [0, 2, 1]]
    V[:, 2] = 0.02 * np.cos(V[:, 0] * 6)  # a gentle wave: normals that differ along the cloth
    body = _Body(np.c_[np.random.default_rng(0).uniform(-0.2, 0.6, (400, 2)), np.full(400, -0.05)])
    res = {"mesh": M, "V": V, "body": body}
    old = cloth.garments
    cloth.garments = lambda *a, **k: [("sheet", dict(g, detail={"texture": 256}), res)]
    try:
        out = Path(tmp_path or tempfile.mkdtemp())
        parts = cloth.export_part("x", {}, out, texture=256, log=lambda *a: None)
    finally:
        cloth.garments = old
    p = parts[0][1]
    cv, n = p["corner_vert"], p["normal"]
    nv = len(V)
    outer = cv < nv
    assert (n[outer][:, 2] > 0.9).all()  # every piece faces out
    sw = M["sew"]
    for a, b in sw:  # a seam's two sides: one normal
        na, nb = n[cv == a], n[cv == b]
        if len(na) and len(nb):
            assert np.allclose(na[0], nb[0], atol=1e-5)


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
