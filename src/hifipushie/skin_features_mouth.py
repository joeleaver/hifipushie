"""The mouth: inner lip values, the interior's values, GNM's own mouth. Part of the skin features (skin_features.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_features

def inner_lip_values(head) -> np.ndarray | None:
    """Per GNM vertex, how much of the wet inner lip (mucosa) colour it takes: GNM's skin rings from the open mouth
    loop (where the sock joins) to the contact ring (base.LIP_RING) 1, the next ring INNER_LIP_FADE, else 0. With the
    lips closed the scene's surface has no rolls, so the bake filled them from the skin beside them and every shape
    that parts the lips (jawOpen, smiles) showed a ragged brown fringe round the opening (review expr_r1). The export
    paints these values onto the low poly's own triangles (asset_bake.bake, "inner_paint")."""
    import collections
    from . import base as _base
    from . import base_gnm_parts, base_identity
    if head is None or head.get("gnm_world") is None:
        return None
    g = base_identity._gnm_data()
    mp = base_gnm_parts.gnm_mouth(head)
    n = len(np.asarray(head["gnm_world"]))
    skin = np.asarray(g["skin"], bool)
    sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
    Q = np.asarray(g["quads"])
    Q = Q[skin[Q].all(1)]
    adj = collections.defaultdict(set)
    for q in Q:
        for k in range(4):
            a, b = int(q[k]), int(q[(k + 1) % 4])
            adj[a].add(b), adj[b].add(a)
    own = sock[mp["sock"]["ids"]]
    rim = [int(v) for v in mp["sock"]["ids"][~own]]
    if not rim:
        return None
    lev = {v: 0 for v in rim}
    front = list(rim)
    ring = _base.LIP_RING
    while front and min(lev[v] for v in front) <= ring:
        nxt = []
        for v in front:
            for u in adj[v]:
                if u not in lev and not sock[u]:
                    lev[u] = lev[v] + 1
                    nxt.append(u)
        front = nxt
    val = np.zeros(n)
    for v, lv in lev.items():
        # (v25 faded the contact ring itself, nothing past it, against "a jagged pink band with a notch" (expr_r8..r10):
        # the notch was the upper roll folded forward through the seam (faceshapes._rolls_behind), and without the
        # wet colour on the contact ring the closed seam showed the projected skin's dark lip line as a jagged
        # dark gap (expr_r11 / r12): back to the ring at 1, the next at INNER_LIP_FADE)
        val[v] = 1.0 if lv <= ring else skin_features.INNER_LIP_FADE if lv == ring + 1 else 0.0
    return val


