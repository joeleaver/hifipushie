"""Step 10 (T11): a chain garment as a game asset (garment_export, garment_glb, garment_export_tool)."""
import json

import numpy as np
import pytest

from hifipushie import garment_export as ge, garment_glb as glbw, garment_record as gr


def _grid(nx, ny, w, h, x0=0.0):
    xs, ys = np.linspace(0, w, nx), np.linspace(0, h, ny)
    U = np.array([[x0 + x, y] for y in ys for x in xs])
    q = np.arange(nx * ny).reshape(ny, nx)
    a, b, c, d = q[:-1, :-1].ravel(), q[:-1, 1:].ravel(), q[1:, 1:].ravel(), q[1:, :-1].ravel()
    return U, np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])


def tiny_result(bend=True):
    """Two 0.3 x 0.4 m pieces sewn along one side (each its own vertices), the 3D surface a BENT copy (wrapped round a
    cylinder: a deformed copy, lengths kept), one fold row on piece b, piece b stiff (made)."""
    Ua, Fa = _grid(16, 21, 0.3, 0.4)
    Ub, Fb = _grid(16, 21, 0.3, 0.4, x0=0.3)
    uv = np.vstack([Ua, Ub]); F = np.vstack([Fa, Fb + len(Ua)])
    piece = np.r_[np.zeros(len(Ua), int), np.ones(len(Ub), int)]
    R = 0.25
    th = uv[:, 0] / R if bend else uv[:, 0]
    X = np.c_[R * np.sin(th), -R * np.cos(th), uv[:, 1]] if bend else np.c_[uv[:, 0], np.zeros(len(uv)), uv[:, 1]]
    ia = np.flatnonzero((piece == 0) & np.isclose(uv[:, 0], 0.3))
    ib = np.flatnonzero((piece == 1) & np.isclose(uv[:, 0], 0.3))
    ia, ib = ia[np.argsort(uv[ia, 1])], ib[np.argsort(uv[ib, 1])]
    fold = np.flatnonzero((piece == 1) & np.isclose(uv[:, 1], 0.2))
    fold = fold[np.argsort(uv[fold, 0])]
    M = {"uv": uv, "F": F, "piece": piece, "names": ["a", "b"], "sew": np.stack([ia, ib], 1),
         "sew_seam": np.zeros(len(ia), int), "made": ["b"], "folds": [{"piece": "b", "name": "f", "rows": [fold]}]}
    body = np.c_[0.2 * np.sin(np.linspace(0, 6.28, 400)), -0.2 * np.cos(np.linspace(0, 6.28, 400)), np.linspace(0, 0.4, 400)]
    return {"X": X, "M": M, "bV": body}


def test_regrid_onto_a_deformed_copy_uvs_are_the_pattern_and_budget_met():
    r = tiny_result()
    drape = ge.drape_of(r)
    g, tries = ge.fit_budget(drape, r["M"], 1500, extra=0, body=r["bV"])
    assert len(g["T"]) <= 1500 and len(tries) >= 1
    o = g["outer"]
    # every game vertex lies on the bent surface (radius 0.25) at the place its pattern uv says (the map is the pattern)
    assert np.allclose(np.hypot(o["V"][:, 0], o["V"][:, 1]), 0.25, atol=0.004)
    th = np.arctan2(o["V"][:, 0], -o["V"][:, 1])
    assert np.allclose(th * 0.25, o["uv_pattern"][:, 0], atol=0.004)
    assert np.allclose(o["V"][:, 2], o["uv_pattern"][:, 1], atol=1e-6)
    # the packed uvs are the pattern, scaled into [0, 1] (one scale for every piece)
    assert g["uv"].min() >= -1e-9 and g["uv"].max() <= 1 + 1e-9
    d = np.linalg.norm(o["uv"][o["T"][:, 1]] - o["uv"][o["T"][:, 0]], axis=1) * g["side"]
    dp = np.linalg.norm(o["uv_pattern"][o["T"][:, 1]] - o["uv_pattern"][o["T"][:, 0]], axis=1)
    assert np.allclose(d, dp, atol=1e-9)
    st = ge.uv_stretch(o)
    assert 0.97 < st["p5"] and st["p95"] < 1.01  # a bent copy keeps its lengths: no stretch
    assert g["missing_boundary_edges"] == 0
    # the stiff piece is finer, the fold row is kept as vertices
    hp = ge.piece_h(r["M"], g["h"])
    assert hp["b"] <= hp["a"] and hp["b"] <= 0.3 / ge.MADE_MIN_ROWS + 1e-9
    pb = o["uv_pattern"][o["piece"] == 1]
    assert np.sum(np.isclose(pb[:, 1], 0.2, atol=1e-6)) >= 0.3 / hp["b"]
    # seams shared: the two pieces' boundary vertices at x = 0.3 meet exactly
    on = np.isclose(o["uv_pattern"][:, 0], 0.3, atol=1e-6)
    A, B = o["V"][on & (o["piece"] == 0)], o["V"][on & (o["piece"] == 1)]
    assert len(A) == len(B) and np.allclose(A[np.argsort(A[:, 2])], B[np.argsort(B[:, 2])])


