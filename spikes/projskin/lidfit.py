"""lidfit.py <model with the references> <src model> <dst>: the upper-lid fold in MESH space (base.head.lid_fold) set from the
front picture's lid read (lidfold.read_lid: the visible platform = lash line -> fold line, at three columns per eye) and saved
on a copy. crease = the anatomical crease height by sex (Price 2009: women 7.5, men 6.2 mm), overhang = crease - the visible
platform (a hooded lid shows little platform: a large overhang), per column, per side. LIGHT. Prints the read and what was set."""
import copy, os, sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, lidfold, skin, store

ref, src, dst = sys.argv[1:4]
rj = bi._refs(ref)
vi = bi._front(rj)
v = rj["views"][vi]
img = Image.open(v["image"]).convert("RGB")
P = bi.detect_view(img, v)
rd = lidfold.read_lid(img, P)
spec = copy.deepcopy(store.load(src))
p = skin.params(spec)
# the fold sits a little above the line the picture shows: the drape over it grows with age (dermatochalasis; Price 2009:
# platform show falls with age). crease = the visible platform + the overhang, per column. (First rule: crease = the
# sex norm and overhang = norm - platform: a 2.5 mm roll on a 22-year-old with a crisp crease.)
ag = float(np.clip((p["age"] - 25.0) / 40.0, 0.0, 1.0))
ov0 = 0.5 + 2.0 * ag
cfg = {"thick": round(0.7 + 0.8 * ag, 2)}
for s_, key in ((0, "R"), (1, "L")):      # read_lid: subject's right first; columns inner -> outer
    tps = [c.get("tps") for c in rd[s_]]
    dark = [c.get("dark") for c in rd[s_]]
    print(f"eye {key}: visible platform mm (inner, middle, outer) {[None if t is None else round(float(t), 2) for t in tps]}, line darkness {[None if d is None else round(float(d), 2) for d in dark]}")
    ok = [t for t in tps if t is not None and np.isfinite(t)]
    if not ok:
        continue
    fill = float(np.median(ok))
    t3 = [float(t) if t is not None and np.isfinite(t) else fill for t in tps]
    # HOODING from the read: where the visible platform shrinks toward the outer corner, the drape covers it (a
    # hooded outer lid); plus the age term, the outer third first
    ov = [round(ov0 * w + max(0.0, t3[0] - t), 2) for w, t in zip((0.8, 1.0, 1.3), t3)]
    cfg[key] = {"crease": [round(t + o, 2) for t, o in zip(t3, ov)], "overhang": ov}
