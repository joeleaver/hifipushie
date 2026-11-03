"""F9: the SDF block-in (garment_blockin) and the pattern mapped onto it (blockin_map), on a synthetic body cylinder."""
from types import SimpleNamespace

import numpy as np
import pytest

from hifipushie import blockin_map as bm, garment_blockin as gb
from hifipushie.chain_garment import Body

R0, EASE = 0.10, 0.010
R = R0 + EASE
TOP, BOT = 0.70, 0.30


def _cylinder(r=R0, z0=0.1, z1=0.9, n=96, m=60):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    z = np.linspace(z0, z1, m)
    V = np.array([[r * np.cos(t), r * np.sin(t), h] for h in z for t in a])
    F = []
    for j in range(m - 1):
        for i in range(n):
            p, q = j * n + i, j * n + (i + 1) % n
            F += [(p, q, q + n), (p, q + n, p + n)]
    c0, c1 = len(V), len(V) + 1
    V = np.r_[V, [[0, 0, z0], [0, 0, z1]]]
    for i in range(n):
        F += [(c0, (i + 1) % n, i), (c1, (m - 1) * n + i, (m - 1) * n + (i + 1) % n)]
    return Body(V, np.array(F), {"waist_z": TOP})


BI = {"ease": [{"at": 0.0, "mm": EASE * 1000}], "voxel_mm": 5,
      "cuts": [{"z": "waist_z", "keep": "below"}, {"z": BOT, "keep": "above"}],
      "seams": [{"name": "front:side", "plane": {"y": 0.0}}],
      "regions": [{"piece": "front", "seed": [0.0, -0.2, 0.5], "mirror": False},
                  {"piece": "back", "seed": [0.0, 0.2, 0.5], "mirror": False}]}


@pytest.fixture(scope="module")
def blk():
    return gb.build(BI, _cylinder())


def test_blockin_regions_and_seam_lines(blk):
    assert gb.validate(BI, {"waist_z": TOP}) == []
    assert blk.reads["unassigned_area_pct"] < 1.0
    area = np.pi * R * (TOP - BOT)
    for p in ("front", "back"):
        assert abs(blk.reads["regions"][p] / 1e4 / area - 1) < 0.04
    lines = blk.seams[("front", "back")] if ("front", "back") in blk.seams else blk.seams[("back", "front")]
    assert len(lines) == 2
    for l in lines:
        assert abs(gb._plen(l) - (TOP - BOT)) < 0.012


def _fake(height=TOP - BOT, nu=24, nv=20):
    """Two panels (front, back), each half the block-in's girth wide, sewn along both long edges."""
    W = np.pi * R
    uv, piece, F, names = [], [], [], ["front", "back"]
    for k, p in enumerate(names):
        o = len(uv)
        for j in range(nv + 1):
            for i in range(nu + 1):
                uv.append((W * i / nu, -height * j / nv))
                piece.append(k)
        for j in range(nv):
            for i in range(nu):
                a = o + j * (nu + 1) + i
                F += [(a, a + 1, a + nu + 2), (a, a + nu + 2, a + nu + 1)]
    uv, piece, F = np.array(uv), np.array(piece), np.array(F)
    col = lambda k, i: np.array([k * (nu + 1) * (nv + 1) + j * (nu + 1) + i for j in range(nv + 1)])
    S = np.r_[np.c_[col(0, nu), col(1, 0)], np.c_[col(0, 0), col(1, nu)]]
    ss = np.r_[np.zeros(nv + 1, int), np.ones(nv + 1, int)]
    n = len(uv)
    net = SimpleNamespace(names=names, piece=piece, uv=uv, F=F, sew=S, n=n, M={"sew_seam": ss},
                          verts=lambda p: np.where(piece == names.index(p))[0], pid=lambda p: names.index(p))
    b = SimpleNamespace(net=net, roles=SimpleNamespace(panels=names, tubes=[]), reads={},
                        _stiff_mask=lambda: np.zeros(n, bool))
    # the guide: each panel round its half (front at -y), top at TOP
    G = np.zeros((n, 3))
    for k in range(2):
        m = piece == k
        phi = -np.pi / 2 + uv[m, 0] / R + k * np.pi
        G[m] = np.c_[R * 1.3 * np.sin(phi), -R * 1.3 * np.cos(phi), TOP + uv[m, 1]]
    return b, G


