"""skin_project on synthetic input, no Blender (`uv run python tests/test_skin_project.py`; needs the gnm + makehuman
packs, skips without): the head's atlas and its lookup at surface points (image wrap "uv"), a picture sampled into the
atlas through a known camera, and the de-lighting against a KNOWN albedo shaded by a known light through the head's
own light transport."""
import numpy as np

from hifipushie import assets, humanfit as hf, likeness as lk, skin, skin_project as sp
from hifipushie.spec import SpecError

B = {"body": {"source": "human", "age": 40, "sex": 1.0}, "head": {"seed": 3, "spread": 0.5}}
_C = {}


def _have():
    try:
        assets.pack("gnm")
        assets.pack("makehuman")
        return True
    except Exception as err:  # noqa: BLE001
        print("skipped:", str(err)[:80])
        return False


def setup():
    if not _C:
        _C.update(at=sp.atlas(B, 512), mesh=lk.model_mesh(B))
    return _C


def test_atlas_and_lookup():
    if not _have():
        return
    at = setup()["at"]
    H, W = at["shape"]
    assert W == 512 and 300 < H < 512 and 0.7 < at["mm"] < 1.2, (at["shape"], at["mm"])
    assert len(at["ii"]) > 0.5 * H * W                        # the head fills most of its box
    hm = sp.interp(at, at["groups"]["hockey_mask"]) > 0.5
    assert hm.sum() > 0.1 * len(hm)
    # every texel's surface point looks itself up: the same atlas coordinates, weight 1 away from the cut
    X = sp.interp(at, at["V"])
    rng = np.random.default_rng(0)
    idx = rng.choice(len(X), 4000, replace=False)
    u, v, w = sp.lookup(B, X[idx])
    u0, v0, u1, v1 = at["box"]
    px = (u - u0) / (u1 - u0) * W
    py = (v1 - v) / (v1 - v0) * H
    ok = w > 0.99
    assert ok.mean() > 0.93, ok.mean()
    err = np.hypot(px - (at["jj"][idx] + 0.5), py - (at["ii"][idx] + 0.5))
    assert np.percentile(err[ok], 99) < 0.75, np.percentile(err[ok], 99)
    # off the head (the chest) and inside the mouth's sock: no weight
    far = sp.lookup(B, np.array([[0.0, -0.1, 1.2], [0.3, 0.0, 1.0]]))[2]
    assert (far == 0).all()
    # a point 1 mm off the surface still lands; 2 cm off does not
    N = sp.interp(at, lk._vertex_normals(at["V"], at["T"]))
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    assert (sp.lookup(B, X[idx] + 0.001 * N[idx])[2][ok] > 0.9).mean() > 0.97
    assert (sp.lookup(B, X[idx] + 0.02 * N[idx])[2] == 0).mean() > 0.97      # (a few land on another fold of the head: an ear)


