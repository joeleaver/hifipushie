"""fuse and grab (reshape.py): two masses worked into one, and clay moved where it stands."""
import copy

import numpy as np
import pytest

from hifipushie import reshape, store
from hifipushie.sdf import field_at
from hifipushie.spec import SpecError, compile_prims, empty_spec


def _figure():
    """A ball of a head on a ball of a body, an ear each side, an arm that is a bone (so bone + blob orders mix)."""
    s = empty_spec()
    s["joints"] = {"pelvis": {"pos": [0, 0, 0.25]}, "head": {"pos": [0, 0, 0.6]}, "ear.L": {"pos": [0.13, 0, 0.74]},
                   "shoulder.L": {"pos": [0.17, 0, 0.42]}, "wrist.L": {"pos": [0.3, 0, 0.3]}}
    s["bones"] = {"arm.L": {"a": "shoulder.L", "b": "wrist.L", "r_a": 0.04, "r_b": 0.035}}
    s["blobs"] = {"torso": {"at": "pelvis", "size": [0.2, 0.18, 0.2]},
                  "head": {"at": "head", "size": [0.2, 0.17, 0.16]},
                  "ear.L": {"at": "ear.L", "size": [0.045, 0.025, 0.06], "blend": 0.02}}
    return s


def _top(prims, x, y=0.0, z0=0.4, z1=1.0):
    """The highest z at (x, y) where there is clay."""
    z = np.linspace(z0, z1, 1201)
    f = field_at(prims, np.stack([np.full_like(z, x), np.full_like(z, y), z], 1), clip=False)
    return float(z[np.nonzero(f < 0)[0].max()])


def _edge(prims, z, y=0.0):
    """The furthest x at height z where there is clay."""
    x = np.linspace(0.0, 0.6, 1201)
    f = field_at(prims, np.stack([x, np.full_like(x, y), np.full_like(x, z)], 1), clip=False)
    return float(x[np.nonzero(f < 0)[0].max()])


def test_a_fuse_fills_the_waist_and_more_fill_fills_more():
    prims = compile_prims(_figure())
    w = [reshape.waist(prims, "head", "torso", k)["width"] for k in (0.0, 0.05, 0.1, 0.2)]
    assert w == sorted(w) and w[-1] - w[0] > 0.05


def test_a_width_read_off_the_reference_is_met():
    prims = compile_prims(_figure())
    fill, said = reshape.solve_fill(prims, "head", "torso", 0.30)
    assert said == "" and abs(reshape.waist(prims, "head", "torso", fill)["width"] - 0.30) < 0.003


def test_a_width_wider_than_a_fuse_can_fill_is_said():
    prims = compile_prims(_figure())
    fill, said = reshape.solve_fill(prims, "head", "torso", 0.39)
    assert fill > 0.2 and "overlap further" in said


def test_a_width_no_fill_can_reach_is_said():
    prims = compile_prims(_figure())
    narrow = reshape.waist(prims, "head", "torso", 0.0)["width"]
    fill, said = reshape.solve_fill(prims, "head", "torso", narrow - 0.02)
    assert fill == 0.0 and "already" in said


def test_fused_masses_are_one_group_whatever_their_order_and_the_model_shows_the_fill():
    s = _figure()
    plain = compile_prims(copy.deepcopy(s))
    for n in ("head", "torso"):
        s["blobs"][n].update(fuse="head+torso", fill=0.15)
    s["blobs"] = {"torso": s["blobs"]["torso"], "ear.L": s["blobs"]["ear.L"], "head": s["blobs"]["head"]}  # apart
    prims = compile_prims(s)
    names = [p.name for p in prims]
    assert abs(names.index("head") - names.index("torso")) == 1
    assert {p.group for p in prims if p.name in ("head", "torso")} == {"fuse:head+torso"}
    z = reshape.waist(plain, "head", "torso", 0.03)["z"]
    assert _edge(prims, z, y=0.04) - _edge(plain, z, y=0.04) > 0.02  # the neck is wider in the whole model (clear of the arm)
    for p in prims:
        if p.name in ("head", "torso"):
            assert p.inert >= 0.15  # their boxes reach as far as the fill rounds (a short reach leaves a torn band)


def test_a_fuse_on_one_mass_alone_and_a_fuse_with_a_grouped_mass_are_refused():
    s = _figure()
    s["blobs"]["head"].update(fuse="x", fill=0.1)
    with pytest.raises(SpecError, match="two or more"):
        compile_prims(s)
    s["blobs"]["torso"].update(fuse="x", fill=0.1, group="g")
    with pytest.raises(SpecError, match="already in the group"):
        compile_prims(s)


def test_a_grab_moves_the_clay_it_holds_to_where_it_is_put():
    s = _figure()
    before = _top(compile_prims(copy.deepcopy(s)), 0.13)
    s["grabs"] = {"tip": {"of": ["ear.L"], "view": "front", "at": [0.13, before], "to": [0.13, before + 0.03],
                          "radius": 0.07}}
    prims = compile_prims(s)
    assert abs(_top(prims, 0.13) - (before + 0.03)) < 0.003
    assert abs(_top(prims, -0.13) - (before + 0.03)) < 0.003  # the right ear too
    assert abs(_top(prims, 0.0) - _top(compile_prims(_figure()), 0.0)) < 1e-3  # the head, not named, has not moved


