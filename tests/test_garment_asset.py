"""garment_asset: the character's export takes a chain garment as export_garment wrote it (C434).

The old route re-simulated the garment's draft and shipped that. These tests hold the hand-over: the file reads back
as written, the two-sided layout is recognised, an unapproved or unexported garment is left out and said, weights
follow the rig by bone NAME, and the character export never hands a garment with a record to cloth.export_part.
C439: each LOD of the character takes the garment's own LOD file (never a decimation of its LOD0)."""
from pathlib import Path

import numpy as np
import pytest

from hifipushie import garment_asset as ga, garment_glb, garment_record as gr

BONES = [{"name": "root", "head": [0, 0, 0], "parent": -1}, {"name": "spine", "head": [0, 0, 1.0], "parent": 0},
         {"name": "arm", "head": [0.2, 0, 1.4], "parent": 1}]


def _garment():
    """A strip of cloth as garment_game.shell lays it out: outer triangles, the inner copy wound back, two rim ones."""
    V0 = np.array([[x * 0.1, 0.0, 1.0 + z * 0.1] for z in range(2) for x in range(3)], float)
    T0 = np.array([[0, 1, 3], [1, 4, 3], [1, 2, 4], [2, 5, 4]])
    n = len(V0)
    V = np.r_[V0, V0 + [0.0, 0.001, 0.0]]
    T = np.r_[T0, T0[:, [0, 2, 1]] + n, [[0, n, 1], [1, n, n + 1]]]
    uv = np.r_[V0[:, [0, 2]] - [0.0, 1.0], V0[:, [0, 2]] - [0.0, 1.0]] * [4.0, 8.0] + 0.05
    N = np.r_[np.tile([0.0, -1.0, 0.0], (n, 1)), np.tile([0.0, 1.0, 0.0], (n, 1))]
    J = np.zeros((2 * n, 4), int)
    J[:, 0], J[:, 1] = 1, 2
    W = np.zeros((2 * n, 4))
    W[:, 0], W[:, 1] = 0.75, 0.25
    return {"name": "shirt", "V": V, "T": T, "uv": uv, "N": N, "colour": [0.5, 0.6, 0.7], "J": J, "W": W}


def _button(i=0):
    V = np.array([[0.05, -0.002, 1.05], [0.06, -0.002, 1.05], [0.055, -0.002, 1.06], [0.055, -0.006, 1.055]]) + [0.1 * i, 0, 0]
    T = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])
    J = np.zeros((4, 4), int)
    J[:, 0] = 2
    W = np.zeros((4, 4))
    W[:, 0] = 1.0
    return {"name": f"shirt_buttons{i}", "V": V, "T": T, "colour": [0.9, 0.2 * i, 0.1], "J": J, "W": W, "roughness": 0.4,
            "metallic": float(i)}


def _file(tmp_path, meshes=None) -> Path:
    return garment_glb.write(tmp_path / "shirt.glb", "shirt", meshes or [_garment(), _button(0), _button(1)], BONES)


def test_a_garment_file_reads_back_as_written(tmp_path):
    g = ga.read(_file(tmp_path))
    assert g["bones"] == ["root", "spine", "arm"]
    m, want = g["meshes"][0], _garment()
    assert [x["name"] for x in g["meshes"]] == ["shirt", "shirt_buttons0", "shirt_buttons1"]
    for k in ("V", "uv", "N", "W"):  # (Blender axes and our v-up uv again, to float32)
        assert np.allclose(m[k], want[k], atol=1e-6), k
    assert np.array_equal(m["T"], want["T"]) and np.array_equal(m["J"], want["J"])
    assert g["meshes"][2]["metallic"] == 1.0 and abs(g["meshes"][1]["roughness"] - 0.4) < 1e-6
    assert np.allclose(g["meshes"][2]["colour"], [0.9, 0.2, 0.1], atol=1e-6) and m["maps"] is None


def test_the_two_sides_are_recognised_and_a_plain_mesh_is_not():
    m = _garment()
    sh = ga.shell_of(m["V"], m["T"])
    assert sh["outer"] == 4 and abs(sh["thickness"] - 0.001) < 1e-9
    b = _button()
    assert ga.shell_of(b["V"], b["T"]) is None
    assert ga.shell_of(m["V"][:6], m["T"][:4]) is None  # (the outer face alone)


def _rec(**steps):
    rec = gr.load("no_such_model_for_this_test", "shirt")
    for sid, st in steps.items():
        rec["steps"][sid].update(st)
    return rec


