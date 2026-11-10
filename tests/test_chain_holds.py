"""chain_holds (R3b): what holds what, read from the pattern's construction, on small synthetic nets: a ply (sewn round
its host, congruent), a two-piece sleeve and a band on its collar along one edge (not plies), a floating layer and its
host, a roll fold on a soft piece (its own fold) vs a stiff one (a FALL), the order, plies placed from their host."""
import types

import numpy as np

from hifipushie import chain_garment as cg, chain_holds as ch, chain_net as cn
from hifipushie.chain_core import LAYER

NX, NY = 7, 5


def _rect(w, h, x0, mirror=False):
    xs, ys = np.linspace(0, w, NX), np.linspace(0, h, NY)
    uv = np.array([[x0 + (w - x if mirror else x), y] for y in ys for x in xs])
    F = []
    for j in range(NY - 1):
        for i in range(NX - 1):
            a = j * NX + i
            F += [[a, a + 1, a + NX], [a + 1, a + NX + 1, a + NX]]
    edges = {"bottom": [i for i in range(NX)], "top": [(NY - 1) * NX + i for i in range(NX)],
             "left": [j * NX for j in range(NY)], "right": [j * NX + NX - 1 for j in range(NY)]}
    # (mirror: edges keep their index order, so a mirrored piece's edges are the reflection of the other's)
    return uv, np.array(F), edges


def _net(pieces: dict, stiff=(), sew=(), folds=(), roles=None, place=None):
    """pieces {name: (w, h[, mirror])}; sew [(a, edge, b, edge)]: the two edges' vertices sewn in order."""
    uvs, Fs, ps, off, ed = [], [], [], {}, {}
    k = 0
    for i, (nm, spec) in enumerate(pieces.items()):
        uv, F, e = _rect(spec[0], spec[1], 0.5 * i, *(spec[2:] or ()))
        uvs.append(uv), Fs.append(F + k), ps.append(np.full(len(uv), i))
        off[nm], ed[nm] = k, e
        k += len(uv)
    pairs = [[off[a] + x, off[b] + y] for a, ea, b, eb in sew for x, y in zip(ed[a][ea], ed[b][eb])]
    M = {"uv": np.concatenate(uvs), "F": np.concatenate(Fs), "piece": np.concatenate(ps), "names": list(pieces),
         "sew": np.array(pairs, np.int64).reshape(-1, 2), "folds": list(folds), "closures": []}
    if roles:
        M["roles"] = roles
    if place:
        M["place"] = place
    st = np.zeros(len(M["uv"]))
    for nm in stiff:
        st[M["piece"] == list(pieces).index(nm)] = 1.0
    return cn.Network(M, st, np.ones(len(st)))


def test_a_ply_sewn_round_its_host_is_one_part_with_the_body_side_outer():
    net = _net({"body": (0.3, 0.2), "collar": (0.2, 0.05), "canvas": (0.2, 0.05)}, stiff=["collar", "canvas"],
               sew=[("body", "top", "collar", "bottom"), ("canvas", "top", "collar", "top"),
                    ("canvas", "left", "collar", "left"), ("canvas", "right", "collar", "right")])
    H = ch.read(net)
    assert H.plies == {"canvas": "collar"}
    pt = H.part_of("canvas")
    assert pt.outer == "collar" and pt.pieces == ["collar", "canvas"] and pt.stiff and pt.rests_on == ["body"]


def test_a_ply_cut_face_to_face_is_still_a_ply():  # (the rigid fit allows a reflection)
    net = _net({"body": (0.3, 0.2), "collar": (0.2, 0.05), "under": (0.2, 0.05, True)}, stiff=["collar", "under"],
               sew=[("body", "top", "under", "bottom"), ("collar", "top", "under", "top"),
                    ("collar", "left", "under", "left"), ("collar", "right", "under", "right")])
    assert ch.read(net).plies == {"collar": "under"}


def test_the_measured_table_two_piece_sleeve_and_band_on_collar_are_not_plies():
    sleeve = _net({"top": (0.2, 0.5), "under": (0.1, 0.5)},
                  sew=[("top", "left", "under", "left"), ("top", "right", "under", "right")])
    (p, q), = [k for k in ch._sewn(sleeve)[0] if k[0] < k[1]]
    ab = np.asarray(ch._sewn(sleeve)[0][(p, q)])
    assert ch.rigid_rms(sleeve.uv[ab[:, 0]], sleeve.uv[ab[:, 1]]) > 10 * ch.PLY_RMS  # (the widths differ: not congruent)
    assert ch.read(sleeve).plies == {}
    band = _net({"band": (0.4, 0.04), "collar": (0.4, 0.07)}, stiff=["band", "collar"],
                sew=[("band", "top", "collar", "bottom")])
    ab = np.asarray(ch._sewn(band)[0][(0, 1)])
    assert ch.rigid_rms(band.uv[ab[:, 0]], band.uv[ab[:, 1]]) < ch.PLY_RMS  # (one line maps rigidly ...)
    assert ch.hull_share(band.uv[ab[:, 1]], 0.4 * 0.07) < ch.PLY_AREA  # (... but closes round no area)
    assert ch.read(band).plies == {}


