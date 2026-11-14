"""judge: ONE validated way to judge a game asset (docs/notes/judge.md; gates.md "Process rules (2026-10-19)").

Why: rounds were wasted on unvalidated measures (uvs read upside down, AgX vs PBR Neutral renders compared, a
preview drawing cards half-sided, a photo mask dropping highlights, the wrong reference, swapped reviewer labels).
So every run re-validates itself and REFUSES to report when a check fails.

  shots(glb, out, head=...)   the standard cameras (SHOTS) under the named lights (game rig; photo_light for the
                              likeness close-ups), rendered by blender_game.py (the GLB re-imported, the engine's
                              materials from the shading notes, two-sided), RGBA; the feature crops cut by MediaPipe
                              landmarks (face) or centred on a bone (crown, nape, collar, cuffs); <= 512 px, native
                              pixels for the 1 m / 3 m game-distance crops. Self-checks: uv orientation (a known texel
                              lands on its surface point, read our way and Blender's way), triangles drawn == the
                              GLB's, two-sided materials, every render's view transform / light recorded.
  measure(run, ref)           per crop: L* p10 / p50 / p90, chroma p50, a mid-scale blotch std, edge (outline)
                              difference vs the reference (a run of another GLB at the same cameras, or the photo
                              crops of the head's references, aligned by their own landmarks). Before reporting:
                              the reference against itself gives ~0 on every measure, a planted dark blot is found
                              (where it was put), and the compared renders' states (view, light) are identical.
  ab(old, new, out, ref)      blind trios (ref | X | Y) of the SAME crops through bin/review-ab, plus two CONTROL
                              trios (the reference itself as one candidate, once as "old", once as "new"): a review
                              whose key-applied controls don't pick the reference is refused (labels swapped / the
                              reviewer didn't look).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at judge.NAME: C422). judge_glb: the GLB, read our way: the container, accessors, triangles, images, texels,
UV probes, merged and double-sided faces. judge_render: rendering the standard shots, and the self-checks a run must
pass before it is reported. judge_crops: feature crops: detection, boxes, the crops of a run and of the head's photos.
judge_measures: the measures (absolute, against another run, against the photos), their self-check, and the report.
judge_ab: blind A/B with controls: the trios, the key, the review's score.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from . import moved

ROOT = Path(os.environ.get("HIFIPUSHIE_JUDGE_DIR", "/mnt/data/hifipushie/judge"))
REVIEW_AB = os.environ.get("HIFIPUSHIE_REVIEW_AB", "/mnt/data/hifipushie/bin/review-ab")
CROP_MAX = 512          # every crop's longest side (px)
FEATURE_PX = 384        # face feature crops are resized to this longest side (render and photo alike)
GAME = None             # blender_game's game rig (light_rig(None)): hard key + fill + back suns, PBR Neutral

# The game-distance frame (gates.md "Game distance"): 1920x1080, vertical fov 59 deg, crops at native pixels.
_GD = {"w": 1920, "h": 1080, "fov": 59.0}
SHOTS = [
    # name, views, focus bone, lift (m), dist (m), fov, w, h, lights, crops
    {"name": "g1m", "views": ["front", "three_quarter", "side", "back"], "focus": "Head", "lift": 0.0, "dist": 1.0,
     **_GD, "lights": ["game"], "crop": [384, 512]},
    {"name": "g3m", "views": ["front", "three_quarter", "side", "back"], "focus": "Hips", "lift": 0.15, "dist": 3.0,
     **_GD, "lights": ["game"], "crop": [320, 512]},
    {"name": "face", "views": ["front", "three_quarter"], "focus": "Head", "lift": 0.0, "dist": 0.6, "fov": 30.0,
     "w": 1024, "h": 1024, "lights": ["game", "photo"], "features": True},
    {"name": "crown", "views": ["top", "back_quarter"], "focus": "HeadTop_End", "lift": -0.03, "dist": 0.6,
     "fov": 30.0, "w": 512, "h": 512, "lights": ["game"]},
    {"name": "nape", "views": ["back"], "focus": "Neck", "lift": 0.06, "dist": 0.5, "fov": 30.0, "w": 512, "h": 512,
     "lights": ["game"]},
    {"name": "collar", "views": ["front", "three_quarter"], "focus": "Neck", "lift": -0.04, "dist": 0.5, "fov": 30.0,
     "w": 512, "h": 512, "lights": ["game"]},
    {"name": "cuffs", "views": ["front"], "focus": "LeftHand", "lift": 0.0, "dist": 0.45, "fov": 30.0, "w": 512,
     "h": 512, "lights": ["game"]},
]
# Face features: centre = mean of these MediaPipe (478) landmarks, box = half sizes x the outer-canthus distance
# (33 - 263), so the render's and the photo's crops cover the same part of the face whatever their scale.
FEATURES = {
    "eyes": ([33, 133, 362, 263], 0.80, 0.30),
    "brows": ([70, 105, 107, 300, 334, 336], 0.85, 0.24),
    "nose": ([1, 2, 98, 327, 168], 0.36, 0.42),
    "mouth": ([61, 291, 0, 17], 0.50, 0.32),
    "hairline": ([10], 0.90, 0.32, -0.30),   # (4th: the centre shifted up by this x the canthus distance)
}
# views whose face crops are compared with the reference photos (the photo's own view index by yaw)
PHOTO_VIEWS = {"front": 0, "three_quarter": 45}

_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

# ------------------------------------------------------------------ the report
ROW_KEYS = ("L10", "L50", "L90", "C50", "blotch", "spot", "edge", "sharp", "outline")


# ------------------------------------------------------------------ the whole run
def run_dir(glb, tag: str | None = None, swap: dict | None = None) -> Path:
    h = hashlib.sha1("|".join(f"{Path(g).resolve()}:{Path(g).stat().st_mtime_ns}:{Path(g).stat().st_size}"
                              for g in [glb, *sorted((swap or {}).values())]).encode()).hexdigest()[:8]
    glb = Path(glb).resolve()
    return ROOT / "runs" / f"{tag or glb.stem}_{h}"


def shots(glb, head: str | None = None, tag: str | None = None, boxes_from=None, force: bool = False,
          swap: dict | None = None) -> Path:
    """Render (cached per GLB content), cut the crops, run the render self-checks (checks.json). Returns the run dir.
    swap {mesh: glb}: that part replaced by another GLB's meshes (same world frame), e.g. a hair build on the character."""
    from . import judge_crops, judge_render
    out = run_dir(glb, tag, swap)
    if force or not (out / "audit.json").exists():
        judge_render.render(glb, out, head, swap=swap)
    checks = judge_render.check_run(glb, out, swap or {})
    (out / "checks.json").write_text(json.dumps(checks))
    judge_crops.crops(out, boxes_from)
    (out / "meta.json").write_text(json.dumps({"glb": str(Path(glb).resolve()), "head": head, "tag": tag, "swap": swap}))
    return out