def _states(nine=True, ten="done", stale=False):
    def states(rec, approved=None):
        s = {sid: {"status": "approved", "ready": True, "stale": False, "why": ""} for sid in gr.IDS}
        s["9"] = {"status": "approved" if nine else "done", "ready": nine, "stale": False,
                  "why": "" if nine else "done; waits for approval (Joe or the coordinator)"}
        s["10"] = {"status": ten, "ready": ten == "done" and not stale, "stale": stale, "why": ""}
        return s
    return states


def test_only_an_approved_exported_garment_is_shipped(tmp_path, monkeypatch):
    glb = _file(tmp_path)
    rec = _rec(**{"10": {"status": "done", "output": {"glb": str(glb)}}})
    monkeypatch.setattr(gr, "next_step", lambda rec, approved=None: {"step": "9", "why": "", "uses": [], "call": "look_chain(...)"})
    monkeypatch.setattr(gr, "states", _states())
    assert ga.exported(rec) == (glb, [])
    monkeypatch.setattr(gr, "states", _states(nine=False))  # the look is not approved: never shipped
    with pytest.raises(ga.NotShipped, match=r"step 9.*next: step 9: look_chain"):
        ga.exported(rec)
    monkeypatch.setattr(gr, "states", _states(ten="todo"))
    with pytest.raises(ga.NotShipped, match=r'no export yet.*next: export_garment\("no_such_model_for_this_test", "shirt"\)'):
        ga.exported(rec)
    monkeypatch.setattr(gr, "states", _states(stale=True))
    with pytest.raises(ga.NotShipped, match="stale"):
        ga.exported(rec)
    monkeypatch.setattr(gr, "states", _states())
    gone = _rec(**{"10": {"status": "done", "output": {"glb": str(tmp_path / "gone.glb")}}})
    with pytest.raises(ga.NotShipped, match="gone"):
        ga.exported(gone)
    # its own gate failed: shipped as it is, and the log names the rows (the record keeps each row's "id")
    monkeypatch.setattr(gr, "states", _states(ten="failed"))
    bad = _rec(**{"10": {"status": "failed", "output": {"glb": str(glb)}, "gate": {"rows": [
        {"id": "triangles", "status": "PASS"}, {"id": "uv stretch", "status": "INFO"},
        {"id": "LOD3 open pattern edges", "status": "FAIL"}, {"id": "bends cleanly: arm", "status": "FAIL"}]}}})
    p, warn = ga.exported(bad)
    assert p == glb and warn == ["step 10's own gate FAILED (LOD3 open pattern edges; bends cleanly: arm): shipped as exported"]


def test_parts_are_the_files_own_mesh_maps_and_weights(tmp_path, monkeypatch):
    glb = _file(tmp_path)
    monkeypatch.setattr(gr, "states", _states())
    recs = {"shirt": _rec(**{"10": {"status": "done", "output": {"glb": str(glb)}}}),
            "coat": _rec(**{"10": {"status": "todo"}})}
    log = []
    cparts, weights, looks, left, lods = ga.parts("m", recs, tmp_path, log.append)
    assert [pn for pn, _, _ in cparts] == ["cloth_shirt", "cloth_shirt_details"]
    assert [g for g, _ in left] == ["coat"] and "export_garment" in left[0][1] and looks == {}
    # an export from before the LOD files: shipped, its LODs left to the decimator, and the log says how to change that
    assert lods == {} and sum("WARNING cloth shirt: its export has no LOD files" in line and "DECIMATED" in line
                              and 'next: export_garment("m", "shirt") again' in line for line in log) == 1
    (_, part, files), (_, dpart, dfiles) = cparts
    want = _garment()
    assert np.allclose(part["verts"], want["V"], atol=1e-6) and np.array_equal(part["corner_vert"], want["T"].ravel())
    assert part["shell"]["outer"] == 4 and np.allclose(part["uv"], want["uv"][want["T"].ravel()], atol=1e-6)
    assert np.allclose(part["normal"], want["N"][want["T"].ravel()], atol=1e-6)  # the garment's own normals
    for p in (part, dpart):
        for k in ("normal", "tangent"):
            assert np.allclose(np.linalg.norm(p[k], axis=1), 1.0, atol=1e-5), k
        assert np.abs((p["normal"] * p["tangent"]).sum(1)).max() < 1e-5 and set(np.unique(p["sign"])) <= {-1.0, 1.0}
        assert len(p["uv"]) == len(p["corner_vert"]) == len(p["normal"])
    assert all(Path(f).exists() for f in list(files.values()) + list(dfiles.values()))
    assert set(files) == set(dfiles) == {"basecolor", "normal", "orm", "specular"}
    # the details: one part, each detail's colour / roughness / metallic in its own palette cell
    from PIL import Image
    base, orm = np.array(Image.open(dfiles["basecolor"])), np.array(Image.open(dfiles["orm"]))
    assert base.shape == (ga.CELL, 2 * ga.CELL, 3) and "shell" not in dpart
    u = dpart["uv"][:, 0]
    assert np.allclose(u[:12], 0.25) and np.allclose(u[12:], 0.75)
    assert tuple(base[4, 4]) == (230, 0, 26) and tuple(base[4, 12]) == (230, 51, 26)
    assert tuple(orm[4, 4]) == (255, 102, 0) and tuple(orm[4, 12]) == (255, 102, 255)
    assert weights["cloth_shirt"][0] == ["root", "spine", "arm"] and len(weights["cloth_shirt_details"][1]) == 8
    assert any("not rebuilt" in line for line in log) and any("2 detail(s)" in line for line in log)


