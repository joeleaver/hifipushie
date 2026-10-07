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
    # (tiers with undercuts over a bare foot: the outline has notches and no skirt; smooth tiers to the ground were 0.85)
    assert i["match"]["iou"] > 0.65 and i["triangles"] <= st["budget"] * 1.02
    assert all(e.get("down") is not None and e["down"] < e["r"][2] for e in vs.fit(T, st)["ells"])  # eggs: flat below, round above
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
        # contract version and the full slot list lead the seasons json (an engine can refuse what it doesn't know)
        raw = json.loads(Path(sj["path"]).read_text())
        assert list(raw)[:2] == ["contract", "slot_list"] and raw["contract"]["version"] == veg_export.CONTRACT == max(veg_export.CONTRACT_LOG)
        sl = {e["slot"]: e for e in raw["slot_list"]}
        assert set(sl) == set(sj["slots"]) and sl["bark_forks"]["hidden_in"] == ["summer", "spring", "autumn", "snow"]
        assert sl["bark_forks"]["on"][0]["primitive"] == 1 and sl["foliage"]["hidden_in"] == ["winter"] and "COLOR_0" in sl["foliage"]["channels"]
        # the impostor: single sided; front and back of each quad are faces of their own with opposite normals and
        # their own tangent (w = -1 behind), so one normal map lights both; pictures face the cameras that made them
        img = {"image": np.ones((8, 16, 4), np.float32), "normal": np.full((8, 16, 3), 0.5, np.float32), "size": 6.0, "height": 3.0,
               "seasons": {"winter": {"image": np.zeros((8, 16, 4), np.float32), "normal": np.full((8, 16, 3), 0.5, np.float32)}}}
        Gi, arr_i = _glb(veg_export.write_impostor(T, str(Path(tmp) / "i.glb"), "b", img, ("summer", "winter")))
        pi = Gi["meshes"][0]["primitives"][0]
        mi = Gi["materials"][pi["material"]]
        assert not mi.get("doubleSided") and len(arr_i(pi["indices"])) == 24 and "normalTexture" in mi and mi["extras"]["receive_shadows"] is False
        assert len(Gi["images"]) == 3  # (two pictures, one normal map shared by both seasons)
        P, N, Tg, I = arr_i(pi["attributes"]["POSITION"]), arr_i(pi["attributes"]["NORMAL"]), arr_i(pi["attributes"]["TANGENT"]), arr_i(pi["indices"]).reshape(-1, 3)
        fn = np.cross(P[I[:, 1]] - P[I[:, 0]], P[I[:, 2]] - P[I[:, 0]])
        fn /= np.linalg.norm(fn, axis=1, keepdims=True)
        assert np.allclose(fn, N[I[:, 0]], atol=1e-5) and len(P) == 16
        assert np.allclose(np.cross(N, Tg[:, :3]) * Tg[:, 3:], [0, 1, 0], atol=1e-6)  # bitangent = up (glTF is Y up) on every face
        assert np.allclose(N[:4], [0, 0, 1]) and np.allclose(N[8:12], [-1, 0, 0])  # picture 1 faces Blender -y, picture 2 Blender -x
        si = veg_export.seasons_json(str(Path(tmp) / "i.glb"))
        assert si["slots"]["impostor"]["receive_shadows"] is False and Path(tmp, si["slots"]["impostor"]["normalTexture"]["file"]).exists()


def test_impostor_maps():
    """World normals from each view land in that quad's tangent frame; albedo is shaded and bled under the alpha."""
    h = 6
    A = np.zeros((h, h, 4), np.float32)
    A[2:4, 2:4] = [0.5, 0.5, 0.5, 1]
    sh = np.ones((h, h, 4), np.float32)
    sh[2:4, 2:4, 0] = 0.0
    out = []
    for right, front in veg_export.impostor_frames():
        n = 0.6 * front + 0.8 * np.array([0, 0, 1.0])  # facing the camera and up
        Nw = np.zeros((h, h, 4), np.float32)
        Nw[2:4, 2:4] = [*(n * 0.5 + 0.5), 1]
        out.append(Nw)
    m = veg_export.impostor_maps([A, A], out, [sh, sh], shade_amount=0.5, depth=1.0)
    assert m["image"].shape == (h, 2 * h, 4) and m["normal"].shape == (h, 2 * h, 3)
    for j in (0, 1):
        ts = m["normal"][2, 2 + h * j] * 2 - 1
        assert np.allclose(ts, [0, 0.8, 0.6], atol=0.02), ts
    assert np.allclose(m["normal"][0, 0] * 2 - 1, [0, 0.8, 0.6], atol=0.02)  # bled: no flat normal under the alpha
    assert m["image"][0, 0, 3] == 0 and 0.2 < m["image"][0, 0, 0] < 0.5 and m["image"][2, 2, 0] < 0.5  # albedo darkened by the shade, bled


