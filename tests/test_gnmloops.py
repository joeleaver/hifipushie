"""The upper lids' extra edge loops (gnmloops.py): cut into GNM's quads as closed rings, appended so every old index
holds, mirror symmetric, and the one mesh's surface unchanged by them (uv / weights / faces carried)."""
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hifipushie import assets, base, gnmloops, humans, onemesh  # noqa: E402
from hifipushie.spec import expand_mirror  # noqa: E402


def _gnm_ok():
    try:
        assets.path("gnm", base.GNM)
        return True
    except Exception:
        return False


def test_loops_are_closed_manifold_and_symmetric():
    if not _gnm_ok():
        return
    P = gnmloops.plan()
    Q = P["quads"]
    k = len(P["parents"])
    assert k == 530 and len(Q) == P["n_quads"] + 530  # three rings: 200 + 200 + 118 quads, 12 cut both ways
    raw = gnmloops._raw()["quads"]
    # the old quads' edges are all still there (split), each directed edge once, each edge in at most two quads
    dirc, cnt = collections.Counter(), collections.Counter()
    for f in Q:
        for i in range(4):
            u, v = int(f[i]), int(f[(i + 1) % 4])
            dirc[(u, v)] += 1
            cnt[(min(u, v), max(u, v))] += 1
    assert max(dirc.values()) == 1 and max(cnt.values()) <= 2
    rc = collections.Counter((min(int(f[i]), int(f[(i + 1) % 4])), max(int(f[i]), int(f[(i + 1) % 4])))
                             for f in raw for i in range(4))
    open_raw = sum(1 for c in rc.values() if c == 1)
    assert sum(1 for c in cnt.values() if c == 1) == open_raw  # no new open edge
    # every new vertex has 4 edges (a ring through a quad cut once), mirror maps new to new, an involution
    deg = collections.Counter(v for e in cnt for v in e)
    assert all(deg[gnmloops.N_RAW + j] == 4 for j in range(k))
    m = P["mirror"] - gnmloops.N_RAW
    assert (m[m] == np.arange(k)).all()
    mi = gnmloops._raw()["mirror"]  # (GNM's own template is symmetric only to ~0.1 mm: the asset's is exact)
    par = P["parents"]
    assert all(set(mi[par[j]].tolist()) == set(par[m[j]].tolist()) for j in range(k))
    g = base._gnm_data()
    # GNM's tables extend by the parents' mean; take() reads them at new ids
    B = g["vertex_identity_basis"][:3]
    assert np.allclose(gnmloops.take(B, np.arange(gnmloops.N_RAW + k), axis=1), gnmloops.ext(B, axis=1), atol=1e-6)


def test_one_mesh_unchanged_by_the_loops():
    """The fused template keeps every old vertex bit-identical (positions, asset ids, order); the built surface moves
    < 0.05 mm anywhere (the subdivision's limit and the kernel widths shift a hair round the new rows); the asset's
    weights still sum to 1 and its uvs stay inside the square."""
    if not _gnm_ok():
        return
    sp = humans.spec(age=40, sex=1.0, seed=3, skin=False, source="human")
    e = expand_mirror(sp)
    out = {}
    try:
        for on in (False, True):
            gnmloops.ENABLED = on
            onemesh._CACHE.pop(("tpl", onemesh._tkey(sp["base"])), None)
            base._CACHE.clear()
            out[on] = (onemesh.template(sp["base"]), base.surface(e, sp["base"]))
    finally:
        gnmloops.ENABLED = True
        base._CACHE.clear()
    (t0, s0), (t1, s1) = out[False], out[True]
    n0 = len(t0["P"])
    assert len(t1["P"]) == n0 + 530 and len(t1["S"]) == len(t0["S"]) + 530
    assert np.array_equal(t0["P"], t1["P"][:n0]) and np.array_equal(t0["fid"], t1["fid"][:n0])
    V0 = s0["verts"]
    d = np.abs(base._sd_body(V0, s1) - base._sd_body(V0, s0))
    assert d.max() < 5e-5, d.max()
    a = onemesh.asset()
    assert np.abs(a["w"].sum(1) - 1).max() < 1e-5 and a["uv"].min() >= 0 and a["uv"].max() <= 1
    # the loops are where they were meant to be: on the pupil's column, between the rows they split
    L = t1["loop_rows"]
    assert len(L) == 530 and (np.asarray(a["gnm_exact"])[t1["fid"][L]] >= gnmloops.N_RAW).all()


if __name__ == "__main__":
    test_loops_are_closed_manifold_and_symmetric()
    test_one_mesh_unchanged_by_the_loops()
    print("ok")
