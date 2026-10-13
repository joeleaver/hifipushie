"""The native attach (onemesh, base.head.attach "native"): GNM's head untouched at its own size down to the seam ring,
the body fitted. uv run python tests/test_headbody.py   (needs the gnm and makehuman packs)"""
import copy
import hashlib

import numpy as np

from hifipushie import assets, onemesh

IDENT = {"head_000": 1.2, "head_001": -0.8, "head_004": 0.9, "head_011": -1.1, "head_030": 0.7}
STYLE = {"human": {"head_size": 0.95, "legs": 1.03, "hips": 0.92, "limbs": 0.9, "waist": 0.95}}


def have():
    try:
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        from hifipushie import makehuman
        makehuman.body({"age": 25, "sex": 0.5})
        return True
    except Exception as err:  # the packs aren't in the repo
        print("skipped:", str(err)[:80])
        return False


def _b(head=None, style=None, **body):
    b = {"body": {"source": "human", **body}, "head": {"identity": dict(IDENT), "attach": "native", **(head or {})}}
    if style:
        b["style"] = copy.deepcopy(style)
    return b


def _gnm(ident, expression=None):
    from hifipushie import base as B
    g = B._gnm_data()
    ci = B._gnm_coeffs(g["identity_names"], ident)
    V = g["template_vertex_positions"] + np.tensordot(ci, g["vertex_identity_basis"], 1)
    return g, V.astype(float)


def _head_rows():
    """GNM's skin vertices from the seam ring up (the vertices the head mesh is made of)."""
    from hifipushie import base as B
    g = B._gnm_data()
    a = onemesh.asset()
    return np.asarray(g["skin"], bool) & (a["g_lev"].astype(int) >= onemesh._reference()["meta"]["RING"])


def test_head_is_gnms_evaluation_under_one_similarity():
    """No face, jaw, skull or neck vertex above the seam ring moves: every one is GNM's own evaluation of the
    identity x size + a translation, to float precision; on a plain body, a styled body, a child-sized `size`."""
    keep = _head_rows()
    for kw, size in ((dict(age=22, sex=0.0, weight=0.15, height=1.636), 1.0),
                     (dict(age=52, sex=1.0, weight=0.4, height=1.7715, style=STYLE), 1.0),
                     (dict(age=30, sex=0.5), 0.9)):
        b = _b({"size": size} if size != 1.0 else None, **kw)
        ht = onemesh.head_rest(b)
        g, V = _gnm(IDENT)
        size = onemesh.head_desc(b)["bound"]["native"]["size"]
        X = V @ onemesh._RG.T
        W = np.asarray(ht["gnm_world"], float)
        t = (W[keep] - size * X[keep]).mean(0)
        err = np.abs(W[keep] - (size * X[keep] + t)).max()
        assert err < 1e-9, (kw, err)
        # and the template's head rows ARE those vertices (what is meshed, exported, skinned)
        tpl = onemesh.template(b)
        nb, hr = tpl["n_body"], tpl["head_rows"]
        assert np.abs(tpl["P"][nb:nb + len(hr)] - ht["verts"][hr]).max() < 1e-12
        skin_ids = np.flatnonzero(g["skin"])
        assert keep[skin_ids[hr]].all() and keep.sum() == len(hr)


def test_lip_close_is_the_only_other_move_and_it_is_gnms_expression():
    """With the rest mouth closed (lip_close: GNM's lower-face expression, our coefficients) the head differs from
    template + identity only inside GNM's expression basis; the skull and the eyes do not move at all."""
    from hifipushie import base as B
    keep = _head_rows()
    b0 = _b(age=30, sex=1.0)
    b1 = _b({"lip_close": True}, age=30, sex=1.0)
    W0, W1 = (np.asarray(onemesh.head_rest(b)["gnm_world"], float) for b in (b0, b1))
    d = (W1 - W0)[keep]
    assert np.abs(d).max() > 1e-4  # (it does close the lips)
    g = B._gnm_data()
    low = [i for i, n in enumerate(g["expression_names"]) if str(n).startswith("lower_face")]
    E = np.asarray(g["expression_basis"])[low][:, keep] @ onemesh._RG.T
    A = E.reshape(len(low), -1).T
    c = np.linalg.lstsq(A, d.ravel(), rcond=None)[0]
    assert np.abs(A @ c - d.ravel()).max() < 1e-7
    up = np.asarray(g["groups"]["scalp"] if "scalp" in g["groups"] else g["groups"]["ears"])[keep] > 0.5
    assert np.abs(d[up]).max() < 1e-9


