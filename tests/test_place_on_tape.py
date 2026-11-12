"""P2 (docs/proposals/place_where_measured.md): step 5 places every piece where the body was measured for it. A stiff
piece's edge that step 4 names on a tape is laid along that tape by arc length from the end they share (a centre piece
from CB, its -X half on the tape mirrored; a sided piece from its centre-line end, .R on the mirrored tape), then solved
as before; a piece with no tape is refused by name before anything is placed, never started from a guess."""
import numpy as np
import pytest

from hifipushie import chain_garment as cg, chain_roles as cr, piece_start as ps
from test_chain_loops import _lathe, _pattern

R0, Z0 = 0.0705, 1.458  # (the lathe's neck base, on the shoulders' slope)


def _half_neck(n=33):
    """A path tape CB -> round the +X side of the neck -> CF (pi x R0 = 221 mm), as body_tape keeps a length."""
    th = np.linspace(0, np.pi, n)
    return np.c_[R0 * np.sin(th), R0 * np.cos(th), np.full(n, Z0)].tolist()


def _collar(edge_tape=True, tape=None):
    """A stiff strip (0.44 m: 0.22 each side of CB) sewn along its neck edge to a soft panel."""
    pat, vid = _pattern({"body": (-0.22, 0.22, -0.3, 0.0, 23, 5), "collar": (-0.22, 0.22, 0.0, 0.04, 23, 4)},
                        stiff=["collar"], sew_rows=[("collar", 0, "body", -1)])
    pat.M["starts"] = {"pieces": {"body": ["neckline"], "collar": ["neckline"]},
                       "tapes": {"neckline": {"kind": "path", "pts": tape or _half_neck()}},
                       "edges": {"collar": {"neck": {"tape": "neckline", "arc": None}}} if edge_tape else {}}
    return cg.GarmentBuild(pat, _lathe(), {"state": "closed"}, log=lambda *_: None), vid


def _on_tape_dist(P, Q):
    """Distance of each point to the tape polyline Q or its mirror."""
    Q = np.asarray(Q, float)
    out = []
    for p in P:
        best = np.inf
        for QQ in (Q, Q * [-1, 1, 1]):
            a, b = QQ[:-1], QQ[1:]
            t = np.clip(((p - a) * (b - a)).sum(1) / ((b - a) ** 2).sum(1), 0, 1)
            best = min(best, float(np.linalg.norm(a + t[:, None] * (b - a) - p, axis=1).min()))
        out.append(best)
    return np.array(out)


def test_a_stiff_edge_is_laid_along_its_tape_from_cb_by_arc_length():
    b, vid = _collar()
    sb = np.array([vid("collar", c, 0) for c in range(23)])  # (flat x -0.22 .. 0.22: CB at c 11)
    P, rd = ps.lay_on_tape(b, "collar", sb, mid=11, su=1.0)
    assert rd["tape"] == "neckline" and abs(rd["edge_mm"] - 440) < 1 and abs(rd["tape_mm"] - 221.5) < 1
    assert np.abs(P[11, :2] - [0.0, R0]).max() < 0.004  # (CB on the tape's centre-line end, at the back)
    for c in (15, 22):  # (a point d from CB along the edge lies d along the tape)
        d = (c - 11) * 0.02
        th = d / R0
        assert np.linalg.norm(P[c, :2] - [R0 * np.sin(th), R0 * np.cos(th)]) < 0.004, (c, P[c])
    assert (_on_tape_dist(P, _half_neck()) < cg.GAP + 0.002).all()
    assert (b.body.contact.query(P)[0] >= cg.GAP - 5e-4).all()  # (lifted GAP off the skin it was measured on)
    assert "edge laid on its tape neckline" in b.reads["starts"]["collar"]


def test_the_other_half_of_a_centre_piece_lies_on_the_tape_mirrored():
    b, vid = _collar()
    sb = np.array([vid("collar", c, 0) for c in range(23)])
    P, _ = ps.lay_on_tape(b, "collar", sb, mid=11, su=1.0)
    assert np.allclose(P[:11][::-1], P[12:] * [-1, 1, 1], atol=1.5e-3)  # (x -> -x about CB)
    assert (P[:11, 0] < 0).all() and (P[12:, 0] > 0).all()
    Pm, _ = ps.lay_on_tape(b, "collar", sb, mid=11, su=-1.0)  # (its flat runs the other way: the halves swap)
    assert np.allclose(Pm, P * [-1, 1, 1], atol=1.5e-3)


