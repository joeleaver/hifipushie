"""Build one continuous surface of a creature straight from what its pictures show, as a solid of two skins
(twoskin.py): the front picture's surface and the back picture's, joined at the outline.

A `group` is the masses that make ONE surface as the front and back pictures show it (a head with its eyes and
ears): no borders are cut between them, so none can tear. A mass that stands in front with air behind it (a can in
the mouth), or that runs away from the viewer (a horn curling back: neither picture shows its length), is left
out and built on its own; where it hides the group, the skin is carried through smoothly underneath.

DETAIL IS THE POINT. The solid's grid is fine (GRID, under half a millimetre), and each picture is read in
several close-ups, the tightest one that covers a place winning: the whole group, the group without its seated
parts (a face read with its ears in frame is read three times coarser), and each seated part. A read mutes small
relief: what is smaller than FINE is deepened by DETAIL.

Both skins are solved on the FRONT picture's grid (its outline is the solid's; the back picture's read is laid
onto it mirrored, world place for world place). Each is the read's slopes (surfaceread.py) added up over the
group's whole outline, AS READ: a read gets the shape of an eye or a muzzle about right and flattens the head as a
whole (measured on Scraps: one gain for everything stretched the head into an anteater's, holds pinned into the
solve folded the face). So the surface is kept, and a smooth BEND (the stiffest sheet that does it, bend()) carries
it to where the other pictures say it is:
  the outline       where it is an edge of the solid, both skins to ONE depth, the block-in clay's mid-depth there:
                    front and back meet in an edge, as a closed surface does where it turns away
  seated parts      (`seat`: ears, whatever stands off to one side) softly to the block-in clay's own surface: the
                    marks in the other views say where such a part sits in depth and how thick it is
  the middle line   to the profile the side view shows of the group's middle mass (`main`)
The block-in under the group is then taken out of the clay: it was scaffolding.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

from . import featuremap, featuresee, relief_press as rp, surfaceread, twoskin
from .spec import compile_prims

GRID = 0.00045     # m: the solid's grid (a reference picture rarely holds more; the reads are blown up to it)
MOST = 1500        # the grid's long side at most, in pixels (a wider group gets a coarser grid)
CLOSE = (1024, 6.0)   # a close-up's long side for the reader, and the most a view pixel is blown up
FEATHER = 0.008    # m: a tighter close-up takes over from a wider one across this much
FINE, DETAIL = 0.01, 1.7   # relief smaller than FINE (m) is deepened DETAIL times: a read mutes it
PIN_PER = 0.00127  # m: the pixel the pins' weights below were found at
PIN_OUTLINE, PIN_MIDDLE, PIN_SEAT = 1.0, 0.05, 0.02   # hold "pins": at the edge, along the middle band, at a seat
READ = 1.2         # the read's slopes are taken this much deeper as a whole (it mutes even local shape a little)
CELL = 0.003       # m: the bend is solved on cells this size (it has nothing finer in it)
OUTLINE_W, MIDDLE_W, SEAT_W = 30.0, 3.0, 0.05   # how hard the bend is held at the edge, the middle line, a seat
EDGE_IN = 0.008    # m: the read's normals are led over to "turned away" across this much, in from the solid's edge
EDGE_Z = 0.12      # what facing the viewer is left at the very edge (a slope of 8: the solver's limit)
MIDDLE = 0.006     # m: the middle line is a band this wide either side
THIN = 0.004       # m: the two skins are never closer than this inside the outline
SPECK = 0.0001     # m2: a loose piece of the outline smaller than this is dropped, a hole smaller is filled


def _stands_on(fm: dict, f: str, group) -> bool:
    seen = set()
    f = fm["features"][f].get("on")
    while f and f in fm["features"] and f not in seen:
        if f in group:
            return True
        seen.add(f)
        f = fm["features"][f].get("on")
    return False


def footprint(name: str, fm: dict, group, view: str):
    """(the group's whole outline in the view, what the view shows of it): view-pixel masks. The second leaves out
    every mass that stands on the group without being of it."""
    feats = fm["features"]
    marks = [featuremap.mask(name, g, view) for g in group if view in feats[g]["marks"]]
    if not marks:
        raise ValueError(f"none of {list(group)} is marked in {view!r}")
    foot = np.any(marks, 0)
    for f, c in feats.items():
        if c.get("kind") == "form" and view in c["marks"] and featuresee._mass_of(fm, f) in group:
            foot |= featuremap.mask(name, f, view)
    data = foot.copy()
    for f, c in feats.items():
        if c.get("kind") == "mass" and f not in group and view in c["marks"] and _stands_on(fm, f, group):
            data &= ~featuremap.mask(name, f, view)
    return foot, data


def _read(name: str, fm: dict, group, main: str, view: str, seat=()) -> dict:
    """A view's read of the group on that view's own fine grid: normals put together from its close-ups, masks, and
    the grid's place in the world."""
    rec = fm["views"][view]
    feats = fm["features"]
    foot_v, data_v = footprint(name, fm, group, view)
    ys, xs = np.where(foot_v)
    k = rec["m_per_px"]
    m = int(np.ceil(0.02 / k))
    Hv, Wv = foot_v.shape
    box = (max(0, xs.min() - m), max(0, ys.min() - m), min(Wv, xs.max() + 1 + m), min(Hv, ys.max() + 1 + m))
    G = min(k / GRID, MOST / max(box[2] - box[0], box[3] - box[1]))      # grid pixels per view pixel
    W, H = int(round((box[2] - box[0]) * G)), int(round((box[3] - box[1]) * G))
    px = k / G

    def grid(a, soft=True):
        a = np.asarray(Image.fromarray(a[box[1]:box[3], box[0]:box[2]].astype(np.uint8) * 255).resize((W, H), Image.NEAREST)) > 127
        return ndimage.gaussian_filter(a.astype(float), 0.6 * G) > 0.5 if soft else a

    full = grid(foot_v)
    lab, nl = ndimage.label(full)                       # no specks, no pinholes: a mark's stray pixels
    if nl > 1:
        sizes = ndimage.sum(full, lab, range(1, nl + 1)) * px * px
        full = np.isin(lab, 1 + np.flatnonzero((sizes >= SPECK) | (sizes == sizes.max())))
    holes, nh = ndimage.label(~full)
    if nh > 1:
        sizes = ndimage.sum(~full, holes, range(1, nh + 1)) * px * px
        full |= np.isin(holes, 1 + np.flatnonzero(sizes < SPECK))
    # the close-ups: the whole group, the group without its seated parts, each seated part
    seats = [f for f in seat if f in feats and view in feats[f]["marks"]]
    regions = [foot_v]
    if seats:
        core = [g for g in group if g not in seats]
        if any(view in feats[g]["marks"] for g in core):
            regions.append(footprint(name, fm, core, view)[0])
        regions += [featuremap.mask(name, f, view) for f in seats]
    shots = [rp.closeup(rec, r, CLOSE) for r in regions]
    reads = surfaceread.normals([s[0] for s in shots])
    gy, gx = np.mgrid[0:H, 0:W].astype(np.float64)
    vx, vy = box[0] + (gx + 0.5) / G, box[1] + (gy + 0.5) / G          # the grid's pixels in view pixels
    nm = np.zeros((H, W, 3))
    zooms = []
    for i, ((img, cbox, cz), n, reg) in enumerate(zip(shots, reads, regions)):
        at = [(vy - cbox[1]) * cz - 0.5, (vx - cbox[0]) * cz - 0.5]
        s = np.stack([ndimage.map_coordinates(n[..., j], at, order=1, mode="nearest") for j in range(3)], -1)
        if i == 0:
            nm = s
        else:                                           # a tighter close-up takes over inside its own region
            inside = ndimage.distance_transform_edt(grid(reg)) * px
            wgt = rp._smooth(inside / FEATHER)[..., None]
            nm = nm * (1 - wgt) + s * wgt
        zooms.append(round(float(cz), 2))
    nm /= np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-6)
    into = np.zeros(full.shape, bool)                   # what the group stands on: there the surface runs on
    up, seen_up = feats[main].get("on"), set()
    while up and up in feats and up not in seen_up:
        if view in feats[up]["marks"]:
            into |= grid(featuremap.mask(name, up, view), soft=False)
        seen_up.add(up)
        up = feats[up].get("on")
    seat_m = np.zeros(full.shape, bool)
    for f in seats:
        seat_m |= grid(featuremap.mask(name, f, view))
    za, zb = rp._zfit(name, fm, main, view)
    F, U = (np.array(v) for v in rp.FRAMES[rec["kind"]])
    return {"normals": nm.astype(np.float32), "full": full, "seen": grid(data_v) & full, "seats": seat_m & full,
            "into": into & ~full, "px": px, "za": za, "z0": za * (rec["ground_px"] - box[1]) * k + zb,
            "u0": (box[0] - rec["centre_px"]) * k, "U": U, "F": F, "rec": rec, "box": box, "G": G, "zooms": zooms}