def test_sample_view():
    if not _have():
        return
    c = setup()
    at, mesh = c["at"], c["mesh"]
    L = np.asarray(mesh["L"], float)
    w, h = 640, 800
    cam = {"r": [0.0, 0.0, 0.0], "yaw": 0.0, "centre": L[:68].mean(0).tolist(), "t": [0.0, 0.0, 1.6], "f": 2400.0, "size": [w, h]}
    photo = np.full((h, w, 3), 128, np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = hf.project(cam, L[30][None])[0]                    # a red dot at the nose tip
    photo[(xx - u) ** 2 + (yy - v) ** 2 < 6 ** 2] = (255, 0, 0)
    s = sp.sample_view(at, mesh, cam, photo)
    X = sp.interp(at, at["V"])
    red = (s["rgb"][:, 0] > 0.8) & (s["rgb"][:, 1] < 0.1) & s["vis"]
    assert red.sum() > 5
    assert np.linalg.norm(X[red].mean(0) - L[30]) < 0.004, X[red].mean(0) - L[30]
    back = X[:, 1] > L[:68, 1].max() + 0.06                   # the back of the head is not seen from the front
    assert not s["vis"][back].any()
    assert 0.6 < s["mm"] < 0.75                               # 1.6 m / 2400 px


def test_delight_known_light():
    if not _have():
        return
    c = setup()
    at, mesh = c["at"], c["mesh"]
    X = sp.interp(at, at["V"])
    N = sp.interp(at, lk._vertex_normals(at["V"], at["T"]))
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    front = np.flatnonzero((N[:, 1] < -0.3) & (sp.interp(at, at["groups"]["hockey_mask"]) > 0.5))
    rng = np.random.default_rng(2)
    sub = front[rng.choice(len(front), 6000, replace=False)]
    tr = sp.transfer(mesh, X, N, sub, n_dirs=64)
    assert tr["T"].shape == (len(X), 9) and 0.0 <= tr["ao"].min() and tr["ao"].max() <= 1.0001
    # a nostril / the lip line is occluded, the forehead open
    assert np.percentile(tr["ao"][front], 0.2) < 0.8 < 0.9 < np.percentile(tr["ao"][front], 80), np.percentile(tr["ao"][front], [0.2, 2, 80])
    # the known scene: a flat tone with freckles (pigment), a soft sky + one key from the upper left with its shadow
    alb = np.tile([0.55, 0.36, 0.27], (len(X), 1))
    spots = rng.choice(front, 300, replace=False)
    alb[spots] *= 0.6
    sh = np.zeros(9)
    sh[0], sh[3], sh[2] = 0.35, 0.12, -0.1                    # ambient, from above, from the front (-y)
    kd = np.array([0.5, -0.65, 0.55]) / np.linalg.norm([0.5, -0.65, 0.55])
    kb = sp.key_basis(mesh, X, N, kd)
    shade = tr["T"] @ sh + 0.9 * kb
    rgb = alb * shade[:, None] * np.array([1.0, 0.95, 0.85])   # a warm light
    view = {"rgb": rgb.astype(np.float32), "T": tr["T"], "D": tr["D"], "sub": sub, "sub_vis": tr["sub_vis"], "X": X, "N": N}
    fit = sub
    lt = sp.fit_light(view, np.tile([0.55, 0.36, 0.27], (len(X), 1)), fit, mesh=mesh)
    assert lt["key"] is not None and np.degrees(np.arccos(np.clip(np.dot(lt["key"]["dir"], kd), -1, 1))) < 14, lt["key"]
    rec = rgb / np.maximum(lt["S"], 1e-4)
    lit = shade[front] > 0.3 * np.median(shade[front])
    e = np.abs(np.log(rec[front][lit] @ sp.Y) - np.log(alb[front][lit] @ sp.Y))
    assert np.median(e) < 0.03 and np.percentile(e, 90) < 0.12, (np.median(e), np.percentile(e, 90))
    # the pigment survives: the freckles stay ~0.6 x their surroundings
    sp_lit = spots[shade[spots] > 0.3 * np.median(shade[front])]
    ratio = np.median(rec[sp_lit] @ sp.Y) / np.median(rec[front][lit] @ sp.Y)
    assert 0.52 < ratio < 0.68, ratio
    # without the key the residual is clearly worse
    assert lt["rms"] < 0.7 * lt["rms0"], (lt["rms"], lt["rms0"])


def test_spec_layers():
    spec = {"skin": {"tone": {"fitzpatrick": 2}, "projection": {"albedo": "0" * 16, "detail": "1" * 16, "box": [0.56, 0.65, 1.0, 0.99],
                                                               "opacity": 1.0, "detail_depth": 0.0001, "head": "abc"}}}
    p = skin.params(spec)
    out = {}
    sp.layers(spec, p["projection"], out, "body")
    assert out["skin:projection"]["image"]["wrap"] == "uv" and out["skin:projection"]["color"] == "image"
    assert out["skin:projection_detail"]["height"] == -0.0001 and out["skin:projection_detail"]["mask"][0]["image"]["channel"] == "luma"
    try:
        skin.params({"skin": {"projection": {"albedo": "x", "bogus": 1, "box": [0, 0, 1, 1]}}})
        raise AssertionError("bad projection keys accepted")
    except SpecError:
        pass
    assert skin.params({"skin": {}})["projection"] is None


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
