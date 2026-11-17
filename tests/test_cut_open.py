"""R3f-6 (C503): step 6 on a garment worn OPEN: buttons placed on the closed state and carried to each front
(cut_tapes.closure_marks), layers traced from the front's own outline (a share of a short hem; a line that leaves the
host refused by name, cut_layers), the collar flattened with its neck edge's length held (cut_collar.held_flatten)."""
import numpy as np
import pytest

from hifipushie import cut_layers, cut_tapes
from hifipushie.cut_collar import held_flatten
from hifipushie.flatten import flatten
from hifipushie.mark_split import chains, edge_faces


def _grid(nx=21, nz=11, w=0.2, h=0.1, x0=0.0):
    x, z = np.meshgrid(np.linspace(x0, x0 + w, nx), np.linspace(0, h, nz), indexing="ij")
    V = np.c_[x.ravel(), np.zeros(x.size), z.ravel()]
    idx = np.arange(x.size).reshape(nx, nz)
    F = np.r_[np.c_[idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel()],
              np.c_[idx[:-1, :-1].ravel(), idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()]]
    return V, F


def _piece(name, V, F, edge_of):
    """A flat piece (U = the 3D x, z) with its outline loop and edges named by edge_of(a, b) on each outline segment."""
    U = V[:, [0, 2]].copy()
    E, ef = edge_faces(F)
    loop = np.asarray(next(iter(chains(E[ef[:, 1] < 0]))))
    loop = loop[:-1] if loop[0] == loop[-1] else loop
    P = U[loop]
    if np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(P[:, 1], np.roll(P[:, 0], -1)) < 0:
        loop = loop[::-1]
    n = len(loop)
    keys = [edge_of(U[loop[k]], U[loop[(k + 1) % n]]) for k in range(n)]
    k0 = next(k for k in range(n) if keys[k] != keys[k - 1])  # (start on an edge's first segment)
    loop, keys = np.roll(loop, -k0), keys[k0:] + keys[:k0]
    edges = {}
    for k, e in enumerate(keys):
        edges.setdefault(e, []).append(k)
    f = {"name": name, "V": V, "U": U, "F": F, "lp": loop, "loop": list(loop), "bad": np.zeros(len(F)), "rep": {}}
    return f, edges


def _box_edges(x0, x1, h, front_x):
    def e(a, b):
        if abs(a[1]) < 1e-9 and abs(b[1]) < 1e-9:
            return "hem"
        if abs(a[1] - h) < 1e-9 and abs(b[1] - h) < 1e-9:
            return "top"
        if abs(a[0] - front_x) < 1e-9 and abs(b[0] - front_x) < 1e-9:
            return "front"
        return "side"
    return e


def test_open_front_carries_its_buttons_from_the_closed_state():
    pcs, edges = {}, {}
    for p, x0, fx in (("front.L", 0.06, 0.06), ("front.R", -0.26, -0.06)):  # (the fronts 6 cm apart: open)
        V, F = _grid(x0=x0)
        pcs[p], edges[p] = _piece(p, V, F, _box_edges(x0, x0 + 0.2, 0.1, fx))
    B = {"pieces": {p: {"marks": {}} for p in pcs},
         "closures": [{"name": "front_closure", "over": "front.L", "under": "front.R",
                       "edge": {"over": "front.a>front.m>front.b", "under": "front.a>front.m>front.b"}}]}
    # closed: no front reaches centre front, so the old reading refuses
    assert cut_tapes.closure_marks({**B, "closures": [dict(B["closures"][0])]}, pcs, {"wear": "closed", "buttons_z": [0.04]}, edges)
    # open with no closed state: refused by name
    assert "closed_buttons" in cut_tapes.closure_marks(B, pcs, {"wear": "open", "buttons_z": [0.04]}, edges)[0]
    op = {"wear": "open", "buttons_z": [0.04, 0.07],
          "closed_buttons": [{"z": 0.07, "from_edge_mm": 20.0}, {"z": 0.04, "from_edge_mm": 20.0}]}
    why = cut_tapes.closure_marks(B, pcs, op, edges)
    assert not why, why
    assert B["closures"][0]["pairs"] == [["button1", "buttonhole1"], ["button2", "buttonhole2"]]
    assert np.allclose(B["pieces"]["front.L"]["marks"]["button1"], [0.08, 0.07], atol=1e-6)  # (20 mm in from its edge)
    assert np.allclose(B["pieces"]["front.R"]["marks"]["buttonhole2"], [-0.08, 0.04], atol=1e-6)


