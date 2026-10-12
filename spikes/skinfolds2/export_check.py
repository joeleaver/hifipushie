"""export_check.py <model> <tag> [triangles=30000] [texture=2048] [shots=1]: what the GAME ASSET keeps of skin.folds, on the
FULL BODY with the model's own export settings (parts.body.topology "wrap" on Garrett) and face shapes.
1. export_asset(face_shapes=True) -> $G/out/export_<tag>/ (skipped when the GLB is there).
2. GEOMETRY: per laid fold and side, on points sampled over the GLB's skin triangles within 7 mm of the fold's line:
   the relief the exact field has there (folded field - fold-free field, mm) and the low poly's error to the FOLDED
   surface. lost = rms(error) / rms(relief): 1 = the triangles ignore the fold (it is in the normal map or nowhere), 0 =
   all of it is geometry.
3. NORMAL MAP: the baked tangent-space normal at the same points (through the GLB's UVs): rms of its tilt, with the
   same number 12-20 mm away from every fold (the skin's own micro relief) beside it.
4. FACE SHAPES with the folds present: blink, jaw open, smile: the posed mesh's folded edges / turned faces against the
   neutral's (tearing), and how far the lid fold's line travels in a blink against the lid margin under it.
5. PREVIEW of the GLB (Cycles, as an engine loads it): eyes and mouth close-ups, neutral + the three poses, under a
   frontal and a raking light -> $G/out/export_<tag>_<pose>.png (shots=0 skips)."""
import json, os, struct, sys, time
from pathlib import Path
import numpy as np
from PIL import Image
from hifipushie import asset, images, skin as skinmod, skin_folds as sf, skin_read as sr, sdf, store

model, tag = sys.argv[1:3]
kw = dict(a.split("=") for a in sys.argv[3:])
G = os.environ["G"] + "/out"
out = Path(f"{G}/export_{tag}")
glb = out / f"{model}.glb"
spec = store.load(model)
t = time.time()
if not glb.exists():
    info = asset.export(model, out, int(kw.get("triangles", 30000)), int(kw.get("texture", 2048)), 256, 1, None, True, False, False, True)
    print(f"== export: {info['glb']} {info['triangles']} triangles, height range +-{info['height_range_m'] * 1000:.2f} mm, {time.time() - t:.0f} s")
    for ln in info["log"]:
        if any(k in ln for k in ("quality", "WARNING", "wrapped", "face shapes", "shapes", "atlas", "body")):
            print("   ", ln[:320])
    json.dump(info["log"], open(out / "log.json", "w"))


def read(path):
    raw = Path(path).read_bytes()
    jl = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20 + jl])
    binary = raw[28 + jl:]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    dtype = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}

    def view(bv, ctype, n, k, off=0):
        v = doc["bufferViews"][bv]
        st = v.get("byteStride") or 0
        o = v.get("byteOffset", 0) + off
        if st and st != np.dtype(dtype[ctype]).itemsize * k:
            a = np.frombuffer(binary, np.uint8, st * n, o).reshape(n, st)[:, :np.dtype(dtype[ctype]).itemsize * k]
            return np.frombuffer(a.tobytes(), dtype[ctype]).reshape(n, k)
        return np.frombuffer(binary, dtype[ctype], n * k, o).reshape(n, k)

    def acc(i):
        a = doc["accessors"][i]
        k = width[a["type"]]
        o = view(a["bufferView"], a["componentType"], a["count"], k, a.get("byteOffset", 0)).astype(np.float64) if "bufferView" in a else np.zeros((a["count"], k))
        if "sparse" in a:
            sp = a["sparse"]
            idx = view(sp["indices"]["bufferView"], sp["indices"]["componentType"], sp["count"], 1, sp["indices"].get("byteOffset", 0)).ravel()
            o = o.copy()
            o[idx] = view(sp["values"]["bufferView"], a["componentType"], sp["count"], k, sp["values"].get("byteOffset", 0))
        return o
    res = {}
    for m in doc["meshes"]:
        p = m["primitives"][0]
        mat = doc["materials"][p["material"]] if "material" in p else {}
        res[m["name"]] = {"P": acc(p["attributes"]["POSITION"]), "uv": acc(p["attributes"]["TEXCOORD_0"]) if "TEXCOORD_0" in p["attributes"] else None,
                          "T": acc(p["indices"]).astype(int).reshape(-1, 3), "names": (m.get("extras") or {}).get("targetNames") or [],
                          "targets": [acc(tg["POSITION"]) for tg in p.get("targets") or []], "material": mat}
    return res, doc


