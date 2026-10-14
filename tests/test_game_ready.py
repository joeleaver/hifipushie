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
        assert n["lods"][1]["switch_m"] > 0 and "unreal" in kinds["hair_cards"]["engines"]
        assert "## LODs" in open(m).read()


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
