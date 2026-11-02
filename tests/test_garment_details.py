"""Step 7, details and trims (T10, C290): marks on a synthetic flat pattern anchored barycentrically and carried onto a
deformed copy; an edge-following trim; rows; refusals (positions at step 7, unknown names, outside the piece, unmarked,
cloth-made); the marks' validation at step 4; the record write (7 + 7a) and chain_presim's step-7 hook. Cheap: no
builds, no renders."""
import json
import pickle

import numpy as np
import pytest
from PIL import Image

from hifipushie import draft_own, garment_details as gd, garment_details_tool as gdt, garment_record as gr, store


def _grid(x0, w=0.2, h=0.4, s=0.01):
    nx, ny = int(round(w / s)) + 1, int(round(h / s)) + 1
    u, v = np.meshgrid(np.linspace(0, w, nx), np.linspace(0, h, ny))
    uv = np.c_[u.ravel() + x0, v.ravel()]
    F = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            F += [[a, a + 1, a + nx + 1], [a, a + nx + 1, a + nx]]
    return uv, np.asarray(F), nx


def flat_M():
    """Two 200 x 400 mm pieces, front.L and front.R, each with corner points a (top left), b (bottom left), c and
    marks button1..3 down the left side."""
    uvs, Fs, pc, pts = [], [], [], {}
    o = 0
    for k, (p, x0) in enumerate((("front.L", 0.0), ("front.R", 0.5))):
        uv, F, nx = _grid(x0)
        ny = len(uv) // nx
        idx = lambda i, j: o + j * nx + i
        pts.update({f"{p}:a": idx(0, ny - 1), f"{p}:b": idx(0, 0), f"{p}:c": idx(nx - 1, 0)})
        pts.update({f"{p}:button{n}": idx(5, 10 * n) for n in (1, 2, 3)})
        uvs.append(uv)
        Fs.append(F + o)
        pc += [k] * len(uv)
        o += len(uv)
    return {"uv": np.concatenate(uvs), "F": np.concatenate(Fs), "piece": np.asarray(pc), "names": ["front.L", "front.R"],
            "points": pts, "marks": {}, "closures": []}


def bent(X):
    """The flat layout rolled round a cylinder (R 0.15 m about the y axis): a stand-in for the build."""
    R = 0.15
    return np.c_[R * np.sin(X[:, 0] / R), X[:, 1], R * np.cos(X[:, 0] / R)]


INV = {"on": ["front.L", "front.R"]}


def test_point_follows_the_cloth():
    M = flat_M()
    fl = gd.Flat(M)
    d = gd.place(fl, "btn", {"piece": "front.L", "at": [{"point": "b", "dx": 50, "dy": 100}]},
                 {"kind": "point", "size_mm": 12, "thickness_mm": 3, "shape": "disc"}, INV)
    assert d["count"] == 1 and "front.L:b +50,+100 mm" in d["where"][0]
    X0 = gd.flat_positions(M)
    V0, _ = gd.carry(d["instances"], X0, M)
    assert np.allclose(V0[:, :2].mean(0), [0.05, 0.1], atol=1e-3)  # (on the flat layout: where it was marked)
    X1 = bent(X0)
    V1, _ = gd.carry(d["instances"], X1, M)
    want = bent(np.array([[0.05, 0.1, 0.0]]))[0]
    n = want * [1, 0, 1] / np.linalg.norm(want * [1, 0, 1])
    c = V1.mean(0)
    assert np.linalg.norm((c - want) - ((c - want) @ n) * n) < 0.002  # rides the bent cloth at its mark
    assert 0 < (c - want) @ n < 0.004  # on the outside, its own thickness off the surface
    assert np.ptp(V1 @ n) < 0.005 and np.ptp(V1[:, 1]) > 0.011  # lies flat on the surface, 12 mm across


def test_trim_follows_an_edge():
    M = flat_M()
    fl = gd.Flat(M, {"front.L": {"cf": "a>b"}})
    d = gd.place(fl, "bind", {"follows": ["front.L:cf"]}, {"kind": "line", "width_mm": 8}, INV, {"thickness_mm": 1.5})
    it = d["instances"][0]
    assert d["count"] == 1 and abs(it["length"] - 0.4) < 0.002
    assert np.allclose(it["C"][:, 0], 0.004, atol=1e-4)  # inset half its width: its outer side on the edge
    V, F = gd.carry(d["instances"], bent(gd.flat_positions(M)), M)
    assert len(F) and np.isfinite(V).all() and abs(it["thick"] - 0.0015) < 1e-9


