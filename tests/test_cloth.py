"""Cloth checks that need no Blender: validation, coarse -> fine transfer, the clean-up pass, detail maps.
Run: uv run python tests/test_cloth.py"""
import numpy as np

from hifipushie import cloth, pattern


def _tablecloth(h):
    g = {"pieces": {"cloth": {"rect": [1.2, 0.8],
                              "wrap": {"to": "flat", "at": [0, 0, 0.8]}}}, "state": "draped"}
    B = cloth.pieces(g, {})
    return g, B, cloth.mesh(B, h)


def test_validate():
    ok = {"base": {"body": {"source": "makehuman"}}, "cloth": {"shirt": {"pattern": {"from": "simon"}}}}
    cloth.validate(ok)
    for bad, word in (({"pattern": {"from": "nope"}}, "pattern"), ({"pattern": {"from": "simon"}, "fabric": "x"}, "fabric"),
                      ({"pattern": {"from": "simon"}, "state": {"hang": {"hanger": {"kind": "plastic"}}}}, "hanger"),
                      ({"pattern": {"from": "simon"}, "state": {"hang": {"hanger": {}, "rack": []}}}, "hang"),
                      ({"pattern": {"from": "simon"}, "colour": "#fff"}, "unknown keys"),
                      ({"pattern": {"from": "simon", "ease": {"chestt": 0.1}}}, "ease")):
        try:
            cloth.validate({"base": ok["base"], "cloth": {"g": bad}})
        except cloth.ClothError as e:
            assert word in str(e), (word, str(e))
        else:
            raise AssertionError(f"not rejected: {bad}")
    # a tablecloth needs no body; a wrapped piece on a model without one is refused
    cloth.validate({"cloth": {"t": _tablecloth(0.05)[0]}})
    try:
        cloth.validate({"cloth": {"s": {"pattern": {"from": "simon"}}}})
    except cloth.ClothError as e:
        assert "base" in str(e)
    else:
        raise AssertionError("a shirt on a model without a body")


def test_transfer():
    _, B, Mc = _tablecloth(0.08)
    _, _, Mf = _tablecloth(0.03)
    # a curved sheet: z = f(u, v); the fine mesh carried from the coarse lies on the coarse triangles
    f = lambda uv: np.c_[uv, 0.1 * np.sin(3 * uv[:, 0]) + 0.05 * uv[:, 1] ** 2]
    Vf = cloth.transfer(Mc, f(Mc["uv"]), Mf)
    err = np.abs(Vf - f(Mf["uv"])).max()
    assert err < 0.01, err  # linear interpolation of a smooth surface at 8 cm
    assert np.allclose(Vf[:, :2], Mf["uv"], atol=1e-3)


