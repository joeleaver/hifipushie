"""A chain-built garment as a part of its character's game asset (asset_export's clothes; C434).

Why: asset_export took clothes only from cloth.export_part, which re-runs the old cloth simulation on a garment's
draft, so the garment an agent built, looked at and had approved (steps 0-10, garment_record) was not the one in the
character's GLB. A chain garment has its own game mesh already: the GLB export_garment wrote at step 10, the file its
look and its bend check were made from. The character's export takes THAT file, never a rebuild: the same vertices,
the pattern UVs, step 9a's maps and the garment's own skin weights (matched to the export rig by bone name).

records(name, spec) -> {garment: record}: the model's garments that have a garment record (the chain route).
exported(rec) -> (glb, warnings), or NotShipped(why; next: the call): a garment whose look (step 9) is not approved, or
    whose step 10 is missing or stale, is NOT in the character's export (stages consume approved pieces), and the
    export's log says so first. A step 10 whose own gate FAILED is shipped as exported, with a WARNING naming the rows.
lod_files(rec) -> {k: (glb, share)}: the garment's own LOD files (C439: export_garment writes <garment>_LOD<k>.glb, the
    same pattern re-grid at a coarser grid). One file per LOD: the character's export takes them AS THEY ARE instead
    of decimating LOD0 (the generic decimator kinked the shirt at LOD2 and tore its fronts at LOD3).
parts(name, recs, out_dir, log) -> (cparts, weights, looks, left_out, lods):
    cparts as cloth.export_part gives them, [(part name, part, files)]: "cloth_<garment>" (two-sided, part["shell"]
    as lods_part._lod_shell and asset_hidden read it) and, when the garment has details (buttons ...),
    "cloth_<garment>_details" on a small palette texture (one cell per detail's colour, roughness, metallic);
    weights {part name: (bone names, J, W)}; looks {part name: {"alpha_cutoff"}} for an alpha-cut base map;
    left_out [(garment, why)]; lods {k: {part name: (part | None, weights | None, share)}} from the LOD files
    (None: the LOD leaves the part out, details too small to see there). A shipped garment with NO LOD files is
    logged as a WARNING naming export_garment: asset_export then decimates it like any part.
take_lods(own, parts, lp, lr, rep, bones) -> log line: one LOD's chain parts into asset_export's LOD (its LOD loop).
skin_through(p, covers, P0, under0) -> keep per triangle: skin that comes THROUGH a garment's own LOD cloth and was
    under a garment at LOD0 is cut at that LOD (C440): a 9-12 cm grid's flat faces sink further under the skin than
    the push-under looks (2 cm) or moves (1 cm), and moving the cloth out instead bloats the garment.
bone_weights(weights, bones) -> {part name: (J, W)} in the export rig's bone order.
read(glb) -> the garment GLB as arrays in Blender axes (garment_glb.write's inverse).
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

CELL = 8  # px of one detail's cell in the details palette (one texel per detail bleeds into its neighbours at the mips)
_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class NotShipped(ValueError):
    """Why a garment is not in the character's export, ending with the call that would put it there."""


def records(name: str, spec: dict) -> dict:
    from . import garment_record as gr
    out = {}
    for g in spec.get("cloth") or {}:
        try:
            p = gr.path(name, g)
        except ValueError:
            continue
        if p.exists():
            out[g] = gr.load(name, g)
    return out


def exported(rec: dict) -> tuple[Path, list]:
    from . import garment_record as gr
    s = gr.states(rec)
    call = f'export_garment("{rec["model"]}", "{rec["garment"]}")'
    if not s["9"]["ready"]:
        nx = gr.next_step(rec)
        raise NotShipped(f"its look (step 9) is {s['9']['status']}{': ' + s['9']['why'] if s['9']['why'] else ''}; "
                         f"next: step {nx['step']}: {nx['call']}")
    st = rec["steps"]["10"]
    out = st.get("output") or {}
    if s["10"]["status"] == "todo" or not out.get("glb"):
        raise NotShipped(f"it has no export yet (step 10); next: {call}")
    if s["10"]["stale"]:
        raise NotShipped(f"its export (step 10) is stale ({s['10']['why'] or 'a step before it changed'}); next: {call}")
    glb = Path(out["glb"])
    if not glb.exists():
        raise NotShipped(f"its exported file is gone ({glb}); next: {call}")
    warn = []
    if s["10"]["status"] == "failed":
        bad = [r for r in ((st.get("gate") or {}).get("rows") or []) if r.get("status") not in ("PASS", "INFO")]
        warn.append(f"step 10's own gate FAILED ({'; '.join(str(r['id']) for r in bad if 'id' in r)}): shipped as exported")
    return glb, warn


