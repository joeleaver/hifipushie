"""One human mesh (onemesh.py, human_mesh.npz): uv run python tests/test_onemesh.py   (the asset checks need nothing;
the rest needs the gnm and makehuman packs)"""
import collections
import json
from pathlib import Path

import numpy as np

from hifipushie import assets, onemesh

ROOT = Path(__file__).resolve().parents[1]


def have():
    try:
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        from hifipushie import makehuman
        makehuman.body({"age": 25, "sex": 0.5})
        return True
    except Exception as err:  # the packs aren't in the repo
        print("skipped:", str(err)[:80])
        return False


def _b(head=None, **body):
    return {"body": {"source": "human", **body}, "head": head or {"seed": 3, "spread": 0.5}}


def test_asset_topology():
    """Closed and manifold but for the loose parts' own open edges, wound one way, mirror-symmetric to the bit, every
    bridge vertex with 3-5 edges and no folded bridge quad; weights sum to 1; uvs inside the square."""
    a = onemesh.asset()
    V, F = a["neutral"].astype(float), a["faces"]
    n = len(V)
    cnt, dirc = collections.Counter(), collections.Counter()
    for f in F:
        for k in range(4):
            u, v = int(f[k]), int(f[(k + 1) % 4])
            cnt[(min(u, v), max(u, v))] += 1
            dirc[(u, v)] += 1
    assert set(cnt.values()) <= {1, 2} and max(dirc.values()) == 1
    part_of = {}
    for f, p in zip(F, a["part"]):
        for v in f:
            part_of[int(v)] = int(p)
    assert all(part_of[u] >= 2 for (u, v), c in cnt.items() if c == 1), "an open edge on the skin"
    m = a["mirror"]
    assert (m[m] == np.arange(n)).all() and np.abs(V[m] * [-1, 1, 1] - V).max() == 0
    fs = {tuple(sorted(f)) for f in F.tolist()}
    assert all(tuple(sorted(m[f].tolist())) in fs for f in F)
    n0, n_ring, n_all, nb0 = (int(x) for x in a["bridge"])
    assert n_all == int(a["n_raw_v"])  # (then the lids' loops' vertices, gnmloops.py)
    nf = int(a["n_raw_f"])
    deg = np.zeros(n, int)
    for u, v in cnt:
        deg[u] += 1
        deg[v] += 1
    br = np.r_[a["loop_a"], a["loop_c"], np.arange(n0, n_all)]
    assert deg[br].min() >= 3 and deg[br].max() <= 5, collections.Counter(deg[br].tolist())
    ax = V[n0:n_all].mean(0)
    for f in F[nb0:nf]:
        X = V[f]
        out = X.mean(0) - ax
        out[2] = 0
        for k in range(4):
            nrm = np.cross(X[(k + 1) % 4] - X[k], X[(k + 3) % 4] - X[k])
            assert nrm @ out > 0.05 * np.linalg.norm(nrm) * np.linalg.norm(out), "a folded bridge quad"
    assert np.abs(a["w"].sum(1) - 1).max() < 1e-5
    assert a["uv"].min() >= 0 and a["uv"].max() <= 1
    # every skin vertex is the body's, GNM's or the bridge's, once
    assert ((a["mh_id"] >= 0).astype(int) + (a["gnm_id"] >= 0) + ((np.arange(n) >= n0) & (np.arange(n) < n_all)) == 1).all()


