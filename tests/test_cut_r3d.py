"""Step 6 takes its lengths from the toile (R3d, C495): planned folds along cut edges, each piece names the step-3 tapes it lies on, a declared
seam ease is kept as cut (never trued) and a ".L" ease serves ".R"."""
import json

import numpy as np

from hifipushie import cut_tapes, cut_tool


def plane(x0, x1, z0, z1, n=41, y=0.0):
    x, z = np.linspace(x0, x1, n), np.linspace(z0, z1, n)
    X, Z = np.meshgrid(x, z)
    V = np.dstack([X, np.full_like(X, y), Z]).reshape(-1, 3)
    idx = np.arange(n * n).reshape(n, n)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    return V, np.r_[np.c_[a, b, c], np.c_[a, c, d]]


def test_fold_rows_along_a_hem_and_mirror():
    edges = {"sleeve.L": {"hem": [3, 4, 5], "cap": [0, 1, 2]}, "sleeve.R": {"hem": [3, 4, 5], "cap": [0, 1, 2]}}
    out, bad = cut_tapes.folds({"folds": {"sleeve.L": {"sleeve_hem": "hem"}}}, edges)
    assert not bad
    assert {(f["piece"], f["name"], tuple(f["line"]), f["kind"]) for f in out} == {
        ("sleeve.L", "sleeve_hem", ("hem.a", "hem.b"), "press"), ("sleeve.R", "sleeve_hem", ("hem.a", "hem.b"), "press")}
    _, bad = cut_tapes.folds({"folds": {"sleeve.L": {"sleeve_hem": "cuff"}}}, edges)
    assert bad and "cuff" in bad[0]


def test_a_piece_names_the_tapes_it_lies_on():
    """Two sheets (front y = -0.1, back y = +0.1) crossed by a girth loop round both and a length down the front only:
    each names the girth; only the front the length; a layer names its host's; a sheet below a loop doesn't cross it."""
    Vf, Ff = plane(-0.15, 0.15, 1.0, 1.4, y=-0.1)
    Vb, Fb = plane(-0.15, 0.15, 1.0, 1.4, y=0.1)
    th = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    chest = np.c_[0.15 * np.cos(th), 0.09 * np.sin(th), np.full(64, 1.2)]
    neck = np.c_[0.05 * np.cos(th), 0.09 * np.sin(th), np.full(64, 1.45)]  # (above both sheets: crosses neither)
    length = np.c_[np.full(10, 0.05), np.full(10, -0.09), np.linspace(1.35, 1.05, 10)]
    step3 = {"measurements": [{"name": "chest", "loop": chest.tolist()}, {"name": "neck", "loop": neck.tolist()},
                              {"name": "front_len", "path": length.tolist()}]}
    pcs = {"front.L": {"V": Vf, "F": Ff, "rep": {}}, "back.L": {"V": Vb, "F": Fb, "rep": {}},
           "facing.L": {"V": Vf, "F": Ff, "rep": {"host": "front.L"}}}
    T = cut_tapes.piece_tapes(pcs, step3)
    assert sorted(T["front.L"]) == ["chest", "front_len"], T
    assert T["back.L"] == ["chest"], T
    assert T["facing.L"] == T["front.L"]


def test_declared_cap_ease_kept_as_cut_and_mirrored():
    """A cap 6 % longer than its armhole: declared, it stays 6 % (not trued to the mean) on both halves; undeclared, it
    is trued."""
    def piece(L):
        P = np.c_[np.linspace(0, L, 11), np.zeros(11)]
        P = np.r_[P, [[L, -0.1], [0, -0.1]]]
        return {"loop": list(range(13)), "U": P, "lp": np.arange(13), "V": np.c_[P, np.zeros(13)]}
    pcs = {"sleeve.L": piece(0.106), "front.L": piece(0.100), "sleeve.R": piece(0.106), "front.R": piece(0.100)}
    edges = {p: {("cap" if p.startswith("sleeve") else "armhole"): list(range(10))} for p in pcs}
    s1 = {"seams": [{"a": f"sleeve.{h}:cap", "b": f"front.{h}:armhole"} for h in "LR"]}
    from hifipushie.cut_made import _mir
    ease = {"sleeve.L:cap": [0.04, 0.09]}
    ease.update({_mir(k): v for k, v in ease.items()})
    B, decl = cut_tool.block({k: dict(v) for k, v in pcs.items()}, edges, s1, {}, ease)
    from hifipushie import pattern
    for h in "LR":
        cap = pattern.length(B["pieces"][f"sleeve.{h}"]["P"][:11])
        arm = pattern.length(B["pieces"][f"front.{h}"]["P"][:11])
        assert abs(cap / arm - 1.06) < 1e-6, (h, cap, arm)
        assert any(d.get("ease") == [0.04, 0.09] for d in decl["seams"] if d["a"] == f"sleeve.{h}:cap")
    assert all(json.loads(k)[0].startswith("sleeve") for k in B["seam_notes"])
    B2, _ = cut_tool.block({k: dict(v, U=v["U"].copy()) for k, v in pcs.items()}, edges, s1, {}, {})
    assert abs(pattern.length(B2["pieces"]["sleeve.L"]["P"][:11]) / pattern.length(B2["pieces"]["front.L"]["P"][:11]) - 1) < 0.002
