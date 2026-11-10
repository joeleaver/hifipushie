"""chain_roles (T8, C289): roles read from any pattern on small synthetic ones: a stand never read from a declared role
or a name (C396), a TUBE of two pieces, halves of a back as panels, a ZIP edge to edge; the shirt's
roles unchanged; draft_pattern's text lists failing seam pairs first."""
import numpy as np
import pytest

from hifipushie import chain_garment as cg, chain_net as cn, chain_roles as cr, pattern_sheet

N = 5


def _pattern(pieces: list, stiff=(), sew=(), roles=None, closures=(), folds=()):
    """pieces: names, each a flat N x 2 strip 0.1 x 0.02 m at its own x; sew: (piece a, vertex a, piece b, vertex b)."""
    uvs, Fs, ps, off = [], [], [], {}
    k = 0
    for i, nm in enumerate(pieces):
        xs = np.linspace(0.2 * i, 0.2 * i + 0.1, N)
        uvs.append(np.r_[np.c_[xs, np.zeros(N)], np.c_[xs, np.full(N, 0.02)]])
        Fs.append(np.array([f for j in range(N - 1) for f in ([j, j + 1, N + j], [j + 1, N + j + 1, N + j])]) + k)
        ps.append(np.full(2 * N, i))
        off[nm] = k
        k += 2 * N
    M = {"uv": np.concatenate(uvs), "F": np.concatenate(Fs), "piece": np.concatenate(ps), "names": list(pieces),
         "sew": np.array([[off[a] + va, off[b] + vb] for a, va, b, vb in sew], np.int64).reshape(-1, 2),
         "folds": list(folds), "closures": [dict(c) for c in closures]}
    if roles:
        M["roles"] = roles
    st = np.zeros(len(M["uv"]))
    for nm in stiff:
        st[M["piece"] == pieces.index(nm)] = 1.0
    return cn.Network(M, st, np.ones(len(st))), off


JACKET = ["front.L", "front.R", "back.L", "back.R", "sleeve.L", "undersleeve.L", "collar"]
JSEW = [("front.L", 0, "back.L", 4), ("back.L", 0, "back.R", 0), ("front.R", 4, "back.R", 4),
        ("sleeve.L", 0, "undersleeve.L", 0), ("sleeve.L", 4, "undersleeve.L", 4), ("sleeve.L", 2, "front.L", 7),
        ("collar", 0, "front.R", 6), ("collar", 2, "back.L", 6), ("collar", 4, "front.L", 6)]


def _zip():
    return {"name": "front", "kind": "zip", "over": "front.L", "under": "front.R", "state": "closed", "closed": [],
            "v": [], "edge_xy": {"over": np.array([[0.0, 0.0], [0.0, 0.02]]), "under": np.array([[0.3, 0.0], [0.3, 0.02]])}}


def test_a_stand_is_read_from_the_construction_never_its_role():
    """C396: a declared role or a name never makes a stand (read_roles leaves a stiff part with nothing on it a ring;
    the build's chain_roles.neck_part makes it the stand when its seam lies on the neckline). A stiff collar with no
    roll whose name reads collar_fall was refused by name (the suit jacket's collar): it is now read the same way."""
    for roles in ({"collar": "collar_stand"}, None):
        net, _ = _pattern(JACKET, stiff=["collar"], sew=JSEW, roles=roles, closures=[_zip()])
        R = cg.read_roles(net)
        assert R.band is None and not R.stand and R.fall is None and "collar" in R.rings


def test_a_two_piece_sleeve_is_one_tube_and_half_backs_are_panels():
    net, _ = _pattern(JACKET, stiff=["collar"], sew=JSEW, roles={"collar": "collar_stand"}, closures=[_zip()])
    R = cg.read_roles(net)
    assert set(R.tubes) == {"sleeve.L", "undersleeve.L"}
    assert R.tube_groups["sleeve.L"] == R.tube_groups["undersleeve.L"] == ["sleeve.L", "undersleeve.L"]
    assert set(R.panels) == {"front.L", "front.R", "back.L", "back.R"}


def test_a_self_sewn_sleeve_stays_a_tube_of_its_own():
    net, _ = _pattern(["front.L", "sleeve.L"], sew=[("sleeve.L", 0, "sleeve.L", 4), ("sleeve.L", 2, "front.L", 7)])
    R = cg.read_roles(net)
    assert R.tubes == ["sleeve.L"] and R.tube_groups == {} and R.panels == ["front.L"]


def test_a_zip_meets_edge_to_edge():
    net, off = _pattern(JACKET, stiff=["collar"], sew=JSEW, roles={"collar": "collar_stand"}, closures=[_zip()])
    R = cg.read_roles(net)
    v = np.asarray(R.front["v"])
    assert len(v) == 2 and all(R.front["closed"])
    assert set(net.piece[v[:, 0]]) == {0} and set(net.piece[v[:, 1]]) == {1}  # over on front.L, under on front.R
    assert net.M["closures"][0]["v"] == R.front["v"]  # (written into the pattern: the reads take pairs from there)
    assert cr.tie_gap(R.front, cg.LAYER) == cr.ZIP_GAP < cg.LAYER
    assert cr.tie_gap({"kind": "buttons"}, cg.LAYER) == cg.LAYER


def test_failing_seam_pairs_come_first():
    rows = [{"len_a_mm": 100, "len_b_mm": 100, "ease": 0.0, "ok": True, "kind": "plain", "band": (-0.01, 0.01)},
            {"len_a_mm": 120, "len_b_mm": 100, "ease": 0.2, "ok": False, "kind": "plain", "band": (-0.01, 0.01)}]
    out = pattern_sheet.text_lines({"pieces": {}, "seams": [0, 1]}, rows, names=["a = b", "c = d"])
    k = next(i for i, ln in enumerate(out) if ln.startswith("seams ("))
    assert out[k + 1].startswith("  S2 FAIL c = d: 120 / 100 mm") and "band" in out[k + 1]
    assert out[k + 2] == "  S1 PASS a = b: 100 / 100 mm, ease +0.0 %"
