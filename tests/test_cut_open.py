"""R3f-6 / R3f-7 (C503, C504): step 6 on a garment worn OPEN, cut from its CLOSED state: the buttons on centre front
where the lapped fronts cross it (cut_tapes.closure_marks), layers traced from the front's own outline (a share of a
short hem; a line that leaves the host refused by name, cut_layers), the collar flattened as draped, its neck edge
never stretched to the body's (cut_collar.build: the mismatch reported; held_flatten deleted)."""
import numpy as np
import pytest

from hifipushie import cut_collar, cut_layers, cut_tapes
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


def test_buttons_on_centre_front_of_the_closed_cut():
    """Cut closed (C504): each front laps 20 mm past centre front; the button and its hole sit where x = 0 crosses."""
    pcs, edges = {}, {}
    for p, x0, fx in (("front.L", -0.02, -0.02), ("front.R", -0.18, 0.02)):
        V, F = _grid(w=0.2 if p == "front.L" else 0.2, x0=x0)
        pcs[p], edges[p] = _piece(p, V, F, _box_edges(x0, x0 + 0.2, 0.1, fx))
    B = {"pieces": {p: {"marks": {}} for p in pcs},
         "closures": [{"name": "front_closure", "over": "front.L", "under": "front.R"}]}
    why = cut_tapes.closure_marks(B, pcs, {"wear": "open", "cut": "closed", "buttons_z": [0.04, 0.07]})
    assert not why, why
    assert B["closures"][0]["pairs"] == [["button1", "buttonhole1"], ["button2", "buttonhole2"]]
    assert np.allclose(B["pieces"]["front.L"]["marks"]["button1"], [0.0, 0.07], atol=1e-6)  # (on CF, 20 mm in)
    assert np.allclose(B["pieces"]["front.R"]["marks"]["buttonhole2"], [0.0, 0.04], atol=1e-6)
    # a front that doesn't reach centre front (an open toile's cut) is refused by name
    V, F = _grid(x0=0.06)
    pcs["front.L"], edges["front.L"] = _piece("front.L", V, F, _box_edges(0.06, 0.26, 0.1, 0.06))
    B["closures"] = [{"name": "front_closure", "over": "front.L", "under": "front.R"}]
    assert "doesn't cross the centre line" in cut_tapes.closure_marks(B, pcs, {"buttons_z": [0.04]})[0]


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


def _band(tmp_path, r=0.06, nr=9, nc=41, ks=3, h=0.04):
    """A collar standing straight up round a cylinder (developable: it flattens at its own lengths), saved as step 4's
    toile.npz collar part; columns at theta -1.3 .. 1.3."""
    th = np.linspace(-1.3, 1.3, nc)
    z = np.linspace(0, h, nr)
    V = np.stack([r * np.sin(th)[None].repeat(nr, 0), -r * np.cos(th)[None].repeat(nr, 0), z[:, None].repeat(nc, 1)], 2)
    idx = np.arange(nr * nc).reshape(nr, nc)
    F = np.r_[np.c_[idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel()],
              np.c_[idx[:-1, :-1].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()]]
    np.savez(tmp_path / "toile.npz", **{"collar:V": V.reshape(-1, 3), "collar:F": F, "collar_grid": np.array([nr, nc, ks])})
    return {"toile": str(tmp_path / "toile.npz")}


def _neck_piece(name, t0, t1, r=0.06, k=1.0):
    """A garment piece below the neck between angles t0..t1, its top edge "neck": in 3D on the collar's neck row; its
    flat k times as long along the neck (k != 1: the body's neck edge disagrees with the collar's)."""
    th = np.linspace(t0, t1, int(round((t1 - t0) / 0.0325)) + 1)
    n = len(th)
    zz = np.array([-0.05, 0.0])
    V3 = np.stack([r * np.sin(th)[:, None].repeat(2, 1), -r * np.cos(th)[:, None].repeat(2, 1), zz[None].repeat(n, 0)], 2)
    Vf = np.stack([k * r * th[:, None].repeat(2, 1), np.zeros((n, 2)), zz[None].repeat(n, 0)], 2)
    idx = np.arange(2 * n).reshape(n, 2)
    F = np.r_[np.c_[idx[:-1, 0], idx[1:, 0], idx[1:, 1]], np.c_[idx[:-1, 0], idx[1:, 1], idx[:-1, 1]]]
    f, e = _piece(name, Vf.reshape(-1, 3), F, lambda a, b: "neck" if abs(a[1]) < 1e-9 and abs(b[1]) < 1e-9 else "rest")
    f["V"] = V3.reshape(-1, 3)
    return f, e


@pytest.mark.parametrize("k", [1.0, 1.04])
def test_collar_flattened_as_draped_its_neck_never_stretched(tmp_path, k):
    assert not hasattr(cut_collar, "held_flatten")  # (R3f-7: the stretch to fit is gone)
    out4 = _band(tmp_path)
    pcs, edges = {}, {}
    for p, t0, t1 in (("front.R", -1.3, -0.78), ("back.R", -0.78, 0.0), ("back.L", 0.0, 0.78), ("front.L", 0.78, 1.3)):
        pcs[p], edges[p] = _neck_piece(p, t0, t1, k=k)
    s1 = {"seams": [{"a": f"collar:neck_{p}", "b": f"{p}:neck"} for p in pcs]}
    d = {"pieces": ["collar"], "neck": ["front.L:neck", "back.L:neck"], "outer": "fall", "end": "end.L"}
    c_pcs, c_edges, folds, rep, bad = cut_collar.build(pcs, edges, d, s1, {}, out4)
    assert not bad, bad
    assert "neck_held_pct" not in rep
    for g, v in rep["seams"].items():
        assert abs(v["collar_mm"] - v["collar_3d_mm"]) < 0.5, (g, v)  # (flattened at its own length: nothing stretched)
        assert abs(v["garment_mm"] - k * v["garment_3d_mm"]) < 0.5, (g, v)
        if k == 1.0:
            assert abs(v["collar_mm"] - v["garment_mm"]) < 1.0, (g, v)  # (the seams match where they agree in 3D)
        else:  # (the body's edge 4 % longer: reported, the collar not worked to it)
            assert v["garment_mm"] - v["collar_mm"] > 0.03 * v["collar_mm"], (g, v)