def mouth_interior_values(head) -> np.ndarray | None:
    """Per GNM vertex 0..1: how deep in the mouth's sock it is (0 off the sock, rising ring by ring from the rim to 1 at
    MOUTH_DEEP_RINGS). The sock is in the low poly but hidden in the closed scene, so the bake painted it grey: grey
    shards inside every parted mouth and a grey dot at the upper lip's centre in the neutral (review expr_r2)."""
    import collections
    from . import base_gnm_parts, base_identity
    if head is None or head.get("gnm_world") is None:
        return None
    g = base_identity._gnm_data()
    mp = base_gnm_parts.gnm_mouth(head)
    n = len(np.asarray(head["gnm_world"]))
    sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
    Q = np.asarray(g["quads"])
    adj = collections.defaultdict(set)
    for q in Q:
        for k in range(4):
            a, b = int(q[k]), int(q[(k + 1) % 4])
            adj[a].add(b), adj[b].add(a)
    own = sock[mp["sock"]["ids"]]
    rim = [int(v) for v in mp["sock"]["ids"][~own]]
    if not rim:
        return None
    lev = {v: 0 for v in rim}
    front = list(rim)
    while front:
        nxt = []
        for v in front:
            for u in adj[v]:
                if u not in lev and u < len(sock) and sock[u]:
                    lev[u] = lev[v] + 1
                    nxt.append(u)
        front = nxt
    val = np.zeros(n)
    for v, lv in lev.items():
        if v < len(sock) and sock[v]:
            val[v] = min(1.0, lv / skin_features.MOUTH_DEEP_RINGS)
    val[:len(sock)][sock & (val[:len(sock)] == 0)] = 1.0  # sock vertices out of reach of the rim: deep
    # and by depth behind the lips' front: the corners' walls are near the rim in rings but 5-10 mm in, beside the
    # teeth; lit pink they read as torn lining in every jawOpen (expr_r7..r9). A cavity in shadow is dark.
    ml = base_gnm_parts.mouth_lips(head)
    W = np.asarray(head["gnm_world"], float)
    lm = np.asarray(head["lm68"], float)
    front = float(np.max((lm[[48, 54, 51, 57]] - ml["M"]) @ ml["out"]))
    depth = front - (W - ml["M"]) @ np.asarray(ml["out"], float)
    by_depth = np.clip((depth - skin_features.MOUTH_DARK_DEPTH[0]) / (skin_features.MOUTH_DARK_DEPTH[1] - skin_features.MOUTH_DARK_DEPTH[0]), 0, 1)
    if skin_features.MOUTH_DARK_SIDE:  # (r32) the side walls past the dental arch, a little in: the cheeks' inner walls in shadow
        # (jaw: lit pink walls beside the tongue with a black edge-on line between, "black vertical side lines")
        a, b, d0, d1 = skin_features.MOUTH_DARK_SIDE
        u = np.abs((W - ml["M"]) @ np.asarray(ml["side"], float)) / max(0.5 * ml["width"], 1e-6)
        by_depth = np.maximum(by_depth, np.clip((u - a) / (b - a), 0, 1) * np.clip((depth - d0) / (d1 - d0), 0, 1))
    on = np.zeros(n, bool)
    on[:len(sock)] = sock
    val[on] = np.maximum(val[on], by_depth[on])
    return val