def test_lod_normals_are_the_fields():
    """Every LOD's NORMAL is the field's gradient at its vertex (mixed `normals` toward out of the crown), never the
    low mesh's own face normals: a low LOD shades as smooth as the full one (the consumer once saw faceted creases)."""
    for sp in ({**BASE, "style": "blobby"}, {"species": "norway_spruce", "age": 30, "style": "blobby"}):
        T = v.grow(sp)
        st = vs.sheet(T["spec"])
        ft = vs.fit(T, st)
        ells, bl = ft["ells"], ft["blend"]
        cfn = lambda q: vs.field(ells, q, bl, floor=ft["floor"])
        wfn = lambda q: np.maximum(vs.wood_field(ft["wood"]["segs"], q, ft["wood"]["blend"]), -0.3 - q[:, 2])
        for share in (1.0, 0.45, 0.18):
            D = vs.dress(T, st, int(st["budget"] * share))
            C, W = D["crown"], D["wood"]
            g = vs.grad(cfn, C["V"])
            g /= np.linalg.norm(g, axis=1, keepdims=True)
            o = C["V"] - np.mean([e["c"] for e in ells], axis=0)
            o /= np.linalg.norm(o, axis=1, keepdims=True)
            w = float(st["crown"].get("normals", 0.0))
            n = (1 - w) * g + w * o
            n /= np.linalg.norm(n, axis=1, keepdims=True)
            assert (np.einsum("ij,ij->i", n, C["N"]) > 0.9999).all() and np.percentile(np.abs(cfn(C["V"])), 95) < 0.02, share
            gw = vs.grad(wfn, W["V"])
            gw /= np.linalg.norm(gw, axis=1, keepdims=True)
            assert (np.einsum("ij,ij->i", gw, W["N"]) > 0.9999).all(), share
        # and that is what the file holds
        with tempfile.TemporaryDirectory() as tmp:
            c = veg_export.write_glb(T, str(Path(tmp) / "b.glb"), "b", lods=3)
            G, arr = _glb(c["path"])
            for m in G["meshes"]:
                if not m["name"].endswith("foliage"):
                    continue
                at = m["primitives"][0]["attributes"]
                P, N = arr(at["POSITION"]).astype(float), arr(at["NORMAL"]).astype(float)
                Pb, Nb = np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1), np.stack([N[:, 0], -N[:, 2], N[:, 1]], 1)  # back to Z up
                g = vs.grad(cfn, Pb)
                g /= np.linalg.norm(g, axis=1, keepdims=True)
                o = Pb - np.mean([e["c"] for e in ells], axis=0)
                o /= np.linalg.norm(o, axis=1, keepdims=True)
                n = (1 - w) * g + w * o
                n /= np.linalg.norm(n, axis=1, keepdims=True)
                assert (np.einsum("ij,ij->i", n, Nb) > 0.999).all(), m["name"]


