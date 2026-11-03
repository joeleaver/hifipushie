"""F7 (chain_sew.py): the start is each piece flat round its region (exact), then sewn by bending only.
On F4's synthetic two-legged body: the arrangement reads 0 % on every link; sewing closes the seams with every length
held; a seam the pieces can't reach without stretch is refused by name (a PATTERN FAULT, back to step 4)."""
import numpy as np

from hifipushie import chain_garment as cg, chain_sew as sw, chain_stages as cst
from test_chain_stages import PIECES, SEWS, _legs
from test_piece_start import _build, _cyl


def _guide(b):
    b.sew_start = False
    return b.soft_start()


def test_a_flat_arrangement_reads_zero_at_the_start():
    b = _legs()
    X = sw.arrange(b, _guide(b))
    g = sw.gate_arrange(b, X)
    assert g["verdict"] == "PASS"
    ln = g["reads"]["lengths"]
    assert ln["chain_stretch_pct"] < 0.05 and ln["edge_worst_pct"] < 0.05, ln  # (nothing long)
    assert ln["chain_worst_pct"] <= cg.MAX_FREE_PCT  # (a chord across the bend: 1 - sinc short on this coarse mesh)
    for p in PIECES:  # (each piece on its own cylinder, round its own leg, off the body)
        assert b.reads["sew"]["laid"][p]["radius_mm"] >= 70
        sx = 1 if p.endswith(".L") else -1
        assert np.sign(X[b.net.verts(p), 0].mean()) == sx
    d = b.body.contact.query(X[np.isin(b.net.piece, [b.net.pid(p) for p in PIECES])])[0]
    assert (d > 0).all()


def test_a_sewn_seam_closes_with_lengths_held():
    b = _legs()
    X = sw.arrange(b, _guide(b))
    assert max(v[0] for v in sw.seam_gaps(b, X).values()) < 0.02  # (laid with its seams facing: a tube group closes)
    for p in ("back.L", "back.R"):  # (moved apart rigidly: still exact, the seams open)
        X[b.net.verts(p)] += [0.0, 0.03, 0.02]
    g0 = max(v[0] for v in sw.seam_gaps(b, X).values())
    Y = sw.sew(b, X)
    g = sw.gate_sew(b, Y)
    assert g["verdict"] == "PASS", [r for r in g["rows"] if r["status"] == "FAIL"]
    assert g0 > 0.01 and max(v[0] for v in sw.seam_gaps(b, Y).values()) <= sw.SEW_TOL
    ln = g["reads"]["lengths"]
    assert ln["chain_worst_pct"] <= cg.MAX_FREE_PCT and ln["edge_worst_pct"] <= cg.MAX_FREE_PCT, ln
    # the whole start through soft_start: gated arrange, sew, then START with its start_length a verdict (a finer
    # flat: a chord across the bend reads 1 - sinc short, 1.5 % on the 50 mm links above)
    fine = (0.0, 0.25, -1.08, 0.0, 13, 12)
    b2 = _build({p: fine for p in PIECES}, {p: ["thigh", "knee", "outseam"] for p in PIECES},
                [(a, 12 if ca else 0, c, 12 if cb else 0) for a, ca, c, cb in SEWS])
    b2.body = _legs().body
    X2 = b2.soft_start()
    assert list(b2.reads["stages"]) == ["arrange", "sew"]
    st = cst.gate_start(b2, X2)
    row = next(r for r in st["rows"] if r["id"] == "start_length:chains")
    assert row["status"] == "PASS", row


def test_a_seam_that_cant_close_is_refused_by_name():
    narrow = dict(PIECES, **{"front.L": (0.0, 0.05, -1.08, 0.0, 3, 12), "front.R": (0.0, 0.05, -1.08, 0.0, 3, 12)})
    sews = [("front.L", 0, "back.L", 0), ("front.L", 2, "back.L", 5), ("front.R", 0, "back.R", 0),
            ("front.R", 2, "back.R", 5)]
    b = _build(narrow, {p: ["thigh", "knee", "outseam"] for p in narrow}, sews)
    Vs, Fs, k = [], [], 0
    for cx in (0.10, -0.10):
        V, F = _cyl(cx, 0.07, 0.02, 1.15)
        Vs.append(V), Fs.append(F + k)
        k += len(V)
    b.body = cg.Body(np.concatenate(Vs), np.concatenate(Fs), b.body.at)
    X = sw.arrange(b, _guide(b))
    hold = np.isin(b.net.piece, [b.net.pid("back.L"), b.net.pid("back.R")])  # (as if built first: held, like a stiff part)
    b._stiff_mask = lambda: hold
    X[hold] = X[hold]
    b.X = X.copy()
    Y = sw.sew(b, X)
    g = sw.gate_sew(b, Y)
    assert g["verdict"] == "FAIL" and g["back_to"] == "4"
    bad = [r for r in g["rows"] if r["status"] == "FAIL"]
    assert bad and all(r["id"].startswith("sew:front.") for r in bad)
    assert "PATTERN FAULT" in bad[0]["change"] and "thigh" in bad[0]["change"]
    ln = g["reads"]["lengths"]  # (never stretched shut)
    assert ln["chain_worst_pct"] <= cg.MAX_FREE_PCT and ln["edge_worst_pct"] <= cg.MAX_FREE_PCT, ln
