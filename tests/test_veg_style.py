"""Vegetation styles: the same grown plant dressed another way. uv run python tests/test_veg_style.py"""
import json
import struct
import tempfile
from pathlib import Path

import numpy as np

from hifipushie import veg_export, veg_style as vs, vegetation as v

BASE = {"species": "birch", "age": 22}


def _glb(path):
    raw = open(path, "rb").read()
    jl = struct.unpack("<I", raw[12:16])[0]
    G = json.loads(raw[20:20 + jl])
    binp = raw[20 + jl + 8:]

    def arr(i):
        a = G["accessors"][i]
        bv = G["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        dt = {5126: np.float32, 5125: np.uint32}[a["componentType"]]
        return np.frombuffer(binp, dt, a["count"] * n, bv.get("byteOffset", 0)).reshape(-1, n)
    return G, arr


def test_same_individual():
    """A style never touches the growth: the skeleton is the realistic tree's, node for node."""
    a, b = v.grow(BASE), v.grow({**BASE, "style": "blobby"})
    assert np.array_equal(a["pos"], b["pos"]) and np.array_equal(a["radius"], b["radius"]) and a["height"] == b["height"]
    assert vs.sheet(a["spec"]) is None and vs.sheet(b["spec"])["name"] == "blobby"
    assert vs.sheet({"style": "realistic"}) is None


def test_sheet_overrides_and_unknowns():
    st = vs.sheet({"style": {"sheet": "blobby", "crown": {"masses": 4}, "budget": 3000}})
    assert st["crown"]["masses"] == 4 and st["budget"] == 3000 and st["wood"]["radius"] == vs.describe("blobby")["wood"]["radius"]
    for bad in ({"style": "nosuch"}, {"style": {"sheet": "blobby", "krown": {}}}, {"style": {"sheet": "blobby", "crown": {"mases": 3}}}):
        try:
            vs.sheet(bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_blobby_dress():
    T = v.grow({**BASE, "style": "blobby"})
    st = vs.sheet(T["spec"])
    D = vs.dress(T, st)
    i = D["info"]
    lo, hi = st["wood"]["limbs"]
    assert lo <= i["limbs_kept"] <= hi and i["axes_kept"] == 1 + i["limbs_kept"] + i["stubs"] < i["axes"]
    assert i["stubs"] <= st["wood"]["stubs"] * i["limbs_kept"] and i["core"] and i["blend_m"] >= st["crown"]["blend"]
    # the wood is one closed smooth surface too (forks are fillets), and every drawn limb ends inside the crown
    W = D["wood"]
    ew = np.sort(np.vstack([W["F"][:, [0, 1]], W["F"][:, [1, 2]], W["F"][:, [2, 0]]]), axis=1)
    assert (np.unique(ew, axis=0, return_counts=True)[1] == 2).mean() > 0.99
    ft = vs.fit(T, st)
    mini = ft["mini"]
    ends = [np.flatnonzero(mini["axis"] == a)[-1] for a in np.unique(mini["axis"]) if a > 0]
    dep = -vs.field(ft["ells"], mini["pos"][ends], ft["blend"])
    assert (dep > 0).all(), dep
    # toy proportions: limbs as stout as what they carry
    size = np.mean([e["r"].mean() for e in ft["ells"] if not e.get("core")])
    first = [np.flatnonzero(mini["axis"] == a)[0] for a in np.unique(mini["axis"][mini["order"] == 1])]
    assert min(mini["radius"][first]) >= 0.6 * st["wood"]["limb_mass"] * size
    assert st["crown"]["masses"][0] <= i["masses"] <= st["crown"]["masses"][1]
    assert i["triangles"] <= st["budget"] * 1.02, i["triangles"]
    C = D["crown"]
    V, F = C["V"], C["F"]
    # closed: every edge is shared by exactly two triangles
    e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    assert (cnt == 2).mean() > 0.995, (cnt != 2).sum()
    # outward, smooth normals: unit, and facing the way the faces do
    assert np.allclose(np.linalg.norm(C["N"], axis=1), 1, atol=1e-5)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    assert (np.einsum("ij,ij->i", fn, C["N"][F].mean(1)) > 0).mean() > 0.98
    # one tone per mass, a few across the tree, colours within glTF's 0..1
    assert 1 <= i["tones"] <= st["crown"]["tones"] and C["col"].min() >= 0 and C["col"].max() <= 1 + 1e-9
    for m in np.unique(C["mass"]):
        assert len(np.unique(C["col"][C["mass"] == m].round(5), axis=0)) == 1
    top, low = C["col"][C["tone"][C["mass"]] == C["tone"].max()], C["col"][C["tone"][C["mass"]] == C["tone"].min()]
    assert i["tones"] == 1 or top[:, 1].mean() > low[:, 1].mean()  # the top is lighter
    # ... in every season: the material's colour never clips a channel (autumn went flat orange)
    for se in ("summer", "spring", "autumn", "snow"):
        f = np.array(vs.material_color(vs.season_color(T["spec"], se, st), st))
        assert f.max() <= 1 + 1e-9 and f.min() >= 0
    assert D["forks"] is not None and i["forks_triangles"] > 0  # (a deciduous tree's forks: there for the bare season)
    # the same tree from afar
    m = i["match"]
    assert m["iou"] > 0.7, m
    assert abs(m["height_m"][1] - m["height_m"][0]) < 0.06 * m["height_m"][0], m
    # nothing under the ground but the trunk's foot
    assert V[:, 2].min() > 0
    # wind: the foot stands still, masses move, every channel within 0..1 and no flutter
    tr, br, ph, fl = C["wind"]
    for w in (tr, br, ph, fl):
        assert np.isfinite(w).all() and w.min() >= 0 and w.max() <= 1
    assert br.min() >= st["wind"]["mass"] - st["wind"]["squash"] and D["wood_wind"][0][D["wood"]["V"][:, 2] < 0.05].max() < 1e-3
    # lower LODs: the same masses, fewer triangles
    D2 = vs.dress(T, st, int(st["budget"] * 0.18))
    assert D2["info"]["masses"] == i["masses"] and D2["info"]["triangles"] < 0.3 * i["triangles"]
    assert abs(D2["crown"]["V"][:, 2].max() - V[:, 2].max()) < 0.3


def test_conifer_tiers():
    """A needle tree takes the sheet's `conifer` numbers: stacked tiers on a bare pole, a crown all year."""
    T = v.grow({"species": "norway_spruce", "age": 30, "style": "blobby"})
    st = vs.sheet(T["spec"])
    assert st["crown"]["kind"] == "tiers" and "conifer" not in st and vs.sheet({"style": "blobby"})["crown"]["kind"] == "masses"
    D = vs.dress(T, st)
    i = D["info"]
    assert 3 <= i["masses"] <= 5 and i["limbs_kept"] == 0 and D["forks"] is None and not i["core"]
    cz = [m["center"][2] for m in i["mass_list"]]
    assert cz == sorted(cz) and max(abs(m["center"][0]) + abs(m["center"][1]) for m in i["mass_list"]) < 0.15 * T["height"]  # stacked on the stem
    assert i["match"]["iou"] > 0.75 and i["triangles"] <= st["budget"] * 1.02
    assert vs.dress(T, st, season="winter")["crown"] is not None
    st2 = vs.sheet({**T["spec"], "style": {"sheet": "blobby", "conifer": {"crown": {"masses": 3}}}})
    assert st2["crown"]["masses"] == 3 and st2["crown"]["kind"] == "tiers"


def test_deterministic():
    a = vs.dress(v.grow({**BASE, "style": "blobby"}), vs.sheet({"style": "blobby"}))
    vs._FIT.clear()
    b = vs.dress(v.grow({**BASE, "style": "blobby"}), vs.sheet({"style": "blobby"}))
    assert np.array_equal(a["crown"]["V"], b["crown"]["V"]) and np.array_equal(a["wood"]["V"], b["wood"]["V"])


def test_seasons():
    T = v.grow({**BASE, "style": "blobby"})
    st = vs.sheet(T["spec"])
    cols = {se: vs.season_color(T["spec"], se, st) for se in vs.SEASONS}
    assert cols["winter"] is None and all(cols[se] is not None for se in ("spring", "summer", "autumn", "snow"))
    assert len({tuple(c) for c in cols.values() if c}) == 4
    assert cols["autumn"][0] > cols["autumn"][2] and cols["spring"][1] > cols["summer"][1]
    P = v.grow({"species": "norway_spruce", "age": 12})
    assert vs.season_color(P["spec"], "winter", st) is not None  # an evergreen keeps its crown
    Wn = vs.dress(v.grow({**BASE, "style": "blobby", "season": "winter"}), st, season="winter")
    assert Wn["crown"] is None
    # a bare tree keeps the summer tree's limbs and forks (it is fitted in leaf whatever the season)
    assert Wn["info"]["axes_kept"] == vs.dress(T, st)["info"]["axes_kept"] > 1 + Wn["info"]["limbs_kept"]
    # the realistic tree has a spring too: smaller, fresher leaves
    sp = veg_export.spring_leaves(T["spec"])
    assert sp["length"] < T["spec"]["leaves"].get("length", 0.07) and sp["color"] != T["spec"]["leaves"]["color"]


def test_export_contract():
    """The styled GLB keeps the realistic one's contract: node / mesh / material names, LODs, wind channels, variants,
    collision; its foliage is untextured geometry with COLOR_0."""
    T = v.grow({**BASE, "style": "blobby"})
    R = v.grow(BASE)
    with tempfile.TemporaryDirectory() as tmp:
        seasons = ("summer", "spring", "autumn", "winter", "snow")
        c = veg_export.write_glb(T, str(Path(tmp) / "b.glb"), "b", lods=3, seasons=seasons)
        veg_export.write_glb(R, str(Path(tmp) / "r.glb"), "b", triangles=6000, lods=3, seasons=("summer", "autumn", "winter"))
        G, arr = _glb(c["path"])
        Gr, _ = _glb(str(Path(tmp) / "r.glb"))
        names = lambda g: sorted(n["name"] for n in g["nodes"])
        assert names(G) == names(Gr)
        assert [m["name"] for m in G["materials"]][:2] == ["bark", "foliage"] == [m["name"] for m in Gr["materials"]][:2]
        assert "textures" not in G and [x["name"] for x in G["extensions"]["KHR_materials_variants"]["variants"]] == list(seasons)
        assert len(c["lods"]) == 3 and c["lods"][0]["triangles"] <= 5100 and c["lods"][2]["triangles"] < c["lods"][1]["triangles"] < c["lods"][0]["triangles"]
        fol = [m for m in G["meshes"] if m["name"].endswith("foliage")]
        assert len(fol) == 3
        for m in G["meshes"]:
            a = m["primitives"][0]["attributes"]
            assert {"POSITION", "NORMAL", "TEXCOORD_0", "TEXCOORD_1", "TEXCOORD_2", "_WIND"} <= set(a), m["name"]
        p = fol[0]["primitives"][0]
        col = arr(p["attributes"]["COLOR_0"])
        assert col.min() >= 0 and col.max() <= 1 and len(np.unique(col.round(4), axis=0)) <= 3
        maps = {v_: mp["material"] for mp in p["extensions"]["KHR_materials_variants"]["mappings"] for v_ in mp["variants"]}
        assert len(set(maps.values())) == 5
        winter = G["materials"][maps[seasons.index("winter")]]
        assert winter.get("alphaMode") == "MASK" and winter["alphaCutoff"] > 1  # a deciduous winter: bare
        ex = G["extras"]["hifipushie_plant"]
        assert ex["style"]["name"] == "blobby" and ex["style"]["simplified"] and ex["collision"][0]["capsules"]
        assert any(n.get("extras", {}).get("collision") for n in G["nodes"])
        # collision is the grown tree's, whatever the style
        assert ex["collision"] == Gr["extras"]["hifipushie_plant"]["collision"]
        assert winter["extras"]["hidden"] is True
        # for engines without variants / out-of-scene nodes: a seasons json and a collision file
        sj = veg_export.seasons_json(c["path"])
        assert sj["variants"] == list(seasons) and set(sj["slots"]) == {"bark", "foliage", "bark_forks"}
        # the forks: a second wood primitive, hidden except in the bare season
        assert sj["seasons"]["summer"]["bark_forks"]["hidden"] and not sj["seasons"]["winter"]["bark_forks"]["hidden"]
        assert len(G["meshes"][0]["primitives"]) == 2
        assert sj["seasons"]["winter"]["foliage"]["hidden"] and not sj["seasons"]["autumn"]["foliage"]["hidden"]
        assert sj["seasons"]["autumn"]["foliage"]["baseColorFactor"] != sj["seasons"]["summer"]["foliage"]["baseColorFactor"]
        assert json.loads(Path(sj["path"]).read_text())["default"] == "summer"
        sr = veg_export.seasons_json(str(Path(tmp) / "r.glb"))
        fs = [k for k in sr["slots"] if k.startswith("foliage")]  # (a budgeted tree's LODs may each have their own bough picture)
        assert fs and all(Path(tmp, sr["seasons"]["autumn"][k]["baseColorTexture"]["file"]).exists() for k in fs)
        assert all(sr["seasons"]["winter"][k]["hidden"] for k in fs)
        Gc, _ = _glb(veg_export.write_collision(T, str(Path(tmp) / "c.glb"), "b"))
        assert Gc["nodes"][Gc["scenes"][0]["nodes"][0]]["name"] == "b_collision-colonly" and Gc["extras"]["hifipushie_collision"]["capsules"]
        # the impostor: single sided, each quad drawn from both sides, normals up and out
        img = {"image": np.ones((8, 16, 4), np.float32), "size": 6.0, "height": 3.0}
        Gi, arr_i = _glb(veg_export.write_impostor(T, str(Path(tmp) / "i.glb"), "b", img))
        pi = Gi["meshes"][0]["primitives"][0]
        assert not Gi["materials"][pi["material"]].get("doubleSided") and len(arr_i(pi["indices"])) == 24
        assert arr_i(pi["attributes"]["NORMAL"])[:, 1].min() > 0.5  # (glTF is Y up)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