def test_cleanup_keeps_folds():
    _, B, M = _tablecloth(0.01)
    uv = M["uv"]
    rng = np.random.default_rng(1)
    fold = 0.02 * np.sin(uv[:, 0] * 2 * np.pi / 0.25)  # 25 cm folds, 2 cm deep
    V = np.c_[uv, fold + 0.002 * rng.standard_normal(len(uv))]  # + 2 mm crinkle
    body = cloth.Body({"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "J": {}})
    X, info = cloth.cleanup(V, M, body, {"clear": 0})
    s0, s1 = cloth.shape_numbers(V, M), cloth.shape_numbers(X, M)
    assert s1["crinkle_mm"] < 0.6 * s0["crinkle_mm"], (s0, s1)
    inner = ~M["border"]
    assert np.abs(X[inner, 2] - fold[inner]).mean() < 0.0025  # the folds stay


def test_detail_maps():
    g, B, M = _tablecloth(0.05)
    uv, side = cloth.atlas_uv(M)
    dm = cloth.detail_maps(M, uv, side, g, texture=512)
    assert dm["normal"].shape == (512, 512, 3)
    assert dm["thread"].max() > 0.5  # a topstitch line along the hem
    assert dm["height"].max() > 0  # the turned hem stands proud
    # a pressed crease (a press fold past 180 deg) is a sharp ridge along its row, in the middle of the cloth
    k = np.where(M["piece"] == 0)[0]
    mid = k[np.abs(M["uv"][k, 0] - np.median(M["uv"][k, 0])) < 0.026]
    row = mid[np.argsort(M["uv"][mid, 1])]
    M2 = dict(M, folds=[{"piece": M["names"][0], "kind": "press", "angle": 205.0, "strength": 0.6, "rows": [row.tolist()]}])
    dm2 = cloth.detail_maps(M2, uv, side, dict(g, detail={"hem": 0, "topstitch": 0}), texture=512)
    dm0 = cloth.detail_maps(M, uv, side, dict(g, detail={"hem": 0, "topstitch": 0}), texture=512)
    assert (dm2["height"] - dm0["height"]).max() > 0.0004  # ~0.6 mm proud on the row


def test_marks_make_no_slivers():
    # a notch on the outline and two marks 1 mm apart: the outline vertex / one vertex, not sub-mm edges
    h = 0.01
    g = {"pieces": {"p": {"rect": [0.3, 0.2], "marks": {"notch": [0.0003, 0.0997], "a": [0.05, 0.0], "b": [0.051, 0.0]},
                          "wrap": {"to": "flat"}}}}
    M = cloth.mesh(cloth.pieces(g, {}), h)
    F, uv = M["F"], M["uv"]
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    assert np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1).min() > 0.3 * h
    assert M["border"][M["marks"]["p:notch"]] and M["marks"]["p:a"] == M["marks"]["p:b"]


def test_straight_arms():
    # a bent arm (a box of points along shoulder -> elbow -> wrist) straightened, then posed back exactly
    sh, el = np.array([0.2, 0, 1.4]), np.array([0.45, 0, 1.2])
    d1 = (el - sh) / np.linalg.norm(el - sh)
    wr = el + 0.25 * np.array([0.3, -0.7, -0.65]) / np.linalg.norm([0.3, -0.7, -0.65])
    t = np.linspace(0, 1, 40)[:, None]
    V = np.r_[sh + t * (el - sh), el + t * (wr - el)] + [0, 0, 0.0]
    body = cloth.Body({"V": V, "F": np.zeros((0, 3), int), "J": {"shoulder.L": sh, "elbow.L": el, "wrist.L": wr}})
    body._m = {"mm": {}, "at": {}}
    sb, pose = body.straight_arms()
    w = sb.J["wrist.L"]
    assert np.allclose((w - el) / np.linalg.norm(w - el), d1, atol=1e-6)  # in line with the upper arm
    far = np.r_[(V[:40] - el) @ ((d1 + (wr - el) / np.linalg.norm(wr - el)) / 2) < -0.045, np.zeros(40, bool)]
    assert far.sum() > 20 and np.allclose(sb.V[far], V[far])  # the upper arm (outside the band) doesn't move
    assert np.abs(pose(sb.V) - V).max() < 2e-3  # posed back (the blend band read from the bent side)


def test_piece_crossings():
    _, B, M = _tablecloth(0.1)
    X = np.c_[M["uv"], np.zeros(len(M["uv"]))]
    assert cloth._piece_crossings(X, M) == set()
    Y = X.copy()  # fold the cloth's right half down through its left half
    r = M["uv"][:, 0] > 0.1
    Y[r] = np.c_[0.1 - (M["uv"][r, 0] - 0.1), M["uv"][r, 1], 0.05 * np.sin(8 * M["uv"][r, 1])]
    assert ("cloth", "cloth") in cloth._piece_crossings(Y, M)


def _on_hanger_case():
    """A hanger (level arms at z 1, a hook up to 1.1) and a 'coat': an elliptic tube closed over the arms by a
    shoulder sheet with a neck hole round the hook."""
    from hifipushie import hanger
    c = np.array([0.0, 0.0, 1.0])
    segs = [(c, c + [sg * 0.18, 0, 0], (0.008, 0.011), (0.02, 0.013), f"arm.{s}") for s, sg in (("L", 1), ("R", -1))]
    rod = (c + [0, 0, 0.005], c + [0, 0, 0.1])
    segs.append((rod[0], rod[1], (0.003, 0.003), (0.003, 0.003), "hook"))
    h = {"segments": segs, "rail": [], "arms": {"L": (c, c + [0.18, 0, 0]), "R": (c, c - [0.18, 0, 0])}, "rod": rod}
    nt, rx, ry, top = 64, 0.2, 0.12, 1.0 + 0.011 + 0.004
    rings = [(1.0, z) for z in np.linspace(0.5, top, 26)] + [(s, top) for s in np.linspace(1.0, 0.45, 9)[1:]]
    th = np.linspace(0, 2 * np.pi, nt, endpoint=False)
    V = np.concatenate([np.c_[rx * s * np.cos(th), ry * s * np.sin(th), np.full(nt, z)] for s, z in rings])
    F = []
    for k in range(len(rings) - 1):
        for i in range(nt):
            a, b, cc, d = k * nt + i, k * nt + (i + 1) % nt, (k + 1) * nt + (i + 1) % nt, (k + 1) * nt + i
            F += [[a, b, cc], [a, cc, d]]
    M = {"F": np.asarray(F), "sew": np.zeros((0, 2), np.int64)}
    return hanger, h, V, M


def test_hanger_measures():
    hanger, h, V, M = _on_hanger_case()
    sup = hanger.support(V, M, h)
    on = hanger.on_hanger(V, M, h)
    ok, line = hanger.verdict(sup, on)
    assert on["ok"], on
    assert sup["share"].get("arm.L", 0) > 0.3 and sup["share"].get("arm.R", 0) > 0.3, sup
    assert ok and line.startswith("ON THE HANGER"), line
    # the same coat floating 30 cm in front of its hanger fails, and says why
    Vf = V + [0, -0.3, 0]
    ok, line = hanger.verdict(hanger.support(Vf, M, h), hanger.on_hanger(Vf, M, h))
    assert not ok and "NOT ON ITS HANGER" in line and "arm" in line, line
    # held by pins (the old hang): the pins carry it
    pins = np.where(V[:, 2] > 1.01)[0]
    ok, line = hanger.verdict(hanger.support(Vf, M, h, pins), None)
    assert not ok and "pins carry" in line, line


def test_zozo_backend_keys():
    """A ZOZO result is keyed on its runner (cloth_zozo.py), never on blender_cloth.py, and not on where it ran: a
    pod's result is found locally (the tooling card: a 27-min result lost to an edit of the Blender script)."""
    import os
    from hifipushie import cloth_job
    assert cloth_job.backend_of({"backend": "zozo"}) == "zozo"
    assert cloth_job.solver_of("zozo") == "zozo"
    k = cloth_job.solver_code("zozo")
    old = os.environ.get("HIFIPUSHIE_ZOZO_REMOTE")
    os.environ["HIFIPUSHIE_ZOZO_REMOTE"] = "true"
    try:
        assert cloth_job.solver_code(cloth_job.solver_of("zozo")) == k
    finally:
        os.environ.pop("HIFIPUSHIE_ZOZO_REMOTE") if old is None else os.environ.__setitem__("HIFIPUSHIE_ZOZO_REMOTE", old)
    import hashlib
    assert k == hashlib.sha1(cloth_job.ZOZO_RUNNER.read_bytes() + b"zozo").hexdigest()
    assert cloth.placement_of({"backend": "zozo"}) == "smooth" and cloth.placement_of({}) == "fitted"
    base = {"base": {"body": {"source": "makehuman"}}}
    cloth.validate({**base, "cloth": {"s": {"pattern": {"from": "simon"}, "backend": "zozo", "zozo": {"dt": 0.01}}}})
    for bad, word in (({"backend": "zozo", "zozo": 3}, "zozo"), ({"placement": "smooth"}, "smooth"),
                      ({"backend": "bullet"}, "backend")):
        try:
            cloth.validate({**base, "cloth": {"s": {"pattern": {"from": "simon"}, **bad}}})
        except cloth.ClothError as e:
            assert word in str(e), (word, str(e))
        else:
            raise AssertionError(f"not rejected: {bad}")


def test_coincident_stitches_are_parted_not_dropped():
    """Two panels drafted edge to edge (a centre back seam): the stitches' ends start on one point. ZOZO has no
    direction for them; dropped, nothing sews the seam. The runner steps each end back into its own cloth."""
    from hifipushie.cloth_zozo import part_stitches
    h = 0.02
    gx, gy = np.meshgrid(np.arange(4) * h, np.arange(5) * h, indexing="ij")
    A = np.c_[gx.ravel() - 3 * h, gy.ravel(), np.zeros(gx.size)]  # x from -3h to 0
    B = np.c_[gx.ravel(), gy.ravel(), np.zeros(gx.size)]  # x from 0 to 3h
    quad = [(i * 5 + j, (i + 1) * 5 + j, (i + 1) * 5 + j + 1, i * 5 + j + 1) for i in range(3) for j in range(4)]
    Fa = np.array([t for q in quad for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))])
    X, F = np.r_[A, B], np.r_[Fa, Fa + 20]
    sew = np.c_[15 + np.arange(5), np.arange(5)] + [0, 20]  # A's x = 0 column to B's
    X2, sew2, info = part_stitches(X, F, sew)
    d = np.linalg.norm(X2[sew2[:, 0]] - X2[sew2[:, 1]], axis=1)
    assert len(sew2) == 5 and info["coincident"] == 5 and d.min() > 0.0012 and d.max() < 0.0025, (d, info)
    assert (X2[15:20, 0] < 0).all() and (X2[20:25, 0] > 0).all() and np.abs(X2 - X).max() < 0.0011
    # one side held as made: only the other steps back; both held: dropped
    held = np.zeros(len(X), bool)
    held[15:20] = True
    X3, sew3, _ = part_stitches(X, F, sew, held)
    assert np.allclose(X3[15:20], X[15:20]) and len(sew3) == 5
    assert np.linalg.norm(X3[sew3[:, 0]] - X3[sew3[:, 1]], axis=1).min() > 0.0008
    held[20:25] = True
    assert len(part_stitches(X, F, sew, held)[1]) == 0
    # two layers on each other (a facing on its front): they part along the normal
    X4, sew4, info4 = part_stitches(np.r_[A, A], F, np.c_[np.arange(20), 20 + np.arange(20)])
    d4 = np.linalg.norm(X4[sew4[:, 0]] - X4[sew4[:, 1]], axis=1)
    assert len(sew4) == 20 and d4.min() > 0.0008 and info4["by_normal"] == 20, (d4.min(), info4)
    # stitches that start apart are left alone
    X5, sew5, info5 = part_stitches(X + np.r_[np.zeros((20, 3)), np.tile([0.01, 0, 0], (20, 1))], F, sew)
    assert info5["coincident"] == 0 and len(sew5) == 5 and np.allclose(X5[:20], X[:20])