def test_a_grab_off_the_centre_line_of_a_centre_mass_is_made_on_both_sides():
    s = _figure()
    z = 0.6
    e0 = _edge(compile_prims(copy.deepcopy(s)), z)
    s["grabs"] = {"cheek": {"of": ["head"], "view": "front", "at": [e0, z], "to": [e0 + 0.02, z], "radius": 0.08}}
    prims = compile_prims(s)
    x = np.linspace(-0.6, 0.6, 2401)
    inside = field_at(prims, np.stack([x, np.zeros_like(x), np.full_like(x, z)], 1), clip=False) < 0
    assert abs(x[inside].max() - (e0 + 0.02)) < 0.003 and abs(x[inside].min() + (e0 + 0.02)) < 0.003


def test_a_grab_that_would_fold_the_clay_is_refused_with_the_radius_it_needs():
    s = _figure()
    s["grabs"] = {"far": {"of": ["head"], "view": "front", "at": [0, 0.76], "to": [0, 0.86], "radius": 0.08}}
    with pytest.raises(SpecError, match="radius of 20.0 cm"):
        compile_prims(s)


def test_a_grab_of_a_mass_that_is_not_there_names_the_masses():
    s = _figure()
    s["grabs"] = {"g": {"of": ["nose"], "view": "side", "at": [0, 0.6], "to": [0.01, 0.6], "radius": 0.05}}
    with pytest.raises(SpecError, match="no mass called 'nose'"):
        compile_prims(s)


def test_the_tools_save_a_version_and_say_what_they_did(tmp_path, monkeypatch):
    from hifipushie import server
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(server.tools_reshape if hasattr(server, "tools_reshape") else __import__(
        "hifipushie.tools_reshape", fromlist=["x"]), "_with_look", lambda name, views, text: text)
    store.save("fig", _figure(), "start")
    out = server.fuse("fig", "head", "torso", width=0.30)
    import re
    assert "worked into one mass" in out and "before:" in out
    assert abs(float(re.search(r"them: (\d+\.\d) cm across", out).group(1)) - 30.0) < 0.4
    assert store.load("fig")["blobs"]["head"]["fuse"] == "head+torso"
    out = server.grab("fig", ["ear.L"], "front", [0.13, 0.8], [0.14, 0.82], 0.06, label="tip")
    assert "grab 'tip'" in out and store.load("fig")["grabs"]["tip"]["radius"] == 0.06
    out = server.grab("fig", [], "front", [0, 0], [0, 0], 0.1, label="tip", remove=True)
    assert "taken off" in out and "grabs" not in store.load("fig")
    out = server.fuse("fig", "head", "torso", fill=0)
    assert "parted" in out and "fuse" not in store.load("fig")["blobs"]["head"]
    with pytest.raises(ValueError, match="no mass called 'neck'"):
        server.fuse("fig", "head", "neck", fill=0.1)


def test_a_blob_is_aimed_by_where_it_points_and_where_it_faces():
    s = _figure()
    s["blobs"]["ear.L"] = {"at": "ear.L", "shape": "blade", "size": [0.04, 0.07, 0.012],
                           "aim": {"point": "up out", "face": "forward"}}
    prims = {p.name: p for p in compile_prims(s)}
    R, Rr = prims["ear.L"].params["rot"], prims["ear.R"].params["rot"]
    assert np.allclose(R[:, 1], np.array([1, 0, 1]) / 2 ** 0.5)  # its length rises and leans out
    assert np.allclose(R[:, 2], [0, -1, 0])  # its hollow side looks forward
    assert np.allclose(Rr[:, 1], np.array([-1, 0, 1]) / 2 ** 0.5) and np.allclose(Rr[:, 2], [0, -1, 0])  # the twin
    assert abs(np.linalg.det(R) - 1) < 1e-9 and abs(np.linalg.det(Rr) - 1) < 1e-9
    s["blobs"]["ear.L"] = {"at": "ear.L", "size": [0.045, 0.025, 0.06], "aim": {"point": [1, 0, 0]}}  # an ellipsoid
    R = {p.name: p for p in compile_prims(s)}["ear.L"].params["rot"]
    assert np.allclose(R[:, 2], [1, 0, 0])  # its longest axis (z) lies along x


def test_an_aim_that_is_no_direction_or_comes_with_angles_is_refused():
    s = _figure()
    s["blobs"]["ear.L"].update(aim={"point": "up"}, rot=[0, 0, 0])
    with pytest.raises(SpecError, match="aim or rot"):
        compile_prims(s)
    del s["blobs"]["ear.L"]["rot"]
    s["blobs"]["ear.L"]["aim"] = {"point": "upwards"}
    with pytest.raises(SpecError, match="not a direction"):
        compile_prims(s)
    s["blobs"]["ear.L"]["aim"] = {"point": "up", "face": "up"}
    with pytest.raises(SpecError, match="looks along"):
        compile_prims(s)


