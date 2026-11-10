"""R3c2: no vertex of a chain build left unplaced. A floating layer is placed a LAYER inside its host and stiffens it; every
point of a ply is placed (also the ones sewn only to a third piece), so a piece sewn to the ply starts at its seam; a
facing starts inside its front; the START row names a point left at the origin, and a seam sewn the wrong way round."""
import types

import numpy as np
import pytest

from hifipushie import chain_holds as ch, chain_net as cn, chain_placed as cpl, chain_stages as cst
from hifipushie.chain_core import LAYER, ChainRefused

NX, NY = 7, 5


def _rect(w, h, x0, y0):
    xs, ys = np.linspace(0, w, NX), np.linspace(0, h, NY)
    uv = np.array([[x0 + x, y0 + y] for y in ys for x in xs])
    F = [[j * NX + i, j * NX + i + 1, j * NX + i + NX] for j in range(NY - 1) for i in range(NX - 1)]
    F += [[j * NX + i + 1, j * NX + i + NX + 1, j * NX + i + NX] for j in range(NY - 1) for i in range(NX - 1)]
    edges = {"bottom": list(range(NX)), "top": [(NY - 1) * NX + i for i in range(NX)],
             "left": [j * NX for j in range(NY)], "right": [j * NX + NX - 1 for j in range(NY)]}
    return uv, np.array(F), edges


def _net(pieces: dict, stiff=(), sew=(), place=None, bend=None):
    """pieces {name: (w, h, x0, y0)} on one flat; sew [(a, edge, b, edge[, "rev"])]: the edges' vertices in order."""
    uvs, Fs, ps, off, ed, k = [], [], [], {}, {}, 0
    for i, (nm, (w, h, x0, y0)) in enumerate(pieces.items()):
        uv, F, e = _rect(w, h, x0, y0)
        uvs.append(uv), Fs.append(F + k), ps.append(np.full(len(uv), i))
        off[nm], ed[nm] = k, e
        k += len(uv)
    pairs = []
    for s in sew:
        a, ea, b_, eb = s[:4]
        eb_ = ed[b_][eb][::-1] if s[4:] == ("rev",) else ed[b_][eb]
        pairs += [[off[a] + x, off[b_] + y] for x, y in zip(ed[a][ea], eb_)]
    M = {"uv": np.concatenate(uvs), "F": np.concatenate(Fs), "piece": np.concatenate(ps), "names": list(pieces),
         "sew": np.array(pairs, np.int64).reshape(-1, 2), "folds": [], "closures": [], "place": place or {}}
    st, bd = np.zeros(len(M["uv"])), np.ones(len(M["uv"]))
    for nm in stiff:
        st[M["piece"] == list(pieces).index(nm)] = 1.0
    for nm, v in (bend or {}).items():
        bd[M["piece"] == list(pieces).index(nm)] = v
    return cn.Network(M, st, bd)


def _build(net, on: str, z=1.0):
    """A build with `on` laid at its flat at height z (outside +z), every other point at the origin (not placed yet)."""
    X = np.zeros((net.n, 3))
    hv = net.verts(on)
    X[net.root[hv]] = np.c_[net.uv[hv], np.full(len(hv), z)]
    X = X[net.root]
    contact = types.SimpleNamespace(query=lambda P: (np.asarray(P)[:, 2] - z, np.tile([0.0, 0.0, 1.0], (len(P), 1))))
    return types.SimpleNamespace(net=net, X=X, reads={}, holds=ch.read(net), body=types.SimpleNamespace(contact=contact),
                                 _stiff_mask=lambda: np.isin(net.piece, [net.pid(p) for p in net.names if net.stiff[net.verts(p)].mean() > 0.95]))


PL = {"to": "torso", "side": "front"}


def test_a_floating_layer_is_placed_inside_its_host_and_stiffens_it():
    net = _net({"front.L": (0.3, 0.5, 0.0, 0.0), "canvas.L": (0.2, 0.3, 0.05, 0.1)}, stiff=["canvas.L"],
               place={"front.L": PL, "canvas.L": PL}, bend={"canvas.L": 6.0})
    b = _build(net, "front.L")
    assert b.holds.layers == {"canvas.L": "front.L"}
    rep = ch.place_layers(b)
    cv, hv = net.verts("canvas.L"), net.verts("front.L")
    assert not (np.linalg.norm(b.X[cv], axis=1) < 1e-9).any()  # (nothing of it at the origin)
    assert np.allclose(b.X[cv, 2], 1.0 - LAYER) and np.allclose(b.X[cv, :2], net.uv[cv], atol=1e-9)
    inside = np.all((net.uv[hv] >= [0.05 - 1e-9, 0.1 - 1e-9]) & (net.uv[hv] <= [0.25 + 1e-9, 0.4 + 1e-9]), axis=1)
    assert np.allclose(net.bend[hv[inside]], 6.0) and np.allclose(net.bend[hv[~inside]], 1.0)  # (stiffened where it lies)
    assert np.allclose(b.layer_stiff[hv[inside]], 1.0) and not b.layer_stiff[hv[~inside]].any()
    assert rep["canvas.L"]["built"] and rep["canvas.L"]["covers"] == int(inside.sum())
    assert b.reads["layers"]["canvas.L"]["stiffens"] == "front.L"


