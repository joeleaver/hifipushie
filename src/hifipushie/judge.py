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
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

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


# ------------------------------------------------------------------ the GLB, read our way

def read_glb(path) -> tuple[dict, bytes]:
    b = Path(path).read_bytes()
    magic, _, _ = struct.unpack_from("<III", b, 0)
    if magic != 0x46546C67:
        raise ValueError(f"{path}: not a GLB")
    off, js, binc = 12, None, b""
    while off < len(b):
        n, kind = struct.unpack_from("<II", b, off)
        chunk = b[off + 8: off + 8 + n]
        if kind == 0x4E4F534A:
            js = json.loads(chunk)
        elif kind == 0x004E4942:
            binc = chunk
        off += 8 + n
    return js, binc


_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def accessor(js, binc, i) -> np.ndarray:
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    dt = np.dtype(_CT[a["componentType"]])
    nc = _NC[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0) or dt.itemsize * nc
    raw = np.frombuffer(binc, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * nc, offset=start)
    out = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * nc), (stride, 1)).copy()
    out = out.view(dt).reshape(a["count"], nc)
    if a.get("normalized") and dt != np.float32:
        out = out.astype(np.float32) / np.iinfo(dt).max
    return out if nc > 1 else out[:, 0]


def glb_triangles(js) -> dict:
    """Triangles per mesh name, counted once per node that draws the mesh (mode 4; indexed or not)."""
    per = {}
    for nd in js.get("nodes", []):
        if "mesh" not in nd:
            continue
        m = js["meshes"][nd["mesh"]]
        n = 0
        for p in m["primitives"]:
            if p.get("mode", 4) != 4:
                continue
            cnt = js["accessors"][p["indices"]]["count"] if "indices" in p else js["accessors"][p["attributes"]["POSITION"]]["count"]
            n += cnt // 3
        per[m.get("name", f"mesh{nd['mesh']}")] = per.get(m.get("name", f"mesh{nd['mesh']}"), 0) + n
    return per


