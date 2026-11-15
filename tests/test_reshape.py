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


def _fused_with(grab):
    s = _figure()
    for n in ("head", "torso"):
        s["blobs"][n].update(fuse="h", fill=0.25)
    before = compile_prims(copy.deepcopy(s))
    s["grabs"] = {"g": grab}
    return before, compile_prims(s)


def test_a_grab_pushed_into_a_fused_mass_raises_no_ring_round_it():
    # (the back pushed in 2.3 cm stood out as a ring round the dent: the grabbed mass's field was scaled where it bent)
    before, after = _fused_with({"of": ["torso"], "view": "side", "at": [0.17, 0.3], "to": [0.147, 0.3], "radius": 0.07})
    y = np.linspace(0.0, 0.5, 2001)
    moved = []
    for z in np.linspace(0.18, 0.42, 13):
        f0, f1 = (field_at(p, np.stack([np.zeros_like(y), y, np.full_like(y, z)], 1), clip=False) for p in (before, after))
        moved.append(y[np.nonzero(f1 < 0)[0].max()] - y[np.nonzero(f0 < 0)[0].max()])
    assert max(moved) < 0.001 and min(moved) < -0.015  # in at the middle, and nowhere out


def test_a_grabbed_model_is_meshed_whole():
    # the grabbed field is steeper than a distance: the mesher's band has to allow for it, or blocks go missing
    from hifipushie import sdf
    _, prims = _fused_with({"of": ["head"], "view": "side", "at": [-0.15, 0.6], "to": [-0.2, 0.6], "radius": 0.105})
    g = sdf.evaluate(prims, resolution=72)
    lo, voxel, shape = sdf.frame(prims, 72)
    pts = lo + voxel * np.stack(np.meshgrid(*[np.arange(n) for n in shape], indexing="ij"), -1).reshape(-1, 3)
    exact = field_at(prims, pts, clip=False).reshape(shape)
    sure = np.abs(exact) > 1e-6  # (a voxel exactly on the surface rounds either way)
    assert np.array_equal((g.field < 0)[sure], (exact < 0)[sure])


def _low(prims, x, y=0.0):
    """The lowest z at (x, y) where there is clay."""
    z = np.linspace(-0.1, 0.4, 2001)
    f = field_at(prims, np.stack([np.full_like(z, x), np.full_like(z, y), z], 1), clip=False)
    return float(z[np.nonzero(f < 0)[0].min()])


def test_a_trim_cuts_a_flat_face_along_its_line():
    s = _figure()
    round_under = [_low(compile_prims(copy.deepcopy(s)), x) for x in (0.0, 0.1)]
    assert round_under[1] - round_under[0] > 0.02  # a ball: its underside rises away from the middle
    s["trims"] = {"sole": {"of": ["torso"], "view": "front", "a": [-0.3, 0.1], "b": [0.3, 0.1], "off": "down", "soft": 0}}
    prims = compile_prims(s)
    assert all(abs(_low(prims, x, y) - 0.1) < 0.001 for x, y in ((0.0, 0.0), (0.1, 0.0), (0.0, 0.1)))  # flat, through the depth
    assert abs(_top(prims, 0.0) - _top(compile_prims(_figure()), 0.0)) < 1e-6  # and nothing else moved


def test_a_trim_says_which_sides_its_line_has():
    s = _figure()
    for off, said in (("front", "no front side"), ("left", "neither side")):
        s["trims"] = {"t": {"of": ["torso"], "view": "front", "a": [-0.3, 0.1], "b": [0.3, 0.1], "off": off}}
        with pytest.raises(SpecError, match=said):
            compile_prims(copy.deepcopy(s))
    s["trims"] = {"t": {"of": ["nose"], "view": "front", "a": [-0.3, 0.1], "b": [0.3, 0.1], "off": "down"}}
    with pytest.raises(SpecError, match="no mass called 'nose'"):
        compile_prims(s)


def test_a_trim_off_the_centre_line_is_made_on_both_sides_and_stays_put_under_a_grab():
    s = _figure()
    s["trims"] = {"side": {"of": ["head"], "view": "front", "a": [0.15, 0.4], "b": [0.15, 0.8], "off": "left", "soft": 0}}
    prims = compile_prims(copy.deepcopy(s))
    assert abs(_edge(prims, 0.6, y=0.1) - 0.15) < 0.001
    x = np.linspace(-0.6, 0.0, 1201)  # the right side too
    f = field_at(prims, np.stack([x, np.full_like(x, 0.1), np.full_like(x, 0.6)], 1), clip=False)
    assert abs(x[np.nonzero(f < 0)[0].min()] + 0.15) < 0.001
    s["grabs"] = {"cheek": {"of": ["head"], "view": "front", "at": [0.19, 0.6], "to": [0.23, 0.6], "radius": 0.12}}
    assert abs(_edge(compile_prims(s), 0.6, y=0.1) - 0.15) < 0.001  # the clay was pulled out; the cut is where it was drawn


