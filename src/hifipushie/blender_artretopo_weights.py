"""Artist retopo, inside Blender: the weighting passes after bone heat (blender_artretopo_rig.py calls them in order).
Each is a lesson from the spike (Mabel, Scraps, Hettie); guide(topic="retopo") "Rig" has the reasons.

1. helpers: half-angle _bend bones on shoulder, elbow, knee take the joint's share of vertices weighted to both
   sides; the hand-over Laplacian-smoothed. (No hip helper: 5 x stretches.)
2. jaw: the cage's jaw group replaces bone heat's guess (bone heat's own group named after the Jaw bone is reused: a
   second "Jaw.001" is never driven); the mouth inside belongs to Head (+ Jaw) only; what bone heat gave wholly to the
   jaw beyond the group's weight goes to Head; the border smoothed.
3. fingers: feather fingers in a flat paddle (a wing tip) weighted by GEOMETRY (bone heat blurs them into each other):
   along the tip each part belongs to its finger segment (tents over the joint stations), across the tip to its finger
   (gaussians over the fingers' lanes); the tip's share of the total is kept.
4. head_only: the cage's head_only group (a muzzle / beak from its root inward) blends to Head (keeping its Jaw
   share): a beak sitting on the chest otherwise has its lower half owned by Neck / Spine and smears on a head turn.
5. shoulder midline: a clavicle never owns the midline: its weight fades to Spine2 (smoothstep) from 15 % to 60 % of
   the shoulder joint's |x| (bone heat gave a chin on the chest to both clavicles, 0.3 + 0.33).
6. neck_ramp [z0, z1] (joints): a character with no neck: over the band each vertex's Spine2 + Neck + Head share is
   re-laid by height as (1-f)^2, 2f(1-f), f^2 (smoothstep f): a head turn twists through the collar softly.
7. empty: a vertex left with no weight copies its nearest weighted neighbour.
8. normalise: every vertex whose total is between 1e-3 and 0.999 is scaled to 1 (a short total leaves part of the
   vertex behind when its bones move)."""
import json
import math
import os

import bpy
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree

import blender_artretopo_common as C


def _subtree(BONES, n):
    kids = {}
    for b, par, *_ in BONES:
        kids.setdefault(par, []).append(b)
    out, todo = [], [n]
    while todo:
        x = todo.pop(); out.append(x); todo += kids.get(x, [])
    return out


def _neighbours(body):
    bm = bmesh.new(); bm.from_mesh(body.data); bm.verts.ensure_lookup_table()
    nb = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]; bm.free()
    return nb


def helpers(body, rig, BONES, HELP, PFX, smooth=6):
    arm_d = rig.data; VG = body.vertex_groups
    bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="EDIT")
    for side in ("Left", "Right"):
        for j, par in HELP.items():
            jb = arm_d.edit_bones[PFX + side + j]
            h = arm_d.edit_bones.new(PFX + side + j + "_bend"); h.head = jb.head; h.tail = jb.head + (jb.tail - jb.head) * 0.3
            h.parent = arm_d.edit_bones[PFX + (side + par if par else "Hips")]; h.roll = jb.roll
    bpy.ops.object.mode_set(mode="OBJECT")
    for side in ("Left", "Right"):
        for j in HELP:
            sub = {PFX + x for x in _subtree(BONES, side + j)}
            hg = VG.new(name=PFX + side + j + "_bend")
            for v in body.data.vertices:
                ws = {VG[g.group].name: g.weight for g in v.groups}
                a_ = sum(w for n, w in ws.items() if n in sub)
                b_ = sum(w for n, w in ws.items() if n not in sub and not n.endswith("_bend"))
                hgt = 2 * min(a_, b_)
                if hgt <= 1e-4:
                    continue
                sa = (a_ - hgt / 2) / a_ if a_ > 0 else 0; sb = (b_ - hgt / 2) / b_ if b_ > 0 else 0
                for n, w in ws.items():
                    if not n.endswith("_bend"):
                        VG[n].add([v.index], w * (sa if n in sub else sb), "REPLACE")
                hg.add([v.index], hgt, "REPLACE")
    nb = _neighbours(body)
    for side in ("Left", "Right"):
        for j, par in HELP.items():
            names = [PFX + side + j + "_bend", PFX + side + j, PFX + (side + par if par else "Hips")]
            W = {n: [0.0] * len(body.data.vertices) for n in names}
            for v in body.data.vertices:
                for g in v.groups:
                    n = VG[g.group].name
                    if n in W:
                        W[n][v.index] = g.weight
            zone = [i for i in range(len(nb)) if any(W[n][i] > 0 for n in names)]
            tot = [sum(W[n][i] for n in names) for i in range(len(nb))]
            for _ in range(smooth):
                for n in names:
                    w = W[n]; W[n] = w[:]
                    for i in zone:
                        W[n][i] = 0.5 * w[i] + 0.5 * sum(w[k] for k in nb[i]) / len(nb[i])
            for i in zone:
                ssum = sum(W[n][i] for n in names) or 1
                for n in names:
                    val = W[n][i] / ssum * tot[i]
                    if val > 1e-4:
                        VG[n].add([i], val, "REPLACE")
                    else:
                        VG[n].remove([i])


