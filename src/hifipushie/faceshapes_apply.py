"""apply: the shapes put on an export's parts (which part takes which, the sculpt, unevenness, the seam check),
read_glb, face_of. Part of face shapes (faceshapes.py has the overview)."""
from __future__ import annotations

import numpy as np

from .spec import SpecError
from . import faceshapes_consts
from .faceshapes import ALL, CORRECTIVES, SMILE_JAW_CANCEL, SMILE_JAW_CANCEL_LM, family, vertex_normals
from .faceshapes_consts import SEAM_SHOWING, refuse_sculpt
from .faceshapes_face import Face
from .faceshapes_gnm import GnmFace

UNEVEN_LIMIT = 0.2   # worst `unevenness` over which the export log warns (the lid seal's sawtooth read 0.21 / 0.38,
#                      the same blinks unsealed and repaired 0.05-0.09)
UNEVEN_COUNT = 0.05  # vertices over this are counted


def unevenness(V: np.ndarray, T: np.ndarray, d: np.ndarray, sel: np.ndarray | None = None) -> tuple[float, int, int]:
    """How jagged a shape's move is over the mesh: per vertex, how far its move lies OUTSIDE the range of its edge
    neighbours' moves (per axis; 0 for any vertex between its neighbours, however steep the field), per metre of
    its mean edge: (worst, vertices over UNEVEN_COUNT, vertices with 4+ neighbours). A smooth field reads ~0 (a lid
    travelling 8 mm over 5 mm of skin is steep, not jagged); a vertex that goes further than everything round it
    is a spike, and several of them a sawtooth in whatever is painted there. Vertices at a tear (the lips' slit:
    neighbours moving opposite ways) are left out. V, T welded (no uv-seam duplicates:
    `weld`); sel limits the count to those vertices."""
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    e = e[e[:, 0] != e[:, 1]]
    L = np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1)
    n = len(V)
    lo, hi = np.full((n, 3), np.inf), np.full((n, 3), -np.inf)
    ls, cnt = np.zeros(n), np.zeros(n)
    # a tear is not unevenness: the two lips meet along the slit and at its corners, and part (neighbours going
    # opposite ways, both by more than a millimetre)
    mv = np.linalg.norm(d, axis=1)
    apart = ((d[e[:, 0]] * d[e[:, 1]]).sum(1) < 0) & (np.minimum(mv[e[:, 0]], mv[e[:, 1]]) > 1e-3)
    torn = np.zeros(n, bool)
    torn[e[apart].ravel()] = True
    for a, b in ((0, 1), (1, 0)):
        np.minimum.at(lo, e[:, a], d[e[:, b]])
        np.maximum.at(hi, e[:, a], d[e[:, b]])
        np.add.at(ls, e[:, a], L)
        np.add.at(cnt, e[:, a], 1)
    ok = (cnt >= 4) & ~torn
    if sel is not None:
        ok &= sel
    if not ok.any():
        return 0.0, 0, 0
    r = np.maximum(np.maximum(lo[ok] - d[ok], d[ok] - hi[ok]), 0.0)
    q = np.linalg.norm(r, axis=1) / np.maximum(ls[ok] / cnt[ok], 2e-3)  # (a mesh finer than 2 mm: per 2 mm)
    return float(q.max()), int((q > UNEVEN_COUNT).sum()), int(ok.sum())


def weld(V: np.ndarray, T: np.ndarray, tol: float = 1e-6):
    """(index of each welded vertex's first copy, triangles on welded indices, welded index of every vertex)."""
    key = np.round(np.asarray(V, float) / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    Tw = inv[T]
    return first, Tw[(Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])], inv