def test_a_layer_whose_flat_is_not_in_its_host_is_refused_by_name():
    net = _net({"front.L": (0.3, 0.5, 0.0, 0.0), "canvas.L": (0.2, 0.3, 0.6, 0.0)}, stiff=["canvas.L"],
               place={"front.L": PL, "canvas.L": PL})
    b = _build(net, "front.L")
    with pytest.raises(ChainRefused, match="canvas.L"):
        ch.place_layers(b)


def _collar_net():
    # body cloth -> collar (outer, sewn to the body) + under (a ply sewn round it) -> facing sewn to the under's bottom only
    return _net({"body": (0.3, 0.2, 0.0, 0.0), "collar": (0.2, 0.05, 0.5, 0.0), "under": (0.2, 0.05, 0.8, 0.0),
                 "facing": (0.2, 0.1, 1.1, 0.0)}, stiff=["collar", "under"],
                sew=[("body", "top", "collar", "bottom"), ("under", "top", "collar", "top"),
                     ("under", "left", "collar", "left"), ("under", "right", "collar", "right"),
                     ("facing", "top", "under", "bottom")])


def test_every_point_of_a_ply_is_placed_and_a_piece_sewn_to_it_starts_at_its_seam():
    net = _collar_net()
    b = _build(net, "collar")
    assert b.holds.plies == {"under": "collar"}
    rep = ch.place_plies(b)
    uv_ = net.verts("under")
    assert not (np.linalg.norm(b.X[uv_], axis=1) < 1e-9).any()  # (every ply point placed: not only the unsewn ones)
    on_host = np.isin(net.root[uv_], net.root[net.verts("collar")])
    assert np.allclose(b.X[uv_[~on_host], 2], 1.0 - LAYER)
    assert rep["under"]["placed"] == int((~on_host).sum()) == len(uv_) - 15  # (top, left, right on the host)
    # the facing's points sewn to the ply: on it, where its seam puts them (one node)
    fv = net.verts("facing")
    sewn = fv[np.isin(net.root[fv], net.root[uv_])]
    assert len(sewn) == NX and np.allclose(b.X[sewn], b.X[net.root[sewn]])
    assert not (np.linalg.norm(b.X[sewn], axis=1) < 1e-9).any()


def test_a_facing_starts_inside_its_front_and_a_two_piece_sleeve_is_not_a_lining():
    arm = {"to": "arm.L"}
    net = _net({"front.L": (0.3, 0.5, 0.0, 0.0), "facing.L": (0.1, 0.5, 0.2, 0.0),
                "top.L": (0.3, 0.5, 1.0, 0.0), "under.L": (0.2, 0.5, 1.05, 0.0)},
               sew=[("facing.L", "right", "front.L", "right"), ("under.L", "left", "top.L", "left"),
                    ("under.L", "right", "top.L", "right")],
               place={"front.L": PL, "facing.L": PL, "top.L": arm, "under.L": arm})
    b = _build(net, "front.L")
    assert b.holds.inside == {"facing.L": "front.L"}
    ch.place_inside(b, b.X)
    fv = net.verts("facing.L")
    free = ~np.isin(net.root[fv], net.root[net.verts("front.L")])
    assert np.allclose(b.X[fv[free], 2], 1.0 - LAYER) and np.allclose(b.X[fv[free], :2], net.uv[fv[free]], atol=1e-9)


def test_the_start_row_fails_a_point_left_at_the_origin_and_a_seam_sewn_the_wrong_way_round():
    net = _collar_net()
    b = _build(net, "collar")
    rows, reads = cpl.placed_rows(b, b.X, cst._row)
    names = {r["id"]: r for r in rows}
    assert "placed:under" in names and names["placed:under"]["status"] == "FAIL"
    assert names["placed:body"]["ours"]["value"] == str(len(net.verts("body")) - NX)  # (its top: the collar's, placed)
    assert "under (a ply of collar)" in names["placed:under"]["change"]
    ch.place_plies(b)
    assert "placed:under" not in {r["id"] for r in cpl.placed_rows(b, b.X, cst._row)[0]}
    assert cst.verdict("start", rows)["verdict"] == "FAIL"  # (a verdict, not provisional)
    # a seam sewn end to end the wrong way round folds a piece onto itself: named at the start
    bad = _net({"a": (0.3, 0.1, 0.0, 0.0), "b": (0.3, 0.1, 0.5, 0.0), "c": (0.3, 0.1, 1.0, 0.0)},
               sew=[("a", "top", "b", "bottom"), ("b", "bottom", "c", "bottom", "rev"), ("c", "bottom", "a", "top")])
    rows = cpl.crossed_rows(_build(bad, "a"), cst._row)[0]
    assert {r["id"] for r in rows} >= {"crossed:a"} and all(r["status"] == "FAIL" for r in rows)
    assert cpl.crossed_rows(_build(net, "collar"), cst._row)[0] == []