def test_weld_beside_a_layer_stays_welded():
    # A seam's draped side lies a contact gap under a made layer (a collar's fall on the back neck); its partner, the
    # made piece's edge, is on the layer's other side. The weld carries the draped edge through the layer; the answer
    # used to be to send those places (two rings wide) back to the sim's surface: the seam stayed as open as the sim
    # left it. Now the draped vertices lose only the part of their move across the layer.
    g = {"pieces": {"a": {"rect": [0.2, 0.1], "wrap": {"to": "flat", "at": [0, 0, 1.0]}},
                    "b": {"rect": [0.2, 0.1], "wrap": {"to": "flat", "at": [0, 0, 1.0]}},
                    "c": {"rect": [0.2, 0.1], "wrap": {"to": "flat", "at": [0, 0, 1.0]}}},
         "seams": [["a:nw>n>ne", "b:sw>s>se"]]}
    Bp = cloth.pieces(g, {})
    M = cloth.mesh(Bp, 0.02)
    uv, pid = M["uv"], M["piece"]
    V = np.c_[uv, np.zeros(len(uv))]
    ia, ib, ic = (pid == M["names"].index(n) for n in "abc")
    V[ia, 1] -= 0.05                       # a: y -0.1 .. 0, z 0 (draped)
    V[ib, 1] += 0.053; V[ib, 2] = 0.0015   # b: y 0.003 .. 0.103 (the seam 3 mm open in the plane), 1.5 mm up (made)
    V[ic, 2] = 0.0008                      # c: a made layer between the two, over the seam
    stiff = (ib | ic).astype(float)
    sw = M["sew"]
    gap = lambda X: np.linalg.norm(X[sw[:, 0]] - X[sw[:, 1]], axis=1)
    assert gap(V).min() > 0.003 and not cloth._crossing_verts(V, M).any()
    W, _ = cloth.cleanup(V, M, None, {"smooth": 0}, stiff=stiff)
    assert gap(W).max() < 1e-9 and cloth._crossing_verts(W, M).any()  # welded, through the layer
    C, left = cloth._weld_clear(W, V, M, stiff)
    assert left == 0 and not cloth._crossing_verts(C, M).any()
    d = C[sw[:, 0]] - C[sw[:, 1]]
    assert np.abs(d[:, :2]).max() < 2e-4, np.abs(d[:, :2]).max()  # closed in the cloth's plane
    assert np.abs(d[:, 2]).max() < 0.0016                          # what is left: the layer between them
    assert np.allclose(C[ib | ic], V[ib | ic], atol=2e-4)          # the made pieces stayed