# THE CREASE'S PATH from the front picture, per chain ANGLE of the wrap (the photographs' creases run 4-11 mm past the
# outer canthus; set by heights along the lid alone ours stopped at the corner): each chain's radial line, projected,
# meets the traced crease; the distance along it is that chain's crease height (mm)
try:
    import crease_trace as ct
    from hifipushie import gnm_fold as gf, humanfit, likeness as lk, onemesh
    cam = rj["cameras"][vi]
    st = humanfit.state(bi.view_base(spec["base"], rj, vi))
    L68 = st["L"]
    M = humanfit.project(cam, L68[:70])
    mmpx = 1000.0 * float(np.linalg.norm(L68[36] - L68[39])) / float(np.linalg.norm(M[36] - M[39]))
    Pp = np.asarray(P, float)[:, :2]
    resp = ct.ridge(img, mmpx)
    tpl = st["tpl"]
    fid = np.asarray(tpl["fid"])
    gidall = np.asarray(onemesh.asset()["gnm_id"])
    gid = np.where(fid < len(gidall), gidall[np.clip(fid, 0, len(gidall) - 1)], -1)
    rows = {int(gg): i for i, gg in enumerate(gid) if gg >= 0}
    ch, ang = gf.chains_wrap()
    bags = []
    UPL = ((33, 246, 161, 160, 159, 158, 157, 173, 133), (263, 466, 388, 387, 386, 385, 384, 398, 362))
    for s_, key in ((0, "R"), (1, "L")):
        lid = Pp[list(UPL[s_])]
        outer_, inner_ = lid[0], lid[-1]
        ex = (outer_ - inner_) / np.linalg.norm(outer_ - inner_)
        upv = np.array([ex[1], -ex[0]])
        if upv[1] > 0:
            upv = -upv
        cen = 0.5 * (outer_ + inner_)
        tps_mid = cfg.get(key, {}).get("crease", [6.0] * 3)[1] - cfg.get(key, {}).get("overhang", [0.5] * 3)[1]
        # (never within 1.8 mm of the lash line: the lash line is the strongest dark line there and was traced instead)
        bp, best = ct.seed_near(resp, lid[len(lid) // 2], upv, ex, mmpx, lo=max(1.8, tps_mid - 1.0), hi=tps_mid + 3.0)
        tr = ct.follow(resp, bp, best, ex, mmpx, cen)
        # the chains of THIS eye (left chains for x > 0 on the head)
        cands = []
        for ids in (ch, gf.topo()["mir"][ch]):
            r0 = [rows.get(int(x)) for x in ids[:, 0]]
            if None in r0:
                continue
            pts0 = np.asarray(tpl["P"])[r0]
            cands.append((ids, pts0))
        ids, pts0 = min(cands, key=lambda c: np.linalg.norm(humanfit.project(cam, c[1]).mean(0) - cen))
        out = []
        cross_px = []
        from scipy.spatial import cKDTree
        tree = cKDTree(tr)
        for j in range(len(ids)):
            a_, b_ = rows.get(int(ids[j, 0])), rows.get(int(ids[j, 10]))
            if a_ is None or b_ is None:
                continue
            p0, p1 = humanfit.project(cam, np.asarray(tpl["P"])[[a_, b_]])
            dr = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-9)
            far = abs(ang[j]) > 60.0                     # round the corners the crease runs far out along the chain (his ~11 mm)
            hs = np.arange(max(1.5, tps_mid - 1.5), tps_mid + (12.0 if far else 6.0), 0.1)    # (the lash line and the lid edge lie below)
            dd, _ = tree.query(p0[None] + (hs / mmpx)[:, None] * dr[None])
            k = int(np.argmin(dd))
            if dd[k] * mmpx < 0.5:   # the TRUE crossing: the ray's nearest approach to the traced line
                cross_px.append(p0 + (hs[k] / mmpx) * dr)
                # the line a picture shows is the hood's EDGE: the crease (our slit) sits above it by the overhang there
                ovl = cfg.get(key, {}).get("overhang", [0.5] * 3)
                ov_here = float(np.interp(ang[j], [-60.0, 0.0, 90.0], ovl))
                out.append([round(float(ang[j]), 1), round(float(hs[k]) + ov_here, 2)])
        # THE TAIL: the traced crease PAST the outer canthus (the chains radiate from the corner and miss a crease running
        # on laterally: an older test head's runs ~11 mm out, ours stopped ~5 mm out), lifted onto the head as a path of
        # GNM vertices (this eye's skin outside the margin, within 30 mm of the eye), outward, at most 14 mm past
        sd = 1 if ids is ch else -1
        ring_s = gf.topo()["ring"] if sd == 1 else gf.topo()["ring"][gf.topo()["mir"]]
        g_ = gf.gc.gnm()
        skin_ = np.asarray(g_["groups"]["skin"]) > 0.5
        allg = np.array(sorted(rows))
        Pall = np.asarray(tpl["P"])[[rows[int(x)] for x in allg]]
        ectr = np.asarray(tpl["P"])[[rows[int(x)] for x in ids[:, 0] if int(x) in rows]].mean(0)
        okc = skin_[allg] & (ring_s[allg] >= 1) & (np.linalg.norm(Pall - ectr, axis=1) < 0.03)
        cg, cP = allg[okc], Pall[okc]
        c2 = humanfit.project(cam, cP)
        past = ((tr - outer_) @ ex) * mmpx
        # the tail STARTS where the fold's own chains stop (1 mm overlap to blend): started at the canthus it ran along
        # the fold's roll over the outer third (a crumpled pale "crust") and dented the corner (a pale blob)
        fold_end = max([float(((q - outer_) @ ex) * mmpx) for q in cross_px] + [0.5])
        sel = np.flatnonzero((past > max(0.5, fold_end - 1.0)) & (past < 14.0))
        tail_ids = []
        if len(sel) and float(past[sel].max()) < fold_end + 2.0:   # the trace ends within the fold's own reach: no tail
            sel = sel[:0]
        if len(sel) >= 4:
            sel = sel[np.argsort(past[sel])]
            t2 = cKDTree(c2)
            for q in tr[sel]:
                dq, jq = t2.query(q)
                if dq * mmpx < 1.5 and (not tail_ids or tail_ids[-1] != int(cg[jq])):
                    tail_ids.append(int(cg[jq]))
            ry = [resp[int(round(q[1])), int(round(q[0]))] for q in tr[sel]]
            ag_ = float(np.clip((p["age"] - 25.0) / 40.0, 0.0, 1.0))
            tdep = round((0.35 + 0.45 * ag_) * float(np.clip(np.mean(ry) / max(best, 1e-9), 0.4, 1.0)), 2)
            if len(tail_ids) >= 4:
                cfg.setdefault(key, {})["tail"] = {"path": tail_ids, "depth": tdep}
                print(f"eye {key}: crease TAIL {fold_end - 1.0:.1f}..{float(past[sel].max()):.1f} mm past the outer canthus (the fold's chains end at {fold_end:.1f}), {len(tail_ids)} vertices, depth {tdep} mm")
        # THE BAG: the lower-lid bag's lower edge (the lid-cheek junction / the bag's crease) traced under the lower lid's
        # middle, 4-16 mm below the lash line; its height sets headage's eye_bag height, its strength against the upper
        # crease's (x age) the bag's amount; the tear trough (cheek_flat) follows it on an older face
        LOW = (145, 374)
        lowp = Pp[LOW[s_]]
        # (a BROAD shadow line, at ~2 mm: at the crease's 0.8 mm the lower lid's own fine lines won, 2.5 mm under the lashes)
        respb = ct.ridge(img, mmpx * 0.8 / 2.0)
        bbp, bbest = ct.seed_near(respb, lowp, -upv, ex, mmpx, lo=4.0, hi=16.0)
        btr = ct.follow(respb, bbp, bbest, ex, mmpx, cen) if bbp is not None else None
        best_b = float(ct.seed_near(respb, lid[len(lid) // 2], upv, ex, mmpx, lo=max(1.8, tps_mid - 1.0), hi=tps_mid + 3.0)[1])
        if bbp is not None:
            hb_mm = float((bbp - lowp) @ (-upv)) * mmpx
            wid_mm = float(np.linalg.norm(outer_ - inner_)) * mmpx
            ratio = float(bbest / max(best_b, 1e-9))   # against the upper crease at the same scale
            ag_ = float(np.clip((p["age"] - 25.0) / 40.0, 0.0, 1.0))
            bags.append({"h": hb_mm, "wid": wid_mm, "ratio": ratio, "len": float(len(btr)) * 0.5 if btr is not None else 0.0, "ag": ag_})
            print(f"eye {key}: BAG edge {hb_mm:.1f} mm under the lash line, strength {ratio:.2f} x the crease's, traced {bags[-1]['len']:.0f} mm")
        if os.environ.get("LIDFIT_DEBUG"):
            from PIL import ImageDraw
            im2 = img.copy(); dr2 = ImageDraw.Draw(im2)
            dr2.line([tuple(q) for q in tr], fill=(255, 0, 0), width=2)
            for j in range(len(ids)):
                a_, b_ = rows.get(int(ids[j, 0])), rows.get(int(ids[j, 10]))
                if a_ is not None and b_ is not None:
                    p0, p1 = humanfit.project(cam, np.asarray(tpl["P"])[[a_, b_]])
                    dr2.line([tuple(p0), tuple(p0 + (p1 - p0) / np.linalg.norm(p1 - p0) * 14 / mmpx)], fill=(0, 255, 0), width=1)
            if btr is not None:
                dr2.line([tuple(q) for q in btr], fill=(255, 220, 0), width=2)
            if tail_ids:
                tq = humanfit.project(cam, np.asarray(tpl["P"])[[rows[i_] for i_ in tail_ids]])
                dr2.line([tuple(q) for q in tq], fill=(0, 80, 255), width=2)
            box = (int(cen[0] - 25 / mmpx), int(cen[1] - 25 / mmpx), int(cen[0] + 25 / mmpx), int(cen[1] + 25 / mmpx))
            im2.crop(box).resize((600, 600)).save(os.environ["LIDFIT_DEBUG"] + f"_{key}.png")
        if len(out) >= 4:
            cfg.setdefault(key, {})["crease_by_angle"] = out
            # the wrap reaches as far round the outer corner as the crease was traced (+ its fade)
            cfg[key]["wrap"] = round(float(np.clip(max(o[0] for o in out) - 90.0 + 25.0, 15.0, 70.0)), 1)
            # the fold's last ring: far enough out for the traced crease (rings ~0.55 mm apart near the eye, wider out;
            # at 10 the fold stopped ~5 mm out round the outer corner whatever the trace said)
            cfg["last"] = int(np.clip(10 + (max(o[1] for o in out) - 6.0) / 0.9, 10, 14))
            print(f"eye {key}: crease traced on {len(out)} of {len(ids)} chains, angles {out[0][0]}..{out[-1][0]} deg, heights {out[0][1]}..{max(o[1] for o in out)} mm")
except Exception as e:  # noqa: BLE001
    print("crease path NOT TRACED:", str(e)[:200])
spec["base"]["head"]["lid_fold"] = cfg
if bags and os.environ.get("LIDFIT_BAGS", "1") == "1":
    # bag height: headage puts the bag's crease at 1.25 x 0.2 eye widths under the margin; amount (m): faint on a young
    # face, ~1.5 mm on a strong older bag; the trough beside it (cheek_flat) only past ~35
    h_ = float(np.median([b["h"] for b in bags]))
    wd_ = float(np.median([b["wid"] for b in bags]))
    r_ = float(np.clip(np.median([b["ratio"] for b in bags]), 0.0, 1.5))
    ag_ = bags[0]["ag"]
    amt = (0.25 + 1.25 * ag_) * float(np.clip(r_, 0.2, 1.2)) / 1000.0
    shp = dict(spec["base"]["head"].get("shape") or {})
    shp["eye_bag"] = {"amount": round(amt, 5), "crease": round(0.4 + 0.3 * ag_, 2), "height": round(float(np.clip(h_ / (1.25 * 0.2 * wd_), 0.6, 2.0)), 2)}
    if ag_ > 0.25:
        shp["cheek_flat"] = {"amount": round(0.6 * amt * ag_ / 0.5, 5)}
    spec["base"]["head"]["shape"] = shp
    print("head.shape bags:", {k: shp[k] for k in ("eye_bag", "cheek_flat") if k in shp})
rj2 = copy.deepcopy(bi._refs(src))
if rj2.get("blockin"):
    rj2["blockin"] = {**rj2["blockin"], "root": dst}
bi._save(dst, spec, f"upper-lid fold in mesh space from {ref}'s front picture", rj2)
print(dst, "base.head.lid_fold =", cfg)