def _lod_garment(nx):
    """The strip again on a coarser grid (nx columns), two-sided as garment_game.shell lays it out."""
    V0 = np.array([[x * 0.2 / (nx - 1), 0.0, 1.0 + z * 0.1] for z in range(2) for x in range(nx)], float)
    q = np.arange(2 * nx).reshape(2, nx)
    T0 = np.concatenate([np.stack([q[0, :-1], q[0, 1:], q[1, :-1]], 1), np.stack([q[0, 1:], q[1, 1:], q[1, :-1]], 1)])
    n = len(V0)
    J = np.zeros((2 * n, 4), int)
    J[:, 0] = 2
    W = np.zeros((2 * n, 4))
    W[:, 0] = 1.0
    return {"name": "shirt", "V": np.r_[V0, V0 + [0.0, 0.001, 0.0]], "T": np.r_[T0, T0[:, [0, 2, 1]] + n],
            "uv": np.tile((V0[:, [0, 2]] - [0.0, 1.0]) * [4.0, 8.0] + 0.05, (2, 1)),
            "N": np.r_[np.tile([0.0, -1.0, 0.0], (n, 1)), np.tile([0.0, 1.0, 0.0], (n, 1))], "colour": [0.5, 0.6, 0.7],
            "J": J, "W": W}


