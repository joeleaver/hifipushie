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


def test_loops_follow_the_outline_quad_dominant_seams_shared():
    """garment_loops: rings parallel to every border, quads, the seam still shared, UVs still the pattern."""
    from scipy.spatial import cKDTree
    from hifipushie import garment_loops as gl
    r = tiny_result()
    g, _ = ge.fit_budget(ge.drape_of(r), r["M"], 1500, body=r["bV"], joints={})
    o = g["outer"]
    assert o["quad_share"] >= 0.7 and g["missing_boundary_edges"] == 0
    hp = ge.piece_h(r["M"], g["h"])
    U = o["uv_pattern"][o["piece"] == 0]
    d = np.min(np.stack([U[:, 0], 0.3 - U[:, 0], U[:, 1], 0.4 - U[:, 1]]), 0)  # distance to piece a's border
    h = hp["a"]
    for k in range(1, gl.LOOP_RINGS + 1):  # ring k: a row of vertices k h in from the border all round
        on = np.abs(d - k * h) < 0.08 * h
        assert on.sum() >= 0.8 * (2 * (0.3 + 0.4) - 8 * k * h) / h
    # the ring's consecutive points are mesh edges (a loop, not just points)
    E = set(map(tuple, np.sort(np.concatenate([o["T"][:, [0, 1]], o["T"][:, [1, 2]], o["T"][:, [2, 0]]]), 1).tolist()))
    idx = np.flatnonzero(o["piece"] == 0)[np.abs(d - h) < 0.08 * h]
    P = o["uv_pattern"][idx]
    nb = cKDTree(P).query(P, k=2)[1][:, 1]
    assert np.mean([(min(a, b), max(a, b)) in E for a, b in zip(idx, idx[nb])]) > 0.9
    on = np.isclose(o["uv_pattern"][:, 0], 0.3, atol=1e-6)
    A, B = o["V"][on & (o["piece"] == 0)], o["V"][on & (o["piece"] == 1)]
    assert len(A) == len(B) and np.allclose(A[np.argsort(A[:, 2])], B[np.argsort(B[:, 2])])
    st = ge.uv_stretch(o)
    assert 0.97 < st["p5"] and st["p95"] < 1.01


def _sheet(nx, ny, w, h, z):
    U, F = _grid(nx, ny, w, h)
    return np.c_[U[:, 0] - w / 2, U[:, 1], np.full(len(U), z)], F


def test_projected_weights_smoothed_do_not_jump_between_neighbours():
    """A two-bone body whose weights STEP at x = 0; cloth 3 cm off it: the projection alone jumps across one edge,
    the geodesic smoothing spreads it over the radius."""
    from hifipushie import garment_bend as gb
    bV, bT = _sheet(41, 11, 0.8, 0.2, 0.0)
    ref = np.c_[(bV[:, 0] < 0).astype(float), (bV[:, 0] >= 0).astype(float)]
    gV, gT = _sheet(33, 9, 0.64, 0.16, 0.03)
    gV[:, 1] += 0.02
    E = gb.edges_of(gT)
    D0, _ = gb.transfer(bV, bT, ref, gV, gT, 0.02, smooth=False)
    D1, info = gb.transfer(bV, bT, ref, gV, gT, 0.02, smooth=True)
    j0 = 0.5 * np.abs(D0[E[:, 0]] - D0[E[:, 1]]).sum(1).max()
    j1 = 0.5 * np.abs(D1[E[:, 0]] - D1[E[:, 1]]).sum(1).max()
    assert info["geo_radius_m"] >= gb.GEO_R_MIN and j0 > 0.9 and j1 < 0.5
    assert np.allclose(D1.sum(1), 1, atol=1e-9)


