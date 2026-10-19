"""cloth_over: a piece draped alone over a finished garment (dress-garrett ak)."""
import numpy as np
from hifipushie import cloth_over as co, cloth_job as cj


def _strip(n=9, m=5, w=0.04):
    s = np.linspace(-0.1, 0.1, n)
    t = np.linspace(0, w, m)
    return np.stack([np.stack([np.full(m, x), np.zeros(m), t], -1) for x in s])  # columns straight up z


def test_resample_columns_widths_and_extension():
    G = _strip()
    W = np.linspace(0.02, 0.06, len(G))
    X = co.resample_columns(G, W)
    assert np.allclose(co.col_lengths(X), W, atol=1e-9)


def test_turn_onto_plane_lies_in_plane_pointing_toward():
    G = _strip()
    N, T = np.array([0, -1.0, 0]), np.array([0, 0, -1.0])  # lie in the xz plane... turned to point down
    sel = np.ones(len(G), bool)
    R, info = co.turn_onto_plane(G, sel, np.array([0, 0, 1.0]), np.array([0, -1.0, 0]), lift=0.0, weight=np.ones(len(G)))
    d = R[:, -1] - R[:, 0]
    assert np.abs(d[:, 2]).max() < 1e-3 and (d[:, 1] < 0).all()  # flat in z = const, pointing -y
    assert np.allclose(co.col_lengths(R), co.col_lengths(G))


def test_flat_draft_is_isometric_for_a_developable_piece():
    G = _strip()
    uv = co.flat_draft(G)
    assert np.allclose(co.col_lengths(uv), co.col_lengths(G), atol=1e-9)
    assert np.allclose(co.row_lengths(uv), co.row_lengths(G), rtol=1e-3)


def test_under_draft_turn_of_cloth():
    uv = co.flat_draft(_strip())
    u = co.under_draft(uv, turn=0.003)
    assert np.allclose(co.col_lengths(u), co.col_lengths(uv) - 0.003, atol=1e-9)


def test_job_pins_and_rest_and_collider_cut():
    G = _strip()
    pinned = np.zeros(G.shape[:2], bool); pinned[:, 0] = True
    bV = np.array([[0, 0.01, 0], [1, 0.01, 0], [0, 0.01, 1], [-0.1, 0.01, 0.001]]); bT = np.array([[0, 1, 2], [0, 2, 3]])
    C = co.collider([(bV, bT)], near=G[:, 0][[4]], radius=0.02)
    assert len(C[1]) < 2
    cfg, arr = co.job(G, co.flat_draft(G), G, pinned, (bV, bT))
    assert set(arr["carryIdx"]) == set(np.where(pinned.reshape(-1))[0])
    assert arr["rest"].shape == arr["X"].shape and len(arr["restIdx"]) == len(arr["X"])
    jc = cj.job_config(cfg)
    assert [s["name"] for s in jc["stages"]][:2] == ["sew", "settle"]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print("ok", k)


def test_collider_drops_long_edge_past_pin_and_edge_clear():
    """al: a long collider edge passing 1.4 mm from a pin (both its ends far) is dropped; edge_pairs finds an
    edge-edge pair a vertex-face test misses, and clear_start(F=) clears it."""
    import numpy as np
    from hifipushie import cloth_over as co
    from hifipushie.cloth_made import grid_faces
    bV = np.array([[-0.05, 0.0014, 0.0], [0.05, 0.0014, 0.0], [0.0, 0.05, 0.0]])
    C = co.collider([(bV, np.array([[0, 1, 2]]))], near=np.array([[0.0, 0.0, 0.0]]), radius=0.004)
    assert len(C[1]) == 0
    C = co.collider([(bV, np.array([[0, 1, 2]]))], near=None, labels=True)
    assert len(C) == 3 and (C[2] == 0).all()
    # a 2 x 2 grid piece whose edge crosses a collider ridge 1 mm below its middle (vertices 5 mm off)
    X = np.array([[[-0.005, 0.0, 0.005], [-0.005, 0.01, 0.005]], [[0.005, 0.0, -0.005], [0.005, 0.01, -0.005]]])
    rV = np.array([[0.0, -0.05, -0.001], [0.0, 0.05, -0.001], [0.0, 0.0, -0.05]])
    coll = (rV, np.array([[0, 1, 2]]))
    free = np.ones((2, 2), bool)
    E, bE, d, _ = co.edge_pairs(X.reshape(-1, 3), grid_faces(2, 2), coll, free.reshape(-1), 0.003)
    assert len(E) and d.min() < 0.002
    X2, mv = co.clear_start(X, coll, free, clear=0.003, F=grid_faces(2, 2))
    E, _, d, _ = co.edge_pairs(X2.reshape(-1, 3), grid_faces(2, 2), coll, free.reshape(-1), 0.0029)
    assert not len(E)
