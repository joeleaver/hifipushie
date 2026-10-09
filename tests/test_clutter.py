"""Clutter kit (clutter.py): rocks, driftwood, bushes and litter as small game assets in a style.
Sound LODs within budget that keep the outline, proportions that differ between variants, the pivot on the ground line,
deterministic, style and preset keys checked, files and json as the contract says."""
import json
import struct

import numpy as np
import pytest

from hifipushie import clutter

SMALL = {"variants": 2, "atlas": 256}


@pytest.fixture(scope="module")
def boulder():
    return clutter.build({"kind": "boulder", "style": "realistic", **SMALL})


def test_presets_and_styles_resolve():
    assert {"boulder", "river_rock", "cobbles", "slab", "driftwood", "bush", "litter"} <= set(clutter.presets())
    assert clutter.styles()[0] == "realistic" and {"blobby", "anime", "cartoon", "pixar"} <= set(clutter.styles())
    for k in clutter.presets():
        for st in clutter.styles():
            c = clutter.resolve({"kind": k, "style": st})
            assert c["lods"] and len(c["color"]) == 3


def test_unknown_keys_refused():
    with pytest.raises(ValueError, match="unknown"):
        clutter.resolve({"kind": "boulder", "form": {"bevvel": 0.1}})
    with pytest.raises(ValueError, match="unknown"):
        clutter.resolve({"kind": "boulder", "paint": {"mosss": 0.1}})
    with pytest.raises(ValueError, match="unknown"):
        clutter.resolve({"kind": "pebble"})
    with pytest.raises(ValueError, match="unknown"):
        clutter.resolve({"kind": "boulder", "colour": [1, 0, 0]})


def test_lods_sound_within_budget_and_keep_the_outline(boulder):
    cfg = boulder["cfg"]
    for v in boulder["variants"]:
        for j, (L, tgt) in enumerate(zip(v["lods"], cfg["lods"])):
            chk = clutter.mesh_check(L["V"], L["F"])
            assert chk["open_edges"] == 0 and chk["nonmanifold_edges"] == 0 and chk["degenerate"] == 0, (v["name"], j, chk)
            assert L["triangles"] <= 1.12 * tgt, (v["name"], j, L["triangles"], tgt)
            assert L["iou"] >= (0.9 if j == 1 else 0.82 if j == 2 else 1.0), (v["name"], j, L["iou"])
            assert np.allclose(np.linalg.norm(L["N"], axis=1), 1, atol=1e-3)
            assert np.allclose(np.linalg.norm(L["T"][:, :3], axis=1), 1, atol=1e-3)
            assert (np.abs((L["N"] * L["T"][:, :3]).sum(1)) < 0.02).all()  # tangent square to the normal
            assert L["UV"].min() >= 0 and L["UV"].max() <= 1


def test_one_metre_across_pivot_on_the_ground_line(boulder):
    for v in boulder["variants"]:
        V = v["lods"][0]["V"]
        plan = max(np.ptp(V[:, 0]), np.ptp(V[:, 1]))
        assert abs(plan - 1.0) < 0.03
        assert abs(V[:, 2].min() + v["sink"]) < 0.02 and v["sink"] > 0.1  # the mass sits IN the ground
        assert abs(V[:, :2].min(0) + V[:, :2].max(0)).max() < 0.02  # centred in plan


def test_variants_differ_in_proportion():
    B = clutter.build({"kind": "boulder", "style": "realistic", "variants": 3, "atlas": 256, "lods": [200]})
    h = [v["height"] for v in B["variants"]]
    assert max(h) / min(h) > 1.25, h  # a lump, a flat block, a tall wedge


def test_a_boulder_is_not_a_box(boulder):
    # no pair of big faces is parallel: the area-weighted share of LOD 1 face normals with an opposite twin is small
    for v in boulder["variants"]:
        L = v["lods"][1]
        V, F = L["V"], L["F"]
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        a = np.linalg.norm(n, axis=1)
        n = n / a[:, None]
        m = clutter.outline_measures(v["lods"][0]["V"], v["lods"][0]["F"])
        assert 0.35 < m["height_over_width"] < 1.0, m
        assert m["top_over_base"] < 1.6  # (base at 20% / top at 80% of the height: wider low; reported the other way round)


def test_deterministic():
    a = clutter.build({"kind": "slab", "style": "anime", "variants": 1, "atlas": 128, "lods": [120]})
    b = clutter.build({"kind": "slab", "style": "anime", "variants": 1, "atlas": 128, "lods": [120]})
    assert np.array_equal(a["variants"][0]["lods"][0]["V"], b["variants"][0]["lods"][0]["V"])
    assert np.array_equal(a["albedo"]["summer"], b["albedo"]["summer"])


