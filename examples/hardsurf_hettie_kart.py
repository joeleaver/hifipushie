"""Worked example: Hettie's crate kart (Braynard Racing) from her concept's fused point cloud, with the hard-surface tools.

    uv run python examples/hardsurf_hettie_kart.py <fused.ply> <views.npz> <folder>

The point cloud (oxidegen make_point_cloud: fused mesh + its renders) is framed, every part is fitted to it or drawn
off its votes, built, checked, baked and rigged. The numbers below are the artist's decisions, each with its reason;
the `disagree` calls log where the sculpt and the concept (or the game) disagreed. Same result as the oxidegen spike
(artifacts/budget3d_spike/retopo/karts/hettie, landed in braynard-racing 583d296)."""
import json
import math
import sys

import numpy as np

from hifipushie import hardsurf_fit as F
from hifipushie import hardsurf_run as R

fused, views, D = sys.argv[1], sys.argv[2], sys.argv[3]
RUB, STEEL, WOOD = dict(rough=0.9, metal=0.0), dict(rough=0.45, metal=0.9), dict(rough=0.75, metal=0.0)

R.start(D, fused, views)
# a near-square footprint (track ~ wheelbase): PCA can't pick the long axis, so the first turn is given (yaw0); then
# the contact PAIRS square it up; the wheelbase from build.json scales it
fr = R.frame(D, up="y", contact_h=0.04, contacts=4, yaw="pairs", yaw0=0, scale={"pair_gap": 0.82},
            shift=[0, -0.01, 0])      # build.json puts the axles at y -0.42 / +0.40: their midpoint at -0.01
S = R.solid(D, 0.002)

# ---- wheels: contact patches give x / y; a ring fit through the tyre (plane x = const) gives the hub and radius
wheels = {}
for c in fr["contacts"]:
    x, y = c["centre"]; k = ("F" if y < 0 else "R") + ("L" if x > 0 else "R")
    ctr, r, err = F.ring_fit(S, [x, y, 0.2], [1, 0, 0], rmin=0.12, rmax=0.3)
    wheels[k] = dict(c=[x, float(ctr[1]), float(ctr[2])], r=r, w=c["size"][0])
FWD = 0.05     # GAME CALL: the full-width crate blocks the front tyres' steer: the front axle moves 5 cm forward
R.disagree(D, "front axle vs crate", "front tyres 6 cm from the crate", "a full-width crate (character)",
           "front axle assembly 5 cm forward, baked in place (bake_offset)")
parts = []
for ax, (L, Rt) in {"F": ("FL", "FR"), "R": ("RL", "RR")}.items():
    w = wheels[L]
    prof, _ = F.turned_profile(S, w["c"], [1, 0, 0], -w["w"] / 2 + 0.004, w["w"] / 2 + 0.03, w["r"] * 1.25, 0.002, 48, tol=0.0025)
    for k in (L, Rt):
        c = list(wheels[k]["c"]); side = 1 if c[0] > 0 else -1
        if ax == "F": c[1] -= FWD
        parts.append(dict(type="lathe", name=f"wheel_{k}", origin=c, axis=[side, 0, 0], profile=prof, seg=40,
                          nmap=1.0 if ax == "R" else 0.6, **({"bake_offset": [0, FWD, 0]} if ax == "F" else {}), **RUB))
        if ax == "R":     # tractor lugs: the revolution vote averages them away -> modelled as their own radial part
            parts.append(dict(type="radial", name=f"lugs_{k}", origin=c, axis=[side, 0, 0], count=16, r=0.221,
                              size=[0.085, 0.034, 0.03], arms=[[0.048, 24, 0.0], [-0.048, -24, 0.5]], bevel=0.008, nmap=0.3, **RUB))
R.disagree(D, "front beam", "a 17 cm deep oval seen from above (splat bulge)", "a round bar", "round, r 0.045")
yF = -0.42 - FWD
parts += [dict(type="tube", name="beam_F", paths=[[[-0.37, yF, 0.195], [0.37, yF, 0.195]]], r=0.045, seg=16, smooth=False, nmap=0.4, bake_offset=[0, FWD, 0], **STEEL),
          dict(type="tube", name="beam_R", paths=[[[-0.39, 0.40, 0.22], [0.39, 0.40, 0.22]]], r=0.045, seg=16, smooth=False, nmap=0.4, **STEEL),
          dict(type="lathe", name="collar", origin=[0, yF, 0.0], axis=[0, 0, 1], profile=[[0.2, 0], [0.2, 0.06], [0.215, 0.066], [0.255, 0.062], [0.262, 0.04], [0.262, 0]], seg=24, nmap=0.4, bake_offset=[0, FWD, 0], **STEEL)]
# ---- the crate: the y-vote reads planks at z 0.22-0.415 / 0.445-0.565 with a 3 cm slot; the concept's is a thin line
R.disagree(D, "crate planks", "3 cm slot between planks", "a thin dark line", "1 cm gap + corner battens (nothing floats)")
parts.append(dict(type="rbox", name="floor", c=[0, 0.065, 0.212], size=[0.60, 0.59, 0.065], bevel=0.01, bseg=2, nmap=0.6, **WOOD))
for nm, z0, z1 in (("crate_front_lo", 0.22, 0.43), ("crate_front_hi", 0.44, 0.565)):
    parts.append(dict(type="rbox", name=nm, c=[-0.01, -0.205, (z0 + z1) / 2], size=[0.80, 0.062, z1 - z0], bevel=0.016, bseg=3, nmap=1.0, bake_offset=[0, -0.07, 0], **WOOD))
