"""What the tools show and write: looks, the impostor, export, the Blender import, wind, a set's export. Part of the plant tools (veg_tools.py has the overview)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import veg_tools
from . import vegetation_tree
from .veg_tools import _dir, grown, history, home, load
from .veg_tools_report import reference, set_names

def veg_look_ground(T: dict, P) -> np.ndarray:
    return vegetation_tree.ground_at(T["spec"], np.asarray(P)[:, :2])


def _view_jobs(T: dict, views, azimuth: float, size: int, stem) -> tuple[list, list]:
    """Blender view jobs for named views or camera dicts; (jobs, [(name, path)])."""
    from . import veg_look
    import math
    has_leaves = len(veg_look.veg_leaf_place(T)) > 0
    from . import veg_style
    styled = veg_style.sheet(T["spec"]) is not None
    H = T["height"]
    c_, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    toward = np.array([-s_, -c_, 0.0])
    sz = [int(size * 0.95), size]
    jobs, got = [], []
    for k, x in enumerate(views):
        if isinstance(x, dict):  # a camera of your own: {"eye": [x, y, z], "look": [x, y, z], "fov": deg, "name"}
            nm = x.get("name", f"camera{k + 1}")
            if "eye" not in x or "look" not in x:
                raise ValueError('a camera view needs "eye" [x, y, z] and "look" [x, y, z] (m), optional "fov" deg, "name"')
            j = {"out": stem(nm), "size": sz, "eye": x["eye"], "look": x["look"], "fov": x.get("fov", 40),
                 "leaves": has_leaves and x.get("leaves", True), "clay": bool(x.get("clay")),
                 "sun": x.get("sun") or [math.degrees(math.atan2(x["eye"][0] - x["look"][0], x["eye"][1] - x["look"][1])) + 55, 40]}
            jobs.append(j)
            got.append((nm, j["out"]))
            continue
        if x not in veg_tools.VIEWS:
            raise ValueError(f"unknown view {x!r}: {list(veg_tools.VIEWS)} or a camera {{'eye', 'look', 'fov'}}")
        j = {"out": stem(x), "size": sz, "sun": [azimuth + 235, 40]}
        if x == "clay":
            j.update(azimuth=azimuth, leaves=styled, clay=True, ruler=True)  # (a style's crown is its structure: clay shows it)
        elif x == "bare":
            j.update(azimuth=azimuth, elevation=4, leaves=False, ruler=True)
        elif x == "leaf":
            j.update(azimuth=azimuth, elevation=4, leaves=has_leaves)
        elif x == "far":  # from far enough that the tree is about half the picture's height
            j.update(eye=(toward * max(12.0, 4.5 * H) + [0, 0, 1.7]).tolist(), look=[0, 0, 0.45 * H], fov=24, leaves=has_leaves)
        elif x == "near":  # standing by it: a small tree from close, a big one from 5 m, looking at the trunk and up
            dist = veg_look.near_distance(T, toward, float(np.clip(0.45 * H, 2.0, 5.0)))
            j.update(eye=(toward * dist + [0, 0, min(1.7, 0.6 * H)]).tolist(), look=[0, 0, min(0.5 * H, 5.0)], fov=62, leaves=has_leaves)
        elif x == "under":  # standing under the crown, looking up along a limb: is there foliage under and round the wood?
            ends_ = T["pos"][T["ends"]]
            q = ends_[np.argmax(ends_[:, :2] @ toward[:2])] if len(ends_) else np.array([0, 0, H])
            j.update(eye=(toward * 0.25 * float(np.linalg.norm(q[:2])) + [0, 0, 1.6]).tolist(),
                     look=[float(0.8 * q[0]), float(0.8 * q[1]), float(q[2])], fov=58, leaves=has_leaves)
        elif x == "ground":  # where the plant meets the ground: eye 1 m up, 8 m from its lowest foliage, half from the side
            E = T["pos"][T["ends"] & (T["order"] > 0)]
            if len(E):
                low = E[E[:, 2] - veg_look_ground(T, E) < np.percentile(E[:, 2] - veg_look_ground(T, E), 3) + 0.3]
                q = low[np.argmax(low[:, :2] @ toward[:2] + 0.3 * np.linalg.norm(low[:, :2], axis=1))]
            else:
                q = np.zeros(3)
            out_ = q[:2] / max(float(np.linalg.norm(q[:2])), 1e-6) if np.linalg.norm(q[:2]) > 0.3 else toward[:2]
            eye = q[:2] + 5.0 * out_ + 6.2 * np.array([-out_[1], out_[0]])
            gq = float(veg_look_ground(T, q[None])[0])
            j.update(eye=[float(eye[0]), float(eye[1]), 1.0], look=[float(q[0]), float(q[1]), gq + 0.35], fov=42, leaves=has_leaves,
                     sun=[math.degrees(math.atan2(eye[0] - q[0], eye[1] - q[1])) + 55, 40])
        elif x == "close":
            j.update(azimuth=azimuth, elevation=8, focus=veg_look.closeup_focus(T, azimuth), span=min(2.4, 0.6 * H), leaves=has_leaves)
        if "eye" in j:  # the eye stands on the hillside, not on the level of the plant's foot
            j["eye"] = [j["eye"][0], j["eye"][1], j["eye"][2] + veg_look.ground_z(T["spec"], j["eye"])]
        jobs.append(j)
        got.append((x, j["out"]))
    return jobs, got


def look(name: str, views=("clay", "leaf", "far"), azimuth: float = 0.0, size: int = 640, foliage: str | None = None,
         sheet: bool = False, triangles: int | None = None) -> list:
    """Render views of the plant; returns [(view name, png path)]. See look_plant (the tool) for the views."""
    from . import veg_look
    T = grown(name)
    if T.get("sward"):
        raise ValueError("a sward is a tile of blades: one tile alone says nothing. Export it (export_plant) and judge it as a FIELD in an "
                         "engine: spikes/godot_veg/field.gd lays the tiles with their LOD rings and fade and measures the ground hidden, "
                         "triangles and GPU time (field_measure.py); grow_plant's report has the blade and triangle counts")
    d = _dir(name)
    v = len(history(name))
    if sheet:
        ref = reference(name)
        if not ref:
            raise ValueError("no reference yet: plant_reference(name, image_path, ...) first")
        out = str(d / f"sheet_v{v}.png")
        veg_look.reference_sheet(load(name), ref, out, bare=ref["bare"], title=name, foliage=foliage)
        return [("sheet", out)]
    suffix = (f"_{name.partition('#')[2]}" if "#" in name else "") + (f"_az{int(round(azimuth))}" if azimuth else "") + (f"_{triangles}tris" if triangles else "")
    if T.get("clump"):  # a small plant is seen from the side, from standing height and from above; and its pictures
        import math
        from PIL import Image
        from . import veg_leaf, veg_small
        s = T["spec"]
        at = veg_leaf.atlas(s["leaves"], (s.get("bark") or {}).get("twig_color") or [0.45, 0.4, 0.35])
        c = at["color"]
        img = np.clip(c[..., :3] * c[..., 3:] + np.array([0.75, 0.78, 0.82]) * (1 - c[..., 3:]), 0, 1)
        pa = str(d / f"atlas{suffix}_v{v}.png")
        Image.fromarray((img * 255).astype(np.uint8)).resize((size, size)).save(pa)
        H, R = T["height"], max(veg_small.measures(T)["spread_m"] / 2, 0.1)
        D = 2.2 * max(H, 2 * R)
        ca, sa = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
        e = lambda dist, z: [-sa * dist, -ca * dist, z]
        jobs = [{"name": "side", "eye": e(D, 0.45 * H), "look": [0, 0, 0.45 * H], "fov": 40},
                {"name": "stand", "eye": e(max(1.5, 1.5 * D), 1.6), "look": [0, 0, 0.45 * H], "fov": 28 if H < 1 else 46},
                {"name": "above", "eye": e(0.3 * D, 1.6 * D), "look": [0, 0, 0.3 * H], "fov": 40}]
        got = [("atlas", pa)]
        for j in jobs:
            j.update(out=str(d / f"{j['name']}{suffix}_v{v}.png"), size=[size, size], sun=[azimuth + 235, 40])
            got.append((j["name"], j["out"]))
        veg_look.render(T, jobs, foliage=foliage, triangles=triangles)
        return got
    jobs, got = _view_jobs(T, views, azimuth, size, lambda x: str(d / f"{x}{suffix}_v{v}.png"))
    veg_look.render(T, jobs, foliage=foliage, triangles=triangles)
    return got


def look_group(names: list[str], at: list | None = None, spacing: float | None = None, views=("far",),
               azimuth: float = 0.0, size: int = 640, foliage: str | None = None, triangles: int | None = None) -> list:
    """Several plants standing together in one picture. `at` = [[x, y], ...] per plant (m), or `spacing` m apart on a
    loose ring (default: 0.35 x the tallest's height). The first plant's environment (ground slope, look) sets the
    scene; "far"/"near" frame the whole group. Returns [(view, path)]."""
    from . import veg_look
    import math
    trees = [grown(n) for n in names]
    H = max(t["height"] for t in trees)
    if at is None:
        sp = spacing or 0.35 * H
        r = sp / (2 * math.sin(math.pi / max(len(names), 2))) if len(names) > 1 else 0.0
        at = [[r * math.cos(2.4 * i + 0.5) * (0.8 + 0.2 * ((i * 7) % 3)), r * math.sin(2.4 * i + 0.5)] for i in range(len(names))]
    if len(at) != len(names):
        raise ValueError(f"{len(names)} plants but {len(at)} positions")
    at = [np.asarray(a, float)[:2] for a in at]
    d = home() / "_groups"
    d.mkdir(parents=True, exist_ok=True)
    tag = "+".join(names).replace("#", "-")
    if len(tag) > 60:  # (a cut-off name read as another plant's)
        tag = f"{names[0].replace('#', '-')}+{len(names) - 1}more_{hashlib.sha1(tag.encode()).hexdigest()[:6]}"
    tag += (f"_az{int(round(azimuth))}" if azimuth else "") + (f"_{triangles}tris" if triangles else "")
    c_, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    toward = np.array([-s_, -c_, 0.0])
    right = np.array([c_, -s_, 0.0])
    cen = np.r_[np.mean(at, axis=0), 0.0]
    # the group's width as this view sees it (crowns included), and the eye's distance to fill ~80% of the frame
    rads = [float(np.percentile(np.linalg.norm(t["pos"][:, :2], axis=1), 98)) for t in trees]
    xs = [float(np.r_[a, 0] @ right) for a in at]
    width = max(x + r for x, r in zip(xs, rads)) - min(x - r for x, r in zip(xs, rads))
    depth = max(float(np.r_[a, 0] @ -toward) + r for a, r in zip(at, rads))
    aspect = 1.3

    def frame(fov):  # vertical fov deg -> eye distance from the group's middle
        tv = math.tan(math.radians(fov) / 2)
        return max(H / (2 * tv), width / (2 * tv * aspect)) * 1.2 + max(depth, 0.0)

    jobs, got = [], []
    for k, x in enumerate(views):
        nm = x if isinstance(x, str) else x.get("name", f"camera{k + 1}")
        o = str(d / f"{tag}_{nm}.png")
        j = {"out": o, "size": [int(size * aspect), size], "sun": [azimuth + 235, 40]}
        if isinstance(x, dict):  # (world metres, the same frame as `at`)
            j.update(eye=x["eye"], look=x["look"], fov=x.get("fov", 40), clay=bool(x.get("clay")))
        elif x in ("far", "clay"):
            j.update(eye=(cen + toward * frame(30) + [0, 0, 1.7]).tolist(), look=(cen + [0, 0, 0.47 * H]).tolist(), fov=30)
            if x == "clay":
                j.update(clay=True, leaves=False)
        elif x == "near":
            j.update(eye=(cen + toward * (0.5 * frame(62) + 2.0) + [0, 0, 1.7]).tolist(), look=(cen + [0, 0, 0.4 * H]).tolist(), fov=62)
        elif x == "top":
            j.update(eye=(cen + [0, -0.01, 2.4 * max(width, H)]).tolist(), look=cen.tolist(), fov=30)
        else:
            raise ValueError(f"group views: far, near, clay, top or a camera {{'eye', 'look', 'fov'}} (got {x!r})")
        if isinstance(x, str):  # (the eye stands on the hillside)
            j["eye"] = [j["eye"][0], j["eye"][1], j["eye"][2] + veg_look.ground_z(trees[0]["spec"], j["eye"])]
        jobs.append(j)
        got.append((nm, o))
    others = [(t, a.tolist(), (i * 137.5) % 360 if names[i] in names[:i] else 0.0)
              for i, (t, a) in enumerate(zip(trees[1:], at[1:]), start=1)]  # (a repeated plant is turned; others stand as made)
    veg_look.render(trees[0], jobs, foliage=foliage, others=others, at=at[0].tolist(), triangles=triangles)
    return got


def impostor(name: str, px: int = 512, season: str | None = None, kind: str = "octahedral", **over) -> dict:
    """The plant from two sides (looking along +y, then along +x) for the last LOD's crossed quads: {"image" (h, 2w, 4)
    0..1 = albedo with the shade of what stands above baked in, "normal" (h, 2w, 3) = its tangent-space normal map
    (each half in its own quad's frame), "size": the square each view covers (m), "height": its middle's height (m)}.
    Three unlit passes per view (blender_vegetation._pass_material: albedo, shading normal, sky reaching the point),
    put together by veg_export_parts.impostor_maps; `over` = its numbers (shade_amount, depth)."""
    from PIL import Image
    import tempfile
    from . import veg_export, veg_look
    from . import veg_export_parts
    T = grown(name)
    if season:  # the same grown plant shown in another season ("snow" = as it stands, under snow)
        T = {**T, "spec": {**T["spec"], **({"snow": 0.8, "season": "winter"} if season == "snow" else {"season": season})}}
    if kind in ("octahedral", "hemi_octahedral", True):  # one quad, N x N views over the upper hemisphere (veg_impostor)
        from . import veg_impostor
        over = dict(over)
        return veg_impostor.bake(T, int(over.pop("frames", veg_impostor.FRAMES)), int(over.pop("frame_px", veg_impostor.FRAME_PX)),
                                 geometry=over.pop("geometry", None), **{k_: v_ for k_, v_ in over.items() if k_ in ("shade_amount", "shade_bright")})
    H = T["height"]
    R = float(np.percentile(np.linalg.norm(T["pos"][:, :2], axis=1), 99.5))
    S = float(max(H, 2 * R) * 1.06)
    with tempfile.TemporaryDirectory(prefix="hifipushie-vegimp-") as tmp:
        jobs = [{"out": f"{tmp}/{kind}{i}.png", "size": [px, px], "azimuth": az, "elevation": 0, "focus": [0, 0, 0.5 * H], "span": S,
                 "leaves": True, "transparent": True, "no_ground": True, "pass": kind}
                for kind in ("albedo", "normal", "shade") for i, az in enumerate(veg_export.IMPOSTOR_AZIMUTHS)]
        veg_look.render(T, jobs)
        rd = lambda kind: [np.asarray(Image.open(f"{tmp}/{kind}{i}.png").convert("RGBA"), np.float32) / 255 for i in range(2)]
        from . import veg_style
        if "depth" not in over and not veg_style.sheet(T["spec"]):
            over = {**over, "depth": veg_export.IMPOSTOR["depth_cards"]}
        m = veg_export_parts.impostor_maps(rd("albedo"), rd("normal"), rd("shade"), **over)
    return {**m, "size": S, "height": 0.5 * H}


def export(name: str, out_dir: str | None = None, triangles: int | None = None, lods: int = 1, seasons=("summer",),
           wet: bool = False, impostor_lod: bool | str = False, lod_files: bool = False, grade: str = "full") -> dict:
    """The plant's GLB (see veg_export_glb.write_glb). lods 1-3 mesh LODs (+ impostor_lod: crossed quads with its picture
    as the last); lod_files also writes each LOD as <name>_LOD<k>.glb for engines without MSFT_lod.
    grade "groundcover" (small plants only): the clump baked onto a few cards per LOD (veg_groundcover), its own folder
    (default export_groundcover/) of <name>_LOD0..2.glb + <name>.glb + <name>_seasons.json."""
    from . import veg_export
    from . import veg_export_files, veg_export_glb
    T = grown(name)
    if T.get("sward"):  # a tile of blades: its own files (LODs are fewer / wider blades; no impostor, no budget)
        from . import veg_sward
        c = veg_sward.export(T, out_dir or str(_dir(name) / "export"), name.replace("#", "_"),
                             seasons=tuple(seasons) if seasons and len(seasons) > 1 else ("summer", "spring", "autumn", "winter", "snow"))
        c["grade"] = "sward"
        return c
    if grade == "groundcover":
        from . import veg_groundcover
        stem = name.replace("#", "_")
        c = veg_groundcover.export(T, out_dir or str(_dir(name) / "export_groundcover"), stem,
                                   seasons=tuple(seasons) if seasons and len(seasons) > 1 else veg_groundcover.SEASONS)
        c["grade"] = "groundcover"
        return c
    if grade != "full":
        raise ValueError(f"grade must be 'full' or 'groundcover', not {grade!r}")
    out = Path(out_dir) if out_dir else _dir(name) / "export"
    kind = "cross" if impostor_lod == "cross" else "octahedral"
    imp = impostor(name, season=seasons[0] if seasons and seasons[0] != T["spec"].get("season", "summer") else None, kind=kind) if impostor_lod else None
    if imp is not None and len(seasons) > 1:  # a picture per season: the last LOD changes with the year like the others
        geo = {}  # (seasons with the same geometry share their normal / depth / shade frames: only the albedo is rendered again)
        if kind == "octahedral":
            from . import veg_impostor
            geo[veg_impostor.geometry_key(T["spec"], seasons[0])] = imp.get("passes")
        imp["seasons"] = {}
        for se in seasons[1:]:
            gk = veg_impostor.geometry_key(T["spec"], se) if kind == "octahedral" else None
            r_ = impostor(name, season=se, kind=kind, **({"geometry": geo.get(gk)} if kind == "octahedral" else {}))
            if gk is not None:
                geo.setdefault(gk, r_.get("passes"))
            imp["seasons"][se] = {k_: v_ for k_, v_ in r_.items() if k_ in ("image", "normal")}
    stem = name.replace("#", "_")
    c = veg_export_glb.write_glb(T, str(out / f"{stem}.glb"), stem, triangles=triangles, lods=lods, seasons=seasons, wet=wet, impostor=imp)
    c["total"] = c["wood_triangles"] + c["foliage_triangles"]
    c["over"] = max(0, c["total"] - triangles) if triangles else 0
    c["files"] = [c["path"]]
    if not T.get("clump"):  # the file as an engine gets it: nothing but the trunk's foot under the ground
        from . import veg_ground
        c["ground"] = veg_ground.audit_glb(c["path"], T["spec"], float(T["radius"][1]))
    if lod_files and len(c["lods"]) > 1:
        base = triangles or (c["style"]["budget"] if c.get("style") else c["lods"][0]["triangles"])
        for li, L in enumerate(c["lods"]):
            if L.get("impostor"):
                f = veg_export_glb.write_impostor(T, str(out / f"{stem}_LOD{li}.glb"), stem, imp, seasons)
            else:
                f = veg_export_glb.write_glb(T, str(out / f"{stem}_LOD{li}.glb"), stem, triangles=int(base * veg_export.LODS[li][0]),
                                         seasons=seasons, wet=wet, cap=veg_export.LODS[li][1])["path"]
            c["files"].append(f)
    # for engines that read neither MSFT_lod, out-of-scene nodes nor KHR_materials_variants (Godot 4.7 reads none of the three)
    if not T.get("clump"):
        f = veg_export_files.write_collision(T, str(out / f"{stem}_collision.glb"), stem)
        if f:
            c["files"].append(f)
            c["collision_file"] = f
    sj = veg_export_files.seasons_json(c["path"])
    if sj:
        c["files"].append(sj["path"])
        c["seasons_file"] = sj["path"]
    return c


def blender_import(glb: str, frames: int = 0, out: str | None = None, **job) -> dict:
    """Open a GLB with Blender's own glTF importer and report what arrived (objects, uv sets, attributes, variants);
    with frames, also render it swaying from its wind channels into `out`."""
    import subprocess
    import tempfile
    from . import render as _render
    script = Path(__file__).with_name("blender_veg_wind.py")
    with tempfile.TemporaryDirectory(prefix="hifipushie-vegwind-") as tmp:
        rp = Path(tmp) / "report.json"
        jp = Path(tmp) / "job.json"
        jp.write_text(json.dumps({"glb": str(glb), "frames": frames, "out": out, "report": str(rp), **job}))
        r = subprocess.run([_render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script),
                            "--", str(jp)], capture_output=True, text=True, timeout=1800)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
        return json.loads(rp.read_text())


def wind(name: str, triangles: int | None = 20000, seconds: float = 4.0, fps: int = 12, strength: float = 1.0,
         wind_from: float = 270.0, azimuth: float = 0.0, size: int = 480) -> dict:
    """The exported plant swaying: its GLB (at `triangles`) imported by Blender's glTF importer and moved from the
    file's own wind channels by the recipe an engine shader would use. Writes wind_v<n>.mp4 (when ffmpeg is there),
    the frames, and wind_v<n>_strip.png (six frames side by side + their difference from frame 0); returns paths, the
    importer's report and how far the plant moved."""
    import shutil
    import subprocess
    from PIL import Image
    from . import veg_export_glb
    T = grown(name)
    d = _dir(name)
    v = len(history(name))
    stem = name.replace("#", "_")
    glb = veg_export_glb.write_glb(T, str(d / "export" / f"{stem}_wind.glb"), stem, triangles=triangles)["path"]
    fr = d / f"wind_v{v}"
    if fr.exists():
        shutil.rmtree(fr)
    fr.mkdir(parents=True)
    n = int(round(seconds * fps))
    rep = blender_import(glb, frames=n, out=str(fr), fps=fps, strength=strength, height=T["height"], azimuth=azimuth,
                         size=[size, int(size * 1.12)], **{"from": wind_from})
    files = sorted(fr.glob("f_*.png"))
    ims = [np.asarray(Image.open(f).convert("RGB"), np.float32) for f in files]
    pick = [int(round(i * (len(ims) - 1) / 5)) for i in range(6)]
    top = np.concatenate([ims[i] for i in pick], axis=1)
    diff = np.concatenate([np.clip(np.abs(ims[i] - ims[0]) * 4, 0, 255) for i in pick], axis=1)
    strip = str(d / f"wind_v{v}_strip.png")
    Image.fromarray(np.concatenate([top, diff], axis=0).astype(np.uint8)).save(strip)
    moved = float(np.mean([(np.abs(i_ - ims[0]).max(-1) > 24).mean() for i_ in ims[1:]])) if len(ims) > 1 else 0.0
    out = {"frames": str(fr), "strip": strip, "glb": glb, "import": rep, "moved_share": round(moved, 3), "n": len(files),
           "height": float(T["height"]), "displacement": rep.get("displacement") or {}}
    if shutil.which("ffmpeg"):
        mp4 = str(d / f"wind_v{v}.mp4")
        q = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(fr / "f_%03d.png"),
                            "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", mp4], capture_output=True, text=True)
        if q.returncode == 0:
            out["mp4"] = mp4
    return out


def export_set(name: str, out_dir: str | None = None, triangles: int | None = None, lods: int = 1,
               seasons=("summer",), wet: bool = False) -> dict:
    """The set as ONE GLB (<name>_set.glb): a node per plant, one bark and one foliage material shared."""
    from . import veg_export_glb
    names = set_names(name)
    if not names:
        raise ValueError(f"{name} has no set: grow_plant(name, patch={{\"set\": {{\"count\": 5}}}})")
    out = Path(out_dir) if out_dir else _dir(name) / "export"
    c = veg_export_glb.write_glb([grown(n_) for n_ in names], str(out / f"{name}_set.glb"),
                             [n_.replace("#", "_") for n_ in names], triangles=triangles, lods=lods, seasons=seasons, wet=wet)
    c["total"] = c["wood_triangles"] + c["foliage_triangles"]
    return c
