"""A river added to ground the design already made cuts its own valley and leaves the land away from it alone
(pushieworld note 115: a beck down the volcano's flank, its bed heights read off the old ground, raised 122 ha by over
5 m, up to +69 m). Also: an unknown river key is a warning, not silently dropped.
uv run python tests/test_river_cut.py"""
import copy
import time

import numpy as np

from hifipushie import terrain

SPEC = {"world": {"kind": "coast", "base": 14}, "extent": [[0, 0], [512, 512]], "cell": 4.0,
        "sea": {"level": 0, "land": "isle", "depth": 20, "shore": "rocky"},
        "zones": {"isle": {"polygon": [[40, 60], [470, 40], [490, 470], [60, 490]]}},
        "peaks": {"knob": {"at": [360, 330], "h": 110, "radius": 120}},
        "rivers": {"main": {"source": [30, 480, 40], "through": [[200, 250]], "mouth": [480, 30, 2],
                            "valley": {"profile": "open", "floor": 40}}},
        "cover": [{"type": "meadow", "in": "everywhere"}]}
BECK = [[360, 420], [300, 430], [240, 470]]  # down the knob's north flank, away from the main river


class _Stop(Exception):
    pass


def base(spec):
    """The ground right after the harmonic base (before erosion and the rest: what the river's solve decides)."""
    keep = {}
    orig = terrain.Terrain._texture

    def stop(self):
        keep["T"] = self
        raise _Stop
    terrain.Terrain._texture = stop
    try:
        terrain.Terrain(copy.deepcopy(spec))
    except _Stop:
        pass
    finally:
        terrain.Terrain._texture = orig
    return keep["T"]


def with_beck(A, **extra):
    s = copy.deepcopy(SPEC)
    z = A.sample(np.array(BECK, float))
    s["rivers"]["beck"] = {"source": [*BECK[0], float(z[0])], "through": [[*p, float(h)] for p, h in zip(BECK[1:-1], z[1:-1])],
                           "mouth": [*BECK[-1], float(z[-1])], **extra}
    return s


def _far(T, name, r):
    L = T.lines[name]
    from scipy.spatial import cKDTree
    d = cKDTree(L.xy).query(T.P)[0].reshape(T.X.shape)
    return d > r


def test_new_river_leaves_land_alone(A):
    B = base(with_beck(A))
    assert "beck" in B._cut_rivers and B._cut_rivers - {"beck"} == A._cut_rivers, (A._cut_rivers, B._cut_rivers)
    L = B.lines["beck"]
    D = B.H - A.H
    assert D.max() < 0.05, f"the beck raised ground by {D.max():.1f} m"
    # its own valley: the ground at its bed, the valley about floor + its sides wide
    assert np.percentile(B.sample(L.xy) - L.h, 90) < 1.0, np.percentile(B.sample(L.xy) - L.h, 90)
    # the valley's width: its floor and both sides up from the deepest cut (+ the shoulder's ~6 m) at its grade
    cut = float(np.max(A.sample(L.xy) - B.sample(L.xy)))
    width = L.props["floor"] + 2 * (cut + 6.0) / max(L.props["side"], 0.3)
    far = _far(B, "beck", 2 * width)
    assert np.abs(D[far]).max() < 0.05, np.abs(D[far]).max()
    print(f"ok new river leaves the land alone (valley ~{width:.0f} m wide; beyond 2x: max |dz| "
          f"{np.abs(D[far]).max():.3f} m; cut {D.min():.1f} m)")


def test_cut_false_is_the_old_solve(A):
    B = base(with_beck(A, valley={"cut": False}))
    assert "beck" not in B._cut_rivers
    print(f"ok valley.cut false: the river holds the solve's low ground (as before; ground moved up to "
          f"{np.abs(B.H - A.H).max():.1f} m)")


def test_unknown_key_warns():
    s = copy.deepcopy(SPEC)
    s["rivers"]["main"]["cascades"] = [1]
    T = base(s)
    assert any("unknown key" in w and "cascades" in w for w in T.warnings), T.warnings
    print("ok unknown river key warns")


if __name__ == "__main__":
    t = time.time()
    A = base(SPEC)
    test_new_river_leaves_land_alone(A)
    test_cut_false_is_the_old_solve(A)
    test_unknown_key_warns()
    print(f"all ok {time.time() - t:.0f} s")
