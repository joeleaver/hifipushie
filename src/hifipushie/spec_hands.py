"""A modeller's hands, compiled: masses fused into one (`_fuse`), a direction by word (`_aim`), clay grabbed and moved (`_grabs`), cuts and trims, and csg groups (`_csg`). Part of the spec module (spec.py has the format and every constant)."""
from __future__ import annotations

import zlib

import numpy as np

from . import spec
from .spec import Prim, SpecError, _mirror_vec

def _fuse(prims: list[Prim], els: list[dict]) -> tuple[list[Prim], list[dict]]:
    """Elements that share a "fuse" tag are worked into one mass (reshape.py): joined first, smooth by the tag's
    "fill" (the largest given), then blended into the rest once, like a kit's group. A group joins neighbours in
    the combination order, so the members are gathered at the first one's place."""
    tags: dict = {}
    for i, el in enumerate(els):
        if el.get("fuse"):
            tags.setdefault(str(el["fuse"]), []).append(i)
    if not tags:
        return prims, els
    order, placed = [], set()
    for i in range(len(prims)):
        if i in placed:
            continue
        t = els[i].get("fuse")
        mem = tags[str(t)] if t else [i]
        if t:
            if len(mem) < 2:
                raise SpecError(f"fuse {t!r}: only {prims[i].name!r} has it; a fuse works two or more masses together")
            if min(float(els[j].get("fill", 0.0)) for j in mem) < 0:
                raise SpecError(f"fuse {t!r}: fill is how far a mass is worked into the others, in metres: 0 or more")
            mem = sorted(mem, key=lambda j: -float(els[j].get("fill", 0.0)))  # (stable) the widest joins first
            for j in mem:
                p, p0 = prims[j], prims[mem[0]]
                if p.group:
                    raise SpecError(f"{p.name!r} is already in the group {p.group!r}: it can't be fused as well")
                if p.op != "add" or (p.layer, p.part) != (p0.layer, p0.part):
                    raise SpecError(f"fuse {t!r}: {p.name!r} and {p0.name!r} must both add clay, in the same layer and part")
            for j in mem:  # each mass: how far IT is worked into the masses of the fuse before it, and on which sides
                prims[j].group, prims[j].join = f"fuse:{t}", float(els[j].get("fill", 0.0))
                prims[j].sides = _fuse_sides(t, els[j].get("fill_sides"), [prims[i] for i in mem])
        order += mem
        placed.update(mem)
    return [prims[i] for i in order], [els[i] for i in order]


def _fuse_sides(tag: str, sides, members: list[Prim]):
    """A fuse's "fill_sides" {side: 0..1}: on that side of the fuse's middle only that part of the fill is worked
    in (0 = a crease there, 1 = all of it): a head smooth into the body behind and creased under the chin."""
    if not sides:
        return None
    if not isinstance(sides, dict) or any(k not in spec.FUSE_SIDES for k in sides):
        raise SpecError(f"fuse {tag!r}: fill_sides is {{side: part of the fill}} with sides {', '.join(spec.FUSE_SIDES)} "
                        "(front is where the figure faces, -y), e.g. {\"front\": 0.2}")
    if any(not 0.0 <= float(v) <= 1.0 for v in sides.values()):
        raise SpecError(f"fuse {tag!r}: a side takes a part of the fill, 0 (a crease on that side) to 1 (all of it)")
    lo, hi = np.min([p.lo for p in members], 0), np.max([p.hi for p in members], 0)
    return (tuple(float(v) for v in (lo + hi) / 2), tuple(float(max(v, 0.02)) for v in (hi - lo) / 2),
            tuple(sorted((spec.FUSE_SIDES[k][0], spec.FUSE_SIDES[k][1], float(v)) for k, v in sides.items())))


