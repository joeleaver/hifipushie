"""T13 (C297): draped pieces: their rows wait for the hang, the plan validates the split, the start is legal."""
import types

import numpy as np
import pytest
from scipy.spatial import ConvexHull

from hifipushie import chain_drape as cd, garment_plan as gp, garment_reads as gr, structure_rows as sr
from hifipushie.chain_net import Contact

READ = {"views": [{"image": "x.png", "view": "front"}]}
PARTS = {"pieces": {"cloak": {"hang": "draped", "held": ["neck"]}, "hood.L": {"hang": "draped"}},
         "details": {}, "closures": {"clasp": {"pieces": ["cloak"]}}}


def _style(rows, drape=None):
    return {"ties": {"clasp": {"fastened": [1], "of": 1, "source": "f"}}, "pose": {"name": "A", "source": "f"}, "bends": [],
            "drape": drape if drape is not None else {"hood.L": {"falls": "up", "source": "f"}}, "rows": rows,
            "traces": [{"id": "hem", "what": "hem", "view": 0, "points": [[10, 90], [20, 92], [30, 92], [40, 90]], "source": "f"}],
            "body_marks": [{"view": 0, "at": {"chest_z": [25, 40], "waist_z": [25, 60]}, "source": "f (no step-0 fit)"}]}


def _row(what, judged=None, **t):
    r = {"id": what, "what": what, "target": dict({"value": 300, "unit": "mm"}, **t), "source": "ref"}
    if judged:
        r["judged"] = judged
    return r


def test_draped_rows_wait_for_the_hang():
    plan = {"parts": PARTS, "style": _style([_row("drape_hem_height", value=340), _row("hood_opening")])}
    its, _ = sr.plan_items(plan, set())
    assert {it["id"]: it["on"] for it in its} == {"drape_hem_height": "hang", "hood_opening": "hang"}
    its += cd.rule_items(plan)
    on = {it["id"]: it["on"] for it in its}
    assert on["drape_start_clear"] == "build" and on["drape_held_exact"] == "build" and on["hood_on_head"] == "hang"
    rows = gr.checklist_rows(its, {"drape_clear_min_mm": 8.0, "drape_held_worst_pct": 0.1}, "build")
    st = {r["id"].split(":", 1)[1]: r["status"] for r in rows}
    assert st["drape_hem_height"] == st["hood_opening"] == st["hood_on_head"] == "LATER"  # (shown, not judged)
    assert st["drape_start_clear"] == st["drape_held_exact"] == "PASS"
    hung = gr.checklist_rows(its, {"drape_hem_height_mm": 350.0, "hood_opening_mm": 200.0, "hood_over_head_mm": 5.0},
                             "hang")
    st = {r["id"].split(":", 1)[1]: r["status"] for r in hung}
    assert st["drape_hem_height"] == "PASS" and st["hood_opening"] == "FAIL" and st["drape_start_clear"] == "LATER"


def test_plan_refuses_a_row_on_the_wrong_stage_with_the_list():
    with pytest.raises(gp.PlanRefused) as e:  # a hang kind said to be judged on the build
        gp.check_style(_style([_row("drape_hem_height", judged="build")]), READ, PARTS)
    assert "judged on the hang" in str(e.value) and "on the build: collar_points_apart" in str(e.value)
    with pytest.raises(gp.PlanRefused, match="sleeve_end is judged on the build"):  # and vice versa
        gp.check_style(_style([_row("sleeve_end", judged="hang")]), READ, PARTS)
    fitted = {"pieces": {"cloak": {}}, "details": {}, "closures": {"clasp": {"pieces": ["cloak"]}}}
    with pytest.raises(gp.PlanRefused, match="no draped piece|have none"):  # a hang row with nothing draped
        gp.check_style(_style([_row("drape_hem_height")], drape={}), READ, fitted)
    with pytest.raises(gp.PlanRefused, match="drape.cloak: not a step-1 piece"):
        gp.check_style(_style([_row("sleeve_end")], drape={"cloak": {"falls": "up", "source": "f"}}), READ, fitted)
    gp.check_style(_style([_row("drape_hem_height", judged="hang"), _row("hood_depth")]), READ, PARTS)


def test_parts_hang_and_held_validated():
    bad = []
    cd.check_parts({"a": {"hang": "floppy"}, "b": {"held": ["neck"]}, "c": {"hang": "draped", "held": ["neck"]}}, bad)
    assert len(bad) == 2 and "a.hang" in bad[0] and "b.held" in bad[1]


def _snowman():
    """A closed convex body: torso ellipsoid + head sphere (hull), with neck landmarks on it."""
    u, v = np.meshgrid(np.linspace(0, 2 * np.pi, 48), np.linspace(0, np.pi, 24))
    sph = lambda c, r: (np.c_[np.cos(u).ravel() * np.sin(v).ravel() * r[0], np.sin(u).ravel() * np.sin(v).ravel() * r[1],
                              np.cos(v).ravel() * r[2]] + c)
    P = np.r_[sph([0, 0, 1.15], [0.2, 0.12, 0.35]), sph([0, 0, 1.62], [0.09, 0.1, 0.12])]
    h = ConvexHull(P)
    V = P[np.unique(h.simplices)]
    h = ConvexHull(V)
    T = h.simplices.copy()
    c = V.mean(0)
    flip = np.einsum("ij,ij->i", np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), V[T].mean(1) - c) < 0
    T[flip] = T[flip][:, [0, 2, 1]]
    ct = Contact(V, T)
    z = 1.48
    at = {"cf_neck": np.r_[0, -0.08, z], "cb_neck": np.r_[0, 0.08, z], "neck_side.L": np.r_[0.1, 0, z]}
    return types.SimpleNamespace(V=V, T=T, at=at, contact=ct)


