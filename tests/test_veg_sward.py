"""A sward (veg_sward): plain grass as a tile of blades. No Blender."""
import json
import struct

import numpy as np
import pytest

from hifipushie import veg_export, veg_sward, vegetation


def _tile(spec=None):
    return vegetation.grow(spec or {"species": "sward"})


def test_variants_and_unknown_keys():
    h = {}
    for sp in ("sward_mown", "sward", "sward_rough"):
        T = _tile({"species": sp})
        assert T["sward"] and T["height"] > 0
        h[sp] = T["height"]
    assert h["sward_mown"] < 0.1 < h["sward"] < h["sward_rough"]
    with pytest.raises(ValueError):
        vegetation.grow({"species": "sward", "sward": {"hight": 1}})
    with pytest.raises(ValueError):
        vegetation.grow({"species": "sward", "sward": {"variant": "lawn"}})


def test_tile_is_periodic():
    S = 2.0
    xy = np.random.default_rng(1).random((500, 2)) * S
    for cell in (0.4, 0.5, 1.0):
        a = veg_sward.tile_noise(xy, S, cell, 3)
        assert np.allclose(a, veg_sward.tile_noise(xy + [S, 0], S, cell, 3)) and np.allclose(a, veg_sward.tile_noise(xy + [0, S], S, cell, 3))
    B = veg_sward.blades(vegetation.resolve({"species": "sward"}))
    r = B["root"]
    assert (r >= -0.02).all() and (r <= S + 0.02).all()
    # no grid: roots are spread evenly (every 0.25 m cell of the tile holds blades), none bare
    c = np.histogram2d(r[:, 0], r[:, 1], bins=8, range=[[0, S], [0, S]])[0]
    assert c.min() > 0.3 * c.mean()


def test_lods_are_nested_and_cover_alike():
    T = _tile()
    b = T["built"]
    info = b["info"]
    assert [i["blades"] for i in info] == sorted([i["blades"] for i in info], reverse=True)
    assert info[0]["triangles_per_m2"] > 4 * info[1]["triangles_per_m2"] > 4 * info[-1]["triangles_per_m2"] > 0
    # a blade's plan area x the blades kept stays within a factor of two from LOD to LOD (fewer, wider)
    p = b["p"]
    area = [sh * wd for sh, wd, _ in p["lods"]]
    assert max(area) / min(area) <= 2.0
    assert len(p["rings"]) == len(p["lods"]) - 1


