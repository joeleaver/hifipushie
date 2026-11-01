"""hsrd_export.py <pose>: one HSRD-100 pose reduced to what the REAL-PHOTO SET keeps (docs/notes/groundtruth.md "## The
HSRD-100 real-photo set"), from the working copy (prep.py, align0.py, register.py, check_cams.py, fit3d.py p1b3 +
p1eb3 run before) and the unpacked download:
  $HIFIPUSHIE_GROUNDTRUTH/hsrd100/<subject>/<pose>/
    photos/<cam>.jpg        every rig photo that holds the WHOLE head, cut to a head-and-shoulders box at the photo's
                            own resolution (no resampling; JPEG quality 95, 4:4:4: one re-encode of the rig's JPEG)
    masks/<cam>.png         the dataset's foreground mask, the same cut
    cameras.json            per photo: the cut's box in the original, K for the CUT (f px, cx, cy), brown3 k1..k3,
                            R (rig world -> camera, x right / y down / z forward), C (camera centre, rig metres); where
                            the camera stands round the head (az + = the subject's left, el, distance), px / mm at the
                            head; + T_scan_to_rig (register.py, its silhouette rms) and the head's frame in the rig
    scan_head.npz           the LOD0 scan's top 0.42 m (head, neck, shoulders): V (scan frame, m), F, C (vertex
                            colours), FUV (per-corner uv into scan_head_texture.png), skin (per vertex: not hair / cloth)
    scan_head_texture.png   the 16k texture cut to the head's texels (the used region's bounding box; the rest black)
    scan_head_dec.npz       a decimated copy (vertex clustering at 2.5 mm): V, F, C
    fit.json                the Part 1 direct GNM fits: identity (p1b3) and identity + expression (p1eb3): c, e, S
                            (scan -> GNM world), region tables, "flag" when the face mean is over 1 mm
    labels.npz              per photo the projected landmark sets with TRUE visibility and a label quality (below)
labels.npz: sets "dl3" (denselm's v3 set: 756 GNM vertices), "lm68" (the 68 standard), "mp" (readmix's MediaPipe ->
GNM surface points, 468). Per set: <set>_xy (photos, n, 2) pixels IN THE CUT (through the distortion), <set>_vis
(photos, n) bool = the point is the first surface along its ray against the WHOLE scan (hair, clothes, hands as
occluders; 4 mm tolerance) and inside the cut, <set>_q (n,) mm = the fit's distance to the scan's surface at that
point (a label is only as good as the fit there; nan = no skin there: hair / cloth over it, eyeball, teeth, tongue),
<set>_form (n,) bool = a vermilion-border label: the geometry knows the lip's FORM, not its colour edge; <set>_X (n, 3)
the points in the rig's frame. The 3D points are the identity + expression fit's (the face as the scan has it)."""
import json
import sys
import numpy as np
from PIL import Image
import gt, hsrd, rast, fit3d

Image.MAX_IMAGE_PIXELS = None
SET = gt.ROOT / "hsrd100"


def decimate(V, F, C, cell=0.0025):
    q = np.floor(V / cell).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    inv = inv.ravel()
    n = inv.max() + 1
    cnt = np.bincount(inv, minlength=n).astype(float)
    Vd = np.stack([np.bincount(inv, V[:, k], n) / cnt for k in range(3)], 1)
    Cd = np.stack([np.bincount(inv, C[:, k], n) / cnt for k in range(3)], 1) if C is not None else None
    f = inv[F]
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    f = np.unique(np.sort(f, 1), axis=0, return_index=True)[1]
    Fd = inv[F][(inv[F][:, 0] != inv[F][:, 1]) & (inv[F][:, 1] != inv[F][:, 2]) & (inv[F][:, 0] != inv[F][:, 2])][f]
    return Vd.astype(np.float32), Fd.astype(np.int32), None if Cd is None else Cd.astype(np.float32)


