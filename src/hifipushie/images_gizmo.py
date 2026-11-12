"""Decals as gizmos in the Blender scene (scene.sync / scene.pull): entries, the gizmo, and back from it. Part of images (images.py has the spec)."""
from __future__ import annotations

import numpy as np

from .images_frame import _offset, frame
from .images_project import _place

# ---- decals as gizmos in the Blender scene (scene.sync / scene.pull) -------------------------------------------------
def decal_entries(spec: dict) -> list[tuple[list, dict, str, object]]:
    """Every image entry in the spec's paint layers: (json path to it, the image dict, layer name, the layer's
    parts). Mask stacks included (["paint", layer, "mask", i, ..., "image"])."""
    out = []

    def walk(obj, path, ly, parts):
        if isinstance(obj, dict):
            if isinstance(obj.get("image"), dict):
                out.append((path + ["image"], obj["image"], ly, parts))
            for i, e in enumerate(obj.get("mask") or []):
                walk(e, path + ["mask", i], ly, parts)
    for ly, d in (spec.get("paint") or {}).items():
        walk(d, ["paint", ly], ly, (d or {}).get("part", "body") if isinstance(d, dict) else "body")
    return out


def _outline(fr: dict, n: int = 24) -> np.ndarray:
    """The decal's rectangle as it lies (a closed ring of world points: on the plane, or round the wrap)."""
    t = np.linspace(0, 1, n + 1)[:-1]
    z, o = np.zeros_like(t), np.ones_like(t)
    gu = np.concatenate([t, o, 1 - t, z])
    gv = np.concatenate([z, t, o, 1 - t])
    return _place(fr, gu, gv)




def gizmo(fr: dict) -> dict:
    """A decal's object for the Blender scene: {"matrix" (4 x 4, local -> world), "verts" (local), "edges"}.
    Planar and surface decals: origin at the centre, x = right, y = up, z = dir, scaled by the size (the object's
    scale is the decal's size); the unit rectangle, a tick on its top edge (up) and a normal stub. Cylinder and
    sphere wraps: origin on the axis at the label's centre height (a sphere's centre), x = toward the decal's
    centre, z = the axis, scaled uniformly by the label's height; its outline round the axis and the axis itself."""
    if fr["wrap"] in ("planar", "surface"):
        R = np.stack([fr["right"], fr["up"], fr["dir"]], 1)
        s = np.array([fr["w"], fr["h"], min(fr["w"], fr["h"])])
        M = np.eye(4)
        M[:3, :3] = R * s
        M[:3, 3] = fr["c"]
        verts = [[-0.5, -0.5, 0], [0.5, -0.5, 0], [0.5, 0.5, 0], [-0.5, 0.5, 0], [-0.08, 0.5, 0], [0.0, 0.62, 0],
                 [0.08, 0.5, 0], [0, 0, 0], [0, 0, 0.3]]
        edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [7, 8]]
        return {"matrix": M.tolist(), "verts": verts, "edges": edges}
    k = np.asarray(fr["k"], float)
    e1 = np.asarray(fr["dir"], float)
    R = np.stack([e1, np.cross(k, e1), k], 1)
    g = float(fr["h"])
    M = np.eye(4)
    M[:3, :3] = R * g
    M[:3, 3] = fr["o"]
    ring = (_outline(fr) - np.asarray(fr["o"])) @ R / g  # world -> local
    n = len(ring)
    half = (0.5 * fr["h"] + 0.2 * fr["r0"] if fr["wrap"] == "cylinder" else 1.2 * fr["r0"]) / g
    verts = ring.tolist() + [[0, 0, -half], [0, 0, half], [0, 0, 0], [fr["r0"] / g, 0, 0]]
    edges = [[i, (i + 1) % n] for i in range(n)] + [[n, n + 1], [n + 2, n + 3]]
    return {"matrix": M.tolist(), "verts": verts, "edges": edges}


