"""diag_render known answers: the measures (pure) and the rendered colours read back by pixel (needs Blender + the GPU:
run under /mnt/data/hifipushie/bin/capped, else the render tests skip).

    /mnt/data/hifipushie/bin/capped uv run python tests/test_diag_render.py [outdir]
"""
import os
import sys
import tempfile

import numpy as np

from hifipushie import diag_render as dr


def grid(x0, x1, z0, z1, nx, nz, y=0.0, flip=False):
    """A sheet in the XZ plane at y, normals toward -Y (the front camera) unless flip; uv = (x, z)."""
    xs, zs = np.linspace(x0, x1, nx + 1), np.linspace(z0, z1, nz + 1)
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    V = np.c_[X.ravel(), np.full(X.size, y), Z.ravel()]
    q = np.arange(V.shape[0]).reshape(nx + 1, nz + 1)
    a, b, c, d = q[:-1, :-1].ravel(), q[1:, :-1].ravel(), q[1:, 1:].ravel(), q[:-1, 1:].ravel()
    F = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    if flip:
        F = F[:, ::-1]
    return V, F, V[:, [0, 2]].copy()


def two_panels():
    """Pieces A (x -0.2..0) and B (x 0..0.2) sewn at x = 0; B's strip past x = 0.15 folded 180 deg over its front
    (onto x 0.10..0.15, 4 mm toward the camera)."""
    VA, FA, uA = grid(-0.2, 0.0, 0.0, 0.3, 20, 30)
    VB, FB, uB = grid(0.0, 0.2, 0.0, 0.3, 20, 30)
    nA = len(VA)
    V = np.r_[VA, VB]
    F = np.r_[FA, FB + nA]
    uv = np.r_[uA, uB]
    piece = np.r_[np.zeros(nA, int), np.ones(len(VB), int)]
    colA = np.where(np.isclose(VA[:, 0], 0.0))[0]
    colB = np.where(np.isclose(VB[:, 0], 0.0))[0] + nA
    sew = np.stack([colA[np.argsort(VA[colA, 2])], colB[np.argsort(V[colB, 2])]], 1)
    row = np.where((piece == 1) & np.isclose(V[:, 0], 0.15))[0]
    row = row[np.argsort(V[row, 2])]
    fl = (piece == 1) & (V[:, 0] > 0.15 + 1e-9)
    V = V.copy()
    V[fl, 0] = 0.3 - V[fl, 0]
    V[fl, 1] = -0.004
    M = {"uv": uv, "piece": piece, "names": ["A", "B"], "F": F, "sew": sew, "sew_seam": np.zeros(len(sew), int),
         "folds": [{"piece": "B", "name": "flap", "kind": "press", "turn": np.pi, "sign": -1.0, "rows": [row]}]}
    return V, F, M, fl


def test_measures():
    V, F, M, fl = two_panels()
    got = dr.flap_faces(M)
    want = M["uv"][F].mean(1)[:, 0] > 0.15  # every face past the fold line (the hinge column too)
    assert (got == want).all(), (got.sum(), want.sum())
    assert len(dr.seam_edges(M)) == 2 * 30  # both sides of the 30-edge seam
    cols = dr._piece_colours([{"name": "g", "mesh": M}])
    assert cols[("g", 0)] != cols[("g", 1)]
    # stretched strip: strain only there
    Vs, Fs, us = strip_sheet()
    s = dr.face_strain(Vs, Fs, us)
    cx = us[Fs].mean(1)[:, 0]
    ins = (cx > 0.15) & (cx < 0.25)
    assert np.allclose(s[ins], 0.10, atol=1e-6) and np.allclose(s[~ins], 0.0, atol=1e-6)
    # pierce: the bump only
    (Vu, Fu), (Vc, Fc), body = poke_layers()
    pm = dr.pierce_faces(Vu, Fu, Vc, Fc, body)
    c = Vu[Fu].mean(1)
    near = np.hypot(c[:, 0], c[:, 2] - 0.2) < 0.04
    assert pm.any() and not pm[~near].any(), (pm.sum(), pm[~near].sum())


def strip_sheet():
    V, F, uv = grid(0.0, 0.4, 0.0, 0.4, 40, 40)
    x = uv[:, 0]
    V = V.copy()
    V[:, 0] = np.where(x < 0.15, x, np.where(x <= 0.25, 0.15 + (x - 0.15) * 1.1, x + 0.01))
    return V, F, uv


def poke_layers():
    Vu, Fu, _ = grid(-0.15, 0.15, 0.05, 0.35, 30, 30, y=0.0)
    r = np.hypot(Vu[:, 0], Vu[:, 2] - 0.2)
    Vu = Vu.copy()
    Vu[:, 1] = np.where(r < 0.03, -0.02 * (1 - (r / 0.03) ** 2), 0.0)
    Vc, Fc, _ = grid(-0.15, 0.15, 0.05, 0.35, 23, 23, y=-0.008)
    body = grid(-0.15, 0.15, 0.05, 0.35, 10, 10, y=0.05)[0]
    return (Vu, Fu), (Vc, Fc), body


def _mesh(V, F, names=("A",)):
    uv = V[:, [0, 2]].copy()
    return {"uv": uv, "piece": np.zeros(len(V), int), "names": list(names), "F": F, "sew": np.zeros((0, 2), int)}


RES, ASPECT = 400, 1.0