def _grid(nx=12, ny=20, h=0.02):
    u, v = np.meshgrid(np.arange(nx) * h, np.arange(ny) * h)
    uv = np.c_[u.ravel(), v.ravel()]
    F = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            F += [[a, a + 1, a + nx + 1], [a, a + nx + 1, a + nx]]
    return uv, np.array(F)


def test_relax_strain_takes_out_shear():
    # a sheet laid with its columns leaning 0.2 against its rows: every edge within 2%, the triangles ~10% along the
    # diagonal; the relaxation brings every triangle under the limit (compression is left alone)
    from hifipushie import cloth_zozo
    uv, F = _grid()
    V = np.c_[uv[:, 0] + 0.2 * uv[:, 1], uv[:, 1], np.zeros(len(uv))]
    M = {"uv": uv, "F": F}
    s0 = cloth_zozo._start_stretch(np.c_[uv, np.zeros(len(uv))], V, F)
    assert s0.max() > 1.09
    R = cloth._relax_strain(V, M, np.ones(len(uv), bool), 0.03, iters=400)
    s1 = cloth_zozo._start_stretch(np.c_[uv, np.zeros(len(uv))], R, F)
    assert s1.max() < 1.035, s1.max()


def test_a_stopped_runs_solver_is_cleared():
    # a ZOZO solver whose cloth_zozo.py runner died (a stopped session) is a stray and is stopped; one whose runner is
    # alive, or one that isn't ours (no hp_job_ session), is left alone
    import os, subprocess, tempfile, time
    from pathlib import Path
    from hifipushie import cloth_job
    d = Path(tempfile.mkdtemp())
    solver = d / "ppf-contact-solver"
    solver.write_text("#!/bin/sh\nsleep 60\n")
    solver.chmod(0o755)
    mark = f"hp_job_t{os.getpid()}_"
    orphan_path = str(d / f"{mark}a_sim" / "session")
    live_path = str(d / f"{mark}b_sim" / "session")
    other = str(d / "someone_else" / "session")
    # orphan: started in the background by a shell that exits at once (reparented, no runner above it)
    subprocess.run(["sh", "-c", f"'{solver}' --path '{orphan_path}' >/dev/null 2>&1 &"], check=True)
    subprocess.run(["sh", "-c", f"'{solver}' --path '{other}' >/dev/null 2>&1 &"], check=True)
    # held: its parent's command line runs cloth_zozo.py and stays alive
    held = subprocess.Popen(["sh", "-c", f"'{solver}' --path '{live_path}'; true", "cloth_zozo.py"])
    try:
        time.sleep(0.5)
        strays = cloth_job.stray_solvers(mark)
        assert [s["session"] for s in strays] == [orphan_path], strays
        gone = cloth_job.clear_strays(log=lambda *_: None, mark=mark, wait=3)
        assert len(gone) == 1 and cloth_job._proc(gone[0]["pid"]) is None
        assert cloth_job.stray_solvers(mark) == []  # the held one stays
        assert any(live_path in " ".join(cloth_job._proc(int(p.name))[1]) for p in Path("/proc").iterdir()
                   if p.name.isdigit() and cloth_job._proc(int(p.name)))
    finally:
        held.kill()
        subprocess.run(["pkill", "-f", str(d)], check=False)
    try:  # ZOZO checks only its own run's solvers: the queue's GPU claim is the exclusion (needs the release)
        _, env = cloth_job.zozo_command(d)
    except FileNotFoundError:
        env = None
    if env is not None:
        assert env["PPF_SOLVER_SCAN_DESCENDANTS"] == "1"