z2 = lambda a: np.stack([a[:, 0], -a[:, 2], a[:, 1]], 1)        # glTF (Y up) -> the model's axes (Z up)  # noqa: E731
meshes, doc = read(glb)
print("meshes:", {k: (len(v["P"]), len(v["T"]), len(v["names"])) for k, v in meshes.items()})
part = (spec.get("skin") or {}).get("part", "body")
body = next(v for k, v in meshes.items() if k == part or k.startswith(part))
V, Tr = z2(body["P"]), body["T"]
st = spec
J = skinmod._joints(spec)
cfg = sf.options((spec.get("skin") or {}).get("folds"))
prims_f = images.prims_on(spec, [part])
prims_0 = images.prims_on(sf.without(spec), [part])
ps = sf.paths(sf.without(spec), part, J, cfg, S=sf.field_surface(prims_0, J))
# points over the skin's triangles
rng = np.random.default_rng(0)
A, B, C = V[Tr[:, 0]], V[Tr[:, 1]], V[Tr[:, 2]]
cen = (A + B + C) / 3
from scipy.spatial import cKDTree
allP = np.concatenate([q["P"][q["amount"] > 0] for q in ps.values() if (q["amount"] > 0).any()] or [np.zeros((0, 3))])
head = np.linalg.norm(cen - np.asarray(J["lm_nose_tip"], float), axis=1) < 0.16
ti = np.flatnonzero(head)
bc = rng.dirichlet([1, 1, 1], (len(ti), 6))
S = (bc[..., 0:1] * A[ti][:, None] + bc[..., 1:2] * B[ti][:, None] + bc[..., 2:3] * C[ti][:, None]).reshape(-1, 3)
St = np.repeat(ti, 6)
Sb = bc.reshape(-1, 3)
ff, f0 = sdf.field_at(prims_f, S) * 1000, sdf.field_at(prims_0, S) * 1000
dall = cKDTree(allP).query(S)[0] if len(allP) else np.full(len(S), 1.0)
rms = lambda a: float(np.sqrt(np.mean(np.square(a)))) if len(a) else 0.0  # noqa: E731
print(f"== GEOMETRY ({len(V)} vertices, {len(Tr)} triangles on {part}; {head.sum()} on the head; edge length on the face p50 "
      f"{1000 * float(np.median(np.linalg.norm(A[ti] - B[ti], axis=1))):.1f} mm)")
far = (dall > 0.012) & (dall < 0.02)
print(f"   away from every fold (12-20 mm): low poly error to the field rms {rms(ff[far]):.2f} mm (the wrap's own fit)")
# the normal map
nm = None
tex = (body["material"].get("normalTexture") or {}).get("index")
if tex is not None:
    img = doc["images"][doc["textures"][tex]["source"]]
    f = out / img["uri"] if "uri" in img else None
    if f is not None and f.exists():
        nm = np.asarray(Image.open(f).convert("RGB"), float) / 255.0 * 2 - 1
if nm is None and (out / f"{model}_normal.png").exists():
    nm = np.asarray(Image.open(out / f"{model}_normal.png").convert("RGB"), float) / 255.0 * 2 - 1
uv = body["uv"]


FLIP = [None]