for side, sx in (("L", 0.358), ("R", -0.362)):
    for nm, z0, z1 in (("lo", 0.22, 0.43), ("hi", 0.44, 0.565)):
        parts.append(dict(type="rbox", name=f"crate_{side}_{nm}", c=[sx, -0.006, (z0 + z1) / 2], size=[0.06, 0.348, z1 - z0], bevel=0.016, bseg=3, nmap=1.0, **WOOD))
for nm, x, y in (("batten_FL", 0.312, -0.158), ("batten_FR", -0.316, -0.158), ("batten_RL", 0.312, 0.15), ("batten_RR", -0.316, 0.15)):
    parts.append(dict(type="rbox", name=nm, c=[x, y, 0.39], size=[0.03, 0.03, 0.33], bevel=0.006, bseg=2, nmap=0.8, **WOOD))
# ---- seat: the x-vote of (y, z) sections (print F.vote_text to read it) -> centre profile; the bucket's sides stand
# 4 cm proud (side vote x 0.2..0.26) -> a side profile blended over the outer 45 %
A, B, V = F.profile_vote(S, "x", np.linspace(-0.22, 0.2, 9), (0.1, 0.62, 0.18, 0.75), 0.012)
centre = [(0.15, 0.235), (0.15, 0.36), (0.17, 0.385), (0.40, 0.39), (0.43, 0.42), (0.44, 0.52), (0.45, 0.62), (0.47, 0.675), (0.50, 0.69),
          (0.535, 0.675), (0.555, 0.62), (0.565, 0.5), (0.56, 0.4), (0.55, 0.30), (0.53, 0.235)]
side = [(0.15, 0.235), (0.15, 0.40), (0.17, 0.42), (0.30, 0.425), (0.36, 0.45), (0.40, 0.50), (0.43, 0.60), (0.46, 0.66), (0.50, 0.675),
        (0.53, 0.66), (0.545, 0.60), (0.55, 0.50), (0.545, 0.40), (0.53, 0.235)]
parts.append(F.sweep("seat", centre, -0.29, 0.30, n=56, round_r=0.05, steps=5, mid=9, side=side, nmap=0.8, rough=0.8, metal=0.0))
# ---- steering: column off the collar, the rim tilted to the driver (side view), a T of spokes, a hub
swc, swa = [-0.005, -0.125, 0.715], [0, 0.846, 0.533]
n = np.array(swa) / np.linalg.norm(swa); u = np.array([1.0, 0, 0]); v = np.cross(n, u)
spokes = [[list(np.array(swc) + 0.03 * (math.cos(math.radians(a)) * u + math.sin(math.radians(a)) * v)),
           list(np.array(swc) + 0.165 * (math.cos(math.radians(a)) * u + math.sin(math.radians(a)) * v))] for a in (0, 180, 90)]
parts += [dict(type="tube", name="column", paths=[[[0, yF, 0.25], [-0.005, -0.135, 0.70]]], r=0.026, seg=12, smooth=False, nmap=0.4, **STEEL),
          dict(type="torus", name="steering_wheel", c=swc, axis=swa, R=0.172, r=0.025, seg=40, rseg=10, nmap=0.5, rough=0.8, metal=0.0),
          dict(type="tube", name="steering_spokes", paths=spokes, r=0.014, seg=8, smooth=False, nmap=0.3, rough=0.8, metal=0.0),
          dict(type="lathe", name="steering_hub", origin=swc, axis=swa, profile=[[-0.025, 0], [-0.025, 0.035], [0.0, 0.042], [0.022, 0.03], [0.03, 0]], seg=20, nmap=0.3, rough=0.8, metal=0.0)]
R.put_parts(D, parts)
out = {"frame": fr, "wheels": wheels, "build": R.build(D), "check": R.check(D)}
out["bake"] = R.bake(D)
# ---- rig: generic rigid joints. Spinners on the hubs, hinges at the kingpins with the other kingpin and the steering
# wheel FOLLOWING (ratio 1 and 1/0.3), the body on a slider (bounce)
body = [p["name"] for p in parts if not p["name"].startswith(("wheel_", "lugs_", "beam_", "steering_"))]
J = []
for k, w in wheels.items():
    c = list(w["c"]); side = 1 if c[0] > 0 else -1
    if k[0] == "F":
        c[1] -= FWD; kp = [c[0] - side * (w["w"] / 2 + 0.02), c[1], c[2]]
        J.append(dict(name=f"pivot_{k}", kind="hinge", parts=[], pivot=kp, axis=[0, 0, 1], range=[-26, 26],
                      **({} if k == "FL" else {"follows": {"joint": "pivot_FL", "ratio": 1.0}})))
        J.append(dict(name=f"spin_{k}", kind="spinner", parts=[f"wheel_{k}"], pivot=c, axis=[side, 0, 0], parent=f"pivot_{k}", range=[-90, 90]))
    else:
        J.append(dict(name=f"spin_{k}", kind="spinner", parts=[f"wheel_{k}", f"lugs_{k}"], pivot=c, axis=[side, 0, 0], range=[-90, 90]))
J.append(dict(name="body", kind="slider", parts=body + ["column"], pivot=[0, 0, 0.25], axis=[0, 0, 1], range=[-0.03, 0.03]))
J.append(dict(name="steering", kind="hinge", parts=["steering_wheel", "steering_spokes", "steering_hub"], pivot=swc, axis=swa,
              parent="body", range=[-87, 87], follows={"joint": "pivot_FL", "ratio": 1 / 0.3}))
out["rig"] = R.rig(D, J)
json.dump(out, open(R.folder(D) / "example_report.json", "w"), indent=1, default=str)
print(json.dumps({k: (v if k != "rig" else v["joints"]) for k, v in out.items() if k in ("check", "bake", "rig")}, default=str)[:3000])