def _decompose(M):
    M = np.asarray(M, float)
    s = np.linalg.norm(M[:3, :3], axis=0)
    return M[:3, 3], M[:3, :3] / np.maximum(s, 1e-12), s


def _rv(v, nd=4):
    return [round(float(x), nd) + 0.0 for x in v]  # (+ 0.0: no "-0.0" in the spec)


def _signed_angle(a, b, axis) -> float:
    """Degrees from a to b about axis (both projected off it)."""
    a = a - (a @ axis) * axis
    b = b - (b @ axis) * axis
    return float(np.degrees(np.arctan2(np.cross(a, b) @ axis, a @ b)))


def from_gizmo(spec: dict, img: dict, parts, was, now) -> tuple[dict | None, list[str]]:
    """The image dict after its gizmo was edited in the scene: `was` is the matrix the sync wrote, `now` the
    object's. Each of position, orientation and size counts only if it moved from what the sync wrote (so spec
    edits made elsewhere since aren't clobbered), and then the decal is put where the gizmo now is: absolute, so
    pulling twice gives the same spec. Returns (new image dict or None when nothing moved, notes).

    A decal at a named joint, blob or bone point comes back as "offset" (world axes) while it stays within its
    own larger side of where the anchor alone puts it: the decal keeps riding its anchor when the model is
    edited. Moved further it has left what it was placed on, so its world point becomes "at" (and dir/up that
    were the blob's are written out)."""
    from .spec import expand_mirror, resolve_point
    ow, Rw, sw = _decompose(was)
    on, Rn, sn = _decompose(now)
    wrap = img.get("wrap", "planar")
    flat = wrap in ("planar", "surface")
    moved = float(np.linalg.norm(on - ow)) > 1e-5
    turned = float(np.abs(Rn - Rw).max()) > 2e-4
    scaled = bool(np.abs(sn[:2] / sw[:2] - 1).max() > 1e-4) if flat else bool(abs(sn.mean() / sw.mean() - 1) > 1e-4)
    if not (moved or turned or scaled):
        return None, []
    s = expand_mirror(spec)
    fr = frame(spec, img, s, parts=parts)
    new = dict(img)
    notes = []
    at = img.get("at")
    named = isinstance(at, (str, dict))
    blob = (s.get("blobs") or {}).get(at) if isinstance(at, str) else None
    limit = max(fr["w"], fr["h"])

    def unname(n):  # dir/up/axis that were the blob's own (named faces, its default up and axis) as vectors
        if isinstance(n.get("dir"), str) or (blob is not None and "dir" not in n):
            n["dir"] = _rv(fr["dir"] if flat else (np.cos(fr["phic"]) * np.asarray(fr["dir"])
                                                    + np.sin(fr["phic"]) * np.asarray(fr["k"])))
        if flat and blob is not None and "up" not in n:
            up0, d0 = np.asarray(fr["up"]), np.asarray(fr["dir"])
            if n.get("rotate"):  # the frame's up has the rotate in it: take it back out
                r = -np.radians(float(n["rotate"]))
                up0 = up0 * np.cos(r) + np.cross(d0, up0) * np.sin(r) + d0 * (d0 @ up0) * (1 - np.cos(r))
            n["up"] = _rv(up0)
        if not flat and blob is not None and "axis" not in n:
            n["axis"] = _rv(fr["k"])

    def far(off):
        notes.append(f"moved {np.linalg.norm(off) * 1000:.0f} mm off {at!r} (more than the decal's own size): "
                     f"now at a world point")

    if turned:
        if flat:
            d0, up0 = np.asarray(fr["dir"]), np.asarray(fr["up"])
            d1, up1 = Rn[:, 2], Rn[:, 1]
            tilt = float(np.degrees(np.arccos(np.clip(d0 @ d1, -1, 1))))
            if tilt < 0.5 or wrap == "surface":  # a spin about its own normal: "rotate"
                if wrap == "surface" and tilt >= 0.5:
                    notes.append("a surface sticker lies on the surface: only its spin about the normal is kept")
                rot = float(img.get("rotate", 0.0)) + _signed_angle(up0, up1, d0)
                rot = round((rot + 180.0) % 360.0 - 180.0, 2)
                if abs(rot) < 0.005:
                    new.pop("rotate", None)
                else:
                    new["rotate"] = rot
            else:
                new["dir"], new["up"] = _rv(d1), _rv(up1)
                new.pop("rotate", None)
        else:
            k0, k1, e1 = np.asarray(fr["k"]), Rn[:, 2], Rn[:, 0]
            new["dir"] = _rv(np.cos(fr["phic"]) * e1 + np.sin(fr["phic"]) * k1)
            if float(np.degrees(np.arccos(np.clip(k0 @ k1, -1, 1)))) > 0.5:  # the axis itself turned
                if isinstance(new.get("axis"), dict):
                    new["axis"] = {**new["axis"], "dir": _rv(k1)}
                elif new.get("at") is not None:
                    new["axis"] = _rv(k1)
                else:
                    new["axis"] = {"at": _rv(fr["o"]), "dir": _rv(k1)}
    if scaled:
        sz = img.get("size")
        if flat:
            w1, h1 = float(sn[0]), float(sn[1])
            same = abs(w1 / h1 - fr["w"] / fr["h"]) < 1e-3 * fr["w"] / fr["h"]
            if isinstance(sz, list) and same and (sz[0] is None or sz[1] is None):
                new["size"] = [round(w1, 4) if sz[0] is not None else None, round(h1, 4) if sz[1] is not None else None]
            else:
                new["size"] = [round(w1, 4), round(h1, 4)]
        else:
            g = float(sn.mean()) / fr["h"]  # the gizmo is scaled by the label's height
            if img.get("span") is not None:
                sp = img["span"]
                new["span"] = [round(float(x) * g, 2) for x in sp] if isinstance(sp, list) else round(float(sp) * g, 2)
                if isinstance(sz, list):
                    new["size"] = [None, round(float(sz[1]) * g, 4)] if sz[1] is not None else sz
            else:
                new["size"] = [round(fr["w"] * g, 4) if not isinstance(sz, list) or sz[0] is not None else None,
                               round(fr["h"] * g, 4) if not isinstance(sz, list) or sz[1] is not None else None]
    if moved and not flat:
        dt = on - np.asarray(fr["o"])  # (the spec's own placement may have changed since the sync)
        if wrap == "sphere":
            notes.append("a sphere wrap's gizmo was moved: its centre is the ball's ('at'); turn it instead")
        elif at is None:  # a cylinder placed by its axis alone ({"at", "dir"}): the axis moves
            new["axis"] = {**new["axis"], "at": _rv(np.asarray(fr["o"]) + dt)}
        elif not named:
            new["at"] = _rv(np.asarray(at, float) + dt)
        else:
            off = _offset(img) + dt
            if float(np.linalg.norm(off)) <= limit:
                new["offset"] = _rv(off)
            else:
                unname(new)
                new["at"] = _rv(resolve_point(s, at) + off)
                new.pop("offset", None)
                far(off)
    if flat and (moved or (turned and blob is not None)):
        # the centre goes where the gizmo is (turned on a blob, it would re-seat on another point of its face)
        c_star = on if moved else np.asarray(fr["c"])
        if not named:
            new["at"] = _rv(c_star - _offset(img))
        else:
            c_seat = np.asarray(frame(spec, {**new, "offset": [0.0, 0.0, 0.0]}, s, parts=parts)["c"])
            off = c_star - c_seat
            if float(np.linalg.norm(off)) <= limit:
                if float(np.linalg.norm(off)) < 1e-5:
                    new.pop("offset", None)
                else:
                    new["offset"] = _rv(off)
            else:
                unname(new)
                new["at"] = _rv(c_star)
                new.pop("offset", None)
                far(off)
    return (new if new != img else None), notes
