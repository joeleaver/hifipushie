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
    J = clutter.export({"kind": "bush", "style": "realistic", "variants": 1, "atlas": 384}, tmp_path, stem="b")
    v = J["clutter"]["variants"][0]
    assert v["lods"][0]["cards"] > v["lods"][2]["cards"] and v["lods"][0]["triangles"] < 320 and v["lods"][2]["triangles"] < 70
    G = _glb_json(tmp_path / v["lods"][0]["file"])
    assert {"TEXCOORD_1", "TEXCOORD_2", "_WIND"} <= set(G["meshes"][0]["primitives"][0]["attributes"])
    assert G["materials"][0]["alphaMode"] == "MASK"
    files = {J["seasons"][se]["foliage"]["baseColorTexture"]["file"] for se in ("spring", "summer", "autumn", "winter")}
    assert len(files) == 4 and all((tmp_path / f).exists() for f in files)
    from PIL import Image
    a = np.asarray(Image.open(tmp_path / J["slots"]["foliage"]["baseColorTexture"]["file"]))
    assert a.shape[2] == 4 and (a[..., 3] < 128).mean() > 0.05 and (a[..., 3] > 128).mean() > 0.1  # sprays cut out, dome opaque
    blob = clutter.resolve({"kind": "bush", "style": "blobby"})
    assert blob["form"]["cards"][1] == 0  # a closed style: no cards


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
