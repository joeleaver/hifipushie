"""Splitting parts: density groups, split, mesh parts, big parts, topology parts. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import asset
from . import assemble, sdf, store, surface
from .spec import compile_prims
from .asset_hidden import _deep_hidden

def _pow2(x: float, lo: int = 256) -> int:
    return int(max(lo, 2 ** int(np.ceil(np.log2(max(x, 1.0))))))


def density_groups(units: dict, loads: dict, fixed: dict, max_texture: int, fill: float) -> dict:
    """Atlas name per part, from a texel density: units ({unit: [parts]}, a prefab's parts stay together) go
    largest first into the first atlas with room (max_texture^2 x fill texels), opening atlases as needed.
    fixed: parts with their own "atlas" name, which they keep."""
    cap = max_texture ** 2 * fill
    out = dict(fixed)
    bins: list[float] = []
    for u in sorted(units, key=lambda u: -sum(loads[p] for p in units[u])):
        ps = [p for p in units[u] if p not in fixed]
        need = sum(loads[p] for p in ps)
        if not ps:
            continue
        i = next((k for k, b in enumerate(bins) if b + need <= cap), None)
        if i is None:
            bins.append(0.0)
            i = len(bins) - 1
        bins[i] += need
        for p in ps:
            out[p] = str(i)
    return out


def split(spec: dict, resolution: int, instancing: bool, log: list, min_share: int = 2,
          voxels: dict | None = None) -> dict:
    """What gets meshed and baked: the model's parts, minus the instances of shared prefabs, plus one copy of each
    shared prefab's parts (named "<prefab>/<part>") taken from its bake instance (the first unmirrored one).
    A prefab is shared when it has `min_share`+ instances (the scene uses 1: every instance is a movable object),
    unless prefabs.<p>.export is "unique" (then its instances are
    baked into the scene like any element). Returns {"streams": {export part: prims}, "origin": {export part:
    model part}, "frames": {export part: (lo, voxel, shape)}, "voxel": scene voxel, "full": {model part: prims}
    (the whole model: AO, sky and paint context), "prefabs": {prefab: {"bake": instance, "instances": {instance:
    local -> world 4x4}, "parts": [export parts]}}}. voxels: {part: voxel} at most (face shapes: the lips' slit)."""
    prims = compile_prims(spec)
    full = {ps[0].part: ps for ps in sdf.streams(prims)}
    lo, voxel, shape = sdf.frame(prims, resolution)
    pls = assemble.placements(spec) if instancing else {}
    by_pf: dict[str, list] = {}
    for inst, pl in pls.items():
        by_pf.setdefault(pl["use"], []).append(inst)
    shared = {}
    for pf, insts in by_pf.items():
        mode = ((spec.get("prefabs") or {}).get(pf) or {}).get("export", "share")
        if mode not in ("share", "unique"):
            raise ValueError(f"prefabs.{pf}.export is \"share\" or \"unique\"")
        if mode == "unique" or len(insts) < min_share:
            log.append(f"prefab {pf}: {len(insts)} instance(s) baked into the scene"
                       + (" (export: unique)" if mode == "unique" else ""))
            continue
        bake = next((i for i in insts if not pls[i]["mirror"]), insts[0])
        shared[pf] = {"bake": bake, "instances": {i: assemble.world_of(pls[i]) for i in insts}, "parts": []}
    owner = {inst: pf for pf, d in shared.items() for inst in d["instances"]}
    xs, origin = {}, {}
    for pn, ps in full.items():
        groups: dict[str, list] = {}
        shells = [p for p in ps if p.kind == "shell"]
        for p in ps:
            if p.kind == "shell":
                continue
            pf = owner.get(p.instance)
            if pf is not None and p.instance != shared[pf]["bake"]:
                continue
            groups.setdefault(pn if pf is None else f"{pf}/{pn}", []).append(p)
        for key, g in groups.items():
            if not any(q.op in ("add", "intersect") for q in g):
                continue  # only cuts (or a shell's region is all on instances)
            xs[key], origin[key] = shells + g, pn
            if key != pn:
                shared[key.split("/")[0]]["parts"].append(key)
    frames = {}
    for key, ps in xs.items():
        if key == origin[key]:
            from . import scene_objects
            pv, _ = scene_objects.part_voxel(ps, voxel)
            if (voxels or {}).get(key):
                pv = min(pv, float(voxels[key]))
            # a part finer than the model's voxel (a shirt collar's 6 mm sheet, a strap) on its own grid, as the
            # scene meshes it: at the model's 7.8 mm the collar came out as shreds
            frames[key] = (lo, voxel, shape) if pv >= voxel else scene_objects._frame(ps, pv)
            continue
        # a prefab is meshed in a box of its own, finer if it's small (`resolution` voxels across it)
        pf = key.split("/")[0]
        own = [q for k in shared[pf]["parts"] for q in xs[k] if q.kind != "shell" and q.op in ("add", "intersect")]
        a, b = np.min([q.lo for q in own], 0) - 0.02, np.max([q.hi for q in own], 0) + 0.02
        v = min(voxel, float((b - a).max()) / resolution)
        frames[key] = (a, v, np.ceil((b - a) / v).astype(int) + 1)
    for pf, d in shared.items():
        v = frames[d["parts"][0]][1] if d["parts"] else voxel
        log.append(f"prefab {pf}: {len(d['instances'])} instances share one mesh and one set of texels, baked at "
                   f"{d['bake']} (its paint, AO and sky as it stands there; voxel {v * 1000:.1f} mm)")
    return {"streams": xs, "origin": origin, "frames": frames, "voxel": float(voxel), "full": full,
            "prefabs": {pf: d for pf, d in shared.items() if d["parts"]}, "defs": spec.get("parts") or {}}


def mesh_parts(ctx: dict, out: Path) -> Path:
    """Mesh every export part on its frame and project it onto its exact surface (as store.build does)."""
    V, F, N, P, names = [], [], [], [], []
    for key, ps in ctx["streams"].items():
        lo, vx, shape = ctx["frames"][key]
        f, _ = sdf.PartGrid().update(ps, (lo, vx, shape))
        m = store._mesh_part(ps, f, lo, vx, [], {})
        if m is False:
            continue
        v, fc, n, _ = m
        F.append(fc + sum(len(x) for x in V))
        V.append(v)
        N.append(n)
        P.append(np.full(len(v), len(names), np.int16))
        names.append(key)
    np.savez(out, verts=np.concatenate(V), faces=np.concatenate(F), normals=np.concatenate(N),
             part=np.concatenate(P), part_names=np.array(names))
    return out


def split_big(mesh: Path, ctx: dict, rel: dict, texture: int, log: list) -> None:
    """A part (not a prefab's) that wants more texels than one `texture` atlas holds at its density is cut into
    slabs of equal load along its longest side ("roof~0", "roof~1", ...), each an export part of its own on the
    same exact surface (ctx streams, frames and origin copied), so each can take an atlas. The slabs keep the
    vertices they share on the high mesh, so the joint decimation keeps them joined (lowpoly never re-decimates
    them alone: `split` in their cfg)."""
    z = dict(np.load(mesh))
    V, F, part = z["verts"].astype(np.float64), z["faces"], z["part"].copy()
    names = [str(n) for n in z["part_names"]]
    fpart = part[F[:, 0]]
    c = V[F]
    area = np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1) / 2
    cap = texture ** 2 * asset.FILL
    pf_parts = {pn for d in ctx["prefabs"].values() for pn in d["parts"]}
    changed = False
    for i, pn in enumerate(list(names)):
        sel = fpart == i
        load = float(area[sel].sum()) * rel.get(pn, 1.0) ** 2
        if pn in pf_parts or not sel.any() or load <= cap:
            continue
        k = int(np.ceil(load / cap))
        cen = c[sel].mean(1)
        ax = int(np.argmax(np.ptp(cen, 0)))
        order = np.argsort(cen[:, ax])
        cum = np.cumsum(area[sel][order]) / area[sel].sum()
        cuts = [float(cen[order[np.searchsorted(cum, j / k)], ax]) for j in range(1, k)]
        vids = np.unique(F[sel])
        grp = np.searchsorted(cuts, V[vids, ax])
        new = [f"{pn}~{j}" for j in range(k)]
        idx = [i] + [len(names) + j for j in range(k - 1)]
        names[i] = new[0]
        names += new[1:]
        part[vids] = np.asarray(idx, part.dtype)[grp]
        for n in new:
            for key in ("streams", "frames", "origin"):
                ctx[key][n] = ctx[key][pn]
        for key in ("streams", "frames", "origin"):
            ctx[key].pop(pn)
        ctx.setdefault("split", {}).update({n: pn for n in new})
        log.append(f"{pn}: {load / cap:.1f} atlases' worth of texels at its density ({asset.FILL:.0%} packed): split into "
                   f"{k} along {'xyz'[ax]} ({', '.join(new)})")
        changed = True
    if changed:
        z["part"], z["part_names"] = part, np.array(names)
        np.savez(mesh, **z)


def topology_parts(spec: dict, ctx: dict, out_dir: Path, log: list, high: Path | None = None) -> dict:
    """Parts with a modelled topology instead of a decimation: parts.<p>.topology = "wrap" (the body of a humanoid:
    retopo_wrap.wrap, the template's quads carried onto it; a base's grafted head keeps its own) or "limbs" (any creature:
    limbloops.build, quad rings down each limb of the part and out into its body, the rest of the part decimated to
    parts.<p>.topology_triangles, from the export's own high mesh), its faces buried in other parts (skin under
    clothes, where animation would only poke it through) dropped. {part: npz path}."""
    import hashlib
    defs = spec.get("parts") or {}
    out = {}
    for pn in ctx["streams"]:
        kind = (defs.get(ctx["origin"][pn]) or {}).get("topology")
        if kind not in ("wrap", "template", "limbs"):
            continue
        tl = []
        if kind == "limbs":
            from . import limbloops
            if high is None:
                raise ValueError(f"parts.{pn}.topology = \"limbs\" needs the export's high mesh")
            with np.load(high) as z:
                hv, hf, hp = z["verts"], z["faces"], z["part"]
                k = [str(n) for n in z["part_names"]].index(pn)
            fb = hf[(hp[hf] == k).all(1)]
            used = np.unique(fb)
            r = limbloops.build(spec, ctx["streams"][pn], hv[used], np.searchsorted(used, fb), ctx["voxel"],
                                int((defs.get(ctx["origin"][pn]) or {}).get("topology_triangles", limbloops.BODY_TRIANGLES)),
                                part=ctx["origin"][pn], log=tl)
            tl = [f"limbs: {x}" if not x.startswith("limbs") else x for x in tl]
            log.extend(x for x in tl if "WARNING" in x)
        else:
            if ctx["origin"][pn] != "body":
                raise ValueError(f"parts.{pn}.topology = \"wrap\": only the body (a humanoid's) can be wrapped")
            from . import retopo_wrap
            r = retopo_wrap.wrap(spec, log=tl)
        V, L, S = r["verts"], r["loops"], r["sizes"]
        names = list(ctx["streams"])
        hid = surface.hidden(ctx["streams"], V, np.full(len(V), names.index(pn)), names, ctx["voxel"],
                             ctx.get("apart")) > 0.5
        hid = _deep_hidden(np.asarray(V, np.float64), hid, np.zeros(len(V), int))
        if r.get("gnm") is not None:  # (one mesh) GNM's head is all kept: its lids' insides lie in the eyeballs and
            # its mouth round the teeth, and a blink or a jaw drags them out (dropped, the left lid's margin was a row
            # of spikes with the eyeball showing through: the eyes look a little apart, so one side lost more)
            hid &= np.asarray(r["gnm"]) < 0
        if kind == "limbs":  # an opening's rings keep their faces under teeth and tongue: they show when it moves
            for k_, ids in (r.get("rings") or {}).items():
                if " rim" in k_ or " wall" in k_:
                    hid[np.asarray(ids)] = False
        st = np.r_[0, np.cumsum(S)[:-1]]
        faces = [L[a:a + k] for a, k in zip(st, S)]
        kept = [f for f in faces if not hid[f].all()]
        used = np.unique(np.concatenate(kept))
        rm = np.full(len(V), -1)
        rm[used] = np.arange(len(used))
        Vk, Lk, Sk = V[used], rm[np.concatenate(kept)], np.array([len(f) for f in kept])
        gk = np.asarray(r["gnm"])[used] if r.get("gnm") is not None else None
        if kind != "limbs" and (defs.get(ctx["origin"][pn]) or {}).get("joint_density", True) and \
                spec.get("rig", {}) is not False:  # (limbs pack their own joint loops)
            # the same triangles spent where it bends: hinge zones split, shafts thinned (topodensity.py)
            from . import rig_report
            from . import topodensity
            try:
                Vk, Lk, Sk, gk = topodensity.rebalance(rig_report.rig_bones(spec), Vk, Lk, Sk, gk, ctx["streams"][pn],
                                                       ctx["voxel"], log)
            except Exception as e:  # (the plain wrap is still a body)
                log.append(f"WARNING body density: not rebalanced ({type(e).__name__}: {e})")
        path = out_dir / f"topology_{pn}.npz"
        extra = {"gnm": gk} if gk is not None else {}  # (one mesh: GNM vertex ids,
        # face shapes go by index)
        if r.get("rings") and kind == "limbs":  # (limbs: the key rings' vertex ids, for quality and later passes;
            # a ring the hidden drop broke is left out)
            import json as _json
            keep = {k: rm[np.asarray(v)].tolist() for k, v in r["rings"].items() if (rm[np.asarray(v)] >= 0).all()}
            extra["rings"] = np.array(_json.dumps(keep))
        np.savez(path, verts=Vk, loops=Lk, sizes=Sk, **extra)
        out[pn] = (str(path), hashlib.sha1(Vk.tobytes() + Lk.tobytes()).hexdigest()[:12])
        log.append(f"{pn}: {'limb-loop' if kind == 'limbs' else 'wrapped'} topology, {len(Sk)} faces ({(Sk == 4).mean():.0%} quads, "
                   f"{int((Sk - 2).sum())} triangles), {len(faces) - len(kept)} faces under other parts dropped; "
                   + "; ".join(x for x in tl if x.startswith(("wrapped", "head", "limbs:"))))
    return out
