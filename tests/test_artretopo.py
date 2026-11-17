"""Artist retopo (artretopo_*): the cage kit on a synthetic sculpt, the checks that refuse a broken cage, the bake
repair; Blender steps only in the slow test (a tiny character pressed and baked)."""
import json
import math

import numpy as np
import pytest

from hifipushie import artretopo_check as check
from hifipushie import artretopo_fill as fill
from hifipushie import artretopo_poly as poly
from hifipushie import artretopo_run as R
from hifipushie.artretopo_cage import Cage, X, Y, Z, az
from hifipushie.artretopo_mesh import Mesh, read_ply, write_ply
from hifipushie.artretopo_sculpt import Sculpt, fit_sphere


def _blob(path, R_=0.3, h=0.5, n=64):
    """a capsule along z (radius R_, half length h) as a watertight PLY with colours: a stand-in sculpt"""
    from skimage.measure import marching_cubes
    L = h + R_ + 0.05; g = np.linspace(-L, L, n); x, y, z = np.meshgrid(g, g, g, indexing="ij")
    sdf = np.sqrt(x ** 2 + y ** 2 + np.maximum(np.abs(z) - h, 0) ** 2) - R_
    V, F, _, _ = marching_cubes(sdf, 0.0, spacing=(g[1] - g[0],) * 3)
    V = V - L
    if Mesh(V, F, weld=False).signed_volume() < 0:
        F = F[:, ::-1]                              # outward
    C = np.full((len(V), 4), 200, np.uint8)
    write_ply(path, V, F, C)
    return path


@pytest.fixture(scope="module")
def blob(tmp_path_factory):
    return _blob(tmp_path_factory.mktemp("blob") / "high.ply")


def test_poly_selftest():
    poly._selftest()