def _aim_vec(v, what: str = "aim") -> np.ndarray:
    """A direction as words ("up out": their sum; a word twice leans more that way) or as [x, y, z]."""
    if isinstance(v, str):
        words = v.replace(",", " ").replace("+", " ").split()
        bad = [w for w in words if w not in spec.AIM_WORDS]
        if bad or not words:
            raise SpecError(f"{what}: {v!r} is not a direction. Use words ({', '.join(spec.AIM_WORDS)}; \"up out\" is "
                            "between the two; out is away from the centre line on a mirrored mass) or [x, y, z]")
        d = np.sum([spec.AIM_WORDS[w] for w in words], 0).astype(float)
    else:
        d = np.asarray(v, float)
        if d.shape != (3,):
            raise SpecError(f"{what}: a direction is words (\"up out\") or [x, y, z]")
    n = np.linalg.norm(d)
    if n < 1e-9:
        raise SpecError(f"{what}: {v!r} adds up to no direction")
    return d / n


def _mirror_aim(aim: dict) -> dict:
    return {k: _mirror_vec([float(x) for x in _aim_vec(v, f"aim.{k}")]) for k, v in aim.items() if k in ("point", "face")}


def _aim(name: str, bl: dict, size: np.ndarray) -> np.ndarray:
    """A blob turned by saying where it points and which way it faces, instead of by angles ("aim": {"point",
    "face"}). point: where its LENGTH goes (a blade's root-to-tip axis; any other shape's longest axis). face:
    where its FLAT side looks (a blade's hollow side; any other shape's thinnest axis). Either or both."""
    aim = bl["aim"]
    if "rot" in bl:
        raise SpecError(f"blob {name!r}: give aim or rot, not both")
    if not isinstance(aim, dict) or not aim or any(k not in ("point", "face") for k in aim):
        raise SpecError(f"blob {name!r}: aim is {{\"point\": where its length goes, \"face\": where its flat side looks}}, "
                        "each as words (\"up out\", \"forward down\") or [x, y, z]; one of the two is enough")
    if bl.get("shape", "ellipsoid") == "blade":
        L, F = 1, 2
    else:
        L, F = int(np.argmax(size)), int(np.argmin(size))
        if L == F:
            L, F = 2, 1
    T = 3 - L - F
    p = _aim_vec(aim["point"], f"blob {name!r}: aim.point") if "point" in aim else None
    f = _aim_vec(aim["face"], f"blob {name!r}: aim.face") if "face" in aim else None
    eye = np.eye(3)
    if p is None:
        p = eye[L] - (eye[L] @ f) * f
        p = p / np.linalg.norm(p) if np.linalg.norm(p) > 1e-6 else np.cross(f, eye[T]) / np.linalg.norm(np.cross(f, eye[T]))
    if f is None:
        f = next(e for e in (eye[F], eye[T], eye[L]) if np.linalg.norm(e - (e @ p) * p) > 0.3)
    f = f - (f @ p) * p
    if np.linalg.norm(f) < 1e-6:
        raise SpecError(f"blob {name!r}: aim.face looks along aim.point; the flat side faces across the length")
    f = f / np.linalg.norm(f)
    R = np.zeros((3, 3))
    R[:, L], R[:, F] = p, f
    R[:, T] = np.cross(p, f)
    if np.linalg.det(R) < 0:
        R[:, T] = -R[:, T]
    return R