def test_stature_is_the_stated_one_and_the_body_gives():
    for kw in (dict(age=22, sex=0.0, weight=0.15, height=1.636), dict(age=52, sex=1.0, height=1.7715, style=STYLE)):
        b = _b(**kw)
        P = onemesh.template(b)["P"]
        assert abs(float(P[:, 2].max() - P[:, 2].min()) - kw["height"]) < 5e-4, kw
        r = onemesh.attach_report(b)
        assert r["native"] and abs(r["size"] - 1.0) < 6e-3 and abs(r["eyeball_r"] - 0.0146) < 2e-4
        assert 6.5 < r["heads_tall"] < 8.8, r["heads_tall"]
        assert "base.style.human.head_size" in r["ignored"] if kw.get("style") else not r["ignored"]


def test_seam_ring_and_neck():
    """The seam ring: 110 vertices, GNM's ring exactly; the body's vertices moved to meet it fade out below (nothing
    under the armpits moves), no quad next to the ring is folded, the mesh stays closed there."""
    import collections
    b = _b(age=22, sex=0.0, weight=0.15, height=1.636)
    tpl = onemesh.template(b)
    ring = onemesh.seam_ring(tpl)
    assert len(ring) == 110 and (ring >= tpl["n_body"]).all()
    P = tpl["P"]
    hd = onemesh.head_desc(b)
    a = onemesh.asset()
    mh_rows = np.flatnonzero(a["m2f"] >= 0)
    own = onemesh.bound(hd["bound"]["body"], 1.0)["P"][mh_rows]
    moved = np.linalg.norm(P[:tpl["n_mh"]] - own, axis=1)
    assert 0.002 < moved.max() < 0.06
    assert own[moved > 1e-5][:, 2].min() > 0.68 * 1.636  # (shoulders and neck only)
    faces, i = [], 0
    for n in tpl["S"]:
        faces.append(tpl["L"][i:i + n])
        i += n
    near = np.zeros(len(P), bool)
    near[:tpl["n_mh"]] = moved > 1e-5
    near[tpl["n_mh"]:tpl["n_body"]] = True
    cnt = collections.Counter()
    for f in faces:
        f = np.asarray(f)
        if near[f].any():
            X = P[f]
            if len(f) == 4:
                n1 = np.cross(X[1] - X[0], X[2] - X[0])
                n2 = np.cross(X[2] - X[0], X[3] - X[0])
                assert n1 @ n2 > 0, "a folded quad at the neck"
        if np.isin(f, ring).any():
            for k in range(len(f)):
                u, v = int(f[k]), int(f[(k + 1) % len(f)])
                if u in set(ring.tolist()) and v in set(ring.tolist()):
                    cnt[(min(u, v), max(u, v))] += 1
    assert len(cnt) == 110 and set(cnt.values()) == {2}  # every ring edge has a head face and a body face


def test_the_default_attach_is_unchanged():
    """The old path (no attach key) builds the same template as before this change (hashes of main 1ed30ce)."""
    b = {"body": {"source": "human", "age": 30, "sex": 1.0}, "head": {"identity": dict(IDENT), "gnm_base": 1.0, "dimorphism": 0.0}}
    P = onemesh.template(b)["P"]
    h = hashlib.sha256(np.round(P, 7).tobytes()).hexdigest()[:16]
    assert h == OLD_HASH, h


