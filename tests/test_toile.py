"""Step 4 of drape first, the TOILE (toile.py, toile_style.py, toile_gate.py, toile_tool.py): a synthetic body (a capsule
torso, a neck, two arms held off it) built from its declaration: girths at plan, nothing inside the body, sleeves as
tubes, an over front past centre front; a missing declaration refused by name."""
import numpy as np
import pytest

from hifipushie import toile_tool
from hifipushie.toile import Inputs, Toile
from hifipushie import toile_gate


def _seg(P, a, b, ra, rb):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    u = np.clip(((P - a) @ d) / (d @ d), 0, 1)
    return np.linalg.norm(P - (a + u[:, None] * d), axis=1) - (ra + (rb - ra) * u)


def _body():
    from skimage import measure
    h = 0.008
    xs, ys, zs = np.arange(-0.5, 0.5, h), np.arange(-0.25, 0.25, h), np.arange(0.70, 1.72, h)
    G = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
    f = np.minimum(_seg(G, (0, 0, 0.86), (0, 0, 1.42), 0.15, 0.15), _seg(G, (0, 0, 1.40), (0, 0, 1.66), 0.062, 0.058))
    for s in (1, -1):
        f = np.minimum(f, _seg(G, (s * 0.21, 0, 1.43), (s * 0.45, -0.02, 0.85), 0.05, 0.035))
    V, F, _, _ = measure.marching_cubes(f.reshape(len(xs), len(ys), len(zs)), 0.0, spacing=(h, h, h))
    from hifipushie.toile_geom import outward
    V = V + [xs[0], ys[0], zs[0]]
    return V, outward(V, F)


def _circle(c, r, n=48):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[c[0] + r * np.cos(a), c[1] + r * np.sin(a), np.full(n, c[2])]


def _inputs(decl):
    V, T = _body()
    tapes = {"neck": _circle((0, 0, 1.58), 0.062), "chest": _circle((0, 0, 1.30), 0.152),
             "armhole_front": np.array([[0.245, 0, 1.475], [0.215, -0.05, 1.42], [0.185, -0.05, 1.36], [0.165, 0, 1.32]]),
             "armhole_back": np.array([[0.245, 0, 1.475], [0.215, 0.05, 1.42], [0.185, 0.05, 1.36], [0.165, 0, 1.32]]),
             "shoulderToWrist": np.array([[0.245, 0, 1.475], [0.33, -0.01, 1.15], [0.445, -0.02, 0.87]]),
             "wrist": _circle((0.442, -0.02, 0.88), 0.036)}
    levels = {"chest": (1.24, 1.06), "waist": (1.12, 1.04), "hips": (0.98, 1.06), "hem": (0.92, 1.08)}
    heights = {"hem": 0.92, "sleeve_hem": 0.98}
    traces = {"front_edge.L": {"xz": np.array([[0.0, 1.40], [0.0, 1.20], [0.0, 1.0], [0.04, 0.95], [0.08, 0.92]]),
                               "corners": [], "what": "front_edge"},
              "hem.L": {"xz": np.array([[0.05, 0.92], [0.10, 0.92], [0.15, 0.92]]), "corners": [], "what": "hem"}}
    marks = {"buttons": np.array([[0.0, 1.15], [0.0, 1.05]])}
    return Inputs(V=V, T=T, tapes=tapes, levels=levels, heights=heights, decl=decl, traces=traces, marks=marks)


DECL = {"parts": ["sleeves", "opening", "pad"], "hang_from": "hips", "armhole": {"length_mm": 470},
        "sleeves": {"ease_mm": [18, 22], "crown_mm": 10, "hem": "sleeve_hem"},
        "opening": {"lap_mm": 20, "edge": "front_edge.L", "buttons": "buttons"}, "pad": {"thickness_mm": 6}}


@pytest.mark.timeout(600)
def test_synthetic_toile_girths_clearance_sleeves_opening():
    t = Toile(_inputs(DECL), log=lambda *_: None).build()
    rows = {r["id"]: r for r in toile_gate.rows(t)}
    for lv in ("chest", "waist", "hips"):
        assert rows[f"girth:{lv}"]["status"] == "PASS", rows[f"girth:{lv}"]
    assert rows["clearance"]["status"] == "PASS", rows["clearance"]
    assert rows["closed"]["status"] == "PASS", rows["closed"]
    s = t.info["sleeve"]  # a tube: monotone from the wrist up, never narrower than the arm + its ease
    r = np.array(s["tube_round_mm"])
    assert np.all(np.diff(r) <= 1e-6) and np.all(r >= np.array(s["arm_tape_mm"]) + 2 * np.pi * 17)
    V, F = t.meshes["toile"]
    front = (V[:, 1] < t.yc) & (np.abs(V[:, 2] - 1.2) < 0.02)
    assert V[front, 0].min() < -0.015  # the over front runs past centre front by the lap
    assert {"pad.L", "pad.R"} <= set(t.meshes)


def test_a_missing_declaration_is_refused_by_name():
    s0 = {"fit": {"hips": {"level_z_m": 0.98}}, "heights": {"hem": {"z_mm": 920}, "sleeve_hem": {"z_mm": 980}}}
    s2 = {"traces": [{"id": "front_edge.L"}], "rows": [{"id": "buttons"}]}
    assert toile_tool.validate(DECL, s0, s2) == []
    bad = toile_tool.validate({k: v for k, v in DECL.items() if k != "armhole"}, s0, s2)
    assert any(b.startswith("armhole:") for b in bad)
    bad = toile_tool.validate(dict(DECL, parts=["sleeves", "lapel"]), s0, s2)
    assert any("lapel: listed in parts but not declared" in b for b in bad)
    assert any("lapel: needs \"opening\"" in b for b in bad)
    bad = toile_tool.validate(dict(DECL, hang_from="seat"), s0, s2)
    assert any("hang_from: 'seat'" in b for b in bad)
    bad = toile_tool.validate(dict(DECL, opening={"lap_mm": 20, "edge": "nope"}), s0, s2)
    assert any("opening.edge: 'nope'" in b for b in bad)