def test_styles_change_form_and_paint():
    r = clutter.build({"kind": "boulder", "style": "realistic", "variants": 1, "atlas": 128, "lods": [300]})
    b = clutter.build({"kind": "boulder", "style": "blobby", "variants": 1, "atlas": 128, "lods": [300]})

    def sharp(B):  # mean angle between neighbouring face normals
        L = B["variants"][0]["lods"][0]
        _, inv = np.unique(np.round(L["V"], 6), axis=0, return_inverse=True)
        G = inv.reshape(-1)[L["F"]]
        n = np.cross(L["V"][L["F"][:, 1]] - L["V"][L["F"][:, 0]], L["V"][L["F"][:, 2]] - L["V"][L["F"][:, 0]])
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        e = {}
        tot = []
        for fi, f in enumerate(G):
            for k in range(3):
                key = tuple(sorted((int(f[k]), int(f[(k + 1) % 3]))))
                if key in e:
                    tot.append(np.degrees(np.arccos(np.clip(n[fi] @ n[e[key]], -1, 1))))
                e[key] = fi
        return float(np.percentile(tot, 95))
    assert sharp(b) < sharp(r)  # a pebble has no arrises
    assert b["cfg"]["color"] != r["cfg"]["color"]


def _glb_json(path):
    d = open(path, "rb").read()
    assert d[:4] == b"glTF"
    n = struct.unpack("<I", d[12:16])[0]
    return json.loads(d[20:20 + n])


def test_export_files_and_json(tmp_path):
    J = clutter.export({"kind": "boulder", "style": "cartoon", **SMALL}, tmp_path, stem="t")
    assert J["grade"] == "clutter" and J["kind"] == "boulder" and J["style"]["name"] == "cartoon"
    assert J["contract"]["version"] >= 12 and J["slot_list"][0]["slot"] == "rock"
    c = J["clutter"]
    assert c["size_m"] == 1.0 and c["sink_m"] > 0 and c["lod_switch_m"]["lod1"] < c["lod_switch_m"]["lod2"] < c["lod_switch_m"]["cull"]
    for v in c["variants"]:
        for l in v["lods"]:
            G = _glb_json(tmp_path / l["file"])
            at = G["meshes"][0]["primitives"][0]["attributes"]
            assert {"POSITION", "NORMAL", "TANGENT", "TEXCOORD_0"} <= set(at)
            assert all((tmp_path / im["uri"]).exists() for im in G["images"])
        G = _glb_json(tmp_path / v["collision"])
        assert G["nodes"][0]["name"].endswith("-convcolonly") and v["collision_triangles"] <= 26
    for se in ("spring", "summer", "autumn", "winter", "snow"):
        assert (tmp_path / J["seasons"][se]["rock"]["baseColorTexture"]["file"]).exists()
    assert "boulder" in clutter.report(J)


def test_bush_has_wind_cards_and_seasons(tmp_path):
    J = clutter.export({"kind": "bush", "style": "realistic", "variants": 1, "atlas": 512}, tmp_path, stem="b")
    v = J["clutter"]["variants"][0]
    t = [l["triangles"] for l in v["lods"]]
    assert t[0] <= 290 and t[1] <= 110 and t[2] <= 24, t  # sprays + stems / a share of the same sprays + stems / two crossed cards
    assert v["lods"][0]["cards"] >= 20 and 12 <= v["lods"][1]["cards"] <= 0.5 * v["lods"][0]["cards"] and v["lods"][2]["cards"] == 2
    G = _glb_json(tmp_path / v["lods"][0]["file"])
    assert {"TEXCOORD_1", "TEXCOORD_2", "_WIND"} <= set(G["meshes"][0]["primitives"][0]["attributes"])
    assert G["materials"][0]["alphaMode"] == "MASK"
    files = {J["seasons"][se]["foliage"]["baseColorTexture"]["file"] for se in ("spring", "summer", "autumn", "winter")}
    assert len(files) == 4 and all((tmp_path / f).exists() for f in files)
    from PIL import Image
    a = np.asarray(Image.open(tmp_path / J["slots"]["foliage"]["baseColorTexture"]["file"]))
    assert a.shape[2] == 4 and 0.1 < (a[..., 3] > 128).mean() < 0.7  # pictures of sprays, boughs and the whole bush, cut out