def tilt(sel):
    if nm is None or uv is None:
        return float("nan")
    u = (Sb[sel][:, 0:1] * uv[Tr[St[sel], 0]] + Sb[sel][:, 1:2] * uv[Tr[St[sel], 1]] + Sb[sel][:, 2:3] * uv[Tr[St[sel], 2]])
    x = np.clip((u[:, 0] % 1) * nm.shape[1], 0, nm.shape[1] - 1).astype(int)
    y = np.clip((u[:, 1] % 1) * nm.shape[0], 0, nm.shape[0] - 1).astype(int)
    n = nm[y, x]
    n2 = nm[np.clip(((1 - u[:, 1]) % 1) * nm.shape[0], 0, nm.shape[0] - 1).astype(int), x]     # (whichever way v runs: the flatter read is the right one away from folds)
    if FLIP[0] is None:
        FLIP[0] = bool(np.abs(n2[:, :2]).mean() < np.abs(n[:, :2]).mean())
    n = n2 if FLIP[0] else n
    return float(np.degrees(np.sqrt(np.mean(np.arctan2(np.hypot(n[:, 0], n[:, 1]), np.maximum(n[:, 2], 1e-3)) ** 2))))


print(f"   normal map tilt away from folds: rms {tilt(far):.1f} deg")
for (name, sd), q in ps.items():
    on = q["amount"] > 0
    if not on.any():
        continue
    d = cKDTree(q["P"][on]).query(S)[0]
    sel = d < 0.007
    if sel.sum() < 30:
        print(f"   {name + sd:15s} no skin triangles by it"); continue
    r = ff[sel] - f0[sel]
    print(f"   {name + sd:15s} amount {float(q['amount'].max()):.2f}: relief in the exact field rms {rms(r):.2f} max {np.abs(r).max():.2f} mm | low poly error to "
          f"the folded surface rms {rms(ff[sel]):.2f} p95 {np.percentile(np.abs(ff[sel]), 95):.2f} mm | LOST from the triangles {min(rms(ff[sel]) / max(rms(r), 1e-6), 9.99):.2f}"
          f" (were it ignored: {rms(f0[sel] * 0 + r):.2f}; the fold-free surface's error there {rms(f0[sel]):.2f}) | normal map tilt rms {tilt(sel):.1f} deg")
# face shapes
names = body["names"]
print(f"== FACE SHAPES: {len(names)} targets on {part}")
tris_h = Tr[head]
used = np.unique(tris_h)
remap = -np.ones(len(V), int); remap[used] = np.arange(len(used))


def quality(Vp):
    q = asset.mesh_quality(Vp[used], remap[tris_h])
    return {k: q[k] for k in q if k in ("folds", "folded", "turned", "slivers", "open", "non_manifold") or "fold" in k}


q0 = quality(V)
print("   neutral (head):", q0)
POSES = {"blink05": {"eyeBlinkLeft": 0.5, "eyeBlinkRight": 0.5}, "blink": {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0},
         "wide": {"eyeWideLeft": 1.0, "eyeWideRight": 1.0}, "squint": {"eyeSquintLeft": 1.0, "eyeSquintRight": 1.0, "cheekSquintLeft": 1.0, "cheekSquintRight": 1.0},
         "smile": {"mouthSmileLeft": 1.0, "mouthSmileRight": 1.0}, "jaw": {"jawOpen": 0.7}}