@pytest.fixture()
def fig(tmp_path, monkeypatch):
    from hifipushie import tools_reshape
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(tools_reshape, "_with_look", lambda name, views, text: text)
    s = _figure()
    del s["blobs"]["ear.L"]
    store.save("fig", s, "start")
    return "fig"


def test_a_flap_grows_from_its_root_over_its_arch_to_its_tip_on_both_sides(fig):
    from hifipushie import server
    root, over, tip = [0.12, 0.0, 0.72], [0.17, -0.02, 0.82], [0.2, -0.1, 0.76]
    out = server.flap(fig, "ear.L", root=root, over=over, tip=tip, width=0.09)
    assert "mirrored as ear.R" in out and "OUTSIDE" not in out
    b = store.load(fig)["blobs"]["ear.L"]
    assert b["shape"] == "sheet" and b["at"] == "ear.L" and len(b["spine"]) == 3  # (the joint nearest its root)
    prims = compile_prims(store.load(fig))
    near_tip = np.array(tip) + 0.012 * (np.array(over) - tip) / np.linalg.norm(np.array(over) - tip)
    pts = np.array([over, near_tip, [-over[0], over[1], over[2]], [-near_tip[0], near_tip[1], near_tip[2]]])
    assert (field_at(prims, pts, clip=False) < 0).all()
    beyond = np.array(tip) + 0.03 * (np.array(tip) - over) / np.linalg.norm(np.array(tip) - over)
    assert field_at(prims, beyond[None], clip=False)[0] > 0
    # the same name again replaces it; a root out in the air is said
    out = server.flap(fig, "ear.L", root=[0.3, 0.0, 0.9], over=[0.33, -0.02, 0.98], tip=[0.36, -0.1, 0.92], width=0.09)
    assert "OUTSIDE the clay" in out and len(store.load(fig)["blobs"]) == 3


def test_a_flap_that_cannot_be_one_is_refused_with_what_to_move(fig):
    from hifipushie import server
    with pytest.raises(ValueError, match="in one line"):
        server.flap(fig, "ear.L", root=[0.1, 0, 0.7], over=[0.1, 0, 0.8], tip=[0.1, 0, 0.9], width=0.08)
    with pytest.raises(ValueError, match="name the left one"):
        server.flap(fig, "ear.R", root=[-0.1, 0, 0.7], over=[-0.15, 0, 0.8], tip=[-0.2, -0.1, 0.76], width=0.08)
    with pytest.raises(ValueError, match="thickness"):
        server.flap(fig, "ear.L", root=[0.1, 0, 0.7], over=[0.15, 0, 0.8], tip=[0.2, -0.1, 0.76], width=0.02, thickness=0.05)


def test_trim_and_carve_tools_cut_and_put_back(fig):
    from hifipushie import server
    out = server.trim(fig, of="all", view="side", a=[-0.14, 0.4], b=[-0.14, 0.8], off="front", label="face")
    assert "trim 'face'" in out and "next:" in out
    y = np.linspace(-0.4, 0.0, 801)
    front = lambda: y[np.nonzero(field_at(compile_prims(store.load(fig)),  # noqa: E731
                                          np.stack([np.zeros_like(y), y, np.full_like(y, 0.6)], 1), clip=False) < 0)[0].min()]
    assert abs(front() + 0.14) < 0.003
    server.trim(fig, of="all", view="side", a=[0, 0], b=[0, 1], off="front", label="face", remove=True)
    assert front() < -0.165 and "trims" not in store.load(fig)
    s = store.load(fig)
    s["joints"]["mouth"] = {"pos": [0, -0.16, 0.56]}
    s["blobs"]["mouth"] = {"at": "mouth", "size": [0.06, 0.05, 0.03]}
    store.save(fig, s, "a mouth-shaped mass")
    at = np.array([[0.0, -0.15, 0.56]])
    assert field_at(compile_prims(store.load(fig)), at, clip=False)[0] < 0
    out = server.carve(fig, "mouth", of=["head"])
    assert "taken out of head" in out and field_at(compile_prims(store.load(fig)), at, clip=False)[0] > 0
    server.carve(fig, "mouth", of=[], back=True)
    assert field_at(compile_prims(store.load(fig)), at, clip=False)[0] < 0
    with pytest.raises(ValueError, match="not a cutter"):
        server.carve(fig, "mouth", of=[], back=True)
