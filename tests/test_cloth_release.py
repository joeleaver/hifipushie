"""cloth_release: worn open = the closed fit + one short sim that lets the closure go (fit round 16, Joe 2026-10-20).

KAT: an open-front "jacket" on a torso: a chest (cylinder R_CHEST, z 1.40-1.50, capped) over an oblique cone to the
waist (the chest circle scaled 0.7 about an apex behind, so the back is near plumb and the front recedes 100 mm). The
garment: a disc on the cap, a band round the chest, the cone (developed exactly from its apex) LAYER off the body, its
two fronts overlapping at CF (the sheet runs past a full turn as a spiral); the band's overlap is stitched shut (the
chest), the cone's buttoned every 4th row: the closed fit draws the fronts back onto the receding waist.
Released, the over front's edge must LEAVE the cloth it was buttoned to at the hem (>= 15 mm and >= 10x the buttoned
control's), the sim must have settled in the frames given (still moving < 0.1 mm over the last 6 frames), and the
chest must sit where the control's sits (p90 difference < 2 mm: both sink ~6 mm as the fit's seams close, the same).
Measured 2026-10-20 (local ZOZO, ROCm, 37 s for both): released 21.3 mm, control 1.0, still 0.02 mm. A plain cylinder
opened 10 mm, a symmetric cone 15 mm and still moving: the opening is the overhang of the chest over a receding
front under gravity, limited by the cone's own isometry (a cut-in front can't hang plumb), which is the physics the
form lacks. The solver part runs only with HP_RUN_ZOZO=1."""
import os
import types

import numpy as np
import pytest

from hifipushie import cloth_release as cr

R_CHEST, LAYER, LAP = 0.17, 0.006, 0.006
Z_CAP, Z_CHEST, Z_HEM = 1.50, 1.40, 1.10
S_HEM, Y_HEM = 0.7, 0.05  # the waist: the chest circle scaled 0.7 and centred 50 mm back (the front recedes 0.10)
APEX = np.array([0.0, Y_HEM / (1 - S_HEM), (Z_HEM - S_HEM * Z_CHEST) / (1 - S_HEM)])  # the oblique cone's apex
NC, NB, NW = 48, 6, 16  # columns round; rows in the band, in the cone


def _scale(z):
    """The cone's scale about its apex at height z (1 at the chest, S_HEM at the hem)."""
    return (z - APEX[2]) / (Z_CHEST - APEX[2])


def _ring(z, r, th):
    """Points at height z of the surface whose chest circle has radius r (cylinder above the chest, the oblique cone
    to the hem, a cylinder below)."""
    P = np.c_[r * np.cos(th), r * np.sin(th), np.full(len(th), Z_CHEST)]
    zc = min(max(z, Z_HEM), Z_CHEST)
    Q = APEX + (P - APEX) * _scale(zc)
    Q[:, 2] = z
    return Q


def _torso(n=64):
    # (the cap's edge rounded over 10 mm: at a sharp 90 deg edge the body's signed distance (pattern_form._Surface)
    # read the disc and band as 13 mm INSIDE, so cloth_release.clear_body pushed them 4 mm and the start stretched
    # 18 %: the solver's CCD failed at t = 0 from fit round 16 step 2 on, found in round 20)
    zs = np.r_[np.linspace(0.85, Z_HEM, 6)[:-1], np.linspace(Z_HEM, Z_CHEST, 16)[:-1],
               np.linspace(Z_CHEST, Z_CAP - 0.01, 4)[:-1], Z_CAP - 0.01 + 0.01 * np.sin(np.linspace(0, np.pi / 2, 5))]
    rr = np.r_[np.full(len(zs) - 5, R_CHEST), R_CHEST - 0.01 + 0.01 * np.cos(np.linspace(0, np.pi / 2, 5))]
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = [_ring(z, r_, th) for z, r_ in zip(zs, rr)]
    m = len(zs)
    V = np.concatenate(V + [np.array([[0, Y_HEM, zs[0]], [0, 0, Z_CAP]])])
    T = []
    for j in range(m - 1):
        for i in range(n):
            a, b, c, d = j * n + i, j * n + (i + 1) % n, (j + 1) * n + i, (j + 1) * n + (i + 1) % n
            T += [(a, b, d), (a, d, c)]
    bot, top = m * n, m * n + 1
    for i in range(n):
        T += [(bot, (i + 1) % n, i), (top, (m - 1) * n + i, (m - 1) * n + (i + 1) % n)]
    return types.SimpleNamespace(V=V, T=np.asarray(T, np.int64), at={})