def test_over_budget_at_the_coarsest_grid_returns_it_for_the_refusal():
    r = tiny_result()
    g, _ = ge.fit_budget(ge.drape_of(r), r["M"], 20, body=r["bV"])
    assert len(g["T"]) > 20 and g["h"] == ge.H_MAX


def test_glb_counts_and_skin(tmp_path):
    r = tiny_result()
    g, _ = ge.fit_budget(ge.drape_of(r), r["M"], 1500, body=r["bV"])
    n = len(g["V"])
    bones = [{"name": "root", "head": np.zeros(3), "parent": -1}, {"name": "arm", "head": np.array([0, 0, 0.2]), "parent": 0}]
    J = np.zeros((n, 4), int); W = np.zeros((n, 4)); W[:, 0] = 1
    p = glbw.write(tmp_path / "g.glb", "g", [{"name": "g", "V": g["V"], "T": g["T"], "uv": g["uv"], "N": g["N"],
                                              "colour": [1, 0, 0], "J": J, "W": W},
                                             {"name": "button", "V": g["V"][:3], "T": np.array([[0, 1, 2]]), "colour": [1, 1, 1]}], bones)
    assert glbw.read_counts(p) == {"g": len(g["T"]), "button": 1}
    assert json.loads(p.with_suffix(".json").read_text())["bounds_blender"]


def test_weight_check_follows_when_weights_match():
    bones = [{"name": "root", "head": np.zeros(3), "parent": -1}, {"name": "mixamorig:LeftArm", "head": np.zeros(3), "parent": 0}]
    bV = np.random.default_rng(0).normal(size=(200, 3)) * 0.1 + [0.3, 0, 0]
    gV = bV * 1.02
    J = np.c_[np.ones((200, 1), int), np.zeros((200, 3), int)]; W = np.c_[np.ones((200, 1)), np.zeros((200, 3))]
    wc = ge.weight_check(bones, gV, J, W, bV, J, W)
    assert wc["ok"] and wc["moved_vertices"] > 100
    J0 = np.zeros_like(J)  # the garment left on the root: it stays behind as the arm moves
    assert not ge.weight_check(bones, gV, J0, W, bV, J, W)["ok"]


def _write_steps(model, garment, upto):
    for sid in gr.IDS[:gr.IDS.index(upto) + 1]:
        gr.write(model, garment, sid, "done", output={"t": sid})


def test_refused_without_approval_and_the_record_write(tmp_path, monkeypatch):
    from hifipushie import garment_export_tool as get, store
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setenv("HIFIPUSHIE_APPROVED", str(tmp_path / "approved.json"))
    monkeypatch.setenv("HIFIPUSHIE_PRESIM_APPROVAL", "optional")
    m, g = "mx", "shirt"
    (tmp_path / m).mkdir()
    d = tmp_path / m / "chain" / "shirt_open"
    d.mkdir(parents=True)
    with pytest.raises(ge.ExportRefused, match="step 9 .*not approved.*next: step 0"):
        get.source(gr.load(m, g), d)
    _write_steps(m, g, "9")
    with pytest.raises(ge.ExportRefused, match="waits for approval"):
        get.source(gr.load(m, g), d)
    rec = gr.load(m, g)
    (tmp_path / "approved.json").write_text(json.dumps({"approved": {f"garment/{gr.piece(m, g, '9')}": {
        "model": f"{gr.path(m, g)}#{rec['steps']['9']['digest']}"}}}))
    with pytest.raises(ge.ExportRefused):  # approved, but nothing built to export
        get.source(gr.load(m, g), d)
    (d / "built.pkl").write_bytes(b"x")
    p, what = get.source(gr.load(m, g), d)
    assert p.name == "built.pkl" and "step 9 approved" in what
    (d / "final.pkl").write_bytes(b"x")
    assert get.source(gr.load(m, g), d)[0].name == "final.pkl"
    gr.write(m, g, "10", "done", output={"glb": "x.glb", "triangles": 10}, gate={"verdict": "PASS", "rows": []})
    s = gr.states(gr.load(m, g))
    assert s["10"]["ready"] and gr.load(m, g)["steps"]["10"]["output"]["glb"] == "x.glb"


def test_budget_role_refused_by_name():
    with pytest.raises(ge.ExportRefused, match="role 'nobody'"):
        ge.budget_for("nobody")
    assert ge.budget_for("main_npc") == 12000
