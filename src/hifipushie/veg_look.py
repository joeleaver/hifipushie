"""Looks at a plant: Blender renders (clay skeleton, leafed colour) and the reference sheet (photo, outlines over
each other, renders, numbers)."""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from . import render as _render
from . import veg_ground, veg_mesh, vegetation

SCRIPT = Path(__file__).with_name("blender_vegetation.py")


# needle litter and bare soil under a closed canopy (sRGB): what a look draws under a plant whose environment.setting is
# a stand, unless the spec's look.ground gives colours
FOREST_FLOOR = {"color": [0.25, 0.18, 0.12], "color2": [0.34, 0.25, 0.16], "dry": [0.29, 0.22, 0.15]}


def _euler(frames: np.ndarray) -> np.ndarray:
    from scipy.spatial.transform import Rotation
    return Rotation.from_matrix(frames).as_euler("xyz") if len(frames) else np.zeros((0, 3))


BARK_OF = {"furrowed": "furrowed", "plates": "plates", "lenticel": "lenticel", "scales": "scales"}


def ground_z(spec: dict, at) -> float:
    """The ground's height at [x, y] on the plant's hillside (environment.ground: slope deg, falling `toward`)."""
    g = (spec.get("environment") or {}).get("ground") or {}
    if not g.get("slope"):
        return 0.0
    t = np.asarray(g.get("toward", [1, 0]), float)
    t = t / max(np.linalg.norm(t), 1e-9)
    return float(-math.tan(math.radians(g["slope"])) * (np.asarray(at, float)[:2] @ t))


def _plant_job(tree: dict, tmp: Path, out: Path, tag: str, foliage: str | None, triangles: int | None = None) -> tuple[dict, dict]:
    """One plant's arrays (an npz) and its part of the Blender job; also its counts."""
    from . import veg_bark, veg_leaf
    s = tree["spec"]
    lf = s["leaves"]
    if s.get("season") == "autumn" and not lf.get("evergreen", str(lf.get("shape", "")).startswith("needle")):
        lf = {**lf, "color": lf.get("autumn", [0.78, 0.56, 0.16])}  # (veg_export.AUTUMN)
    foliage = foliage or lf.get("foliage", "cards")
    bark = dict(s.get("bark") or {})
    bm = veg_bark.bark_maps(bark.get("kind", "furrowed"), 256, seed=int(s.get("seed", 1)))
    sc = float(bark.get("scale", 1.0))
    tile = [bm["tile"][0] * sc, bm["tile"][1] * sc]
    M = veg_mesh.tubes(tree, tile=tile)
    tw = veg_leaf.place(tree)
    at_b = None
    if triangles:  # the budgeted plant, exactly as export_plant(triangles=) writes it
        from . import veg_export
        if foliage != "cards":
            raise ValueError("a triangle budget is for cards (what the export draws): foliage='cards'")
        ct = veg_leaf.atlas(lf, bark.get("twig_color") or [0.45, 0.4, 0.35])["triangles"] if len(tw["pos"]) else 0
        bud = veg_export.budget(tree, triangles, tile, ct)
        M = bud["wood"]
        if bud.get("boughs"):  # cards of the tree's own boughs
            from . import veg_bough
            at_b = veg_bough.atlas(tree, lf, bark.get("twig_color") or [0.45, 0.4, 0.35], bud["boughs"])
            tw = veg_bough.place(tree, bud["boughs"], at_b)
        else:
            lf, cap_c, back_c = veg_export.cluster_leaves(lf, bud["keep"])
            tw = veg_export.pick_twigs(tree, bud["keep"], bud["min_radius"], bud["protect"], tw, cap=cap_c, back=back_c)[0]
    arrays = {"V": M["V"], "F": M["F"], "tan": M["tan"], "radius": M["radius"], "uv": M["uv"], "dead": M["dead"]}
    info = {"triangles": int(len(M["F"])), "twigs": int(len(tw["pos"])), "foliage": foliage, "leaf_triangles": 0}
    at = None

    if len(tw["pos"]):
        if foliage == "cards":
            at = at_b or veg_leaf.atlas(lf, bark.get("twig_color") or [0.45, 0.4, 0.35])
            nv = len(at["cards"])
            if not tree.get("clump"):  # no card reaches under the ground
                gst = {}
                tw = veg_ground.clear(s, tw, at["cards"], veg_leaf.card_variant(tw, nv), stats=gst)
                info["ground"] = gst
            var = veg_leaf.card_variant(tw, nv)
            for i, c in enumerate(at["cards"]):
                arrays.update({f"card{i}_V": c["V"], f"card{i}_F": c["F"], f"card{i}_uv": c["uv"]})
            info.update(leaf_triangles=int(len(tw["pos"]) * at["triangles"]), card_fill=round(at["fill"], 2),
                        atlas_px=int(at["color"].shape[0]))
        else:
            if tw.get("part") is not None:  # (dead twig cards are cards: mesh foliage leaves them out)
                m_ = tw["part"] == 0
                tw = {k_: (v_[m_] if isinstance(v_, np.ndarray) and len(v_) == len(m_) else v_) for k_, v_ in tw.items() if k_ != "card"}
            nv = int(tw["variant"].max()) + 1
            var = tw["variant"]
            per = []
            if not tree.get("clump"):  # (twig meshes: the same rule on their own vertices)
                tw = veg_ground.clear(s, tw, [{"V": veg_leaf.twig_mesh(lf, i)["V"]} for i in range(nv)], var)
                var = tw["variant"]
            for i in range(nv):
                tm = veg_leaf.twig_mesh(lf, i)
                arrays.update({f"twig{i}_V": tm["V"], f"twig{i}_F": tm["F"], f"twig{i}_mat": tm["mat"], f"twig{i}_col": tm["col"]})
                per.append(len(tm["F"]))
            info["leaf_triangles"] = int(sum(per[v] for v in var))
        arrays.update(tw_pos=tw["pos"], tw_rot=_euler(tw["frame"]), tw_scale=tw["scale"], tw_var=var,
                      tw_tint=vegetation._u(tw["key"], 77))
    npz = tmp / f"plant{tag}.npz"
    np.savez(npz, **arrays)
    bark["maps"] = veg_bark.write(bm, str(out / f"bark{tag}"))
    if bark.get("base_kind"):
        bark["base_maps"] = veg_bark.write(veg_bark.bark_maps(bark["base_kind"], 256, seed=7), str(out / f"bark_base{tag}"))
    pj = {"npz": str(npz), "bark": bark,
          "leaf": {k: lf[k] for k in ("color", "through", "translucency", "roughness", "alpha_cut", "card_normal", "round") if k in lf},
          "cards": veg_leaf.write_atlas(at, str(out / f"foliage{tag}")) if at is not None else None,
          "snow": float(s.get("snow") or 0.0), "wet": float(s.get("wet") or 0.0)}
    return pj, info