def _case(state="open"):
    """(res, X, (band rows, button rows)): the placed pattern (disc, band, cone) and its closed fit."""
    th0, dth, ov = -np.pi / 2, 2 * np.pi / NC, 2  # CF faces -Y; `ov` columns past CF either way
    nc = NC + 2 * ov + 1
    t = th0 - ov * dth + dth * np.arange(nc)
    lap = LAP * (t - t[0]) / (t[-1] - t[0])  # the spiral: the over end LAP further out
    X, uv, pid, F = [], [], [], []
    grids = {}

    def grid(name, k, zs, rad, flat):
        base = len(X)
        for z in zs:
            for c in range(nc):
                r = rad(z) + lap[c]
                X.append((r * np.cos(t[c]), r * np.sin(t[c]), z))
                uv.append(flat(z, c))
                pid.append(k)
        for j in range(len(zs) - 1):
            for c in range(nc - 1):
                a, b, cc, d = (base + j * nc + c, base + j * nc + c + 1, base + (j + 1) * nc + c,
                               base + (j + 1) * nc + c + 1)
                F.extend([(a, b, d), (a, d, cc)])
        grids[name] = (base, zs)

    rb = R_CHEST + LAYER
    zb = np.linspace(Z_CHEST, Z_CAP + LAYER, NB)
    grid("band", 1, zb, lambda z: rb, lambda z, c: (1.0 + rb * (t[c] - t[0]), z - Z_CHEST))
    # the oblique cone, developed exactly: each point at rho = |x - apex|, at the angle its ruling makes round the
    # apex, summed along the chest ring (the over end's lap ignored in the pattern: under 4 % stretch)
    r_top = R_CHEST + LAYER
    Pc = _ring(Z_CHEST, r_top, t)
    u_ = (Pc - APEX) / np.linalg.norm(Pc - APEX, axis=1)[:, None]
    phi = np.r_[0.0, np.cumsum(np.arccos(np.clip(np.sum(u_[1:] * u_[:-1], 1), -1, 1)))]
    zw = np.linspace(Z_HEM, Z_CHEST, NW)
    base_w = len(X)
    for z in zw:
        Q = _ring(z, r_top, t)
        Q[:, :2] += (lap[:, None] * np.c_[np.cos(t), np.sin(t)]) * _scale(z)
        rho = np.linalg.norm(_ring(z, r_top, t) - APEX, axis=1)
        for c in range(nc):
            X.append(tuple(Q[c]))
            uv.append((rho[c] * np.cos(phi[c]), rho[c] * np.sin(phi[c])))
            pid.append(2)
    for j in range(NW - 1):
        for c in range(nc - 1):
            a, b, cc, d = (base_w + j * nc + c, base_w + j * nc + c + 1, base_w + (j + 1) * nc + c,
                           base_w + (j + 1) * nc + c + 1)
            F.extend([(a, b, d), (a, d, cc)])
    grids["cone"] = (base_w, zw)
    # the disc on the cap: rings at the columns' angles, a centre vertex; its own uv island
    rings, dv0 = 7, len(X)
    for k in range(1, rings + 1):
        rr = rb * k / rings
        for i in range(NC):
            a_ = th0 + i * dth
            X.append((rr * np.cos(a_), rr * np.sin(a_), Z_CAP + LAYER))
            uv.append((3.0 + rr * np.cos(a_), rr * np.sin(a_)))
            pid.append(0)
    X.append((0, 0, Z_CAP + LAYER))
    uv.append((3.0, 0.0))
    pid.append(0)
    ctr = len(X) - 1
    ring = lambda k, i: dv0 + (k - 1) * NC + i % NC  # noqa: E731
    for i in range(NC):
        F.append((ctr, ring(1, i), ring(1, i + 1)))
        for k in range(1, rings):
            a, b, c, d = ring(k, i), ring(k, i + 1), ring(k + 1, i), ring(k + 1, i + 1)
            F.extend([(a, c, d), (a, d, b)])
    vb = lambda j, c: grids["band"][0] + j * nc + c  # noqa: E731
    vw = lambda j, c: grids["cone"][0] + j * nc + c  # noqa: E731
    sew = [(vb(NB - 1, c), ring(rings, c - ov)) for c in range(nc)]  # band top to the disc rim
    sew += [(vb(0, c), vw(NW - 1, c)) for c in range(nc)]  # band to cone at the chest line
    # the fronts' overlap: the over end (last column) on column 2 ov, the under end (column 0) on column NC
    pairs = lambda v, j: [[v(j, nc - 1), v(j, 2 * ov)], [v(j, 0), v(j, NC)]]  # noqa: E731
    stitch = [p for j in range(1, NB - 1) for p in pairs(vb, j)]
    btn = list(range(0, NW - 1, 4))
    M = {"uv": np.asarray(uv, float), "F": np.asarray(F, np.int64), "piece": np.asarray(pid, np.int64),
         "names": ["top", "band", "cone"], "made": [], "sew": np.asarray(sew, np.int64),
         "stitch": np.asarray(stitch, np.int64), "folds": [],
         "closures": [{"name": "front", "state": state, "v": [p for j in btn for p in pairs(vw, j)]}],
         "nc": nc, "hem_over": vw(0, nc - 1), "hem_mate": vw(0, 2 * ov),
         "points": {"cone:overTop": vw(NW - 1, nc - 1), "cone:overHem": vw(0, nc - 1),
                    "cone:underTop": vw(NW - 1, 0), "cone:underHem": vw(0, 0)}}
    res = {"mesh": M, "pieces": {"interfaced": [], "pieces": {}}, "fabric": {"name": "wool_coating"},
           "body": _torso(), "gate_keys": {"pattern": None, "body": None, "name": "kat:open_front"}}
    return res, np.asarray(X, float), btn