def test_clay_looks_are_matte():
    # dark wool read as leather under the workbench's specular highlight (tr_11): cloth clay looks switch it off
    # unless a job asks, and textured looks take each object's roughness (Blender isn't run here: read the source)
    from pathlib import Path
    src = (Path(cloth.__file__).parent / "blender_cloth.py").read_text()
    r = src[src.index("def render(job, d):"):src.index("def _render_textured")]
    t = src[src.index("def _render_textured"):]
    assert 'sh.show_specular_highlight = bool(job.get("specular", False))' in r
    assert 'o.get("roughness"' in t


def _ball(r=0.1, n=40):
    th, ph = np.meshgrid(np.linspace(0.05, np.pi - 0.05, n), np.linspace(0, 2 * np.pi, 2 * n, endpoint=False))
    V = np.c_[(r * np.sin(th) * np.cos(ph)).ravel(), (r * np.sin(th) * np.sin(ph)).ravel(), (r * np.cos(th)).ravel()]
    from scipy.spatial import ConvexHull
    T = ConvexHull(V).simplices
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    inward = np.sum(n * V[T].mean(1), 1) < 0
    T[inward] = T[inward][:, [0, 2, 1]]  # wound outward
    return V, T


def test_cleanup_clears_faces_off_a_convex_body():
    # a coarse triangle over a ball, its corners 3 mm off it: its middle dips inside (the specks on tr_11's seat)
    from hifipushie import closures
    V, T = _ball()
    body = cloth.Body({"V": V, "F": T, "J": {}})
    body._m = {"mm": {}, "at": {}}
    d = np.array([[1.0, 0, 0], [0.9, 0.44, 0], [0.9, 0, 0.44]])
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    X = d * 0.103
    M = {"F": np.array([[0, 1, 2]]), "uv": X[:, :2].copy(), "piece": np.zeros(3, int), "names": ["p"],
         "sew": np.zeros((0, 2), int), "stitch": np.zeros((0, 2), int), "folds": []}
    c = X.mean(0, keepdims=True)
    q, _, _ = closures._closest_on(c, V, T)
    assert np.linalg.norm(c) < 0.1 + 0.0005  # the middle starts at (or in) the ball
    W, _ = cloth.cleanup(X, M, body, {"smooth": 0, "weld": False, "clear": 0.003, "seams": False, "press": False})
    cw = W.mean(0)
    q, _, _ = closures._closest_on(cw[None], V, T)
    assert np.linalg.norm(cw - q[0]) > 0.0013 and np.linalg.norm(cw) > 0.1, np.linalg.norm(cw - q[0])