def glb_image(js, binc, glb_path, ti):
    from PIL import Image
    import io
    img = js["images"][js["textures"][ti]["source"]]
    if "bufferView" in img:
        bv = js["bufferViews"][img["bufferView"]]
        data = binc[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        im = Image.open(io.BytesIO(data))
    else:
        im = Image.open(Path(glb_path).parent / img["uri"])
    return im, img.get("name") or Path(img.get("uri", "")).stem


def texel_at(arr: np.ndarray, uv) -> np.ndarray:
    """THE uv reader (bilinear, texel centres at half pixels). glTF texcoords: origin at the image's TOP-left, v down,
    so row = v * H. (trimesh flips them to v-up on load: never `1 - v` on trimesh's uvs; r70's mis-read.)"""
    H, W = arr.shape[:2]
    fx, fy = uv[:, 0] * W - 0.5, uv[:, 1] * H - 0.5
    i0, j0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = (fx - i0)[:, None], (fy - j0)[:, None]
    def g(i, j):
        return arr[np.clip(j, 0, H - 1), np.clip(i, 0, W - 1)]
    return ((1 - tx) * (1 - ty) * g(i0, j0) + tx * (1 - ty) * g(i0 + 1, j0) + (1 - tx) * ty * g(i0, j0 + 1)
            + tx * ty * g(i0 + 1, j0 + 1))


def _engine_sides(glb) -> dict:
    """Per mesh, per primitive: drawn two-sided? (doubleSided, or explicit back faces Blender will drop)."""
    js, binc = read_glb(glb)
    mf = glb_merged_faces(js, binc)
    return {k: [bool(x) or mf.get(k, {}).get("back", 0) > 0 for x in v] for k, v in glb_double_sided(js).items()}


def uv_probes(glb, n=40, seed=0, min_tris=500, skip=()) -> tuple[list, dict]:
    """Points on every textured mesh (>= min_tris): triangle centroids (glTF-local positions) on textured spots, the
    base colour read there OUR way (texel_at on the raw glTF uv), and the same read with v flipped (to prove the probe
    tells the two apart). Blender reads the same points its own way (blender_game's audit)."""
    js, binc = read_glb(glb)
    rng = np.random.default_rng(seed)
    probes, ours, flips, meshes, images = [], [], [], [], {}
    for m in js["meshes"]:
        for p in m["primitives"][:1]:
            mat = js["materials"][p["material"]] if "material" in p else {}
            bt = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
            if bt is None or "TEXCOORD_0" not in p["attributes"] or bt.get("texCoord", 0) != 0 or "indices" not in p:
                continue
            F = accessor(js, binc, p["indices"]).reshape(-1, 3)
            if len(F) < min_tris or m.get("name") in skip:
                continue
            X = accessor(js, binc, p["attributes"]["POSITION"]).astype(float)
            U = accessor(js, binc, p["attributes"]["TEXCOORD_0"]).astype(float)
            ti = bt["index"]
            si = js["textures"][ti]["source"]
            if si not in images:
                im, iname = glb_image(js, binc, glb, ti)
                images[si] = (np.asarray(im.convert("RGB"), np.float32) / 255.0, iname or f"Image_{si}")
            arr, iname = images[si]
            pick = rng.choice(len(F), size=min(len(F), 40 * n), replace=False)
            c, uv = X[F[pick]].mean(1), U[F[pick]].mean(1)
            var = np.abs(texel_at(arr, U[F[pick, 0]]) - texel_at(arr, U[F[pick, 1]])).sum(1)
            area = np.linalg.norm(np.cross(X[F[pick, 1]] - X[F[pick, 0]], X[F[pick, 2]] - X[F[pick, 0]]), axis=1)
            order = np.argsort(-(var * (area > np.percentile(area, 30))))[:n]
            ours += texel_at(arr, uv[order]).tolist()
            flips += texel_at(arr, np.c_[uv[order, 0], 1.0 - uv[order, 1]]).tolist()
            probes += [{"mesh": m.get("name"), "image": iname, "local": c[k].tolist()} for k in order]
            meshes.append(m.get("name"))
    if not probes:
        return [], {"error": "no textured mesh", "ours": [], "flipped": []}
    return probes, {"ours": ours, "flipped": flips, "mesh": ",".join(meshes), "image": "base colour"}


def glb_merged_faces(js, binc) -> dict:
    """mesh name -> {"back": triangles that repeat another's corners (an explicit back face: same vertices, reversed),
    "degenerate": triangles with a repeated corner}. Blender can't hold either (one face per vertex set), so its
    import drops them: the drawn count is the GLB's minus these, and a mesh with explicit back faces must then be drawn
    two-sided, or a judge render shows the cards half-sided."""
    out = {}
    for m in js["meshes"]:
        b = d = 0
        for p in m["primitives"]:
            if "indices" not in p or p.get("mode", 4) != 4:
                continue
            F = accessor(js, binc, p["indices"]).reshape(-1, 3).astype(np.int64)
            deg = (F[:, 0] == F[:, 1]) | (F[:, 1] == F[:, 2]) | (F[:, 0] == F[:, 2])
            S = np.sort(F[~deg], 1)
            _, cnt = np.unique(S, axis=0, return_counts=True)
            b += int((cnt - 1).sum())
            d += int(deg.sum())
        out[m.get("name")] = {"back": b, "degenerate": d}
    return out


def glb_double_sided(js) -> dict:
    """mesh name -> [doubleSided per primitive's material] (what an engine culls)."""
    out = {}
    for m in js["meshes"]:
        out[m.get("name")] = [bool(js["materials"][p["material"]].get("doubleSided", False)) if "material" in p else False
                              for p in m["primitives"]]
    return out


# ------------------------------------------------------------------ rendering

def _shots_job(head: str | None) -> list:
    photo = {}
    if head:
        from . import skin_read
        for v, vi in PHOTO_VIEWS.items():
            try:
                photo[v] = skin_read.photo_light(head, _photo_index(head, vi))
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"judge: no photo light for {head} view {v}: {e}")
    out = []
    for s in SHOTS:
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


# ------------------------------------------------------------------ crops

def _detect(img):
    from . import likeness
    P = likeness.detect([img.convert("RGB")])[0]
    if P is None:  # a small face in a big frame: once more on the alpha / centre box
        return None
    return np.asarray(P, float)


def feature_boxes(P: np.ndarray) -> dict:
    iod = float(np.linalg.norm(P[33] - P[263]))
    out = {}
    for name, spec in FEATURES.items():
        idx, hw, hh = spec[:3]
        c = P[idx].mean(0) + np.array([0.0, (spec[3] if len(spec) > 3 else 0.0) * iod])
        out[name] = [c[0] - hw * iod, c[1] - hh * iod, c[0] + hw * iod, c[1] + hh * iod]
    return out


