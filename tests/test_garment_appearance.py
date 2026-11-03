"""T14: the appearance step (garment_appearance): print on the grain, stitches along seams, wear only where planned."""
import json
import struct

import numpy as np
import pytest

from hifipushie import garment_appearance as ga, garment_record as gr


def _grid(x0, w, h, n, piece, z=0.0):
    xs, ys = np.meshgrid(np.linspace(0, w, n), np.linspace(0, h, n))
    uv = np.c_[xs.ravel(), ys.ravel()]
    F = []
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            F += [[a, a + 1, a + n + 1], [a, a + n + 1, a + n]]
    V = np.c_[uv[:, 0] + x0, np.full(len(uv), z), uv[:, 1]]
    return uv, np.array(F), V, np.full(len(uv), piece)


def _drape(sewn=True, n=21):
    """Two 0.2 x 0.3 m pieces; piece A's right edge sewn to piece B's left edge."""
    ua, Fa, Va, pa = _grid(0.0, 0.2, 0.3, n, 0)
    ub, Fb, Vb, pb = _grid(0.2, 0.2, 0.3, n, 1)
    k = len(ua)
    sew = []
    if sewn:
        ra = [j * n + n - 1 for j in range(n)]
        lb = [k + j * n for j in range(n)]
        sew = list(zip(ra, lb))
    return {"V": np.vstack([Va, Vb]), "F": np.vstack([Fa, Fb + k]), "uv": np.vstack([ua, ub]), "piece": np.r_[pa, pb],
            "names": ["A", "B"], "sew": np.array(sew, int).reshape(-1, 2)}


CL = {"c": {"colour": [200, 200, 200], "fabric": "cotton"}}
QUIET = {"c": {"variation": {"amount": 0.0}, "stitch": {"edges": "none"}}}


def _pattern_xy(tex, drape, piece):
    lay = ga.layout(drape)
    n = tex["size"]
    r, c = np.nonzero(tex["pid"] == drape["names"].index(piece))
    lo, pos = lay["place"][piece]
    P = np.c_[(c + 0.5) / n, 1 - (r + 0.5) / n] * lay["side"] - pos + lo
    return r, c, P


@pytest.mark.parametrize("grain", [90.0, 45.0])
def test_print_runs_on_the_grain(grain):
    d = _drape()
    cl = {"c": dict(CL["c"], print={"kind": "stripe", "repeat_mm": 20, "colours": [[0, 0, 255]], "line_mm": 4})}
    tex = ga.bake(d, {"A": "c", "B": "c"}, cl, QUIET, {"A": grain, "B": grain}, 512)
    r, c, P = _pattern_xy(tex, d, "A")
    blue = tex["base"][r, c, 2].astype(float) - tex["base"][r, c, 0]
    g = np.radians(grain)
    across = -P[:, 0] * np.sin(g) + P[:, 1] * np.cos(g)
    along = P[:, 0] * np.cos(g) + P[:, 1] * np.sin(g)
    on = blue > 60
    assert 0.1 < on.mean() < 0.35  # 4 mm lines every 20 mm
    # a stripe is a function of `across` only: texels in one narrow across-band agree whatever their `along`
    band = np.abs(((across / 0.02) % 1) - 0.5) < 0.04  # mid-way between lines
    assert band.sum() > 50 and not on[band].any()
    line = np.abs(((across / 0.02 + 0.5) % 1) - 0.5) < 0.03  # on the lines
    assert on[line].mean() > 0.95 and np.ptp(along[line]) > 0.1


def test_stitches_follow_the_seam_not_the_free_edges():
    d = _drape()
    plan = {"c": {"variation": {"amount": 0.0}, "stitch": {"edges": "seams", "colour": [255, 0, 0], "offset_mm": 4}}}
    tex = ga.bake(d, {"A": "c", "B": "c"}, CL, plan, {"A": 90, "B": 90}, 1024)
    r, c, P = _pattern_xy(tex, d, "A")
    red = (tex["base"][r, c, 0].astype(int) - tex["base"][r, c, 2]) > 25
    assert red.sum() > 50
    x, y = P[red, 0], P[red, 1]
    assert np.all(np.abs(x - (0.2 - 0.004)) < 0.0015)  # 4 mm inside the sewn (right) edge, nowhere else
    assert np.ptp(y) > 0.25  # all the way along it
    # the stitches are dashes: along the seam, texels on the line are part stitch, part cloth
    online = np.abs(P[:, 0] - 0.196) < 0.0003
    assert 0.4 < red[online].mean() < 0.9
    plan["c"]["stitch"]["edges"] = "hems"
    tex = ga.bake(d, {"A": "c", "B": "c"}, CL, plan, {"A": 90, "B": 90}, 1024)
    r, c, P = _pattern_xy(tex, d, "A")
    red = (tex["base"][r, c, 0].astype(int) - tex["base"][r, c, 2]) > 25
    mid = (P[:, 1] > 0.02) & (P[:, 1] < 0.28)  # (away from the corners, where the top / bottom hems cross x = 0.196)
    assert red.any() and not np.any(np.abs(P[red & mid, 0] - 0.196) < 0.0015)  # hems only: the seam side stays clean
    assert np.any(np.abs(P[red & mid, 0] - 0.004) < 0.0015)  # the free left edge is stitched