def test_collider_takes_worn_parts():
    # garment key "collide": the model's parts join the collider (carried with the body like an under garment)
    V, T = _ball()
    W, TW = _ball(0.05)
    W = W + [0, 0, -0.12]
    body = cloth.Body({"V": V, "F": T, "J": {}, "worn": {"V": W, "F": TW, "key": "k"}})
    body._m = {"mm": {}, "at": {}}
    out = cloth._collider(body, None, False)
    assert len(out["bodyV"]) == len(V) + len(W) and out["bodyT"].max() == len(V) + len(W) - 1
    assert np.allclose(out["bodyV"][len(V):], W)


def test_collar_from_the_neck():
    # garment_kb kinds.shirt.collar through Simon's options: the stand as tall as the neck allows (less 13 mm under
    # the jaw) within 20-35 mm, the fall 12 mm deeper at centre back
    tbl = {"kind": "shirt", "collar_rule": "simon"}
    o = {"collarEase": 0.115, "collarGap": 0}
    short = cloth.collar_options(tbl, o, {"neck": 400.0, "neckHeight": 29.0})
    tall = cloth.collar_options(tbl, o, {"neck": 400.0, "neckHeight": 60.0})
    assert np.isclose(short["collarStandWidth"] * 400, 20.0, atol=0.05)  # 16 mm of room: the 20 mm floor
    assert np.isclose(tall["collarStandWidth"] * 400, 35.0, atol=0.05)   # capped at 35
    for r, s in ((short, 20.0), (tall, 35.0)):
        assert np.isclose(s * r["collarWidth"] * 1.03, s + 12.0, atol=0.1)  # fall = stand + 12 (collarRoll 3%)
        assert 0.0 < r["collarBend"] < 0.1
    assert cloth.collar_options({"kind": "shirt"}, o, {"neck": 400.0, "neckHeight": 29.0}) == {}  # no rule: as drafted


