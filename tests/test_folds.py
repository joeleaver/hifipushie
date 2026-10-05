"""Fold lines, the pattern ops they came with (slit, trim) and the fine folds authored from a drape: geometry only,
no sim. uv run python tests/test_folds.py"""
import numpy as np

from hifipushie import cloth, cloth_detail, folds, pattern


def _strip(folds_=None, h=0.02, size=(0.3, 0.12)):
    g = {"pieces": {"strip": {"rect": list(size), "wrap": {"to": "flat", "at": [0, 0, 1.0]}}}, "folds": folds_ or []}
    Bp = cloth.pieces(g, {})
    return Bp, cloth.mesh(Bp, h)


def _edges(F):
    return {tuple(sorted(e)) for t in F for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))}


def test_fold_line_forms():
    Bp, _ = _strip()
    pcs = Bp["pieces"]
    for line in ({"mid": "x"}, ["w", "e"], [[-0.15, 0.0], [0.15, 0.0]], {"edge": "sw>s>se", "offset": 0.06},
                 {"edge": "strip:sw>s>se", "offset": 0.06}):
        L = pattern.fold_line(pcs, {"piece": "strip", "line": line})
        assert np.abs(L[:, 1]).max() < 1e-6, line
        assert abs(abs(L[0, 0]) - 0.15) < 1e-6 and abs(abs(L[-1, 0]) - 0.15) < 1e-6, (line, L[0], L[-1])
    # a drafted line that stops short of the outline runs on to it
    L = pattern.fold_line(pcs, {"piece": "strip", "line": [[-0.14, 0.0], [0.145, 0.0]]})
    assert abs(L[0, 0] + 0.15) < 1e-6 and abs(L[-1, 0] - 0.15) < 1e-6


def test_rows_are_mesh_edges():
    for h in (0.02, 0.01):
        for f in ({"piece": "strip", "line": {"mid": "x"}, "angle": 0, "name": "press"},
                  {"piece": "strip", "line": {"edge": "sw>s>se", "offset": 0.006}, "angle": 0, "kind": "roll",
                   "radius": 0.003, "name": "roll", "flap": "n"}):
            Bp, M = _strip([f], h)
            fd = M["folds"][0]
            E = _edges(M["F"])
            assert fd["missing_edges"] == 0
            for row in fd["rows"]:
                assert len(row) >= 3
                assert all(tuple(sorted((int(a), int(b)))) in E for a, b in zip(row[:-1], row[1:])), (h, f["name"])
                assert M["border"][row[0]] and M["border"][row[-1]]  # the line's ends are outline vertices
    # a roll gets rows over its arc where the mesh can carry them, one crease where it can't
    assert len(_strip([dict(f, radius=0.004)], 0.01)[1]["folds"][0]["rows"]) > 1
    assert len(_strip([dict(f, radius=0.001)], 0.02)[1]["folds"][0]["rows"]) == 1


def test_fold_is_isometric_and_measured():
    f = {"piece": "strip", "line": {"mid": "x"}, "angle": 0, "name": "f"}
    Bp, M = _strip([f])
    fd = M["folds"][0]
    flat = np.c_[M["uv"], np.zeros(len(M["uv"]))]
    ref = folds.bend_reference(M, flat)
    e0, _ = cloth.edge_strain(flat, M["uv"], M["F"])
    e1, _ = cloth.edge_strain(ref, M["uv"], M["F"])
    assert np.abs(e1 - e0).max() < 1e-9  # a straight crease is a rigid turn of the flap
    m = folds.measure(ref, M, fd)
    assert abs(m["turn_deg"] - 170.0) < 0.5, m
    # the other way: folded under
    Bp, M = _strip([dict(f, angle=360)])
    ref2 = folds.bend_reference(M, np.c_[M["uv"], np.zeros(len(M["uv"]))])
    g = folds._geom(M, M["folds"][0])
    assert ref[g["rows"][0]["v"], 2].mean() > 0 > ref2[g["rows"][0]["v"], 2].mean()
    assert folds.weights(M).max() == 1.0 and (folds.weights(M) > 0).sum() == len(M["folds"][0]["rows"][0])