def test_ply_roundtrip_and_mesh(blob, tmp_path):
    V, faces, C = read_ply(blob)
    m = Mesh.load(blob)
    assert m.edges_open() == 0 and m.signed_volume() > 0 and C is not None
    write_ply(tmp_path / "q.ply", [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [[0, 1, 2, 3]])
    V2, F2, _ = read_ply(tmp_path / "q.ply")
    assert len(V2) == 4 and list(F2[0]) == [0, 1, 2, 3]


def test_section_rays_closest(blob):
    s = Sculpt(blob)
    ps = s.slice((0, 0, 0.1), Z, X, Y)
    assert len(ps) == 1 and abs(ps[0].area - math.pi * 0.09) < 0.01        # a circle of radius 0.3
    assert abs(np.linalg.norm(ps[0].centroid)) < 0.01
    h = s.front(0.0, 0.0)
    assert abs(h[1] + 0.3) < 0.01                                          # the front surface at y = -0.3
    q = s.closest([[0.0, -1.0, 0.0]])[0]
    assert abs(q[1] + 0.3) < 0.01
    n = s.normal_at([0.0, -0.3, 0.0])
    assert n[1] < -0.9                                                     # outward = -y there
    c, Rr, rms = fit_sphere(s.verts_near((0, 0, 0.5), 0.6) [s.verts_near((0, 0, 0.5), 0.6)[:, 2] > 0.55])
    assert abs(Rr - 0.3) < 0.02 and rms < 0.01


def _capsule_cage(c):
    """a closed cage round the capsule: 8 rings of 16, a 6 x 2 cap each end"""
    A = [az(360 / 16 * k) for k in range(16)]
    T = [c.hring(z, A, centre=(0.0, 0.0)) for z in (-0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6)]
    for a, b in zip(T, T[1:]):
        c.bridge(a, b)
    top = c.cap_grid(T[-1], 6, 2, lambda i, j, p: c.top(p[0], p[1])); c.fill(top, 6, 2)
    bot = c.cap_grid(T[0], 6, 2, lambda i, j, p: c.bottom(p[0], p[1])); c.fill(bot, 6, 2)
    c.seam([t[8] for t in T], closed=False)
    return T


def test_cage_closed_and_saved(blob, tmp_path):
    c = Cage(Sculpt(blob)); T = _capsule_cage(c)
    c.pin(T[3][0]); c.groups["g"] = {T[3][1]: 0.5}
    V, F = c.save(str(tmp_path / "cage.ply"))
    rep = check.check_cage(V, F)
    assert rep["faults"] == [] and rep["genus"] == 0.0
    assert json.load(open(tmp_path / "cage_pinned.json")) and json.load(open(tmp_path / "cage_groups.json"))["g"]
    assert len(json.load(open(tmp_path / "cage_seams.json"))) == 6


def test_cage_open_is_refused(blob):
    c = Cage(Sculpt(blob)); T = _capsule_cage(c)
    c.F.pop()                                           # a missing quad: an open hole
    V = np.array(c.V); rep = check.check_cage(V, c.F)
    assert any("open edges" in f for f in rep["faults"])
    rep = check.check_cage(V, c.F + [[0, 1, 2]])
    assert any("not 4 distinct" in f for f in rep["faults"])


def test_ring_follows_directions_and_ring_even(blob):
    c = Cage(Sculpt(blob))
    r = c.hring(0.0, [az(d) for d in (0, 90, 180, 270)], centre=(0.0, 0.0))
    P = np.array([c.V[i] for i in r])
    assert np.allclose(P[:, 2], 0) and P[0][1] < -0.28 and P[1][0] > 0.28    # front, then +x
    e = c.ring_even((0, 0, 0.0), Z, X, Y, 8, (0, 0), (1, 0))
    Q = np.array([c.V[i] for i in e]); L = np.linalg.norm(np.diff(np.vstack([Q, Q[:1]]), axis=0), axis=1)
    assert L.std() / L.mean() < 0.05                                          # even by length


def test_tracks_and_snap(blob):
    c = Cage(Sculpt(blob))
    a = c.hring(0.0, [az(d) for d in (0, 120, 240)], centre=(0.0, 0.0))
    b = [c.add(np.asarray(c.V[i]) + np.array([0, 0, -0.2])) for i in a]
    mids = c.tracks(a, b, (0, 0, -1))
    assert len(mids) == 2 and all(len(m) == 3 for m in mids)
    pts = c.snap_to_sphere(a, (0, 0, 0), 0.1, (0, -1, 0), 60)
    assert all(abs(np.linalg.norm(p) - 0.1) < 1e-9 for p in pts)


def test_input_check_flags_inside_out(blob, tmp_path):
    m = Mesh.load(blob)
    assert check.check_input(m)["faults"] == []
    inv = Mesh(m.V, m.F[:, ::-1], m.C, weld=False)
    assert any("INWARD" in f for f in check.check_input(inv)["faults"])


def test_props_cut_keeps_biggest_part(blob, tmp_path, monkeypatch):
    d = tmp_path / "ch"; R.start(str(d), str(blob))
    rep = R.props(str(d), eyes=[{"c": [0, -0.3, 0.3], "R": 0.05}])
    assert rep["removed_triangles"] > 0
    body = Mesh.load(d / "high_body.ply"); assert body.edges_open() > 0
    assert json.loads((d / "props.json").read_text())["cut"][0]["R"] == pytest.approx(0.056)
    rep = R.props(str(d), parts=[{"name": "crest", "cut": [{"type": "sphere", "c": [0, 0, 0.8], "R": 0.1}], "bone": "Head"}])
    J = json.loads((d / "props.json").read_text())
    assert J["cut_parts"][0]["file"] == "part_crest.ply" and Mesh.load(d / "part_crest.ply").F.shape[0] > 10


def test_cage_tool_runs_code_and_keeps_versions(blob, tmp_path):
    d = tmp_path / "ch"; R.start(str(d), str(blob))
    code = ("A = [az(360 / 16 * k) for k in range(16)]\n"
            "T = [c.hring(z, A, centre=(0.0, 0.0)) for z in (-0.4, 0.0, 0.4)]\n"
            "c.bridge(T[0], T[1]); c.bridge(T[1], T[2])\n"
            "g = c.cap_grid(T[2], 6, 2, lambda i, j, p: c.top(p[0], p[1])); c.fill(g, 6, 2)\n"
            "b = c.cap_grid(T[0], 6, 2, lambda i, j, p: c.bottom(p[0], p[1])); c.fill(b, 6, 2)\n")
    rep = R.cage(str(d), code)
    assert rep["faults"] == [] and rep["version"] == 1
    rep = R.cage(str(d), code.replace("c.bridge(T[0], T[1]); ", ""))
    assert rep["version"] == 2 and rep["faults"]
    assert (d / "cage_v1.py").exists() and (d / "cage_v2.py").exists()


def test_mouth_groups(blob):
    """the mouth on the capsule's front: lips split and pinned, a bag behind, groups written"""
    c = Cage(Sculpt(blob))
    root = []
    for k in range(12):
        t = 2 * math.pi * k / 12 - math.pi / 2
        root.append(c.add(c.front(0.12 * math.cos(t), 0.12 * math.sin(t))))
    r1 = c.inset(root, (0.0, 0.0), 0.78); c.bridge(root, r1)
    r2 = c.inset(root, (0.0, 0.0), 0.5); c.bridge(r1, r2)
    out = c.mouth(r1, r2, lip=[1, 2, 3])
    assert len(out["mouth"]) == 8 and len(out["bag"]) == 3            # the lip roll + two sock rings
    gap = np.asarray(c.V[out["upper"][2]]) - np.asarray(c.V[r2[2]])
    assert abs(gap[2] - 0.0005) < 1e-9                                   # the lips meet at rest
    assert {r2[1], r2[2], r2[3], out["upper"][1]} <= c.pinned
    jaw = c.groups["jaw"]; assert jaw[out["mouth"][0]] == 0.5 and jaw[r2[2]] == 1.0
    assert c.groups["mouth_inside"] and not (c.groups["mouth_inside"] & set(out["mouth"]))


def test_fill_repairs_misses_and_mouth(tmp_path):
    from PIL import Image
    n = 32; d = tmp_path
    col = np.full((n, n, 3), 100, np.uint8); col[10:14, 10:14] = 0
    nor = np.full((n, n, 3), 128, np.uint8)
    cov = np.full((n, n), 255, np.uint8); cov[10:14, 10:14] = 0
    isl = np.full((n, n), 255, np.uint8); isl[:, -4:] = 0
    mouth = np.zeros((n, n), np.uint8); mouth[0:4, 0:4] = 255
    for f, a in (("color.png", col), ("normal.png", nor), ("low_cover.png", cov), ("low_island.png", isl), ("low_mouth.png", mouth)):
        Image.fromarray(a).save(d / f)
    rep = fill.repair(str(d), "low")
    out = np.asarray(Image.open(d / "color.png"))
    assert rep["misses"] == 16 and abs(int(out[12, 12, 0]) - 100) <= 2      # the hole filled from round it
    assert tuple(out[1, 1]) == (70, 22, 38)                                  # the mouth inside is dark
    assert out[5, -1, 0] == 100                                             # the gutter got the island's colour
    pp = fill.pull_push(np.full((8, 8, 3), 50, np.float32), np.ones((8, 8), bool))
    assert np.allclose(pp, 50)


@pytest.mark.slow
def test_press_and_bake_tiny(blob, tmp_path):
    """Blender end to end on the capsule: press (no folds), bake, repair, assemble -> final.glb"""
    from hifipushie import artretopo_steps as S
    d = tmp_path / "ch"; R.start(str(d), str(blob))
    R.cage(str(d), "A = [az(360 / 16 * k) for k in range(16)]\n"
                   "T = [c.hring(z, A, centre=(0.0, 0.0)) for z in (-0.6, -0.3, 0.0, 0.3, 0.6)]\n"
                   "for a, b in zip(T, T[1:]): c.bridge(a, b)\n"
                   "g = c.cap_grid(T[-1], 6, 2, lambda i, j, p: c.top(p[0], p[1])); c.fill(g, 6, 2)\n"
                   "b = c.cap_grid(T[0], 6, 2, lambda i, j, p: c.bottom(p[0], p[1])); c.fill(b, 6, 2)\n"
                   "c.seam([t[8] for t in T], closed=False); c.seam(T[0]); c.seam(T[-1])\n")
    p = S.press(str(d)); assert p["folded"] == 0 and p["low_faces"] > 1000
    b = S.bake(str(d), res=256); assert b["seams"] > 0 and (d / "low_uv.glb").exists()
    S.fill(str(d)); S.assemble(str(d)); S.compare(str(d))
    assert (d / "final.glb").exists() and (d / "final_cmp.jpg").exists()
    joints = {"hips": [0, 0, -0.3], "spine": [0, 0, -0.15], "spine1": [0, 0, 0.0], "spine2": [0, 0, 0.15],
              "neck": [0, 0, 0.4], "head": [0, 0, 0.5], "head_top": [0, 0, 0.75], "clavicle": [0.02, 0, 0.35],
              "shoulder": [0.2, 0, 0.35], "elbow": [0.25, 0, 0.1], "wrist": [0.27, 0, -0.1], "hand_end": [0.28, 0, -0.15],
              "hip": [0.1, 0, -0.35], "knee": [0.1, 0, -0.55], "ankle": [0.1, 0, -0.7], "toe": [0.1, -0.05, -0.75],
              "toe_end": [0.1, -0.1, -0.78]}
    info = S.rig(str(d), joints); assert info["bones"] >= 25
    rom = S.rom(str(d), poses=["spine_side_30", {"lean": [["Spine", [0, 1, 0], 20]]}], close_ups=False,
                close={"lean": {"view": [0, -1, 0], "target": [0, 0, 0], "scale": 1.5}})
    assert set(rom["poses"]) == {"rest", "spine_side_30", "lean"} and (d / "close_custom.jpg").exists()
    assert S.lod(str(d))["lod1_faces"] > 100 and (d / "lod1_rigged.glb").exists()


def test_symmetry_yaw_turns_a_yawed_sculpt_back():
    """oxidegen turns the sculpt by the concept camera's yaw: find the turn that puts its mirror plane on x = 0"""
    rng = np.random.default_rng(1)
    P = rng.normal(size=(3000, 3)) * [0.1, 0.2, 0.4]; P[:, 1] += 0.3 * (P[:, 2] > 0.3)   # face forward-ish
    P = np.vstack([P, P * [-1, 1, 1]])                                                  # mirror-symmetric in x
    r = np.radians(-30); Rz = np.array([[np.cos(r), -np.sin(r), 0], [np.sin(r), np.cos(r), 0], [0, 0, 1]])
    yaw, _, err = check.symmetry_yaw(P @ Rz.T + [0.05, 0, 0])
    assert abs(yaw - 30) < 1.0 and err < 0.02


def test_measures(blob):
    from hifipushie import artretopo_measure as M
    s = Sculpt(blob)
    assert M.extreme(s, (-1, -1, 0.5), (1, 1, 1), (0, 0, 1))["point"][2] > 0.79       # the capsule's top
    hits = M.ray(s, (0, -2, 0), (0, 1, 0))["hits"]
    assert len(hits) == 2 and abs(hits[1]["t"] - hits[0]["t"] - 0.6) < 0.01
    assert abs(M.thickness(s, (0.0, -0.5, 0.0))["thickness"] - 0.6) < 0.01
    assert M.colour_at(s, (0, -0.3, 0), 0.05)["rgb"] == [200, 200, 200]
    cyl = M.fit_cylinder(s, "z", [-0.3, 0.0, 0.3], (0, 0))
    assert abs(cyl["R"] - 0.3) < 0.01 and cyl["R_spread"] < 0.01 and abs(cyl["c"][0]) < 0.01


def test_retopo_tools_are_registered_and_documented():
    from hifipushie import mcp_app, server, tools_find  # noqa: F401 (server registers every tool)
    names = mcp_app.TOOL_GROUPS["retopo"]["tools"]
    assert {"retopo_measure", "retopo_fill", "retopo_assemble", "retopo_compare", "retopo_rom", "retopo_lod"} <= set(names)
    for n in names:
        assert n in mcp_app._TOOLS and tools_find._tool_section(n)
    assert "def build" in tools_find.guide("retopo_scraps") or "c.mouth" in tools_find.guide("retopo_scraps")


def test_ring_clip_takes_the_part_beyond_a_line_and_pins_the_cut(blob):
    c = Cage(Sculpt(blob))
    r = c.ring_clip((0, 0, 0.0), Z, X, Y, 8, ((0.15, 0.0), (1.0, 0.0)), (0.2, 0.0), (1, 0))
    P = np.array([c.V[i] for i in r])
    assert (P[:, 0] >= 0.15 - 1e-9).all() and P[:, 0].max() > 0.29                   # beyond x = 0.15, out to the side
    assert any(i in c.pinned for i in r) and not all(i in c.pinned for i in r)       # the cut edge invented


def test_crease_finds_the_notch(tmp_path):
    """a capsule with a groove round it at z = 0.1: the crease is the groove's deepest point"""
    from skimage.measure import marching_cubes
    L = 0.9; g = np.linspace(-L, L, 72); x, y, z = np.meshgrid(g, g, g, indexing="ij")
    sdf = np.sqrt(x ** 2 + y ** 2 + np.maximum(np.abs(z) - 0.5, 0) ** 2) - 0.3 + 0.04 * np.exp(-((z - 0.1) / 0.03) ** 2)
    V, F, _, _ = marching_cubes(sdf, 0.0, spacing=(g[1] - g[0],) * 3); V = V - L
    if Mesh(V, F, weld=False).signed_volume() < 0:
        F = F[:, ::-1]
    write_ply(tmp_path / "g.ply", V, F)
    p = Sculpt(tmp_path / "g.ply").crease(0.0, 0.0, 0.2)
    assert abs(p[2] - 0.1) < 0.02 and p[1] > -0.28