def _crop(im, box, size=None):
    from PIL import Image
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    c = im.crop((x0, y0, x1, y1))
    if size is not None:
        c = c.resize(size, Image.LANCZOS)
    return c


def _fit(w, h, m=FEATURE_PX):
    s = m / max(w, h)
    return (max(1, int(round(w * s))), max(1, int(round(h * s))))


def crops(out: Path, boxes_from: Path | None = None) -> dict:
    """Cut the crops of a run: out/crops/<shot>__<view>[__<feature>].png + crops.json {name: {file, state, box}}.
    boxes_from: another run whose face boxes are reused (the same camera: the same pixels compared)."""
    from PIL import Image
    out = Path(out)
    au = json.loads((out / "audit.json").read_text())
    states = {Path(r["file"]).name: state_sig(r) for r in au["renders"]}
    prev = json.loads((Path(boxes_from) / "crops.json").read_text()) if boxes_from else {}
    (out / "crops").mkdir(exist_ok=True)
    table = {}
    for f in sorted((out / "renders").glob("r_*.png")):
        shot, view = f.stem[2:].split("_", 1)  # r_<shot>_<view>: shot names carry no "_"
        base = shot.split("-")[0]
        spec = next(s for s in SHOTS if s["name"] == base)
        im = Image.open(f)
        if spec.get("features"):
            boxes = {}
            for feat in FEATURES:
                k = f"{shot}__{view}__{feat}"
                if "box" in prev.get(k, {}):
                    boxes[feat] = prev[k]["box"]
            if len(boxes) < len(FEATURES):
                P = _detect(_flat(im))
                if P is None:
                    table[f"{shot}__{view}"] = {"error": "no face found"}
                    continue
                boxes = feature_boxes(P)
            for feat, b in boxes.items():
                k = f"{shot}__{view}__{feat}"
                out_by = max(-b[0], -b[1], b[2] - im.width, b[3] - im.height) / max(b[2] - b[0], b[3] - b[1])
                if out_by > 0.15:  # (beyond the frame = transparent, outside the mask) the feature leaves the frame: the shot's framing is wrong, not the model
                    table[k] = {"error": f"crop leaves the frame by {out_by:.0%} of its size"}
                    continue
                c = _crop(im, b, _fit(b[2] - b[0], b[3] - b[1]))
                c.save(out / "crops" / f"{k}.png")
                table[k] = {"file": str(out / "crops" / f"{k}.png"), "state": states[f.name], "box": b,
                            "feature": feat, "view": view, "shot": shot}
        else:
            cw, ch = spec.get("crop", [min(im.width, CROP_MAX), min(im.height, CROP_MAX)])
            b = [(im.width - cw) / 2, (im.height - ch) / 2, (im.width + cw) / 2, (im.height + ch) / 2]
            k = f"{shot}__{view}"
            _crop(im, b).save(out / "crops" / f"{k}.png")
            table[k] = {"file": str(out / "crops" / f"{k}.png"), "state": states[f.name], "box": b, "view": view,
                        "shot": shot}
    (out / "crops.json").write_text(json.dumps(table, indent=1))
    return table


def _flat(im, bg=(0.5, 0.5, 0.5)):
    from PIL import Image
    if im.mode != "RGBA":
        return im.convert("RGB")
    b = Image.new("RGBA", im.size, tuple(int(255 * c) for c in bg) + (255,))
    return Image.alpha_composite(b, im).convert("RGB")


def photo_crops(head: str, out: Path) -> dict:
    """The head's reference photos (human_refs.json) cut to the same face features by their OWN landmarks, at the
    render crops' size. out/photo/<view>__<feature>.png. The photo's state is "photo" (compared with renders under
    that view's photo_light only)."""
    from PIL import Image
    from . import likeness, store
    refs = json.loads((store.HOME / head / "human_refs.json").read_text())
    out = Path(out) / "photo"
    out.mkdir(parents=True, exist_ok=True)
    table = {}
    for view, yaw in PHOTO_VIEWS.items():
        vi = _photo_index(head, yaw)
        img = Image.open(refs["views"][vi]["image"]).convert("RGB")
        P = _detect(img)
        if P is None:
            P0 = likeness.detect_region(img, (0, 0, img.width, img.height))
            P = None if P0 is None else np.asarray(P0, float)
        if P is None:
            continue
        for feat, b in feature_boxes(P).items():
            c = _crop(img, b, _fit(b[2] - b[0], b[3] - b[1]))
            p = out / f"{view}__{feat}.png"
            c.save(p)
            table[f"{view}__{feat}"] = {"file": str(p), "state": "photo", "box": b, "image": refs["views"][vi]["image"]}
    (out / "photo.json").write_text(json.dumps(table, indent=1))
    return table