CTL_OLD, CTL_NEW = "_b", "_c"   # control items: <crop>_b = the reference as "old", <crop>_c = as "new"

# ------------------------------------------------------------------ CLI (bin/judge)
USAGE = """judge: validated standard shots, measures and blind A/B (docs/notes/judge.md)
  judge shots <glb> [--head <approved head model>] [--tag t] [--force] [--swap mesh=<glb>]
                                                           render + crops + render self-checks
  judge report <glb|run> [--ref <glb|run>] [--head <model>] [--only eyes,mouth]
                                                           measures (abs, vs the ref build, vs the photo crops)
  judge ab <old glb|run> <new glb|run> <out dir> [--ref <glb|run>] [--head <model>] [--only ...] [--dry]
  judge score <ab out>/review                              a subagent's review.md: key applied, controls checked
  judge approved <stage> <piece>                           the approved piece (approve get), as judge sees it
--head: the approved head model (approve get head <who>), e.g. tp_k19 / gp_h6c: its reference photos and photo light."""


def _as_run(x, head=None, tag=None, boxes_from=None):
    p = Path(x)
    if p.is_dir() and (p / "crops.json").exists():
        return p
    return shots(p, head=head, tag=tag, boxes_from=boxes_from)


def main(argv=None):
    from . import judge_ab, judge_crops, judge_measures
    import argparse
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    ap = argparse.ArgumentParser(usage=USAGE)
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--head")
    ap.add_argument("--tag")
    ap.add_argument("--ref")
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--context", default="")
    ap.add_argument("--swap", action="append", default=[], help="mesh=glb: that part replaced by another GLB's meshes")
    o = ap.parse_args(a)
    only = o.only.split(",") if o.only else None
    try:
        if o.cmd == "shots":
            sw = dict(x.split("=", 1) for x in o.swap) or None
            r = shots(o.args[0], head=o.head, tag=o.tag, force=o.force, swap=sw)
            ch = json.loads((r / "checks.json").read_text())
            print("\n".join(f"{'ok  ' if c[1] else 'FAIL'} {c[0]}: {c[2]}" for c in ch))
            print(f"run: {r}  ({len(json.loads((r / 'crops.json').read_text()))} crops in {r / 'crops'})")
            return 0 if all(c[1] for c in ch) else 5
        if o.cmd == "report":
            ref = _as_run(o.ref, o.head) if o.ref else None
            run = _as_run(o.args[0], o.head, boxes_from=ref)
            if ref is not None:
                judge_crops.crops(run, ref)
            print(judge_measures.format_report(judge_measures.report(run, ref, o.head, only)))
            return 0
        if o.cmd == "ab":
            ref = _as_run(o.ref, o.head) if o.ref else None
            old = _as_run(o.args[0], o.head, boxes_from=ref)
            new = _as_run(o.args[1], o.head, boxes_from=ref or old)
            for r_ in (old, new):
                if ref is not None or r_ is new:
                    judge_crops.crops(r_, ref or old)
            res = judge_ab.ab(old, new, o.args[2], ref, o.head, only, o.context, o.dry)
            if res.get("dry"):
                print("review-ab not run" + (f" ({res['error']})" if res.get("error") else "") + ". Give a FRESH blind "
                      f"subagent {o.args[2]}/review/prompt.md (nothing else), then: judge score {o.args[2]}/review\n")
                print(res["prompt"])
                return 4
            print(json.dumps({k: res[k] for k in ("regions", "votes", "controls_ok", "verdict")}, indent=1))
            return 0 if res["controls_ok"] else 6
        if o.cmd == "score":
            res = judge_ab.apply_key(Path(o.args[0]))
            print(json.dumps(res, indent=1))
            return 0 if res["controls_ok"] else 6
        if o.cmd == "approved":
            r = subprocess.run(["/mnt/data/hifipushie/bin/approve", "get", *o.args], capture_output=True, text=True)
            print(r.stdout.strip() or "(none)")
            return r.returncode
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 5
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("judge_glb", "judge_render", "judge_crops", "judge_measures", "judge_ab")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