def _onto(b: dict, f: dict) -> dict:
    """The back view's read laid onto the front's grid, mirrored: the same place in the world, pixel for pixel."""
    H, W = f["full"].shape
    zf = f["z0"] - (np.arange(H) + 0.5) * f["px"] * f["za"]
    xf = f["u0"] + (np.arange(W) + 0.5) * f["px"]                          # world x (the front's U is +x)
    rb = (b["z0"] - zf) / (b["px"] * b["za"]) - 0.5
    cb = (-xf - b["u0"]) / b["px"] - 0.5                                    # the back's U runs along -x
    at = np.meshgrid(rb, cb, indexing="ij")
    ok = (at[0] >= 0) & (at[0] <= b["full"].shape[0] - 1) & (at[1] >= 0) & (at[1] <= b["full"].shape[1] - 1)
    nm = np.stack([ndimage.map_coordinates(b["normals"][..., i], at, order=1, mode="nearest") for i in range(3)], -1)
    nm[..., 0] *= -1.0                                                      # its right is the front's left
    nm /= np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-6)
    pick = lambda m: (ndimage.map_coordinates(m.astype(np.float32), at, order=0, mode="constant") > 0.5) & ok
    return {"normals": nm, "seen": pick(b["seen"]) & f["full"], "seats": pick(b["seats"]) & f["full"]}


