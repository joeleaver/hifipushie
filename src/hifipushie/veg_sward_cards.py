"""The card-patch alternative of a sward, kept to MEASURE against the blades (spikes/godot_veg/field.gd): the same
grass the older way, upright alpha cards scattered over the tile wearing a strip picture of blades. Fewer triangles,
but alpha-tested overdraw, and thin blades thin out or shimmer through the mips (veg_groundcover's finding)."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from .veg_sward import _hash, blades


def card_patch(spec: dict, per_m2: float = 7.0, length: float = 1.0, px_m: int = 512, seed: int = 5) -> dict:
    """`per_m2` cards (each `length` m long, the tallest blade high, front and back faces) at any turn, wearing ONE strip
    picture drawn from the sward's own numbers (the blades standing in a slab as deep as the cards are apart; tileable
    along the strip). Returns mesh arrays + "image" (RGBA uint8)."""
    from PIL import Image, ImageDraw
    from .veg_export import _bleed
    from .veg_style import lin
    B = blades(spec)
    p = B["p"]
    S, H = float(p["size"]), float(p["height"][1]) * 1.02
    W_, Hpx = int(px_m * length), int(max(32, round(px_m * H)))
    ss = 4
    im = Image.new("RGBA", (W_ * ss, Hpx * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    to8 = lambda c: tuple(int(255 * (x * 12.92 if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055)) for x in np.clip(c, 0, 1))
    cg, ct, cs = np.array(lin(p["ground"])) * p["root_dark"], np.array(lin(p["tip"])), np.array(lin(p["straw"]))
    slab = 1.0 / max(per_m2 * length, 1e-6)
    sel = np.nonzero((B["root"][:, 1] % S) < slab)[0]
    order = sel[np.argsort(-B["h"][sel])]  # (tall ones first: short blades in front)
    n = 6
    t = np.linspace(0, 1, n + 1)
    for i in order:
        x0 = (B["root"][i, 0] % length) / length * W_ * ss
        h, w = B["h"][i], B["w"][i]
        side = np.cos(B["yaw"][i])  # the lean's share along the strip
        ang = B["lean"][i] + B["bend"][i] * t ** 1.5
        dx = np.concatenate([[0], np.cumsum(np.sin(ang[:-1]) * h / n)]) * side
        dz = np.concatenate([[0], np.cumsum(np.cos(ang[:-1]) * h / n)])
        wt = (1 - t ** p["taper"]) * w * 0.5 * max(abs(np.sin(B["yaw"][i])), 0.35)
        col = B["tone"][i] * (cg[None] * (1 - t[:, None] ** p["gradient"]) + (cs if B["dry"][i] else ct)[None] * t[:, None] ** p["gradient"])
        for k in range(n):
            for off in (-W_ * ss, 0, W_ * ss):  # (wrapped along the strip)
                X = lambda d_: x0 + off + d_ * px_m * ss
                Y = lambda z_: (Hpx - z_ * px_m) * ss
                dr.polygon([(X(dx[k] - wt[k]), Y(dz[k])), (X(dx[k] + wt[k]), Y(dz[k])), (X(dx[k + 1] + wt[k + 1]), Y(dz[k + 1])),
                            (X(dx[k + 1] - wt[k + 1]), Y(dz[k + 1]))], fill=(*to8(0.5 * (col[k] + col[k + 1])), 255))
    im = im.resize((W_, Hpx), Image.LANCZOS)
    A = np.asarray(im).copy()
    has = A[..., 3] > 8
    if has.any():
        A[..., :3] = (_bleed(A[..., :3].astype(np.float32) / 255, has) * 255).astype(np.uint8)
    n_c = max(1, int(round(per_m2 * S * S)))
    k = np.arange(n_c)
    c = np.c_[_hash(k + seed * 7, 51), _hash(k + seed * 7, 52)] * S
    yaw = _hash(k + seed * 7, 53) * np.pi
    d = np.c_[np.cos(yaw), np.sin(yaw), np.zeros(n_c)]
    Vs, Fs, Us, Ns, Ws = [], [], [], [], []
    cols, base = 4, 0
    for j in range(n_c):
        u0 = _hash(np.array([j + seed]), 54)[0]
        s_ = np.linspace(-length / 2, length / 2, cols + 1)
        P = np.vstack([np.c_[c[j, 0] + s_ * d[j, 0], c[j, 1] + s_ * d[j, 1], np.full(cols + 1, z)] for z in (0.0, H)])
        uv = np.vstack([np.c_[u0 + (s_ + length / 2) / length, np.full(cols + 1, v)] for v in (1.0, 0.0)])
        q = np.arange(cols)
        f = np.vstack([np.c_[q, q + 1, q + cols + 2], np.c_[q, q + cols + 2, q + cols + 1]])
        nrm = np.cross(d[j], [0, 0, 1.0])
        hz = P[:, 2] / H
        for side in (1.0, -1.0):
            N = np.tile(0.7 * np.array([0, 0, 1.0]) + 0.3 * side * nrm, (len(P), 1))
            Vs.append(P)
            Us.append(uv)
            Ns.append(N / np.linalg.norm(N, axis=1, keepdims=True))
            Fs.append((f if side > 0 else f[:, ::-1]) + base)
            base += len(P)
            Ws.append(np.c_[hz ** 1.5, hz ** 1.5 * float(np.clip(H / 1.2, 0.08, 1)), np.full(len(P), _hash(np.array([j]), 55)[0]), 0.5 * hz])
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "uv": np.vstack(Us), "N": np.vstack(Ns), "wind": np.vstack(Ws), "image": A, "p": p,
            "cards": n_c}


def write_cards(path: str, name: str, C: dict) -> dict:
    """The card patch as <path>/<name>_LOD0.glb + <name>_seasons.json (one season), in the sward's own file layout."""
    from . import veg_export, veg_groundcover
    p = C["p"]
    S = p["size"]
    buf = bytearray()
    views, accessors = [], []

    def blob(data: bytes, target=None):
        while len(buf) % 4:
            buf.append(0)
        views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(data), **({"target": target} if target else {})})
        buf.extend(data)
        return len(views) - 1

    def acc(a, kind, comp, target, minmax=False):
        a = np.ascontiguousarray(a)
        d = {"bufferView": blob(a.tobytes(), target), "componentType": comp, "count": int(len(a)), "type": kind}
        if minmax:
            d["min"], d["max"] = a.min(0).tolist(), a.max(0).tolist()
        accessors.append(d)
        return len(accessors) - 1

    y = lambda v_: np.stack([v_[:, 0], v_[:, 2], -v_[:, 1]], 1)
    V = C["V"] - np.array([S / 2, S / 2, 0.0])
    at = {"POSITION": acc(y(V).astype(np.float32), "VEC3", 5126, 34962, True), "NORMAL": acc(y(C["N"]).astype(np.float32), "VEC3", 5126, 34962),
          "TEXCOORD_0": acc(C["uv"].astype(np.float32), "VEC2", 5126, 34962), "TEXCOORD_1": acc(C["wind"][:, :2].astype(np.float32), "VEC2", 5126, 34962),
          "TEXCOORD_2": acc(C["wind"][:, 2:].astype(np.float32), "VEC2", 5126, 34962)}
    idx = acc(C["F"].astype(np.uint32).ravel(), "SCALAR", 5125, 34963)
    img = blob(veg_groundcover._png(C["image"]))
    sward = {"tile_m": S, "variant": p["variant"], "fade": {"start": p["fade"][0], "end": p["fade"][1]}, "ground_srgb": p["ground"],
             "color_gain": 1.0, "lod_rings_m": [], "kind": "cards"}
    while len(buf) % 4:
        buf.append(0)
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": "foliage", "mesh": 0}],
            "meshes": [{"name": "foliage", "primitives": [{"attributes": at, "indices": idx, "material": 0,
                                                            "extensions": {"KHR_materials_variants": {"mappings": [{"material": 0, "variants": [0]}]}}}]}],
            "materials": [{"name": "foliage", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 0.85},
                           "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": False}],
            "textures": [{"source": 0, "sampler": 0}], "images": [{"bufferView": img, "mimeType": "image/png"}],
            "samplers": [{"wrapS": 10497, "wrapT": 33071, "magFilter": 9729, "minFilter": 9987}],
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(buf)}],
            "extensionsUsed": ["KHR_materials_variants"], "extensions": {"KHR_materials_variants": {"variants": [{"name": "summer"}]}},
            "extras": {"hifipushie_plant": {"name": name, "style": {"name": p["style_name"], "kind": "sward cards"}, "sward": sward,
                                            "snow_numbers": veg_export.snow_numbers({}, None)}}}
    js = json.dumps(gltf, separators=(",", ":"), default=float).encode()
    js += b" " * (-len(js) % 4)
    out = Path(path) / f"{name}_LOD0.glb"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(buf)))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(buf), b"BIN\0"))
        f.write(bytes(buf))
    sj = veg_export.seasons_json(str(out))
    d = json.loads(Path(sj["path"]).read_text())
    d["sward"] = sward
    Path(path, f"{name}_seasons.json").write_text(json.dumps(d, indent=1))
    Path(sj["path"]).unlink()
    return {"path": str(out), "triangles": int(len(C["F"])), "cards": C["cards"]}
