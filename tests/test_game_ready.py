"""Game-ready assembly (docs/notes/game_ready.md): frozen garments (cloth.freeze / thaw / carry)."""
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hifipushie import cloth  # noqa: E402


def _grid_body(z0=0.0, bulge=0.0):
    """A closed box-ish body (a subdivided cube) as cloth.Body takes it; bulge pushes the +x half out."""
    n = 6
    V, F = [], []
    idx = {}

    def vid(p):
        k = tuple(np.round(p, 6))
        if k not in idx:
            idx[k] = len(V)
            V.append(list(k))
        return idx[k]
    s = np.linspace(-0.1, 0.1, n + 1)
    for ax in range(3):
        for sign in (-1, 1):
            for i in range(n):
                for j in range(n):
                    q = []
                    for a, b in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                        p = np.zeros(3)
                        p[ax] = 0.1 * sign
                        p[(ax + 1) % 3], p[(ax + 2) % 3] = s[a], s[b]
                        q.append(vid(p))
                    F.append(q if sign > 0 else q[::-1])
    V = np.asarray(V, float)
    V[:, 2] += z0
    V[:, 0] += bulge * (V[:, 0] > 0)
    return {"V": V, "F": F, "J": {}}


def test_carry_moves_with_the_body_and_reports():
    b0, b1 = cloth.Body(_grid_body()), cloth.Body(_grid_body(z0=0.01))
    G = b0.V[b0.V[:, 2] > 0.05] * 1.05  # cloth just off the top half
    res = {"V": G.copy(), "V_sim": G.copy(), "uv": np.zeros((len(G), 2)), "body": b0}
    out = cloth.carry(res, b1)
    assert np.allclose(out["V"] - G, [0, 0, 0.01], atol=1e-6), "a rigid body move carries the cloth rigidly"
    assert np.allclose(out["V_sim"], out["V"]) and np.allclose(out["uv"], 0)
    assert out["body"] is b1 and abs(out["carried"]["max_mm"] - 10.0) < 0.01
    same = cloth.carry(res, b0)
    assert same["carried"]["max_mm"] == 0.0 and np.array_equal(same["V"], G)


def test_carry_pushes_out_what_ends_inside():
    b0, b1 = cloth.Body(_grid_body()), cloth.Body(_grid_body(bulge=0.02))
    # cloth hugging the +x face 1 mm out: the face moves 20 mm out, the cloth with it; nothing ends inside
    G = b0.V[b0.V[:, 0] > 0.099] + [0.001, 0, 0]
    out = cloth.carry({"V": G, "body": b0}, b1)
    assert (out["V"][:, 0] > 0.1195).all()
    try:
        cloth.carry({"V": G, "body": b0}, cloth.Body({"V": b0.V[:-1], "F": [[0, 1, 2]], "J": {}}))
        raise AssertionError("another topology must be refused")
    except cloth.ClothError:
        pass


def test_freeze_thaw_round_trip_keeps_the_garment_and_takes_look_overrides():
    b0 = cloth.Body(_grid_body())
    G = b0.V[:10] * 1.05
    res = {"V": G, "mesh": {"F": np.array([[0, 1, 2]])}, "body": b0, "key": "abc", "collider": b0,
           "under": {"name": "jeans", "key": "k", "V": G}, "pieces": {"x": 1, "_b": b0}}
    g = {"pattern": {"from": "simon"}, "color": "#112233", "over": "jeans"}
    with tempfile.TemporaryDirectory() as d:
        info = cloth.freeze(res, g, Path(d) / "s.pkl", model="m", garment="sweater")
        assert info["vertices"] == 10
        gx, r2 = cloth.thaw({}, {"frozen": info["path"], "color": "#ffffff"})
        assert gx["color"] == "#ffffff" and gx["over"] == "jeans" and "design" not in gx
        assert np.array_equal(r2["V"], G) and "collider" not in r2 and "under" not in r2
        assert r2["pieces"] == {"x": 1} and r2["frozen"]["from_model"] == "m"
        cloth.validate({"cloth": {"s": {"frozen": info["path"], "color": "#ffffff"}}})
        for bad in ({"frozen": info["path"], "pattern": {}}, {"frozen": str(Path(d) / "nope.pkl")}):
            try:
                cloth.validate({"cloth": {"s": bad}})
                raise AssertionError(f"{bad} must be refused")
            except cloth.ClothError:
                pass


def _sheet_part(n=24):
    """A curved n x n sheet as an export part with TWO uv islands (left / right halves: a seam down the middle),
    per-vertex weights (2 bones by x) and one face shape (a bump)."""
    xs = np.linspace(0, 1, n + 1)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    V = np.stack([X.ravel(), Y.ravel(), 0.1 * np.sin(3 * X.ravel()) * np.cos(2 * Y.ravel())], 1)
    vid = lambda i, j: i * (n + 1) + j  # noqa: E731
    F = []
    for i in range(n):
        for j in range(n):
            F += [[vid(i, j), vid(i + 1, j), vid(i + 1, j + 1)], [vid(i, j), vid(i + 1, j + 1), vid(i, j + 1)]]
    F = np.array(F)
    cv = F.ravel()
    left = V[F].mean(1)[:, 0] < 0.5
    uv = V[cv, :2].copy()
    uv[np.repeat(~left, 3), 0] += 0.25  # the right island shifted in the atlas: a uv seam at x 0.5
    nrm = np.tile([0.0, 0.0, 1.0], (len(cv), 1))
    tan = np.tile([1.0, 0.0, 0.0], (len(cv), 1))
    p = {"verts": V.astype(np.float32), "corner_vert": cv, "uv": uv.astype(np.float32), "normal": nrm.astype(np.float32),
         "tangent": tan.astype(np.float32), "sign": np.ones(len(cv), np.float32), "atlas": 0}
    d = np.zeros_like(V)
    d[:, 2] = 0.01 * np.exp(-((V[:, 0] - 0.3) ** 2 + (V[:, 1] - 0.5) ** 2) / 0.02)
    p["shapes"] = {"bump": (d, np.tile([0, 0, 1.0], (len(V), 1)), np.tile([0, 0, 1.0], (len(V), 1)))}
    J = np.zeros((len(V), 4), np.int64)
    J[:, 1] = 1
    W = np.zeros((len(V), 4))
    W[:, 0], W[:, 1] = 1 - V[:, 0], V[:, 0]
    return p, (J, W)


def test_per_character_face_fits_from_the_environment_are_reported():
    """(Garrett assembly 2026-10-18) HP_SMILE_FIT / HP_JAW_FIT / HP_SHAPE_SCULPT are ONE person's fitted / sculpted face
    inputs but apply to whatever head is exported: env_fits() names them, so the export can log each as a WARNING."""
    from hifipushie import faceshapes as fs
    old = (fs.SMILE_FIT, fs.JAW_FIT, fs.SHAPE_SCULPT)
    try:
        fs.SMILE_FIT, fs.JAW_FIT, fs.SHAPE_SCULPT = "", "", ""
        assert fs.env_fits() == {}
        fs.SMILE_FIT, fs.JAW_FIT = "/x/smile_w4_shape.npy", "/x/jaw_w1_shape.npy"
        assert fs.env_fits() == {"HP_SMILE_FIT": "/x/smile_w4_shape.npy", "HP_JAW_FIT": "/x/jaw_w1_shape.npy"}
    finally:
        fs.SMILE_FIT, fs.JAW_FIT, fs.SHAPE_SCULPT = old
    src = open(fs.__file__.replace("faceshapes.py", "asset.py")).read()
    assert "faceshapes.character_fits(" in src


def test_per_character_face_fits_come_from_the_spec():
    """(Garrett assembly 2026-10-18) base.head.face_fits replaces the environment's fits inside character_fits (keys it
    leaves out are cleared), relative paths resolve from the model folder, the globals come back after; with no
    face_fits the environment's stay and are logged as WARNINGs."""
    import tempfile, os
    import pytest
    from hifipushie import faceshapes as fs
    old = (fs.SMILE_FIT, fs.JAW_FIT, fs.SHAPE_SCULPT)
    d = tempfile.mkdtemp()
    np.save(os.path.join(d, "smile.npy"), np.zeros(3))
    try:
        fs.SMILE_FIT, fs.JAW_FIT, fs.SHAPE_SCULPT = "/tess/smile.npy", "/tess/jaw.npy", ""
        log = []
        with fs.character_fits({"base": {"head": {"face_fits": {"smile": "smile.npy"}}}}, log, d):
            assert fs.SMILE_FIT == os.path.join(d, "smile.npy") and fs.JAW_FIT == "" and fs.SHAPE_SCULPT == ""
        assert (fs.SMILE_FIT, fs.JAW_FIT) == ("/tess/smile.npy", "/tess/jaw.npy")
        assert any("from the spec" in m for m in log) and not any("WARNING" in m for m in log)
        log = []
        with fs.character_fits({"base": {"head": {}}}, log, d):
            assert fs.JAW_FIT == "/tess/jaw.npy"
        assert sum("WARNING" in m for m in log) == 2
        with pytest.raises(FileNotFoundError):
            with fs.character_fits({"base": {"head": {"face_fits": {"jaw": "nope.npy"}}}}, [], d):
                pass
        with pytest.raises(ValueError):
            with fs.character_fits({"base": {"head": {"face_fits": {"grin": "smile.npy"}}}}, [], d):
                pass
        assert fs.JAW_FIT == "/tess/jaw.npy"
    finally:
        fs.SMILE_FIT, fs.JAW_FIT, fs.SHAPE_SCULPT = old