RANGE = {"woman": dict(age=30, sex=0.0), "man": dict(age=30, sex=1.0), "heavy": dict(age=40, sex=1.0, weight=0.9),
         "very slim": dict(age=25, sex=0.0, weight=0.05), "muscular": dict(age=30, sex=1.0, muscle=0.95),
         "tall": dict(age=30, sex=1.0, height=1.95), "short": dict(age=30, sex=0.0, height=1.50), "old": dict(age=75, sex=1.0)}


def _class_mean(sex):
    from hifipushie import blockin as bi
    D = bi.data()
    return {f"head_{i:03d}": float(x) for i, x in enumerate(np.asarray(D["m_m"] if sex >= 0.5 else D["m_f"])[:170])}


def test_any_body_takes_the_head():
    """The rule is general: GNM's class-mean head on a spread of bodies, the same code, no per-character constant.
    On each: the stated (or the body's own) stature is met, the head is GNM's to the bit, the seam ring is matched,
    no quad round the neck is folded, and the report's anthropometric checks (heads tall, top of head and chin over
    the pit of the throat, neck girth) are inside their ranges."""
    from hifipushie import makehuman
    keep = _head_rows()
    for name, kw in RANGE.items():
        b = {"body": {"source": "human", **kw}, "head": {"identity": _class_mean(kw["sex"]), "attach": "native"}}
        tpl = onemesh.template(b)
        P = tpl["P"]
        want = kw.get("height") or float(np.asarray(makehuman.body({k: v for k, v in kw.items()})["P"])[:, 2].max())
        assert abs(float(P[:, 2].max() - P[:, 2].min()) - want) < 1e-3, (name, want)
        ht = onemesh.head_rest(b)
        g, V = _gnm(b["head"]["identity"])
        size = onemesh.head_desc(b)["bound"]["native"]["size"]
        assert 0.96 < size < 1.04, (name, size)  # (the head goes a little with the stature: stature ^ ~0.27)
        X = size * (V @ onemesh._RG.T)
        W = np.asarray(ht["gnm_world"], float)
        assert np.abs(W[keep] - (X[keep] + (W[keep] - X[keep]).mean(0))).max() < 1e-9, name
        ring = onemesh.seam_ring(tpl)
        assert len(ring) == 110 and (ring >= tpl["n_body"]).all()
        faces, i = [], 0
        for n in tpl["S"]:
            faces.append(tpl["L"][i:i + n])
            i += n
        hd = onemesh.head_desc(b)
        a = onemesh.asset()
        own = onemesh.bound(hd["bound"]["body"], 1.0)["P"][np.flatnonzero(a["m2f"] >= 0)]
        near = np.zeros(len(P), bool)
        near[:tpl["n_mh"]] = np.linalg.norm(P[:tpl["n_mh"]] - own, axis=1) > 1e-5
        near[tpl["n_mh"]:tpl["n_body"]] = True
        for f in faces:
            f = np.asarray(f)
            if len(f) == 4 and near[f].any():
                Xq = P[f]
                assert np.cross(Xq[1] - Xq[0], Xq[2] - Xq[0]) @ np.cross(Xq[2] - Xq[0], Xq[3] - Xq[0]) > 0, (name, "a folded quad at the neck")
        r = onemesh.attach_report(b)
        bad = [c["name"] for c in r["checks"] if not c["ok"]]
        # the one known limit: GNM's neck has its own length, so on a very tall body head + neck stand short over the
        # shoulders for the stature, and the report says so
        assert bad == (["top of head over the pit of the throat"] if name == "tall" else []), (name, bad, r["text"])


OLD_HASH = "4cd5e3e000a60164"

if __name__ == "__main__":
    if have():
        for fn in (test_head_is_gnms_evaluation_under_one_similarity, test_lip_close_is_the_only_other_move_and_it_is_gnms_expression,
                   test_stature_is_the_stated_one_and_the_body_gives, test_seam_ring_and_neck, test_any_body_takes_the_head, test_the_default_attach_is_unchanged):
            fn()
            print("ok", fn.__name__)
