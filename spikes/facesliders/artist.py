"""artist.py: faces6, the ARTIST BLOCK-IN LOOP's tools (coordinator / Joe: "an artist would be able to know how to get
closer"; the model is the artist: look, name the biggest form difference in masses and planes, a small whole-face
step, keep it only if the whole face reads closer).

  artist.py look <model> <out png> [ref model]
      per view (front, 3/4, profile; the REF model's fitted cameras, default f6_M_mace): photo | clay under her
      fitted light (hair cap, 2 mm brows) | 50 % overlay | outline difference (her face oval / profile contour red,
      the clay's detector oval / silhouette green, on the photo) | squinted photo | squinted clay (Gaussian SQUINT_MM,
      grey: only the big masses read). Prints the five targets (mtable groups, pass counts + misses).
  artist.py step <src> <dst> name=+0.3 ... : <dst> = <src> moved along named whole-face directions: humanmacro's
      (free mode: the population's conditional mean per +1 sd, so the face stays whole), sex_gnm_dir, eth_dir0..2
      (in sd of the sampler's spread), or body / head keys (weight=, dimorphism=, gnm_base=: SET, not added).
      Appends to <dst>/artist_log.json.
"""
import copy
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import wholeclay as WC
from hifipushie import humanfit, humanmacro as hmac, likeness, store

T = int(os.environ.get("T", "330"))
SQUINT_MM = float(os.environ.get("SQUINT_MM", "9"))
F = os.environ.get("F", "/mnt/data/hifipushie/faces6")


def _dir(name):
    if name.endswith("!") and name[:-1] in hmac.NAMES:   # HELD: this macro alone, every other macro kept (the
        # pseudo-inverse column): philtrum -0.5 in free mode also shortened the chin 1.6 mm (the population couples them)
        d = np.zeros(170)
        d[:hmac.K] = hmac.direction(name[:-1], held=True)
        return d
    if name in hmac.NAMES:
        d = np.zeros(170)
        d[:hmac.K] = hmac.direction(name)
        return d
    if name.startswith("nd:"):   # faces6 newdirs.npz: the vocabulary gaps' coupled directions (per +1 sd)
        z = np.load(f"{F}/newdirs.npz")
        return z["dirs"][:, [str(x) for x in z["names"]].index(name[3:])]
    if name == "sex_gnm_dir":
        cv = np.load(f"{F}/cvae_stats.npz")
        d = cv["m_m"] - cv["m_f"]
        return d / np.linalg.norm(d)
    if name.startswith("eth_dir"):
        e = np.load(f"{F}/ethstats.npz")
        k = int(name[-1])
        return e["dirs"][:, k] * float(e["sd"][k])
    raise KeyError(name)


def ident(sp):
    v = np.zeros(170)
    for k, x in (sp["base"]["head"].get("identity") or {}).items():
        if k.startswith("head_"):
            v[int(k.split("_")[1])] = float(x)
    return v


def step(src, dst, moves):
    sp = copy.deepcopy(store.load(src))
    c = ident(sp)
    log = []
    for k, v in moves.items():
        if k in ("weight",):
            sp["base"]["body"][k] = float(v)
        elif k in ("dimorphism", "gnm_base"):
            sp["base"]["head"][k] = float(v)
        elif k in ("lid_upper", "lid_lower", "smile", "brows"):   # base.head.pose (m; SET): the lids' state as GNM's
            # eye-region expression (base.pose_expression), e.g. lid_upper -0.0012 = the upper lid 1.2 mm up
            sp["base"]["head"].setdefault("pose", {})[k] = float(v)
        else:
            c = c + float(v) * _dir(k)
        log.append([k, float(v)])
    sp["base"]["head"]["identity"] = {f"head_{i:03d}": round(float(x), 5) for i, x in enumerate(c)}
    d = store.HOME / dst
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp, indent=1))
    shutil.copy(store.HOME / src / "human_refs.json", d / "human_refs.json")
    hist = []
    if (store.HOME / src / "artist_log.json").exists():
        hist = json.loads((store.HOME / src / "artist_log.json").read_text())
    hist.append({"from": src, "to": dst, "moves": log, "c_norm": round(float(np.linalg.norm(c)), 3)})
    (d / "artist_log.json").write_text(json.dumps(hist, indent=1))
    rd = hmac.read(c[:hmac.K])
    print(f"{dst}: |c| {np.linalg.norm(c):.2f}; macros now " + json.dumps({k: round(rd[k], 2) for k, _ in log if k in rd}))


def _oval_poly(img):
    P = likeness.detect([img])[0]
    return None if P is None else np.asarray(P, float)[likeness.OVAL, :2]