def low_lookup(D, body):
    """per body vertex, the index of the nearest low.ply vertex (the cage groups are on low.ply's vertices)"""
    ref = C.load_ply(f"{D}/low.ply", "ref")
    kd = KDTree(len(ref.data.vertices))
    for v in ref.data.vertices:
        kd.insert(v.co, v.index)
    kd.balance(); bpy.data.objects.remove(ref)
    return [kd.find(body.matrix_world @ v.co)[1] for v in body.data.vertices]


def jaw(D, body, PFX, look, smooth=4):
    G = json.load(open(f"{D}/low_groups.json")); jw = G.get("jaw"); inside = G.get("mouth_inside")
    VG = body.vertex_groups
    gj = VG.get(PFX + "Jaw") or VG.new(name=PFX + "Jaw"); gh = VG[PFX + "Head"]; n = 0
    for v in body.data.vertices:
        ix = look[v.index]; w = jw[ix] if jw else 0.0
        if inside and inside[ix] > 1e-3:      # the inside of the mouth is the head's (and the jaw's) only
            for g in list(v.groups):
                if g.group != gh.index:
                    VG[g.group].remove([v.index])
            gh.add([v.index], 1.0, "REPLACE")
        others = [g for g in v.groups if g.group != gj.index]
        tot = sum(g.weight for g in others)
        if tot > 1e-4:
            for g in others:
                g.weight = g.weight / tot * (1 - w)
        elif w < 1 - 1e-4:                    # bone heat gave it all to the jaw: the rest is the head's
            gh.add([v.index], 1 - w, "REPLACE")
        if w > 1e-3:
            gj.add([v.index], w, "REPLACE"); n += 1
        else:
            gj.remove([v.index])
    if smooth:
        C.select_only(body); VG.active_index = gj.index
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        bpy.ops.object.vertex_group_smooth(group_select_mode="ACTIVE", factor=0.5, repeat=smooth)
        bpy.ops.object.vertex_group_normalize_all(lock_active=True)
        bpy.ops.object.mode_set(mode="OBJECT")
    return n


def fingers(body, JT, PFX):
    """geometric weights for feather fingers at a paddle's tip (JT["fingers"]: {name: 4 points, left side})"""
    fnames = list(JT["fingers"]); VG = body.vertex_groups; moved = 0
    for side, sg in (("Left", 1), ("Right", -1)):
        m = lambda p: Vector((p[0] * sg, p[1], p[2]))
        gi = {g.name for g in VG}
        tipg = [n for n in [PFX + side + "Hand"] + [PFX + f"{side}Hand{f}{k}" for f in fnames for k in (1, 2, 3)] if n in gi]
        W0, T0 = m(JT["wrist"]), m(JT["hand_end"])
        axis = (T0 - W0).normalized()
        lanes = {f: m(JT["fingers"][f][0]) for f in fnames}
        across = lanes[fnames[-1]] - lanes[fnames[0]]; across -= axis * across.dot(axis)
        spread = across.length
        if spread < 1e-6:
            across = Vector((0, 0, 1)); spread = 0.02
        across.normalize()
        lane_c = {f: (lanes[f] - W0).dot(across) for f in fnames}
        sj = [sum((m(JT["fingers"][f][k]) - W0).dot(axis) for f in fnames) / len(fnames) for k in range(4)]
        sigma = spread / max(1, len(fnames) - 1) * 0.6
        for v in body.data.vertices:
            ws = {VG[g.group].name: g.weight for g in v.groups}
            tot = sum(ws.get(n, 0.0) for n in tipg)
            if tot < 1e-3:
                continue
            d = v.co - W0; s_ = d.dot(axis); l_ = d.dot(across)
            hand = 1.0 if s_ < sj[0] - 0.01 else max(0.0, 1 - (s_ - (sj[0] - 0.01)) / 0.02)
            lw = {f: math.exp(-((l_ - lane_c[f]) / sigma) ** 2) for f in fnames}; ls = sum(lw.values()) or 1
            t = (s_ - sj[0]) / max(1e-6, sj[3] - sj[0]) * 3
            kw = {k: max(0.0, 1 - abs(t - (k - 0.5))) for k in (1, 2, 3)}
            if t > 2.5:
                kw[3] = 1.0
            if t < 0.5:
                kw[1] = max(kw[1], 1.0 - hand)
            ks = sum(kw.values()) or 1
            for n in tipg:
                VG[n].remove([v.index])
            if hand > 0:
                VG[PFX + side + "Hand"].add([v.index], tot * hand, "REPLACE")
            for f in fnames:
                for k in (1, 2, 3):
                    w = tot * (1 - hand) * lw[f] / ls * kw[k] / ks
                    if w > 1e-4:
                        VG[PFX + f"{side}Hand{f}{k}"].add([v.index], w, "REPLACE")
            moved += 1
    return moved