def test_lod_keeps_seams_weights_and_shapes():
    from hifipushie import lods
    p, w = _sheet_part()
    q, wq, rep = lods.lod_part(p, w, 0.3)
    assert rep["triangles"] < 0.6 * rep["triangles0"], rep
    assert rep["patches"] == 2
    V = np.asarray(q["verts"], float)
    # the seam's vertices are held: every LOD0 vertex on x = 0.5 is still a vertex, on both sides
    seam0 = np.asarray(p["verts"], float)[np.isclose(p["verts"][:, 0], 0.5)]
    on = np.isclose(V[:, 0], 0.5, atol=1e-6)
    assert len(np.unique(np.round(V[on], 6), axis=0)) == len(seam0)
    # uv: each vertex keeps its own island's uv (the right one shifted 0.25)
    cv = q["corner_vert"]
    x = V[cv, 0]
    du = q["uv"][:, 0] - x
    assert np.all(np.isclose(du, 0, atol=2e-3) | np.isclose(du, 0.25, atol=2e-3))
    # weights follow x; the shape's bump survives
    Jn, Wn = wq
    w1 = np.where(Jn == 1, Wn, 0).sum(1)
    assert np.abs(w1 - V[:, 0]).max() < 0.02
    d = q["shapes"]["bump"][0]
    assert abs(d[:, 2].max() - 0.01) < 0.002


def _sphere(r, n=40):
    th, ph = np.meshgrid(np.linspace(0.05, np.pi - 0.05, n), np.linspace(0, 2 * np.pi, 2 * n, endpoint=False), indexing="ij")
    V = r * np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1).reshape(-1, 3)
    F = []
    m = 2 * n
    for i in range(n - 1):
        for j in range(m):
            a, b, c, d = i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j
            F += [[a, b, c], [a, c, d]]
    F = np.array(F)
    cv = F.ravel()
    nrm = V[cv] / r
    return {"verts": V, "corner_vert": cv, "normal": nrm}


def test_skin_under_cloth_is_dropped_with_a_rim():
    from hifipushie import asset
    skin = _sphere(0.1)
    cloth = _sphere(0.11)
    T = cloth["corner_vert"].reshape(-1, 3)
    cloth["corner_vert"] = T[(cloth["verts"][T][:, :, 2] < 0).all(1)].ravel()  # a garment over the lower half
    keep = asset.under_cloth_keep(skin, [cloth])
    cz = skin["verts"][skin["corner_vert"].reshape(-1, 3)].mean(1)[:, 2]
    assert keep[cz > 0].all(), "uncovered skin stays"
    assert not keep[(cz < -0.06) & (cz > -0.08)].any(), "deeply covered skin goes"  # (the grid's pole is a hole)
    assert keep[(cz < 0) & (cz > -0.02)].all(), "the rim at the opening stays"


def test_cards_take_the_strands_desaturation():
    from hifipushie import hair
    lk = hair.full_look({"eevee_sat": 0.3})
    assert abs(lk["card_sat"] - 0.3 ** hair.CARD_SAT_EXP) < 1e-3
    assert hair.full_look({"eevee_sat": 0.3, "card_sat": 0.9})["card_sat"] == 0.9  # (given wins)
    assert hair.full_look({})["card_sat"] == hair.LOOK["card_sat"]


def test_card_lod_thins_one_layer_by_whole_cards():
    from hifipushie import lods
    # 10 cards of 2 triangles (4 verts each) after a 2-triangle cap: one layer, as tied hair has
    V, F = [], []
    for c in range(11):
        o = len(V)
        V += [[c, 0, 0], [c + 0.5, 0, 0], [c, 1 + c, 0], [c + 0.5, 1 + c, 0]]
        F += [[o, o + 1, o + 2], [o + 1, o + 3, o + 2]]
    cv = np.array(F).ravel()
    n = len(cv)
    p = {"verts": np.array(V, float), "corner_vert": cv, "uv": np.zeros((n, 2)), "normal": np.zeros((n, 3)),
         "tangent": np.zeros((n, 3)), "sign": np.ones(n)}
    q, rep = lods.card_lod(p, {"cap": [0, 2], "layer0": [2, 20]}, 0.5)
    assert rep["triangles"] <= 12 and rep["triangles"] >= 6
    kept = q["corner_vert"].reshape(-1, 3)
    assert {0, 1, 2}.issubset(set(kept[:1].ravel()))  # the cap stays
    assert len(kept) % 2 == 0  # whole cards


def test_shading_notes_cover_every_material():
    from hifipushie import shading
    with tempfile.TemporaryDirectory() as d:
        info = {"glb": f"{d}/x.glb", "triangles": 10, "skin": {"part": "body", "subsurface": {"mean_free_path_m": [2e-3, 7e-4, 4e-4]}},
                "atlases": {"0": {"parts": ["body", "eyes"], "maps": {"basecolor": f"{d}/b.png", "blink": f"{d}/k.png"}},
                            "hair": {"parts": ["hair"], "maps": {"basecolor": f"{d}/h.png", "aux": f"{d}/a.png"}}},
                "parts": {"body": {"mm_per_texel": 0.8}, "eyes": {}, "hair": {"curves": True}},
                "lods": [{"lod": 1, "glb": f"{d}/x_LOD1.glb", "triangles": 5}],
                "face_shapes": {"names": ["eyeBlinkLeft"], "correctives": {}}}
        j, m = shading.write(info, Path(d), "x", eyes_part="eyes")
        n = __import__("json").load(open(j))
        kinds = {mm["model"]: mm for mm in n["materials"]}
        assert set(kinds) == {"skin", "eye", "hair_cards"}
        assert "blink" in kinds["skin"]["maps"] and "blink" not in kinds["eye"]["maps"]
        assert any("lerp(1, blink, 1 - eyeBlink)" in f for f in kinds["skin"]["formulas"])
        assert 0 < n["lods"][1]["screen_size"] < 1 and "unreal" in kinds["hair_cards"]["engines"]
        assert "## LODs" in open(m).read()
        # a hair card's albedo terms are applied ONCE: clump depth and the value per strand are in the atlas, the
        # root ramp / tip / lock tone in COLOR_0; the shader adds no aux shade (it darkened the cards twice)
        hc = kinds["hair_cards"]
        assert hc["params"]["aux_shade"] is None
        assert hc["params"]["albedo_terms"] == shading.HAIR_ALBEDO_TERMS
        assert set(shading.HAIR_ALBEDO_TERMS.values()) == {"atlas", "COLOR_0"}
        assert not any("aux.r)" in f or "lerp(0.65, 1, aux.b)" in f for f in hc["formulas"])


def test_hair_atlas_bakes_what_the_notes_say():
    """shading.HAIR_ALBEDO_TERMS against the atlas itself: deep strands are darker and the strands' values differ IN
    the colour, so a shader must not apply them again."""
    import numpy as np
    from hifipushie import hair_cards as hc
    S = {**hc.strands_of({}), "atlas": 128, "source": "drawn"}
    at = hc.atlas(S, {"gap": "#201810", "lit": "#806040", "vary": 0.25})
    col, aux = at["color"], at["aux"]
    on = aux[..., 3] > 0.9
    lum = col[..., :3].mean(-1)
    deep, high = on & (aux[..., 2] < 0.4), on & (aux[..., 2] > 0.8)
    assert deep.any() and high.any() and lum[deep].mean() < 0.97 * lum[high].mean()  # (sRGB)
    lo, hi = on & (aux[..., 2] > 0.8) & (aux[..., 1] < 0.3), on & (aux[..., 2] > 0.8) & (aux[..., 1] > 0.7)
    assert lum[lo].mean() < lum[hi].mean()  # the value per strand (id)


def test_budget_gate_maps_parts_and_flags_over():
    from hifipushie import asset, budgets
    rb = budgets.role("hero")
    report = {"body": {"triangles": 41000, "meshes": {"head": {"triangles": 23000}, "body": {"triangles": 18000}}},
              "hair": {"triangles": 40000, "curves": True}, "lashes": {"triangles": 4900, "lashes": True},
              "eyes": {"triangles": 350}, "cloth_jeans": {"triangles": 9000, "cloth": True}, "shoes": {"triangles": 745}}
    g = asset.budget_check(rb, report, {})
    assert g["parts"]["head"][0] == 23000 and g["parts"]["body"][0] == 18000
    assert g["parts"]["eyes_mouth_lashes"][0] == 5250 and g["parts"]["accessories"][0] == 745
    over = [ln for ln in g["lines"] if "OVER" in ln]
    assert any("hair_cards" in ln for ln in over) and any("body" in ln for ln in over)
    assert not any(ln.startswith("WARNING budget: head") for ln in g["lines"])


