"""chain_layers (T9, T12): a garment built over another. The plan's `over` validated, the order refusal (the under
garment's steps 1 + 4 and a build first), an over garment inside an under one refused by name, the collider = the body +
the under's THICKNESS where it covers + its stiff parts and solid details (T12), the under garment pressed inside the over
one with its lengths kept (chain_press). Synthetic meshes only: no build, no render."""
import json
import pickle

import numpy as np
import pytest

from types import SimpleNamespace

from hifipushie import chain_garment as cg, chain_layers as cl, chain_press as cpr, garment_plan as gp, server, store

from test_garment_plan import _parts, _read, _style, home  # noqa: F401  (the fixture: a temporary HOME + reference picture)


def _sphere(r, n=24, zmin=-1.0):
    """A lat-long sphere of radius r, outward faces; zmin (fraction of r) cuts it open below (a cloth with a hem)."""
    th = np.linspace(0, np.pi, n + 1)
    th = th[np.cos(th) >= zmin - 1e-9]
    ph = np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)
    V = np.array([[r * np.sin(t) * np.cos(p), r * np.sin(t) * np.sin(p), r * np.cos(t)] for t in th for p in ph])
    m = len(ph)
    F = []
    for i in range(len(th) - 1):
        for j in range(m):
            a, b, c, d = i * m + j, i * m + (j + 1) % m, (i + 1) * m + j, (i + 1) * m + (j + 1) % m
            F += [[a, c, b], [b, c, d]]
    V, F = np.array(V), np.array(F)
    keep = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1) > 1e-12
    return V, F[keep]


def _body():
    V, F = _sphere(0.10)
    return cg.Body(V, F, {"chest_z": 0.05, "waist_z": -0.05, "hps.L": [0.02, 0.0, 0.1]})


def _layered(gap=0.002, details=None):
    body = _body()
    V, F = _sphere(0.11, zmin=-0.3)  # the shirt: open below 30 % of its radius
    layers = [cl.Layer("shirt", "cloth", V, cl.outward(V, F, body.contact), gap, body.contact)]
    if details is not None:
        layers.append(cl.Layer("shirt:details", "solid", details[0], cl.closed_outward(*details), cl.zozo_legal()))
    return cl.LayeredBody(body, layers, {"shirt": {"gap_mm": gap * 1e3, "surface": "built", "approved": True}})


def _over(r, zmin=-1.0):
    V, F = _sphere(r, n=16, zmin=zmin)
    return V, {"piece": np.zeros(len(V), int), "names": ["front.L"], "F": F}


def _model(home, cloth=("shirt", "jacket")):
    store._dir("m").mkdir(parents=True, exist_ok=True)
    (store._dir("m") / "spec.json").write_text(json.dumps({"joints": {}, "bones": {}, "cloth": {c: {} for c in cloth}}))
    for g in cloth:
        gp.write("m", g, "read", _read(home), look=False)


def test_plan_over_validated(home):
    _model(home)
    for bad, why in ((["jacket"], "is this garment"), (["coat"], "not a garment of m"), ("shirt", "a list of garment names")):
        with pytest.raises(gp.PlanRefused, match=why):
            gp.write("m", "jacket", "parts", dict(_parts(), over=bad), look=False)
    r = gp.write("m", "jacket", "parts", dict(_parts(), over=["shirt"]), look=False)
    assert cl.worn_over("m", "jacket") == ["shirt"] and "worn over: shirt" in gp.text("m", "jacket", r)
    with pytest.raises(gp.PlanRefused, match="a loop"):  # (the shirt can't then be worn over the jacket)
        gp.write("m", "shirt", "parts", dict(_parts(), over=["jacket"]), look=False)
    assert cl.under_for("m", "shirt") == {}  # (worn over nothing: the body alone, as before)