def bend(full: np.ndarray, px: float, holds, holds2=None, meet=None, stiff: float = 1.0, cell: float = CELL):
    """The smoothest field over `full` (least bending: a stiff sheet) that takes the values asked for:
    holds = [(mask, values, weight)]. Added to a read surface, it moves the surface to where it is known to be
    without touching anything smaller than a few cells. With `holds2`, TWO fields are found together (a front and
    a back skin's), and `meet` = (mask, values, weight) asks that their SUM take the values there (the two skins
    meeting at the solid's edge, wherever that edge lies in depth). Solved on cells of `cell` metres, then eased
    back up. Returns the field, or the two."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    st = max(1, int(round(cell / px)))
    H, W = full.shape
    Hc, Wc = -(-H // st), -(-W // st)

    def pool(a):
        pad = np.zeros((Hc * st, Wc * st))
        pad[:H, :W] = a
        return pad.reshape(Hc, st, Wc, st).sum((1, 3))

    m = pool(full.astype(float)) > 0
    idx = -np.ones((Hc, Wc), int)
    n = int(m.sum())
    idx[m] = np.arange(n)
    rows, cols, vals = [], [], []
    for dy, dx in ((0, 1), (1, 0)):                      # each pair of neighbours, both ways
        a_, b_ = idx[: Hc - dy, : Wc - dx], idx[dy:, dx:]
        ok = (a_ >= 0) & (b_ >= 0)
        i, j = a_[ok], b_[ok]
        rows += [i, i, j, j]
        cols += [j, i, i, j]
        vals += [np.ones(len(i)), -np.ones(len(i)), np.ones(len(i)), -np.ones(len(i))]
    lap = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    stiffness = stiff * (lap.T @ lap) + 1e-9 * sp.identity(n)

    def held(hs):
        wd, rhs = np.zeros(n), np.zeros(n)
        for mask, values, weight in hs:
            cnt, sm = pool(mask.astype(float)), pool(np.where(mask, values, 0.0))
            sel = (cnt > 0) & m
            wd[idx[sel]] += weight * cnt[sel] / (st * st)
            rhs[idx[sel]] += weight * sm[sel] / (st * st)
        return wd, rhs

    def fine(sol):
        grid = np.full((Hc, Wc), np.nan)
        grid[m] = sol
        yy, xx = np.mgrid[0:H, 0:W]
        return ndimage.map_coordinates(rp._fill(grid), [(yy + 0.5) / st - 0.5, (xx + 0.5) / st - 0.5], order=3, mode="nearest")

    w1, r1 = held(holds)
    if holds2 is None:
        return fine(spl.spsolve((sp.diags(w1) + stiffness).tocsc(), r1)) if w1.any() else np.zeros(full.shape)
    w2, r2 = held(holds2)
    wm, rm = held([meet]) if meet is not None else (np.zeros(n), np.zeros(n))
    A = sp.bmat([[sp.diags(w1 + wm) + stiffness, sp.diags(wm)], [sp.diags(wm), sp.diags(w2 + wm) + stiffness]]).tocsc()
    sol = spl.spsolve(A, np.r_[r1 + rm, r2 + rm])
    return fine(sol[:n]), fine(sol[n:])


def turned_away(nm: np.ndarray, full: np.ndarray, closed: np.ndarray, px: float) -> np.ndarray:
    """At the solid's edge the surface is seen edge-on, facing straight out of the outline: that is known exactly,
    and a read under-does it (it leans every surface towards the viewer). Over the last EDGE_IN metres inside the
    edge (`closed`: where the outline is an edge of the solid) the read's normals are led over to it."""
    d = ndimage.distance_transform_edt(full) * px
    gy, gx = np.gradient(ndimage.gaussian_filter(d, 2.0))
    out = np.stack([-gx, gy, np.full(d.shape, 0.0)], -1)            # x right, y up (rows run down), no z at all
    out /= np.maximum(np.linalg.norm(out, axis=-1, keepdims=True), 1e-6)
    out[..., 2] = EDGE_Z
    near = ndimage.distance_transform_edt(~closed) * px              # how far from the nearest closed edge pixel
    w = (rp._smooth(1.0 - np.maximum(d, near) / EDGE_IN) ** 1.5)[..., None]
    n = nm * (1 - w) + out * w
    return (n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)).astype(np.float32)