def test_bend_helper_takes_the_hinge_overlap_and_is_driven_by_half():
    from hifipushie import rig
    P = rig.PREFIX
    rb = [{"name": P + "Hips", "head": np.zeros(3), "parent": -1, "end": False},
          {"name": P + "LeftUpLeg", "head": np.array([0.1, 0, 0]), "parent": 0, "end": False},
          {"name": P + "LeftLeg", "head": np.array([0.1, 0, -0.4]), "parent": 1, "end": False},
          {"name": P + "LeftFoot", "head": np.array([0.1, 0, -0.8]), "parent": 2, "end": False}]
    rb = rig._add_bend(rb, ["Leg"])
    assert rb[-1]["name"] == P + "LeftLegBend" and rb[-1]["parent"] == 1
    J = np.array([[1, 2, 0, 0], [1, 0, 0, 0], [2, 0, 0, 0]])
    W = np.array([[0.6, 0.4, 0, 0], [1.0, 0, 0, 0], [1.0, 0, 0, 0]])
    J2, W2 = rig._share_bend(rb, J, W)
    assert np.allclose(W2.sum(1), 1.0)
    h = len(rb) - 1
    wh = np.where(J2 == h, W2, 0).sum(1)
    assert abs(wh[0] - 0.8) < 1e-9 and wh[1] == 0 and wh[2] == 0  # 2 x min(0.6, 0.4)
    t = rig.drive_twist(rb, {P + "LeftLeg": ([1, 0, 0], 90.0)})
    assert t[P + "LeftLegBend"] == ([1, 0, 0], 45.0)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and (len(sys.argv) < 2 or any(a in name for a in sys.argv[1:])):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)


def test_bake_falls_back_to_osl_when_a_material_overflows_the_svm_stack():
    """(Garrett export 2026-10-18) the stacked skin (61 layers, 20 with height) overflowed Cycles' SVM stack and the
    export stopped rather than bake black. bake_needs_osl compiles every pass first (bake_maps check_only); an overflow
    makes the bake run with OSL (no stack limit), anything else still raises. Checked on the real scene: OSL renders the
    body's colour pass (SVM: black), and on a material that fits (shoes) OSL and SVM give identical pixels."""
    from hifipushie import asset, scene
    calls = []

    def fake(job, timeout, progress=None, deep=False):
        calls.append(dict(job))
        if deep:
            raise RuntimeError("Cycles ran out of shader stack on material(s) ['part:body']: it would render ...")
        return ""
    old = scene._blender
    try:
        scene._blender = lambda j, t, progress=None: fake(j, t)
        log = []
        assert asset.bake_needs_osl({"mode": "bake_maps"}, log) is False and log == []
        assert calls[-1]["check_only"] is True
        scene._blender = lambda j, t, progress=None: fake(j, t, deep=True)
        assert asset.bake_needs_osl({"mode": "bake_maps"}, log) is True
        assert "['part:body']" in log[-1] and "OSL" in log[-1]

        def boom(j, t, progress=None):
            raise RuntimeError("blender failed: something else")
        scene._blender = boom
        import pytest
        with pytest.raises(RuntimeError):
            asset.bake_needs_osl({"mode": "bake_maps"}, [])
    finally:
        scene._blender = old
    src = open(asset.__file__.replace("asset.py", "blender_scene.py")).read()
    assert 'job.get("osl")' in src and "shading_system = True" in src and 'job.get("check_only")' in src


def test_two_sided_cloth_decimation_keeps_the_inner_shell_inside():
    """Garrett's jacket (session 4): the cloth decimation (17572 -> 4780) decimated the outer and inner shells apart;
    13.8% of the inner vertices ended OUTSIDE the outer (up to 9.6 mm): black blotches all over the jacket in the game
    check. lods._lod_shell decimates the outer and rebuilds the inner from it."""
    import numpy as np
    from hifipushie import lods
    n = 60
    u, v = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
    rng = np.random.default_rng(0)
    z = 0.05 * np.sin(6 * u) * np.cos(5 * v) + 0.002 * rng.standard_normal(u.shape)  # a wrinkled sheet
    V = np.c_[u.ravel(), v.ravel(), z.ravel()]
    i = np.arange(n - 1)
    a = (i[:, None] * n + i[None, :]).ravel()
    F = np.r_[np.c_[a, a + 1, a + n], np.c_[a + 1, a + n + 1, a + n]]
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True)
    th = 0.0008
    Vall = np.r_[V, V - vn * th]
    Fall = np.r_[F, F[:, [0, 2, 1]] + len(V)]
    uv = np.r_[V[:, :2], V[:, :2]]
    cv = Fall.ravel()
    nrm = np.r_[vn, -vn][cv]
    p = {"verts": Vall.astype(np.float32), "corner_vert": cv, "uv": uv[cv].astype(np.float32),
         "normal": nrm.astype(np.float32), "tangent": np.tile([1.0, 0, 0], (len(cv), 1)).astype(np.float32),
         "sign": np.r_[np.ones(3 * len(F)), -np.ones(3 * len(F))].astype(np.float32),
         "shell": {"outer": len(F), "thickness": th}}
    q, _, r = lods.lod_part(p, None, 0.25)
    no = q["shell"]["outer"]
    T = np.asarray(q["corner_vert"]).reshape(-1, 3)
    assert len(T) == 2 * no and abs(len(T) / len(Fall) - 0.25) < 0.05, (len(T), no)
    Vq = np.asarray(q["verts"], float)
    # every inner triangle mirrors an outer one: reversed winding, offset th in along the outer normal
    nq = np.asarray(q["normal"], float).reshape(-1, 3, 3)
    assert np.allclose(nq[no:], -nq[:no][:, [0, 2, 1]], atol=1e-5)
    d = Vq[T[:no][:, [0, 2, 1]]] - Vq[T[no:]]
    assert np.allclose(np.einsum("fkc,fkc->fk", d, nq[:no][:, [0, 2, 1]]), th, atol=1e-4)
    # and a LOD of the LOD keeps the structure
    q2, _, _ = lods.lod_part(q, None, 0.5)
    assert len(np.asarray(q2["corner_vert"])) // 3 == 2 * q2["shell"]["outer"]


def test_cards_from_a_seen_look_take_the_strands_lift():
    """Garrett session 4: G88a's look is `seen` (a photo's colour); its cards' atlas came out as seen itself (no lift)
    while the EEVEE strands draw lit x eevee_gain: near-black cards beside grey strands."""
    from hifipushie import hair
    lk = hair.full_look({"seen": [0.242, 0.232, 0.226]})
    assert lk["card_gain"] == lk["eevee_gain"] == 1.6
    assert hair.full_look({"seen": [0.242, 0.232, 0.226], "eevee_gain": 1.3})["card_gain"] == 1.3
    assert hair.full_look({"seen": [0.242, 0.232, 0.226], "card_gain": 0.9})["card_gain"] == 0.9  # measured wins
    assert hair.full_look({"lit": "#574536", "eevee_gain": 1.4})["card_gain"] == 1.0  # (Tess: explicit colours, as before)


def test_lod_reduces_past_uv_island_borders():
    """(r51) a part cut into many uv islands reaches its LOD share (welded decimation): Tess's body / coat / jeans
    stopped reducing after LOD1 because every island's border was kept."""
    from hifipushie import lods as _l
    _l.LOD_DEV_MAX, _dev0 = 0.0, _l.LOD_DEV_MAX  # (r60: the shape guard trades budget for shape; this tests the budget)
    try:
        _test_lod_reduces_past_uv_island_borders_body()
    finally:
        _l.LOD_DEV_MAX = _dev0