def lod_files(rec: dict) -> dict:
    """{k: (glb, share of the garment's budget)} for the LOD files step 10 recorded that are still on disk."""
    out = {}
    for x in ((rec["steps"]["10"].get("output") or {}).get("lods") or []):
        if Path(x["glb"]).exists():
            out[int(x["lod"])] = (Path(x["glb"]), float(x["share"]))
    return out


def read(path) -> dict:
    """{"bones": [names, in the skin's joint order], "meshes": [{"name", "V", "T", "uv" | None (v up, as our parts keep
    it), "N" | None, "J", "W" | None, "colour", "metallic", "roughness", "alpha_cut", "maps": {"base", "mr", "normal":
    PNG bytes | None} | None}]}."""
    from .garment_glb import _Z_TO_Y
    b = Path(path).read_bytes()
    if b[:4] != b"glTF":
        raise ValueError(f"{path}: not a GLB")
    n = struct.unpack("<I", b[12:16])[0]
    js = json.loads(b[20:20 + n])
    o = 20 + n
    binc = memoryview(b)[o + 8:o + 8 + struct.unpack("<I", b[o:o + 4])[0]]

    def acc(i):
        a = js["accessors"][i]
        v = js["bufferViews"][a["bufferView"]]
        k = _NC[a["type"]]
        if v.get("byteStride") not in (None, np.dtype(_CT[a["componentType"]]).itemsize * k):
            raise ValueError(f"{path}: interleaved buffers are not read here (garment_glb writes none)")
        out = np.frombuffer(binc, _CT[a["componentType"]], a["count"] * k, v.get("byteOffset", 0) + a.get("byteOffset", 0))
        return out.reshape(a["count"], k) if k > 1 else out

    def png(tex):
        if tex is None:
            return None
        im = js["images"][js["textures"][tex["index"]]["source"]]
        if "bufferView" not in im:  # (a character's LOD names its maps by file, beside the GLB: asset_glb external)
            f = Path(path).parent / im.get("uri", "")
            return f.read_bytes() if im.get("uri") and f.exists() else None
        v = js["bufferViews"][im["bufferView"]]
        return bytes(binc[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]])
    bones = [js["nodes"][j]["name"] for j in js["skins"][0]["joints"]] if js.get("skins") else []
    meshes = []
    for nd in js["nodes"]:
        if "mesh" not in nd:
            continue
        for pr in js["meshes"][nd["mesh"]]["primitives"]:
            at = pr["attributes"]
            mat = js["materials"][pr["material"]] if "material" in pr else {}
            pbr = mat.get("pbrMetallicRoughness") or {}
            uv = None
            if "TEXCOORD_0" in at:
                uv = acc(at["TEXCOORD_0"]).astype(np.float64)
                uv[:, 1] = 1.0 - uv[:, 1]  # (glTF's v runs down; ours up, as asset_glb writes it back)
            maps = None
            if "baseColorTexture" in pbr:
                maps = {"base": png(pbr["baseColorTexture"]), "mr": png(pbr.get("metallicRoughnessTexture")),
                        "normal": png(mat.get("normalTexture"))}
            meshes.append({
                "name": nd.get("name") or js["meshes"][nd["mesh"]].get("name") or f"mesh{len(meshes)}",
                "V": acc(at["POSITION"]).astype(np.float64) @ _Z_TO_Y,  # (written as V @ _Z_TO_Y.T: a rotation)
                "T": acc(pr["indices"]).astype(np.int64).reshape(-1, 3),
                "uv": uv, "N": acc(at["NORMAL"]).astype(np.float64) @ _Z_TO_Y if "NORMAL" in at else None,
                "J": acc(at["JOINTS_0"]).astype(np.int64) if "JOINTS_0" in at else None,
                "W": acc(at["WEIGHTS_0"]).astype(np.float64) if "WEIGHTS_0" in at else None,
                "colour": list(pbr.get("baseColorFactor") or [0.8, 0.8, 0.8, 1.0])[:3],
                "metallic": float(pbr.get("metallicFactor", 0.0)), "roughness": float(pbr.get("roughnessFactor", 0.85)),
                "alpha_cut": mat.get("alphaMode") == "MASK", "maps": maps})
    return {"bones": bones, "meshes": meshes}