def test_the_stitch_follows_every_body():
    """Ring A lies on the body's own surface (the binding's target) within 0.5 mm from 1 to 78 years, and the whole
    bound head within 1 mm (p95) of the body's own head: nothing to graft, nothing to cross-fade."""
    from hifipushie import base
    g = base._gnm_data()
    skin_ids = np.flatnonzero(g["skin"])
    row = {int(v): i for i, v in enumerate(skin_ids)}
    a, r = onemesh.asset(), onemesh._reference()
    ringA = np.flatnonzero(a["g_lev"] == r["meta"]["RING"])
    ks = []
    for params in ({"age": 25, "sex": 0.5}, {"age": 1, "sex": 1.0}, {"age": 7, "sex": 0.0}, {"age": 78, "sex": 0.0, "weight": 0.8}):
        b = _b(**params)
        bd = onemesh.bound(onemesh.body_params(b))
        T = (r["bar"][:, :, None] * bd["P"][r["tri"]]).sum(1)
        ht = onemesh.head_template(b)
        dA = np.linalg.norm(ht["verts"][[row[int(v)] for v in ringA]] - T[ringA], axis=1)
        allv = np.flatnonzero(r["val"] & (a["g_lev"] >= r["meta"]["RING"]))
        dall = np.linalg.norm(bd["B"][allv] - T[allv], axis=1)
        assert dA.max() < 5e-4 and np.percentile(dall, 95) < 1e-3, (params, dA.max(), np.percentile(dall, 95))
        ks.append(bd["k"])
    assert abs(ks[0] - 1) < 1e-6 and ks[1] < 0.85 < ks[3] < 1.0  # the head's size is the body's: a baby's is ~0.77


def test_template_is_one_closed_mesh_and_deterministic():
    b = _b(age=30, sex=0.0)
    t1 = onemesh.template(b)
    keep = {k: v for k, v in onemesh._CACHE.items() if k in ("asset",)}
    onemesh._CACHE.clear()
    onemesh._CACHE.update(keep)
    from hifipushie import base
    for k in [k for k in base._CACHE if isinstance(k, tuple) and k[0] == "head"]:
        base._CACHE.pop(k)
    t2 = onemesh.template(b)
    assert np.array_equal(t1["P"], t2["P"]) and np.array_equal(t1["L"], t2["L"])
    F = np.asarray(t1["L"]).reshape(-1, 4)
    cnt = collections.Counter()
    for f in F:
        for k in range(4):
            cnt[(min(f[k], f[(k + 1) % 4]), max(f[k], f[(k + 1) % 4]))] += 1
    open_edges = [e for e, c in cnt.items() if c == 1]
    # the only open edges: GNM's skin ends inside the lips (the mouth sock is not in the field's mesh)
    P = t1["P"]
    assert all(P[u, 2] > t1["chin_lm"] for u, v in open_edges) and len(open_edges) < 200
    assert np.isfinite(P).all()
    # symmetric to 1 mm (the seed's identity is not symmetric: test the neutral head)
    tn = onemesh.template(_b(head={}, age=30, sex=0.0))
    from scipy.spatial import cKDTree
    d, _ = cKDTree(tn["P"]).query(tn["P"] * [-1, 1, 1])
    assert d.max() < 1e-3, d.max()  # (MakeHuman's own targets are symmetric to ~0.6 mm)


def test_identity_fades_out_at_the_stitch():
    """A seed moves the face by centimetres and the bridge / the body's neck not at all."""
    a = onemesh.template(_b(head={}, age=30, sex=1.0))
    c = onemesh.template(_b(head={"seed": 11, "spread": 1.0}, age=30, sex=1.0))
    d = np.linalg.norm(a["P"] - c["P"], axis=1)
    assert d[:a["n_body"]].max() == 0 and d[a["n_body"]:].max() > 0.004
    assert a["chin_mh"] == c["chin_mh"]


def test_old_paths_never_touch_it():
    """A MakeHuman + GNM graft and the plain template build without one call into onemesh."""
    from hifipushie import base, humans
    from hifipushie.spec import expand_mirror
    saved = {k: getattr(onemesh, k) for k in ("template", "head", "hook", "bound")}

    def boom(*a, **k):
        raise AssertionError("an old path called onemesh")
    try:
        for k in saved:
            setattr(onemesh, k, boom)
        for sp in (humans.spec(age=30, sex=1.0, seed=3, skin=False), {"base": {"template": "male_stylized"}, "joints": {}, "bones": {}, "blobs": {}}):
            sf = base.surface(expand_mirror(sp), sp["base"])
            assert sf["template"] != "human"
    finally:
        for k, v in saved.items():
            setattr(onemesh, k, v)