def test_an_open_bush_is_open_and_its_tiers_come_from_it():
    from hifipushie import clutter_bush
    B = clutter_bush.build({"kind": "bush", "style": "realistic", "variants": 2, "atlas": 512})
    for v in B["variants"]:
        assert v["open"] > 0.3, v["open"]  # a shrub has sky and ground between its sprays: never a closed dome
        L0, L1, L2 = v["lods"]
        assert L1["iou"] > 0.6 and L2["iou"] > 0.45, (L1["iou"], L2["iou"])  # the far tiers cover what the sprays cover
        # LOD 1 is the same plant thinner: its sprays stand inside the bush LOD 0 draws, low ones too (no bare stems under a crown)
        z0, z1 = L0["V"][:, 2], L1["V"][:, 2]
        assert z1.max() <= z0.max() * 1.12 and np.percentile(z1, 10) <= np.percentile(z0, 10) + 0.12 * v["height"]
        # every card has its back on vertices of its own (two faces on the same three vertices are one to some importers)
        for L in (L0, L1, L2):
            f = np.sort(L["F"], axis=1)
            assert len(np.unique(f, axis=0)) == len(f)
        assert L0["V"][:, 2].min() >= -0.02 and 0.3 < v["height"] < 1.3
    # the same shrub every time
    B2 = clutter_bush.build({"kind": "bush", "style": "realistic", "variants": 1, "atlas": 512})
    assert np.array_equal(B["variants"][0]["lods"][0]["V"], B2["variants"][0]["lods"][0]["V"])