# ------------------------------------------------------------------ measures

def _lab(im):
    from skimage.color import rgb2lab
    a = np.asarray(im.convert("RGBA"), np.float32) / 255.0
    return rgb2lab(a[..., :3]), a[..., 3]


def _blur(x, s, m=None):
    from scipy.ndimage import gaussian_filter
    if m is None:
        return gaussian_filter(x, s)
    return gaussian_filter(x * m, s) / np.maximum(gaussian_filter(m, s), 1e-6)


def _bandpass(L, m, w):
    return _blur(L, 0.012 * w, m) - _blur(L, 0.05 * w, m)


def _edges(L):
    from scipy.ndimage import sobel
    g = _blur(L, 1.0)
    return np.hypot(sobel(g, 0), sobel(g, 1))


def measures(im, mask=None) -> dict:
    """L* p10 / p50 / p90, chroma p50, blotch (std of the mid-scale band-pass of L*: blotches / speckle 1-5 % of the
    crop) inside the subject (alpha > 0.5)."""
    lab, a = _lab(im)
    m = (a > 0.5) if mask is None else mask
    if m.sum() < 50:
        return {"coverage": float(m.mean())}
    L = lab[..., 0]
    C = np.hypot(lab[..., 1], lab[..., 2])
    w = max(L.shape)
    core = _erode(m, int(0.05 * w))
    bp = _bandpass(L, m.astype(float), w)
    return {"L10": float(np.percentile(L[m], 10)), "L50": float(np.percentile(L[m], 50)),
            "L90": float(np.percentile(L[m], 90)), "C50": float(np.percentile(C[m], 50)),
            "blotch": float(bp[core].std()) if core.sum() > 50 else float(bp[m].std()), "coverage": float(m.mean())}


def _erode(m, r):
    from scipy.ndimage import binary_erosion
    return binary_erosion(m, iterations=max(1, r)) if r > 0 else m


def compare(x, ref) -> dict:
    """x against ref (PIL images; resized to ref's size): each measure's delta (x - ref), edge difference (mean |edges
    x - edges ref| / mean edges ref, inside both subjects), outline (1 - IoU of the alphas, when both have one)
    and the worst spot (the crop cell where the band-passed L* differs most: [x, y] in ref pixels)."""
    from PIL import Image
    if x.size != ref.size:
        x = x.resize(ref.size, Image.LANCZOS)
    lx, ax = _lab(x)
    lr, ar = _lab(ref)
    has_a = (ax < 0.99).any() and (ar < 0.99).any()
    mx, mr = (ax > 0.5), (ar > 0.5)
    both = mx & mr if has_a else np.ones_like(mr)
    mx_ = mr_ = both
    a, b = measures(x, mx_), measures(ref, mr_)
    out = {k: a[k] - b[k] for k in ("L10", "L50", "L90", "C50", "blotch") if k in a and k in b}
    Ex, Er = _edges(lx[..., 0]), _edges(lr[..., 0])
    # inside both subjects, off their borders (the silhouette is the outline measure's; border pixels carry the
    # background / premultiplication, not the surface)
    u = _erode(mx & mr, 3) if has_a else np.ones_like(mr)
    if u.sum() < 50:
        u = (mx | mr) if has_a else np.ones_like(mr)
    out["edge"] = float(np.abs(Ex - Er)[u].mean() / max(Er[u].mean(), 1e-6))
    # signed: + = x's edges harder / more contrasty than the reference's (a decal, a rim), - = softer (smudged)
    out["sharp"] = float(np.percentile(Ex[u], 99) / max(np.percentile(Er[u], 99), 1e-6) - 1.0)  # (p99: the strongest 1 %, a lip outline)
    if has_a:
        out["outline"] = float(1 - (mx & mr).sum() / max((mx | mr).sum(), 1))
    w = max(lr.shape[:2])
    d = np.abs(_bandpass(lx[..., 0], both.astype(float), w) - _bandpass(lr[..., 0], both.astype(float), w))
    d = _blur(d * both, 0.02 * w)
    e = max(2, int(0.04 * w))  # (the blur's border is not a finding)
    d[:e], d[-e:], d[:, :e], d[:, -e:] = 0, 0, 0, 0
    j, i = np.unravel_index(np.argmax(d), d.shape)
    out["spot"] = float(d[j, i])   # the largest local mid-scale L* difference (L*): a blotch / sticker / rim
    out["worst"] = [int(i), int(j)]
    out["ref"] = {k: b[k] for k in ("L10", "L50", "L90", "C50", "blotch") if k in b}
    return out