def _grabs(s: dict, prims: list[Prim]) -> list[Prim]:
    """grabs: clay of named masses moved as a modeller's move brush moves it (reshape.py). Each grab's masses are
    evaluated through its warp, like a style deformation, so what is moved stays one smooth surface and blends
    with its neighbours as before."""
    grabs = s.get("grabs")
    if not grabs:
        return prims
    from . import reshape
    eff = reshape.effective(grabs, bool(s.get("symmetry", True)), [p.name for p in prims])
    sets: dict = {}
    for i, p in enumerate(prims):
        if p.instance is None and p.op in ("add", "subtract", "intersect") and p.kind in spec.SHAPES:
            hit = tuple(j for j, (_, of) in enumerate(eff) if p.name in of)
            if hit:
                prev = p.params.get("warp") if p.kind == "csg" else None
                sets.setdefault((id(prev[0]) if prev else 0, hit), []).append(i)
    from .deform import GRAB_AXES
    from .sdf_shapes import SDF
    for op, of in eff:  # each grab's depth: the middle of its clay on its view's ray through `at`
        mine_p = [p for p in prims if p.name in of and p.instance is None and p.op in ("add", "subtract", "intersect")
                  and p.kind in spec.SHAPES]
        if not mine_p:
            continue
        dep, a, b = GRAB_AXES[op["view"]]
        r = float(op["radius"])
        ts = np.linspace(min(p.lo[dep] for p in mine_p) - r, max(p.hi[dep] for p in mine_p) + r, 257)
        ray = np.zeros((len(ts), 3))
        ray[:, a], ray[:, b], ray[:, dep] = op["at"][0], op["at"][1], ts
        f = np.min([SDF[p.kind](ray, p.params) for p in mine_p], 0)
        inside = np.nonzero(f < 0)[0]  # through the clay: its middle; a ray that only grazes it: the nearest point
        op["depth"] = float((ts[inside[0]] + ts[inside[-1]]) / 2) if len(inside) else float(ts[int(np.argmin(f))])
    for (_, hit), idx in sets.items():
        prev = prims[idx[0]].params.get("warp") if prims[idx[0]].kind == "csg" else None
        mine = [{"grab": eff[j][0]} for j in hit]
        lip, reach = reshape.stretch(mine, [prims[i].name for i in idx])
        ops = (list(prev[0]) if prev else []) + mine
        for i in idx:
            p = prims[i]
            if p.kind != "csg":
                p.params = {"kind": p.kind, "p": p.params, "hollow": 0.0, "cuts": []}
                p.kind = "csg"
            # the field is not divided by the grab's stretch (deform.py says why): the mesher's band takes it
            p.params["warp"] = (ops, prev[1] if prev else 1.0)
            p.lip = max(float(p.lip), lip)
            p.lo, p.hi = p.lo - reach, p.hi + reach
            p.reach = np.asarray(p.reach, float) * lip
    return prims


def _cut(name: str, b: dict) -> float:
    """Flat ends for a bone ("ends": "flat" or {"flat": edge radius}): 0 = the usual round caps."""
    e = b.get("ends")
    if e in (None, "round"):
        return 0.0
    if e == "flat":
        return 0.004
    if isinstance(e, dict) and "flat" in e:
        return max(float(e["flat"]), 1e-4)
    raise SpecError(f"bone {name!r}: ends is \"round\", \"flat\" or {{\"flat\": edge radius}}")


def _trims(s: dict, prims: list[Prim]) -> list[Prim]:
    """spec["trims"] (reshape.py): each named mass is cut by the trim's plane, in world space, after its grabs."""
    trims = s.get("trims")
    if not trims:
        return prims
    from . import reshape
    cut = [p for p in prims if p.instance is None and p.op == "add" and p.kind in spec.SHAPES]
    for point, normal, soft, of in reshape.trims_effective(trims, bool(s.get("symmetry", True)), [p.name for p in cut]):
        for p in cut:
            if p.name in of:
                if p.kind != "csg":
                    p.params = {"kind": p.kind, "p": p.params, "hollow": 0.0, "cuts": []}
                    p.kind = "csg"
                p.params["trims"] = [*p.params.get("trims", []), (point, normal, float(soft))]
    return prims