def turn(vecs: np.ndarray, n0: np.ndarray, n1: np.ndarray) -> np.ndarray:
    """vecs (m, 3) turned by the rotation taking unit n0 to unit n1 (per row), the least rotation."""
    axis = np.cross(n0, n1)
    s = np.linalg.norm(axis, axis=1)
    c = np.clip((n0 * n1).sum(1), -1, 1)
    ang = np.arctan2(s, c)
    k = axis / np.maximum(s, 1e-12)[:, None]
    cs, sn = np.cos(ang)[:, None], np.sin(ang)[:, None]
    out = vecs * cs + np.cross(k, vecs) * sn + k * (k * vecs).sum(1, keepdims=True) * (1 - cs)
    return np.where((s > 1e-9)[:, None], out, vecs)


def names_of(face_shapes) -> list[str]:
    """The targets an export carries: the ARKit names asked for (True: all 52), plus each corrective whose inputs
    are all there."""
    if face_shapes is True:
        names = list(ALL)
    else:
        if isinstance(face_shapes, str):
            face_shapes = [face_shapes]
        names = list(face_shapes or [])
        bad = [n for n in names if n not in ALL]
        if bad:
            raise SpecError(f"face_shapes: unknown shape(s) {bad} (have the ARKit names {', '.join(ALL)})")
    return names + [c for c, (_, *ins) in CORRECTIVES.items() if all(i in names or i + "Left" in names for i in ins)
                    and (c != "jawOpen_mouthSmile" or SMILE_JAW_CANCEL or SMILE_JAW_CANCEL_LM)]


def _sculpted(D: dict, part: str, n: int, log: list) -> dict:
    """(r48) Add hand-sculpted corrective deltas to a part's shapes: SHAPE_SCULPT is an npz of "<part>|<shape>" ->
    (verts, 3) offsets in the export's frame (Blender axes, m), sculpted against the reference on the posed export mesh
    (the solve is the base, the artist finishes). Only the shapes move; the neutral is untouched. Checked by vertex count:
    a mesh that changed since the sculpt is skipped with a WARNING, never applied to the wrong vertices.
    REFUSED since 2026-10-18 (Joe, after r35-r48: "stop hand tuning it and just use the expression parameters"): an
    expression is a mix of the exported ARKit / GNM expression parameters, never per-character sculpted deltas."""
    from . import faceshapes_consts
    refuse_sculpt(faceshapes_consts.SHAPE_SCULPT, log=log)
    z = np.load(faceshapes_consts.SHAPE_SCULPT)
    out = dict(D)
    for k in z.files:
        pn, nm = k.split("|", 1)
        if pn != part or nm not in out:
            continue
        d = np.asarray(z[k], np.float64)
        if d.shape != (n, 3):
            log.append(f"WARNING face shapes: sculpt {k} has {d.shape[0]} vertices, the part {n}: not applied")
            continue
        out[nm] = out[nm] + d
        log.append(f"face shapes: {part} {nm} + sculpt, max {np.linalg.norm(d, axis=1).max() * 1000:.1f} mm")
    return out