def test_whole_person_builds_and_measures_as_the_old_path():
    """humans.spec(source="human"): the same body measures as the grafted path (stature, head height within 1%),
    landmarks and eyes come from the one mesh, the base's surface is one mesh with no seam."""
    from hifipushie import base, humans
    from hifipushie.spec import expand_mirror
    for age, sex in ((3, 0.0), (30, 1.0)):
        new = humans.spec(age=age, sex=sex, seed=5, skin=False, source="human")
        old = humans.spec(age=age, sex=sex, seed=5, skin=False)
        mn, mo = humans.measures(new), humans.measures(old)
        for k in ("stature", "head_height", "sitting_height", "hand_length"):
            assert abs(mn[k] / mo[k] - 1) < 0.02, (k, mn[k], mo[k])  # (the seed moves the crown by millimetres)
        e = expand_mirror(new)
        for j in ("lm_chin", "lm_nose_tip", "eye.L", "eye.R", "eye_front.L", "lm_jaw_4.L"):
            assert j in e["joints"], j
        sf = base.surface(e, new["base"])
        assert sf["template"] == "human" and sf["seam"] is None and sf["wt"] is None and sf["graft"] is None
        assert len(sf["src"]) == len(sf["quads"][0])
        chin = np.array(e["joints"]["lm_chin"]["pos"])
        assert abs(chin[2] - mn["stature"] + mn["head_height"]) < 0.012  # the landmark chin vs the body's own chin vertex


def test_weights_by_index():
    """The rig's template weights for the one mesh: rows sum to 1, the crown is Head's, a fingertip its finger's, and
    above the stitch nothing is left on the arm's side."""
    from hifipushie import base, humans, rig, rig_template
    from hifipushie.spec import expand_mirror
    sp = humans.spec(age=30, sex=1.0, seed=5, skin=False, source="human")
    e = expand_mirror(sp)
    sf = base.surface(e, sp["base"])
    rb = rig.rig_bones(sp)
    W = rig_template.template_weights(sp, rb, sf)
    assert W is not None and W.shape == (len(sf["quads"][0]), len(rb))
    assert np.abs(W.sum(1) - 1).max() < 1e-6
    names = [b["name"] for b in rb]
    V = sf["quads"][0]
    assert names[int(W[np.argmax(V[:, 2])].argmax())].endswith("Head")
    tpl = base.source(sp["base"])
    up = np.arange(len(V)) >= tpl["n_mh"]
    side = np.array([any(s in n for s in ("Shoulder", "Arm", "Hand")) for n in names])
    far = up & (V[:, 2] > np.array(e["joints"]["lm_chin"]["pos"])[2] + 0.06)
    assert W[np.ix_(far, side)].max() < 1e-6
    tip = int(np.argmax(V[:, 0]))
    assert "Hand" in names[int(W[tip].argmax())]


def test_head_size_scales_about_the_centre_line():
    """style.human.head_size scales the head about the neck's top ON THE CENTRE LINE: the eyes stay mirror images
    and the eye midpoint stays at x = 0 (the pivot once fell to a bounding-box corner: the face moved 10 mm sideways)."""
    from hifipushie import base as basemod
    from hifipushie.spec import expand_mirror
    from hifipushie import humans
    sp = humans.spec(age=40, sex=1.0, seed=3, skin=False, source="human")
    sp["base"].setdefault("style", {})["human"] = {"head_size": 1.12}
    h = basemod.head_of(expand_mirror(sp), sp["base"])
    E = np.asarray(h["eyes"], float)
    assert abs(E[0, 0] + E[1, 0]) < 1e-4, E
    assert abs(E[0, 1] - E[1, 1]) < 1e-3 and abs(E[0, 2] - E[1, 2]) < 1e-3, E  # (a seed is a hair asymmetric: 0.2 mm)


