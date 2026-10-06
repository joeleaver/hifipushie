"""Closures (closures.py): a lap held by fastenings, from one design entry. No sim.
uv run python tests/test_closures.py"""
import numpy as np

from hifipushie import closures


def _pieces():
    sq = lambda x0: np.array([[x0, 0.0], [x0 + 0.2, 0.0], [x0 + 0.2, -0.6], [x0, -0.6]])
    mk = lambda x, pre: {f"{pre}{n}": np.array([x, -0.1 * n]) for n in (1, 2, 3)}
    over = {"P": sq(0.0), "names": {"top": 0, "tr": 1, "br": 2, "bottom": 3}, "marks": mk(0.015, "buttonhole")}
    under = {"P": sq(-0.2), "names": {"tl": 0, "top": 1, "bottom": 2, "bl": 3}, "marks": mk(-0.009, "button")}
    return {"front.L": over, "front.R": under}


ENTRY = {"name": "front", "kind": "buttons", "over": "front.L", "under": "front.R",
         "edge": {"over": "bottom>top", "under": "top>bottom"}, "band": {"over": 0.03, "under": 0.018}}


def test_one_entry_makes_stitches_and_band_rows():
    st, folds, seams, out = closures.expand([ENTRY], _pieces())
    assert st == [[f"front.L:buttonhole{n}", f"front.R:button{n}"] for n in (1, 2, 3)]
    assert [f["piece"] for f in folds] == ["front.L", "front.R"] and all(f["angle"] == 180 and f["in_wrap"] for f in folds)
    assert not seams and out[0]["pairs"][0] == ("buttonhole1", "button1") and out[0]["closed"] == [True] * 3


def test_states():
    st, _, _, out = closures.expand([dict(ENTRY, state="open")], _pieces())
    assert not st and out[0]["closed"] == [False] * 3  # open: nothing sewn, the buttons still exist
    st, _, _, out = closures.expand([dict(ENTRY, state={"open_above": "buttonhole2"})], _pieces())
    assert len(st) == 2 and out[0]["closed"] == [False, True, True]  # the top button undone


def test_a_chosen_closure_must_be_in_the_pattern():
    pcs = _pieces()
    pcs["front.R"]["marks"] = {}
    try:
        closures.expand([ENTRY], pcs)
    except closures.ClosureError as e:
        assert "no fastenings" in str(e)
    else:
        raise AssertionError("a closure with no buttons was accepted")
    try:
        closures.validate([dict(ENTRY, snaps=3)])
    except closures.ClosureError:
        pass
    else:
        raise AssertionError("unknown key accepted")
    assert closures.expand([dict(ENTRY, over="gone")], _pieces())[3] == []  # a dropped piece's closure leaves with it


def test_measure_and_buttons():
    _, _, _, out = closures.expand([ENTRY], _pieces())
    marks = {f"front.L:buttonhole{n}": n - 1 for n in (1, 2, 3)}
    marks.update({f"front.R:button{n}": n + 2 for n in (1, 2)})  # button3's vertex lost in the mesh
    M = {"closures": closures.resolve(out, marks, {}), "F": np.array([[0, 1, 2], [3, 4, 5]])}
    V = np.array([[0, 0, 0.002], [0, 0.1, 0.002], [0.1, 0, 0.002], [0, 0, 0.0], [0, 0.1, 0.02], [0.1, 0, 0]], float)
    r = closures.measure(V, M)[0]
    assert r["fastenings"] == 2 and r["lost"] == 1 and not r["ok"]  # one lost, and one 18 mm apart
    assert r["gap_mm"] == [2.0, 18.0] and "LOST" in closures.text([r])
    b = closures.buttons_mesh(V, M, None)
    assert b["V"].shape[1] == 3 and b["F"].max() < len(b["V"]) and len(set(b["at"])) == 2
    rad = np.linalg.norm(b["V"][b["at"] == 0] - V[0], axis=1).max()
    assert 0.005 < rad < 0.0075  # an 11 mm button


def _grid(x0, x1, n=21, m=61):
    xs, ys = np.meshgrid(np.linspace(x0, x1, n), np.linspace(0, -0.6, m))
    uv = np.c_[xs.ravel(), ys.ravel()]
    i = np.arange(n * m).reshape(m, n)
    q = np.c_[i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, 1:].ravel(), i[1:, :-1].ravel()]
    return uv, np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]]


def test_a_closed_lap_is_laid_closed():
    """The solver leaves a lap its contact gap proud (5 mm here) and the buttons a few mm apart in the surface: seat
    lays the over band 1.2 mm off the under layer between the fastenings and brings each fastening's sides together;
    away from the band and beyond the last button the cloth stays where the sim left it."""
    pcs = _pieces()
    _, _, _, out = closures.expand([ENTRY], pcs)
    uo, Fo = _grid(0.0, 0.2)
    uu, Fu = _grid(-0.2, 0.0)
    uv = np.r_[uo, uu]
    F = np.r_[Fo, Fu + len(uo)]
    piece = np.r_[np.zeros(len(uo), int), np.ones(len(uu), int)]
    # world: x across, z down the front, y = depth (out = -y). The under front shifted 3 cm under the over front
    V = np.c_[uv[:, 0], np.zeros(len(uv)), uv[:, 1]]
    V[piece == 1, 0] += 0.03
    V[piece == 0, 1] -= 0.005
    near = lambda k, p: int(np.where(piece == k)[0][np.argmin(np.linalg.norm(uv[piece == k] - p, axis=1))])
    marks = {f"front.L:buttonhole{n}": near(0, pcs["front.L"]["marks"][f"buttonhole{n}"]) for n in (1, 2, 3)}
    marks.update({f"front.R:button{n}": near(1, pcs["front.R"]["marks"][f"button{n}"]) for n in (1, 2, 3)})
    M = {"closures": closures.resolve(out, marks, {}), "F": F, "piece": piece, "uv": uv, "names": ["front.L", "front.R"]}
    before = closures.measure(V, M)[0]
    X, rows = closures.seat(V, M, pcs, None)
    after = closures.measure(X, M)[0]
    assert before["gap_max_mm"] > 6 and after["gap_max_mm"] < 2.0 and after["ok"], (before, after)
    band = (piece == 0) & (uv[:, 0] < 0.028) & (uv[:, 1] < -0.1) & (uv[:, 1] > -0.3)
    assert np.abs(np.abs(X[band, 1]) - closures.LAY).max() < 4e-4  # the band lies 1.2 mm off the under front
    far = (piece == 0) & (uv[:, 0] > 0.12)
    below = (piece == 0) & (uv[:, 1] < -0.4)
    assert np.abs(X[far] - V[far]).max() < 1e-4 and np.abs(X[below] - V[below]).max() < 1e-4
    assert rows[0]["laid"] > 50 and rows[0]["fastenings_left_mm"] == [0.0, 0.0, 0.0]


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