def test_two_congruent_halves_of_a_tube_are_not_plies():  # (sewn in two runs: both ends of the tube stay open)
    net = _net({"front.L": (0.2, 0.5), "back.L": (0.2, 0.5)},
               sew=[("front.L", "left", "back.L", "left"), ("front.L", "right", "back.L", "right")])
    assert ch.rigid_rms(net.uv[net.verts("front.L")], net.uv[net.verts("back.L")]) < ch.PLY_RMS
    assert ch.read(net).plies == {}


def test_a_seamless_stiff_piece_floats_in_the_largest_soft_piece_at_its_place():
    pl = {"to": "torso", "side": "front"}
    net = _net({"front.L": (0.3, 0.5), "facing.L": (0.08, 0.5), "canvas.L": (0.2, 0.3), "front.R": (0.3, 0.5)},
               stiff=["canvas.L"], sew=[("front.L", "right", "facing.L", "left")],
               place={"front.L": pl, "facing.L": pl, "canvas.L": pl, "front.R": pl})
    H = ch.read(net)
    assert H.layers == {"canvas.L": "front.L"} and H.plies == {}
    assert H.part_of("canvas.L") is None and H.part_of("front.L").stiffened_by == ["canvas.L"]


def test_a_roll_on_a_soft_piece_is_its_own_fold_on_a_stiff_part_a_fall():
    folds = [{"name": "lapel", "piece": "front.L", "kind": "roll"}, {"name": "roll", "piece": "collar", "kind": "roll"}]
    net = _net({"front.L": (0.3, 0.5), "stand": (0.2, 0.04), "collar": (0.2, 0.07)}, stiff=["stand", "collar"],
               sew=[("front.L", "top", "stand", "bottom"), ("stand", "top", "collar", "bottom")], folds=folds)
    H = ch.read(net)
    assert [(f["piece"], f["fall"]) for f in H.folds] == [("front.L", False), ("collar", True)]
    assert H.part_of("front.L").folds == ["lapel"]


def test_read_roles_reads_no_fall_from_a_soft_roll():
    folds = [{"name": "lapel", "piece": "front.L", "kind": "roll"}, {"name": "lapel", "piece": "front.R", "kind": "roll"}]
    net = _net({"front.L": (0.3, 0.5), "front.R": (0.3, 0.5, True), "collar": (0.4, 0.04)}, stiff=["collar"],
               sew=[("front.L", "top", "collar", "bottom"), ("front.L", "left", "front.R", "left")], folds=folds,
               roles={"collar": "collar_stand"})
    R = cg.read_roles(net)
    assert R.fall is None and R.fold is None and R.band == "collar" and R.stand


def test_read_roles_gives_plies_no_role():
    net = _net({"front.L": (0.3, 0.5), "front.R": (0.3, 0.5, True), "collar": (0.4, 0.04), "canvas": (0.4, 0.04)},
               stiff=["collar", "canvas"], roles={"collar": "collar_stand"},
               sew=[("front.L", "top", "collar", "bottom"), ("front.L", "left", "front.R", "left"),
                    ("canvas", "top", "collar", "top"), ("canvas", "left", "collar", "left"),
                    ("canvas", "right", "collar", "right")])
    R = cg.read_roles(net)
    assert R.band == "collar" and R.carried == ["canvas"]
    assert "canvas" not in R.rings + R.tubes + R.panels


def test_the_order_stiff_first_a_fall_on_its_band_soft_hangs_from_what_it_is_sewn_to():
    net = _net({"back": (0.3, 0.5), "front.L": (0.3, 0.5), "stand": (0.2, 0.04), "collar": (0.2, 0.07)},
               stiff=["stand", "collar"], folds=[{"name": "roll", "piece": "collar", "kind": "roll"}],
               sew=[("front.L", "top", "stand", "bottom"), ("stand", "top", "collar", "bottom"),
                    ("back", "left", "front.L", "right")])
    H = ch.read(net)
    order = [(p.name, p.rests_on) for p in H.parts]
    assert order[:2] == [("stand", ["body"]), ("collar", ["stand"])]
    assert dict(order)["front.L"] == ["stand"] and dict(order)["back"] == ["body"]


def test_place_plies_puts_a_ply_a_layer_inside_its_host():
    net = _net({"body": (0.3, 0.2), "collar": (0.2, 0.05), "canvas": (0.2, 0.05)}, stiff=["collar", "canvas"],
               sew=[("body", "top", "collar", "bottom"), ("canvas", "top", "collar", "top"),
                    ("canvas", "left", "collar", "left"), ("canvas", "right", "collar", "right")])
    X = np.zeros((net.n, 3))
    hv = net.verts("collar")
    X[net.root[hv]] = np.c_[net.uv[hv] - net.uv[hv].min(0), np.full(len(hv), 1.0)]  # (the host flat at z = 1, outside +z)
    X = X[net.root]
    contact = types.SimpleNamespace(query=lambda P: (np.zeros(len(P)), np.tile([0.0, 0.0, 1.0], (len(P), 1))))
    b = types.SimpleNamespace(net=net, X=X, reads={}, holds=ch.read(net), body=types.SimpleNamespace(contact=contact))
    rep = ch.place_plies(b)
    cv = net.verts("canvas")
    inner = cv[np.bincount(net.root, minlength=net.n)[net.root[cv]] == 1]
    assert rep["canvas"]["placed"] == len(inner) > 0
    assert np.allclose(b.X[inner, 2], 1.0 - LAYER)
    uv0 = net.uv[cv].min(0)
    assert np.allclose(b.X[inner, :2], net.uv[inner] - uv0, atol=1e-9)  # (the flat map: congruent, the same point)