def test_the_stand_keeps_its_neck_on_the_tape_and_its_lengths():
    b, vid = _collar()
    assert b.roles.stand and b.roles.band == "collar"
    cr.stand_ring(b)
    nb = b.net.root[b.sb]
    X = b.X[nb]
    assert (_on_tape_dist(X, _half_neck()) < cg.GAP + 0.004).all(), _on_tape_dist(X, _half_neck()).max()
    L = np.linalg.norm(np.diff(X, axis=0), axis=1)
    assert np.abs(L / 0.02 - 1).max() < 0.03  # (its own neck links at their cut)
    s = b.reads["stand"]
    assert s["top_worst_link_pct"] < 5 and s["rise_deg_min"] >= 57, s
    assert np.linalg.norm(X[0, :2] - [0, -R0]) < 0.006 and np.linalg.norm(X[-1, :2] - [0, -R0]) < 0.006  # (ends at
    # CF, where the tape ends: no "meet at CF" rule put them there)


def test_a_sided_stiff_piece_starts_at_its_centre_line_end_and_its_R_on_the_mirror():
    pat, vid = _pattern({"body": (-0.25, 0.25, -0.3, 0.0, 11, 4), "strip.L": (0.0, 0.2, 0.0, 0.03, 11, 3),
                         "strip.R": (0.0, 0.2, 0.0, 0.03, 11, 3)}, stiff=["strip.L", "strip.R"])
    pat.M["starts"] = {"pieces": {p: ["neckline"] for p in ("body", "strip.L", "strip.R")},
                       "tapes": {"neckline": {"kind": "path", "pts": _half_neck()[::-1]}},  # (stored CF first)
                       "edges": {"strip": {"neck": {"tape": "neckline", "arc": None}}}}  # (the pair, by its base name)
    b = cg.GarmentBuild(pat, _lathe(), {"state": "closed"}, log=lambda *_: None)
    for p in ("strip.L", "strip.R"):
        ch = np.array([vid(p, c, 0) for c in range(11)])[::-1]  # (handed far end first: the flat says which is CB's)
        P, rd = ps.lay_on_tape(b, p, ch)
        assert rd["laid_from"] == "its centre-line end"
        assert np.abs(P[-1, :2] - [0.0, R0]).max() < 0.004, P[-1]  # (flat x 0: on the centre line, at CB)
        if p == "strip.L":
            PL = P
    assert (PL[:-1, 0] > 0).all() and np.allclose(P, PL * [-1, 1, 1], atol=1.5e-3)


def test_a_piece_with_no_tape_is_refused_by_name_before_anything_is_placed():
    pat, vid = _pattern({"body": (-0.22, 0.22, -0.3, 0.0, 23, 5), "apron": (-0.1, 0.1, -0.2, 0.0, 5, 3),
                         "collar": (-0.22, 0.22, 0.0, 0.04, 23, 4)}, stiff=["collar"],
                        sew_rows=[("collar", 0, "body", -1)])
    pat.M["starts"] = {"pieces": {"body": ["neckline"], "collar": ["neckline"], "apron": ["chest"]},  # (chest: no line)
                       "tapes": {"neckline": {"kind": "path", "pts": _half_neck()}},
                       "edges": {"collar": {"neck": {"tape": "neckline"}}}}
    b = cg.GarmentBuild(pat, _lathe(), {"state": "closed"}, log=lambda *_: None)
    with pytest.raises(cg.ChainRefused, match=r"step 4 names no tape for apron: back to step 4, declare tapes"):
        b.run()
    assert not b.X.any()  # (refused at the start: nothing placed)


def test_a_stiff_edge_with_no_edge_tape_or_a_short_tape_is_refused():
    b, _ = _collar(edge_tape=False)
    with pytest.raises(cg.ChainRefused, match=r"step 4 names no tape for collar's edge sewn to the body cloth"):
        cr.stand_ring(b)
    b, _ = _collar(tape=_half_neck()[:17])  # (CB to the side only: 111 mm, the edge needs 220 mm each way)
    with pytest.raises(cg.ChainRefused, match=r"collar: tape 'neckline' runs 111 mm .* needs 220 mm: back to step 3"):
        cr.stand_ring(b)