def render(tree: dict, views: list[dict], save: str | None = None, timeout: float = 900, foliage: str | None = None,
           keep: str | None = None, others: list | None = None, triangles: int | None = None, at=None,
           curves: list | None = None) -> dict:
    """Render views in Blender (see blender_vegetation's job). foliage: "cards" (the twig atlas on cut cards: what a
    game draws) or "mesh" (twig meshes: close LODs, video); default the spec's `leaves.foliage`, else cards.
    others: [(tree, [x, y], yaw deg)] more plants standing in the same scene (a stand). `keep` = a folder for the
    atlas and bark maps (else a temp one). Returns timings and the first plant's counts."""
    s = tree["spec"]
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="hifipushie-veg-") as tmp:
        out = Path(keep or tmp)
        out.mkdir(parents=True, exist_ok=True)
        pj, info = _plant_job(tree, Path(tmp), out, "", foliage, triangles)
        if at is not None:
            pj.update(at=list(at), z=ground_z(s, at))
        plants = [pj]
        made = {id(tree): pj}
        for i, (t_, at_, yaw_) in enumerate(others or []):
            if id(t_) not in made:  # (the same tree stood many times is meshed once)
                made[id(t_)] = _plant_job(t_, Path(tmp), out, f"_{i + 1}", foliage, triangles)[0]
            pj2 = {**made[id(t_)], "at": list(at_), "yaw": float(yaw_), "z": ground_z(s, at_)}
            plants.append(pj2)
        env = s.get("environment") or {}
        job = {"plants": plants, "views": views, "save": save, **(s.get("look") or {})}
        if env.get("setting") in ("forest", "edge", "stand") and "color" not in (job.get("ground") or {}):
            job["ground"] = {**FOREST_FLOOR, **(job.get("ground") or {})}  # a stand's floor is litter, not a lawn
            job.setdefault("bounce_color", [0.6, 0.5, 0.4])  # (and what it throws back up is dim and brown, not a lawn's yellow-green)
            job.setdefault("bounce", 0.75)
        if env.get("ground"):
            job["ground"] = {**(job.get("ground") or {}), **env["ground"]}
        job["ruler"] = float(np.ceil(tree["height"]))
        if curves is not None:
            job["curves"] = curves
        jp = Path(tmp) / "job.json"
        jp.write_text(json.dumps(job))
        t1 = time.perf_counter()
        r = subprocess.run([_render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
                            str(SCRIPT), "--", str(jp)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    info.update(mesh_s=round(t1 - t0, 2), blender_s=round(time.perf_counter() - t1, 2), plants=len(plants))
    return info


def near_distance(tree: dict, toward, least: float = 5.0) -> float:
    """How far to stand for the near view: `least`, or 1.5 m clear of what the plant puts between 0.3 and 3 m high on
    that side (5 m from a spruce's trunk the eye was inside its skirt, a branch filling the picture)."""
    P = tree["pos"]
    m = (P[:, 2] > 0.3) & (P[:, 2] < 3.0)
    if not m.any():
        return least
    t = np.asarray(toward, float)[:2]
    side = np.abs(P[m][:, :2] @ np.array([-t[1], t[0]])) < 2.0
    reach = float((P[m][:, :2] @ t)[side].max()) if side.any() else 0.0
    return max(least, reach + 0.5 + 1.5)


def closeup_focus(tree: dict, azimuth: float = 0.0):
    """A point on the crown's near side at about half height, with twigs: where a close-up shows the foliage."""
    from . import veg_leaf
    tw = veg_leaf.place(tree)
    P = tw["pos"] if len(tw["pos"]) else tree["pos"][tree["ends"]]
    c, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    depth = -P[:, 0] * s_ + P[:, 1] * c  # toward +y is away from the camera at azimuth 0
    H = tree["height"]
    ok = (P[:, 2] > 0.4 * H) & (P[:, 2] < 0.65 * H)
    if not ok.any():
        ok = np.ones(len(P), bool)
    i = np.flatnonzero(ok)[np.argsort(depth[ok])[: max(1, ok.sum() // 20)]]
    return P[i].mean(0).tolist()


def overlay(ref_mask: np.ndarray, ours: np.ndarray, size: int = 420):
    """The two row-filled outlines at equal height, feet together: reference red, ours blue, both dark."""
    from PIL import Image
    A, B = vegetation._outline(ref_mask, size), vegetation._outline(ours, size)
    if (A & B[:, ::-1]).sum() > (A & B).sum():
        B = B[:, ::-1]
    im = np.full(A.shape + (3,), 255, np.uint8)
    im[A & ~B] = (225, 90, 80)
    im[B & ~A] = (80, 120, 225)
    im[A & B] = (70, 70, 70)
    cols = np.flatnonzero((A | B).any(0))
    return Image.fromarray(im[:, max(cols[0] - 8, 0): cols[-1] + 8])


def veg_leaf_place(T):
    from . import veg_leaf
    return veg_leaf.place(T)["pos"]


def reference_sheet(spec: dict, ref: dict | None, out: str, bare: bool = False, title: str = "", height: int = 520,
                    foliage: str | None = None) -> dict:
    """One row: the photo | outlines over each other | clay skeleton | leafed, with the numbers under it.
    ref = {"image", "mask": reference_mask kwargs, "credit"} or None."""
    from PIL import Image, ImageDraw
    T = vegetation.grow(spec)
    panels, text = [], [f"{title or spec.get('species', 'plant')}: age {T['spec']['age']}, {T['stats']['nodes']} nodes, "
                        f"{T['stats']['height_m']} m, trunk {T['stats']['trunk_diameter_m']} m, grown in {T['stats']['grow_s']} s"]
    az = 0
    info = {"stats": T["stats"]}
    if ref:
        R = vegetation.reference_mask(ref["image"], **ref["mask"])
        m = vegetation.match(T, R, bare=bare, azimuths=(0, 45, 90, 135))
        az = m["azimuth"]
        photo = Image.open(ref["image"]).convert("RGB")
        c = ref["mask"].get("crop")
        if c is None and ref["mask"].get("polygon"):
            P = np.asarray(ref["mask"]["polygon"])
            c = [max(int(P[:, 0].min()) - 20, 0), max(int(P[:, 1].min()) - 20, 0), int(P[:, 0].max()) + 20, int(P[:, 1].max()) + 20]
        photo = photo.crop(c) if c else photo
        photo = photo.resize((max(1, int(photo.width * height / photo.height)), height))
        panels += [photo, overlay(R, m["mask"], height)]
        f = lambda M: "  ".join(f"{k} {M[k]:.2f}" for k in ("width_over_height", "bole", "widest_at", "lopsided"))
        text += [f"outline IoU {m['iou']:.2f} (reference red, ours blue, view azimuth {az})",
                 f"reference: {f(m['ref'])}", f"ours:      {f(m['ours'])}"]
        info["match"] = {k: m[k] for k in ("iou", "azimuth", "ours", "ref")}
    ang = vegetation.branch_angles(T, 1)
    text.append(f"first-order branches: {ang['n']}, insertion p10/50/90 {ang['insertion_p10_50_90']} deg, "
                f"far-half elevation {ang['elevation_p10_50_90']} deg")
    info["angles"] = ang
    tmp = Path(tempfile.mkdtemp(prefix="hifipushie-vegsheet-"))
    sz = [int(height * 0.95), height]
    H = T["height"]
    c_, s_ = math.cos(math.radians(az)), math.sin(math.radians(az))
    toward = np.array([-s_, -c_, 0.0])  # from the tree toward the ortho views' camera

    def eye(dist, z):
        return (toward * dist + [0, 0, z]).tolist()

    views = [{"name": "clay", "azimuth": az, "out": str(tmp / "clay.png"), "size": sz, "leaves": False, "clay": True},
             {"name": "bare", "azimuth": az, "elevation": 4, "out": str(tmp / "bare.png"), "size": sz, "leaves": False}]
    has_leaves = len(veg_leaf_place(T)) > 0
    lv = has_leaves
    views += [{"name": "leaf", "azimuth": az, "elevation": 4, "out": str(tmp / "leaf.png"), "size": sz, "leaves": lv},
              {"name": "far", "eye": eye(max(70.0, 3.5 * H), 1.7), "look": [0, 0, 0.42 * H], "fov": 22,
               "out": str(tmp / "far.png"), "size": sz, "leaves": lv},
              {"name": "near", "eye": eye(near_distance(T, toward), 1.7), "look": [0, 0, min(0.5 * H, 6.0)], "fov": 62,
               "out": str(tmp / "near.png"), "size": sz, "leaves": lv}]
    if has_leaves:
        views.append({"name": "close", "azimuth": az, "elevation": 8, "out": str(tmp / "close.png"), "size": sz,
                      "focus": closeup_focus(T, az), "span": 2.4})
    else:
        views.pop(2)
    for v_ in views:  # the sun from behind the eye's left shoulder: a lit side and a shaded side in every view
        v_["sun"] = [az + 180 + 55, 40]
    info["render"] = render(T, views, foliage=foliage)
    r_ = info["render"]
    text.append(f"look: mesh {r_['mesh_s']} s + Blender {r_['blender_s']} s; {r_['triangles']} branch triangles; "
                f"{r_['twigs']} twigs as {r_['foliage']} = {r_['leaf_triangles']} triangles"
                + (f" (card fill {r_['card_fill']}, atlas {r_['atlas_px']} px)" if "card_fill" in r_ else ""))
    text.append("panels: photo | outlines | clay | bare | in leaf | from 70 m | from 5 m | foliage close-up (2.4 m across)")
    panels += [Image.open(v["out"]).convert("RGB") for v in views]
    rows = [panels[: (len(panels) + 1) // 2], panels[(len(panels) + 1) // 2:]] if len(panels) > 4 else [panels]
    W = max(sum(p.width for p in r) + 6 * (len(r) - 1) for r in rows)
    S = Image.new("RGB", (max(W, 900), (height + 6) * len(rows) + 16 * len(text) + 12), "white")
    for j, r in enumerate(rows):
        x = 0
        for p in r:
            S.paste(p, (x, j * (height + 6)))
            x += p.width + 6
    height = (height + 6) * len(rows)
    d = ImageDraw.Draw(S)
    for i, t in enumerate(text):
        d.text((6, height + 6 + 16 * i), t, fill=(0, 0, 0))
    if ref and ref.get("credit"):
        d.text((6, 4), ref["credit"], fill=(255, 255, 255))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    S.save(out)
    info["out"] = out
    return info