def _csg(s: dict, prims: list[Prim], els: list[dict]) -> list[Prim]:
    """Element-level solids: "hollow": t keeps only a wall t thick inside an element's surface, and a subtract
    or intersect with "targets": [names or tags] shapes only those elements (a pot's opening doesn't bite
    the shelf it stands on). Both wrap the target primitive (kind "csg"); the cut isn't a primitive itself."""
    from .assemble import select
    wrapped: dict[str, Prim] = {}

    def wrap(p: Prim) -> Prim:
        if p.kind != "csg":
            p.params = {"kind": p.kind, "p": p.params, "hollow": 0.0, "cuts": []}
            p.kind = "csg"
        return p

    by_name = {p.name: p for p in prims}
    out = []
    for p, el in zip(prims, els):
        lc = el.get("local")  # an instance's element: noise in its prefab's frame, seeded by the prefab element
        frame = None
        if lc and (el.get("lumpy") or el.get("chips")):
            m = np.asarray(lc["m"], float)
            frame = (m, np.asarray(lc["t"], float), float(abs(np.linalg.det(m)) ** (-1 / 3)))
        seed0 = zlib.crc32((lc["name"] if lc else p.name).encode()) % 9973
        if el.get("lumpy"):
            lp = el["lumpy"]
            lp = {"amount": float(lp)} if isinstance(lp, (int, float)) else lp
            amt = float(lp.get("amount", 0.004))
            sc = float(lp.get("scale", max(8 * amt, 0.02)))
            if p.kind not in spec.SHAPES:
                raise SpecError(f"{p.name!r}: lumpy works on bones and shaped blobs")
            wrap(p).params["lumpy"] = (amt, sc, int(lp.get("seed", seed0)), int(lp.get("octaves", 3)))
            grow = amt * (frame[2] if frame else 1.0)
            p.lo, p.hi = p.lo - grow, p.hi + grow
        if el.get("chips"):
            ch = el["chips"]
            ch = {"depth": float(ch)} if isinstance(ch, (int, float)) else ch
            depth = float(ch.get("depth", 0.006))
            sc = float(ch.get("scale", max(6 * depth, 0.02)))
            cover = min(max(float(ch.get("amount", 0.15)), 0.0), 0.9)  # roughly the fraction of surface chipped
            lo = 0.5 + 0.35 * (1 - 2 * cover)
            w = max(0.03, 1.5 * depth / sc)  # keeps the carved field's slope near 1
            if p.kind not in spec.SHAPES:
                raise SpecError(f"{p.name!r}: chips work on bones and shaped blobs")
            where = ch.get("where", "edges")
            if where not in ("edges", "all"):
                raise SpecError(f"{p.name!r}: chips where is \"edges\" or \"all\"")
            wrap(p).params["chips"] = (depth, sc, lo, w, int(ch.get("seed", seed0) + 7), where == "edges")
        if frame is not None:
            p.params["frame"] = frame
        if el.get("hollow"):
            if p.kind not in spec.SHAPES:
                raise SpecError(f"{p.name!r}: hollow works on bones and shaped blobs")
            wrap(p).params["hollow"] = float(el["hollow"])
    for p, el in zip(prims, els):
        if not el.get("targets"):
            out.append(p)
            continue
        if p.op not in ("subtract", "intersect"):
            raise SpecError(f"{p.name!r}: \"targets\" is for op subtract or intersect")
        names = select(s, el["targets"])
        missing = [n for n in names if n not in by_name]
        if missing:
            raise SpecError(f"{p.name!r}: targets {missing} aren't bones, blobs or tags")
        for n in names:
            q = by_name[n]
            m = max(float(p.blend), float(q.blend)) + 0.01
            if p.op == "subtract" and (np.any(p.lo - m > q.hi) or np.any(p.hi + m < q.lo)):
                continue  # a cut nowhere near this target can't shape it: leave it out (and its fingerprint alone,
                # so moving a window re-meshes only the logs around it)
            t = wrap(q)
            t.params["cuts"].append((p.op, p.kind, p.params, float(p.blend)))
            from .sdf import fingerprint
            t.cut_boxes = (*t.cut_boxes, (fingerprint(p), p.lo - m, p.hi + m))
            wrapped[n] = t
    return out