def shell_of(V: np.ndarray, T: np.ndarray) -> dict | None:
    """{"outer": n, "thickness": m} when the mesh is garment_game.shell's: the outer face's triangles first, then the
    same triangles on a second copy of the vertices (the inner face), then rims; else None (one-sided)."""
    h = len(V) // 2
    if len(V) % 2 or not len(T):
        return None
    lead = T.max(1) < h
    k = int(len(T) if lead.all() else np.argmin(lead))
    if not k or len(T) < 2 * k or T[k:2 * k].min() < h:
        return None
    if not np.array_equal(np.sort(T[k:2 * k] - h, axis=1), np.sort(T[:k], axis=1)):
        return None
    return {"outer": k, "thickness": float(np.median(np.linalg.norm(V[:h] - V[h:], axis=1)))}


def part_of(V, T, uv, N=None) -> dict:
    """A per-vertex mesh as an export part (asset_parts.lowpoly's form: per-corner uv, normal, tangent, sign)."""
    from . import hair_export
    V, T = np.asarray(V, np.float64), np.asarray(T, np.int64)
    c = T.ravel()
    UVc = np.asarray(uv, np.float64)[c]
    n, tt, sg = hair_export._tangents(V, T, UVc)
    if N is not None:  # the garment's own normals (shared across its seams; the inner face's point in)
        n = np.asarray(N, np.float64)[c]
        n = n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
    tt = tt - (tt * n).sum(1, keepdims=True) * n
    flat = np.linalg.norm(tt, axis=1) < 1e-6  # (no uv gradient: a detail on one palette cell) any direction across n
    if flat.any():
        ax = np.where(np.abs(n[flat, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
        tt[flat] = np.cross(ax, n[flat])
    tt /= np.linalg.norm(tt, axis=1, keepdims=True) + 1e-12
    return {"verts": V.astype(np.float32), "corner_vert": c.astype(np.int64), "uv": UVc.astype(np.float32),
            "normal": n.astype(np.float32), "tangent": tt.astype(np.float32), "sign": np.asarray(sg, np.float32)}


def _vertex_normals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, T[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)


def _flat_maps(stem: Path, colour=(204, 204, 204), rough=0.85) -> dict:
    from PIL import Image
    f = {k: stem.parent / f"{stem.name}_{k}.png" for k in ("basecolor", "normal", "orm")}
    Image.new("RGB", (16, 16), tuple(int(x) for x in colour)).save(f["basecolor"])
    Image.new("RGB", (16, 16), (128, 128, 255)).save(f["normal"])
    Image.new("RGB", (16, 16), (255, int(255 * rough), 0)).save(f["orm"])
    return f


def own_part(m: dict) -> dict:
    """The garment's own mesh (a read() mesh) as an export part, its two-sided layout named when it has one."""
    uv = m["uv"] if m["uv"] is not None else np.full((len(m["V"]), 2), 0.5)
    part = part_of(m["V"], m["T"], uv, m["N"])
    sh = shell_of(m["V"], m["T"])
    if sh:
        part["shell"] = sh
    return part


def garment_part(gname: str, m: dict, out_dir: Path) -> tuple[dict, dict, bool]:
    """(part, files, alpha_cut) for the garment's own mesh: its maps written as the asset's map files."""
    import io
    from PIL import Image
    stem = Path(out_dir) / f"cloth_{gname}"
    part = own_part(m)
    maps = m["maps"] or {}
    if maps.get("base"):
        files = {"basecolor": stem.parent / f"{stem.name}_basecolor.png", "normal": stem.parent / f"{stem.name}_normal.png",
                 "orm": stem.parent / f"{stem.name}_orm.png"}
        base = Image.open(io.BytesIO(maps["base"]))
        (base if m["alpha_cut"] else base.convert("RGB")).save(files["basecolor"])
        if maps.get("normal"):
            files["normal"].write_bytes(maps["normal"])
        else:
            Image.new("RGB", (16, 16), (128, 128, 255)).save(files["normal"])
        if maps.get("mr"):  # glTF's metallic-roughness (G roughness, B metallic) is our ORM once R (occlusion) is 1
            mr = np.array(Image.open(io.BytesIO(maps["mr"])).convert("RGB"))
            mr[..., 0] = 255
            Image.fromarray(mr).save(files["orm"])
        else:
            Image.new("RGB", (16, 16), (255, int(255 * m["roughness"]), int(255 * m["metallic"]))).save(files["orm"])
    else:
        files = _flat_maps(stem, [round(255 * float(x)) for x in m["colour"]], m["roughness"])
    files["specular"] = stem.parent / f"{stem.name}_specular_gltf.png"
    Image.new("RGBA", (16, 16), (255, 255, 255, 128)).save(files["specular"])
    return part, files, bool(m["alpha_cut"] and maps.get("base"))


def details_mesh(meshes: list, cells: dict) -> tuple[dict, np.ndarray, np.ndarray]:
    """(part, J, W): detail meshes as ONE part, each on its own palette cell (cells: {mesh name: cell index})."""
    n = len(cells)
    Vs, Ts, UVs, Ns, Js, Ws, k = [], [], [], [], [], [], 0
    for m in meshes:
        V, T = m["V"], m["T"]
        Vs.append(V)
        Ts.append(T + k)
        UVs.append(np.tile([(cells[m["name"]] + 0.5) / n, 0.5], (len(V), 1)))
        Ns.append(m["N"] if m["N"] is not None else _vertex_normals(V, T))
        Js.append(m["J"])
        Ws.append(m["W"])
        k += len(V)
    return part_of(np.vstack(Vs), np.vstack(Ts), np.vstack(UVs), np.vstack(Ns)), np.vstack(Js), np.vstack(Ws)


def details_part(gname: str, meshes: list, out_dir: Path) -> tuple[dict, dict, np.ndarray, np.ndarray]:
    """(part, files, J, W): a garment's details as ONE part, each detail's colour / roughness / metallic in its own
    cell of a palette (one material for every button, not one each)."""
    from PIL import Image
    stem = Path(out_dir) / f"cloth_{gname}_details"
    n = len(meshes)
    base = np.zeros((CELL, CELL * n, 3), np.uint8)
    orm = np.zeros((CELL, CELL * n, 3), np.uint8)
    for i, m in enumerate(meshes):
        base[:, i * CELL:(i + 1) * CELL] = [round(255 * float(x)) for x in m["colour"]]
        orm[:, i * CELL:(i + 1) * CELL] = (255, round(255 * m["roughness"]), round(255 * m["metallic"]))
    part, J, W = details_mesh(meshes, {m["name"]: i for i, m in enumerate(meshes)})
    files = {"basecolor": stem.parent / f"{stem.name}_basecolor.png", "normal": stem.parent / f"{stem.name}_normal.png",
             "orm": stem.parent / f"{stem.name}_orm.png", "specular": stem.parent / f"{stem.name}_specular_gltf.png"}
    Image.fromarray(base).save(files["basecolor"])
    Image.fromarray(orm).save(files["orm"])
    Image.new("RGB", (16, 16), (128, 128, 255)).save(files["normal"])
    Image.new("RGBA", (16, 16), (255, 255, 255, 128)).save(files["specular"])
    return part, files, J, W


def _split(g: dict, gname: str) -> tuple[dict, list]:
    """(the garment's own mesh, its detail meshes) of a read() file."""
    own = ([m for m in g["meshes"] if m["name"] == gname] or g["meshes"][:1])[0]
    return own, [m for m in g["meshes"] if m is not own]


def parts(name: str, recs: dict, out_dir, log=print) -> tuple[list, dict, dict, list, dict]:
    out_dir = Path(out_dir)
    cparts, weights, looks, left, lods = [], {}, {}, [], {}
    for gname, rec in recs.items():
        call = f'export_garment("{name}", "{gname}")'
        try:
            glb, warn = exported(rec)
        except NotShipped as e:
            left.append((gname, str(e)))
            continue
        g = read(glb)
        own, det = _split(g, gname)
        if any(m["J"] is None or m["W"] is None for m in [own] + det):
            left.append((gname, f"its exported file has no skin weights ({glb}); next: {call}"))
            continue
        part, files, cut = garment_part(gname, own, out_dir)
        pn = f"cloth_{gname}"
        cparts.append((pn, part, files))
        weights[pn] = (g["bones"], own["J"], own["W"])
        if cut:
            looks[pn] = {"alpha_cutoff": 0.5}
        sh = part.get("shell")
        log(f"cloth {gname}: the chain garment as export_garment wrote it ({glb.name}: {len(own['T'])} triangles"
            + (f", {sh['outer']} outer, {sh['thickness'] * 1000:.1f} mm thick" if sh else ", one-sided")
            + f"; its own maps and weights), not rebuilt")
        if det:
            dpart, dfiles, dJ, dW = details_part(gname, det, out_dir)
            cparts.append((pn + "_details", dpart, dfiles))
            weights[pn + "_details"] = (g["bones"], dJ, dW)
            log(f"cloth {gname}: {len(det)} detail(s) ({', '.join(m['name'][len(gname) + 1:] or m['name'] for m in det)}; "
                f"{sum(len(m['T']) for m in det)} triangles) as one part on a palette")
        for w in warn:
            log(f"WARNING cloth {gname}: {w}")
        cells = {m["name"]: i for i, m in enumerate(det)}
        own_lods = lod_files(rec)
        for k, (f, share) in own_lods.items():
            gk = read(f)
            ok, dk = _split(gk, gname)
            dk = [m for m in dk if m["name"] in cells]
            lods.setdefault(k, {})[pn] = (own_part(ok), (gk["bones"], ok["J"], ok["W"]), share)
            if det:  # (a LOD without details leaves the part out: too small to see at its distance)
                lods[k][pn + "_details"] = (None, None, share)
                if dk:
                    dp, dJ, dW = details_mesh(dk, cells)
                    lods[k][pn + "_details"] = (dp, (gk["bones"], dJ, dW), share)
        if own_lods:
            log(f"cloth {gname}: its own LOD files ({', '.join(f'LOD{k} {f.name}' for k, (f, _) in sorted(own_lods.items()))}):"
                " the pattern re-grid at a coarser grid, taken as they are (never decimated)")
        else:
            log(f"WARNING cloth {gname}: its export has no LOD files, so its LODs are DECIMATED from LOD0 like any part "
                f"(that kinks and tears a chain garment); next: {call} again (it writes one file per LOD), then this export")
    return cparts, weights, looks, left, lods


def take_lods(own: dict, parts: dict, lp: dict, lr: dict | None, rep: dict, bones: list | None) -> str:
    """One LOD's chain parts from the garments' own LOD files, put into asset_export's LOD in place of a decimation:
    own {part name: (part | None, weights, share)} (parts()' lods[k]); parts: LOD0's (the atlas index and the pose
    correctives are carried from it: each LOD vertex takes them at its closest point of LOD0's surface, as
    lods_part.lod_part does); lp / lr["weights"] / rep: this LOD's parts, rig weights and report. A part the LOD
    leaves out is not in lp. Returns the log line."""
    from . import garment_export as ge
    from . import lods as lodmod
    bits = []
    for pn, (part, w, share) in own.items():
        p0 = parts[pn]
        n0 = len(p0["corner_vert"]) // 3
        if part is None:
            lp.pop(pn, None)
            if lr is not None:
                lr["weights"].pop(pn, None)
            rep[pn] = {"triangles0": n0, "triangles": 0, "own_lod": True}
            bits.append(f"{pn} left out (too small to see at this LOD)")
            continue
        q = {**part, "atlas": p0.get("atlas", 0)}
        sh0 = {nm: v for nm, v in (p0.get("shapes") or {}).items() if nm.startswith(lodmod.POSE_SHAPE)}
        if sh0:
            c, b = ge.on_surface(q["verts"], p0["verts"], np.asarray(p0["corner_vert"], np.int64).reshape(-1, 3))
            unit = lambda a: a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)  # noqa: E731
            at = lambda a: np.einsum("nk,nkc->nc", b, np.asarray(a, np.float64)[c])  # noqa: E731
            q["shapes"] = {nm: (at(d), unit(at(n_a)), unit(at(n_b))) for nm, (d, n_a, n_b) in sh0.items()}
        lp[pn] = q
        if lr is not None:
            lr["weights"].update(bone_weights({pn: w}, bones))
        rep[pn] = {"triangles0": n0, "triangles": len(q["corner_vert"]) // 3, "own_lod": True}
        bits.append(f"{pn} {rep[pn]['triangles']} ({share:g} of its budget)")
    return "the garments' own LOD files (export_garment's re-grid; not decimated): " + ", ".join(bits)


THROUGH_REACH = 0.05  # m: how far along a skin vertex's normal, either way, a LOD's cloth is looked for


def skin_through(p: dict, covers: list, P0: np.ndarray, under0: np.ndarray, reach: float = THROUGH_REACH) -> np.ndarray:
    """keep mask per triangle of `p` (a LOD of the skin, or of any part worn under garments): False where a corner
    lies OUTSIDE the nearest surface of `covers` (this LOD's chain garments, their own LOD files) and every corner's
    nearest LOD0 point (P0, lods_under.under_at_lod0's) was under a garment (under0). What was covered at LOD0 and
    sticks through the coarser cloth is hidden skin showing: cut. Skin that was never covered (a wrist past the cuff,
    the chest in the collar's opening) has no such LOD0 point and stays."""
    from scipy.spatial import cKDTree
    from . import lods_under
    T = np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)
    under0 = np.asarray(under0, bool)
    if not covers or not len(P0) or not under0.any() or not len(T):
        return np.ones(len(T), bool)
    V = np.asarray(p["verts"], np.float64)
    vid, _, _, t = lods_under.under_depth(p, covers, reach)
    out = np.zeros(len(V), bool)
    out[np.asarray(vid)[np.isfinite(t) & (t < 0)]] = True
    was = under0[cKDTree(np.asarray(P0, np.float64)).query(V)[1]]
    return ~(was[T].all(1) & out[T].any(1))


def covered_at_lod0(p: dict, covers: list, mask: tuple) -> tuple:
    """(P0, under0) for skin_through: `p`'s LOD0 outward points and whether each lay UNDER `covers` (the chain garments
    at LOD0) within asset.UNDER_CLOTH_REACH, the reach of LOD0's own cull of covered skin. lods_under's mask
    (`mask`: asset_export's under_masks entry) looks 2 cm, and a sleeve stands 2-4 cm off the arm: read by it, the
    skin under a loose sleeve was never covered and stayed, through the LOD's cloth. Points a clip frame uncovers
    (mask[4] and not mask[5]) stay kept at every LOD, as they are for the other culls."""
    from . import asset, lods_under
    P0, under0 = lods_under.under_at_lod0(p, covers, reach=asset.UNDER_CLOTH_REACH)
    if len(mask) > 5 and len(mask[4]) == len(under0):
        under0 = under0 & ~(np.asarray(mask[4], bool) & ~np.asarray(mask[5], bool))
    return P0, under0


def bone_weights(weights: dict, bones: list) -> dict:
    """The garments' weights in the export rig's bone order. A garment bone the rig does not have (the rig changed
    since step 10) is refused: its weights would move the cloth with the wrong bone."""
    at = {b["name"]: i for i, b in enumerate(bones)}
    out = {}
    for pn, (names, J, W) in weights.items():
        J, W = np.asarray(J, np.int64), np.asarray(W, np.float64)
        used = np.unique(J[W > 0])
        gone = sorted({names[j] for j in used if names[j] not in at})
        if gone:
            raise ValueError(f"{pn}: its weights use bone(s) the export rig does not have ({', '.join(gone[:6])}): the rig "
                             "changed since the garment's export. next: export_garment again, then this export")
        remap = np.array([at.get(nm, 0) for nm in names], np.int64)
        out[pn] = (remap[J], W)
    return out