def test_clump_seasons():
    """A small plant through the year: colour, lying down in winter, layers only in their seasons; realistic and styled."""
    from hifipushie import veg_small
    G = {"species": "meadow_grass"}
    su, wi, sp = v.grow(G), v.grow({**G, "season": "winter"}), v.grow({**G, "season": "spring"})
    elev = lambda T: float(np.median(np.degrees(np.arcsin(np.clip(T["twigs"]["frame"][:, 2, 1], -1, 1)))))
    assert elev(wi) < elev(su) - 25 and wi["height"] < 0.7 * su["height"]
    assert len(sp["twigs"]["pos"]) == len(su["twigs"]["pos"]) - 3 == len(wi["twigs"]["pos"])  # the seed heads: summer and autumn only
    st = {se: veg_small.season_state(su["spec"], se) for se in vs.SEASONS}
    assert st["summer"]["color"] == list(su["spec"]["leaves"]["color"]) and st["winter"]["flatten"] > 0.5
    assert st["autumn"]["color"][0] > st["summer"]["color"][0] and veg_small.hidden_parts(su["spec"], "spring") == ["seed"]
    assert veg_small.season_state({**su["spec"], "leaves": {**su["spec"]["leaves"], "evergreen": False}}, "winter") is None
    try:
        v.grow({**G, "clump": {"seasons": {"monsoon": {}}}})
        raise AssertionError("unknown season")
    except ValueError:
        pass
    # the realistic export: a season's atlas has the pictures of layers out of season blanked
    a_su, a_sp = veg_export.season_atlas(su["spec"], "summer", [0.5, 0.5, 0.3]), veg_export.season_atlas(su["spec"], "spring", [0.5, 0.5, 0.3])
    assert a_sp["color"][..., 3].sum() < 0.97 * a_su["color"][..., 3].sum()


def test_blobby_clump():
    """Meadow grass in the blobby style: a few fat closed blades and balls on stalks from the same cards; slot `heads`."""
    T = v.grow({"species": "meadow_grass", "style": "blobby"})
    R = v.grow({"species": "meadow_grass"})
    assert np.array_equal(T["twigs"]["pos"], R["twigs"]["pos"])  # the same individual
    st = vs.sheet(T["spec"])
    D = vs.dress(T, st)
    i = D["info"]
    lo, hi = st["clump"]["blades"]
    assert lo <= i["blades"] <= hi and i["heads"] == 3 and i["triangles"] <= st["clump"]["budget"] * 1.05
    assert abs(i["match"]["height_m"][1] - i["match"]["height_m"][0]) < 0.1 * i["match"]["height_m"][0]
    assert abs(i["match"]["spread_m"][1] - i["match"]["spread_m"][0]) < 0.35 * i["match"]["spread_m"][0]
    C = D["crown"]
    e = np.sort(np.vstack([C["F"][:, [0, 1]], C["F"][:, [1, 2]], C["F"][:, [2, 0]]]), axis=1)
    assert (np.unique(e, axis=0, return_counts=True)[1] == 2).all()  # closed
    fn = np.cross(C["V"][C["F"][:, 1]] - C["V"][C["F"][:, 0]], C["V"][C["F"][:, 2]] - C["V"][C["F"][:, 0]])
    assert (np.einsum("ij,ij->i", fn, C["N"][C["F"]].mean(1)) > 0).mean() > 0.95  # faces outward (an engine culls the back)
    assert C["col"].max() <= 1 and len(np.unique(C["col"].round(4), axis=0)) <= st["clump"]["tones"]
    assert C["wind"][1].max() > 0.05 and C["wind"][1][C["uv"][:, 0] == 0].max() == 0  # bends from the foot
    assert D["heads"]["seasons"] == ["summer", "autumn"]
    low = vs.dress(T, st, 150)
    assert low["info"]["blades"] == i["blades"] and low["info"]["triangles"] < 0.5 * i["triangles"]
    assert vs.dress(v.grow({"species": "meadow_grass", "style": "blobby", "season": "winter"}), st, season="winter")["heads"] is None
    with tempfile.TemporaryDirectory() as tmp:
        seasons = ("summer", "spring", "autumn", "winter", "snow")
        c = veg_export.write_glb(T, str(Path(tmp) / "g.glb"), "g", lods=3, seasons=seasons)
        G, arr = _glb(c["path"])
        assert "textures" not in G and [l["triangles"] for l in c["lods"]] == sorted([l["triangles"] for l in c["lods"]], reverse=True)
        sj = veg_export.seasons_json(c["path"])
        sl = {e_["slot"]: e_ for e_ in sj["slot_list"]}
        assert set(sl) == {"bark", "foliage", "heads"} and sl["heads"]["hidden_in"] == ["spring", "winter", "snow"]
        assert sl["heads"]["on"][0]["primitive"] == 1 and not sl["foliage"]["hidden_in"]
        cols = {se: sj["seasons"][se]["foliage"]["baseColorFactor"] for se in seasons}
        assert len({tuple(np.round(c_, 3)) for c_ in cols.values()}) == 5

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