def _middle(T0, zrow, prof, rec_other: dict, c0: float, px: float, full: np.ndarray):
    """The hold along the middle line: per height the side outline really covers, how far the surface's forward-
    most point in the middle band is from the profile. (mask, values the bend must take there)."""
    mask, val = np.zeros(full.shape, bool), np.zeros(full.shape)
    if prof is None:
        return mask, val
    seen = np.abs(zrow[:, None] - prof[0][None, :]).min(1) < 1.5 * rec_other["m_per_px"]
    e_t = ndimage.gaussian_filter1d(np.interp(zrow, prof[0], prof[1]), max(1.0, 0.004 / px), mode="nearest")
    half = max(1, round(MIDDLE / px))
    cols = np.arange(int(round(c0)) - half, int(round(c0)) + half + 1)
    cols = cols[(cols >= 0) & (cols < full.shape[1])]
    for v in np.flatnonzero(seen):
        if full[v, cols].mean() > 0.9:
            mask[v, cols] = True
            val[v, cols] = e_t[v] - T0[v, cols].max()
    return mask, val


def deepen(T: np.ndarray, full: np.ndarray, px: float, fine: float = FINE, detail: float = DETAIL) -> np.ndarray:
    """Relief smaller than `fine` made `detail` times as deep (a read mutes small relief)."""
    s = fine / px
    low = ndimage.gaussian_filter(np.where(full, T, 0.0), s) / np.maximum(ndimage.gaussian_filter(full.astype(float), s), 1e-3)
    return np.where(full, low + detail * (T - low), T)


