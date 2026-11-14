"""Rendering the standard shots, and the self-checks a run must pass before it is reported. Part of the judge (judge.py has the overview)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np

from . import judge
from .judge_glb import _engine_sides, glb_merged_faces, glb_triangles, read_glb, uv_probes

# ------------------------------------------------------------------ rendering
def _shots_job(head: str | None) -> list:
    photo = {}
    if head:
        from . import skin_read_frames
        for v, vi in judge.PHOTO_VIEWS.items():
            try:
                photo[v] = skin_read_frames.photo_light(head, _photo_index(head, vi))
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"judge: no photo light for {head} view {v}: {e}")
    out = []
    for s in judge.SHOTS:
        for lt in s["lights"]:
            if lt == "photo" and not head:
                continue
            base = {k: s[k] for k in ("focus", "lift", "dist", "fov", "w", "h")}
            if lt == "photo":  # one shot per view: each view under its own photo's fitted light
                for v in s["views"]:
                    out.append({**base, "name": f"{s['name']}-photo-{v.replace('_', '')}", "views": [v],
                                "lighting": photo[v]})
            else:
                out.append({**base, "name": f"{s['name']}-{lt}", "views": list(s["views"])})
    return out


def _photo_index(head: str, yaw: float) -> int:
    from . import store
    refs = json.loads((store.HOME / head / "human_refs.json").read_text())
    ys = [abs(float(v.get("yaw", 0))) for v in refs["views"]]
    return int(np.argmin([abs(y - yaw) for y in ys]))


def render(glb, out: Path, head: str | None = None, timeout: float = 1800, swap: dict | None = None) -> dict:
    """The standard shots of a GLB into out/renders, with blender_game's audit; returns the audit."""
    from . import render as R, resources
    glb = Path(glb).resolve()
    out = Path(out)
    (out / "renders").mkdir(parents=True, exist_ok=True)
    probes, ours = uv_probes(glb, skip=list(swap or {}))
    for g in (swap or {}).values():
        p2, o2 = uv_probes(g)
        probes += p2
        ours["ours"] += o2["ours"]; ours["flipped"] += o2["flipped"]; ours["mesh"] += ",swap:" + o2.get("mesh", "")
    job = {"glb": str(glb), "out": str(out / "renders" / "r"), "shots": _shots_job(head), "transparent": True,
           "audit": str(out / "audit.json"), "uv_probe": probes,
           # NOT merged: merging welds a card's explicit back face onto its front and Blender drops it as a duplicate
           # (rc2n: hair 24,520 -> 14,110 triangles drawn); judge shots are at rest, so the merge's shape-normal fix
           # isn't needed
           "merge_vertices": False,
           "cull": {**_engine_sides(glb), **{k: v for g in (swap or {}).values() for k, v in _engine_sides(g).items()}},
           "swap": {k: str(Path(v).resolve()) for k, v in (swap or {}).items()}}  # drawn as an engine draws it: back faces culled unless doubleSided
    (out / "uv_ours.json").write_text(json.dumps(ours))
    jp = out / "job.json"
    jp.write_text(json.dumps(job, default=float))
    script = Path(__file__).with_name("blender_game.py")
    cmd = [R.BLENDER, "-b", *R._threads(), "--factory-startup", "--python-exit-code", "1", "--python", str(script),
           "--", str(jp)]
    capped = "/mnt/data/hifipushie/bin/capped"
    if os.path.exists(capped):
        cmd = [capped, *cmd]
    with resources.heavy(f"judge {glb.name}", gb=float(os.environ.get("JUDGE_GB", "8"))):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, "CAP": os.environ.get("CAP", "12G")})
    (out / "blender.log").write_text(r.stdout[-200000:] + "\n" + r.stderr[-20000:])
    if r.returncode:
        raise RuntimeError(f"judge: blender failed ({r.returncode}); see {out / 'blender.log'}\n{r.stdout[-2000:]}")
    return json.loads((out / "audit.json").read_text())