def test_a_fuse_can_leave_one_side_creased_and_the_others_smooth():
    from hifipushie import sdf
    s = _figure()
    for n in ("head", "torso"):
        s["blobs"][n].update(fuse="h", fill=0.2)
    even = compile_prims(copy.deepcopy(s))
    for n in ("head", "torso"):
        s["blobs"][n]["fill_sides"] = {"front": 0.1}
    sided = compile_prims(s)
    z = reshape.waist(compile_prims(_figure()), "head", "torso", 0.2)["z"]

    def reach(prims, sign):  # how far the clay stands from the middle line at the waist, to the front (-1) or back
        y = np.linspace(0.0, 0.4, 801)
        f = field_at(prims, np.stack([np.zeros_like(y), sign * y, np.full_like(y, z)], 1), clip=False)
        return float(y[np.nonzero(f < 0)[0].max()])
    assert reach(even, -1) - reach(sided, -1) > 0.01  # the front is left creased
    assert abs(reach(even, 1) - reach(sided, 1)) < 0.004  # behind it is as smooth as before
    g = sdf.evaluate(sided, resolution=48)  # the grid's blocks take the sides too
    assert np.isfinite(g.field).all() and (g.field < 0).any()
    for bad, said in (({"front": 1.5}, "0 .a crease"), ({"chin": 0.2}, "fill_sides is")):
        for n in ("head", "torso"):
            s["blobs"][n]["fill_sides"] = bad
        with pytest.raises(SpecError, match=said):
            compile_prims(s)


def test_each_mass_in_a_fuse_keeps_its_own_fill():
    s = _figure()
    s["joints"]["jaw"] = {"pos": [0, -0.12, 0.5]}
    for n in ("head", "torso"):
        s["blobs"][n].update(fuse="h", fill=0.2)
    two = compile_prims(copy.deepcopy(s))
    s["blobs"]["jaw"] = {"at": "jaw", "size": [0.08, 0.05, 0.04], "fuse": "h", "fill": 0.03}
    three = {p.name: p for p in compile_prims(s)}
    assert (three["head"].join, three["jaw"].join) == (0.2, 0.03)
    names = list(three)
    assert names.index("jaw") > max(names.index("head"), names.index("torso"))  # the widest joins first
    z = reshape.waist(compile_prims(_figure()), "head", "torso", 0.2)["z"]
    x = np.linspace(0.0, 0.5, 1001)
    back = lambda prims: float(x[np.nonzero(field_at(prims, np.stack([np.zeros_like(x), x, np.full_like(x, z)], 1),
                                                     clip=False) < 0)[0].max()])  # noqa: E731
    assert abs(back(list(three.values())) - back(two)) < 0.002  # the jaw's small fill left the neck as it was


def test_a_grab_on_a_fused_mass_moves_nothing_far_from_it():
    s = _figure()
    for n in ("head", "torso"):
        s["blobs"][n].update(fuse="h", fill=0.25)
    before = compile_prims(copy.deepcopy(s))
    s["grabs"] = {"chin": {"of": ["head"], "view": "side", "at": [-0.15, 0.45], "to": [-0.18, 0.44], "radius": 0.07}}
    after = compile_prims(s)
    y = np.linspace(0.0, 0.5, 2001)
    for z in (0.3, 0.37, 0.45, 0.6):  # the back of the figure, 30 cm from the grab (it swelled 4 cm before)
        f0, f1 = (field_at(p, np.stack([np.zeros_like(y), y, np.full_like(y, z)], 1), clip=False) for p in (before, after))
        assert abs(y[np.nonzero(f0 < 0)[0].max()] - y[np.nonzero(f1 < 0)[0].max()]) < 0.002


def test_a_third_mass_is_fused_in_with_its_own_fill_by_the_tool(tmp_path, monkeypatch):
    from hifipushie import server, tools_reshape
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(tools_reshape, "_with_look", lambda name, views, text: text)
    s = _figure()
    s["joints"]["jaw"] = {"pos": [0, -0.12, 0.5]}
    s["blobs"]["jaw"] = {"at": "jaw", "size": [0.08, 0.05, 0.04]}
    store.save("fig", s, "start")
    server.fuse("fig", "head", "torso", fill=0.2, sides={"front": 0.2})
    out = server.fuse("fig", "head", "jaw", fill=0.03)  # (this was refused: "only 'torso' has it")
    b = store.load("fig")["blobs"]
    assert (b["head"]["fill"], b["torso"]["fill"], b["jaw"]["fill"]) == (0.2, 0.2, 0.03)
    assert "fill_sides" not in b["jaw"] and b["head"]["fill_sides"] == {"front": 0.2}
    assert "also holds" in out and "torso (fill 20.0 cm)" in out
    server.fuse("fig", "head", "jaw", fill=0)  # the jaw comes out; head and torso stay fused
    b = store.load("fig")["blobs"]
    assert "fuse" not in b["jaw"] and b["head"]["fuse"] == b["torso"]["fuse"]