def build(name: str, spec: dict, fm: dict, group, main: str | None = None, seat=(), front: str | None = None,
          back: str | None = None, detail: float = DETAIL, hold: str = "pins") -> tuple[dict, dict]:
    """The spec with the group built as one two-skin solid in place of its block-in clay, and what was done."""
    group = list(group)
    main = main or group[0]
    views = {r.get("kind"): v for v, r in fm["views"].items()}
    front, back = front or views.get("front"), back or views.get("back")
    if not front or not back:
        raise ValueError("a two-skin solid needs a front and a back view of the reference")
    f = _read(name, fm, group, main, front, seat)
    braw = _read(name, fm, group, main, back, seat)
    b = _onto(braw, f)
    full, px, za = f["full"], f["px"], f["za"]
    H, W = full.shape
    Ff, U, V = f["F"], f["U"], np.array([0.0, 0.0, -1.0])
    o = U * f["u0"] + np.array([0.0, 0.0, f["z0"]])
    zrow = f["z0"] - (np.arange(H) + 0.5) * px * za
    # the block-in clay along the grid's rays, from the front and from the back: where each part sits in depth
    prims = compile_prims(spec)
    adds = [p for p in prims if p.op == "add"]
    ys = sorted(float(c @ Ff) for c in (np.min([p.lo for p in adds], 0), np.max([p.hi for p in adds], 0)))
    st = max(1, int(round(0.0025 / px)))
    rr, cc = np.mgrid[0:H:st, 0:W:st]
    P0 = o[None] + (cc.reshape(-1, 1) + 0.5) * px * U[None] + (rr.reshape(-1, 1) + 0.5) * px * za * V[None]
    zf = (H / rr.shape[0], W / rr.shape[1])

    def up(a):
        return ndimage.zoom(rp._fill(a.reshape(rr.shape)), zf, order=1, mode="nearest")[:H, :W]

    near_f, far_f = rp._hits(prims, P0, Ff, ys[1] + 0.02, ys[0] - 0.02)     # heights t towards the front viewer
    near_b, _ = rp._hits(prims, P0, -Ff, -ys[0] + 0.02, -ys[1] - 0.02)      # heights -t towards the back viewer
    hit = ndimage.zoom((~np.isnan(near_f)).reshape(rr.shape).astype(np.float32), zf, order=1, mode="nearest")[:H, :W] > 0.5
    Bf, Bb, mid = up(near_f), up(near_b), 0.5 * (up(near_f) + up(far_f))
    # Where the group's outline is an edge of the solid (the figure's own outline, or a part standing on the group
    # hides it: the surface still ends there), both skins are held to ONE depth: the clay's mid-depth, carried
    # along the outline where no clay stood and eased along it. Where the group runs on into what it stands on
    # (a head into its neck), the outline is left open.
    rim = full & (ndimage.distance_transform_edt(full) * px < rp.RIM) \
        & ~ndimage.binary_dilation(f["into"], iterations=max(2, round(2 * rp.RIM / px)))
    edge = np.where(rim & hit, mid, np.nan)
    if np.isfinite(edge).any():
        i = ndimage.distance_transform_edt(~np.isfinite(edge), return_distances=False, return_indices=True)
        edge = np.where(rim, edge[tuple(i)], 0.0)
        sg = 0.012 / px
        edge = ndimage.gaussian_filter(edge, sg) / np.maximum(ndimage.gaussian_filter(rim.astype(float), sg), 1e-6)
        edge = np.where(rim, edge, np.nan)
    c0 = (f["rec"]["centre_px"] - f["box"][0]) * f["G"] - 0.5
    sides = (("front", f["normals"], f["seen"], f["seats"], Bf, front), ("back", b["normals"], b["seen"], b["seats"], Bb, back))
    T0, holds, abouts, out = {}, {}, {}, {}
    per = (px / PIN_PER) ** 2          # a pin's weight is per pixel: the same hold on a finer grid is that much less
    for key, nm, seen, seats, B, view in sides if hold == "pins" else ():
        # the holds inside the solve, as soft pins, with one depth gain for the read (the arrangement that has held
        # together best so far; its faults: a slight ridge along the middle line, and local shape scaled by the gain)
        sign = 1.0 if key == "front" else -1.0
        pin, pw = np.full(full.shape, np.nan), np.zeros(full.shape)
        prof = rp.profile(name, fm, main, view)
        mid_m, mid_v = _middle(np.zeros(full.shape), zrow, prof, fm["views"][prof[2]] if prof else {}, c0, px, full)
        pin[mid_m], pw[mid_m] = mid_v[mid_m], PIN_MIDDLE * per
        m = seats & seen & hit & ~rim
        pin[m], pw[m] = B[m], PIN_SEAT * per
        pin[rim], pw[rim] = sign * edge[rim], PIN_OUTLINE * per
        pw[~np.isfinite(pin)] = 0.0
        T, gain = surfaceread.height(nm, full, px, pin=pin, pin_w=pw, data=seen, gain=rp.GAIN)
        out[key] = rp._fill(np.where(full, deepen(T.astype(np.float64), full, px, detail=detail), np.nan))
        abouts[key] = {"view": view, "gain": round(float(gain), 2), "profile_rows": int(mid_m.any(1).sum()),
                       "seated": int(m.sum()), "hidden": round(float((full & ~seen).sum() / max(full.sum(), 1)), 2)}
    for key, nm, seen, seats, B, view in sides if hold == "bend" else ():
        nm = turned_away(nm, full, rim, px)
        T0[key] = READ * surfaceread.height(nm, full, px, steep=EDGE_Z, data=seen).astype(np.float64)
        prof = rp.profile(name, fm, main, view)
        mid_m, mid_v = _middle(T0[key], zrow, prof, fm["views"][prof[2]] if prof else {}, c0, px, full)
        m = seats & seen & hit & ~rim
        holds[key] = [(mid_m, mid_v, MIDDLE_W), (m, B - T0[key], SEAT_W)]
        abouts[key] = {"view": view, "profile_rows": int(mid_m.any(1).sum()), "seated": int(m.sum()),
                       "hidden": round(float((full & ~seen).sum() / max(full.sum(), 1)), 2)}
    # the two skins meet at the solid's edge, wherever in depth that makes the least bending; if nothing else places
    # them (no profile to go by), the edge is held to the clay's mid-depth as well
    if hold == "bend":
        meet = (rim, -(T0["front"] + T0["back"]), OUTLINE_W)
        if not (abouts["front"]["profile_rows"] or abouts["back"]["profile_rows"]):
            holds["front"].append((rim, edge - T0["front"], 0.3))
        Lf, Lb = bend(full, px, holds["front"], holds["back"], meet)
        for key, L in (("front", Lf), ("back", Lb)):
            out[key] = rp._fill(np.where(full, deepen(T0[key] + L, full, px, detail=detail), np.nan))
            abouts[key]["bent_mm"] = [round(float(np.percentile((L - np.median(L[full]))[full], q)) * 1e3, 1) for q in (2, 98)]
    abouts["edge_gap_mm"] = round(float(np.abs((out["front"] + out["back"])[rim]).mean()) * 1e3, 1)
    abouts["front"]["close_ups"], abouts["back"]["close_ups"] = f["zooms"], braw["zooms"]
    Tf, Tb = out["front"], out["back"]
    inner = ndimage.distance_transform_edt(full) * px
    short = np.clip(np.minimum(THIN, inner) - (Tf + Tb), 0, None) / 2       # the skins may not cross inside
    Tf, Tb = Tf + short, Tb + short

    def cos(t):
        gy, gx = np.gradient(t, px * za, px)
        return np.clip(1.0 / np.sqrt(1.0 + gx ** 2 + gy ** 2), 0.25, 1.0)

    foot = (ndimage.distance_transform_edt(~full) - ndimage.distance_transform_edt(full)) * px
    # map pixel (c, r) sits at o + (c + 0.5, r + 0.5): the frame's origin is half a pixel back
    o_map = o + 0.5 * px * U + 0.5 * px * za * V
    sha = twoskin.put({"o": o_map, "U": U, "V": V / za, "F": Ff, "px": px},
                      {"front": Tf, "back": Tb, "foot": foot, "cf": cos(Tf), "cb": cos(Tb)})
    # the block-in under the group was scaffolding: out of the clay (its joints stay: other parts hang on them)
    gone = {e for g in group for e in (fm["features"][g].get("built") or [])}
    gone |= {featuremap.twin(e) for e in list(gone) if featuremap.twin(e)}
    new = {**spec, "bones": {k: v for k, v in spec.get("bones", {}).items() if k not in gone},
           "blobs": {k: v for k, v in spec.get("blobs", {}).items() if k not in gone}}
    bname = f"{main}_skins"
    new["blobs"][bname] = {"shape": "twoskin", "skins": sha}
    thick = (Tf + Tb)[full]
    about = {"blob": bname, "skins": sha, "group": group, "map": [int(W), int(H)], "px_mm": round(px * 1e3, 2),
             "front": abouts["front"], "back": abouts["back"], "edge_gap_mm": abouts["edge_gap_mm"],
             "thick_mm": [round(float(np.percentile(thick, q)) * 1e3, 1) for q in (2, 50, 98)],
             "taken_out": sorted(e for e in gone if e in spec.get("bones", {}) or e in spec.get("blobs", {}))}
    return new, {"about": about, "front": {"normals": f["normals"], "full": full, "T": Tf},
                 "back": {"normals": b["normals"], "full": full, "T": Tb}}