def look(m, out, ref="f6_M_mace"):
    from noserender import lit_render
    import outl
    refs = json.loads((store.HOME / ref / "human_refs.json").read_text())
    st = humanfit.state(store.load(m)["base"])
    mesh = likeness.model_mesh_from_state(st)
    mesh["C"] = WC.haircap(mesh, st)
    if os.environ.get("EYE_PRES", "1") == "1":
        WC.eye_presentation(mesh)
    ref_st = humanfit.state(store.load(ref)["base"])
    cols = ["photo", f"{m} (her light)", "50% overlay", "outline: photo red / clay green", "squint photo", "squint clay"]
    VIEWS = list(range(len(refs["views"])))
    sheet = Image.new("RGB", (T * len(cols), (T + 18) * 3 + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    for i, vi in enumerate(VIEWS):
        v, cam = refs["views"][vi], refs["cameras"][vi]
        img = Image.open(v["image"]).convert("RGB")
        P = humanfit.project(cam, ref_st["L"])
        cc = 0.5 * (P.min(0) + P.max(0))
        side = 1.45 * float(np.max(P.max(0) - P.min(0)))
        box = (cc[0] - side / 2, cc[1] - side * 0.56, cc[0] + side / 2, cc[1] + side * 0.44)
        px = 2 * T
        # register like an artist lays a tracing over a photo: at the EYES (and nasion), a 2D shift only (the fitted
        # camera belongs to another face; registering on the whole outline would hide the very differences we look for)
        Lm = humanfit.project(cam, st["L"])
        if abs(float(v.get("yaw", 0))) < 70:
            Pd = likeness.detect([img])[0]
            if Pd is None:   # (painted concept art the detector misses: the clicked 68 where given)
                pts = v.get("points") or {}
                Pd = None
                a_ph = np.mean([pts[k] for k in ("lm36", "lm39", "lm42", "lm45", "lm27") if k in pts], 0)
            else:
                a_ph = np.asarray(Pd, float)[[33, 133, 263, 362, 168], :2].mean(0)
            a_md = Lm[[36, 39, 42, 45, 27]].mean(0)
        else:
            pts = v["points"]
            a_ph = np.mean([pts["nose_bridge"], pts["eye_outer.L"]], 0)
            a_md = Lm[[27, 45]].mean(0)
        sh = np.asarray(a_ph, float) - a_md
        pbox = (box[0] + sh[0], box[1] + sh[1], box[2] + sh[0], box[3] + sh[1])
        ph = img.crop(tuple(int(round(b)) for b in pbox)).resize((px, px), Image.LANCZOS)
        cl, _, ps = lit_render(mesh, cam, img, box=box, px=px)
        k = px / side
        if abs(float(v.get("yaw", 0))) < 70 and os.environ.get("HER_BROWS", "1") == "1" and Pd is not None:
            cl = WC.draw_photo_brows(cl.convert("RGB"), Pd, lambda Q: [((q[0] - pbox[0]) * k, (q[1] - pbox[1]) * k) for q in Q])
        else:
            cl = WC.draw_brows(cl.convert("RGB"), mesh, cam, box, k)
        ov = Image.blend(ph, cl, 0.5)
        ol = ph.copy().convert("L").convert("RGB")
        d = ImageDraw.Draw(ol)
        to = lambda Q: [((q[0] - box[0]) * k, (q[1] - box[1]) * k) for q in Q]  # noqa: E731
        to_ph = lambda Q: [((q[0] - pbox[0]) * k, (q[1] - pbox[1]) * k) for q in Q]  # noqa: E731
        if abs(float(v.get("yaw", 0))) < 70:
            Pp = _oval_poly(img)
            # the clay's oval: the detector on the clay render at the picture's pixels (the same reader as the photo's)
            full, _, _ = lit_render(mesh, cam, img)
            Pm = _oval_poly(full.convert("RGB"))
            if Pp is not None:
                d.line(to_ph(np.r_[Pp, Pp[:1]]), fill=(230, 30, 30), width=3)
            if Pm is not None:
                d.line(to(np.r_[Pm, Pm[:1]]), fill=(30, 200, 30), width=3)
        else:
            o = outl.profile_auto(v, step=3)
            d.line(to_ph(o), fill=(230, 30, 30), width=3)
            sil = (ps["part"] >= 0).astype(np.uint8) * 255
            e = Image.fromarray(sil).filter(ImageFilter.FIND_EDGES)
            ea = np.asarray(e) > 0
            olA = np.asarray(ol).copy()
            olA[ea] = (30, 200, 30)
            ol = Image.fromarray(olA)
        mmpx = likeness._mm_per_px(cam, mesh["L"][27:48])
        sg = SQUINT_MM / mmpx * k
        sq = lambda im: im.convert("L").filter(ImageFilter.GaussianBlur(sg)).convert("RGB")  # noqa: E731
        for j, im in enumerate((ph, cl, ov, ol, sq(ph), sq(cl))):
            sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, 18 + i * (T + 18)))
    sheet.save(out)
    print("wrote", out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "step":
        moves = dict(kv.split("=") for kv in sys.argv[4:])
        step(sys.argv[2], sys.argv[3], moves)
    elif cmd == "look":
        look(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "f6_M_mace")