def test_bend_check_fails_a_kink_and_passes_a_smooth_bend():
    """Two bones turning at x = 0 by 40 deg: garment weights that STEP there kink (one sharp new crease); the same
    smooth ramp as the body's bends cleanly."""
    from hifipushie import garment_bend as gb
    bones = [{"name": "root", "head": np.zeros(3), "parent": -1}, {"name": "b1", "head": np.zeros(3), "parent": 0}]
    bV, bT = _sheet(41, 11, 0.8, 0.2, -0.002)  # (a close fit: 2 mm off; farther off, the outer layer of a bend is
    gV, gT = _sheet(41, 11, 0.8, 0.2, 0.0)     # longer than the skin's by stand-off x curvature, and that is strain)

    def jw(V, ramp):
        w1 = np.clip(0.5 + V[:, 0] / ramp, 0, 1) if ramp else (V[:, 0] > 0).astype(float)
        return np.c_[np.zeros(len(V), int), np.ones(len(V), int), np.zeros((len(V), 2), int)], np.c_[1 - w1, w1, np.zeros((len(V), 2))]
    bJ, bW = jw(bV, 0.2)
    turn = {"bend": {"b1": ([0, 1, 0], 40.0)}}
    sJ, sW = jw(gV, 0.2)
    ok = gb.deformation(bones, gV, gT, sJ, sW, bV, bT, bJ, bW, turn)
    assert ok["ok"] and ok["poses"]["bend"]["new_creases"] == 0
    kJ, kW = jw(gV, 0)
    bad = gb.deformation(bones, gV, gT, kJ, kW, bV, bT, bJ, bW, turn)
    assert not bad["ok"] and bad["poses"]["bend"]["new_creases"] > 0
    assert bad["limits"]["crease_deg"] == gb.CREASE_FLOOR  # a flat sheet's sharpest rest fold is below the floor


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
    with pytest.raises(gr.OrderRefused):  # (T14) the export consumes the appearance step (9a)
        gr.write(m, g, "10", "done", output={"glb": "x.glb"})
    gr.write(m, g, "9a", "done", output={"textures": {}})
    gr.write(m, g, "10", "done", output={"glb": "x.glb", "triangles": 10}, gate={"verdict": "PASS", "rows": []})
    s = gr.states(gr.load(m, g))
    assert s["10"]["ready"] and gr.load(m, g)["steps"]["10"]["output"]["glb"] == "x.glb"


def test_budget_role_refused_by_name():
    with pytest.raises(ge.ExportRefused, match="role 'nobody'"):
        ge.budget_for("nobody")
    assert ge.budget_for("main_npc") == 12000


# ---------------------------------------------------------------- the LODs (C439)

def test_a_lod_is_the_same_regrid_coarser_with_fewer_rows_on_the_stiff_pieces():
    from hifipushie import budgets
    plan = ge.lod_plan("main_npc")
    assert [p["lod"] for p in plan] == [1, 2, 3] and [p["budget"] for p in plan] == [3000, 1320, 600]
    assert [p["share"] for p in plan] == budgets.lod_ratios("clothing")[1:]  # what asset_export gives a part below the neck
    assert [p["rows"] for p in plan] == [4, 2, 1] and [p["screen"] for p in plan] == [0.5, 0.25, 0.12]
    assert all(ge.H_MAX < p["h_max"] <= ge.H_MAX_LOD for p in plan) and plan[0]["h_max"] < plan[2]["h_max"]
    r = tiny_result()
    drape = ge.drape_of(r)
    g0, _ = ge.fit_budget(drape, r["M"], 1500, body=r["bV"], joints={})
    g1, tries = ge.fit_budget(drape, r["M"], 375, body=r["bV"], joints={}, rows=4, h_max=0.08)
    assert len(g1["T"]) <= 375 < len(g0["T"]) and ge.H_MAX < g1["h"] <= 0.08 and g1["missing_boundary_edges"] == 0
    assert all(h <= 0.08 for h, _ in tries)
    # the stiff piece: 4 rows across at the LOD, where LOD0 keeps MADE_MIN_ROWS
    assert ge.piece_h(r["M"], 0.08, 4)["b"] == pytest.approx(0.3 / 4) and ge.piece_h(r["M"], 0.08)["b"] == pytest.approx(0.3 / 8)
    # still the pattern: the seam shared exactly, the uv the pattern's, lengths kept
    o = g1["outer"]
    on = np.isclose(o["uv_pattern"][:, 0], 0.3, atol=1e-6)
    A, B = o["V"][on & (o["piece"] == 0)], o["V"][on & (o["piece"] == 1)]
    assert len(A) == len(B) >= 2 and np.allclose(A[np.argsort(A[:, 2])], B[np.argsort(B[:, 2])])
    assert np.allclose(o["V"][:, 2], o["uv_pattern"][:, 1], atol=1e-6) and g1["uv"].min() >= -1e-9 and g1["uv"].max() <= 1 + 1e-9