def test_leg_tube_follows_the_leg():
    # two splayed tapered legs; a front and a back trouser piece (pattern x from the centre line, the side seam at
    # +x, y down from the waist): under the crotch both lie round the leg off it by at least LEG_CLEAR, the side
    # seams and inseams a few mm apart, the front's crease on the leg's front
    zs = np.linspace(0.08, 0.86, 40)
    n = 32
    V, T = [], []
    for sgn in (1.0, -1.0):
        o = len(V)
        for z in zs:
            r = 0.05 + 0.04 * (z - 0.08) / 0.78
            cx = sgn * (0.10 + 0.05 * (0.86 - z) / 0.78)
            for a in np.linspace(0, 2 * np.pi, n, endpoint=False):
                V.append([cx + r * np.cos(a), 1.2 * r * np.sin(a), z])
        for j in range(len(zs) - 1):
            for i in range(n):
                a_, b_ = o + j * n + i, o + j * n + (i + 1) % n
                T += [[a_, b_, b_ + n], [a_, b_ + n, a_ + n]]
    V, T = np.array(V), np.array(T)
    J = {"knee.L": np.array([0.13, 0.0, 0.48]), "ankle.L": np.array([0.15, 0.0, 0.08])}
    body = cloth.Body({"V": V, "F": T, "J": J})
    body._m = {"mm": {}, "at": {"crotch_z": 0.9, "waist_z": 1.1}}
    # a front 30 cm wide narrowing to 22, a back 36 narrowing to 24 (side seams at +x), 1 m long under the waist
    Pf = np.array([[-0.08, 0.0], [0.22, 0.0], [0.19, -1.0], [-0.03, -1.0]])
    Pb = np.array([[-0.13, 0.0], [0.23, 0.0], [0.19, -1.0], [-0.05, -1.0]])
    pcs = {"front.L": {"P": Pf, "wrap": {"to": "leg.L", "side": "front"}},
           "back.L": {"P": Pb, "wrap": {"to": "leg.L", "side": "back"}}}
    names = list(pcs)
    cache = {}
    ys = np.linspace(-0.45, -0.95, 11)
    out = {}
    for nm, P in (("front.L", Pf), ("back.L", Pb)):
        xs = [cloth._piece_xs_at(P, y) for y in ys]
        U = np.array([[x[k], y] for x, y in zip(xs, ys) for k in (np.argmin(x), np.argmax(x))])
        X, t = cloth._leg_tube(body, pcs, names, "leg.L", nm, U, 1.1, 0.012, cache)
        assert (t == 1).all()
        out[nm] = X.reshape(len(ys), 2, 3)
    inseam = np.linalg.norm(out["front.L"][:, 0] - out["back.L"][:, 0], axis=1)
    side = np.linalg.norm(out["front.L"][:, 1] - out["back.L"][:, 1], axis=1)
    assert inseam.max() < 0.02 and side.max() < 0.02, (inseam, side)
    allp = np.concatenate([out["front.L"].reshape(-1, 3), out["back.L"].reshape(-1, 3)])
    assert body.clearance(allp).min() > cloth.LEG_CLEAR - 0.002
    assert (out["front.L"][:, 1, 0] > out["front.L"][:, 0, 0]).all()  # the side seam outside, the inseam inside


def test_cleaned_seam_is_a_smooth_line():
    # The pale zigzag down a jacket's centre back (su_25 / su_31): the sim leaves a sewn seam puckered (its vertices
    # alternately sunk and proud); the clean-up must leave it a smooth line once welded, and the clay look must draw
    # it as ONE surface (welded_faces: scratch renders that drew the raw faces showed every closed, smooth seam as a
    # pale sawtooth).
    g = {"pieces": {"a": {"rect": [0.4, 0.1], "wrap": {"to": "flat", "at": [0, 0, 1.0]}},
                    "b": {"rect": [0.4, 0.1], "wrap": {"to": "flat", "at": [0, 0, 1.0]}}},
         "seams": [["a:nw>n>ne", "b:sw>s>se"]]}
    Bp = cloth.pieces(g, {})
    M = cloth.mesh(Bp, 0.02)
    uv, pid = M["uv"], M["piece"]
    V = np.c_[uv, np.zeros(len(uv))]
    ia, ib = (pid == M["names"].index(n) for n in "ab")
    V[ia, 1] -= 0.05
    V[ib, 1] += 0.051  # 1 mm open
    sw = M["sew"]
    o = np.argsort(V[sw[:, 0], 0])
    z = 0.004 * (-1.0) ** np.arange(len(o))  # 4 mm pucker, alternating
    V[sw[o, 0], 2] = z
    V[sw[o, 1], 2] = z
    W, _ = cloth.cleanup(V, M, None, {"smooth": 0})
    assert np.linalg.norm(W[sw[:, 0]] - W[sw[:, 1]], axis=1).max() < 1e-9  # welded
    line = W[sw[o, 0]]
    sm = line.copy()
    for _ in range(8):
        sm[1:-1] = 0.25 * sm[:-2] + 0.5 * sm[1:-1] + 0.25 * sm[2:]
    zig = np.linalg.norm(line - sm, axis=1)[1:-1].max()
    assert zig < 0.0015, zig  # (4 mm before)
    used = np.unique(cloth.welded_faces(M, W))
    assert not (np.isin(sw[:, 0], used) & np.isin(sw[:, 1], used)).any()  # one row of vertices on the seam