def apply(spec: dict, parts: dict, face_shapes, log: list, quick: bool = False, neutrals: dict | None = None) -> dict:
    """Close the neutral's mouth and give the moving parts their shapes, in place on the export's low-poly parts
    ({part: {"verts", "corner_vert", "normal", "tangent", ...}}, Blender axes). Each moving part gets
    p["shapes"] = {name: (delta (verts, 3), vertex normal before (verts, 3), after (verts, 3))}, in the order of
    `names`; normals and tangents per corner turn with the close. Returns {part: [names]}.
    quick (facepose's posed look): parts need only verts + corner_vert; the same moves, without the per-corner
    normals, the shapes' normals and the export's diagnostics (seam, unevenness). neutrals: {part: neutral verts}
    reused when there (they depend on geometry only; the seal is most of the time), filled in when not."""
    from . import faceshapes_consts
    names = names_of(face_shapes)
    face = face_of(spec)
    if "eyeBlinkLeft" in names and not face.eyes:
        log.append("face shapes: no lids on the face kit's eyes: eyeBlink shapes are flat")
    if isinstance(face, GnmFace):
        if face.note:
            log.append("WARNING " + face.note)
        log.append("face shapes: the mouth is " + ("GNM's own (bag, teeth and gums, tongue: each moved by its own share of "
                                                    "every shape's GNM expression coefficients)" if face.gnm_mouth else
                                                    "the face kit's (base.head.interior: teeth and tongue ride the jaw rigidly)"))
    got, kinds = {}, {}
    for pn, p in parts.items():
        if p.get("lash_root") is not None:  # the lashes (lashes.py) follow the lids' shapes, below
            continue
        base = pn.split("/")[-1].split("~")[0]
        kind = "teeth" if base in face.parts_teeth else "tongue" if base in face.parts_tongue else "skin"
        if any(e.get("part") in (base, base[:-len("_cornea")] if base.endswith("_cornea") else None)
               for e in face.eyes.values()):
            kind = "eyes"  # the eyeballs' own part (and a clear cornea's lens, base_implied.clear_cornea): only the eyeLook
            # shapes turn them
        Xm = np.asarray(p["verts"], np.float64)
        if kind == "skin":
            if not face.owns(base):  # clothes and everything else: no face shapes
                continue
            near = np.linalg.norm(Xm - face.M, axis=1) < 3 * face.width + 2 * face.R
            if not near.any():
                continue
        T = p["corner_vert"].reshape(-1, 3)
        idx = p.get("gnm_index") if kind == "skin" else None  # (one mesh, own quads: GNM's vertices by index)
        cached = (neutrals or {}).get(pn)
        Xn = Xm + face.neutral(Xm, kind, idx) if cached is None else np.asarray(cached, np.float64)
        moved_rest = False
        if faceshapes_consts.SHAPE_SCULPT and kind == "teeth" and cached is None:
            refuse_sculpt(faceshapes_consts.SHAPE_SCULPT, log=log)  # (r48) a sculpted rest for the teeth (levelled incisal edges)
            z = np.load(faceshapes_consts.SHAPE_SCULPT)
            if f"{base}|_neutral" in z.files and z[f"{base}|_neutral"].shape == Xn.shape:
                Xn = Xn + np.asarray(z[f"{base}|_neutral"], np.float64); moved_rest = True
                log.append(f"face shapes: {pn} rest + sculpt, max {np.abs(z[f'{base}|_neutral']).max() * 1000:.1f} mm")
        if kind == "skin" and base == face.slit_part and idx is None and cached is None:
            Xn = Xn + face.seal(Xm, Xn, T)
        if neutrals is not None:
            neutrals[pn] = Xn
        n0m, n0 = vertex_normals(Xm, T), vertex_normals(Xn, T)
        if kind == "skin" and not quick:  # the close turns the corners' normals and tangents with it
            cv = p["corner_vert"]
            p["normal"] = turn(np.asarray(p["normal"], np.float64), n0m[cv], n0[cv]).astype(p["normal"].dtype)
            p["tangent"] = turn(np.asarray(p["tangent"], np.float64), n0m[cv], n0[cv]).astype(p["tangent"].dtype)
        lower = None
        if kind == "teeth" and getattr(face, "gnm_mouth", False):  # GNM's rows are parts of their own
            from . import base_gnm_parts
            lower = np.full(len(Xm), base == base_gnm_parts.TEETH_PARTS[1])
        elif kind == "teeth":  # each connected piece whose middle is under the parting line is the lower row
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
            _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (len(Xm),) * 2),
                                          directed=False)
            h0 = face.local(Xm)["h0"]
            mid = np.bincount(lab, h0) / np.maximum(np.bincount(lab), 1)
            lower = mid[lab] < 0
        D = face.displacements(Xm, Xn, n0, kind, names, lower, idx)
        if faceshapes_consts.SHAPE_SCULPT:
            D = _sculpted(D, pn, len(Xm), log)
        if moved_rest:  # (r48) its corners' normals turned with the sculpted rest
            cv = p["corner_vert"]; n1 = vertex_normals(Xn, T)
            p["normal"] = turn(np.asarray(p["normal"], np.float64), n0m[cv], n1[cv]).astype(p["normal"].dtype)
            p["verts"] = Xn.astype(p["verts"].dtype)
        if not any(np.abs(d).max() > 1e-7 for d in D.values()):
            continue
        p["verts"] = Xn.astype(p["verts"].dtype)
        p["shapes"] = {nm: (d, n0, None if quick else vertex_normals(Xn + d, T)) for nm, d in D.items()}
        got[pn] = list(D)
        kinds[pn] = kind
        moved = sum(int((np.linalg.norm(d, axis=1) > 1e-6).any()) for d in D.values())
        log.append(f"face shapes: {pn} ({kind}) {len(D)} targets ({moved} move it), max "
                   f"{max(np.linalg.norm(d, axis=1).max() for d in D.values()) * 1000:.1f} mm")
        if quick:
            continue
        if kind == "skin" and idx is not None and isinstance(face, GnmFace):  # the closed lips' seam, as seen
            # from the front (an orthographic mask along -out): no inner lip / sock face in front at neutral or blink
            sealed = "mouthClose" if face._gnm.get("parted") is not None else ""  # (r44) parted rest: mouthClose seals
            # (Garrett s6) the blink is measured on the CLOSED mouth: on a parted rest, eyeBlinkLeft alone is the
            # parted lips (Garrett 11.67, Tess 3.23 mm^2 while mouthClose read 0.000), not a blink fault
            seal = D[sealed] if sealed and sealed in D else 0.0
            got_ = {nm: face.seam_showing(Xn + (D[nm] if nm else 0.0) + (seal if nm == "eyeBlinkLeft" else 0.0), T, idx)
                    for nm in (sealed, "eyeBlinkLeft") if not nm or nm in D}
            if sealed and "eyeBlinkLeft" in got_:
                got_["eyeBlinkLeft+mouthClose"] = got_.pop("eyeBlinkLeft")
            rest_ = face.seam_showing(Xn, T, idx) if sealed else None  # the parted rest itself (info, not a gate)
            if any(v is not None for v in got_.values()):
                bad = {nm: v for nm, v in got_.items() if v is not None and v > SEAM_SHOWING}
                log.append(("WARNING " if bad else "") + f"face shapes: {pn} closed lips' seam (inner lip / mouth "
                           f"seen from the front, mm^2, limit {SEAM_SHOWING}): " + ", ".join(
                               f"{nm or 'neutral'} {v:.3f}" for nm, v in got_.items() if v is not None)
                           + (f" (parted rest, not gated: {rest_:.3f})" if rest_ is not None else ""))
                p["seam_showing"] = {nm or "neutral": round(float(v), 4) for nm, v in got_.items() if v is not None}
        if kind == "skin":  # a shape whose move jumps from vertex to vertex shears whatever is painted there
            first, Tw, _ = weld(Xn, T)
            un = {nm: unevenness(Xn[first], Tw, d[first], face.off_margins(nm, Xn[first])) for nm, d in D.items()}
            p["shape_unevenness"] = {nm: round(u[0], 3) for nm, u in un.items() if u[0] > UNEVEN_COUNT}
            top = sorted(un, key=lambda nm: -un[nm][0])[:3]
            log.append(f"face shapes: {pn} unevenness (a vertex's move outside its neighbours', per m of edge; "
                       f"smooth ~0, limit {UNEVEN_LIMIT}): " + ", ".join(f"{nm} {un[nm][0]:.2f}" for nm in top))
            for nm in un:  # (mouth shapes part the lips at the slit's ends: steps there are the shape, not a fault;
                # measured, the kit's read 0.2-1.6 on a handful of vertices at the corners. Listed, not warned.)
                if un[nm][0] > UNEVEN_LIMIT and family(nm.split("_")[0]) != "mouth":
                    log.append(f"WARNING face shapes: {pn} {nm} moves unevenly ({un[nm][0]:.2f}, {un[nm][1]} "
                               f"vertices over {UNEVEN_COUNT}): neighbouring vertices go different ways, which "
                               "shears painted detail into a sawtooth. Look at it posed (rig(glb=, shapes=))")
    skin = [(np.asarray(parts[q]["verts"], np.float64), {nm: np.asarray(x[0]) for nm, x in parts[q]["shapes"].items()})
            for q in got if kinds.get(q) == "skin"]
    for pn, p in parts.items():  # the lashes: each lash turned rigidly with its root's lid (lashes.shapes_from_lids)
        if p.get("lash_root") is None or not skin:
            continue
        from . import lashes as lashmod
        D = lashmod.shapes_from_lids(p, skin, names)
        if not any(np.abs(d).max() > 1e-7 for d in D.values()):
            continue
        T = p["corner_vert"].reshape(-1, 3)
        X0 = np.asarray(p["verts"], np.float64)
        n0 = vertex_normals(X0, T)
        p["shapes"] = {nm: (d, n0, vertex_normals(X0 + d, T)) for nm, d in D.items()}
        got[pn] = list(D)
        log.append(f"face shapes: {pn} (lashes, riding the lids) {len(D)} targets, max "
                   f"{max(np.linalg.norm(d, axis=1).max() for d in D.values()) * 1000:.1f} mm")
    return got