def plant_blot(im, frac=0.06, dL=-25.0, at=None):
    """A dark blot (gaussian, dL in L*, radius frac x the crop) painted on a copy: the planted fault."""
    from PIL import Image
    from skimage.color import lab2rgb
    lab, a = _lab(im)
    H, W = a.shape
    if at is None:
        ys, xs = np.nonzero(_erode(a > 0.5, int(0.12 * max(H, W))) if (a < 0.99).any() else np.ones_like(a, bool))
        if len(xs) == 0:
            ys, xs = np.nonzero(a > 0.5)
        k = len(xs) // 2
        at = (int(xs[k]), int(ys[k]))
    yy, xx = np.mgrid[0:H, 0:W]
    r = frac * max(H, W)
    g = np.exp(-((xx - at[0]) ** 2 + (yy - at[1]) ** 2) / (2 * (r / 2) ** 2))
    lab = lab.copy()
    lab[..., 0] = np.clip(lab[..., 0] + dL * g, 0, 100)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rgb = np.clip(lab2rgb(lab), 0, 1)
    out = np.dstack([rgb, a])
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA"), at


def self_check_measures(ref) -> list:
    """The measure-side self-checks on one reference crop: [(name, ok, detail)]."""
    res = []
    z = compare(ref, ref)
    worst = max(abs(v) for k, v in z.items() if k not in ("worst", "ref"))
    res.append(("ref_vs_itself", worst < 1e-6, f"max |delta| {worst:.2e}"))
    bl, at = plant_blot(ref)
    c = compare(bl, ref)
    w = max(ref.size)
    dist = float(np.hypot(c["worst"][0] - at[0], c["worst"][1] - at[1]))
    ok = c["spot"] > 1.0 and dist < 0.08 * w and c["L50"] <= 0.0
    res.append(("planted_blot", bool(ok), f"spot {c['spot']:.2f}, blotch {c['blotch']:+.2f}, L50 {c['L50']:+.2f}, "
                f"found {dist:.0f} px from it"))
    return res


# ------------------------------------------------------------------ the report

ROW_KEYS = ("L10", "L50", "L90", "C50", "blotch", "spot", "edge", "sharp", "outline")


def report(run: Path, ref_run: Path | None = None, head: str | None = None, only: list | None = None) -> dict:
    """Measures of a run's crops: absolute, vs another run (same crop names, identical render state required), and
    vs the photo crops (face features of the photo-lit shots only). Refuses (raises) when a self-check fails."""
    from PIL import Image
    run = Path(run)
    me = json.loads((run / "crops.json").read_text())
    checks = json.loads((run / "checks.json").read_text()) if (run / "checks.json").exists() else []
    bad = [c for c in checks if not c[1]]
    if bad:
        raise RuntimeError(f"judge: refusing to report on {run}: render self-checks failed: {bad}")
    rows, mchecks = {}, []
    refc = json.loads((Path(ref_run) / "crops.json").read_text()) if ref_run else {}
    pho = photo_crops(head, run) if head else {}
    for k, v in sorted(me.items()):
        if "file" not in v or (only and not any(o in k for o in only)):
            continue
        im = Image.open(v["file"])
        row = {"abs": measures(im)}
        if k in refc and "file" in refc[k]:
            if refc[k]["state"] != v["state"]:
                raise RuntimeError(f"judge: {k}: render state differs from the reference run's ({v['state']} vs "
                                   f"{refc[k]['state']}): view transform / lights not the same; refusing")
            r = Image.open(refc[k]["file"])
            mchecks.append((k, self_check_measures(r)))
            row["vs_ref"] = compare(im, r)
        pk = f"{v.get('view')}__{v.get('feature')}"
        if "-photo-" in k and pk in pho:
            r = Image.open(pho[pk]["file"]).convert("RGBA")
            mchecks.append((k + " (photo)", self_check_measures(r)))
            row["vs_photo"] = compare(_flat(im, _photo_bg(r)).convert("RGBA"), r)
        rows[k] = row
    fails = [(k, c) for k, cs in mchecks for c in cs if not c[1]]
    out = {"run": str(run), "ref": str(ref_run) if ref_run else None, "head": head, "render_checks": checks,
           "measure_checks": mchecks, "rows": rows}
    (run / ("report.json" if not ref_run else f"report_vs_{Path(ref_run).name}.json")).write_text(json.dumps(out, indent=1, default=float))
    if fails:
        raise RuntimeError(f"judge: refusing to report: measure self-checks failed: {fails[:5]}")
    return out