def texture_cut(tex_path, FUV, out_path):
    """The texels the head's triangles use (+ a margin), the rest black, cut to their bounding box; uv re-based."""
    from scipy import ndimage
    tex = np.asarray(Image.open(tex_path).convert("RGB"))
    H, W = tex.shape[:2]
    u = FUV[..., 0] % 1.0 * W
    v = (1.0 - FUV[..., 1] % 1.0) * H
    # a coarse occupancy mask (8 px cells) of the triangles' boxes: cheap, generous
    cs = 8
    m = np.zeros((H // cs + 1, W // cs + 1), bool)
    x0, x1 = np.floor(u.min(1) / cs).astype(int), np.floor(u.max(1) / cs).astype(int)
    y0, y1 = np.floor(v.min(1) / cs).astype(int), np.floor(v.max(1) / cs).astype(int)
    small = (x1 - x0 <= 6) & (y1 - y0 <= 6)
    for dx in range(7):
        for dy in range(7):
            ok = small & (x0 + dx <= x1) & (y0 + dy <= y1)
            m[np.clip(y0[ok] + dy, 0, m.shape[0] - 1), np.clip(x0[ok] + dx, 0, m.shape[1] - 1)] = True
    for i in np.flatnonzero(~small):
        m[max(y0[i], 0):y1[i] + 1, max(x0[i], 0):x1[i] + 1] = True
    m = ndimage.binary_dilation(m, iterations=1)
    ys, xs = np.nonzero(m)
    bx0, bx1, by0, by1 = xs.min() * cs, min((xs.max() + 1) * cs, W), ys.min() * cs, min((ys.max() + 1) * cs, H)
    big = np.kron(m[by0 // cs:(by1 + cs - 1) // cs, bx0 // cs:(bx1 + cs - 1) // cs], np.ones((cs, cs), bool))[:by1 - by0, :bx1 - bx0]
    cut = tex[by0:by1, bx0:bx1] * big[..., None]
    Image.fromarray(cut).save(out_path, optimize=False, compress_level=6)
    # uv into the cut (v up, as OBJ)
    nu = (u - bx0) / (bx1 - bx0)
    nv = 1.0 - (v - by0) / (by1 - by0)
    return np.stack([nu, nv], -1).astype(np.float32), {"box_in_atlas": [int(bx0), int(by0), int(bx1), int(by1)], "atlas": [int(W), int(H)]}


def landmark_sets():
    G = gt.gnm()
    d3 = np.load(SET / "landmark_sets" / "denselm_v3.npz", allow_pickle=False)
    mp = json.loads((SET / "landmark_sets" / "mp_gnm.json").read_text())["points"]
    nV = len(G["T"])
    sets = {}
    ids = d3["gnm"].astype(int)
    W3 = np.zeros((len(ids), 3)), np.stack([ids, ids, ids], 1)
    reg = d3["region"].astype(str)
    sets["dl3"] = {"tri": np.stack([ids, ids, ids], 1), "w": np.tile([1.0, 0, 0], (len(ids), 1)), "form": np.isin(reg, ("lip_border_upper", "lip_border_lower")),
                   "model_only": np.isin(reg, ("eyeball", "teeth_upper", "teeth_lower", "tongue")), "region": reg}
    sets["mp"] = {"tri": np.array([p["tri"] for p in mp], int), "w": np.array([p["w"] for p in mp], float), "form": np.array([p.get("set") == "lip_outer" for p in mp]),
                  "model_only": np.zeros(len(mp), bool), "region": np.array([str(p.get("region")) for p in mp]), "mp_id": np.array([p["mp"] for p in mp], int)}
    return sets, G["WL"]


if __name__ == "__main__":
    pose = sys.argv[1]
    subject = pose.split("-")[0]
    out = SET / subject / pose
    (out / "photos").mkdir(parents=True, exist_ok=True)
    (out / "masks").mkdir(exist_ok=True)
    scan = gt.load_scan(pose)
    T = gt.load_sim(gt.WORK / pose / "T_rig.json")
    Tj = json.loads((gt.WORK / pose / "T_rig.json").read_text())
    fits = {n: json.loads((gt.WORK / pose / f"fit_{n}.json").read_text()) for n in ("p1b3", "p1eb3")}
    sim = lambda j: (j["S"]["s"], np.asarray(j["S"]["R"]), np.asarray(j["S"]["t"]))
    skin_v = np.load(gt.WORK / pose / "skin_v.npy")
    G = gt.gnm()
    # ---- the fitted face (identity + expression) in the scan's frame and in the rig's
    fe = fits["p1eb3"]
    Vg = gt.verts(np.asarray(fe["c"]), np.asarray(fe["e"]))
    Vscan = gt.apply(gt.inverse(sim(fe)), Vg)
    Vrig = gt.apply(T, Vscan)
    Lrig = G["WL"] @ Vrig
    ctr = Lrig[[36, 45, 48, 54, 30]].mean(0)
    Si = gt.compose(T, gt.inverse(sim(fe)))                    # GNM world -> rig
    fwd, left, up = (np.asarray(Si[1]) @ v for v in (np.array([0.0, -1, 0]), np.array([1.0, 0, 0]), np.array([0.0, 0, 1])))
    # ---- label quality: the fit's distance to the scan at each GNM vertex (skin only)
    sc = gt.Surface(scan["V"], scan["F"])
    Q, d, fi, _ = sc.closest(Vscan)
    skin_f = skin_v[scan["F"]].all(1)
    qv = np.where(skin_f[fi] & (d < 0.02) & G["ext"], d * 1000, np.nan)
    # ---- the whole scan as the occluder
    body = np.load(gt.WORK / pose / "body.npz")
    Vb, Fb = gt.apply(T, body["V"].astype(float)), body["F"].astype(np.int64)
    near = np.linalg.norm(Vb - ctr, axis=1) < 0.75             # hands, phones, collars near the head; the rest cannot hide it
    Vo, Fo, _ = gt.submesh(Vb, Fb, near)
    sets, WL = landmark_sets()
    X = {"lm68": Lrig}
    for k, s in sets.items():
        X[k] = (s["w"][:, :, None] * Vrig[s["tri"]]).sum(1)
    qual = {"lm68": WL @ np.nan_to_num(qv, nan=0.0) / np.maximum(WL @ np.isfinite(qv), 1e-9)}
    qual["lm68"][(WL @ np.isfinite(qv)) < 0.5] = np.nan
    form = {"lm68": np.isin(np.arange(68), np.arange(48, 60))}
    for k, s in sets.items():
        q = (s["w"] * qv[s["tri"]]).sum(1)
        q[s["model_only"]] = np.nan
        qual[k], form[k] = q, s["form"]
    # ---- photos
    C = hsrd.cams(pose)
    box3 = ctr + np.array([[a * 0.095, b * 0.095, c * 0.095] for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)])
    crop3 = ctr + np.stack([a * 0.24 * left + b * 0.24 * fwd + c * up for a in (-1, 1) for b in (-1, 1) for c in (-0.34, 0.20)])
    cams, names, lab = {}, [], {k: {"xy": [], "vis": []} for k in X}
    for n, c in sorted(C.items()):
        if c["image"] is None:
            continue
        with Image.open(c["image"]) as im0:
            size = im0.size
            Pb, zb = hsrd.project(c, box3, size)
            if not ((zb > 0).all() and (Pb[:, 0] > 0).all() and (Pb[:, 0] < size[0]).all() and (Pb[:, 1] > 0).all() and (Pb[:, 1] < size[1]).all()):
                continue
            Pc, _ = hsrd.project(c, crop3, size)
            x0, y0 = int(max(np.floor(Pc[:, 0].min()), 0)), int(max(np.floor(Pc[:, 1].min()), 0))
            x1, y1 = int(min(np.ceil(Pc[:, 0].max()), size[0])), int(min(np.ceil(Pc[:, 1].max()), size[1]))
            im0.convert("RGB").crop((x0, y0, x1, y1)).save(out / "photos" / f"{n}.jpg", quality=95, subsampling=0)
        mk = hsrd.mask_path(c["image"])
        if mk is not None:
            with Image.open(mk) as m0:
                m0.convert("L").crop((x0, y0, x1, y1)).save(out / "masks" / f"{n}.png")
        m = max(size)
        f = c["f35"] / 36.0 * m
        dv = c["C"] - ctr
        dist = float(np.linalg.norm(dv))
        # visibility: the scan's depth through a pinhole camera turned onto the head (2 px / mm, 0.6 x 0.7 m)
        hv = hsrd.head_view(c, size, ctr, out_size=(1200, 1400), px_per_m=2000.0)
        pc = hsrd.pipeline_cam(hv, (1.0, np.eye(3), np.zeros(3)))
        zbuf = rast.visibility(Vo, Fo, pc)["z"]
        for k, Xk in X.items():
            P, z = hsrd.project(c, Xk, size)
            xy = P - [x0, y0]
            Xc, Pv = rast.cam_points(pc, Xk)
            pi = np.clip(np.round(Pv - 0.5).astype(int), 0, [1199, 1399])
            zz = zbuf[pi[:, 1], pi[:, 0]]
            inside = (xy[:, 0] >= 0) & (xy[:, 0] < x1 - x0) & (xy[:, 1] >= 0) & (xy[:, 1] < y1 - y0) & (Pv[:, 0] >= 0) & (Pv[:, 0] < 1200) & (Pv[:, 1] >= 0) & (Pv[:, 1] < 1400)
            vis = inside & (Xc[:, 2] <= zz + 0.004)
            lab[k]["xy"].append(xy.astype(np.float32))
            lab[k]["vis"].append(vis)
        cams[n] = {"file": f"photos/{n}.jpg", "mask": f"masks/{n}.png" if mk is not None else None, "box": [x0, y0, x1, y1], "original_size": list(size),
                   "size": [x1 - x0, y1 - y0], "f": f, "cx": size[0] / 2 + c["ppu"] * m - x0, "cy": size[1] / 2 + c["ppv"] * m - y0, "k": c["k"].tolist(),
                   "distortion": "brown3 radial on x = X / Z: x_d = x (1 + k1 r^2 + k2 r^4 + k3 r^6); pixel = f x_d + (cx, cy)",
                   "R": c["R"].tolist(), "C": c["C"].tolist(), "az": float(np.degrees(np.arctan2(dv @ left, dv @ fwd))), "el": float(np.degrees(np.arcsin(dv @ up / dist))),
                   "dist_m": dist, "px_per_mm": f / dist / 1000.0, "roll_deg": float(np.degrees(np.arctan2(-(c["R"] @ up)[0], -(c["R"] @ up)[1]))),
                   "source_file": c["image"].name}
        names.append(n)
    (out / "cameras.json").write_text(json.dumps({"pose": pose, "frame": "the rig's (the .xmp calibration's), metres", "cameras": cams,
                                                  "T_scan_to_rig": {"s": 1.0, "R": np.asarray(T[1]).tolist(), "t": np.asarray(T[2]).tolist(), "silhouette_rms_mm": Tj.get("rms_mm"),
                                                                    "silhouette_median_px_at_1.5px_per_mm": Tj.get("median_px")},
                                                  "head": {"centre": ctr.tolist(), "forward": fwd.tolist(), "left": left.tolist(), "up": up.tolist()},
                                                  "az": "+ = the camera stands on the subject's LEFT; 0 = in front; el + = above", "roll_deg": "the head's up direction in the photo, degrees from the picture's up (some rig cameras are mounted on their side)"}, indent=0))
    np.savez_compressed(out / "labels.npz", photos=np.array(names), **{f"{k}_xy": np.stack(v["xy"]) for k, v in lab.items()}, **{f"{k}_vis": np.stack(v["vis"]) for k, v in lab.items()},
                        **{f"{k}_q": qual[k].astype(np.float32) for k in X}, **{f"{k}_form": form[k] for k in X}, **{f"{k}_X": X[k].astype(np.float32) for k in X},
                        dl3_region=sets["dl3"]["region"], mp_region=sets["mp"]["region"], mp_id=sets["mp"]["mp_id"], gnm_vertices_rig=Vrig.astype(np.float32))
    # ---- the scan's head
    tex = next(iter((gt.ROOT / f"hsrd100/x/{pose}/scan").glob("*_diffuse.png")), None)
    extra = {}
    if tex is not None and "FUV" in scan:
        fuv, tinfo = texture_cut(tex, scan["FUV"], out / "scan_head_texture.png")
        extra = {"FUV": fuv}
    np.savez_compressed(out / "scan_head.npz", V=scan["V"].astype(np.float32), F=scan["F"].astype(np.int32), C=scan["C"].astype(np.float32), skin=skin_v, **extra)
    Vd, Fd, Cd = decimate(scan["V"], scan["F"], scan["C"])
    np.savez_compressed(out / "scan_head_dec.npz", V=Vd, F=Fd, C=Cd)
    face = fits["p1b3"]["table"]["face"]["mean"]
    (out / "fit.json").write_text(json.dumps({"pose": pose, "frame": "S carries the SCAN's frame into GNM world (Z up, the face looks along -Y, left = +X; metres): x_gnm = s R x_scan + t",
                                              "identity": {k: fits["p1b3"][k] for k in ("c", "S", "table", "c_off", "c_max", "measures")},
                                              "identity_expression": {k: fits["p1eb3"][k] for k in ("c", "e", "enames", "S", "table", "c_off", "c_max")},
                                              "face_mean_mm": face, "face_p90_mm": fits["p1b3"]["table"]["face"]["p90"], "flag": bool(face > 1.0), "info": scan["info"]}))
    seen = np.stack(lab["dl3"]["vis"])
    az = np.array([cams[n]["az"] for n in names])
    bins = {"front": int((np.abs(az) < 30).sum()), "three-quarter": int(((np.abs(az) >= 30) & (np.abs(az) < 70)).sum()), "profile": int(((np.abs(az) >= 70) & (np.abs(az) < 115)).sum()),
            "rear": int((np.abs(az) >= 115).sum())}
    summary = {"pose": pose, "photos": len(names), "bins": bins, "face_px": float(np.median([150 * cams[n]["px_per_mm"] for n in names])) if names else 0.0,
               "face_px_range": [float(min(150 * cams[n]["px_per_mm"] for n in names)), float(max(150 * cams[n]["px_per_mm"] for n in names))] if names else None,
               "fit_face_mean_mm": face, "fit_face_p90_mm": fits["p1b3"]["table"]["face"]["p90"], "fit_expr_face_mean_mm": fits["p1eb3"]["table"]["face"]["mean"], "flag": bool(face > 1.0),
               "dl3_visible_per_photo": float(seen.sum(1).mean()) if len(seen) else 0.0, "register_rms_mm": Tj.get("rms_mm"),
               "labels_with_quality_under_1mm": float(np.mean(np.nan_to_num(qual["dl3"], nan=9) < 1.0)),
               "bytes": int(sum(p.stat().st_size for p in out.rglob("*") if p.is_file()))}
    (out / "summary.json").write_text(json.dumps(summary))
    print(json.dumps(summary))