def test_closed_styles_are_lumps_standing_on_the_ground():
    """Blobby / cartoon bushes: a cluster of gumdrop lumps that come DOWN TO THE GROUND (lumps held up on stems read as
    mushroom clouds on wire legs): no stems, the body reaches the ground line all round its foot, several lobes."""
    cfg = clutter.resolve({"kind": "bush", "style": "blobby"})
    assert cfg["form"]["open"] is False and cfg["form"]["cards"][1] == 0
    rng = np.random.default_rng(3)
    S = clutter.Bush(rng, cfg["form"])
    assert S.gum and not S.stems and len(S.ell) >= 4
    # every lump's column is solid from its middle to the ground
    for c, r in S.ell:
        col = np.c_[np.full(8, c[0]), np.full(8, c[1]), np.linspace(0.0, c[2], 8)]
        assert (S.sd(col) < 0).all(), (c, S.sd(col))
    # lobes: the outline at a third of the height is not one round blob (its radius varies round the bush)
    a = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    d = np.c_[np.cos(a), np.sin(a), np.zeros(48)]
    R = np.linalg.norm(S.surface(d, np.array([0.0, 0.0, 0.3 * S.H]))[:, :2], axis=1)
    assert R.min() > 0.05 and R.max() / R.min() > 1.25, (R.min(), R.max())
    B = clutter.build({"kind": "bush", "style": "blobby", "variants": 1, "atlas": 384, "lods": [250, 100]})
    L = B["variants"][0]["lods"][0]
    assert "wind" in L and L["wind"].shape[1] == 4
    # the mesh's foot: vertices at the ground line all round (within 3 cm), none hanging in the air on a stalk
    low = L["V"][L["V"][:, 2] < 0.03]
    ang = np.degrees(np.arctan2(low[:, 1], low[:, 0])) % 360
    assert len(np.unique((ang // 45).astype(int))) >= 7, np.unique((ang // 45).astype(int))


def test_litter_card(tmp_path):
    J = clutter.export({"kind": "litter", "style": "anime", "variants": 2, "atlas": 256}, tmp_path, stem="l")
    assert J["seasons"]["snow"]["litter"]["hidden"] and not J["seasons"]["autumn"]["litter"]["hidden"]
    assert [l["triangles"] for l in J["clutter"]["variants"][0]["lods"]] == [8, 2]
    from PIL import Image
    s = np.asarray(Image.open(tmp_path / J["seasons"]["summer"]["litter"]["baseColorTexture"]["file"]))[..., 3]
    a = np.asarray(Image.open(tmp_path / J["seasons"]["autumn"]["litter"]["baseColorTexture"]["file"]))[..., 3]
    assert (a > 128).mean() > (s > 128).mean() > 0.03  # more leaves in autumn


def test_manifest(tmp_path):
    clutter.export({"kind": "litter", "style": "realistic", "variants": 1, "atlas": 128}, tmp_path / "real_litter", stem="l")
    M = clutter.manifest(tmp_path)
    assert M["kinds"]["litter"]["styles"]["realistic"]["folder"] == "real_litter"
    assert "blobby" in M["kinds"]["litter"]["missing"] and set(M["kinds"]) >= {"bush", "boulder", "reeds", "tussock"}
    assert (tmp_path / "clutter.json").exists()


@pytest.mark.parametrize("kind", ["cobbles", "driftwood"])
def test_patches_and_wood_hold_their_budgets(kind):
    # a patch of stones (a hull per stone) and driftwood (built tubes at LOD 1 / 2, a jam always): never over budget, sound
    B = clutter.build({"kind": kind, "style": "realistic", "atlas": 128})
    cfg = B["cfg"]
    vf = cfg.get("variant_forms") or [{}]
    for k, v in enumerate(B["variants"]):
        x = float(vf[k % len(vf)].get("lods_x", 1.0))
        for j, (L, tgt) in enumerate(zip(v["lods"], cfg["lods"])):
            chk = clutter.mesh_check(L["V"], L["F"])
            assert L["triangles"] <= 1.15 * tgt * x, (kind, v["name"], j, L["triangles"], tgt * x)
            assert chk["open_edges"] == 0 and chk["degenerate"] == 0, (kind, v["name"], j, chk)


@pytest.mark.parametrize("kind", ["litter", "river_rock", "bush", "driftwood"])
def test_no_state_is_null(tmp_path, kind):
    """A first loader crashed on "snow": null (a plant always has an object there). A state or block that does not
    apply is {} or says so; a list is []; only an absent text / file / single number may be null (contract log 13)."""
    J = clutter.export({"kind": kind, "style": "realistic", "variants": 1, "atlas": 256}, tmp_path, stem="k")
    assert isinstance(J["snow"], dict) and "coverage" in J["snow"]
    assert isinstance(J["clutter"]["wet"], dict)
    assert isinstance(J["clutter"]["instance_tints"], list)
    assert isinstance(J["seasons"], dict) and all(isinstance(v, dict) for v in J["seasons"].values())
    assert isinstance(J["slots"], dict) and isinstance(J["slot_list"], list) and isinstance(J["variants"], list)
    if kind == "litter":
        assert J["snow"]["hidden"] is True and J["snow"]["coverage"] == 0.0
    if kind == "river_rock":
        assert J["clutter"]["wet"]["row"] == "water" and J["clutter"]["wet"]["band"] > 0 and "water" in J["clutter"]["wet"]["recipe"]
    assert "ABSENT VALUES" in J["contract"]["changes"][13] or "ABSENT VALUES" in J["contract"]["changes"]["13"]


def test_river_rocks_are_not_all_round_mossy_stones():
    """River rocks read as clean round mossy garden stones: two of the four are angular / broken now, moss lies only on
    faces turned up above the middle, and not on every stone."""
    cfg = clutter.resolve({"kind": "river_rock", "style": "realistic"})
    vf = cfg["variant_forms"]
    assert sum(1 for v in vf if v.get("round", 1.0) <= 0.3) >= 2
    assert cfg["paint"]["moss_up"] >= 0.3 and 0.0 in cfg["paint"]["moss_vary"]
    B = clutter.build({"kind": "river_rock", "style": "realistic", "variants": 4, "atlas": 512})
    # sharper stones have flatter faces: more of their surface within 12 deg of a few directions
    def planar(L):
        V, F = L["V"], L["F"]
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        a = np.linalg.norm(n, axis=1)
        n = n / np.maximum(a[:, None], 1e-12)
        best = 0.0
        for i in np.argsort(-a)[:12]:
            best = max(best, float(a[(n @ n[i]) > np.cos(np.radians(12))].sum() / a.sum()))
        return best
    p = [planar(v["lods"][0]) for v in B["variants"]]
    assert max(p[2], p[3]) > max(p[0], p[1]), p


def test_contract_has_the_clutter_grade():
    from hifipushie import veg_export
    assert veg_export.CONTRACT >= 13 and "clutter" in veg_export.CONTRACT_LOG[13]


@pytest.mark.parametrize("style", ["realistic", "blobby", "anime", "cartoon", "pixar"])
def test_rock_pictures_hold_a_cliffs_tone_range(style):
    """A boulder is tinted per instance to its cliff's rock colour: that only lands it there if its pictures' mean IS the
    stated colour and their tones lie in a cliff's range (cartoon was 0.15 .. 2.9 of a mean 40% under: charcoal)."""
    from hifipushie.terrain_style import _srgb_lin
    B = clutter.build({"kind": "boulder", "style": style, "variants": 2, "atlas": 384})
    cfg = B["cfg"]
    lo, hi = cfg["paint"]["tone_range"]
    w = np.array([0.2126, 0.7152, 0.0722])
    a = _srgb_lin(B["albedo"]["summer"][..., :3])
    L = (a @ w).ravel()
    L = L[L > 1e-4]
    want = float(_srgb_lin(np.asarray(cfg["color"], float)) @ w)
    assert abs(L.mean() / want - 1) < 0.08, (L.mean(), want)
    p5, p95 = np.percentile(L / L.mean(), [5, 95])
    assert p95 / p5 <= hi / lo * 1.12, (p5, p95, lo, hi)
    # and without it the same stones are far wider (what the step is for)
    B0 = clutter.build({"kind": "boulder", "style": style, "variants": 2, "atlas": 384, "paint": {"tone_range": None}})
    L0 = (_srgb_lin(B0["albedo"]["summer"][..., :3]) @ w).ravel()
    L0 = L0[L0 > 1e-4]
    q5, q95 = np.percentile(L0 / L0.mean(), [5, 95])
    assert q95 / q5 > p95 / p5