def test_rows_mirror_and_motif():
    M = flat_M()
    fl = gd.Flat(M, {p: {"cf": "a>b"} for p in ("front.L", "front.R")})
    mark = {"piece": "front.L", "mirror": True, "rows": {"edge": "cf", "count": 4, "from_mm": 50, "pitch_t": 0.2, "in": 20},
            "lines": [[[0, -5], [60, -5]], [[0, 5], [60, 5]]], "knots": [[65, 0]]}
    d = gd.place(fl, "frog", mark, {"kind": "motif", "width_mm": 3, "size_mm": 8}, INV)
    assert d["count"] == 8 and d["pieces"] == ["front.L", "front.R"]
    assert "4 rows from 50 mm, pitch 80.0 mm (0.200 of the edge), in 20 mm" in d["where"][0]
    knots = [i for i in d["instances"] if i["kind"] == "point" and i["piece"] == "front.L"]
    assert np.allclose(sorted(k["uv"][1] for k in knots), [0.11, 0.19, 0.27, 0.35], atol=1e-3)  # down from a (top)
    assert np.allclose([k["uv"][0] for k in knots], 0.085, atol=1e-3)  # 20 mm in + 65 across


def test_refusals():
    M = flat_M()
    fl = gd.Flat(M)
    with pytest.raises(gd.DetailRefused, match="marked on the pattern at step 4"):
        gd.place(fl, "b", {"piece": "front.L", "points": "button*"}, {"kind": "point", "size_mm": 9, "at": []}, INV)
    with pytest.raises(gd.DetailRefused, match="not on the pattern"):
        gd.place(fl, "b", {"piece": "front.L", "at": [{"point": "nope"}]}, {"kind": "point", "size_mm": 9}, INV)
    with pytest.raises(gd.DetailRefused, match="outside front.L"):
        gd.place(fl, "b", {"piece": "front.L", "at": [{"point": "b", "dx": -30}]}, {"kind": "point", "size_mm": 9}, INV)
    with pytest.raises(gd.DetailRefused, match="past the edge's end"):
        gd.place(fl, "b", {"piece": "front.L", "rows": {"edge": "a>b", "count": 9, "pitch_mm": 60}}, {"kind": "point", "size_mm": 9}, INV)
    with pytest.raises(gd.DetailRefused, match="the inventory puts it on"):
        gd.place(fl, "b", {"piece": "front.R", "points": "button*"}, {"kind": "point", "size_mm": 9}, {"on": ["front.L"]})
    assert gd.check_mark("x", {"piece": "front.L", "size_mm": 3})  # (geometry in a mark: refused)


def test_marks_validated_at_step4():
    step1 = {"details": {"btn": {"what": "button", "on": ["front.L"], "build": "full"},
                         "pkt": {"what": "patch pocket", "on": ["front.L"], "build": "full"},
                         "back": {"what": "braid", "on": ["front.L"], "build": "omit"}}}
    decl = {"pieces": {"front.L": {}}}
    bad = draft_own.validate_marks(decl, step1)
    assert len(bad) == 1 and "'btn'" in bad[0] and "has no mark" in bad[0]  # (the pocket is a piece; omitted: no mark)
    assert draft_own.validate_marks(dict(decl, marks={"btn": {"piece": "front.L", "points": "button*"}}), step1) == []
    assert any("not a step-1 detail" in b for b in draft_own.validate_marks(dict(decl, marks={"zz": {"at": []}}), step1))
    step1["closures"] = {"front": {"pieces": ["front.L"], "details": ["btn"]}}
    assert draft_own.validate_marks(dict(decl, closures=[{"name": "front", "kind": "buttons"}]), step1) == []


# ---------------------------------------------------------------- the record + the tool body
@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setenv("HIFIPUSHIE_APPROVED", str(tmp_path / "approved.json"))
    monkeypatch.delenv("HIFIPUSHIE_PRESIM_APPROVAL", raising=False)
    Image.new("RGB", (40, 60), (200, 40, 40)).save(tmp_path / "ref.png")
    monkeypatch.setattr(gdt, "render_look", lambda r, m, out, size=800: [str(tmp_path / "ref.png")])
    return tmp_path