def _photo_bg(r):
    a = np.asarray(r.convert("RGB"), np.float32) / 255.0
    return tuple(np.median(a.reshape(-1, 3), 0))


def format_report(rep: dict) -> str:
    lines = ["SELF-CHECKS:"] + [f"  {'ok  ' if c[1] else 'FAIL'} {c[0]}: {c[2]}" for c in rep["render_checks"]]
    mc = [c for _, cs in rep["measure_checks"] for c in cs]
    if mc:
        n_ok = sum(c[1] for c in mc)
        lines.append(f"  {'ok  ' if n_ok == len(mc) else 'FAIL'} measures: ref_vs_itself + planted_blot on "
                     f"{len(rep['measure_checks'])} reference crops ({n_ok}/{len(mc)} passed)")
    for col in ("vs_ref", "vs_photo"):
        rs = {k: r[col] for k, r in rep["rows"].items() if col in r}
        if not rs:
            continue
        lines.append(f"\n{col.upper()} (x - ref; edge / outline: 0 = same):")
        lines.append(f"  {'crop':38s} " + " ".join(f"{c:>7s}" for c in ROW_KEYS) + "   worst@")
        for k, r in rs.items():
            lines.append(f"  {k:38s} " + " ".join(f"{r[c]:+7.2f}" if c in r else f"{'':>7s}" for c in ROW_KEYS)
                         + f"   {r['worst']}")
    if not any("vs_ref" in r or "vs_photo" in r for r in rep["rows"].values()):
        lines.append(f"\nABSOLUTE:")
        for k, r in rep["rows"].items():
            a = r["abs"]
            lines.append(f"  {k:38s} " + " ".join(f"{c} {a[c]:6.1f}" for c in ("L10", "L50", "L90", "C50", "blotch") if c in a))
    return "\n".join(lines)


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
    out = run_dir(glb, tag, swap)
    if force or not (out / "audit.json").exists():
        render(glb, out, head, swap=swap)
    checks = check_run(glb, out, swap or {})
    (out / "checks.json").write_text(json.dumps(checks))
    crops(out, boxes_from)
    (out / "meta.json").write_text(json.dumps({"glb": str(Path(glb).resolve()), "head": head, "tag": tag, "swap": swap}))
    return out


# ------------------------------------------------------------------ blind A/B