def head_only(D, body, PFX, look):
    ho = json.load(open(f"{D}/low_groups.json"))["head_only"]
    VG = body.vertex_groups; gh = VG[PFX + "Head"]; gj = VG.get(PFX + "Jaw"); n = 0; inside = set()
    for v in body.data.vertices:
        h = ho[look[v.index]]
        if h < 1e-3:
            continue
        if h > 0.5:
            inside.add(v.index)
        ws = {g.group: g.weight for g in v.groups}; tot = sum(ws.values()) or 1.0
        jw = ws.get(gj.index, 0.0) / tot if gj else 0.0
        for gi, w in ws.items():
            if gj and gi == gj.index:
                continue
            VG[gi].add([v.index], w / tot * (1 - h), "REPLACE")
        gh.add([v.index], (ws.get(gh.index, 0.0) / tot) * (1 - h) + h * (1 - jw), "REPLACE")
        if gj and jw > 0:
            gj.add([v.index], jw, "REPLACE")
        n += 1
    return n, inside


def shoulder_midline(body, JT, PFX):
    VG = body.vertex_groups; g2 = VG.get(PFX + "Spine2"); xs = abs(JT["shoulder"][0]); moved = 0
    for side, sg in (("Left", 1), ("Right", -1)):
        gs = VG.get(PFX + side + "Shoulder")
        if not gs or not g2:
            continue
        for v in body.data.vertices:
            w = next((g.weight for g in v.groups if g.group == gs.index), 0.0)
            if w <= 0:
                continue
            x = (body.matrix_world @ v.co).x * sg
            keep = min(1.0, max(0.0, (x - 0.15 * xs) / (0.45 * xs))); keep = keep * keep * (3 - 2 * keep)
            if keep < 1:
                gs.add([v.index], w * keep, "REPLACE"); g2.add([v.index], w * (1 - keep), "ADD"); moved += 1
    return moved


def neck_ramp(body, JT, PFX, skip=()):
    z0, z1 = JT["neck_ramp"]; VG = body.vertex_groups
    chain = [VG.get(PFX + n) for n in ("Spine2", "Neck", "Head")]
    if not all(chain):
        return 0
    ci = [g.index for g in chain]; n = 0
    for v in body.data.vertices:
        z = (body.matrix_world @ v.co).z
        if not (z0 < z < z1) or v.index in skip:
            continue
        T = sum(g.weight for g in v.groups if g.group in ci)
        if T < 1e-3:
            continue
        f = (z - z0) / (z1 - z0); f = f * f * (3 - 2 * f)
        for g, w in zip(chain, ((1 - f) ** 2, 2 * f * (1 - f), f * f)):
            g.add([v.index], T * w, "REPLACE")
        n += 1
    return n


def fill_empty(body):
    VG = body.vertex_groups
    wsum = {v.index: sum(g.weight for g in v.groups) for v in body.data.vertices}
    empty = [i for i, w in wsum.items() if w < 1e-3]
    if empty and len(empty) < len(wsum):
        kd = KDTree(len(wsum) - len(empty))
        for v in body.data.vertices:
            if wsum[v.index] >= 1e-3:
                kd.insert(v.co, v.index)
        kd.balance()
        for i in empty:
            src = body.data.vertices[kd.find(body.data.vertices[i].co)[1]]
            for g in src.groups:
                VG[g.group].add([i], g.weight, "REPLACE")
    return len(empty)


def normalise(body):
    short = 0
    for v in body.data.vertices:
        tot = sum(g.weight for g in v.groups)
        if 1e-3 < tot < 0.999:
            for g in v.groups:
                g.weight = g.weight / tot
            short += 1
    return short


def run(J, D, body, rig, BONES, PFX):
    """every pass in order; returns the numbers for rig.json"""
    JT = J["joints"]
    HELP = {j: {"Arm": "Shoulder", "ForeArm": "Arm", "UpLeg": None, "Leg": "UpLeg"}[j]
            for j in J.get("helpers", ["Arm", "ForeArm", "Leg"])}
    info = {"helpers": list(HELP)}
    if HELP:
        helpers(body, rig, BONES, HELP, PFX, J.get("helper_smooth", 6))
    G = json.load(open(f"{D}/low_groups.json")) if os.path.exists(f"{D}/low_groups.json") else {}
    look = low_lookup(D, body) if G else None
    info["jaw_verts"] = jaw(D, body, PFX, look, J.get("jaw_smooth", 4)) if "jaw" in JT and "jaw" in G else 0
    if JT.get("fingers"):
        info["finger_verts"] = fingers(body, JT, PFX)
    inside = set()
    if "head_only" in G:
        info["head_only_verts"], inside = head_only(D, body, PFX, look)
    info["shoulder_midline_verts"] = shoulder_midline(body, JT, PFX)
    if "neck_ramp" in JT:
        info["neck_ramp_verts"] = neck_ramp(body, JT, PFX, inside)
    info["empty_filled"] = fill_empty(body)
    info["normalised"] = normalise(body)
    return HELP, info