def test_order_needs_the_under_pattern_and_a_build_not_its_approval(home, monkeypatch):
    _model(home)
    gp.write("m", "jacket", "parts", dict(_parts(), over=["shirt"]), look=False)
    monkeypatch.delenv(cl.SETTING, raising=False)
    with pytest.raises(cl.LayerRefused, match="no build"):
        cl.under_for("m", "jacket")
    txt = server.chain_garment("m", "jacket", wait=0)  # (the tool refuses at once, nothing spawned)
    assert "refused (layering)" in txt and "next:" in txt and '"garment": "shirt"' in txt
    d = cl._under_job("m", "shirt")
    pickle.dump({"X": np.zeros((3, 3)), "M": {"F": [[0, 1, 2]]}}, open(d / "built.pkl", "wb"))
    with pytest.raises(cl.LayerRefused, match="step 1 .*step 4|need not be approved"):  # (its parts + pattern, not approval)
        cl.under_for("m", "jacket")
    monkeypatch.setenv(cl.SETTING, "built")  # (development: an unfinished record, flagged)
    u = cl.under_for("m", "jacket")
    assert u["shirt"]["approved"] is False and u["shirt"]["surface"] == "built"
    assert "UNFINISHED" in cl.answer_line({"wear": {"under": u}})


def test_over_garment_inside_the_under_is_refused_by_name():
    L = _layered()
    X, M = _over(0.105)  # between the body (0.10) and the shirt (0.11): inside it
    rd = cl.reads(X, M, L)
    assert rd["shirt"]["inside"] > 0 and rd["shirt"]["pieces"]["front.L"]["level"] in ("neck", "chest", "waist")
    why = cl.inside_refusal(rd)
    assert "front.L is inside shirt" in why and "ease" in why and "draft" in why
    X2, M2 = _over(0.12)  # outside: 10 mm off the shirt, nothing inside
    rd2 = cl.reads(X2, M2, L)
    assert rd2["shirt"]["inside"] == 0 and 9.0 < rd2["shirt"]["closest_mm"] < 10.5 and cl.inside_refusal(rd2) == ""
    X3, M3 = _over(0.105, zmin=-1.0)  # below the shirt's hem the body alone decides: not inside the shirt there
    low = X3[:, 2] < -0.06
    rd3 = cl.reads(X3[low], {"piece": M3["piece"][low], "names": M3["names"]}, L)
    assert rd3["shirt"]["inside"] == 0
    d, _ = L.contact.query(X3)  # the stages' floor (the inflated body): inside the shirt reads below GAP, the body below its hem
    assert (d[X3[:, 2] > 0.05] < cg.GAP).all() and np.allclose(d[X3[:, 2] < -0.08], 0.005, atol=0.001)
    assert np.allclose(L.contact.query(_over(0.11 + 0.002)[0][:40])[0], cg.GAP, atol=0.0015)  # (the floor = the gap off the shirt)


class _Build:
    def __init__(self, X, M):
        self.X, self.pat, self.reads = X, type("P", (), {"M": M})(), {}

    def gate_lengths(self):
        pass


def test_gate_refuses_inside_before_lengths():
    X, M = _over(0.105)
    with pytest.raises(cg.ChainRefused, match="worn over shirt: front.L is inside shirt"):
        cl.gate(_Build(X, M), _layered())
    X2, M2 = _over(0.12)
    b = _Build(X2, M2)
    put = {}
    cl.gate(b, _layered(), put=lambda **kw: put.update(kw))
    assert put["layers"]["shirt"]["inside"] == 0 and b.reads["layers"]


def _button(at, r=0.008, h=0.004):
    """A closed disc (button) lying on the shirt at `at`, faces turned INWARD (closed_outward must fix them)."""
    n = 12
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    rim = np.c_[np.zeros(n), r * np.cos(a), r * np.sin(a)]
    V = np.r_[rim, rim + [h, 0, 0], [[0, 0, 0]], [[h, 0, 0]]] + at
    F = []
    for i in range(n):
        j = (i + 1) % n
        F += [[i, j, n + i], [j, n + j, n + i], [2 * n, j, i], [2 * n + 1, n + i, n + j]]
    return V, np.array(F)[:, [0, 2, 1]]


