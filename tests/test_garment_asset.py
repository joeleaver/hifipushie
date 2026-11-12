"""garment_asset: the character's export takes a chain garment as export_garment wrote it (C433).

The old route re-simulated the garment's draft and shipped that. These tests hold the hand-over: the file reads back
as written, the two-sided layout is recognised, an unapproved or unexported garment is left out and said, weights
follow the rig by bone NAME, and the character export never hands a garment with a record to cloth.export_part."""
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
    # its own gate failed: shipped as it is, and the log says so (the record keeps no row names: the count)
    monkeypatch.setattr(gr, "states", _states(ten="failed"))
    bad = _rec(**{"10": {"status": "failed", "output": {"glb": str(glb)},
                         "gate": {"rows": [{"status": "PASS"}, {"status": "FAIL"}, {"id": "bends cleanly: arm", "status": "FAIL"}]}}})
    p, warn = ga.exported(bad)
    assert p == glb and len(warn) == 1 and "FAILED (bends cleanly: arm" in warn[0] and "shipped as exported" in warn[0]


def test_parts_are_the_files_own_mesh_maps_and_weights(tmp_path, monkeypatch):
    glb = _file(tmp_path)
    monkeypatch.setattr(gr, "states", _states())
    recs = {"shirt": _rec(**{"10": {"status": "done", "output": {"glb": str(glb)}}}),
            "coat": _rec(**{"10": {"status": "todo"}})}
    log = []
    cparts, weights, looks, left = ga.parts("m", recs, tmp_path / "out_missing_is_made" if False else tmp_path, log.append)
    assert [pn for pn, _, _ in cparts] == ["cloth_shirt", "cloth_shirt_details"]
    assert [g for g, _ in left] == ["coat"] and "export_garment" in left[0][1] and looks == {}
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
