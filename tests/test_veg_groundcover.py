"""Groundcover grade (veg_groundcover): cards, maps and files, from synthetic bakes (no Blender), plus one real bake
when Blender is there (slow: set HIFIPUSHIE_SLOW=1)."""
import json
import os
import struct

import numpy as np
import pytest

from hifipushie import veg_export, veg_groundcover as g


def _fake_bake(R=0.3, H=0.5, seasons=("summer", "winter")):
    """Renders as Blender would hand them: a few vertical 'blades' (opaque strips) per card, normals facing the camera."""
    frames = g.plane_frames(R, H)
    out = {}
    for si, se in enumerate(seasons):
        fr = []
        for fi, f in enumerate(frames):
            w, h = f["px"]
            al = np.zeros((h, w, 4), np.float32)
            for k in range(3):
                x = int(w * (0.3 + 0.2 * k)) + fi % 3
                top = int(h * (0.2 + 0.25 * si))  # (winter lower: lying)
                al[top:, x:x + 1, 3] = 1.0
            al[..., :3] = np.where(al[..., 3:] > 0, [0.3, 0.6, 0.2], 0)
            nb = np.zeros((h, w, 4), np.float32)
            nb[..., :3] = (np.asarray(f["back"]) * 0.5 + 0.5)
            nb[..., 3] = al[..., 3]
            sh = np.ones((h, w, 4), np.float32)
            u8 = lambda a_: (a_ * 255 + 0.5).astype(np.uint8)
            fr.append({"albedo": u8(al), "normal": u8(nb), "shade": u8(sh)})
        out[se] = fr
    return {"R": R, "H": H, "frames": frames, "renders": out}


def _glb(path):
    raw = open(path, "rb").read()
    jl = struct.unpack("<I", raw[12:16])[0]
    return json.loads(raw[20:20 + jl]), raw[20 + jl + 8:]