for pn, pose in POSES.items():
    D = np.zeros_like(V)
    for k, w in pose.items():
        if k in names:
            D += w * z2(body["targets"][names.index(k)])
    print(f"   {pn}: moves {int((np.linalg.norm(D, axis=1) > 1e-5).sum())} vertices, max {1000 * np.linalg.norm(D, axis=1).max():.1f} mm;", quality(V + D))
    if pn == "blink":
        for sd in (".L", ".R"):
            q = ps.get(("lid_fold", sd))
            if q is None or not (q["amount"] > 0).any():
                continue
            mid = q["P"][len(q["P"]) // 2]
            lm = np.asarray(J[f"lm_lid_upper{sd}"], float)
            tr = cKDTree(V)
            a = D[tr.query_ball_point(mid, 0.0025)]
            b = D[tr.query_ball_point(lm, 0.0025)]
            print(f"      lid_fold{sd}: in a blink the fold's line (middle) moves {1000 * np.linalg.norm(a.mean(0)) if len(a) else 0:.1f} mm ({len(a)} vertices), "
                  f"the lid margin under it {1000 * np.linalg.norm(b.mean(0)) if len(b) else 0:.1f} mm ({len(b)} vertices)")
if int(kw.get("shots", 1)):
    eyes = 0.5 * (np.asarray(J["eye.L"], float) + np.asarray(J["eye.R"], float))
    mouth = 0.5 * (np.asarray(J["lm_mouth_corner.L"], float) + np.asarray(J["lm_mouth_corner.R"], float))
    face = 0.5 * (eyes + mouth)
    cam = lambda c, w, az, nm_: {"eye": (c + 0.6 * np.array([np.sin(np.radians(az)), -np.cos(np.radians(az)), 0.0])).tolist(), "target": c.tolist(),  # noqa: E731
                                 "fov": float(np.degrees(2 * np.arctan(w / 2 / 0.6))), "name": nm_}
    cams = [cam(np.asarray(J["eye.L"], float) + [0, 0, 0.003], 0.05, 0, "eyeL"), cam(eyes, 0.12, 0, "eyes"), cam(mouth + [0, 0, 0.005], 0.12, 0, "mouth"), cam(face, 0.25, 40, "3/4")]
    LIGHTS = {"front": {"lights": [{"dir": [0.08, -0.74, 0.67], "energy": 3.3, "color": [1, 1, 1], "angle": 38},
                                   {"dir": [0.0, -1.0, 0.05], "energy": 0.7, "color": [1, 1, 1], "angle": 40}],
                        "world": {"color": [0.8, 0.8, 0.8], "strength": 0.45}, "view": "Standard", "exposure": -0.25},
              "rake": {"lights": [{"dir": [0.96, -0.25, 0.12], "energy": 4.0, "color": [1.0, 0.98, 0.96], "angle": 6}],
                       "world": {"color": [0.5, 0.5, 0.52], "strength": 0.12}, "view": "Standard", "exposure": 0.0}}
    order = ["neutral"] + list(POSES)
    for ln, lt in LIGHTS.items():
        sheets = asset.preview(glb, [], size=560, samples=24, cameras=cams, poses=[{}] + [POSES[k] for k in POSES], lighting=lt)
        # ONE SMALL IMAGE PER FEATURE: the poses side by side (the contact sheet's panels cut out)
        from PIL import ImageDraw, ImageFont
        Fn = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        w2, h2 = sheets[0].size[0] // 2, sheets[0].size[1] // 2
        for ci, c_ in enumerate(cams):
            cells = [im.crop(((ci % 2) * w2, (ci // 2) * h2 + 30, (ci % 2 + 1) * w2, (ci // 2 + 1) * h2)).resize((380, int(380 * (h2 - 30) / w2))) for im in sheets]
            row = Image.new("RGB", (380 * len(cells), cells[0].size[1] + 24), "white")
            dr = ImageDraw.Draw(row)
            for k_, (nm_, ce) in enumerate(zip(order, cells)):
                row.paste(ce, (380 * k_, 24))
                dr.text((380 * k_ + 5, 2), nm_, fill=(0, 0, 0), font=Fn)
            fn_ = f"{G}/export_{tag}_{c_['name'].replace('/', '')}_{ln}.png"
            row.save(fn_)
            print("   feature tiles", fn_)
print(f"{time.time() - t:.0f} s")
