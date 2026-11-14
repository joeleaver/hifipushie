"""The card atlas: built once per key, cached on disk, its parts, variants and files. Part of the leaves, twigs and their cards (veg_leaf.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import veg_leaf
from .vegetation_kernels import _child
from .veg_leaf_cards import card_mesh, card_spec, rasterize
from .veg_leaf_twig import twig_mesh

def atlas(leaves: dict, wood_color=(0.2, 0.15, 0.1)) -> dict:
    """The foliage atlas of a plant: every card variant's picture in a grid (color RGBA, normal, mask), and the cards
    cut to them with their uvs in the atlas. `fill` = the share of each card's area its alpha covers (overdraw's
    other side: a card half empty is drawn twice for nothing). Kept by content (a dense needle atlas takes 20 s)."""
    key = _atlas_key(leaves, wood_color)
    if key not in veg_leaf._ATLAS:
        if len(veg_leaf._ATLAS) > 12:
            veg_leaf._ATLAS.pop(next(iter(veg_leaf._ATLAS)))
        a = _disk_get(key)
        if a is None:
            a = _atlas(leaves, wood_color)
            _disk_put(key, a)
            a = _disk_get(key) or a  # (the same 8-bit maps whether it was just made or read back)
        veg_leaf._ATLAS[key] = a
    a = veg_leaf._ATLAS[key]
    return {**a, "cards": [dict(c) for c in a["cards"]]}


def _atlas_key(leaves, wood_color) -> str:
    import json
    return json.dumps([leaves, list(wood_color)], sort_keys=True, default=float)


def atlas_ready(leaves: dict, wood_color=(0.2, 0.15, 0.1)) -> bool:
    """Whether this atlas is already made (in memory or on disk): asking for it costs nothing."""
    key = _atlas_key(leaves, wood_color)
    return key in veg_leaf._ATLAS or _disk_path(key).exists()


def _disk_path(key: str):
    """Atlases are kept on disk by content and this module's source (a needle atlas takes minutes to rasterise):
    $HIFIPUSHIE_VEG_CACHE, else ~/.cache/hifipushie/veg_atlas; the 60 most recently used are kept."""
    import hashlib
    import os
    from pathlib import Path
    root = Path(os.environ.get("HIFIPUSHIE_VEG_CACHE") or Path.home() / ".cache" / "hifipushie" / "veg_atlas")
    from . import moved
    here = Path(__file__).parent  # (C457: veg_leaf.py with every module it was split into; this file alone left the
    # cache blind to a change in the twig or the card it rasterises)
    code = hashlib.sha1(b"".join((here / f).read_bytes() for f in moved.files("veg_leaf"))).hexdigest()[:10]
    return root / f"{hashlib.sha1((code + key).encode()).hexdigest()[:24]}.npz"


def _disk_get(key: str):
    p = _disk_path(key)
    if not p.exists():
        return None
    try:
        z = np.load(p, allow_pickle=False)
        import json
        meta = json.loads(str(z["meta"]))
        a = {k: z[k].astype(np.float32) / 255.0 for k in ("color", "normal", "mask")}
        a["cards"] = [{"V": z[f"c{i}_V"], "F": z[f"c{i}_F"], "uv": z[f"c{i}_uv"], "area": float(ar)} for i, ar in enumerate(meta["areas"])]
        a.update(meta["rest"])
        p.touch()
        return a
    except Exception:
        return None


def _disk_put(key: str, a: dict) -> None:
    import json
    try:
        p = _disk_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        arr = {k: np.clip(a[k] * 255 + 0.5, 0, 255).astype(np.uint8) for k in ("color", "normal", "mask")}
        for i, c in enumerate(a["cards"]):
            arr.update({f"c{i}_V": c["V"], f"c{i}_F": c["F"], f"c{i}_uv": c["uv"]})
        rest = {k: v for k, v in a.items() if k not in ("color", "normal", "mask", "cards")}
        tmp = p.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, meta=json.dumps({"areas": [c["area"] for c in a["cards"]], "rest": rest}, default=float), **arr)
        tmp.replace(p)
        old = sorted(p.parent.glob("*.npz"), key=lambda q: q.stat().st_mtime)[:-60]
        for q in old:
            q.unlink(missing_ok=True)
    except OSError:
        pass


def part_specs(leaves: dict) -> dict:
    """The pictures a plant's atlas holds: {"main": leaves} plus `leaves.parts` ({name: overrides merged over the
    leaves spec, its twig and its card}): a flower stalk beside the leaves, a dead frond, a seed head."""
    base = {k: v for k, v in leaves.items() if k != "parts"}
    out = {"main": base}
    for name, ov in (leaves.get("parts") or {}).items():
        sp = {**base, **{k: v for k, v in ov.items() if k not in ("twig", "card")}}
        sp["twig"] = {**(base.get("twig") or {}), **(ov.get("twig") or {})}
        cb, co = base.get("card") or {}, ov.get("card") or {}
        sp["card"] = {**cb, **co, "twig": {**(cb.get("twig") or {}), **(co.get("twig") or {})},
                      "leaf": {**(cb.get("leaf") or {}), **(co.get("leaf") or {})}}
        out[name] = sp
    return out


def part_cards(leaves: dict) -> dict:
    """{part name: [the atlas's card indices that show it]}."""
    out, k = {}, 0
    for name, sp in part_specs(leaves).items():
        nv = int({**veg_leaf.CARD, **(sp.get("card") or {})}["variants"])
        out[name] = list(range(k, k + nv))
        k += nv
    return out


def card_variant(tw: dict, nv: int) -> np.ndarray:
    """Which card each twig draws: its own (`card`, plants assembled from named parts) or one by its key."""
    if tw.get("card") is not None:
        return np.asarray(tw["card"], int) % max(nv, 1)
    return (_child(tw["key"], 11) % np.uint64(nv)).astype(int)


def _atlas(leaves, wood_color) -> dict:
    parts = part_specs(leaves)
    if len(parts) > 1:
        return _atlas_parts(parts, leaves, wood_color)
    return _atlas_one(leaves, wood_color)


def _atlas_parts(parts, leaves, wood_color) -> dict:
    """Each part's own atlas, laid side by side in one square image (uvs rescaled)."""
    subs = [_atlas_one(sp, wood_color) for sp in parts.values()]
    size = max(a["color"].shape[0] for a in subs)
    g = int(math.ceil(math.sqrt(len(subs))))
    A = {"color": np.zeros((g * size, g * size, 4), np.float32), "normal": np.zeros((g * size, g * size, 3), np.float32),
         "mask": np.zeros((g * size, g * size, 3), np.float32)}
    A["normal"][...] = (0.5, 0.5, 1.0)
    cards, fills = [], []
    for i, a in enumerate(subs):
        r, c = divmod(i, g)
        n = a["color"].shape[0]
        for k in A:
            A[k][r * size: r * size + n, c * size: c * size + n] = a[k]
        f = n / (g * size)
        for cm in a["cards"]:  # (v = 0 is the image's bottom row)
            cm = dict(cm)
            cm["uv"] = np.c_[c * size / (g * size) + cm["uv"][:, 0] * f, 1 - (r * size / (g * size) + (1 - cm["uv"][:, 1]) * f)]
            cards.append(cm)
        fills.append(a["fill"])
    return {**A, "cards": cards, "fill": float(np.mean(fills)), "grid": g, "size": size,
            "triangles": int(np.mean([len(c["F"]) for c in cards]))}


def _atlas_one(leaves, wood_color) -> dict:
    wood_color = leaves.get("wood_color", wood_color)  # (a part's own: dead twigs are grey)
    cd = {**veg_leaf.CARD, **(leaves.get("card") or {})}
    cs = card_spec(leaves)
    tw = {**veg_leaf.TWIG, **cs["twig"]}
    nv, size = int(cd["variants"]), int(cd["size"])
    g = int(math.ceil(math.sqrt(nv * (2 if cd["end"] else 1))))
    A = {"color": np.zeros((g * size, g * size, 4), np.float32), "normal": np.zeros((g * size, g * size, 3), np.float32),
         "mask": np.zeros((g * size, g * size, 3), np.float32)}
    A["normal"][...] = (0.5, 0.5, 1.0)
    cards, fills = [], []
    for i in range(nv):
        tm = twig_mesh(cs, i)
        R = rasterize(tm, leaves.get("color", [0.16, 0.3, 0.08]), wood_color, size)
        r, c = divmod(i, g)
        sl = (slice(r * size, (r + 1) * size), slice(c * size, (c + 1) * size))
        A["color"][sl][..., :3] = R["color"]
        A["color"][sl][..., 3] = R["alpha"]
        A["normal"][sl] = R["normal"]
        A["mask"][sl] = R["mask"]
        cm = card_mesh(R["alpha"], R["frame"], int(cd["verts"]), cd["cup"], int(cd["cross"]), tw["droop"], tw["length"],
                       int(cd["strips"]))
        cm["V"] = cm["V"] * cd["scale"]
        px_area = float((R["alpha"] > 0.5).sum()) * (R["frame"][2] / size) ** 2 * cd["scale"] ** 2
        fills.append(px_area / max(cm["area"] / int(cd["cross"]) * cd["scale"] ** 2, 1e-12))
        cm["uv"] = np.c_[(c + cm["uv"][:, 0]) / g, 1 - (r + 1 - cm["uv"][:, 1]) / g]
        if cd["end"]:  # the same twig seen from its tip, on a card across the shoot where its foliage is
            Vt = tm["V"]
            leafv = np.unique(tm["F"][tm["mat"] == 1])
            yc = float(np.median(Vt[leafv, 1])) if len(leafv) else 0.6 * tw["length"]
            R2 = rasterize({**tm, "V": np.c_[Vt[:, 0], Vt[:, 2], Vt[:, 1]]}, leaves.get("color", [0.16, 0.3, 0.08]), wood_color, size)
            r2, c2 = divmod(nv + i, g)
            sl2 = (slice(r2 * size, (r2 + 1) * size), slice(c2 * size, (c2 + 1) * size))
            A["color"][sl2][..., :3] = R2["color"]
            A["color"][sl2][..., 3] = R2["alpha"]
            A["normal"][sl2] = R2["normal"]
            A["mask"][sl2] = R2["mask"]
            ce = card_mesh(R2["alpha"], R2["frame"], int(cd["verts"]), 0.0, 1, 0.0, tw["length"], 0)
            # (a shallow cone opening toward the tip: seen from the side it is not a line)
            Ve = np.c_[ce["V"][:, 0], yc + 0.25 * np.hypot(ce["V"][:, 0], ce["V"][:, 1]), ce["V"][:, 1]] * cd["scale"]
            uve = np.c_[(c2 + ce["uv"][:, 0]) / g, 1 - (r2 + 1 - ce["uv"][:, 1]) / g]
            cm = {"V": np.vstack([cm["V"], Ve]), "F": np.vstack([cm["F"], ce["F"] + len(cm["V"])]),
                  "uv": np.vstack([cm["uv"], uve]), "area": cm["area"]}
        cards.append(cm)
    # `leaves.color` is the leaf as you SEE it lit: the per-leaf tones, blade shading and the mask's shade had the
    # atlas's median leaf at 0.7 of it (a lit birch rendered at V 0.43 against a photo's 0.69)
    leaf_px = (A["color"][..., 3] > 0.6) & (A["mask"][..., 0] > 0.5)
    if leaf_px.any():
        lum = lambda c_: 0.2126 * c_[..., 0] + 0.7152 * c_[..., 1] + 0.0722 * c_[..., 2]
        seen = float(np.median(lum(A["color"][leaf_px][:, :3]) * A["mask"][leaf_px][:, 2]))
        k_ = float(np.clip(lum(np.asarray(leaves.get("color", [0.16, 0.3, 0.08]), float)) / max(seen, 1e-6), 1.0, 1.8))
        A["color"][..., :3] = np.clip(A["color"][..., :3] * k_, 0, 1)
    return {**A, "cards": cards, "fill": float(np.mean(fills)), "grid": g, "size": size,
            "triangles": int(np.mean([len(c["F"]) for c in cards]))}


def write_atlas(at: dict, stem: str) -> dict:
    """<stem>_color.png (RGBA), _normal.png, _mask.png (R through, G rough, B shade)."""
    from PIL import Image
    out = {}
    for k in ("color", "normal", "mask"):
        out[k] = f"{stem}_{k}.png"
        Image.fromarray(np.clip(at[k] * 255 + 0.5, 0, 255).astype(np.uint8)).save(out[k])
    return out