def _acc(G, binp, i):
    a = G["accessors"][i]
    bv = G["bufferViews"][a["bufferView"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    dt = np.float32 if a["componentType"] == 5126 else np.uint32
    return np.frombuffer(binp, dt, a["count"] * n, bv.get("byteOffset", 0)).reshape(a["count"], n)


def test_tiers_are_scatter_cheap():
    B = g.build({"clump": True, "spec": {}}, baked=_fake_bake())
    tris = [len(t["F"]) for t in B["tiers"]]
    assert 200 <= tris[0] <= 800, tris
    assert 30 <= tris[-1] <= 80, tris
    assert tris[0] > tris[1] > tris[2]


def test_flat_plant_gets_a_lying_card():
    B = g.build({"clump": True, "spec": {}}, baked=_fake_bake(R=0.3, H=0.12))
    assert all(t["flat"] for t in B["tiers"])
    assert len(B["tiers"][0]["F"]) <= 800 and len(B["tiers"][-1]["F"]) <= 80


def test_front_and_back_mirror_the_normal_map():
    B = g.build({"clump": True, "spec": {}}, baked=_fake_bake())
    C = B["tiers"][0]
    w = C["TAN"][:, 3]
    assert set(np.unique(w)) == {-1.0, 1.0} and (w > 0).sum() == (w < 0).sum()
    # normals lean up, each face's toward its own side (mirror images through the card); tangents square to them
    assert (C["N"][:, 2] > 0.6).all()
    fr0 = [f for f in g.plane_frames(0.3, 0.5) if f["tier"] == 0 and not f["top"]][0]
    n_v = (C["V"].shape[0] // 2) // len([f for f in g.plane_frames(0.3, 0.5) if f["tier"] == 0 and not f["top"]])
    nf, nb_ = C["N"][:n_v], C["N"][n_v:2 * n_v]
    b = fr0["back"]
    assert np.allclose(nb_, nf - 2 * (nf @ b)[:, None] * b[None], atol=1e-6)
    assert np.abs((C["N"] * C["TAN"][:, :3]).sum(1)).max() < 1e-6
    # front faces wind counter-clockwise about +back: their geometric normal agrees with the card's front
    V, F = C["V"], C["F"]
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    front = w[F[:, 0]] > 0
    nb = np.cross(fn[front][0], fn[~front][0])
    assert np.linalg.norm(nb) < 1e-9  # (back faces are the front's reversed)
    assert np.dot(fn[front][0], fn[~front][0]) < 0


def test_alpha_keeps_blades_over_the_cut_through_mips(monkeypatch):
    monkeypatch.setattr(g, "HALO", (0.0, 0.0, 0.49))  # (an option, off by default)
    B = g.build({"clump": True, "spec": {}}, baked=_fake_bake())
    A = B["maps"]["summer"][0][..., 3].astype(np.float32) / 255
    keep = np.zeros_like(A, bool)  # (the far tier's pictures: the near ones carry no halo)
    for i, f in enumerate(B["frames"]):
        if f["tier"] == len(g.TIERS) - 1 and B["box"][i] is not None:
            b, (x, y) = B["box"][i], B["at"][i]
            keep[y:y + b[3] - b[2], x:x + b[1] - b[0]] = True
    A = np.where(keep, A, 0.0)

    def drawn(a, k):
        for _ in range(k):
            h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
            a = a[:h, :w].reshape(h // 2, 2, w // 2, 2).mean((1, 3))
        return (a >= g.ALPHA_CUT).sum() * 4 ** k
    base = drawn(A, 0)
    plain = np.where(A >= g.ALPHA_CUT, 1.0, 0.0)
    assert drawn(A, 2) > 0.4 * base and drawn(plain, 2) < 0.2 * base  # (1 px blades: gone at mip 2 without the halo)
    assert (A[A < g.ALPHA_CUT] < g.ALPHA_CUT).all()


def test_export_files_contract_and_seasons(tmp_path):
    B = g.build({"clump": True, "spec": {}}, baked=_fake_bake())
    T = {"clump": True, "spec": {"species": "meadow_grass"}}
    c = g.export(T, str(tmp_path), "gc", built=B)
    names = sorted(os.path.basename(f) for f in c["files"])
    assert names == ["gc.glb", "gc_LOD0.glb", "gc_LOD1.glb", "gc_LOD2.glb", "gc_seasons.json"]
    sj = json.load(open(tmp_path / "gc_seasons.json"))
    assert sj["contract"]["version"] == veg_export.CONTRACT >= 10
    assert [e["slot"] for e in sj["slot_list"]] == ["foliage"]
    assert "TANGENT" in sj["slot_list"][0]["channels"] and "TEXCOORD_1" in sj["slot_list"][0]["channels"]
    assert sj["variants"] == ["summer", "winter"]
    for se in ("summer", "winter"):
        f = sj["seasons"][se]["foliage"]
        assert f["alphaMode"] == "MASK" and not f["doubleSided"] and "file" in f["baseColorTexture"] and "file" in f["normalTexture"]
    assert sj["seasons"]["summer"]["foliage"]["baseColorTexture"]["file"] != sj["seasons"]["winter"]["foliage"]["baseColorTexture"]["file"]
    G, binp = _glb(tmp_path / "gc_LOD2.glb")
    p = G["meshes"][0]["primitives"][0]
    uv = _acc(G, binp, p["attributes"]["TEXCOORD_0"])
    assert (uv >= 0).all() and (uv <= 1).all()
    assert len(_acc(G, binp, p["indices"])) // 3 == c["lods"][2]["triangles"]
    G, _ = _glb(tmp_path / "gc.glb")
    assert "MSFT_lod" in G["extensionsUsed"] and G["extras"]["hifipushie_plant"]["grade"] == "groundcover"


@pytest.mark.skipif(not os.environ.get("HIFIPUSHIE_SLOW"), reason="bakes in Blender (~5 min)")
def test_real_bake_daisy(tmp_path):
    from hifipushie import vegetation
    T = vegetation.grow({"species": "daisy", "style": "blobby"})
    c = g.export(T, str(tmp_path), "daisy", seasons=("summer", "winter"))
    assert c["lods"][0]["triangles"] <= 800 and c["lods"][-1]["triangles"] <= 80
    sj = json.load(open(c["seasons_file"]))
    assert sj["slot_list"][0]["slot"] == "foliage"


def test_heads_gather_and_get_their_own_cards():
    # two flowers of five petals each, 0.2 m apart: two heads
    ang = np.linspace(0, 2 * np.pi, 5, endpoint=False)
    C = np.vstack([np.c_[x0 + 0.03 * np.cos(ang), 0.03 * np.sin(ang), np.full(5, 0.4)] for x0 in (0.0, 0.2)])
    hs = g.clusters(C, np.full(10, 0.015))
    assert len(hs) == 2 and all(abs(h[0][2] - 0.4) < 1e-9 for h in hs)
    fr = g.plane_frames(0.3, 0.5, hs)
    for ti, tr in enumerate(g.TIERS):
        hc = [f for f in fr if f["tier"] == ti and f.get("head")]
        assert len(hc) == 4  # (two crossed cards a head)
        assert not any(f.get("heads_on_wedges") for f in fr if f["tier"] == ti)
    many = [([0.1 * k, 0.0, 0.4], 0.02, 0.01) for k in range(20)]
    fr = g.plane_frames(0.3, 0.5, many)
    assert not any(f.get("head") for f in fr) and all(f["heads_on_wedges"] for f in fr if not f["top"])