def test_each_lod_takes_the_garments_own_lod_file(tmp_path, monkeypatch):
    """export_garment writes <garment>_LOD<k>.glb (the pattern re-grid, coarser); the character's LOD k is that file:
    its mesh, uv and weights, LOD0's palette cell for a detail it keeps, no details part where it keeps none."""
    glb = _file(tmp_path)
    f1 = garment_glb.write(tmp_path / "shirt_LOD1.glb", "shirt", [_lod_garment(2), _button(1)], BONES)
    f2 = garment_glb.write(tmp_path / "shirt_LOD2.glb", "shirt", [_lod_garment(2)], BONES)
    rec = _rec(**{"10": {"status": "done", "output": {"glb": str(glb), "lods": [
        {"lod": 1, "glb": str(f1), "share": 0.25}, {"lod": 2, "glb": str(f2), "share": 0.11},
        {"lod": 3, "glb": str(tmp_path / "shirt_LOD3.glb"), "share": 0.05}]}}})
    assert ga.lod_files(rec) == {1: (f1, 0.25), 2: (f2, 0.11)}  # (LOD3's file is gone: that LOD is left to the decimator)
    monkeypatch.setattr(gr, "states", _states())
    log = []
    cparts, weights, _, _, lods = ga.parts("m", {"shirt": rec}, tmp_path, log.append)
    assert sorted(lods) == [1, 2] and not any("WARNING" in line for line in log)
    assert any("its own LOD files (LOD1 shirt_LOD1.glb, LOD2 shirt_LOD2.glb)" in line for line in log)
    part, (names, J, W), share = lods[1]["cloth_shirt"]
    want = _lod_garment(2)
    assert share == 0.25 and np.allclose(part["verts"], want["V"], atol=1e-6) and part["shell"]["outer"] == 2
    assert np.array_equal(part["corner_vert"], want["T"].ravel()) and np.allclose(part["uv"], want["uv"][want["T"].ravel()], atol=1e-6)
    assert names == ["root", "spine", "arm"] and np.array_equal(J, want["J"])
    dpart, dw, _ = lods[1]["cloth_shirt_details"]  # the one button it keeps, on LOD0's palette cell (the second of two)
    assert len(dpart["corner_vert"]) == 12 and np.allclose(dpart["uv"][:, 0], 0.75) and len(dw[1]) == 4
    assert lods[2]["cloth_shirt_details"] == (None, None, 0.11)
    # into the character's LOD (asset_export's loop): LOD0's atlas index and pose correctives, the export rig's bones
    parts = {pn: dict(p, atlas=i + 3) for i, (pn, p, _) in enumerate(cparts)}
    n0 = len(parts["cloth_shirt"]["verts"])
    d = np.tile([0.0, 0.0, 0.01], (n0, 1))
    parts["cloth_shirt"]["shapes"] = {"corr_arm": (d, np.tile([0.0, -1.0, 0.0], (n0, 1)), np.tile([0.0, -1.0, 0.0], (n0, 1))),
                                      "smile": (d, d, d)}
    rig = [{"name": "arm"}, {"name": "spine"}, {"name": "root"}]
    lp, lr, rep = {"body": {}}, {"weights": {}}, {}
    line = ga.take_lods(lods[1], parts, lp, lr, rep, rig)
    assert set(lp) == {"body", "cloth_shirt", "cloth_shirt_details"} and lp["cloth_shirt"]["atlas"] == 3
    assert lp["cloth_shirt_details"]["atlas"] == 4 and np.all(lr["weights"]["cloth_shirt"][0][:, 0] == 0)  # "arm" by name
    assert list(lp["cloth_shirt"]["shapes"]) == ["corr_arm"]  # (pose correctives stay in every LOD; face shapes are not cloth's)
    assert np.allclose(lp["cloth_shirt"]["shapes"]["corr_arm"][0], [0.0, 0.0, 0.01]) and "shapes" not in lp["cloth_shirt_details"]
    assert rep["cloth_shirt"] == {"triangles0": 10, "triangles": 4, "own_lod": True} and "not decimated" in line
    lp, lr, rep = {}, {"weights": {}}, {}
    line = ga.take_lods(lods[2], parts, lp, lr, rep, rig)
    assert set(lp) == {"cloth_shirt"} and rep["cloth_shirt_details"]["triangles"] == 0 and "cloth_shirt_details left out" in line
    assert ga.take_lods(lods[2], parts, {}, None, {}, None)  # (an unrigged export: no weights to place)


def test_weights_follow_the_rig_by_bone_name():
    names = ["root", "spine", "arm"]
    J = np.array([[1, 2, 0, 0], [2, 0, 0, 0]])
    W = np.array([[0.75, 0.25, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]])
    rig = [{"name": "arm"}, {"name": "extra"}, {"name": "spine"}, {"name": "root"}]
    Jn, Wn = ga.bone_weights({"cloth_shirt": (names, J, W)}, rig)["cloth_shirt"]
    assert Jn[0, 0] == 2 and Jn[0, 1] == 0 and Jn[1, 0] == 0 and np.array_equal(Wn, W)
    # a bone only zero weights name may be missing; one that carries weight may not
    assert ga.bone_weights({"p": (names, J, W)}, [{"name": "arm"}, {"name": "spine"}])["p"][0][0, 0] == 1
    with pytest.raises(ValueError, match=r"spine.*export_garment again"):
        ga.bone_weights({"p": (names, J, W)}, [{"name": "arm"}, {"name": "root"}])


def test_the_character_export_never_hands_a_chain_garment_to_the_old_simulation():
    """asset_export splits spec["cloth"] by garment record: cloth.export_part (which simulates) gets only the others."""
    src = (Path(ga.__file__).parent / "asset_export.py").read_text()
    i, j = src.index("chain = garment_asset.records(name, spec)"), src.index("clothmod.export_part(")
    assert i < j and 'old_ = {g_: v_ for g_, v_ in spec["cloth"].items() if g_ not in chain}' in src[i:j]
    assert 'clothmod.export_part(name, {**spec, "cloth": old_}' in src and ") if old_ else []" in src[j:j + 200]
    assert "garment_asset.bone_weights(" in src and '"garments_left_out"' in src