def test_held_line_and_start_paths_are_legal():
    body = _snowman()
    L = 0.75
    ring = cd.held_ring(body, L, 0.0045)
    per = float(np.linalg.norm(np.diff(np.r_[ring, ring[:1]], axis=0), axis=1).sum())
    assert abs(per / L - 1) < 0.01  # the held line at its cut
    assert body.contact.query(ring)[0].min() >= 0.0045 * 0.9  # resting, never inside
    centre = ring[:, :2].mean(0)
    for i in (0, 180, 360):  # CF, the side, CB: down and up (a hood) both clear of the body past the start
        X0 = ring[i]
        o = np.r_[X0[:2] - centre, 0]
        o /= np.linalg.norm(o)
        for vz in (-1.0, 1.0):
            vert = np.r_[0, 0, vz]
            a, sb = cd._paths(X0, o, vert, np.r_[1.0, 0, 0], 0.8, body.contact)
            t = np.linspace(0.05, 0.8, 30)
            P = cd._path_pts(X0, o, vert, np.zeros(3), a, sb, t, 0.0)
            assert body.contact.query(P)[0].min() >= cd.CLEAR * 0.99
            assert np.allclose(np.linalg.norm(P - X0, axis=1) <= t + 1e-9, True)  # (radial: never longer than its cut)


def test_held_line_sewn_to_itself_refused_by_name():
    """A seam paired the wrong way round sews the held line's CF end to its CB: refused, naming the seam's fix."""
    from types import SimpleNamespace
    import pytest
    from hifipushie.chain_garment import ChainRefused
    hv = np.arange(5)
    uv = np.c_[np.linspace(0.1, -0.1, 5), np.zeros(5)]
    ok = SimpleNamespace(root=np.arange(6), uv=np.r_[uv, [[0, 0.1]]], names=["cloak", "hood"], piece=np.r_[np.zeros(5, int), 1])
    cd.check_held_sewn(ok, "cloak", hv)
    bad = SimpleNamespace(**{**vars(ok), "root": np.array([0, 1, 2, 3, 2, 2])})  # (the end and the middle, through the hood)
    with pytest.raises(ChainRefused, match=r"sewn to itself.*\[2, 4\].*hood.*wrong way round"):
        cd.check_held_sewn(bad, "cloak", hv)


def test_held_line_placed_by_chords_exact_at_a_sharp_turn():
    """A ring with a corner (the clasp): the held links are their cut chords, not arc steps."""
    P = np.r_[[[0.0, 0, 0]], np.c_[np.linspace(0.01, 0.2, 40), np.linspace(0.01, 0.2, 40) * 0.2, np.zeros(40)],
              np.c_[np.linspace(0.2, 0.01, 40), np.linspace(0.2, 0.01, 40) * -0.2, np.zeros(40)]]
    seg = np.full(30, 0.0098)
    Q = cd._chords(P, 0.002, seg)
    assert np.allclose(np.linalg.norm(np.diff(Q, axis=0), axis=1), seg, rtol=1e-3)


def test_start_clear_read_before_soft_net():
    """drape_start_clear reads the free cloth on the start the paths made, not after soft_net (which floors cloth at
    GAP_START 4.5 mm under the 6 mm limit: read there, the row could never pass). Held vertices are not counted."""
    net = types.SimpleNamespace(piece=np.zeros(4, int), pid=lambda p: 0, uv=np.array([[0, 0], [0.1, 0], [0, 0.1], [0.1, 0.1]]))
    body = types.SimpleNamespace(contact=types.SimpleNamespace(query=lambda P: (np.abs(np.asarray(P)[:, 2]), None)))
    held = np.array([True, True, False, False])
    X0 = np.array([[0, 0, cd.GAP_START], [0.1, 0, cd.GAP_START], [0, 0.1, 0.010], [0.1, 0.1, 0.012]])
    X = X0.copy()
    X[2:, 2] = cd.GAP_START  # (soft_net settled the free cloth to its floor)
    drape = {"pieces": {"cloak": {"held": np.array([0, 1]), "falls": "down"}}}
    assert cd.start_reads(X, net, body, drape, held, start=X0)["clear_min_mm"] == pytest.approx(10.0)
    assert cd.start_reads(X, net, body, drape, held)["clear_min_mm"] == pytest.approx(cd.GAP_START * 1000)
    lim = next(i for i in cd.rule_items({"style": {"drape": {"cloak": {"falls": "down", "source": "f"}}}, "parts": PARTS})
               if i["id"] == "drape_start_clear")["range"][0]
    assert 10.0 >= lim > cd.GAP_START * 1000
