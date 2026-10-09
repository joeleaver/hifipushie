"""Caves made walkable by the build, and the report naming the lever that moves a failed walk (pushieworld notes
94-95): a karst mouth whose floor stood over the open ground at a cliff's foot (a 0.7 m step the passage's width and
height couldn't change), and a lava tube down a steep cone (`"grade"`: switchbacks across the flow with level landings
at the turns). uv run python tests/test_caves_walkable.py"""
import json
import tempfile
from pathlib import Path

import numpy as np

from hifipushie import terrain, terrain_caves, terrain_mesh as tm

KARST = {"world": {"kind": "coast", "base": 10}, "extent": [[0, 0], [160, 160]], "cell": 2,
         "tilt": {"down": "south", "grade": 0.4},
         "sea": {"level": 0, "shore": "cliffs", "cliffs": {"height": [10, 14]}},
         "cover": [{"type": "meadow", "in": "everywhere"}],
         "caves": {"grotto": {"kind": "karst", "width": 4, "height": 4,
                              "entrances": {"mouth": {"at": [80, 70]}},
                              "chambers": {"low": {"at": [80, 120], "depth": 14, "size": [8, 5]}},
                              "passages": [["mouth", "low"]]}}}

CONE = {"world": {"kind": "crater", "base": 10}, "extent": [[0, 0], [400, 400]], "cell": 2,
        "volcanoes": {"cone": {"at": [200, 330], "h": 110, "type": "cinder", "base_radius": 230, "crater": False,
                               "gullies": 0.0,
                               "flows": {"flow": {"from": "south", "length": 260, "width": 40, "thick": 6}}}},
        "cover": [{"type": "meadow", "in": "everywhere"}],
        "caves": {"tube": {"kind": "lava", "flow": "flow", "from": 0.15, "to": 0.75}}}


def _terrain(spec):
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(spec))
    return terrain.load(d / "spec.json")


def test_mouth_meets_the_ground(T):
    """A hillside mouth's floor is no higher than the ground where the door ended up, and the floor leaves it on the
    passage's plain grade (the beds' wander eased in): no step where the passage leaves the open ground."""
    caves, field = terrain_caves.light_field(T)
    cv = caves[0]
    m = cv.nodes["mouth"]
    assert m["z"] <= float(T.height(m["xy"])) + 1e-6, (m["z"], float(T.height(m["xy"])))
    e = cv.edges[0]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(e["_xy"], axis=0), axis=1))]
    near = s < 10.0
    rise = np.abs(np.diff(e["_floor"][near])) / np.maximum(np.diff(s[near]), 1e-6)
    assert rise.max() < terrain_caves.GRADE_WALK, rise
    line = terrain_caves.check(caves, field, sea=tm._sea(T))[0]
    assert "PASSES" in line, line


def test_door_floor_from_the_spec(T0):
    spec = json.loads(json.dumps(T0.source))
    spec["caves"]["grotto"]["entrances"]["mouth"]["z"] = -0.4
    caves, _ = terrain_caves.light_field(_terrain(spec))
    assert abs(caves[0].nodes["mouth"]["z"] + 0.4) < 1e-9


def test_step_advice_names_the_lever():
    """A step by a mouth: the door's floor ("z") or its "at"; one further in: the floor's climb; never only width
    and height."""
    class Cv:
        kind = "karst"
        nodes = {"door": {"type": "entrance", "shaft": False, "xy": np.array([0.0, 0.0]), "z": 0.2},
                 "hall": {"type": "chamber", "xy": np.array([100.0, 0.0]), "z": 5.0}}

    class T:
        @staticmethod
        def height(xy):
            return -0.8
    p = {"from": "door", "to": "hall", "length": 100.0, "edge": {}}
    at_door = terrain_caves._walk_fix(T, Cv, p, "a step over 0.6 m (0.70 m at [4, 0, 0.2], 6 m along); first at "
                                                "[4, 0, 0.2], 6 m along")
    assert "from the mouth door" in at_door and '"z": -0.8' in at_door, at_door
    inside = terrain_caves._walk_fix(T, Cv, p, "a step over 0.6 m (0.70 m at [50, 0, 3], 50 m along); first at "
                                               "[50, 0, 3], 50 m along")
    assert "rising faster than it runs" in inside and "mouth" not in inside, inside
    tight = terrain_caves._walk_fix(T, Cv, p, "too tight; first at [50, 0, 3], 50 m along")
    assert '"width"' in tight, tight