def test_release_sews_no_closure_and_keeps_the_rest():
    res, X, btn = _case("closed")
    n_st = len(res["mesh"]["stitch"])
    cfg, arr, info = cr.job(res, X, release=("front",))
    assert info["released"] == ["front"] and len(arr["stitch"]) == n_st
    cfg2, arr2, info2 = cr.job(res, X, release=())
    assert len(arr2["stitch"]) == n_st + 2 * len(btn) and info2["released"] == []
    assert cfg["zozo"]["rest"] == "flat" and cfg["frames"] == cr.SETTLE_FRAMES
    assert len(arr["sew"]) == len(res["mesh"]["sew"])  # every seam stays sewn
    # the start is the fit, the rest the flat pattern: the cone's development is isometric to its placement
    e = np.r_[arr["F"][:, [0, 1]], arr["F"][:, [1, 2]]]
    e = e[(res["mesh"]["piece"][e] == 2).all(1)]
    l3 = np.linalg.norm(X[e[:, 0]] - X[e[:, 1]], axis=1)
    l2 = np.linalg.norm(arr["uv"][e[:, 0]] - arr["uv"][e[:, 1]], axis=1)
    assert np.percentile(np.abs(l3 / l2 - 1), 99) < 0.045


@pytest.mark.skipif(os.environ.get("HP_RUN_ZOZO") != "1", reason="runs the ZOZO solver locally (HP_RUN_ZOZO=1)")
def test_released_front_swings_open_and_the_chest_stays(tmp_path):
    out = {}
    for tag, state, rel in (("open", "open", ("front",)), ("buttoned", "closed", ())):
        res, X, _ = _case(state)
        M = res["mesh"]
        cfg, arr, _ = cr.job(res, X, release=rel)
        jd = cr.write(tmp_path / tag / "sim", cfg, arr, M["names"], res["gate_keys"])
        d, _ = cr.run(jd, progress=lambda *_: None, log=lambda *_: None)
        Y = np.asarray(d["V"], float)
        out[tag] = {"Y": Y, "M": M, "X": X,
                    "hem_gap": float(np.linalg.norm(Y[M["hem_over"]] - Y[M["hem_mate"]]) * 1000),
                    "still": float(np.abs(Y - d["Vprev"]).max() * 1000)}
    chest = np.where(out["open"]["M"]["piece"] == 1)[0]
    diff = np.linalg.norm(out["open"]["Y"][chest] - out["buttoned"]["Y"][chest], axis=1) * 1000
    out = {k: {kk: vv for kk, vv in v.items() if kk not in ("Y", "M", "X")} for k, v in out.items()}
    out["chest_vs_control_p90"] = float(np.percentile(diff, 90))
    print(out)
    assert out["open"]["hem_gap"] >= 15.0 and out["open"]["hem_gap"] >= 10 * out["buttoned"]["hem_gap"], out
    assert out["open"]["still"] < 0.1, out  # settled in SETTLE_FRAMES + SELF_FRAMES
    assert out["chest_vs_control_p90"] < 2.0, out  # the chest stays