def test_details_in_the_collider(home, tmp_path):
    V, F = _button([0.111, 0.0, 0.0])  # on the shirt's +X side, 4 mm proud
    L = _layered(details=(V, F))
    P = np.array([[0.1137, 0.0, 0.0], [0.1137, 0.0, 0.03]])  # inside the button (nearer its top) / clear of it
    det = L.layers[1].query(P)
    assert det[0][0] < 0 < det[0][1] and det[2][0]
    d, n = L.contact.query(P)
    assert d[0] < cg.GAP and n[0][0] > 0.5  # (the button pushes the over garment out, along +X)
    X, M = _over(0.113, zmin=-0.2)
    assert cl.reads(X, M, L)["shirt:details"]["inside"] >= 0  # (read per detail layer)
    # layered_body loads a job's details.pkl beside its build
    d_ = tmp_path / "job"
    d_.mkdir()
    Vs, Fs = _sphere(0.11, zmin=-0.3)
    pickle.dump({"X": Vs, "M": {"F": Fs}}, open(d_ / "built.pkl", "wb"))
    pickle.dump({"anchors": {}, "built": {"buttons": {"V": V, "F": F, "colour": [1, 1, 1]}}, "hung": None},
                open(d_ / "details.pkl", "wb"))
    store._dir("m").mkdir(parents=True, exist_ok=True)
    LB = cl.layered_body("m", "jacket", _body(), {"shirt": {"job": str(d_), "surface": "built", "details": True,
                                                             "approved": True}})
    assert [x.name for x in LB.layers] == ["shirt", "shirt:details"] and LB.info["shirt"]["details_in"] == ["buttons"]
    assert len(LB.V) == len(_body().V) and LB.push.max() > 0.01  # (the body inflated over the shirt + the button)


def test_collider_is_the_under_thickness_not_its_shape():
    """A loose under garment (30 mm off the body) pushes the over garment out by its thickness only; its stiff part by
    how far it really stands off."""
    body = _body()
    V, F = _sphere(0.13, zmin=-0.3)
    push, gap_out = cpr.room(0.0003, 0.001)
    assert 0 < gap_out < push < 0.004 and cpr.room(0.0003, 0.001, "full")[0] > push
    soft = cl.Layer("shirt", "cloth", V, cl.outward(V, F, body.contact), push, body.contact, role="cover")
    LB = cl.LayeredBody(body, [soft], {"shirt": {}})
    assert abs(LB.push.max() - push) < 1e-9 and LB.push[body.V[:, 2] < -0.06].max() == 0  # (none past its hem)
    top = V[:, 2] > 0.12  # a stiff part (a band) where the loose shirt is: it pushes by its stand-off
    Fs = F[top[F].all(1)]
    stiff = cl.Layer("shirt:stiff", "cloth", V, cl.outward(V, Fs, body.contact), gap_out, body.contact)
    LB2 = cl.LayeredBody(body, [soft, stiff], {"shirt": {}})
    assert LB2.push.max() > 0.025 and np.median(LB2.push[(body.V[:, 2] > 0) & (body.V[:, 2] < 0.05)]) == pytest.approx(push)


class _Net:
    def __init__(self, F, n, links):
        self.F, self.root, self.names = F, np.arange(n), ["front"]
        self.link_i, self.link_j = links[:, 0], links[:, 1]
        self.verts = lambda p: np.arange(n)


class _Under:
    """A stand-in under build: chains exact (meridians), the other edges at most their length; nothing held."""

    def __init__(self, V, F, body, stiff=None):
        n = len(V)
        E = cl.cn.edges_of(F)
        mer = np.abs(np.arctan2(V[E[:, 0], 1], V[E[:, 0], 0]) - np.arctan2(V[E[:, 1], 1], V[E[:, 1], 0])) < 1e-6
        self.X, self.body = V.copy(), body
        self.net = _Net(F, n, E[mer])
        self.net.uv = V[:, :2]
        self.net.link_L = np.linalg.norm(V[E[mer, 1]] - V[E[mer, 0]], axis=1)
        L = np.linalg.norm(V[E[:, 1]] - V[E[:, 0]], axis=1)
        self.stiff = np.zeros(n, bool) if stiff is None else stiff
        self.final_links = (E[:, 0], E[:, 1], L, mer, self.stiff, [(body.contact, np.where(~self.stiff)[0], cg.GAP)], None)

    def _stiff_mask(self):
        return self.stiff

    def chain_read(self, X):
        e = np.abs(np.linalg.norm(X[self.net.link_j] - X[self.net.link_i], axis=1) / self.net.link_L - 1) * 100
        return {"free_worst_pct": round(float(e.max()), 3)}