def test_placed_fold_lies_on_its_base():
    f = {"piece": "strip", "line": {"mid": "x"}, "angle": 0, "name": "f"}
    Bp, M = _strip([f], h=0.01)
    body = cloth.Body({"V": np.array([[0, 0, -9.0], [1, 0, -9.0], [1, 1, -9.0], [0, 1, -9.0], [0.5, 0.5, -9.5]]),
                       "F": [[0, 1, 2, 3], [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], "J": {}})  # (far away)
    X = cloth.place(Bp, M, body, smooth=True)
    m = folds.measure(X, M, M["folds"][0])
    assert m["turn_deg"] > 170 and m["gap_mm"][0] <= 6.0, m  # one crease, a contact gap at its first ring: a wedge
    assert not cloth._piece_crossings(X, M)
    # Blender's cloth: a U as wide as its collision distances
    M2 = cloth.mesh(Bp, 0.01, cloth.FOLD_WIDTH_FITTED)
    assert len(M2["folds"][0]["rows"]) == 2
    # a constructed (never simulated) mesh: a U two cloth layers across, the flap parallel to its base
    M3 = cloth.mesh(Bp, 0.01, cloth.FOLD_WIDTH_MADE)
    m3 = folds.measure(cloth.place(Bp, M3, body, smooth=True), M3, M3["folds"][0])
    assert m3["gap_mm"][1] <= 2.2 and not cloth._piece_crossings(cloth.place(Bp, M3, body, smooth=True), M3), m3


def test_fold_must_cross_the_piece():
    try:
        _strip([{"piece": "strip", "line": [[-0.05, 0.0], [0.05, 0.0]], "angle": 0, "reach": 0.001}])
    except ValueError as e:
        assert "edge to edge" in str(e)
    else:
        raise AssertionError("a fold ending inside the piece should be refused")


def test_slit_and_trim():
    pc = pattern.from_spec("s", {"rect": [0.2, 0.3]})
    s = pattern.slit(pc, [[0.02, -0.15], [0.02, 0.0]], 0.002, "placket")
    P = s["P"]
    assert abs(abs(pattern.area(P)) - (0.06 - 0.002 * 0.147 - 0.5 * 0.002 * 0.003)) < 1e-9  # a thin strip is taken
    a, b, t = (P[s["names"][f"placket.{k}"]] for k in ("a", "b", "tip"))
    assert abs(a[0] - 0.019) < 1e-9 and abs(b[0] - 0.021) < 1e-9 and np.allclose(t, [0.02, 0.0])
    assert pattern.arc_indices(s, "placket.b>se")[0] == s["names"]["placket.b"]
    t2 = pattern.trim(pc, "se>sw", 0.05, "cb")
    assert abs(abs(pattern.area(t2["P"])) - 0.05 * 0.3) < 1e-9
    assert np.allclose(t2["P"][t2["names"]["cb.a"]], [0.05, -0.15]) and np.allclose(t2["P"][t2["names"]["cb.b"]], [0.05, 0.15])
    pcs = pattern.apply({"s": pc, "o": pattern.from_spec("o", {"rect": [0.07, 0.1]})},
                        [{"op": "trim", "piece": "s", "edge": "se>sw", "match": ["o:sw>se"], "name": "cb"}])
    assert abs(np.ptp(pcs["s"]["P"][:, 0]) - 0.07) < 1e-9


def test_fine_folds_follow_the_compression():
    Bp, M = _strip(h=0.01, size=(0.3, 0.3))
    V = np.c_[M["uv"], np.zeros(len(M["uv"]))]
    left = M["uv"][:, 0] < 0
    Vc = V.copy()
    Vc[:, 0] = np.where(left, V[:, 0] * 0.95, V[:, 0])  # the left half 5% short across x
    c, d = cloth_detail.compression(M, Vc)
    assert c[M["uv"][:, 0] < -0.03].mean() > 0.03 and c[M["uv"][:, 0] > 0.03].max() < 0.005
    assert np.abs(d[M["uv"][:, 0] < -0.03, 0]).mean() > 0.98  # along x
    uv, side = cloth.atlas_uv(M)
    H, info = cloth_detail.wrinkle_height(M, Vc, uv, side, 512)
    px = lambda q: (int(q[0] * 512), int((1 - q[1]) * 512))
    L_ = H[:, : px(uv[np.argmin(np.abs(M["uv"][:, 0]))])[0] - 20]
    R_ = H[:, px(uv[np.argmin(np.abs(M["uv"][:, 0]))])[0] + 110:]  # (dabs and the smoothed compression reach a few cm over)
    assert sum(info["dabs"]) > 0 and np.abs(L_).max() > 5e-4 and np.abs(R_).max() < 1e-4, info
    # the folds run across the compression: the height varies along x, little along y
    gy, gx = np.gradient(L_)
    assert np.abs(gx).mean() > 2.0 * np.abs(gy).mean()
    # the big folds go into the geometry, lifted off the surface, none at the outline
    D, _ = cloth_detail.fold_dabs(M, Vc)
    Vg, rms = cloth_detail.displace(M, Vc, D)
    dz = Vg[:, 2] - Vc[:, 2]
    assert D["big"].any() and dz.max() > 3e-4 and np.abs(dz[M["border"]]).max() < 1e-9 and dz.min() > -dz.max()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
