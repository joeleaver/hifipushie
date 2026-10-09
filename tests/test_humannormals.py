"""humannormals: a normal map as evidence rows on the identity. Needs GNM's pack (skipped without); never runs DAViD."""
import numpy as np
import pytest

from hifipushie import assets


def _gnm():
    try:
        from hifipushie import base
        return base._gnm_data()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no GNM pack: {e}")


def _setup():
    from hifipushie import humanfit, humannormals as hn, likeness
    g = _gnm()
    G = hn.gnm()
    names = [str(n) for n in g["identity_names"]]
    comps = [i for i, n in enumerate(names) if n.startswith("head")][:40]
    B = np.asarray(g["vertex_identity_basis"])[comps].astype(float)
    IB = np.stack([B[..., 0], -B[..., 2], B[..., 1]], -1)
    V0 = G["V0"]
    ctr = V0[G["face"]].mean(0)
    cam = {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.7], "f": 1100.0, "size": [512, 512], "centre": ctr.tolist(), "yaw": 0.0}
    return hn, humanfit, likeness, G, IB, V0, cam


def _normal_map(hn, humanfit, likeness, G, V, cam):
    w, h = cam["size"]
    Rc = humanfit._cam_rot(cam)
    Xc = (V - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
    P = humanfit.project(cam, V)
    n = hn.vnormals(V, G["T"]) @ Rc.T
    img = np.zeros((h, w, 3))
    zb = np.full((h, w), np.inf)
    F = G["T"]
    fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
    keep = (fn * Xc[F].mean(1)).sum(1) < 0
    likeness._raster()(P[:, 0].copy(), P[:, 1].copy(), Xc[:, 2].copy(), np.ascontiguousarray(F[keep]), np.ascontiguousarray((n * 0.5 + 0.5) * 255), w, h, img, zb)
    out = img / 255 * 2 - 1
    out[~np.isfinite(zb)] = [0, 0, -1]
    return out / np.maximum(np.linalg.norm(out, axis=-1, keepdims=True), 1e-9)


def test_calibration_file():
    from hifipushie import humannormals as hn
    cal = hn.calibration()
    assert cal["g"].shape[0] == 4 and cal["g"].shape == cal["s"].shape == cal["p"].shape
    use = np.isfinite(cal["s"][0]) & (cal["s"][0] < hn.CUT * cal["p"][0])
    assert use.sum() > 2000                      # the front class sees most of the face
    assert 0.2 < np.median(cal["g"][0][use]) < 0.9     # the model exaggerates relief: gains under 1
    assert not np.isfinite(cal["s"][2]).all()


def test_perfect_normals_move_the_identity_toward_the_truth(monkeypatch):
    hn, humanfit, likeness, G, IB, V0, cam = _setup()
    K = IB.shape[0]
    c_true = np.random.default_rng(3).normal(0, 1.0, K)
    Vt = V0 + np.tensordot(c_true, IB, 1)
    nmap = _normal_map(hn, humanfit, likeness, G, Vt, cam)
    nv = len(V0)
    monkeypatch.setitem(hn._C, "cal", {"g": np.ones((4, nv)), "s": np.full((4, nv), 0.02), "p": np.ones((4, nv)), "flip": np.ones(3)})
    c = np.zeros(K)
    for _ in range(4):
        A, y, info = hn.rows(nmap, V0 + np.tensordot(c, IB, 1), IB, c, cam, 0, inflate=1.0)
        assert info["vertices"] > 300
        c = np.linalg.solve(A.T @ A + np.eye(K), A.T @ y)
    n_t = hn.vnormals(Vt, G["T"])
    f = np.flatnonzero(G["face"])
    err = lambda V: np.degrees(np.arccos(np.clip((hn.vnormals(V, G["T"])[f] * n_t[f]).sum(1), -1, 1))).mean()  # noqa: E731
    assert err(V0 + np.tensordot(c, IB, 1)) < 0.5 * err(V0)


def test_hidden_pixels_and_restriction_are_left_out():
    hn, humanfit, likeness, G, IB, V0, cam = _setup()
    nmap = _normal_map(hn, humanfit, likeness, G, V0, cam)
    c = np.zeros(IB.shape[0])
    A, y, info = hn.rows(nmap, V0, IB, c, cam, 0)
    hide = np.zeros((512, 512), bool)
    hide[:256] = True
    A2, y2, info2 = hn.rows(nmap, V0, IB, c, cam, 0, hide=hide)
    assert 0 < info2["vertices"] < info["vertices"]
    assert np.abs(y).max() < 1.0                 # the mean head against its own normals: nothing to say
