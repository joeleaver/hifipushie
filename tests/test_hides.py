"""parts.<p>.hides (hides.py): a body part hidden under the parts that cover it (a foot in a shoe).

A synthetic leg + foot with a shoe shell whose region stops 5 mm above the floor, so the sole of the foot pokes
out under the shoe (as bare toes under a sprung toe do). Checks: the hidden faces are the enclosed ones plus the
poke-through, nothing at the collar opening is hidden, clay builds / export pruning / export culling agree, and
the result is deterministic. Run: uv run python tests/test_hides.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["HIFIPUSHIE_HOME"] = tempfile.mkdtemp(prefix="hp_hides_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np  # noqa: E402

from hifipushie import asset, hides, sdf, store  # noqa: E402
from hifipushie.spec import compile_prims  # noqa: E402

TOP = 0.09  # the shoe's collar height
FLOOR = 0.005  # the shoe region's bottom: the foot below it pokes out


def foot_spec(hide=True, **opts) -> dict:
    s = {"joints": {"knee": {"pos": [0, 0, 0.32], "r": 0.04}, "ankle": {"pos": [0, 0, 0.06], "r": 0.035}},
         "bones": {"shin": {"a": "knee", "b": "ankle", "r_a": 0.045, "r_b": 0.035}},
         "blobs": {"foot": {"at": [0, -0.06, 0.03], "size": [0.04, 0.1, 0.03], "blend": 0.03},
                   "bead": {"at": [0.075, -0.05, TOP + 0.012], "size": [0.006, 0.006, 0.006], "blend": 0.0},
                   "shoe_region": {"at": [0, -0.05, (TOP + FLOOR) / 2], "shape": "box",
                                   "size": [0.08, 0.15, (TOP - FLOOR) / 2], "part": "shoes"}},
         "parts": {"body": {}, "shoes": {"shell": "body", "offset": 0.006, "color": "#333333"}}}
    if hide:
        s["parts"]["shoes"]["hides"] = {"parts": ["body"], **opts} if opts else ["body"]
    return s


def _body(spec):
    prims = compile_prims(spec)
    st = {ps[0].part: ps for ps in sdf.streams(prims)}
    return st


def test_rules():
    r = hides.rules({"shoes": {"hides": ["body"]}, "soles": {"hides": {"parts": ["body"], "rim": 0.002}}})
    assert r["body"]["covers"] == ["shoes", "soles"] and r["body"]["rim"] == 0.002, r
    assert hides.hiders({"shoes": {"hides": "body"}}) == {"shoes": {"body"}}
    try:
        hides.rules({"shoes": {"hides": ["shoes"]}})
        raise AssertionError("self-hiding accepted")
    except ValueError:
        pass


def test_clay_build():
    store.save("foot_bare", foot_spec(False), checked=False)
    store.save("foot_hide", foot_spec(True), checked=False)
    m0 = store.build("foot_bare", 160)
    m1 = store.build("foot_hide", 160)
    z0, z1 = np.load(m0["mesh"]), np.load(m1["mesh"])
    assert "hidden_faces" not in m0 and m1["hidden_faces"]["body"] > 0, m1
    assert np.array_equal(z0["verts"], z1["verts"]), "hiding must not move or drop vertices"
    bi = list(z1["part_names"]).index("body")
    V = z1["verts"].astype(np.float64)
    fb0 = z0["faces"][z0["part"][z0["faces"][:, 0]] == bi]
    fb1 = z1["faces"][z1["part"][z1["faces"][:, 0]] == bi]
    shown = {tuple(f) for f in fb1}
    gone = np.array([f for f in fb0 if tuple(f) not in shown])
    assert len(fb1) + len(gone) == len(fb0)
    st = _body(foot_spec(True))
    c = sdf.field_at(st["shoes"], V)
    zc = V[gone].reshape(-1, 3, 3)[..., 2]
    # hidden: inside the shoe (by the margin) or the poke-through below its floor, never at or above the collar
    assert zc.max() < TOP - hides.RIM / 2, zc.max()
    assert np.all((c[gone] < -hides.MARGIN) | (V[gone][..., 2] < FLOOR + 0.01)), "a hidden face shows"
    # the poke-through under the shoe (outside the shoe's field, and the rounded floor edge above it) is hidden
    poke = np.flatnonzero((V[:, 2] < FLOOR - 0.002) & (z1["part"] == bi))
    assert len(poke) and (c[poke] > 0).all()
    hidden_v = np.zeros(len(V), bool)
    hidden_v[gone.ravel()] = True
    vis = np.zeros(len(V), bool)
    vis[fb1.ravel()] = True
    assert not (vis[poke] & ~hidden_v[poke]).any(), "poke-through left showing"
    # enclosed: every body face deep inside the shoe and away from the collar is gone
    deep = np.all((c[fb0] < -0.004) & (V[fb0][..., 2] < TOP - 0.02) & (V[fb0][..., 2] > FLOOR + 0.01), 1)
    assert deep.sum() > 100 and not any(tuple(f) in shown for f in fb0[deep]), "enclosed skin still drawn"
    # the opening: everything of the leg above the collar and the rim just under it stays
    rim = np.all(V[fb0][..., 2] > TOP - hides.RIM / 2, 1)
    assert rim.sum() > 100 and all(tuple(f) in shown for f in fb0[rim]), "a gap at the collar"
    # a separate patch near the shoe that no covered skin rings (a bead beside the collar) shows
    bead = np.all(np.linalg.norm(V[fb0] - [0.075, -0.05, TOP + 0.012], axis=2) < 0.01, 1)
    assert bead.sum() > 20 and all(tuple(f) in shown for f in fb0[bead]), "an unringed patch was hidden"
    # deterministic: the same mask from a cold build
    k1 = hides.keep_faces(V[z1["part"] == bi], np.searchsorted(np.flatnonzero(z1["part"] == bi), fb0),
                          [st["shoes"]], hides.rules(foot_spec()["parts"])["body"])
    k2 = hides.keep_faces(V[z1["part"] == bi], np.searchsorted(np.flatnonzero(z1["part"] == bi), fb0),
                          [st["shoes"]], hides.rules(foot_spec()["parts"])["body"])
    assert np.array_equal(k1, k2) and (~k1).sum() == len(gone)


def test_scene_objects():
    from hifipushie import scene
    store.save("foot_scene", foot_spec(True), checked=False)
    objs, _, _ = scene.objects("foot_scene", 160)
    o = {x["key"]: x for x in objs}["body"]
    assert o["src_mesh"] and ":" in o["hash"] and o["mesh"] != o["src_mesh"]
    a, b = np.load(o["src_mesh"]), np.load(o["mesh"])
    assert len(b["verts"]) < len(a["verts"]) and len(b["faces"]) < len(a["faces"])
    assert len(np.unique(b["faces"])) == len(b["verts"]), "loose vertices (Blender drops them: inputs misalign)"
    objs2, _, _ = scene.objects("foot_scene", 160)  # cached by content: the same file, both kept
    o2 = {x["key"]: x for x in objs2}["body"]
    assert o2["mesh"] == o["mesh"] and Path(o["src_mesh"]).exists()


def _export_high(spec, tmp):
    log = []
    ctx = asset.split(spec, 160, False, log)
    high = asset.mesh_parts(ctx, Path(tmp) / "high.npz")
    full = dict(np.load(high))
    asset.prune_hidden(ctx, high, log)
    return ctx, full, dict(np.load(high)), log


def test_export():
    tmp = tempfile.mkdtemp(prefix="hp_hides_x_")
    ctx0, _, z0, _ = _export_high(foot_spec(False), tmp)
    ctx1, full, z1, log = _export_high(foot_spec(True), tmp)
    names = [str(n) for n in z1["part_names"]]
    bi, si = names.index("body"), names.index("shoes")
    nb = lambda z: int((z["part"][z["faces"][:, 0]] == bi).sum())  # noqa: E731
    ns = lambda z: int((z["part"][z["faces"][:, 0]] == si).sum())  # noqa: E731
    assert nb(z1) < nb(z0), (nb(z1), nb(z0))  # the poke-through goes too (pruning alone keeps it)
    assert ns(z1) > ns(z0), "the shoe's inside under the hidden sole should come back"
    V = z1["verts"].astype(np.float64)
    fb = z1["faces"][z1["part"][z1["faces"][:, 0]] == bi]
    c = sdf.field_at(ctx1["streams"]["shoes"], V[fb.ravel()]).reshape(-1, 3)
    assert not np.all(c < -0.004, 1)[np.all(V[fb][..., 2] < TOP - 0.02, 1)].any(), "a body face inside the shoe"
    assert not np.all(V[fb][..., 2] < FLOOR - 0.001, 1).any(), "poke-through exported"
    # the finished export part (after decimation / a template wrap): culled again from its corner arrays
    fbf = full["faces"][full["part"][full["faces"][:, 0]] == bi]
    sel = np.flatnonzero(full["part"] == bi)
    loc = np.searchsorted(sel, fbf)
    p = {"verts": full["verts"][sel], "corner_vert": loc.ravel(), "uv": np.zeros((loc.size, 2)),
         "normal": np.zeros((loc.size, 3)), "tangent": np.zeros((loc.size, 4)), "sign": np.ones(loc.size)}
    log = []
    n = asset.hide_export_part(ctx1, "body", p, log)
    assert n > 0 and len(p["corner_vert"]) == 3 * (len(fbf) - n) and len(p["uv"]) == len(p["corner_vert"]), log
    T = p["verts"][p["corner_vert"].reshape(-1, 3)].astype(np.float64)
    c = sdf.field_at(ctx1["streams"]["shoes"], T.reshape(-1, 3)).reshape(-1, 3)
    assert not (np.all(c < -0.004, 1) & np.all(T[..., 2] < TOP - 0.02, 1)).any()
    assert asset.hide_export_part(ctx0, "body", dict(p), []) == 0


if __name__ == "__main__":
    for t in [test_rules, test_clay_build, test_scene_objects, test_export]:
        t()
        print("ok", t.__name__)