def test_fit_points_worn_open_designs_to_the_release():
    from hifipushie import next_steps
    t = next_steps.after_fit("m", "jacket", 3.0, 0, True, worn_open=True)
    assert 'release_garment("m", "jacket")' in t
    assert "release_garment" not in next_steps.after_fit("m", "jacket", 3.0, 0, True)


def test_release_tool_is_registered():
    from hifipushie import server
    assert callable(getattr(server, "release_garment", None))
    assert callable(getattr(server, "arrange_garment", None))
    assert "arrange_garment" in server.TOOLSETS["cloth"]["tools"]


def test_seam_gaps_fail_round16_and_pass_its_closed_fit():
    """Fit round 18: seam_gaps reads an open seam as FAIL on the round 16 release (458 pairs over 1 mm) and PASS on the
    closed fit it started from (r15e, max 0.03 mm); planted: a sew pair pulled 3 mm apart fails."""
    import pickle
    from pathlib import Path
    from hifipushie import cloth_release as cr
    M = {"sew": np.array([[0, 1], [2, 3]])}
    X = np.array([[0, 0, 0], [0, 0, 0.0002], [1, 0, 0], [1, 0, 0.003]], float)
    assert cr.seam_gaps(M, X)["status"] == "FAIL" and cr.seam_gaps(M, X[[0, 1, 2, 2]])["status"] == "PASS"
    r16 = Path("/mnt/data/hifipushie/dress_garrett/fit_round16/asm_r16.pkl")
    fit = Path("/mnt/data/hifipushie/dress_garrett/fit_round17/asm_r15e.pkl")
    if not (r16.exists() and fit.exists()):
        pytest.skip("round 16 data not on this machine")
    a, b = pickle.load(open(r16, "rb")), pickle.load(open(fit, "rb"))
    assert cr.seam_gaps(a["mesh"], a["A"])["status"] == "FAIL"
    assert cr.seam_gaps(b["mesh"], b["A"])["status"] == "PASS"


def test_weld_seams_closes_contact_gaps_and_locates_real_openings():
    """Fit round 19: weld_seams moves sewn pairs within WELD_MM to one point (ZOZO holds them a contact gap apart) and
    reports pairs further apart as located openings, never welded (planted: 0.8 mm welded, 6 mm reported)."""
    from hifipushie import cloth_release as cr
    M = {"sew": np.array([[0, 1], [2, 3]]), "piece": np.array([0, 1, 0, 1]), "names": ["a", "b"]}
    X = np.array([[0, 0, 0], [0, 0, 0.0008], [1, 0, 0], [1, 0, 0.006]], float)
    W, inf = cr.weld_seams(M, X)
    assert np.linalg.norm(W[0] - W[1]) < 1e-12 and abs(W[0, 2] - 0.0004) < 1e-12
    assert inf["welded"] == 1 and len(inf["open"]) == 1 and inf["open"][0]["pieces"] == "a|b"
    assert abs(inf["open"][0]["gap_mm"] - 6.0) < 0.05 and inf["after"]["status"] == "FAIL"


def _open_targets(M, X, side, mm):
    """Arrangement targets for one front edge of the KAT (top -> hem): each vertex turned round the cone's axis at its
    height, away from CF, by a share of `mm` along the surface that rises smoothly from 0 at the chest (sewn) to 1 at
    the hem; its standoff from the body kept."""
    v = cr.pin_vertices(M, f"cone:{side}Top..{side}Hem")
    P = X[v]
    s = np.clip((Z_CHEST - P[:, 2]) / (Z_CHEST - Z_HEM), 0, 1)
    s = s * s * (3 - 2 * s)
    c = APEX[:2] * (1 - _scale(P[:, 2]))[:, None]  # the cone's axis at each height (the chest centre is the origin)
    d = P[:, :2] - c
    r = np.linalg.norm(d, axis=1)
    a = np.arctan2(d[:, 1], d[:, 0]) + (-1 if side == "over" else 1) * s * (mm / 1000) / r
    T = P.copy()
    T[:, :2] = c + r[:, None] * np.c_[np.cos(a), np.sin(a)]
    return v, T