# ------------------------------------------------------------------ self-checks on a run
def check_run(glb, out: Path, swap: dict | None = None) -> list:
    """The render-side self-checks: [(name, ok, detail)]."""
    out = Path(out)
    if swap is None and (out / "meta.json").exists():
        swap = json.loads((out / "meta.json").read_text()).get("swap")
    au = json.loads((out / "audit.json").read_text())
    ours = json.loads((out / "uv_ours.json").read_text())
    js, _ = read_glb(glb)
    res = []
    # 1. uv orientation: Blender's reading of each probe == ours; the flipped reading must be clearly worse
    pr = [p for p in au["probes"] if "rgb" in p]
    if not pr or len(pr) != len(ours["ours"]):
        res.append(("uv_orientation", False, f"{len(pr)} probes located of {len(ours.get('ours', []))}"))
    else:
        bl = np.array([p["rgb"] for p in pr])
        d = np.abs(bl - np.array(ours["ours"])).max(1)
        dfl = np.abs(bl - np.array(ours["flipped"])).max(1)
        far = np.array([p["dist"] for p in pr])
        ok = np.median(d) < 0.02 and (d < 0.06).mean() > 0.9 and np.median(dfl) > 3 * max(np.median(d), 0.005)
        res.append(("uv_orientation", bool(ok), f"median |ours - blender| {np.median(d):.4f} (flipped {np.median(dfl):.4f}), "
                    f"{(d < 0.06).mean():.0%} within 0.06, probe-to-surface p90 {np.percentile(far, 90) * 1000:.3f} mm, "
                    f"{ours['image']} on {ours['mesh']}"))
    # 2. triangles drawn == the GLB's, per mesh (less the faces Blender can't hold: explicit back faces, drawn by the
    # two-sided material instead, and degenerate ones)
    _, binc = read_glb(glb)
    gt, mf = glb_triangles(js), glb_merged_faces(js, binc)
    for k, g in (swap or {}).items():
        gt.pop(k, None)
        j2, b2 = read_glb(g)
        for k2, v2 in glb_triangles(j2).items():
            gt[k2] = gt.get(k2, 0) + v2
        mf.update(glb_merged_faces(j2, b2))
    bt = {}
    for o in au["objects"].values():
        if not o["hide_render"]:
            bt[o["mesh"].split(".")[0]] = bt.get(o["mesh"].split(".")[0], 0) + o["triangles"]
    bad = {k: (v, bt.get(k), mf[k]) for k, v in gt.items() if bt.get(k) != v - mf[k]["back"] - mf[k]["degenerate"]}
    nb = sum(v["back"] for v in mf.values())
    res.append(("triangles", not bad, f"GLB {sum(gt.values())}, drawn {sum(bt.values())} + {nb} explicit back faces "
                f"(drawn by two-sided materials) + {sum(v['degenerate'] for v in mf.values())} degenerate"
                + (f"; DIFFER (glb, drawn, merged) {dict(list(bad.items())[:6])}" if bad else "")))
    # 3. sidedness as the engine draws it: a doubleSided material never culled, a single-sided one culled
    ds = {**_engine_sides(glb), **{k: v for g in (swap or {}).values() for k, v in _engine_sides(g).items()}}
    wrong = []
    for name, o in au["objects"].items():
        want = ds.get(o["mesh"].split(".")[0])
        if want is None:
            continue
        for k, c in enumerate(o["culling"]):
            w = want[k] if k < len(want) else want[-1]
            if c is not None and bool(c) == bool(w):
                wrong.append(f"{name}[{k}] {'culled' if c else 'not culled'} (doubleSided {w})")
    res.append(("sidedness", not wrong, "; ".join(wrong[:8]) if wrong else
                f"{sum(len(v) for v in ds.values())} primitives as the engine draws them "
                f"({sum(sum(v) for v in ds.values())} two-sided: doubleSided or explicit back faces)"))
    # 4. one state per light set (every shot of the "game" set drawn under the same view + rig)
    st = {}
    for r in au["renders"]:
        key = Path(r["file"]).stem.split("_")[1]  # r_<shot>_<view>
        lt = key.split("-")[1] if "-" in key else "game"
        st.setdefault(lt if lt != "photo" else key, set()).add(state_sig(r))
    multi = {k: len(v) for k, v in st.items() if len(v) != 1}
    res.append(("render_state", not multi, f"{len(au['renders'])} renders; light sets {sorted(st)}" + (f"; MIXED {multi}" if multi else "")))
    return res


def state_sig(r: dict) -> str:
    return hashlib.sha1(json.dumps({k: v for k, v in r.items() if k != "file"}, sort_keys=True).encode()).hexdigest()[:12]