def _test_lod_reduces_past_uv_island_borders_body():
    import numpy as np
    from hifipushie import lods
    n = 40
    g = np.linspace(0, 1, n + 1)
    X, Y = np.meshgrid(g, g)
    V = np.c_[X.ravel(), Y.ravel(), 0.05 * np.sin(6 * X.ravel()) * np.cos(5 * Y.ravel())]
    idx = lambda i, j: i * (n + 1) + j
    F = []
    for i in range(n):
        for j in range(n):
            F += [(idx(i, j), idx(i, j + 1), idx(i + 1, j + 1)), (idx(i, j), idx(i + 1, j + 1), idx(i + 1, j))]
    F = np.array(F)
    cv = F.ravel()
    # every 4x4 cell block its own uv island (offset uv per block), so island borders are everywhere
    blk = ((F[:, 0] // (n + 1)) // 4) * 100 + ((F[:, 0] % (n + 1)) // 4)
    uv = V[cv, :2] + np.repeat(blk, 3)[:, None] * 0.01
    p = {"verts": V.astype(np.float32), "corner_vert": cv, "uv": uv, "normal": np.tile([0, 0, 1.0], (len(cv), 1)),
         "tangent": np.tile([1.0, 0, 0], (len(cv), 1)), "sign": np.ones(len(cv))}
    for r in (0.25, 0.1):
        q, _, rep = lods.lod_part(p, None, r)
        assert rep["triangles"] <= lods.LOD_WELD_OVER * r * len(F) + 4, (r, rep["triangles"], len(F))
        assert rep["welded"]
        uvq = np.asarray(q["uv"])
        assert np.isfinite(uvq).all() and len(q["corner_vert"]) % 3 == 0
    lods.LOD_WELD = False
    try:
        _, _, rep0 = lods.lod_part(p, None, 0.1)
        assert rep0["triangles"] > lods.LOD_WELD_OVER * 0.1 * len(F)  # the floor this replaces
    finally:
        lods.LOD_WELD = True


def test_lod_reduces_pattern_pieces():
    """(r52) a part made of separate pieces (pattern-piece cloth: sim seams are not shared vertices) reaches its LOD share:
    rc2's coat / jeans / sweater were mostly border edges and stayed at 3.5k / 3.0k / 2.4k from LOD2 to LOD3. Border
    collapses keep the pieces' outlines in place (no vertex wanders off the LOD0 surface)."""
    from hifipushie import lods as _l
    _l.LOD_DEV_MAX, _dev0 = 0.0, _l.LOD_DEV_MAX  # (r60: the shape guard trades budget for shape; this tests the budget)
    try:
        _test_lod_reduces_pattern_pieces_body()
    finally:
        _l.LOD_DEV_MAX = _dev0


def _test_lod_reduces_pattern_pieces_body():
    import numpy as np
    from scipy.spatial import cKDTree
    from hifipushie import lods
    n, b = 48, 6  # 8 x 8 pieces of 6 x 6 cells, each with its OWN vertices, 0.2 mm apart
    V, F = [], []
    for pi in range(n // b):
        for pj in range(n // b):
            g = np.linspace(0, b / n, b + 1)
            X, Y = np.meshgrid(g + pi * b / n + pi * 2e-4, g + pj * b / n + pj * 2e-4)
            o = len(V) and sum(len(v) for v in V)
            V.append(np.c_[X.ravel(), Y.ravel(), 0.05 * np.sin(6 * X.ravel()) * np.cos(5 * Y.ravel())])
            idx = lambda i, j: o + i * (b + 1) + j
            for i in range(b):
                for j in range(b):
                    F += [(idx(i, j), idx(i, j + 1), idx(i + 1, j + 1)), (idx(i, j), idx(i + 1, j + 1), idx(i + 1, j))]
    V, F = np.concatenate(V), np.array(F)
    cv = F.ravel()
    p = {"verts": V.astype(np.float32), "corner_vert": cv, "uv": V[cv, :2], "normal": np.tile([0, 0, 1.0], (len(cv), 1)),
         "tangent": np.tile([1.0, 0, 0], (len(cv), 1)), "sign": np.ones(len(cv))}
    r = 0.12
    q, _, rep = lods.lod_part(p, None, r)
    assert rep["triangles"] <= lods.LOD_WELD_OVER * r * len(F) + 8, (rep["triangles"], len(F))
    d, _ = cKDTree(V).query(np.asarray(q["verts"], float))
    assert d.max() < 1.5 / n, d.max()  # within ~a LOD0 cell of the original surface
    # (r53) the seams stay closed: rc2b's border collapses opened the sim seams (grey slits); welded first, the only border
    # left is the sheet's outline (length by position: vertices split per uv patch are joined at 0.5 mm)
    def border_len(q):
        Vq = np.asarray(q["verts"], float)
        T = np.asarray(q["corner_vert"], np.int64).reshape(-1, 3)
        _, inv = np.unique(np.round(Vq / 5e-4), axis=0, return_inverse=True)
        T = inv.ravel()[T]
        E = np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1)
        u, c = np.unique(E, axis=0, return_counts=True)
        Pq = np.zeros((inv.max() + 1, 3))
        Pq[inv.ravel()] = Vq
        b_ = u[c == 1]
        return np.linalg.norm(Pq[b_[:, 0]] - Pq[b_[:, 1]], axis=1).sum()
    assert border_len(q) < 1.6 * 4 * 1.0, border_len(q)  # the 1 x 1 sheet's outline (and its wave), no seams
    keep = lods.LOD_BORDER_OVER, lods.LOD_SEAM_WELD
    lods.LOD_BORDER_OVER = lods.LOD_SEAM_WELD = 0
    try:
        _, _, rep0 = lods.lod_part(p, None, r)
        assert rep0["triangles"] > lods.LOD_WELD_OVER * r * len(F)  # the floor these replace
        lods.LOD_BORDER_OVER = keep[0]
        q1, _, _ = lods.lod_part(p, None, r)  # border collapses alone: the share, but the seams open
        assert border_len(q1) > 1.6 * 4, border_len(q1)
    finally:
        lods.LOD_BORDER_OVER, lods.LOD_SEAM_WELD = keep


def test_lod_under_garment_stays_under():
    """(r53) each LOD puts an under garment back under its decimated cover: rc2's LOD1-3 showed the jeans through the coat
    skirt and the sweater through its elbows / back (each garment decimated alone, the error bigger than the layer gap).
    Two nested tubes: the inner two-sided (cloth.export_part's shell layout) with bumps through the outer; after
    push_under_layers no inner vertex in reach is less than the gap under, its inner shell moved with it, and the part of
    the inner tube the outer doesn't reach is untouched."""
    import numpy as np
    from hifipushie import lods

    def tube(r, z0, z1, na=48, nz=30, bump=None):
        a, z = np.meshgrid(np.linspace(0, 2 * np.pi, na, endpoint=False), np.linspace(z0, z1, nz))
        rr = r + (bump(a, z) if bump else 0)
        V = np.c_[(rr * np.cos(a)).ravel(), (rr * np.sin(a)).ravel(), z.ravel()]
        F = []
        for i in range(nz - 1):
            for j in range(na):
                q, w = i * na + j, i * na + (j + 1) % na
                F += [(q, w, w + na), (q, w + na, q + na)]
        return V, np.array(F)

    def part(V, F, shell=None):
        Nv = V.copy()
        Nv[:, 2] = 0
        Nv /= np.linalg.norm(Nv, axis=1, keepdims=True)
        if shell:
            n = len(F)
            V = np.r_[V, V - Nv * shell]
            F = np.r_[F, F[:, [0, 2, 1]] + len(Nv)]
            Nv = np.r_[Nv, -Nv]
        cv = F.ravel()
        p = {"verts": V.astype(np.float32), "corner_vert": cv, "uv": V[cv, :2], "normal": Nv[cv],
             "tangent": np.tile([0, 0, 1.0], (len(cv), 1)), "sign": np.ones(len(cv))}
        if shell:
            p["shell"] = {"outer": n, "thickness": shell}
        return p

    bump = lambda a, z: 0.006 * np.clip(np.sin(5 * a) * np.cos(9 * z), 0, None)  # up to 6 mm through a 3 mm gap
    Vi, Fi = tube(0.10, 0.0, 0.6, bump=bump)
    Vo, Fo = tube(0.103, 0.0, 0.4, na=20, nz=10)  # the cover: coarse (decimated) and shorter
    under, cover = part(Vi, Fi, shell=0.0008), part(Vo, Fo)
    _, _, _, t0 = lods.under_depth(under, [cover])
    assert (np.isfinite(t0) & (t0 < 0)).sum() > 50  # the bumps poke through
    parts = {"jeans": under, "coat": cover}
    rep = lods.push_under_layers(parts, {"jeans": ["coat"]})
    q = parts["jeans"]
    _, _, _, t1 = lods.under_depth(q, [cover])
    ok = np.isfinite(t1)
    assert rep["jeans"]["poking0"] > 50 and rep["jeans"]["poking"] == 0, rep
    assert t1[ok].min() > lods.LOD_UNDER_GAP - 2e-4, t1[ok].min()
    V0, V1 = np.asarray(under["verts"], float), np.asarray(q["verts"], float)
    nv = len(Vi)
    assert np.allclose(V1[nv:] - V1[:nv], V0[nv:] - V0[:nv], atol=1e-6)  # the inner shell kept its offset
    low = Vi[:, 2] > 0.45  # beyond the cover's reach
    assert np.allclose(V1[:nv][low], V0[:nv][low]) and np.allclose(V1[nv:][low], V0[nv:][low])
    assert np.asarray(cover["verts"]).tobytes() == np.asarray(parts["coat"]["verts"]).tobytes()  # the cover never moves


def test_cloth_under_cloth_culled():
    """(r53, coordinator) an under garment's faces its cover hides are dropped at LOD0 (the jeans / sweater kept every
    triangle under the coat: budget, and the LOD poke-through): a two-sided tube under a shorter cover loses its covered
    middle on BOTH shells, keeps the part past the cover's opening and a rim inside it, and its shell layout stays valid."""
    import numpy as np
    from hifipushie import asset

    def tube(r, z0, z1, na=40, nz=40):
        a, z = np.meshgrid(np.linspace(0, 2 * np.pi, na, endpoint=False), np.linspace(z0, z1, nz))
        V = np.c_[(r * np.cos(a)).ravel(), (r * np.sin(a)).ravel(), z.ravel()]
        F = [(i * na + j, i * na + (j + 1) % na, (i + 1) * na + (j + 1) % na) for i in range(nz - 1) for j in range(na)]
        F += [(i * na + j, (i + 1) * na + (j + 1) % na, (i + 1) * na + j) for i in range(nz - 1) for j in range(na)]
        return V, np.array(F)

    Vi, Fi = tube(0.10, 0.0, 0.8)
    Nv = Vi * [1, 1, 0] / 0.10
    n = len(Fi)
    V2, F2 = np.r_[Vi, Vi - Nv * 0.0008], np.r_[Fi, Fi[:, [0, 2, 1]] + len(Vi)]
    N2 = np.r_[Nv, -Nv]
    cv = F2.ravel()
    under = {"verts": V2, "corner_vert": cv, "uv": V2[cv, :2], "normal": N2[cv], "tangent": N2[cv], "sign": np.ones(len(cv)),
             "shell": {"outer": n, "thickness": 0.0008}}
    Vo, Fo = tube(0.115, 0.0, 0.5)
    cover = {"verts": Vo, "corner_vert": Fo.ravel(), "normal": (Vo * [1, 1, 0] / 0.115)[Fo.ravel()]}
    keep = asset.cloth_under_keep(under, [cover])
    ko, ki = keep[:n], keep[n:2 * n]
    assert (ko == ki).all()
    zc = Vi[Fi].mean(1)[:, 2]
    assert not ko[(zc > 0.05) & (zc < 0.4)].any()  # covered: dropped
    assert ko[zc > 0.5].all() and ko[(zc > 0.47) & (zc < 0.5)].all()  # past the opening, and the rim inside it
    q = asset.cull_tris(under, keep)
    assert q["shell"]["outer"] == int(ko.sum()) and len(q["corner_vert"]) == 3 * 2 * int(ko.sum())
    assert asset._over_chain({"coat": "sweater", "sweater": "jeans", "jeans": None}, "coat") == ["sweater", "jeans"]


def test_bake_cage_is_per_vertex():
    """(r51) the bake cage pushes each vertex by its OWN faces' stray (skin r14: one extrusion per part, the part's worst
    stray, baked pinwheel fans into Tess's nostrils)."""
    import numpy as np
    from hifipushie import asset
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [5, 0, 0], [6, 0, 0], [5, 1, 0]], float)
    C = np.array([0, 1, 2, 3, 4, 5])
    p = {"verts": V, "corner_vert": C, "normal": np.tile([0, 0, 1.0], (6, 1))}
    d = np.r_[[0.0, -0.01], np.zeros(3), np.full(3, -0.01)]  # face 1 strays 10 mm (its centre and edges), face 0 not
    cg = asset.cage_verts(p, d, 0.001)
    off = cg[:, 2]
    assert np.allclose(off[:3], 0.002) and np.allclose(off[3:], 0.017)
    assert np.allclose(cg[:, :2], V[:, :2])


def _grid_sheet(nx, ny, w, h, z):
    """A sheet over [0, w] x [0, h], height z(x, y), normals +z (the outward side), triangles in rows."""
    import numpy as np
    x, y = np.meshgrid(np.linspace(0, w, nx), np.linspace(0, h, ny))
    V = np.c_[x.ravel(), y.ravel(), z(x, y).ravel()]
    F = []
    for i in range(ny - 1):
        for j in range(nx - 1):
            q = i * nx + j
            F += [(q, q + 1, q + nx + 1), (q, q + nx + 1, q + nx)]
    return V, np.array(F)


def test_lod_made_pieces_stay_over_their_shell():
    """(r54) a two-sided garment's made pieces (a pocket after its shells) keep LOD_MADE_FLOOR of their triangles and stay
    over the decimated outer shell: rc2c's LOD1-3 coat fronts showed grey fans at the hip pockets (1,176 made-piece
    triangles cut to 134 at LOD2, the decimated shell through them)."""
    import numpy as np
    from hifipushie import lods
    wave = lambda x, y: 0.008 * np.sin(60 * x) * np.cos(50 * y)  # a rumpled front: decimation flattens it by mm
    Vo, Fo = _grid_sheet(60, 60, 0.4, 0.4, wave)
    Vp, Fp = _grid_sheet(20, 20, 0.12, 0.12, lambda x, y: wave(x + 0.14, y + 0.14) + 0.0015)  # the pocket, 1.5 mm over
    Vp[:, :2] += 0.14
    th, n = 0.0008, len(Fo)
    V = np.r_[Vo, Vo - [0, 0, th], Vp]
    F = np.r_[Fo, Fo[:, [0, 2, 1]] + len(Vo), Fp + 2 * len(Vo)]

    def vnormals(V, F):
        N = np.zeros_like(V)
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        for k in range(3):
            np.add.at(N, F[:, k], fn)
        return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    cv = F.ravel()
    p = {"verts": V.astype(np.float32), "corner_vert": cv, "uv": V[cv, :2], "normal": vnormals(V, F)[cv],
         "tangent": np.tile([1.0, 0, 0], (len(cv), 1)), "sign": np.ones(len(cv)), "shell": {"outer": n, "thickness": th}}
    for floor in (0.0, lods.LOD_MADE_FLOOR):
        lods.LOD_MADE_FLOOR, gap0 = floor, lods.LOD_MADE_GAP
        if not floor:
            lods.LOD_MADE_GAP = 0
        try:
            q, _, r = lods._lod_shell(dict(p), None, 0.08)
        finally:
            lods.LOD_MADE_FLOOR, lods.LOD_MADE_GAP = (floor or 0.35), gap0
        T = np.asarray(q["corner_vert"]).reshape(-1, 3)
        no = q["shell"]["outer"]
        made = {"verts": q["verts"], "corner_vert": T[2 * no:].ravel(), "normal": np.asarray(q["normal"])[6 * no:]}
        _, _, _, t = lods.under_depth(made, [{"verts": q["verts"], "corner_vert": T[:no].ravel()}], lods.LOD_MADE_REACH)
        through = int((np.isfinite(t) & (t > 0)).sum())  # the shell OUTSIDE a pocket vertex: it shows through
        if not floor:
            assert through > 0, "the bare decimation should put the shell through the pocket (else the test proves nothing)"
        else:
            assert len(T) - 2 * no >= 0.8 * min(lods.LOD_MADE_FLOOR, lods.LOD_MADE_FLOOR_X * 0.08) * len(Fp), (len(T) - 2 * no, len(Fp))
            assert through == 0 and np.nanmax(t) <= -lods.LOD_MADE_GAP + 1e-6, (through, np.nanmax(t))
            assert r["made_lifted"] > 0


def test_lod_buttons_whole_folds_rewound_small_parts_far():
    """(r55) rc2d's LOD2 coat: buttons decimated with the lapels at the made floor became grey cones (now a small own
    piece is kept whole at LOD1-2 and cut to LOD_KEEP_PIECE_FAR at LOD3); folded-over decimated triangles shaded dark as
    radial fans on the pockets (now wound to face their normals: no triangle is wound against its corners' normals); and
    small parts (< MIN_PART) halve at the far LOD (LOD3 was 164 over 12,360, ~4.9k of it small parts kept whole)."""
    import numpy as np
    from hifipushie import lods
    wave = lambda x, y: 0.01 * np.sin(70 * x) * np.cos(60 * y)
    Vo, Fo = _grid_sheet(50, 50, 0.4, 0.4, wave)
    Vb, Fb = _grid_sheet(8, 8, 0.02, 0.02, lambda x, y: 0.004 * np.cos(80 * x) * np.cos(80 * y) + 0.03)  # a button: 98
    Vb[:, :2] += 0.19
    Vl, Fl = _grid_sheet(20, 20, 0.1, 0.1, lambda x, y: wave(x + 0.25, y + 0.25) + 0.0015)  # a lapel: 722
    Vl[:, :2] += 0.25
    th, n = 0.0008, len(Fo)
    V = np.r_[Vo, Vo - [0, 0, th], Vl, Vb]
    F = np.r_[Fo, Fo[:, [0, 2, 1]] + len(Vo), Fl + 2 * len(Vo), Fb + 2 * len(Vo) + len(Vl)]
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    cv = F.ravel()
    p = {"verts": V.astype(np.float32), "corner_vert": cv, "uv": V[cv, :2], "normal": N[cv],
         "tangent": np.tile([1.0, 0, 0], (len(cv), 1)), "sign": np.ones(len(cv)), "shell": {"outer": n, "thickness": th}}
    for ratio, want in ((0.25, len(Fb)), (0.07, None)):
        q, _, r = lods._lod_shell(dict(p), None, ratio)
        T = np.asarray(q["corner_vert"]).reshape(-1, 3)
        Vq = np.asarray(q["verts"], np.float64)
        cen = Vq[T].mean(1)
        nb = int((cen[:, 2] > 0.02).sum())  # the button's triangles (all above the sheet and the lapel)
        if want:
            assert nb == want, (nb, want)
        else:
            assert 0 < nb < 0.7 * len(Fb), nb  # (r61: at LOD3 the button is its convex hull, decimated: a closed lens)
        gn = np.cross(Vq[T[:, 1]] - Vq[T[:, 0]], Vq[T[:, 2]] - Vq[T[:, 0]])
        back = (gn * np.asarray(q["normal"]).reshape(-1, 3, 3).sum(1)).sum(1) < 0
        assert not back.any(), int(back.sum())
    small = {"verts": Vb.astype(np.float32), "corner_vert": Fb.ravel(), "uv": Vb[Fb.ravel(), :2],
             "normal": np.tile([0, 0, 1.0], (Fb.size, 1)), "tangent": np.tile([1.0, 0, 0], (Fb.size, 1)), "sign": np.ones(Fb.size)}
    for ratio, kept in ((0.25, True), (0.07, False)):
        out, _, rep = lods.lod_parts({"clip": small, "eyes": small}, None, ratio)
        assert (len(out["clip"]["corner_vert"]) == Fb.size) == kept, (ratio, len(out["clip"]["corner_vert"]) // 3)
        assert len(out["eyes"]["corner_vert"]) == Fb.size  # (the eyes: never)


def test_lod_small_outer_pieces_whole_and_made_pieces_lifted_rigidly():
    """(r56) rc2e's LOD2 coat pockets: a patch pocket is its own small piece of the OUTER shell (106 triangles, 62 border
    vertices); welded with the coat and decimated with its border held it became a fan of long triangles (pale streaks).
    Now kept whole at LOD1-2 like a button, with its inner shell rebuilt. And a small made piece (a button) lifted over
    the decimated shell moves as one (vertex by vertex it came out lumpy)."""
    import numpy as np
    from hifipushie import lods
    wave = lambda x, y: 0.02 * np.sin(40 * x) * np.cos(35 * y)
    Vo, Fo = _grid_sheet(50, 50, 0.4, 0.4, wave)
    Vp, Fp = _grid_sheet(10, 10, 0.08, 0.08, lambda x, y: wave(x + 0.1, y + 0.1) + 0.002)  # a pocket: 162, own piece
    Vp[:, :2] += 0.1
    Vb, Fb = _grid_sheet(6, 6, 0.016, 0.016, lambda x, y: 0.024 + 0.0 * x)  # a flat button (50), close over the sheet
    Vb[:, :2] += 0.25
    th = 0.0008
    Vout, Fout = np.r_[Vo, Vp], np.r_[Fo, Fp + len(Vo)]
    n = len(Fout)
    V = np.r_[Vout, Vout - [0, 0, th], Vb]
    F = np.r_[Fout, Fout[:, [0, 2, 1]] + len(Vout), Fb + 2 * len(Vout)]
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    cv = F.ravel()
    p = {"verts": V.astype(np.float32), "corner_vert": cv, "uv": V[cv, :2], "normal": N[cv],
         "tangent": np.tile([1.0, 0, 0], (len(cv), 1)), "sign": np.ones(len(cv)), "shell": {"outer": n, "thickness": th}}
    got = {}
    for keep in (False, True):
        lods.LOD_KEEP_OUTER_PIECES = keep
        try:
            q, _, r = lods._lod_shell(dict(p), None, 0.2)
        finally:
            lods.LOD_KEEP_OUTER_PIECES = True
        T = np.asarray(q["corner_vert"]).reshape(-1, 3)
        Vq = np.asarray(q["verts"], np.float64)
        no = q["shell"]["outer"]
        cen = Vq[T[:no]].mean(1)
        inp = ((cen[:, :2] > 0.1) & (cen[:, :2] < 0.18)).all(1) & (cen[:, 2] > wave(cen[:, 0], cen[:, 1]) + 0.001)
        got[keep] = int(inp.sum())
    assert got[True] >= len(Fp) > got[False], got  # (the box may catch a few big sheet triangles)
    # the button: its vertices all moved by the same offset from LOD0
    from scipy.spatial import cKDTree
    bt = T[2 * no:]
    vb = np.unique(bt)
    d, i = cKDTree(Vb).query(Vq[vb])
    off = Vq[vb] - Vb[i]
    assert np.allclose(off, off[0], atol=1e-6), np.ptp(off, 0)


def test_lod_under_faces_pushed_where_the_cover_dips_between_vertices():
    """(r57) rc2f LOD1: three long sweater faces 3.5 mm outside the coat beside the lapel, all their vertices 2 mm under it
    (the coat bends between them). push_under_layers also tests face centroids: a coarse under quad whose corners sit
    under a flat cover with a dent between them ends with every face centroid under the cover; with LOD_UNDER_FACES off
    nothing moves (the vertices alone are under)."""
    import numpy as np
    from hifipushie import lods
    g = np.linspace(-0.05, 0.05, 41)
    X, Y = np.meshgrid(g, g)
    Z = -0.008 * np.clip(1 - np.hypot(X - 0.01, Y + 0.01) / 0.02, 0, None)  # flat, a dent 8 mm deep inside the quad
    Vc = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    Fc = []
    for i in range(40):
        for j in range(40):
            q = i * 41 + j
            Fc += [(q, q + 1, q + 42), (q, q + 42, q + 41)]
    Fc = np.array(Fc).ravel()
    cover = {"verts": Vc.astype(np.float32), "corner_vert": Fc, "normal": np.tile([0, 0, 1.0], (len(Fc), 1))}
    Vu = np.array([[-0.03, -0.03, -0.0025], [0.03, -0.03, -0.0025], [0.03, 0.03, -0.0025], [-0.03, 0.03, -0.0025]])
    Fu = np.array([0, 1, 2, 0, 2, 3])
    under = {"verts": Vu.astype(np.float32), "corner_vert": Fu, "normal": np.tile([0, 0, 1.0], (6, 1))}
    for faces in (False, True):
        lods.LOD_UNDER_FACES = faces
        try:
            parts = {"sw": dict(under), "coat": cover}
            rep = lods.push_under_layers(parts, {"sw": ["coat"]})
        finally:
            lods.LOD_UNDER_FACES = True
        V = np.asarray(parts["sw"]["verts"], float)
        C = V[Fu.reshape(-1, 3)].mean(1)
        tf = lods.cover_depth(C, np.tile([0, 0, 1.0], (2, 1)), [cover])
        if not faces:
            assert np.allclose(V, Vu, atol=1e-6) and (tf < 0).any(), (rep, tf)
        else:
            assert rep["sw"]["faces_poking0"] >= 1 and (tf > 0).all(), (rep, tf)


def test_lod_under_face_grid_finds_pokes_away_from_vertices_and_centroids():
    """(r58) rc2h LOD2: a hexagonal sweater patch through the coat at her right armhole (flat-ID render, then a ray pick
    from the close-up camera: sweater 5 mm in front of the coat) where every sweater vertex and face centroid was under
    the coat. A coarse under quad under a flat cover with a dent at the middle of one EDGE (far from both centroids):
    with LOD_UNDER_FACE_GRID = 1 (centroids, r57) nothing moves; with the grid every grid point ends under the cover.
    A point more than LOD_UNDER_FACE_DEEP outside is a face running out from under the cover's edge: left alone."""
    import numpy as np
    from hifipushie import lods
    g = np.linspace(-0.05, 0.05, 81)
    X, Y = np.meshgrid(g, g)
    Z = -0.008 * np.clip(1 - np.hypot(X, Y + 0.027) / 0.012, 0, None)  # a dent 8 mm deep by the quad's edge y = -0.03
    Vc = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    Fc = []
    for i in range(80):
        for j in range(80):
            q = i * 81 + j
            Fc += [(q, q + 1, q + 82), (q, q + 82, q + 81)]
    Fc = np.array(Fc).ravel()
    cover = {"verts": Vc.astype(np.float32), "corner_vert": Fc, "normal": np.tile([0, 0, 1.0], (len(Fc), 1))}
    Vu = np.array([[-0.03, -0.03, -0.0025], [0.03, -0.03, -0.0025], [0.03, 0.03, -0.0025], [-0.03, 0.03, -0.0025]])
    Fu = np.array([0, 1, 2, 0, 2, 3])
    under = {"verts": Vu.astype(np.float32), "corner_vert": Fu, "normal": np.tile([0, 0, 1.0], (6, 1))}
    B = lods.face_grid(4)
    assert len(B) == 13 and np.allclose(B.sum(1), 1) and (B.max(1) < 1).all()
    for k in (1, 4):
        old = lods.LOD_UNDER_FACE_GRID
        lods.LOD_UNDER_FACE_GRID = k
        try:
            parts = {"sw": dict(under), "coat": cover}
            lods.push_under_layers(parts, {"sw": ["coat"]})
        finally:
            lods.LOD_UNDER_FACE_GRID = old
        V = np.asarray(parts["sw"]["verts"], float)
        P = np.einsum("bk,fkd->fbd", B, V[Fu.reshape(-1, 3)]).reshape(-1, 3)
        t = lods.cover_depth(P, np.tile([0, 0, 1.0], (len(P), 1)), [cover])
        if k == 1:
            assert np.allclose(V, Vu, atol=1e-6) and (t < 0).any(), t
        else:
            assert (t > 0).all(), t
    old = lods.LOD_UNDER_FACE_DEEP
    lods.LOD_UNDER_FACE_DEEP = 0.002  # the 3.5 mm poke now reads as a face running out from under: nothing moves
    try:
        parts = {"sw": dict(under), "coat": cover}
        lods.push_under_layers(parts, {"sw": ["coat"]})
    finally:
        lods.LOD_UNDER_FACE_DEEP = old
    assert np.allclose(np.asarray(parts["sw"]["verts"], float), Vu, atol=1e-6)


def test_lod_patch_pockets_seated_on_the_decimated_panel():
    """(r58) rc2h LOD2: patch pockets kept whole (LOD_KEEP_OUTER_PIECES) over a coarser decimated panel stood off as a
    twisted flap / crumpled with the panel through them. LOD_SEAT_PATCHES re-seats each piece vertex on the decimated
    panel at its LOD0 offset: a pocket 2.6 mm over a bumpy two-sided panel ends 2.6 mm (+-0.3) over the LOD2 panel."""
    import numpy as np
    from hifipushie import lods
    k = 60
    g = np.linspace(-0.15, 0.15, k + 1)
    X, Y = np.meshgrid(g, g)
    h = lambda x, y: 0.012 * np.sin(x / 0.03) * np.cos(y / 0.04)  # a bumpy panel (decimation error: mm)
    Vp = np.c_[X.ravel(), Y.ravel(), h(X, Y).ravel()]
    Fp = []
    for i in range(k):
        for j in range(k):
            q = i * (k + 1) + j
            Fp += [(q, q + 1, q + k + 2), (q, q + k + 2, q + k + 1)]
    Fp = np.array(Fp)
    m = 8  # the pocket: a 4 cm square, its own piece, 2.6 mm over the panel along +z (the panel is gentle there)
    gq = np.linspace(-0.02, 0.02, m + 1)
    Xq, Yq = np.meshgrid(gq + 0.03, gq)
    Vq = np.c_[Xq.ravel(), Yq.ravel(), h(Xq, Yq).ravel() + 0.0026]
    Fq = []
    for i in range(m):
        for j in range(m):
            q = i * (m + 1) + j
            Fq += [(q, q + 1, q + m + 2), (q, q + m + 2, q + m + 1)]
    Fq = np.array(Fq) + len(Vp)
    nO = len(Fp) + len(Fq)
    V = np.r_[Vp, Vq, Vp - [0, 0, 0.0006]]
    Fi = Fp[:, [0, 2, 1]] + len(Vp) + len(Vq)
    T = np.r_[Fp, Fq, np.r_[Fi, Fi[:len(Fq)]]]  # outer (panel + pocket), inner (as many: the layout's contract)
    nt = len(T)
    cv = T.ravel()
    nrm = np.tile([0, 0, 1.0], (3 * nt, 1))
    nrm[3 * nO:] *= -1
    p = {"verts": V.astype(np.float32), "corner_vert": cv, "uv": V[cv, :2].astype(np.float32), "normal": nrm,
         "tangent": np.tile([1, 0, 0.0], (3 * nt, 1)), "sign": np.ones(3 * nt), "shell": {"outer": nO, "thickness": 0.0006}}
    res = {}
    for seat in (False, True):
        lods.LOD_SEAT_PATCHES = seat
        try:
            out, _, r = lods._lod_shell(dict(p), None, 0.1, shapes=False)
        finally:
            lods.LOD_SEAT_PATCHES = True
        Vo = np.asarray(out["verts"], float)
        To = np.asarray(out["corner_vert"], np.int64).reshape(-1, 3)[:out["shell"]["outer"]]
        piece = (np.abs(Vo[To].mean(1)[:, 2] - h(*Vo[To].mean(1)[:, :2].T)) > 0.0013)  # the pocket's triangles
        _, _, _, off, _ = lods._patch_offsets(Vo, To, ~piece, piece, np.asarray(out["normal"], float)[:3 * len(To)])
        res[seat] = (off, r)
    assert res[True][1].get("patches_seated", 0) > 0, res[True][1]
    assert np.abs(res[True][0] - 0.0026).max() < 0.0003, res[True][0]
    assert np.abs(res[False][0] - 0.0026).max() > np.abs(res[True][0] - 0.0026).max()


def test_lod_worn_parts_pushed_only_where_under_at_lod0():
    """(r54) a part worn under a garment that is not a garment (socks under the jeans: kept whole, so the decimated jeans
    sank into them, pale blotches on rc2c's LOD2 calves) is pushed back under, but only where it was under at LOD0:
    a part over the garment there (a shoe collar over the hem) is left alone."""
    import numpy as np
    from hifipushie import lods
    Vu, Fu = _grid_sheet(30, 30, 0.3, 0.3, lambda x, y: np.zeros_like(x))
    Vc, Fc = _grid_sheet(8, 8, 0.3, 0.3, lambda x, y: np.full_like(x, 0.003))  # the cover 3 mm out
    mk = lambda V, F: {"verts": V.astype(np.float32), "corner_vert": F.ravel(), "uv": V[F.ravel(), :2],
                       "normal": np.tile([0, 0, 1.0], (F.size, 1)), "tangent": np.tile([1.0, 0, 0], (F.size, 1)),
                       "sign": np.ones(F.size)}
    under0, cover = mk(Vu, Fu), mk(Vc, Fc)
    masks = {"socks": lods.under_at_lod0(under0, [cover])}
    over = Vu[:, 0] > 0.2  # this end was over the cover at LOD0 (a shoe collar): lift it out there
    Vu0 = Vu.copy()
    Vu0[over, 2] = 0.006
    masks["socks"] = lods.under_at_lod0(mk(Vu0, Fu), [cover])
    assert masks["socks"][1].sum() > 0 and not masks["socks"][1][over[np.unique(Fu)]].any()
    Vk = Vu0.copy()
    Vk[~over, 2] += 0.0045 * (np.sin(30 * Vu[~over, 0]) > 0)  # LODk: the under end pokes through in bands
    parts = {"socks": mk(Vk, Fu), "jeans": cover}
    rep = lods.push_under_layers(parts, {"socks": ["jeans"]}, masks=masks)
    Vr = np.asarray(parts["socks"]["verts"], float)
    assert rep["socks"]["poking"] == 0 and rep["socks"]["moved"] > 0
    assert np.allclose(Vr[over], Vk[over]), "a part over the garment at LOD0 must not be pushed under it"
    assert (Vr[~over, 2] <= 0.003 - lods.LOD_UNDER_GAP + 1e-6).all()


def test_cull_restores_faces_exposed_in_a_pose():
    """(r54) the garment-under-garment cull is checked over posed frames (blender_game "dump" npz: rest / posed vertices
    per mesh): a triangle hidden at rest but uncovered in any frame is kept. A two-sided tube under a shorter cover; in
    the 'pose' the cover rides up 6 cm: the band it leaves comes back, a still pose restores nothing."""
    import numpy as np
    from hifipushie import asset

    def tube(r, z0, z1, na=40, nz=40, shell=None):
        a, z = np.meshgrid(np.linspace(0, 2 * np.pi, na, endpoint=False), np.linspace(z0, z1, nz))
        V = np.c_[(r * np.cos(a)).ravel(), (r * np.sin(a)).ravel(), z.ravel()]
        F = []
        for i in range(nz - 1):
            for j in range(na):
                q, w = i * na + j, i * na + (j + 1) % na
                F += [(q, w, w + na), (q, w + na, q + na)]
        F = np.array(F)
        Nv = V.copy(); Nv[:, 2] = 0; Nv /= np.linalg.norm(Nv, axis=1, keepdims=True)
        n = len(F)
        if shell:
            V, F, Nv = np.r_[V, V - Nv * shell], np.r_[F, F[:, [0, 2, 1]] + len(V)], np.r_[Nv, -Nv]
        cv = F.ravel()
        p = {"verts": V, "corner_vert": cv, "normal": Nv[cv], "uv": V[cv, :2], "tangent": np.tile([0, 0, 1.0], (len(cv), 1)),
             "sign": np.ones(len(cv))}
        if shell:
            p["shell"] = {"outer": n, "thickness": shell}
        return p
    under, cover = tube(0.10, 0.0, 0.8, shell=0.0008), tube(0.115, 0.2, 0.8)
    keep0 = asset.cloth_under_keep(under, [cover])
    assert (~keep0).sum() > 100
    Vu, Vc = np.asarray(under["verts"]), np.asarray(cover["verts"])
    still = {"under:rest": Vu, "under:posed": Vu, "cover:rest": Vc, "cover:posed": Vc}
    k1, r1 = asset.cull_exposed_keep(under, [cover], "under", ["cover"], [still], keep0)
    assert r1["restored"] == 0 and (k1 == keep0).all()
    up = dict(still, **{"cover:posed": Vc + [0, 0, 0.06]})
    k2, r2 = asset.cull_exposed_keep(under, [cover], "under", ["cover"], [still, up], keep0)
    assert r2["restored"] > 0 and r2["frames"] == 2 and (k2 | ~keep0).all()
    T = np.asarray(under["corner_vert"]).reshape(-1, 3)
    zc = Vu[T].mean(1)[:, 2]
    back = k2 & ~keep0
    assert back.any() and zc[back].min() > 0.2 - 1e-6 and zc[back].max() < 0.2 + 0.06 + 0.04 + 1e-6
    q = asset.cull_tris(under, k2)
    assert q["shell"]["outer"] == int(k2[:under["shell"]["outer"]].sum())


def test_lod_worn_part_drops_its_covered_rim_far():
    """(r60) at far LODs a worn part (socks) drops the faces that were deep under a garment at LOD0 (beyond a rim from
    the nearest point that was not): rc2j's LOD2 sock tops showed through the decimated jeans' calf as a shard."""
    import numpy as np
    from hifipushie import lods
    Vu, Fu = _grid_sheet(30, 30, 0.3, 0.3, lambda x, y: np.zeros_like(x))
    Vc, Fc = _grid_sheet(8, 8, 0.15, 0.3, lambda x, y: np.full_like(x, 0.003))  # the cover over x < 0.15 only
    mk = lambda V, F: {"verts": V.astype(np.float32), "corner_vert": F.ravel(), "uv": V[F.ravel(), :2],
                       "normal": np.tile([0, 0, 1.0], (F.size, 1)), "tangent": np.tile([1.0, 0, 0], (F.size, 1)),
                       "sign": np.ones(F.size)}
    sock, cover = mk(Vu, Fu), mk(Vc, Fc)
    P0, un0 = lods.under_at_lod0(sock, [cover])
    assert un0.any() and not un0.all()
    keep = lods.cull_covered(sock, P0, un0)
    T = Fu.reshape(-1, 3)
    xc = Vu[T].mean(1)[:, 0]
    assert keep[xc > 0.15].all(), "faces in the open stay"
    assert keep[(xc > 0.15 - lods.LOD_UNDER_CULL_RIM + 0.011) & (xc < 0.15)].all(), "the rim under the opening stays"
    assert not keep[xc < 0.15 - lods.LOD_UNDER_CULL_RIM - 0.011].any(), "deep under the cover is dropped"


def test_lod_welded_decimation_redone_where_it_strays():
    """(r60) a welded group decimated to a small target must not collapse across a deep fold (rc2j's LOD2 jeans bridged
    the crotch, 41 mm off LOD0: a slit at the fly): the result is redone at a bigger target while it strays past
    LOD_DEV_MAX."""
    import numpy as np
    from hifipushie import lods
    # a deep narrow V fold (two walls 60 mm deep, 4 mm apart at the bottom) in a sheet
    V, F = _grid_sheet(60, 20, 0.3, 0.1, lambda x, y: -0.06 * np.clip(1 - np.abs(x - 0.15) / 0.012, 0, 1))
    tgt = 24
    p = {"verts": V.astype(np.float32), "corner_vert": F.ravel(), "uv": V[F.ravel(), :2],
         "normal": np.tile([0, 0, 1.0], (F.size, 1)), "tangent": np.tile([1.0, 0, 0], (F.size, 1)), "sign": np.ones(F.size)}
    src = np.arange(len(V))
    r = tgt / len(F)

    def run(dev_max):
        old = lods.LOD_DEV_MAX, lods.LOD_DEV_TRIES, lods.LOD_DEV_REF
        try:
            lods.LOD_DEV_MAX, lods.LOD_DEV_TRIES, lods.LOD_DEV_REF = dev_max, 4, r
            out = lods._welded_pieces(p, [(0, np.arange(len(F)), src, F, V, V, F)], src, None, [], r, None, len(F))
        finally:
            lods.LOD_DEV_MAX, lods.LOD_DEV_TRIES, lods.LOD_DEV_REF = old
        Vw = np.concatenate([o[5] for o in out])
        Fw = np.concatenate([o[6] + sum(len(x[5]) for x in out[:i]) for i, o in enumerate(out)])
        return lods._deviation(V, Vw, Fw), len(Fw)
    d0, n0 = run(0.0)
    d1, n1 = run(0.003)
    assert d0 > 0.003, f"the unguarded decimation should stray here ({d0 * 1000:.0f} mm)"
    assert d1 < 0.6 * d0 and n1 > n0, (d0, n0, d1, n1)  # (36 mm, 24 tris -> 18 mm, 68)


def test_lod_worn_part_push_is_capped():
    """(r61) a worn part (the skin) moves at most LOD_UNDER_WORN_MAX when it is put back under its covers: rc2l's LOD3
    neck was pushed up to 49 mm under the sweater's collar and its big triangles dragged the visible neck into wedges."""
    import numpy as np
    from hifipushie import lods
    Vu, Fu = _grid_sheet(20, 20, 0.2, 0.2, lambda x, y: np.zeros_like(x))
    Vc, Fc = _grid_sheet(8, 8, 0.2, 0.2, lambda x, y: np.full_like(x, -0.015))  # the cover 15 mm INSIDE the skin
    mk = lambda V, F: {"verts": V.astype(np.float32), "corner_vert": F.ravel(), "uv": V[F.ravel(), :2],
                       "normal": np.tile([0, 0, 1.0], (F.size, 1)), "tangent": np.tile([1.0, 0, 0], (F.size, 1)),
                       "sign": np.ones(F.size)}
    skin, cover = mk(Vu, Fu), mk(Vc, Fc)
    masks = {"skin": (Vu.astype(np.float64), np.ones(len(Vu), bool), None, np.tile([0, 0, 1.0], (len(Vu), 1)))}
    parts = {"skin": skin, "cover": cover}
    lods.push_under_layers(parts, {"skin": ["cover"]}, masks=masks)
    mv = np.linalg.norm(np.asarray(parts["skin"]["verts"], np.float64) - Vu, axis=1)
    assert mv.max() > 0.005, "the skin is pushed in"
    assert mv.max() <= lods.LOD_UNDER_WORN_MAX + 1e-6, mv.max()


def test_drawn_made_parts_without_thickness():
    """(Garrett export 2026-10-18) the frozen shirt's made stand / collar had no "thickness": drawn() fell over (KeyError)."""
    from hifipushie import cloth_made
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float)
    F = np.array([[0, 1, 2], [1, 3, 2]])
    res = {"mesh": {"F": F, "piece": [0, 0], "names": ["a"]}, "made": {"parts": [{"name": "stand", "V": V, "F": F}]}}
    hide, parts = cloth_made.drawn(res)
    assert parts[0][0] == "stand" and not hide.any()


def test_lod0_hair_tier_defaults_to_the_role():
    """LOD0's card tier comes from the role when hair.export.tier is unset (Garrett v3 / v4 got EXPORT_CARDS' old
    per-lock cut, 96 cards + cap, while LOD1-3 had tiers); an explicit tier (Tess: "hero") is kept; no role warns."""
    from hifipushie import asset
    sp = {"hair": {"style": "strands", "export": {"card_gain": 2.1}}}
    log = []
    out = asset.hair_tier_default(sp, "hero", log)
    assert out["hair"]["export"] == {"card_gain": 2.1, "tier": "hero"} and "tier" not in sp["hair"]["export"]
    assert asset.hair_tier_default(sp, "secondary_npc", [])["hair"]["export"]["tier"] == "npc"
    tess = {"hair": {"style": "strands", "export": {"tier": "hero"}}}
    assert asset.hair_tier_default(tess, "crowd", []) is tess
    locks = {"hair": {"locks": {}}}
    assert asset.hair_tier_default(locks, "hero", []) is locks
    log = []
    assert asset.hair_tier_default(sp, None, log) is sp and any(l.startswith("WARNING hair") for l in log)


def test_cloth_decimated_under_its_budget_despite_floors():
    """Parts with floors (made pieces kept whole) overshoot one shared ratio (Garrett v5: clothing 27,032 of 25,000):
    decimate_cloth scales the ratio by the overshoot until the garments fit."""
    from hifipushie import asset, lods

    def fake(p, w, ratio, **k):  # a part keeps its floor + ratio of the rest
        n0 = len(p["corner_vert"]) // 3
        n = min(n0, p["floor"] + int(ratio * (n0 - p["floor"])))
        return {"corner_vert": np.zeros(3 * n, np.int64)}, None, {"triangles0": n0, "triangles": n}

    parts = [(nm, {"corner_vert": np.zeros(3 * n, np.int64), "floor": f}, {}) for nm, n, f in
             (("shirt", 29000, 7400), ("jacket", 17600, 0), ("trousers", 45300, 0))]
    old, lods.lod_part = lods.lod_part, fake
    try:
        log = []
        out = asset.decimate_cloth(parts, 25000, log)
    finally:
        lods.lod_part = old
    tot = sum(len(q["corner_vert"]) // 3 for _, q, _ in out)
    assert 24000 < tot <= 25000 and not any(l.startswith("WARNING") for l in log), (tot, log)


def test_frozen_garments_keep_their_over_chain_in_the_export():
    """Garrett v6: frozen garments in the spec ({"frozen", "color"}) carry no "over", so asset._garment_stack was empty
    and no garment push-under ran at any LOD, silently. The export falls back to the chain frozen with each garment
    (logged); the spec's own "over" wins; garments with no chain anywhere are a WARNING."""
    from hifipushie import asset
    b0 = cloth.Body(_grid_body())
    res = {"V": b0.V[:10] * 1.05, "mesh": {"F": np.array([[0, 1, 2]])}, "body": b0, "key": "k", "pieces": {}}
    with tempfile.TemporaryDirectory() as d:
        paths = {}
        for gn, over in (("shirt", None), ("jacket", "shirt"), ("trousers", "shirt")):
            g = {"pattern": {"from": "simon"}, **({"over": over} if over else {})}
            paths[gn] = cloth.freeze(res, g, Path(d) / f"{gn}.pkl", model="m", garment=gn)["path"]
        spec = {"cloth": {gn: {"frozen": p_, "color": "#333333"} for gn, p_ in paths.items()}}
        parts = {f"cloth_{gn}": {} for gn in paths}
        log = []
        st = asset._garment_stack(spec, parts, log.append)
        assert sorted(st["cloth_shirt"]) == ["cloth_jacket", "cloth_trousers"] and len(st) == 1, st
        assert any("frozen garments' own chain" in l and "jacket over shirt" in l for l in log), log
        spec["cloth"]["jacket"]["over"] = "trousers"  # the spec wins
        st = asset._garment_stack(spec, parts)
        assert sorted(st["cloth_shirt"]) == ["cloth_jacket", "cloth_trousers"] and st["cloth_trousers"] == ["cloth_jacket"]
    log = []
    assert asset.garment_over({"cloth": {"a": {}, "b": {}}}, log.append) == {"a": None, "b": None}
    assert any(l.startswith("WARNING garment layers") for l in log)