def _opened(M, X0, Y):
    """How far the two hem corners moved apart round the cone, along its surface (mm, + = away from CF each): the
    opening the arrangement made (each corner's turn about the cone's axis at its height x its radius, summed)."""
    out = 0.0
    for side, sg in (("over", -1), ("under", 1)):
        v = M["points"][f"cone:{side}Hem"]
        a = []
        for P in (X0[v], Y[v]):
            c = APEX[:2] * (1 - _scale(P[2]))
            a.append((np.arctan2(P[1] - c[1], P[0] - c[0]), np.linalg.norm(P[:2] - c)))
        out += sg * (a[1][0] - a[0][0]) * 0.5 * (a[0][1] + a[1][1]) * 1000
    return float(out)


def test_arrange_pins_name_points_and_edges():
    res, X, _ = _case("closed")
    M = res["mesh"]
    v = cr.pin_vertices(M, "cone:overTop..overHem")
    assert v[0] == M["points"]["cone:overTop"] and v[-1] == M["points"]["cone:overHem"] and len(v) == NW
    _, T = _open_targets(M, X, "over", 25)
    cfg, arr, info = cr.arrange_job(res, X, [{"at": "cone:overTop..overHem", "targets": T},
                                             {"at": "cone:overHem", "by": [0, 0, 1]}], release=("front",))
    assert len(arr["arrIdx"]) == NW and info["arrange"]["vertices"] == [NW, 0]  # (the hem vertex kept by the first)
    assert cfg["arrange"]["keep"] is False and cfg["frames"] == cr.ARRANGE_PLACE + cr.ARRANGE_HOLD
    assert abs(np.linalg.norm(T[-1] - X[v[-1]]) - 0.025) < 0.002 and np.linalg.norm(T[0] - X[v[0]]) < 1e-9


@pytest.mark.skipif(os.environ.get("HP_RUN_ZOZO") != "1", reason="runs the ZOZO solver locally (HP_RUN_ZOZO=1)")
def test_arranged_open_front_stays_open(tmp_path):
    """KAT (fit round 20): the released open-front tube on the oblique cone, its two front edges placed 25 mm each
    away from CF at the hem (50 mm apart along the surface, `_opened`) by soft pins over a gravity settle.
    Measured 2026-10-20 (local ZOZO): hard pins let go: placed 50.0, sprang back to 24.7 (15-33 mm per pin, still
    moving 1.2 mm): the KAT's fronts hang 6 mm off the body with nothing under them, so no friction can hold them.
    Pull 1 stopped 12 mm short. Kept light pins (pull 10, keep: "placed by hand"): open 48.1 at let-go time, 49.0 at
    the end, springback 0.8, stretch p99 near the pins 0.10 % (rest 0.21, start 3.25), still 0.56 mm. Thresholds: open
    within 6 mm of 50, springback < 3 mm, near-pin stretch p99 < 1 %, still < 1 mm."""
    res, X, _ = _case("open")
    M = res["mesh"]
    pins = []
    for side in ("over", "under"):
        _, T = _open_targets(M, X, side, 25)
        pins.append({"name": side, "at": f"cone:{side}Top..{side}Hem", "targets": T})
    cfg, arr, info = cr.arrange_job(res, X, pins, release=("front",), keep=True)
    jd = cr.write(tmp_path / "arr" / "sim", cfg, arr, M["names"], res["gate_keys"])
    d, _ = cr.run(jd, progress=lambda *_: None, log=lambda *_: None)
    rep = cr.arranged(M, arr, d, keep=True, X_ref=arr["X"])
    out = {"open_end": _opened(M, arr["X"], d["V"]), "still": float(np.abs(d["V"] - d["Vprev"]).max() * 1000), **rep}
    print(out)
    assert abs(out["open_end"] - 50) < 6, out
    assert max(p["springback_max"] for p in rep["pins"].values()) < 3, out
    assert out["stretch_p99_near"] < 1.0 and rep["status"] == "placed by hand", out
    assert out["still"] < 1.0, out