def test_under_garment_pressed_inside_the_over_one():
    """A loose under garment (r 0.13, long) fitted inside an over one (r 0.12, shorter): its chains keep their lengths,
    no covered point stays past the over garment's inner limit, the tails below the hem stay where they are; visible
    mode keeps the seen cloth + a margin, its hidden edge held."""
    body = _body()
    LB = cl.LayeredBody(body, [], {})
    oV, oF = _sphere(0.12, n=20, zmin=-0.3)
    uV, uF = _sphere(0.13, n=20, zmin=-0.6)
    ub = _Under(uV, uF, body)
    push, gap_out = cpr.room(0.0003, 0.001)
    f = cpr.fit_one(ub, oV, oF, LB, "visible", gap_out)
    X, rd = f["X"], f["read"]
    assert rd["chains_free_worst_pct"] < cg.MAX_FREE_PCT and rd["outside_limit"] == 0
    sd, _ = cpr.OuterLimit(oV, oF, body.contact).query(X)
    cov = sd < 0.5
    assert cov.sum() > 100 and (sd[cov] > gap_out - 0.001).all()
    assert (body.contact.query(X)[0] > cg.GAP - 0.001).all()
    r = np.linalg.norm(X, axis=1)
    assert np.median(r[uV[:, 2] > 0.05]) < 0.12 - gap_out + 0.002  # (pressed in from 0.13)
    assert rd["pieces"]["front"]["in_mm_p95"] > 5 and rd["pieces"]["front"]["pressed_pct"] > 10
    # (hidden: covered by the over garment; the synthetic spheres' unwelded poles read as open there, so seen + margin)
    low = uV[:, 2] < -0.07  # the tails below the over garment's hem: seen, kept
    kept_v = np.zeros(len(X), bool)
    kept_v[uF[f["keep"]].ravel()] = True
    assert kept_v[low].all() and not kept_v[(uV[:, 2] > 0.04) & (uV[:, 2] < 0.08)].any() and f["held"].sum() > 0
    full = cpr.fit_one(ub, oV, oF, LB, "full", gap_out)
    assert full["keep"].all() and full["held"].sum() == 0


def test_stiff_under_parts_are_not_pressed():
    """A stiff part of the under garment stays as built (it pushed the over garment out); the soft cloth is pressed."""
    body = _body()
    oV, oF = _sphere(0.12, n=20, zmin=-0.3)
    uV, uF = _sphere(0.13, n=20, zmin=-0.6)
    stiff = uV[:, 2] > 0.11
    f = cpr.fit_one(_Under(uV, uF, body, stiff), oV, oF, cl.LayeredBody(body, [], {}), "full", 0.003)
    assert np.allclose(f["X"][stiff], uV[stiff]) and np.linalg.norm(f["X"][~stiff] - uV[~stiff], axis=1).max() > 0.005


def test_plan_layers_option(home):
    _model(home)
    gp.write("m", "jacket", "parts", dict(_parts(), over=["shirt"]), look=False)
    with pytest.raises(gp.PlanRefused, match="layers"):
        gp.write("m", "jacket", "style", dict(_style(), layers={"mode": "full"}), look=False)  # (full needs its reason)
    gp.write("m", "jacket", "style", dict(_style(), layers={"mode": "full", "why": "the jacket comes off"}), look=False)
    assert cpr.mode("m", "jacket")[0] == "full" and cpr.mode("m", "shirt")[0] == "visible"
