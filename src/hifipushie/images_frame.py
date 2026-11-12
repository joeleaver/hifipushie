"""Placement: the frame an image sits in (on a prim, at a point, along an axis), the wrap frame, the UV frame. Part of images (images.py has the spec)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import images
from .spec import SpecError
from .images import image_size, source_path, styled_path

# ---- placement ----------------------------------------------------------------------------------------------------
def _unit(v, what):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    if v.shape != (3,) or n < 1e-9:
        raise SpecError(f"{what}: {v.tolist()} isn't a direction [x, y, z]")
    return v / n


def prims_on(spec: dict, parts) -> list:
    """The primitives of these parts (their cuts too): what a wrap measures its surface on. None / "*": every part."""
    from .spec import compile_prims
    prims = compile_prims(spec)
    if parts is None or parts == "*" or (not isinstance(parts, str) and "*" in parts):
        return list(prims)
    parts = [parts] if isinstance(parts, str) else list(parts)
    return [p for p in prims if p.part in parts]


def _geo(prims) -> str:
    from . import sdf
    g = hashlib.sha1(json.dumps(sorted(sdf.fingerprint(p) for p in prims)).encode()).hexdigest()[:16]
    images._PRIMS[g] = prims
    if len(images._PRIMS) > 32:
        images._PRIMS.pop(next(iter(images._PRIMS)))
    return g


def _hit(prims, o, d, what) -> float:
    """Distance along d from o to the outermost surface crossing (marched in from outside the model)."""
    from . import sdf
    adds = [p for p in prims if p.op == "add"]
    if not adds:
        raise SpecError(f"{what}: no surface to wrap onto (the parts have no primitives)")
    lo, hi = np.min([p.lo for p in adds], 0), np.max([p.hi for p in adds], 0)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    tmax = float(np.linalg.norm(corners - o, axis=1).max()) + 0.01
    t = np.linspace(tmax, 0.0, 400)
    f = sdf.field_at(prims, o + t[:, None] * d)
    idx = np.flatnonzero((f[:-1] > 0) & (f[1:] <= 0))
    if not len(idx):
        raise SpecError(f"{what}: the wrap's centre ray (from {np.round(o, 3).tolist()} along "
                        f"{np.round(d, 2).tolist()}) hits nothing on the decal's parts")
    a, b = t[idx[0]], t[idx[0] + 1]
    for _ in range(40):
        m = 0.5 * (a + b)
        if sdf.field_at(prims, (o + m * d)[None])[0] > 0:
            a = m
        else:
            b = m
    return 0.5 * (a + b)


def _offset(img: dict, what: str = "image") -> np.ndarray:
    off = img.get("offset", [0.0, 0.0, 0.0])
    if not (isinstance(off, list) and len(off) == 3 and all(isinstance(x, (int, float)) for x in off)):
        raise SpecError(f"{what}: offset is [x, y, z] in metres (world axes)")
    return np.asarray(off, float)


def _at_point(s: dict, img: dict) -> np.ndarray:
    """The image's "at" as a point, moved by its "offset" (world axes; what a decal moved in the Blender scene
    off its joint or blob comes back as)."""
    from .spec import resolve_point
    return resolve_point(s, img["at"]) + _offset(img)


def _axis(s: dict, img: dict, blob, R, what):
    """(a point on the axis, unit direction) of a cylinder/sphere wrap: "axis" = a bone | [joint or xyz, joint or
    xyz] | [x, y, z] (a direction through "at") | {"at", "dir"}; default the "at" blob's own z axis (a cylinder
    blob: a can, a bottle), or world Z through "at"."""
    from .spec import resolve_point
    ax = img.get("axis")
    at = img.get("at")
    if ax is None:
        if at is None:
            raise SpecError(f"{what}: a {img.get('wrap')} wrap needs \"axis\" (a bone, [joint, joint] or "
                            f"{{\"at\", \"dir\"}}) or \"at\" (a cylinder blob, or a point the axis runs up through)")
        return _at_point(s, img), R @ np.array([0, 0, 1.0])
    if isinstance(ax, str):
        b = (s.get("bones") or {}).get(ax)
        if b is None:
            raise SpecError(f"{what}: axis bone {ax!r} doesn't exist")
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        return 0.5 * (a + bb), _unit(bb - a, f"{what} axis")
    if isinstance(ax, dict):
        if "dir" not in ax:
            raise SpecError(f"{what}: axis {{\"at\", \"dir\"}} needs dir")
        o = resolve_point(s, ax["at"]) if "at" in ax else (_at_point(s, img) if at is not None else None)
        if o is None:
            raise SpecError(f"{what}: axis needs \"at\" (a point on it)")
        return o, _unit(ax["dir"], f"{what} axis dir")
    if isinstance(ax, list) and len(ax) == 3 and all(isinstance(x, (int, float)) for x in ax):
        if at is None:
            raise SpecError(f"{what}: axis [x, y, z] is a direction: give \"at\" (a point on the axis) too")
        return _at_point(s, img), _unit(ax, f"{what} axis")
    if isinstance(ax, list) and len(ax) == 2:
        a, bb = resolve_point(s, ax[0]), resolve_point(s, ax[1])
        return 0.5 * (a + bb), _unit(bb - a, f"{what} axis")
    raise SpecError(f"{what}: axis is a bone, [joint, joint], [x, y, z] (with at) or {{\"at\", \"dir\"}}")


def frame(spec: dict, img: dict, expanded: dict | None = None, what: str = "image", parts=None) -> dict:
    """The decal's placement in world space: centre c, unit right/up/dir, size w x h (m), depth, facing, and the
    image file. Computed from the spec (joints and blobs follow edits). parts: the layer's parts (the surface a
    wrap is measured on; an image's own "on" wins)."""
    from .spec import euler_matrix, expand_mirror, resolve_point
    bad = set(img) - images.KEYS
    if bad:
        raise SpecError(f"{what}: unknown keys {sorted(bad)} (have {', '.join(sorted(images.KEYS))})")
    wrap = img.get("wrap", "planar")
    if wrap not in images.WRAPS:
        raise SpecError(f"{what}: wrap is one of {', '.join(images.WRAPS)}")
    if wrap == "uv":  # the model's own texture space (skin_project_lookup.lookup): no placement, the image covers "box"
        return _uv_frame(spec, img, what)
    if "at" not in img and not (wrap == "cylinder" and "axis" in img):
        raise SpecError(f"{what}: needs \"at\" (the decal's centre: a joint, a blob, [x, y, z])")
    for k in ("axis", "seam", "span"):
        if k in img and wrap not in ("cylinder", "sphere"):
            raise SpecError(f"{what}: {k} is for wrap cylinder or sphere")
    if "rotate" in img and wrap in ("cylinder", "sphere"):
        raise SpecError(f"{what}: rotate is for planar and surface decals (a wrap's picture runs round its axis)")
    s = expanded if expanded is not None else expand_mirror(spec)
    at = img.get("at")
    blob = (s.get("blobs") or {}).get(at) if isinstance(at, str) else None
    if isinstance(at, str) and at not in (s.get("joints") or {}) and blob is None:
        raise SpecError(f"{what}: at {at!r} is no joint or blob")
    R = euler_matrix(blob.get("rot", [0, 0, 0])) if blob is not None else np.eye(3)
    path = source_path(img)
    if img.get("style"):
        path = styled_path(path, (spec.get("style") or {}).get("paint") or {})
    pw, ph = image_size(path)
    ch = img.get("channel", "alpha")
    if ch not in images.CHANNELS:
        raise SpecError(f"{what}: channel is one of {', '.join(images.CHANNELS)}")
    base = {"path": str(path), "wrap": wrap, "facing": float(img.get("facing", 0.3)), "channel": ch,
            "flip": bool(img.get("flip", False)), "mirror": bool(img.get("mirror", False)), "px": [pw, ph],
            "mirror_image": bool(img.get("mirror_image", False))}
    if wrap in ("cylinder", "sphere"):
        return {**base, **_wrap_frame(spec, s, img, blob, R, wrap, pw, ph, parts, what)}
    d = img.get("dir", "front" if blob is not None else [0, -1, 0])
    named = isinstance(d, str)
    if named:
        if d not in images.FACES:
            raise SpecError(f"{what}: dir {d!r} is a vector or one of {', '.join(images.FACES)}")
        d = R @ np.array(images.FACES[d], float)
    d = _unit(d, f"{what} dir")
    c = resolve_point(s, at)
    if blob is not None:  # onto the blob's face along dir
        size = np.asarray(blob.get("size", [0.05] * 3), float)
        loc = R.T @ d
        if blob.get("shape") == "box":
            ext = float(np.abs(loc) @ size)
        elif blob.get("shape") == "cylinder":
            ext = float(np.hypot(loc[0] * size[0], loc[1] * size[1]) + abs(loc[2]) * size[2])
        else:
            ext = float(np.linalg.norm(loc * size))
        c = c + d * ext
    c = c + _offset(img, what)
    sz = img.get("size")
    if not (isinstance(sz, list) and len(sz) == 2 and (sz[0] or sz[1])):
        raise SpecError(f"{what}: size is [width, height] in m (one may be null: from the image's aspect)")
    w = float(sz[0]) if sz[0] else float(sz[1]) * pw / ph
    h = float(sz[1]) if sz[1] else w * ph / pw
    if w <= 0 or h <= 0:
        raise SpecError(f"{what}: size must be > 0")
    geo = None
    if wrap == "surface":  # seated on the field: the centre and its normal are the surface's own
        from . import sdf
        prims = prims_on(spec, img.get("on", parts))
        if not prims:
            raise SpecError(f"{what}: no surface to lay the decal on (parts {img.get('on', parts)!r})")
        geo = _geo(prims)
        def fg(x, h=1e-5):  # unclipped: the centre may start well off the surface
            st = np.vstack([x, x + np.eye(3) * h])
            f = sdf.field_at(prims, st, clip=False)
            return f[0], (f[1:] - f[0]) / h
        for _ in range(12):
            f, g = fg(c)
            c = c - (f / max(float(g @ g), 1e-12)) * g
        f, g = fg(c)
        if abs(f) > 1e-3 * max(w, h):
            raise SpecError(f"{what}: couldn't seat the decal's centre on the surface (left {f:.4f} m off)")
        n0 = _unit(g, f"{what} surface normal")
        if n0 @ d < -0.2 and "dir" in img:
            raise SpecError(f"{what}: the surface at the centre faces away from dir")
        d = n0
    if "up" in img:
        up = _unit(img["up"], f"{what} up")
    elif named:
        up = R @ (np.array([0, 1.0, 0]) if img.get("dir") in ("top", "bottom") else np.array([0, 0, 1.0]))
    else:
        up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.95 else np.array([0, 1.0, 0])
    up = up - (up @ d) * d
    if np.linalg.norm(up) < 1e-6:
        raise SpecError(f"{what}: up is along dir")
    up /= np.linalg.norm(up)
    right = np.cross(up, d)
    rot = np.radians(float(img.get("rotate", 0.0)))
    if rot:
        right, up = np.cos(rot) * right + np.sin(rot) * up, -np.sin(rot) * right + np.cos(rot) * up
    out = {**base, "c": c.tolist(), "right": right.tolist(), "up": up.tolist(), "dir": d.tolist(), "w": w, "h": h}
    if wrap == "surface":
        from . import decalmap
        reach = 0.5 * float(np.hypot(w, h)) * decalmap.REACH
        vox = max(2 * reach / decalmap.RES, min(w, h) / 60, decalmap.MIN_VOXEL)
        out.update(geo=geo, reach=reach, voxel=vox, depth=float(img.get("depth", max(0.04 * max(w, h), 3 * vox))))
    else:
        out["depth"] = float(img.get("depth", 0.25 * max(w, h)))
    if out["depth"] <= 0:
        raise SpecError(f"{what}: depth must be > 0")
    return out