def _px(im, box, x, z):
    """Pixel colour (int RGB) at world (x, z) in a front ortho view of box."""
    lo, hi = np.asarray(box[0], float), np.asarray(box[1], float)
    c = (lo + hi) / 2
    size = float(max(hi - lo)) * 1.08
    H, W = im.shape[:2]
    px = int(round(W / 2 + (x - c[0]) * max(W, H) / size))
    py = int(round(H / 2 - (z - c[2]) * max(W, H) / size))
    return im[py, px].astype(int)


def _close(p, hexc, tol=24):
    return np.abs(p - np.round(dr.hex_rgb(hexc) * 255)).max() <= tol


def _render(objs, modes, box, out, tag):
    from PIL import Image
    paths, legend = dr.render(objs, os.path.join(out, tag), modes, views=["front"], resolution=RES, box=box,
                              aspect=ASPECT)
    return np.asarray(Image.open(paths[0]).convert("RGB")), legend


def render_cases(out):
    from hifipushie import resources
    rows = []
    with resources.heavy("diag_render known answers", gb=2, gpu=True):
        # 1. two panels, a seam, a turned flap
        V, F, M, fl = two_panels()
        box = ([-0.25, -0.25, -0.1], [0.25, 0.25, 0.4])
        im, lg = _render([{"name": "g", "V": V, "F": F, "mesh": M}], ["panels", "seams", "turned"], box, out, "kp_panels")
        cA, cB = dict(lg)["g:A"], dict(lg)["g:B"]
        rows += [("panel A colour", _close(_px(im, box, -0.1, 0.15), cA)),
                 ("panel B colour", _close(_px(im, box, 0.05, 0.15), cB)),
                 ("seam dark at x=0", _close(_px(im, box, 0.0, 0.15), dr.SEAM, 40)),
                 ("turned flap orange", _close(_px(im, box, 0.125, 0.15), dr.TURNED)),
                 ("fold line yellow somewhere on x=0.15",
                  any(_close(_px(im, box, 0.15, z), dr.FOLD, 40) for z in np.linspace(0.02, 0.28, 60)))]
        # 2. 10 % stretched strip: red only there
        Vs, Fs, us = strip_sheet()
        M2 = _mesh(Vs, Fs)
        M2["uv"] = us
        box = ([-0.05, -0.25, -0.05], [0.46, 0.25, 0.45])
        im, _ = _render([{"name": "g", "V": Vs, "F": Fs, "mesh": M2}], ["strain"], box, out, "kp_strain")
        red = [_close(_px(im, box, x, 0.2), dr.RED) for x in np.linspace(0.005, 0.405, 81)]
        xs = np.linspace(0.005, 0.405, 81)
        strip = (xs > 0.155) & (xs < 0.255)  # (the strip is 0.15..0.26 in 3D)
        rows += [("strip red", all(np.array(red)[strip])),
                 ("outside strip not red", not any(np.array(red)[(xs < 0.145) | (xs > 0.265)])),
                 ("outside strip white", _close(_px(im, box, 0.07, 0.2), "#ffffff") and _close(_px(im, box, 0.35, 0.2), "#ffffff"))]
        # 3. an inside-out piece next to a right one
        Vo, Fo, _ = grid(-0.2, -0.02, 0.0, 0.3, 10, 10, flip=True)
        Vr, Fr, _ = grid(0.02, 0.2, 0.0, 0.3, 10, 10)
        box = ([-0.25, -0.25, -0.1], [0.25, 0.25, 0.4])
        im, _ = _render([{"name": "out", "V": Vo, "F": Fo, "mesh": _mesh(Vo, Fo)},
                         {"name": "ok", "V": Vr, "F": Fr, "mesh": _mesh(Vr, Fr)}], ["backfaces"], box, out, "kp_back")
        rows += [("inside-out piece red", _close(_px(im, box, -0.1, 0.15), dr.RED)),
                 ("right piece not red (clay)", _close(_px(im, box, 0.1, 0.15), dr.CLAY))]
        # 4. a shirt face poking through a jacket
        (Vu, Fu), (Vc, Fc), body = poke_layers()
        Bf = grid(-0.15, 0.15, 0.05, 0.35, 10, 10, y=0.05)[1]
        box = ([-0.2, -0.2, 0.0], [0.2, 0.2, 0.4])
        im, _ = _render([{"name": "body", "V": body, "F": Bf},
                         {"name": "shirt", "V": Vu, "F": Fu, "mesh": _mesh(Vu, Fu)},
                         {"name": "jacket", "V": Vc, "F": Fc, "mesh": _mesh(Vc, Fc)}], ["layers"], box, out, "kp_layers")
        rows += [("magenta at the poke", _close(_px(im, box, 0.0, 0.2), dr.MAGENTA)),
                 ("jacket colour away from it", _close(_px(im, box, -0.08, 0.12), dr.LAYERS[1])),
                 ("no magenta away from it",
                  not any(_close(_px(im, box, x, z), dr.MAGENTA) for x in (-0.1, 0.1) for z in (0.1, 0.3)))]
    return rows


def test_render_cases():
    if not os.environ.get("HIFIPUSHIE_CAPPED"):
        print("skip render cases (not under bin/capped)")
        return
    out = sys.argv[1] if len(sys.argv) > 1 and __name__ == "__main__" else tempfile.mkdtemp()
    os.makedirs(out, exist_ok=True)
    rows = render_cases(out)
    for k, ok in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {k}")
    assert all(ok for _, ok in rows), [k for k, ok in rows if not ok]


if __name__ == "__main__":
    test_measures()
    print("measures ok")
    test_render_cases()