def _record(home, marks):
    ddir = home / "decl"
    ddir.mkdir(exist_ok=True)
    (ddir / "declarations.json").write_text(json.dumps({"edges": {"front.L": {"cf": "a>b"}}, "marks": marks}))
    gr.write("m", "g", "0", "done", output={"kind": "jacket", "views": [{"image": str(home / "ref.png")}],
                                            "cloth": {"braid": {"colour": [210, 170, 60], "thickness_mm": 1.5}}})
    gr.write("m", "g", "1", "done", output={"details": {
        "buttons": {"what": "buttons", "on": ["front.L"], "count": 3, "build": "full"},
        "binding": {"what": "edge binding", "on": ["front.L"], "cloth": "braid", "count": 1, "build": "full"},
        "pocket": {"what": "patch pocket", "on": ["front.L"], "build": "full"},
        "back_braid": {"what": "braid", "on": ["front.L"], "build": "omit", "why": "unseen"}}, "closures": {}})
    for sid in ("2", "3"):
        gr.write("m", "g", sid, "done", output={"n": sid})
    gr.write("m", "g", "4", "done", output={"dir": str(ddir)})
    for sid in ("5", "6"):
        gr.write("m", "g", sid, "done", output={"n": sid})
    M = flat_M()
    X = bent(gd.flat_positions(M))
    bV = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float) * [0.1, 0.5, 0.1]
    bT = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                   [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    d = store.HOME / "m" / "chain" / "g_open"
    d.mkdir(parents=True, exist_ok=True)
    pickle.dump({"X": X, "M": M, "bV": bV, "bT": bT}, open(d / "built.pkl", "wb"))
    return d


MARKS = {"buttons": {"piece": "front.L", "points": "button*"}, "binding": {"follows": ["front.L:cf"]}}
GEOM = {"buttons": {"kind": "point", "size_mm": 11, "colour": [240, 240, 235]}, "binding": {"kind": "line", "width_mm": 6}}


def test_tool_writes_step7_and_7a(home):
    d = _record(home, MARKS)
    assert gdt.presim_step7("m", "g", {"build": "b1"})[1] is False  # (details inventoried, none placed: 7a waits)
    assert gr.load("m", "g")["steps"]["7"]["status"] == "todo"
    looks, txt = gdt.run("m", "g", GEOM)
    assert "PASS" in txt.splitlines()[0] and "buttons: 3 on front.L" in txt and "front.L:button1" in txt
    rec = gr.load("m", "g")
    assert rec["steps"]["7"]["status"] == "done" and rec["steps"]["7a"]["status"] == "done"
    assert set(rec["steps"]["7"]["output"]["details"]) == {"buttons", "binding"}
    saved = pickle.load(open(d / "details.pkl", "rb"))
    assert set(saved["built"]) == {"buttons", "binding"} and saved["built"]["binding"]["colour"] == [210, 170, 60]
    assert len(looks) == 2 and all(isinstance(p, str) for p in looks)


def test_tool_fails_and_refuses_by_name(home):
    _record(home, MARKS)
    _, txt = gdt.run("m", "g", {"buttons": GEOM["buttons"]}, look=False)
    assert "FAIL binding: not placed" in txt and gr.load("m", "g")["steps"]["7"]["status"] == "failed"
    for bad, why in (({"pocket": {"kind": "point", "size_mm": 9}}, "made of cloth"),
                     ({"back_braid": {"kind": "line", "width_mm": 3}}, "the inventory omits it"),
                     ({"zz": {"kind": "point", "size_mm": 9}}, "not in step 1's details"),
                     ({"buttons": dict(GEOM["buttons"], points="button*")}, "marked on the pattern at step 4")):
        _, txt = gdt.run("m", "g", bad, look=False)
        assert txt.startswith("garment_details REFUSED") and why in txt, txt


def test_unmarked_detail_is_a_step4_fail(home):
    _record(home, {"buttons": MARKS["buttons"]})
    _, txt = gdt.run("m", "g", {"buttons": GEOM["buttons"]}, look=False)
    assert "FAIL binding: no mark on the pattern" in txt
    _, txt = gdt.run("m", "g", GEOM, look=False)
    assert "binding: no mark on the pattern" in txt and "REFUSED" in txt