def ab(old_run, new_run, out, ref_run=None, head=None, only=None, context="", dry=False) -> dict:
    """Blind trios of the same crops: reference | X | Y (bin/review-ab randomises X / Y and keeps the key), the
    reference = ref_run's crop (e.g. the approved build) or, for the photo-lit face features, the photo crop. Two
    CONTROL items carry the reference itself as a candidate (once as old, once as new): the key-applied review must
    call the reference copy closer in both, else the review is refused (labels swapped, or the reviewer didn't look).
    dry: write the trios + prompt for a subagent instead of running review-ab."""
    from PIL import Image
    old_run, new_run, out = Path(old_run), Path(new_run), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    co, cn = (json.loads((r / "crops.json").read_text()) for r in (old_run, new_run))
    cr = json.loads((Path(ref_run) / "crops.json").read_text()) if ref_run else {}
    pho = photo_crops(head, out) if head else {}
    items = []
    for k in sorted(set(co) & set(cn)):
        if "file" not in co[k] or "file" not in cn[k] or (only and not any(o in k for o in only)):
            continue
        if co[k]["state"] != cn[k]["state"]:
            raise RuntimeError(f"judge ab: {k}: old and new were rendered under different states; refusing")
        ref = None
        if k in cr and "file" in cr[k]:
            if cr[k]["state"] != cn[k]["state"]:
                raise RuntimeError(f"judge ab: {k}: the reference run's render state differs; refusing")
            ref = cr[k]["file"]
        elif "-photo-" in k and f"{co[k].get('view')}__{co[k].get('feature')}" in pho:
            ref = pho[f"{co[k]['view']}__{co[k]['feature']}"]["file"]
        if ref is None:
            continue
        flat = []
        for p in (ref, co[k]["file"], cn[k]["file"]):  # flattened on one grey, the reference's size
            im = _flat(Image.open(p))
            q = out / "in" / f"{k}__{len(flat)}.png"
            q.parent.mkdir(exist_ok=True)
            im.save(q)
            flat.append(str(q))
        items.append((k, flat))
    if not items:
        raise RuntimeError("judge ab: no crop has a reference (give ref_run or head)")
    ctl = items[len(items) // 2]
    args = [f"{k}={a}:{b}:{c}" for k, (a, b, c) in items]
    # (named like crops, so the reviewer can't tell which items are controls)
    args += [f"{ctl[0]}{CTL_OLD}={ctl[1][0]}:{ctl[1][0]}:{ctl[1][2]}", f"{ctl[0]}{CTL_NEW}={ctl[1][0]}:{ctl[1][1]}:{ctl[1][0]}"]
    meta = {"old": str(old_run), "new": str(new_run), "ref": str(ref_run) if ref_run else f"photo:{head}",
            "items": [k for k, _ in items], "control_crop": ctl[0]}
    (out / "ab.json").write_text(json.dumps(meta, indent=1))
    if dry or not os.path.exists(REVIEW_AB):
        return {**meta, "dry": True, "args": args, "prompt": _trios(out / "review", args, context)}
    cmd = [sys.executable, REVIEW_AB, str(out / "review"), *args, "--context", context or "game character crops"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode == 4 or "KEY APPLIED" not in r.stdout:
        return {**meta, "dry": True, "args": args, "error": "review-ab did not run: " + r.stdout[-300:],
                "prompt": _trios(out / "review", args, context)}
    return {**meta, **score_review(out / "review")}


def _trios(rdir: Path, args: list, context: str = "") -> str:
    """review-ab's trios without its reviewer (no `claude -p`): trio_<n>.png, key.json and prompt.md for a fresh
    blind subagent, which writes its answer to review.md; then `judge score <dir>` applies the key."""
    import random
    from PIL import Image, ImageDraw
    rdir = Path(rdir)
    rdir.mkdir(parents=True, exist_ok=True)
    key, listing = {}, []
    args = random.sample(args, len(args))  # (the controls not always last)
    for n, a in enumerate(args):
        name, _, trio = a.partition("=")
        ref, old, new = trio.split(":")
        order = [("old", old), ("new", new)]
        random.shuffle(order)
        key[name] = {"X": order[0][0], "Y": order[1][0]}
        ims = [Image.open(q).convert("RGB") for q in (ref, order[0][1], order[1][1])]
        h = max(i.height for i in ims)
        ims = [i.resize((max(1, i.width * h // i.height), h)) for i in ims]
        im = Image.new("RGB", (sum(i.width for i in ims) + 24, h + 22), (30, 30, 30))
        d, x = ImageDraw.Draw(im), 0
        for lab, i in zip(("REFERENCE", "X", "Y"), ims):
            im.paste(i, (x, 22))
            d.text((x + 4, 4), lab, fill=(255, 255, 255))
            x += i.width + 12
        q = rdir / f"trio_{n}.png"
        im.save(q)
        listing.append(f"- {name}: {q}")
    (rdir / "key.json").write_text(json.dumps(key, indent=1))
    prompt = (f"You are a senior art director at a game studio comparing two candidate results against a reference. You "
              f"have no stake in either. {('What is shown: ' + context) if context else ''}\nEach image is one region: "
              "REFERENCE on the left, then candidates X and Y, same framing. Read every image with the Read tool.\n"
              + "\n".join(listing) + "\n\nFor each region: list each candidate's faults against the REFERENCE, worst "
              "first, concretely, marking each MAJOR or MINOR; describe in one line what X and what Y look like; then say "
              "which is closer to the reference. Don't praise, don't guess at causes. End with exactly one line per region "
              "\"REGION <name>: X|Y|SAME\", then \"OVERALL: X|Y|SAME\". Write your whole answer to " + str(rdir / "review.md"))
    (rdir / "prompt.md").write_text(prompt)
    return prompt


def apply_key(rdir: Path) -> dict:
    """A subagent's review.md (REGION lines) with key.json applied -> KEY APPLIED lines appended; then scored."""
    import re
    rdir = Path(rdir)
    txt = (rdir / "review.md").read_text().split("\nKEY APPLIED:")[0]
    key = json.loads((rdir / "key.json").read_text())
    lines = []
    for name, k in key.items():
        m = re.search(r"REGION\s+" + re.escape(name) + r"\s*:\s*(X|Y|SAME)", txt)
        v = m.group(1) if m else "?"
        lines.append(f"{name}: {k.get(v, 'same' if v == 'SAME' else '?').upper()}")
    (rdir / "review.md").write_text(txt + "\nKEY APPLIED:\n" + "\n".join(lines) + "\n")
    return score_review(rdir)


CTL_OLD, CTL_NEW = "_b", "_c"   # control items: <crop>_b = the reference as "old", <crop>_c = as "new"


def score_review(rdir: Path) -> dict:
    """The key-applied review (review.md's KEY APPLIED lines), with the controls checked."""
    txt = (Path(rdir) / "review.md").read_text()
    res = {}
    for ln in txt.split("KEY APPLIED:")[-1].splitlines():
        if ":" in ln and not ln.startswith("VERDICT"):
            k, v = ln.split(":", 1)
            res[k.strip()] = v.strip().lower()
    meta = json.loads((Path(rdir).parent / "ab.json").read_text()) if (Path(rdir).parent / "ab.json").exists() else {}
    c = meta.get("control_crop")
    co = res.get(f"{c}{CTL_OLD}") if c else next((v for k, v in res.items() if k.endswith(CTL_OLD)), None)
    cn = res.get(f"{c}{CTL_NEW}") if c else next((v for k, v in res.items() if k.endswith(CTL_NEW)), None)
    ctl_ok = co == "old" and cn == "new"
    ctl_keys = {f"{c}{CTL_OLD}", f"{c}{CTL_NEW}"} if c else {k for k in res if k.endswith((CTL_OLD, CTL_NEW))}
    votes = {"old": 0, "new": 0, "same": 0}
    for k, v in res.items():
        if k not in ctl_keys and v in votes:
            votes[v] += 1
    verdict = ("NEW" if votes["new"] > votes["old"] else "OLD" if votes["old"] > votes["new"] else "TIE")
    return {"controls_ok": ctl_ok, "regions": res, "votes": votes,
            "verdict": verdict if ctl_ok else f"REFUSED (controls: {co} / {cn}; the reference copy must win both: "
                                              "labels swapped, or the reviewer didn't look)"}


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
                crops(run, ref)
            print(format_report(report(run, ref, o.head, only)))
            return 0
        if o.cmd == "ab":
            ref = _as_run(o.ref, o.head) if o.ref else None
            old = _as_run(o.args[0], o.head, boxes_from=ref)
            new = _as_run(o.args[1], o.head, boxes_from=ref or old)
            for r_ in (old, new):
                if ref is not None or r_ is new:
                    crops(r_, ref or old)
            res = ab(old, new, o.args[2], ref, o.head, only, o.context, o.dry)
            if res.get("dry"):
                print("review-ab not run" + (f" ({res['error']})" if res.get("error") else "") + ". Give a FRESH blind "
                      f"subagent {o.args[2]}/review/prompt.md (nothing else), then: judge score {o.args[2]}/review\n")
                print(res["prompt"])
                return 4
            print(json.dumps({k: res[k] for k in ("regions", "votes", "controls_ok", "verdict")}, indent=1))
            return 0 if res["controls_ok"] else 6
        if o.cmd == "score":
            res = apply_key(Path(o.args[0]))
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