def _piece(T):
    """A unit square's outline (4 border vertices) and one inner vertex, triangulated by T."""
    uv = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.5, 0.4]])
    return {"T": np.array(T), "uv": uv, "gid": np.array([0, 1, 2, 3, -1]), "tris": np.array(T), "missing_boundary_edges": 2}


def test_a_corner_the_triangulation_dropped_is_put_back():
    """remesh_loops drops every triangle on a chord close to the outline: at a coarse grid that cut the shirt's hem
    corner off and left a hole at the side seam. The corner triangle comes back, with the one behind its chord."""
    p = _piece([[0, 1, 4], [1, 2, 4], [2, 0, 4]])  # vertex 3 in no triangle; its chord 2-0 is a mesh edge
    assert ge.close_corners(p) == 1 and p["missing_boundary_edges"] == 0 and p["T"][-1].tolist() == [2, 3, 0]
    p = _piece([[0, 1, 4], [1, 2, 4]])  # ... and the triangle behind the chord is gone too
    assert ge.close_corners(p) == 1 and p["missing_boundary_edges"] == 0
    assert p["T"][-2:].tolist() == [[2, 3, 0], [2, 0, 4]] and len(p["tris"]) == 4
    d1, d2 = p["uv"][p["T"][:, 1]] - p["uv"][p["T"][:, 0]], p["uv"][p["T"][:, 2]] - p["uv"][p["T"][:, 0]]
    assert 0.5 * (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]).sum() == pytest.approx(1.0)  # the square exactly, one winding
    q = _piece([[1, 0, 4], [2, 1, 4]])  # the other winding stays the other winding
    assert ge.close_corners(q) == 1 and q["T"][-2:].tolist() == [[0, 3, 2], [4, 0, 2]]
    full = _piece([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
    assert ge.close_corners(full) == 0 and len(full["T"]) == 4


def _ball(c, r, n=8):
    """A closed ball of 2 n (n - 1) triangles."""
    th, ph = np.linspace(0, np.pi, n + 1)[1:-1], np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = [[0, 0, r]] + [[r * np.sin(t) * np.cos(p), r * np.sin(t) * np.sin(p), r * np.cos(t)] for t in th for p in ph] + [[0, 0, -r]]
    F, last = [], len(V) - 1
    for j in range(n):
        k = (j + 1) % n
        F.append([0, 1 + j, 1 + k])
        F.append([last, 1 + (n - 2) * n + k, 1 + (n - 2) * n + j])
        for i in range(n - 2):
            a, b, c2, d = 1 + i * n + j, 1 + i * n + k, 1 + (i + 1) * n + k, 1 + (i + 1) * n + j
            F += [[a, d, c2], [a, c2, b]]
    return np.array(V) + c, np.array(F)


def test_details_at_a_lod_small_ones_left_out_the_rest_simplified_and_seated_on_its_cloth():
    Va, Fa = _ball([0.2, 0.2, 0.005], 0.005)  # a 1 cm button
    Vb, Fb = _ball([0.6, 0.6, 0.03], 0.03)    # a 6 cm one, in the same detail
    det = {"buttons": {"V": np.vstack([Va, Vb]), "F": np.vstack([Fa, Fb + len(Va)]), "colour": "#102030"}}
    out, info = ge.lod_details(det, 0.25, 100.0)  # 100 px / m: 1 px and 6 px
    assert info["buttons"]["pieces"] == 2 and info["buttons"]["kept"] == 1
    x = out["buttons"]
    assert ge.DETAIL_MIN_TRIS <= len(x["F"]) < len(Fb) and info["buttons"]["triangles"] == len(x["F"])
    assert np.linalg.norm(x["V"].mean(0) - [0.6, 0.6, 0.03]) < 0.01 and x["colour"] == "#102030"
    assert ge.lod_details(det, 0.25, 10.0) == ({}, {"buttons": {**info["buttons"], "kept": 0, "triangles": 0, "px": 0.4}})
    both, info2 = ge.lod_details(det, 1.0, 1000.0)  # close: everything, as made
    assert info2["buttons"]["kept"] == 2 and len(both["buttons"]["F"]) == len(Fa) + len(Fb)
    assert "1 of 2 kept" in ge.details_text(info) and "left out" in ge.details_text({"b": {**info["buttons"], "kept": 0}})
    # the LOD's cloth lies 1 cm under LOD0's there (a coarser grid's chords sink): the button goes down with it
    sq = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
    T = np.array([[0, 1, 2], [0, 2, 3]])
    z0 = x["V"][:, 2].copy()
    ge.seat_details(out, sq, T, sq - [0, 0, 0.01], T)
    assert np.allclose(x["V"][:, 2], z0 - 0.01) and np.allclose(ge.closest([[0.3, 0.3, 0.5]], sq, T), [[0.3, 0.3, 0.0]])


def test_gate_rows_have_one_name_key_and_the_record_keeps_it():
    """Step 10 named its rows "row", the record keeps "id": a failed export's rows reached the record without names."""
    r = tiny_result()
    g, _ = ge.fit_budget(ge.drape_of(r), r["M"], 1500, body=r["bV"])
    st = ge.uv_stretch(g["outer"])
    bend = {"limits": {"strain_p99": 0.1, "crease_deg": 30.0},
            "poses": {"arm_raised_45": {"ok": False, "strain_p99": 0.2, "new_creases": 3, "crease_where": "armpit"}}}
    lod = [{"lod": 1, "open_edges": 0, "triangles": 400, "budget": 375, "share": 0.25},
           {"lod": 2, "open_edges": 2, "triangles": 100, "budget": 165, "share": 0.11}]
    rows = ge.gate_rows(g, 0, 1500, st, bend, st, lod)
    assert all("id" in x and "row" not in x for x in rows)
    kept = [gr._row(x) for x in rows]
    assert [x["id"] for x in kept] == ["triangles", "uv stretch vs the drape (informational)", "open pattern edges",
                                       "bends cleanly: arm_raised_45", "LOD1 open pattern edges",
                                       "LOD1 triangles vs its share (informational)", "LOD2 open pattern edges",
                                       "LOD2 triangles vs its share (informational)"]
    assert [x["status"] for x in kept] == ["PASS", "INFO", "PASS", "FAIL", "PASS", "INFO", "FAIL", "INFO"]  # over a share: information


def test_the_next_line_names_the_way_onto_the_character():
    from hifipushie import garment_export_tool as get
    t = get.next_line("cf", "main_npc", "PASS", 3, True)
    assert t.startswith("next: ") and 'export_asset("cf", "<out_dir>", role="main_npc", rig=True)' in t
    assert "3 LOD file(s)" in t and "FAIL row" not in t and "WARNING" not in t
    f = get.next_line("cf", "hero", "FAIL", 3, True)
    assert "a FAIL row names what to change" in f and 'role="hero"' in f and "ships with a WARNING" in f
    assert "until step 9 (the look) is approved" in get.next_line("cf", "hero", "PASS", 3, False)


def test_the_tool_writes_one_file_per_lod_and_records_each(tmp_path, monkeypatch):
    """export_garment's LOD files: <garment>_LOD<k>.glb at each LOD's share, counted, with the details the LOD keeps."""
    from hifipushie import garment_export_tool as get
    r = tiny_result()
    drape, M, bV = ge.drape_of(r), r["M"], r["bV"]
    rb = [{"name": "root", "head": np.zeros(3), "parent": -1}]
    monkeypatch.setattr(get.gb, "skin", lambda spec, rb, V, T, h, smooth=True: (
        np.zeros((len(V), 4), int), np.c_[np.ones(len(V)), np.zeros((len(V), 3))], {}))
    Vb, Fb = _ball([0.1, -0.26, 0.2], 0.01)
    details = {"buttons": {"V": Vb, "F": Fb, "colour": "#202020"}}
    g0, _ = ge.fit_budget(drape, M, 12000, len(Fb), body=bV, joints={})
    (tmp_path / "shirt_LOD7.glb").write_bytes(b"stale")
    bT = np.array([[i, i + 1, i + 2] for i in range(0, len(bV) - 2, 3)])  # (a thread of a body: nothing to lift off)
    entries, lines = get.lods("shirt", {"steps": {"9a": {}}}, "main_npc", {}, rb, drape, M, bV, bT, details,
                              [0.5, 0.5, 0.5], g0, tmp_path)
    assert [e["lod"] for e in entries] == [1, 2, 3] and not (tmp_path / "shirt_LOD7.glb").exists()
    assert len(lines) == 4 and "never a decimation" in lines[0]
    last = len(g0["T"])
    for e, ln in zip(entries, lines[1:]):
        f = tmp_path / f"shirt_LOD{e['lod']}.glb"
        assert e["glb"] == str(f) and f.exists() and ln.strip().startswith(f"LOD{e['lod']}: {f.name} {e['triangles']} triangles")
        assert sum(e["counts"].values()) == e["triangles"] <= e["budget"] and e["open_edges"] == 0
        assert e["counts"]["shirt"] < last and e["rows"] == ge.lod_plan("main_npc")[e["lod"] - 1]["rows"]
        last = e["counts"]["shirt"]
        m = glbw.read_counts(f)
        assert m == e["counts"] and ("shirt_buttons" in m) == bool(e["details"]["buttons"]["kept"])


@pytest.mark.parametrize("flip", [False, True])
def test_a_seam_whose_one_side_is_several_stretches_is_shared_on_both_sides(flip):
    """One strip's edge sewn to TWO pieces in one seam (a sleeve cap to front and back; flipped: a cuff to a sleeve end
    cut in two). Keyed by the whole seam, the single side's stretches were not found again: resampled as free edges
    with a rim, an open loop that only read closed while the grid was fine."""
    from hifipushie import garment_game as gg
    Ua, Fa = _grid(17, 5, 0.4, 0.1)
    Ub, Fb = _grid(9, 5, 0.2, 0.1)
    Uc, Fc = _grid(9, 5, 0.2, 0.1, x0=0.2)
    uv = np.vstack([Ua, Ub + [0.0, 0.2], Uc + [0.0, 0.2]])  # (the pattern lays b and c apart from a)
    X = np.vstack([np.c_[Ua[:, 0], 0 * Ua[:, 0], Ua[:, 1]], np.c_[Ub[:, 0], 0 * Ub[:, 0], Ub[:, 1] + 0.1],
                   np.c_[Uc[:, 0], 0 * Uc[:, 0], Uc[:, 1] + 0.1]])  # (worn: b and c stand on a's top edge)
    piece = np.r_[np.zeros(len(Ua), int), np.ones(len(Ub), int), np.full(len(Uc), 2)]
    F = np.vstack([Fa, Fb + len(Ua), Fc + len(Ua) + len(Ub)])
    top = np.flatnonzero((piece == 0) & np.isclose(uv[:, 1], 0.1))
    pairs = []
    for k in (1, 2):
        low = np.flatnonzero((piece == k) & np.isclose(uv[:, 1], 0.2))
        for j in low:
            i = top[np.argmin(np.abs(X[top, 0] - X[j, 0]))]
            pairs.append((j, i) if flip else (i, j))
    M = {"uv": uv, "F": F, "piece": piece, "names": ["a", "b", "c"], "sew": np.array(pairs),
         "sew_seam": np.zeros(len(pairs), int), "made": [], "folds": []}
    drape = ge.drape_of({"X": X, "M": M})
    bd = gg.boundaries(drape, 0.05)
    assert int((~bd["a"]["free"]).sum()) == 8 and int((~bd["b"]["free"]).sum()) == 4 == int((~bd["c"]["free"]).sum())
    for n in "bc":  # the same samples on both sides: ids and points
        both = np.intersect1d(bd["a"]["gid"], bd[n]["gid"])
        assert len(both) >= 3  # (a run's last sample is the next run's first: counted there)
        ia = [list(bd["a"]["gid"]).index(g) for g in both]
        ib = [list(bd[n]["gid"]).index(g) for g in both]
        assert np.allclose(bd["a"]["loop3d"][ia], bd[n]["loop3d"][ib])
    g = ge.game_mesh(drape, M, 0.05, joints={})
    o = g["outer"]
    e = np.sort(o["weld"][np.concatenate([o["T"][:, [0, 1]], o["T"][:, [1, 2]], o["T"][:, [2, 0]]])], 1)
    u, c = np.unique(e, axis=0, return_counts=True)
    P = np.zeros((o["weld"].max() + 1, 3))
    P[o["weld"]] = o["V"]
    open_len = np.linalg.norm(P[u[c == 1][:, 0]] - P[u[c == 1][:, 1]], axis=1).sum()
    assert open_len == pytest.approx(1.2, abs=1e-6) and g["missing_boundary_edges"] == 0  # the 0.4 x 0.2 outline, no slit
    assert g["rim_faces"] == 2 * int((c == 1).sum())  # rims on the outline only


def test_a_lods_cloth_is_lifted_clear_of_the_body_its_flat_faces_cut():
    """Cloth wrapped 5 mm off a round body, on a grid so coarse its faces are chords THROUGH the body: every face is
    lifted until its points are outside; a fine grid, and cloth far off the body, are left alone."""
    n, R = 48, 0.1
    th, z = np.linspace(0, 2 * np.pi, n, endpoint=False), np.linspace(-0.3, 0.3, 13)
    bV = np.array([[R * np.cos(a), R * np.sin(a), zz] for zz in z for a in th])
    q = np.arange(len(bV)).reshape(len(z), n)
    a, b, c, d = q[:-1], np.roll(q[:-1], -1, 1), np.roll(q[1:], -1, 1), q[1:]
    bT = np.concatenate([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])  # outward

    def sleeve(k, scale=1.0):  # k faces round, the corners on the cloth's own circle (5 mm off the body)
        t2, z2 = np.linspace(0, 2 * np.pi, k, endpoint=False), np.linspace(-0.2, 0.2, 5)
        V = np.array([[scale * (R + 0.005) * np.cos(x), scale * (R + 0.005) * np.sin(x), zz] for zz in z2 for x in t2])
        g = np.arange(len(V)).reshape(len(z2), k)
        a, b, c, d = g[:-1], np.roll(g[:-1], -1, 1), np.roll(g[1:], -1, 1), g[1:]
        T = np.concatenate([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])
        return {"V": V, "T": T, "weld": np.arange(len(V)), "N": None}
    m = sleeve(5)  # five faces round: each chord's middle is 15 mm UNDER the skin
    r0 = np.hypot(m["V"][:, 0], m["V"][:, 1]).copy()
    info = ge.clear_body(m, bV, bT)
    mid = np.einsum("sk,tkc->tsc", ge._S, m["V"][m["T"]]).reshape(-1, 3)
    assert info["under"] == 0 and np.hypot(mid[:, 0], mid[:, 1]).min() >= R  # every face point outside the body now
    assert info["lifted"] == len(m["V"]) and 0.01 < info["most_m"] <= ge.LOD_CLEAR_MAX
    assert np.all(np.hypot(m["V"][:, 0], m["V"][:, 1]) > r0) and np.allclose(np.linalg.norm(m["N"], axis=1), 1.0)
    fine = sleeve(48)  # as fine as the body: nothing cuts, nothing moves
    V0 = fine["V"].copy()
    assert ge.clear_body(fine, bV, bT)["lifted"] == 0 and np.array_equal(fine["V"], V0)
    far = sleeve(5, 3.0)  # cloth 20 cm off the body (a collar's fall): out of reach, not touched
    assert ge.clear_body(far, bV, bT) == {"lifted": 0, "most_m": 0.0, "under": 0, "points": 0}