def test_undersides_are_their_own_faces_with_mirrored_normals():
    M = _tile()["built"]["lods"][0]
    n = len(M["V"]) // 2
    assert np.allclose(M["V"][:n], M["V"][n:])
    assert (M["N"][:, 2] > 0).all()  # (no normal points into the ground: an engine's back-face flip never happens)
    V, F = M["V"], M["F"]
    f0, f1 = F[: len(F) // 2], F[len(F) // 2:]
    n0 = np.cross(V[f0[:, 1]] - V[f0[:, 0]], V[f0[:, 2]] - V[f0[:, 0]])
    n1 = np.cross(V[f1[:, 1]] - V[f1[:, 0]], V[f1[:, 2]] - V[f1[:, 0]])
    assert (np.einsum("ij,ij->i", n0, n1) < 0).all()
    # the front is the blade's upper face
    assert np.mean(n0[:, 2] > 0) > 0.95


def test_styles_change_the_blades_not_the_tile():
    real = _tile()["built"]
    for st, wider in (("blobby", True), ("cartoon", True), ("pixar", False), ("anime", False)):
        b = _tile({"species": "sward", "style": st})["built"]
        assert b["p"]["style_name"] == st and b["p"]["size"] == real["p"]["size"]
        assert (b["p"]["width"] > 1.5 * real["p"]["width"]) == wider
        assert b["p"]["ground"] != real["p"]["ground"]  # (through the sheet's colour, as the terrain style's grass)
    assert _tile({"species": "sward", "style": "pixar"})["built"]["info"][0]["blades"] > real["info"][0]["blades"]


def test_export_files_and_numbers(tmp_path):
    T = _tile({"species": "sward_mown", "style": "anime"})
    c = veg_sward.export(T, str(tmp_path), "sw")
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["sw.glb"] + [f"sw_LOD{k}.glb" for k in range(len(T["built"]["lods"]))] + ["sw_seasons.json"]
    sj = json.load(open(tmp_path / "sw_seasons.json"))
    assert sj["contract"]["version"] == veg_export.CONTRACT >= 11
    assert [e["slot"] for e in sj["slot_list"]] == ["foliage"]
    ch = sj["slot_list"][0]["channels"]
    assert {"COLOR_0", "TEXCOORD_1", "TEXCOORD_2", "TEXCOORD_3"} <= set(ch)
    assert sj["variants"] == ["summer", "spring", "autumn", "winter", "snow"]
    sw = sj["sward"]
    assert sw["tile_m"] == 2.0 and sw["fade"]["start"] < sw["fade"]["end"] and len(sw["ground_linear"]) == 3 and sw["lod_rings_m"]
    assert not sj["seasons"]["summer"]["foliage"]["doubleSided"]
    raw = open(tmp_path / "sw_LOD0.glb", "rb").read()
    jl = struct.unpack("<I", raw[12:16])[0]
    G, binp = json.loads(raw[20:20 + jl]), raw[20 + jl + 8:]
    a = G["accessors"][G["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"]]
    bv = G["bufferViews"][a["bufferView"]]
    col = np.frombuffer(binp, np.float32, a["count"] * 4, bv["byteOffset"]).reshape(-1, 4)
    assert col.max() <= 1.0 and col[:, :3].min() >= 0
    pos = G["accessors"][G["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert pos["min"][1] >= -1e-6 and abs(pos["min"][0] + pos["max"][0]) < 0.3  # (y up, the tile's middle at the origin)
    assert c["lods"][0]["triangles"] == T["built"]["info"][0]["triangles"]


def test_same_spec_same_tile():
    a, b = _tile()["built"]["lods"][0], _tile()["built"]["lods"][0]
    assert np.array_equal(a["V"], b["V"]) and np.array_equal(a["col"], b["col"])


def _drawn(M, d, lod):
    """The LOD recipe in numpy at one distance: per vertex (visible share of its blade, its drawn offset across)."""
    dist, share, band = np.array(lod["dist"]), np.array(lod["share"]), lod["band"]
    S = float(np.exp(np.interp(d, dist, np.log(share))))
    lo = S - max(1e-4, band * S * min(max((1 - S) * 8, 0), 1))
    t = np.clip((M["lodv"][:, 0] - lo) / (S - lo), 0, 1)
    vis = 1 - t * t * (3 - 2 * t)
    return vis, M["across"] * (vis / (S * M["lodv"][:, 1] * (1 - 0.5 * (S - lo) / S)))[:, None], S


def test_lod_thins_per_blade_and_meets_the_next_mesh(tmp_path):
    T = vegetation.grow({"species": "sward"})
    b = T["built"]
    r = veg_sward.export(T, str(tmp_path), "sw", seasons=("summer", "autumn"))
    lod = r["sward"]["lod"]
    assert lod["share"] == [l_[0] for l_ in b["p"]["lods"]] and lod["dist"][1:] == [float(x) for x in b["p"]["rings"]]
    for k in range(1, len(b["lods"])):
        A, B = b["lods"][k - 1], b["lods"][k]
        va, xa, S = _drawn(A, lod["dist"][k], lod)
        vb, xb, _ = _drawn(B, lod["dist"][k], lod)
        assert abs(S - lod["share"][k]) < 1e-9
        # at the ring the finer mesh draws none of the blades the coarser one lacks, and the same width on the ground
        assert not (va[A["lodv"][:, 0] >= S] > 1e-6).any()
        ground = lambda M, x, v: float((np.linalg.norm(x, axis=1) * v)[M["uv"][:, 1] == 0].sum())
        assert ground(A, xa, va) == pytest.approx(ground(B, xb, vb), rel=0.02)
    v0, x0, S0 = _drawn(b["lods"][0], 0.5, lod)  # near the eye nothing is thinned or widened
    assert S0 == 1.0 and (v0 == 1).all() and np.allclose(x0, b["lods"][0]["across"], rtol=1e-3)
    raw = open(r["path"], "rb").read()
    G = json.loads(raw[20:20 + struct.unpack("<I", raw[12:16])[0]])
    at = G["meshes"][0]["primitives"][0]["attributes"]
    assert "TEXCOORD_4" in at and "TEXCOORD_5" in at
    assert r["sward"]["fade"]["blend_from"] < r["sward"]["fade"]["start"]