def read_glb(path) -> dict:
    """The face shapes in a GLB, decoded (sparse accessors too): {mesh name: {"names": targetNames, "count":
    vertices, "weights", "targets": [{"POSITION": (count, 3), "NORMAL": (count, 3)}] per primitive 0}}. For checks
    and tests (the export round trip), not for engines."""
    import json
    import struct
    from pathlib import Path
    raw = Path(path).read_bytes()
    jl = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20 + jl])
    bl = struct.unpack_from("<I", raw, 20 + jl)[0]
    binary = raw[28 + jl:28 + jl + bl]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    dtype = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}

    def view(bv, ctype, n, k):
        v = doc["bufferViews"][bv]
        return np.frombuffer(binary, dtype[ctype], n * k, v.get("byteOffset", 0)).reshape(n, k) if k > 1 else \
            np.frombuffer(binary, dtype[ctype], n, v.get("byteOffset", 0))

    def acc(i):
        a = doc["accessors"][i]
        k = width[a["type"]]
        out = (view(a["bufferView"], a["componentType"], a["count"], k).astype(np.float64)
               if "bufferView" in a else np.zeros((a["count"], k)))
        if "sparse" in a:
            sp = a["sparse"]
            idx = view(sp["indices"]["bufferView"], sp["indices"]["componentType"], sp["count"], 1)
            out = out.copy()
            out[idx] = view(sp["values"]["bufferView"], a["componentType"], sp["count"], k)
        return out
    res = {}
    for m in doc["meshes"]:
        pr = m["primitives"][0]
        res[m["name"]] = {"names": (m.get("extras") or {}).get("targetNames", []), "weights": m.get("weights", []),
                          "count": doc["accessors"][pr["attributes"]["POSITION"]]["count"],
                          "targets": [{k: acc(v) for k, v in t.items()} for t in pr.get("targets", [])]}
    return res


def face_of(spec: dict) -> Face:
    """The face shapes' anatomy for a model: a GNM head (base.head.source "gnm") or the face kit."""
    hd = ((spec.get("base") or {}).get("head") or {})
    if hd and hd.get("source", "gnm") == "gnm" and not any(
            k.get("type") == "face" for k in (spec.get("kits") or {}).values()):
        return GnmFace(spec)
    return Face(spec)