def test_graded_lava_tube(C):
    """Without a grade the tube follows its flow down the cone and the report says how to walk it; with one it
    switchbacks across the flow: no stretch steeper than the grade (landings level), the floor everywhere under the
    ground by at least its roof, and the walk passes."""
    rep = C.report()
    w = [l for l in rep.splitlines() if l.strip().startswith("cave tube:")]
    assert w and '"grade"' in w[0], w
    spec = json.loads(json.dumps(C.source))
    spec["caves"]["tube"].update({"grade": 0.18, "swing": 80})
    G = _terrain(spec)
    caves, field = terrain_caves.light_field(G)
    cv = caves[0]
    assert any("switchbacks" in n for n in cv.notes), cv.notes
    e = cv.edges[0]
    xy, fl = e["_xy"], e["_floor"]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    ss = np.arange(0, s[-1], 1.0)
    f1 = np.interp(ss, s, fl)
    k = int(terrain_caves.GRADE_RUN)
    g10 = np.abs(f1[k:] - f1[:-k]) / k
    assert g10.max() <= 0.18 + 0.02, g10.max()
    cover = G.sample(xy) - (fl + e["_h"])
    assert cover.min() > 1.0, cover.min()
    line = terrain_caves.check(caves, field, sea=tm._sea(G))[0]
    assert "PASSES" in line, line


def test_collision_floor():
    """The floor a character stands on, read off a mesh: the highest surface under the walk's floor + a knee, so a
    riser the mesh has (and the field doesn't) shows as a step."""
    P = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [10, 10, 0],
                  [5, 0, 0.6], [10, 0, 0.6], [5, 10, 0.6], [10, 10, 0.6],
                  [0, 0, 3], [10, 0, 3], [0, 10, 3]], float)
    F = np.array([[0, 1, 3], [0, 3, 2], [4, 5, 7], [4, 7, 6], [8, 9, 10]])
    xy = np.array([[2.0, 5.0], [7.0, 5.0], [7.0, 5.0]])
    z = np.array([0.0, 0.1, -4.0])
    cz = terrain_caves.collision_floor(xy, z, P, F)
    assert np.allclose(cz[:2], [0.0, 0.6]) and np.isnan(cz[2]), cz  # (the roof at 3 m is over the knee: not a floor)


STEEP = {"world": {"kind": "coast", "base": 10}, "extent": [[0, 0], [160, 160]], "cell": 2,
         "tilt": {"down": "south", "grade": 1.3}, "cover": [{"type": "meadow", "in": "everywhere"}]}


def test_deep_cave_under_a_steep_face():
    """A passage 20 m+ under a steep hillside keeps its clearance in the export's field (pushieworld note 117: the
    face's rock relief, a column grid, was taken at full size round crown_tube 12 m under a 56 deg valley side, built
    a sheet of rock across it (width 0, a 1.3 m step) and failed the tile walk where set_terrain's walk passed).
    Deeper than the relief's reach under the ground a cave's walls take only their own passage-scaled relief: the
    rock field's walk is within 0.5 m of the plain one's (before: headroom 0.8 m and width 1.6 m less)."""
    T = _terrain(STEEP)
    xy = np.c_[np.linspace(30, 130, 67), np.full(67, 80.0)]
    g = T.sample(xy)
    w, h = 5.0, 4.0
    fl = np.full(len(xy), g.min() - 22.0 - h)
    tube = tm.Tube("t", np.c_[xy, fl], 0.5 * w, h, fl, seed=3, rough=0.4, rough_scale=3.0, blend=0.8)
    cv = terrain_caves.Cave("t", "lava", {"a": {}, "b": {}},
                            [{"from": "a", "to": "b", "_xy": xy, "_floor": fl, "_w": w, "_h": h}], [tube], [])
    rock = tm.rock_config(T, dict(tm.DEFAULTS))
    full = tm.Field(T, [tube], rock)
    assert full.relief_at(xy[:20, 0], xy[:20, 1]).mean() > 0.5  # (the face over it takes the rock's relief)
    got = {}
    for nm, F in (("plain", tm.Field(T, [tube], None)), ("rock", full)):
        paths = []
        line = terrain_caves.check([cv], F, paths=paths)[0]
        assert "PASSES" in line, (nm, line)
        got[nm] = (np.nanmin(np.array(paths[0]["headroom_m"], float)), np.nanmin(np.array(paths[0]["width_m"], float)))
    (h0, w0), (h1, w1) = got["plain"], got["rock"]
    assert h0 - h1 < 0.5 and w0 - w1 < 0.5, got


if __name__ == "__main__":
    test_collision_floor()
    test_step_advice_names_the_lever()
    test_deep_cave_under_a_steep_face()
    T0 = _terrain(KARST)
    test_mouth_meets_the_ground(T0)
    test_door_floor_from_the_spec(T0)
    C = _terrain(CONE)
    test_graded_lava_tube(C)
    print("ok")