def _gnm_mouth(spec, out, part) -> None:
    """GNM's OWN MOUTH, dressed (minimal, 2026-10-12; Joe: "we'll figure out the dressing as we go along"): the mouth
    bag dark wet red on the skin's part, the gums on the teeth's part. Both masks are point clouds made from GNM's own
    vertices (its `mouth_sock` and `gums` groups, as the head places them), read like a hand-painted mask
    (paint_masks.painted_values): the gum line is GNM's scalloped one, not a height. Teeth and tongue keep their parts'
    flat colours (base_gnm_parts.MOUTH_PARTS): no enamel translucency, no tongue texture, no wet film yet."""
    from . import base_gnm_parts, base_identity, base_imls, base_measures
    from . import base
    from . import paint_masks
    from . import spec as _specmod
    b = spec.get("base") or {}
    if base_gnm_parts.mouth_mode(b) != "gnm":
        return
    head = base_measures.head_of({"joints": _specmod.expand_mirror(spec)["joints"]}, b)
    if head is None or base_gnm_parts.mouth_mode(b, head) != "gnm":
        return
    mp = base_gnm_parts.gnm_mouth(head)
    g = base_identity._gnm_data()
    sk = mp["sock"].get("points") or base_gnm_parts._piece_points(mp["sock"]["verts"], mp["sock"]["faces"], rounds=1)
    # (the joining quads' lip-loop vertices are skin: the bag's colour starts a ring behind them)
    own = np.asarray(g["groups"]["mouth_sock"])[mp["sock"]["ids"]] > 0.5
    from scipy.spatial import cKDTree
    d_own = cKDTree(mp["sock"]["verts"][own]).query(sk["verts"])[0]
    d_rim = cKDTree(mp["sock"]["verts"][~own]).query(sk["verts"])[0] if (~own).any() else np.full(len(sk["verts"]), 1.0)
    # (the cloud's own spacing, and only points clearly inside the sock: at a 3 mm spacing the mask reached ~6 mm and
    # printed the bag's near-black red onto the outer skin at the mouth corners: two black "curls" on every GNM head)
    sp_ = float(np.median(cKDTree(sk["verts"]).query(sk["verts"], k=2)[0][:, 1]))
    pid = paint_masks.save_painted(sk["verts"], sk["normals"], (d_own < d_rim - 0.0008).astype(float), float(np.clip(sp_, 0.0005, 0.0015)))
    # (the inner rolls are NOT a scene layer: with the lips closed the scene's surface has no rolls (the fill behind the
    # seam), so a painted cloud there found the outer lips instead (v8: lipstick red). The export paints them on the
    # low poly's own triangles by GNM index: asset_bake.bake's "inner_paint", values from inner_lip_values)
    out["skin:mouth_bag"] = {"part": part, "color": list(base.BAG_COLOR), "roughness": 0.4, "specular": 0.5,
                             "mask": [{"painted": pid}]}
    for k, tpart in (("teeth_upper", base.TEETH_PARTS[0]), ("teeth_lower", base.TEETH_PARTS[1])):
        V, F = mp[k]["verts"], [list(map(int, f)) for f in mp[k]["faces"]]
        gum = mp[k]["gum"].astype(float)[:, None].repeat(3, 1)
        for _ in range(base.MOUTH_SUBDIVIDE):
            V2, F2 = base_imls._catmull_clark(V, F)
            gum = base_imls._catmull_clark(gum, F)[0]  # (the group's weight subdivided like the positions)
            V, F = V2, F2
        N, h = base_imls._normals_and_h(V, F)
        pid = paint_masks.save_painted(V, N, np.clip((gum[:, 0] - 0.35) / 0.3, 0, 1), 0.0012)
        out["skin:gums" + ("" if tpart == "teeth" else "_lower")] = {
            "part": tpart, "color": list(base.GUM_COLOR), "roughness": 0.4, "specular": 0.5, "mask": [{"painted": pid}]}
    if skin_features.TEETH_BACK:
        out_ = np.asarray(mp["frame"][1], float)
        for k, tpart in (("teeth_upper", base.TEETH_PARTS[0]), ("teeth_lower", base.TEETH_PARTS[1])):
            V, F = mp[k]["verts"], [list(map(int, f)) for f in mp[k]["faces"]]
            for _ in range(base.MOUTH_SUBDIVIDE):
                V, F = base_imls._catmull_clark(V, F)
            N, _h = base_imls._normals_and_h(V, F)
            dep = float((V @ out_).max()) - V @ out_
            u = np.clip((dep - skin_features.TEETH_BACK[0]) / (skin_features.TEETH_BACK[1] - skin_features.TEETH_BACK[0]), 0, 1)
            pid = paint_masks.save_painted(V, N, skin_features.TEETH_BACK[2] * u * u * (3 - 2 * u), 0.0012)
            out["skin:teeth_back" + ("" if tpart == "teeth" else "_lower")] = {
                "part": tpart, "color": list(skin_features.TEETH_BACK[3]), "roughness": 0.4, "specular": 0.5, "mask": [{"painted": pid}]}
    if skin_features.TONGUE_BACK and "tongue" in mp and len(mp["tongue"]["verts"]):
        # the tongue's back darkened into the throat (expr_r15: the flat-coloured dorsum read as "a flat red back wall"
        # in jawOpen; a real tongue's back falls into the mouth's shadow): by depth behind its tip, along the mouth's `out`
        V, F = mp["tongue"]["verts"], [list(map(int, f)) for f in mp["tongue"]["faces"]]
        for _ in range(base.MOUTH_SUBDIVIDE):
            V, F = base_imls._catmull_clark(V, F)
        N, _h = base_imls._normals_and_h(V, F)
        out_ = np.asarray(mp["frame"][1], float)
        dep = float((V @ out_).max()) - V @ out_
        u = np.clip((dep - skin_features.TONGUE_BACK[0]) / (skin_features.TONGUE_BACK[1] - skin_features.TONGUE_BACK[0]), 0, 1)
        pid = paint_masks.save_painted(V, N, u * u * (3 - 2 * u), 0.0012)
        out["skin:tongue_back"] = {"part": "tongue", "color": list(skin_features.MOUTH_DEEP_COLOR), "roughness": 0.45,
                                   "specular": 0.5, "mask": [{"painted": pid}]}