def test_wear_only_where_the_plan_says():
    d = _drape()
    body = d["V"] + np.array([0.0, 0.005, 0.0])  # touching everywhere
    rb = [{"name": "mixamorig:LeftForeArm", "head": [0.1, 0.0, 0.15]}, {"name": "mixamorig:LeftLeg", "head": [0.3, 0.0, 0.15]}]
    w = ga.high_point_wear(d, body, rb, ["elbows"])
    near = np.linalg.norm(d["V"] - [0.1, 0.0, 0.15], axis=1) < 0.03
    assert w[near].min() > 0.5 and w[d["piece"] == 1].max() < 0.2  # the elbow (on A), not the knee (on B)
    assert not ga.high_point_wear(d, body, rb, []).any()
    cl = {"a": {"colour": [120, 60, 40]}, "b": {"colour": [120, 60, 40]}}
    q = {"variation": {"amount": 0.0}, "stitch": {"edges": "none"}, "edges": 0.0}
    plan = {"a": dict(q, wear=1.0, why="t", where=["elbows"]), "b": dict(q, wear=0.0)}
    tex = ga.bake(d, {"A": "a", "B": "b"}, cl, plan, {"A": 90, "B": 90}, 256, {"a": w})
    new = ga.bake(d, {"A": "a", "B": "b"}, cl, {"a": dict(q), "b": dict(q)}, {"A": 90, "B": 90}, 256)
    diff = np.abs(tex["base"][..., :3].astype(int) - new["base"][..., :3]).sum(2)
    assert diff[tex["pid"] == 1].max() == 0  # B: no wear planned, untouched
    assert diff[tex["pid"] == 0].max() > 10  # A: worn at the elbow
    assert (diff[tex["pid"] == 0] > 3).mean() < 0.5  # and only there


def test_plan_check_and_fray():
    assert any("why" in b for b in ga.check_plan({"c": {"wear": 0.3}}, ["c"]))
    assert any("unknown" in b for b in ga.check_plan({"c": {"colur": 1}}, ["c"]))
    assert any("not a cloth" in b for b in ga.check_plan({"x": {}}, ["c"]))
    assert any("material" in b for b in ga.check_plan({"details": {"btn": {"material": "gold"}}}, ["c"], ["btn"]))
    assert not ga.check_plan({"c": {"wear": 0.2, "why": "a season's use", "where": ["elbows"]}}, ["c"])
    d = _drape(sewn=True)
    plan = {"c": {"variation": {"amount": 0.0}, "fray": {"pieces": ["B"], "depth_mm": 15}}}
    tex = ga.bake(d, {"A": "c", "B": "c"}, CL, plan, {"A": 90, "B": 90}, 512)
    a = tex["base"][..., 3]
    assert tex["alpha_cut"] and (a[tex["pid"] == 0] == 255).all() and (a[tex["pid"] == 1] == 0).any()


def test_record_step_and_glb_textures(tmp_path):
    i = gr.IDS.index("9a")
    assert gr.IDS[i - 1] == "9" and gr.IDS[i + 1] == "10" and gr.STEP["appearance"]["id"] == "9a"
    from PIL import Image
    from hifipushie import garment_glb
    png = tmp_path / "b.png"
    Image.new("RGB", (8, 8), (10, 20, 30)).save(png)
    m = {"name": "g", "V": np.eye(3), "T": [[0, 1, 2]], "uv": np.zeros((3, 2)), "textures": {"base": png, "mr": png, "normal": png}}
    p = garment_glb.write(tmp_path / "g.glb", "g", [m])
    raw = p.read_bytes()
    g = json.loads(raw[20:20 + struct.unpack("<I", raw[12:16])[0]])
    mat = g["materials"][0]
    assert len(g["images"]) == 3 and "baseColorTexture" in mat["pbrMetallicRoughness"] and "normalTexture" in mat
