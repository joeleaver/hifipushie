"""Steps 5 / 6 (drape first, R3b): a synthetic toile (an open-fronted cylinder torso: developable) marked into back /
side / front pieces per side by body-line fields, each one region; flattened with near-zero strain; seams equal; the
flat pattern passes the flat gate's seams row; a mark that doesn't separate is refused."""
import numpy as np
import pytest

from hifipushie import cloth_check, cut, cut_tool, mark

R, H = 0.16, 0.6


def torso(n_a=96, n_z=40, gap=0.25):
    """A cylinder round z, open at the front (-y) over `gap` rad: one disc of cloth."""
    th = np.linspace(-np.pi + gap / 2, np.pi - gap / 2, n_a)  # angle from the back (+y) round; front gap at +-pi
    z = np.linspace(0.9, 0.9 + H, n_z)
    T, Zg = np.meshgrid(th, z)
    V = np.c_[R * np.sin(T).ravel(), R * np.cos(T).ravel(), Zg.ravel()]
    idx = np.arange(n_a * n_z).reshape(n_z, n_a)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    return V, np.r_[np.c_[a, b, c], np.c_[a, c, d]]


class Stub:
    yc = 0.0

    def field(self, line, P, Vreg):
        ang = np.arctan2(np.abs(P[:, 0]), -P[:, 1])  # 0 at the front, pi at the back
        if line["kind"] == "centre_back":
            return P[:, 0]
        if line["kind"] == "panel":
            return ang - line["at"] + 0.03 * (P[:, 2] - 1.2)  # a seam leaning a little
        return np.full(len(P), 1.0)  # "nothing": never crosses


MARKS = [{"name": "centre_back", "line": {"kind": "centre_back"}, "region": "toile", "into": ["body.R", "body.L"]},
         {"name": "front_side.L", "line": {"kind": "panel", "at": 1.3}, "region": "body.L", "into": ["front.L", "rest.L"]},
         {"name": "side_back.L", "line": {"kind": "panel", "at": 2.1}, "region": "rest.L", "into": ["side.L", "back.L"]}]
S1 = {"pieces": {p + s: {"build": "full"} for p in ("front", "side", "back") for s in (".L", ".R")},
      "seams": [{"a": f"front{s}:side", "b": f"side{s}:front"} for s in (".L", ".R")]
      + [{"a": f"side{s}:back", "b": f"back{s}:side"} for s in (".L", ".R")] + [{"a": "back.L:cb", "b": "back.R:cb"}]}


def marked():
    V, F = torso()
    return mark.run_marks(V, F, mark.mirrored(MARKS), Stub(), log=lambda *_: None)


def test_marks_cut_into_one_region_each_and_seams_marked():
    V, F, lab, names, rep = marked()
    assert sorted(names) == sorted(S1["pieces"])
    assert all(r["length_mm"] > 0.5 * H * 1000 for r in rep)
    got, miss, skipped, extra, pairs, free = mark.seam_map(V, F, lab, names, S1, {})
    assert not miss and len(got) == 5 and not extra
    rows = mark.gate(rep, names, lab, V, F, S1, {}, got, miss, skipped, extra)
    assert all(r["status"] in ("PASS", "INFO") for r in rows), rows


def test_mark_that_does_not_separate_is_refused():
    V, F = torso()
    bad = MARKS[:1] + [{"name": "nothing.L", "line": {"kind": "none"}, "region": "body.L", "into": ["a.L", "b.L"]}]
    with pytest.raises(mark.MarkRefused, match="nothing.L does not separate"):
        mark.run_marks(V, F, mark.mirrored(bad), Stub(), log=lambda *_: None)


def test_flat_pattern_developable_seams_equal_and_gate_seams_row():
    V, F, lab, names, rep = marked()
    free = {"front.L": {"front": "side", "hem": "bottom", "neck": "top"}, "side.L": {"hem": "bottom", "neck": "top"},
            "back.L": {"hem": "bottom", "neck": "top"}}
    pcs, edges = {}, {}
    for p, nm in enumerate(names):
        f = cut.flatten_piece(V, F, lab, p, nm)
        assert f["rep"]["strain_mean_pct"] < 0.5, (nm, f["rep"])
        rs = cut.runs_of(f["loop"], V, cut.other_label(F, lab, p), names, p, free.get(nm) or free.get(nm[:-2] + ".L"))
        edges[nm], bad = cut.name_runs(nm, rs, V, f["loop"], S1, {}, {}, free)
        assert not bad, bad
        pcs[nm] = f
    B, decl = cut_tool.block(pcs, edges, S1, {}, {})
    assert max(abs(t["before_pct"]) for t in B["trued"]) < 1.0  # developable: the seams come off equal
    sm = cloth_check.seams(B)
    assert len(sm) == 5 and all(abs(r["len_a_mm"] / r["len_b_mm"] - 1) < 0.01 for r in sm)
    from hifipushie import draft_own_gate
    rows = draft_own_gate.gate(B, decl, S1)
    by = {r["id"]: r for r in rows}
    assert by["seams"]["status"] == "PASS" and by["sewn"]["status"] == "PASS" and by["cut"]["status"] == "PASS"
