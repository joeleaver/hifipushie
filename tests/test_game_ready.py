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