def test_face_shapes_by_index_on_own_quads():
    """On the one mesh's own quads (parts.body.topology "wrap") the head's vertices ARE GNM's: face shapes are GNM's
    offsets by vertex index (no projection), GNM's mouth sock closes the mouth, its interior surfaces aren't snapped
    onto the field, and the neutral's lips meet on GNM's contact ring. jawOpen moves evenly (the projected path's
    strands read 3.2 on the same mesh)."""
    from hifipushie import faceshapes, humans, retopo
    sp = humans.spec(age=40, sex=1.0, seed=3, skin=False, source="human",
                     head={"interior": {"teeth": {"show": 0.0035}, "tongue": True}})  # (GNM's own lips: no mouth_gap)
    sp.setdefault("parts", {}).setdefault("body", {})["topology"] = "wrap"
    r = retopo.wrap(sp, log=[])
    V, L, S, gnm = r["verts"], r["loops"], r["sizes"], np.asarray(r["gnm"])
    assert (gnm >= 0).sum() > 10000 and any(x.startswith("mouth:") for x in r["log"])
    st = np.r_[0, np.cumsum(S)[:-1]]
    T = np.array([(L[a], L[a + j], L[a + j + 1]) for a, k in zip(st, S) for j in range(1, k - 1)])
    face = faceshapes.face_of(sp)
    Xn = V + face.neutral(V, "skin", gnm)
    R = face._lip_rings()
    assert R["ok"]
    row = {int(v): i for i, v in enumerate(gnm) if v >= 0}
    from scipy.spatial import cKDTree
    gap = cKDTree(Xn[[row[v] for v in R["lo"]]]).query(Xn[[row[v] for v in R["up"]]])[0]
    assert gap.mean() < 0.0012, gap.mean()
    n0 = faceshapes.vertex_normals(Xn, T)
    D = face.displacements(V, Xn, n0, "skin", ["jawOpen", "eyeBlinkLeft"], None, gnm)
    first, Tw, _ = faceshapes.weld(Xn, T)
    for nm in ("jawOpen", "eyeBlinkLeft"):
        u = faceshapes.unevenness(Xn[first], Tw, D[nm][first], face.off_margins(nm, Xn[first]))[0]
        assert u < faceshapes.UNEVEN_LIMIT, (nm, u)
    assert np.linalg.norm(D["jawOpen"], axis=1).max() > 0.015


def test_stored_warp_survives_features():
    """A human() keeps base.head.features (the seed's look); head_desc used to REPLACE base.head.warp with the
    features' warp, so every fit_outline on such a head was dropped (Tess: widths moved 0.0 mm in 3 rounds)."""
    from hifipushie import base as basemod
    from hifipushie import humans
    from hifipushie.spec import expand_mirror
    sp = humans.spec(age=22, sex=0.0, seed=35, skin=False, source="human")
    assert sp["base"]["head"].get("features"), "the case needs a head with features"
    h0 = basemod.head_of(expand_mirror(sp), sp["base"])
    w = {"at": [[0.071, 0.24, 0.033], [-0.071, 0.24, 0.033]], "coef": [[0.004, 0.0, 0.0], [-0.004, 0.0, 0.0]],
         "sigma": 0.022}  # GNM frame: the cheeks at the mouth (as fit_outline writes)
    sp["base"]["head"]["warp"] = w
    hd = onemesh.head_desc(sp["base"])
    assert isinstance(hd["warp"], list) and hd["warp"][-1] == w and len(hd["warp"]) == 2, hd.get("warp")
    h1 = basemod.head_of(expand_mirror(sp), sp["base"])
    d = max(float(np.abs(np.asarray(h1[k], float) - np.asarray(h0[k], float)).max())
            for k in h0 if isinstance(h0[k], (list, np.ndarray)) and np.asarray(h0[k]).dtype.kind == "f"
            and np.shape(h0[k]) == np.shape(h1.get(k)))
    assert d > 1e-3, f"the stored warp moved nothing ({d})"


if __name__ == "__main__":
    test_asset_topology()
    print("ok test_asset_topology")
    if have():
        for fn in (test_the_stitch_follows_every_body, test_template_is_one_closed_mesh_and_deterministic,
                   test_identity_fades_out_at_the_stitch, test_old_paths_never_touch_it,
                   test_whole_person_builds_and_measures_as_the_old_path, test_weights_by_index,
                   test_head_size_scales_about_the_centre_line, test_face_shapes_by_index_on_own_quads,
                   test_stored_warp_survives_features):
            fn()
            print("ok", fn.__name__)