def test_the_character_export_never_decimates_a_chain_garment_that_has_its_own_lod_files():
    """asset_export's LOD loop keeps the parts with an own LOD file away from lods_part and takes the files instead."""
    src = (Path(ga.__file__).parent / "asset_export.py").read_text()
    i = src.index("own_ = {pn: v for pn, v in chain_lods.get(k, {}).items() if pn in parts}")
    j = src.index("garment_asset.take_lods(own_, parts, lp, lr, rep_l")
    assert i < src.index("if pn not in pf_of and pn not in own_}", i) < j < src.index("write_glb(lg, aname, lp", j)
    assert "chain_lods = garment_asset.parts(name, chain, out_dir, log.append)" in src


def _sheet(nx, x0, x1, z, up=True):
    xs, ys = np.linspace(x0, x1, nx), np.linspace(0.0, 0.2, 5)
    V = np.array([[x, y, z] for y in ys for x in xs])
    q = np.arange(len(V)).reshape(len(ys), nx)
    a, b, c, d = q[:-1, :-1].ravel(), q[:-1, 1:].ravel(), q[1:, 1:].ravel(), q[1:, :-1].ravel()
    T = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    return ga.part_of(V, T if up else T[:, ::-1], V[:, :2] * 2.0, np.tile([0.0, 0.0, 1.0 if up else -1.0], (len(V), 1)))


def test_skin_through_a_garments_own_lod_cloth_is_cut_where_it_was_covered_at_lod0():
    """Skin (z = 0, facing up) under a LOD's cloth that has sunk to 3 cm UNDER it between x = 0.2 and 0.4 (a coarse
    face's chord), and lies over it elsewhere. Covered at LOD0 for x < 0.6 only: the skin sticking through there is
    cut; the same skin where it was never covered (a wrist past the cuff) stays; covered skin under the cloth stays."""
    skin = _sheet(41, 0.0, 0.8, 0.0)
    V = np.asarray(skin["verts"], float)
    low = np.asarray(_sheet(9, 0.2, 0.4, -0.03)["verts"], float)
    cloth = np.vstack([np.asarray(_sheet(9, 0.0, 0.2, 0.01)["verts"], float), low,
                       np.asarray(_sheet(9, 0.4, 0.6, 0.01)["verts"], float), np.asarray(_sheet(9, 0.6, 0.8, -0.03)["verts"], float)])
    T1 = np.asarray(_sheet(9, 0.0, 0.2, 0.0)["corner_vert"]).reshape(-1, 3)
    cover = ga.part_of(cloth, np.vstack([T1 + 45 * i for i in range(4)]), cloth[:, :2], np.tile([0.0, 0.0, 1.0], (len(cloth), 1)))
    keep = ga.skin_through(skin, [cover], V, V[:, 0] < 0.6)
    c = V[np.asarray(skin["corner_vert"]).reshape(-1, 3)].mean(1)[:, 0]
    assert not keep[(c > 0.23) & (c < 0.37)].any()      # through the cloth, covered at LOD0: cut
    assert keep[(c < 0.17) | ((c > 0.43) & (c < 0.57))].all()  # under the cloth: kept
    assert keep[c > 0.63].all()                          # through it too, but never covered at LOD0: kept
    assert ga.skin_through(skin, [], V, V[:, 0] < 0.6).all() and ga.skin_through(skin, [cover], V, np.zeros(len(V), bool)).all()


def test_covered_at_lod0_reads_a_loose_sleeve_as_cover_and_keeps_what_a_pose_uncovers():
    """Cloth 4 cm off the skin (a loose sleeve) over x < 0.4: covered, though lods_under's 2 cm mask says not; the
    points a clip frame uncovers (in the mask's [4], not in its [5]) are not counted."""
    from hifipushie import lods_under
    skin = _sheet(41, 0.0, 0.8, 0.0)
    cover = _sheet(21, 0.0, 0.4, 0.04)
    P2, near = lods_under.under_at_lod0(skin, [cover])
    assert not near.any()  # (2 cm: the sleeve is out of reach)
    P0, under0 = ga.covered_at_lod0(skin, [cover], (P2, near, 0.0, None, near))
    assert np.array_equal(P0, P2) and under0[P0[:, 0] < 0.38].all() and not under0[P0[:, 0] > 0.42].any()
    un = P0[:, 0] < 0.4
    _, kept = ga.covered_at_lod0(skin, [cover], (P0, un, 0.0, None, un, un & (P0[:, 0] > 0.2)))  # x <= 0.2 shows in a pose
    assert not kept[P0[:, 0] < 0.18].any() and kept[(P0[:, 0] > 0.22) & (P0[:, 0] < 0.38)].all()