def test_facing_traced_off_a_front_with_a_short_hem():
    V, F = _grid(w=0.084, nx=15)  # (an 84 mm hem: a cutaway)
    f, edges = _piece("front.L", V, F, _box_edges(0, 0.084, 0.1, 0.0))
    d = {"host": "front.L", "line": [["top", 40, "front"], ["hem", 90, "front"]], "keeps": "front"}
    with pytest.raises(cut_layers.LayerRefused, match="84 mm long"):
        cut_layers.cut_layer(f, edges, d, "facing.L")
    d["line"][1] = ["hem", "60%", "front"]  # (a share of the front's own hem)
    g, out, rep, bad = cut_layers.cut_layer(f, edges, d, "facing.L")
    assert not bad and sorted(out) == ["front", "hem", "inner", "top"]
    hem = g["U"][np.asarray(g["lp"])[out["hem"] + [(out["hem"][-1] + 1) % len(g["lp"])]]]
    assert abs(np.ptp(hem[:, 0]) - 0.6 * 0.084) < 1e-3


def test_a_line_that_leaves_its_host_is_refused():
    V, F = _grid()
    C = V[F].mean(1)
    F = F[~((C[:, 0] > 0.08) & (C[:, 0] < 0.12) & (C[:, 2] > 0.05))]  # (a notch from the top: the line would cross it)
    f, edges = _piece("front.L", V, F, lambda a, b: "hem" if a[1] < 1e-9 and b[1] < 1e-9 else
                      "front" if a[0] < 1e-9 and b[0] < 1e-9 else "side" if a[0] > 0.2 - 1e-9 and b[0] > 0.2 - 1e-9 else "top")
    d = {"host": "front.L", "line": [["front", 80, "hem"], ["side", 80, "hem"]], "keeps": "hem"}
    with pytest.raises(cut_layers.LayerRefused, match="leaves front.L"):
        cut_layers.cut_layer(f, edges, d, "canvas.L")
    d["line"] = [["front", 30, "hem"], ["side", 30, "hem"]]  # (below the notch: one run across)
    g, out, rep, bad = cut_layers.cut_layer(f, edges, d, "canvas.L")
    assert sorted(out) == ["front", "hem", "inner", "side"]


def _collar(nr=9, nc=41, ks=3):
    """A stand rising and leaning out, a fall turned down over it: a surface of revolution (not developable)."""
    th = np.linspace(-1.3, 1.3, nc)
    r = np.arange(nr)
    R = np.where(r <= ks, 0.06 + 0.004 * r, 0.072 + 0.006 * (r - ks))
    Z = np.where(r <= ks, 0.008 * r, 0.024 - 0.007 * (r - ks))
    V = np.stack([R[:, None] * np.sin(th)[None], -R[:, None] * np.cos(th)[None], np.repeat(Z[:, None], nc, 1)], 2).reshape(-1, 3)
    idx = np.arange(nr * nc).reshape(nr, nc)
    F = np.r_[np.c_[idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel()],
              np.c_[idx[:-1, :-1].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()]]
    return V, F, (nr, nc, ks)


def test_collar_neck_edge_flattens_to_the_bodys_length():
    V, F, (nr, nc, ks) = _collar()
    Vg = V.reshape(nr, nc, 3)
    seg_g = ["front.R:neck" if c < 10 else "back:neck" if c < 30 else "front.L:neck" for c in range(nc - 1)]
    run = lambda Ug, g: sum(float(np.linalg.norm(Ug[0, c + 1] - Ug[0, c])) for c in range(nc - 1) if seg_g[c] == g)
    want = {g: run(Vg, g) * 1.04 for g in set(seg_g)}  # (the body's neck edges, 4 % longer than the toile's row)
    U0 = flatten(V, F)[0].reshape(nr, nc, 2)
    assert max(abs(run(U0, g) - want[g]) for g in want) > 0.002  # (a plain flatten misses them)
    U, S, Fk, held = held_flatten(V, F, (nr, nc, ks), seg_g, want)
    Ug = U.reshape(nr, nc, 2)
    for g in want:
        assert abs(run(Ug, g) - want[g]) < 0.001, (g, run(Ug, g), want[g])
    assert set(held) == set(want)
