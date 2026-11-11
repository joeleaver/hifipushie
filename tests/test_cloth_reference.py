"""The garment reading checklist (cloth_checklist.json) and cloth_reference's camera, readings and measures, on
synthetic bodies and garments. No sim, no Blender.
uv run python tests/test_cloth_reference.py"""
import json

import numpy as np

from hifipushie import cloth_reference as cr, garment_design


class FakeBody:
    """A standing figure's landmarks without a mesh build: Body.at / Body.J / V / T as cloth.Body has them."""

    def __init__(self):
        self.J = {"neck": np.array([0, -0.01, 1.55]), "elbow.L": np.array([0.30, 0, 1.21]),
                  "wrist.L": np.array([0.43, -0.02, 0.98]), "knee.L": np.array([0.14, -0.03, 0.54]),
                  "knee.R": np.array([-0.14, -0.03, 0.54]), "ankle.L": np.array([0.16, -0.01, 0.07]),
                  "ankle.R": np.array([-0.16, -0.01, 0.07]), "lm_chin": np.array([0, -0.09, 1.62])}
        self.at = {"shoulder.L": np.array([0.22, 0, 1.48]), "cf_neck": np.array([0, -0.11, 1.55]), "armpit_z": 1.36,
                   "chest_z": 1.34, "waist_z": 1.13, "hips_z": 0.97, "seat_z": 0.92, "crotch_z": 0.88}
        # a box torso: front face at y = -0.12 (the chest's front)
        z = np.linspace(0.0, 1.84, 40)
        self.V = np.array([[x, y, zz] for zz in z for x in (-0.15, 0.15) for y in (-0.12, 0.10)], float)
        self.T = np.array([[0, 1, 2]])


def _tube(cx, cy, r, z0, z1, n=24, m=30):
    """A vertical tube (a sleeve, a leg, a torso): vertices and triangles."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    zs = np.linspace(z0, z1, m)
    V = np.array([[cx + r * np.cos(t), cy + r * np.sin(t), z] for z in zs for t in a])
    F = []
    for i in range(m - 1):
        for j in range(n):
            p, q = i * n + j, i * n + (j + 1) % n
            F += [[p, q, p + n], [q, q + n, p + n]]
    return V, np.array(F)


def test_guide_topic():
    from hifipushie import server
    assert "points-of-measure" in server.guide("cloth_reference") or "POM" in server.guide("cloth_reference")


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)