def test_matching_piece_maps_with_no_distortion(blk):
    b, G = _fake()
    r = bm.check(b, blk, G)
    assert r["verdict"] == "PASS", [x for x in r["rows"] if x["status"] != "PASS"]
    for row in r["rows"]:
        if row["id"].startswith("map:"):
            assert abs(row["value"]) < 12
    for p, st in r["map"]["pieces"].items():
        assert abs(st["stretch"]["along"][1] - 1) < 0.05 and abs(st["stretch"]["across"][1] - 1) < 0.06


def test_too_long_piece_flagged_by_seam_and_way(blk):
    b, G = _fake(height=TOP - BOT + 0.12)
    r = bm.check(b, blk, G)
    assert r["verdict"] == "FAIL"
    bad = [x for x in r["rows"] if x["id"].startswith("map:") and x["status"] == "FAIL"]
    assert len(bad) == 2 and all("too long" in x["why"] and "front:side" in x["why"] for x in bad)


def test_start_seams_closed(blk):
    b, G = _fake()
    X = bm.start(b, blk, G)
    S = b.net.sew
    assert np.linalg.norm(X[S[:, 0]] - X[S[:, 1]], axis=1).max() < 1e-9
    # every point on the block-in, outside the body
    rr = np.linalg.norm(X[:, :2], axis=1)
    assert rr.min() > R0 and abs(np.median(rr) - R) < 0.004


# ---- F10 (C331, C333): the fork ceiling; the plan's block-in is the start


def _fork_z(at):
    """The highest z on the centre line (x = y = 0) where a two-cone block-in is open (field > 0), far from any body."""
    bi = {"ease": [{"at": 0.0, "mm": 10}],
          "shapes": [{"kind": "cone", "a": [0.06, 0.0, 0.95], "b": [0.09, 0.0, 0.1], "r_a": 0.1, "r_b": 0.07}]}
    z = np.linspace(0.1, 0.95, 171)
    P = np.c_[np.zeros_like(z), np.zeros_like(z), z]
    f = gb.field(bi, SimpleNamespace(at=at), P, np.full(len(z), 1.0))
    return float(z[f > 0].max()) if (f > 0).any() else None


def test_fork_ceiling_keeps_the_fork_at_the_bodys_crotch():
    low = _fork_z({})  # (F9's fault: the cones and their smooth union fill the notch far below the crotch)
    assert low is not None and low < 0.45
    fz = _fork_z({"crotch_z": 0.6})
    assert fz is not None and 0.6 - 0.02 <= fz <= 0.6 + 1e-9


def test_single_centred_shape_not_ceilinged():  # (a skirt's bell: one shape on the centre plane fills between the legs)
    bi = {"ease": [{"at": 0.0, "mm": 10}],
          "shapes": [{"kind": "cone", "a": [0.0, 0.0, 0.95], "b": [0.0, 0.0, 0.1], "r_a": 0.1, "r_b": 0.2}]}
    P = np.array([[0.0, 0.0, 0.3]])
    assert gb.field(bi, SimpleNamespace(at={"crotch_z": 0.6}), P, np.ones(1))[0] < 0


def test_plan_blockin_is_the_start(monkeypatch):
    from hifipushie import chain_garment as cg
    monkeypatch.delenv("HIFIPUSHIE_BLOCKIN_START", raising=False)
    assert cg.uses_blockin_start(SimpleNamespace(blockin=BI))
    assert not cg.uses_blockin_start(SimpleNamespace(blockin=None))
    monkeypatch.setenv("HIFIPUSHIE_BLOCKIN_START", "0")
    assert not cg.uses_blockin_start(SimpleNamespace(blockin=BI))
    spec = {"cloth": {"g": {"a": 1}}}
    assert cg.job_key(spec, "g", {"state": "closed"}) == cg.job_key(spec, "g", {"state": "closed"}, None)
    assert cg.job_key(spec, "g", {"state": "closed"}, BI) != cg.job_key(spec, "g", {"state": "closed"})