def _wrap_frame(spec, s, img, blob, R, wrap, pw, ph, parts, what) -> dict:
    """A cylinder or sphere wrap: the axis (o, k), the centre's direction e1 (dir projected off the axis), e2 = k x
    e1 (the picture's right, seen from outside), the surface's radius at the centre r0 (measured), the seam."""
    from .spec import resolve_point
    if wrap == "cylinder":
        o, k = _axis(s, img, blob, R, what)
        if img.get("at") is not None:  # the centre's height: "at" projected onto the axis
            o = o + ((_at_point(s, img) - o) @ k) * k
    else:
        if img.get("at") is None:
            raise SpecError(f"{what}: a sphere wrap needs \"at\" (the sphere's centre)")
        o = _at_point(s, img)
        if img.get("axis") is None:
            k = R @ np.array([0, 0, 1.0])
        else:
            k = _axis(s, img, blob, R, what)[1]
    d = img.get("dir", "front" if blob is not None else [0, -1, 0])
    if isinstance(d, str):
        if d not in images.FACES:
            raise SpecError(f"{what}: dir {d!r} is a vector or one of {', '.join(images.FACES)}")
        d = R @ np.array(images.FACES[d], float)
    d = _unit(d, f"{what} dir")
    e1 = d - (d @ k) * k
    if np.linalg.norm(e1) < 1e-3:
        if wrap == "cylinder":
            raise SpecError(f"{what}: dir runs along the axis (dir is the way the decal's centre faces, off the axis)")
        e1 = np.cross(k, [1.0, 0, 0] if abs(k[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(k, e1)
    phic = float(np.arcsin(np.clip(d @ k, -1, 1))) if wrap == "sphere" else 0.0
    cdir = np.cos(phic) * e1 + np.sin(phic) * k  # from o to the decal's centre
    prims = prims_on(spec, img.get("on", parts))
    r0 = _hit(prims, o, cdir, what)
    seam = np.radians(float(img.get("seam", 180.0)))
    span = img.get("span")
    su = sv = None
    if span is not None:
        sp = span if isinstance(span, list) else [span, None]
        if not (len(sp) == 2 and sp[0] and float(sp[0]) > 0 and (sp[1] is None or float(sp[1]) > 0)):
            raise SpecError(f"{what}: span is degrees round the axis (> 0), or [round, up] for a sphere")
        if sp[1] is not None and wrap == "cylinder":
            raise SpecError(f"{what}: a cylinder's span is one angle (round the axis); its height is size[1] or "
                            f"from the image's aspect")
        su = float(np.radians(float(sp[0])))
        sv = float(np.radians(float(sp[1]))) if sp[1] is not None else None
    sz = img.get("size")
    rho0 = r0 * np.cos(phic)  # the centre's distance from the axis
    if su is not None:
        w = su * rho0
        if sz is not None and (not isinstance(sz, list) or len(sz) != 2 or sz[0]):
            raise SpecError(f"{what}: with span, size is [null, height] (or left out: from the image's aspect)")
        if sv is not None:
            h = sv * r0
        elif sz is not None and sz[1]:
            h = float(sz[1])
        else:
            h = w * ph / pw
            if wrap == "sphere":
                sv = su * ph / pw  # equirectangular: square pixels at the equator
                h = sv * r0
    else:
        if not (isinstance(sz, list) and len(sz) == 2 and (sz[0] or sz[1])):
            raise SpecError(f"{what}: size is [width, height] in m (width measured round the surface), or give "
                            f"span (degrees)")
        w = float(sz[0]) if sz[0] else float(sz[1]) * pw / ph
        h = float(sz[1]) if sz[1] else w * ph / pw
    if w <= 0 or h <= 0:
        raise SpecError(f"{what}: size must be > 0")
    if su is None and w > 2 * np.pi * rho0 * 1.0001:
        raise SpecError(f"{what}: {w:.3f} m is more than once round ({2 * np.pi * rho0:.3f} m at the centre's radius)")
    depth = float(img.get("depth", 0.25 * max(w, h)))
    if depth <= 0:
        raise SpecError(f"{what}: depth must be > 0")
    out = {"o": o.tolist(), "k": k.tolist(), "c": (o + r0 * cdir).tolist(), "dir": e1.tolist(), "up": k.tolist(),
           "right": e2.tolist(), "r0": float(r0), "phic": phic, "seam": float(seam),
           "dc": float(np.mod(-seam, 2 * np.pi)), "su": su, "sv": sv, "w": float(w), "h": float(h), "depth": depth,
           "m": 0.0, "unroll": "arc"}
    if wrap == "cylinder":
        unroll = img.get("unroll", "auto")
        if unroll not in images.UNROLLS:
            raise SpecError(f"{what}: unroll is one of {', '.join(images.UNROLLS)}")
        # the surface's taper over the label: its radius a little above and below the centre (a local cone)
        def probe(sgn):  # half the label's height out; nearer where the surface ends first (a can's rim cut)
            for f in (0.5, 0.25, 0.1):
                try:
                    return _hit(prims, o + sgn * f * h * k, e1, what), f * h
                except SpecError:
                    pass
            return r0, 0.0
        (r_hi, a_hi), (r_lo, a_lo) = probe(1), probe(-1)
        m = float((r_hi - r_lo) / (a_hi + a_lo)) if a_hi + a_lo > 0 else 0.0
        if unroll == "auto":
            unroll = "cone" if abs(m) > images.TAPER else "arc"
        out.update(m=m, unroll=unroll)
        if unroll == "cone":  # fan-cut: rows on circles round the axis, columns on the cone's generators
            if abs(m) < 1e-6:
                raise SpecError(f"{what}: unroll cone on a surface with no taper here (use arc)")
            out.update(ta=float(-r0 / m), Rc=float(r0 * np.sqrt(1 + m * m) / abs(m)), sg=1.0 if m < 0 else -1.0)
    elif "unroll" in img:
        raise SpecError(f"{what}: unroll is for cylinder wraps")
    return out


def _uv_frame(spec: dict, img: dict, what: str) -> dict:
    """wrap "uv": the image lies in the model's own texture space (the one human mesh's atlas; skin_project_atlas.atlas):
    "box" [u0, v0, u1, v1] = the rectangle of the atlas the image covers (default the whole atlas). No "at", "size" or
    "dir": the surface says where each texel is. Measured per vertex (u, v, weight), sampled per pixel."""
    import hashlib
    import json
    from . import onemesh
    b = spec.get("base") or {}
    if not onemesh.applies(b):
        raise SpecError(f"{what}: wrap \"uv\" needs a model with a texture atlas of its own (the one human mesh: base.body.source \"human\")")
    bad = set(img) - {"file", "id", "name", "wrap", "box", "channel", "style"}
    if bad:
        raise SpecError(f"{what}: wrap \"uv\" takes file | id, box, channel (not {sorted(bad)})")
    box = [float(x) for x in img.get("box", [0.0, 0.0, 1.0, 1.0])]
    if len(box) != 4 or box[2] <= box[0] or box[3] <= box[1]:
        raise SpecError(f"{what}: box is [u0, v0, u1, v1] in atlas units")
    path = source_path(img)
    pw, ph = image_size(path)
    ch = img.get("channel", "alpha")
    if ch not in images.CHANNELS:
        raise SpecError(f"{what}: channel is one of {', '.join(images.CHANNELS)}")
    geo = hashlib.sha1(json.dumps(b, sort_keys=True, default=str).encode()).hexdigest()[:16]
    images._UVBASE[geo] = b
    return {"path": str(path), "wrap": "uv", "facing": 0.0, "channel": ch, "flip": False, "mirror": False, "px": [pw, ph],
            "mirror_image": False, "box": box, "geo": geo, "c": [0.0, 0.0, 0.0], "right": [1.0, 0.0, 0.0], "up": [0.0, 0.0, 1.0],
            "dir": [0.0, -1.0, 0.0], "w": 1.0, "h": 1.0, "depth": 1.0}
