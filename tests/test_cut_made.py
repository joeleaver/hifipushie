"""Step 6's made pieces (R3c, cut_made.py): a turned flap unfolded across its roll edge onto its piece (cut_flap.py), a
facing traced off its host's flat with its seam equal to the host's edge (cut_layers.py); neck_toile serves the
collar's test (test_toile_collar.py: the collar draped on the toile, cut and unfolded)."""
import numpy as np

from hifipushie import cut
from hifipushie.cut_flap import unfold
from hifipushie.cut_layers import cut_layer


def grid(P, closed=False):
    """Faces of a (rows, cols, 3) point grid (closed: the columns wrap)."""
    nr, nc = P.shape[:2]
    idx = np.arange(nr * nc).reshape(nr, nc)
    if closed:
        idx = np.c_[idx, idx[:, :1]]
    a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    return P.reshape(-1, 3), np.r_[np.c_[a, b, c], np.c_[a, c, d]]


def pieces(V, F, lab, names, s1, free):
    pcs, edges = {}, {}
    for p, nm in enumerate(names):
        f = cut.flatten_piece(V, F, lab, p, nm)
        rs = cut.runs_of(f["loop"], V, cut.other_label(F, lab, p), names, p, free.get(nm))
        edges[nm], bad = cut.name_runs(nm, rs, V, f["loop"], s1, {}, {}, free)
        assert not bad, bad
        pcs[nm] = f
    return pcs, edges


def sheet():
    """A flat front (x 0..0.30) with a side strip sewn to it, in the plane y = 0; the front edge at x = 0."""
    x, z = np.linspace(0, 0.35, 36), np.linspace(1.0, 1.5, 51)
    X, Z = np.meshgrid(x, z)
    V, F = grid(np.dstack([X, np.zeros_like(X), Z]))
    lab = (V[F, 0].mean(1) > 0.30).astype(int)
    s1 = {"seams": [{"a": "front.L:side", "b": "side.L:front"}]}
    free = {"front.L": {"front": "side", "neck": "top", "hem": "bottom"},
            "side.L": {"neck": "top", "hem": "bottom", "out": "side"}}
    return pieces(V, F, lab, ["front.L", "side.L"], s1, free)


def edge_len(f, idx, flat=True):
    pos = list(idx) + [(idx[-1] + 1) % len(f["lp"])]
    P = (f["U"] if flat else f["V"])[np.asarray(f["lp"])[pos]]
    return float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())


def test_flap_unfolds_across_its_roll_edge():
    pcs, edges = sheet()
    f = pcs["front.L"]
    x, z = np.linspace(0, 0.08, 9), np.linspace(1.2, 1.45, 26)
    X, Z = np.meshgrid(x, z)
    Vf, Ff = grid(np.dstack([X, np.full_like(X, -0.003), Z]))  # (the lapel turned back, lying on the front)
    g, e2, names, rep, bad = unfold(f, edges["front.L"], Vf, Ff, {"side": "front", "top": "front", "bottom": "front"},
                                    "roll", "lapel.L")
    assert not bad, bad
    assert rep["lands_across_roll"] and rep["reflected"] and rep["hinge_mean_mm"] < 1.0, rep
    assert abs(rep["roll_flat_mm"]["piece"] - rep["roll_flat_mm"]["flap"]) < 10, rep
    # the flap lies across the roll edge (the front edge, x = 0 on the flat's own axis) from the piece
    Upc = f["U"][np.asarray(f["lp"])]
    a, b = g["U"][g["lp"][names["roll.a"]]], g["U"][g["lp"][names["roll.b"]]]
    t = (b - a) / np.linalg.norm(b - a)
    side = lambda P: np.sign(t[0] * (P[:, 1] - a[1]) - t[1] * (P[:, 0] - a[0]))
    flap_flat = g["U"][len(f["V"]):]
    assert np.median(side(flap_flat)) == -np.median(side(Upc))
    # the fold lies on the roll edge: its ends are on the piece's old front edge
    assert abs(g["V"][g["lp"][names["roll.a"]], 0]) < 0.01 and abs(g["V"][g["lp"][names["roll.b"]], 0]) < 0.01
    assert "front" in e2 and "side" in e2


def test_facing_traced_off_its_host_seam_equal():
    pcs, edges = sheet()
    f, e = pcs["front.L"], edges["front.L"]
    d = {"host": "front.L", "line": [["neck", 60, "front"], ["hem", 80, "front"]], "keeps": "front",
         "edges": {"neck": "gorge"}}
    g, e2, rep, bad = cut_layer(f, e, d, "facing.L")
    assert not bad, bad
    assert sorted(e2) == ["front", "gorge", "hem", "inner"], e2
    assert abs(edge_len(g, e2["front"]) - edge_len(f, e["front"])) < 1e-4  # (its seam is the host's edge)
    assert abs(edge_len(g, e2["front"], flat=False) - edge_len(f, e["front"], flat=False)) < 1e-4
    assert abs(edge_len(g, e2["gorge"]) - 0.060) < 0.002 and abs(edge_len(g, e2["hem"]) - 0.080) < 0.002
    assert 0.06 * 0.5 < rep["area_cm2"] / 1e4 < 0.08 * 0.5


def neck_toile():
    """A cylinder body (r 0.17) under a sloping shoulder up to a neck ring (r 0.065 at z 1.50), cut in four quarters."""
    th = np.linspace(-np.pi, np.pi, 96, endpoint=False)
    r = np.r_[np.linspace(0.065, 0.17, 18), np.full(20, 0.17)]
    z = np.r_[np.linspace(1.50, 1.44, 18), np.linspace(1.43, 1.15, 20)]
    T, Rr = np.meshgrid(th, r)
    Zz = np.repeat(z[:, None], len(th), 1)
    V, F = grid(np.dstack([Rr * np.sin(T), -Rr * np.cos(T), Zz]), closed=True)  # (theta 0: the front, -y)
    c = V[F].mean(1)
    names = ["front.L", "back.L", "front.R", "back.R"]
    lab = np.where(c[:, 1] < 0, np.where(c[:, 0] > 0, 0, 2), np.where(c[:, 0] > 0, 1, 3))
    seams = [{"a": f"front{s}:side", "b": f"back{s}:front"} for s in (".L", ".R")] + [
        {"a": "front.L:cf", "b": "front.R:cf"}, {"a": "back.L:cb", "b": "back.R:cb"}] + [
        {"a": f"collar:neck_{p}{s}", "b": f"{p}{s}:neck"} for p in ("front", "back") for s in (".L", ".R")]
    s1 = {"pieces": {n: {} for n in names + ["collar"]}, "seams": seams}
    free = {n: {"neck": "top", "hem": "bottom"} for n in names}
    pcs, edges = pieces(V, F, lab, names, s1, free)
    return pcs, edges, s1, (V, F)