def test_clearing_a_hollow_stays_local():
    # cloth across the hollow where two balls meet (the crotch between the thighs): pushing its vertices along the body's
    # normal doesn't clear its faces, and a gap grown round after round sent tr_13's fork tips 35-106 mm across the body
    # (a 10x stretched start). The fine settle's clearing caps the growth (CLEAR_GROW)
    V1, T1 = _ball()
    V, T = np.r_[V1, V1 + [0.21, 0, 0]], np.r_[T1, T1 + len(V1)]
    body = cloth.Body({"V": V, "F": T, "J": {}})
    body._m = {"mm": {}, "at": {}}
    X = np.array([[x, 0.0, z] for x in np.linspace(0.06, 0.15, 10) for z in (-0.02, 0.02)])
    X[:, 1] = -np.sqrt(np.maximum(0.01 - np.minimum(np.abs(X[:, 0]), np.abs(X[:, 0] - 0.21)) ** 2 - X[:, 2] ** 2, 0)) - 0.002
    F = np.array([f for i in range(9) for f in ([2 * i, 2 * i + 2, 2 * i + 1], [2 * i + 1, 2 * i + 2, 2 * i + 3])])
    free = np.ones(len(X), bool)
    far = np.linalg.norm(cloth._clear_of_body(X, F, free, body, 0.0042, 0.0034) - X, axis=1).max()
    near = np.linalg.norm(cloth._clear_of_body(X, F, free, body, 0.0042, 0.0034, cloth.CLEAR_GROW) - X, axis=1).max()
    assert far > 0.03 and near < 0.015, (far, near)


def test_fine_start_check_fails_loudly():
    # the fine settle's start is checked before the GPU is spent: draped triangles the solver moves, stretched past
    # 1 + FINE_START_MAX from the flat pattern, are named (a carried or made triangle isn't the solver's to start)
    uv = np.array([[0, 0], [0.01, 0], [0, 0.01], [0.01, 0.01]], float)
    M = {"uv": uv, "F": np.array([[0, 1, 2], [1, 3, 2]]), "piece": np.zeros(4, int), "names": ["back.L"]}
    X = np.c_[uv, np.zeros(4)]
    plan = {"start": X.copy(), "idx": np.zeros(0, int), "rest_idx": np.zeros(0, int)}
    assert cloth.fine_start_check(M, plan) == ""
    plan["start"][3] = [0.05, 0.05, 0]  # the second triangle 5x
    msg = cloth.fine_start_check(M, plan)
    assert "1 triangles" in msg and "back.L" in msg, msg
    assert cloth.fine_start_check(M, dict(plan, idx=np.array([1, 2, 3]))) == ""  # all carried
    assert cloth.fine_start_check(M, dict(plan, rest_idx=np.array([3]))) == ""  # made


def test_folds_in_geometry_lift_off_the_body_whatever_the_winding():
    # cloth_detail.displace moves vertices out along the garment's OUTSIDE (oriented_faces), not the pattern's winding:
    # on su_garrett's trousers the inward-wound back.L had its folds pushed into the thigh (111 faces inside the body)
    from hifipushie import cloth_detail
    V, T = _ball()
    body = cloth.Body({"V": V, "F": T, "J": {}})
    body._m = {"mm": {}, "at": {}}
    th = np.linspace(-0.6, 0.6, 9)
    zz = np.linspace(-0.04, 0.04, 5)
    X = np.array([[0.105 * np.cos(t), 0.105 * np.sin(t), z] for z in zz for t in th])
    uv = np.array([[0.105 * t, z] for z in zz for t in th])
    F = []
    for j in range(4):
        for i in range(8):
            a, b, c, d = j * 9 + i, j * 9 + i + 1, (j + 1) * 9 + i, (j + 1) * 9 + i + 1
            F += [[a, c, b], [b, c, d]]  # wound INTO the ball
    F = np.array(F)
    M = {"F": F, "uv": uv, "piece": np.zeros(len(X), int), "names": ["p"], "sew": np.zeros((0, 2), int),
         "border": np.zeros(len(X), bool)}
    orig = cloth_detail.height_at
    cloth_detail.height_at = lambda *a, **k: np.full(len(X), 0.004)
    try:
        W, _ = cloth_detail.displace(M, X, {}, body=body)
    finally:
        cloth_detail.height_at = orig
    r0, r1 = np.linalg.norm(X, axis=1), np.linalg.norm(W, axis=1)
    assert np.all(r1 > r0 + 0.003), (r1 - r0).min()


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
