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


def _along(P, q):
    """A point's arc length along a polyline."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    ab = P[1:] - P[:-1]
    t = np.clip(np.sum((q - P[:-1]) * ab, 1) / seg ** 2, 0, 1)
    i = int(np.argmin(np.linalg.norm(P[:-1] + t[:, None] * ab - q, axis=1)))
    return float(seg[:i].sum() + t[i] * seg[i])


def test_fold_ending_on_a_seam_keeps_the_seam_paired():
    # a fold line (and a roll's further rows) ending on a sewn edge: both sides of the seam get a sample there. The
    # row's end used to move the outline's nearest vertex along the seam on its own side: pairs up to 13-16 mm apart
    # along the seam (a jacket's gorge beside the roll line never closed)
    for h in (0.02, 0.01):
        for kind in ("press", "roll"):
            f = {"piece": "a", "line": [[-0.113, -0.06], [0.0537, 0.06]], "angle": 0, "name": "f", "flap": "nw",
                 "kind": kind, **({"radius": 0.004} if kind == "roll" else {})}
            g = {"pieces": {"a": {"rect": [0.3, 0.12], "wrap": {"to": "flat", "at": [0, 0, 1.0]}},
                            "b": {"rect": [0.33, 0.1], "wrap": {"to": "flat", "at": [0, 0.2, 1.0]}},  # (10% ease)
                            "c": {"rect": [0.3, 0.1], "wrap": {"to": "flat", "at": [0, 0.4, 1.0]}}},
                 "seams": [["a:nw>n>ne", "b:sw>s>se"], ["b:nw>n>ne", "c:sw>s>se"]], "folds": [f]}
            Bp = cloth.pieces(g, {})
            M = cloth.mesh(Bp, h)
            pcs, uv = Bp["pieces"], M["uv"]
            for si, (A, B_) in enumerate(Bp["seams"]):
                Ls = [pcs[e.split(":")[0]]["P"][cloth._edge(pcs, e)[1]] for e in (A, B_)]
                tot = [pattern.length(L) for L in Ls]
                na = M["names"].index(A.split(":")[0])
                for a, b in M["sew"][M["sew_seam"] == si]:
                    a, b = (a, b) if M["piece"][a] == na else (b, a)
                    assert abs(_along(Ls[0], uv[a]) / tot[0] - _along(Ls[1], uv[b]) / tot[1]) * max(tot) < 1e-6, (h, kind, si)
            fd = M["folds"][0]
            assert fd["missing_edges"] == 0
            ends = {int(r[-1]) for r in fd["rows"]} | {int(r[0]) for r in fd["rows"]}
            sewn = set(M["sew"].ravel().tolist())
            assert len(ends & sewn) >= 1  # the fold ends on a sewn vertex ...
            for r in fd["rows"]:  # ... which lies on the fold's line (not bent to a neighbour) or within SEAM_JOIN h
                L = folds.rows(pcs, folds.entries(Bp)[0], h)["lines"]
                d = min(np.linalg.norm(Lr[-1] - uv[r[-1]]) for Lr in L)
                d0 = min(np.linalg.norm(Lr[0] - uv[r[0]]) for Lr in L)
                assert min(d, d0) < 1.5 * cloth.SEAM_JOIN * h + 1e-9, (h, kind, d, d0)
            # no sliver edges on the seam
            E = np.r_[M["F"][:, [0, 1]], M["F"][:, [1, 2]], M["F"][:, [2, 0]]]
            assert np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1).min() > 0.1 * h, (h, kind)


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
